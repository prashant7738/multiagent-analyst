import React, { useEffect, useState } from "react";
import { AlertCircle, CheckCircle, AlertTriangle, RotateCw } from "lucide-react";
import { apiUrl, testLlmConnections, fetchApiKeysStatus } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

/**
 * LLM connectivity status (Groq for tagging, Gemini fallback, HF for embeddings)
 * plus the RAG database (Postgres+pgvector) that dataset-chat depends on.
 *
 * The coloured dots come from the passive /api/health poll, which always
 * reflects the app's SHARED keys. "Test Connections" instead tests whichever
 * key is actually in effect for the signed-in user — their saved key per
 * provider, or the shared default where they haven't saved one. Keys are
 * managed in Profile → API Keys, never typed here.
 */
export default function LLMHealthIndicator() {
  const { user } = useAuth();
  const [llmStatus, setLlmStatus] = useState({ groq: "unknown", gemini: "unknown", huggingface: "unknown" });
  const [ragStatus, setRagStatus] = useState({ database: "unknown" });
  const [isTesting, setIsTesting] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const [lastTestTime, setLastTestTime] = useState(null);
  const [testedOwnKeys, setTestedOwnKeys] = useState(false);
  const [savedProviders, setSavedProviders] = useState({});

  const checkHealth = async () => {
    try {
      const response = await fetch(apiUrl("/api/health"));
      if (response.ok) {
        const data = await response.json();
        setLlmStatus(data.llm || { groq: "unknown", gemini: "unknown", huggingface: "unknown" });
        setRagStatus(data.rag || { database: "unknown" });
      }
    } catch (error) {
      console.error("Failed to fetch health status:", error);
    }
  };

  const testConnections = async () => {
    setIsTesting(true);
    try {
      const data = await testLlmConnections(); // tests saved keys when signed in
      setLlmStatus(data.llm || llmStatus);
      setRagStatus(data.rag || ragStatus);
      setTestedOwnKeys(Boolean(user) && Object.values(savedProviders).some(Boolean));
      setLastTestTime(new Date().toLocaleTimeString());
    } catch (error) {
      console.error("Failed to test LLM connections:", error);
    } finally {
      setIsTesting(false);
    }
  };

  useEffect(() => {
    checkHealth();
    // Each backend check is a real, quota-metered call per provider, so poll
    // slowly (2 min); use "Test Connections" for an immediate check.
    const interval = setInterval(checkHealth, 120000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!user) {
      setSavedProviders({});
      return;
    }
    fetchApiKeysStatus()
      .then((data) => {
        if (cancelled) return;
        setSavedProviders({
          groq: !!data?.groq?.configured,
          gemini: !!data?.gemini?.configured,
          huggingface: !!data?.hf_token?.configured,
        });
      })
      .catch(() => !cancelled && setSavedProviders({}));
    return () => { cancelled = true; };
  }, [user]);

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

  const ProviderRow = ({ statusKey, status, label }) => (
    <div className="flex items-center gap-2">
      {getStatusIcon(status)}
      <div className="flex-1">
        <div className="font-medium text-ink">{label}</div>
        <div className="text-ink-secondary">
          {getStatusLabel(status)}
          {testedOwnKeys && savedProviders[statusKey] && (
            <span className="ml-1.5 text-[10px] font-medium text-accent">(your key)</span>
          )}
        </div>
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
              <button onClick={() => setShowTooltip(false)} className="text-ink-muted hover:text-ink">
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

            <p className="text-ink-muted">
              {user
                ? "Test Connections checks your saved keys, or the shared default where you haven't set one. Manage keys in Profile → API Keys."
                : "Dots reflect the app's shared keys. Sign in and save your own keys in Profile to test them here."}
            </p>

            {lastTestTime && (
              <div className="text-ink-muted text-xs py-1 border-t border-line">
                Last tested: {lastTestTime}
                {testedOwnKeys ? " · your saved keys" : " · shared defaults"}
              </div>
            )}

            <button
              onClick={testConnections}
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
                ⚠️ API quota exhausted. Check plan/billing, or save your own key in Profile → API Keys.
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
