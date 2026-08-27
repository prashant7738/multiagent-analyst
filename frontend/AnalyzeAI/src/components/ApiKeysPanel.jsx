import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Eye, EyeOff, CheckCircle2, XCircle, AlertTriangle, Loader2, Trash2 } from "lucide-react";
import { fetchApiKeysStatus, saveApiKeys, deleteApiKey, testApiKey } from "@/lib/api";

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
      onChanged();
    } catch (err) {
      setError(err.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    setSaving(true);
    setError("");
    try {
      await deleteApiKey(config.provider);
      onChanged();
    } catch (err) {
      setError(err.message || "Clear failed");
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
        {status?.configured ? (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-green-700 dark:text-green-400 whitespace-nowrap">
            <CheckCircle2 className="w-3.5 h-3.5" /> Configured ({status.masked})
          </span>
        ) : (
          <span className="text-xs text-neutral-500 dark:text-neutral-500 whitespace-nowrap">Using shared default</span>
        )}
      </div>
      <p className="text-xs text-neutral-500 dark:text-neutral-500 mb-4">{config.hint}</p>

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

        {status?.configured && (
          <motion.button
            type="button"
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleClear}
            disabled={saving}
            title="Remove this key and go back to the shared default"
            className="p-2.5 border border-neutral-200 dark:border-neutral-800 hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-700 dark:hover:text-red-400 rounded-sm transition-all disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" />
          </motion.button>
        )}
      </div>

      <div className="mt-2 min-h-[1.25rem]">
        {error ? (
          <span className="text-xs text-red-700 dark:text-red-400">{error}</span>
        ) : (
          <ResultBadge result={testResult} />
        )}
      </div>
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
