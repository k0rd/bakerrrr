"""Module-backed combat helpers for deployed drones."""

from __future__ import annotations

from engine.events import Event

from game.components import (
    ArmorLoadout,
    Collider,
    CoverState,
    DroneState,
    Position,
    Render,
    Vitality,
)
from game.drone_recon import drone_has_camera_sensor, linked_camera_status
from game.drone_runtime import (
    drone_profile_for_item,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
)
from game.system_support.actor_runtime import _apply_downed_actor_state
from game.system_support.combat_targeting_runtime import (
    _entity_is_weapon_targetable,
    _first_targetable_entity_at,
    _weapon_target_viability,
)
from game.system_support.cover_runtime import _effective_cover_value
from game.system_support.entity_naming import _entity_display_name
from game.system_support.fire_runtime import upsert_fire_cell
from game.system_support.interaction_ordering import _manhattan
from game.system_support.offense_runtime import (
    ACTION_OFFENSE_BASE,
    ACTION_OFFENSE_CONTEXT_BONUS,
    _offense_notice_radius,
    _offense_tier,
)
from game.system_support.status_runtime import _status_modifier_total, _status_multiplier


DRONE_PISTOL_MODULE_ID = "drone_pistol_module"
DRONE_AMMO_RACK_MODULE_ID = "drone_ammo_rack_module"
DRONE_FLAME_NOZZLE_MODULE_ID = "drone_flame_nozzle_module"
DRONE_FUEL_TANK_MODULE_ID = "drone_fuel_tank_module"

