// Thin client around the FastAPI backend (see backend/api/routes).
// Base URL is configurable via VITE_API_BASE_URL (see .env); defaults to the
// local uvicorn dev server started with `python -m api` / `uvicorn api.app:app`.
import { readStoredToken, clearStoredAuth } from "./authStorage";

const configuredApiBase =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_BACKEND_URL ||
  "http://localhost:8000";
const API_BASE = configuredApiBase.replace(/\/$/, "");

/** Prefix a backend-relative path (e.g. "/api/analyze/x/stream") with the API base. */
export function apiUrl(path) {
  if (!path) return path;
  return /^https?:\/\//i.test(path) ? path : `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

/** Resolve a chart path returned by Agent 4 (served under /plots/{filename}) into a full URL. */
export function chartUrl(pathOrUrl) {
  return apiUrl(pathOrUrl);
}

/**
 * Full URL to download the Agent 6 report (PDF/HTML) for a completed job.
 * Carries the bearer token as a query param because this URL is used both by
 * fetch() and by plain <a href target="_blank"> links, which can't set headers.
 */
export function reportDownloadUrl(jobId, format = 'html') {
  const token = readStoredToken();
  const tokenParam = token ? `&token=${encodeURIComponent(token)}` : "";
  return apiUrl(`/api/report/${jobId}?format=${format}${tokenParam}`);
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

/** Unauthenticated POST — used only by login/signup, before a token exists. */
async function postJson(path, payload) {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow(res);
}

/**
 * fetch() wrapper for every endpoint that requires a signed-in user. Attaches
 * the stored bearer token and, on a 401 (missing/expired session), clears the
 * stale local session and hard-redirects to /login — the backend is the source
 * of truth for whether the session is still valid, not just localStorage.
 */
async function authedFetch(path, options = {}) {
  const token = readStoredToken();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(apiUrl(path), { ...options, headers });

  if (res.status === 401) {
    clearStoredAuth();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }

  return res;
}

async function authedPostJson(path, payload) {
  const res = await authedFetch(path, {
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

/** POST /api/auth/logout — invalidates the given token server-side. Best-effort. */
export async function logoutUser(token) {
  if (!token) return;
  try {
    await fetch(apiUrl("/api/auth/logout"), {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    /* best-effort — local session is already cleared regardless */
  }
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
  const res = await authedFetch("/api/analyze", { method: "POST", body: form });
  return parseJsonOrThrow(res);
}

/**
 * Open an SSE subscription to a job's progress stream.
 * `handlers` may include onEvent(name, data), onOpen(), onError(err).
 * Returns the EventSource so the caller can close() it.
 *
 * EventSource can't set custom headers, so the bearer token is passed as a
 * ?token= query param instead (the backend's auth dependency accepts either).
 */
export function subscribeToJobStream(streamUrl, { onEvent, onOpen, onError } = {}) {
  const token = readStoredToken();
  const url = new URL(apiUrl(streamUrl));
  if (token) url.searchParams.set("token", token);
  const source = new EventSource(url.toString());

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
    "pipeline_cancelled",
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
  const res = await authedFetch(`/api/analyze/${jobId}/result`);
  return parseJsonOrThrow(res);
}

/**
 * POST /api/analyze/{job_id}/cancel — ask a running analysis to stop.
 * The pipeline halts at the next agent boundary; the SSE stream then emits
 * `pipeline_cancelled` and the job ends in the `cancelled` state.
 */
export async function cancelJob(jobId) {
  const res = await authedFetch(`/api/analyze/${jobId}/cancel`, { method: "POST" });
  return parseJsonOrThrow(res);
}

/** GET /api/jobs — the caller's own jobs only. */
export async function fetchJobs() {
  const res = await authedFetch("/api/jobs");
  return parseJsonOrThrow(res);
}

/** GET /api/jobs/{job_id} */
export async function fetchJob(jobId) {
  const res = await authedFetch(`/api/jobs/${jobId}`);
  return parseJsonOrThrow(res);
}

/**
 * DELETE /api/jobs/{job_id} — remove a past analysis from history,
 * including its stored artifacts (upload, charts, report).
 */
export async function deleteJob(jobId) {
  const res = await authedFetch(`/api/jobs/${jobId}`, { method: "DELETE" });
  return parseJsonOrThrow(res);
}

/**
 * DELETE /api/jobs — clear the caller's own history. Returns { deleted, skipped }
 * (running analyses are skipped by the backend).
 */
export async function deleteAllJobs() {
  const res = await authedFetch("/api/jobs", { method: "DELETE" });
  return parseJsonOrThrow(res);
}

/** GET /api/analyze/{job_id}/chat — returns the stored Q&A transcript for a job. */
export async function fetchChatHistory(jobId) {
  const res = await authedFetch(`/api/analyze/${jobId}/chat`);
  return parseJsonOrThrow(res);
}

/**
 * POST /api/analyze/{job_id}/chat — ask a question about the analyzed dataset.
 * Returns { answer, source, chart, chart_generated, history }.
 */
export async function askDatasetQuestion(jobId, question) {
  return authedPostJson(`/api/analyze/${jobId}/chat`, { question });
}

/**
 * GET /api/settings/api-keys — per-provider configured/masked status for the
 * signed-in user's own Groq/Gemini/HF keys. Never returns the raw key.
 */
export async function fetchApiKeysStatus() {
  const res = await authedFetch("/api/settings/api-keys");
  return parseJsonOrThrow(res);
}

/**
 * PUT /api/settings/api-keys — save one or more keys. Fields omitted from
 * `updates` are left unchanged; an empty string clears that key.
 */
export async function saveApiKeys(updates) {
  const res = await authedFetch("/api/settings/api-keys", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return parseJsonOrThrow(res);
}

/** DELETE /api/settings/api-keys/{provider} — clear one key ("groq" | "gemini" | "hf_token"). */
export async function deleteApiKey(provider) {
  const res = await authedFetch(`/api/settings/api-keys/${provider}`, { method: "DELETE" });
  return parseJsonOrThrow(res);
}

/**
 * POST /api/settings/api-keys/test — try a candidate key against the real
 * provider without saving it. Returns { provider, status }.
 */
export async function testApiKey(provider, apiKey) {
  return authedPostJson("/api/settings/api-keys/test", { provider, api_key: apiKey });
}
