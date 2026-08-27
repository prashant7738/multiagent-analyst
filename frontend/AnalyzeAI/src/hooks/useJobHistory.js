import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJobs, fetchJobResult, deleteJob, deleteAllJobs } from "@/lib/api";

/**
 * Single source of job history for HistoryPage and ProfilePage (previously a
 * copy-pasted fetch-and-enrich block in each, with failures silently
 * swallowed into an empty list).
 *
 * Enrichment still requires one result request per completed job (the backend
 * exposes no batch endpoint — do not change the API), but it is now:
 *  - concurrency-limited (6 parallel) so large histories don't hammer /result
 *  - failure-aware: a job whose result expired is marked `enrichFailed`
 *    instead of quietly showing "—", and `partial` tells the UI to say so.
 *
 * Two more things this hook owns:
 *  - Live progress: while any job is still queued/processing, it re-polls
 *    GET /api/jobs on a short interval so an analysis started on another page
 *    (or by a previous visit) keeps updating here too — not just on the page
 *    that opened the SSE stream. `job.progress` (agent -> status) rides along
 *    for the UI to render "3 of 6 agents done" style progress. After 5
 *    minutes of continuous "running" (a real analysis finishes well before
 *    that), polling backs off to a slow interval instead of continuing to
 *    hammer the backend for what's almost certainly an orphaned job.
 *  - A module-level cache: the last-fetched list survives navigating away and
 *    back (same SPA session) so the page renders instantly from cache instead
 *    of a blank "Loading…" every time, while a fresh fetch quietly runs in
 *    the background to catch anything that changed.
 */
const CONCURRENCY = 6;
const FAST_POLL_MS = 3000;
const SLOW_POLL_MS = 20000;
// A normal analysis finishes in well under this. Past it, a "running" job is
// almost certainly orphaned (e.g. killed mid-run by a backend redeploy/restart)
// rather than genuinely still working — keep checking in case it does finish,
// but stop hammering the backend every 3s indefinitely for a job that's dead.
const FAST_POLL_BUDGET_MS = 5 * 60 * 1000;
const RUNNING_STATUSES = new Set(["processing", "queued", "running"]);

let jobsCache = null; // resets on a full page reload, survives SPA navigation
let fastPollStartedAt = null; // when continuous "running" polling began, module-level so
// navigating away and back doesn't hand a stuck job a fresh 5-minute fast-poll budget

// Job ids the user just deleted, client-side. The background poll can have a
// GET /api/jobs already in flight when a delete happens — if that response
// was fetched before the server processed the delete, it still lists the job
// and would otherwise silently repopulate it a moment after the optimistic
// removal. Every poll tick filters this out, so a deleted job can never come
// back without a real reload — job ids are unique per job, so this is safe to
// keep for the whole session (no risk of filtering out a genuinely new job).
const deletedJobIds = new Set();

function normalizeStatus(status) {
  if (status === "completed") return "done";
  if (status === "failed" || status === "error") return "error";
  if (status === "processing" || status === "queued") return "running";
  return status;
}

function toRow(job) {
  return {
    id: job.job_id,
    file: job.filename || "unknown.csv",
    rows: null,
    cols: null,
    quality: null,
    confidence: null,
    reportAvailable: false,
    enrichFailed: false,
    profile: job.analysis_config?.preprocessing_profile || "balanced",
    date: job.created_at?.slice(0, 10) ?? "—",
    duration: `${Math.max(0, Math.round((new Date(job.updated_at) - new Date(job.created_at)) / 1000))}s`,
    status: normalizeStatus(job.status),
    progress: job.progress || {}, // {"Agent 1": "completed", "Agent 2": "running", ...}
  };
}

