import React, { useEffect, useState } from "react";
import { AlertCircle, CheckCircle, AlertTriangle, RotateCw, KeyRound } from "lucide-react";
import { apiUrl, testApiKey } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

// Maps this widget's health-payload provider keys to the settings API's
// provider identifiers (the one mismatch: "huggingface" here vs "hf_token" there).
const PROVIDER_TEST_KEY = { groq: "groq", gemini: "gemini", huggingface: "hf_token" };

/**
 * Display LLM connectivity status (Groq for semantic tagging, Gemini for fallback, HF for embeddings)
 * plus the RAG database status (Postgres+pgvector) that dataset-chat actually depends on — this can
 * be down even when every LLM shows healthy, since none of the LLM checks touch Postgres.
 * Fetches health from /api/health and shows indicator in navbar.
 * Manual test button triggers /api/health/test-llm for on-demand connectivity check.
 *
 * Signed-in users can also type their own key per provider to test THAT key
 * instead of the app's shared/default one — leaving a field empty tests the
 * default, exactly like before. Nothing typed here is saved; use Profile >
 * Settings > API Keys to actually keep a key in place of the shared one.
 */
export default function LLMHealthIndicator() {
  const { user } = useAuth();
  const [llmStatus, setLlmStatus] = useState({ groq: "unknown", gemini: "unknown", huggingface: "unknown" });
  const [ragStatus, setRagStatus] = useState({ database: "unknown" });
  const [isChecking, setIsChecking] = useState(true);
  const [isTesting, setIsTesting] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const [lastTestTime, setLastTestTime] = useState(null);
  const [customKeys, setCustomKeys] = useState({ groq: "", gemini: "", huggingface: "" });
  const [customTested, setCustomTested] = useState({});

  const checkHealth = async () => {
    try {
      const response = await fetch(apiUrl("/api/health"));
      if (response.ok) {
        const data = await response.json();
        setLlmStatus(data.llm || { groq: "unknown", gemini: "unknown", huggingface: "unknown" });
        setRagStatus(data.rag || { database: "unknown" });
        setCustomTested({}); // background check reflects the default keys only
      }
    } catch (error) {
      console.error("Failed to fetch health status:", error);
    } finally {
      setIsChecking(false);
    }
  };

  const testLLMs = async () => {
    setIsTesting(true);
    try {
      const response = await fetch(apiUrl("/api/health/test-llm"), { method: "POST" });
      let nextLlm = llmStatus;
      let nextRag = ragStatus;
      if (response.ok) {
        const data = await response.json();
        nextLlm = data.llm || nextLlm;
        nextRag = data.rag || nextRag;
      } else {
        console.error("Test failed with status:", response.status);
      }

      // Any provider with a key typed in gets tested with THAT key instead,
      // overriding the default result just fetched above.
      const overrides = {};
      const usedCustom = {};
      await Promise.all(
        Object.entries(customKeys).map(async ([provider, key]) => {
          const trimmed = key.trim();
          if (!trimmed || !user) return;
          try {
            const result = await testApiKey(PROVIDER_TEST_KEY[provider], trimmed);
            overrides[provider] = result.status;
          } catch {
            overrides[provider] = "unreachable";
          }
          usedCustom[provider] = true;
        })
      );

      setLlmStatus({ ...nextLlm, ...overrides });
      setRagStatus(nextRag);
      setCustomTested(usedCustom);
      setLastTestTime(new Date().toLocaleTimeString());
    } catch (error) {
      console.error("Failed to test LLM connections:", error);
    } finally {
      setIsTesting(false);
    }
  };

  useEffect(() => {
    checkHealth();
    // Backend checks now make a real, quota-metered call per provider (not a free
    // connectivity ping) so decommissioned models / exhausted quota show up here
    // instead of a false "healthy". Polling every 2 minutes instead of 30s keeps
    // that cost sane for tight free-tier daily limits; use "Test Connections" for
    // an immediate on-demand check.
    const interval = setInterval(checkHealth, 120000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case "healthy":
        return "bg-green-500";
      case "not_configured":
        return "bg-gray-400";
      case "unreachable":
      case "model_unavailable":
        return "bg-red-500";
      case "invalid_key":
      case "unauthorized":
      case "auth_failed":
      case "extension_missing":
      case "quota_exceeded":
        return "bg-orange-500";
      default:
        return "bg-gray-300";
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case "healthy":
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case "unreachable":
      case "invalid_key":
      case "unauthorized":
      case "auth_failed":
      case "model_unavailable":
        return <AlertCircle className="h-4 w-4 text-red-600" />;
      case "extension_missing":
      case "quota_exceeded":
        return <AlertTriangle className="h-4 w-4 text-orange-600" />;
      case "not_configured":
        return <AlertTriangle className="h-4 w-4 text-gray-600" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-gray-600" />;
    }
  };

  const getStatusLabel = (status) => {
    const labels = {
      healthy: "Connected",
      not_configured: "Not configured",
      unreachable: "Unreachable",
      invalid_key: "Invalid key",
      unauthorized: "Unauthorized",
      auth_failed: "Auth failed",
      extension_missing: "pgvector extension missing",
      quota_exceeded: "Quota exceeded",
      model_unavailable: "Model decommissioned",
      unknown: "Unknown",
    };
    return labels[status] || status;
  };

  const groqStatus = llmStatus.groq || "unknown";
  const geminiStatus = llmStatus.gemini || "unknown";
  const hfStatus = llmStatus.huggingface || "unknown";
  const dbStatus = ragStatus.database || "unknown";

  const setCustomKey = (provider, value) => {
    setCustomKeys((prev) => ({ ...prev, [provider]: value }));
  };

  // One row = one provider's status line plus its optional "test with my own key" input.
  const ProviderRow = ({ statusKey, status, label }) => (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        {getStatusIcon(status)}
        <div className="flex-1">
          <div className="font-medium text-ink">{label}</div>
          <div className="text-ink-secondary">
            {getStatusLabel(status)}
            {customTested[statusKey] && (
              <span className="ml-1.5 text-[10px] font-medium text-accent">(your key)</span>
            )}
          </div>
        </div>
      </div>
      <div className="relative">
        <KeyRound className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-muted" />
        <input
          type="password"
          value={customKeys[statusKey]}
          onChange={(e) => setCustomKey(statusKey, e.target.value)}
          disabled={!user}
          placeholder={user ? "Test with your own key…" : "Sign in to test your own key"}
          className="w-full rounded border border-line bg-raised py-1 pl-6 pr-2 text-[11px] text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
        />
      </div>
    </div>
  );

  return (
    <div className="relative">
      <button
        onClick={() => setShowTooltip(!showTooltip)}
        className="relative flex items-center gap-2 rounded-lg bg-raised px-3 py-1.5 text-xs hover:bg-canvas transition-colors"
        title="LLM API Status"
      >
        <span className="text-ink-secondary">LLM Status</span>
        <div className="flex gap-1">
          <div className={`h-2 w-2 rounded-full ${getStatusColor(groqStatus)}`} title={`Groq: ${getStatusLabel(groqStatus)}`} />
          <div className={`h-2 w-2 rounded-full ${getStatusColor(geminiStatus)}`} title={`Gemini: ${getStatusLabel(geminiStatus)}`} />
          <div className={`h-2 w-2 rounded-full ${getStatusColor(hfStatus)}`} title={`Hugging Face: ${getStatusLabel(hfStatus)}`} />
          <div className={`h-2 w-2 rounded-full ${getStatusColor(dbStatus)}`} title={`RAG Database: ${getStatusLabel(dbStatus)}`} />
        </div>
      </button>

      {showTooltip && (
        <div className="absolute right-0 mt-2 w-72 rounded-lg border border-line bg-canvas p-3 shadow-lg z-50">
          <div className="space-y-3 text-xs">
            <div className="flex justify-between items-center">
              <div className="font-semibold text-ink">LLM Connectivity</div>
              <button
                onClick={() => setShowTooltip(false)}
                className="text-ink-muted hover:text-ink"
              >
                ✕
              </button>
            </div>

            <ProviderRow statusKey="groq" status={groqStatus} label="Semantic Tagging (Groq)" />
            <ProviderRow statusKey="gemini" status={geminiStatus} label="Narrative (Gemini)" />
            <ProviderRow statusKey="huggingface" status={hfStatus} label="RAG Embeddings (Hugging Face)" />

            <div className="flex items-center gap-2 border-t border-line pt-3">
              {getStatusIcon(dbStatus)}
              <div>
                <div className="font-medium text-ink">RAG Database (Postgres/pgvector)</div>
                <div className="text-ink-secondary">{getStatusLabel(dbStatus)}</div>
              </div>
            </div>

            {!user && (
              <p className="text-ink-muted">Sign in to test your own Groq/Gemini/HF keys here — fields above will unlock.</p>
            )}

            {lastTestTime && (
              <div className="text-ink-muted text-xs py-1 border-t border-line">
                Last tested: {lastTestTime}
              </div>
            )}

            <button
              onClick={testLLMs}
              disabled={isTesting}
              className="w-full flex items-center justify-center gap-2 rounded bg-accent text-white py-2 px-3 hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              <RotateCw className={`h-3 w-3 ${isTesting ? "animate-spin" : ""}`} />
              {isTesting ? "Testing..." : "Test Connections"}
            </button>

            {(groqStatus === "not_configured" || geminiStatus === "not_configured" || hfStatus === "not_configured") && (
              <div className="rounded bg-orange-50 p-2 text-orange-800">
                ⚠️ Configure missing API keys in .env
              </div>
            )}
            {(groqStatus === "unreachable" || geminiStatus === "unreachable" || hfStatus === "unreachable") && (
              <div className="rounded bg-red-50 p-2 text-red-800">
                ❌ API unreachable. Check network and credentials.
              </div>
            )}
            {(groqStatus === "model_unavailable" || geminiStatus === "model_unavailable") && (
              <div className="rounded bg-red-50 p-2 text-red-800">
                ❌ Configured model has been retired by the provider. Update the model constant in the backend.
              </div>
            )}
            {(groqStatus === "quota_exceeded" || geminiStatus === "quota_exceeded" || hfStatus === "quota_exceeded") && (
              <div className="rounded bg-orange-50 p-2 text-orange-800">
                ⚠️ API quota exhausted. Check plan/billing for that provider.
              </div>
            )}
            {dbStatus === "not_configured" && (
              <div className="rounded bg-orange-50 p-2 text-orange-800">
                ⚠️ Set DATABASE_URL to enable detailed RAG dataset chat.
              </div>
            )}
            {dbStatus === "extension_missing" && (
              <div className="rounded bg-orange-50 p-2 text-orange-800">
                ⚠️ Run <code>CREATE EXTENSION vector;</code> on the database.
              </div>
            )}
            {(dbStatus === "unreachable" || dbStatus === "auth_failed") && (
              <div className="rounded bg-red-50 p-2 text-red-800">
                ❌ RAG database unreachable. Check DATABASE_URL and credentials.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
