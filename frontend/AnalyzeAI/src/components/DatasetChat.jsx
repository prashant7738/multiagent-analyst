import React, { useState, useRef, useEffect, useCallback } from "react";
import { askDatasetQuestion, fetchChatHistory, chartUrl } from "@/lib/api";

const SUGGESTED_QUESTIONS = [
  "What are the strongest correlations in this dataset?",
  "Which category performs best?",
  "Are there any anomalies I should worry about?",
  "How reliable is this analysis?",
];

/**
 * Conversational Q&A panel for a completed analysis job. Answers are grounded
 * in the job's already-computed facts (see backend/api/services/chat_service.py);
 * the assistant may occasionally return a freshly generated chart image.
 */
export default function DatasetChat({ jobId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    (async () => {
      try {
        const history = await fetchChatHistory(jobId);
        if (!cancelled) setMessages(Array.isArray(history) ? history : []);
      } catch {
        // no history yet, or backend unreachable — start with an empty transcript
      } finally {
        if (!cancelled) setHistoryLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

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
        setMessages((prev) => [...prev, { role: "assistant", content: res.answer, chart: res.chart || null }]);
      } catch (err) {
        setError(err.message || "Failed to reach the chat service.");
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: err.message || "I couldn't get a response from the chat service.", chart: null },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [input, loading, jobId]
  );

  const onKeyDown = (evt) => {
    if (evt.key === "Enter" && !evt.shiftKey) {
      evt.preventDefault();
      send();
    }
  };

  return (
    <div className="rounded-3xl border border-white/8 bg-white/2 p-6">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h2 className="text-white font-semibold text-lg">Ask about this dataset</h2>
          <p className="text-white/30 text-sm">Grounded answers from the computed stats — ask a follow-up any time.</p>
        </div>
        <span className="px-2.5 py-1 rounded-full border border-cyan-500/20 bg-cyan-500/8 text-cyan-300 text-[10px] font-mono uppercase tracking-[0.18em]">
          live
        </span>
      </div>

      <div ref={scrollRef} className="rounded-2xl border border-white/8 bg-black/20 p-4 max-h-96 overflow-auto space-y-3">
        {historyLoaded && messages.length === 0 && (
          <p className="text-white/30 text-sm">
            No questions yet — try one of the suggestions below, or type your own.
          </p>
        )}
        {messages.map((message, index) => (
          <div key={index} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                message.role === "user"
                  ? "bg-violet-600/90 text-white"
                  : "bg-white/5 border border-white/8 text-white/80"
              }`}
            >
              {message.content}
              {message.chart?.url && (
                <a href={chartUrl(message.chart.url)} target="_blank" rel="noreferrer" className="block mt-3">
                  <img
                    src={chartUrl(message.chart.url)}
                    alt={message.chart.name || "Generated chart"}
                    className="rounded-xl border border-white/10 max-w-full"
                  />
                </a>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl px-4 py-3 text-sm bg-white/5 border border-white/8 text-white/40">
              Thinking…
            </div>
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-red-300 text-xs">{error}</p>}

      {messages.length === 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTED_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => send(q)}
              className="px-3 py-1.5 rounded-full border border-white/8 bg-white/2 text-white/50 hover:text-white hover:border-violet-500/30 text-xs transition-all cursor-pointer">
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(evt) => setInput(evt.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="Ask a question about this dataset…"
          className="flex-1 bg-black/40 border border-white/10 rounded-xl px-3 py-3 text-white text-sm outline-none focus:border-violet-500/60 transition-all resize-none"
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim()}
          className="px-5 py-3 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors cursor-pointer shrink-0">
          Send
        </button>
      </div>
    </div>
  );
}
