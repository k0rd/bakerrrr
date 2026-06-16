"""Shared HUD and status-text helpers extracted from ``game.systems``."""

import re

from game.components import VehicleState
from game.service_runtime import _int_or_default
from game.system_support.status_runtime import (
    SURVIVAL_CRITICAL_LEVEL,
    SURVIVAL_LOW_LEVEL,
    SURVIVAL_SEVERE_LEVEL,
    _ensure_survival_needs,
    _float_or_default,
    _status_multiplier,
)
from game.ui_text_runtime import _rich_line, _segment


SURVIVAL_METER_HIGH_COLOR = "survival_meter_high"
SURVIVAL_METER_MID_COLOR = "survival_meter_mid"
SURVIVAL_METER_LOW_COLOR = "survival_meter_low"


def _floor_label(z, *, long=False):
    try:
        z = int(z)
    except (TypeError, ValueError):
        return str(z)
    if z < 0:
        return f"Basement {abs(z)}" if long else f"B{abs(z)}"
    if long:
        return f"Floor {z + 1}"
    return str(z + 1)


def _humanize_slug(value, *, title=False):
    text = re.sub(r"\s+", " ", str(value or "").replace("_", " ").strip())
    if not text:
        return ""
    return text.title() if title else text


def _hud_status_label(text, fallback="Unknown"):
    label = str(text or "").strip().replace("_", " ")
    if not label:
        return str(fallback or "Unknown")
    return label.title()


def _hud_primary_status_chunks(sim, *, zoom_mode, active_z, player_pos, lighting_state, area_type, district_type, security):
    chunk_coord = getattr(sim, "active_chunk_coord", None)
    if chunk_coord:
        chunk_text = f"{int(chunk_coord[0])},{int(chunk_coord[1])}"
    else:
        chunk_text = "?,?"

    light_phase = _hud_status_label(lighting_state.get("phase", "day"), fallback="Day")
    time_label = str(lighting_state.get("time_label", "--:--")).strip() or "--:--"
    area_label = _hud_status_label(area_type, fallback="Unknown")
    district_label = _hud_status_label(district_type, fallback="")
    floor_text = _floor_label(active_z, long=True)

    view_only = False
    local_in_vehicle = False
    try:
        vehicle_state = sim.ecs.get(VehicleState).get(int(getattr(sim, "player_eid", 0) or 0))
        local_in_vehicle = bool(vehicle_state and vehicle_state.in_vehicle and zoom_mode != "overworld")
    except (AttributeError, TypeError, ValueError):
        local_in_vehicle = False
    if zoom_mode == "overworld":
        records = getattr(sim, "overworld_view_only_by_eid", {})
        try:
            view_only = bool(records.get(int(getattr(sim, "player_eid", 0) or 0), False))
        except (TypeError, ValueError):
            view_only = False

    status_chunks = [
        "Map View" if zoom_mode == "overworld" and view_only else "In Vehicle" if zoom_mode == "overworld" or local_in_vehicle else "On Foot",
        "Overworld Map" if zoom_mode == "overworld" and view_only else "Quick Travel" if zoom_mode == "overworld" else "Local Driving" if local_in_vehicle else floor_text,
        f"Chunk {chunk_text}",
        f"Area {area_label}",
    ]
    if district_label and district_label.lower() != area_label.lower():
        status_chunks.append(f"District {district_label}")
    if str(security or "").strip() and str(security).strip() != "?":
        status_chunks.append(f"Security {security}")
    status_chunks.append(f"Time {time_label} {light_phase}")
    return status_chunks


def _survival_meter_color(value):
    value = max(0.0, min(100.0, _float_or_default(value, 0.0)))
    if value >= SURVIVAL_LOW_LEVEL:
        return SURVIVAL_METER_HIGH_COLOR
    if value >= SURVIVAL_CRITICAL_LEVEL:
        return SURVIVAL_METER_MID_COLOR
    return SURVIVAL_METER_LOW_COLOR


def _survival_indicator_chunks(needs, *, rich=False):
    needs = _ensure_survival_needs(needs)
    if needs is None:
        return []

    def label(prefix, value):
        value = max(0.0, min(100.0, _float_or_default(value, 0.0)))
        marker = "!!" if value < SURVIVAL_SEVERE_LEVEL else "!" if value < SURVIVAL_CRITICAL_LEVEL else ""
        text = f"{prefix}{marker}{value:.0f}"
        if rich:
            return _rich_line([_segment(text, color=_survival_meter_color(value))], text=text)
        return text

    return [
        label("F", getattr(needs, "hunger", 0.0)),
        label("W", getattr(needs, "thirst", 0.0)),
    ]


def _sentence_from_note(note):
    text = str(note or "").strip()
    if not text:
        return ""
    text = text[:1].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


