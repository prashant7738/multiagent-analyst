"""Versioned definitions for rules that affect quality and anomaly findings."""

import hashlib
import json


RULE_DEFINITIONS = {
    "percentage_bounds": "configured unit_scale controls ratio [0, 1] vs percent [0, 100]",
    "count_range": "counts must be non-negative integers",
    "anomaly_iqr": "skewed values use the configured Tukey far-out fence",
    "tax_rate": "tax must not exceed the configured reasonable tax rate",
    "reconciliation": "total must match amount + tax - discount within configured tolerance",
}
RULE_DEFINITION_VERSION = "2026.08.1"
RULE_DEFINITION_HASH = hashlib.sha256(
    json.dumps(RULE_DEFINITIONS, sort_keys=True).encode("utf-8")
).hexdigest()[:12]


def rule_manifest():
    return {
        "version": RULE_DEFINITION_VERSION,
        "hash": RULE_DEFINITION_HASH,
        "definitions": dict(RULE_DEFINITIONS),
    }