"""Player-facing item action runtime extracted from ``game.systems``."""

import random

from engine.events import Event
from game.components import Inventory, PlayerAssets, Position, StatusEffects, WeaponLoadout
from game.item_semantics import (
    identify_item_for_actor,
    item_display_name_for_actor,
    item_identification_profile,
)
from game.items import ITEM_CATALOG, credstick_total_credits, is_credstick_item, item_display_name
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import property_covering as _property_covering
from game.system_support.actor_runtime import _apply_downed_actor_state, _entity_is_downed
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
    _item_tags,
    _item_weapon_id,
    _weapon_uses_ammo,
)
from game.system_support.player_feedback import _log_player_feedback
from game.weapons import roll_weapon_instance, weapon_by_id


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
            removed_reduction = loadout.damage_reduction
            loadout.clear()
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
            loadout.clear()
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=previous_item_id,
                armor_name=previous_name,
                reason="replaced",
                damage_reduction=previous_reduction,
            ))

        loadout.equip(
            instance_id=entry.get("instance_id"),
            item_id=entry.get("item_id"),
            name=item_name,
            damage_reduction=armor["damage_reduction"],
            slot=armor.get("slot", "body"),
        )
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

    def _is_theft(self, actor_eid, item_entry):
        owner_eid = item_entry.get("owner_eid")
        owner_tag = str(item_entry.get("owner_tag", "") or "").strip().lower() or None

        if owner_eid == actor_eid:
            return False
        if owner_tag == "player" and actor_eid == self.player_eid:
            return False

        item_x = item_entry.get("x")
        item_y = item_entry.get("y")
        item_z = item_entry.get("z", 0)
        prop = _property_covering(self.sim, item_x, item_y, item_z)
        if prop:
            access = _evaluate_property_access(
                self.sim,
                actor_eid,
                prop,
                x=item_x,
                y=item_y,
                z=item_z,
            )
            if not access.permitted:
                prop_owner_eid = prop.get("owner_eid")
                prop_owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
                if prop_owner_eid not in {None, actor_eid}:
                    return True
                if prop_owner_eid is None and prop_owner_tag not in {"", "public", "unowned", "none", "neutral"}:
                    return True

        if owner_eid is None and owner_tag in {None, "public", "unowned", "city"}:
            return False
        return True

    def _apply_item_effects(self, eid, item_def):
        return _apply_item_effects_to_entity(self.sim, eid, item_def)

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

    def consume_item(self, eid, x, y, z, instance_id=None, reason="manual"):
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

        applied = self._apply_item_effects(eid, item_def)
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

    def handle_pickup(self, eid, x, y, z):
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
        is_theft = self._is_theft(eid, ground)
        stolen_prop = _property_covering(self.sim, ground.get("x"), ground.get("y"), ground.get("z", z)) if is_theft else None
        stolen_metadata = {
            "justice_stolen": True,
            "stolen_tick": int(getattr(self.sim, "tick", 0)),
            "stolen_owner_eid": ground.get("owner_eid"),
            "stolen_owner_tag": ground.get("owner_tag"),
            "stolen_property_id": str((stolen_prop or {}).get("id", "")).strip(),
        } if is_theft else {}
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
                        x=ground["x"],
                        y=ground["y"],
                        z=ground["z"],
                    ))
                    self.item_system._emit_action_offense(
                        eid=eid,
                        action="pickup_item",
                        context="item_theft",
                        x=ground["x"],
                        y=ground["y"],
                        z=ground["z"],
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
            stack_max=1 if is_theft else item_def.get("stack_max", 1),
            instance_id=ground.get("instance_id"),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player" if eid == self.player_eid else "npc",
            metadata={**ground_metadata, "origin_ground_id": ground["ground_item_id"], **stolen_metadata},
        )
        if not added:
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
                x=ground["x"],
                y=ground["y"],
                z=ground["z"],
            ))
            self.item_system._emit_action_offense(
                eid=eid,
                action="pickup_item",
                context="item_theft",
                x=ground["x"],
                y=ground["y"],
                z=ground["z"],
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
        ground_id = self.sim.register_ground_item(
            item_id=removed["item_id"],
            x=x,
            y=y,
            z=z,
            quantity=removed["quantity"],
            owner_eid=eid,
            owner_tag="player" if eid == self.player_eid else "npc",
            instance_id=removed["instance_id"],
            metadata=removed.get("metadata"),
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
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
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
            self.handle_pickup(eid, pos.x, pos.y, pos.z)
            return

        if action == "drop_item":
            self.handle_drop(eid, pos.x, pos.y, pos.z)
            return

        if action == "use_item":
            self.consume_item(
                eid=eid,
                x=pos.x,
                y=pos.y,
                z=pos.z,
                reason="manual",
            )

    def update(self):
        self.reconcile_player_credsticks()
