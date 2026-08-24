"""Tests for PAGASA local naming: PAR geometry, set rotation, and
chronological name assignment."""

from datetime import datetime, timedelta, timezone

from app.services import pagasa


def test_regular_sets_shape_and_rotation():
    # Four rotating sets of 25, auxiliary sets of 10
    for key in (0, 1, 2, 3):
        assert len(pagasa.REGULAR_SETS[key]) == 25
        assert len(pagasa.AUX_SETS[key]) == 10

    # Official column headers: Set I 2025..., II 2022/2026..., III 2023...,
    # IV 2024...
    assert pagasa.REGULAR_SETS[2025 % 4][0] == "AURING"
    assert pagasa.REGULAR_SETS[2026 % 4][0] == "ADA"
    assert pagasa.REGULAR_SETS[2027 % 4][0] == "AMANG"
    assert pagasa.REGULAR_SETS[2028 % 4][0] == "AGHON"


def test_point_in_par_geometry():
    assert pagasa.point_in_par(125.0, 15.0)          # central PAR
    assert pagasa.point_in_par(130.0, 24.0)          # northern band >=120E
    assert pagasa.point_in_par(122.0, 23.0)
    assert pagasa.point_in_par(120.0, 6.0)           # southern band

    assert not pagasa.point_in_par(140.0, 20.0)      # west Pacific, east of PAR
    assert not pagasa.point_in_par(110.0, 10.0)      # west of PAR
    assert not pagasa.point_in_par(118.0, 23.0)      # notch NW of (120,21)-(120,25)
    assert not pagasa.point_in_par(130.0, 3.0)       # south of PAR
    assert not pagasa.point_in_par(130.0, 26.0)      # north of PAR


def test_par_entry_time_finds_first_inside_fix():
    def fx(iso, lat, lon):
        return {"_dt": datetime.fromisoformat(iso).replace(tzinfo=timezone.utc),
                "LAT": lat, "LON": lon}

    fixes = [fx("2026-08-18T00:00:00", 12.0, 141.0),
             fx("2026-08-19T00:00:00", 14.0, 133.0),
             fx("2026-08-20T00:00:00", 16.0, 128.0)]
    entry = pagasa.par_entry_time(fixes)
    assert entry is not None
    assert entry.strftime("%Y-%m-%dT%H:%M:%S") == "2026-08-19T00:00:00"

    never = pagasa.par_entry_time([fx("2026-08-19T00:00:00", 8.0, 150.0)])
    assert never is None


def test_assign_names_chronological_with_aux_overflow():
    dt = lambda d, h=0: datetime(2026, 8, d, h, tzinfo=timezone.utc)  # noqa: E731
    out = pagasa.assign_pagasa_names([
        ("sid-late", dt(20)),
        ("sid-first", dt(18)),
        ("sid-mid", dt(19)),
    ])
    set2 = pagasa.REGULAR_SETS[2026 % 4]
    assert out == {"sid-first": set2[0], "sid-mid": set2[1],
                   "sid-late": set2[2]}
    assert set2[:3] == ["ADA", "BASYANG", "CALOY"]

    # Past 25 cyclones the auxiliary set takes over
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    many = [(f"s{i}", base + timedelta(hours=i)) for i in range(27)]
    out = pagasa.assign_pagasa_names(many)
    aux = pagasa.AUX_SETS[2026 % 4]
    assert out["s25"] == aux[0]
    assert out["s26"] == aux[1]

    # Entry-year grouping: a December 2025 entrant uses Set I, untouched
    # by 2026 assignments
    out = pagasa.assign_pagasa_names([
        ("old", datetime(2025, 12, 30, tzinfo=timezone.utc)),
        ("new", datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ])
    assert out == {"old": "AURING", "new": "ADA"}


def test_storm_without_slot_gets_no_name():
    # More than 25+10 entrants: extras stay unnamed rather than invented
    many = [(f"s{i}", datetime(2026, 1, 1, i % 24, tzinfo=timezone.utc))
            for i in range(36)]
    out = pagasa.assign_pagasa_names(many)
    assert len(out) == 35


def test_tc_code_bands_match_panahon_scheme():
    assert pagasa.tc_code(None) is None
    assert pagasa.tc_code(20) == "TD"
    assert pagasa.tc_code(33.9) == "TD"
    assert pagasa.tc_code(34) == "TS"
    assert pagasa.tc_code(47.9) == "TS"
    assert pagasa.tc_code(48) == "STS"
    assert pagasa.tc_code(63.9) == "STS"
    assert pagasa.tc_code(64) == "TY"
    assert pagasa.tc_code(99.9) == "TY"
    assert pagasa.tc_code(100) == "ST"

    # Official panahon.gov.ph palette
    assert pagasa.TC_COLORS["TD"] == "#00e400"
    assert pagasa.TC_COLORS["TS"] == "#ffe400"
    assert pagasa.TC_COLORS["STS"] == "#ff9800"
    assert pagasa.TC_COLORS["TY"] == "#ff2020"
    assert pagasa.TC_COLORS["ST"] == "#e000e0"
    assert set(pagasa.SIGNAL_COLORS) == {1, 2, 3, 4, 5}
