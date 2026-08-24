"""PAGASA local naming of tropical cyclones entering the Philippine
Area of Responsibility (PAR).

Rules implemented (per PAGASA's official "Philippine Tropical Cyclone
Names", learning-tools page, list as revised January 2022 / January 2025
replacement names included):

* Four regular sets of 25 Filipino names rotate annually and repeat
  every four years. Column selection is simply ``year mod 4``:
  Set I 2025/2029..., Set II 2022/2026..., Set III 2023/2027...,
  Set IV 2024/2028....
* Each regular set has a corresponding auxiliary set of 10 names used
  when a season exceeds 25 named cyclones.
* Names are assigned chronologically as disturbances enter the PAR.

Honesty note: IBTrACS gives us only the last N days of fixes, so the
sequence here is an *estimate* — storms that entered PAR earlier in the
season than our data window are invisible to it. Callers should disclose
that (the /api/cyclones payload does).
"""

from collections import defaultdict
from datetime import datetime

# Official PAR boundary (PAGASA definition): 5N115E -> 15N115E ->
# 21N120E -> 25N120E -> 25N135E -> 5N135E, closed.
PAR_RING: list[tuple[float, float]] = [
    (115.0, 5.0),
    (115.0, 15.0),
    (120.0, 21.0),
    (120.0, 25.0),
    (135.0, 25.0),
    (135.0, 5.0),
]

REGULAR_SETS: dict[int, list[str]] = {
    1: [  # Set I — 2025, 2029, ...
        "AURING", "BISING", "CRISING", "DANTE", "EMONG", "FABIAN",
        "GORIO", "HUANING", "ISANG", "JACINTO", "KIKO", "LANNIE",
        "MIRASOL", "NANDO", "OPONG", "PAOLO", "QUEDAN", "RAMIL",
        "SALOME", "TINO", "UWAN", "VERBENA", "WILMA", "YASMIN",
        "ZORAIDA",
    ],
    2: [  # Set II — 2022, 2026, 2030, ... (active in 2026)
        "ADA", "BASYANG", "CALOY", "DOMENG", "ESTER", "FRANCISCO",
        "GARDO", "HENRY", "INDAY", "JOSIE", "KIYAPO", "LUIS",
        "MAYMAY", "NENENG", "OBET", "PILANDOK", "QUEENIE", "ROSAL",
        "SAMUEL", "TOMAS", "UMBERTO", "VENUS", "WALDO", "YAYANG",
        "ZENY",
    ],
    3: [  # Set III — 2023, 2027, ...
        "AMANG", "BETTY", "CHEDENG", "DODONG", "EMIL", "FALCON",
        "GAVINO", "HANNA", "INENG", "JENNY", "KABAYAN", "LIWAYWAY",
        "MARILYN", "NIMFA", "ONYOK", "PERLA", "QUIEL", "RAMON",
        "SARAH", "TAMARAW", "UGONG", "VIRING", "WENG", "YOYOY",
        "ZIGZAG",
    ],
    0: [  # Set IV — 2024, 2028, ...
        "AGHON", "BUTCHOY", "CARINA", "DINDO", "ENTENG", "FERDIE",
        "GENER", "HELEN", "IGME", "JULIAN", "KRISTINE", "LEON",
        "MARCE", "NIKA", "OFEL", "PEPITO", "QUERUBIN", "ROMINA",
        "SIONY", "TONYO", "UPANG", "VICKY", "WARREN", "YOYONG",
        "ZOSIMO",
    ],
}

AUX_SETS: dict[int, list[str]] = {
    1: ["ALAMID", "BRUNO", "CONCHING", "DOLOR", "ERNIE", "FLORANTE",
        "GERARDO", "HERNAN", "ISKO", "JEROME"],
    2: ["AGILA", "BAGWIS", "CHITO", "DIEGO", "ELENA", "FELINO",
        "GUNDING", "HARRIET", "INDANG", "JESSA"],
    3: ["ABE", "BERTO", "CHARO", "DADO", "ESTOY", "FELIONG",
        "GENING", "HERMAN", "IRMA", "JAIME"],
    0: ["ALAKDAN", "BALDO", "CLARA", "DENCIO", "ESTONG", "FELIPE",
        "GOMER", "HELING", "ISMAEL", "JULIO"],
}

