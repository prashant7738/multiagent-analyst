import React from "react";
import { Download, FileDown } from "lucide-react";
import { chartUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * GOAL: deliver the answer. Inverted pyramid — the executive summary and key
 * findings ARE the product; trust signals tell you how much to believe it;
 * charts and schema are evidence; run config is archival metadata (collapsed).
 *
 * Exactly ONE persistent "Download report" action lives in the sticky header.
 */

function Stat({ label, value, tone = "" }) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs text-ink-faint">{label}</p>
      <p className={cn("tnum mt-1 font-heading text-2xl font-bold", tone || "text-ink")}>{value}</p>
    </div>
  );
}

function SectionHeading({ title, sub }) {
  return (
    <div>
      <h2 className="font-heading text-lg font-semibold text-ink">{title}</h2>
      {sub && <p className="mt-0.5 text-sm text-ink-muted">{sub}</p>}
    </div>
  );
}

export default function ResultsView({ result, jobId }) {
  const narrative = result.insight_narrative || {};
  const findings = Array.isArray(narrative.key_findings) ? narrative.key_findings : [];
  const charts = result.charts || [];
  const schemaEntries = Object.entries(result.schema_blueprint || {});
  const ready = result.reliability?.decision_readiness === "ready";

  return (
    <div className="flex flex-col gap-8">
      {/* 1 — The deliverable: executive summary + key findings */}
      <section aria-labelledby="results-summary" className="rounded-panel border border-line bg-surface p-7">
        <SectionHeading
          title="Executive summary"
          sub="Written from verified statistics by the report agent."
        />
        <p className="mt-4 max-w-[75ch] text-lg leading-relaxed text-ink">
          {narrative.executive_summary || "No executive summary was returned for this run."}
        </p>

        {findings.length > 0 && (
          <>
            <h3 className="mt-7 font-heading text-sm font-semibold uppercase tracking-[0.12em] text-ink-muted">
              Key findings
            </h3>
            <ol className="mt-3 divide-y divide-line border-y border-line">
              {findings.map((finding, i) => (
                <li key={`${i}-${finding}`} className="flex gap-4 py-3.5 text-sm leading-relaxed text-ink-secondary">
                  <span className="tnum shrink-0 font-heading font-semibold text-accent-ink">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {finding}
                </li>
              ))}
            </ol>
          </>
        )}
      </section>

      {/* 2 — Trust signals: how much to believe the above */}
      <section aria-labelledby="results-trust">
        <SectionHeading title="Trust signals" sub="How much confidence to place in this analysis." />
        <div className="mt-3 grid divide-y divide-line rounded-panel border border-line bg-surface sm:grid-cols-2 sm:divide-x lg:grid-cols-4 lg:divide-y-0">
          <Stat
            label="Confidence"
            value={
              result.reliability?.overall_confidence != null
                ? `${Math.round(result.reliability.overall_confidence * 100)}%`
                : "—"
            }
            tone="text-success"
          />
          <Stat
            label="Quality score"
            value={result.data_quality?.overall_quality_score != null ? `${Math.round(result.data_quality.overall_quality_score)}%` : "—"}
          />
          <Stat
            label="Validation"
            value={result.validation?.overall_validation_score != null ? `${Math.round(result.validation.overall_validation_score)}/100` : "—"}
          />
          <Stat
            label="Decision readiness"
            value={result.reliability?.decision_readiness ?? "unknown"}
            tone={ready ? "text-success" : "text-warning"}
          />
        </div>
      </section>

      {/* 3 — Charts: visual evidence */}
      <section aria-labelledby="results-charts">
        <SectionHeading title="Charts" sub="Generated visual evidence. Click any chart to view full size." />
        {charts.length > 0 ? (
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {charts.map((chart, i) => {
              const url = chartUrl(chart?.url || chart);
              const name = chart?.name || `Chart ${i + 1}`;
              return (
                <figure
                  key={chart?.url || i}
                  className="overflow-hidden rounded-panel border border-line bg-surface"
                >
                  <a href={url} target="_blank" rel="noreferrer" className="block">
                    <img
                      src={url}
                      alt={name}
                      decoding="async"
                      className="max-h-[420px] w-full object-contain p-4"
                      data-retried={jobId ? "" : undefined}
                      onError={(e) => {
                        const el = e.currentTarget;
                        // Old jobs store flat URLs but files live in per-job
                        // folders — retry the job-scoped path once.
                        if (jobId && !el.dataset.retried) {
                          el.dataset.retried = "1";
                          const scoped = chartUrl(`/plots/${jobId}/${name}`);
                          el.src = scoped;
                          if (el.parentElement?.tagName === "A") el.parentElement.href = scoped;
                          return;
                        }
                        el.style.display = "none";
                        const href = el.parentElement?.href || url;
                        el.parentElement?.insertAdjacentHTML(
                          "afterend",
                          `<div class="px-4 py-8 text-center"><a href="${href}" target="_blank" rel="noreferrer" class="text-sm text-accent-ink underline">Open ${name} in a new tab</a></div>`
                        );
                      }}
                    />
                  </a>
                  <figcaption className="border-t border-line px-4 py-2.5 text-xs text-ink-muted">
                    {name}
                  </figcaption>
                </figure>
              );
            })}
          </div>
        ) : (
          <p className="mt-3 rounded-panel border border-line bg-surface px-5 py-6 text-sm text-ink-faint">
            No charts were generated for this run.
          </p>
        )}
      </section>

      {/* 4 — Schema snapshot */}
      <section aria-labelledby="results-schema">
        <SectionHeading title="Schema snapshot" sub="How each column was interpreted." />
        {schemaEntries.length > 0 ? (
          <div className="mt-3 overflow-hidden rounded-panel border border-line bg-surface">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th scope="col" className="px-5 py-3 font-medium">Column</th>
                  <th scope="col" className="px-5 py-3 font-medium">Semantic tag</th>
                  <th scope="col" className="px-5 py-3 font-medium">Type</th>
                  <th scope="col" className="px-5 py-3 font-medium">Analysis</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {schemaEntries.slice(0, 12).map(([column, meta]) => (
                  <tr key={column}>
                    <td className="px-5 py-3 font-medium text-ink">{column}</td>
                    <td className="px-5 py-3 text-ink-secondary">{meta?.semantic_tag || "unknown"}</td>
                    <td className="tnum px-5 py-3 text-ink-muted">{meta?.intended_type || "—"}</td>
                    <td className="px-5 py-3">
                      {meta?.analysis_allowed === false ? (
                        <span className="rounded-full bg-warning-subtle px-2 py-0.5 text-xs text-warning">blocked</span>
                      ) : (
                        <span className="rounded-full bg-raised px-2 py-0.5 text-xs text-ink-muted">allowed</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {schemaEntries.length > 12 && (
              <p className="border-t border-line px-5 py-2.5 text-xs text-ink-faint">
                +{schemaEntries.length - 12} more columns in the full report.
              </p>
            )}
          </div>
        ) : (
          <p className="mt-3 rounded-panel border border-line bg-surface px-5 py-6 text-sm text-ink-faint">
            Schema details were not returned.
          </p>
        )}
      </section>

      {/* 5 — Run configuration: archival metadata, collapsed by default */}
      <details className="rounded-panel border border-line bg-surface">
        <summary className="cursor-pointer list-none px-5 py-4 [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-2 text-sm font-medium text-ink-muted">
            <FileDown size={15} aria-hidden="true" />
            Run configuration used for this job
          </span>
        </summary>
        <dl className="grid grid-cols-2 gap-4 border-t border-line px-5 py-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-ink-faint">Profile</dt>
            <dd className="mt-0.5 capitalize text-ink">{result.summary?.preprocessing_profile || "balanced"}</dd>
          </div>
          <div>
            <dt className="text-xs text-ink-faint">Currency cap</dt>
            <dd className="tnum mt-0.5 text-ink">
              {result.summary?.analysis_config?.preprocessing_config?.currency_max_abs_value?.toLocaleString() ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-ink-faint">Imputer neighbors</dt>
            <dd className="tnum mt-0.5 text-ink">
              {result.summary?.analysis_config?.preprocessing_config?.knn_imputer_neighbors ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-ink-faint">Reconciliation tol.</dt>
            <dd className="tnum mt-0.5 text-ink">
              {result.summary?.analysis_config?.preprocessing_config?.reconciliation_abs_tol ?? "—"}
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

export function DownloadReportButton({ href, format, size = "md" }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={cn(
        "pressable inline-flex h-10 items-center gap-2 rounded-(--radius-control) bg-accent px-4 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent-hover",
        size === "sm" && "h-9 px-3 text-xs"
      )}
    >
      <Download size={15} strokeWidth={1.75} aria-hidden="true" />
      Download report{format ? ` (${format.toUpperCase()})` : ""}
    </a>
  );
}
