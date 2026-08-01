import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppNavbar from "@/components/AppNavbar";
import { fetchJobs, fetchJobResult, reportDownloadUrl } from "@/lib/api";

const STATUS_LABEL = { completed: "done", failed: "error", processing: "running", queued: "queued" };

function durationLabel(createdAt, updatedAt) {
  const secs = Math.max(0, Math.round((new Date(updatedAt) - new Date(createdAt)) / 1000));
  return `${secs}s`;
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const jobs = await fetchJobs();
        // Enrich completed jobs with row/column counts from their result payload.
        const enriched = await Promise.all(
          jobs.map(async (job) => {
            let rows = null;
            let cols = null;
            if (job.status === "completed") {
              try {
                const result = await fetchJobResult(job.job_id);
                rows = result?.summary?.rows ?? null;
                cols = result?.summary?.columns ?? null;
              } catch {
                // Result may have expired from the in-memory store; ignore.
              }
            }
            return {
              id: job.job_id,
              file: job.filename || "unknown.csv",
              rows,
              cols,
              date: job.created_at?.slice(0, 10) ?? "—",
              duration: durationLabel(job.created_at, job.updated_at),
              status: STATUS_LABEL[job.status] || job.status,
            };
          })
        );
        if (!cancelled) setItems(enriched);
      } catch (err) {
        if (!cancelled) setError(err.message || "Failed to load history from the backend.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, []);

  const doneCount = items.filter((h) => h.status === "done").length;
  const errorCount = items.filter((h) => h.status === "error").length;
  const totalRows = items.reduce((s, h) => s + (h.rows || 0), 0);

  return (
    <div className="dark min-h-screen bg-black font-sans antialiased text-white">
      {/* Consistent ambient background */}
      <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-225 h-125 bg-radial-[ellipse_at_top] from-violet-950/25 via-transparent to-transparent" />
        <div className="page-grid absolute inset-0 opacity-40" />
      </div>

      <AppNavbar />

      <div className="relative z-10 max-w-5xl mx-auto px-6 py-12">
        {/* Page header */}
        <div className="flex items-start justify-between mb-10 flex-wrap gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-violet-500/25 bg-violet-500/8 text-violet-300 text-xs font-medium mb-4">
              <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
              {doneCount} analyses complete
            </div>
            <h1 className="text-4xl font-black text-white tracking-tight">Analysis History</h1>
            <p className="text-white/40 text-sm mt-2">Past analyses and their generated reports.</p>
          </div>
          <button onClick={() => navigate("/analyze")}
            className="px-5 py-2.5 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer shadow-[0_0_16px_rgba(139,92,246,0.35)] self-end">
            New Analysis →
          </button>
        </div>

        {error && <p className="text-red-300 text-sm mb-6">⚠ {error}</p>}

        {/* Summary stat chips */}
        <div className="flex flex-wrap gap-3 mb-8">
          {[
            { label: "Total Runs",    value: items.length,                     color: "border-white/10 text-white/50" },
            { label: "Successful",   value: doneCount,                        color: "border-emerald-500/25 text-emerald-300" },
            { label: "Failed",       value: errorCount,                       color: "border-red-500/25 text-red-300" },
            { label: "Rows Analyzed",value: totalRows.toLocaleString(),       color: "border-violet-500/25 text-violet-300" },
          ].map(s => (
            <div key={s.label} className={`px-4 py-2 rounded-xl border bg-white/2 flex items-center gap-2 ${s.color}`}>
              <span className="font-black text-sm">{s.value}</span>
              <span className="text-white/30 text-xs">{s.label}</span>
            </div>
          ))}
        </div>

        {/* Table */}
        <div className="rounded-2xl border border-white/5 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 bg-white/2">
                <th className="text-left px-6 py-4 text-white/30 font-medium">File</th>
                <th className="text-left px-4 py-4 text-white/30 font-medium">Rows</th>
                <th className="text-left px-4 py-4 text-white/30 font-medium">Cols</th>
                <th className="text-left px-4 py-4 text-white/30 font-medium">Date</th>
                <th className="text-left px-4 py-4 text-white/30 font-medium">Time</th>
                <th className="text-left px-4 py-4 text-white/30 font-medium">Status</th>
                <th className="px-4 py-4" />
              </tr>
            </thead>
            <tbody>
              {items.map((item, i) => (
                <tr key={item.id}
                  className={`border-b border-white/5 hover:bg-white/2 transition-colors ${i === items.length - 1 ? "border-b-0" : ""}`}>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <span className="text-lg">📁</span>
                      <span className="text-white/80 font-medium">{item.file}</span>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-white/40">{item.rows != null ? item.rows.toLocaleString() : "—"}</td>
                  <td className="px-4 py-4 text-white/40">{item.cols ?? "—"}</td>
                  <td className="px-4 py-4 text-white/40">{item.date}</td>
                  <td className="px-4 py-4 text-white/40">{item.duration}</td>
                  <td className="px-4 py-4">
                    {item.status === "done" ? (
                      <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-medium">
                        ✓ Complete
                      </span>
                    ) : item.status === "error" ? (
                      <span className="px-2.5 py-1 rounded-full bg-red-500/10 text-red-400 text-xs font-medium">
                        ✗ Error
                      </span>
                    ) : (
                      <span className="px-2.5 py-1 rounded-full bg-violet-500/10 text-violet-300 text-xs font-medium">
                        ⋯ {item.status}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    {item.status === "done" && (
                      <a href={reportDownloadUrl(item.id)} target="_blank" rel="noreferrer"
                        className="text-violet-400 hover:text-violet-300 text-xs font-medium transition-colors">
                        Download →
                      </a>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && items.length === 0 && !error && (
                <tr>
                  <td colSpan={7} className="px-6 py-10 text-center text-white/20 text-sm">
                    No analyses yet — run one from the Analyze page.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {loading && <p className="text-center text-white/10 text-xs mt-6">Loading history from the backend…</p>}
      </div>

    </div>
  );
}

