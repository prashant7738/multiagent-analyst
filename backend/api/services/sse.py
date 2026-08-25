"""Server-Sent-Events (SSE) streaming service.

Turns a job's append-only event log into an SSE byte stream. Subscribers track
their position by index, so they can connect at any time (before, during, or
after the pipeline runs) and still receive the full ordered history followed by
live updates. Multiple concurrent subscribers are supported.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from api.config import get_settings
from api.services.job_manager import JobManager
from api.utils.serialization import json_safe

logger = logging.getLogger("api.sse")


def format_sse(event: dict[str, Any]) -> str:
    """Serialize an event dict into the SSE wire format.

    Emits a named ``event:`` line plus a JSON ``data:`` payload. The event name
    defaults to ``message`` when absent.
    """
    name = event.get("event", "message")
    data = {k: v for k, v in event.items() if k != "event"}
    payload = json.dumps(json_safe(data), ensure_ascii=False)
    return f"event: {name}\ndata: {payload}\n\n"


async def event_stream(manager: JobManager, job_id: str) -> AsyncIterator[bytes]:
    """Yield SSE-formatted bytes for a job until it finishes.

    Replays all past events first, then follows new ones. Periodic comment
    keepalives prevent idle proxies from closing the connection.
    """
    settings = get_settings()
    job = manager.get_job(job_id)
    if job is None:
        yield format_sse({"event": "error", "message": f"Unknown job_id: {job_id}"}).encode("utf-8")
        return

    # Initial handshake so the client's EventSource opens promptly.
    yield b": connected\n\n"

    index = 0
    idle_ticks = 0
    terminal_sent = False
    keepalive_ticks = max(1, int(settings.sse_keepalive_interval / max(settings.sse_poll_interval, 0.01)))

    while True:
        # Snapshot new events under the job's lock.
        with job.condition:
            pending = job.events[index:]
            index = len(job.events)
            finished = job.finished

        if pending:
            idle_ticks = 0
            for event in pending:
                yield format_sse(event).encode("utf-8")
                if event.get("event") in {"completed", "pipeline_failed"}:
                    terminal_sent = True
        elif not terminal_sent:
            idle_ticks += 1
            if finished:
                # No more events will arrive and log is drained.
                return
            if idle_ticks >= keepalive_ticks:
                idle_ticks = 0
                yield b": keepalive\n\n"
        else:
            # The terminal event was delivered. Do NOT close the connection here:
            # a browser EventSource treats a server-initiated close as a dropped
            # connection and auto-reconnects, which (with no Last-Event-ID support
            # in this replay-by-index protocol) replays the entire history and
            # re-delivers "completed" — an infinite reconnect loop that flickers
            # the UI and hammers the server. Idle instead and let the CLIENT close
            # the connection once it's done handling the terminal event; if the
            # client (or its tab) goes away, the ASGI server cancels this
            # generator for us, same as any other disconnect.
            idle_ticks += 1
            if idle_ticks >= keepalive_ticks:
                idle_ticks = 0
                yield b": keepalive\n\n"

        await asyncio.sleep(settings.sse_poll_interval)
