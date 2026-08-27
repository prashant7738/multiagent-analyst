import React, { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Download, Trash2, Eye, Filter } from "lucide-react";
import AppLayout from "@/layouts/AppLayout";
import useJobHistory from "@/hooks/useJobHistory";
import { reportDownloadUrl } from "@/lib/api";

const StatusBadge = ({ status }) => {
  const statusConfig = {
    done: { bg: "bg-green-100 dark:bg-green-950", text: "text-green-700 dark:text-green-300", label: "Complete" },
    error: { bg: "bg-red-100 dark:bg-red-950", text: "text-red-700 dark:text-red-300", label: "Failed" },
    cancelled: { bg: "bg-neutral-100 dark:bg-neutral-800", text: "text-neutral-600 dark:text-neutral-300", label: "Cancelled" },
    running: { bg: "bg-blue-100 dark:bg-blue-950", text: "text-blue-700 dark:text-blue-300", label: "Running" },
  };
  const config = statusConfig[status] || statusConfig.running;

  return (
    <div className={`inline-flex items-center px-2 py-1 rounded-sm text-xs font-medium ${config.bg} ${config.text}`}>
      {config.label}
    </div>
  );
};

// Mirrors the 6-agent pipeline in AnalyzePage.jsx — kept as plain names here
// since a running job may be watched from a page that never opened its SSE
// stream (e.g. History, reached straight from another tab).
const AGENT_NAMES = [
  "Structural profiling",
  "Semantic tagging",
  "Preprocessing",
  "Statistics & visualization",
  "Quality guardrail",
  "Report assembly",
];

function summarizeProgress(progress) {
  if (!progress || Object.keys(progress).length === 0) return null;
  const completedCount = Object.values(progress).filter((s) => s === "completed").length;
  const runningKey = Object.keys(progress).find((k) => progress[k] === "running");
  const runningIdx = runningKey ? parseInt(runningKey.replace(/\D/g, ""), 10) : null;
  const runningName = runningIdx ? AGENT_NAMES[runningIdx - 1] : null;
  return { completedCount, total: AGENT_NAMES.length, runningName };
}

const RunningProgress = ({ progress }) => {
  const summary = summarizeProgress(progress);
  if (!summary) return <p className="mt-1 text-xs text-ink-muted">Starting…</p>;
  const pct = Math.round((summary.completedCount / summary.total) * 100);
  return (
    <div className="mt-1.5 w-28">
      <p className="truncate text-xs text-ink-muted" title={summary.runningName || undefined}>
        {summary.runningName || "Finishing up…"} · {summary.completedCount}/{summary.total}
      </p>
      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-line">
        <motion.div
          className="h-full rounded-full bg-blue-500"
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4 }}
        />
      </div>
    </div>
  );
};

