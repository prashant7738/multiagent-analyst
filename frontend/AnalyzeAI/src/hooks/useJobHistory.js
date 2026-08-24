import { useCallback, useEffect, useState } from "react";
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
 */
const CONCURRENCY = 6;

function normalizeStatus(status) {
  if (status === "completed") return "done";
  if (status === "failed" || status === "error") return "error";
  return status; // processing | queued | ...
}

export default function useJobHistory() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [partial, setPartial] = useState(false);
  const [deletingIds, setDeletingIds] = useState(() => new Set());
  const [deletingAll, setDeletingAll] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const rawJobs = await fetchJobs();

        // Base rows immediately — the list renders without waiting on enrichment
        const base = rawJobs.map((job) => ({
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
        }));
        if (!cancelled) setJobs(base);

        // Concurrency-limited enrichment of completed jobs
        const completedIdx = base
          .map((j, i) => (j.status === "done" ? i : -1))
          .filter((i) => i >= 0);
        let failed = false;
        let next = 0;

        async function worker() {
          while (!cancelled) {
            const idx = next++;
            if (idx >= completedIdx.length) return;
            const jobIdx = completedIdx[idx];
            try {
              const result = await fetchJobResult(base[jobIdx].id);
              if (cancelled) return;
              const patch = {
                rows: result?.summary?.rows ?? null,
                cols: result?.summary?.columns ?? null,
                quality: result?.summary?.quality_score ?? null,
                confidence: result?.summary?.overall_confidence ?? null,
                reportAvailable: Boolean(result?.report?.available),
              };
              setJobs((prev) =>
                prev.map((j, i) => (i === jobIdx ? { ...j, ...patch } : j))
              );
            } catch {
              failed = true;
              if (cancelled) return;
              setJobs((prev) =>
                prev.map((j, i) =>
                  i === jobIdx ? { ...j, enrichFailed: true } : j
                )
              );
            }
          }
        }

        await Promise.all(
          Array.from({ length: Math.min(CONCURRENCY, completedIdx.length) }, worker)
        );
        if (!cancelled) setPartial(failed);
      } catch (err) {
        if (!cancelled) setError(err.message || "Failed to load history from the backend.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Remove one analysis from history. Optimistic: the row disappears
   * immediately and is restored if the backend rejects the delete.
   */
  const removeJob = useCallback(async (jobId) => {
    const snapshot = jobs.find((j) => j.id === jobId);
    setDeletingIds((prev) => new Set(prev).add(jobId));
    setJobs((prev) => prev.filter((j) => j.id !== jobId));
    try {
      await deleteJob(jobId);
      setError(null);
    } catch (err) {
      if (snapshot) setJobs((prev) => [...prev, snapshot]);
      setError(err.message || "Failed to delete the analysis.");
      throw err;
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  }, [jobs]);

  /**
   * Clear the whole history. Optimistic: finished rows disappear immediately
   * and are restored if the backend rejects; running rows always stay.
   */
  const removeAllJobs = useCallback(async () => {
    const snapshot = jobs;
    const isFinished = (j) => j.status === "done" || j.status === "error";
    setJobs((prev) => prev.filter((j) => !isFinished(j)));
    setDeletingAll(true);
    try {
      const out = await deleteAllJobs();
      setError(null);
      return out;
    } catch (err) {
      setJobs(snapshot);
      setError(err.message || "Failed to clear history.");
      throw err;
    } finally {
      setDeletingAll(false);
    }
  }, [jobs]);

  return { jobs, loading, error, partial, removeJob, deletingIds, removeAllJobs, deletingAll };
}
