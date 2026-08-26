"""Volcano activity assessment tests (app/hazards/volcano_assessment)."""

from __future__ import annotations

from app.hazards.volcano_assessment import (
    DISCLAIMER,
    METHODOLOGY,
    build_assessment,
)


def _seis(count, max_mag=None):
    return {
        "available": True,
        "total_7d": count,
        "count_24h": 0,
        "strongest": ({"magnitude": max_mag, "place": "near edifice"}
                      if max_mag is not None else None),
    }


def test_curated_flag_dominates_to_active():
    out = build_assessment({"active_now": True, "last_known_eruption": "2024"},
                           _seis(0))
    assert out["level"] == "active-curated"
    assert "PHIVOLCS" in out["signals"][0]
    assert out["context"]["years_since_last_eruption"] >= 1


def test_unrest_by_swarm_count():
    out = build_assessment({"active_now": False}, _seis(7, 3.2))
    assert out["level"] == "unrest-evidence"
    assert any("7 earthquakes" in s for s in out["signals"])
    assert out["context"]["seismicity"]["count_7d"] == 7


def test_unrest_by_single_large_event():
    out = build_assessment({"active_now": False}, _seis(1, 4.8))
    assert out["level"] == "unrest-evidence"
    assert any("M4.8" in s for s in out["signals"])


def test_quiet_volcano_is_monitored():
    out = build_assessment({"active_now": False}, _seis(0))
    assert out["level"] == "monitored"
    assert any("no notable nearby seismicity" in s for s in out["signals"])


def test_module_offline_still_assesses_from_registry():
    out = build_assessment({"active_now": False}, {"available": False})
    assert out["level"] == "monitored"
    assert out["context"]["seismicity"] is None
    # small swarm below threshold stays monitored
    out2 = build_assessment({"active_now": False}, _seis(2, 3.0))
    assert out2["level"] == "monitored"


def test_honesty_strings_always_present():
    for props, seis in (({"active_now": True}, _seis(9, 5.0)),
                        ({}, None)):
        out = build_assessment(props, seis)
        assert out["methodology"] == METHODOLOGY
        assert "not an official PHIVOLCS Alert Level" in out["disclaimer"]
        assert DISCLAIMER in out["disclaimer"]
