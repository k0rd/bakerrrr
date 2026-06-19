"""Shared item and equipment runtime helpers."""

from engine.events import Event

from game.components import (
    ArmorLoadout,
    NPCNeeds,
    PlayerAssets,
    StatusEffects,
    SubstanceUseState,
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


def _metadata_float(metadata, key, default=1.0):
    try:
        value = float((metadata if isinstance(metadata, dict) else {}).get(key, default) or default)
    except (TypeError, ValueError):
        value = float(default)
    return value


def _item_positive_effect_scalar(item_metadata=None):
    metadata = item_metadata if isinstance(item_metadata, dict) else {}
    effect_scalar = max(0.25, min(3.0, _metadata_float(metadata, "item_effect_scalar", 1.0)))
    positive_effect_scalar = _metadata_float(metadata, "item_positive_effect_scalar", effect_scalar)
    return max(0.25, min(3.0, positive_effect_scalar))


def _item_restore_hp_delta(item_def, *, item_metadata=None):
    if not isinstance(item_def, dict):
        return 0
    positive_effect_scalar = _item_positive_effect_scalar(item_metadata)
    total = 0
    for effect in tuple(item_def.get("effects", ()) or ()):
        if not isinstance(effect, dict) or effect.get("type") != "restore_hp":
            continue
        try:
            delta = int(round(float(effect.get("delta", 0) or 0) * positive_effect_scalar))
        except (TypeError, ValueError):
            delta = 0
        if delta > 0:
            total += int(delta)
    return int(max(0, total))


def _item_can_recover_downed_actor(item_def, *, item_metadata=None):
    tags = _item_tags(item_def)
    if "death_save" in tags or "medical" not in tags:
        return False
    return _item_restore_hp_delta(item_def, item_metadata=item_metadata) > 0


def _smallest_recovery_item_for_downed_actor(inventory, item_catalog=None):
    if not inventory:
        return None, None, 0
    catalog = item_catalog or {}
    best = None
    for index, entry in enumerate(list(getattr(inventory, "items", ()) or ())):
        if not isinstance(entry, dict):
            continue
        item_def = catalog.get(entry.get("item_id"))
        if not isinstance(item_def, dict):
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else None
        restore_hp = _item_restore_hp_delta(item_def, item_metadata=metadata)
        if restore_hp <= 0 or not _item_can_recover_downed_actor(item_def, item_metadata=metadata):
            continue
        row = (
            int(restore_hp),
            str(entry.get("item_id", "") or ""),
            str(entry.get("instance_id", "") or ""),
            int(index),
            entry,
            item_def,
        )
        if best is None or row[:4] < best[:4]:
            best = row
    if best is None:
        return None, None, 0
    return best[4], best[5], best[0]


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


def _item_substance_intoxication_duration(item_def):
    profile = item_def.get("substance_profile", {})
    if isinstance(profile, dict):
        try:
            explicit = int(profile.get("intoxication_duration", 0) or 0)
        except (TypeError, ValueError):
            explicit = 0
        if explicit > 0:
            return explicit

    durations = []
    for effect in item_def.get("effects", ()):
        if not isinstance(effect, dict) or effect.get("type") != "status":
            continue
        try:
            durations.append(max(0, int(effect.get("duration", 0) or 0)))
        except (TypeError, ValueError):
            continue
    return max(durations) if durations else 0


def _apply_item_effects_to_entity(sim, eid, item_def, *, item_metadata=None):
    needs = sim.ecs.get(NPCNeeds).get(eid)
    vitality = sim.ecs.get(Vitality).get(eid)
    statuses = sim.ecs.get(StatusEffects).get(eid)
    substance_states = sim.ecs.get(SubstanceUseState)
    assets = sim.ecs.get(PlayerAssets).get(eid)
    metadata = item_metadata if isinstance(item_metadata, dict) else {}
    try:
        effect_scalar = float(metadata.get("item_effect_scalar", 1.0) or 1.0)
    except (TypeError, ValueError):
        effect_scalar = 1.0
    effect_scalar = max(0.25, min(3.0, effect_scalar))
    try:
        positive_effect_scalar = float(metadata.get("item_positive_effect_scalar", effect_scalar) or effect_scalar)
    except (TypeError, ValueError):
        positive_effect_scalar = effect_scalar
    positive_effect_scalar = max(0.25, min(3.0, positive_effect_scalar))
    try:
        negative_effect_scalar = float(metadata.get("item_negative_effect_scalar", effect_scalar) or effect_scalar)
    except (TypeError, ValueError):
        negative_effect_scalar = effect_scalar
    negative_effect_scalar = max(0.25, min(3.0, negative_effect_scalar))
    try:
        duration_scalar = float(metadata.get("item_status_duration_scalar", 1.0) or 1.0)
    except (TypeError, ValueError):
        duration_scalar = 1.0
    duration_scalar = max(0.25, min(3.0, duration_scalar))

    applied = []
    for effect in item_def.get("effects", []):
        effect_type = effect.get("type")

        if effect_type == "modify_need":
            need = effect.get("need")
            try:
                raw_delta = float(effect.get("delta", 0))
            except (TypeError, ValueError):
                continue
            delta = raw_delta * (positive_effect_scalar if raw_delta >= 0.0 else negative_effect_scalar)

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
                delta = int(round(float(effect.get("delta", 0) or 0) * positive_effect_scalar))
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
            duration = int(max(1, round(float(effect.get("duration", 1) or 1) * duration_scalar)))
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
                before = int(loadout.reserve_ammo_value(weapon_id, default=0))
                after = max(0, before + amount)
                loadout.set_reserve_ammo_value(weapon_id, after)
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

    if needs:
        for need in ("energy", "safety", "social", "hunger", "thirst"):
            try:
                delta = float(metadata.get(f"item_extra_{need}_delta", 0.0) or 0.0)
            except (TypeError, ValueError):
                delta = 0.0
            if abs(delta) <= 1e-6 or not hasattr(needs, need):
                continue
            current = getattr(needs, need)
            setattr(needs, need, _clamp(current + delta))
            applied.append({
                "type": "modify_need",
                "need": need,
                "delta": float(delta),
                "source": "item_metadata",
            })

    substance_profile = item_def.get("substance_profile", {})
    if isinstance(substance_profile, dict) and substance_profile.get("substance_id") and statuses:
        substance_state = substance_states.get(eid)
        if substance_state is None:
            substance_state = SubstanceUseState()
            sim.ecs.add(eid, substance_state)
        state_snapshot = substance_state.record_use(
            substance_profile.get("substance_id"),
            tick=int(getattr(sim, "tick", 0) or 0),
            intoxication_duration=_item_substance_intoxication_duration(item_def),
            dependence_gain=substance_profile.get("dependence_gain", 0.0),
            dependence_decay=substance_profile.get("dependence_decay", 0.0),
            withdrawal_threshold=substance_profile.get("withdrawal_threshold", 1.0),
            withdrawal_status=substance_profile.get("withdrawal_status", ""),
            withdrawal_duration=substance_profile.get("withdrawal_duration", 0),
            withdrawal_cooldown=substance_profile.get("withdrawal_cooldown", 0),
            withdrawal_modifiers=substance_profile.get("withdrawal_modifiers", {}),
            statuses=statuses,
        )
        if state_snapshot:
            applied.append({
                "type": "substance_profile",
                "substance_id": substance_profile.get("substance_id"),
                "dependence": float(state_snapshot.get("dependence", 0.0) or 0.0),
            })

    return applied


def _ensure_armor_loadout(sim, eid):
    loadouts = sim.ecs.get(ArmorLoadout)
    loadout = loadouts.get(eid)
    if loadout:
        return loadout
    loadout = ArmorLoadout()
    sim.ecs.add(eid, loadout)
    return loadout
