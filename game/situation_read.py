"""Skill-backed local situation and tactical reads."""

from __future__ import annotations

import math

from engine.events import Event
from engine.systems import System

from game.components import AI, CoverState, CreatureIdentity, NPCWill, Occupation, PlayerControlled, Position, SuppressionState, Vitality, WeaponLoadout
from game.property_keys import property_lock_state
from game.property_runtime import property_covering as _property_covering, property_is_public as _property_is_public, site_services_for_property as _site_services_for_property
from game.skills import actor_skill
from game.system_support.combat_targeting_runtime import _entity_visible_to_player, _target_condition_descriptor, _weapon_ammo_type_label, _weapon_reserve_ammo
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import _manhattan
from game.system_support.player_feedback import _log_player_feedback
from game.weapons import weapon_by_id


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _skill(sim, eid, skill_id):
    try:
        return float(actor_skill(sim, eid, skill_id))
    except Exception:
        return 5.0


def _dir_label(dx, dy, perception):
    dx = int(dx)
    dy = int(dy)
    if dx == 0 and dy == 0:
        return "here"
    angle = (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0
    if perception >= 8.5:
        names = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
        index = int((angle + 11.25) // 22.5) % 16
        return f"{names[index]} {int(round(angle))}deg"
    if perception >= 5.5:
        names = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        index = int((angle + 22.5) // 45.0) % 8
        return names[index]
    if abs(dx) >= abs(dy):
        return "east" if dx > 0 else "west"
    return "south" if dy > 0 else "north"


def _distance_label(dist, perception):
    dist = int(max(0, dist))
    if dist <= 0:
        return "here"
    if perception >= 6.0:
        return f"{dist}m"
    if dist <= 2:
        return "nearby"
    if dist <= 6:
        return "close"
    return "far"


def area_effect_radius_read(sim, eid, radius, *, tactics=None, effect_label="area effect"):
    radius = int(max(0, _int(radius, 0)))
    if tactics is None:
        tactics = _skill(sim, eid, "tactics") if sim is not None and eid is not None else 5.0
    try:
        tactics = float(tactics)
    except (TypeError, ValueError):
        tactics = 5.0

    if radius <= 1:
        size = "small"
    elif radius <= 3:
        size = "medium"
    else:
        size = "large"

    effect = str(effect_label or "area effect").strip().lower() or "area effect"
    if tactics >= 6.0:
        label = f"{effect} radius about {radius} m"
        precise = True
    else:
        label = f"{size} {effect}"
        precise = False
    return {
        "radius": int(radius),
        "size": size,
        "effect_label": effect,
        "label": label,
        "precise": bool(precise),
        "tactics": float(tactics),
    }


def blast_radius_read(sim, eid, radius, *, tactics=None):
    return area_effect_radius_read(sim, eid, radius, tactics=tactics, effect_label="blast")


def _actor_kind(sim, eid, perception):
    ais = sim.ecs.get(AI)
    ai = ais.get(eid) if ais else None
    identities = sim.ecs.get(CreatureIdentity)
    identity = identities.get(eid) if identities else None
    occupations = sim.ecs.get(Occupation)
    occupation = occupations.get(eid) if occupations else None

    if perception < 3.8:
        return "movement"
    role = str(getattr(ai, "role", "") or "").strip().lower().replace("_", " ")
    if role and role not in {"npc", "civilian"}:
        return role
    career = str(getattr(occupation, "career", "") or "").strip().lower().replace("_", " ")
    if perception >= 7.0 and career:
        return career
    if identity is not None and str(getattr(identity, "taxonomy_class", "") or "").strip().lower() != "hominid":
        return str(identity.display_name()).replace("_", " ").strip().lower() or "creature"
    return "person"


def _activity_read(sim, eid, streetwise):
    if streetwise < 4.0:
        return ""
    ai = sim.ecs.get(AI).get(eid)
    will = sim.ecs.get(NPCWill).get(eid)
    suppression = sim.ecs.get(SuppressionState).get(eid)
    if suppression and bool(getattr(suppression, "surrendered", False)):
        return "standing down"
    state = str(getattr(ai, "state", "") or "").strip().lower().replace("_", " ")
    intent = str(getattr(will, "intent", "") or "").strip().lower().replace("_", " ")
    if streetwise >= 7.0:
        if state in {"protecting", "chasing"} or intent in {"protecting", "chasing"}:
            return "moving like a threat"
        if state in {"investigating", "searching"} or intent in {"investigating", "searching"}:
            return "searching"
        if state == "following" or intent == "following":
            return "following someone"
        if state in {"holding", "guarding"}:
            return "holding position"
    if state and state not in {"idle", "npc"}:
        return state
    if intent and intent not in {"idle", "wander"}:
        return intent
    return ""


def _cover_source_label(sim, cover):
    source = getattr(cover, "source", None)
    if isinstance(source, (list, tuple)) and len(source) >= 3:
        sx, sy, sz = _int(source[0]), _int(source[1]), _int(source[2])
        prop = None
        try:
            prop = sim.property_at(sx, sy, sz) or _property_covering(sim, sx, sy, sz)
        except Exception:
            prop = None
        if isinstance(prop, dict):
            name = str(prop.get("name", "") or prop.get("kind", "") or "cover").strip()
            if name:
                return name.lower()
    kind = str(getattr(cover, "source_kind", "") or getattr(cover, "cover_kind", "") or "cover").strip().lower()
    return kind.replace("_", " ") or "cover"


def cover_read_phrase(sim, cover, *, tactical=5.0):
    if not cover or not bool(getattr(cover, "active", False)):
        return "exposed"
    value = max(0.0, min(0.95, float(getattr(cover, "cover_value", 0.0) or 0.0)))
    source = _cover_source_label(sim, cover)
    if tactical < 4.0:
        return f"behind {source}"
    if value >= 0.78:
        return f"mostly behind {source}"
    if value >= 0.52:
        return f"partially behind {source}"
    if value >= 0.28:
        return f"screened by {source}"
    return f"barely covered by {source}"


def _weapon_posture(sim, eid, tactics):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout or not callable(getattr(loadout, "current_weapon", None)):
        return ""
    weapon_id = loadout.current_weapon()
    if not weapon_id:
        return ""
    weapon = weapon_by_id(weapon_id)
    if not weapon:
        return ""
    name = str(weapon.get("name", weapon_id)).strip().lower()
    if tactics < 6.0:
        return "armed"
    try:
        rng = int(weapon.get("range", 1))
    except (TypeError, ValueError):
        rng = 1
    ammo = ""
    try:
        reserve = _weapon_reserve_ammo(loadout, weapon_id)
    except Exception:
        reserve = None
    if reserve is not None and tactics >= 8.0:
        ammo = f", {int(reserve)} {_weapon_ammo_type_label(weapon)}"
    return f"{name} range {rng}{ammo}"


def _actor_read(sim, player_eid, target_eid, player_pos, target_pos, *, tactical=False):
    perception = _skill(sim, player_eid, "perception")
    streetwise = _skill(sim, player_eid, "streetwise")
    tactics = _skill(sim, player_eid, "tactics")
    dx = int(target_pos.x) - int(player_pos.x)
    dy = int(target_pos.y) - int(player_pos.y)
    dist = _manhattan(player_pos.x, player_pos.y, target_pos.x, target_pos.y)
    kind = _actor_kind(sim, target_eid, perception)
    direction = _dir_label(dx, dy, perception)
    distance = _distance_label(dist, perception)
    bits = [f"{kind} {direction} {distance}"]
    activity = _activity_read(sim, target_eid, streetwise)
    if activity:
        bits.append(activity)
    if tactical:
        condition = _target_condition_descriptor(sim, player_eid, target_eid, include_uncertainty=True)
        if condition:
            bits.append(condition)
        cover = sim.ecs.get(CoverState).get(target_eid)
        bits.append(cover_read_phrase(sim, cover, tactical=tactics))
        weapon = _weapon_posture(sim, target_eid, tactics)
        if weapon:
            bits.append(weapon)
    return " ".join(bit for bit in bits if bit).strip(), bool(activity)


def _property_access_read(sim, prop, streetwise):
    try:
        lock = property_lock_state(prop)
    except Exception:
        lock = {}
    if bool(lock.get("locked")):
        return "locked"
    if streetwise < 4.0:
        return ""
    if _property_is_public(prop):
        services = tuple(_site_services_for_property(prop) or ())
        if services:
            return "service open"
        return "public"
    if streetwise >= 7.0:
        return "private/restricted"
    return "private"


def _property_read(sim, player_eid, prop, player_pos):
    perception = _skill(sim, player_eid, "perception")
    streetwise = _skill(sim, player_eid, "streetwise")
    px = _int(prop.get("x", player_pos.x))
    py = _int(prop.get("y", player_pos.y))
    dx = px - int(player_pos.x)
    dy = py - int(player_pos.y)
    dist = _manhattan(player_pos.x, player_pos.y, px, py)
    if perception < 4.0:
        kind = "place"
    else:
        kind = str(prop.get("archetype", "") or prop.get("kind", "") or "place").strip().lower().replace("_", " ")
        if perception >= 7.0:
            kind = str(prop.get("name", "") or kind).strip()
    access = _property_access_read(sim, prop, streetwise)
    text = f"{kind} {_dir_label(dx, dy, perception)} {_distance_label(dist, perception)}"
    if access:
        text += f" {access}"
    return text.strip(), bool(access)


def _visible_actor_rows(sim, player_eid, player_pos, *, radius=12):
    rows = []
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    players = sim.ecs.get(PlayerControlled)
    for eid, pos in positions.items():
        if eid == player_eid or players.get(eid):
            continue
        if not ais.get(eid) or int(pos.z) != int(player_pos.z):
            continue
        dist = _manhattan(player_pos.x, player_pos.y, pos.x, pos.y)
        if dist > radius:
            continue
        try:
            if not _entity_visible_to_player(sim, player_eid, eid):
                continue
        except Exception:
            pass
        rows.append((dist, int(eid), pos))
    rows.sort(key=lambda row: (int(row[0]), int(row[1])))
    return rows


def _nearby_property_rows(sim, player_pos, *, radius=10):
    rows = []
    for prop_id, prop in sorted(getattr(sim, "properties", {}).items(), key=lambda row: str(row[0])):
        if not isinstance(prop, dict):
            continue
        if _int(prop.get("z", 0)) != int(player_pos.z):
            continue
        px = _int(prop.get("x", player_pos.x))
        py = _int(prop.get("y", player_pos.y))
        try:
            if sim.detail_for_xy(px, py) == "unloaded":
                continue
        except Exception:
            pass
        dist = _manhattan(player_pos.x, player_pos.y, px, py)
        if dist <= radius:
            rows.append((dist, str(prop_id), prop))
    rows.sort(key=lambda row: (int(row[0]), str(row[1])))
    return rows


def build_situation_read(sim, player_eid, *, tactical=False, target=None):
    positions = sim.ecs.get(Position)
    player_pos = positions.get(player_eid)
    if not player_pos:
        return {"text": "Read: no position", "signature": "missing-position", "meaningful": False}

    perception = _skill(sim, player_eid, "perception")
    streetwise = _skill(sim, player_eid, "streetwise")
    tactics = _skill(sim, player_eid, "tactics")
    slot_limit = 1 if perception < 4.0 else (2 if perception < 6.0 else (3 if perception < 8.0 else 4))
    prefix = "Tactical" if tactical else "Read"
    perception_access = (
        str(target.get("perception_access", "") or "").strip().lower()
        if isinstance(target, dict)
        else ""
    )
    if perception_access in {"remembered", "unknown"}:
        text = f"{prefix}: no current visual read at that cursor"
        return {
            "text": text,
            "signature": f"{('t' if tactical else 'r')}::cursor::{perception_access}",
            "meaningful": False,
            "has_streetwise": False,
            "has_tactics": bool(tactical),
        }
    entries = []
    has_streetwise = False
    has_tactics = bool(tactical)

    if isinstance(target, dict) and target.get("target_eid") is not None:
        target_eid = target.get("target_eid")
        target_pos = positions.get(target_eid)
        if target_pos:
            text, sw = _actor_read(sim, player_eid, target_eid, player_pos, target_pos, tactical=tactical)
            entries.append(text)
            has_streetwise = has_streetwise or sw
    elif isinstance(target, dict) and target.get("x") is not None and target.get("y") is not None:
        tx = _int(target.get("x"))
        ty = _int(target.get("y"))
        tz = _int(target.get("z"), player_pos.z)
        for eid in sim.tilemap.entities_at(tx, ty, tz):
            if eid == player_eid:
                continue
            text, sw = _actor_read(sim, player_eid, eid, player_pos, positions.get(eid), tactical=tactical) if positions.get(eid) else ("", False)
            if text:
                entries.append(text)
                has_streetwise = has_streetwise or sw
                break
        if not entries:
            prop = _property_covering(sim, tx, ty, tz)
            if isinstance(prop, dict):
                text, sw = _property_read(sim, player_eid, prop, player_pos)
                entries.append(text)
                has_streetwise = has_streetwise or sw

    if not entries:
        for _dist, eid, pos in _visible_actor_rows(sim, player_eid, player_pos)[:slot_limit]:
            text, sw = _actor_read(sim, player_eid, eid, player_pos, pos, tactical=tactical)
            if text:
                entries.append(text)
                has_streetwise = has_streetwise or sw
        remaining = max(0, slot_limit - len(entries))
        if remaining:
            for _dist, _prop_id, prop in _nearby_property_rows(sim, player_pos)[:remaining]:
                text, sw = _property_read(sim, player_eid, prop, player_pos)
                if text:
                    entries.append(text)
                    has_streetwise = has_streetwise or sw

    if tactical:
        cover = sim.ecs.get(CoverState).get(player_eid)
        overlay = getattr(sim, "combat_overlay", {}) if isinstance(getattr(sim, "combat_overlay", {}), dict) else {}
        threat_count = int(overlay.get("threat_count", 0) or 0)
        exposure = float(overlay.get("player_exposure", getattr(cover, "exposure", 1.0) if cover else 1.0) or 1.0)
        tactical_bits = [cover_read_phrase(sim, cover, tactical=tactics)]
        if threat_count:
            tactical_bits.append(f"{threat_count} threat{'s' if threat_count != 1 else ''}")
        if tactics >= 6.0:
            tactical_bits.append(f"exposure {int(round(exposure * 100.0))}%")
        entries.append(", ".join(tactical_bits))
        has_tactics = True

    if not entries:
        text = f"{prefix}: quiet nearby"
    else:
        text = f"{prefix}: " + "; ".join(entries[:slot_limit + (1 if tactical else 0)])
    if not tactical and perception < 4.0:
        text += " (uncertain)"

    signature_bits = [
        "t" if tactical else "r",
        str(int(perception * 10)),
        str(int(streetwise * 10)),
        str(int(tactics * 10)),
        "|".join(entries[:5]),
    ]
    return {
        "text": text,
        "signature": "::".join(signature_bits),
        "meaningful": bool(entries),
        "has_streetwise": bool(has_streetwise),
        "has_tactics": bool(has_tactics),
    }


def build_focus_read(sim, player_eid, x, y, z, *, purpose="inspect"):
    target = {"x": int(x), "y": int(y), "z": int(z)}
    tactical = str(purpose or "").strip().lower() == "aim"
    result = build_situation_read(sim, player_eid, tactical=tactical, target=target)
    text = str(result.get("text", "") or "").strip()
    if not text:
        return ""
    if text.lower().startswith("tactical:"):
        return "read:" + text[len("tactical:"):].strip()
    if text.lower().startswith("read:"):
        return "read:" + text[len("read:"):].strip()
    return "read:" + text


def perform_tactical_read(sim, player_eid, *, target=None, purpose=""):
    result = build_situation_read(sim, player_eid, tactical=True, target=target)
    text = str(result.get("text", "") or "Tactical: nothing clear").strip()
    perception_access = (
        str(target.get("perception_access", "visible") or "visible").strip().lower()
        if isinstance(target, dict)
        else "visible"
    )
    state = {
        "text": text,
        "tick": int(getattr(sim, "tick", 0)),
        "signature": str(result.get("signature", "") or ""),
        "target": dict(target or {}) if isinstance(target, dict) else {},
        "purpose": str(purpose or "").strip().lower(),
    }
    sim.tactical_read_ui = state
    sim.situation_read_state = {
        "text": text,
        "tick": int(getattr(sim, "tick", 0)),
        "signature": str(result.get("signature", "") or ""),
        "meaningful": bool(result.get("meaningful", False)),
        "has_streetwise": bool(result.get("has_streetwise", False)),
        "has_tactics": True,
    }
    sim.emit(Event(
        "tactical_read_performed",
        eid=player_eid,
        text=text,
        signature=state["signature"],
        purpose=state["purpose"],
        has_streetwise=bool(result.get("has_streetwise", False)),
        meaningful=bool(result.get("meaningful", False)),
        perception_access=perception_access,
    ))
    _log_player_feedback(
        sim,
        text,
        kind="interaction",
        dedupe_key=f"tactical_read:{state['signature']}",
        dedupe_window=2,
    )
    return state


class SituationReadSystem(System):
    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.runs_without_turn = True

    def update(self):
        tick = int(getattr(self.sim, "tick", 0))
        tactical_ui = getattr(self.sim, "tactical_read_ui", None)
        if isinstance(tactical_ui, dict) and tick - int(tactical_ui.get("tick", -10_000) or -10_000) <= 1:
            return

        previous = getattr(self.sim, "situation_read_state", None)
        previous_signature = str((previous or {}).get("signature", "") if isinstance(previous, dict) else "")
        result = build_situation_read(self.sim, self.player_eid, tactical=False)
        state = {
            "text": str(result.get("text", "") or ""),
            "tick": tick,
            "signature": str(result.get("signature", "") or ""),
            "meaningful": bool(result.get("meaningful", False)),
            "has_streetwise": bool(result.get("has_streetwise", False)),
            "has_tactics": False,
        }
        self.sim.situation_read_state = state
        if state["signature"] and state["signature"] != previous_signature:
            self.sim.emit(Event(
                "situation_read_changed",
                eid=self.player_eid,
                text=state["text"],
                signature=state["signature"],
                meaningful=state["meaningful"],
                has_streetwise=state["has_streetwise"],
            ))
