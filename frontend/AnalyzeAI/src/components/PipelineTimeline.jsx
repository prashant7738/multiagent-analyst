import React from "react";
import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";

const PENDING = "pending";
const RUNNING = "running";
const DONE = "done";
const ERROR = "error";

/**
 * GOAL: someone should be able to explain what is happening to a colleague
 * by reading this screen. Six named stages, one line of plain language each,
 * live status and duration — a linear list instead of decorative cards.
 */
export default function PipelineTimeline({ agents, elapsedTotal }) {
  return (
    <ol className="rounded-panel border border-line bg-surface" aria-label="Pipeline progress">
      {agents.map((agent, i) => {
        const running = agent.status === RUNNING;
        const done = agent.status === DONE;
        const error = agent.status === ERROR;
        const pending = agent.status === PENDING;

        return (
          <li key={agent.id}>
            <div className={cn("flex items-start gap-4 px-5 py-4", i > 0 && "border-t border-line")}>
              {/* Status glyph */}
              <span
                aria-hidden="true"
                className={cn(
                  "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  done && "border-success bg-success-subtle text-success",
                  error && "border-danger bg-danger-subtle text-danger",
                  running && "border-accent bg-accent-subtle text-accent-ink",
                  pending && "border-line bg-raised text-ink-faint"
                )}
              >
                {done ? <Check size={12} strokeWidth={1.75} /> : error ? <X size={12} strokeWidth={1.75} /> : i + 1}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <h3
                    className={cn(
                      "font-heading text-sm font-semibold",
                      pending ? "text-ink-faint" : "text-ink"
                    )}
                  >
                    {agent.name}
                  </h3>
                  <span className="tnum shrink-0 text-xs text-ink-faint">
                    {agent.duration != null ? `${agent.duration}s` : running ? `${elapsedTotal}s elapsed` : ""}
                  </span>
                </div>

                <p className={cn("mt-0.5 text-xs leading-relaxed", pending ? "text-ink-faint" : "text-ink-muted")}>
                  {agent.plain}
                </p>

                {/* Live output summary — the actual news from the backend */}
                {agent.summary && (
                  <p
                    className={cn(
                      "tnum mt-1.5 text-xs leading-relaxed",
                      error ? "text-danger" : "text-accent-ink"
                    )}
                  >
                    {agent.summary}
                  </p>
                )}

                {/* Indeterminate bar only while working — constant motion = linear easing */}
                {running && (
                  <div className="pipe-bar relative mt-2 h-0.5 overflow-hidden rounded-full bg-raised" />
                )}
              </div>

              <span
              className={cn(
                "shrink-0 rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
                done && "bg-success-subtle text-success",
                error && "bg-danger-subtle text-danger",
                running && "bg-accent-subtle text-accent-ink",
                pending && "bg-raised text-ink-faint"
              )}
            >
                {running ? "working" : agent.status === ERROR ? "failed" : agent.status}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export { PENDING, RUNNING, DONE, ERROR };
