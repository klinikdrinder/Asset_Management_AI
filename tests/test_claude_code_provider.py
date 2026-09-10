"""Regression guards for the Claude Code semantic transport.

The load-bearing claim is Step 6 of the rollout: with KDI_SEMANTIC_PROVIDER=claude_code the
production path must never reach the Anthropic Messages API, and the CLI subprocess must never
inherit ANTHROPIC_API_KEY (which would silently restore metered API billing).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kdi_media.claude_code_provider import (  # noqa: E402
    ClaudeCodeConfig,
    ClaudeCodeConfigurationError,
    ClaudeCodeSemanticProvider,
    ClaudeCodeUsageLimitError,
)
from kdi_media.claude_provider import LAYER_IDS  # noqa: E402
from kdi_media.semantic_provider_factory import build_semantic_provider  # noqa: E402


def _config(**overrides):
    base = dict(model="sonnet", enabled=True, cli="claude.cmd", max_retries=0,
                timeout_seconds=60.0, max_turns=2)
    base.update(overrides)
    return ClaudeCodeConfig(**base)


def _package() -> dict:
    return {
        "narrative": "A clinician holds a handheld device against a reclining person's jaw. "
                     "The room is a clinical treatment space.",
        "layers": [{"layer_id": x, "state": "UNKNOWN", "evaluated": True,
                    "display_text": "not determinable", "evidence": []} for x in LAYER_IDS],
    }


def _result_event(package: dict) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": json.dumps(package), "session_id": "s-1",
                       "total_cost_usd": 0.04,
                       "usage": {"input_tokens": 2, "output_tokens": 1700}}) + "\n"


class _Completed:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


@pytest.fixture()
def claude_code_env(monkeypatch):
    monkeypatch.setenv("KDI_SEMANTIC_PROVIDER", "claude_code")
    monkeypatch.setenv("KDI_EXTERNAL_AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-must-never-be-inherited")


def test_factory_returns_claude_code_provider(claude_code_env):
    assert isinstance(build_semantic_provider(), ClaudeCodeSemanticProvider)


def test_factory_returns_api_provider_for_claude(monkeypatch):
    monkeypatch.setenv("KDI_SEMANTIC_PROVIDER", "claude")
    monkeypatch.setenv("KDI_EXTERNAL_AI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    from kdi_media.claude_provider import ClaudeSemanticProvider
    assert isinstance(build_semantic_provider(), ClaudeSemanticProvider)


def test_subprocess_never_inherits_the_api_key(claude_code_env, monkeypatch):
    """The CLI must not receive ANTHROPIC_API_KEY, and os.environ must keep it."""
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs["env"]
        return _Completed(_result_event(_package()))

    monkeypatch.setattr("kdi_media.claude_code_provider.subprocess.run", fake_run)
    provider = ClaudeCodeSemanticProvider(_config())
    provider.analyze(asset_id="a-1", evidence_text="evidence", images=[b"\xff\xd8jpeg"])

    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in seen["env"]
    assert "ANTHROPIC_BASE_URL" not in seen["env"]
    # The key survives in the parent process for other tooling.
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-must-never-be-inherited"
    assert seen["cmd"][1] == "-p"
    assert "--bare" not in seen["cmd"], "--bare would force ANTHROPIC_API_KEY authentication"


def test_no_anthropic_messages_api_request_is_made(claude_code_env, monkeypatch):
    """Any outbound httpx request from the production path is a hard failure."""
    import httpx

    def forbidden(*args, **kwargs):  # pragma: no cover - only runs on regression
        raise AssertionError("ANTHROPIC_API_USED: the Messages API was called")

    monkeypatch.setattr(httpx.Client, "post", forbidden)
    monkeypatch.setattr(httpx.Client, "get", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(
        "kdi_media.claude_code_provider.subprocess.run",
        lambda cmd, **kw: _Completed(_result_event(_package())),
    )
    result = build_semantic_provider().analyze(
        asset_id="a-1", evidence_text="evidence", images=[b"\xff\xd8jpeg"])
    assert result["provider"] == "claude_code"
    assert [x["layer_id"] for x in result["layers"]] == list(LAYER_IDS)


def test_contract_validation_still_rejects_incomplete_packages(claude_code_env, monkeypatch):
    short = _package()
    short["layers"] = short["layers"][:17]
    monkeypatch.setattr(
        "kdi_media.claude_code_provider.subprocess.run",
        lambda cmd, **kw: _Completed(_result_event(short)),
    )
    from kdi_media.claude_provider import ClaudeResponseError
    with pytest.raises(ClaudeResponseError):
        ClaudeCodeSemanticProvider(_config()).analyze(
            asset_id="a-1", evidence_text="evidence", images=[b"\xff\xd8jpeg"])


def test_usage_limit_is_raised_not_retried(claude_code_env, monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        return _Completed("", "Claude AI usage limit reached. Your limit will reset at 3pm.", 1)

    monkeypatch.setattr("kdi_media.claude_code_provider.subprocess.run", fake_run)
    with pytest.raises(ClaudeCodeUsageLimitError):
        ClaudeCodeSemanticProvider(_config(max_retries=3)).analyze(
            asset_id="a-1", evidence_text="evidence", images=[b"\xff\xd8jpeg"])
    assert calls["n"] == 1, "an exhausted allowance must not be retried"


def test_credit_balance_error_is_a_configuration_fault(claude_code_env, monkeypatch):
    """If the CLI ever reaches metered billing, stop the batch instead of paying for it."""
    monkeypatch.setattr(
        "kdi_media.claude_code_provider.subprocess.run",
        lambda cmd, **kw: _Completed("", "Your credit balance is too low to access the "
                                         "Anthropic API.", 1),
    )
    with pytest.raises(ClaudeCodeConfigurationError):
        ClaudeCodeSemanticProvider(_config()).analyze(
            asset_id="a-1", evidence_text="evidence", images=[b"\xff\xd8jpeg"])


def test_frame_sampling_matches_the_api_provider(claude_code_env, monkeypatch):
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["payload"] = json.loads(kwargs["input"])
        return _Completed(_result_event(_package()))

    monkeypatch.setattr("kdi_media.claude_code_provider.subprocess.run", fake_run)
    provider = ClaudeCodeSemanticProvider(_config())
    result = provider.analyze(asset_id="a-1", evidence_text="evidence",
                              images=[bytes([i]) for i in range(50)])
    content = seen["payload"]["message"]["content"]
    images = [x for x in content if x["type"] == "image"]
    assert len(images) == ClaudeCodeSemanticProvider.MAX_IMAGES_PER_REQUEST
    assert result["image_count"] == ClaudeCodeSemanticProvider.MAX_IMAGES_PER_REQUEST
    assert content[-1]["type"] == "text"


def test_disabled_external_ai_refuses_inference(claude_code_env):
    with pytest.raises(ClaudeCodeConfigurationError):
        ClaudeCodeSemanticProvider(_config(enabled=False)).analyze(
            asset_id="a-1", evidence_text="evidence", images=[b"\xff\xd8jpeg"])
