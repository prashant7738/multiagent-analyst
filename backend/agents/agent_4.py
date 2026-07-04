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

warnings.filterwarnings("ignore")

CHARTS_DIR = "outputs/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

COLORS = {
    "primary":   "#2563EB",
    "secondary": "#16A34A",
    "accent":    "#DC2626",
    "warning":   "#D97706",
    "purple":    "#7C3AED",
    "bars":      ["#2563EB","#16A34A","#DC2626","#D97706","#7C3AED",
                  "#0891B2","#DB2777","#65A30D","#EA580C","#4F46E5"],
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _save(fig, name):
    path = os.path.join(CHARTS_DIR, f"{name}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _find_col(df, keywords):
    for col in df.columns:
        for kw in keywords:
            if re.search(rf'\b{re.escape(kw)}\b', col.lower()):
                return col
    return None


def _to_serializable(obj):
    """Recursively convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_serializable(i) for i in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


def _numeric_cols(df, schema_blueprint):
    """Return numeric columns that are meaningful for analysis — skip IDs, dates, derived date parts."""
    skip_suffixes = ("_year","_month","_quarter","_day","_day_of_week","_is_weekend","_week_of_year")
    cols = []
    for col in df.columns:
        if col.startswith("derived_"):
            continue
        if any(col.endswith(s) for s in skip_suffixes):
            continue
        meta = schema_blueprint.get(col, {})
        if meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


def _categorical_cols(df, schema_blueprint):
    """Return categorical columns suitable for grouping."""
    cols = []
    for col in df.columns:
        if col.startswith("derived_"):
            continue
        meta = schema_blueprint.get(col, {})
        if meta.get("is_identifier"):
            continue
        if meta.get("semantic_tag") in ("datetime", "identifier"):
            continue
        if df[col].dtype == object or meta.get("semantic_tag") in ("categorical_label", "geographic"):
            if df[col].nunique() <= 30:
                cols.append(col)
    return cols


def _has_time_series(df):
    """True if dataset has date-extracted columns with enough periods."""
    month_col = next((c for c in df.columns if c.endswith("_month")), None)
    if month_col and df[month_col].nunique() >= 2:
        return True
    return False


def _has_revenue(df):
    """True if a revenue-like numeric column exists."""
    col = _find_col(df, ["revenue", "sales", "income", "total_amount", "net_sales"])
    return col is not None and pd.api.types.is_numeric_dtype(df[col])


def _has_categories(df, schema_blueprint):
    """True if usable categorical columns exist."""
    return len(_categorical_cols(df, schema_blueprint)) > 0


def _has_derived(df):
    """True if Agent 3 computed derived business metrics."""
    return any(c.startswith("derived_") and pd.api.types.is_numeric_dtype(df[c])
               for c in df.columns)


# ─────────────────────────────────────────────────────────────────────────────
# 1 — DESCRIPTIVE STATISTICS (always runs)
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
# 2 — CORRELATION (only if 2+ numeric cols with enough rows)
# ─────────────────────────────────────────────────────────────────────────────

def _correlation(df, schema_blueprint):
    cols = _numeric_cols(df, schema_blueprint)
    if len(cols) < 2:
        return {}, None

    corr_df = df[cols].dropna()
    if len(corr_df) < 4:
        return {}, None

    pearson  = corr_df.corr(method="pearson").round(4)
    spearman = corr_df.corr(method="spearman").round(4)

    strong_pairs = []
    for i, c1 in enumerate(cols):
        for c2 in cols[i+1:]:
            r = float(pearson.loc[c1, c2])
            if abs(r) >= 0.5:
                strong_pairs.append({
                    "col1":      c1,
                    "col2":      c2,
                    "pearson_r": round(r, 4),
                    "direction": "positive" if r > 0 else "negative",
                    "strength":  "strong" if abs(r) >= 0.7 else "moderate",
                })

    # Only draw heatmap if meaningful correlation exists
    path = None
    if strong_pairs:
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
# 3 — GROWTH RATES (only if time series + revenue exist)
# ─────────────────────────────────────────────────────────────────────────────

def _growth_rates(df, schema_blueprint):
    result = {}
    chart_paths = []

    if not _has_time_series(df) or not _has_revenue(df):
        return result, chart_paths

    rev_col     = _find_col(df, ["revenue", "sales", "income", "total_amount"])
    month_col   = next((c for c in df.columns if c.endswith("_month")), None)
    year_col    = next((c for c in df.columns if c.endswith("_year")), None)
    quarter_col = next((c for c in df.columns if c.endswith("_quarter")), None)

    # MoM — needs at least 2 distinct months
    if month_col and year_col:
        monthly = (
            df.groupby([year_col, month_col])[rev_col]
            .sum().reset_index()
            .sort_values([year_col, month_col])
        )
        if len(monthly) >= 2:
            monthly["mom_growth_pct"] = monthly[rev_col].pct_change() * 100
            monthly["label"] = (monthly[year_col].astype(str) + "-M"
                                + monthly[month_col].astype(str).str.zfill(2))
            result["monthly"] = monthly.dropna().to_dict(orient="records")

            fig, ax = plt.subplots(figsize=(max(8, len(monthly)), 4))
            ax.bar(monthly["label"], monthly[rev_col],
                   color=COLORS["primary"], alpha=0.85, label="Revenue")
            ax2 = ax.twinx()
            valid = monthly.dropna(subset=["mom_growth_pct"])
            ax2.plot(valid["label"], valid["mom_growth_pct"],
                     color=COLORS["accent"], marker="o", linewidth=2, label="MoM Growth %")
            ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
            ax.set_xlabel("Month")
            ax.set_ylabel(rev_col)
            ax2.set_ylabel("MoM Growth %")
            ax.set_title("Monthly Revenue & MoM Growth", fontsize=13, fontweight="bold")
            plt.xticks(rotation=45, ha="right")
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1+lines2, labels1+labels2, loc="upper left", fontsize=9)
            fig.tight_layout()
            chart_paths.append(_save(fig, "monthly_revenue_growth"))

    # QoQ — needs at least 2 distinct quarters
    if quarter_col and year_col:
        quarterly = (
            df.groupby([year_col, quarter_col])[rev_col]
            .sum().reset_index()
            .sort_values([year_col, quarter_col])
        )
        if len(quarterly) >= 2:
            quarterly["qoq_growth_pct"] = quarterly[rev_col].pct_change() * 100
            quarterly["label"] = (quarterly[year_col].astype(str) + "-Q"
                                  + quarterly[quarter_col].astype(str))
            result["quarterly"] = quarterly.dropna().to_dict(orient="records")

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
# 4 — TOP/BOTTOM RANKINGS (only if revenue + categorical cols exist)
# ─────────────────────────────────────────────────────────────────────────────

def _top_bottom_rankings(df, schema_blueprint, n=5):
    result = {}
    chart_paths = []

    if not _has_revenue(df) or not _has_categories(df, schema_blueprint):
        return result, chart_paths

    rev_col  = _find_col(df, ["revenue", "sales", "income", "total_amount"])
    cat_cols = _categorical_cols(df, schema_blueprint)

    for cat_col in cat_cols[:3]:
        grouped = (
            df.groupby(cat_col)[rev_col]
            .agg(["sum","mean","count"]).reset_index()
            .rename(columns={"sum":"total_revenue","mean":"avg_revenue","count":"records"})
            .sort_values("total_revenue", ascending=False)
        )

        # Only draw chart if there are at least 2 categories
        if len(grouped) < 2:
            continue

        grouped["revenue_share_pct"] = (
            grouped["total_revenue"] / grouped["total_revenue"].sum() * 100
        ).round(2)

        top_n = grouped.head(min(n, len(grouped)))
        result[cat_col] = {
            "top":              top_n.to_dict(orient="records"),
            "bottom":           grouped.tail(min(n, len(grouped))).to_dict(orient="records"),
            "total_categories": int(len(grouped)),
        }

        fig, ax = plt.subplots(figsize=(8, max(3, len(top_n)*0.6+1)))
        bars = ax.barh(top_n[cat_col].astype(str), top_n["total_revenue"],
                       color=COLORS["bars"][:len(top_n)], alpha=0.88)
        for bar, pct in zip(bars, top_n["revenue_share_pct"]):
            ax.text(bar.get_width(), bar.get_y()+bar.get_height()/2,
                    f"  {pct:.1f}%", va="center", fontsize=9)
        ax.set_xlabel(f"Total {rev_col}")
        ax.set_title(f"Top {len(top_n)} {cat_col} by {rev_col}", fontsize=13, fontweight="bold")
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.invert_yaxis()
        fig.tight_layout()
        chart_paths.append(_save(fig, f"top_{cat_col.lower()}_revenue"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 5 — SEASONALITY (only if time series + revenue + enough periods)
# ─────────────────────────────────────────────────────────────────────────────

def _seasonality(df, schema_blueprint):
    result = {}
    chart_paths = []

    if not _has_time_series(df) or not _has_revenue(df):
        return result, chart_paths

    rev_col     = _find_col(df, ["revenue", "sales", "income", "total_amount"])
    month_col   = next((c for c in df.columns if c.endswith("_month")), None)
    quarter_col = next((c for c in df.columns if c.endswith("_quarter")), None)
    dow_col     = next((c for c in df.columns if c.endswith("_day_of_week")), None)

    month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}

    # Monthly — only if 3+ distinct months
    if month_col and df[month_col].nunique() >= 3:
        monthly_avg = df.groupby(month_col)[rev_col].mean().reset_index()
        monthly_avg["month_name"] = monthly_avg[month_col].map(month_names)
        best  = monthly_avg.loc[monthly_avg[rev_col].idxmax()]
        worst = monthly_avg.loc[monthly_avg[rev_col].idxmin()]
        result["monthly"] = {
            "avg_by_month": monthly_avg.to_dict(orient="records"),
            "best_month":   {"month": best["month_name"],  "avg_revenue": round(float(best[rev_col]), 2)},
            "worst_month":  {"month": worst["month_name"], "avg_revenue": round(float(worst[rev_col]), 2)},
        }
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(monthly_avg["month_name"], monthly_avg[rev_col],
                marker="o", color=COLORS["primary"], linewidth=2.5, markersize=7)
        ax.fill_between(range(len(monthly_avg)), monthly_avg[rev_col],
                        alpha=0.1, color=COLORS["primary"])
        ax.set_xticks(range(len(monthly_avg)))
        ax.set_xticklabels(monthly_avg["month_name"])
        ax.set_title("Monthly Revenue Seasonality", fontsize=13, fontweight="bold")
        ax.set_ylabel(f"Avg {rev_col}")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.grid(axis="y", linestyle="--", alpha=0.5)
        fig.tight_layout()
        chart_paths.append(_save(fig, "monthly_seasonality"))

    # Quarterly — only if 2+ distinct quarters
    if quarter_col and df[quarter_col].nunique() >= 2:
        quarterly_avg = df.groupby(quarter_col)[rev_col].mean().reset_index()
        quarterly_avg["quarter_name"] = "Q" + quarterly_avg[quarter_col].astype(str)
        best  = quarterly_avg.loc[quarterly_avg[rev_col].idxmax()]
        worst = quarterly_avg.loc[quarterly_avg[rev_col].idxmin()]
        result["quarterly"] = {
            "avg_by_quarter": quarterly_avg.to_dict(orient="records"),
            "best_quarter":   {"quarter": best["quarter_name"],  "avg_revenue": round(float(best[rev_col]), 2)},
            "worst_quarter":  {"quarter": worst["quarter_name"], "avg_revenue": round(float(worst[rev_col]), 2)},
        }
        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(quarterly_avg["quarter_name"], quarterly_avg[rev_col],
                      color=COLORS["bars"][:4], alpha=0.88, width=0.5)
        for bar, val in zip(bars, quarterly_avg[rev_col]):
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(),
                    f"{val:,.0f}", ha="center", va="bottom", fontsize=9)
        ax.set_title("Quarterly Revenue Seasonality", fontsize=13, fontweight="bold")
        ax.set_ylabel(f"Avg {rev_col}")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        fig.tight_layout()
        chart_paths.append(_save(fig, "quarterly_seasonality"))

    # Day of week — only if 3+ distinct days
    if dow_col and df[dow_col].nunique() >= 3:
        day_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
        dow_avg = df.groupby(dow_col)[rev_col].mean().reset_index()
        dow_avg["day_name"] = dow_avg[dow_col].map(day_names)
        result["day_of_week"] = dow_avg.to_dict(orient="records")

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(dow_avg["day_name"], dow_avg[rev_col],
               color=COLORS["bars"][:len(dow_avg)], alpha=0.88)
        ax.set_title("Revenue by Day of Week", fontsize=13, fontweight="bold")
        ax.set_ylabel(f"Avg {rev_col}")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        fig.tight_layout()
        chart_paths.append(_save(fig, "day_of_week_revenue"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 6 — ANOMALY DETECTION (only if enough rows)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_anomalies(df, schema_blueprint, z_threshold=2.5):
    result = {}
    if len(df) < 10:
        return result  # too few rows for meaningful anomaly detection

    for col in _numeric_cols(df, schema_blueprint):
        s = df[col].dropna()
        if len(s) < 10:
            continue
        mean, std = float(s.mean()), float(s.std())
        if std == 0:
            continue
        z_scores = (df[col] - mean) / std
        anomaly_mask = z_scores.abs() > z_threshold
        anomaly_indices = df.index[anomaly_mask].tolist()
        if anomaly_indices:
            result[col] = {
                "count":           int(len(anomaly_indices)),
                "z_threshold":     z_threshold,
                "anomaly_indices": [int(i) for i in anomaly_indices],
                "anomaly_values":  [round(float(v), 4) for v in df.loc[anomaly_indices, col]],
                "col_mean":        round(mean, 4),
                "col_std":         round(std, 4),
            }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 7 — CATEGORY DISTRIBUTIONS (only if categorical cols exist)
# ─────────────────────────────────────────────────────────────────────────────

def _category_distributions(df, schema_blueprint):
    result = {}
    chart_paths = []

    if not _has_categories(df, schema_blueprint):
        return result, chart_paths

    for col in _categorical_cols(df, schema_blueprint):
        counts = df[col].value_counts(dropna=False)
        if len(counts) < 2:
            continue
        pct  = (counts / len(df) * 100).round(2)
        dist = pd.DataFrame({"count": counts, "pct": pct}).reset_index()
        dist.columns = [col, "count", "pct"]
        result[col] = dist.to_dict(orient="records")

        if len(counts) <= 15:
            fig, ax = plt.subplots(figsize=(max(6, len(counts)), 4))
            bars = ax.bar(counts.index.astype(str), counts.values,
                          color=COLORS["bars"][:len(counts)], alpha=0.88)
            for bar, p in zip(bars, pct.values):
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(),
                        f"{p:.1f}%", ha="center", va="bottom", fontsize=9)
            ax.set_title(f"Distribution of {col}", fontsize=13, fontweight="bold")
            ax.set_ylabel("Count")
            plt.xticks(rotation=30, ha="right")
            fig.tight_layout()
            chart_paths.append(_save(fig, f"dist_{col.lower()}"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 8 — REGRESSION (only if time series exists and enough rows)
# ─────────────────────────────────────────────────────────────────────────────

def _regression_trends(df, schema_blueprint):
    result = {}
    chart_paths = []

    time_col = next((c for c in df.columns if c.endswith("_month")), None)
    if not time_col or len(df) < 4:
        return result, chart_paths

    for col in _numeric_cols(df, schema_blueprint):
        pair = df[[time_col, col]].dropna()
        if len(pair) < 4:
            continue
        x = pair[time_col].values
        y = pair[col].values
        slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, y)
        result[col] = {
            "slope":       round(float(slope), 6),
            "intercept":   round(float(intercept), 4),
            "r_squared":   round(float(r_value**2), 4),
            "p_value":     round(float(p_value), 4),
            "std_err":     round(float(std_err), 6),
            "trend":       "upward" if slope > 0 else "downward",
            "significant": bool(p_value < 0.05),  # native bool, not numpy bool
        }

    # Trend line chart — only for revenue if R² is meaningful
    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount"])
    if (rev_col and rev_col in result
            and result[rev_col]["r_squared"] >= 0.3
            and pd.api.types.is_numeric_dtype(df[rev_col])):
        pair = df[[time_col, rev_col]].dropna().sort_values(time_col)
        x = pair[time_col].values
        y = pair[rev_col].values
        slope    = result[rev_col]["slope"]
        intercept= result[rev_col]["intercept"]
        y_pred   = slope * x + intercept

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.scatter(x, y, color=COLORS["primary"], s=60, zorder=5, label="Actual")
        ax.plot(x, y_pred, color=COLORS["accent"], linewidth=2,
                linestyle="--", label=f"Trend (R²={result[rev_col]['r_squared']:.3f})")
        ax.set_xlabel(time_col)
        ax.set_ylabel(rev_col)
        ax.set_title(f"{rev_col} Linear Trend", fontsize=13, fontweight="bold")
        ax.legend(fontsize=9)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        fig.tight_layout()
        chart_paths.append(_save(fig, "revenue_trend_regression"))

    return result, chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 9 — DISTRIBUTION CHARTS (only if 2+ numeric cols and enough rows)
# ─────────────────────────────────────────────────────────────────────────────

def _distribution_charts(df, schema_blueprint):
    chart_paths = []
    num_cols = _numeric_cols(df, schema_blueprint)

    # Box plot — only if 2+ columns and 5+ rows
    if len(num_cols) >= 2 and len(df) >= 5:
        data = [df[col].dropna().values for col in num_cols]
        fig, ax = plt.subplots(figsize=(max(8, len(num_cols)*1.5), 5))
        bp = ax.boxplot(data, patch_artist=True)
        for patch, color in zip(bp["boxes"], COLORS["bars"]):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        ax.set_xticks(range(1, len(num_cols)+1))
        ax.set_xticklabels(num_cols, rotation=30, ha="right", fontsize=9)
        ax.set_title("Numeric Columns — Box Plot", fontsize=13, fontweight="bold")
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        fig.tight_layout()
        chart_paths.append(_save(fig, "boxplot_numeric_cols"))

    # Histogram — only for revenue if 10+ rows
    rev_col = _find_col(df, ["revenue", "sales", "income", "total_amount"])
    if rev_col and pd.api.types.is_numeric_dtype(df[rev_col]) and len(df) >= 10:
        s = df[rev_col].dropna()
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(s, bins=min(20, len(s)), color=COLORS["primary"], alpha=0.8, edgecolor="white")
        ax.axvline(s.mean(),   color=COLORS["accent"],  linewidth=2,
                   linestyle="--", label=f"Mean: {s.mean():,.0f}")
        ax.axvline(s.median(), color=COLORS["warning"], linewidth=2,
                   linestyle="-",  label=f"Median: {s.median():,.0f}")
        ax.set_title(f"{rev_col} Distribution", fontsize=13, fontweight="bold")
        ax.set_xlabel(rev_col)
        ax.set_ylabel("Frequency")
        ax.legend(fontsize=9)
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        fig.tight_layout()
        chart_paths.append(_save(fig, "revenue_histogram"))

    return chart_paths


# ─────────────────────────────────────────────────────────────────────────────
# 10 — DERIVED METRICS CHARTS (only if derived cols exist)
# ─────────────────────────────────────────────────────────────────────────────

def _derived_metrics_charts(df):
    chart_paths = []

    if not _has_derived(df):
        return chart_paths

    derived_cols = [c for c in df.columns if c.startswith("derived_")
                    and pd.api.types.is_numeric_dtype(df[c])]

    month_col  = next((c for c in df.columns if c.endswith("_month")), None)
    margin_col = next((c for c in derived_cols if "margin" in c), None)

    # Profit margin trend — only if time series + enough months
    if margin_col and month_col and df[month_col].nunique() >= 2:
        monthly = df.groupby(month_col)[margin_col].mean().reset_index()
        if len(monthly) >= 2:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(monthly[month_col].astype(str), monthly[margin_col],
                    marker="o", color=COLORS["purple"], linewidth=2.5, markersize=7)
            ax.axhline(float(monthly[margin_col].mean()), color="gray",
                       linestyle="--", linewidth=1,
                       label=f"Avg: {float(monthly[margin_col].mean()):.1f}%")
            ax.set_title("Profit Margin % Over Time", fontsize=13, fontweight="bold")
            ax.set_xlabel("Month")
            ax.set_ylabel("Profit Margin %")
            ax.legend(fontsize=9)
            ax.grid(axis="y", linestyle="--", alpha=0.4)
            fig.tight_layout()
            chart_paths.append(_save(fig, "profit_margin_trend"))

    # Summary bar of derived metric averages — only if 2+ derived cols
    if len(derived_cols) >= 2:
        avgs  = {col: float(df[col].mean()) for col in derived_cols[:6]}
        labels = [c.replace("derived_","").replace("_"," ").title() for c in avgs]
        fig, ax = plt.subplots(figsize=(max(7, len(avgs)), 4))
        bars = ax.bar(labels, avgs.values(), color=COLORS["bars"][:len(avgs)], alpha=0.88)
        for bar, val in zip(bars, avgs.values()):
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height(),
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
    verbose = os.getenv("PIPELINE_VERBOSE", "0").strip().lower() in {"1", "true", "yes", "on"}

    if df is None:
        errors.append("Agent4: No cleaned_df in state. Agent 3 failed.")
        return {**state, "errors": errors}

    print(f"[Agent 4] Analysis: input={df.shape[0]}x{df.shape[1]}")
    if verbose:
        print(f"[Agent 4] Dataset has: revenue={_has_revenue(df)}, "
              f"time_series={_has_time_series(df)}, "
              f"categories={_has_categories(df, schema_blueprint)}, "
              f"derived={_has_derived(df)}")

    all_chart_paths = []
    stats = {}

    stats["descriptive"] = _descriptive_stats(df, schema_blueprint)
    if verbose:
        print(f"[Agent 4] Step 1 - Descriptive stats: {len(stats['descriptive'])} columns")

    stats["correlation"], corr_path = _correlation(df, schema_blueprint)
    if corr_path:
        all_chart_paths.append(corr_path)
    if verbose:
        print(f"[Agent 4] Step 2 - Correlation: {len(stats['correlation'].get('strong_pairs', []))} strong pairs")

    stats["growth_rates"], paths = _growth_rates(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if verbose:
        print(f"[Agent 4] Step 3 - Growth rates: {len(paths)} charts")

    stats["top_bottom"], paths = _top_bottom_rankings(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if verbose:
        print(f"[Agent 4] Step 4 - Rankings: {len(paths)} charts")

    stats["seasonality"], paths = _seasonality(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if verbose:
        print(f"[Agent 4] Step 5 - Seasonality: {len(paths)} charts")

    stats["anomalies"] = _detect_anomalies(df, schema_blueprint)
    if verbose:
        print(f"[Agent 4] Step 6 - Anomalies: {len(stats['anomalies'])} columns flagged")

    stats["distributions"], paths = _category_distributions(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if verbose:
        print(f"[Agent 4] Step 7 - Distributions: {len(paths)} charts")

    stats["regression"], paths = _regression_trends(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if verbose:
        print(f"[Agent 4] Step 8 - Regression: {len(stats['regression'])} columns, {len(paths)} charts")

    paths = _distribution_charts(df, schema_blueprint)
    all_chart_paths.extend(paths)
    if verbose:
        print(f"[Agent 4] Step 9 - Distribution charts: {len(paths)} charts")

    paths = _derived_metrics_charts(df)
    all_chart_paths.extend(paths)
    if verbose:
        print(f"[Agent 4] Step 10 - Derived metrics charts: {len(paths)} charts")

    print(
        f"[Agent 4] Completed: descriptive={len(stats['descriptive'])} "
        f"strong_corr={len(stats['correlation'].get('strong_pairs', []))} "
        f"anomaly_cols={len(stats['anomalies'])} "
        f"regression_models={len(stats['regression'])} "
        f"charts={len(all_chart_paths)}"
    )

    return {
        **state,
        "stats":       _to_serializable(stats),
        "chart_paths": all_chart_paths,
        "errors":      errors,
    }