# AnalyzeAI

### Turn an opaque spreadsheet into a decision-ready story.

AnalyzeAI is a production-minded, multi-agent data analyst that takes messy business data and turns it into an explainable analysis: cleaned data, quality scores, statistical findings, signal-driven charts, recommendations, and a polished HTML/PDF report.

This is more than an LLM wrapper. The system combines deterministic data engineering and statistics with carefully bounded LLM assistance, so the output remains auditable when a model is unavailable, uncertain, or wrong.

## Why This Project Stands Out

- **End-to-end ownership:** upload a dataset, watch the analysis progress in real time, explore the results, ask questions, and download a report from one product.
- **Multi-agent architecture with a clear contract:** six specialized stages communicate through a shared `GraphState`, making responsibilities visible, testable, and replaceable.
- **Grounded AI instead of unbounded generation:** deterministic facts are extracted from computed statistics first; LLM prose is validated before it reaches the report.
- **Dataset-aware visualization:** chart selection is driven by statistical signal such as correlation, regression strength, concentration, skew, outliers, and category effects, rather than hardcoded column names.
- **Failure-aware engineering:** LLM fallbacks, validation gates, accumulated errors, cooperative cancellation, upload limits, and isolated run artifacts keep partial failures understandable.
- **Real product surface:** authentication, job history, per-user model keys, live Server-Sent Events (SSE), report downloads, responsive React UI, and dataset chat turn the pipeline into a usable application.
- **Evidence of quality:** a focused backend test suite covers parsing, normalization, statistical edge cases, chart safety, report grounding, API behavior, and regression paths.

## Product Flow

```text
Upload CSV / Excel / JSON / JSONL / Parquet
                    |
                    v
       Profile -> Understand -> Prepare
                    |
                    v
       Analyze -> Validate -> Explain
                    |
                    v
     Interactive dashboard + HTML/PDF report + chat
```

## What the Six Agents Do

| Stage | Responsibility | Engineering value |
| --- | --- | --- |
| **Agent 1: Structural Profiler** | Profiles shape, types, missingness, duplicates, and representative values. | Establishes a trustworthy baseline before transformations begin. |
| **Agent 2: Semantic Tagger** | Combines local type sniffing with LLM-assisted semantic labels such as currency, identifier, date, and category. | Gives downstream processing business context without sending entire datasets to the model. |
| **Agent 3: Preprocessor** | Coerces types, normalizes text/nulls/currencies, imputes missing values, removes duplicates, clips outliers, scales values, extracts date features, and derives business metrics. | Produces reproducible transformations with an audit trail and quality score. |
| **Agent 4: Statistical Analyst** | Computes descriptive statistics, correlations, anomalies, regression, growth, seasonality, and cross-dimensional findings. | Converts cleaned data into measurable evidence. |
| **Agent 5: Output Validator** | Checks categories, trends, metrics, leakage risks, and report inputs for consistency. | Adds a quality gate between computation and communication. |
| **Agent 6: Insight Report Generator** | Builds grounded findings, recommendations, charts, and plain-language HTML/PDF reports. | Makes analysis useful to both technical and non-technical readers. |

## Technical Highlights

### Reliable AI orchestration

- LangGraph state-based DAG with conditional routing and shared typed state.
- Minimal prompts based on metadata and samples to reduce cost and data exposure.
- Groq and Gemini support with graceful fallback behavior.
- Deterministic narrative fallback when no LLM key is available.
- Hybrid narrative validation for unsupported claims, unknown chart IDs, and unexplained jargon.

### Data quality and reproducibility

- Handles messy currencies including `$`, `€`, `£`, `₹`, `¥`, and `₩`.
- Normalizes common null-string variants and inconsistent categorical values.
- Tracks scaling parameters for downstream interpretation and inverse transformation.
- Records every preprocessing action in an audit log.
- Produces completeness, duplicate, validation, confidence, and decision-readiness signals.

### Insight reports that communicate

- KPI hero section followed by an “In Plain English” explanation.
- Story structure: what happened, why it matters, and what to do next.
- Chart specs carry titles, explanations, alt text, annotations, and pre-aggregated data.
- Apache ECharts for interactive browser visuals and deterministic Matplotlib twins for print/PDF.
- Per-run chart/report directories prevent concurrent jobs from overwriting one another.
- Technical details remain available in a structured appendix rather than overwhelming the main story.

### Full-stack application engineering

