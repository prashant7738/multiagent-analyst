"""Pydantic models describing API requests, responses, and SSE payloads.

These schemas define the *contract* the React/Vite frontend can rely on. They
never expose raw DataFrames — those are converted to JSON-safe summaries by the
serialization utilities before reaching any model here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Lifecycle states for a single analysis job."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(str, Enum):
    """Per-agent execution status streamed over SSE."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = Field(default="healthy")
    version: str = Field(default="1.0.0")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class AuthSignupRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class AuthUser(BaseModel):
    user_id: str
    name: str
    email: str
    created_at: datetime


class AuthResponse(BaseModel):
    message: str = "ok"
    user: AuthUser


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------
class AnalyzeResponse(BaseModel):
    """Returned immediately after a CSV upload; the pipeline runs in background."""

    job_id: str
    status: JobStatus = JobStatus.PROCESSING
    filename: str | None = None
    stream_url: str
    result_url: str


class JobSummary(BaseModel):
    """Lightweight job snapshot for polling / listing."""

    job_id: str
    status: JobStatus
    filename: str | None = None
    analysis_config: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, str] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    error: str | None = None


# ---------------------------------------------------------------------------
# SSE event payload (documentation contract; SSE is serialized manually)
# ---------------------------------------------------------------------------
class ProgressEvent(BaseModel):
    event: str
    agent: str | None = None
    status: AgentStatus | None = None
    message: str | None = None
    detail: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Result — frontend-friendly projection of the final GraphState
# ---------------------------------------------------------------------------
class ReliabilityModel(BaseModel):
    stage_confidence: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float | None = None
    decision_readiness: str | None = None
    evidence: list[Any] = Field(default_factory=list)


class ValidationModel(BaseModel):
    passed: bool | None = None
    overall_validation_score: float | None = None
    tier1_checks: dict[str, Any] = Field(default_factory=dict)
    passed_checks: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    flagged_issues: list[Any] = Field(default_factory=list)
    semantic_tagging_agreement: dict[str, Any] = Field(default_factory=dict)


class ReportModel(BaseModel):
    report_path: str | None = None
    available: bool = False
    format: str | None = None
    download_url: str | None = None
    generated_at: datetime | None = None
    narrative_source: str | None = None


class AnalysisResult(BaseModel):
    """Full, JSON-safe projection of the pipeline's final GraphState."""

    job_id: str
    status: JobStatus
    filename: str | None = None

    summary: dict[str, Any] = Field(default_factory=dict)
    raw_profile: dict[str, Any] = Field(default_factory=dict)
    schema_blueprint: dict[str, Any] = Field(default_factory=dict)
    preprocessing_log: list[Any] = Field(default_factory=list)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
    charts: list[dict[str, str]] = Field(default_factory=list)
    validation: ValidationModel = Field(default_factory=ValidationModel)
    reliability: ReliabilityModel = Field(default_factory=ReliabilityModel)
    report: ReportModel = Field(default_factory=ReportModel)
    insight_narrative: dict[str, Any] = Field(default_factory=dict)

    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataset chat — per-job Q&A grounded in the analysis result
# ---------------------------------------------------------------------------
class ChatAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    chart: dict[str, str] | None = None
    ts: datetime | None = None


class ChatResponse(BaseModel):
    answer: str
    source: str  # "groq" | "gemini" | "fallback"
    chart: dict[str, str] | None = None
    chart_generated: bool = False
    history: list[ChatMessage] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Uniform error envelope returned by every endpoint on failure."""

    status: str = "error"
    message: str
    detail: str | None = None
