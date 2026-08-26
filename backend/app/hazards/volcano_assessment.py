"""Volcano activity assessment — NOAH's automated synthesis.

Combines two independent signals:

1. PHIVOLCS curated flag (`active_now`): a MANUAL snapshot of whether
   public PHIVOLCS reporting indicates ongoing eruptive/unrest activity
   (see app/data/volcanoes.py ACTIVE_AS_OF). Human-curated, refreshed
   periodically, never fabricated.
2. Live nearby seismicity: earthquakes M2.5+ within 30 km over the
   last 7 days from the USGS-fed store — an objective, automatic
   corroboration signal (volcanic unrest almost always shows up as
   shallow swarm seismicity).

Output levels (deliberately NOT the official PHIVOLCS Alert Level
scale, which only PHIVOLCS may issue):

    active-curated    curated flag says ongoing activity
    unrest-evidence   not flagged, but significant nearby seismicity
    monitored         flagged quiet AND no notable seismicity

Every response carries a methodology string and a disclaimer so the UI
can never present this as an official government alert level.
"""

from __future__ import annotations

from datetime import datetime, timezone

SEISMIC_RADIUS_KM = 30
SEISMIC_WINDOW_DAYS = 7
UNREST_MIN_COUNT_7D = 5      # events M2.5+ near the edifice in a week
UNREST_MIN_MAGNITUDE = 4.5   # or any single sizable event

_LEVEL_META = {
    "active-curated": {
        "label": "ACTIVE · PHIVOLCS-curated",
        "color": "#22c55e",
        "weight": 3,
    },
    "unrest-evidence": {
        "label": "UNREST EVIDENCE · seismic",
        "color": "#f59e0b",
        "weight": 2,
    },
    "monitored": {
        "label": "MONITORED · no anomalies",
        "color": "#94a3b8",
        "weight": 1,
    },
}

METHODOLOGY = (
    "Automated synthesis: (1) PHIVOLCS public-reporting activity flag "
    "(manual curated snapshot), combined with (2) USGS earthquakes "
    f"M2.5+ within {SEISMIC_RADIUS_KM} km over {SEISMIC_WINDOW_DAYS} days "
    f"(unrest heuristic: >= {UNREST_MIN_COUNT_7D} events or any single "
    f"M{UNREST_MIN_MAGNITUDE}+). This is NOT the official PHIVOLCS "
    "Alert Level — only PHIVOLCS issues those."
)

DISCLAIMER = (
    "NOAH assessment — not an official PHIVOLCS Alert Level. Current "
    "official status exclusively via PHIVOLCS bulletins."
)


def build_assessment(properties: dict, seismicity: dict | None) -> dict:
    """Synthesize the assessment from registry metadata + seismicity."""
    curated_active = bool(properties.get("active_now"))
    last_eruption = properties.get("last_known_eruption")

    signals: list[str] = []
    weight = 0
    seis_stats = None
    if seismicity and seismicity.get("available"):
        count = int(seismicity.get("total_7d") or 0)
        strongest = seismicity.get("strongest")
        max_mag = (strongest or {}).get("magnitude") if strongest else None
        seis_stats = {
            "count_7d": count,
            "max_magnitude_7d": max_mag,
            "radius_km": SEISMIC_RADIUS_KM,
            "window_days": SEISMIC_WINDOW_DAYS,
            "thresholds": {
                "min_count_7d": UNREST_MIN_COUNT_7D,
                "min_single_magnitude": UNREST_MIN_MAGNITUDE,
            },
        }
        if count >= UNREST_MIN_COUNT_7D:
            signals.append(
                f"{count} earthquakes M2.5+ within {SEISMIC_RADIUS_KM} km "
                f"in {SEISMIC_WINDOW_DAYS} days")
            weight = max(weight, 2)
        elif strongest and isinstance(max_mag, (int, float)) \
                and max_mag >= UNREST_MIN_MAGNITUDE:
            signals.append(
                f"single M{max_mag:g} event within {SEISMIC_RADIUS_KM} km "
                f"in {SEISMIC_WINDOW_DAYS} days")
            weight = max(weight, 2)

    if curated_active:
        signals.insert(0,
                       "PHIVOLCS public reporting flags ongoing eruptive/"
                       "unrest activity (curated snapshot)")
        weight = 3

    level = "monitored"
    for candidate, meta in _LEVEL_META.items():
        if meta["weight"] == weight:
            level = candidate
            break
    if weight == 0:
        signals.append(
            "No curated activity flag; no notable nearby seismicity")

    years_since = None
    if last_eruption:
        try:
            years_since = datetime.now(timezone.utc).year - int(last_eruption)
        except ValueError:
            pass

    return {
        "level": level,
        "label": _LEVEL_META[level]["label"],
        "color": _LEVEL_META[level]["color"],
        "signals": signals,
        "context": {
            "phivolcs_curated_flag": {
                "active_now": curated_active,
            },
            "last_known_eruption": last_eruption,
            "years_since_last_eruption": years_since,
            "seismicity": seis_stats,
        },
        "methodology": METHODOLOGY,
        "disclaimer": DISCLAIMER,
    }
