"""Configurable alert engine + notification dispatcher abstraction.

Rules live in a JSON document (path via NOAH_EQ_ALERT_RULES); a sane
default set ships inline. Rule shape:

  {"name": "strong-global",
   "any_of": [{"field": "magnitude", "op": ">=", "value": 6.0}],
   "severity": "HIGH"}

Supported fields: magnitude, depth_km, distance_km (km from a configured
reference point), region (equality). Operators: >=, <=, >, <, ==.
All matching rules fire; each produces one severity-max alert.

The dispatcher decouples detection from delivery: today only the
dashboard channel exists (alerts ride the SSE bus); sirens/email/SMS can
subscribe later WITHOUT touching this engine.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.hazards.base import SEVERITIES, HazardEvent

logger = logging.getLogger("noah.hazards.alerts")

DEFAULT_RULES = [
    {"name": "major-quake-global", "severity": "CRITICAL",
     "any_of": [{"field": "magnitude", "op": ">=", "value": 7.0}]},
    {"name": "strong-quake-global", "severity": "HIGH",
     "any_of": [{"field": "magnitude", "op": ">=", "value": 6.0}]},
    {"name": "notable-quake-global", "severity": "MODERATE",
     "any_of": [{"field": "magnitude", "op": ">=", "value": 5.0}]},
]

_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


@dataclass(slots=True)
class AlertDecision:
    severity: str
    rule_name: str
    summary: str
    event_uid: str


def load_rules(path: str | None) -> list[dict]:
    if not path:
        return DEFAULT_RULES
    try:
        doc = json.loads(Path(path).read_text())
        rules = doc.get("rules", doc) if isinstance(doc, dict) else doc
        return list(rules)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("alert rules file unusable (%s); defaults active", exc)
        return DEFAULT_RULES


def _event_fields(ev: HazardEvent, reference_point: tuple[float, float] | None,
                  distance_km: float | None) -> dict:
    fields = {
        "magnitude": ev.magnitude,
        "depth_km": ev.depth_km,
        "region": ev.region,
    }
    if distance_km is not None:
        fields["distance_km"] = round(distance_km, 1)
    return fields


def _condition_matches(cond: dict, fields: dict) -> bool:
    op = cond.get("op")
    fn = _OPS.get(op)
    if fn is None or cond.get("field") not in fields:
        return False
    actual = fields[cond["field"]]
    if actual is None:
        return False
    try:
        return fn(actual, cond.get("value"))
    except TypeError:
        return False


def evaluate_event(
        ev: HazardEvent, rules: list[dict],
        reference_point: tuple[float, float] | None = None,
        reference_radius_km: float | None = None,
        distance_km: float | None = None,
) -> list[AlertDecision]:
    """Evaluate every rule against one event; return fired decisions."""
    fired: list[AlertDecision] = []
    for rule in rules:
        conditions = rule.get("all_of") or []
        any_conditions = rule.get("any_of") or []
        ok_all = all(_condition_matches(c, _event_fields(
            ev, reference_point, distance_km)) for c in conditions)
        ok_any = (not any_conditions) or any(
            _condition_matches(c, _event_fields(ev, reference_point, distance_km))
            for c in any_conditions)
        # Region-scope guard: a rule may restrict itself to events within
        # reference_radius_km when a reference point is configured.
        if rule.get("within_reference_km") is not None:
            if distance_km is None or distance_km > rule["within_reference_km"]:
                continue
        severity = rule.get("severity", "INFO")
        if severity not in SEVERITIES:
            severity = "INFO"
        if ok_all and ok_any:
            mag = f"M{ev.magnitude:.1f}" if ev.magnitude is not None else "M?"
            fired.append(AlertDecision(
                severity=severity, rule_name=rule.get("name", "unnamed"),
                summary=f"{mag} — {ev.place or 'location unknown'}"
                        f" (depth {ev.depth_km if ev.depth_km is not None else '?'} km)",
                event_uid=ev.uid))
    return fired


class NotificationDispatcher:
    """Channel registry. Dashboard channel rides the event bus; add
    email/SMS/siren channels later by registering new callables."""

    def __init__(self) -> None:
        self._channels: dict[str, object] = {}

    def register(self, name: str, sink) -> None:
        self._channels[name] = sink

    async def dispatch(self, decision: AlertDecision, event: HazardEvent,
                       publish) -> int:
        payload = {
            "event": "hazard.alert",
            "severity": decision.severity,
            "rule": decision.rule_name,
            "summary": decision.summary,
            "event_uid": decision.event_uid,
            "origin_time": event.origin_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        delivered = 0
        for name, sink in self._channels.items():
            try:
                result = sink(payload)
                # Bus sink is sync; future async channels awaited here
                if hasattr(result, "__await__"):
                    await result
                delivered += 1
            except Exception as exc:  # noqa: BLE001 — never kill ingestion
                logger.error("notification channel %r failed: %s", name, exc)
        publish(payload)
        return delivered
