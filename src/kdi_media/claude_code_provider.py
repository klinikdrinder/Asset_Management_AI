"""Claude Code (Max subscription) semantic interpretation provider.

Architecturally identical to :mod:`kdi_media.claude_provider`: it never writes semantic truth,
it receives evidence and returns the same strictly validated 18-layer package.  The only
difference is transport.  Instead of the Anthropic Messages API it drives the locally
authenticated Claude Code CLI in non-interactive mode, so inference is billed against the
operator's Claude Code subscription rather than API credits.

The subprocess environment deliberately drops ANTHROPIC_API_KEY so the CLI can never silently
fall back to metered API billing; `.env.local` is left untouched.  Evidence is handed over as
base64 image blocks through `--input-format stream-json`, which is the same content shape the
Messages API provider builds, so no tool access, no filesystem permission and no project
context is required for inference.
"""
from __future__ import annotations

import base64
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Sequence

from .claude_provider import (
    LAYER_IDS,
    STATES,
    ClaudeConfigurationError,
    ClaudeResponseError,
    ClaudeSemanticProvider,
)

__all__ = [
    "ClaudeCodeConfig",
    "ClaudeCodeConfigurationError",
    "ClaudeCodeSemanticProvider",
    "ClaudeCodeUsageLimitError",
    "LAYER_IDS",
    "STATES",
]

PROVIDER_NAME = "claude_code"

# Claude Code reports an exhausted subscription allowance as prose rather than a status code.
USAGE_LIMIT_PATTERNS = (
    re.compile(r"usage limit", re.I),
    re.compile(r"limit (?:will )?reset", re.I),
    re.compile(r"out of (?:your )?(?:weekly|session|5-hour) (?:usage|limit)", re.I),
    re.compile(r"upgrade to (?:a )?higher (?:usage )?limit", re.I),
)
# A missing or expired subscription login is a configuration fault, never a per-asset failure.
AUTH_PATTERNS = (
    re.compile(r"invalid api key", re.I),
    re.compile(r"please run /login", re.I),
    re.compile(r"not (?:logged in|authenticated)", re.I),
    re.compile(r"authentication (?:failed|error)", re.I),
    re.compile(r"oauth token (?:has )?expired", re.I),
)
# CREDIT_BALANCE_TOO_LOW proves the CLI reached metered API billing instead of the subscription.
API_BILLING_PATTERN = re.compile(r"credit balance is too low", re.I)


class ClaudeCodeUsageLimitError(RuntimeError):
    """Raised when the Claude Code subscription allowance is exhausted.

    This is not a per-asset failure: the queue must stop issuing new inference, keep every
    completed asset and cached response, and stay resumable once the allowance resets.
    """


# `ClaudeConfigurationError` is what the indexer already treats as a systemic, non-retryable
# configuration stop, so the Claude Code fault keeps that behaviour by inheriting from it.
class ClaudeCodeConfigurationError(ClaudeConfigurationError):
    """Raised when the Claude Code CLI is not safely usable for production inference."""


