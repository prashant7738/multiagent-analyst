"""RAG dataset-chat: embeddings for raw rows + analysis facts, stored in pgvector.

Two document families are embedded into the SAME table, scoped by ``job_id``:

* ``row``     — one document per (possibly sampled) row of the ORIGINAL uploaded CSV
                (``job.csv_path``), human-readable, for record-level lookups.
* everything else (``dataset_summary``, ``column_meta``, ``descriptive_stat``,
  ``correlation``, ``trend``, ``ranking``, ``anomaly_summary``, ``quality_validation``,
  ``narrative_summary``, ``key_finding``, ``existing_charts``) — derived from
  ``build_dataset_context()`` (chat_service.py), i.e. the SAME deterministic facts
  Agents 1-6 already computed over the FULL dataset. These stay accurate even
  when rows are sampled.

Row embedding intentionally reads ``job.csv_path`` (the original per-job upload
under ``backend/uploads/``) rather than Agent 3's cleaned export
(``outputs/cleaned_data.csv``) — that path is a single hardcoded file shared by
EVERY job (see agent_3.py `_export_cleaned_dataset`), so using it here would let
concurrent/later jobs silently overwrite each other's indexed data.

Building the index calls an external embeddings API and can take a while for
large files, so it must always run in a background thread (see
``start_rag_build``) — never inline on a request thread.
"""

from __future__ import annotations

import os
import threading
import time
import re
from contextlib import contextmanager
from typing import Any, Iterator, TYPE_CHECKING

import numpy as np
import pandas as pd
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector

from api.config import get_settings
from api.services.db_pool import get_pool
from api.services.request_context import get_api_key_override
from api.utils.serialization import json_safe

if TYPE_CHECKING:
    from api.services.job_manager import Job, JobManager

_SCHEMA_READY = False
_MAX_EMBED_RETRIES = 4
_MAX_BACKOFF_SECONDS = 90
_ALWAYS_INCLUDE_FACT_TYPES = (
    "dataset_summary",
    "columns_overview",
    "narrative_summary",
    "key_finding",
    "anomaly_summary",
    "quality_validation",
    "existing_charts",
    "correlation",
    "trend",
    "ranking",
    "category_distribution",
)
# When the always-included set is larger than this it's truncated by
# _ALWAYS_INCLUDE_PRIORITY (below), not arbitrarily by doc_type name. Raised
# from 60 as columns_overview + category_distribution docs joined the set.
_MAX_ALWAYS_INCLUDED_FACTS = 110
# Lower number = kept first when the set overflows _MAX_ALWAYS_INCLUDED_FACTS.
# Compact, high-value, bounded-count facts rank above the potentially-numerous
# ones (correlations, per-column distributions) so they never get crowded out.
_ALWAYS_INCLUDE_PRIORITY = {
    "dataset_summary": 0,
    "columns_overview": 1,
    "quality_validation": 2,
    "narrative_summary": 3,
    "anomaly_summary": 4,
    "existing_charts": 5,
    "key_finding": 6,
    "trend": 7,
    "ranking": 8,
    "category_distribution": 9,
    "correlation": 10,
}

# BAAI/bge-* models are asymmetric: queries need this instruction prefix, documents don't.
_HF_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_hf_client = None
_hf_client_cache: dict[str, Any] = {}  # per-user-override tokens — never shared with the global singleton


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        term in text
        for term in ("429", "resource_exhausted", "quota exceeded", "rate limit", "too many requests")
    )


def _quota_retry_delay_seconds(exc: Exception) -> int:
    text = str(exc)
    match = re.search(r"retry in\s+(\d+(?:\.\d+)?)s", text, re.IGNORECASE)
    if match:
        try:
            return max(5, int(float(match.group(1))))
        except ValueError:
            pass
    return 20


# ─────────────────────────────────────────────────────────────────────────────
# Connection / schema
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def _connect() -> Iterator[psycopg.Connection]:
    dsn = get_settings().database_url
    if not dsn:
        raise RuntimeError("RAG dataset chat requires DATABASE_URL (Postgres + pgvector) to be configured")
    # Note: We skip register_vector() to avoid compatibility issues
    # PostgreSQL can handle vector operations directly without Python type registration
    with get_pool(dsn).connection() as conn:
        yield conn


