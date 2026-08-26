import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Trash2, LogOut, Plus, Eye, Settings, History } from "lucide-react";
import AppLayout from "@/layouts/AppLayout";
import useJobHistory from "@/hooks/useJobHistory";
import { useAuth } from "@/contexts/AuthContext";
import ApiKeysPanel from "@/components/ApiKeysPanel";

const TabNav = ({ tabs, activeTab, setActiveTab }) => {
  return (
    <div className="flex gap-8 border-b border-neutral-200 dark:border-neutral-800">
      {tabs.map((tab) => {
        const icons = {
          overview: Eye,
          history: History,
          settings: Settings,
        };
        const Icon = icons[tab];

        return (
          <motion.button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`relative pb-4 text-sm font-medium capitalize transition-colors flex items-center gap-2 ${
              activeTab === tab
                ? "text-amber-700 dark:text-amber-600"
                : "text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-300"
            }`}
          >
            <Icon className="w-4 h-4" />
            {tab}
            {activeTab === tab && (
              <motion.div
                layoutId="underline"
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-amber-700 dark:bg-amber-600"
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
              />
            )}
          </motion.button>
        );
      })}
    </div>
  );
};

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { jobs, loading } = useJobHistory();
  const [activeTab, setActiveTab] = useState("overview");

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-neutral-950">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center"
        >
          <div className="border border-neutral-200 dark:border-neutral-800 p-8 max-w-md">
            <h1 className="text-3xl font-serif font-bold text-neutral-900 dark:text-white mb-2">
              Sign in to continue
            </h1>
            <p className="text-neutral-600 dark:text-neutral-400 text-sm mb-6">
              Your workspace is only available when you are signed in.
            </p>
            <motion.button
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate("/login")}
              className="w-full px-4 py-3 bg-amber-700 hover:bg-amber-800 text-white font-semibold rounded-sm transition-all"
            >
              Sign in
            </motion.button>
          </div>
        </motion.div>
      </div>
    );
  }

  const initial = user.name?.[0]?.toUpperCase() ?? "U";
  const joinedYear = user.joinedDate ? new Date(user.joinedDate).getFullYear() : null;
  const doneJobs = jobs.filter((j) => j.status === "done");
  const TABS = ["overview", "history", "settings"];

  return (
    <AppLayout size="default">
      <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-12 pb-12 border-b border-neutral-200 dark:border-neutral-800"
        >
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-8">
            {/* User Info */}
            <div className="flex items-center gap-4">
              <motion.div
                className="flex h-16 w-16 items-center justify-center bg-amber-700 text-white font-serif font-bold text-xl rounded-sm"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                {initial}
              </motion.div>
              <div>
                <h1 className="text-3xl font-serif font-bold">{user.name}</h1>
                <p className="text-neutral-600 dark:text-neutral-400 text-sm mt-1">
                  {user.email}
                  {joinedYear ? ` · Member since ${joinedYear}` : ""}
                </p>
              </div>
            </div>

            {/* Action Buttons */}
            <motion.div
              className="flex gap-3"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
            >
              <motion.button
                whileHover={{ y: -1 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => navigate("/analyze")}
                className="px-6 py-3 bg-amber-700 hover:bg-amber-800 text-white font-semibold rounded-sm transition-all flex items-center gap-2 text-sm"
              >
                <Plus className="w-4 h-4" />
                New Analysis
              </motion.button>
              <motion.button
                whileHover={{ y: -1 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => { logout(); navigate("/"); }}
                className="px-6 py-3 border border-neutral-200 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-900 font-semibold rounded-sm transition-all flex items-center gap-2 text-sm"
              >
                <LogOut className="w-4 h-4" />
                Log out
              </motion.button>
            </motion.div>
          </div>
        </motion.div>

        {/* Tab Navigation */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mb-8"
        >
          <TabNav tabs={TABS} activeTab={activeTab} setActiveTab={setActiveTab} />
        </motion.div>

        {/* Tab Content */}
        <div>
          <AnimatePresence mode="wait">
            {/* ── Overview ── */}
            {activeTab === "overview" && (
              <motion.div
                key="overview"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.2 }}
              >
                {/* Stats Grid */}
                <motion.div
                  className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.1 }}
                >
                  {[
                    { label: "Analyses run", value: jobs.length },
                    { label: "Completed", value: doneJobs.length },
                    { label: "Success Rate", value: jobs.length > 0 ? `${Math.round((doneJobs.length / jobs.length) * 100)}%` : "—" },
                  ].map((stat, i) => (
                    <motion.div
                      key={stat.label}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.05 * i }}
                      className="border border-neutral-200 dark:border-neutral-800 p-6"
                    >
                      <div className="text-xs uppercase tracking-widest text-neutral-500 dark:text-neutral-500 font-mono mb-2">
                        {stat.label}
                      </div>
                      <div className="text-3xl font-serif font-bold text-amber-700 dark:text-amber-600">
                        {stat.value}
                      </div>
                    </motion.div>
                  ))}
                </motion.div>

                {/* Recent Analyses */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                  <h2 className="text-2xl font-serif font-bold mb-6">Recent Analyses</h2>
                  {loading ? (
                    <div className="text-center py-8 text-neutral-600 dark:text-neutral-400">Loading…</div>
                  ) : jobs.length === 0 ? (
                    <div className="border border-neutral-200 dark:border-neutral-800 p-8 text-center">
                      <p className="text-neutral-600 dark:text-neutral-400 mb-4">No analyses yet</p>
                      <motion.button
                        whileHover={{ y: -1 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => navigate("/analyze")}
                        className="px-6 py-2 bg-amber-700 hover:bg-amber-800 text-white font-medium rounded-sm transition-all text-sm"
                      >
                        Run First Analysis
                      </motion.button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {jobs.slice(0, 5).map((job, i) => (
                        <motion.div
                          key={job.id}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.2 + i * 0.05 }}
                          className="border border-neutral-200 dark:border-neutral-800 p-4 hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors flex items-center justify-between"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-sm">{job.file}</p>
                            <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">
                              {job.date} · {job.duration}
                            </p>
                          </div>
                          <div className="flex items-center gap-3 ml-4">
                            <div className={`text-xs font-medium px-2 py-1 rounded-sm ${
                              job.status === "done"
                                ? "bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300"
                                : job.status === "error"
                                ? "bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300"
                                : "bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300"
                            }`}>
                              {job.status === "done" ? "Complete" : job.status === "error" ? "Failed" : "Running"}
                            </div>
                            {job.status === "done" && (
                              <motion.button
                                whileHover={{ scale: 1.05 }}
                                whileTap={{ scale: 0.95 }}
                                onClick={() => navigate(`/analyze/${job.id}`)}
                                className="px-3 py-1 bg-amber-700 text-white rounded-sm text-xs font-medium hover:bg-amber-800 transition-all"
                              >
                                View
                              </motion.button>
                            )}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  )}
                </motion.div>
              </motion.div>
            )}

            {/* ── History ── */}
            {activeTab === "history" && (
              <motion.div
                key="history"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.2 }}
              >
                <h2 className="text-2xl font-serif font-bold mb-6">Full Analysis History</h2>
                {loading ? (
                  <div className="text-center py-8 text-neutral-600 dark:text-neutral-400">Loading…</div>
                ) : jobs.length === 0 ? (
                  <div className="border border-neutral-200 dark:border-neutral-800 p-8 text-center">
                    <p className="text-neutral-600 dark:text-neutral-400">No analyses yet</p>
                  </div>
                ) : (
                  <div className="border border-neutral-200 dark:border-neutral-800 divide-y divide-neutral-200 dark:divide-neutral-800">
                    <div className="bg-neutral-50 dark:bg-neutral-900 px-6 py-4 grid grid-cols-5 gap-4 text-xs uppercase tracking-widest font-mono text-neutral-600 dark:text-neutral-400">
                      <div>Analysis</div>
                      <div>Date</div>
                      <div>Status</div>
                      <div>Confidence</div>
                      <div className="text-right">Actions</div>
                    </div>
                    {jobs.map((job, i) => (
                      <motion.div
                        key={job.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: i * 0.02 }}
                        className="px-6 py-4 grid grid-cols-5 gap-4 items-center hover:bg-neutral-50 dark:hover:bg-neutral-900 transition-colors"
                      >
                        <div className="font-medium text-sm">{job.file}</div>
                        <div className="text-sm text-neutral-600 dark:text-neutral-400">{job.date}</div>
                        <div className="text-xs">
                          <span className={`px-2 py-1 rounded-sm ${
                            job.status === "done"
                              ? "bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300"
                              : job.status === "error"
                              ? "bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300"
                              : "bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300"
                          }`}>
                            {job.status === "done" ? "Complete" : job.status === "error" ? "Failed" : "Running"}
                          </span>
                        </div>
                        <div className="text-sm text-neutral-600 dark:text-neutral-400">
                          {job.confidence != null ? `${Math.round(job.confidence * 100)}%` : "—"}
                        </div>
                        <div className="text-right">
                          {job.status === "done" && (
                            <motion.button
                              whileHover={{ scale: 1.05 }}
                              whileTap={{ scale: 0.95 }}
                              onClick={() => navigate(`/analyze/${job.id}`)}
                              className="text-xs text-amber-700 dark:text-amber-600 hover:text-amber-800 font-medium"
                            >
                              View
                            </motion.button>
                          )}
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </motion.div>
            )}

            {/* ── Settings ── */}
            {activeTab === "settings" && (
              <motion.div
                key="settings"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.2 }}
              >
                <div className="max-w-2xl">
                  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                    <h2 className="text-2xl font-serif font-bold mb-6">Account Settings</h2>

                    <div className="border border-neutral-200 dark:border-neutral-800 p-8 mb-6">
                      <p className="text-neutral-600 dark:text-neutral-400 text-sm mb-6">
                        Your account information is read-only for now. Backend support for updates coming soon.
                      </p>

                      <div className="space-y-6">
                        {/* Display Name */}
                        <div>
                          <label className="block text-xs uppercase tracking-widest text-neutral-600 dark:text-neutral-400 font-mono mb-2">
                            Display Name
                          </label>
                          <input
                            type="text"
                            value={user.name || ""}
                            disabled
                            className="w-full px-4 py-2.5 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-100 disabled:opacity-60 cursor-not-allowed rounded-sm text-sm"
                          />
                        </div>

                        {/* Email */}
                        <div>
                          <label className="block text-xs uppercase tracking-widest text-neutral-600 dark:text-neutral-400 font-mono mb-2">
                            Email Address
                          </label>
                          <input
                            type="email"
                            value={user.email || ""}
                            disabled
                            className="w-full px-4 py-2.5 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-100 disabled:opacity-60 cursor-not-allowed rounded-sm text-sm"
                          />
                        </div>
                      </div>
                    </div>

                    <p className="text-xs text-neutral-600 dark:text-neutral-400">
                      For account security, do not upload files containing personal information you are not authorized to process.
                    </p>

                    <ApiKeysPanel />
                  </motion.div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
    </AppLayout>
  );
}
