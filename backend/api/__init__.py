"""FastAPI communication layer for the MultiAgent DataAnalyst pipeline.

This package wraps the existing LangGraph pipeline (Agents 1-6) with a
production-ready HTTP + Server-Sent-Events API so a React/Vite frontend can
upload CSVs, stream live progress, and fetch results. It does NOT modify any
agent or the pipeline itself.
"""

__version__ = "1.0.0"
