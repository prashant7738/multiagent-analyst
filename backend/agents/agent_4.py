import os
import re
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats as scipy_stats
from agents.agent_1 import GraphState
from main import update_reliability

warnings.filterwarnings("ignore")

CHARTS_DIR = "outputs/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)


def _clear_chart_dir():
    for filename in os.listdir(CHARTS_DIR):
        if not filename.lower().endswith(".png"):
            continue
        path = os.path.join(CHARTS_DIR, filename)
        if os.path.isfile(path):
            os.remove(path)

# ── palette ───────────────────────────────────────────────────────────────────
COLORS = {
    "primary":   "#2563EB",
    "secondary": "#16A34A",
    "accent":    "#DC2626",
    "warning":   "#D97706",
    "purple":    "#7C3AED",
    "bars":      ["#2563EB", "#16A34A", "#DC2626", "#D97706", "#7C3AED",
                  "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4F46E5"],
}

def _save(fig, name):
    path = os.path.join(CHARTS_DIR, f"{name}.png")
    if os.path.exists(path):
        os.remove(path)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path

# ── filter out internal validation columns ──
_VALIDATION_SUFFIXES = ("_parse_failed", "_range_failed")
_BACKUP_SUFFIXES = ("_raw", "_scaled")
ANOMALY_Z_THRESHOLD = 3.5

def _numeric_cols(df, schema_blueprint):
    """Return numeric columns, excluding validation suffixes and identifiers/datetimes."""
    cols = []
    for col in df.columns:
        if col.endswith(_VALIDATION_SUFFIXES):
            continue
        if col.endswith(_BACKUP_SUFFIXES):
            continue
        meta = schema_blueprint.get(col, {})
        if meta.get("analysis_allowed") is False:
            continue
        if meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        if pd.api.types.is_bool_dtype(df[col]):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols

def _categorical_cols(df, schema_blueprint):
    """Return categorical columns, excluding validation suffixes and identifiers/datetimes."""
    cols = []
    for col in df.columns:
        if col.endswith(_VALIDATION_SUFFIXES):
            continue
        meta = schema_blueprint.get(col, {})
        if meta.get("analysis_allowed") is False:
            continue
        if meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        if df[col].dtype == object or meta.get("semantic_tag") == "categorical_label":
            cols.append(col)
    return cols

def _find_col(df, keywords, schema_blueprint):
    """Find a column containing any keyword; restrict to valid numeric columns."""
    numeric_cols = _numeric_cols(df, schema_blueprint)
    for col in numeric_cols:
        for kw in keywords:
            if re.search(rf'\b{re.escape(kw)}\b', col.lower()):
                return col
    return None

# ─────────────────────────────────────────────────────────────────────────────
# 1 — DESCRIPTIVE STATISTICS
# ─────────────────────────────────────────────────────────────────────────────

