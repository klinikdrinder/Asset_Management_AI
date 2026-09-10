"""ChatGPT-subscription Codex CLI semantic interpretation provider.

This backend has the same narrow interface and locked 18-layer return contract as the
production Claude providers.  It invokes the locally authenticated Codex CLI, never the
OpenAI SDK or API-key authentication, and supplies prepared visual evidence through the
CLI's supported ``--image`` inputs.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .claude_provider import (
    LAYER_IDS,
    STATES,
    ClaudeConfigurationError,
    ClaudeResponseError,
    ClaudeSemanticProvider,
)

PROVIDER_NAME = "codex_cli"

USAGE_LIMIT_PATTERNS = (
    re.compile(r"usage limit", re.I),
    re.compile(r"(?:session|weekly|plan) limit", re.I),
    re.compile(r"limit (?:will )?reset", re.I),
    re.compile(r"you(?:'ve| have) hit .*limit", re.I),
    re.compile(r"quota.*(?:exceeded|exhausted)", re.I),
)
AUTH_PATTERNS = (
    re.compile(r"not logged in", re.I),
    re.compile(r"login required", re.I),
    re.compile(r"authentication (?:failed|error|required)", re.I),
    re.compile(r"credentials .*not .*found", re.I),
)
API_AUTH_ENV = (
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORGANIZATION", "OPENAI_ORG_ID",
    "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "AUTH_TOKEN", "BASE_URL",
)


class CodexCliUsageLimitError(RuntimeError):
    """The ChatGPT/Codex subscription allowance is temporarily exhausted."""


class CodexCliConfigurationError(ClaudeConfigurationError):
    """Codex CLI cannot be used safely through ChatGPT subscription authentication."""


@dataclass(frozen=True)
class CodexCliConfig:
    enabled: bool
    cli: str
    model: str = ""
    max_retries: int = 3
    timeout_seconds: float = 900.0

    @classmethod
    def from_environment(cls) -> "CodexCliConfig":
        enabled = os.getenv("KDI_EXTERNAL_AI_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        provider = os.getenv("KDI_SEMANTIC_PROVIDER", "").strip().lower()
        if provider != PROVIDER_NAME:
            raise CodexCliConfigurationError(
                f"unsupported production provider for the Codex CLI backend: {provider!r}"
            )
        cli = shutil.which("codex.exe") or shutil.which("codex.cmd") or shutil.which("codex")
        if enabled and not cli:
            raise CodexCliConfigurationError("the codex CLI is not installed on PATH")
        return cls(
            enabled=enabled,
            cli=cli or "",
            model=os.getenv("KDI_CODEX_MODEL", "").strip(),
            max_retries=int(os.getenv("KDI_CODEX_MAX_RETRIES", "3")),
            timeout_seconds=float(os.getenv("KDI_CODEX_TIMEOUT_SECONDS", "900")),
        )


class CodexCliSemanticProvider:
    """Runs schema-constrained multimodal inference through ChatGPT-authenticated Codex."""

    MAX_IMAGES_PER_REQUEST = ClaudeSemanticProvider.MAX_IMAGES_PER_REQUEST

    def __init__(self, config: CodexCliConfig | None = None) -> None:
        self.config = config or CodexCliConfig.from_environment()
        self.usage: list[dict[str, Any]] = []
        self.retry_events: list[dict[str, Any]] = []

    def discover_model(self) -> str:
        return self.config.model or "codex-default"

    @classmethod
    def _prompt(cls, evidence_text: str) -> str:
        return (
            "Act only as a schema-constrained visual media analysis backend. Do not use tools, "
            "inspect files other than the attached images, or discuss the task. "
            + ClaudeSemanticProvider._prompt(evidence_text)
        )

    @staticmethod
    def _validate(value: Any) -> dict[str, Any]:
        return ClaudeSemanticProvider._validate(value)

    @staticmethod
    def _schema() -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["narrative", "layers"],
            "properties": {
                "narrative": {"type": "string"},
                "layers": {
                    "type": "array", "minItems": 18, "maxItems": 18,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["layer_id", "state", "evaluated", "display_text", "evidence"],
                        "properties": {
                            "layer_id": {"type": "string", "enum": list(LAYER_IDS)},
                            "state": {"type": "string", "enum": sorted(STATES)},
                            "evaluated": {"type": "boolean", "const": True},
                            "display_text": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        }

    @staticmethod
    def _environment() -> dict[str, str]:
        env = os.environ.copy()
        for name in API_AUTH_ENV:
            env.pop(name, None)
        return env

    def _command(self, workdir: str, schema_path: str, image_paths: Sequence[str]) -> list[str]:
        command = [
            self.config.cli, "-a", "never", "exec", "--ephemeral", "--ignore-user-config",
            "--ignore-rules", "--skip-git-repo-check", "-s", "read-only", "-C", workdir,
            "--output-schema", schema_path, "--json",
        ]
        if self.config.model:
            command.extend(["-m", self.config.model])
        for path in image_paths:
            command.extend(["--image", path])
        command.append("-")
        return command

    @staticmethod
    def _parse_events(stdout: str) -> tuple[str, dict[str, Any]]:
        message = ""
        usage: dict[str, Any] = {}
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    message = str(item.get("text", ""))
            elif event.get("type") == "turn.completed":
                usage = event.get("usage") or {}
        if not message:
            raise ClaudeResponseError(
                f"codex CLI produced no final agent message: {' '.join(stdout.split())[:500]}"
            )
        return message, usage

    @staticmethod
    def _classify(text: str) -> None:
        if any(pattern.search(text) for pattern in USAGE_LIMIT_PATTERNS):
            raise CodexCliUsageLimitError(
                f"Codex subscription allowance reached: {' '.join(text.split())[:400]}"
            )
        if any(pattern.search(text) for pattern in AUTH_PATTERNS):
            raise CodexCliConfigurationError(
                f"Codex ChatGPT authentication failed: {' '.join(text.split())[:400]}"
            )

    def analyze(self, *, asset_id: str, evidence_text: str, image_bytes: bytes | None = None,
                images: Sequence[bytes] | None = None, request_type: str = "asset") -> dict[str, Any]:
        if not self.config.enabled:
            raise CodexCliConfigurationError("external AI is disabled; refusing production inference")
        frames = [x for x in (list(images) if images else []) if x]
        if image_bytes:
            frames.insert(0, image_bytes)
        if len(frames) > self.MAX_IMAGES_PER_REQUEST:
            step = len(frames) / self.MAX_IMAGES_PER_REQUEST
            frames = [frames[int(i * step)] for i in range(self.MAX_IMAGES_PER_REQUEST)]

        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                with tempfile.TemporaryDirectory(prefix="kdi-codex-cli-") as workdir:
                    root = Path(workdir)
                    schema_path = root / "semantic-output.schema.json"
                    schema_path.write_text(json.dumps(self._schema()), encoding="utf-8")
                    image_paths = []
                    for index, frame in enumerate(frames):
                        path = root / f"evidence-{index:02d}.jpg"
                        path.write_bytes(frame)
                        image_paths.append(str(path))
                    completed = subprocess.run(
                        self._command(workdir, str(schema_path), image_paths),
                        input=self._prompt(evidence_text), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", env=self._environment(), cwd=workdir,
                        timeout=self.config.timeout_seconds,
                    )
                combined = f"{completed.stdout}\n{completed.stderr}"
                self._classify(combined)
                if completed.returncode != 0:
                    raise ClaudeResponseError(
                        f"codex CLI exited {completed.returncode}: {' '.join(combined.split())[:500]}"
                    )
                text, usage = self._parse_events(completed.stdout)
                parsed = json.loads(text)
                result = self._validate(parsed)
                result.update({"provider": PROVIDER_NAME, "model": self.discover_model(),
                               "asset_id": asset_id, "image_count": len(frames)})
                self.usage.append({
                    "asset_id": asset_id, "request_type": request_type,
                    "model": self.discover_model(), "images": len(frames), "attempt": attempt + 1,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    **usage,
                })
                return result
            except (CodexCliUsageLimitError, CodexCliConfigurationError):
                raise
            except subprocess.TimeoutExpired as exc:
                last = ClaudeResponseError(
                    f"codex CLI timed out after {self.config.timeout_seconds}s"
                )
            except (ClaudeResponseError, json.JSONDecodeError) as exc:
                last = exc
            self.retry_events.append({"asset_id": asset_id, "status": "CLI", "attempt": attempt + 1})
            if attempt < self.config.max_retries:
                time.sleep((2 ** attempt) + random.uniform(0.0, 1.0))
        raise ClaudeResponseError(f"Codex CLI analysis failed after retries: {last}")
