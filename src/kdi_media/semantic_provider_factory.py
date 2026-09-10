"""Single place that decides which semantic inference backend production uses.

`KDI_SEMANTIC_PROVIDER` selects the transport.  Both providers return the identical validated
18-layer package, so everything downstream -- caching, staging, completeness, publication -- is
unchanged by the choice.

    claude       Anthropic Messages API, billed against API credits.
    claude_code  The locally authenticated Claude Code CLI, billed against the subscription.
    codex_cli    The locally authenticated Codex CLI, billed against the ChatGPT subscription.
"""
from __future__ import annotations

import os
from typing import Any

__all__ = ["SUPPORTED_PROVIDERS", "resolve_provider_name", "build_semantic_provider"]

SUPPORTED_PROVIDERS = ("claude", "claude_code", "codex_cli")


def resolve_provider_name() -> str:
    name = os.getenv("KDI_SEMANTIC_PROVIDER", "claude").strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        raise RuntimeError(f"CLAUDE_CONFIGURATION: unsupported semantic provider {name!r}")
    return name


def build_semantic_provider() -> Any:
    """Returns the configured provider instance.

    The Anthropic API module is imported only on the `claude` branch, so a `claude_code` run
    cannot construct an API client even accidentally.
    """
    name = resolve_provider_name()
    if name == "claude_code":
        from .claude_code_provider import ClaudeCodeSemanticProvider
        return ClaudeCodeSemanticProvider()
    if name == "codex_cli":
        from .codex_cli_provider import CodexCliSemanticProvider
        return CodexCliSemanticProvider()
    from .claude_provider import ClaudeSemanticProvider
    return ClaudeSemanticProvider()
