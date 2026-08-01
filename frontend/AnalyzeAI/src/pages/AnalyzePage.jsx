import React, { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AppNavbar from "@/components/AppNavbar";
import DatasetChat from "@/components/DatasetChat";
import { analyzeCsv, subscribeToJobStream, fetchJob, fetchJobResult, reportDownloadUrl } from "@/lib/api";

// ─── Agent definitions ────────────────────────────────────────────────────────
const AGENTS = [
  {
    id: 1,
    name: "Raw Structural Profiler",
    description: "Reads the CSV, records dimensions, data types, missing values, and duplicate rates without modifying anything.",
    icon: "🔍",
    color: { border: "border-blue-500/40", bg: "bg-blue-500/8", glow: "shadow-[0_0_24px_rgba(59,130,246,0.15)]", badge: "bg-blue-500/15 text-blue-300", bar: "bg-blue-500", text: "text-blue-400", dim: "text-blue-400/50" },
  },
  {
    id: 2,
    name: "Semantic Tagging Agent",
    description: "Infers intended column types and assigns business context tags (currency, date, identifier, geographic indicator) via one LLM call.",
    icon: "🏷️",
    color: { border: "border-violet-500/40", bg: "bg-violet-500/8", glow: "shadow-[0_0_24px_rgba(139,92,246,0.15)]", badge: "bg-violet-500/15 text-violet-300", bar: "bg-violet-500", text: "text-violet-400", dim: "text-violet-400/50" },
  },
  {
    id: 3,
    name: "Preprocessing Agent",
    description: "Executes the cleaning blueprint — type coercion, median/mean imputation, IQR outlier clipping, and Min-Max normalization.",
    icon: "⚙️",
    color: { border: "border-cyan-500/40", bg: "bg-cyan-500/8", glow: "shadow-[0_0_24px_rgba(6,182,212,0.15)]", badge: "bg-cyan-500/15 text-cyan-300", bar: "bg-cyan-500", text: "text-cyan-400", dim: "text-cyan-400/50" },
  },
  {
    id: 4,
    name: "Visualization & Statistics Agent",
    description: "Computes descriptive stats, correlation matrices, trend regression, and generates bar/line/distribution charts as static PNG/SVG files.",
    icon: "📊",
    color: { border: "border-amber-500/40", bg: "bg-amber-500/8", glow: "shadow-[0_0_24px_rgba(245,158,11,0.15)]", badge: "bg-amber-500/15 text-amber-300", bar: "bg-amber-500", text: "text-amber-400", dim: "text-amber-400/50" },
  },
  {
    id: 5,
    name: "Quality Guardrail Agent",
    description: "Cross-checks every number and chart. Enforces confidence threshold C(I) ≥ 0.95. Halts pipeline and routes back if validation fails.",
    icon: "🛡️",
    color: { border: "border-emerald-500/40", bg: "bg-emerald-500/8", glow: "shadow-[0_0_24px_rgba(16,185,129,0.15)]", badge: "bg-emerald-500/15 text-emerald-300", bar: "bg-emerald-500", text: "text-emerald-400", dim: "text-emerald-400/50" },
  },
  {
    id: 6,
    name: "Report Assembly Agent",
    description: "Generates plain-language narrative from verified statistics via LLM, then compiles everything into a PDF/HTML report using Jinja2/WeasyPrint.",
    icon: "📄",
    color: { border: "border-rose-500/40", bg: "bg-rose-500/8", glow: "shadow-[0_0_24px_rgba(244,63,94,0.15)]", badge: "bg-rose-500/15 text-rose-300", bar: "bg-rose-500", text: "text-rose-400", dim: "text-rose-400/50" },
  },
];

const STATUS = { PENDING: "pending", RUNNING: "running", DONE: "done", ERROR: "error" };

// "Agent 1" .. "Agent 6" (as emitted by the SSE stream) -> AGENTS[].id
const agentIdFromLabel = (label) => Number((/\d+/.exec(label || "") || [])[0]);

const DATA_TYPES = ["Sales Records", "Transaction Logs", "Expense Sheets", "Financial Statements", "Inventory Data", "Revenue Reports"];
const PREPROCESSING_PROFILES = [
  { value: "strict", label: "Strict", description: "Best for messy finance or sales exports." },
  { value: "balanced", label: "Balanced", description: "Default mix of safety and flexibility." },
  { value: "lenient", label: "Lenient", description: "Keeps more data when sources are noisy." },
];

const DEFAULT_RUN_CONFIG = {
  preprocessingProfile: "balanced",
  currencyMaxAbsValue: "1000000000",
  knnImputerNeighbors: "5",
  reconciliationAbsTol: "1.0",
};

const toNumberOrNull = (value) => {
  if (value === "" || value == null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const buildAnalysisConfig = (config) => {
  const preprocessingConfig = {};
  const currencyMaxAbsValue = toNumberOrNull(config.currencyMaxAbsValue);
  const knnImputerNeighbors = toNumberOrNull(config.knnImputerNeighbors);
  const reconciliationAbsTol = toNumberOrNull(config.reconciliationAbsTol);

  if (currencyMaxAbsValue != null) preprocessingConfig.currency_max_abs_value = currencyMaxAbsValue;
  if (knnImputerNeighbors != null) preprocessingConfig.knn_imputer_neighbors = knnImputerNeighbors;
  if (reconciliationAbsTol != null) preprocessingConfig.reconciliation_abs_tol = reconciliationAbsTol;

  return {
    preprocessingProfile: config.preprocessingProfile || "balanced",
    preprocessingConfig,
  };
};

// ─── Agent Card ───────────────────────────────────────────────────────────────
function AgentCard({ agent, index, total }) {
  const { status, color, name, description, icon, duration, summary } = agent;
  const isRunning = status === STATUS.RUNNING;
  const isDone    = status === STATUS.DONE;
  const isError   = status === STATUS.ERROR;
  const isPending = status === STATUS.PENDING;

  return (
    <div className="flex gap-0">
      {/* Left number + connector column */}
      <div className="flex flex-col items-center w-12 shrink-0 pt-1">
        <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-sm shrink-0 border transition-all duration-500
          ${isDone    ? `${color.bg} ${color.border} ${color.glow}` : ""}
          ${isRunning ? `${color.bg} ${color.border} ${color.glow}` : ""}
          ${isPending ? "bg-white/3 border-white/8" : ""}
          ${isError   ? "bg-red-500/10 border-red-500/30" : ""}
        `}>
          {isDone    && <span className={`text-xs font-bold ${color.text}`}>✓</span>}
          {isError   && <span className="text-xs font-bold text-red-400">✗</span>}
          {isRunning && <span className="animate-pulse">{icon}</span>}
          {isPending && <span className="text-xs text-white/15 font-mono">{index + 1}</span>}
        </div>
        {index < total - 1 && (
          <div className={`w-px flex-1 mt-1 mb-1 transition-all duration-700 ${isDone ? `${color.bar} opacity-30` : "bg-white/6"}`}
            style={{ minHeight: "1.5rem" }} />
        )}
      </div>

      {/* Card */}
      <div className={`relative flex-1 mb-3 rounded-2xl border p-4 transition-all duration-500 overflow-hidden
        ${isDone    ? `${color.border} ${color.bg}` : ""}
        ${isRunning ? `${color.border} ${color.bg} ${color.glow}` : ""}
        ${isPending ? "border-white/6 bg-white/1.5" : ""}
        ${isError   ? "border-red-500/30 bg-red-500/5" : ""}
      `}>
        {/* Scan line animation while running */}
        {isRunning && (
          <div className="absolute inset-0 overflow-hidden rounded-2xl pointer-events-none">
            <div className="absolute left-0 right-0 h-px bg-linear-to-r from-transparent via-white/20 to-transparent"
              style={{ animation: "scanline 2s ease-in-out infinite" }} />
          </div>
        )}

        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-lg border transition-all duration-300
            ${isDone || isRunning ? `${color.bg} ${color.border}` : "bg-white/3 border-white/8"}
          `}>
            <span className={isPending ? "opacity-20" : ""}>{icon}</span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded ${
                  isDone || isRunning ? color.badge : "bg-white/5 text-white/20"
                }`}>AGENT {index + 1}</span>
                <h3 className={`text-sm font-semibold transition-colors ${
                  isDone || isRunning ? "text-white" : "text-white/30"
                }`}>{name}</h3>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {duration && <span className={`text-[10px] font-mono ${color.dim}`}>{duration}s</span>}
                {isPending && <span className="text-white/15 text-xs font-mono">waiting</span>}
                {isRunning && (
                  <span className={`flex items-center gap-1.5 text-xs font-medium ${color.text}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${color.bar} animate-pulse`} />
                    processing
                  </span>
                )}
                {isDone  && <span className={`text-xs font-semibold ${color.text}`}>✓ complete</span>}
                {isError && <span className="text-xs font-semibold text-red-400">✗ failed</span>}
              </div>
            </div>

            <p className={`text-xs mt-1.5 leading-relaxed transition-colors ${
              isDone || isRunning ? "text-white/40" : "text-white/15"
            }`}>{description}</p>

            {summary && (
              <div className={`mt-2.5 flex items-center gap-2 text-xs font-mono px-3 py-2 rounded-lg border ${color.bg} ${color.border} ${color.text}`}>
                <span className="opacity-60">›</span>
                <span>{summary}</span>
              </div>
            )}

            {isRunning && (
              <div className="mt-2.5 h-0.5 bg-white/5 rounded-full overflow-hidden">
                <div className={`h-full ${color.bar} rounded-full`}
                  style={{ animation: "indeterminate 1.8s ease-in-out infinite" }} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function AnalyzePage() {
  const navigate = useNavigate();
  const { jobId: routeJobId } = useParams();
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [phase, setPhase] = useState("upload"); // upload | running | done | error
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loadedJobName, setLoadedJobName] = useState(null);
  const [runConfig, setRunConfig] = useState({ ...DEFAULT_RUN_CONFIG });
  const [agentStates, setAgentStates] = useState(
    AGENTS.map((a) => ({ ...a, status: STATUS.PENDING, duration: null, summary: null }))
  );
  const [elapsedTotal, setElapsedTotal] = useState(0);
  const [jobId, setJobId] = useState(null);
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const eventSourceRef = useRef(null);
  const timerRef = useRef(null);
  const agentStartRef = useRef({});
  const runStatusRef = useRef("idle"); // idle | running | done | error

  const closeStream = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  };

  useEffect(() => () => closeStream(), []); // cleanup on unmount

  useEffect(() => {
    if (!routeJobId) return;

    let cancelled = false;

    (async () => {
      setHistoryLoading(true);
      setErrorMessage(null);
      setResult(null);
      setPhase("upload");
      setFile(null);
      setLoadedJobName(null);
      closeStream();

      try {
        const [job, data] = await Promise.all([fetchJob(routeJobId), fetchJobResult(routeJobId)]);
        if (cancelled) return;

        setJobId(routeJobId);
        setLoadedJobName(job?.filename || "historical analysis");
        setResult(data);
        setAgentStates(AGENTS.map((a) => ({ ...a, status: STATUS.DONE, duration: null, summary: null })));
        setElapsedTotal(0);
        runStatusRef.current = "done";
        setPhase("done");
      } catch (err) {
        if (cancelled) return;
        setErrorMessage(err.message || "Failed to load the saved analysis.");
        setPhase("error");
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [routeJobId]);

  const acceptFile = (f) => { if (f && f.name.endsWith(".csv")) setFile(f); };

  const onDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false); acceptFile(e.dataTransfer.files[0]);
  }, []);

  const markAgent = (id, patch) => setAgentStates((p) => p.map((a) => (a.id === id ? { ...a, ...patch } : a)));

  const fail = (message) => {
    runStatusRef.current = "error";
    closeStream();
    setErrorMessage(message);
    setPhase("error");
    setAgentStates((p) => p.map((a) => (a.status === STATUS.RUNNING ? { ...a, status: STATUS.ERROR } : a)));
  };

  const finish = async (id) => {
    runStatusRef.current = "done";
    try {
      const data = await fetchJobResult(id);
      setResult(data);
    } catch (err) {
      // Progress already reached 100%; surface the fetch failure without discarding it.
      setErrorMessage(err.message || "Failed to load the analysis result.");
    } finally {
      closeStream();
      setPhase("done");
    }
  };

  const handleStreamEvent = (id, name, data) => {
    if (name === "progress" && data.agent) {
      const agentId = agentIdFromLabel(data.agent);
      if (data.status === "running") {
        agentStartRef.current[agentId] = Date.now();
        markAgent(agentId, { status: STATUS.RUNNING });
      } else if (data.status === "completed") {
        const started = agentStartRef.current[agentId];
        const duration = started ? ((Date.now() - started) / 1000).toFixed(1) : null;
        markAgent(agentId, { status: STATUS.DONE, duration, summary: data.message || null });
      }
      return;
    }
    if (name === "charts_generated") {
      markAgent(4, { summary: `${data.detail?.count ?? 0} chart(s) generated` });
      return;
    }
    if (name === "validation_passed") {
      markAgent(5, { summary: `Confidence ${data.detail?.score ?? "?"} · validation passed` });
      return;
    }
    if (name === "validation_failed") {
      markAgent(5, { status: STATUS.ERROR, summary: "Validation failed — see report for details" });
      return;
    }
    if (name === "report_generated") {
      markAgent(6, { summary: "Report generated" });
      return;
    }
    if (name === "pipeline_failed") {
      fail(data.message || "Pipeline failed.");
      return;
    }
    if (name === "error") {
      fail(data.message || "Stream error.");
      return;
    }
    if (name === "completed") {
      finish(id);
    }
  };

  const runPipeline = async () => {
    if (!file) return;
    runStatusRef.current = "running";
    setPhase("running");
    setErrorMessage(null);
    setResult(null);
    agentStartRef.current = {};
    setAgentStates(AGENTS.map((a) => ({ ...a, status: STATUS.PENDING, duration: null, summary: null })));

    const startTime = Date.now();
    timerRef.current = setInterval(() => setElapsedTotal(Math.floor((Date.now() - startTime) / 1000)), 1000);

    try {
      const analysisConfig = buildAnalysisConfig(runConfig);
      const { job_id, stream_url } = await analyzeCsv(file, analysisConfig);
      setJobId(job_id);
      eventSourceRef.current = subscribeToJobStream(stream_url, {
        onEvent: (name, data) => handleStreamEvent(job_id, name, data),
        onError: () => {
          // EventSource fires this on network hiccups too; only fail if the
          // job never reached a terminal state (stream would otherwise retry).
          if (runStatusRef.current === "running") fail("Lost connection to the analysis stream.");
        },
      });
    } catch (err) {
      fail(err.message || "Failed to start the analysis.");
    }
  };

  const reset = () => {
    runStatusRef.current = "idle";
    closeStream();
    setFile(null); setPhase("upload"); setElapsedTotal(0);
    setJobId(null); setResult(null); setErrorMessage(null);
    setLoadedJobName(null);
    setHistoryLoading(false);
    navigate("/analyze");
    setAgentStates(AGENTS.map(a => ({ ...a, status: STATUS.PENDING, duration: null, summary: null })));
  };

  const doneCount  = agentStates.filter(a => a.status === STATUS.DONE).length;
  const progressPct = (doneCount / AGENTS.length) * 100;

  return (
    <div className="dark min-h-screen bg-black font-sans antialiased text-white">
      {/* Consistent ambient background — same as all other inner pages */}
      <div className="fixed inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-225 h-125 bg-radial-[ellipse_at_top] from-violet-950/25 via-transparent to-transparent" />
        <div className="page-grid absolute inset-0 opacity-40" />
      </div>

      <AppNavbar />

      {/* ── Upload ─────────────────────────────────────────── */}
      {phase === "upload" && !routeJobId && (
        <div className="relative z-10 flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] py-16">
          <div className="w-full max-w-3xl mx-auto px-6 flex flex-col items-center gap-10">
            <div className="text-center">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-violet-500/25 bg-violet-500/8 text-violet-300 text-xs font-medium mb-5">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
                6-Agent AI Pipeline · LangGraph DAG
              </div>
              <h1 className="text-5xl font-black text-white tracking-tight leading-tight">
                Analyze Your{" "}
                <span className="text-transparent bg-clip-text bg-linear-to-r from-violet-400 to-cyan-400">Data</span>
              </h1>
              <p className="mt-4 text-white/40 text-base max-w-lg mx-auto leading-relaxed">
                Upload a CSV file. Six specialized AI agents will profile, clean, visualize, and compile a full analytical report end-to-end.
              </p>
            </div>

            <div className="w-full rounded-3xl border border-white/8 bg-white/2 backdrop-blur-sm p-5 shadow-[0_0_40px_rgba(139,92,246,0.08)]">
              <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
                <div>
                  <h2 className="text-white font-semibold text-sm uppercase tracking-[0.18em]">Run settings</h2>
                  <p className="text-white/30 text-xs mt-1">These settings are saved with the job and passed to Agent 3.</p>
                </div>
                <span className="px-2.5 py-1 rounded-full border border-cyan-500/20 bg-cyan-500/8 text-cyan-300 text-[10px] font-mono uppercase tracking-[0.18em]">
                  configurable pipeline
                </span>
              </div>

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <label className="flex flex-col gap-2">
                  <span className="text-white/40 text-xs font-semibold uppercase tracking-widest">Preprocessing profile</span>
                  <select
                    value={runConfig.preprocessingProfile}
                    onChange={(e) => setRunConfig((prev) => ({ ...prev, preprocessingProfile: e.target.value }))}
                    className="bg-black/40 border border-white/10 rounded-xl px-3 py-3 text-white text-sm outline-none focus:border-violet-500/60 transition-all cursor-pointer"
                  >
                    {PREPROCESSING_PROFILES.map((profile) => (
                      <option key={profile.value} value={profile.value}>{profile.label}</option>
                    ))}
                  </select>
                </label>

                <label className="flex flex-col gap-2">
                  <span className="text-white/40 text-xs font-semibold uppercase tracking-widest">Currency max abs value</span>
                  <input
                    type="number"
                    min="0"
                    step="1000000"
                    value={runConfig.currencyMaxAbsValue}
                    onChange={(e) => setRunConfig((prev) => ({ ...prev, currencyMaxAbsValue: e.target.value }))}
                    className="bg-black/40 border border-white/10 rounded-xl px-3 py-3 text-white text-sm outline-none focus:border-violet-500/60 transition-all cursor-text"
                  />
                </label>

                <label className="flex flex-col gap-2">
                  <span className="text-white/40 text-xs font-semibold uppercase tracking-widest">KNN imputer neighbors</span>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={runConfig.knnImputerNeighbors}
                    onChange={(e) => setRunConfig((prev) => ({ ...prev, knnImputerNeighbors: e.target.value }))}
                    className="bg-black/40 border border-white/10 rounded-xl px-3 py-3 text-white text-sm outline-none focus:border-violet-500/60 transition-all cursor-text"
                  />
                </label>

                <label className="flex flex-col gap-2">
                  <span className="text-white/40 text-xs font-semibold uppercase tracking-widest">Reconciliation tolerance</span>
                  <input
                    type="number"
                    min="0"
                    step="0.1"
                    value={runConfig.reconciliationAbsTol}
                    onChange={(e) => setRunConfig((prev) => ({ ...prev, reconciliationAbsTol: e.target.value }))}
                    className="bg-black/40 border border-white/10 rounded-xl px-3 py-3 text-white text-sm outline-none focus:border-violet-500/60 transition-all cursor-text"
                  />
                </label>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {PREPROCESSING_PROFILES.map((profile) => (
                  <button
                    key={profile.value}
                    type="button"
                    onClick={() => setRunConfig((prev) => ({ ...prev, preprocessingProfile: profile.value }))}
                    className={`px-3 py-2 rounded-xl border text-left transition-all cursor-pointer ${
                      runConfig.preprocessingProfile === profile.value
                        ? "border-violet-500/40 bg-violet-500/10 text-violet-200"
                        : "border-white/8 bg-white/2 text-white/40 hover:text-white/70 hover:border-white/15"
                    }`}
                  >
                    <div className="text-sm font-semibold">{profile.label}</div>
                    <div className="text-[11px] mt-0.5 leading-snug max-w-[16rem]">{profile.description}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Drop zone */}
            <div
              onClick={() => fileInputRef.current?.click()}
              onDrop={onDrop}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              className={`relative w-full rounded-3xl border-2 border-dashed p-14 flex flex-col items-center gap-5 cursor-pointer transition-all duration-300 group
                ${dragging  ? "border-violet-400 bg-violet-500/10 shadow-[0_0_60px_rgba(139,92,246,0.25)]"
                : file      ? "border-emerald-500/50 bg-emerald-500/5 shadow-[0_0_40px_rgba(16,185,129,0.1)]"
                : "border-white/10 bg-white/1.5 hover:border-violet-500/40 hover:bg-violet-500/5 hover:shadow-[0_0_40px_rgba(139,92,246,0.12)]"}`}
            >
              <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
                onChange={(e) => acceptFile(e.target.files[0])} />

              {file ? (
                <>
                  <div className="relative flex items-center justify-center w-20 h-20">
                    <div className="absolute inset-0 rounded-full border border-emerald-500/20 animate-ping" />
                    <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
                      <svg viewBox="0 0 24 24" className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                  </div>
                  <div className="text-center">
                    <p className="text-white font-semibold text-lg">{file.name}</p>
                    <p className="text-white/40 text-sm mt-1">{(file.size / 1024).toFixed(1)} KB · CSV</p>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); setFile(null); }}
                    className="text-white/25 hover:text-white/60 text-xs transition-colors cursor-pointer">
                    ✕ Remove
                  </button>
                </>
              ) : (
                <>
                  <div className="relative flex items-center justify-center w-20 h-20">
                    <div className="absolute inset-0 rounded-full border border-white/5 group-hover:border-violet-500/15 transition-colors" />
                    <div className="absolute inset-3 rounded-full border border-white/5 group-hover:border-violet-500/10 transition-colors" />
                    <div className="w-14 h-14 rounded-2xl bg-white/3 border border-white/8 group-hover:border-violet-500/20 group-hover:bg-violet-500/5 flex items-center justify-center transition-all">
                      <svg viewBox="0 0 24 24" className="w-7 h-7 text-white/25 group-hover:text-violet-400 transition-colors" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </div>
                  </div>
                  <div className="text-center">
                    <p className="text-white/60 font-semibold group-hover:text-white/80 transition-colors">Drop your CSV file here</p>
                    <p className="text-white/25 text-sm mt-1">or click to browse</p>
                  </div>
                  <p className="text-white/15 text-xs">Supports .csv · up to 100 MB</p>
                </>
              )}
            </div>

            {/* Data type pills */}
            <div className="flex flex-wrap gap-2 justify-center">
              {DATA_TYPES.map(t => (
                <span key={t} className="px-3 py-1 rounded-full border border-white/8 bg-white/2 text-white/25 text-xs font-medium">{t}</span>
              ))}
            </div>

            <button onClick={runPipeline} disabled={!file}
              className={`px-14 py-4 rounded-full text-base font-bold tracking-wide transition-all duration-300 cursor-pointer
                ${file ? "bg-violet-600 hover:bg-violet-500 text-white shadow-[0_0_40px_rgba(139,92,246,0.55)] hover:shadow-[0_0_55px_rgba(139,92,246,0.75)] hover:scale-105"
                : "bg-white/4 text-white/20 cursor-not-allowed"}`}>
              {file ? "Launch Pipeline →" : "Select a CSV file first"}
            </button>

            {/* Agent flow preview */}
            <div className="flex items-center gap-1.5 flex-wrap justify-center">
              {AGENTS.map((a, i) => (
                <div key={a.id} className="flex items-center gap-1.5">
                  <div title={a.name} className={`w-7 h-7 rounded-lg ${a.color.bg} border ${a.color.border} flex items-center justify-center text-sm cursor-default`}>
                    {a.icon}
                  </div>
                  {i < AGENTS.length - 1 && <span className="text-white/10 text-xs">→</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {routeJobId && historyLoading && (
        <div className="relative z-10 flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] py-16 px-6 text-center">
          <div className="rounded-3xl border border-white/8 bg-white/2 px-8 py-10 max-w-md">
            <div className="text-white/80 text-lg font-semibold">Loading saved analysis…</div>
            <p className="mt-2 text-white/35 text-sm">Restoring the stored result and chat transcript for this past run.</p>
          </div>
        </div>
      )}

      {/* ── Running / Done / Error ────────────────────────── */}
      {(phase === "running" || phase === "done" || phase === "error") && (
        <div className="relative z-10 max-w-3xl mx-auto px-6 py-10">
          <div className="mb-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-medium mb-3 ${
                  phase === "done"
                    ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-300"
                    : phase === "error"
                    ? "border-red-500/30 bg-red-500/8 text-red-300"
                    : "border-violet-500/30 bg-violet-500/8 text-violet-300"
                }`}>
                  {phase === "done"
                    ? <><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> All 6 agents complete</>
                    : phase === "error"
                    ? <><span className="w-1.5 h-1.5 rounded-full bg-red-400" /> Pipeline failed</>
                    : <><span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" /> Pipeline running · {elapsedTotal}s elapsed</>
                  }
                </div>
                <h1 className="text-3xl font-black text-white tracking-tight">
                  {phase === "done" ? "Analysis Complete" : phase === "error" ? "Analysis Failed" : "Analysis in Progress"}
                </h1>
                <p className="text-white/35 text-sm mt-1">
                  {routeJobId ? (loadedJobName ? `${loadedJobName} · restored from history` : "Saved analysis") : `${file?.name} · ${(file?.size / 1024).toFixed(1)} KB`}
                </p>
              </div>
              {phase === "error" && (
                <div className="flex gap-2 shrink-0 mt-1">
                  <button onClick={reset}
                    className="px-4 py-2 rounded-full border border-red-500/30 hover:border-red-500/50 text-red-300 hover:text-red-200 text-sm transition-all cursor-pointer">
                    Try again
                  </button>
                </div>
              )}
              {phase === "done" && (
                <div className="flex gap-2 shrink-0 mt-1">
                  <button onClick={routeJobId ? () => navigate("/history") : reset}
                    className="px-4 py-2 rounded-full border border-white/10 hover:border-white/25 text-white/50 hover:text-white text-sm transition-all cursor-pointer">
                    {routeJobId ? "← Back to history" : "← New"}
                  </button>
                  {result?.report?.available && (
                    <a href={reportDownloadUrl(jobId)} target="_blank" rel="noreferrer"
                      className="px-5 py-2 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer shadow-[0_0_16px_rgba(139,92,246,0.4)]">
                      Download ↓
                    </a>
                  )}
                </div>
              )}
            </div>

            {/* Progress bar */}
            <div className="mt-5">
              <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-700 ease-out bg-linear-to-r ${
                  phase === "done" ? "from-violet-500 to-emerald-400" : "from-violet-600 to-cyan-500"
                }`} style={{ width: `${phase === "done" ? 100 : progressPct}%` }} />
              </div>
              <div className="flex justify-between mt-1.5">
                <span className="text-white/20 text-[10px] font-mono">{doneCount} / {AGENTS.length} agents</span>
                <span className="text-white/20 text-[10px] font-mono">{phase === "done" ? 100 : Math.round(progressPct)}%</span>
              </div>
            </div>
          </div>

          {/* Agent cards */}
          <div className="flex flex-col">
            {agentStates.map((agent, idx) => (
              <AgentCard key={agent.id} agent={agent} index={idx} total={AGENTS.length} />
            ))}
          </div>

          {/* Completion banner */}
          {phase === "done" && (
            <div className="mt-4 rounded-3xl border border-violet-500/20 bg-linear-to-br from-violet-500/8 to-cyan-500/4 p-7">
              {errorMessage && (
                <p className="mb-4 text-amber-300 text-xs">⚠ {errorMessage}</p>
              )}
              <div className="flex flex-col sm:flex-row items-center gap-6">
                <div className="flex gap-6 flex-wrap justify-center sm:justify-start">
                  {[
                    { label: "Rows Processed", value: result?.summary?.rows?.toLocaleString?.() ?? "—", color: "text-violet-300" },
                    { label: "Columns Tagged",  value: result?.summary?.columns ?? "—",     color: "text-cyan-300" },
                    { label: "Charts Created",  value: result?.summary?.chart_count ?? "—",      color: "text-amber-300" },
                    { label: "Confidence",    value: result?.summary?.overall_confidence != null ? `${Math.round(result.summary.overall_confidence * 100)}%` : "—", color: "text-emerald-300" },
                  ].map(s => (
                    <div key={s.label} className="text-center">
                      <div className={`text-2xl font-black ${s.color}`}>{s.value}</div>
                      <div className="text-white/30 text-xs mt-0.5">{s.label}</div>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2 sm:ml-auto shrink-0">
                  {routeJobId ? (
                    <button onClick={() => navigate("/history")}
                      className="px-6 py-3 rounded-full border border-white/10 hover:border-white/25 text-white/50 hover:text-white font-semibold text-sm transition-all cursor-pointer">
                      Back to history
                    </button>
                  ) : null}
                  {result?.report?.available ? (
                    <a href={reportDownloadUrl(jobId)} target="_blank" rel="noreferrer"
                      className="px-6 py-3 rounded-full bg-violet-600 hover:bg-violet-500 text-white font-semibold text-sm transition-all cursor-pointer shadow-[0_0_24px_rgba(139,92,246,0.4)] hover:shadow-[0_0_32px_rgba(139,92,246,0.6)]">
                      {result.report.format === "pdf" ? "PDF Report ↓" : "Report ↓"}
                    </a>
                  ) : (
                    <span className="px-6 py-3 rounded-full border border-white/10 text-white/25 font-medium text-sm">
                      Report unavailable
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {phase === "done" && result && (
            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <div className="rounded-3xl border border-white/8 bg-white/2 p-6">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <div>
                    <h2 className="text-white font-semibold text-lg">Run configuration</h2>
                    <p className="text-white/30 text-sm">The exact settings used for this job.</p>
                  </div>
                  <span className="px-2.5 py-1 rounded-full border border-violet-500/20 bg-violet-500/8 text-violet-300 text-[10px] font-mono uppercase tracking-[0.18em]">
                    persisted
                  </span>
                </div>
                <div className="grid sm:grid-cols-2 gap-3 text-sm">
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <div className="text-white/30 text-xs uppercase tracking-widest">Profile</div>
                    <div className="text-white mt-1 font-semibold">{result.summary?.preprocessing_profile || "balanced"}</div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <div className="text-white/30 text-xs uppercase tracking-widest">Currency cap</div>
                    <div className="text-white mt-1 font-semibold">
                      {result.summary?.analysis_config?.preprocessing_config?.currency_max_abs_value != null
                        ? result.summary.analysis_config.preprocessing_config.currency_max_abs_value.toLocaleString()
                        : "—"}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <div className="text-white/30 text-xs uppercase tracking-widest">KNN neighbors</div>
                    <div className="text-white mt-1 font-semibold">
                      {result.summary?.analysis_config?.preprocessing_config?.knn_imputer_neighbors ?? "—"}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <div className="text-white/30 text-xs uppercase tracking-widest">Tolerance</div>
                    <div className="text-white mt-1 font-semibold">
                      {result.summary?.analysis_config?.preprocessing_config?.reconciliation_abs_tol ?? "—"}
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-3xl border border-white/8 bg-white/2 p-6">
                <div className="flex items-center justify-between gap-3 mb-4">
                  <div>
                    <h2 className="text-white font-semibold text-lg">Trust signals</h2>
                    <p className="text-white/30 text-sm">Quality, validation, and readiness at a glance.</p>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono uppercase tracking-[0.18em] ${
                    result.reliability?.decision_readiness === "ready"
                      ? "border border-emerald-500/20 bg-emerald-500/8 text-emerald-300"
                      : "border border-amber-500/20 bg-amber-500/8 text-amber-300"
                  }`}>
                    {result.reliability?.decision_readiness || "unknown"}
                  </span>
                </div>
                <div className="grid sm:grid-cols-3 gap-3 text-sm">
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <div className="text-white/30 text-xs uppercase tracking-widest">Quality score</div>
                    <div className="text-violet-300 mt-1 font-black text-xl">
                      {result.data_quality?.overall_quality_score != null ? `${Math.round(result.data_quality.overall_quality_score)}%` : "—"}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <div className="text-white/30 text-xs uppercase tracking-widest">Validation</div>
                    <div className="text-cyan-300 mt-1 font-black text-xl">
                      {result.validation?.overall_validation_score != null ? `${Math.round(result.validation.overall_validation_score)}/100` : "—"}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
                    <div className="text-white/30 text-xs uppercase tracking-widest">Confidence</div>
                    <div className="text-emerald-300 mt-1 font-black text-xl">
                      {result.reliability?.overall_confidence != null ? `${Math.round(result.reliability.overall_confidence * 100)}%` : "—"}
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-3xl border border-white/8 bg-white/2 p-6 lg:col-span-2">
                <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
                  <div>
                    <h2 className="text-white font-semibold text-lg">Executive summary</h2>
                    <p className="text-white/30 text-sm">Narrative and key findings produced by Agent 6.</p>
                  </div>
                  {result.report?.available && (
                    <a href={reportDownloadUrl(jobId)} target="_blank" rel="noreferrer"
                      className="px-4 py-2 rounded-full bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold transition-colors cursor-pointer shadow-[0_0_16px_rgba(139,92,246,0.35)]">
                      Open report
                    </a>
                  )}
                </div>
                <p className="text-white/75 text-sm leading-relaxed max-w-4xl">
                  {result.insight_narrative?.executive_summary || "No executive summary was returned by the report agent."}
                </p>
                {Array.isArray(result.insight_narrative?.key_findings) && result.insight_narrative.key_findings.length > 0 && (
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {result.insight_narrative.key_findings.slice(0, 4).map((finding, index) => (
                      <div key={`${index}-${finding}`} className="rounded-2xl border border-white/8 bg-black/20 p-4 text-sm text-white/70">
                        <span className="text-violet-300 font-semibold mr-2">#{index + 1}</span>
                        {finding}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-3xl border border-white/8 bg-white/2 p-6">
                <div className="mb-4">
                  <h2 className="text-white font-semibold text-lg">Charts</h2>
                  <p className="text-white/30 text-sm">Generated visual evidence for the analysis.</p>
                </div>
                <div className="space-y-2 max-h-64 overflow-auto pr-1">
                  {(result.charts || []).length > 0 ? (
                    result.charts.map((chart, index) => (
                      <a key={chart?.url || index} href={chart?.url || chart} target="_blank" rel="noreferrer"
                        className="flex items-center justify-between rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm text-white/70 hover:border-violet-500/30 hover:text-white transition-colors">
                        <span>Chart {index + 1}</span>
                        <span className="text-violet-300">Open →</span>
                      </a>
                    ))
                  ) : (
                    <p className="text-white/30 text-sm">No charts were generated for this run.</p>
                  )}
                </div>
              </div>

              <div className="rounded-3xl border border-white/8 bg-white/2 p-6">
                <div className="mb-4">
                  <h2 className="text-white font-semibold text-lg">Schema snapshot</h2>
                  <p className="text-white/30 text-sm">A quick preview of the tagged columns.</p>
                </div>
                <div className="space-y-2 max-h-64 overflow-auto pr-1">
                  {Object.entries(result.schema_blueprint || {}).slice(0, 6).map(([columnName, meta]) => (
                    <div key={columnName} className="rounded-2xl border border-white/8 bg-black/20 p-4">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-white text-sm font-medium truncate">{columnName}</div>
                        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-cyan-300">
                          {meta?.semantic_tag || "unknown"}
                        </span>
                      </div>
                      <div className="mt-1 text-white/35 text-xs">
                        {meta?.intended_type || "—"} · {meta?.analysis_allowed === false ? "analysis blocked" : "analysis allowed"}
                      </div>
                    </div>
                  ))}
                  {Object.keys(result.schema_blueprint || {}).length === 0 && (
                    <p className="text-white/30 text-sm">Schema details were not returned.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {phase === "done" && result && jobId && (
            <div className="mt-4">
              <DatasetChat jobId={jobId} />
            </div>
          )}

          {/* Error banner */}
          {phase === "error" && (
            <div className="mt-4 rounded-3xl border border-red-500/25 bg-red-500/5 p-7">
              <p className="text-red-300 text-sm font-medium">✗ {errorMessage || "Something went wrong while running the pipeline."}</p>
              <button onClick={reset}
                className="mt-4 px-5 py-2 rounded-full bg-red-600/80 hover:bg-red-500 text-white text-sm font-semibold transition-colors cursor-pointer">
                ← Start over
              </button>
            </div>
          )}
        </div>
      )}

      {/* Elapsed timer */}
      {phase === "running" && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2 rounded-full bg-black/80 border border-white/8 text-white/40 text-xs backdrop-blur-md">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
          {elapsedTotal}s elapsed
        </div>
      )}

      <style>{`
        @keyframes scanline {
          0%   { top: -2px; opacity: 0; }
          10%  { opacity: 1; }
          90%  { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }
        @keyframes indeterminate {
          0%   { width: 0%;  margin-left: 0%; }
          50%  { width: 60%; margin-left: 20%; }
          100% { width: 0%;  margin-left: 100%; }
        }
      `}</style>
    </div>
  );
}

