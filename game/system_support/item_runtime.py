"""Shared item and equipment runtime helpers."""

from engine.events import Event

from game.components import (
    ArmorLoadout,
    NPCNeeds,
    PlayerAssets,
    StatusEffects,
    Vitality,
    WeaponLoadout,
)
from game.weapons import WEAPON_CATALOG, weapon_by_id


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


def _item_weapon_id(item_def):
    weapon_id = str(item_def.get("weapon_id", "")).strip()
    if not weapon_id:
        return None
    return weapon_id if weapon_id in WEAPON_CATALOG else None


def _item_tags(item_def):
    if not isinstance(item_def, dict):
        return set()
    return {
        str(tag).strip().lower()
        for tag in item_def.get("tags", ())
        if str(tag).strip()
    }


def _weapon_uses_ammo(weapon):
    if not isinstance(weapon, dict):
        return False
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    return "melee" not in tags


def _default_weapon_reserve_ammo(weapon):
    if not _weapon_uses_ammo(weapon):
        return 0
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    if "launcher" in tags or "explosive" in tags:
        return 3
    if "shotgun" in tags:
        return 10
    if "rifle" in tags or "carbine" in tags:
        return 14
    if "smg" in tags or "burst" in tags:
        return 24
    if "handgun" in tags:
        return 18
    return 12


def _item_armor_profile(item_def):
    armor = item_def.get("armor")
    if not isinstance(armor, dict):
        return None
    slot = str(armor.get("slot", "body")).strip().lower() or "body"
    try:
        damage_reduction = float(armor.get("damage_reduction", 0.0))
    except (TypeError, ValueError):
        damage_reduction = 0.0
    damage_reduction = max(0.0, min(0.85, damage_reduction))
    if damage_reduction <= 0.0:
        return None
    return {
        "slot": slot,
        "damage_reduction": damage_reduction,
    }


def _apply_item_effects_to_entity(sim, eid, item_def):
    needs = sim.ecs.get(NPCNeeds).get(eid)
    vitality = sim.ecs.get(Vitality).get(eid)
    statuses = sim.ecs.get(StatusEffects).get(eid)
    assets = sim.ecs.get(PlayerAssets).get(eid)

    applied = []
    for effect in item_def.get("effects", []):
        effect_type = effect.get("type")

        if effect_type == "modify_need":
            need = effect.get("need")
            try:
                delta = float(effect.get("delta", 0))
            except (TypeError, ValueError):
                continue

            if not needs or not hasattr(needs, need):
                continue

            current = getattr(needs, need)
            setattr(needs, need, _clamp(current + delta))
            applied.append({
                "type": "modify_need",
                "need": need,
                "delta": delta,
            })
            continue

        if effect_type == "restore_hp":
            try:
                delta = int(effect.get("delta", 0))
            except (TypeError, ValueError):
                continue
            if delta <= 0 or not vitality:
                continue
            before = int(getattr(vitality, "hp", 0))
            max_hp = int(getattr(vitality, "max_hp", 0))
            if before >= max_hp:
                continue
            after = min(max_hp, before + delta)
            healed = max(0, after - before)
            if healed <= 0:
                continue
            vitality.hp = int(after)
            applied.append({
                "type": "restore_hp",
                "delta": int(healed),
            })
            continue

        if effect_type == "status":
            if not statuses:
                continue
            status = effect.get("status")
            duration = int(max(1, effect.get("duration", 1)))
            modifiers = effect.get("modifiers", {})
            if not isinstance(modifiers, dict):
                modifiers = {}
            is_new = statuses.add(
                status=status,
                duration=duration,
                modifiers=modifiers,
                source_item=item_def["id"],
            )
            applied.append({
                "type": "status",
                "status": status,
                "duration": duration,
                "modifiers": dict(modifiers),
                "new": is_new,
            })
            sim.emit(Event(
                "status_applied",
                eid=eid,
                status=status,
                duration=duration,
                source_item=item_def["id"],
                modifiers=dict(modifiers),
                new=is_new,
            ))
            continue

        if effect_type == "credits":
            if not assets:
                continue
            try:
                delta = int(effect.get("delta", 0))
            except (TypeError, ValueError):
                continue
            assets.credits += delta
            applied.append({
                "type": "credits",
                "delta": delta,
            })
            continue

        if effect_type == "add_ammo":
            loadout = sim.ecs.get(WeaponLoadout).get(eid)
            if not loadout:
                continue
            try:
                amount = int(effect.get("amount", 0))
            except (TypeError, ValueError):
                amount = 0
            amount = max(0, amount)
            if amount <= 0:
                continue

            wanted_ids = {
                str(item).strip()
                for item in effect.get("weapon_ids", ())
                if str(item).strip()
            }
            wanted_tags = {
                str(item).strip().lower()
                for item in effect.get("weapon_tags", ())
                if str(item).strip()
            }

            targets = []
            for weapon_id in list(loadout.weapon_ids):
                weapon = weapon_by_id(weapon_id)
                if not _weapon_uses_ammo(weapon):
                    continue
                if wanted_ids and weapon_id not in wanted_ids:
                    continue
                if wanted_tags:
                    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
                    if not tags.intersection(wanted_tags):
                        continue
                targets.append((weapon_id, weapon))

            if not targets:
                equipped = loadout.current_weapon()
                if equipped:
                    weapon = weapon_by_id(equipped)
                    if _weapon_uses_ammo(weapon):
                        if (not wanted_ids or equipped in wanted_ids):
                            tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
                            if (not wanted_tags) or tags.intersection(wanted_tags):
                                targets.append((equipped, weapon))

            if not targets:
                continue

            updated = []
            for weapon_id, weapon in targets:
                before = int(loadout.reserve_ammo.get(weapon_id, 0))
                after = max(0, before + amount)
                loadout.reserve_ammo[weapon_id] = after
                updated.append({
                    "weapon_id": weapon_id,
                    "weapon_name": str(weapon.get("name", weapon_id)),
                    "before": before,
                    "after": after,
                    "added": amount,
                })

            applied.append({
                "type": "add_ammo",
                "amount": amount,
                "targets": updated,
            })
            continue

    return applied


def _ensure_armor_loadout(sim, eid):
    loadouts = sim.ecs.get(ArmorLoadout)
    loadout = loadouts.get(eid)
    if loadout:
        return loadout
    loadout = ArmorLoadout()
    sim.ecs.add(eid, loadout)
    return loadout
