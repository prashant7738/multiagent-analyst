"""Per-execution-context LLM API key overrides.

Each analysis job runs in its own dedicated thread, and each RAG-index build
runs in another (see ``pipeline_runner.py`` / ``rag_service.py``); chat
requests run on the request's own asyncio task. None of these share state
with each other, so a ``ContextVar`` set at the top of each one correctly
scopes a signed-in user's own API keys to *their* execution only — it's the
thread/task-local mechanism Python provides for exactly this. Threads do not
inherit a parent thread's context automatically, so callers that hand work to
a **new** thread (pipeline runs, RAG builds) must re-set this at the top of
that thread's entry point rather than relying on inheritance.
"""

from __future__ import annotations

import contextvars

_overrides: "contextvars.ContextVar[dict[str, str]]" = contextvars.ContextVar(
    "api_key_overrides", default={}
)


def set_api_key_overrides(overrides: dict[str, str] | None) -> None:
    _overrides.set({k: v for k, v in (overrides or {}).items() if v})


def get_api_key_override(provider: str) -> str | None:
    return _overrides.get().get(provider)