- FastAPI API with authenticated routes for analysis, jobs, reports, chat, settings, and health.
- Background pipeline jobs return immediately with a job ID.
- SSE progress streams expose agent-level status to the frontend without polling.
- Upload validation, size limits, request validation, structured JSON errors, and cooperative cancellation.
- React 19 + Vite frontend with responsive analysis, history, profile, report, and dataset-chat views.
- Optional PostgreSQL persistence with `pgvector` support for retrieval-oriented features.

## Architecture

```text
                         +----------------------+
                         | React 19 / Vite UI   |
                         | upload, dashboard,   |
                         | history, chat        |
                         +----------+-----------+
                                    |
                         HTTP + SSE |
                                    v
                         +----------------------+
                         | FastAPI application  |
                         | auth, jobs, reports, |
                         | settings, health     |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | LangGraph pipeline   |
                         | Agents 1 -> 6        |
                         +----------+-----------+
                                    |
             +----------------------+----------------------+
             v                      v                      v
       cleaned data          chart specifications     HTML / PDF report
       + audit trail          + static render          + grounded narrative
```

## Tech Stack

**Backend:** Python 3.12+, FastAPI, Uvicorn, LangGraph, LangChain Core, Pandas, NumPy, SciPy, scikit-learn, Matplotlib, Jinja2, WeasyPrint

**AI and persistence:** Groq, Google Gemini, Hugging Face integrations, PostgreSQL, `pgvector`, cryptography

**Frontend:** React 19, Vite, Tailwind CSS, Framer Motion, React Router, Lucide icons

**Quality:** Pytest, focused unit/integration tests, validation gates, deterministic fallbacks

## Repository Layout

```text
backend/
├── agents/                 # Six analysis and reporting stages
├── api/
│   ├── routes/             # Auth, analysis, jobs, reports, chat, settings, health
│   ├── services/           # Job management, pipeline execution, SSE, persistence
│   └── models/             # API schemas and domain models
├── templates/              # HTML report templates
├── tests/                  # Backend regression and behavior tests
├── pipeline.py             # LangGraph pipeline entry point
├── main.py                 # Shared graph state
└── run.py                  # FastAPI/Uvicorn launcher
frontend/AnalyzeAI/
├── src/components/         # Dashboard, timeline, chat, report, upload UI
├── src/pages/              # Analyze, history, profile, auth, and error views
└── src/lib/                # API and client utilities
```

## Run Locally

### 1. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # if your local setup provides one
python run.py
```

The API runs at `http://localhost:8000`; interactive API documentation is available at `http://localhost:8000/docs`.

### 2. Start the frontend

```bash
cd frontend/AnalyzeAI
npm install
npm run dev
```

The Vite development server will print the local frontend URL. Configure the frontend API base URL using the project's environment example before connecting it to a non-default backend.

### 3. Run the pipeline directly

For a script-first run without the web application:

```bash
cd backend
python pipeline.py
```

The pipeline writes cleaned data, analysis artifacts, charts, audit information, and reports under `backend/outputs/`.

## Configuration

The backend is environment-driven. Typical local configuration includes:

- LLM credentials for Groq and/or Gemini.
- API host, port, reload, and logging settings.
- Upload directory, maximum upload size, and allowed file extensions.
- Optional database URL for persistence and user settings.
- Optional frontend API URL for local development.

Keep secrets in environment variables and never commit `.env` files or API keys.

## Testing

Run the backend tests from the backend directory:

```bash
cd backend
pytest -q
```

The suite covers agent behavior, JSON recovery, currency parsing, category normalization, derived metrics, anomaly calibration, chart planning/rendering, report grounding, table completeness, API services, configuration propagation, and data-quality auditing.

## Engineering Decisions Worth Discussing

1. **Why not let the LLM analyze the raw file?** Metadata-first prompts reduce cost and exposure, while deterministic Python handles transformations and calculations.
2. **Why validate generated prose?** A fluent sentence can still make an unsupported claim. The report pipeline keeps computed facts authoritative and treats model prose as an enhancement.
3. **Why use both ECharts and Matplotlib?** Users get an interactive web experience and a deterministic, printable artifact from the same chart contract.
4. **Why keep agents as state transformations?** Explicit `(state) -> state` boundaries make the workflow observable, testable, and easy to extend.

## Future Direction

The architecture is ready for larger datasets through chunked ingestion, streaming execution, richer anomaly detection, persisted model artifacts, and distributed processing. These are deliberate extension points rather than prerequisites for the current end-to-end workflow.

## License

This project is currently maintained as a portfolio and learning project. Add a license before distributing it as an open-source package.
