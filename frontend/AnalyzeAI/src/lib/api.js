// Thin client around the FastAPI backend (see backend/api/routes).
// Base URL is configurable via VITE_API_BASE_URL (see .env); defaults to the
// local uvicorn dev server started with `python -m api` / `uvicorn api.app:app`.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

/** Prefix a backend-relative path (e.g. "/api/analyze/x/stream") with the API base. */
export function apiUrl(path) {
  if (!path) return path;
  return /^https?:\/\//i.test(path) ? path : `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

/** Resolve a chart path returned by Agent 4 (served under /plots/{filename}) into a full URL. */
export function chartUrl(pathOrUrl) {
  return apiUrl(pathOrUrl);
}

/** Full URL to download the Agent 6 report (PDF/HTML) for a completed job. */
export function reportDownloadUrl(jobId) {
  return apiUrl(`/api/report/${jobId}`);
}

async function parseJsonOrThrow(res) {
  let body = null;
  try {
    body = await res.json();
  } catch {
    // no JSON body
  }
  if (!res.ok) {
    const detail = body?.detail ?? body?.message ?? res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

async function postJson(path, payload) {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow(res);
}

/** GET /api/health */
export async function checkHealth() {
  const res = await fetch(apiUrl("/api/health"));
  return parseJsonOrThrow(res);
}

/** POST /api/auth/login */
export async function loginUser(email, password) {
  return postJson("/api/auth/login", { email, password });
}

/** POST /api/auth/signup */
export async function signupUser(payload) {
  return postJson("/api/auth/signup", payload);
}

/**
 * POST /api/analyze — upload a CSV and start a pipeline run.
 * Returns { job_id, status, filename, stream_url, result_url }.
 */
export async function analyzeCsv(file, options = {}) {
  const form = new FormData();
  form.append("file", file);
  form.append("preprocessing_profile", options.preprocessingProfile || "balanced");
  form.append("analysis_config", JSON.stringify(options.preprocessingConfig || {}));
  const res = await fetch(apiUrl("/api/analyze"), { method: "POST", body: form });
  return parseJsonOrThrow(res);
}

/**
 * Open an SSE subscription to a job's progress stream.
 * `handlers` may include onEvent(name, data), onOpen(), onError(err).
 * Returns the EventSource so the caller can close() it.
 */
export function subscribeToJobStream(streamUrl, { onEvent, onOpen, onError } = {}) {
  const source = new EventSource(apiUrl(streamUrl));

  const names = [
    "progress",
    "csv_loaded",
    "pipeline_started",
    "charts_generated",
    "validation_passed",
    "validation_failed",
    "report_generated",
    "pipeline_finished",
    "completed",
    "pipeline_failed",
    "error",
  ];
  for (const name of names) {
    source.addEventListener(name, (evt) => {
      let data = {};
      try {
        data = JSON.parse(evt.data);
      } catch {
        // ignore malformed payload
      }
      onEvent?.(name, data);
    });
  }
  source.onopen = () => onOpen?.();
  source.onerror = (err) => onError?.(err);

  return source;
}

/** GET /api/analyze/{job_id}/result — returns the raw AnalysisResult payload. */
export async function fetchJobResult(jobId) {
  const res = await fetch(apiUrl(`/api/analyze/${jobId}/result`));
  return parseJsonOrThrow(res);
}

/** GET /api/jobs */
export async function fetchJobs() {
  const res = await fetch(apiUrl("/api/jobs"));
  return parseJsonOrThrow(res);
}

/** GET /api/jobs/{job_id} */
export async function fetchJob(jobId) {
  const res = await fetch(apiUrl(`/api/jobs/${jobId}`));
  return parseJsonOrThrow(res);
}

/** GET /api/analyze/{job_id}/chat — returns the stored Q&A transcript for a job. */
export async function fetchChatHistory(jobId) {
  const res = await fetch(apiUrl(`/api/analyze/${jobId}/chat`));
  return parseJsonOrThrow(res);
}

/**
 * POST /api/analyze/{job_id}/chat — ask a question about the analyzed dataset.
 * Returns { answer, source, chart, chart_generated, history }.
 */
export async function askDatasetQuestion(jobId, question) {
  return postJson(`/api/analyze/${jobId}/chat`, { question });
}