export default function useJobHistory() {
  const [jobs, setJobs] = useState(() => jobsCache || []);
  const [loading, setLoading] = useState(() => !jobsCache);
  const [error, setError] = useState(null);
  const [partial, setPartial] = useState(false);
  const [deletingIds, setDeletingIds] = useState(() => new Set());
  const [deletingAll, setDeletingAll] = useState(false);

  // Always-current snapshot for the poll loop, without retriggering the effect.
  const jobsRef = useRef(jobs);
  jobsRef.current = jobs;

  const enrichJob = useCallback(async (jobId) => {
    try {
      const result = await fetchJobResult(jobId);
      const patch = {
        rows: result?.summary?.rows ?? null,
        cols: result?.summary?.columns ?? null,
        quality: result?.summary?.quality_score ?? null,
        confidence: result?.summary?.overall_confidence ?? null,
        reportAvailable: Boolean(result?.report?.available),
      };
      setJobs((prev) => {
        const next = prev.map((j) => (j.id === jobId ? { ...j, ...patch } : j));
        jobsCache = next;
        return next;
      });
      return true;
    } catch {
      setJobs((prev) => {
        const next = prev.map((j) => (j.id === jobId ? { ...j, enrichFailed: true } : j));
        jobsCache = next;
        return next;
      });
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let pollTimer = null;

    async function tick(isFirst) {
      try {
        const rawJobs = await fetchJobs();
        if (cancelled) return;

        const prevById = new Map(jobsRef.current.map((j) => [j.id, j]));
        const nextJobs = rawJobs
          .filter((job) => !deletedJobIds.has(job.job_id))
          .map((job) => {
            const fresh = toRow(job);
            const prev = prevById.get(fresh.id);
            // Keep already-fetched enrichment (rows/cols/quality/...); refresh live fields.
            return prev
              ? { ...prev, status: fresh.status, progress: fresh.progress, duration: fresh.duration }
              : fresh;
          });
        setJobs(nextJobs);
        jobsCache = nextJobs;
        jobsRef.current = nextJobs;

        const toEnrich = nextJobs.filter((j) => j.status === "done" && j.rows == null && !j.enrichFailed);
        if (toEnrich.length) {
          let idx = 0;
          let anyFailed = false;
          async function worker() {
            while (!cancelled) {
              const i = idx++;
              if (i >= toEnrich.length) return;
              const ok = await enrichJob(toEnrich[i].id);
              if (!ok) anyFailed = true;
            }
          }
          await Promise.all(Array.from({ length: Math.min(CONCURRENCY, toEnrich.length) }, worker));
          if (!cancelled && anyFailed) setPartial(true);
        }

        const stillRunning = nextJobs.some((j) => RUNNING_STATUSES.has(j.status));
        if (!cancelled && stillRunning) {
          if (fastPollStartedAt == null) fastPollStartedAt = Date.now();
          const elapsed = Date.now() - fastPollStartedAt;
          const nextInterval = elapsed > FAST_POLL_BUDGET_MS ? SLOW_POLL_MS : FAST_POLL_MS;
          pollTimer = setTimeout(() => tick(false), nextInterval);
        } else {
          fastPollStartedAt = null; // clean run — a future new job gets a fresh fast-poll budget
        }
      } catch (err) {
        if (!cancelled && isFirst) setError(err.message || "Failed to load history from the backend.");
      } finally {
        if (!cancelled && isFirst) setLoading(false);
      }
    }

    tick(true);

    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [enrichJob]);

  /**
   * Remove one analysis from history. Optimistic: the row disappears
   * immediately and is restored if the backend rejects the delete.
   */
  const removeJob = useCallback(async (jobId) => {
    const snapshot = jobsRef.current.find((j) => j.id === jobId);
    deletedJobIds.add(jobId);
    setDeletingIds((prev) => new Set(prev).add(jobId));
    setJobs((prev) => {
      const next = prev.filter((j) => j.id !== jobId);
      jobsCache = next;
      return next;
    });
    try {
      await deleteJob(jobId);
      setError(null);
    } catch (err) {
      deletedJobIds.delete(jobId); // delete failed — it's still real, let polling see it again
      if (snapshot) {
        setJobs((prev) => {
          const next = [...prev, snapshot];
          jobsCache = next;
          return next;
        });
      }
      setError(err.message || "Failed to delete the analysis.");
      throw err;
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }, []);

  /**
   * Clear the whole history. Optimistic: finished rows disappear immediately
   * and are restored if the backend rejects; running rows always stay.
   */
  const removeAllJobs = useCallback(async () => {
    const snapshot = jobsRef.current;
    const isFinished = (j) => j.status === "done" || j.status === "error" || j.status === "cancelled";
    const removedIds = snapshot.filter(isFinished).map((j) => j.id);
    removedIds.forEach((id) => deletedJobIds.add(id));
    setJobs((prev) => {
      const next = prev.filter((j) => !isFinished(j));
      jobsCache = next;
      return next;
    });
    setDeletingAll(true);
    try {
      const out = await deleteAllJobs();
      setError(null);
      return out;
    } catch (err) {
      removedIds.forEach((id) => deletedJobIds.delete(id)); // failed — they're still real
      setJobs(snapshot);
      jobsCache = snapshot;
      setError(err.message || "Failed to clear history.");
      throw err;
    } finally {
      setDeletingAll(false);
    }
  }, []);

  return { jobs, loading, error, partial, removeJob, deletingIds, removeAllJobs, deletingAll };
}