def _descriptive_stats(df, schema_blueprint):
    result = {}
    for col in _numeric_cols(df, schema_blueprint):
        s = df[col].dropna()
        if len(s) == 0:
            continue
        result[col] = {
            "count":    int(s.count()),
            "mean":     round(float(s.mean()), 4),
            "median":   round(float(s.median()), 4),
            "std":      round(float(s.std()), 4),
            "variance": round(float(s.var()), 4),
            "min":      round(float(s.min()), 4),
            "max":      round(float(s.max()), 4),
            "q1":       round(float(s.quantile(0.25)), 4),
            "q3":       round(float(s.quantile(0.75)), 4),
            "skewness": round(float(s.skew()), 4),
            "kurtosis": round(float(s.kurt()), 4),
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2 — CORRELATION MATRIX
# ─────────────────────────────────────────────────────────────────────────────

def _correlation(df, schema_blueprint):
    cols = _numeric_cols(df, schema_blueprint)
    if len(cols) < 2:
        return {}, None

    corr_df = df[cols].dropna()
    if len(corr_df) < 3:
        return {}, None

    pearson  = corr_df.corr(method="pearson").round(4)
    spearman = corr_df.corr(method="spearman").round(4)

    strong_pairs = []
    for i, c1 in enumerate(cols):
        for c2 in cols[i+1:]:
            r = pearson.loc[c1, c2]
            if abs(r) >= 0.5:
                strong_pairs.append({
                    "col1": c1, "col2": c2,
                    "pearson_r": round(float(r), 4),
                    "direction": "positive" if r > 0 else "negative",
                    "strength":  "strong" if abs(r) >= 0.7 else "moderate",
                })

    fig, ax = plt.subplots(figsize=(max(6, len(cols)), max(5, len(cols)-1)))
    im = ax.imshow(pearson.values, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
    plt.colorbar(im, ax=ax, shrink=0.8)
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(cols, fontsize=9)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, f"{pearson.values[i,j]:.2f}",
                    ha="center", va="center", fontsize=8,
                    color="black" if abs(pearson.values[i,j]) < 0.7 else "white")
    ax.set_title("Pearson Correlation Heatmap", fontsize=13, fontweight="bold", pad=12)
    fig.tight_layout()
    path = _save(fig, "correlation_heatmap")

    return {
        "pearson":      pearson.to_dict(),
        "spearman":     spearman.to_dict(),
        "strong_pairs": strong_pairs,
    }, path


# ─────────────────────────────────────────────────────────────────────────────
# 3 — GROWTH RATES (MoM and QoQ)
# ─────────────────────────────────────────────────────────────────────────────

def _growth_rates(df, schema_blueprint):
    result = {}
    chart_paths = []

    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)
    if not rev_col or not pd.api.types.is_numeric_dtype(df[rev_col]):
        return result, chart_paths

    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    year_col  = next((c for c in df.columns if c.endswith("_year")), None)

    if month_col and year_col:
        monthly = (
            df.groupby([year_col, month_col])[rev_col]
            .sum()
            .reset_index()
            .sort_values([year_col, month_col])
        )
        monthly["mom_growth_pct"] = monthly[rev_col].pct_change() * 100
        monthly["label"] = (
            monthly[year_col].astype(str) + "-M"
            + monthly[month_col].astype(str).str.zfill(2)
        )
        result["monthly"] = monthly.dropna().to_dict(orient="records")

        if len(monthly) >= 2:
            fig, ax = plt.subplots(figsize=(max(8, len(monthly)), 4))
            ax.bar(monthly["label"], monthly[rev_col],
                   color=COLORS["primary"], alpha=0.85, label="Revenue")
            ax2 = ax.twinx()
            valid = monthly.dropna(subset=["mom_growth_pct"])
            ax2.plot(valid["label"], valid["mom_growth_pct"],
                     color=COLORS["accent"], marker="o", linewidth=2, label="MoM Growth %")
            ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
            ax.set_xlabel("Month", fontsize=10)
            ax.set_ylabel(f"{rev_col}", fontsize=10)
            ax2.set_ylabel("MoM Growth %", fontsize=10)
            ax.set_title("Monthly Revenue & MoM Growth", fontsize=13, fontweight="bold")
            plt.xticks(rotation=45, ha="right")
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1+lines2, labels1+labels2, loc="upper left", fontsize=9)
            fig.tight_layout()
            chart_paths.append(_save(fig, "monthly_revenue_growth"))

    quarter_col = next((c for c in df.columns if c.endswith("_quarter")), None)
    if quarter_col and year_col:
        quarterly = (
            df.groupby([year_col, quarter_col])[rev_col]
            .sum()
            .reset_index()
            .sort_values([year_col, quarter_col])
        )
        quarterly["qoq_growth_pct"] = quarterly[rev_col].pct_change() * 100
        quarterly["label"] = (
            quarterly[year_col].astype(str) + "-Q"
            + quarterly[quarter_col].astype(str)
        )
        result["quarterly"] = quarterly.dropna().to_dict(orient="records")

        if len(quarterly) >= 2:
            fig, ax = plt.subplots(figsize=(max(6, len(quarterly)+2), 4))
            bars = ax.bar(quarterly["label"], quarterly[rev_col],
                          color=COLORS["secondary"], alpha=0.85)
            for bar, val in zip(bars, quarterly[rev_col]):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f"{val:,.0f}", ha="center", va="bottom", fontsize=9)
            ax.set_title("Quarterly Revenue", fontsize=13, fontweight="bold")
            ax.set_ylabel(rev_col)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
            fig.tight_layout()
            chart_paths.append(_save(fig, "quarterly_revenue"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 4 — TOP / BOTTOM N RANKINGS
# ─────────────────────────────────────────────────────────────────────────────

def _top_bottom_rankings(df, schema_blueprint, n=5):
    result = {}
    chart_paths = []

    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)
    if not rev_col or not pd.api.types.is_numeric_dtype(df[rev_col]):
        return result, chart_paths

    cat_cols = _categorical_cols(df, schema_blueprint)

    for cat_col in cat_cols[:3]:
        grouped = (
            df.groupby(cat_col)[rev_col]
            .agg(["sum", "mean", "count"])
            .reset_index()
            .rename(columns={"sum": "total_revenue", "mean": "avg_revenue", "count": "records"})
            .sort_values("total_revenue", ascending=False)
        )
        grouped["revenue_share_pct"] = (
            grouped["total_revenue"] / grouped["total_revenue"].sum() * 100
        ).round(2)

        top_n    = grouped.head(n)
        bottom_n = grouped.tail(n)

        result[cat_col] = {
            "top":    top_n.to_dict(orient="records"),
            "bottom": bottom_n.to_dict(orient="records"),
            "total_categories": len(grouped),
        }

        fig, ax = plt.subplots(figsize=(8, max(3, len(top_n) * 0.6 + 1)))
        bars = ax.barh(
            top_n[cat_col].astype(str),
            top_n["total_revenue"],
            color=COLORS["bars"][:len(top_n)],
            alpha=0.88,
        )
        for bar, pct in zip(bars, top_n["revenue_share_pct"]):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height()/2,
                    f"  {pct:.1f}%", va="center", fontsize=9)
        ax.set_xlabel(f"Total {rev_col}", fontsize=10)
        ax.set_title(f"Top {n} {cat_col} by {rev_col}", fontsize=13, fontweight="bold")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.invert_yaxis()
        fig.tight_layout()
        chart_paths.append(_save(fig, f"top_{n}_{cat_col.lower()}_revenue"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 5 — SEASONALITY DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _seasonality(df, schema_blueprint):
    result = {}
    chart_paths = []

    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)
    if not rev_col or not pd.api.types.is_numeric_dtype(df[rev_col]):
        return result, chart_paths

    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    if month_col:
        monthly_avg = df.groupby(month_col)[rev_col].mean().reset_index()
        monthly_avg["month_name"] = monthly_avg[month_col].map(month_names)
        best_month  = monthly_avg.loc[monthly_avg[rev_col].idxmax()]
        worst_month = monthly_avg.loc[monthly_avg[rev_col].idxmin()]

        result["monthly"] = {
            "avg_by_month": monthly_avg.to_dict(orient="records"),
            "best_month":   {"month": best_month["month_name"],  "avg_revenue": round(float(best_month[rev_col]), 2)},
            "worst_month":  {"month": worst_month["month_name"], "avg_revenue": round(float(worst_month[rev_col]), 2)},
        }

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(monthly_avg["month_name"], monthly_avg[rev_col],
                marker="o", color=COLORS["primary"], linewidth=2.5, markersize=7)
        ax.fill_between(range(len(monthly_avg)), monthly_avg[rev_col],
                        alpha=0.1, color=COLORS["primary"])
        ax.set_xticks(range(len(monthly_avg)))
        ax.set_xticklabels(monthly_avg["month_name"])
        ax.set_title("Monthly Revenue Seasonality", fontsize=13, fontweight="bold")
        ax.set_ylabel(f"Avg {rev_col}", fontsize=10)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        chart_paths.append(_save(fig, "monthly_seasonality"))

    quarter_col = next((c for c in df.columns if c.endswith("_quarter")), None)
    if quarter_col:
        quarterly_avg = df.groupby(quarter_col)[rev_col].mean().reset_index()
        quarterly_avg["quarter_name"] = "Q" + quarterly_avg[quarter_col].astype(str)
        best_q  = quarterly_avg.loc[quarterly_avg[rev_col].idxmax()]
        worst_q = quarterly_avg.loc[quarterly_avg[rev_col].idxmin()]

        result["quarterly"] = {
            "avg_by_quarter": quarterly_avg.to_dict(orient="records"),
            "best_quarter":   {"quarter": best_q["quarter_name"],  "avg_revenue": round(float(best_q[rev_col]), 2)},
            "worst_quarter":  {"quarter": worst_q["quarter_name"], "avg_revenue": round(float(worst_q[rev_col]), 2)},
        }

        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(quarterly_avg["quarter_name"], quarterly_avg[rev_col],
                      color=COLORS["bars"][:4], alpha=0.88, width=0.5)
        for bar, val in zip(bars, quarterly_avg[rev_col]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{val:,.0f}", ha="center", va="bottom", fontsize=9)
        ax.set_title("Quarterly Revenue Seasonality", fontsize=13, fontweight="bold")
        ax.set_ylabel(f"Avg {rev_col}", fontsize=10)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        fig.tight_layout()
        chart_paths.append(_save(fig, "quarterly_seasonality"))

    dow_col = next((c for c in df.columns if c.endswith("_day_of_week")), None)
    if dow_col:
        day_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
        dow_avg = df.groupby(dow_col)[rev_col].mean().reset_index()
        dow_avg["day_name"] = dow_avg[dow_col].map(day_names)
        result["day_of_week"] = dow_avg.to_dict(orient="records")

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 6 — ANOMALY DETECTION (Z-score)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_anomalies(df, schema_blueprint, z_threshold=ANOMALY_Z_THRESHOLD):
    result = {}
    all_anomaly_indices = set()
    for col in _numeric_cols(df, schema_blueprint):
        s = df[col].dropna()
        if len(s) < 4:
            continue
        mean, std = s.mean(), s.std()
        if std == 0:
            continue
        z_scores = (df[col] - mean) / std
        anomaly_mask = z_scores.abs() > z_threshold
        anomaly_indices = df.index[anomaly_mask].tolist()
        if anomaly_indices:
            all_anomaly_indices.update(anomaly_indices)
            result[col] = {
                "count":           len(anomaly_indices),
                "z_threshold":     z_threshold,
                "anomaly_indices": anomaly_indices,
                "anomaly_values":  df.loc[anomaly_indices, col].round(4).tolist(),
                "col_mean":        round(float(mean), 4),
                "col_std":         round(float(std), 4),
            }
    summary = {
        "z_threshold": z_threshold,
        "flagged_columns": len(result),
        "total_flagged_values": int(sum(v["count"] for v in result.values())),
        "unique_flagged_rows": int(len(all_anomaly_indices)),
        "unique_flagged_row_pct": round((len(all_anomaly_indices) / max(len(df), 1)) * 100, 2),
    }
    return result, summary


# ─────────────────────────────────────────────────────────────────────────────
# 7 — CATEGORY DISTRIBUTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _category_distributions(df, schema_blueprint):
    result = {}
    chart_paths = []

    for col in _categorical_cols(df, schema_blueprint):
        counts = df[col].value_counts(dropna=False)
        pct    = (counts / len(df) * 100).round(2)
        dist   = pd.DataFrame({"count": counts, "pct": pct}).reset_index()
        dist.columns = [col, "count", "pct"]
        result[col] = dist.to_dict(orient="records")

        if len(counts) <= 15:
            fig, ax = plt.subplots(figsize=(max(6, len(counts)), 4))
            bars = ax.bar(
                counts.index.astype(str), counts.values,
                color=COLORS["bars"][:len(counts)], alpha=0.88
            )
            for bar, p in zip(bars, pct.values):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f"{p:.1f}%", ha="center", va="bottom", fontsize=9)
            ax.set_title(f"Distribution of {col}", fontsize=13, fontweight="bold")
            ax.set_ylabel("Count", fontsize=10)
            plt.xticks(rotation=30, ha="right")
            fig.tight_layout()
            chart_paths.append(_save(fig, f"dist_{col.lower()}"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 8 — LINEAR REGRESSION (time-series trend) — FINAL FIX
# ─────────────────────────────────────────────────────────────────────────────

def _regression_trends(df, schema_blueprint):
    result = {}
    chart_paths = []

    time_col = next((c for c in df.columns if c.endswith("_month")), None)
    if not time_col:
        return result, chart_paths

    # Work on a copy to avoid modifying the original
    df_work = df.copy()
    # Ensure time column is numeric (convert if possible)
    if not pd.api.types.is_numeric_dtype(df_work[time_col]):
        df_work[time_col] = pd.to_numeric(df_work[time_col], errors='coerce')

    for col in _numeric_cols(df, schema_blueprint):
        if not pd.api.types.is_numeric_dtype(df_work[col]):
            continue
        pair = df_work[[time_col, col]].dropna()
        if len(pair) < 3:
            continue
        # Convert to float64 directly to handle nullable dtypes
        x = pair[time_col].to_numpy(dtype='float64', na_value=np.nan).ravel()
        y = pair[col].to_numpy(dtype='float64', na_value=np.nan).ravel()
        if x.size < 3 or y.size < 3:
            continue
        # Drop remaining NaNs
        mask = ~(np.isnan(x) | np.isnan(y))
        x = x[mask]
        y = y[mask]
        if len(x) < 3:
            continue
        try:
            slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, y)
        except Exception:
            continue
        # Ensure scalar values (in case linregress returns arrays)
        if not np.isscalar(slope):
            if np.array(slope).size == 1:
                slope = float(slope)
            else:
                continue
        if not np.isscalar(intercept):
            if np.array(intercept).size == 1:
                intercept = float(intercept)
            else:
                continue
        if not np.isscalar(r_value):
            if np.array(r_value).size == 1:
                r_value = float(r_value)
            else:
                continue
        if not np.isscalar(p_value):
            if np.array(p_value).size == 1:
                p_value = float(p_value)
            else:
                continue
        if not np.isscalar(std_err):
            if np.array(std_err).size == 1:
                std_err = float(std_err)
            else:
                continue
        result[col] = {
            "slope":     round(float(slope), 6),
            "intercept": round(float(intercept), 4),
            "r_squared": round(float(r_value**2), 4),
            "p_value":   round(float(p_value), 4),
            "std_err":   round(float(std_err), 6),
            "trend":     "upward" if slope > 0 else "downward",
            "significant": p_value < 0.05,
        }

    # Revenue trend line chart
    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)
    if rev_col and rev_col in result and pd.api.types.is_numeric_dtype(df[rev_col]):
        pair = df[[time_col, rev_col]].dropna().sort_values(time_col)
        x = pair[time_col].values.ravel()
        y = pair[rev_col].values.ravel()
        if len(x) >= 3:
            slope = result[rev_col]["slope"]
            intercept = result[rev_col]["intercept"]
            y_pred = slope * x + intercept

            fig, ax = plt.subplots(figsize=(8, 4))
            ax.scatter(x, y, color=COLORS["primary"], s=60, zorder=5, label="Actual")
            ax.plot(x, y_pred, color=COLORS["accent"], linewidth=2,
                    linestyle="--", label=f"Trend (R²={result[rev_col]['r_squared']:.3f})")
            ax.set_xlabel(time_col, fontsize=10)
            ax.set_ylabel(rev_col, fontsize=10)
            ax.set_title(f"{rev_col} Linear Trend", fontsize=13, fontweight="bold")
            ax.legend(fontsize=9)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
            fig.tight_layout()
            chart_paths.append(_save(fig, "revenue_trend_regression"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 9 — DISTRIBUTION CHARTS (box + histogram for key numeric cols)
# ─────────────────────────────────────────────────────────────────────────────

def _distribution_charts(df, schema_blueprint):
    chart_paths = []
    num_cols = _numeric_cols(df, schema_blueprint)[:6]

    if not num_cols:
        return chart_paths

    data = [df[col].dropna().values for col in num_cols]
    fig, ax = plt.subplots(figsize=(max(8, len(num_cols)*1.5), 5))
    bp = ax.boxplot(data, patch_artist=True, notch=False)
    for patch, color in zip(bp["boxes"], COLORS["bars"]):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_xticks(range(1, len(num_cols)+1))
    ax.set_xticklabels(num_cols, rotation=30, ha="right", fontsize=9)
    ax.set_title("Numeric Columns — Box Plot", fontsize=13, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    chart_paths.append(_save(fig, "boxplot_numeric_cols"))

    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount"], schema_blueprint)
    if rev_col and pd.api.types.is_numeric_dtype(df[rev_col]):
        s = df[rev_col].dropna()
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(s, bins=min(20, len(s)), color=COLORS["primary"], alpha=0.8, edgecolor="white")
        ax.axvline(s.mean(),   color=COLORS["accent"],  linewidth=2, linestyle="--", label=f"Mean: {s.mean():,.0f}")
        ax.axvline(s.median(), color=COLORS["warning"], linewidth=2, linestyle="-",  label=f"Median: {s.median():,.0f}")
        ax.set_title(f"{rev_col} Distribution", fontsize=13, fontweight="bold")
        ax.set_xlabel(rev_col, fontsize=10)
        ax.set_ylabel("Frequency", fontsize=10)
        ax.legend(fontsize=9)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        fig.tight_layout()
        chart_paths.append(_save(fig, "revenue_histogram"))

    return chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 10 — DERIVED METRICS CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def _derived_metrics_charts(df):
    chart_paths = []

    derived_cols = [c for c in df.columns if c.startswith("derived_")
                    and pd.api.types.is_numeric_dtype(df[c])]

    if not derived_cols:
        return chart_paths

    margin_col = next((c for c in derived_cols if "margin" in c), None)
    month_col  = next((c for c in df.columns if c.endswith("_month")), None)

    if margin_col and month_col:
        monthly = df.groupby(month_col)[margin_col].mean().reset_index()
        if len(monthly) >= 2:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(monthly[month_col].astype(str), monthly[margin_col],
                    marker="o", color=COLORS["purple"], linewidth=2.5, markersize=7)
            ax.axhline(monthly[margin_col].mean(), color="gray",
                       linestyle="--", linewidth=1, label=f"Avg: {monthly[margin_col].mean():.1f}%")
            ax.set_title("Profit Margin % Over Time", fontsize=13, fontweight="bold")
            ax.set_xlabel("Month")
            ax.set_ylabel("Profit Margin %")
            ax.legend(fontsize=9)
            ax.grid(axis="y", linestyle="--", alpha=0.4)
            fig.tight_layout()
            chart_paths.append(_save(fig, "profit_margin_trend"))

    if len(derived_cols) >= 2:
        avgs = {col: df[col].mean() for col in derived_cols[:6]}
        fig, ax = plt.subplots(figsize=(max(7, len(avgs)), 4))
        bars = ax.bar(
            [c.replace("derived_", "").replace("_", " ").title() for c in avgs],
            avgs.values(),
            color=COLORS["bars"][:len(avgs)], alpha=0.88
        )
        for bar, val in zip(bars, avgs.values()):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f"{val:,.1f}", ha="center", va="bottom", fontsize=9)
        ax.set_title("Derived Business Metrics — Averages", fontsize=13, fontweight="bold")
        ax.set_ylabel("Average Value")
        plt.xticks(rotation=20, ha="right")
        fig.tight_layout()
        chart_paths.append(_save(fig, "derived_metrics_summary"))

    return chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AGENT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def agent4_analysis(state: GraphState) -> GraphState:
    errors = state.get("errors", [])
    schema_blueprint = state.get("schema_blueprint", {})
    df = state.get("cleaned_df")

    if df is None:
        errors.append("Agent4: No cleaned_df in state. Agent 3 failed.")
        return {**state, "errors": errors}

    _clear_chart_dir()

    print(f"[Agent 4] Starting analysis: {df.shape[0]} rows × {df.shape[1]} cols")

    all_chart_paths = []
    stats = {}

    stats["descriptive"] = _descriptive_stats(df, schema_blueprint)
    print(f"[Agent 4] Step 1 — Descriptive stats: {len(stats['descriptive'])} columns")

    stats["correlation"], corr_path = _correlation(df, schema_blueprint)
    if corr_path:
        all_chart_paths.append(corr_path)
    print(f"[Agent 4] Step 2 — Correlation done, strong pairs: {len(stats['correlation'].get('strong_pairs', []))}")

    stats["growth_rates"], paths = _growth_rates(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if stats["growth_rates"] or paths:
        print(f"[Agent 4] Step 3 — Growth rates done ({len(paths)} charts)")
    else:
        print("[Agent 4] Step 3 — Growth rates skipped (no revenue/time axis)")

    stats["top_bottom"], paths = _top_bottom_rankings(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if stats["top_bottom"] or paths:
        print(f"[Agent 4] Step 4 — Rankings done ({len(paths)} charts)")
    else:
        print("[Agent 4] Step 4 — Rankings skipped (no revenue/category pairing)")

    stats["seasonality"], paths = _seasonality(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if stats["seasonality"] or paths:
        print(f"[Agent 4] Step 5 — Seasonality done ({len(paths)} charts)")
    else:
        print("[Agent 4] Step 5 — Seasonality skipped (no time axis)")

    stats["anomalies"], anomaly_summary = _detect_anomalies(df, schema_blueprint)
    stats["anomaly_summary"] = anomaly_summary
    print(
        f"[Agent 4] Step 6 — Anomalies: {anomaly_summary['unique_flagged_rows']} unique rows "
        f"({anomaly_summary['unique_flagged_row_pct']}%) across {anomaly_summary['flagged_columns']} columns"
    )

    stats["distributions"], paths = _category_distributions(df, schema_blueprint)
    all_chart_paths.extend(paths)
    print(f"[Agent 4] Step 7 — Distributions done ({len(paths)} charts)")

    stats["regression"], paths = _regression_trends(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if stats["regression"] or paths:
        print(f"[Agent 4] Step 8 — Regression done ({len(stats['regression'])} columns, {len(paths)} charts)")
    else:
        print("[Agent 4] Step 8 — Regression skipped (no time axis)")

    paths = _distribution_charts(df, schema_blueprint)
    all_chart_paths.extend(paths)
    print(f"[Agent 4] Step 9 — Distribution charts done ({len(paths)} charts)")

    paths = _derived_metrics_charts(df)
    all_chart_paths.extend(paths)
    if paths:
        print(f"[Agent 4] Step 10 — Derived metrics charts done ({len(paths)} charts)")
    else:
        print("[Agent 4] Step 10 — Derived metrics skipped (no derived metrics)")

    print(f"[Agent 4] Done — {len(all_chart_paths)} charts saved to {CHARTS_DIR}/")

    state_with_reliability = update_reliability(
        state,
        "agent4",
        0.9 if stats else 0.4,
        evidence=[f"stat_sections={len(stats)}", f"charts={len(all_chart_paths)}"],
        decision_readiness="ready" if stats else "blocked",
    )

    return {
        **state_with_reliability,
        "stats":       stats,
        "chart_paths": all_chart_paths,
        "errors":      errors,
    }