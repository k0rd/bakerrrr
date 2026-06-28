"""Rare history-backed visible scars for surviving NPCs."""

from __future__ import annotations

import random

from engine.events import Event
from game.appearance_loadout import SKIN_MARK_SLOT_LABELS, appearance_loadout_for
from game.components import CreatureIdentity, Position, Vitality
from game.property_runtime import property_covering, property_metadata
from game.vision_scene_runtime import event_is_vision_only


_HISTORY_SCAR_SLOTS = (
    "left_cheek",
    "right_cheek",
    "chin",
    "neck",
    "left_forearm",
    "right_forearm",
    "left_hand",
    "right_hand",
    "left_brow",
    "right_brow",
    "collarline",
)

_DAMAGE_KIND_NOUNS = {
    "fire": "fire",
    "burn": "fire",
    "explosion": "blast",
    "explosive": "blast",
    "bullet": "shooting",
    "gunshot": "shooting",
    "projectile": "shooting",
    "melee": "fight",
    "blade": "fight",
    "armed_assault": "fight",
    "unarmed_assault": "fight",
}


def _text(value) -> str:
    return str(value or "").strip()


def _key(value) -> str:
    return _text(value).lower()


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _place_label(sim, x, y, z) -> str:
    prop = property_covering(sim, x, y, z) if sim is not None else None
    if isinstance(prop, dict):
        metadata = property_metadata(prop)
        return (
            _text(metadata.get("business_name"))
            or _text(prop.get("name"))
            or _text(prop.get("id"))
        )
    return ""


def _history_noun(damage_kind: str, context: str = "") -> str:
    for key in (_key(damage_kind), _key(context)):
        if key in _DAMAGE_KIND_NOUNS:
            return _DAMAGE_KIND_NOUNS[key]
    if "fire" in _key(damage_kind) or "burn" in _key(damage_kind):
        return "fire"
    if "explos" in _key(damage_kind):
        return "blast"
    if "gun" in _key(damage_kind) or "shot" in _key(damage_kind):
        return "shooting"
    return "trouble"


def _existing_history_scar(loadout) -> bool:
    for mark in dict(getattr(loadout, "skin_marks", {}) or {}).values():
        if not isinstance(mark, dict):
            continue
        if _key(mark.get("source")) == "incident_history" or bool(mark.get("history_named")):
            return True
    return False


def _available_slots(loadout) -> tuple[str, ...]:
    marks = dict(getattr(loadout, "skin_marks", {}) or {})
    slots = []
    for slot in _HISTORY_SCAR_SLOTS:
        mark = marks.get(slot)
        if not isinstance(mark, dict):
            slots.append(slot)
            continue
        if _key(mark.get("kind")) not in {"tattoo", "scar"}:
            slots.append(slot)
    return tuple(slots)


def maybe_record_named_scar_from_damage(sim, target_eid, event_or_data, *, force=False) -> dict:
    """Maybe add a tasteful, visible history scar to a surviving NPC."""

    if sim is None or target_eid is None or event_is_vision_only(event_or_data):
        return {"ok": False, "reason": "ineligible"}
    data = event_or_data if isinstance(event_or_data, dict) else getattr(event_or_data, "data", {})
    data = data if isinstance(data, dict) else {}
    try:
        target_eid = int(target_eid)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "bad_target"}
    if target_eid == getattr(sim, "player_eid", None):
        return {"ok": False, "reason": "player"}
    identity = sim.ecs.get(CreatureIdentity).get(target_eid)
    if identity is None or _key(getattr(identity, "taxonomy_class", "hominid")) != "hominid":
        return {"ok": False, "reason": "non_hominid"}
    vitality = sim.ecs.get(Vitality).get(target_eid)
    if vitality is not None and (
        bool(getattr(vitality, "dead", False))
        or bool(getattr(vitality, "downed", False))
        or _safe_int(getattr(vitality, "hp", 1), 1) <= 0
    ):
        return {"ok": False, "reason": "not_surviving"}
    damage = _safe_int(data.get("damage"), 0)
    damage_kind = _key(data.get("damage_kind") or data.get("context") or data.get("action"))
    if not force:
        if damage < 14 and damage_kind not in {"fire", "burn", "explosion", "explosive", "gunshot", "bullet"}:
            return {"ok": False, "reason": "minor_damage"}
        tick = _safe_int(getattr(sim, "tick", 0), 0)
        x = _safe_int(data.get("x"), -999999)
        y = _safe_int(data.get("y"), -999999)
        seed = f"{getattr(sim, 'seed', 0)}:named-scar:{target_eid}:{tick}:{damage}:{damage_kind}:{x}:{y}"
        chance = min(0.22, 0.035 + (max(0, damage - 12) * 0.012))
        if random.Random(seed).random() > chance:
            return {"ok": False, "reason": "rare_miss"}
    loadout = appearance_loadout_for(sim, target_eid, create=True)
    if loadout is None:
        return {"ok": False, "reason": "no_loadout"}
    if _existing_history_scar(loadout):
        return {"ok": False, "reason": "already_marked"}
    slots = _available_slots(loadout)
    if not slots:
        return {"ok": False, "reason": "no_slot"}
    pos = sim.ecs.get(Position).get(target_eid)
    x = _safe_int(data.get("x"), getattr(pos, "x", 0))
    y = _safe_int(data.get("y"), getattr(pos, "y", 0))
    z = _safe_int(data.get("z"), getattr(pos, "z", 0))
    place = _text(data.get("property_name")) or _place_label(sim, x, y, z)
    noun = _history_noun(damage_kind, data.get("context"))
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:named-scar-slot:{target_eid}:{damage_kind}:{x}:{y}:{z}")
    slot = slots[rng.randrange(len(slots))]
    label = SKIN_MARK_SLOT_LABELS.get(slot, slot.replace("_", " ")).lower()
    shape = rng.choice(("pale line", "thin scar", "silvered nick", "faint seam", "old mark"))
    if place:
        description = f"{shape} at the {label} from the {noun} at {place}"
    else:
        description = f"{shape} at the {label} from old {noun}"
    mark = {
        "kind": "scar",
        "slot": slot,
        "description": description,
        "self_phrase": description,
        "design": shape,
        "source": "incident_history",
        "history_named": True,
        "history_kind": noun,
        "history_place": place,
        "created_tick": _safe_int(getattr(sim, "tick", 0), 0),
    }
    loadout.skin_marks[slot] = mark
    if hasattr(loadout, "normalize"):
        loadout.normalize()
    try:
        sim.emit(Event(
            "named_scar_recorded",
            actor_eid=target_eid,
            slot=slot,
            description=description,
            history_kind=noun,
            history_place=place,
            x=x,
            y=y,
            z=z,
        ))
    except AttributeError:
        pass
    return {"ok": True, "slot": slot, "description": description, "history_kind": noun, "history_place": place}