DRONE_WEAPON_SPECS = {
    "pistol": {
        "weapon_id": "drone_pistol_module",
        "module_id": DRONE_PISTOL_MODULE_ID,
        "resource_module_id": DRONE_AMMO_RACK_MODULE_ID,
        "resource_key": "ammo_count",
        "resource_label": "ammo",
        "resource_default": 6,
        "resource_max": 6,
        "range": 5,
        "damage": 5,
        "cooldown": 2,
        "battery_cost": 4,
        "damage_kind": "ballistic",
        "trajectory": "ballistic",
    },
    "flame": {
        "weapon_id": "drone_flame_nozzle_module",
        "module_id": DRONE_FLAME_NOZZLE_MODULE_ID,
        "resource_module_id": DRONE_FUEL_TANK_MODULE_ID,
        "resource_key": "fuel_charge",
        "resource_label": "fuel",
        "resource_default": 3,
        "resource_max": 3,
        "range": 2,
        "damage": 6,
        "cooldown": 3,
        "battery_cost": 5,
        "damage_kind": "fire",
        "trajectory": "ballistic",
    },
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clean(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _deployed_state(sim, drone_eid):
    state = sim.ecs.get(DroneState).get(drone_eid)
    if state is None:
        return None
    if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
        return None
    return state


def _module_entries(state, item_id):
    item_id = str(item_id or "").strip().lower()
    if not item_id:
        return []
    return [
        module
        for module in list(getattr(state, "modules", ()) or ())
        if isinstance(module, dict)
        and str(module.get("item_id", "") or "").strip().lower() == item_id
    ]


def _module_by_id(state, item_id):
    rows = _module_entries(state, item_id)
    return rows[0] if rows else None


def _module_metadata(module):
    if not isinstance(module, dict):
        return {}
    metadata = module.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        module["metadata"] = metadata
    return metadata


def _sync_modules_metadata(state):
    if state is None:
        return
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    metadata["modules"] = [
        dict(module)
        for module in (getattr(state, "modules", None) or ())
        if isinstance(module, dict)
    ]
    metadata["battery_charge"] = int(max(0, _int(getattr(state, "battery_charge", 0), 0)))


def _weapon_cooldowns(state):
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    cooldowns = metadata.get("weapon_cooldowns")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        metadata["weapon_cooldowns"] = cooldowns
    return cooldowns


def weapon_cooldown_remaining(state, weapon_kind, *, tick=0):
    cooldowns = _weapon_cooldowns(state)
    ready_at = _int(cooldowns.get(str(weapon_kind or "").strip().lower()), 0)
    return int(max(0, ready_at - int(tick or 0)))


def tick_drone_weapon_cooldowns(state, *, tick=0):
    cooldowns = _weapon_cooldowns(state)
    changed = False
    for key, value in list(cooldowns.items()):
        ready_at = _int(value, 0)
        if ready_at <= int(tick or 0):
            cooldowns.pop(key, None)
            changed = True
    return changed


def _set_weapon_cooldown(state, weapon_kind, cooldown, *, tick=0):
    cooldowns = _weapon_cooldowns(state)
    cooldowns[str(weapon_kind or "").strip().lower()] = int(tick or 0) + int(max(1, cooldown))


def _resource_amount(state, spec, *, initialize=False):
    module = _module_by_id(state, spec["resource_module_id"])
    if module is None:
        return None
    metadata = _module_metadata(module)
    key = spec["resource_key"]
    max_value = int(spec["resource_max"])
    if key not in metadata:
        if initialize:
            metadata[key] = int(spec["resource_default"])
        return int(spec["resource_default"])
    value = _int(metadata.get(key), spec["resource_default"])
    value = int(max(0, min(max_value, value)))
    if initialize:
        metadata[key] = value
    return value


def _weapon_ready_rows(state, *, item_catalog=None, tick=0):
    rows = []
    for weapon_kind, spec in DRONE_WEAPON_SPECS.items():
        weapon_module = _module_by_id(state, spec["module_id"])
        resource_module = _module_by_id(state, spec["resource_module_id"])
        installed = weapon_module is not None and resource_module is not None
        rows.append({
            "weapon_kind": weapon_kind,
            "installed": bool(installed),
            "weapon_module_id": spec["module_id"],
            "resource_module_id": spec["resource_module_id"],
            "resource_label": spec["resource_label"],
            "resource_amount": _resource_amount(state, spec, initialize=False) if resource_module is not None else None,
            "range": int(spec["range"]),
            "damage": int(spec["damage"]),
            "battery_cost": int(spec["battery_cost"]),
            "cooldown": int(spec["cooldown"]),
            "cooldown_remaining": weapon_cooldown_remaining(state, weapon_kind, tick=tick),
            "profile": drone_profile_for_item(spec["module_id"], item_catalog=item_catalog),
        })
    return rows


def drone_weapon_status(state, *, item_catalog=None, tick=0):
    rows = _weapon_ready_rows(state, item_catalog=item_catalog, tick=tick)
    armed = [row for row in rows if row.get("installed")]
    return {
        "armed": bool(armed),
        "weapons": tuple(rows),
        "primary_weapon": armed[0]["weapon_kind"] if armed else None,
    }


def _block(sim, controller_eid, drone_eid, reason, *, weapon_kind=None, target_eid=None, x=None, y=None, z=None):
    reason = str(reason or "blocked").strip().lower() or "blocked"
    sim.emit(Event(
        "drone_weapon_blocked",
        eid=controller_eid,
        controller_eid=controller_eid,
        responsible_eid=controller_eid,
        drone_eid=drone_eid,
        weapon_kind=str(weapon_kind or "").strip().lower(),
        target_eid=target_eid,
        reason=reason,
        x=x,
        y=y,
        z=z,
    ))
    return {"ok": False, "reason": reason, "weapon_kind": weapon_kind}


def _resolve_weapon_kind(state, weapon_kind):
    requested = str(weapon_kind or "").strip().lower()
    if requested in {"", "auto", "weapon"}:
        status = drone_weapon_status(state)
        return status.get("primary_weapon") or "pistol"
    if requested in DRONE_WEAPON_SPECS:
        return requested
    return requested


def _target_for_fire(sim, drone_eid, target_eid=None, target_x=None, target_y=None, target_z=None):
    positions = sim.ecs.get(Position)
    if target_eid is not None:
        target_pos = positions.get(target_eid)
        if target_pos is None:
            return None, "missing_target"
        return (
            int(target_eid),
            int(target_pos.x),
            int(target_pos.y),
            int(target_pos.z),
        ), None
    if target_x is None or target_y is None:
        return None, "missing_target"
    try:
        tx = int(target_x)
        ty = int(target_y)
        tz = int(0 if target_z is None else target_z)
    except (TypeError, ValueError):
        return None, "invalid_target"
    target_eid = _first_targetable_entity_at(
        sim,
        tx,
        ty,
        tz,
        exclude_eid=drone_eid,
        current_tick=getattr(sim, "tick", None),
    )
    if target_eid is None:
        return None, "no_target"
    return (int(target_eid), tx, ty, tz), None


def _fire_camera_visible(sim, controller_eid, drone_eid, target_x, target_y, target_z, *, item_catalog=None):
    status = linked_camera_status(sim, controller_eid, drone_eid, item_catalog=item_catalog)
    if not bool(status.get("ok")):
        return False, str(status.get("reason", "camera_unavailable") or "camera_unavailable")
    return (int(target_x), int(target_y), int(target_z)) in set(status.get("visible", set()) or set()), "no_camera_los"


def _damage_entity_from_drone(sim, target_eid, source_eid, weapon_id, raw_damage, x, y, z, *, damage_kind):
    vitalities = sim.ecs.get(Vitality)
    vitality = vitalities.get(target_eid)
    if vitality is None:
        return False
    if bool(getattr(vitality, "downed", False)):
        return False

    armor_loadouts = sim.ecs.get(ArmorLoadout)
    covers = sim.ecs.get(CoverState)
    positions = sim.ecs.get(Position)
    colliders = sim.ecs.get(Collider)
    renders = sim.ecs.get(Render)

    source_pos = positions.get(source_eid)
    target_pos = positions.get(target_eid)
    cover_absorb = 0.0
    if source_pos and target_pos and int(source_pos.z) == int(target_pos.z):
        cover = covers.get(target_eid)
        if cover and cover.active:
            cover_absorb = _effective_cover_value(
                cover,
                target_pos.x,
                target_pos.y,
                source_pos.x,
                source_pos.y,
            )
    cover_absorb = max(0.0, min(0.95, cover_absorb + _status_modifier_total(sim, target_eid, "cover_absorb_bonus", default=0.0)))

    armor_absorb = 0.0
    armor_name = None
    armor = armor_loadouts.get(target_eid)
    if armor and armor.equipped_instance_id:
        armor_absorb = max(0.0, min(0.85, float(armor.damage_reduction)))
        armor_name = _clean(armor.equipped_name or armor.equipped_item_id) or None
    armor_absorb = max(0.0, min(0.9, armor_absorb + _status_modifier_total(sim, target_eid, "armor_absorb_bonus", default=0.0)))

    previous_hp = int(max(0, getattr(vitality, "hp", 0) or 0))
    raw_damage = int(max(1, raw_damage))
    incoming_damage_mult = _status_multiplier(sim, target_eid, "incoming_damage_mult", minimum=0.2, maximum=3.0)
    final_damage = int(max(1, round(raw_damage * (1.0 - cover_absorb) * (1.0 - armor_absorb) * incoming_damage_mult)))
    vitality.hp = max(0, int(vitality.hp) - final_damage)

    sim.emit(Event(
        "entity_damaged",
        target_eid=target_eid,
        source_eid=source_eid,
        weapon_id=weapon_id,
        damage_kind=damage_kind,
        raw_damage=raw_damage,
        damage=final_damage,
        cover_absorb=round(cover_absorb, 3),
        armor_absorb=round(armor_absorb, 3),
        armor_name=armor_name,
        hp=vitality.hp,
        max_hp=vitality.max_hp,
        x=x,
        y=y,
        z=z,
    ))

    if vitality.hp > 0:
        return True

    drone_state = sim.ecs.get(DroneState).get(target_eid)
    if drone_state is not None and str(getattr(drone_state, "mode", "") or "").strip().lower() == "deployed":
        from game.drone_system import destroy_deployed_drone

        destroy_deployed_drone(
            sim,
            target_eid,
            source_eid=source_eid,
            reason="lethal_drone_weapon",
            damage_kind=damage_kind,
            damage_amount=final_damage,
            overkill_amount=max(0, int(final_damage) - int(previous_hp)),
        )
        return True

    vitality.downed_count += 1
    setattr(vitality, "last_attacker_eid", source_eid)
    if target_eid == getattr(sim, "player_eid", None):
        vitality.downed = True
        vitality.downed_tick = int(getattr(sim, "tick", 0) or 0)
        setattr(vitality, "death_reason", "bled_out")
        setattr(vitality, "death_reported_tick", None)
        sim.emit(Event(
            "player_downed",
            target_eid=target_eid,
            source_eid=source_eid,
            weapon_id=weapon_id,
            reason="lethal_damage",
            bleedout_ticks=8,
            bleedout_at_tick=int(getattr(sim, "tick", 0) or 0) + 8,
            damage_kind=damage_kind,
            x=x,
            y=y,
            z=z,
        ))
        return True

    vitality.downed = True
    vitality.downed_tick = int(getattr(sim, "tick", 0) or 0)
    setattr(vitality, "death_reason", "bled_out")
    _apply_downed_actor_state(sim, target_eid, tick=getattr(sim, "tick", 0))
    collider = colliders.get(target_eid)
    if collider:
        collider.blocks = False
    render = renders.get(target_eid)
    if render:
        render.glyph = "x"
    sim.emit(Event(
        "npc_downed",
        target_eid=target_eid,
        source_eid=source_eid,
        weapon_id=weapon_id,
        x=x,
        y=y,
        z=z,
    ))
    return True


def _emit_action_offense(sim, responsible_eid, drone_eid, target_eid, weapon_kind, x, y, z, tx, ty, tz):
    if responsible_eid is None:
        return
    context = "arson" if weapon_kind == "flame" else "armed_assault"
    action = "drone_weapon_fire"
    base = int(ACTION_OFFENSE_BASE.get("fire_weapon", 8))
    score = base + int(ACTION_OFFENSE_CONTEXT_BONUS.get(context, 0))
    target_name = _entity_display_name(sim, target_eid, title_case=False) or ""
    target_prop = sim.property_covering(tx, ty, tz) if hasattr(sim, "property_covering") else None
    sim.emit(Event(
        "action_offense",
        eid=responsible_eid,
        actor_eid=responsible_eid,
        responsible_eid=responsible_eid,
        source_eid=drone_eid,
        source_drone_eid=drone_eid,
        action=action,
        context=context,
        tier=_offense_tier(score),
        score=score,
        notice_radius=_offense_notice_radius(score),
        x=x,
        y=y,
        z=z,
        target_eid=target_eid,
        victim_eid=target_eid,
        victim_name=target_name,
        target_name=target_name,
        target_x=tx,
        target_y=ty,
        target_z=tz,
        property_id=(target_prop or {}).get("id"),
        property_name=(target_prop or {}).get("name"),
        drone_weapon_kind=weapon_kind,
    ))


def fire_drone_weapon(
    sim,
    controller_eid,
    drone_eid,
    *,
    target_eid=None,
    target_x=None,
    target_y=None,
    target_z=None,
    weapon_kind="auto",
    require_remote=True,
    require_camera=True,
    consume_turn=False,
    item_catalog=None,
):
    state = _deployed_state(sim, drone_eid)
    weapon_kind = _resolve_weapon_kind(state, weapon_kind) if state is not None else str(weapon_kind or "auto").strip().lower()
    spec = DRONE_WEAPON_SPECS.get(weapon_kind)
    pos = sim.ecs.get(Position).get(drone_eid)
    if state is None:
        return _block(sim, controller_eid, drone_eid, "not_deployed", weapon_kind=weapon_kind)
    if pos is None:
        return _block(sim, controller_eid, drone_eid, "missing_position", weapon_kind=weapon_kind)
    if spec is None:
        return _block(sim, controller_eid, drone_eid, "unknown_weapon", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    if not drone_state_controlled_by_actor(state, controller_eid):
        return _block(sim, controller_eid, drone_eid, "not_controller", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    if require_remote and not drone_state_has_capability(state, "remote_control", item_catalog=item_catalog):
        return _block(sim, controller_eid, drone_eid, "no_remote_control", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    if require_camera and not drone_has_camera_sensor(state, item_catalog=item_catalog):
        return _block(sim, controller_eid, drone_eid, "no_camera", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    if _module_by_id(state, spec["module_id"]) is None:
        return _block(sim, controller_eid, drone_eid, "missing_weapon", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    resource_module = _module_by_id(state, spec["resource_module_id"])
    if resource_module is None:
        return _block(sim, controller_eid, drone_eid, f"missing_{spec['resource_label']}", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    if int(getattr(state, "battery_charge", 0) or 0) < int(spec["battery_cost"]):
        return _block(sim, controller_eid, drone_eid, "battery_depleted", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    cooldown_remaining = weapon_cooldown_remaining(state, weapon_kind, tick=int(getattr(sim, "tick", 0) or 0))
    if cooldown_remaining > 0:
        return _block(sim, controller_eid, drone_eid, "cooldown", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)
    resource_amount = _resource_amount(state, spec, initialize=True)
    if resource_amount is None or resource_amount <= 0:
        return _block(sim, controller_eid, drone_eid, f"{spec['resource_label']}_depleted", weapon_kind=weapon_kind, x=pos.x, y=pos.y, z=pos.z)

    target, reason = _target_for_fire(
        sim,
        drone_eid,
        target_eid=target_eid,
        target_x=target_x,
        target_y=target_y,
        target_z=target_z if target_z is not None else getattr(pos, "z", 0),
    )
    if reason:
        return _block(sim, controller_eid, drone_eid, reason, weapon_kind=weapon_kind, x=getattr(pos, "x", None), y=getattr(pos, "y", None), z=getattr(pos, "z", None))
    target_eid, tx, ty, tz = target
    if not _entity_is_weapon_targetable(sim, target_eid, current_tick=getattr(sim, "tick", None)):
        return _block(sim, controller_eid, drone_eid, "invalid_target", weapon_kind=weapon_kind, target_eid=target_eid, x=tx, y=ty, z=tz)

    if require_camera:
        visible, camera_reason = _fire_camera_visible(
            sim,
            controller_eid,
            drone_eid,
            tx,
            ty,
            tz,
            item_catalog=item_catalog,
        )
        if not visible:
            return _block(sim, controller_eid, drone_eid, camera_reason, weapon_kind=weapon_kind, target_eid=target_eid, x=tx, y=ty, z=tz)

    weapon_shape = {"range": int(spec["range"]), "trajectory": spec["trajectory"]}
    viability = _weapon_target_viability(
        sim,
        drone_eid,
        pos,
        weapon_shape,
        tx,
        ty,
        tz,
        target_eid=target_eid,
    )
    if not bool(viability.get("ok")):
        return _block(
            sim,
            controller_eid,
            drone_eid,
            viability.get("reason", "blocked_line"),
            weapon_kind=weapon_kind,
            target_eid=target_eid,
            x=tx,
            y=ty,
            z=tz,
        )

    resource_metadata = _module_metadata(resource_module)
    resource_metadata[spec["resource_key"]] = max(0, int(resource_amount) - 1)
    state.battery_charge = max(0, int(getattr(state, "battery_charge", 0) or 0) - int(spec["battery_cost"]))
    _set_weapon_cooldown(state, weapon_kind, int(spec["cooldown"]), tick=int(getattr(sim, "tick", 0) or 0))
    state.last_command = "fire"
    state.target_eid = target_eid
    state.target = (int(tx), int(ty), int(tz))
    _sync_modules_metadata(state)

    hit = _damage_entity_from_drone(
        sim,
        target_eid,
        drone_eid,
        spec["weapon_id"],
        int(spec["damage"]),
        tx,
        ty,
        tz,
        damage_kind=spec["damage_kind"],
    )
    if weapon_kind == "flame" and hit:
        upsert_fire_cell(
            sim,
            tx,
            ty,
            tz,
            fire_intensity=2,
            source_kind="drone_flame",
            source_eid=drone_eid,
        )
    responsible_eid = getattr(state, "controller_eid", None) or getattr(state, "owner_eid", None) or controller_eid
    _emit_action_offense(sim, responsible_eid, drone_eid, target_eid, weapon_kind, pos.x, pos.y, pos.z, tx, ty, tz)
    sim.emit(Event(
        "drone_weapon_fired",
        eid=controller_eid,
        controller_eid=controller_eid,
        responsible_eid=responsible_eid,
        owner_eid=getattr(state, "owner_eid", None),
        drone_eid=drone_eid,
        chassis_class=getattr(state, "chassis_class", None),
        weapon_kind=weapon_kind,
        weapon_id=spec["weapon_id"],
        target_eid=target_eid,
        target_x=tx,
        target_y=ty,
        target_z=tz,
        damage=int(spec["damage"]),
        hit=bool(hit),
        battery_charge=int(getattr(state, "battery_charge", 0) or 0),
        resource_key=spec["resource_key"],
        resource_remaining=int(resource_metadata.get(spec["resource_key"], 0) or 0),
        cooldown=int(spec["cooldown"]),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    if consume_turn:
        sim.turn_advance_requested = True
    return {
        "ok": True,
        "reason": None,
        "weapon_kind": weapon_kind,
        "target_eid": target_eid,
        "hit": bool(hit),
        "battery_charge": int(getattr(state, "battery_charge", 0) or 0),
        "resource_remaining": int(resource_metadata.get(spec["resource_key"], 0) or 0),
    }


def drone_weapon_target_in_range(sim, drone_eid, target_eid, *, weapon_kind="auto", item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None:
        return False
    weapon_kind = _resolve_weapon_kind(state, weapon_kind)
    spec = DRONE_WEAPON_SPECS.get(weapon_kind)
    drone_pos = sim.ecs.get(Position).get(drone_eid)
    target_pos = sim.ecs.get(Position).get(target_eid)
    if spec is None or drone_pos is None or target_pos is None or int(drone_pos.z) != int(target_pos.z):
        return False
    if _manhattan(drone_pos.x, drone_pos.y, target_pos.x, target_pos.y) > int(spec["range"]):
        return False
    return bool(_weapon_target_viability(
        sim,
        drone_eid,
        drone_pos,
        {"range": int(spec["range"]), "trajectory": spec["trajectory"]},
        target_pos.x,
        target_pos.y,
        target_pos.z,
        target_eid=target_eid,
    ).get("ok"))


__all__ = [
    "DRONE_WEAPON_SPECS",
    "drone_weapon_status",
    "drone_weapon_target_in_range",
    "fire_drone_weapon",
    "tick_drone_weapon_cooldowns",
    "weapon_cooldown_remaining",
]