def _matches(patterns: Sequence[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


@dataclass(frozen=True)
class ClaudeCodeConfig:
    model: str
    enabled: bool
    cli: str
    max_retries: int = 3
    timeout_seconds: float = 900.0
    max_turns: int = 2

    @classmethod
    def from_environment(cls) -> "ClaudeCodeConfig":
        enabled = os.getenv("KDI_EXTERNAL_AI_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        provider = os.getenv("KDI_SEMANTIC_PROVIDER", "").strip().lower()
        if provider != PROVIDER_NAME:
            raise ClaudeCodeConfigurationError(
                f"unsupported production provider for the Claude Code backend: {provider!r}"
            )
        cli = (
            shutil.which("claude.cmd")
            or shutil.which("claude.exe")
            or shutil.which("claude")
        )
        if enabled and not cli:
            raise ClaudeCodeConfigurationError("the claude CLI is not installed on PATH")
        return cls(
            model=os.getenv("KDI_CLAUDE_CODE_MODEL", "sonnet").strip() or "sonnet",
            enabled=enabled,
            cli=cli or "",
            max_retries=int(os.getenv("KDI_CLAUDE_CODE_MAX_RETRIES", "3")),
            timeout_seconds=float(os.getenv("KDI_CLAUDE_CODE_TIMEOUT_SECONDS", "900")),
        )


class ClaudeCodeSemanticProvider:
    """Drives the authenticated Claude Code CLI and validates the locked semantic contract.

    Exposes exactly the surface the Messages API provider does -- ``analyze``, ``usage`` and
    ``retry_events`` -- so the orchestrator, caching wrapper and persistence layer are unchanged.
    """

    MAX_IMAGES_PER_REQUEST = ClaudeSemanticProvider.MAX_IMAGES_PER_REQUEST
    SYSTEM_PROMPT = (
        "You are a strict media-analysis backend for a clinical media library. You reply with "
        "exactly one JSON object and nothing else: no prose, no markdown fence, no preamble, no "
        "follow-up question. You evaluate only the evidence supplied in the message."
    )

    def __init__(self, config: ClaudeCodeConfig | None = None) -> None:
        self.config = config or ClaudeCodeConfig.from_environment()
        self.usage: list[dict[str, Any]] = []
        self.retry_events: list[dict[str, Any]] = []

    def discover_model(self) -> str:
        return self.config.model

    @classmethod
    def _prompt(cls, evidence_text: str) -> str:
        # Reuse the locked contract verbatim so both providers ask for the identical package.
        return ClaudeSemanticProvider._prompt(evidence_text)

    @staticmethod
    def _validate(value: Any) -> dict[str, Any]:
        return ClaudeSemanticProvider._validate(value)

    @staticmethod
    def _environment() -> dict[str, str]:
        """Subprocess environment for the CLI.

        ANTHROPIC_API_KEY is removed so an authenticated Claude Code session can never fall back
        to metered API billing.  `.env.local` keeps the key for other tooling.
        """
        env = os.environ.copy()
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
            env.pop(name, None)
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        return env

    def _command(self) -> list[str]:
        return [
            self.config.cli, "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--model", self.config.model,
            "--system-prompt", self.SYSTEM_PROMPT,
            "--allowedTools", "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--max-turns", str(self.config.max_turns),
        ]

    @staticmethod
    def _message(frames: Sequence[bytes], prompt: str) -> str:
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(frame).decode("ascii")}}
            for frame in frames
        ]
        content.append({"type": "text", "text": prompt})
        return json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"

    @staticmethod
    def _final_event(stdout: str) -> dict[str, Any]:
        final: dict[str, Any] | None = None
        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "result":
                final = event
        if final is None:
            raise ClaudeResponseError(
                f"claude CLI produced no result event: {' '.join(stdout.split())[:400]}")
        return final

    def _classify(self, text: str) -> None:
        """Turns CLI prose failures into the right exception class."""
        if API_BILLING_PATTERN.search(text):
            raise ClaudeCodeConfigurationError(
                "the claude CLI reached metered API billing instead of the subscription: "
                "CREDIT_BALANCE_TOO_LOW")
        if _matches(USAGE_LIMIT_PATTERNS, text):
            raise ClaudeCodeUsageLimitError(
                f"claude code subscription allowance reached: {' '.join(text.split())[:300]}")
        if _matches(AUTH_PATTERNS, text):
            raise ClaudeCodeConfigurationError(
                f"claude code authentication failed: {' '.join(text.split())[:300]}")

    def _invoke(self, payload: str) -> dict[str, Any]:
        # A neutral working directory keeps project CLAUDE.md and git context out of the request.
        with tempfile.TemporaryDirectory(prefix="kdi-claude-code-") as workdir:
            try:
                completed = subprocess.run(
                    self._command(), input=payload, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", env=self._environment(),
                    cwd=workdir, timeout=self.config.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise ClaudeResponseError(
                    f"claude CLI timed out after {self.config.timeout_seconds}s") from exc
        self._classify(f"{completed.stdout}\n{completed.stderr}")
        if completed.returncode != 0:
            raise ClaudeResponseError(
                f"claude CLI exited {completed.returncode}: "
                f"{' '.join(completed.stderr.split())[:400]}")
        event = self._final_event(completed.stdout)
        if event.get("is_error") or event.get("subtype") != "success":
            detail = str(event.get("result", event.get("subtype", "")))
            self._classify(detail)
            raise ClaudeResponseError(
                f"claude CLI reported {event.get('subtype')}: {' '.join(detail.split())[:400]}")
        return event

    def analyze(self, *, asset_id: str, evidence_text: str, image_bytes: bytes | None = None,
                images: Sequence[bytes] | None = None, request_type: str = "asset") -> dict[str, Any]:
        """Evaluates the locked 18-layer contract over real visual evidence.

        Same signature, same frame sampling and same return contract as the Messages API
        provider; only the transport differs.
        """
        if not self.config.enabled:
            raise ClaudeCodeConfigurationError("external AI is disabled; refusing production inference")
        frames: list[bytes] = [x for x in (list(images) if images else []) if x]
        if image_bytes:
            frames.insert(0, image_bytes)
        if len(frames) > self.MAX_IMAGES_PER_REQUEST:
            # Same deterministic, evenly spaced sample the API provider takes.
            step = len(frames) / self.MAX_IMAGES_PER_REQUEST
            frames = [frames[int(i * step)] for i in range(self.MAX_IMAGES_PER_REQUEST)]
        image_count = len(frames)
        model = self.discover_model()
        payload = self._message(frames, self._prompt(evidence_text))
        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                event = self._invoke(payload)
                text = str(event.get("result", ""))
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    # The CLI occasionally wraps otherwise valid JSON in a fence or preamble.
                    start, end = text.find("{"), text.rfind("}")
                    if start < 0 or end <= start:
                        raise
                    parsed = json.loads(text[start:end + 1])
                result = self._validate(parsed)
                result["provider"] = PROVIDER_NAME
                result["model"] = model
                result["asset_id"] = asset_id
                result["image_count"] = image_count
                usage = event.get("usage") or {}
                self.usage.append({
                    "asset_id": asset_id, "request_type": request_type, "model": model,
                    "images": image_count, "attempt": attempt + 1,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    "input_tokens": usage.get("input_tokens", 0),
                    "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "subscription_cost_usd": event.get("total_cost_usd"),
                    "session_id": event.get("session_id"),
                })
                return result
            except (ClaudeCodeUsageLimitError, ClaudeCodeConfigurationError):
                # Neither is retryable and neither may be recorded as an asset failure.
                raise
            except (ClaudeResponseError, json.JSONDecodeError) as exc:
                last = exc
                self.retry_events.append({"asset_id": asset_id, "status": "CLI", "attempt": attempt + 1})
                if attempt < self.config.max_retries:
                    time.sleep((2 ** attempt) + random.uniform(0.0, 1.0))
        raise ClaudeResponseError(f"Claude Code analysis failed after retries: {last}")
