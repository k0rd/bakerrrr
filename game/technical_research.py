"""Persistent technical research recovered from wire data packets."""

from __future__ import annotations

from collections.abc import Mapping


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _actor_state(sim, actor_eid, *, create=False):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        if not create:
            return None
        traits = {}
        sim.world_traits = traits
    root = traits.get("technical_research")
    if not isinstance(root, dict):
        if not create:
            return None
        root = {"schema_version": 1, "actors": {}}
        traits["technical_research"] = root
    actors = root.get("actors")
    if not isinstance(actors, dict):
        actors = {}
        root["actors"] = actors
    actor_key = str(_int(actor_eid, 0))
    state = actors.get(actor_key)
    if not isinstance(state, dict):
        if not create:
            return None
        state = {"unlocks": {}}
        actors[actor_key] = state
    if not isinstance(state.get("unlocks"), dict):
        state["unlocks"] = {}
    return state


def technical_research_unlock_key(record):
    if not isinstance(record, Mapping):
        return ""
    target_kind = _key(record.get("research_target_kind"))
    target_item_id = _key(record.get("research_target_item_id"))
    effect_key = _key(record.get("research_effect_key"))
    if not target_kind or not target_item_id or not effect_key:
        return ""
    return f"{target_kind}:{target_item_id}:{effect_key}"


def record_technical_research(sim, actor_eid, record):
    key = technical_research_unlock_key(record)
    if not key:
        return {"ok": False, "reason": "not_technical_research"}
    state = _actor_state(sim, actor_eid, create=True)
    unlocks = state["unlocks"]
    if key in unlocks:
        return {"ok": False, "reason": "research_already_known", "key": key, "record": dict(unlocks[key])}
    clean = {
        "key": key,
        "target_kind": _key(record.get("research_target_kind")),
        "target_item_id": _key(record.get("research_target_item_id")),
        "target_name": _text(record.get("subject_name")),
        "effect_key": _key(record.get("research_effect_key")),
        "effect_delta": _int(record.get("research_effect_delta"), 0),
        "effect_label": _text(record.get("research_effect_label")),
        "learned_tick": _int(getattr(sim, "tick", 0), 0),
        "source_property_id": _text(record.get("source_property_id")),
        "source_property_name": _text(record.get("source_property_name")),
    }
    unlocks[key] = clean
    return {"ok": True, "reason": None, "key": key, "record": dict(clean)}


def technical_research_rows(sim, actor_eid, *, target_kind="", target_item_id=""):
    state = _actor_state(sim, actor_eid, create=False)
    if not state:
        return ()
    kind = _key(target_kind)
    item_id = _key(target_item_id)
    rows = []
    for row in state.get("unlocks", {}).values():
        if not isinstance(row, Mapping):
            continue
        if kind and _key(row.get("target_kind")) != kind:
            continue
        if item_id and _key(row.get("target_item_id")) != item_id:
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: (row.get("target_kind", ""), row.get("target_item_id", ""), row.get("effect_key", "")))
    return tuple(rows)


def _base_profile(item_id, target_kind, *, item_catalog=None):
    if item_catalog is None:
        from game.items import ITEM_CATALOG

        item_catalog = ITEM_CATALOG
    item = item_catalog.get(_key(item_id), {}) if isinstance(item_catalog, dict) else {}
    if target_kind == "drone_module":
        return dict(item.get("drone_profile") or {}) if isinstance(item, dict) else {}
    if target_kind == "wire_program":
        return dict(item.get("wire_profile") or {}) if isinstance(item, dict) else {}
    if target_kind == "wire_interface":
        return dict(item.get("wire_interface_profile") or {}) if isinstance(item, dict) else {}
    return {}


def apply_technical_research_to_entry(sim, actor_eid, entry, *, item_catalog=None):
    if not isinstance(entry, dict):
        return False
    item_id = _key(entry.get("item_id"))
    if not item_id:
        return False
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        entry["metadata"] = metadata
    applied = metadata.get("applied_technical_research")
    if not isinstance(applied, list):
        applied = list(applied or ()) if isinstance(applied, (tuple, set)) else []
        metadata["applied_technical_research"] = applied

    changed = False
    for row in technical_research_rows(sim, actor_eid, target_item_id=item_id):
        unlock_key = _text(row.get("key"))
        if not unlock_key or unlock_key in applied:
            continue
        target_kind = _key(row.get("target_kind"))
        effect_key = _key(row.get("effect_key"))
        delta = _int(row.get("effect_delta"), 0)
        profile = _base_profile(item_id, target_kind, item_catalog=item_catalog)
        if target_kind == "drone_module":
            overrides = metadata.get("research_profile_overrides")
            if not isinstance(overrides, dict):
                overrides = {}
                metadata["research_profile_overrides"] = overrides
            current = _int(overrides.get(effect_key), _int(profile.get(effect_key), 0))
            value = current + delta
            if effect_key in {"active_draw", "standby_draw", "weight", "sensor_power_cost"}:
                value = max(0, value)
            elif effect_key == "sensor_range":
                value = max(1, value)
            overrides[effect_key] = value
        else:
            current = _int(metadata.get(effect_key), _int(profile.get(effect_key), 0))
            value = current + delta
            if effect_key in {"noise", "trace_cost", "reload_ticks", "noise_floor", "buffer_size"}:
                value = max(0, value)
            if effect_key in {"trace_resistance", "warning_rating"}:
                value = max(0, min(5, value))
            metadata[effect_key] = value
            if effect_key == "durability_max":
                metadata["durability"] = max(0, _int(metadata.get("durability"), current)) + max(0, delta)
        applied.append(unlock_key)
        changed = True
    return changed


def drone_module_profile_with_research(module, *, item_catalog=None):
    if not isinstance(module, Mapping):
        return {}
    item_id = _key(module.get("item_id") or module.get("module_item_id"))
    profile = _base_profile(item_id, "drone_module", item_catalog=item_catalog)
    metadata = module.get("metadata") if isinstance(module.get("metadata"), Mapping) else {}
    overrides = metadata.get("research_profile_overrides") if isinstance(metadata, Mapping) else {}
    if isinstance(overrides, Mapping):
        profile.update({str(key): value for key, value in overrides.items()})
    return profile