NAMING_DISCLOSURE = ("PAGASA local names estimated by chronological "
                     "PAR-entry order within the loaded data window")


def point_in_par(lon: float, lat: float) -> bool:
    """Ray-casting point-in-polygon against the official PAR boundary."""
    inside = False
    n = len(PAR_RING)
    j = n - 1
    for i in range(n):
        xi, yi = PAR_RING[i]
        xj, yj = PAR_RING[j]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _f(raw) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def par_entry_time(fixes: list[dict]) -> datetime | None:
    """Earliest fix timestamp whose position lies inside the PAR.

    ``fixes`` are IBTrACS row dicts with ``_dt``, ``LAT`` and ``LON``
    (as produced by cyclones.fetch_recent_fixes); time-sorted input is
    not required — sorting happens here.
    """
    entry: datetime | None = None
    for fix in sorted(fixes, key=lambda r: r["_dt"]):
        lat = _f(fix.get("LAT"))
        lon = _f(fix.get("LON"))
        if lat is None or lon is None:
            continue
        if point_in_par(lon, lat):
            entry = fix["_dt"]
            break
    return entry


def assign_pagasa_names(entries: list[tuple[str, datetime]]) -> dict[str, str]:
    """sid -> PAGASA name, assigned chronologically by PAR entry.

    Storms are grouped by the calendar year of their PAR entry (a storm
    lingering across New Year keeps the season it was named in) and take
    the next free slot of that year's regular set, overflowing into the
    auxiliary set past 25 cyclones.
    """
    by_year: dict[int, list[tuple[datetime, str]]] = defaultdict(list)
    for sid, dt in entries:
        by_year[dt.year].append((dt, sid))

    out: dict[str, str] = {}
    for year, items in by_year.items():
        items.sort(key=lambda t: (t[0], t[1]))
        pool = REGULAR_SETS.get(year % 4, []) + AUX_SETS.get(year % 4, [])
        for idx, (_, sid) in enumerate(items):
            if idx < len(pool):
                out[sid] = pool[idx]
    return out


# --- Tropical-cyclone classification & visualization palette --------------
#
# Codes, labels and colors are the ones used by panahon.gov.ph
# (PAGASA's interactive map): LPA grey, TD green, TS yellow,
# STS orange, TY red, STY magenta.

TC_CODES = ("LPA", "TD", "TS", "STS", "TY", "ST")
TC_COLORS: dict[str, str] = {
    "LPA": "#9aa5b1",
    "TD": "#00e400",
    "TS": "#ffe400",
    "STS": "#ff9800",
    "TY": "#ff2020",
    "ST": "#e000e0",
}
CODE_LABELS: dict[str, str] = {
    "LPA": "Low Pressure Area",
    "TD": "Tropical Depression",
    "TS": "Tropical Storm",
    "STS": "Severe Tropical Storm",
    "TY": "Typhoon",
    "ST": "Super Typhoon",
}

# PAGASA TCWS wind-signal hues (official convention: blue / yellow /
# orange / dark red / magenta)
SIGNAL_COLORS: dict[int, str] = {
    1: "#0000FF",
    2: "#FFCC00",
    3: "#FF8C00",
    4: "#8B0000",
    5: "#8B008B",
}


def tc_code(wind_kt: float | None) -> str | None:
    """PAGASA classification code from sustained winds (kt).

    Bands mirror forecast.pagasa_status applied to available agency
    winds: TD <34, TS >=34, STS >=48, TY >=64, ST >=100."""
    if wind_kt is None:
        return None
    if wind_kt < 34:
        return "TD"
    if wind_kt < 48:
        return "TS"
    if wind_kt < 64:
        return "STS"
    if wind_kt < 100:
        return "TY"
    return "ST"


def display_name(international: str, pagasa: str | None) -> str:
    """Map label: PAGASA name leads once the storm carries one."""
    if pagasa:
        return f"{pagasa} ({international})"
    return international
