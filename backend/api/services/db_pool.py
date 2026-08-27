"""Process-wide Postgres connection pool, shared by every store.

Every store (auth, jobs, per-user API keys, RAG) previously opened a brand
new raw ``psycopg.connect()`` per query and closed it immediately after —
fine for a couple of requests, but it burns through a hosted Postgres's
connection limit fast under real concurrent load (each connect is also a
full TCP + auth handshake, so it's slower too). All four talk to the same
``DATABASE_URL``, so they share one small pool of already-open connections
here instead.

``prepare_threshold=None`` disables psycopg's automatic server-side prepared
statements. They're tied to whichever physical backend connection created
them, which breaks under transaction-mode connection poolers (e.g. Supabase's
Supavisor, PgBouncer) that hand out a different backend connection per
transaction — a "prepared statement does not exist" error under load. Turning
this off costs nothing at this app's scale and keeps the DSN swappable
between a direct connection and a pooled one without that class of bug.
"""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pools: dict[str, ConnectionPool] = {}


def get_pool(dsn: str) -> ConnectionPool:
    """Return the shared pool for ``dsn``, opening it on first use."""
    pool = _pools.get(dsn)
    if pool is None:
        pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
            open=True,
        )
        _pools[dsn] = pool
    return pool
