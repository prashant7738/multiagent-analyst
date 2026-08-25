import React, { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Loader2, MessageCircleQuestion, Send, X } from "lucide-react";
import { askDatasetQuestion, fetchChatHistory, fetchJob, chartUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

const SUGGESTED_QUESTIONS = [
  "What are the strongest correlations in this dataset?",
  "Which category performs best?",
  "Are there any anomalies I should worry about?",
  "How reliable is this analysis?",
];

const PHASE_LABELS = {
  preparing: "Preparing dataset for indexing…",
  embedding: "Embedding rows",
  saving: "Saving vector index…",
};

/**
 * GOAL: follow-up questions without losing your place in the results.
 * Collapsed by default as a quiet floating action; opens as a right-docked
 * panel (full-screen sheet on mobile) so results stay primary. Escape closes;
 * focus moves into the panel on open and back to the trigger on close.
 *
 * Answers are grounded in the job's computed facts (backend chat_service) and
 * may include a freshly generated chart.
 */
export default function DatasetChat({ jobId }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [error, setError] = useState(null);
  // RAG embedding-index state polled from GET /api/jobs/{id}
  const [rag, setRag] = useState(null);

  const scrollRef = useRef(null);
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  const inputRef = useRef(null);

  // One-shot snapshot on mount so the FAB dot can show indexing state
  // before the panel is ever opened.
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    fetchJob(jobId)
      .then((job) => {
        if (cancelled || !job) return;
        setRag({
          status: job.rag_status,
          error: job.rag_error,
          progress: job.rag_progress || {},
          sampleInfo: job.rag_sample_info || {},
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  // While the panel is open, follow the RAG build live (2.5s cadence while
  // building; stops once ready/failed). `ragPollNonce` forces an immediate
  // refresh right after a chat reply reports index activity.
  const [ragPollNonce, setRagPollNonce] = useState(0);
  useEffect(() => {
    if (!jobId || !open) return;
    let cancelled = false;
    let timer = null;

    const tick = async () => {
      try {
        const job = await fetchJob(jobId);
        if (cancelled) return;
        setRag({
          status: job.rag_status,
          error: job.rag_error,
          progress: job.rag_progress || {},
          sampleInfo: job.rag_sample_info || {},
        });
        if (job.rag_status === "building") timer = setTimeout(tick, 2500);
      } catch {
        if (!cancelled) timer = setTimeout(tick, 4000);
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, open, ragPollNonce]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    (async () => {
      try {
        const history = await fetchChatHistory(jobId);
        if (!cancelled) setMessages(Array.isArray(history) ? history : []);
      } catch {
        /* no transcript yet — start empty */
      } finally {
        if (!cancelled) setHistoryLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, loading]);

  // Focus management on open/close
  useEffect(() => {
    if (open) {
      // Enter: focus the input after the drawer transition starts
      const t = setTimeout(() => inputRef.current?.focus(), 120);
      return () => clearTimeout(t);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const closePanel = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  const send = useCallback(
    async (question) => {
      const text = (question ?? input).trim();
      if (!text || loading || !jobId) return;

      setInput("");
      setError(null);
      setMessages((prev) => [...prev, { role: "user", content: text, chart: null }]);
      setLoading(true);

      try {
        const res = await askDatasetQuestion(jobId, text);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: res.answer, chart: res.chart || null, source: res.source },
        ]);
        // A reply with index_status means the RAG build just started or moved —
        // refresh the indicator immediately instead of waiting for the next tick.
        if (res.index_status) setRagPollNonce((n) => n + 1);
      } catch (err) {
        setError(err.message || "Failed to reach the chat service.");
      } finally {
        setLoading(false);
      }
    },
    [input, loading, jobId]
  );

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  // ── RAG indexing indicator state (derived) ──────────────────────────────
  const ragBuilding = rag?.status === "building";
  const ragReady = rag?.status === "ready";
  const ragFailed = rag?.status === "failed";
  const showRagStrip = open && (ragBuilding || ragReady || ragFailed);

  let ragLabel = "Indexing dataset…";
  if (ragBuilding) {
    const phase = rag?.progress?.phase;
    if (phase === "embedding") {
      const embedded = Number(rag?.progress?.embedded ?? 0);
      const total = Number(rag?.progress?.total ?? 0);
      ragLabel =
        total > 0
          ? `Embedding rows… ${embedded.toLocaleString("en-US")} / ${total.toLocaleString("en-US")}`
          : "Embedding rows…";
    } else {
      ragLabel = PHASE_LABELS[phase] || "Indexing dataset…";
    }
  }
  const ragEmbedded = Number(rag?.progress?.embedded ?? 0);
  const ragTotal = Number(rag?.progress?.total ?? 0);
  const ragPct = ragTotal > 0 ? Math.min(100, Math.round((ragEmbedded / ragTotal) * 100)) : null;
  const ragIndexedRows = Number(rag?.sampleInfo?.sampled_rows ?? 0);

  // Only show the button if RAG is ready, building, or failed (not in null/unknown state)
  const shouldShowButton = rag && (ragBuilding || ragReady || ragFailed);

  return (
    <>
      {/* Floating trigger — appears only when dataset is indexed or indexing */}
      {shouldShowButton && (
        <button
          ref={triggerRef}
          onClick={() => setOpen(true)}
          disabled={ragFailed}
          className={cn(
            "pressable fixed bottom-6 right-6 z-50 inline-flex h-12 items-center gap-2 rounded-full",
            "shadow-lg transition-colors",
            ragFailed
              ? "bg-danger text-white hover:bg-danger/90 cursor-not-allowed opacity-60"
              : "bg-accent px-5 text-sm font-medium text-white hover:bg-accent-hover"
          )}
          aria-haspopup="dialog"
          aria-expanded={open}
          title={ragFailed ? "Dataset indexing failed" : "Ask questions about this dataset"}
        >
          <span className="relative inline-flex">
            <MessageCircleQuestion size={17} strokeWidth={1.75} aria-hidden="true" />
            {ragBuilding && (
              <span
                className="absolute -right-1.5 -top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-accent animate-pulse"
                aria-hidden="true"
              />
            )}
          </span>
          Ask about this dataset
        </button>
      )}

      <AnimatePresence>
        {open && (
          <>
            {/* Close Button - Simple Text */}
            <motion.button
              key="close-btn"
              onClick={closePanel}
              style={{
                position: 'fixed',
                top: '70px',
                right: '20px',
                zIndex: 99999,
                width: '50px',
                height: '50px',
                borderRadius: '50%',
                backgroundColor: '#f59e0b',
                border: 'none',
                color: 'white',
                fontSize: '28px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(0,0,0,0.3)'
              }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              title="Close (Esc)"
              type="button"
            >
              ✕
            </motion.button>

            {/* Scrim (mobile only — the dock doesn't block the page on desktop) */}
            <motion.div
              key="scrim"
              className="fixed inset-0 z-40 bg-black/50 md:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              onClick={closePanel}
            />

            <motion.aside
              key="panel"
              ref={panelRef}
              role="dialog"
              aria-label="Ask about this dataset"
              className="fixed top-16 right-0 bottom-0 z-50 flex w-full flex-col border-l border-line bg-canvas sm:max-w-md"
              initial={{ transform: "translateX(100%)" }}
              animate={{ transform: "translateX(0%)" }}
              exit={{ transform: "translateX(100%)" }}
              transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
            >
              <header className="flex items-center justify-between gap-4 border-b border-line bg-raised px-6 py-4 flex-shrink-0">
                <div>
                  <h2 className="font-heading text-base font-semibold text-ink">Ask about this dataset</h2>
                  <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">
                    {ragReady && "Grounded in this run's verified stats"}
                    {ragBuilding && "Building index—questions available when ready"}
                    {ragFailed && "Index build failed—questions unavailable"}
                  </p>
                </div>
                <button
                  onClick={closePanel}
                  type="button"
                  className="ml-auto flex-shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-lg bg-surface hover:bg-line text-ink-secondary hover:text-ink transition-colors"
                  title="Close (Esc)"
                  aria-label="Close chat"
                >
                  <X size={22} strokeWidth={2} />
                </button>
              </header>

              <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
                {ragFailed && (
                  <div className="rounded-lg border border-danger/30 bg-danger/10 p-4">
                    <p className="text-xs text-danger font-medium">Dataset indexing failed</p>
                    <p className="text-xs text-danger/80 mt-1">{rag?.error || "Unable to build search index"}</p>
                  </div>
                )}
                {ragBuilding && (
                  <div className="rounded-lg border border-accent/30 bg-accent/10 p-4">
                    <p className="text-xs text-accent font-medium">Dataset is being indexed</p>
                    <p className="text-xs text-accent/80 mt-1">You can ask questions once the index is ready</p>
                  </div>
                )}
                {historyLoaded && messages.length === 0 && ragReady && (
                  <div className="flex flex-col gap-2">
                    <p className="text-sm text-ink-faint">Try one of these to start:</p>
                    {SUGGESTED_QUESTIONS.map((q) => (
                      <button
                        key={q}
                        onClick={() => send(q)}
                        className="rounded-(--radius-control) border border-line bg-surface px-3 py-2 text-left text-xs text-ink-secondary transition-colors hover:border-accent hover:text-ink"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}

                {messages.map((message, index) => (
                  <div key={index} className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}>
                    <div
                      className={cn(
                        "max-w-[85%] whitespace-pre-wrap rounded-panel px-4 py-3 text-sm leading-relaxed",
                        message.role === "user"
                          ? "bg-accent text-white"
                          : "border border-line bg-surface text-ink-secondary"
                      )}
                    >
                      {message.content}
                      {message.role === "assistant" && message.source === "fallback" && (
                        <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-warning">
                          <AlertTriangle size={12} className="shrink-0" />
                          Fallback answer — AI model unavailable
                        </p>
                      )}
                      {message.chart?.url && (
                        <a href={chartUrl(message.chart.url)} target="_blank" rel="noreferrer" className="mt-3 block">
                          <img
                            src={chartUrl(message.chart.url)}
                            alt={message.chart.name || "Generated chart"}
                            loading="lazy"
                            className="w-full rounded-(--radius-control) border border-line"
                          />
                        </a>
                      )}
                    </div>
                  </div>
                ))}

                {loading && (
                  <div className="flex justify-start">
                    <div className="rounded-panel border border-line bg-surface px-4 py-3 text-sm text-ink-faint">
                      Working out an answer…
                    </div>
                  </div>
                )}
              </div>

              {showRagStrip && (
                <div className="border-t border-line px-5 py-2.5 text-xs" role="status">
                  {ragBuilding && (
                    <div>
                      <div className="flex items-center gap-2">
                        <Loader2 size={13} className="shrink-0 animate-spin text-accent" />
                        <span className="text-ink-secondary">{ragLabel}</span>
                        {ragPct != null && <span className="ml-auto tabular-nums text-ink-faint">{ragPct}%</span>}
                      </div>
                      <div
                        className="mt-1.5 h-1 overflow-hidden rounded-full bg-raised"
                        role="progressbar"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={ragPct ?? undefined}
                        aria-label="Embedding progress"
                      >
                        <div
                          className="h-full rounded-full bg-accent transition-[width] duration-500"
                          style={{ width: `${ragPct ?? 5}%` }}
                        />
                      </div>
                    </div>
                  )}
                  {ragReady && (
                    <p className="flex items-center gap-2 text-success">
                      <CheckCircle2 size={13} className="shrink-0" />
                      Row-level index ready
                      {ragIndexedRows > 0 && ` · ${ragIndexedRows.toLocaleString("en-US")} rows indexed`}
                    </p>
                  )}
                  {ragFailed && (
                    <p className="flex items-start gap-2 text-danger">
                      <AlertTriangle size={13} className="mt-px shrink-0" />
                      <span>Indexing failed — {(rag?.error || "unknown error").slice(0, 160)}</span>
                    </p>
                  )}
                </div>
              )}

              {error && (
                <p role="alert" className="border-t border-line px-5 py-2 text-xs text-danger">
                  {error}
                </p>
              )}

              <div className="flex items-end gap-2 border-t border-line p-4">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  disabled={!ragReady || loading}
                  rows={1}
                  placeholder={
                    ragFailed
                      ? "Indexing failed—questions unavailable"
                      : ragBuilding
                      ? "Indexing dataset…questions available soon"
                      : "Ask a question about this dataset…"
                  }
                  aria-label="Your question"
                  className="max-h-32 min-h-[42px] flex-1 resize-none rounded-(--radius-control) border border-line bg-raised px-3 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <button
                  onClick={() => send()}
                  disabled={loading || !input.trim() || !ragReady}
                  aria-label="Send question"
                  className="pressable flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-(--radius-control) bg-accent text-white transition-colors hover:bg-accent-hover disabled:bg-raised disabled:text-ink-faint disabled:cursor-not-allowed"
                >
                  <Send size={16} strokeWidth={1.75} />
                </button>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
