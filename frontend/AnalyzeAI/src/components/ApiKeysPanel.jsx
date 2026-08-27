import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Eye, EyeOff, CheckCircle2, XCircle, AlertTriangle, Loader2 } from "lucide-react";
import { fetchApiKeysStatus, saveApiKeys, deleteApiKey, testApiKey } from "@/lib/api";
import { cn } from "@/lib/utils";

const PROVIDERS = [
  {
    field: "groq_api_key",
    provider: "groq",
    label: "Groq API Key",
    hint: "Used for semantic tagging and report writing. Get one at console.groq.com/keys.",
    placeholder: "gsk_...",
  },
  {
    field: "gemini_api_key",
    provider: "gemini",
    label: "Gemini API Key",
    hint: "Backup provider — used automatically if Groq is unavailable. Get one at aistudio.google.com/apikey.",
    placeholder: "AIza...",
  },
  {
    field: "hf_token",
    provider: "hf_token",
    label: "Hugging Face Token",
    hint: "Powers dataset chat (embeddings). Get one at huggingface.co/settings/tokens.",
    placeholder: "hf_...",
  },
];

const TEST_LABELS = {
  healthy: { text: "Working", tone: "good" },
  invalid_key: { text: "Invalid key", tone: "bad" },
  unauthorized: { text: "Unauthorized", tone: "bad" },
  quota_exceeded: { text: "Quota exceeded", tone: "warn" },
  model_unavailable: { text: "Model unavailable", tone: "warn" },
  not_configured: { text: "No key entered", tone: "warn" },
  unreachable: { text: "Unreachable", tone: "bad" },
};

