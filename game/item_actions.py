"""Player-facing item action runtime extracted from ``game.systems``."""

import random

from engine.events import Event
from game.components import AI, Inventory, JusticeProfile, PlayerAssets, Position, StatusEffects, Vitality, WeaponLoadout
from game.appearance_loadout import (
    equip_appearance_item,
    is_appearance_item,
    mark_inventory_instance_worn,
    stow_cosmetic_outer_for_armor,
)
from game.item_semantics import (
    identify_item_for_actor,
    item_display_name_for_actor,
    item_identification_profile,
)
from game.items import ITEM_CATALOG, credstick_total_credits, is_credstick_item, item_display_name, item_inventory_slot_cost, item_lead_profile
from game.quick_travel_ramps import local_interactions_suspended_for_actor
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import (
    property_covering as _property_covering,
    property_distance as _property_distance,
    property_services as _property_services,
    remember_property_lead_for_actor as _remember_property_lead_for_actor,
)
from game.system_support.actor_runtime import _apply_downed_actor_state, _entity_is_downed, _recover_downed_actor_state
from game.system_support.container_runtime import (
    _clear_inventory_container_assignments,
    _unlink_removed_item_from_gear,
)
from game.system_support.interaction_ordering import _manhattan
from game.system_support.item_runtime import (
    _apply_item_effects_to_entity,
    _default_weapon_reserve_ammo,
    _ensure_armor_loadout,
    _item_armor_profile,
    _item_can_recover_downed_actor as _runtime_item_can_recover_downed_actor,
    _item_tags,
    _item_weapon_id,
    _smallest_recovery_item_for_downed_actor,
    _weapon_uses_ammo,
)
from game.system_support.combat_targeting_runtime import _projectile_path_points
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.item_provenance_runtime import (
    CLAIM_PRIVATE_EFFECT,
    item_entitlement_for_actor,
    stamp_item_provenance,
)
from game.system_support.player_feedback import _log_player_feedback
from game.skills import actor_skill
from game.weapons import roll_weapon_instance, weapon_by_id


RADIO_SCAN_JUSTICE_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
RADIO_SCAN_MIN_MECHANICS = 6.0


