# MultiAgent DataAnalyst - Project Overview

## Project Summary
**MultiAgent_DataAnalyst** is an automated, LLM-powered data analysis pipeline that processes CSV files through a sequence of specialized agents. It performs structural profiling, semantic tagging, data preprocessing, statistical analysis, and visualization generation.

---

## Architecture Overview

### Technology Stack
- **LLM**: Groq API (llama-3.3-70b-versatile)
- **Orchestration**: LangGraph (state-based DAG pipeline)
- **Data**: Pandas, NumPy, SciPy
- **Visualization**: Matplotlib
- **Framework**: Python 3.12+

### Core Components

#### 1. **GraphState** (Shared State Container)
Located in [main.py](backend/main.py), defines the schema for data flowing between agents:
- **Inputs**: `csv_path`
- **Agent Outputs**: 
  - Agent 1: `raw_profile`, `_df_cache`
  - Agent 2: `schema_blueprint`
  - Agent 3: `cleaned_df`, `scaling_params`, `preprocessing_log`, `data_quality`
  - Agent 4: `stats`, `chart_paths`
  - Agents 5-6: Placeholder fields for future expansion
- **Shared**: `errors` (error collection throughout pipeline)

#### 2. **Pipeline Architecture** ([pipeline.py](backend/pipeline.py))
Conditional DAG with error-aware routing:
- Sequential flow: Agent1 → Agent2 → Agent3 → Agent4 → END
- Conditional edges with error checks at each stage
- Graceful failure mode: Pipeline stops if any agent errors occur
- Uses `langgraph.StateGraph` for composability

---

## Agent Details

### **Agent 1: Structural Profiler** ([agent_1.py](backend/agents/agent_1.py))
**Purpose**: Read and analyze raw CSV structure  
**Process**:
1. Load CSV with low memory mode
2. Profile each column:
   - Data type (Pandas dtype)
   - Missing value count & percentage
   - Unique value count
   - Sample values (first 3)
3. Calculate dataset-level stats:
   - Shape (rows × cols)
   - Total cells & missing rate
   - Duplicate rows & rate

**Output**: `raw_profile` dict + `_df_cache` (cached DataFrame for downstream agents)  
**Error Handling**: CSV load failures caught and logged

---

### **Agent 2: Semantic Tagger** ([agent_2.py](backend/agents/agent_2.py))
**Purpose**: Infer data types and semantic meaning of columns  
**Process**:
1. **Type Sniffing** (pure Python, no LLM):
   - Numeric: int/float dtypes or coercible strings (80%+ parseable)
   - DateTime: Strings matching datetime patterns (80%+ parseable)
   - Boolean: Bool dtype
   - String: Everything else
   - Fallback: "unknown"

2. **Semantic Tagging** (LLM-powered via Groq):
   - System prompt defines schema rules for:
     - Currency (scaling=false, imputation=median)
     - Identifiers (imputation=drop)
     - DateTime (scaling=false, imputation=none)
     - Categorical labels (<20 unique values)
   - Input: Column metadata + 3 sample values (minimal prompt)
   - Output: Schema blueprint with per-column metadata

3. **Fallback**: If LLM fails, uses basic heuristics

**Output**: `schema_blueprint` (dict with column metadata + processing rules)  
**Error Handling**: JSON parsing errors + LLM API failures use fallback logic

---

### **Agent 3: Preprocessor** ([agent_3.py](backend/agents/agent_3.py))
**Purpose**: Clean and transform data according to schema blueprint  
**10-Step Pipeline**:

1. **Type Coercion**: Convert columns to intended types (float/int/datetime/boolean)
   - Tracks NaN creation during coercion
   - Conditional int conversion (only if no NaNs remain)

2. **Currency Cleaning**: 
   - Remove symbols (₹, $, €, £, ¥, ₩)
   - Handle parenthetical negatives: `(123)` → `-123`
   - Convert European format: `1.234,56` → `1234.56`
   - Parse to numeric

3. **Text Standardization**:
   - Strip whitespace
   - Title case
   - Replace null strings: "nan", "none", "n/a", "#n/a", etc. → NaN
   - Preserve identifiers (no standardization if `is_identifier=true`)

4. **Duplicate Removal**: Drop exact row duplicates

5. **Imputation**:
   - **mean/median**: For numeric columns
   - **mode**: For categorical
   - **unknown_label**: Fill with "Unknown"
   - **drop**: Remove rows with missing identifiers
   - **none**: Leave NaNs as-is

6. **Outlier Clipping**: IQR-based clipping (only if `scaling_allowed=true`)
   - Bounds: Q1 - 1.5×IQR to Q3 + 1.5×IQR
   - Counts clipped values

7. **Scaling**: Min-Max normalization (0-1) for scaling-allowed columns
   - Saves scaling parameters for inverse-transform

8. **Date Feature Extraction**: For datetime columns, derive:
   - year, month, quarter, day, day_of_week, is_weekend, week_of_year

9. **Business Metrics Derivation**: Intelligent column pairing:
   - Profit = Revenue - Cost
   - Profit Margin % = (Profit / Revenue) × 100
   - Revenue per Unit = Revenue / Units
   - Total Revenue = Price × Units (if no revenue column)
   - Revenue after Discount, Discount %
   - Budget Variance & %
   - Total Cost = Cost + Tax + Shipping (or subset)

