"""Per-agent API-key usage tracking.

Every agent declares HOW it used external services (or that it didn't):
which provider, a masked fingerprint of the key, the model, and why.

Records are captured into a thread-local scope so concurrent pipeline jobs
(each running in its own daemon thread) never see each other's usage. The
captured entries land in GraphState["api_key_usage"], get streamed through
the SSE progress messages, and are exposed by /api/analyze/{id}/result so
the frontend can show exactly where API keys were involved.

Fingerprints are sha256 prefixes — never reversible to the real key.
"""

from __future__ import annotations

import hashlib
import os
import threading

_local = threading.local()

_GEMINI_ENV_NAMES = (
    "GEMINI_API_KEYS", "GEMINI_API_KEY", "Gemini_API_Key",
    "GOOGLE_API_KEY",
) + tuple(f"GEMINI_API_KEY_{i}" for i in range(1, 6))


def mask_key(value) -> str:
    """Stable 10-char fingerprint of a secret (never the secret itself)."""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:10]


def start_capture() -> None:
    """Reset this thread's usage buffer (call at the top of an agent's work)."""
    _local.records = []


def record(agent: str, provider: str, key=None, purpose: str = "", model: str = "") -> None:
    """Capture one API-key use and echo an ASCII-safe console line."""
    entry = {
        "provider": str(provider),
        "fingerprint": mask_key(key),
        "purpose": purpose or "",
        "model": model or "",
    }
    records = getattr(_local, "records", None)
    if records is None:
        records = _local.records = []
    records.append({"agent": agent, **entry})
    suffix = f" model={entry['model']}" if entry["model"] else ""
    purpose_sfx = f" purpose={entry['purpose']}" if entry["purpose"] else ""
    print(
        f"[{agent}] API USE: {provider} key=fp:{entry['fingerprint']}"
        f"{suffix}{purpose_sfx}"
    )


def drain_capture(agent: str) -> list[dict]:
    """Return this thread's captured uses (agent-tagged) and clear the buffer."""
    records = getattr(_local, "records", None) or []
    _local.records = []
    return [{k: v for k, v in r.items()} for r in records if r.get("agent") == agent]


def local_entry(note: str = "local computation only") -> dict:
    """Standard 'no API' usage block."""
    return {"uses_api": False, "providers": [], "note": note}


def llm_entry(records: list[dict], fallback_note: str) -> dict:
    """Build a usage block from captured records."""
    grouped: dict[str, dict] = {}
    for rec in records:
        provider = rec.get("provider") or "unknown"
        slot = grouped.setdefault(
            provider,
            {"provider": provider, "fingerprints": [], "models": [], "purposes": []},
        )
        if rec.get("fingerprint") and rec["fingerprint"] not in slot["fingerprints"]:
            slot["fingerprints"].append(rec["fingerprint"])
        if rec.get("model") and rec["model"] not in slot["models"]:
            slot["models"].append(rec["model"])
        if rec.get("purpose") and rec["purpose"] not in slot["purposes"]:
            slot["purposes"].append(rec["purpose"])
    providers = [
        {
            "provider": p["provider"],
            "fingerprints": p["fingerprints"],
            "models": p["models"],
            "purposes": p["purposes"],
        }
        for p in grouped.values()
    ]
    return {
        "uses_api": bool(providers),
        "providers": providers,
        "note": None if providers else fallback_note,
    }


def configured_summary() -> dict:
    """Which providers have keys configured right now (masked)."""
    summary: dict[str, list[str]] = {}
    if os.getenv("GROQ_API_KEY", "").strip():
        summary["Groq"] = [mask_key(os.getenv("GROQ_API_KEY"))]
    gemini_fps: list[str] = []
    for name in _GEMINI_ENV_NAMES:
        raw = os.getenv(name, "").strip()
        for candidate in raw.replace(";", ",").replace(" ", ",").split(","):
            if candidate:
                fp = mask_key(candidate)
                if fp not in gemini_fps:
                    gemini_fps.append(fp)
    if gemini_fps:
        summary["Gemini"] = gemini_fps
    hf = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
    if hf and hf.strip():
        summary["HuggingFace"] = [mask_key(hf)]
    return summary


def usage_fragment(state, agent_key: str, entry: dict) -> dict:
    """Merge one agent's entry into the accumulated api_key_usage state map."""
    merged = dict(state.get("api_key_usage") or {})
    merged[agent_key] = entry
    return merged