export default function HistoryPage() {
  const navigate = useNavigate();
  const { jobs, loading, error, removeJob, deletingIds } = useJobHistory();
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [isDarkMode, setIsDarkMode] = useState(() => document.documentElement.classList.contains("dark"));

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDarkMode(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      const matchesSearch = job.file.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === "all" || job.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [jobs, searchQuery, statusFilter]);

  const doneCount = jobs.filter((j) => j.status === "done").length;

  return (
    <AppLayout size="wide">
      <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-12"
        >
          <div className="text-xs uppercase tracking-widest text-accent mb-4 font-mono">
            Analysis History
          </div>
          <h1 className="text-5xl font-serif font-bold mb-4">Your analyses.</h1>
          <p className="text-ink-secondary max-w-2xl">
            View and manage all your past analyses. Each run is deterministic — same CSV, same results.
          </p>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-6 mt-12">
            {[
              { label: "Total Analyses", value: jobs.length },
              { label: "Completed", value: doneCount },
              { label: "Success Rate", value: jobs.length > 0 ? `${Math.round((doneCount / jobs.length) * 100)}%` : "—" },
            ].map((stat, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 * (i + 1) }}
              >
                <div className="text-xs uppercase tracking-widest text-ink-muted font-mono mb-2">
                  {stat.label}
                </div>
                <div className="text-3xl font-serif font-bold text-accent">
                  {stat.value}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Controls */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mb-8 space-y-4"
        >
          {/* Search Bar */}
          <div className="relative flex items-center">
            <Search className="absolute left-4 w-4 h-4 text-neutral-400 pointer-events-none" />
            <input
              type="text"
              placeholder="Search analyses..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-3 bg-raised border border-line text-ink placeholder-ink-muted focus:outline-none focus:border-amber-700 focus:ring-2 focus:ring-amber-700/20 transition-all"
              style={{ paddingLeft: "44px" }}
            />
          </div>

          {/* Filter */}
          <div className="flex gap-3">
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="pl-3 pr-9 py-2 bg-raised border border-line focus:outline-none focus:border-amber-700 cursor-pointer text-sm font-medium rounded-sm w-full"
                style={{
                  appearance: "none",
                  WebkitAppearance: "none",
                  backgroundImage: "none",
                  color: isDarkMode ? "rgb(243, 244, 246)" : "rgb(17, 24, 39)",
                  paddingRight: "2.25rem",
                }}
              >
                <option value="all" style={{ color: isDarkMode ? "rgb(243, 244, 246)" : "rgb(17, 24, 39)" }}>All Status</option>
                <option value="done" style={{ color: isDarkMode ? "rgb(243, 244, 246)" : "rgb(17, 24, 39)" }}>Complete</option>
                <option value="error" style={{ color: isDarkMode ? "rgb(243, 244, 246)" : "rgb(17, 24, 39)" }}>Failed</option>
                <option value="running" style={{ color: isDarkMode ? "rgb(243, 244, 246)" : "rgb(17, 24, 39)" }}>Running</option>
              </select>
              <Filter 
                className="absolute w-4 h-4 pointer-events-none"
                style={{ 
                  color: isDarkMode ? "rgb(229, 231, 235)" : "rgb(55, 65, 81)",
                  right: "0.5rem",
                  top: "50%",
                  transform: "translateY(-50%)"
                }}
              />
            </div>
          </div>
        </motion.div>

        {/* Table */}
        {loading ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-16 text-ink-secondary"
          >
            Loading history…
          </motion.div>
        ) : filteredJobs.length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center py-16 border border-line p-8"
          >
            <p className="text-ink-secondary mb-4">No analyses found</p>
            <motion.button
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate("/analyze")}
              className="px-6 py-2 bg-amber-700 hover:bg-amber-800 text-white font-medium rounded-sm transition-all text-sm"
            >
              Run First Analysis
            </motion.button>
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="border border-line divide-y divide-neutral-200 dark:divide-neutral-800"
          >
            {/* Header */}
            <div className="bg-neutral-50 dark:bg-neutral-900 px-6 py-4 grid grid-cols-6 gap-4 text-xs uppercase tracking-widest font-mono text-ink-secondary">
              <div>Analysis</div>
              <div>Date</div>
              <div>Rows</div>
              <div>Confidence</div>
              <div>Status</div>
              <div className="text-right">Actions</div>
            </div>

            {/* Rows */}
            <div>
              <AnimatePresence>
                {filteredJobs.map((job, i) => (
                  <motion.div
                    key={job.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.05 * i }}
                    className="px-6 py-4 grid grid-cols-6 gap-4 items-center hover:bg-neutral-50 dark:hover:bg-neutral-900/50 transition-colors border-b border-line last:border-0"
                  >
                    <div>
                      <p 
                        className="font-medium text-sm" 
                        style={{ color: isDarkMode ? "rgb(243, 244, 246)" : "rgb(0, 0, 0)" }}
                      >
                        {job.file}
                      </p>
                    </div>
                    <div className="text-sm text-ink-secondary">
                      {job.date}
                    </div>
                    <div className="text-sm text-ink-secondary">
                      {job.rows != null && !job.enrichFailed ? job.rows.toLocaleString() : "—"}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-line rounded-full overflow-hidden">
                          <motion.div
                            className="h-full bg-amber-700"
                            initial={{ width: 0 }}
                            animate={{ width: `${(job.confidence || 0) * 100}%` }}
                            transition={{ duration: 0.8, delay: 0.1 * i }}
                          />
                        </div>
                        <span className="text-xs font-mono text-ink-secondary">
                          {job.confidence != null ? `${Math.round(job.confidence * 100)}%` : "—"}
                        </span>
                      </div>
                    </div>
                    <div>
                      <StatusBadge status={job.status} />
                      {job.status === "running" && <RunningProgress progress={job.progress} />}
                    </div>
                    <div className="flex justify-end gap-2">
                      {job.status === "done" && (
                        <>
                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={() => navigate(`/analyze/${job.id}`)}
                            className="p-2 text-ink-secondary hover:text-amber-700 dark:hover:text-amber-600 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-sm transition-colors"
                            title="View analysis"
                          >
                            <Eye className="w-4 h-4" />
                          </motion.button>
                          {job.reportAvailable && (
                            <motion.a
                              whileHover={{ scale: 1.05 }}
                              whileTap={{ scale: 0.95 }}
                              href={reportDownloadUrl(job.id)}
                              target="_blank"
                              rel="noreferrer"
                              className="p-2 text-ink-secondary hover:text-green-700 dark:hover:text-green-600 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-sm transition-colors"
                              title="Download report"
                            >
                              <Download className="w-4 h-4" />
                            </motion.a>
                          )}
                        </>
                      )}
                      {(job.status === "done" || job.status === "error" || job.status === "cancelled") && (
                        <motion.button
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={() => {
                            if (window.confirm(`Delete "${job.file}"? This cannot be undone.`)) {
                              removeJob(job.id).catch(() => {});
                            }
                          }}
                          disabled={deletingIds.has(job.id)}
                          className="p-2 text-ink-secondary hover:text-red-700 dark:hover:text-red-600 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-sm transition-colors disabled:opacity-50"
                          title="Delete analysis"
                        >
                          <Trash2 className="w-4 h-4" />
                        </motion.button>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
    </AppLayout>
  );
}