def _table() -> sql.Identifier:
    return sql.Identifier(get_settings().rag_embeddings_table)


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    settings = get_settings()
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                # Ensure vector extension is created
                print("[RAG] Creating vector extension...")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                print("[RAG] Vector extension ensured")
                
                # Create embeddings table
                print("[RAG] Creating embeddings table...")
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            id BIGSERIAL PRIMARY KEY,
                            job_id TEXT NOT NULL,
                            doc_type TEXT NOT NULL,
                            row_index INTEGER,
                            doc_text TEXT NOT NULL,
                            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            embedding vector({}) NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                        """
                    ).format(_table(), sql.Literal(settings.rag_embedding_dim))
                )
                print("[RAG] Embeddings table ensured")
                
                # Create index
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (job_id);").format(
                        sql.Identifier(f"idx_{settings.rag_embeddings_table}_job_id"), _table()
                    )
                )
                # Composite (job_id, doc_type) — the always-included-facts query
                # filters on exactly these two columns; keeps it index-only as the
                # single shared table accumulates jobs.
                cur.execute(
                    sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (job_id, doc_type);").format(
                        sql.Identifier(f"idx_{settings.rag_embeddings_table}_job_doctype"), _table()
                    )
                )
                print("[RAG] Index ensured")
        # Best-effort ANN index for the vector <=> scans, in its OWN transaction
        # so a failure (pgvector < 0.5, no hnsw) can't roll back the table above.
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "CREATE INDEX IF NOT EXISTS {} ON {} "
                            "USING hnsw (embedding vector_cosine_ops);"
                        ).format(
                            sql.Identifier(f"idx_{settings.rag_embeddings_table}_embedding_hnsw"),
                            _table(),
                        )
                    )
            print("[RAG] HNSW vector index ensured")
        except Exception as ann_exc:  # noqa: BLE001 — optional acceleration only
            print(f"[RAG] HNSW index unavailable, using exact search ({ann_exc})")
        _SCHEMA_READY = True
        print("[RAG] Schema initialization complete")
    except Exception as e:
        print(f"[RAG] Schema initialization failed: {e}")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Embeddings (Hugging Face Inference API, quota-aware batching)
# ─────────────────────────────────────────────────────────────────────────────

def _get_hf_client():
    """Return the active Hugging Face Inference client, importing the SDK only when needed.

    A per-job user-supplied token (see ``api.services.request_context``) always
    wins over the shared/env-configured client — cached per-token, never into
    the module-global ``_hf_client``, so it can't leak to another user's job.
    """
    settings = get_settings()
    override = get_api_key_override("hf_token")
    if override:
        cached = _hf_client_cache.get(override)
        if cached is not None:
            return cached
        from huggingface_hub import InferenceClient

        client = InferenceClient(model=settings.rag_embedding_model, provider="hf-inference", token=override)
        _hf_client_cache[override] = client
        return client

    global _hf_client
    if _hf_client is not None:
        return _hf_client

    if not settings.hf_token:
        raise RuntimeError("HF_TOKEN is not set")

    from huggingface_hub import InferenceClient

    _hf_client = InferenceClient(
        model=settings.rag_embedding_model,
        provider="hf-inference",
        token=settings.hf_token,
    )
    return _hf_client


def embed_texts(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
    progress_cb: "Any | None" = None,
) -> list[list[float]]:
    """Embed ``texts`` in provider-safe batches, retrying with backoff on quota errors.

    ``progress_cb(done, total)`` fires after each successful batch so callers can
    surface live progress. Storage behavior is unchanged: vectors are returned
    in full and the caller still performs a single bulk insert.
    """
    if not texts:
        return []

    settings = get_settings()
    client = _get_hf_client()
    is_query = task_type == "RETRIEVAL_QUERY"
    vectors: list[list[float]] = []
    done = 0

    for start in range(0, len(texts), settings.rag_embed_batch_size):
        batch = texts[start:start + settings.rag_embed_batch_size]
        if is_query:
            batch = [_HF_QUERY_INSTRUCTION + text for text in batch]
        last_error: Exception | None = None
        for attempt in range(_MAX_EMBED_RETRIES):
            try:
                embeddings = client.feature_extraction(batch)
                vectors.extend(np.asarray(embeddings).reshape(len(batch), -1).tolist())
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001 — retried below, re-raised if exhausted
                last_error = exc
                if _is_quota_error(exc) and attempt < _MAX_EMBED_RETRIES - 1:
                    delay = min(_quota_retry_delay_seconds(exc), _MAX_BACKOFF_SECONDS)
                    print(f"[RAG] Embedding quota hit, retrying batch in {delay}s ({exc})")
                    time.sleep(delay)
                    continue
                raise
        if last_error is not None:
            raise last_error

        done += len(batch)
        if progress_cb is not None:
            try:
                progress_cb(done, len(texts))
            except Exception:  # noqa: BLE001 — progress reporting must never kill a build
                pass

    return vectors


# ─────────────────────────────────────────────────────────────────────────────
# Document construction
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_text(row_index: int, row: dict[str, Any]) -> str:
    parts = [
        f"{col}={value}"
        for col, value in row.items()
        if value is not None and str(value).strip().lower() not in ("", "nan", "none", "nat")
    ]
    return f"Row {row_index}: " + " | ".join(parts)


def _fmt_category_value(raw: Any) -> str:
    if raw is None or str(raw).strip().lower() in ("", "nan", "none", "nat"):
        return "(missing)"
    return str(raw)


# A distribution over hundreds of near-unique values (free-text notes, high-card
# IDs that slipped past identifier tagging) isn't a meaningful "most common" fact
# and would bloat the always-included set — skip embedding those.
_MAX_CATEGORY_DISTRIBUTION_UNIQUE = 200
_MAX_CATEGORY_DISTRIBUTION_SHOWN = 12


# Bounds for stratified sampling below - keep the guaranteed-coverage pass cheap
# and small relative to `cap` even on datasets with many categorical columns.
_STRAT_MAX_CATEGORICAL_UNIQUE = 20  # same "low-cardinality label" threshold agent_2 uses
_STRAT_MAX_CATEGORICAL_COLUMNS = 8  # cap how many columns get guaranteed coverage
_STRAT_MIN_ROWS_PER_VALUE = 3  # example rows guaranteed per category value


def _sample_rows(df: pd.DataFrame, cap: int) -> pd.DataFrame:
    """Sample down to ``cap`` rows for RAG indexing.

    Plain random sampling can silently omit an entire category - e.g. every row with
    order_status="Cancelled" - when ``cap`` is a small fraction of the dataset. That
    value then isn't just hard to retrieve, it's structurally absent from the index:
    no amount of vector search finds a row that was never embedded. This first
    reserves a few example rows for every value of every low-cardinality categorical
    column (object dtype, 2-20 unique values, same threshold agent_2 uses for
    "categorical_label"), then fills the remaining budget with plain random rows as
    before, so common questions about any category still have at least one real
    example to retrieve.
    """
    if len(df) <= cap:
        return df

    categorical_cols = [
        col for col in df.columns
        if df[col].dtype == object and 2 <= df[col].nunique(dropna=True) <= _STRAT_MAX_CATEGORICAL_UNIQUE
    ]
    # Coarsest-grained columns first - fewest unique values means fewest rows spent
    # per column to guarantee full coverage.
    categorical_cols.sort(key=lambda col: df[col].nunique(dropna=True))
    categorical_cols = categorical_cols[:_STRAT_MAX_CATEGORICAL_COLUMNS]

    guaranteed_indices: set = set()
    for col in categorical_cols:
        if len(guaranteed_indices) >= cap:
            break
        for _, group in df.groupby(col, dropna=True):
            picks = group.sample(n=min(_STRAT_MIN_ROWS_PER_VALUE, len(group)), random_state=42)
            guaranteed_indices.update(picks.index)
            if len(guaranteed_indices) >= cap:
                break

    if len(guaranteed_indices) > cap:
        guaranteed_indices = set(list(guaranteed_indices)[:cap])

    remaining_cap = cap - len(guaranteed_indices)
    if remaining_cap > 0:
        remaining_pool = df.drop(index=list(guaranteed_indices), errors="ignore")
        if len(remaining_pool) > 0:
            fill = remaining_pool.sample(n=min(remaining_cap, len(remaining_pool)), random_state=42)
            guaranteed_indices.update(fill.index)

    return df.loc[sorted(guaranteed_indices)]


def _read_and_sample_rows(csv_path: str, cap: int) -> tuple[pd.DataFrame, int]:
    """Read the upload in chunks, keeping at most ``cap`` sampled rows in memory.

    The previous implementation did ``pd.read_csv(whole_file)`` then sampled — so
    peak RAM was the entire dataset regardless of ``RAG_MAX_ROWS``, and a large
    upload could OOM a small instance before a single embedding ran. This bounds
    the working set to roughly ``cap + one chunk``: each chunk is concatenated
    onto the running sample and, once that exceeds the budget, re-sampled back
    down to ``cap`` via the same stratified ``_sample_rows``. The DataFrame
    index is rewritten to the true 0-based file row number (chunked reads
    otherwise restart the index at 0 every chunk, so ``row_index`` would
    collide across chunks).

    Stratification is slightly weaker than a whole-file pass (each re-sample
    only sees the rows still in the working set) but every low-cardinality
    category still gets example rows, which is what row retrieval needs.
    """
    chunk_rows = max(1000, get_settings().rag_read_chunk_rows)
    working: pd.DataFrame | None = None
    total = 0
    offset = 0
    for chunk in pd.read_csv(csv_path, low_memory=False, chunksize=chunk_rows):
        chunk.index = range(offset, offset + len(chunk))
        offset += len(chunk)
        total += len(chunk)
        working = chunk if working is None else pd.concat([working, chunk])
        if len(working) > cap + chunk_rows:
            working = _sample_rows(working, cap)
    if working is None or working.empty:
        return pd.DataFrame(), total
    return _sample_rows(working, cap), total


def _facts_to_documents(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn chat_service.build_dataset_context()'s output into granular embeddable docs."""
    docs: list[dict[str, Any]] = []
    dataset = context.get("dataset", {}) or {}

    docs.append({
        "doc_type": "dataset_summary",
        "text": (
            f"Dataset {dataset.get('filename')}: {dataset.get('rows')} rows, "
            f"{dataset.get('columns')} columns, quality score {dataset.get('quality_score')}."
        ),
        "metadata": dataset,
    })

    schema_cols = context.get("available_columns") or {}

    for col, meta in schema_cols.items():
        docs.append({
            "doc_type": "column_meta",
            "text": f"Column '{col}': type={meta.get('intended_type')}, semantic_tag={meta.get('semantic_tag')}.",
            "metadata": {"column": col, **meta},
        })

    # One always-included doc naming EVERY queryable column (schema columns plus
    # Agent 3's derived numeric / categorical columns, which never get a
    # column_meta entry). Without this the data-query engine can only reference
    # columns that happen to land in the top-k vector-matched column_meta docs,
    # so on a wide dataset it "can't find" the column the user asked about.
    def _col_kind(name: str) -> str:
        tag = (schema_cols.get(name) or {}).get("intended_type")
        if tag:
            return str(tag)
        if name in (context.get("descriptive_stats") or {}):
            return "numeric"
        if name in (context.get("category_distributions") or {}):
            return "categorical"
        return "unknown"

    all_cols = list(dict.fromkeys([
        *schema_cols.keys(),
        *(context.get("descriptive_stats") or {}).keys(),
        *(context.get("category_distributions") or {}).keys(),
    ]))
    if all_cols:
        shown_cols = all_cols[:120]
        listed = ", ".join(f"{c}: {_col_kind(c)}" for c in shown_cols)
        if len(all_cols) > len(shown_cols):
            listed += f", + {len(all_cols) - len(shown_cols)} more"
        docs.append({
            "doc_type": "columns_overview",
            "text": f"All {len(all_cols)} queryable columns (name: kind): {listed}.",
            "metadata": {"columns": all_cols},
        })

    for col, metrics in (context.get("descriptive_stats") or {}).items():
        docs.append({
            "doc_type": "descriptive_stat",
            "text": (
                f"{col}: mean={metrics.get('mean')}, median={metrics.get('median')}, "
                f"std={metrics.get('std')}, min={metrics.get('min')}, max={metrics.get('max')}, "
                f"missing={metrics.get('missing_pct')}%."
            ),
            "metadata": {"column": col, **metrics},
        })

    for pair in context.get("strong_correlations") or []:
        docs.append({
            "doc_type": "correlation",
            "text": (
                f"{pair.get('col1')} and {pair.get('col2')} are {pair.get('strength')} "
                f"{pair.get('direction')} correlated (pearson r={pair.get('pearson_r')})."
            ),
            "metadata": pair,
        })

    for col, metrics in (context.get("significant_trends") or {}).items():
        docs.append({
            "doc_type": "trend",
            "text": f"{col} shows a {metrics.get('trend')} trend (R-squared={metrics.get('r_squared')}).",
            "metadata": {"column": col, **metrics},
        })

    for col, data in (context.get("top_bottom_rankings") or {}).items():
        docs.append({
            "doc_type": "ranking",
            "text": f"Top values for {col}: {data.get('top')}. Bottom values: {data.get('bottom')}.",
            "metadata": {"column": col, **data},
        })

    for col, records in (context.get("category_distributions") or {}).items():
        if not records or len(records) > _MAX_CATEGORY_DISTRIBUTION_UNIQUE:
            continue
        total = len(records)
        shown = records[:_MAX_CATEGORY_DISTRIBUTION_SHOWN]
        parts = [
            f"{_fmt_category_value(rec.get(col))}={rec.get('count')} ({rec.get('pct')}%)"
            for rec in shown
        ]
        text = (
            f"Value counts for '{col}' (full dataset, {total} "
            f"categor{'y' if total == 1 else 'ies'}): " + ", ".join(parts)
        )
        if total > len(shown):
            text += f", + {total - len(shown)} more"
        text += f". Most common: {_fmt_category_value(shown[0].get(col))}."
        docs.append({
            "doc_type": "category_distribution",
            "text": text,
            "metadata": {"column": col, "categories": total, "distribution": shown},
        })

    anomaly = context.get("anomaly_summary") or {}
    if anomaly:
        docs.append({
            "doc_type": "anomaly_summary",
            "text": (
                f"{anomaly.get('unique_flagged_rows')} rows ({anomaly.get('unique_flagged_row_pct')}%) "
                f"flagged as anomalous across {anomaly.get('flagged_columns')} column(s)."
            ),
            "metadata": anomaly,
        })

    validation = context.get("validation") or {}
    reliability = context.get("reliability") or {}
    if validation or reliability:
        docs.append({
            "doc_type": "quality_validation",
            "text": (
                f"Data quality score {dataset.get('quality_score')}; validation passed={validation.get('passed')}; "
                f"reliability confidence={reliability.get('overall_confidence')}."
            ),
            "metadata": {"validation": validation, "reliability": reliability},
        })

    summary = context.get("executive_summary")
    if summary:
        docs.append({"doc_type": "narrative_summary", "text": summary, "metadata": {}})

    for idx, finding in enumerate(context.get("key_findings") or []):
        docs.append({"doc_type": "key_finding", "text": str(finding), "metadata": {"index": idx}})

    charts = context.get("existing_charts") or []
    if charts:
        docs.append({
            "doc_type": "existing_charts",
            "text": f"Existing charts already generated: {', '.join(str(c) for c in charts)}.",
            "metadata": {"charts": charts},
        })

    return [d for d in docs if d["text"] and d["text"].strip()]


