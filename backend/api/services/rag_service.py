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
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector

from api.config import get_settings
from api.utils.serialization import json_safe

if TYPE_CHECKING:
    from api.services.job_manager import Job, JobManager

_SCHEMA_READY = False
_MAX_EMBED_RETRIES = 4
_MAX_BACKOFF_SECONDS = 90

# BAAI/bge-* models are asymmetric: queries need this instruction prefix, documents don't.
_HF_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_hf_client = None


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
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        register_vector(conn)
        yield conn


def _table() -> sql.Identifier:
    return sql.Identifier(get_settings().rag_embeddings_table)


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    settings = get_settings()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
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
                        embedding VECTOR({}) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                ).format(_table(), sql.Literal(settings.rag_embedding_dim))
            )
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (job_id);").format(
                    sql.Identifier(f"idx_{settings.rag_embeddings_table}_job_id"), _table()
                )
            )
    _SCHEMA_READY = True


# ─────────────────────────────────────────────────────────────────────────────
# Embeddings (Hugging Face Inference API, quota-aware batching)
# ─────────────────────────────────────────────────────────────────────────────

def _get_hf_client():
    """Return the cached Hugging Face Inference client, importing the SDK only when needed."""
    global _hf_client
    if _hf_client is not None:
        return _hf_client

    settings = get_settings()
    if not settings.hf_token:
        raise RuntimeError("HF_TOKEN is not set")

    from huggingface_hub import InferenceClient

    _hf_client = InferenceClient(
        model=settings.rag_embedding_model,
        provider="hf-inference",
        token=settings.hf_token,
    )
    return _hf_client


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed ``texts`` in provider-safe batches, retrying with backoff on quota errors."""
    if not texts:
        return []

    settings = get_settings()
    client = _get_hf_client()
    is_query = task_type == "RETRIEVAL_QUERY"
    vectors: list[list[float]] = []

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


def _sample_rows(df: pd.DataFrame, cap: int) -> pd.DataFrame:
    if len(df) <= cap:
        return df
    return df.sample(n=cap, random_state=42).sort_index()


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

    for col, meta in (context.get("available_columns") or {}).items():
        docs.append({
            "doc_type": "column_meta",
            "text": f"Column '{col}': type={meta.get('intended_type')}, semantic_tag={meta.get('semantic_tag')}.",
            "metadata": {"column": col, **meta},
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
                    vector,
                )
                for doc, vector in zip(docs, vectors)
            ]
            cur.executemany(
                sql.SQL(
                    "INSERT INTO {} (job_id, doc_type, row_index, doc_text, metadata, embedding) "
                    "VALUES (%s, %s, %s, %s, %s, %s);"
                ).format(_table()),
                rows,
            )


def build_rag_index(job: "Job") -> dict[str, int]:
    """Rebuild the embedding index for ``job`` from scratch. Returns row sampling info."""
    _ensure_schema()
    _delete_job_docs(job.job_id)

    from api.services.chat_service import build_dataset_context  # deferred: avoids circular import

    context = build_dataset_context(job.result or {})
    fact_docs = _facts_to_documents(context)

    row_docs: list[dict[str, Any]] = []
    total_rows = 0
    sampled_rows = 0
    if job.csv_path and os.path.exists(job.csv_path):
        df = pd.read_csv(job.csv_path, low_memory=False)
        total_rows = len(df)
        sampled_df = _sample_rows(df, get_settings().rag_max_rows)
        sampled_rows = len(sampled_df)
        for idx, row in sampled_df.iterrows():
            row_dict = row.where(pd.notna(row), None).to_dict()
            row_docs.append({
                "doc_type": "row",
                "row_index": int(idx),
                "text": _row_to_text(int(idx), row_dict),
                "metadata": json_safe(row_dict),
            })

    all_docs = fact_docs + row_docs
    if all_docs:
        vectors = embed_texts([d["text"] for d in all_docs], task_type="RETRIEVAL_DOCUMENT")
        _insert_documents(job.job_id, all_docs, vectors)

    return {"total_rows": total_rows, "sampled_rows": sampled_rows}


def start_rag_build(manager: "JobManager", job: "Job") -> bool:
    """Kick off an async index build for ``job`` unless one is already running.

    Returns True if a build was (re)started, False if one was already in flight.
    """
    if not manager.try_begin_rag_build(job.job_id):
        return False

    def _run() -> None:
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
    """Semantically retrieve the row + fact documents most relevant to ``question``."""
    _ensure_schema()
    settings = get_settings()
    question_vector = embed_texts([question], task_type="RETRIEVAL_QUERY")[0]

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT doc_type, doc_text, metadata, row_index FROM {} "
                    "WHERE job_id = %s AND doc_type = 'row' "
                    "ORDER BY embedding <=> %s::vector LIMIT %s;"
                ).format(_table()),
                (job_id, question_vector, settings.rag_top_k_rows),
            )
            row_docs = cur.fetchall()

            cur.execute(
                sql.SQL(
                    "SELECT doc_type, doc_text, metadata, row_index FROM {} "
                    "WHERE job_id = %s AND doc_type != 'row' "
                    "ORDER BY embedding <=> %s::vector LIMIT %s;"
                ).format(_table()),
                (job_id, question_vector, settings.rag_top_k_facts),
            )
            fact_docs = cur.fetchall()

            cur.execute(
                sql.SQL(
                    "SELECT doc_type, doc_text, metadata, row_index FROM {} "
                    "WHERE job_id = %s AND doc_type = 'dataset_summary' LIMIT 1;"
                ).format(_table()),
                (job_id,),
            )
            summary_doc = cur.fetchone()

    if summary_doc and not any(d["doc_type"] == "dataset_summary" for d in fact_docs):
        fact_docs = [summary_doc] + list(fact_docs)

    return {"facts": fact_docs, "rows": row_docs}


def has_any_documents(job_id: str) -> bool:
    """Cheap existence check used to distinguish a genuinely-empty index from not-yet-built."""
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT 1 FROM {} WHERE job_id = %s LIMIT 1;").format(_table()), (job_id,))
            return cur.fetchone() is not None