def _status_modifier_brief_label(key, value):
    value = _float_or_default(value, 0.0)
    if abs(value) <= 0.0001:
        return ""

    if key == "ranged_accuracy_mult":
        return f"aim {value * 100.0:+.0f}%"
    if key == "projectile_spread_mod":
        return f"spread {int(round(value)):+d}"
    if key == "weapon_cooldown_mult":
        return f"fire {(-value) * 100.0:+.0f}%"
    if key == "melee_cooldown_mult":
        return f"melee rate {(-value) * 100.0:+.0f}%"
    if key == "ranged_damage_mult":
        return f"shot {value * 100.0:+.0f}%"
    if key == "melee_damage_mult":
        return f"melee {value * 100.0:+.0f}%"
    if key == "incoming_damage_mult":
        return f"guard {(-value) * 100.0:+.0f}%"
    if key == "armor_absorb_bonus":
        return f"armor {value * 100.0:+.0f}%"
    if key == "cover_absorb_bonus":
        return f"cover {value * 100.0:+.0f}%"
    if key == "suppression_resist_mult":
        return f"steady {value * 100.0:+.0f}%"
    if key == "move_speed_mult":
        return f"speed {value * 100.0:+.0f}%"
    if key == "movement_misdirect_chance":
        return f"misstep {value * 100.0:+.0f}%"
    if key == "hallucination_intensity":
        return f"visions {value * 100.0:+.0f}%"
    if key == "hallucination_read_chance":
        return f"false reads {value * 100.0:+.0f}%"
    if key == "control_lapse_chance":
        return f"lapse {value * 100.0:+.0f}%"
    if key == "control_lapse_ticks":
        return f"stun {int(round(value)):+d}t"
    if key == "blackout_chance":
        return f"blackout {value * 100.0:+.0f}%"
    if key == "blackout_min_ticks":
        return f"blackout min {int(round(value))}t"
    if key == "blackout_max_ticks":
        return f"blackout max {int(round(value))}t"
    if key == "blackout_cooldown_ticks":
        return f"blackout cd {int(round(value))}t"
    if key == "hp_tick_delta":
        label = "regen" if value > 0.0 else "bleed"
        return f"{label} {value:+.2f}/t"
    if key == "toxicity_tick_delta":
        return f"toxin {value:+.2f}/t"
    if key == "assault_bias_delta":
        return f"push {value * 100.0:+.0f}%"
    if key == "retreat_bias_delta":
        return f"nerve {(-value) * 100.0:+.0f}%"
    return ""


def _status_modifier_summary_text(modifiers, *, limit=3):
    if not isinstance(modifiers, dict):
        return ""

    labels = []
    ordered_keys = (
        "ranged_accuracy_mult",
        "projectile_spread_mod",
        "weapon_cooldown_mult",
        "ranged_damage_mult",
        "melee_damage_mult",
        "incoming_damage_mult",
        "suppression_resist_mult",
        "move_speed_mult",
        "movement_misdirect_chance",
        "hallucination_intensity",
        "hallucination_read_chance",
        "control_lapse_chance",
        "control_lapse_ticks",
        "blackout_chance",
        "hp_tick_delta",
        "toxicity_tick_delta",
        "armor_absorb_bonus",
        "cover_absorb_bonus",
        "assault_bias_delta",
        "retreat_bias_delta",
    )
    for key in ordered_keys:
        if key not in modifiers:
            continue
        label = _status_modifier_brief_label(key, modifiers.get(key, 0.0))
        if label:
            labels.append(label)

    if not labels:
        return ""
    if len(labels) <= int(max(1, limit)):
        return ", ".join(labels)
    visible = labels[: int(max(1, limit))]
    visible.append(f"+{len(labels) - len(visible)} more")
    return ", ".join(visible)


def _status_effect_label(status, duration=0, modifiers=None, *, title=False, limit=3):
    status_name = _humanize_slug(status, title=title) or ("Effect" if title else "effect")
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 0
    summary = _status_modifier_summary_text(modifiers, limit=limit)
    if duration > 0 and summary:
        return f"{status_name} {duration}t [{summary}]"
    if duration > 0:
        return f"{status_name} {duration}t"
    if summary:
        return f"{status_name} [{summary}]"
    return status_name


def _active_status_summary(effects, *, max_names=1, title=False):
    if not effects or not isinstance(getattr(effects, "active", None), dict):
        return "0"
    active = list(effects.active.items())
    if not active:
        return "0"
    active.sort(key=lambda item: (-_int_or_default(item[1].get("remaining", 0), 0), str(item[0])))
    labels = [
        _humanize_slug(status, title=title) or ("Effect" if title else "effect")
        for status, _state in active
    ]
    max_names = max(1, int(max_names))
    if len(labels) <= max_names:
        return ", ".join(labels)
    visible = labels[:max_names]
    visible.append(f"+{len(labels) - max_names}")
    return " ".join(visible)


def _entity_status_move_speed_multiplier(sim, eid, *, base=1.0, minimum=0.2, maximum=3.0):
    try:
        speed = float(base)
    except (TypeError, ValueError):
        speed = 1.0

    return _status_multiplier(
        sim,
        eid,
        "move_speed_mult",
        base=speed,
        minimum=minimum,
        maximum=maximum,
    )
