"""Transparent SLA risk assessment from configured targets and ticket age."""

from __future__ import annotations

import hashlib
import json
import math
import os

from src.config.settings import settings


def _positive_hours(name: str, default: str) -> float:
    try:
        value = float(os.environ.get(name, default))
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number of hours.") from error
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number of hours.")
    return value


SLA_TARGET_HOURS = {
    "Critical": _positive_hours("SLA_TARGET_CRITICAL_HOURS", "1"),
    "High": _positive_hours("SLA_TARGET_HIGH_HOURS", "4"),
    "Medium": _positive_hours("SLA_TARGET_MEDIUM_HOURS", "8"),
    "Low": _positive_hours("SLA_TARGET_LOW_HOURS", "24"),
}
try:
    _warning_percent = float(os.environ.get("SLA_WARNING_FRACTION_PERCENT", "25"))
except ValueError as error:
    raise ValueError("SLA_WARNING_FRACTION_PERCENT must be between 0 and 99.99.") from error
if not math.isfinite(_warning_percent) or not 0 <= _warning_percent < 100:
    raise ValueError("SLA_WARNING_FRACTION_PERCENT must be between 0 and 99.99.")
SLA_WARNING_FRACTION = _warning_percent / 100
SLA_POLICY_VERSION = "priority-age-policy-v2"
SLA_POLICY_SHA256 = hashlib.sha256(json.dumps({
    "version": SLA_POLICY_VERSION,
    "targets_hours": SLA_TARGET_HOURS,
    "warning_fraction": SLA_WARNING_FRACTION,
}, sort_keys=True).encode()).hexdigest()


def policy_description() -> dict:
    return {
        "version": SLA_POLICY_VERSION,
        "targets_hours": dict(SLA_TARGET_HOURS),
        "warning_fraction": SLA_WARNING_FRACTION,
        "warning_percent": round(SLA_WARNING_FRACTION * 100),
        "features": ["priority", "created_hours"],
        "uses_ticket_text": False,
        "uses_actual_outcome": False,
        "is_ml_model": False,
    }


def assess_sla(priority: str, created_hours: float) -> dict:
    if priority not in settings.priority_map:
        raise ValueError(f"Unsupported priority: {priority!r}.")
    if isinstance(created_hours, bool) or not isinstance(created_hours, (int, float)) or not math.isfinite(created_hours) or created_hours < 0:
        raise ValueError("created_hours must be a finite, non-negative number.")

    target = SLA_TARGET_HOURS[priority]
    elapsed = float(created_hours)
    remaining = target - elapsed
    warning_window = target * SLA_WARNING_FRACTION
    if remaining <= 0:
        status, risk, reason = "Breached", "High", f"Ticket age ({elapsed:g} hours) has reached or exceeded the {target:g}-hour target."
    elif remaining <= warning_window:
        status, risk, reason = "Approaching target", "High", f"Only {remaining:g} hours remain, inside the {warning_window:g}-hour warning window ({SLA_WARNING_FRACTION:.0%} of target)."
    else:
        status, risk = "On track", "Low"
        reason = f"{remaining:g} hours remain, outside the {warning_window:g}-hour warning window."
    return {
        "sla_breach_risk": risk,
        "sla_status": status,
        "priority": priority,
        "elapsed_hours": round(elapsed, 2),
        "target_hours": target,
        "remaining_hours": round(remaining, 2),
        "warning_window_hours": round(warning_window, 2),
        "explanation": reason,
        "policy_version": SLA_POLICY_VERSION,
        "policy_sha256": SLA_POLICY_SHA256,
    }