10. **Quality Scoring**:
    - Overall score: (Completeness - Duplicate Penalty) × 100
    - Completeness = 1 - (Missing Cells / Total Cells)
    - Duplicate Penalty = Duplicate Rows / Total Rows

**Output**: 
- `cleaned_df`: Fully preprocessed DataFrame
- `scaling_params`: {col: {min, max}} for denormalization
- `preprocessing_log`: Audit trail of all actions
- `data_quality`: Quality metrics
- `data_quality.overall_quality_score`: 0-100 score

**Error Handling**: Skips missing columns, catches exceptions per step

---

### **Agent 4: Statistical Analysis** ([agent_4.py](backend/agents/agent_4.py) - Partial)
**Purpose**: Generate descriptive statistics, correlations, anomalies, and visualizations  
**Planned Features**:
- Descriptive stats (mean, median, std, quantiles)
- Correlation analysis (Pearson, identify strong pairs)
- Anomaly detection (statistical outliers)
- Regression modeling
- Chart generation (saved to `outputs/charts/`)

**Output**: 
- `stats`: Comprehensive statistical summary
- `chart_paths`: List of generated chart file paths

---

### **Agents 5-6** (Future)
- **Agent 5**: Data validation & constraint checking
- **Agent 6**: Final report generation

---

## Data Flow

```
CSV File (sample_sales.csv)
    ↓
[Agent 1] Structural Profiler
    → raw_profile, _df_cache
    ↓
[Agent 2] Semantic Tagger (LLM)
    → schema_blueprint
    ↓
[Agent 3] Preprocessor
    → cleaned_df, scaling_params, preprocessing_log, data_quality
    ↓
[Agent 4] Statistical Analysis
    → stats, chart_paths
    ↓
Output (JSON + Charts)
```

---

## Key Design Patterns

### 1. **Stateless Agent Functions**
- Each agent is a pure function: `state → state`
- All data passed via GraphState
- No side effects except logging and file writing

### 2. **Error Propagation**
- All agents check for upstream errors
- Errors accumulated in `state["errors"]`
- Pipeline halts on critical failures

### 3. **Semantic-Driven Processing**
- Agent 2's schema blueprint drives Agent 3's decisions
- Scaling, imputation, feature extraction all conditional on metadata
- Extensible metadata model (can add new tags/rules)

### 4. **Audit Trail**
- Agent 3 generates `preprocessing_log` for reproducibility
- Every transformation recorded with parameters
- Data quality score provides overview of transformation impact

### 5. **LLM Fallback**
- Agent 2 uses LLM for semantic tagging
- Falls back to pure Python heuristics on failure
- Pipeline continues even if LLM unavailable

---

## File Structure

```
backend/
├── main.py                    # GraphState definition
├── pipeline.py                # DAG construction & entry point
├── sample_sales.csv           # Test dataset
├── pyproject.toml             # Dependencies (groq, langchain, langgraph, pandas)
├── agents/
│   ├── agent_1.py            # Structural profiler
│   ├── agent_2.py            # Semantic tagger (LLM)
│   ├── agent_3.py            # Preprocessor (10-step pipeline)
│   └── agent_4.py            # Statistical analysis
└── outputs/
    └── charts/               # Generated PNG visualizations

README.md                       # Project root (currently minimal)
skills-lock.json               # Dependency lock file
```

---

## Current State

### ✅ Implemented
- Agent 1: Fully functional structural profiling
- Agent 2: Type sniffing + Groq-powered semantic tagging with fallback
- Agent 3: Complete 10-step preprocessing pipeline with audit trail
- Agent 4: Partial (core analysis logic, chart generation TBD)
- Pipeline orchestration with conditional routing

### 🚧 In Progress / Planned
- Agent 4: Full statistics, correlation, anomaly detection, regression
- Agent 5: Validation & constraint checking
- Agent 6: Report generation
- Frontend/UI for pipeline visualization
- Support for multiple file formats (Excel, JSON, etc.)

### 💡 Notable Features
- **Intelligent Business Metrics**: Auto-derives profit, margins, revenue per unit
- **Quality Scoring**: 0-100 score reflecting data quality pre/post-processing
- **Scaling Parameter Tracking**: Saves min/max for inverse-transform
- **Minimal LLM Prompts**: Reduces API costs by sending only metadata + 3 samples
- **Whole-Word Keyword Matching**: Prevents false column matches ("count" won't match "Country")
- **Currency Cleaning**: Handles international symbols and formats
- **Null String Normalization**: Converts 14+ variants to NaN

---

## Usage

```bash
cd backend
python pipeline.py
```

**Output**:
- Descriptive statistics (JSON)
- Correlation pairs
- Anomalies
- Regression results
- Generated charts (PNG)

---

## Dependencies

- `groq>=1.5.0` - LLM API client
- `langchain-core>=1.4.8` - Core LangChain utilities
- `langgraph>=1.2.6` - State graph orchestration
- `pandas>=3.0.3` - Data manipulation
- `numpy` - Numerical operations
- `scipy` - Statistical functions
- `matplotlib` - Visualization

---

## Notes for Future Development

1. **Agent 4 Completion**: Implement correlation analysis, anomaly detection, regression
2. **Agents 5-6**: Add validation layer and report generation
3. **Configuration**: Move hardcoded paths/thresholds to config file
4. **Logging**: Add structured logging (current: print statements)
5. **Testing**: Add unit tests for each agent function
6. **Performance**: Profile memory usage for large CSVs (consider chunking)
7. **Extensibility**: Allow custom preprocessing rules via config
