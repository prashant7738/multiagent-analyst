import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, RotateCcw } from "lucide-react";
import AppLayout from "@/layouts/AppLayout";
import Button from "@/components/ui/button";
import Dropzone from "@/components/Dropzone";
import RunSettings from "@/components/RunSettings";
import PipelineTimeline, { PENDING, RUNNING, DONE, ERROR } from "@/components/PipelineTimeline";
import ResultsView, { DownloadReportButton } from "@/components/ResultsView";
import DatasetChat from "@/components/DatasetChat";
import { analyzeCsv, subscribeToJobStream, fetchJob, fetchJobResult, reportDownloadUrl } from "@/lib/api";

/**
 * GOAL: one coherent flow — configure → upload → watch → read results.
 * The upload screen explains what each setting does before running; the run
 * screen narrates progress in plain language; the done screen leads with the
 * deliverable (summary/findings), not backend ordering.
 */

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

// "Agent N" (as emitted by the SSE stream) -> AGENTS[].id
const agentIdFromLabel = (label) => Number((/\d+/.exec(label || "") || [])[0]);

export default function AnalyzePage() {
  const navigate = useNavigate();
  const { jobId: routeJobId } = useParams();

  const [file, setFile] = useState(null);
  const [phase, setPhase] = useState("upload"); // upload | running | done | error
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

  // ── SSE / job lifecycle logic — contract-sensitive, do not restructure ────
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
    setAgentStates(AGENTS.map(a => ({ ...a, status: PENDING, duration: null, summary: null })));
  };
  // ── End SSE / job lifecycle logic ─────────────────────────────────────────

  const doneCount = agentStates.filter((a) => a.status === DONE).length;
  const progressPct = (doneCount / AGENTS.length) * 100;
  const reportHref = jobId ? reportDownloadUrl(jobId) : "#";

  /* ── UPLOAD ─────────────────────────────────────────────────────────────*/
  if (phase === "upload" && !routeJobId && !historyLoading) {
    return (
      <AppLayout size="wide">
        <div className="mx-auto max-w-3xl">
          <h1 className="font-heading text-3xl font-bold tracking-tight text-ink">New analysis</h1>
          <p className="mt-2 max-w-[60ch] text-base text-ink-muted">
            Choose a CSV, review how it will be cleaned, then run six agents over it end-to-end.
          </p>
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_380px]">
          {/* Primary column: file in, pipeline out */}
          <div className="flex flex-col gap-6">
            <Dropzone file={file} onFile={setFile} onClear={() => setFile(null)} />

            <div className="flex flex-wrap items-center gap-4">
              <Button size="lg" onClick={runPipeline} disabled={!file}>
                {file ? "Run analysis" : "Select a CSV first"}
              </Button>
              <p className="text-xs leading-relaxed text-ink-faint">
                Typical runs take under a minute.
                <br />
                You&apos;ll watch each stage complete live.
              </p>
            </div>

            <div className="rounded-panel border border-line bg-surface p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-muted">
                What will happen
              </p>
              <ol className="mt-3 space-y-2">
                {AGENTS.map((a, i) => (
                  <li key={a.id} className="flex gap-3 text-sm">
                    <span className="tnum shrink-0 font-heading text-xs font-semibold text-accent-ink">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="text-ink-secondary">{a.plain}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          {/* Secondary column: configuration with consequences explained */}
          <RunSettings config={runConfig} onChange={setRunConfig} />
        </div>
      </AppLayout>
    );
  }

  /* ── LOADING A SAVED JOB ───────────────────────────────────────────────*/
  if (routeJobId && historyLoading) {
    return (
      <AppLayout size="default">
        <p className="py-24 text-center text-sm text-ink-faint" role="status">
          Restoring saved analysis…
        </p>
      </AppLayout>
    );
  }

  /* ── RUNNING / DONE / ERROR ────────────────────────────────────────────*/
  return (
    <AppLayout size="default">
      {/* Header: status, subject, and the ONE persistent download action */}
      <div className="sticky top-16 z-30 -mx-6 mb-8 border-b border-line bg-canvas/90 px-6 py-4 backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className={`h-2 w-2 rounded-full ${
                  phase === "done" ? "bg-success" : phase === "error" ? "bg-danger" : "bg-accent animate-pulse"
                }`}
              />
              <h1 className="truncate font-heading text-xl font-bold tracking-tight text-ink">
                {phase === "done"
                  ? "Analysis complete"
                  : phase === "error"
                    ? "Analysis failed"
                    : routeJobId
                      ? "Saved analysis"
                      : "Analysis running"}
              </h1>
              {phase === "running" && (
                <span className="tnum rounded-full bg-raised px-2 py-0.5 text-xs text-ink-muted">
                  {elapsedTotal}s
                </span>
              )}
            </div>
            <p className="tnum mt-0.5 truncate text-sm text-ink-muted">
              {routeJobId
                ? loadedJobName || "Restored from history"
                : file
                  ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB`
                  : ""}
              {" · "}
              {doneCount}/{AGENTS.length} stages
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={routeJobId ? () => navigate("/history") : reset}
            >
              <ArrowLeft size={14} aria-hidden="true" />
              {routeJobId ? "History" : "New run"}
            </Button>
            {phase === "done" && result?.report?.available && (
              <DownloadReportButton href={reportHref} format={result.report.format} size="sm" />
            )}
          </div>
        </div>

        {phase !== "done" && (
          <div
            className="mt-3 h-1 overflow-hidden rounded-full bg-raised"
            role="progressbar"
            aria-valuenow={Math.round(progressPct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Pipeline progress: ${doneCount} of ${AGENTS.length} stages`}
          >
            {phase === "error" ? (
              <div className="h-full w-full bg-danger" style={{ width: "100%" }} />
            ) : (
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-300 ease-out-quart"
                style={{ width: `${progressPct}%` }}
              />
            )}
          </div>
        )}
      </div>

      {/* Pipeline timeline — visible while running; collapsed after success */}
      {(phase === "running" || phase === "error" || (phase === "done" && errorMessage)) && (
        <section aria-label="Pipeline stages" className="mb-8">
          <PipelineTimeline agents={agentStates} elapsedTotal={elapsedTotal} />
        </section>
      )}

      {/* Error state */}
      {phase === "error" && (
        <div className="rounded-panel border border-danger bg-danger-subtle p-6" role="alert">
          <p className="flex items-start gap-2.5 text-sm text-danger">
            <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
            {errorMessage || "Something went wrong while running the pipeline."}
          </p>
          {!routeJobId && (
            <Button variant="secondary" onClick={reset} className="mt-4">
              <RotateCcw size={14} aria-hidden="true" /> Start over
            </Button>
          )}
        </div>
      )}

      {/* Results — inverted pyramid lives in ResultsView */}
      {phase === "done" && result && (
        <>
          {errorMessage && (
            <p role="status" className="mb-6 rounded-panel border border-warning bg-warning-subtle px-4 py-3 text-sm text-warning">
              {errorMessage}
            </p>
          )}
          <ResultsView result={result} jobId={jobId} />
        </>
      )}

      {/* Chat: docked panel via floating action, never competing with results */}
      {phase === "done" && result && jobId && <DatasetChat jobId={jobId} />}
    </AppLayout>
  );
}
