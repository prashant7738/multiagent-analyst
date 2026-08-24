import React from "react";
import { cn } from "@/lib/utils";

/**
 * Label-above-input, helper text under the label, error text below the input.
 * No placeholder-as-label. Used by auth forms and run settings.
 */
export function Field({ label, htmlFor, help, error, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-muted">
        {label}
      </label>
      {help && <p className="text-xs leading-relaxed text-ink-faint">{help}</p>}
      {children}
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export const inputClass = ({ invalid } = {}) =>
  cn(
    "w-full rounded-(--radius-control) border bg-raised px-3 py-2.5 text-sm text-ink",
    "placeholder:text-ink-faint outline-none transition-colors duration-150",
    invalid
      ? "border-danger focus:border-danger"
      : "border-line hover:border-line-strong focus:border-accent"
  );
