"""Player nearby interaction, fixture tamper, and container runtime."""

from engine.events import Event

from game.appearance_loadout import is_entry_worn
from game.components import AI, Position, SuppressionState, Vitality
from game.item_semantics import item_display_name_for_actor
from game.items import ITEM_CATALOG
from game.herbal_chemistry_runtime import harvest_flora_patch, nearest_harvestable_flora
from game.hunting_runtime import field_dress_carcass, nearest_hunting_carcass
from game.meaningful_objects_runtime import nearest_item_backed_object_fixture, pickup_meaningful_object_fixture
from game.opportunities import _item_label, mark_bounty_target_restrained, resolve_opportunities
from game.property_access import (
    property_access_controller as _property_access_controller,
    property_access_level as _property_access_level,
)
from game.property_runtime import (
    property_covering as _property_covering,
    property_infrastructure_role as _property_infrastructure_role,
    property_runtime_container_entries as _property_runtime_container_entries,
)
from game.system_support.actor_runtime import _recover_downed_actor_state
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.container_runtime import (
    ITEM_STOWED_CONTAINER_METADATA_KEY,
    _entry_stowed_container_instance,
    _inventory_entries_loose_for_container,
    _inventory_entries_stowed_in_container,
    _unlink_removed_item_from_gear,
)
from game.system_support.interaction_ordering import _manhattan
from game.system_support.item_runtime import (
    _apply_item_effects_to_entity,
    _smallest_recovery_item_for_downed_actor,
)
from game.system_support.item_provenance_runtime import (
    CLAIM_SCENE_SALVAGE,
    item_entitlement_for_actor,
    stamp_item_provenance,
)
from game.justice_dispatch_runtime import request_player_justice_dispatch
from game.system_support.player_feedback import _log_player_feedback


CAMPFIRE_HERB_CACHE_KIND = "campfire_herb_cache"
CAMPFIRE_HERB_CACHE_CAPACITY = 3
HERBAL_CACHE_ITEM_TAGS = {"herbal_ingredient", "plant_material"}


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _item_tags_for_entry(entry, *, item_catalog=ITEM_CATALOG):
    item_id = str((entry or {}).get("item_id", "") or "").strip().lower()
    item_def = item_catalog.get(item_id, {}) if isinstance(item_catalog, dict) else {}
    return {
        str(tag or "").strip().lower()
        for tag in tuple(item_def.get("tags", ()) or ())
        if str(tag or "").strip()
    }


def entry_allowed_in_container(entry, *, container_kind="container", item_catalog=ITEM_CATALOG, container_profile=None):
    container_kind = str(container_kind or "container").strip().lower() or "container"
    if container_kind == CAMPFIRE_HERB_CACHE_KIND:
        return bool(_item_tags_for_entry(entry, item_catalog=item_catalog).intersection(HERBAL_CACHE_ITEM_TAGS))
    if isinstance(container_profile, dict):
        accepted_item_ids = {
            str(item_id or "").strip().lower()
            for item_id in tuple(container_profile.get("accepted_item_ids", ()) or ())
            if str(item_id or "").strip()
        }
        accepted_tags = {
            str(tag or "").strip().lower()
            for tag in tuple(container_profile.get("accepted_tags", ()) or ())
            if str(tag or "").strip()
        }
        rejected_tags = {
            str(tag or "").strip().lower()
            for tag in tuple(container_profile.get("rejected_tags", ()) or ())
            if str(tag or "").strip()
        }
        if accepted_item_ids or accepted_tags or rejected_tags:
            item_id = str((entry or {}).get("item_id", "") or "").strip().lower()
            tags = _item_tags_for_entry(entry, item_catalog=item_catalog)
            if rejected_tags and tags.intersection(rejected_tags):
                return False
            return bool(item_id in accepted_item_ids or tags.intersection(accepted_tags))
    return True


def container_capacity_for_kind(container_kind, *, default=None):
    container_kind = str(container_kind or "container").strip().lower() or "container"
    if container_kind == CAMPFIRE_HERB_CACHE_KIND:
        return CAMPFIRE_HERB_CACHE_CAPACITY
    return default


