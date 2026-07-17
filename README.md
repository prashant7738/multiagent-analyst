# MultiAgent DataAnalyst - Automated LLM-Powered Data Analysis Pipeline

## 📋 Project Overview

**MultiAgent_DataAnalyst** is an automated, LLM-powered data analysis pipeline that processes CSV files through a sequence of specialized agents. It performs structural profiling, semantic tagging, data preprocessing, statistical analysis, and visualization generation.

This project demonstrates a sophisticated multi-agent architecture using state-based orchestration to intelligently analyze and transform raw data into actionable insights.

---

## 🏗️ Architecture Overview

### Technology Stack
- **LLM**: Groq API (llama-3.3-70b-versatile)
- **Orchestration**: LangGraph (state-based DAG pipeline)
- **Data Processing**: Pandas, NumPy, SciPy
- **Visualization**: Matplotlib
- **Framework**: Python 3.12+

### Pipeline Flow

```
CSV File (Input)
    ↓
[Agent 1] Structural Profiler
    → Analyze raw structure & profiling
    ↓
[Agent 2] Semantic Tagger (LLM)
    → Infer data types & semantic meaning
    ↓
[Agent 3] Preprocessor
    → Clean, transform & normalize data
    ↓
[Agent 4] Statistical Analysis
    → Generate statistics & visualizations
    ↓
Processed Data + Analysis (Output)
```

---

## ✅ Completed Features

### Agent 1: Structural Profiler (100% Complete)
- Reads and analyzes raw CSV structure
- **Outputs**:
  - Data type detection for each column
  - Missing value count & percentage
  - Unique value counts
  - Sample values preview
  - Dataset-level statistics (shape, total cells, duplicate rows)
- **Error Handling**: Robust CSV loading with error logging

### Agent 2: Semantic Tagger (100% Complete)
- **Type Sniffing**: Pure Python heuristics for numeric, datetime, boolean, and string detection
- **LLM-Powered Tagging** (via Groq):
  - Semantic classification (Currency, Identifier, DateTime, Categorical)
  - Column-specific processing rules
  - Imputation strategy recommendations
- **Fallback Logic**: Graceful degradation when LLM unavailable
- **Output**: Schema blueprint with per-column metadata

### Agent 3: Preprocessor (100% Complete)
Comprehensive 10-step data cleaning and transformation pipeline:

1. **Type Coercion** - Convert columns to intended types (float, int, datetime, boolean)
2. **Currency Cleaning** - Handle international symbols (₹, $, €, £, ¥, ₩) and formats
3. **Text Standardization** - Normalize whitespace, case, and null variants
4. **Duplicate Removal** - Drop exact row duplicates
5. **Imputation** - Smart missing value handling (mean, median, mode, drop, unknown_label)
6. **Outlier Clipping** - IQR-based outlier detection and clipping
7. **Scaling** - Min-Max normalization (0-1) with parameter tracking
8. **Date Feature Extraction** - Derive year, month, day, day_of_week, is_weekend, etc.
9. **Business Metrics Derivation** - Auto-calculate profit, margins, revenue per unit, etc.
10. **Quality Scoring** - Generate comprehensive data quality metrics (0-100 score)

- **Outputs**: Cleaned DataFrame, scaling parameters, audit trail, quality metrics

### Agent 4: Statistical Analysis (Partial - 40% Complete)
- **Implemented**: Core analysis framework and chart generation infrastructure
- **Status**: Foundation laid for full statistics pipeline

### Pipeline Orchestration (100% Complete)
- LangGraph-based state management
- Error-aware routing with conditional edges
- Graceful failure handling
- Sequential flow with error accumulation

---

## 🚧 In Progress / Planned Features

### Agent 4: Statistical Analysis (Complete)
- [x] Descriptive statistics (mean, median, std, quantiles)
- [x] Correlation analysis (Pearson + Spearman, strong-pair detection)
- [x] Anomaly detection (z-score, configurable threshold)
- [x] Regression modeling (linear trend per numeric column)
- [x] Advanced chart generation (heatmap, box plots, histograms, bar charts, trend lines)

### Future Agents
- **Agent 5**: Data validation & constraint checking
- **Agent 6**: Final comprehensive report generation

### Additional Features
- [ ] Frontend/UI for pipeline visualization
- [x] Support for multiple file formats — CSV, Excel (.xlsx/.xlsm/.xls), JSON, JSON Lines, Parquet
- [ ] Configuration file for customizable processing rules
- [ ] Structured logging framework
- [x] Unit tests for Agent 1, Agent 2, Agent 3, Agent 4, and pipeline diagnostics
- [ ] Performance optimization for very large datasets (chunked ingestion)

---

## 📁 Project Structure

