"""Shared intrusion and ingress vocabulary helpers.

These helpers are reused across ingress, pressure, reputation, controllers,
and the remaining systems facade. Keep this module narrow: aperture
classification, ingress labeling, and quiet/noisy breach classification only.
"""

from __future__ import annotations


QUIET_TAMPER_METHODS = {
    "badge_reader_spoof",
    "biometric_spoof",
    "biometric_jam",
    "picked_front_door",
    "manual_front_door_override",
    "hotwire",
    "ignition_override",
    "locked_vehicle_entry",
}

NOISY_TAMPER_METHODS = {
    "forced_breach",
    "forced_side_entry",
    "deep_breach",
    "crash_window_entry",
    "window_shot",
}

OBVIOUS_TRESPASS_METHODS = {
    "forced_side_entry",
    "jimmied_side_entry",
    "forced_breach",
    "deep_breach",
    "crash_window_entry",
}


def _ingress_mode_label(mode):
    mode = str(mode or "").strip().lower()
    mapping = {
        "side_entry": "door breach",
        "window_entry": "window",
        "forced_breach": "wall breach",
    }
    return mapping.get(mode, mode.replace("_", " "))


def _is_window_aperture(aperture_kind):
    return str(aperture_kind or "").strip().lower() in {"window", "skylight"}


def _is_side_aperture(aperture_kind):
    return str(aperture_kind or "").strip().lower() in {"service_door", "employee_door", "side_door"}


def _is_operable_door_aperture(aperture_kind):
    kind = str(aperture_kind or "").strip().lower()
    return kind == "door" or _is_side_aperture(kind)


def _trespass_label_from_score(score):
    try:
        severity = int(score)
    except (TypeError, ValueError):
        severity = 0
    if severity <= 0:
        return "clear"
    if severity < 15:
        return "suspicious"
    if severity < 30:
        return "trespass"
    return "serious_trespass"


def _ingress_method_label(method):
    method = str(method or "").strip().lower()
    mapping = {
        "side_entry": "door breach",
        "authorized_side_entry": "authorized",
        "jimmied_side_entry": "jimmied",
        "manual_side_entry": "manual bypass",
        "forced_side_entry": "forced",
        "picked_front_door": "picked front door",
        "manual_front_door_override": "manual front door",
        "badge_reader_spoof": "badge spoof",
        "badge_reader_override": "badge override",
        "biometric_spoof": "biometric spoof",
        "biometric_jam": "biometric jam",
        "biometric_override": "biometric override",
        "quiet_window_entry": "quiet window",
        "careful_window_entry": "careful window",
        "crash_window_entry": "crash window",
        "window_shot": "shot out window",
        "forced_breach": "forced breach",
        "deep_breach": "deep breach",
        "hotwire": "hotwire",
        "ignition_override": "ignition override",
        "locked_vehicle_entry": "locked vehicle",
    }
    return mapping.get(method, method.replace("_", " "))


def _tamper_is_noisy(*, ingress_kind="", ingress_method="", breach_severity=0.0):
    ingress_kind = str(ingress_kind or "").strip().lower()
    ingress_method = str(ingress_method or "").strip().lower()
    breach_severity = float(max(0.0, breach_severity))
    if ingress_kind in {"boundary_breach", "deep_breach"}:
        return True
    if ingress_method in NOISY_TAMPER_METHODS:
        return True
    if ingress_method in QUIET_TAMPER_METHODS:
        return False
    return breach_severity >= 0.45


def _quiet_unwitnessed_tamper(prop, *, witnessed, ingress_kind="", ingress_method="", breach_severity=0.0):
    del prop
    if bool(witnessed):
        return False
    return not _tamper_is_noisy(
        ingress_kind=ingress_kind,
        ingress_method=ingress_method,
        breach_severity=breach_severity,
    )


def _trespass_is_obvious_breach(*, ingress_kind="", ingress_method="", breach_severity=0.0):
    ingress_kind = str(ingress_kind or "").strip().lower()
    ingress_method = str(ingress_method or "").strip().lower()
    breach_severity = float(max(0.0, breach_severity))
    if ingress_kind in {"boundary_breach", "deep_breach"}:
        return True
    if ingress_method in OBVIOUS_TRESPASS_METHODS:
        return True
    return breach_severity >= 0.58