function ResultBadge({ result }) {
  if (!result) return null;
  if (result === "testing") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Testing…
      </span>
    );
  }
  const meta = TEST_LABELS[result] || { text: result, tone: "warn" };
  const toneClasses = {
    good: "text-green-700 dark:text-green-400",
    bad: "text-red-700 dark:text-red-400",
    warn: "text-amber-700 dark:text-amber-500",
  }[meta.tone];
  const Icon = meta.tone === "good" ? CheckCircle2 : meta.tone === "bad" ? XCircle : AlertTriangle;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${toneClasses}`}>
      <Icon className="w-3.5 h-3.5" /> {meta.text}
    </span>
  );
}

function ProviderRow({ config, status, onChanged }) {
  const [value, setValue] = useState("");
  const [showValue, setShowValue] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  // null → derive from server state; otherwise the user's explicit pick for this row.
  // Reset to null after every save/clear so it re-syncs with the reloaded status.
  const [modeOverride, setModeOverride] = useState(null);
  const mode = modeOverride ?? (status?.configured ? "own" : "default");

  const handleChanged = () => {
    setModeOverride(null);
    onChanged();
  };

  const handleTest = async () => {
    if (!value.trim()) return;
    setTestResult("testing");
    setError("");
    try {
      const res = await testApiKey(config.provider, value.trim());
      setTestResult(res.status);
    } catch (err) {
      setTestResult(null);
      setError(err.message || "Test failed");
    }
  };

  const handleSave = async () => {
    if (!value.trim()) return;
    setSaving(true);
    setError("");
    try {
      await saveApiKeys({ [config.field]: value.trim() });
      setValue("");
      setTestResult(null);
      handleChanged();
    } catch (err) {
      setError(err.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const selectOwn = () => {
    setError("");
    setModeOverride("own");
  };

  const selectDefault = async () => {
    setError("");
    setValue("");
    setTestResult(null);
    setModeOverride("default");
    if (!status?.configured) return;
    // A saved key exists — switching to "shared default" means deleting it.
    setSaving(true);
    try {
      await deleteApiKey(config.provider);
      handleChanged();
    } catch (err) {
      setModeOverride("own");
      setError(err.message || "Couldn't switch back to the shared default");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-neutral-200 dark:border-neutral-800 p-6">
      <div className="flex items-start justify-between gap-4 mb-1">
        <label className="block text-xs uppercase tracking-widest text-neutral-600 dark:text-neutral-400 font-mono">
          {config.label}
        </label>
        {status?.configured && (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-green-700 dark:text-green-400 whitespace-nowrap">
            <CheckCircle2 className="w-3.5 h-3.5" /> Saved ({status.masked})
          </span>
        )}
      </div>
      <p className="text-xs text-neutral-500 dark:text-neutral-500 mb-4">{config.hint}</p>

      <div
        role="radiogroup"
        aria-label={`${config.label} source`}
        className="mb-3 inline-flex overflow-hidden rounded-sm border border-neutral-200 text-xs font-medium dark:border-neutral-800"
      >
        {[
          { key: "default", label: "Shared default" },
          { key: "own", label: "My own key" },
        ].map((opt, i) => (
          <button
            key={opt.key}
            type="button"
            role="radio"
            aria-checked={mode === opt.key}
            disabled={saving}
            onClick={opt.key === "own" ? selectOwn : selectDefault}
            className={cn(
              "px-3 py-1.5 transition-colors disabled:opacity-50",
              i > 0 && "border-l border-neutral-200 dark:border-neutral-800",
              mode === opt.key
                ? "bg-amber-700 text-white"
                : "bg-white text-neutral-600 hover:bg-neutral-50 dark:bg-neutral-950 dark:text-neutral-400 dark:hover:bg-neutral-900"
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {mode === "default" ? (
        <p className="text-xs text-neutral-500 dark:text-neutral-500">
          {saving
            ? "Switching to the shared default…"
            : "This provider uses the app's shared key. Your quota isn't touched."}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[220px]">
              <input
                type={showValue ? "text" : "password"}
                value={value}
                onChange={(e) => { setValue(e.target.value); setTestResult(null); }}
                placeholder={status?.configured ? "Enter a new key to replace it…" : config.placeholder}
                className="w-full pl-3 pr-10 py-2.5 bg-white dark:bg-neutral-950 border border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-sm text-sm focus:outline-none focus:border-amber-700 dark:focus:border-amber-600"
              />
              <button
                type="button"
                onClick={() => setShowValue((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                tabIndex={-1}
              >
                {showValue ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>

            <motion.button
              type="button"
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleTest}
              disabled={!value.trim() || testResult === "testing"}
              className="px-3 py-2.5 border border-neutral-200 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-900 text-sm font-medium rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Test
            </motion.button>

            <motion.button
              type="button"
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSave}
              disabled={!value.trim() || saving}
              className="px-4 py-2.5 bg-amber-700 hover:bg-amber-800 text-white text-sm font-medium rounded-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Save
            </motion.button>
          </div>

          <div className="mt-2 min-h-[1.25rem]">
            {error ? (
              <span className="text-xs text-red-700 dark:text-red-400">{error}</span>
            ) : (
              <ResultBadge result={testResult} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function ApiKeysPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const load = async () => {
    setLoadError("");
    try {
      const res = await fetchApiKeysStatus();
      setStatus(res);
    } catch (err) {
      setLoadError(err.message || "Failed to load API key settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="mt-6">
      <h3 className="text-lg font-serif font-bold mb-2">Your Own API Keys</h3>
      <p className="text-neutral-600 dark:text-neutral-400 text-sm mb-6">
        If analysis or report generation isn't working — the shared key may be out of quota or
        revoked. Add your own key below and it's used for your analyses, chat, and reports
        instead. Keys are encrypted at rest and never shown again once saved.
      </p>

      {loading ? (
        <div className="text-sm text-neutral-500 dark:text-neutral-400">Loading…</div>
      ) : loadError ? (
        <div className="text-sm text-red-700 dark:text-red-400">{loadError}</div>
      ) : (
        <div className="space-y-4">
          {PROVIDERS.map((config) => (
            <ProviderRow
              key={config.provider}
              config={config}
              status={status?.[config.provider]}
              onChanged={load}
            />
          ))}
        </div>
      )}
    </div>
  );
}
