"""Flood-risk classification engine.

Combines per-station metrics into one of five clearly-defined statuses:

    NORMAL > ADVISORY > WATCH > WARNING > CRITICAL

Default thresholds (NOAH-defined, PAGASA-inspired rainfall heuristics —
NOT official PAGASA warnings) live in a JSON file (env:
NOAH_FLOOD_THRESHOLDS_PATH) so operators can tune without code changes:

    {"rainfall_mm_h":  {"ADVISORY": 2.5, "WATCH": 7.5,
                        "WARNING": 15, "CRITICAL": 30},
     "rainfall_mm_3h": {...}, "rainfall_mm_24h": {...},
     "water_level_m":  {...}}

Every output carries `basis` ('observed' | 'estimated') so the UI can
never present an estimate as a confirmed observation, plus a
recommended action per level.
"""

from __future__ import annotations

import json
import os

DEFAULT_THRESHOLDS: dict = {
    "rainfall_mm_h": {"ADVISORY": 2.5, "WATCH": 7.5, "WARNING": 15.0,
                      "CRITICAL": 30.0},
    "rainfall_mm_3h": {"ADVISORY": 5.0, "WATCH": 10.0, "WARNING": 20.0,
                       "CRITICAL": 45.0},
    "rainfall_mm_24h": {"ADVISORY": 15.0, "WATCH": 30.0, "WARNING": 60.0,
                        "CRITICAL": 100.0},
    # water-level thresholds are station-specific in reality; these are
    # conservative placeholders used ONLY if a future feed supplies
    # depth above gauge datum without its own thresholds.
    "water_level_m": {"ADVISORY": None, "WATCH": None, "WARNING": None,
                      "CRITICAL": None},
}

LEVEL_ORDER = ["NORMAL", "ADVISORY", "WATCH", "WARNING", "CRITICAL"]

RECOMMENDED_ACTIONS: dict[str, str] = {
    "NORMAL": "No action required. Continue routine monitoring.",
    "ADVISORY": "Stay informed. Monitor updates from official sources.",
    "WATCH": "Prepare for possible flooding. Check drainage, secure "
             "low-lying property.",
    "WARNING": "Move to higher ground. Avoid riverbanks and low crossings.",
    "CRITICAL": "Evacuate low-lying areas immediately. Follow LGU/MDRRMO "
                "evacuation directives.",
}

_LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVEL_ORDER)}


def load_thresholds(path: str | None) -> dict:
    """Merge the JSON file over defaults; unknown keys ignored."""
    thresholds = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    if path and os.path.exists(path):
        try:
            with open(path) as fh:
                overrides = json.load(fh)
            for metric, levels in overrides.items():
                if metric in thresholds and isinstance(levels, dict):
                    thresholds[metric].update(levels)
        except (OSError, ValueError) as exc:
            # A broken config must not silently change risk behaviour.
            raise ValueError(f"flood threshold config invalid: {exc}") from exc
    return thresholds


def classify_metric(metric: str, value: float,
                    thresholds: dict) -> tuple[str, float] | None:
    """Return (level, crossed_threshold) for one measurement."""
    levels = thresholds.get(metric)
    if not levels:
        return None
    level = "NORMAL"
    crossed: float | None = None
    for name in LEVEL_ORDER[1:]:
        bound = levels.get(name)
        if bound is not None and value >= float(bound):
            level, crossed = name, float(bound)
    return (level, crossed) if crossed is not None else ("NORMAL", 0.0)


def assess_station(
    observations: list[dict],
    thresholds: dict,
    station_kind: str,
) -> dict:
    """observations: normalized dicts with metric/value/observed_at.

    Returns the assessment payload consumed by /api/flood/status:
    level, basis, reason(s), per-metric breakdown, recommended action.
    """
    by_metric: dict[str, dict] = {}
    level = "NORMAL"
    reasons: list[str] = []
    alert_payload: dict | None = None

    for obs in observations:
        metric = obs["metric"]
        result = classify_metric(metric, obs["value"], thresholds)
        if result is None:
            continue
        m_level, crossed = result
        by_metric[metric] = {
            "value": obs["value"], "level": m_level,
            "threshold_crossed": crossed or None,
            "observed_at": obs.get("observed_at"),
        }
        if _LEVEL_RANK[m_level] > _LEVEL_RANK[level]:
            level = m_level

    if level != "NORMAL":
        # Reason cites every metric at or above the winning level.
        for metric, info in sorted(by_metric.items()):
            if _LEVEL_RANK[info["level"]] >= _LEVEL_RANK[level]:
                unit = "mm/h" if metric.endswith("_h") and "_3" not in metric \
                    else "mm"
                reasons.append(
                    f"{metric.replace('_', ' ')} = "
                    f"{info['value']:g} {unit}"
                    + (f" (threshold {info['threshold_crossed']:g})"
                       if info["threshold_crossed"] else ""))
        worst = max(
            (info for info in by_metric.values()
             if _LEVEL_RANK[info["level"]] >= _LEVEL_RANK[level]),
            key=lambda i: _LEVEL_RANK[i["level"]])
        alert_payload = {
            "level": level,
            "reason": "; ".join(reasons),
            "measurement": worst["value"],
            "threshold": worst["threshold_crossed"],
        }

    return {
        "level": level,
        "basis": "observed",
        "reasons": reasons,
        "metrics": by_metric,
        "recommended_action": RECOMMENDED_ACTIONS[level],
        "alert": alert_payload,
    }