```
backend/
├── main.py                      # GraphState definition & shared state schema
├── pipeline.py                  # LangGraph DAG construction & entry point
├── pyproject.toml              # Dependencies & project configuration
├── sample_sales.csv            # Test dataset
├── agents/
│   ├── agent_1.py             # Structural Profiler
│   ├── agent_2.py             # Semantic Tagger (LLM)
│   ├── agent_3.py             # Preprocessor (10-step pipeline)
│   └── agent_4.py             # Statistical Analysis
└── outputs/
    └── charts/                # Generated visualizations (PNG)
```

---

## 🎯 Key Design Patterns

1. **Stateless Agent Functions**: Pure functions that transform state without side effects
2. **Error Propagation**: Errors accumulated and propagated throughout pipeline
3. **Semantic-Driven Processing**: Agent 2's schema drives downstream decisions
4. **Audit Trail**: Complete preprocessing log for reproducibility
5. **LLM Fallback**: Graceful degradation when LLM unavailable
6. **Minimal LLM Prompts**: Reduces API costs by sending only metadata + samples

---

## 💡 Notable Features

- **Intelligent Business Metrics**: Auto-derives profit, margins, revenue per unit
- **Quality Scoring**: 0-100 score reflecting data quality before/after processing
- **Scaling Parameter Tracking**: Saves min/max for inverse-transform capability
- **Minimal LLM Prompts**: Reduces API costs by sending only metadata + 3 samples
- **Whole-Word Keyword Matching**: Prevents false column matches
- **Currency Cleaning**: Handles international symbols and formats
- **Null String Normalization**: Converts 14+ variants to NaN

---

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- Groq API key

### Installation

```bash
cd backend
pip install -r requirements.txt
```

### Usage

```bash
cd backend
python pipeline.py
```

**Output**:
- Preprocessed CSV with cleaned data
- JSON file with statistics and quality metrics
- Generated visualizations (PNG charts)
- Complete preprocessing audit log

---

## 📦 Dependencies

- `groq>=1.5.0` - LLM API client
- `langchain-core>=1.4.8` - LangChain utilities
- `langgraph>=1.2.6` - State graph orchestration
- `pandas>=3.0.3` - Data manipulation
- `numpy` - Numerical operations
- `scipy` - Statistical functions
- `matplotlib` - Visualization

---

## 📊 Completion Status

| Component | Status | Completion |
|-----------|--------|------------|
| Agent 1 - Structural Profiler | ✅ Complete | 100% |
| Agent 2 - Semantic Tagger | ✅ Complete | 100% |
| Agent 3 - Preprocessor | ✅ Complete | 100% |
| Agent 4 - Statistical Analysis | ✅ Complete | 100% |
| Pipeline Orchestration | ✅ Complete | 100% |
| Error Handling | ✅ Complete | 100% |
| Agents 5-6 | 📋 Planned | 0% |
| Frontend/UI | 📋 Planned | 0% |
| Multi-format Support (CSV/Excel/JSON/Parquet) | ✅ Complete | 100% |
| Testing Suite | 🚧 In Progress | 70% |

---

## 🔗 Data Flow & State Management

The pipeline uses a centralized `GraphState` that contains:

**Inputs**:
- `csv_path` - Path to input CSV file

**State Fields**:
- `raw_profile` - Raw structural analysis from Agent 1
- `_df_cache` - Cached DataFrame for downstream use
- `schema_blueprint` - Column metadata from Agent 2
- `cleaned_df` - Processed DataFrame from Agent 3
- `scaling_params` - Min/max values for normalization
- `preprocessing_log` - Audit trail of all transformations
- `data_quality` - Quality metrics (0-100 score)
- `stats` - Statistical analysis from Agent 4
- `chart_paths` - Generated visualization file paths
- `errors` - Error collection throughout pipeline

---

## 📝 Notes for Developers

1. Each agent is a pure function: `(state) → (state)`
2. All data flows through `GraphState`
3. Errors are accumulated and checked at each pipeline stage
4. Pipeline halts gracefully on critical failures
5. Agent 2 uses minimal LLM prompts for cost efficiency
6. Agent 3's preprocessing is fully auditable via preprocessing_log

---

## 🎓 Educational Value

This project demonstrates:
- **Multi-Agent Architectures**: State-based orchestration with LangGraph
- **LLM Integration**: API calls with fallback patterns
- **Data Engineering**: Multi-step ETL pipeline design
- **Error Handling**: Graceful degradation and error propagation
- **Data Quality**: Comprehensive quality scoring and audit trails
- **Software Architecture**: Stateless function design and separation of concerns

---

## 📚 Future Enhancements

- Performance optimization for datasets >1GB
- Streaming data support
- Advanced anomaly detection algorithms
- ML model persistence and deployment
- Interactive dashboard for pipeline monitoring
- Distributed processing with Apache Spark