# ─────────────────────────────────────────────────────────────────────────────
# Index build (must run off the request thread — see start_rag_build)
# ─────────────────────────────────────────────────────────────────────────────

def _delete_job_docs(job_id: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DELETE FROM {} WHERE job_id = %s;").format(_table()), (job_id,))


def delete_job_documents(job_id: str) -> None:
    """Best-effort removal of a job's RAG embeddings (used when deleting history)."""
    try:
        _delete_job_docs(job_id)
    except Exception:  # noqa: BLE001 — deletion must not fail the request
        pass


def _insert_documents(job_id: str, docs: list[dict[str, Any]], vectors: list[list[float]]) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            rows = [
                (
                    job_id,
                    doc["doc_type"],
                    doc.get("row_index"),
                    doc["text"],
                    Jsonb(json_safe(doc.get("metadata") or {})),
                    f"[{','.join(str(v) for v in vector)}]",  # Convert to PostgreSQL vector format
                )
                for doc, vector in zip(docs, vectors)
            ]
            cur.executemany(
                sql.SQL(
                    "INSERT INTO {} (job_id, doc_type, row_index, doc_text, metadata, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s::vector);"
                ).format(_table()),
                rows,
            )


_PERSIST_BATCH_MIN = 200  # docs embedded + inserted per pass (>= rag_embed_batch_size)


def build_rag_index(job: "Job") -> dict[str, int]:
    """Rebuild the embedding index for ``job`` from scratch. Returns row sampling info.

    Publishes live progress via ``JobManager.set_rag_progress`` (phase +
    embedded/total counters) so the frontend can show an indicator.

    Documents are embedded and inserted in bounded batches rather than
    accumulating every vector in memory for one final bulk insert — that peak
    (all row docs + all their float vectors + the stringified copy for the
    INSERT, held simultaneously) was the main thing that OOM'd small instances.
    A build that fails partway leaves partial rows, but ``retrieve`` only runs
    once ``rag_status == "ready"`` and every build starts by deleting the job's
    existing docs, so a retry is always clean.
    """
    _ensure_schema()
    _delete_job_docs(job.job_id)

    from api.services.job_manager import get_job_manager  # deferred: avoids circular import

    manager = get_job_manager()

    def _report(phase: str, embedded: int | None = None, total: int | None = None) -> None:
        try:
            manager.set_rag_progress(job.job_id, phase, embedded=embedded, total=total)
        except Exception:  # noqa: BLE001 — progress reporting must never kill a build
            pass

    _report("preparing", embedded=0, total=0)

    from api.services.chat_service import build_dataset_context  # deferred: avoids circular import

    context = build_dataset_context(job.result or {})
    fact_docs = _facts_to_documents(context)

    row_docs: list[dict[str, Any]] = []
    total_rows = 0
    sampled_rows = 0
    if job.csv_path and os.path.exists(job.csv_path):
        sampled_df, total_rows = _read_and_sample_rows(job.csv_path, get_settings().rag_max_rows)
        sampled_rows = len(sampled_df)
        for idx, row in sampled_df.iterrows():
            row_dict = row.where(pd.notna(row), None).to_dict()
            row_docs.append({
                "doc_type": "row",
                "row_index": int(idx),
                "text": _row_to_text(int(idx), row_dict),
                "metadata": json_safe(row_dict),
            })

    all_docs = [d for d in (fact_docs + row_docs) if d["text"] and d["text"].strip()]
    if all_docs:
        total_docs = len(all_docs)
        print(f"[RAG] Embedding {total_docs} documents for job {job.job_id[:8]} "
              f"({sampled_rows}/{total_rows} rows + {len(fact_docs)} facts)")
        _report("embedding", embedded=0, total=total_docs)

        persist_batch = max(_PERSIST_BATCH_MIN, get_settings().rag_embed_batch_size)
        embedded = 0
        for start in range(0, total_docs, persist_batch):
            part = all_docs[start:start + persist_batch]
            vectors = embed_texts([d["text"] for d in part], task_type="RETRIEVAL_DOCUMENT")
            _insert_documents(job.job_id, part, vectors)
            embedded += len(part)
            print(f"[RAG] Embedded + saved {embedded}/{total_docs} documents "
                  f"({embedded * 100 // total_docs}%)")
            _report("embedding", embedded=embedded, total=total_docs)

        _report("saving", embedded=total_docs, total=total_docs)

    return {"total_rows": total_rows, "sampled_rows": sampled_rows}


def start_rag_build(manager: "JobManager", job: "Job", api_key_overrides: dict[str, str] | None = None) -> bool:
    """Kick off an async index build for ``job`` unless one is already running.

    Returns True if a build was (re)started, False if one was already in flight.
    ``api_key_overrides`` (e.g. {"hf_token": "..."}) is re-applied at the top of
    the build thread — a new thread starts with no inherited context, so it
    must be passed explicitly rather than relying on contextvar propagation.
    """
    if not manager.try_begin_rag_build(job.job_id):
        return False

    def _run() -> None:
        from api.services.request_context import set_api_key_overrides

        set_api_key_overrides(api_key_overrides)
        try:
            sample_info = build_rag_index(job)
            manager.set_rag_status(job.job_id, "ready", sample_info=sample_info)
        except Exception as exc:  # noqa: BLE001 — never let the background thread crash silently
            print(f"[RAG] Index build failed for job {job.job_id}: {exc}")
            manager.set_rag_status(job.job_id, "failed", error=str(exc))

    threading.Thread(target=_run, daemon=True, name=f"rag-build-{job.job_id[:8]}").start()
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval
# ─────────────────────────────────────────────────────────────────────────────

def retrieve(job_id: str, question: str) -> dict[str, list[dict[str, Any]]]:
    """Retrieve rows semantically and preserve dataset-wide facts for synthesis.

    Dataset-wide insight documents are always included because broad questions
    do not reliably match one narrow fact by vector similarity.
    """
    _ensure_schema()
    settings = get_settings()
    question_vector = embed_texts([question], task_type="RETRIEVAL_QUERY")[0]
    
    # Convert vector to PostgreSQL format: [0.1, 0.2, 0.3, ...]
    vector_str = f"[{','.join(str(v) for v in question_vector)}]"

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT doc_type, doc_text, metadata, row_index FROM {} "
                    "WHERE job_id = %s AND doc_type = 'row' "
                    "ORDER BY embedding <=> %s::vector LIMIT %s;"
                ).format(_table()),
                (job_id, vector_str, settings.rag_top_k_rows),
            )
            row_docs = cur.fetchall()

            # Order by curated priority (not doc_type name) so that when a
            # fact-rich dataset overflows the LIMIT, the compact high-value facts
            # survive and only the long tail (extra correlations / distributions)
            # is dropped.
            priority_case = sql.SQL("CASE doc_type {} ELSE 99 END").format(
                sql.SQL(" ").join(
                    sql.SQL("WHEN {} THEN {}").format(sql.Literal(dt), sql.Literal(rank))
                    for dt, rank in _ALWAYS_INCLUDE_PRIORITY.items()
                )
            )
            cur.execute(
                sql.SQL(
                    "SELECT doc_type, doc_text, metadata, row_index FROM {} "
                    "WHERE job_id = %s AND doc_type = ANY(%s) "
                    "ORDER BY {}, row_index NULLS FIRST LIMIT %s;"
                ).format(_table(), priority_case),
                (job_id, list(_ALWAYS_INCLUDE_FACT_TYPES), _MAX_ALWAYS_INCLUDED_FACTS),
            )
            always_included_facts = cur.fetchall()

            cur.execute(
                sql.SQL(
                    "SELECT doc_type, doc_text, metadata, row_index FROM {} "
                    "WHERE job_id = %s AND doc_type IN ('column_meta', 'descriptive_stat') "
                    "ORDER BY embedding <=> %s::vector LIMIT %s;"
                ).format(_table()),
                (job_id, vector_str, settings.rag_top_k_facts),
            )
            column_facts = cur.fetchall()

    fact_docs = list(always_included_facts) + list(column_facts)

    return {"facts": fact_docs, "rows": row_docs}


def has_any_documents(job_id: str) -> bool:
    """Cheap existence check used to distinguish a genuinely-empty index from not-yet-built."""
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT 1 FROM {} WHERE job_id = %s LIMIT 1;").format(_table()), (job_id,))
            return cur.fetchone() is not None
