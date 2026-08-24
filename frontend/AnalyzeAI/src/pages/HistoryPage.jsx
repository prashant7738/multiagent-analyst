import React from "react";
import { useNavigate } from "react-router-dom";
import { Download, Plus, Trash2 } from "lucide-react";
import AppLayout from "@/layouts/AppLayout";
import Button from "@/components/ui/button";
import useJobHistory from "@/hooks/useJobHistory";
import { reportDownloadUrl } from "@/lib/api";

/**
 * GOAL: find a past analysis and get back to it (or its report) in one scan.
 * A single consistent table over the shared useJobHistory hook — same data
 * shape the Profile page uses, so both surfaces always agree.
 */

function StatusBadge({ status }) {
  if (status === "done")
    return <span className="rounded-full bg-success-subtle px-2 py-0.5 text-xs text-success">Complete</span>;
  if (status === "error")
    return <span className="rounded-full bg-danger-subtle px-2 py-0.5 text-xs text-danger">Failed</span>;
  return <span className="rounded-full bg-raised px-2 py-0.5 text-xs capitalize text-ink-muted">{status}</span>;
}

function DeleteButton({ job, onDelete, busy }) {
  const running = job.status !== "done" && job.status !== "error";
  if (running) return null;
  return (
    <button
      onClick={() => {
        if (window.confirm(`Delete "${job.file}" from history? Its report and charts are removed too.`)) {
          onDelete(job.id);
        }
      }}
      disabled={busy}
      aria-label={`Delete analysis for ${job.file}`}
      className="inline-flex items-center gap-1 text-xs font-medium text-danger transition-opacity hover:opacity-70 disabled:opacity-40"
    >
      <Trash2 size={12} aria-hidden="true" /> Delete
    </button>
  );
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const { jobs, loading, error, partial, removeJob, deletingIds, removeAllJobs, deletingAll } =
    useJobHistory();

  const doneCount = jobs.filter((j) => j.status === "done").length;
  const deletableCount = jobs.filter((j) => j.status === "done" || j.status === "error").length;

  const handleDeleteAll = () => {
    if (
      window.confirm(
        `Delete all ${deletableCount} finished run${deletableCount === 1 ? "" : "s"} from history? Their reports and charts are removed too.`
      )
    ) {
      removeAllJobs().catch(() => {});
    }
  };

  return (
    <AppLayout size="wide">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-3xl font-bold tracking-tight text-ink">Analysis history</h1>
          <p className="tnum mt-1.5 text-sm text-ink-muted">
            {jobs.length} run{jobs.length === 1 ? "" : "s"} · {doneCount} complete
          </p>
        </div>
        <div className="flex items-center gap-2">
          {deletableCount > 0 && (
            <Button variant="danger" onClick={handleDeleteAll} disabled={deletingAll}>
              <Trash2 size={15} aria-hidden="true" />
              {deletingAll ? "Deleting…" : "Delete all"}
            </Button>
          )}
          <Button onClick={() => navigate("/analyze")}>
            <Plus size={15} aria-hidden="true" /> New analysis
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-6 rounded-panel border border-danger bg-danger-subtle px-4 py-3 text-sm text-danger">
          {error}
        </p>
      )}
      {partial && !error && (
        <p role="status" className="mt-6 rounded-panel border border-warning bg-warning-subtle px-4 py-3 text-sm text-warning">
          Some older results have expired from storage; their metrics show as “—”.
        </p>
      )}

      {/* Consistent job table */}
      <div className="mt-8 overflow-x-auto rounded-panel border border-line bg-surface">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
              <th scope="col" className="px-5 py-3.5 font-medium">File</th>
              <th scope="col" className="px-4 py-3.5 font-medium">Rows</th>
              <th scope="col" className="px-4 py-3.5 font-medium">Profile</th>
              <th scope="col" className="px-4 py-3.5 font-medium">Confidence</th>
              <th scope="col" className="px-4 py-3.5 font-medium">Date</th>
              <th scope="col" className="px-4 py-3.5 font-medium">Took</th>
              <th scope="col" className="px-4 py-3.5 font-medium">Status</th>
              <th scope="col" className="px-4 py-3.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {jobs.map((job) => (
              <tr key={job.id} className="transition-colors hover:bg-raised/50">
                <td className="px-5 py-3.5 font-medium text-ink">{job.file}</td>
                <td className="tnum px-4 py-3.5 text-ink-muted">
                  {job.rows != null && !job.enrichFailed ? job.rows.toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3.5 capitalize text-ink-muted">{job.profile}</td>
                <td className="tnum px-4 py-3.5 text-ink-muted">
                  {job.confidence != null ? `${Math.round(job.confidence * 100)}%` : "—"}
                </td>
                <td className="tnum px-4 py-3.5 text-ink-muted">{job.date}</td>
                <td className="tnum px-4 py-3.5 text-ink-muted">{job.duration}</td>
                <td className="px-4 py-3.5">
                  <StatusBadge status={job.status} />
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex items-center justify-end gap-4 whitespace-nowrap">
                    {job.status === "done" && (
                      <>
                        <button
                          onClick={() => navigate(`/analyze/${job.id}`)}
                          className="text-xs font-medium text-accent-ink transition-colors hover:text-accent"
                        >
                          Open
                        </button>
                        {job.reportAvailable && (
                          <a
                            href={reportDownloadUrl(job.id)}
                            target="_blank"
                            rel="noreferrer"
                            aria-label={`Download report for ${job.file}`}
                            className="inline-flex items-center gap-1 text-xs font-medium text-accent-ink transition-colors hover:text-accent"
                          >
                            <Download size={12} aria-hidden="true" /> Report
                          </a>
                        )}
                      </>
                    )}
                    <DeleteButton
                      job={job}
                      busy={deletingIds.has(job.id)}
                      onDelete={(id) => removeJob(id).catch(() => {})}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!loading && jobs.length === 0 && !error && (
          <div className="px-6 py-14 text-center">
            <p className="text-sm text-ink-muted">No analyses yet.</p>
            <Button variant="secondary" size="sm" className="mt-4" onClick={() => navigate("/analyze")}>
              Run your first analysis
            </Button>
          </div>
        )}
        {loading && (
          <p className="px-6 py-10 text-center text-xs text-ink-faint" role="status">
            Loading history…
          </p>
        )}
      </div>
    </AppLayout>
  );
}