class ItemActionRuntime:
    def __init__(self, item_system):
        self.item_system = item_system
        self.sim = item_system.sim
        self.player_eid = item_system.player_eid
        self.catalog = item_system.catalog

    def _inventory_for(self, eid):
        return self.sim.ecs.get(Inventory).get(eid)

    def _assets_for(self, eid):
        return self.sim.ecs.get(PlayerAssets).get(eid)

    def _status_for(self, eid):
        return self.sim.ecs.get(StatusEffects).get(eid)

    def _item_def(self, item_id):
        return self.catalog.get(item_id, {
            "id": item_id,
            "name": item_id,
            "glyph": "?",
            "stack_max": 1,
            "tags": [],
            "legal_status": "legal",
            "effects": [],
        })

    def _item_can_recover_downed_actor(self, item_def):
        return _runtime_item_can_recover_downed_actor(item_def)

    def _downed_recovery_entry(self, inventory, *, instance_id=None):
        if not inventory:
            return None
        if instance_id:
            return inventory.find(instance_id=instance_id)
        entry, _item_def, _restore_hp = _smallest_recovery_item_for_downed_actor(inventory, self.catalog)
        return entry

    def _item_throw_profile(self, item_def):
        profile = item_def.get("throw_profile") if isinstance(item_def, dict) else None
        return profile if isinstance(profile, dict) else None

    def _display_name_for_actor(self, eid, item_or_entry, *, identified=None):
        return item_display_name_for_actor(
            self.sim,
            eid,
            item_or_entry,
            identified=identified,
            item_catalog=self.catalog,
        )

    def _maybe_identify_item(self, eid, item_or_entry, *, source_kind="direct"):
        profile = item_identification_profile(item_or_entry, item_catalog=self.catalog)
        if not profile.get("requires_identification", False):
            return False
        return identify_item_for_actor(
            self.sim,
            eid,
            item_or_entry,
            source_kind=source_kind,
            item_catalog=self.catalog,
        )

    def _weapon_loadout_for(self, eid):
        loadouts = self.sim.ecs.get(WeaponLoadout)
        loadout = loadouts.get(eid)
        if loadout:
            return loadout
        loadout = WeaponLoadout()
        self.sim.ecs.add(eid, loadout)
        return loadout

    def _weapon_item_instance(self, entry, item_def):
        metadata = entry.setdefault("metadata", {})
        instance = metadata.get("weapon_instance")
        if isinstance(instance, dict):
            instance = dict(instance)
        else:
            weapon_id = _item_weapon_id(item_def) or item_def.get("id")
            rng = random.Random(f"{self.sim.seed}:weapon_item:{entry.get('instance_id')}:{weapon_id}")
            instance = roll_weapon_instance(rng, weapon_id)
        instance["inventory_instance_id"] = entry.get("instance_id")
        metadata["weapon_instance"] = instance

        custom_name = str(instance.get("custom_name", "")).strip()
        if custom_name:
            metadata["display_name"] = custom_name
        return instance

    def emit_removed_gear_events(self, eid, removed_entry, reason):
        changes = _unlink_removed_item_from_gear(self.sim, eid, removed_entry, item_catalog=self.catalog)
        if changes.get("armor_name"):
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=changes.get("armor_item_id"),
                armor_name=changes["armor_name"],
                reason=reason,
            ))
        if changes.get("weapon_id"):
            self.sim.emit(Event(
                "weapon_removed",
                eid=eid,
                weapon_id=changes["weapon_id"],
                weapon_name=changes["weapon_name"],
                reason=reason,
            ))
        if changes.get("disguise_name"):
            self.sim.emit(Event(
                "disguise_removed",
                eid=eid,
                item_id=changes.get("disguise_item_id"),
                item_name=changes["disguise_name"],
                reason=reason,
            ))
        if changes.get("container_name"):
            self.sim.emit(Event(
                "container_removed",
                eid=eid,
                item_id=changes.get("container_item_id"),
                item_name=changes["container_name"],
                reason=reason,
            ))

    def _toggle_weapon_item(self, eid, entry, item_def, reason="manual"):
        weapon_id = _item_weapon_id(item_def)
        if not weapon_id:
            return False

        loadout = self._weapon_loadout_for(eid)
        item_name = self._display_name_for_actor(eid, entry)
        equipped_weapon_id = loadout.current_weapon()
        if equipped_weapon_id == weapon_id:
            instance = loadout.weapon_instances.get(weapon_id, {})
            linked_instance_id = str(instance.get("inventory_instance_id", "")).strip() if isinstance(instance, dict) else ""
            target_instance_id = str(entry.get("instance_id", "")).strip()
            if not linked_instance_id or not target_instance_id or linked_instance_id == target_instance_id:
                loadout.equipped_weapon_id = None
                self.sim.emit(Event(
                    "weapon_removed",
                    eid=eid,
                    weapon_id=weapon_id,
                    weapon_name=item_name,
                    source_item_id=entry.get("item_id"),
                    source_instance_id=entry.get("instance_id"),
                    reason=reason,
                ))
                return True

        previous = loadout.current_weapon()
        instance = self._weapon_item_instance(entry, item_def)
        loadout.add_weapon(weapon_id, instance=instance)
        weapon = weapon_by_id(weapon_id)
        if _weapon_uses_ammo(weapon):
            current = loadout.reserve_ammo_value(
                weapon_id,
                default=-1,
                instance_id=entry.get("instance_id"),
            )
            if current < 0:
                loadout.set_reserve_ammo_value(
                    weapon_id,
                    int(_default_weapon_reserve_ammo(weapon)),
                    instance_id=entry.get("instance_id"),
                )
        loadout.equip(weapon_id)

        self.sim.emit(Event(
            "weapon_equipped",
            eid=eid,
            previous_weapon_id=previous,
            weapon_id=weapon_id,
            weapon_name=item_name,
            source_item_id=entry.get("item_id"),
            source_instance_id=entry.get("instance_id"),
            reason=reason,
        ))
        return True

    def _toggle_armor_item(self, eid, entry, item_def, reason="manual"):
        armor = _item_armor_profile(item_def)
        if not armor:
            return False

        loadout = _ensure_armor_loadout(self.sim, eid)
        item_name = self._display_name_for_actor(eid, entry)
        if loadout.is_equipped(entry.get("instance_id")):
            inventory = self._inventory_for(eid)
            metadata = dict(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), dict) else {}
            metadata.pop("appearance_worn", None)
            metadata.pop("appearance_slot", None)
            stowed_cost = item_inventory_slot_cost({
                "item_id": entry.get("item_id"),
                "metadata": metadata,
            })
            if inventory and stowed_cost > 0 and inventory.slot_count() + stowed_cost > int(getattr(inventory, "capacity", 0) or 0):
                self.sim.emit(Event(
                    "item_use_blocked",
                    eid=eid,
                    reason="appearance_pack_full",
                    item_id=item_def["id"],
                    item_name=item_name,
                    blocked_slot="outer",
                ))
                return False
            removed_reduction = loadout.damage_reduction
            loadout.clear()
            mark_inventory_instance_worn(self.sim, eid, entry.get("instance_id"), worn=False)
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=entry.get("item_id"),
                armor_name=item_name,
                reason=reason,
                damage_reduction=removed_reduction,
            ))
            return True

        if loadout.equipped_instance_id and loadout.equipped_instance_id != entry.get("instance_id"):
            previous_name = loadout.equipped_name or loadout.equipped_item_id or "armor"
            previous_item_id = loadout.equipped_item_id
            previous_reduction = loadout.damage_reduction
            previous_instance_id = loadout.equipped_instance_id
            loadout.clear()
            mark_inventory_instance_worn(self.sim, eid, previous_instance_id, worn=False)
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=previous_item_id,
                armor_name=previous_name,
                reason="replaced",
                damage_reduction=previous_reduction,
            ))

        outer_result = stow_cosmetic_outer_for_armor(self.sim, eid)
        if not bool(getattr(outer_result, "ok", False)):
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason=f"appearance_{getattr(outer_result, 'reason', 'outer_blocked')}",
                item_id=item_def["id"],
                item_name=item_name,
                blocked_slot="outer",
            ))
            return False

        loadout.equip(
            instance_id=entry.get("instance_id"),
            item_id=entry.get("item_id"),
            name=item_name,
            damage_reduction=armor["damage_reduction"],
            slot=armor.get("slot", "body"),
        )
        mark_inventory_instance_worn(self.sim, eid, entry.get("instance_id"), worn=True, slot="outer")
        self.sim.emit(Event(
            "armor_equipped",
            eid=eid,
            item_id=entry.get("item_id"),
            armor_name=item_name,
            reason=reason,
            slot=armor.get("slot", "body"),
            damage_reduction=armor["damage_reduction"],
        ))
        return True

    def _toggle_disguise_item(self, eid, entry, item_def, reason="manual"):
        disguise_profile = item_def.get("disguise", {})
        if not disguise_profile:
            return False
        item_id = item_def.get("id") or entry.get("item_id")
        instance_id = entry.get("instance_id")
        item_name = self._display_name_for_actor(eid, entry)
        current = getattr(self.sim, "disguise_state", None)
        if isinstance(current, dict) and current.get("instance_id") == instance_id:
            self.sim.disguise_state = None
            self.sim.emit(Event(
                "disguise_removed",
                eid=eid,
                item_id=item_id,
                item_name=item_name,
                reason=reason,
            ))
            return True
        if isinstance(current, dict):
            self.sim.emit(Event(
                "disguise_removed",
                eid=eid,
                item_id=current.get("item_id"),
                item_name=current.get("item_name", ""),
                reason="replaced",
            ))
        role_id = str(disguise_profile.get("role_id", "worker")).strip()
        strength = float(disguise_profile.get("strength", 1.0))
        self.sim.disguise_state = {
            "item_id": item_id,
            "instance_id": instance_id,
            "item_name": item_name,
            "role_id": role_id,
            "strength": strength,
            "equipped_tick": int(getattr(self.sim, "tick", 0)),
        }
        self.sim.emit(Event(
            "disguise_equipped",
            eid=eid,
            item_id=item_id,
            item_name=item_name,
            role_id=role_id,
            strength=strength,
            reason=reason,
        ))
        return True

    def _toggle_container_item(self, eid, entry, item_def, reason="manual"):
        container_profile = item_def.get("container", {})
        if not container_profile:
            return False
        bonus_slots = int(container_profile.get("bonus_slots", 0))
        if bonus_slots <= 0:
            return False
        item_id = item_def.get("id") or entry.get("item_id")
        instance_id = entry.get("instance_id")
        item_name = self._display_name_for_actor(eid, entry)
        inventory = self._inventory_for(eid)
        current = getattr(self.sim, "equipped_container", None)
        if isinstance(current, dict) and current.get("instance_id") == instance_id:
            if inventory:
                _clear_inventory_container_assignments(inventory, instance_id)
            self.sim.equipped_container = None
            if inventory:
                inventory.capacity = max(1, inventory.capacity - bonus_slots)
            self.sim.emit(Event(
                "container_removed",
                eid=eid,
                item_id=item_id,
                item_name=item_name,
                reason=reason,
            ))
            _log_player_feedback(self.sim, f"You put away the {item_name}.", kind="interaction")
            return True
        old_bonus = 0
        if isinstance(current, dict):
            old_instance_id = str(current.get("instance_id", "")).strip()
            old_bonus = int(current.get("bonus_slots", 0))
            if inventory and old_instance_id:
                _clear_inventory_container_assignments(inventory, old_instance_id)
            self.sim.emit(Event(
                "container_removed",
                eid=eid,
                item_id=current.get("item_id"),
                item_name=current.get("item_name", ""),
                reason="replaced",
            ))
        self.sim.equipped_container = {
            "item_id": item_id,
            "instance_id": instance_id,
            "item_name": item_name,
            "bonus_slots": bonus_slots,
            "equipped_tick": int(getattr(self.sim, "tick", 0)),
        }
        if inventory:
            inventory.capacity = max(1, inventory.capacity - old_bonus + bonus_slots)
        self.sim.emit(Event(
            "container_equipped",
            eid=eid,
            item_id=item_id,
            item_name=item_name,
            bonus_slots=bonus_slots,
            reason=reason,
        ))
        _log_player_feedback(self.sim, f"You equip the {item_name} (+{bonus_slots} slots).", kind="interaction")
        return True

    def _nearest_ground_item(self, x, y, z, radius=1):
        nearby = self.sim.ground_items_in_radius(x, y, z=z, r=radius)
        if not nearby:
            return None
        nearby = sorted(nearby, key=lambda item: _manhattan(x, y, item["x"], item["y"]))
        return nearby[0]

    def _rotate_blocked_ground_item(self, ground):
        ground_item_id = str((ground or {}).get("ground_item_id", "") or "").strip()
        if not ground_item_id:
            return False
        rotate = getattr(self.sim, "rotate_ground_item_to_back", None)
        if not callable(rotate):
            return False
        return bool(rotate(ground_item_id))

    def _is_theft(self, actor_eid, item_entry):
        entitlement = item_entitlement_for_actor(self.sim, actor_eid, item_entry)
        return bool(entitlement and not entitlement.get("lawful_take"))

    def _apply_item_effects(self, eid, item_def, *, item_metadata=None):
        return _apply_item_effects_to_entity(
            self.sim,
            eid,
            item_def,
            item_metadata=item_metadata,
        )

    def _property_matches_item_lead_profile(self, prop, lead_profile):
        if not isinstance(prop, dict):
            return False
        if not isinstance(lead_profile, dict):
            return False

        required_archetypes = {
            str(archetype).strip().lower()
            for archetype in tuple(lead_profile.get("property_archetypes", ()) or ())
            if str(archetype).strip()
        }
        if required_archetypes:
            metadata = prop.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            prop_archetype = str(metadata.get("archetype", prop.get("kind", "")) or "").strip().lower()
            if prop_archetype not in required_archetypes:
                return False

        required_services = {
            str(service).strip().lower()
            for service in tuple(lead_profile.get("property_services", ()) or ())
            if str(service).strip()
        }
        if required_services:
            prop_services = {
                str(service).strip().lower()
                for service in tuple(_property_services(prop) or ())
                if str(service).strip()
            }
            if not prop_services.intersection(required_services):
                return False

        return True

    def _resolve_item_lead_property(self, x, y, z, entry, item_def, lead_profile):
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        source_key = str(lead_profile.get("source_metadata_key", "source_property_id") or "").strip() or "source_property_id"
        source_property_id = str(metadata.get(source_key, "") or "").strip()
        if source_property_id:
            prop = getattr(self.sim, "properties", {}).get(source_property_id)
            if self._property_matches_item_lead_profile(prop, lead_profile):
                return prop

        current_prop = _property_covering(self.sim, x, y, z)
        if self._property_matches_item_lead_profile(current_prop, lead_profile):
            return current_prop

        candidates = []
        for prop in getattr(self.sim, "properties", {}).values():
            if not self._property_matches_item_lead_profile(prop, lead_profile):
                continue
            candidates.append(prop)

        if not candidates:
            return None

        candidates.sort(
            key=lambda prop: (
                _property_distance(int(x), int(y), prop),
                str(prop.get("name", "") or "").strip().lower(),
                str(prop.get("id", "") or "").strip(),
            ),
        )
        return candidates[0]

    def _use_lead_item(self, eid, x, y, z, inventory, entry, item_def, *, reason="manual"):
        lead_profile = item_lead_profile(item_def.get("id"), item_catalog=self.catalog)
        if not isinstance(lead_profile, dict):
            return None

        prop = self._resolve_item_lead_property(x, y, z, entry, item_def, lead_profile)
        item_name = self._display_name_for_actor(eid, entry)
        if not prop:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="no_property_lead",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        removed = None
        if bool(lead_profile.get("consume_on_use", False)):
            removed = inventory.remove_item(instance_id=entry["instance_id"], quantity=1)
            if not removed:
                self.sim.emit(Event(
                    "item_use_blocked",
                    eid=eid,
                    reason="consume_failed",
                    item_id=item_def["id"],
                    item_name=item_name,
                ))
                return False

        changed = _remember_property_lead_for_actor(
            self.sim,
            eid,
            prop,
            lead_kind=lead_profile.get("lead_kind"),
            confidence=float(lead_profile.get("confidence", 0.66)),
            hidden=True if bool(lead_profile.get("hidden_on_learn", False)) else None,
        )
        hidden = bool(lead_profile.get("hidden_on_learn", False))

        if changed:
            self.sim.emit(Event(
                "property_self_discovered",
                eid=eid,
                property_id=prop.get("id"),
                property_name=str(prop.get("name", prop.get("id", "location"))).strip() or "location",
                discovery_mode=str(lead_profile.get("discovery_mode", "advertisement") or "advertisement").strip().lower() or "advertisement",
                confidence=float(lead_profile.get("confidence", 0.66)),
                source_item_id=item_def["id"],
                source_item_name=item_name,
                lead_kind=str(lead_profile.get("lead_kind", "") or "").strip().lower(),
                hidden=hidden,
            ))

        entry_metadata = dict(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), dict) else {}
        self.sim.emit(Event(
            "item_used",
            eid=eid,
            item_id=item_def["id"],
            item_name=item_name,
            reason=reason,
            applied=[],
            usage_kind="property_lead",
            lead_changed=bool(changed),
            lead_kind=str(lead_profile.get("lead_kind", "") or "").strip().lower(),
            property_id=str(prop.get("id", "") or "").strip(),
            property_name=str(prop.get("name", prop.get("id", "location"))).strip() or "location",
            discovery_mode=str(lead_profile.get("discovery_mode", "advertisement") or "advertisement").strip().lower() or "advertisement",
            hidden=hidden,
            consumed=bool(removed),
            item_metadata=entry_metadata,
            source_property_id=str(entry_metadata.get("source_property_id", "") or "").strip() or None,
            source_organization_eid=entry_metadata.get("source_organization_eid"),
            source_organization_key=str(entry_metadata.get("source_organization_key", "") or "").strip() or None,
            source_practice_key=str(entry_metadata.get("source_practice_key", "") or "").strip() or None,
        ))

        self.item_system._emit_action_offense(
            eid=eid,
            action="use_item",
            context="ordinary",
            x=x,
            y=y,
            z=z,
        )
        return True

    def _is_radio_scanner_item(self, entry, item_def):
        item_id = str((entry or {}).get("item_id") or item_def.get("id", "") or "").strip().lower()
        tags = _item_tags(item_def)
        return item_id in {"two_way_radio", "radio", "walkie_talkie"} or "radio" in tags

    def _justice_radio_scan_rows(self, eid, x, y, z, *, radius, limit):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        justices = self.sim.ecs.get(JusticeProfile)
        rows = []
        for target_eid, pos in positions.items():
            if int(target_eid) == int(eid) or int(pos.z) != int(z):
                continue
            ai = ais.get(target_eid)
            justice = justices.get(target_eid)
            role = str(getattr(ai, "role", "") or "").strip().lower()
            if role not in RADIO_SCAN_JUSTICE_ROLES and not bool(getattr(justice, "enforce_all", False)):
                continue
            if _entity_is_downed(self.sim, target_eid):
                continue
            distance = _manhattan(int(x), int(y), int(pos.x), int(pos.y))
            if distance > int(radius):
                continue
            rows.append({
                "eid": int(target_eid),
                "x": int(pos.x),
                "y": int(pos.y),
                "z": int(pos.z),
                "distance": int(distance),
                "role": role or "justice",
            })
        rows.sort(key=lambda row: (int(row.get("distance", 0)), int(row.get("eid", 0))))
        return rows[: max(1, int(limit))]

    def _use_radio_scan(self, eid, x, y, z, inventory, entry, item_def, *, reason="manual"):
        item_id = str(entry.get("item_id", item_def.get("id", "two_way_radio")) or "two_way_radio").strip().lower()
        item_name = self._display_name_for_actor(eid, entry)
        entry_metadata = dict(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), dict) else {}
        removed = inventory.remove_item(instance_id=entry["instance_id"], quantity=1)
        if not removed:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="consume_failed",
                item_id=item_id,
                item_name=item_name,
            ))
            return False

        mechanics = float(actor_skill(self.sim, eid, "mechanics", default=5.0))
        success = mechanics >= RADIO_SCAN_MIN_MECHANICS
        duration = 0
        radius = 0
        rows = []
        if success:
            duration = max(18, min(90, int(round(18 + ((mechanics - RADIO_SCAN_MIN_MECHANICS) * 10)))))
            radius = max(18, min(42, int(round(18 + ((mechanics - RADIO_SCAN_MIN_MECHANICS) * 5)))))
            limit = max(3, min(8, int(round(3 + max(0.0, mechanics - RADIO_SCAN_MIN_MECHANICS)))))
            rows = self._justice_radio_scan_rows(eid, x, y, z, radius=radius, limit=limit)
            self.sim.world_traits["justice_radio_scan"] = {
                "source_eid": int(eid),
                "created_tick": int(getattr(self.sim, "tick", 0)),
                "expires_tick": int(getattr(self.sim, "tick", 0)) + int(duration),
                "radius": int(radius),
                "mechanics": round(float(mechanics), 2),
                "positions": list(rows),
            }
        self.sim.emit(Event(
            "justice_radio_scan",
            eid=eid,
            item_id=item_id,
            item_name=item_name,
            success=bool(success),
            broken=True,
            mechanics=round(float(mechanics), 2),
            duration=int(duration),
            radius=int(radius),
            rows=list(rows),
        ))
        self.sim.emit(Event(
            "item_used",
            eid=eid,
            item_id=item_id,
            item_name=item_name,
            reason=reason,
            applied=[],
            usage_kind="justice_radio_scan",
            success=bool(success),
            broken=True,
            mechanics=round(float(mechanics), 2),
            duration=int(duration),
            radius=int(radius),
            scan_rows=list(rows),
            item_metadata=entry_metadata,
        ))
        self.item_system._emit_action_offense(
            eid=eid,
            action="use_item",
            context="ordinary",
            x=x,
            y=y,
            z=z,
        )
        return True

    def throw_item(self, eid, x, y, z, *, instance_id=None, target_x=None, target_y=None, target_z=None, reason="manual"):
        inventory = self._inventory_for(eid)
        if not inventory:
            self.sim.emit(Event("item_use_blocked", eid=eid, reason="no_inventory"))
            return False

        entry = inventory.find(instance_id=instance_id) if instance_id else None
        if not entry:
            self.sim.emit(Event("item_use_blocked", eid=eid, reason="no_usable_item"))
            return False

        item_def = self._item_def(entry["item_id"])
        throw_profile = self._item_throw_profile(item_def)
        item_name = self._display_name_for_actor(eid, entry)
        if not throw_profile:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="item_not_throwable",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        try:
            tx = int(target_x)
            ty = int(target_y)
            tz = int(target_z if target_z is not None else z)
        except (TypeError, ValueError):
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="no_throw_target",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        if int(tz) != int(z):
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="wrong_floor",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        max_range = int(max(1, throw_profile.get("range", 5)))
        distance = max(abs(int(tx) - int(x)), abs(int(ty) - int(y)))
        if distance <= 0:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="no_throw_target",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False
        if distance > max_range:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="throw_out_of_range",
                item_id=item_def["id"],
                item_name=item_name,
                range=max_range,
            ))
            return False

        path = _projectile_path_points(int(x), int(y), tx, ty, max_steps=max_range)
        if not path:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="no_throw_target",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        removed = None
        if bool(throw_profile.get("consume_on_throw", True)):
            removed = inventory.remove_item(instance_id=entry["instance_id"], quantity=1)
            if not removed:
                self.sim.emit(Event(
                    "item_use_blocked",
                    eid=eid,
                    reason="consume_failed",
                    item_id=item_def["id"],
                    item_name=item_name,
                ))
                return False

        first_x, first_y = path[0]
        trajectory = str(throw_profile.get("trajectory", "lobbed") or "lobbed").strip().lower() or "lobbed"
        projectile_id = self.sim.register_projectile({
            "source_eid": eid,
            "weapon_id": f"throw:{item_def['id']}",
            "thrown_item_id": item_def["id"],
            "thrown_item_name": item_name,
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "dx": int(first_x) - int(x),
            "dy": int(first_y) - int(y),
            "path": path,
            "path_index": 0,
            "speed": float(max(0.1, throw_profile.get("speed", 0.9))),
            "travel_bank": 0.0,
            "remaining_range": len(path),
            "damage": int(max(0, throw_profile.get("damage", 0))),
            "trajectory": trajectory,
            "explosion_radius": int(max(0, throw_profile.get("explosion_radius", 0))),
            "aoe_falloff": float(max(0.0, min(1.0, throw_profile.get("aoe_falloff", 0.5)))),
            "cover_penetration": float(max(0.0, min(1.0, throw_profile.get("cover_penetration", 0.0)))),
            "fire_intensity": int(max(0, throw_profile.get("fire_intensity", 0))),
            "smoke_intensity": int(max(0, throw_profile.get("smoke_intensity", 0))),
            "cloud_radius": int(max(0, throw_profile.get("cloud_radius", 0))),
            "cloud_duration": int(max(0, throw_profile.get("cloud_duration", 0))),
            "aerosol_status": str(throw_profile.get("aerosol_status", "") or "").strip().lower(),
            "aerosol_duration": int(max(0, throw_profile.get("aerosol_duration", 0))),
            "aerosol_modifiers": dict(throw_profile.get("aerosol_modifiers", {}) or {}),
            "aerosol_exposure_cooldown": int(max(1, throw_profile.get("aerosol_exposure_cooldown", 6))),
            "aerosol_label": str(throw_profile.get("aerosol_label", "") or "").strip(),
            "projectile_glyph": str(throw_profile.get("projectile_glyph", "*") or "*")[:1] or "*",
            "target_x": tx,
            "target_y": ty,
            "target_z": tz,
            "ignore_walls": trajectory == "lobbed",
            "shatter": bool(throw_profile.get("shatter", False)),
        })

        noise_radius = int(max(0, throw_profile.get("noise_radius", 0)))
        if noise_radius > 0:
            self.sim.emit(Event(
                "noise",
                source_eid=eid,
                x=int(x),
                y=int(y),
                z=int(z),
                radius=noise_radius,
                cause="throw_item",
                item_id=item_def["id"],
                item_name=item_name,
            ))

        self.sim.emit(Event(
            "item_used",
            eid=eid,
            item_id=item_def["id"],
            item_name=item_name,
            reason=reason,
            applied=[],
            usage_kind="throw",
            projectile_id=projectile_id,
            target_x=tx,
            target_y=ty,
            target_z=tz,
            consumed=bool(removed),
            shatter=bool(throw_profile.get("shatter", False)),
            incendiary=bool(int(throw_profile.get("fire_intensity", 0)) > 0),
            smoke=bool(int(throw_profile.get("smoke_intensity", 0)) > 0),
            aerosol=bool(str(throw_profile.get("aerosol_status", "") or "").strip()),
        ))

        context = "explosive_discharge" if (
            int(throw_profile.get("explosion_radius", 0)) > 0
            or int(throw_profile.get("fire_intensity", 0)) > 0
        ) else "ordinary"
        self.item_system._emit_action_offense(
            eid=eid,
            action="use_item",
            context=context,
            x=int(x),
            y=int(y),
            z=int(z),
        )
        return True

    def reconcile_player_credsticks(self):
        inventory = self._inventory_for(self.player_eid)
        assets = self._assets_for(self.player_eid)
        if not inventory or not assets:
            return 0

        converted_credits = 0
        converted_quantity = 0
        for entry in list(getattr(inventory, "items", ()) or ()):
            item_id = str(entry.get("item_id", "") or "").strip().lower()
            if not is_credstick_item(item_id):
                continue
            quantity = max(1, int(entry.get("quantity", 1) or 1))
            removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=quantity)
            if not removed:
                continue
            converted_quantity += max(1, int(removed.get("quantity", quantity) or quantity))
            converted_credits += credstick_total_credits(
                quantity=removed.get("quantity", quantity),
                metadata=removed.get("metadata"),
            )

        if converted_credits > 0:
            assets.credits = int(max(0, int(getattr(assets, "credits", 0)) + int(converted_credits)))
            self.sim.emit(Event(
                "item_picked_up",
                eid=self.player_eid,
                item_id="credstick_chip",
                item_name=item_display_name(
                    "credstick_chip",
                    metadata={"stored_credits": int(converted_credits)},
                    item_catalog=self.catalog,
                ),
                quantity=int(max(1, converted_quantity)),
                instance_id=None,
                cash_pickup=True,
                credits_gained=int(converted_credits),
                source="inventory_reconcile",
            ))
        return int(converted_credits)

    def consume_item(self, eid, x, y, z, instance_id=None, reason="manual", preferred_appearance_slot=None):
        inventory = self._inventory_for(eid)
        if not inventory:
            self.sim.emit(Event("item_use_blocked", eid=eid, reason="no_inventory"))
            return False

        entry = inventory.find(instance_id=instance_id) if instance_id else inventory.first_usable(self.catalog)
        if not entry:
            self.sim.emit(Event("item_use_blocked", eid=eid, reason="no_usable_item"))
            return False

        item_def = self._item_def(entry["item_id"])
        item_name = self._display_name_for_actor(eid, entry)
        if _item_weapon_id(item_def):
            return self._toggle_weapon_item(
                eid=eid,
                entry=entry,
                item_def=item_def,
                reason=reason,
            )

        if _item_armor_profile(item_def):
            return self._toggle_armor_item(
                eid=eid,
                entry=entry,
                item_def=item_def,
                reason=reason,
            )

        if is_appearance_item(entry, item_catalog=self.catalog):
            result = equip_appearance_item(
                self.sim,
                eid,
                entry.get("instance_id"),
                preferred_slot=preferred_appearance_slot,
            )
            if bool(getattr(result, "ok", False)):
                return True
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason=f"appearance_{getattr(result, 'reason', 'blocked')}",
                item_id=item_def["id"],
                item_name=item_name,
                blocked_slot=getattr(result, "slot", ""),
            ))
            return False

        if item_def.get("disguise"):
            return self._toggle_disguise_item(
                eid=eid,
                entry=entry,
                item_def=item_def,
                reason=reason,
            )

        if item_def.get("container"):
            return self._toggle_container_item(
                eid=eid,
                entry=entry,
                item_def=item_def,
                reason=reason,
            )

        if "death_save" in _item_tags(item_def) and reason not in {"death_save", "critical_auto"}:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="auto_only_item",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        if self._is_radio_scanner_item(entry, item_def):
            return self._use_radio_scan(
                eid,
                x,
                y,
                z,
                inventory,
                entry,
                item_def,
                reason=reason,
            )

        lead_result = self._use_lead_item(
            eid,
            x,
            y,
            z,
            inventory,
            entry,
            item_def,
            reason=reason,
        )
        if lead_result is not None:
            return bool(lead_result)

        effects = item_def.get("effects", [])
        if not effects:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="item_not_usable",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        entry_metadata = dict(entry.get("metadata") or {}) if isinstance(entry.get("metadata"), dict) else {}
        applied = self._apply_item_effects(eid, item_def, item_metadata=entry_metadata)
        if not applied:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="no_applicable_effect",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        removed = inventory.remove_item(instance_id=entry["instance_id"], quantity=1)
        if not removed:
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="consume_failed",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        profile = item_identification_profile(item_def["id"], item_catalog=self.catalog)
        if profile.get("auto_identify_on_use", False):
            self._maybe_identify_item(
                eid,
                {"item_id": item_def["id"], "metadata": entry.get("metadata"), "instance_id": entry.get("instance_id")},
                source_kind="use",
            )

        self.sim.emit(Event(
            "item_used",
            eid=eid,
            item_id=item_def["id"],
            item_name=self._display_name_for_actor(
                eid,
                {"item_id": item_def["id"], "metadata": entry.get("metadata"), "instance_id": entry.get("instance_id")},
            ),
            reason=reason,
            applied=applied,
            item_metadata=entry_metadata,
            source_property_id=str(entry_metadata.get("source_property_id", "") or "").strip() or None,
            source_organization_eid=entry_metadata.get("source_organization_eid"),
            source_organization_key=str(entry_metadata.get("source_organization_key", "") or "").strip() or None,
            source_practice_key=str(entry_metadata.get("source_practice_key", "") or "").strip() or None,
        ))

        self.item_system._emit_action_offense(
            eid=eid,
            action="use_item",
            context="contraband_use" if item_def.get("legal_status", "legal") == "illegal" else "ordinary",
            x=x,
            y=y,
            z=z,
        )
        return True

    def _use_downed_recovery_item(self, eid, x, y, z, *, instance_id=None, reason="manual", preferred_appearance_slot=None):
        if int(eid) != int(self.player_eid):
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
            return False

        inventory = self._inventory_for(eid)
        if not inventory:
            self.sim.emit(Event("item_use_blocked", eid=eid, reason="no_inventory"))
            return False

        entry = self._downed_recovery_entry(inventory, instance_id=instance_id)
        if not entry:
            self.sim.emit(Event("item_use_blocked", eid=eid, reason="no_usable_item"))
            return False

        item_def = self._item_def(entry["item_id"])
        item_name = self._display_name_for_actor(eid, entry)
        if "death_save" in _item_tags(item_def):
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="auto_only_item",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False
        if not self._item_can_recover_downed_actor(item_def):
            self.sim.emit(Event(
                "item_use_blocked",
                eid=eid,
                reason="downed_requires_medical",
                item_id=item_def["id"],
                item_name=item_name,
            ))
            return False

        used = self.consume_item(
            eid,
            x,
            y,
            z,
            instance_id=entry["instance_id"],
            reason=reason,
            preferred_appearance_slot=preferred_appearance_slot,
        )
        vitality = self.sim.ecs.get(Vitality).get(eid)
        if not used or not vitality or int(getattr(vitality, "hp", 0)) <= 0:
            return bool(used)

        _recover_downed_actor_state(
            self.sim,
            eid,
            tick=self.sim.tick,
            min_hp=int(getattr(vitality, "hp", 1) or 1),
        )
        self.sim.emit(Event(
            "player_recovered_from_downed",
            eid=eid,
            target_eid=eid,
            item_id=item_def["id"],
            item_name=item_name,
            recovered_hp=int(getattr(vitality, "hp", 0)),
            max_hp=int(getattr(vitality, "max_hp", 0)),
        ))
        return True

    def handle_pickup(self, eid, x, y, z):
        if local_interactions_suspended_for_actor(self.sim, eid):
            self.sim.emit(Event("item_pickup_blocked", eid=eid, reason="map_mode"))
            return

        inventory = self._inventory_for(eid)
        if not inventory:
            self.sim.emit(Event("item_pickup_blocked", eid=eid, reason="no_inventory"))
            return

        ground = self._nearest_ground_item(x, y, z, radius=1)
        if not ground:
            self.sim.emit(Event("item_pickup_blocked", eid=eid, reason="no_item_nearby"))
            return

        item_def = self._item_def(ground["item_id"])
        ground_metadata = ground.get("metadata") if isinstance(ground.get("metadata"), dict) else {}
        entitlement = item_entitlement_for_actor(self.sim, eid, ground)
        is_theft = bool(entitlement and not entitlement.get("lawful_take"))
        stolen_prop = _property_covering(self.sim, ground.get("x"), ground.get("y"), ground.get("z", z)) if is_theft else None
        theft_observation = observation_payload_for_position(
            self.sim,
            ground.get("x"),
            ground.get("y"),
            ground.get("z", z),
            exclude_eid=eid,
            offender_eid=eid,
            observation_channels=("actor_witness",),
        ) if is_theft else {}
        item_metadata = stamp_item_provenance(
            self.sim,
            {
                **ground,
                "metadata": ground_metadata,
            },
            prop=stolen_prop,
            source_context=ground_metadata.get("source_context", "ground_pickup"),
            latent_claim_violation=bool(entitlement and entitlement.get("latent_claim_violation")),
            source_owner_eid=(entitlement or {}).get("source_owner_eid", ground.get("owner_eid")),
            source_owner_tag=(entitlement or {}).get("source_owner_tag", ground.get("owner_tag")),
            source_property_id=(entitlement or {}).get("source_property_id", str((stolen_prop or {}).get("id", "")).strip() or None),
            last_transfer_tick=int(getattr(self.sim, "tick", 0)),
            last_transfer_kind="ground_pickup",
            last_holder_eid=eid,
        )
        if is_theft:
            item_metadata["stolen_tick"] = int(getattr(self.sim, "tick", 0))
            item_metadata["stolen_owner_eid"] = ground.get("owner_eid")
            item_metadata["stolen_owner_tag"] = ground.get("owner_tag")
            item_metadata["stolen_property_id"] = str((stolen_prop or {}).get("id", "")).strip()
            item_metadata["justice_stolen"] = True
        if eid == self.player_eid and is_credstick_item(ground["item_id"]):
            assets = self._assets_for(eid)
            if assets is not None:
                credits_gained = credstick_total_credits(
                    quantity=ground.get("quantity", 1),
                    metadata=ground_metadata,
                )
                assets.credits = int(max(0, int(getattr(assets, "credits", 0)) + int(credits_gained)))
                self.sim.remove_ground_item(ground["ground_item_id"])
                self.sim.emit(Event(
                    "item_picked_up",
                    eid=eid,
                    item_id=ground["item_id"],
                    item_name=item_display_name("credstick_chip", metadata={"stored_credits": int(credits_gained)}, item_catalog=self.catalog),
                    quantity=ground.get("quantity", 1),
                    instance_id=ground.get("instance_id"),
                    ground_item_id=ground["ground_item_id"],
                    x=ground.get("x"),
                    y=ground.get("y"),
                    z=ground.get("z", 0),
                    cash_pickup=True,
                    credits_gained=int(credits_gained),
                ))
                if is_theft:
                    self.sim.emit(Event(
                        "item_stolen",
                        offender_eid=eid,
                        item_id=ground["item_id"],
                        item_name=item_display_name("credstick_chip", metadata={"stored_credits": int(credits_gained)}, item_catalog=self.catalog),
                        owner_eid=ground.get("owner_eid"),
                        owner_tag=ground.get("owner_tag"),
                        property_id=(stolen_prop or {}).get("id"),
                        x=ground["x"],
                        y=ground["y"],
                        z=ground["z"],
                        **theft_observation,
                    ))
                    self.item_system._emit_action_offense(
                        eid=eid,
                        action="pickup_item",
                        context="item_theft",
                        x=ground["x"],
                        y=ground["y"],
                        z=ground["z"],
                        property_id=(stolen_prop or {}).get("id"),
                        **theft_observation,
                    )
                else:
                    self.item_system._emit_action_offense(
                        eid=eid,
                        action="pickup_item",
                        context="ordinary",
                        x=ground["x"],
                        y=ground["y"],
                        z=ground["z"],
                    )
                return
        added, instance_id = inventory.add_item(
            item_id=ground["item_id"],
            quantity=ground.get("quantity", 1),
            stack_max=item_def.get("stack_max", 1),
            instance_id=ground.get("instance_id"),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player" if eid == self.player_eid else "npc",
            metadata={**item_metadata, "origin_ground_id": ground["ground_item_id"]},
        )
        if not added:
            self._rotate_blocked_ground_item(ground)
            self.sim.emit(Event(
                "item_pickup_blocked",
                eid=eid,
                reason="inventory_full",
                item_id=ground["item_id"],
                item_name=self._display_name_for_actor(eid, ground),
            ))
            return

        self.sim.remove_ground_item(ground["ground_item_id"])
        self.sim.emit(Event(
            "item_picked_up",
            eid=eid,
            item_id=ground["item_id"],
            item_name=self._display_name_for_actor(eid, ground),
            quantity=ground.get("quantity", 1),
            instance_id=instance_id,
            ground_item_id=ground["ground_item_id"],
            x=ground.get("x"),
            y=ground.get("y"),
            z=ground.get("z", 0),
        ))

        if is_theft:
            self.sim.emit(Event(
                "item_stolen",
                offender_eid=eid,
                item_id=ground["item_id"],
                item_name=self._display_name_for_actor(eid, ground),
                owner_eid=ground.get("owner_eid"),
                owner_tag=ground.get("owner_tag"),
                property_id=(stolen_prop or {}).get("id"),
                x=ground["x"],
                y=ground["y"],
                z=ground["z"],
                **theft_observation,
            ))
            self.item_system._emit_action_offense(
                eid=eid,
                action="pickup_item",
                context="item_theft",
                x=ground["x"],
                y=ground["y"],
                z=ground["z"],
                property_id=(stolen_prop or {}).get("id"),
                **theft_observation,
            )
        else:
            self.item_system._emit_action_offense(
                eid=eid,
                action="pickup_item",
                context="ordinary",
                x=ground["x"],
                y=ground["y"],
                z=ground["z"],
            )

    def handle_drop(self, eid, x, y, z, instance_id=None):
        inventory = self._inventory_for(eid)
        if not inventory:
            self.sim.emit(Event("item_drop_blocked", eid=eid, reason="no_inventory"))
            return

        if not inventory.items:
            self.sim.emit(Event("item_drop_blocked", eid=eid, reason="inventory_empty"))
            return

        target_instance_id = instance_id if instance_id else inventory.items[0]["instance_id"]
        target_entry = inventory.find(instance_id=target_instance_id)
        removed = inventory.remove_item(instance_id=target_instance_id, quantity=1)
        if not removed:
            item_id = str((target_entry or {}).get("item_id", "") or "").strip().lower()
            item_name = (
                self._display_name_for_actor(eid, target_entry)
                if item_id
                else ""
            )
            self.sim.emit(Event(
                "item_drop_blocked",
                eid=eid,
                reason="remove_failed",
                item_id=item_id,
                item_name=item_name,
            ))
            return

        self.emit_removed_gear_events(eid, removed, reason="dropped")
        drop_metadata = stamp_item_provenance(
            self.sim,
            {
                **removed,
                "x": x,
                "y": y,
                "z": z,
                "metadata": removed.get("metadata"),
            },
            source_context="actor_drop",
            claim_class=CLAIM_PRIVATE_EFFECT,
            source_owner_eid=eid,
            source_owner_tag="player" if eid == self.player_eid else "npc",
            source_actor_eid=eid,
            source_property_id=str((_property_covering(self.sim, x, y, z) or {}).get("id", "")).strip() or None,
            latent_claim_violation=bool((removed.get("metadata") or {}).get("latent_claim_violation", False)),
            last_transfer_tick=int(getattr(self.sim, "tick", 0)),
            last_transfer_kind="actor_drop",
            last_holder_eid=eid,
        )
        ground_id = self.sim.register_ground_item(
            item_id=removed["item_id"],
            x=x,
            y=y,
            z=z,
            quantity=removed["quantity"],
            owner_eid=eid,
            owner_tag="player" if eid == self.player_eid else "npc",
            instance_id=removed["instance_id"],
            metadata=drop_metadata,
        )
        self._item_def(removed["item_id"])
        self.sim.emit(Event(
            "item_dropped",
            eid=eid,
            item_id=removed["item_id"],
            item_name=self._display_name_for_actor(eid, removed),
            quantity=removed["quantity"],
            ground_item_id=ground_id,
            x=x,
            y=y,
            z=z,
        ))

    def on_use_item_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return

        if _entity_is_downed(self.sim, eid):
            positions = self.sim.ecs.get(Position)
            pos = positions.get(eid)
            if not pos:
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                return
            self._use_downed_recovery_item(
                eid,
                pos.x,
                pos.y,
                pos.z,
                instance_id=event.data.get("item_instance_id"),
                reason="downed_medical",
                preferred_appearance_slot=event.data.get("preferred_appearance_slot"),
            )
            return

        positions = self.sim.ecs.get(Position)
        pos = positions.get(eid)
        if not pos:
            return

        self.consume_item(
            eid=eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            instance_id=event.data.get("item_instance_id"),
            reason=event.data.get("reason", "request"),
            preferred_appearance_slot=event.data.get("preferred_appearance_slot"),
        )

    def on_throw_item_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return

        if _entity_is_downed(self.sim, eid):
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
            return

        positions = self.sim.ecs.get(Position)
        pos = positions.get(eid)
        if not pos:
            return

        self.throw_item(
            eid=eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            instance_id=event.data.get("item_instance_id"),
            target_x=event.data.get("target_x"),
            target_y=event.data.get("target_y"),
            target_z=event.data.get("target_z", pos.z),
            reason=event.data.get("reason", "request"),
        )

    def on_drop_item_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return

        positions = self.sim.ecs.get(Position)
        pos = positions.get(eid)
        if not pos:
            return

        self.handle_drop(
            eid=eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            instance_id=event.data.get("item_instance_id"),
        )

    def on_player_action(self, event):
        action = event.data.get("action")
        eid = event.data.get("eid")
        if eid is None:
            return

        if action not in {"pickup_item", "drop_item", "use_item"}:
            return

        positions = self.sim.ecs.get(Position)
        pos = positions.get(eid)
        if not pos:
            return

        if action == "pickup_item":
            if _entity_is_downed(self.sim, eid):
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                self.sim.emit(Event("item_use_blocked", eid=eid, reason="downed_requires_medical"))
                return
            self.handle_pickup(eid, pos.x, pos.y, pos.z)
            return

        if action == "drop_item":
            if _entity_is_downed(self.sim, eid):
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                self.sim.emit(Event("item_use_blocked", eid=eid, reason="downed_requires_medical"))
                return
            self.handle_drop(eid, pos.x, pos.y, pos.z)
            return

        if action == "use_item":
            if _entity_is_downed(self.sim, eid):
                self._use_downed_recovery_item(
                    eid,
                    pos.x,
                    pos.y,
                    pos.z,
                    reason="downed_medical",
                )
                return
            self.consume_item(
                eid=eid,
                x=pos.x,
                y=pos.y,
                z=pos.z,
                reason="manual",
            )

    def update(self):
        self.reconcile_player_credsticks()