def campfire_herb_cache_note(sim, prop):
    property_id = str((prop or {}).get("id", "") or "").strip()
    if not property_id:
        return "Campfire herbs: load 2-3 plant materials here. Mortar kit required."
    count = len(_property_runtime_container_entries(sim, property_id, container_kind=CAMPFIRE_HERB_CACHE_KIND))
    if count <= 0:
        return "Campfire herbs: load 2-3 plant materials here. Mortar kit required."
    if count == 1:
        return "Campfire herbs: 1/3 loaded. Add at least one more plant material. Mortar kit required."
    if count <= CAMPFIRE_HERB_CACHE_CAPACITY:
        return f"Campfire herbs: {count}/3 ready. Close, then choose recipe or free-mix. Mortar kit required."
    return f"Campfire herbs: {count}/3 loaded. Remove extras before mixing."


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

    def _interact_target_coords(self, pos, *, preferred_dir=None, exact_direction=False, target=None):
        if isinstance(target, (tuple, list)) and len(target) >= 2:
            try:
                target_x = int(target[0])
                target_y = int(target[1])
                target_z = int(target[2] if len(target) >= 3 and target[2] is not None else pos.z)
            except (TypeError, ValueError):
                return None
            return target_x, target_y, target_z

        if exact_direction:
            direction = preferred_dir if preferred_dir is not None else None
            if not isinstance(direction, tuple) or len(direction) < 2:
                return None
            dx = _int_or_default(direction[0], 0)
            dy = _int_or_default(direction[1], 0)
            if dx == 0 and dy == 0:
                return None
            return int(pos.x) + int(dx), int(pos.y) + int(dy), int(pos.z)

        return None

    def _interact_target_direction(self, pos, target=None):
        target_coords = self._interact_target_coords(pos, target=target)
        if target_coords is None:
            return None
        target_x, target_y, target_z = target_coords
        if int(target_z) != int(pos.z):
            return None
        dx = int(target_x) - int(pos.x)
        dy = int(target_y) - int(pos.y)
        if max(abs(dx), abs(dy)) != 1:
            return None
        if dx < 0:
            dx = -1
        elif dx > 0:
            dx = 1
        if dy < 0:
            dy = -1
        elif dy > 0:
            dy = 1
        return None if (dx, dy) == (0, 0) else (dx, dy)

    def nearest_downed_actor(self, eid, pos, *, preferred_dir=None, exact_direction=False, target=None):
        target_coords = self._interact_target_coords(
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
            target=target,
        )
        candidates = []
        positions = self.sim.ecs.get(Position)
        players = getattr(self.sim, "player_eid", None)
        for other_eid, vitality in self.sim.ecs.get(Vitality).items():
            if other_eid == eid:
                continue
            if players is not None and other_eid == players and eid != players:
                continue
            if not bool(getattr(vitality, "downed", False)):
                continue
            if getattr(vitality, "death_reported_tick", None) is not None:
                continue
            other_pos = positions.get(other_eid)
            if not other_pos or int(other_pos.z) != int(pos.z):
                continue
            if target_coords is not None:
                target_x, target_y, target_z = target_coords
                if (
                    int(other_pos.x) != int(target_x)
                    or int(other_pos.y) != int(target_y)
                    or int(other_pos.z) != int(target_z)
                ):
                    continue
            elif max(abs(int(other_pos.x) - int(pos.x)), abs(int(other_pos.y) - int(pos.y))) > 1:
                continue

            distance = max(abs(int(other_pos.x) - int(pos.x)), abs(int(other_pos.y) - int(pos.y)))
            if distance > 1:
                continue
            candidates.append((
                self.action_system._interaction_target_sort_key(
                    eid,
                    pos,
                    int(other_pos.x),
                    int(other_pos.y),
                    stable_tiebreaker=(int(other_eid),),
                ),
                other_eid,
            ))

        if not candidates:
            return None
        candidates.sort(key=lambda row: row[0])
        return candidates[0][1]

    def _active_bounty_for_target(self, target_eid):
        traits = getattr(self.sim, "world_traits", None)
        state = traits.get("opportunities") if isinstance(traits, dict) else None
        active = state.get("active", ()) if isinstance(state, dict) else ()
        for entry in active:
            if not isinstance(entry, dict):
                continue
            requirements = entry.get("requirements") if isinstance(entry.get("requirements"), dict) else {}
            try:
                bounty_target = int(requirements.get("bounty_target_eid", 0) or 0)
            except (TypeError, ValueError):
                bounty_target = 0
            if bounty_target != int(target_eid):
                continue
            if bool(requirements.get("bounty_restrained")):
                continue
            if not bool(requirements.get("player_accepted")):
                continue
            return entry
        return None

    def nearest_bounty_restrainable_actor(self, eid, pos, *, preferred_dir=None, exact_direction=False, target=None):
        target_coords = self._interact_target_coords(
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
            target=target,
        )
        candidates = []
        positions = self.sim.ecs.get(Position)
        vitality_map = self.sim.ecs.get(Vitality)
        suppression_map = self.sim.ecs.get(SuppressionState)
        players = getattr(self.sim, "player_eid", None)
        for other_eid, other_pos in positions.items():
            if other_eid == eid:
                continue
            if players is not None and other_eid == players and eid != players:
                continue
            if self._active_bounty_for_target(other_eid) is None:
                continue
            vitality = vitality_map.get(other_eid)
            suppression = suppression_map.get(other_eid)
            downed = bool(vitality and getattr(vitality, "downed", False))
            surrendered = bool(suppression and getattr(suppression, "surrendered", False))
            if not downed and not surrendered:
                continue
            if vitality and getattr(vitality, "death_reported_tick", None) is not None:
                continue
            if not other_pos or int(other_pos.z) != int(pos.z):
                continue
            if target_coords is not None:
                target_x, target_y, target_z = target_coords
                if (
                    int(other_pos.x) != int(target_x)
                    or int(other_pos.y) != int(target_y)
                    or int(other_pos.z) != int(target_z)
                ):
                    continue
            elif max(abs(int(other_pos.x) - int(pos.x)), abs(int(other_pos.y) - int(pos.y))) > 1:
                continue
            distance = max(abs(int(other_pos.x) - int(pos.x)), abs(int(other_pos.y) - int(pos.y)))
            if distance > 1:
                continue
            candidates.append((
                self.action_system._interaction_target_sort_key(
                    eid,
                    pos,
                    int(other_pos.x),
                    int(other_pos.y),
                    stable_tiebreaker=(int(other_eid),),
                ),
                other_eid,
            ))
        if not candidates:
            return None
        candidates.sort(key=lambda row: row[0])
        return candidates[0][1]

    def _field_restraint_entry(self, eid):
        inventory = self.action_system._inventory_for(eid)
        if not inventory:
            return None
        for entry in list(getattr(inventory, "items", ()) or ()):
            if str(entry.get("item_id", "") or "").strip().lower() == "field_restraint_jab":
                if int(entry.get("quantity", 0) or 0) > 0:
                    return entry
        return None

    def player_restrain_bounty_target(self, eid, pos, target_eid):
        opportunity = self._active_bounty_for_target(target_eid)
        if not isinstance(opportunity, dict):
            return False
        target_vitality = self.sim.ecs.get(Vitality).get(target_eid)
        target_pos = self.sim.ecs.get(Position).get(target_eid)
        suppression = self.sim.ecs.get(SuppressionState).get(target_eid)
        downed = bool(target_vitality and getattr(target_vitality, "downed", False))
        surrendered = bool(suppression and getattr(suppression, "surrendered", False))
        if not downed and not surrendered:
            return False
        if not target_pos or int(target_pos.z) != int(pos.z):
            return False
        if max(abs(int(target_pos.x) - int(pos.x)), abs(int(target_pos.y) - int(pos.y))) > 1:
            return False
        entry = self._field_restraint_entry(eid)
        if entry is None:
            _log_player_feedback(
                self.sim,
                "You need an issued field restraint jab for this pickup.",
                kind="interaction",
                dedupe_window=3,
                dedupe_key=f"bounty_no_restraint:{target_eid}",
            )
            return True
        inventory = self.action_system._inventory_for(eid)
        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=1) if inventory else None
        if not removed:
            return False
        item_metadata = dict(removed.get("metadata") or {}) if isinstance(removed.get("metadata"), dict) else {}
        applied = _apply_item_effects_to_entity(
            self.sim,
            target_eid,
            ITEM_CATALOG.get("field_restraint_jab", {}),
            item_metadata=item_metadata,
        )
        if target_vitality is not None:
            _recover_downed_actor_state(
                self.sim,
                target_eid,
                tick=self.sim.tick,
                min_hp=max(1, int(getattr(target_vitality, "hp", 1) or 1)),
            )
        suppression = self.sim.ecs.get(SuppressionState).get(target_eid)
        if suppression is None:
            self.sim.ecs.add(target_eid, SuppressionState())
            suppression = self.sim.ecs.get(SuppressionState).get(target_eid)
        if suppression is not None:
            suppression.surrendered = True
            suppression.surrender_tick = int(getattr(self.sim, "tick", 0))
            suppression.pressure = 1.0
        ai = self.sim.ecs.get(AI).get(target_eid)
        if ai is not None:
            ai.state = "surrendered"
            ai.target = None
            ai.target_eid = None
        marked = mark_bounty_target_restrained(self.sim, eid, target_eid)
        target_name = "the target"
        if isinstance(marked, dict):
            requirements = marked.get("requirements") if isinstance(marked.get("requirements"), dict) else {}
            target_name = str(requirements.get("bounty_target_name", "") or target_name).strip()
        self.sim.emit(Event(
            "item_used",
            eid=eid,
            target_eid=target_eid,
            item_id="field_restraint_jab",
            item_name=item_display_name_for_actor(self.sim, self._viewer_eid(), removed, item_catalog=ITEM_CATALOG),
            reason="bounty_restraint",
            usage_kind="bounty_restraint",
            applied=applied,
            consumed=True,
            item_metadata=item_metadata,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        self.sim.emit(Event(
            "bounty_target_restrained",
            eid=target_eid,
            target_eid=target_eid,
            rescuer_eid=eid,
            target_name=target_name,
            opportunity_id=int((marked or {}).get("id", 0) or 0) if isinstance(marked, dict) else 0,
            x=int(target_pos.x),
            y=int(target_pos.y),
            z=int(target_pos.z),
        ))
        self.sim.emit(Event(
            "bounty_pickup_dispatch_requested",
            eid=eid,
            target_eid=target_eid,
            target_name=target_name,
            opportunity_id=int((marked or {}).get("id", 0) or 0) if isinstance(marked, dict) else 0,
            x=int(target_pos.x),
            y=int(target_pos.y),
            z=int(target_pos.z),
        ))
        resolve_opportunities(self.sim, eid)
        _log_player_feedback(
            self.sim,
            f"{target_name} is restrained and law pickup is called.",
            kind="interaction",
            dedupe_window=3,
            dedupe_key=f"bounty_restrained:{target_eid}",
        )
        return True

    def player_stabilize_downed_actor(self, eid, pos, target_eid):
        if self.player_restrain_bounty_target(eid, pos, target_eid):
            return True
        target_vitality = self.sim.ecs.get(Vitality).get(target_eid)
        target_pos = self.sim.ecs.get(Position).get(target_eid)
        if not target_vitality or not bool(getattr(target_vitality, "downed", False)):
            return False
        if not target_pos or int(target_pos.z) != int(pos.z):
            return False
        if max(abs(int(target_pos.x) - int(pos.x)), abs(int(target_pos.y) - int(pos.y))) > 1:
            return False

        inventory = self.action_system._inventory_for(eid)
        entry, item_def, _restore_hp = _smallest_recovery_item_for_downed_actor(inventory, ITEM_CATALOG)
        if entry is None or not item_def:
            _log_player_feedback(
                self.sim,
                "You need restorative medical aid to stabilize them.",
                kind="interaction",
                dedupe_window=3,
                dedupe_key=f"stabilize_no_aid:{target_eid}",
            )
            return True

        item_name = item_display_name_for_actor(self.sim, self._viewer_eid(), entry, item_catalog=ITEM_CATALOG)
        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=1) if inventory else None
        if not removed:
            return False
        item_metadata = dict((removed or entry).get("metadata") or {}) if isinstance((removed or entry).get("metadata"), dict) else {}
        applied = _apply_item_effects_to_entity(self.sim, target_eid, item_def, item_metadata=item_metadata)
        _recover_downed_actor_state(
            self.sim,
            target_eid,
            tick=self.sim.tick,
            min_hp=int(getattr(target_vitality, "hp", 1) or 1),
        )
        recovered_hp = int(getattr(target_vitality, "hp", 1) or 1)
        max_hp = int(getattr(target_vitality, "max_hp", recovered_hp) or recovered_hp)
        self.sim.emit(Event(
            "item_used",
            eid=eid,
            target_eid=target_eid,
            item_id=item_def.get("id"),
            item_name=item_name,
            reason="player_field_rescue",
            usage_kind="field_rescue",
            applied=applied,
            consumed=True,
            item_metadata=item_metadata,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        payload = {
            "rescuer_eid": eid,
            "target_eid": target_eid,
            "item_id": item_def.get("id"),
            "item_name": item_name,
            "recovered_hp": int(recovered_hp),
            "max_hp": int(max_hp),
            "professional": False,
            "applied": applied,
            "x": int(target_pos.x),
            "y": int(target_pos.y),
            "z": int(target_pos.z),
        }
        self.sim.emit(Event("npc_medical_rescue_applied", **payload))
        self.sim.emit(Event("npc_recovered_from_downed", eid=target_eid, **payload))
        return True

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

    def player_trigger_alarm_dispatch(self, eid, pos, prop):
        now = self.sim.tick
        prop_id = prop["id"]
        alarm_name = prop.get("name", "alarm panel")
        disabled = getattr(self.sim, "camera_disabled", None)
        if isinstance(disabled, dict) and disabled.get(prop_id, 0) > now:
            _log_player_feedback(
                self.sim,
                f"The {alarm_name} is offline.",
                kind="interaction",
            )
            return
        target_prop = self.security_fixture_target_property(prop)
        target_name = str((target_prop or {}).get("name", "")).strip()
        target_x = int(pos.x)
        target_y = int(pos.y)
        target_z = int(pos.z)
        if isinstance(target_prop, dict):
            target_x = int(target_prop.get("x", target_x) or target_x)
            target_y = int(target_prop.get("y", target_y) or target_y)
            target_z = int(target_prop.get("z", target_z) or target_z)
        request_player_justice_dispatch(
            self.sim,
            eid,
            target_x,
            target_y,
            target_z,
            source="alarm",
            property_id=(target_prop or prop).get("id") if isinstance((target_prop or prop), dict) else prop_id,
            property_name=target_name or str(alarm_name or "alarm").strip(),
        )

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
            "container_profile": container_profile,
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
        profile = runtime.get("container_profile") if isinstance(runtime.get("container_profile"), dict) else {}
        accepts_note = str(profile.get("accepts_note", "") or "").strip()
        note = f"Equipped +{bonus_slots} slots"
        if accepts_note:
            note += f"; accepts {accepts_note}"
        return note

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
        if container_kind == CAMPFIRE_HERB_CACHE_KIND:
            return campfire_herb_cache_note(self.sim, prop)
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
        if container_kind == CAMPFIRE_HERB_CACHE_KIND:
            return "Herbs"
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
        container_capacity = (
            self.action_system.CACHE_MAX_STACKS
            if container_kind in {"cache", "bones"}
            else container_capacity_for_kind(container_kind, default=None)
        )
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
            self.action_system._emit_action_offense(
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
        if not entry_allowed_in_container(
            target_entry,
            container_kind="worn",
            item_catalog=ITEM_CATALOG,
            container_profile=runtime.get("container_profile"),
        ):
            accepts_note = str((runtime.get("container_profile") or {}).get("accepts_note", "") or "").strip()
            if accepts_note:
                _log_player_feedback(self.sim, f"The {runtime['item_name']} only holds {accepts_note}.", kind="interaction")
            else:
                _log_player_feedback(self.sim, f"The {runtime['item_name']} will not hold that.", kind="interaction")
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
        capacity_default = self.action_system.CACHE_MAX_STACKS if container_kind in {"cache", "bones"} else None
        fixed_capacity = container_capacity_for_kind(container_kind, default=capacity_default)
        max_stacks = fixed_capacity if fixed_capacity is not None else max(8, len(container_items) + 1)
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
            _log_player_feedback(self.sim, "Remove the active cover before stashing it.", kind="interaction")
            return False
        container = getattr(self.sim, "equipped_container", None)
        if isinstance(container, dict) and str(container.get("instance_id", "")).strip() == target_instance_id:
            _log_player_feedback(self.sim, "Take off the active container before stashing it.", kind="interaction")
            return False
        if is_entry_worn(target_entry):
            _log_player_feedback(self.sim, "Remove the worn item before stashing it.", kind="interaction")
            return False
        if not entry_allowed_in_container(target_entry, container_kind=container_kind, item_catalog=ITEM_CATALOG):
            if container_kind == CAMPFIRE_HERB_CACHE_KIND:
                _log_player_feedback(self.sim, "The herb cache only takes harvested plant materials.", kind="interaction")
            else:
                _log_player_feedback(self.sim, f"The {container_name} will not take that.", kind="interaction")
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

    def handle_interact_action(self, eid, pos, *, force_direction=False, target=None):
        target_dir = self._interact_target_direction(pos, target)
        preferred_dir = target_dir or self.action_system._player_interact_direction(eid, pos)
        exact_direction = bool(force_direction and preferred_dir is not None)

        bounty_actor = self.nearest_bounty_restrainable_actor(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
            target=target,
        )
        if bounty_actor is not None and self.player_restrain_bounty_target(eid, pos, bounty_actor):
            return

        downed_actor = self.nearest_downed_actor(
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
            target=target,
        )
        if downed_actor is not None and self.player_stabilize_downed_actor(eid, pos, downed_actor):
            return

        carcass = nearest_hunting_carcass(
            self.sim,
            pos.x,
            pos.y,
            pos.z,
            radius=1,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if carcass is not None:
            field_dress_carcass(self.sim, eid, carcass.get("carcass_id"))
            return

        flora = nearest_harvestable_flora(
            self.sim,
            pos.x,
            pos.y,
            pos.z,
            radius=1,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if flora is not None:
            harvest_flora_patch(
                self.sim,
                eid,
                flora.get("id"),
                preferred_dir=preferred_dir,
                exact_direction=exact_direction,
            )
            return

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
            self.player_trigger_alarm_dispatch(eid, pos, alarm_prop)
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
        object_prop = nearest_item_backed_object_fixture(
            self.sim,
            eid,
            pos,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
        if object_prop is not None:
            result = pickup_meaningful_object_fixture(self.sim, eid, str(object_prop.get("id")))
            item_name = str(result.get("item_name", "object") or "object").strip()
            if result.get("ok"):
                if bool(result.get("theft")) and bool(result.get("witnessed_by_owner")):
                    _log_player_feedback(
                        self.sim,
                        f"You take {item_name}. Someone recognizes it.",
                        kind="interaction",
                        dedupe_window=2,
                        dedupe_key=f"meaningful_object_taken:{result.get('object_id')}",
                    )
                else:
                    _log_player_feedback(
                        self.sim,
                        f"You take {item_name}.",
                        kind="interaction",
                        dedupe_window=2,
                        dedupe_key=f"object_fixture_taken:{result.get('instance_id')}",
                    )
            elif str(result.get("reason")) == "inventory_full":
                _log_player_feedback(
                    self.sim,
                    f"You do not have room for {item_name}.",
                    kind="interaction",
                    dedupe_window=2,
                    dedupe_key=f"object_fixture_full:{object_prop.get('id')}",
                )
            return
        hard_traversal_prop = self.action_system.property_actions.hard_traversal_property_at(pos)
        if hard_traversal_prop is not None:
            self.action_system.property_actions.remember_player_property_discovery(
                eid,
                hard_traversal_prop,
                discovery_mode="interact",
            )
            self.action_system.property_actions._emit_property_interact(
                eid,
                hard_traversal_prop,
                interaction_mode="physical",
            )
            return
        return self.action_system.property_actions.handle_interact_action(
            eid,
            pos,
            force_direction=force_direction,
            target=target,
        )
