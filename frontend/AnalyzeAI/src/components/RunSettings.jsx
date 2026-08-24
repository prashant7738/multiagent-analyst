import React from "react";
import { Field, inputClass } from "@/components/ui/field";
import { cn } from "@/lib/utils";

const PROFILES = [
  {
    value: "strict",
    label: "Strict",
    help: "Aggressive cleaning for messy exports: drops unusable rows, clips outliers harder.",
  },
  {
    value: "balanced",
    label: "Balanced",
    help: "The default. Safe imputation and standard outlier handling for most business data.",
  },
  {
    value: "lenient",
    label: "Lenient",
    help: "Keeps more of your data when the source is noisy — fewer rows removed, softer clipping.",
  },
];

/**
 * GOAL: the user should understand what they're configuring *before* they
 * run — this is where analysis quality is decided. Every control carries
 * inline help that says what it does to the analysis, not just its name.
 */
export default function RunSettings({ config, onChange }) {
  const set = (key) => (e) => onChange((prev) => ({ ...prev, [key]: e.target.value }));
  const activeProfile = PROFILES.find((p) => p.value === config.preprocessingProfile);

  return (
    <section aria-labelledby="run-settings-heading" className="rounded-panel border border-line bg-surface p-6">
      <h2 id="run-settings-heading" className="font-heading text-base font-semibold text-ink">
        Run settings
      </h2>
      <p className="mt-1 text-xs leading-relaxed text-ink-faint">
        Saved with this job and applied during preprocessing.
      </p>

      <div className="mt-5 flex flex-col gap-5">
        {/* Profile selector: radio group so every option's consequence is readable */}
        <fieldset>
          <legend className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-muted">
            Preprocessing profile
          </legend>
          <div className="mt-2 flex flex-col gap-2">
            {PROFILES.map((profile) => {
              const active = config.preprocessingProfile === profile.value;
              return (
                <label
                  key={profile.value}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-(--radius-control) border p-3 transition-colors duration-150",
                    active ? "border-accent bg-accent-subtle" : "border-line hover:border-line-strong"
                  )}
                >
                  <input
                    type="radio"
                    name="preprocessing-profile"
                    value={profile.value}
                    checked={active}
                    onChange={() => onChange((prev) => ({ ...prev, preprocessingProfile: profile.value }))}
                    className="mt-0.5 accent-[var(--accent)]"
                  />
                  <span>
                    <span className={`block text-sm font-medium ${active ? "text-ink" : "text-ink-secondary"}`}>
                      {profile.label}
                      {profile.value === "balanced" && (
                        <span className="ml-2 rounded-full bg-raised px-1.5 py-0.5 text-xs font-medium text-ink-faint">
                          default
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">{profile.help}</span>
                  </span>
                </label>
              );
            })}
          </div>
          <p className="sr-only">Selected: {activeProfile?.label}</p>
        </fieldset>

        <Field
          label="Currency cap"
          htmlFor="rs-currency"
          help="Values above this absolute amount are treated as data-entry errors and excluded, not analyzed as real revenue."
        >
          <input
            id="rs-currency"
            type="number"
            min="0"
            step="1000000"
            value={config.currencyMaxAbsValue}
            onChange={set("currencyMaxAbsValue")}
            className={inputClass()}
          />
        </Field>

        <Field
          label="Imputer neighbors"
          htmlFor="rs-knn"
          help="How many similar rows the KNN imputer consults when filling a missing numeric value. Higher = smoother, lower = more local."
        >
          <input
            id="rs-knn"
            type="number"
            min="1"
            step="1"
            value={config.knnImputerNeighbors}
            onChange={set("knnImputerNeighbors")}
            className={inputClass()}
          />
        </Field>

        <Field
          label="Reconciliation tolerance"
          htmlFor="rs-tol"
          help="Allowed gap between derived metrics (e.g. Profit vs Revenue − Cost) before the guardrail flags them as diverged."
        >
          <input
            id="rs-tol"
            type="number"
            min="0"
            step="0.1"
            value={config.reconciliationAbsTol}
            onChange={set("reconciliationAbsTol")}
            className={inputClass()}
          />
        </Field>
      </div>
    </section>
  );
}
