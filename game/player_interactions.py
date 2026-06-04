"""Player nearby interaction, fixture tamper, and container runtime."""

from engine.events import Event

from game.components import Position
from game.item_semantics import item_display_name_for_actor
from game.items import ITEM_CATALOG
from game.opportunities import _item_label
from game.property_access import (
    property_access_controller as _property_access_controller,
    property_access_level as _property_access_level,
)
from game.property_runtime import (
    property_covering as _property_covering,
    property_infrastructure_role as _property_infrastructure_role,
    property_runtime_container_entries as _property_runtime_container_entries,
)
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.container_runtime import (
    ITEM_STOWED_CONTAINER_METADATA_KEY,
    _entry_stowed_container_instance,
    _inventory_entries_loose_for_container,
    _inventory_entries_stowed_in_container,
    _unlink_removed_item_from_gear,
)
from game.system_support.interaction_ordering import _manhattan
from game.system_support.item_provenance_runtime import (
    CLAIM_SCENE_SALVAGE,
    item_entitlement_for_actor,
    stamp_item_provenance,
)
from game.system_support.player_feedback import _log_player_feedback


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class PlayerInteractionRuntime:
    def __init__(self, action_system, *, infrastructure_target_property):
        self.action_system = action_system
        self.sim = action_system.sim
        self._infrastructure_target_property = infrastructure_target_property

    def _viewer_eid(self):
        return getattr(self.sim, "player_eid", None)

    def _nearest_fixture_by_role(self, eid, pos, *roles, preferred_dir=None, exact_direction=False):
        allowed = {
            str(role or "").strip().lower()
            for role in roles
            if str(role or "").strip()
        }
        if not allowed:
            return None
        nearby = self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=1)
        if exact_direction:
            direction = preferred_dir if preferred_dir is not None else self.action_system._player_interact_direction(eid, pos)
            if not isinstance(direction, tuple) or len(direction) < 2:
                return None
            dx = _int_or_default(direction[0], 0)
            dy = _int_or_default(direction[1], 0)
            if dx == 0 and dy == 0:
                return None
            target_x = int(pos.x) + int(dx)
            target_y = int(pos.y) + int(dy)
            nearby = [
                prop
                for prop in nearby
                if int(prop.get("x", 0)) == target_x
                and int(prop.get("y", 0)) == target_y
                and int(prop.get("z", pos.z)) == int(pos.z)
            ]
        candidates = []
        for prop in nearby:
            if _property_infrastructure_role(prop) not in allowed:
                continue
            candidates.append((
                self.action_system._interaction_target_sort_key(
                    eid,
                    pos,
                    int(prop.get("x", 0)),
                    int(prop.get("y", 0)),
                    stable_tiebreaker=(str(prop.get("id", "")),),
                ),
                prop,
            ))
        if not candidates:
            return None
        candidates.sort(key=lambda row: row[0])
        return candidates[0][1]

    def nearest_sabotage_fixture(self, eid, pos, *, preferred_dir=None, exact_direction=False):
        return self._nearest_fixture_by_role(
            eid,
            pos,
            "sabotage_target",
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )

    def security_fixture_target_property(self, prop):
        if not isinstance(prop, dict):
            return None

        target = self._infrastructure_target_property(self.sim, prop)
        if isinstance(target, dict):
            return target

        try:
            px = int(prop.get("x", 0))
            py = int(prop.get("y", 0))
            pz = int(prop.get("z", 0))
        except (TypeError, ValueError):
            return None

        covered = _property_covering(self.sim, px, py, pz)
        if isinstance(covered, dict) and covered.get("id") != prop.get("id"):
            return covered

        candidates = []
        for candidate in self.sim.properties_in_radius(px, py, pz, r=3):
            if candidate.get("id") == prop.get("id"):
                continue
            if str(candidate.get("kind", "")).strip().lower() != "building":
                continue
            controller = _property_access_controller(self.sim, candidate)
            access_level = _property_access_level(candidate)
            security_tier = max(1, _int_or_default(controller.get("security_tier"), 1))
            candidates.append((
                0 if access_level != "public" else 1,
                -security_tier,
                _manhattan(px, py, int(candidate.get("x", px)), int(candidate.get("y", py))),
                candidate,
            ))
        if not candidates:
            return None
        candidates.sort(key=lambda row: (row[0], row[1], row[2]))
        return candidates[0][3]

    def player_sabotage_fixture(self, eid, pos, prop):
        now = self.sim.tick
        prop_id = prop["id"]
        fixture_name = prop.get("name", prop_id)
        power_cuts = getattr(self.sim, "fixture_power_cuts", None)
        if not isinstance(power_cuts, dict):
            self.sim.fixture_power_cuts = {}
            power_cuts = self.sim.fixture_power_cuts
        if power_cuts.get(prop_id, 0) > now:
            _log_player_feedback(
                self.sim,
                f"The {fixture_name} is already offline.",
                kind="interaction",
            )
            return

        self.action_system._emit_action_offense(
            eid=eid,
            action="tamper",
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            context="ordinary",
        )

        cover_index = getattr(self.sim, "property_cover_index", {})
        key = (int(prop["x"]), int(prop["y"]), int(prop.get("z", 0)))
        building_id = None
        for pid in cover_index.get(key, ()):
            candidate = self.sim.properties.get(pid)
            if candidate and str(candidate.get("kind", "")).strip().lower() == "building":
                building_id = pid
                break

        duration = 180 + (int(self.sim.seed or 0) % 40)
        cut_until = now + duration
        power_cuts[prop_id] = cut_until
        if building_id:
            power_cuts[building_id] = cut_until

        target_prop = self.sim.properties.get(building_id) if building_id else self.security_fixture_target_property(prop)
        target_name = str((target_prop or {}).get("name", "")).strip()
        _log_player_feedback(
            self.sim,
            (
                f"You disable the {fixture_name}. {target_name} goes dark; "
                "cameras and alarms cut out, and the night glow goes with them."
            )
            if target_name
            else f"You disable the {fixture_name}. Nearby power and security cut out.",
            kind="interaction",
        )
        self.sim.emit(Event(
            "fixture_sabotaged",
            eid=eid,
            property_id=prop_id,
            building_id=building_id,
            cut_until=cut_until,
        ))

    def nearest_camera_fixture(self, eid, pos, *, preferred_dir=None, exact_direction=False):
        return self._nearest_fixture_by_role(
            eid,
            pos,
            "camera_target",
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )

    def player_disable_camera(self, eid, pos, prop):
        now = self.sim.tick
        prop_id = prop["id"]
        cam_name = prop.get("name", "camera")
        disabled = getattr(self.sim, "camera_disabled", None)
        if not isinstance(disabled, dict):
            self.sim.camera_disabled = {}
            disabled = self.sim.camera_disabled
        if disabled.get(prop_id, 0) > now:
            _log_player_feedback(
                self.sim,
                f"The {cam_name} is already blind.",
                kind="interaction",
            )
            return

        self.action_system._emit_action_offense(
            eid=eid,
            action="interact",
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            context="tamper",
        )

        duration = 120 + (int(self.sim.seed or 0) % 30)
        disabled[prop_id] = now + duration
        target_prop = self.security_fixture_target_property(prop)
        target_name = str((target_prop or {}).get("name", "")).strip()
        _log_player_feedback(
            self.sim,
            f"You blind the {cam_name}. Surveillance at {target_name} is thinner."
            if target_name
            else f"You blind the {cam_name}. Nearby surveillance is thinner.",
            kind="interaction",
        )
        self.sim.emit(Event(
            "camera_disabled",
            eid=eid,
            property_id=prop_id,
            disabled_until=now + duration,
        ))

    def nearest_alarm_fixture(self, eid, pos, *, preferred_dir=None, exact_direction=False):
        return self._nearest_fixture_by_role(
            eid,
            pos,
            "alarm_target",
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )

    def player_disable_alarm(self, eid, pos, prop):
        now = self.sim.tick
        prop_id = prop["id"]
        alarm_name = prop.get("name", "alarm panel")
        disabled = getattr(self.sim, "camera_disabled", None)
        if not isinstance(disabled, dict):
            self.sim.camera_disabled = {}
            disabled = self.sim.camera_disabled
        if disabled.get(prop_id, 0) > now:
            _log_player_feedback(
                self.sim,
                f"The {alarm_name} is already offline.",
                kind="interaction",
            )
            return

        self.action_system._emit_action_offense(
            eid=eid,
            action="interact",
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            context="tamper",
        )

        duration = 150 + (int(self.sim.seed or 0) % 40)
        disabled[prop_id] = now + duration
        target_prop = self.security_fixture_target_property(prop)
        target_name = str((target_prop or {}).get("name", "")).strip()
        _log_player_feedback(
            self.sim,
            f"You cut the {alarm_name}. Alarm response at {target_name} is degraded."
            if target_name
            else f"You cut the {alarm_name}. Nearby alarm response is degraded.",
            kind="interaction",
        )
        self.sim.emit(Event(
            "alarm_disabled",
            eid=eid,
            property_id=prop_id,
            disabled_until=now + duration,
        ))

    def equipped_worn_container(self, eid, container_instance_id=None):
        inventory = self.action_system._inventory_for(eid)
        if not inventory:
            return None
        current = getattr(self.sim, "equipped_container", None)
        if not isinstance(current, dict):
            return None
        active_instance_id = str(current.get("instance_id", "") or "").strip()
        target_instance_id = str(container_instance_id or active_instance_id or "").strip()
        if not target_instance_id or target_instance_id != active_instance_id:
            return None
        entry = inventory.find(instance_id=target_instance_id)
        if not entry:
            return None
        item_def = ITEM_CATALOG.get(entry["item_id"], {})
        container_profile = item_def.get("container", {}) if isinstance(item_def.get("container"), dict) else {}
        bonus_slots = max(0, _int_or_default(container_profile.get("bonus_slots"), 0))
        if bonus_slots <= 0:
            return None
        item_name = str(current.get("item_name", "") or "").strip() or item_display_name_for_actor(
            self.sim,
            self._viewer_eid(),
            entry,
            item_catalog=ITEM_CATALOG,
        )
        return {
            "inventory": inventory,
            "entry": entry,
            "item_def": item_def,
            "instance_id": target_instance_id,
            "item_name": item_name,
            "bonus_slots": bonus_slots,
        }

    def worn_container_panel_note(self, runtime):
        if not isinstance(runtime, dict):
            return ""
        bonus_slots = max(0, _int_or_default(runtime.get("bonus_slots"), 0))
        if bonus_slots <= 0:
            return ""
        return f"Equipped +{bonus_slots} slots"

    def refresh_worn_container_panel_state(self, eid, container_instance_id):
        inventory_ui = getattr(self.sim, "inventory_ui", None)
        if not isinstance(inventory_ui, dict):
            return
        runtime = self.equipped_worn_container(eid, container_instance_id)
        inventory_ui["inspect_text"] = ""
        inventory_ui["note_text"] = self.worn_container_panel_note(runtime)
        if not runtime:
            inventory_ui["selected_index"] = 0
            return
        view = str(
            inventory_ui.get("container_view", inventory_ui.get("cache_view", "pack"))
        ).strip().lower() or "pack"
        if view == "pack":
            entries = _inventory_entries_loose_for_container(runtime["inventory"], runtime["instance_id"])
        else:
            entries = _inventory_entries_stowed_in_container(runtime["inventory"], runtime["instance_id"])
        if not entries:
            inventory_ui["selected_index"] = 0
            return
        inventory_ui["selected_index"] = max(
            0,
            min(int(inventory_ui.get("selected_index", 0)), len(entries) - 1),
        )

    def container_inventory_entries(self, prop_id, *, container_kind="container"):
        prop_id = str(prop_id or "").strip()
        if not prop_id:
            return []
        return _property_runtime_container_entries(
            self.sim,
            prop_id,
            container_kind=container_kind,
        )

    def cache_panel_mission_note(self, prop):
        if not isinstance(prop, dict):
            return ""
        property_id = str(prop.get("id", "") or "").strip()
        if not property_id:
            return ""
        cache_items = self.container_inventory_entries(property_id, container_kind="cache")
        for entry in cache_items:
            if not isinstance(entry, dict):
                continue
            metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
            if str(entry.get("owner_tag", "")).strip().lower() == "quest":
                return "Mission cache: retrieve assigned package"
            quest_kind = str(metadata.get("quest_kind", "")).strip().lower()
            if quest_kind:
                return f"Mission cache: {quest_kind.replace('_', ' ')}"
        return ""

    def container_panel_note(self, prop, *, container_kind=None):
        container_kind = str(container_kind or "container").strip().lower() or "container"
        if container_kind == "cache":
            note = self.cache_panel_mission_note(prop)
            if note:
                return note
        if container_kind == "bones":
            metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
            note = str(metadata.get("bones_note", "") or "").strip()
            if note:
                return note
        metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
        note = str(metadata.get("container_note_text", "") or "").strip()
        if note:
            return note
        return ""

    def container_label(self, container_kind=None):
        container_kind = str(container_kind or "container").strip().lower() or "container"
        if container_kind == "cache":
            return "Cache"
        if container_kind == "scene":
            return "Cargo"
        if container_kind == "bones":
            return "Stash"
        return "Container"

    def nearest_cache_fixture(self, eid, pos, *, preferred_dir=None, exact_direction=False):
        return self._nearest_fixture_by_role(
            eid,
            pos,
            "cache_target",
            "bones_stash",
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )

    def nearest_run_echo_fixture(self, eid, pos, *, preferred_dir=None, exact_direction=False):
        return self._nearest_fixture_by_role(
            eid,
            pos,
            "run_echo_notice",
            "run_echo_stash",
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )

    def nearest_business_scene_cache(self, eid, pos, *, preferred_dir=None, exact_direction=False):
        return self._nearest_fixture_by_role(
            eid,
            pos,
            "business_scene_cache",
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )

    def open_property_container_ui(self, eid, prop, *, container_kind="container", container_label=None):
        inventory_ui = getattr(self.sim, "inventory_ui", None)
        if not isinstance(inventory_ui, dict):
            self.sim.inventory_ui = {}
            inventory_ui = self.sim.inventory_ui
        container_kind = str(container_kind or "container").strip().lower() or "container"
        container_label = str(container_label or self.container_label(container_kind)).strip() or self.container_label(container_kind)
        container_capacity = self.action_system.CACHE_MAX_STACKS if container_kind in {"cache", "bones"} else None
        self.container_inventory_entries(prop.get("id"), container_kind=container_kind)
        inventory_ui.update({
            "panel_kind": "container",
            "title": str(prop.get("name", prop.get("id", container_label))).strip() or container_label,
            "open": True,
            "property_id": prop.get("id"),
            "container_kind": container_kind,
            "container_label": container_label,
            "container_instance_id": None,
            "container_capacity": container_capacity,
            "container_view": "container",
            "cache_view": "cache",
            "selected_index": 0,
            "inspect_text": "",
            "note_text": self.container_panel_note(prop, container_kind=container_kind),
        })
        self.sim.emit(Event(
            "inventory_panel_toggled",
            eid=eid,
            open=True,
            panel_kind="container",
            title=inventory_ui["title"],
            property_id=prop.get("id"),
            container_kind=container_kind,
            container_label=container_label,
            container_instance_id=None,
        ))

    def player_interact_cache(self, eid, pos, prop):
        if _property_infrastructure_role(prop) == "bones_stash":
            self.open_property_container_ui(
                eid,
                prop,
                container_kind="bones",
                container_label="Stash",
            )
            return
        self.open_property_container_ui(
            eid,
            prop,
            container_kind="cache",
            container_label="Cache",
        )

    def player_interact_business_scene_cache(self, eid, pos, prop):
        metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
        container_kind = str(metadata.get("container_kind", "scene") or "scene").strip().lower() or "scene"
        container_label = str(
            metadata.get("container_label", self.container_label(container_kind)) or self.container_label(container_kind)
        ).strip() or self.container_label(container_kind)
        self.open_property_container_ui(
            eid,
            prop,
            container_kind=container_kind,
            container_label=container_label,
        )

    def player_interact_run_echo(self, eid, pos, prop):
        del pos
        metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
        infrastructure_role = _property_infrastructure_role(prop)
        if infrastructure_role == "run_echo_stash":
            container_kind = str(metadata.get("container_kind", "cache") or "cache").strip().lower() or "cache"
        else:
            container_kind = str(metadata.get("container_kind", "container") or "container").strip().lower() or "container"
        container_label = str(
            metadata.get("container_label", self.container_label(container_kind)) or self.container_label(container_kind)
        ).strip() or self.container_label(container_kind)
        self.open_property_container_ui(
            eid,
            prop,
            container_kind=container_kind,
            container_label=container_label,
        )

    def withdraw_from_worn_container(self, eid, container_instance_id, *, selected_index=0):
        runtime = self.equipped_worn_container(eid, container_instance_id)
        if not runtime:
            _log_player_feedback(self.sim, "No equipped container is ready.", kind="interaction")
            return False
        container_items = _inventory_entries_stowed_in_container(runtime["inventory"], runtime["instance_id"])
        if not container_items:
            _log_player_feedback(self.sim, f"The {runtime['item_name']} is empty.", kind="interaction")
            return False
        index = max(0, min(int(selected_index), len(container_items) - 1))
        entry = container_items[index]
        metadata = dict(entry.get("metadata") or {})
        metadata.pop(ITEM_STOWED_CONTAINER_METADATA_KEY, None)
        runtime["inventory"].update_item_metadata(entry["instance_id"], metadata=metadata, replace=True)
        name = item_display_name_for_actor(self.sim, self._viewer_eid(), entry, item_catalog=ITEM_CATALOG)
        _log_player_feedback(self.sim, f"Took {name} from {runtime['item_name']}.", kind="interaction")
        self.sim.emit(Event(
            "container_withdraw",
            eid=eid,
            container_kind="worn",
            container_instance_id=runtime["instance_id"],
            item_id=entry["item_id"],
            quantity=max(1, _int_or_default(entry.get("quantity"), 1)),
        ))
        self.refresh_worn_container_panel_state(eid, runtime["instance_id"])
        return True

    def withdraw_from_container(self, eid, prop_id, *, selected_index=0, container_kind="container"):
        prop = self.sim.properties.get(prop_id)
        container_kind = str(container_kind or "container").strip().lower() or "container"
        container_name = str((prop or {}).get("name", self.container_label(container_kind).lower())).strip() or self.container_label(container_kind).lower()
        container_items = self.container_inventory_entries(prop_id, container_kind=container_kind)
        inventory = self.action_system._inventory_for(eid)
        actor_pos = self.sim.ecs.get(Position).get(eid)
        if not inventory:
            return False
        if not container_items:
            _log_player_feedback(self.sim, f"The {container_name} is empty.", kind="interaction")
            return False
        index = max(0, min(int(selected_index), len(container_items) - 1))
        entry = container_items[index]
        item_id = str(entry.get("item_id", "")).strip().lower()
        quantity = max(1, _int_or_default(entry.get("quantity"), 1))
        item_def = ITEM_CATALOG.get(item_id, {})
        stack_max = max(1, int(item_def.get("stack_max", 1) or 1))
        entry_payload = {
            **entry,
            "x": (prop or {}).get("x"),
            "y": (prop or {}).get("y"),
            "z": (prop or {}).get("z", 0),
        }
        source_context = f"{container_kind}_withdraw"
        claim_class = CLAIM_SCENE_SALVAGE if container_kind in {"cache", "bones"} else None
        entitlement = item_entitlement_for_actor(
            self.sim,
            eid,
            entry_payload,
            prop=prop,
            source_context=source_context,
        )
        item_metadata = stamp_item_provenance(
            self.sim,
            entry_payload,
            prop=prop,
            source_context=source_context,
            claim_class=claim_class,
            latent_claim_violation=bool(entitlement and entitlement.get("latent_claim_violation")),
            last_transfer_tick=int(getattr(self.sim, "tick", 0)),
            last_transfer_kind=source_context,
            last_holder_eid=eid,
        )
        success, _instance_id = inventory.add_item(
            item_id,
            quantity=quantity,
            stack_max=stack_max,
            instance_factory=getattr(self.sim, "new_item_instance_id", None),
            owner_eid=eid,
            owner_tag="player",
            metadata=item_metadata,
        )
        if not success:
            _log_player_feedback(
                self.sim,
                f"Inventory full — can't take from {self.container_label(container_kind).lower()}.",
                kind="interaction",
            )
            return False
        removed = container_items.pop(index)
        name = item_display_name_for_actor(self.sim, self._viewer_eid(), removed, item_catalog=ITEM_CATALOG)
        _log_player_feedback(self.sim, f"Took {name} from {container_name}.", kind="interaction")
        self.sim.emit(Event(
            "container_withdraw",
            eid=eid,
            property_id=prop_id,
            container_kind=container_kind,
            item_id=item_id,
            quantity=quantity,
        ))
        if container_kind == "cache":
            self.sim.emit(Event(
                "cache_withdraw",
                eid=eid,
                property_id=prop_id,
                item_id=item_id,
                quantity=quantity,
            ))
        if entitlement and not entitlement.get("lawful_take"):
            event_x = int(getattr(actor_pos, "x", (prop or {}).get("x", 0)) or 0)
            event_y = int(getattr(actor_pos, "y", (prop or {}).get("y", 0)) or 0)
            event_z = int(getattr(actor_pos, "z", (prop or {}).get("z", 0)) or 0)
            theft_observation = observation_payload_for_position(
                self.sim,
                event_x,
                event_y,
                event_z,
                exclude_eid=eid,
                offender_eid=eid,
                observation_channels=("actor_witness",),
            )
            self.sim.emit(Event(
                "item_stolen",
                offender_eid=eid,
                item_id=item_id,
                item_name=name,
                owner_eid=entry.get("owner_eid"),
                owner_tag=entry.get("owner_tag"),
                property_id=prop_id,
                property_name=(prop or {}).get("name"),
                x=event_x,
                y=event_y,
                z=event_z,
                **theft_observation,
            ))
            self.action_system.item_system._emit_action_offense(
                eid=eid,
                action="pickup_item",
                context="item_theft",
                x=event_x,
                y=event_y,
                z=event_z,
                property_id=prop_id,
                **theft_observation,
            )
        inventory_ui = getattr(self.sim, "inventory_ui", None)
        if isinstance(inventory_ui, dict):
            inventory_ui["inspect_text"] = ""
            inventory_ui["selected_index"] = max(
                0,
                min(int(inventory_ui.get("selected_index", 0)), max(0, len(container_items) - 1)),
            )
            inventory_ui["note_text"] = self.container_panel_note(prop, container_kind=container_kind)
        return True

    def withdraw_from_cache(self, eid, prop_id, *, selected_index=0):
        return self.withdraw_from_container(
            eid,
            prop_id,
            selected_index=selected_index,
            container_kind="cache",
        )

    def deposit_to_worn_container(self, eid, container_instance_id, *, instance_id=None):
        runtime = self.equipped_worn_container(eid, container_instance_id)
        if not runtime:
            _log_player_feedback(self.sim, "No equipped container is ready.", kind="interaction")
            return False
        bag_entries = _inventory_entries_stowed_in_container(runtime["inventory"], runtime["instance_id"])
        if len(bag_entries) >= int(runtime["bonus_slots"]):
            _log_player_feedback(self.sim, f"The {runtime['item_name']} is full.", kind="interaction")
            return False
        if not _inventory_entries_loose_for_container(runtime["inventory"], runtime["instance_id"]):
            _log_player_feedback(self.sim, "Pack empty — nothing to stash.", kind="interaction")
            return False
        target_entry = runtime["inventory"].find(instance_id=instance_id) if instance_id else None
        if target_entry is None:
            _log_player_feedback(self.sim, "No pack item selected to stash.", kind="interaction")
            return False
        target_instance_id = str(target_entry.get("instance_id", "")).strip()
        if target_instance_id == runtime["instance_id"]:
            _log_player_feedback(self.sim, "You can't stash the active container inside itself.", kind="interaction")
            return False
        if _entry_stowed_container_instance(target_entry) == runtime["instance_id"]:
            _log_player_feedback(self.sim, f"{runtime['item_name']} already holds that item.", kind="interaction")
            return False
        metadata = dict(target_entry.get("metadata") or {})
        metadata[ITEM_STOWED_CONTAINER_METADATA_KEY] = runtime["instance_id"]
        runtime["inventory"].update_item_metadata(target_entry["instance_id"], metadata=metadata)
        name = item_display_name_for_actor(self.sim, self._viewer_eid(), target_entry, item_catalog=ITEM_CATALOG)
        _log_player_feedback(self.sim, f"Stashed {name} in {runtime['item_name']}.", kind="interaction")
        self.sim.emit(Event(
            "container_deposit",
            eid=eid,
            container_kind="worn",
            container_instance_id=runtime["instance_id"],
            item_id=target_entry["item_id"],
            quantity=max(1, _int_or_default(target_entry.get("quantity"), 1)),
        ))
        self.refresh_worn_container_panel_state(eid, runtime["instance_id"])
        return True

    def deposit_to_container(self, eid, prop_id, *, instance_id=None, container_kind="container"):
        prop = self.sim.properties.get(prop_id)
        container_kind = str(container_kind or "container").strip().lower() or "container"
        container_name = str((prop or {}).get("name", self.container_label(container_kind).lower())).strip() or self.container_label(container_kind).lower()
        container_items = self.container_inventory_entries(prop_id, container_kind=container_kind)
        inventory = self.action_system._inventory_for(eid)
        if not inventory:
            return False
        metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
        if bool(metadata.get("container_read_only")):
            message = str(metadata.get("container_read_only_reason", "") or "").strip()
            if not message:
                message = f"You can't stash anything in the {container_name}."
            _log_player_feedback(self.sim, message, kind="interaction")
            return False
        max_stacks = (
            self.action_system.CACHE_MAX_STACKS
            if container_kind in {"cache", "bones"}
            else max(8, len(container_items) + 1)
        )
        if len(container_items) >= max_stacks:
            _log_player_feedback(self.sim, f"The {container_name} is full.", kind="interaction")
            return False
        if not inventory.items:
            _log_player_feedback(self.sim, "Pack empty — nothing to stash.", kind="interaction")
            return False
        target_entry = inventory.find(instance_id=instance_id) if instance_id else None
        if target_entry is None:
            _log_player_feedback(self.sim, "No pack item selected to stash.", kind="interaction")
            return False
        target_instance_id = str(target_entry.get("instance_id", "")).strip()
        disguise = getattr(self.sim, "disguise_state", None)
        if isinstance(disguise, dict) and str(disguise.get("instance_id", "")).strip() == target_instance_id:
            _log_player_feedback(self.sim, "Remove the active disguise before stashing it.", kind="interaction")
            return False
        container = getattr(self.sim, "equipped_container", None)
        if isinstance(container, dict) and str(container.get("instance_id", "")).strip() == target_instance_id:
            _log_player_feedback(self.sim, "Take off the active container before stashing it.", kind="interaction")
            return False
        removed = inventory.remove_item(instance_id=target_entry["instance_id"], quantity=target_entry["quantity"])
        if not removed:
            return False
        removed_changes = _unlink_removed_item_from_gear(self.sim, eid, removed, item_catalog=ITEM_CATALOG)
        if removed_changes.get("armor_name"):
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=removed_changes.get("armor_item_id"),
                armor_name=removed_changes["armor_name"],
                reason="stashed",
            ))
        if removed_changes.get("weapon_id"):
            self.sim.emit(Event(
                "weapon_removed",
                eid=eid,
                weapon_id=removed_changes["weapon_id"],
                weapon_name=removed_changes["weapon_name"],
                reason="stashed",
            ))
        container_items.append({
            "instance_id": removed.get("instance_id"),
            "item_id": removed["item_id"],
            "quantity": removed["quantity"],
            "name": item_display_name_for_actor(self.sim, self._viewer_eid(), removed, item_catalog=ITEM_CATALOG),
            "metadata": removed.get("metadata"),
            "owner_eid": removed.get("owner_eid"),
            "owner_tag": removed.get("owner_tag"),
        })
        name = item_display_name_for_actor(self.sim, self._viewer_eid(), removed, item_catalog=ITEM_CATALOG)
        _log_player_feedback(self.sim, f"Stashed {name} in {container_name}.", kind="interaction")
        self.sim.emit(Event(
            "container_deposit",
            eid=eid,
            property_id=prop_id,
            container_kind=container_kind,
            item_id=removed["item_id"],
            quantity=removed["quantity"],
        ))
        if container_kind == "cache":
            self.sim.emit(Event(
                "cache_deposit",
                eid=eid,
                property_id=prop_id,
                item_id=removed["item_id"],
                quantity=removed["quantity"],
            ))
        inventory_ui = getattr(self.sim, "inventory_ui", None)
        if isinstance(inventory_ui, dict):
            inventory_ui["inspect_text"] = ""
            inventory_ui["selected_index"] = max(0, int(inventory_ui.get("selected_index", 0)))
            inventory_ui["note_text"] = self.container_panel_note(prop, container_kind=container_kind)
        return True

    def deposit_to_cache(self, eid, prop_id, *, instance_id=None):
        return self.deposit_to_container(
            eid,
            prop_id,
            instance_id=instance_id,
            container_kind="cache",
        )

    def handle_interact_action(self, eid, pos, *, force_direction=False):
        preferred_dir = self.action_system._player_interact_direction(eid, pos)
        exact_direction = bool(force_direction and preferred_dir is not None)

        sabotage_prop = self.nearest_sabotage_fixture(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if sabotage_prop is not None:
            self.player_sabotage_fixture(eid, pos, sabotage_prop)
            return
        camera_prop = self.nearest_camera_fixture(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if camera_prop is not None:
            self.player_disable_camera(eid, pos, camera_prop)
            return
        alarm_prop = self.nearest_alarm_fixture(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if alarm_prop is not None:
            self.player_disable_alarm(eid, pos, alarm_prop)
            return
        business_scene_cache = self.nearest_business_scene_cache(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if business_scene_cache is not None:
            self.player_interact_business_scene_cache(eid, pos, business_scene_cache)
            return
        run_echo_fixture = self.nearest_run_echo_fixture(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if run_echo_fixture is not None:
            self.player_interact_run_echo(eid, pos, run_echo_fixture)
            return
        cache_prop = self.nearest_cache_fixture(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if cache_prop is not None:
            self.player_interact_cache(eid, pos, cache_prop)
            return
        return self.action_system.property_actions.handle_interact_action(
            eid,
            pos,
            force_direction=force_direction,
        )
