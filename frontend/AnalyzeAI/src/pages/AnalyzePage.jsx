import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, ArrowLeft, RotateCcw, Upload, Download, CheckCircle2, FileBarChart2 } from "lucide-react";
import AppLayout from "@/layouts/AppLayout";
import Dropzone from "@/components/Dropzone";
import RunSettings from "@/components/RunSettings";
import PipelineTimeline, { PENDING, RUNNING, DONE, ERROR } from "@/components/PipelineTimeline";
import ResultsView from "@/components/ResultsView";
import ReportDashboard from "@/components/ReportDashboard";
import DownloadReportModal from "@/components/DownloadReportModal";
import DatasetChat from "@/components/DatasetChat";
import { analyzeCsv, subscribeToJobStream, fetchJob, fetchJobResult, reportDownloadUrl } from "@/lib/api";

const AGENTS = [
  {
    id: 1,
    name: "Structural profiler",
    plain: "Reads the file and records dimensions, missing values, and duplicates.",
  },
  {
    id: 2,
    name: "Semantic tagging",
    plain: "Decides what each column means — currency, date, identifier, category.",
  },
  {
    id: 3,
    name: "Preprocessing",
    plain: "Cleans values: fixes types, fills gaps, clips outliers, normalizes.",
  },
  {
    id: 4,
    name: "Statistics & visualization",
    plain: "Computes stats, correlations, and trends; draws the charts.",
  },
  {
    id: 5,
    name: "Quality guardrail",
    plain: "Cross-checks every number against the source before anything ships.",
  },
  {
    id: 6,
    name: "Report assembly",
    plain: "Writes the narrative from verified facts and compiles your report.",
  },
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

const agentIdFromLabel = (label) => Number((/\d+/.exec(label || "") || [])[0]);

export default function AnalyzePage() {
  const navigate = useNavigate();
  const { jobId: routeJobId } = useParams();

  const [file, setFile] = useState(null);
  const [phase, setPhase] = useState("upload");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [loadedJobName, setLoadedJobName] = useState(null);
  const [runConfig, setRunConfig] = useState({ ...DEFAULT_RUN_CONFIG });
  const [agentStates, setAgentStates] = useState(
    AGENTS.map((a) => ({ ...a, status: PENDING, duration: null, summary: null }))
  );
  const [elapsedTotal, setElapsedTotal] = useState(0);
  const [jobId, setJobId] = useState(null);
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [showDownloadModal, setShowDownloadModal] = useState(false);

  const eventSourceRef = useRef(null);
  const timerRef = useRef(null);
  const agentStartRef = useRef({});
  const runStatusRef = useRef("idle");
  const liveJobIdRef = useRef(null);

  const closeStream = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  };

  useEffect(() => () => closeStream(), []);

  useEffect(() => {
    if (!routeJobId) return;
    // A just-finished live run navigates to its own /analyze/:jobId so the URL
    // reflects the report (see finish() below) — the result is already loaded
    // at that point, so skip the network refetch instead of flashing back to
    // the upload screen while it reloads data we already have.
    if (routeJobId === liveJobIdRef.current && runStatusRef.current === "done") return;

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
        setAgentStates(AGENTS.map((a) => ({ ...a, status: DONE, duration: null, summary: null })));
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

  const markAgent = (id, patch) => setAgentStates((p) => p.map((a) => (a.id === id ? { ...a, ...patch } : a)));

  const fail = (message) => {
    runStatusRef.current = "error";
    closeStream();
    setErrorMessage(message);
    setPhase("error");
    setAgentStates((p) => p.map((a) => (a.status === RUNNING ? { ...a, status: ERROR } : a)));
  };

  const finish = async (id) => {
    runStatusRef.current = "done";
    // Close our end the instant "completed" arrives, before the async result
    // fetch below — otherwise the EventSource sits open across that await and
    // can auto-reconnect (browsers treat a server-closed SSE connection as
    // dropped) and replay the whole event log, re-triggering this handler.
    closeStream();
    try {
      const data = await fetchJobResult(id);
      setResult(data);
      setPhase("done");
      // Move the URL to /analyze/:jobId now that there's a finished report to
      // show at it — matches how History/Profile link to a completed job, and
      // means refreshing or sharing the link lands back on this report instead
      // of a blank upload screen.
      if (!routeJobId) navigate(`/analyze/${id}`, { replace: true });
    } catch (err) {
      runStatusRef.current = "error";
      setErrorMessage(err.message || "Failed to load the analysis result.");
      setPhase("error");
    }
  };

  const handleStreamEvent = (id, name, data) => {
    if (name === "progress" && data.agent) {
      const agentId = agentIdFromLabel(data.agent);
      if (data.status === "running") {
        agentStartRef.current[agentId] = Date.now();
        markAgent(agentId, { status: RUNNING });
      } else if (data.status === "completed") {
        const started = agentStartRef.current[agentId];
        const duration = started ? ((Date.now() - started) / 1000).toFixed(1) : null;
        markAgent(agentId, { status: DONE, duration, summary: data.message || null });
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
      markAgent(5, { status: ERROR, summary: "Validation failed — see report for details" });
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
    if (name === "pipeline_finished") {
      // An agent can catch its own error and still return normally (e.g. a file
      // that fails to parse) — the pipeline then "finishes" gracefully with no
      // report, using the SAME event name as a real success. Without this check
      // the "completed" event below routes to finish(), which never touches
      // agentStates — so whichever agent was mid-run stays stuck on its spinner
      // forever even though the run is actually over.
      const errs = data.detail?.errors;
      if (Array.isArray(errs) && errs.length > 0 && !data.detail?.has_report) {
        fail(errs[0] || "Analysis failed.");
      }
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
    setAgentStates(AGENTS.map((a) => ({ ...a, status: PENDING, duration: null, summary: null })));

    const startTime = Date.now();
    timerRef.current = setInterval(() => setElapsedTotal(Math.floor((Date.now() - startTime) / 1000)), 1000);

    try {
      const analysisConfig = buildAnalysisConfig(runConfig);
      const { job_id, stream_url } = await analyzeCsv(file, analysisConfig);
      liveJobIdRef.current = job_id;
      setJobId(job_id);
      eventSourceRef.current = subscribeToJobStream(stream_url, {
        onEvent: (name, data) => handleStreamEvent(job_id, name, data),
        onError: () => {
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
    setAgentStates(AGENTS.map(a => ({ ...a, status: PENDING, duration: null, summary: null })));
  };

  const doneCount = agentStates.filter((a) => a.status === DONE).length;
  const progressPct = (doneCount / AGENTS.length) * 100;
  const reportHref = jobId ? reportDownloadUrl(jobId) : "#";
  const analysisReady = Boolean(jobId && agentStates.some((agent) => agent.id === 6 && agent.status === DONE));
  const openAnalysis = () => {
    if (jobId) navigate(`/analyze/${jobId}`);
  };

  /* ── UPLOAD ─────────────────────────────────────────────────────────────*/
  if (phase === "upload" && !routeJobId && !historyLoading) {
    return (
      <AppLayout size="wide" className="flex flex-col py-6!">
        {/* Compact Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="mb-6"
        >
          <div className="flex items-baseline gap-2 mb-2">
            <h1 className="text-3xl font-serif font-bold">CSV Analysis</h1>
            <span className="text-xs uppercase tracking-widest text-amber-700 dark:text-amber-600 font-mono">
              Single-page workflow
            </span>
          </div>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Six agents: structure, semantics, cleaning, statistics, validation, insights.
          </p>
        </motion.div>

        {/* Main Stack - Vertical Layout */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="flex flex-col gap-6 flex-1"
        >
          {/* Dropzone */}
          <Dropzone file={file} onFile={setFile} onClear={() => setFile(null)} />

          {/* File Preview - Compact */}
          <AnimatePresence>
            {file && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="border border-neutral-200 dark:border-neutral-800 p-3 rounded-sm"
              >
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-xs text-amber-700 dark:text-amber-600 uppercase tracking-widest font-mono mb-0.5">
                      Ready
                    </p>
                    <p className="text-sm font-medium truncate">{file.name}</p>
                  </div>
                  <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400 shrink-0 ml-2" />
                </div>
                <p className="text-xs text-neutral-600 dark:text-neutral-400 mt-1">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Settings - Horizontal */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="border border-neutral-200 dark:border-neutral-800 p-6 rounded-sm"
          >
            <RunSettings config={runConfig} onConfigChange={setRunConfig} />
          </motion.div>

          {/* Run Button */}
          <motion.button
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.98 }}
            onClick={runPipeline}
            disabled={!file}
            className="py-2.5 px-4 bg-amber-700 hover:bg-amber-800 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-sm transition-all flex items-center justify-center gap-2 text-sm shrink-0 w-full sm:w-auto"
          >
            <Upload className="w-4 h-4" />
            Analyze
          </motion.button>
        </motion.div>
      </AppLayout>
    );
  }

  /* ── RUNNING ────────────────────────────────────────────────────────────*/
  if (phase === "running") {
    return (
      <AppLayout size="content" className="flex flex-col items-center justify-center py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="w-full text-center"
        >
          <div className="text-xs uppercase tracking-widest text-amber-700 dark:text-amber-600 mb-4 font-mono">
            Analyzing {loadedJobName || file?.name}
          </div>
          <h2 className="text-4xl font-serif font-bold mb-4">
            Pipeline running.
          </h2>
          <p className="text-ink-secondary">
            Each agent validates its work before handing off. Typical runtime: 30-90 seconds.
          </p>
        </motion.div>

        {/* Progress Bar */}
        <div className="w-full mt-12">
          <div className="h-1 bg-neutral-200 dark:bg-neutral-800 rounded-full overflow-hidden mb-4">
            <motion.div
              className="h-full bg-linear-to-r from-amber-700 to-amber-600"
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <p className="text-xs text-center text-ink-secondary font-mono">
            {doneCount} of {AGENTS.length} agents complete · {elapsedTotal}s elapsed
          </p>
        </div>

        {/* Pipeline Timeline */}
        <div className="w-full mt-8">
          <PipelineTimeline agents={agentStates} elapsedTotal={elapsedTotal} />
        </div>

        {analysisReady && (
          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.98 }}
            onClick={openAnalysis}
            className="mt-8 inline-flex items-center gap-2 px-5 py-2.5 bg-accent hover:bg-accent-hover text-white font-semibold rounded-sm transition-all"
          >
            <FileBarChart2 className="w-4 h-4" />
            View Analysis
          </motion.button>
        )}
      </AppLayout>
    );
  }

  /* ── ERROR ──────────────────────────────────────────────────────────────*/
  if (phase === "error") {
    return (
      <AppLayout size="content" className="flex items-center justify-center py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/30 p-8 rounded-sm w-full"
        >
          <div className="flex gap-4">
            <AlertCircle className="w-6 h-6 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <h2 className="text-xl font-serif font-bold text-red-700 dark:text-red-300 mb-2">
                Analysis failed
              </h2>
              <p className="text-red-700 dark:text-red-400 text-sm mb-6">
                {errorMessage}
              </p>

              <motion.button
                whileHover={{ y: -1 }}
                whileTap={{ scale: 0.98 }}
                onClick={reset}
                className="px-6 py-2 bg-red-700 hover:bg-red-800 text-white font-medium rounded-sm transition-all flex items-center gap-2 text-sm"
              >
                <RotateCcw className="w-4 h-4" />
                Try Again
              </motion.button>
            </div>
          </div>
        </motion.div>
      </AppLayout>
    );
  }

  /* ── DONE ───────────────────────────────────────────────────────────────*/
  if (phase === "done") {
    return (
      <AppLayout size="wide">
        {/* Back Button */}
        <motion.button
          whileHover={{ x: -2 }}
          whileTap={{ scale: 0.95 }}
          onClick={reset}
          className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-600 hover:text-amber-800 dark:hover:text-amber-500 transition-colors mb-8"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to upload
        </motion.button>

        {/* Results */}
        {result ? (
          <>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-12"
            >
              <div className="text-xs uppercase tracking-widest text-amber-700 dark:text-amber-600 mb-4 font-mono">
                Analysis Complete
              </div>
              <h1 className="text-4xl font-serif font-bold mb-6">
                {loadedJobName || file?.name}
              </h1>

              <motion.button
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => setShowDownloadModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2.5 bg-accent hover:bg-accent-hover font-semibold rounded-sm transition-all text-white"
              >
                <Download className="w-4 h-4" />
                Download Report
              </motion.button>
            </motion.div>

            {/* Dashboard */}
            <ReportDashboard reportData={result} />

            {/* Chat */}
            {DatasetChat && <DatasetChat jobId={jobId} />}
          </>
        ) : (
          <div className="text-center py-12">
            <p className="text-ink-secondary">Loading results…</p>
          </div>
        )}

        {/* Download Modal */}
        <DownloadReportModal
          isOpen={showDownloadModal}
          onClose={() => setShowDownloadModal(false)}
          reportData={result}
          jobId={jobId}
        />
      </AppLayout>
    );
  }

  /* ── LOADING HISTORY ────────────────────────────────────────────────────*/
  if (historyLoading) {
    return (
      <AppLayout size="wide">
        <div className="flex items-center justify-center py-12">
          <p className="text-ink-secondary">Loading analysis…</p>
        </div>
      </AppLayout>
    );
  }

  return null;
}
