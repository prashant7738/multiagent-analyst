import React, { useCallback, useId, useRef, useState } from "react";
import { FileUp, FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * A real dropzone, not a clickable div: keyboard operable (Enter/Space opens
 * the file picker), exposed to screen readers (role=button + aria-label +
 * live status), visible focus ring from the global :focus-visible rule.
 *
 * State changes are communicated by border/background color AND an icon/text
 * change — never color alone.
 */
export default function Dropzone({ file, onFile, onClear }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const inputId = useId();
  const statusId = useId();

  const accept = useCallback(
    (f) => {
      if (f && f.name.toLowerCase().endsWith(".csv")) onFile(f);
    },
    [onFile]
  );

  const onKeyDown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputRef.current?.click();
    }
  };

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label={file ? `Selected file ${file.name}. Press Enter to choose a different file.` : "Upload a CSV file: drop it here or press Enter to browse."}
        aria-describedby={statusId}
        onClick={() => inputRef.current?.click()}
        onKeyDown={onKeyDown}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files[0]);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        className={cn(
          "flex w-full cursor-pointer flex-col items-center gap-4 rounded-panel border-2 border-dashed p-10 text-center",
          "transition-colors duration-150 outline-none",
          dragging
            ? "border-accent bg-accent-subtle"
            : file
              ? "border-success bg-success-subtle"
              : "border-line-strong bg-surface hover:border-accent hover:bg-accent-subtle"
        )}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept=".csv"
          className="sr-only"
          tabIndex={-1}
          onChange={(e) => accept(e.target.files[0])}
        />

        {file ? (
          <>
            <FileText size={32} strokeWidth={1.75} className="text-success" aria-hidden="true" />
            <div>
              <p className="font-medium text-ink">{file.name}</p>
              <p id={statusId} aria-live="polite" className="tnum mt-1 text-sm text-ink-muted">
                {(file.size / 1024).toFixed(1)} KB · ready to analyze
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onClear();
              }}
              className="inline-flex items-center gap-1 text-xs text-ink-muted transition-colors hover:text-danger"
            >
              <X size={12} aria-hidden="true" /> Remove
            </button>
          </>
        ) : (
          <>
            <FileUp size={32} strokeWidth={1.75} className="text-ink-faint" aria-hidden="true" />
            <div>
              <p className="font-medium text-ink">Drop your CSV here</p>
              <p className="mt-1 text-sm text-ink-muted">or press Enter to browse</p>
            </div>
            <p id={statusId} aria-live="polite" className="text-xs text-ink-faint">
              .csv files · up to 100 MB
            </p>
          </>
        )}
      </div>
    </div>
  );
}
