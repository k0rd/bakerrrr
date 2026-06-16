"""Small shared helpers for item-backed throwable readability."""

from __future__ import annotations

from game.status_ui_runtime import _status_effect_label


def _int_or_default(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def throwable_summary_bits(throw_profile, *, include_consumed=False):
    if not isinstance(throw_profile, dict) or not throw_profile:
        return []

    bits = [f"throw rng {_int_or_default(throw_profile.get('range'), 1)}"]
    damage = max(0, _int_or_default(throw_profile.get("damage"), 0))
    if damage > 0:
        bits.append(f"impact {damage}")
    blast_radius = max(0, _int_or_default(throw_profile.get("explosion_radius"), 0))
    if blast_radius > 0:
        bits.append(f"blast r{blast_radius}")
    cloud_radius = max(0, _int_or_default(throw_profile.get("cloud_radius"), 0))
    smoke = max(0, _int_or_default(throw_profile.get("smoke_intensity"), 0))
    if smoke > 0:
        smoke_text = "smoke"
        if cloud_radius > 0:
            smoke_text += f" r{cloud_radius}"
        bits.append(smoke_text)
    if max(0, _int_or_default(throw_profile.get("fire_intensity"), 0)) > 0:
        bits.append("fire")
    aerosol_status = str(throw_profile.get("aerosol_status", "") or "").strip().lower()
    if aerosol_status:
        aerosol_label = str(throw_profile.get("aerosol_label", "") or "").strip().lower()
        status_text = _status_effect_label(
            aerosol_status,
            duration=_int_or_default(throw_profile.get("aerosol_duration"), 0),
            modifiers=throw_profile.get("aerosol_modifiers", {}),
            title=False,
            limit=2,
        )
        bits.append(f"{aerosol_label or 'aerosol'} {status_text}")
    if include_consumed and bool(throw_profile.get("consume_on_throw", True)):
        bits.append("consumed")
    return bits


def throwable_summary_text(throw_profile, *, include_consumed=False):
    return " ".join(throwable_summary_bits(throw_profile, include_consumed=include_consumed))
