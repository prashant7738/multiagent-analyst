"""Shared presentation layer for charts and the insight report.

One source of truth for colors and number formatting so the matplotlib PNGs,
the interactive ECharts options, and the report prose all agree:

  * PALETTE / CHART_COLORS  -> consumed by chart_render_static + template JS
  * humanize_* helpers      -> "₹1.2M", "45.0%", "3 out of 10" style output
  * column_label()          -> honest, human titles derived from column names

These are also registered as Jinja filters in agent_6's render environment.
"""

from __future__ import annotations

import hashlib
import re

PALETTE = {
    "primary":   "#2563EB",
    "secondary": "#16A34A",
    "accent":    "#DC2626",
    "warning":   "#D97706",
    "purple":    "#7C3AED",
}
# Categorical series colors (same order/feel as the legacy agent_4 palette).
CHART_COLORS = [
    "#2563EB", "#16A34A", "#DC2626", "#D97706", "#7C3AED",
    "#0891B2", "#DB2777", "#65A30D", "#EA580C", "#4F46E5",
]
SEVERITY = {"good": "#16a34a", "warn": "#d97706", "bad": "#dc2626"}


def humanize_number(value, decimals: int | None = None) -> str:
    """1234567.0 -> '1.23M', 4200 -> '4.2K', 42 -> '42'. None-safe."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math_is_nan(num):
        return "—"
    sign = "-" if num < 0 else ""
    num = abs(num)
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if num >= divisor:
            scaled = num / divisor
            text = f"{scaled:.2f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    if decimals is not None:
        return f"{sign}{num:,.{decimals}f}"
    if float(num).is_integer():
        return f"{sign}{int(num):,}"
    text = f"{num:.2f}".rstrip("0").rstrip(".")
    return f"{sign}{text}"


def humanize_currency(value, symbol: str = "") -> str:
    """Humanized currency amount; symbol prepended when known (e.g. ₹/$)."""
    body = humanize_number(value)
    if body == "—":
        return body
    return f"{symbol}{body}" if symbol else body


def humanize_pct(value) -> str:
    """45.0 -> '45%', 12.34 -> '12.3%'. None-safe."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return f"{value}%"
    if math_is_nan(num):
        return "—"
    text = f"{num:.1f}".rstrip("0").rstrip(".")
    return f"{text}%"


def humanize_ratio(part, total) -> str:
    """(3, 10) -> '3 out of 10' with graceful zero-total handling."""
    try:
        part_i = int(round(float(part)))
        total_i = int(round(float(total)))
    except (TypeError, ValueError):
        return "—"
    if total_i <= 0:
        return humanize_number(part)
    return f"{part_i:,} out of {total_i:,}"


def titleize(column_name: str) -> str:
    """Column name -> human label: 'derived_total_spend' -> 'Total Spend'."""
    name = str(column_name or "")
    if name.startswith("derived_"):
        name = name[len("derived_"):]
    words = [w for w in name.replace("_", " ").split() if w]
    small = {"by", "of", "the", "and", "to", "per", "in", "on", "vs"}
    out = []
    for i, word in enumerate(words):
        low = word.lower()
        if i > 0 and low in small:
            out.append(low)
        elif low == "id":
            out.append("ID")
        elif len(word) <= 4 and not any(ch in low for ch in "aeiou"):
            out.append(low.upper())  # consonant-only short tokens read as acronyms: mrr -> MRR
        elif len(word) > 1 and word.isupper():
            out.append(word)  # preserve explicit acronyms like ROI / KPI
        else:
            out.append(word.capitalize())
    return " ".join(out) or name


def slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    return slug or "value"


def safe_filename_component(label: str, max_length: int = 120) -> str:
    """Return a deterministic, portable filename component for arbitrary labels."""
    original = str(label)
    slug = slugify(original)
    digest = hashlib.sha256(original.encode("utf-8", errors="replace")).hexdigest()[:10]
    changed = slug != original or original in {".", ".."}
    if changed:
        suffix = f"_{digest}"
        slug = f"{slug[:max_length - len(suffix)]}{suffix}"
    return slug[:max_length] or "value"


def math_is_nan(num: float) -> bool:
    return num != num  # noqa: PLR0124 — NaN check without importing numpy here
