import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { GlowBorderCard } from "@/components/ui/glow-border-card";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { FlipText } from "@/components/ui/flip-text";
import { LightLines } from "@/components/ui/light-lines";
import AppNavbar from "@/components/AppNavbar";
import { useAuth } from "@/contexts/AuthContext";
import { MOCK_HISTORY } from "@/data/mockHistory";

const PROFILE_STATS = [
  { value: 14,  label: "Analyses Run",       suffix: "",  preset: "aurora" },
  { value: 12,  label: "Reports Generated",  suffix: "",  preset: "ocean" },
  { value: 97,  label: "Avg Quality Score",  suffix: "%", preset: "sunset" },
];

const AGENTS_INFO = [
  { id: 1, name: "Structural Profiler",     icon: "🔍", color: "violet" },
  { id: 2, name: "Semantic Tagging",         icon: "🏷️", color: "blue" },
  { id: 3, name: "Preprocessing",            icon: "⚙️", color: "cyan" },
  { id: 4, name: "Statistics & Viz",         icon: "📊", color: "emerald" },
  { id: 5, name: "Quality Guardrail",        icon: "🛡️", color: "amber" },
  { id: 6, name: "Report Assembly",          icon: "📄", color: "violet" },
];

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState("overview");

  if (!user) {
    return (
      <div className="dark min-h-screen bg-black font-sans antialiased text-white flex flex-col">
        <AppNavbar />
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center px-6">
          <span className="text-6xl">🔒</span>
          <h2 className="text-3xl font-black text-white">Sign in to view your profile</h2>
          <p className="text-white/40 text-sm max-w-sm">
            Your analyses, reports, and account settings are only accessible when you&apos;re logged in.
          </p>
          <div className="flex gap-3">
            <button onClick={() => navigate("/login")}
              className="px-6 py-3 rounded-full bg-violet-600 hover:bg-violet-500 text-white font-semibold text-sm transition-colors cursor-pointer">
              Sign In
            </button>
            <button onClick={() => navigate("/signup")}
              className="px-6 py-3 rounded-full border border-white/10 hover:border-white/30 text-white/60 hover:text-white text-sm transition-colors cursor-pointer">
              Create Account
            </button>
          </div>
        </div>
      </div>
    );
  }

  const initial = user.name?.[0]?.toUpperCase() ?? "U";
  const joinedYear = user.joinedDate ? new Date(user.joinedDate).getFullYear() : "2026";

  return (
    <div className="dark min-h-screen bg-black font-sans antialiased text-white flex flex-col">
      <AppNavbar />

      {/* Profile hero */}
      <div className="relative overflow-hidden border-b border-white/5">
        <div className="absolute inset-0 z-0 opacity-40">
          <LightLines
            gradientFrom="#4f46e5"
            gradientTo="#7c3aed"
            lightColor="#a78bfa"
            lineColor="#6d28d9"
            linesOpacity={0.03}
            lightsOpacity={0.5}
          />
        </div>
        <div className="absolute inset-0 z-1 bg-linear-to-b from-black/20 to-black pointer-events-none" />
        <div className="relative z-10 max-w-5xl mx-auto px-6 py-12 flex flex-col sm:flex-row items-center sm:items-end gap-6">
          {/* Avatar */}
          <div className="w-20 h-20 rounded-2xl bg-violet-600 border-2 border-violet-500/50 flex items-center justify-center text-4xl font-black text-white shadow-[0_0_32px_rgba(139,92,246,0.5)]">
            {initial}
          </div>
          {/* Info */}
          <div className="flex-1 text-center sm:text-left">
            <FlipText className="text-3xl font-black text-white tracking-tight" duration={2} loop={false}>
              {user.name}
            </FlipText>
            <p className="text-white/40 text-sm mt-1">{user.email} · Member since {joinedYear}</p>
          </div>
          {/* Actions */}
          <div className="flex gap-3">
            <button onClick={() => navigate("/analyze")}
              className="px-5 py-2.5 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer shadow-[0_0_16px_rgba(139,92,246,0.4)]">
              New Analysis →
            </button>
            <button
              onClick={() => { logout(); navigate("/"); }}
              className="px-5 py-2.5 rounded-full border border-white/10 hover:border-red-500/30 text-white/40 hover:text-red-400 text-sm transition-all duration-200 cursor-pointer">
              Log Out
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-white/5 bg-black/60 backdrop-blur-sm sticky top-16 z-40">
        <div className="max-w-5xl mx-auto px-6 flex gap-0">
          {["overview", "history", "settings"].map((tab) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-5 py-3.5 text-sm font-medium capitalize transition-all duration-200 border-b-2 cursor-pointer
                ${activeTab === tab
                  ? "text-white border-violet-500"
                  : "text-white/30 border-transparent hover:text-white/60"
                }`}>
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-10 w-full">

        {/* ── Overview tab ── */}
        {activeTab === "overview" && (
          <div className="flex flex-col gap-8">
            {/* Stats */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
              {PROFILE_STATS.map((s) => (
                <GlowBorderCard key={s.label} colorPreset={s.preset}
                  width="100%" height="auto" aspectRatio="unset"
                  animationDuration={5} className="bg-[#0a0a0a]">
                  <div className="p-6 flex flex-col gap-1">
                    <div className="flex items-end gap-0.5">
                      <AnimatedNumber value={s.value} className="text-5xl font-black text-white tabular-nums" />
                      <span className="text-2xl font-bold text-white/30 mb-1">{s.suffix}</span>
                    </div>
                    <p className="text-white/40 text-sm">{s.label}</p>
                  </div>
                </GlowBorderCard>
              ))}
            </div>

            {/* Agent pipeline status */}
            <div>
              <h2 className="text-white font-bold text-lg mb-4">Your Pipeline Agents</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                {AGENTS_INFO.map((a) => (
                  <div key={a.id}
                    className="flex flex-col items-center gap-2 p-4 rounded-2xl border border-white/5 bg-white/2 hover:border-violet-500/20 hover:bg-violet-500/5 transition-all duration-200">
                    <span className="text-2xl">{a.icon}</span>
                    <span className="text-white/50 text-xs text-center leading-snug">{a.name}</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
                  </div>
                ))}
              </div>
            </div>

            {/* Recent analyses */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-white font-bold text-lg">Recent Analyses</h2>
                <button onClick={() => setActiveTab("history")}
                  className="text-violet-400 hover:text-violet-300 text-xs transition-colors cursor-pointer">
                  View all →
                </button>
              </div>
              <div className="flex flex-col gap-3">
                {MOCK_HISTORY.slice(0, 3).map((item) => (
                  <div key={item.id}
                    className="flex items-center justify-between p-4 rounded-xl border border-white/5 bg-white/2 hover:border-white/10 transition-colors">
                    <div className="flex items-center gap-3">
                      <span className="text-xl">📁</span>
                      <div>
                        <p className="text-white/80 text-sm font-medium">{item.file}</p>
                        <p className="text-white/30 text-xs">{item.rows.toLocaleString()} rows · {item.cols} cols · {item.date} · {item.duration}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {item.status === "done" ? (
                        <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs">✓ Complete</span>
                      ) : (
                        <span className="px-2.5 py-1 rounded-full bg-red-500/10 text-red-400 text-xs">✗ Error</span>
                      )}
                      {item.status === "done" && (
                        <button className="text-violet-400 hover:text-violet-300 text-xs transition-colors cursor-pointer">
                          Download →
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── History tab ── */}
        {activeTab === "history" && (
          <div className="flex flex-col gap-6">
            {/* Summary stat chips */}
            <div className="flex flex-wrap gap-3">
              {[
                { label: "Total Runs",    value: MOCK_HISTORY.length,                                                      color: "border-white/10 text-white/50" },
                { label: "Successful",    value: MOCK_HISTORY.filter(h => h.status === "done").length,                     color: "border-emerald-500/25 text-emerald-300" },
                { label: "Failed",        value: MOCK_HISTORY.filter(h => h.status === "error").length,                    color: "border-red-500/25 text-red-300" },
                { label: "Rows Analyzed", value: MOCK_HISTORY.reduce((s, h) => s + h.rows, 0).toLocaleString(),            color: "border-violet-500/25 text-violet-300" },
              ].map(s => (
                <div key={s.label} className={`px-4 py-2 rounded-xl border bg-white/2 flex items-center gap-2 ${s.color}`}>
                  <span className="font-black text-sm">{s.value}</span>
                  <span className="text-white/30 text-xs">{s.label}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between">
              <h2 className="text-white font-bold text-lg">All Analyses</h2>
              <button onClick={() => navigate("/analyze")}
                className="px-5 py-2 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer">
                New Analysis →
              </button>
            </div>
            <div className="rounded-2xl border border-white/5 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5 bg-white/2">
                    <th className="text-left px-5 py-4 text-white/30 font-medium">File</th>
                    <th className="text-left px-4 py-4 text-white/30 font-medium">Rows</th>
                    <th className="text-left px-4 py-4 text-white/30 font-medium">Cols</th>
                    <th className="text-left px-4 py-4 text-white/30 font-medium">Date</th>
                    <th className="text-left px-4 py-4 text-white/30 font-medium">Time</th>
                    <th className="text-left px-4 py-4 text-white/30 font-medium">Status</th>
                    <th className="px-4 py-4" />
                  </tr>
                </thead>
                <tbody>
                  {MOCK_HISTORY.map((item, i) => (
                    <tr key={item.id}
                      className={`border-b border-white/5 hover:bg-white/2 transition-colors ${i === MOCK_HISTORY.length - 1 ? "border-b-0" : ""}`}>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <span className="text-lg">📁</span>
                          <span className="text-white/80 font-medium">{item.file}</span>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-white/40">{item.rows.toLocaleString()}</td>
                      <td className="px-4 py-4 text-white/40">{item.cols}</td>
                      <td className="px-4 py-4 text-white/40">{item.date}</td>
                      <td className="px-4 py-4 text-white/40">{item.duration}</td>
                      <td className="px-4 py-4">
                        {item.status === "done" ? (
                          <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-medium">✓ Complete</span>
                        ) : (
                          <span className="px-2.5 py-1 rounded-full bg-red-500/10 text-red-400 text-xs font-medium">✗ Error</span>
                        )}
                      </td>
                      <td className="px-4 py-4">
                        {item.status === "done" && (
                          <button className="text-violet-400 hover:text-violet-300 text-xs font-medium transition-colors cursor-pointer">
                            Download →
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Settings tab ── */}
        {activeTab === "settings" && (
          <div className="flex flex-col gap-6 max-w-lg">
            <h2 className="text-white font-bold text-lg">Account Settings</h2>
            <GlowBorderCard colorPreset="custom" width="100%" height="auto"
              aspectRatio="unset" animationDuration={8} className="bg-[#0a0a0a]">
              <div className="p-6 flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <label className="text-white/50 text-xs font-semibold tracking-widest uppercase">Display Name</label>
                  <input defaultValue={user.name}
                    className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-violet-500/60 transition-all cursor-text" />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-white/50 text-xs font-semibold tracking-widest uppercase">Email</label>
                  <input defaultValue={user.email} type="email"
                    className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-sm outline-none focus:border-violet-500/60 transition-all cursor-text" />
                </div>
                <button className="self-start px-6 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer">
                  Save Changes
                </button>
              </div>
            </GlowBorderCard>
          </div>
        )}
      </div>
    </div>
  );
}
