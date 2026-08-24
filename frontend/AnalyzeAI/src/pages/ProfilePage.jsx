import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";
import AppLayout from "@/layouts/AppLayout";
import Button from "@/components/ui/button";
import useJobHistory from "@/hooks/useJobHistory";
import { useAuth } from "@/contexts/AuthContext";

/**
 * GOAL: "what have I done, and how well is it going?" One overview: identity,
 * honest account info (no fake Save), and the same job table as History via
 * the shared hook.
 *
 * Settings tab note: display name/email are read-only on purpose — the auth
 * backend exposes no update endpoint (and no sessions at all; see
 * AuthContext). Showing disabled inputs beats a Save button that lies.
 */
export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { jobs, loading, error, partial, removeJob, deletingIds } = useJobHistory();
  const [activeTab, setActiveTab] = useState("overview");

  if (!user) {
    return (
      <AppLayout size="content">
        <div className="py-24 text-center">
          <h1 className="font-heading text-2xl font-bold text-ink">Sign in to view your profile</h1>
          <p className="mx-auto mt-2 max-w-sm text-sm text-ink-muted">
            Your analyses and reports are only listed when you&apos;re signed in.
          </p>
          <Button className="mt-6" onClick={() => navigate("/login")}>
            Sign in
          </Button>
        </div>
      </AppLayout>
    );
  }

  const initial = user.name?.[0]?.toUpperCase() ?? "U";
  const joinedYear = user.joinedDate ? new Date(user.joinedDate).getFullYear() : null;

  const doneJobs = jobs.filter((j) => j.status === "done");
  const failedJobs = jobs.filter((j) => j.status === "error");
  const confidenceValues = doneJobs.filter((j) => j.confidence != null);
  const avgConfidence =
    confidenceValues.length > 0
      ? Math.round(
          (confidenceValues.reduce((sum, j) => sum + j.confidence, 0) / confidenceValues.length) * 100
        )
      : null;
  const qualityValues = doneJobs.filter((j) => j.quality != null);
  const avgQuality =
    qualityValues.length > 0
      ? Math.round(qualityValues.reduce((sum, j) => sum + j.quality, 0) / qualityValues.length)
      : null;

  const TABS = ["overview", "history", "settings"];

  return (
    <AppLayout size="wide">
      {/* Identity row */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent font-heading text-xl font-bold text-white">
            {initial}
          </span>
          <div>
            <h1 className="font-heading text-2xl font-bold tracking-tight text-ink">{user.name}</h1>
            <p className="text-sm text-ink-muted">
              {user.email}
              {joinedYear ? ` · Member since ${joinedYear}` : ""}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => navigate("/analyze")}>New analysis</Button>
          <Button variant="secondary" onClick={() => { logout(); navigate("/"); }}>
            Log out
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div role="tablist" aria-label="Profile sections" className="mt-8 flex gap-1 border-b border-line">
        {TABS.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm capitalize transition-colors ${
              activeTab === tab
                ? "border-accent font-medium text-ink"
                : "border-transparent text-ink-muted hover:text-ink"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="mt-8">
        {/* ── Overview ── */}
        {activeTab === "overview" && (
          <>
            <dl className="grid grid-cols-2 divide-line rounded-panel border border-line bg-surface sm:grid-cols-4 sm:divide-x">
              {[
                { label: "Analyses run", value: jobs.length },
                { label: "Reports generated", value: doneJobs.length },
                { label: "Avg quality", value: avgQuality != null ? `${avgQuality}%` : "—" },
                { label: "Avg confidence", value: avgConfidence != null ? `${avgConfidence}%` : "—" },
              ].map((s) => (
                <div key={s.label} className="px-5 py-4">
                  <dd className="tnum font-heading text-2xl font-bold text-ink">{s.value}</dd>
                  <dt className="mt-0.5 text-xs text-ink-faint">{s.label}</dt>
                </div>
              ))}
            </dl>

            <h2 className="mt-10 font-heading text-base font-semibold text-ink">Recent runs</h2>
            <ul className="mt-3 divide-y divide-line rounded-panel border border-line bg-surface">
              {jobs.slice(0, 4).map((job) => (
                <li key={job.id} className="flex items-center justify-between gap-3 px-5 py-3.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{job.file}</p>
                    <p className="tnum mt-0.5 text-xs text-ink-muted">
                      {job.date} · {job.duration} ·{" "}
                      {job.status === "done" ? "complete" : job.status === "error" ? "failed" : job.status}
                    </p>
                  </div>
                  <button
                    onClick={() => navigate(`/analyze/${job.id}`)}
                    className="shrink-0 text-xs font-medium text-accent-ink transition-colors hover:text-accent"
                  >
                    Open
                  </button>
                </li>
              ))}
              {!loading && jobs.length === 0 && (
                <li className="px-5 py-6 text-sm text-ink-faint">
                  No runs yet — start your first analysis.
                </li>
              )}
              {loading && (
                <li className="px-5 py-6 text-xs text-ink-faint">Loading…</li>
              )}
            </ul>
          </>
        )}

        {/* ── History ── */}
        {activeTab === "history" && (
          <div className="overflow-x-auto rounded-panel border border-line bg-surface">
            <table className="w-full min-w-[680px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th scope="col" className="px-5 py-3.5 font-medium">File</th>
                  <th scope="col" className="px-4 py-3.5 font-medium">Rows</th>
                  <th scope="col" className="px-4 py-3.5 font-medium">Confidence</th>
                  <th scope="col" className="px-4 py-3.5 font-medium">Date</th>
                  <th scope="col" className="px-4 py-3.5 font-medium">Status</th>
                  <th scope="col" className="px-4 py-3.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td className="px-5 py-3.5 font-medium text-ink">{job.file}</td>
                    <td className="tnum px-4 py-3.5 text-ink-muted">
                      {job.rows != null && !job.enrichFailed ? job.rows.toLocaleString() : "—"}
                    </td>
                    <td className="tnum px-4 py-3.5 text-ink-muted">
                      {job.confidence != null ? `${Math.round(job.confidence * 100)}%` : "—"}
                    </td>
                    <td className="tnum px-4 py-3.5 text-ink-muted">{job.date}</td>
                    <td className="px-4 py-3.5 capitalize text-ink-muted">{job.status}</td>
                    <td className="px-4 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-4 whitespace-nowrap">
                        {job.status === "done" && (
                          <button
                            onClick={() => navigate(`/analyze/${job.id}`)}
                            className="text-xs font-medium text-accent-ink transition-colors hover:text-accent"
                          >
                            Open
                          </button>
                        )}
                        {job.status !== "done" && job.status !== "error" ? null : (
                          <button
                            onClick={() => {
                              if (window.confirm(`Delete "${job.file}" from history? Its report and charts are removed too.`)) {
                                removeJob(job.id).catch(() => {});
                              }
                            }}
                            disabled={deletingIds.has(job.id)}
                            aria-label={`Delete analysis for ${job.file}`}
                            className="inline-flex items-center gap-1 text-xs font-medium text-danger transition-opacity hover:opacity-70 disabled:opacity-40"
                          >
                            <Trash2 size={12} aria-hidden="true" /> Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading && <p className="px-6 py-8 text-center text-xs text-ink-faint">Loading…</p>}
          </div>
        )}

        {/* ── Settings: honest read-only account info ── */}
        {activeTab === "settings" && (
          <div className="max-w-md rounded-panel border border-line bg-surface p-6">
            <h2 className="font-heading text-base font-semibold text-ink">Account</h2>
            <p className="mt-1 text-xs leading-relaxed text-ink-faint">
              Sign-in currently identifies you for this browser only — the backend doesn&apos;t
              support profile updates or password changes yet.
            </p>
            <dl className="mt-5 space-y-4">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-muted">Display name</dt>
                <dd className="mt-1 rounded-(--radius-control) border border-line bg-raised px-3 py-2.5 text-sm text-ink">
                  {user.name || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-muted">Email</dt>
                <dd className="mt-1 rounded-(--radius-control) border border-line bg-raised px-3 py-2.5 text-sm text-ink">
                  {user.email || "—"}
                </dd>
              </div>
            </dl>
            {(failedJobs.length > 0 || partial) && (
              <p className="mt-5 text-xs leading-relaxed text-ink-muted">
                {failedJobs.length > 0 && `${failedJobs.length} run(s) ended in errors.`}{" "}
                {partial && "Some stored results have expired."}
              </p>
            )}
          </div>
        )}

        {(error || partial) && activeTab !== "settings" && (
          <p role="status" className="mt-6 text-xs text-warning">
            {error ? error : "Note: some older results have expired from storage."}
          </p>
        )}
      </div>
    </AppLayout>
  );
}
