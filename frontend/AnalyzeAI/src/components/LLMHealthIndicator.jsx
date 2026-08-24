import React, { useEffect, useState } from "react";
import { AlertCircle, CheckCircle, AlertTriangle, RotateCw } from "lucide-react";

/**
 * Display LLM connectivity status (Groq for semantic tagging, Gemini for fallback, HF for embeddings).
 * Fetches health from /api/health and shows indicator in navbar.
 * Manual test button triggers /api/health/test-llm for on-demand connectivity check.
 */
export default function LLMHealthIndicator() {
  const [llmStatus, setLlmStatus] = useState({ groq: "unknown", gemini: "unknown", huggingface: "unknown" });
  const [isChecking, setIsChecking] = useState(true);
  const [isTesting, setIsTesting] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const [lastTestTime, setLastTestTime] = useState(null);

  const checkHealth = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/health");
      if (response.ok) {
        const data = await response.json();
        setLlmStatus(data.llm || { groq: "unknown", gemini: "unknown", huggingface: "unknown" });
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
      const response = await fetch("http://localhost:8000/api/health/test-llm", {
        method: "POST",
      });
      if (response.ok) {
        const data = await response.json();
        setLlmStatus({ groq: data.groq, gemini: data.gemini, huggingface: data.huggingface });
        setLastTestTime(new Date().toLocaleTimeString());
      } else {
        console.error("Test failed with status:", response.status);
      }
    } catch (error) {
      console.error("Failed to test LLM connections:", error);
    } finally {
      setIsTesting(false);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30s
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case "healthy":
        return "bg-green-500";
      case "not_configured":
        return "bg-gray-400";
      case "unreachable":
        return "bg-red-500";
      case "invalid_key":
      case "unauthorized":
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
        return <AlertCircle className="h-4 w-4 text-red-600" />;
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
      unknown: "Unknown",
    };
    return labels[status] || status;
  };

  const groqStatus = llmStatus.groq || "unknown";
  const geminiStatus = llmStatus.gemini || "unknown";
  const hfStatus = llmStatus.huggingface || "unknown";

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
        </div>
      </button>

      {showTooltip && (
        <div className="absolute right-0 mt-2 w-64 rounded-lg border border-line bg-canvas p-3 shadow-lg z-50">
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

            <div className="flex items-center gap-2">
              {getStatusIcon(groqStatus)}
              <div>
                <div className="font-medium text-ink">Semantic Tagging (Groq)</div>
                <div className="text-ink-secondary">{getStatusLabel(groqStatus)}</div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {getStatusIcon(geminiStatus)}
              <div>
                <div className="font-medium text-ink">Narrative (Gemini)</div>
                <div className="text-ink-secondary">{getStatusLabel(geminiStatus)}</div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {getStatusIcon(hfStatus)}
              <div>
                <div className="font-medium text-ink">RAG Embeddings (Hugging Face)</div>
                <div className="text-ink-secondary">{getStatusLabel(hfStatus)}</div>
              </div>
            </div>

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
          </div>
        </div>
      )}
    </div>
  );
}
