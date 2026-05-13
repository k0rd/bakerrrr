"""Extracted systems from ``game.systems``: WorldStreamingSystem, QuestSystem, OpportunitySystem, RivalOperatorSystem, FinalOperationSystem."""

import random
import re
from engine.buildings import building_exterior_profile, layout_chunk_building, world_building_id
from engine.events import Event
from engine.fixtures import generate_chunk_fixture_records
from engine.persistence import restore_chunk_state, unload_chunk_state
from engine.sites import layout_chunk_site, site_gameplay_profile
from engine.systems import System
from engine.tilemap import Tile
from engine.visibility import (
    has_line_of_sight as _shared_has_line_of_sight,
    observer_can_see_position as _shared_observer_can_see_position,
    update_player_visibility as _update_player_visibility,
)
from game.bones import archive_failed_run_bones, maybe_seed_bones_for_chunk
from game.components import (
    AI,
    AnimalMemory,
    AnimalBehaviorContext,
    AnimalPhysicalProfile,
    AnimalSocialProfile,
    ArmorLoadout,
    Collider,
    ContactLedger,
    CoreStats,
    CoverState,
    CreatureIdentity,
    DoorWaitState,
    EcologyProfile,
    FinancialProfile,
    HumanWildlifePresence,
    InsightStats,
    Inventory,
    ItemUseProfile,
    JusticeProfile,
    MovementThrottle,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSettlement,
    NPCSocial,
    NPCTraits,
    NPCWill,
    NoiseProfile,
    Occupation,
    OrganizationAffiliations,
    PlayerAssets,
    PlayerControlled,
    PlayerModeState,
    Position,
    PropertyKnowledge,
    PropertyPortfolio,
    Render,
    SkillProfile,
    StatusEffects,
    SuppressionState,
    VehicleState,
    Vitality,
    WildlifeSocialState,
    WildlifeBehavior,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.final_operation import (
    active_final_operation_target_property_id,
    ensure_final_operation_unlocked,
    evaluate_final_operation,
    mark_final_operation_target_recovered,
    sync_final_operation_runtime,
    try_complete_final_operation,
    try_fail_final_operation,
)
from game.items import (
    ITEM_CATALOG,
    apply_item_durability_loss,
    credstick_total_credits,
    is_credstick_item,
    item_display_name,
    merge_item_stack_metadata,
    prepare_item_stack_metadata,
)
from game.opportunities import (
    SPECIALTY_OPPORTUNITY_THEMES,
    append_external_opportunity,
    evaluate_opportunity_board,
    evaluate_opportunity_facts,
    format_reward_text,
    opportunity_intel_for_observer,
    opportunity_distance_text,
    opportunity_known_count,
    opportunity_source_label,
    refresh_dynamic_opportunities,
    reveal_opportunity_to_observer,
    resolve_external_opportunity,
    resolve_opportunities,
    seed_run_opportunities,
    stage_active_opportunities,
)
from game.organizations import (
    ensure_property_organization,
    occupation_targets_property,
    organization_name,
    property_org_members,
    property_organization_eid,
    seed_property_organization_defaults,
    sync_actor_organization_affiliations,
)
from game.population import (
    ADMIN_ROOM_KINDS,
    FRONT_ROOM_KINDS,
    HOSPITALITY_ROOM_KINDS,
    INDUSTRIAL_ARCHETYPES,
    MEDICAL_ARCHETYPES,
    MEDICAL_ROOM_KINDS,
    NIGHTLIFE_ARCHETYPES,
    RESIDENTIAL_ARCHETYPES,
    SALVAGE_ARCHETYPES,
    SECURITY_ARCHETYPES,
    SECURE_ROOM_KINDS,
    STOREFRONT_ARCHETYPES,
    TRANSIT_ARCHETYPES,
    WORKROOM_KINDS,
    _bond_pair,
    _give_item,
    _shift_window_for,
    _spawn_human,
    seed_chunk_items,
    spawn_chunk_npcs,
    work_shift_active,
)
from game.property_access import (
    PropertyIngressResult,
    _boundary_tile as _property_boundary_tile,
    apply_controller_intrusion as _apply_controller_intrusion,
    controller_intrusion_access_for_actor as _controller_intrusion_access_for_actor,
    controller_intrusion_state as _controller_intrusion_state,
    default_site_services_for_archetype as _default_site_services_for_archetype,
    _property_archetype,
    property_access_controller as _property_access_controller,
    evaluate_property_access as _evaluate_property_access,
    sync_property_access_controller as _sync_property_access_controller,
    property_access_level as _property_access_level,
    property_apertures as _property_apertures,
    property_ingress_context as _property_ingress_context,
    property_claim_reason as _property_claim_reason,
    property_status_text as _property_status_text,
    world_hour as _world_hour,
)
from game.property_runtime import (
    building_id_from_property as _building_id_from_property,
    building_id_from_structure as _building_id_from_structure,
    clear_property_runtime_container_state as _clear_property_runtime_container_state,
    controller_access_requirement_text as _controller_access_requirement_text,
    controller_credential_short_label as _controller_credential_short_label,
    controller_holder_for_actor as _controller_holder_for_actor,
    finance_services_for_property as _finance_services_for_property,
    property_cover_intended as _property_cover_intended,
    property_infrastructure_role as _property_infrastructure_role,
    property_linked_building_id as _property_linked_building_id,
    property_linked_property_id as _property_linked_property_id,
    property_aperture_at as _property_aperture_at,
    property_covering as _property_covering,
    property_enclosing_structure as _property_enclosing_structure,
    property_display_position as _property_display_position,
    property_distance as _property_distance,
    property_focus_position as _property_focus_position,
    property_for_action as _property_for_action,
    property_is_public as _property_is_public,
    property_is_storefront as _property_is_storefront,
    property_is_vehicle as _property_is_vehicle,
    property_runtime_container_entry_count as _property_runtime_container_entry_count,
    property_runtime_container_entry_snapshot as _property_runtime_container_entry_snapshot,
    property_metadata as _property_metadata,
    remember_property_lead_for_actor as _remember_property_lead_for_actor,
    property_runtime_container_entries as _property_runtime_container_entries,
    property_services as _property_services,
    property_signage as _property_signage,
    site_services_for_property as _site_services_for_property,
    storefront_service_mode as _storefront_service_mode,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
    vehicle_profile_from_property as _vehicle_profile_from_property,
    viewer_property_credential_status as _viewer_property_credential_status,
    viewer_revealed_building_id as _viewer_revealed_building_id,
)
from game.system_support.interaction_ordering import (
    _direction_step,
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.vehicles import (
    generate_chunk_vehicle_records,
    roll_vehicle_profile,
    vehicle_metadata,
    vehicle_services_for_archetype,
)
from game.run_objectives import evaluate_run_objective

def _facade():
    from game import systems as facade

    return facade


def _generate_human_personal_name(*args, **kwargs):
    return _facade().generate_human_personal_name(*args, **kwargs)


def _building_site_service_seed_token(*args, **kwargs):
    return _facade()._building_site_service_seed_token(*args, **kwargs)

def _clamp(*args, **kwargs):
    return _facade()._clamp(*args, **kwargs)

def _int_or_default(*args, **kwargs):
    return _facade()._int_or_default(*args, **kwargs)

def _rank(*args, **kwargs):
    return _facade()._rank(*args, **kwargs)

def _site_service_seed_token(*args, **kwargs):
    return _facade()._site_service_seed_token(*args, **kwargs)

class WorldStreamingSystem(System):

    def __init__(self, sim, focus_eid):
        super().__init__(sim)
        self.focus_eid = focus_eid
        if not hasattr(self.sim, "chunk_property_records"):
            self.sim.chunk_property_records = {}
        if not hasattr(self.sim, "chunk_saved_states"):
            self.sim.chunk_saved_states = {}

    def _ensure_property_anchor(self, x, y, z=0):
        tile = self.sim.tilemap.tile_at(x, y, z)
        if tile and tile.walkable:
            return
        self.sim.tilemap.set_tile(x, y, Tile(walkable=True, transparent=True, glyph="."), z=z)

    def _ensure_chunk_properties(self, cx, cy):
        key = (int(cx), int(cy))
        if restore_chunk_state(self.sim, key):
            return
        if key in self.sim.chunk_property_records:
            return

        chunk = self.sim.world.get_chunk(key[0], key[1])
        rng = random.Random(f"{self.sim.seed}:{key[0]}:{key[1]}:properties")
        records = []

        chunk_size = int(max(8, self.sim.chunk_size))
        origin_x = key[0] * chunk_size
        origin_y = key[1] * chunk_size
        area_type = str(chunk.get("district", {}).get("area_type", "city")).strip().lower() or "city"
        finance_by_archetype = {
            "bank": ("banking", "insurance"),
            "brokerage": ("banking", "insurance"),
            "office": ("insurance",),
            "tower": ("insurance",),
            "pawn_shop": ("insurance",),
            "backroom_clinic": ("insurance",),
        }

        for block in chunk.get("blocks", []):
            bx = int(block.get("grid_x", 0))
            by = int(block.get("grid_y", 0))
            building_count = len(block.get("buildings", []))

            for i, building in enumerate(block.get("buildings", [])):
                layout = layout_chunk_building(
                    origin_x=origin_x,
                    origin_y=origin_y,
                    chunk_size=chunk_size,
                    block_grid_x=bx,
                    block_grid_y=by,
                    building_index=i,
                    building=building,
                    building_count=building_count,
                )
                if not layout:
                    continue

                x = int(layout["anchor_x"])
                y = int(layout["anchor_y"])
                z = 0
                if self.sim.property_at(x, y, z):
                    continue

                self._ensure_property_anchor(x, y, z)
                archetype = building["archetype"]
                local_building_id = str(building.get("building_id", "") or "").strip()
                chunk_building_id = world_building_id(key[0], key[1], local_building_id)
                service_seed_token = _building_site_service_seed_token(key[0], key[1], building, building_index=i)
                finance_services = list(finance_by_archetype.get(archetype, ()))
                site_services = list(dict.fromkeys(
                    list(_default_site_services_for_archetype(archetype, seed_token=service_seed_token))
                    + list(vehicle_services_for_archetype(archetype))
                ))
                business_name = str(building.get("business_name") or "").strip()
                business_founder_name = str(building.get("business_founder_name") or "").strip()
                business_founder_first_name = str(building.get("business_founder_first_name") or "").strip()
                business_founder_last_name = str(building.get("business_founder_last_name") or "").strip()
                display_name = business_name if business_name else f"{archetype}:{building['building_id']}"
                property_id = self.sim.register_property(
                    name=display_name,
                    kind="building",
                    x=x,
                    y=y,
                    z=z,
                    owner_eid=None,
                    owner_tag="city",
                    metadata={
                        "archetype": archetype,
                        "building_id": chunk_building_id,
                        "local_building_id": local_building_id or None,
                        "large_parcel": bool(building.get("large_parcel")),
                        "parcel_span_x": int(building.get("parcel_span_x", 1) or 1),
                        "parcel_span_y": int(building.get("parcel_span_y", 1) or 1),
                        "floors": int(building.get("floors", 1)),
                        "rooms": list(building.get("rooms", ())),
                        "footprint": dict(layout.get("footprint", {})),
                        "footprint_excluded_cells": [
                            {"x": int(cell_x), "y": int(cell_y)}
                            for cell_x, cell_y in sorted(layout.get("excluded", ()) or ())
                        ],
                        "entry": dict(layout.get("entry", {})),
                        "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                        "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                        "security_features": list(building.get("security_features", ())),
                        "purchase_cost": rng.randint(180, 460),
                        "finance_services": finance_services,
                        "site_services": site_services,
                        "site_service_seed_token": service_seed_token,
                        "is_storefront": bool(building.get("is_storefront")),
                        "public": bool(building.get("public")),
                        "business_name": business_name or None,
                        "business_founder_name": business_founder_name or None,
                        "business_founder_first_name": business_founder_first_name or None,
                        "business_founder_last_name": business_founder_last_name or None,
                        "chunk": key,
                    },
                )
                prop = self.sim.properties.get(property_id)
                seed_property_organization_defaults(prop, district=chunk.get("district"))
                ensure_property_organization(self.sim, prop)

                records.append({
                    "id": property_id,
                    "kind": "building",
                    "x": x,
                    "y": y,
                    "z": z,
                    "archetype": archetype,
                    "building_id": chunk_building_id,
                })

        reserved_site_footprints = []
        for idx, site in enumerate(chunk.get("sites", ())):
            if not isinstance(site, dict):
                continue

            layout = layout_chunk_site(
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
                site_index=idx,
                site=site,
                reserved_footprints=reserved_site_footprints,
            )
            if not layout:
                continue
            reserved_site_footprints.append(dict(layout.get("footprint", {})))

            x = int(layout["anchor_x"])
            y = int(layout["anchor_y"])
            z = 0
            if self.sim.property_at(x, y, z):
                continue

            self._ensure_property_anchor(x, y, z)
            site_kind = str(site.get("kind", "site")).strip().lower() or "site"
            service_seed_token = _site_service_seed_token(key[0], key[1], site, site_index=idx)
            site_name = str(site.get("name", site_kind.replace("_", " ").title())).strip() or "Site"
            gameplay = site_gameplay_profile(site)
            public = bool(gameplay.get("public"))
            site_services = list(gameplay.get("site_services", ()))
            if not site_services:
                site_services = list(_default_site_services_for_archetype(site_kind, seed_token=service_seed_token))
            extra_services = list(vehicle_services_for_archetype(site_kind))
            if extra_services:
                site_services = list(dict.fromkeys(site_services + extra_services))
            property_id = self.sim.register_property(
                name=site_name,
                kind="building",
                x=x,
                y=y,
                z=z,
                owner_eid=None,
                owner_tag="public" if public else area_type,
                metadata={
                    "archetype": site_kind,
                    "site_kind": site_kind,
                    "floors": 1,
                    "rooms": ["entry", "room"],
                    "footprint": dict(layout.get("footprint", {})),
                    "footprint_excluded_cells": [
                        {"x": int(cell_x), "y": int(cell_y)}
                        for cell_x, cell_y in sorted(layout.get("excluded", ()) or ())
                    ],
                    "entry": dict(layout.get("entry", {})),
                    "apertures": [dict(aperture) for aperture in layout.get("apertures", ()) if isinstance(aperture, dict)],
                    "signage": dict(layout["signage"]) if isinstance(layout.get("signage"), dict) else None,
                    "purchase_cost": rng.randint(110, 260),
                    "finance_services": list(gameplay.get("finance_services", ())),
                    "is_storefront": bool(gameplay.get("is_storefront")),
                    "site_services": list(site_services),
                    "site_service_seed_token": service_seed_token,
                    "site_id": str(site.get("site_id", idx)),
                    "public": public,
                    "chunk": key,
                },
            )
            prop = self.sim.properties.get(property_id)
            seed_property_organization_defaults(prop, district=chunk.get("district"))
            ensure_property_organization(self.sim, prop)

            records.append({
                "id": property_id,
                "kind": "building",
                "x": x,
                "y": y,
                "z": z,
                "archetype": site_kind,
                "building_id": f"{key[0]}:{key[1]}:{site.get('site_id', idx)}",
            })

        fixture_count = max(1, chunk_size // 8) if area_type != "city" else max(4, chunk_size // 4)
        fixtures = generate_chunk_fixture_records(
            self.sim,
            chunk,
            rng,
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            target_count=fixture_count,
        )
        for fixture in fixtures:
            x = int(fixture["x"])
            y = int(fixture["y"])
            kind = str(fixture.get("kind", "fixture")).strip().lower() or "fixture"
            metadata = dict(fixture.get("metadata", {}))
            metadata["chunk"] = key

            property_id = self.sim.register_property(
                name=str(fixture.get("name", "Fixture")).strip() or "Fixture",
                kind=kind,
                x=x,
                y=y,
                z=0,
                owner_eid=None,
                owner_tag=str(fixture.get("owner_tag", "city")).strip() or "city",
                metadata=metadata,
            )
            records.append({
                "id": property_id,
                "kind": kind,
                "x": x,
                "y": y,
                "z": 0,
                "archetype": metadata.get("archetype"),
                "building_id": None,
            })

        vehicle_target_count = max(1, chunk_size // 12) if area_type == "city" else (1 if rng.random() < 0.55 else 0)
        vehicles = generate_chunk_vehicle_records(
            self.sim,
            chunk,
            rng,
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            target_count=vehicle_target_count,
        )
        for vehicle in vehicles:
            x = int(vehicle["x"])
            y = int(vehicle["y"])
            if self.sim.property_at(x, y, 0):
                continue
            property_id = self.sim.register_property(
                name=str(vehicle.get("name", "Vehicle")).strip() or "Vehicle",
                kind="vehicle",
                x=x,
                y=y,
                z=0,
                owner_eid=None,
                owner_tag=str(vehicle.get("owner_tag", "public")).strip() or "public",
                metadata=dict(vehicle.get("metadata", {})),
            )
            records.append({
                "id": property_id,
                "kind": "vehicle",
                "x": x,
                "y": y,
                "z": 0,
                "archetype": "vehicle",
                "building_id": None,
            })

        self.sim.chunk_property_records[key] = records
        maybe_seed_bones_for_chunk(self.sim, chunk)

    def _ensure_chunk_population(self, cx, cy):
        key = (int(cx), int(cy))
        chunk = self.sim.world.get_chunk(key[0], key[1])
        records = self.sim.chunk_property_records.get(key, ())
        if not records:
            return
        seed_chunk_items(self.sim, chunk, records)
        spawn_chunk_npcs(self.sim, chunk, records)

    def update(self):
        positions = self.sim.ecs.get(Position)
        focus = positions.get(self.focus_eid)
        if not focus:
            return

        report = self.sim.stream_world(focus.x, focus.y)
        self.sim.ensure_loaded_chunk_terrain()
        for (loaded_cx, loaded_cy), loaded_data in tuple(self.sim.world.loaded_chunks.items()):
            detail = str((loaded_data or {}).get("detail", "coarse") or "").strip().lower() or "coarse"
            if detail != "active":
                continue
            self._ensure_chunk_properties(loaded_cx, loaded_cy)
            self._ensure_chunk_population(loaded_cx, loaded_cy)
        if not report.get("changed"):
            return

        for cx, cy in report["unloaded"]:
            unload_chunk_state(self.sim, (cx, cy))

        if report["focus_changed"]:
            cx, cy = report["focus"]
            district_data = self.sim.active_chunk.get("district", {})
            district = district_data.get("district_type", "unknown")
            area_type = district_data.get("area_type", "city")
            desc = self.sim.world.overworld_descriptor(cx, cy)
            self.sim.emit(Event(
                "chunk_focus_changed",
                cx=cx,
                cy=cy,
                district_type=district,
                area_type=area_type,
                region_name=desc.get("region_name"),
                settlement_name=desc.get("settlement_name"),
            ))

        for cx, cy in report["loaded"]:
            detail = self.sim.chunk_detail.get((cx, cy), "coarse")
            self.sim.emit(Event("chunk_loaded", cx=cx, cy=cy, detail=detail))

        for cx, cy in report["unloaded"]:
            self.sim.emit(Event("chunk_unloaded", cx=cx, cy=cy))

        for cx, cy in report["detail_changed"]:
            detail = self.sim.chunk_detail.get((cx, cy), "coarse")
            self.sim.emit(Event("chunk_detail_changed", cx=cx, cy=cy, detail=detail))

class QuestSystem(System):

    def __init__(self, sim, player_eid, max_available=3, max_active=2):
        super().__init__(sim)
        self.player_eid = player_eid
        self.max_available = max_available
        self.max_active = max_active

        self.rng = random.Random(f"{sim.seed}:quest_engine")

        self.sim.events.subscribe("quest_accept_requested", self.on_quest_accept_requested)
        self.sim.events.subscribe("quest_turn_in_requested", self.on_quest_turn_in_requested)
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("cache_withdraw", self.on_cache_withdraw)

    def _next_id(self):
        quest_id = f"Q-{self.sim.next_quest_id}"
        self.sim.next_quest_id += 1
        return quest_id

    def _recent_templates(self):
        return self.sim.quests["history_templates"][-4:]

    def _properties_for_templates(self):
        props = list(self.sim.properties.values())
        self.rng.shuffle(props)
        return props

    def _pick_owned_property(self, excluded_property_ids=None):
        excluded_property_ids = excluded_property_ids or set()
        props = [
            p
            for p in self._properties_for_templates()
            if p["id"] not in excluded_property_ids and p.get("owner_eid") not in (None, self.player_eid)
        ]
        return props[0] if props else None

    def _pick_claimable_property(self, excluded_property_ids=None):
        excluded_property_ids = excluded_property_ids or set()
        props = [
            p for p in self._properties_for_templates()
            if p["id"] not in excluded_property_ids and (p.get("owner_eid") is None or p.get("owner_tag") in {None, "city"})
        ]
        return props[0] if props else None

    def _pick_route_properties(self, min_nodes=2, max_nodes=3):
        candidates = [p for p in self._properties_for_templates() if p.get("owner_eid") not in (None, self.player_eid)]
        if len(candidates) < min_nodes:
            return []

        route_count = min(len(candidates), self.rng.randint(min_nodes, max_nodes))
        return candidates[:route_count]

    def _reward(self, low, high, difficulty=1, property_deed=None):
        base = self.rng.randint(low, high)
        scaled = int(base * (1.0 + ((max(1, difficulty) - 1) * 0.2)))
        return {
            "credits": scaled,
            "property_deed": property_deed,
        }

    def _quest_signature(self, quest):
        objective = quest.get("objective", {})
        return (
            quest.get("template"),
            objective.get("type"),
            objective.get("property_id"),
            tuple(objective.get("property_ids", [])),
            tuple(objective.get("chunk", ())),
            objective.get("target_z"),
        )

    def _existing_signatures(self):
        signatures = set()
        for bucket in ("available", "active"):
            for quest in self.sim.quests[bucket]:
                signatures.add(self._quest_signature(quest))
        return signatures

    def _build_visit_property(self):
        prop = self._pick_owned_property()
        if not prop:
            return None

        return {
            "id": self._next_id(),
            "template": "visit_property",
            "difficulty": 1,
            "status": "available",
            "title": f"Inspect {prop['name']}",
            "description": "Check the site and report what you find.",
            "objective": {
                "type": "visit_property",
                "property_id": prop["id"],
                "radius": 1,
                "target": 1,
            },
            "progress": 0,
            "reward": self._reward(20, 45, difficulty=1),
        }

    def _build_assist_owner(self):
        prop = self._pick_owned_property()
        if not prop:
            return None

        owner_eid = prop.get("owner_eid")
        if owner_eid is None:
            return None

        return {
            "id": self._next_id(),
            "template": "assist_owner",
            "difficulty": 2,
            "status": "available",
            "title": f"Assist Owner at {prop['name']}",
            "description": "Reach the owner and interact at their property.",
            "objective": {
                "type": "interact_property",
                "property_id": prop["id"],
                "owner_eid": owner_eid,
                "target": 1,
            },
            "progress": 0,
            "reward": self._reward(35, 65, difficulty=2),
        }

    def _build_patrol_chunk(self):
        if not self.sim.active_chunk_coord:
            return None

        cx, cy = self.sim.active_chunk_coord
        target_ticks = self.rng.randint(12, 20)

        return {
            "id": self._next_id(),
            "template": "patrol_chunk",
            "difficulty": 2,
            "status": "available",
            "title": f"Patrol Chunk ({cx}, {cy})",
            "description": "Remain in the target chunk to stabilize the area.",
            "objective": {
                "type": "patrol_chunk",
                "chunk": (cx, cy),
                "target": target_ticks,
            },
            "progress": 0,
            "reward": self._reward(30, 55, difficulty=2),
        }

    def _build_claim_property(self):
        prop = self._pick_claimable_property()
        if not prop:
            return None

        return {
            "id": self._next_id(),
            "template": "claim_property",
            "difficulty": 4,
            "status": "available",
            "title": f"Claim Deed: {prop['name']}",
            "description": "Complete legal capture and receive the deed.",
            "objective": {
                "type": "interact_property",
                "property_id": prop["id"],
                "target": 1,
            },
            "progress": 0,
            "reward": self._reward(60, 90, difficulty=4, property_deed=prop["id"]),
        }

    def _build_inspection_route(self):
        route_props = self._pick_route_properties(min_nodes=2, max_nodes=3)
        if len(route_props) < 2:
            return None

        property_ids = [prop["id"] for prop in route_props]
        first_name = route_props[0]["name"]
        difficulty = min(4, 1 + len(property_ids))

        return {
            "id": self._next_id(),
            "template": "inspection_route",
            "difficulty": difficulty,
            "status": "available",
            "title": f"Inspect Route from {first_name}",
            "description": "Visit multiple owned properties and verify conditions.",
            "objective": {
                "type": "visit_property_list",
                "property_ids": property_ids,
                "visited": [],
                "radius": 1,
                "target": len(property_ids),
            },
            "progress": 0,
            "reward": self._reward(55, 95, difficulty=difficulty),
        }

    def _build_reach_floor(self):
        if self.sim.tilemap.max_floors <= 1:
            return None

        target_z = self.rng.randint(1, self.sim.tilemap.max_floors - 1)
        return {
            "id": self._next_id(),
            "template": "reach_floor",
            "difficulty": 2,
            "status": "available",
            "title": f"Reach Floor {target_z}",
            "description": "Use vertical routes to reach the assigned floor.",
            "objective": {
                "type": "reach_floor",
                "target_z": target_z,
                "target": 1,
            },
            "progress": 0,
            "reward": self._reward(35, 70, difficulty=2),
        }

    CACHE_SEED_ITEMS = (
        "credstick_chip", "scrap_circuit", "battery_pack",
        "signal_jammer", "lockpick_kit", "med_gel",
        "micro_medkit", "focus_inhaler", "energy_bar",
    )

    def _pick_cache_property(self):
        props = self._properties_for_templates()
        for prop in props:
            metadata = prop.get("metadata")
            if not isinstance(metadata, dict):
                continue
            if str(metadata.get("interaction_role", "")).strip().lower() == "cache_target":
                return prop
        return None

    def _build_cache_pickup(self):
        cache_prop = self._pick_cache_property()
        if not cache_prop:
            return None
        seed_item_id = self.rng.choice(self.CACHE_SEED_ITEMS)
        seed_item_def = ITEM_CATALOG.get(seed_item_id, {})
        seed_name = seed_item_def.get("name", seed_item_id.replace("_", " "))
        # Seed the item into the cache inventory.
        cache_items = _property_runtime_container_entries(
            self.sim,
            cache_prop["id"],
            container_kind="cache",
        )
        cache_items.append({
            "instance_id": self.sim.new_item_instance_id(),
            "item_id": seed_item_id,
            "quantity": 1,
            "name": seed_name,
            "metadata": None,
            "owner_eid": None,
            "owner_tag": "quest",
        })
        return {
            "id": self._next_id(),
            "template": "cache_pickup",
            "difficulty": 2,
            "status": "available",
            "title": f"Retrieve {seed_name}",
            "description": f"Pick up a {seed_name} from the cache box near {cache_prop['name']}.",
            "objective": {
                "type": "cache_pickup",
                "property_id": cache_prop["id"],
                "item_id": seed_item_id,
                "target": 1,
            },
            "progress": 0,
            "reward": self._reward(30, 55, difficulty=2),
        }

    def _template_builders(self):
        return {
            "visit_property": self._build_visit_property,
            "assist_owner": self._build_assist_owner,
            "patrol_chunk": self._build_patrol_chunk,
            "claim_property": self._build_claim_property,
            "inspection_route": self._build_inspection_route,
            "reach_floor": self._build_reach_floor,
            "cache_pickup": self._build_cache_pickup,
        }

    def _generate_quest(self, existing_signatures=None):
        builders = self._template_builders()
        template_keys = list(builders.keys())
        self.rng.shuffle(template_keys)

        existing_signatures = existing_signatures or set()
        recent = set(self._recent_templates())

        for template in template_keys:
            if template in recent and self.rng.random() < 0.55:
                continue

            quest = builders[template]()
            if not quest:
                continue

            signature = self._quest_signature(quest)
            if signature in existing_signatures:
                continue
            return quest

        # Fallback pass if anti-repeat filtering skipped too much.
        for template in builders:
            quest = builders[template]()
            if not quest:
                continue

            signature = self._quest_signature(quest)
            if signature in existing_signatures:
                continue
            return quest

        return None

    def _apply_rewards(self, quest):
        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        reward = quest.get("reward", {})
        credits = int(reward.get("credits", 0))

        if assets:
            assets.credits += credits

        deed_property_id = reward.get("property_deed")
        if deed_property_id:
            prop = self.sim.properties.get(deed_property_id)
            old_owner = prop.get("owner_eid") if prop else None

            self.sim.assign_property_owner(deed_property_id, owner_eid=self.player_eid, owner_tag="player")
            self.sim.emit(Event(
                "property_owner_changed",
                property_id=deed_property_id,
                old_owner_eid=old_owner,
                new_owner_eid=self.player_eid,
            ))

    def _complete_quest(self, quest, reason):
        if quest["status"] == "completed":
            return

        active = self.sim.quests["active"]
        if quest in active:
            active.remove(quest)

        quest["status"] = "completed"
        quest["completed_tick"] = self.sim.tick
        quest["completion_reason"] = reason

        self.sim.quests["completed"].append(quest)
        self.sim.quests["history_templates"].append(quest["template"])
        self.sim.quests["history_templates"] = self.sim.quests["history_templates"][-20:]

        self._apply_rewards(quest)

        self.sim.emit(Event(
            "quest_completed",
            quest_id=quest["id"],
            title=quest["title"],
            difficulty=quest.get("difficulty", 1),
            reward=quest["reward"],
        ))

    def on_quest_accept_requested(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        available = self.sim.quests["available"]
        active = self.sim.quests["active"]

        if len(active) >= self.max_active:
            self.sim.emit(Event(
                "quest_accept_blocked",
                eid=self.player_eid,
                reason="max_active",
            ))
            return

        if not available:
            quest = self._generate_quest(existing_signatures=self._existing_signatures())
            if quest:
                available.append(quest)
                self.sim.emit(Event(
                    "quest_available",
                    quest_id=quest["id"],
                    title=quest["title"],
                    difficulty=quest.get("difficulty", 1),
                ))

        if not available:
            self.sim.emit(Event("quest_none_available", eid=self.player_eid))
            return

        quest = available.pop(0)
        quest["status"] = "active"
        quest["accepted_tick"] = self.sim.tick
        active.append(quest)

        self.sim.emit(Event(
            "quest_accepted",
            quest_id=quest["id"],
            title=quest["title"],
            difficulty=quest.get("difficulty", 1),
        ))

    def on_quest_turn_in_requested(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        # Rewards are applied at completion time for responsiveness.
        self.sim.emit(Event("quest_turn_in_noop", eid=self.player_eid))

    def _update_from_position(self, x, y, z):
        active = list(self.sim.quests["active"])
        for quest in active:
            objective = quest["objective"]
            kind = objective.get("type")

            if kind == "visit_property":
                prop = self.sim.properties.get(objective["property_id"])
                if not prop or prop["z"] != z:
                    continue

                focus = _property_focus_position(prop)
                if focus and _manhattan(x, y, focus[0], focus[1]) <= objective.get("radius", 1):
                    quest["progress"] = objective.get("target", 1)
                    self._complete_quest(quest, reason="visited_property")

            elif kind == "visit_property_list":
                visited = set(objective.get("visited", []))
                target_ids = objective.get("property_ids", [])
                radius = objective.get("radius", 1)

                for property_id in target_ids:
                    if property_id in visited:
                        continue

                    prop = self.sim.properties.get(property_id)
                    if not prop or prop["z"] != z:
                        continue

                    focus = _property_focus_position(prop)
                    if focus and _manhattan(x, y, focus[0], focus[1]) <= radius:
                        visited.add(property_id)

                objective["visited"] = sorted(visited)
                quest["progress"] = len(visited)
                if quest["progress"] >= objective.get("target", len(target_ids)):
                    self._complete_quest(quest, reason="route_inspected")

            elif kind == "patrol_chunk":
                target_chunk = objective.get("chunk")
                current_chunk = self.sim.chunk_coords(x, y)

                if current_chunk == target_chunk:
                    quest["progress"] += 1
                else:
                    quest["progress"] = max(0, quest["progress"] - 1)

                if quest["progress"] >= objective.get("target", 1):
                    self._complete_quest(quest, reason="patrol_complete")

            elif kind == "reach_floor":
                if z == objective.get("target_z"):
                    quest["progress"] = 1
                    self._complete_quest(quest, reason="floor_reached")

    def on_entity_moved(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        self._update_from_position(
            x=event.data.get("x"),
            y=event.data.get("y"),
            z=event.data.get("z"),
        )

    def on_property_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        property_id = event.data.get("property_id")
        if not property_id:
            return

        active = list(self.sim.quests["active"])
        for quest in active:
            objective = quest["objective"]
            if objective.get("type") != "interact_property":
                continue

            if objective.get("property_id") != property_id:
                continue

            quest["progress"] = objective.get("target", 1)
            self._complete_quest(quest, reason="property_interacted")

    def on_cache_withdraw(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_id = event.data.get("property_id")
        withdrawn_item_id = event.data.get("item_id")
        if not property_id or not withdrawn_item_id:
            return
        active = list(self.sim.quests["active"])
        for quest in active:
            objective = quest["objective"]
            if objective.get("type") != "cache_pickup":
                continue
            if objective.get("property_id") != property_id:
                continue
            if objective.get("item_id") != withdrawn_item_id:
                continue
            quest["progress"] = objective.get("target", 1)
            self._complete_quest(quest, reason="cache_item_collected")

    def update(self):
        available = self.sim.quests["available"]
        existing_signatures = self._existing_signatures()

        while len(available) < self.max_available:
            quest = self._generate_quest(existing_signatures=existing_signatures)
            if not quest:
                break

            available.append(quest)
            existing_signatures.add(self._quest_signature(quest))
            self.sim.emit(Event(
                "quest_available",
                quest_id=quest["id"],
                title=quest["title"],
                difficulty=quest.get("difficulty", 1),
            ))

class OpportunitySystem(System):

    def __init__(self, sim, player_eid, refresh_interval=20):
        super().__init__(sim)
        self.player_eid = player_eid
        self.refresh_interval = max(5, int(refresh_interval))
        self.last_refresh_tick = -10_000
        self.announced_opportunity_ids = set()
        self.seed_rng = random.Random(f"{self.sim.seed}:opportunity-system-seed")
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("npc_interacted", self.on_npc_interacted)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("site_intel_report", self.on_site_intel_report)
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("stakeout_intel_gained", self.on_stakeout_intel_gained)
        self.sim.events.subscribe("overworld_discovery_found", self.on_overworld_discovery_found)

    def _ensure_seeded(self):
        return seed_run_opportunities(self.sim, player_eid=self.player_eid, rng=self.seed_rng)

    def _emit_new_opportunity_log(self):
        state = getattr(self.sim, "world_traits", {}).get("opportunities", {})
        if not isinstance(state, dict):
            return

        active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
        new_entries = []
        for entry in active:
            oid = int(entry.get("id", 0))
            if oid <= 0 or oid in self.announced_opportunity_ids:
                continue
            self.announced_opportunity_ids.add(oid)
            new_entries.append(entry)

        if not new_entries:
            return

        new_entries.sort(key=lambda row: int(row.get("id", 0)))
        preview_lines = []
        for entry in new_entries[:3]:
            raw_chunk = entry.get("chunk", (0, 0))
            if isinstance(raw_chunk, (list, tuple)) and len(raw_chunk) == 2:
                try:
                    chunk = (int(raw_chunk[0]), int(raw_chunk[1]))
                except (TypeError, ValueError):
                    chunk = (0, 0)
            else:
                chunk = (0, 0)
            source_text = opportunity_source_label(entry.get("source", "unknown"), short=False)
            title = str(entry.get("title", "Opportunity")).strip() or "Opportunity"
            preview_lines.append(
                f"O{int(entry.get('id', 0))} {title} @ {chunk} from {source_text}"
            )

        self.sim.emit(Event(
            "opportunity_added",
            eid=self.player_eid,
            count=len(new_entries),
            lines=tuple(preview_lines),
            remaining=max(0, len(new_entries) - len(preview_lines)),
        ))

    def _emit_report(self, limit=8):
        refresh_dynamic_opportunities(self.sim, self.player_eid)
        board = evaluate_opportunity_board(self.sim, self.player_eid, limit=max(1, int(limit)))
        title = (
            f"Opportunities ({int(board.get('active_count', 0))} active / "
            f"{int(board.get('completed_count', 0))} done)"
        )
        self.sim.emit(Event(
            "opportunity_report",
            eid=self.player_eid,
            title=title,
            lines=list(board.get("lines", ())),
            remaining=int(board.get("remaining", 0)),
            summary=str(board.get("summary_line", "")).strip(),
        ))

    def on_player_action(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        action = str(event.data.get("action", "")).strip().lower()
        if action == "opportunity_report":
            self._emit_report(limit=8)

    def _ensure_activity_state(self):
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        state = traits.get("recent_opportunity_actions")
        if not isinstance(state, dict):
            state = {"properties": {}, "buildings": {}, "chunks": {}}
            traits["recent_opportunity_actions"] = state
        return state

    def _remember_opportunity_activity(self, *, property_id=None, building_id=None, chunk=None, tag=""):
        tag = str(tag or "").strip().lower()
        property_id = str(property_id or "").strip()
        building_id = str(building_id or "").strip()
        if isinstance(chunk, (list, tuple)) and len(chunk) == 2:
            try:
                chunk = (int(chunk[0]), int(chunk[1]))
            except (TypeError, ValueError):
                chunk = None
        else:
            chunk = None
        if not tag or (not property_id and not building_id and chunk is None):
            return

        state = self._ensure_activity_state()
        current_tick = int(getattr(self.sim, "tick", 0))
        for bucket_key, site_id in (("properties", property_id), ("buildings", building_id)):
            if not site_id:
                continue
            bucket = state.get(bucket_key)
            if not isinstance(bucket, dict):
                bucket = {}
                state[bucket_key] = bucket
            tag_ticks = bucket.get(site_id)
            if not isinstance(tag_ticks, dict):
                tag_ticks = {}
                bucket[site_id] = tag_ticks
            tag_ticks[tag] = current_tick
        if chunk is not None:
            chunk_key = f"{int(chunk[0])},{int(chunk[1])}"
            chunk_bucket = state.get("chunks")
            if not isinstance(chunk_bucket, dict):
                chunk_bucket = {}
                state["chunks"] = chunk_bucket
            tag_ticks = chunk_bucket.get(chunk_key)
            if not isinstance(tag_ticks, dict):
                tag_ticks = {}
                chunk_bucket[chunk_key] = tag_ticks
            tag_ticks[tag] = current_tick

        cutoff = current_tick - 24
        for bucket_key in ("properties", "buildings", "chunks"):
            bucket = state.get(bucket_key)
            if not isinstance(bucket, dict):
                continue
            for raw_site_id, tag_ticks in list(bucket.items()):
                if not isinstance(tag_ticks, dict):
                    bucket.pop(raw_site_id, None)
                    continue
                for raw_tag, raw_tick in list(tag_ticks.items()):
                    if _int_or_default(raw_tick, default=-10_000) < cutoff:
                        tag_ticks.pop(raw_tag, None)
                if not tag_ticks:
                    bucket.pop(raw_site_id, None)

    def _remember_opportunity_activity_for_property(self, property_id, tag):
        property_id = str(property_id or "").strip()
        if not property_id:
            return
        prop = self.sim.properties.get(property_id) if hasattr(self.sim, "properties") else None
        building_id = _building_id_from_property(prop) if isinstance(prop, dict) else ""
        chunk = None
        if isinstance(prop, dict):
            try:
                chunk = self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
            except (TypeError, ValueError):
                chunk = None
        self._remember_opportunity_activity(property_id=property_id, building_id=building_id, chunk=chunk, tag=tag)

    def _remember_opportunity_activity_at_player_site(self, tag):
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if not pos:
            return
        prop = _property_covering(self.sim, pos.x, pos.y, pos.z) or self.sim.property_at(pos.x, pos.y, pos.z)
        if not isinstance(prop, dict):
            return
        self._remember_opportunity_activity(
            property_id=prop.get("id"),
            building_id=_building_id_from_property(prop),
            chunk=self.sim.chunk_coords(int(pos.x), int(pos.y)),
            tag=tag,
        )

    def _remember_opportunity_chunk_activity(self, chunk, tag):
        self._remember_opportunity_activity(chunk=chunk, tag=tag)

    def _remember_opportunity_property_interaction(self, property_id):
        property_id = str(property_id or "").strip()
        if not property_id:
            return
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        current_tick = int(getattr(self.sim, "tick", 0))

        recent_props = traits.get("recent_property_interactions")
        if not isinstance(recent_props, dict):
            recent_props = {}
            traits["recent_property_interactions"] = recent_props
        recent_props[property_id] = current_tick

        prop = self.sim.properties.get(property_id) if hasattr(self.sim, "properties") else None
        building_id = _building_id_from_property(prop) if isinstance(prop, dict) else ""
        if building_id:
            recent_buildings = traits.get("recent_building_interactions")
            if not isinstance(recent_buildings, dict):
                recent_buildings = {}
                traits["recent_building_interactions"] = recent_buildings
            recent_buildings[building_id] = current_tick
        else:
            recent_buildings = traits.get("recent_building_interactions")

        cutoff = current_tick - 16
        for raw_property_id, raw_tick in list(recent_props.items()):
            if _int_or_default(raw_tick, default=-10_000) < cutoff:
                recent_props.pop(raw_property_id, None)
        if isinstance(recent_buildings, dict):
            for raw_building_id, raw_tick in list(recent_buildings.items()):
                if _int_or_default(raw_tick, default=-10_000) < cutoff:
                    recent_buildings.pop(raw_building_id, None)

    def on_property_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._remember_opportunity_property_interaction(event.data.get("property_id"))

    def on_npc_interacted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("dialog_modal")):
            return
        self._remember_opportunity_activity_at_player_site("contact")

    def on_site_service_used(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_id = event.data.get("property_id")
        self._remember_opportunity_activity_for_property(property_id, "service")
        if str(event.data.get("service", "")).strip().lower() == "intel":
            self._remember_opportunity_activity_for_property(property_id, "intel")

    def on_site_intel_report(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._remember_opportunity_activity_for_property(event.data.get("property_id"), "intel")

    def on_trade_bought(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._remember_opportunity_activity_for_property(event.data.get("property_id"), "trade")

    def on_trade_sold(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._remember_opportunity_activity_for_property(event.data.get("property_id"), "trade")

    def on_bank_transaction(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._remember_opportunity_activity_for_property(event.data.get("property_id"), "finance")

    def on_insurance_policy_purchased(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._remember_opportunity_activity_for_property(event.data.get("property_id"), "finance")

    def on_stakeout_intel_gained(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_id = event.data.get("property_id")
        self._remember_opportunity_activity_for_property(property_id, "stakeout")
        self._remember_opportunity_activity_for_property(property_id, "intel")

    def on_overworld_discovery_found(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        raw_chunk = event.data.get("chunk")
        if isinstance(raw_chunk, (list, tuple)) and len(raw_chunk) == 2:
            try:
                chunk = (int(raw_chunk[0]), int(raw_chunk[1]))
            except (TypeError, ValueError):
                chunk = None
        else:
            chunk = None
        if chunk is None:
            return
        self._remember_opportunity_chunk_activity(chunk, "discovery")
        kind = str(event.data.get("kind", "")).strip().lower()
        if kind:
            self._remember_opportunity_chunk_activity(chunk, f"discovery_{kind}")
        if kind == "landmark":
            self._remember_opportunity_chunk_activity(chunk, "intel")

    def update(self):
        self._ensure_seeded()
        tick = int(getattr(self.sim, "tick", 0))
        if tick - self.last_refresh_tick >= self.refresh_interval:
            refresh_dynamic_opportunities(self.sim, self.player_eid)
            self.last_refresh_tick = tick
        self._emit_new_opportunity_log()
        for notice in stage_active_opportunities(self.sim, self.player_eid):
            self.sim.log.add(notice, channel="opportunity", priority="high")

        completed = resolve_opportunities(self.sim, self.player_eid)
        if not completed:
            return

        active_count = int(opportunity_known_count(self.sim, self.player_eid, observer_eid=self.player_eid))
        for entry in completed:
            raw_chunk = entry.get("chunk", (0, 0))
            if isinstance(raw_chunk, (list, tuple)) and len(raw_chunk) == 2:
                try:
                    chunk = (int(raw_chunk[0]), int(raw_chunk[1]))
                except (TypeError, ValueError):
                    chunk = (0, 0)
            else:
                chunk = (0, 0)

            reward = dict(entry.get("reward_applied", {}))
            self.sim.emit(Event(
                "opportunity_completed",
                eid=self.player_eid,
                opportunity_id=int(entry.get("id", 0)),
                title=str(entry.get("title", "Opportunity")).strip() or "Opportunity",
                summary=str(entry.get("summary", "")).strip(),
                chunk=chunk,
                source=str(entry.get("source", "unknown")).strip(),
                risk=str(entry.get("risk", "low")).strip(),
                playstyles=tuple(entry.get("playstyles", ())),
                reward=reward,
                reward_text=format_reward_text(reward),
                completion_reason=str(entry.get("completion_reason", "")).strip(),
                active_remaining=active_count,
            ))

class RivalOperatorSystem(System):

    RIVAL_COUNT = 3
    DECISION_INTERVAL = 90
    TRAVEL_INTERVAL = 55
    ACTION_INTERVAL = 210
    LOCAL_ACTION_INTERVAL = 72
    RUMOR_INTERVAL = 150
    HOME_MIN_DISTANCE = 2
    HOME_MAX_DISTANCE = 7
    TARGET_DECAY_TICKS = 320
    RECOVERY_TICKS = 260
    LOCAL_RESOLVE_DISTANCE = 2
    LOCAL_SPOTTED_COOLDOWN = 60
    SPAWN_MIN_PLAYER_DISTANCE = 5

    PUBLIC_MASKS = (
        "clean",
        "rough",
        "quiet",
        "slick",
        "blunt",
        "bright",
    )
    HUSTLES = (
        "cash",
        "network",
        "intel",
        "predator",
    )
    REPUTATIONS = (
        "steady",
        "hungry",
        "cold",
        "restless",
        "professional",
        "dangerous",
    )
    RIVAL_FOLLOWUP_LABELS = (
        "Rival Aftermath:",
        "Burned Trail:",
        "Last Trace:",
    )

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.sim.events.subscribe("npc_downed", self.on_npc_downed)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)

    def _state(self):
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        state = traits.get("rival_operators")
        if not isinstance(state, dict):
            state = {}
            traits["rival_operators"] = state
        if not isinstance(state.get("rivals"), list):
            state["rivals"] = []
        state["seeded"] = bool(state.get("seeded", False))
        state.setdefault("seed_tick", -1)
        return state

    def _player_pos(self):
        return self.sim.ecs.get(Position).get(self.player_eid)

    def _player_chunk_coord(self):
        pos = self._player_pos()
        if pos:
            cx, cy = self.sim.chunk_coords(pos.x, pos.y)
            return (int(cx), int(cy))
        active = getattr(self.sim, "active_chunk_coord", None)
        if isinstance(active, (list, tuple)) and len(active) == 2:
            try:
                return (int(active[0]), int(active[1]))
            except (TypeError, ValueError):
                return (0, 0)
        return (0, 0)

    def _normalize_chunk(self, value, fallback=None):
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                pass
        if isinstance(fallback, (list, tuple)) and len(fallback) == 2:
            return (int(fallback[0]), int(fallback[1]))
        return (0, 0)

    def _chunk_distance(self, a, b):
        first = self._normalize_chunk(a)
        second = self._normalize_chunk(b)
        return _manhattan(first[0], first[1], second[0], second[1])

    def _normalize_rival_runtime_state(self, rival):
        if not isinstance(rival, dict):
            return
        raw_eid = rival.get("materialized_eid")
        try:
            eid = int(raw_eid)
        except (TypeError, ValueError):
            eid = 0
        rival["materialized_eid"] = eid if eid > 0 else None
        rival["status"] = str(rival.get("status", "hustling")).strip().lower() or "hustling"
        rival.setdefault("last_materialized_tick", -10_000)
        rival.setdefault("last_spotted_tick", -10_000)
        rival.setdefault("recover_until_tick", -1)
        if not isinstance(rival.get("inventory_snapshot"), list):
            rival["inventory_snapshot"] = []
        if not isinstance(rival.get("weapon_loadout_snapshot"), dict):
            rival["weapon_loadout_snapshot"] = {}
        if not isinstance(rival.get("armor_loadout_snapshot"), dict):
            rival["armor_loadout_snapshot"] = {}
        if not isinstance(rival.get("vitality_snapshot"), dict):
            rival["vitality_snapshot"] = {}

    def _rival_is_available(self, rival):
        self._normalize_rival_runtime_state(rival)
        if str(rival.get("status", "")).strip().lower() in {"dead", "retired"}:
            return False
        return int(rival.get("recover_until_tick", -1)) <= int(self.sim.tick)

    def _recover_rival_if_ready(self, rival):
        self._normalize_rival_runtime_state(rival)
        if str(rival.get("status", "")).strip().lower() != "wounded":
            return
        if int(self.sim.tick) < int(rival.get("recover_until_tick", -1)):
            return
        vitality_snapshot = rival.get("vitality_snapshot")
        if isinstance(vitality_snapshot, dict) and vitality_snapshot:
            max_hp = max(1, int(vitality_snapshot.get("max_hp", 1) or 1))
            recover_to_hp = max(
                1,
                min(
                    max_hp,
                    int(vitality_snapshot.get("recover_to_hp", max(1, round(max_hp * 0.38))) or 1),
                ),
            )
            heal_ratio = 0.34 + (float(rival.get("caution", 0.5)) * 0.18) + (float(rival.get("discipline", 0.5)) * 0.14)
            healed_hp = max(recover_to_hp, int(round(max_hp * min(0.72, heal_ratio))))
            vitality_snapshot["hp"] = min(max_hp, max(1, healed_hp))
            vitality_snapshot["downed"] = False
            vitality_snapshot["downed_tick"] = None
        rival["status"] = "regrouping"
        rival["recover_until_tick"] = -1
        rival["heat"] = max(0, int(rival.get("heat", 0) or 0) - 4)

    def _materialized_eid(self, rival):
        self._normalize_rival_runtime_state(rival)
        eid = rival.get("materialized_eid")
        if not eid:
            return None
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None:
            rival["materialized_eid"] = None
            return None
        return int(eid)

    def _rival_for_materialized_eid(self, eid):
        try:
            target_eid = int(eid)
        except (TypeError, ValueError):
            return None
        if target_eid <= 0:
            return None
        for rival in self._state().get("rivals", ()):
            self._normalize_rival_runtime_state(rival)
            if int(rival.get("materialized_eid") or 0) == target_eid:
                return rival
        return None

    def _rival_rng(self, rival, salt):
        rival_id = int(rival.get("id", 0) or 0)
        return random.Random(f"{self.sim.seed}:rival:{rival_id}:{salt}:{int(self.sim.tick)}")

    def _active_opportunities(self):
        traits = getattr(self.sim, "world_traits", {})
        opp_state = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
        active = opp_state.get("active", ()) if isinstance(opp_state, dict) else ()
        return [entry for entry in active if isinstance(entry, dict)]

    def _is_rival_followup_entry(self, entry):
        if not isinstance(entry, dict):
            return False
        kind = str(entry.get("kind", "")).strip().lower()
        if kind == "rival_followup":
            return True
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        return bool(requirements.get("rival_followup"))

    def _collapse_repeated_rival_followup_labels(self, text):
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        for label in self.RIVAL_FOLLOWUP_LABELS:
            pattern = rf"(?:{re.escape(label)}\s*){{2,}}"
            cleaned = re.sub(pattern, f"{label} ", cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    def _normalize_rival_followup_entry(self, entry):
        if not self._is_rival_followup_entry(entry):
            return False
        changed = False
        title = self._collapse_repeated_rival_followup_labels(entry.get("title", ""))
        summary = self._collapse_repeated_rival_followup_labels(entry.get("summary", ""))
        if title and title != str(entry.get("title", "")).strip():
            entry["title"] = title
            changed = True
        if summary and summary != str(entry.get("summary", "")).strip():
            entry["summary"] = summary
            changed = True
        return changed

    def _normalize_rival_followup_opportunities(self):
        traits = getattr(self.sim, "world_traits", {})
        opp_state = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
        if not isinstance(opp_state, dict):
            return False
        changed = False
        for bucket in ("active", "completed"):
            entries = opp_state.get(bucket, ())
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict):
                    changed = self._normalize_rival_followup_entry(entry) or changed
        return changed

    def _target_entry(self, rival):
        target_id = int(rival.get("target_opportunity_id", 0) or 0)
        if target_id <= 0:
            return None
        for entry in self._active_opportunities():
            if int(entry.get("id", 0) or 0) == target_id:
                return entry
        return None

    def _clone_inventory_items(self, items, *, owner_eid=None):
        cloned = []
        for entry in list(items or ()):
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("item_id", "")).strip()
            instance_id = str(entry.get("instance_id", "")).strip()
            if not item_id or not instance_id:
                continue
            try:
                quantity = max(1, int(entry.get("quantity", 1) or 1))
            except (TypeError, ValueError):
                quantity = 1
            cloned.append({
                "instance_id": instance_id,
                "item_id": item_id,
                "quantity": quantity,
                "owner_eid": owner_eid,
                "owner_tag": str(entry.get("owner_tag", "npc") or "npc").strip() or "npc",
                "metadata": dict(entry.get("metadata") or {}),
            })
        return cloned

    def _snapshot_has_physical_state(self, rival):
        self._normalize_rival_runtime_state(rival)
        return bool(
            rival.get("inventory_snapshot")
            or rival.get("weapon_loadout_snapshot")
            or rival.get("armor_loadout_snapshot")
            or rival.get("vitality_snapshot")
        )

    def _capture_materialized_state(self, rival):
        eid = self._materialized_eid(rival)
        if not eid:
            return False

        inventory = self.sim.ecs.get(Inventory).get(eid)
        weapon_loadout = self.sim.ecs.get(WeaponLoadout).get(eid)
        armor_loadout = self.sim.ecs.get(ArmorLoadout).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)

        rival["inventory_snapshot"] = self._clone_inventory_items(
            getattr(inventory, "items", ()) if inventory else (),
            owner_eid=None,
        )
        rival["weapon_loadout_snapshot"] = {
            "weapon_ids": list(getattr(weapon_loadout, "weapon_ids", ()) or ()),
            "equipped_weapon_id": getattr(weapon_loadout, "equipped_weapon_id", None),
            "reserve_ammo": dict(getattr(weapon_loadout, "reserve_ammo", {}) or {}),
            "weapon_instances": {
                str(weapon_id): dict(instance or {})
                for weapon_id, instance in dict(getattr(weapon_loadout, "weapon_instances", {}) or {}).items()
                if str(weapon_id).strip()
            },
            "cooldown_until_tick": int(getattr(weapon_loadout, "cooldown_until_tick", 0) or 0),
            "last_fire_tick": int(getattr(weapon_loadout, "last_fire_tick", -10_000) or -10_000),
        } if weapon_loadout else {}
        rival["armor_loadout_snapshot"] = {
            "slot": str(getattr(armor_loadout, "slot", "body") or "body").strip().lower() or "body",
            "equipped_instance_id": getattr(armor_loadout, "equipped_instance_id", None),
            "equipped_item_id": getattr(armor_loadout, "equipped_item_id", None),
            "equipped_name": getattr(armor_loadout, "equipped_name", None),
            "damage_reduction": float(getattr(armor_loadout, "damage_reduction", 0.0) or 0.0),
        } if armor_loadout else {}
        rival["vitality_snapshot"] = {
            "max_hp": int(getattr(vitality, "max_hp", 1) or 1),
            "hp": int(getattr(vitality, "hp", 0) or 0),
            "downed": bool(getattr(vitality, "downed", False)),
            "recover_to_hp": int(getattr(vitality, "recover_to_hp", 1) or 1),
            "downed_tick": getattr(vitality, "downed_tick", None),
            "downed_count": int(getattr(vitality, "downed_count", 0) or 0),
        } if vitality else {}
        return True

    def _restore_materialized_state(self, rival, eid):
        self._normalize_rival_runtime_state(rival)
        if not self._snapshot_has_physical_state(rival):
            return False

        inventory = self.sim.ecs.get(Inventory).get(eid)
        weapon_loadout = self.sim.ecs.get(WeaponLoadout).get(eid)
        armor_loadout = self.sim.ecs.get(ArmorLoadout).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)

        if inventory:
            inventory.items = self._clone_inventory_items(
                rival.get("inventory_snapshot", ()),
                owner_eid=eid,
            )

        weapon_snapshot = rival.get("weapon_loadout_snapshot", {})
        if weapon_loadout and isinstance(weapon_snapshot, dict):
            weapon_loadout.weapon_ids = [
                str(weapon_id).strip()
                for weapon_id in list(weapon_snapshot.get("weapon_ids", ()) or ())
                if str(weapon_id).strip()
            ]
            weapon_loadout.equipped_weapon_id = (
                str(weapon_snapshot.get("equipped_weapon_id", "")).strip()
                or (weapon_loadout.weapon_ids[0] if weapon_loadout.weapon_ids else None)
            )
            weapon_loadout.reserve_ammo = {
                str(weapon_id).strip(): int(amount or 0)
                for weapon_id, amount in dict(weapon_snapshot.get("reserve_ammo", {}) or {}).items()
                if str(weapon_id).strip()
            }
            weapon_loadout.weapon_instances = {
                str(weapon_id).strip(): dict(instance or {})
                for weapon_id, instance in dict(weapon_snapshot.get("weapon_instances", {}) or {}).items()
                if str(weapon_id).strip()
            }
            weapon_loadout.cooldown_until_tick = int(weapon_snapshot.get("cooldown_until_tick", 0) or 0)
            weapon_loadout.last_fire_tick = int(weapon_snapshot.get("last_fire_tick", -10_000) or -10_000)

        armor_snapshot = rival.get("armor_loadout_snapshot", {})
        if armor_loadout and isinstance(armor_snapshot, dict):
            armor_loadout.slot = str(armor_snapshot.get("slot", "body") or "body").strip().lower() or "body"
            armor_loadout.equipped_instance_id = (
                str(armor_snapshot.get("equipped_instance_id", "")).strip() or None
            )
            armor_loadout.equipped_item_id = (
                str(armor_snapshot.get("equipped_item_id", "")).strip() or None
            )
            armor_loadout.equipped_name = (
                str(armor_snapshot.get("equipped_name", "")).strip() or None
            )
            try:
                armor_loadout.damage_reduction = float(armor_snapshot.get("damage_reduction", 0.0) or 0.0)
            except (TypeError, ValueError):
                armor_loadout.damage_reduction = 0.0

        vitality_snapshot = rival.get("vitality_snapshot", {})
        if vitality and isinstance(vitality_snapshot, dict) and vitality_snapshot:
            max_hp = max(1, int(vitality_snapshot.get("max_hp", vitality.max_hp) or vitality.max_hp))
            vitality.max_hp = max_hp
            vitality.recover_to_hp = max(
                1,
                min(max_hp, int(vitality_snapshot.get("recover_to_hp", vitality.recover_to_hp) or vitality.recover_to_hp)),
            )
            vitality.hp = max(0, min(max_hp, int(vitality_snapshot.get("hp", vitality.hp) or vitality.hp)))
            vitality.downed = bool(vitality_snapshot.get("downed", False))
            vitality.downed_tick = vitality_snapshot.get("downed_tick")
            vitality.downed_count = max(0, int(vitality_snapshot.get("downed_count", 0) or 0))

        return True

    def _add_rival_snapshot_item(self, rival, item_id, *, quantity=1, metadata=None):
        item_id = str(item_id or "").strip()
        item_def = ITEM_CATALOG.get(item_id)
        if not item_id or not item_def:
            return False

        remaining = max(1, int(quantity))
        stack_max = max(1, int(item_def.get("stack_max", 1) or 1))
        snapshot = rival.get("inventory_snapshot")
        if not isinstance(snapshot, list):
            snapshot = []
            rival["inventory_snapshot"] = snapshot

        if stack_max > 1:
            for entry in snapshot:
                if str(entry.get("item_id", "")).strip() != item_id:
                    continue
                current = max(0, int(entry.get("quantity", 0) or 0))
                if current >= stack_max:
                    continue
                amount = min(stack_max - current, remaining)
                entry["metadata"] = merge_item_stack_metadata(
                    item_id,
                    existing_metadata=entry.get("metadata"),
                    existing_quantity=current,
                    incoming_metadata=metadata,
                    incoming_quantity=amount,
                )
                entry["quantity"] = current + amount
                remaining -= amount
                if remaining <= 0:
                    return True

        rival_id = int(rival.get("id", 0) or 0)
        while remaining > 0:
            amount = min(stack_max, remaining)
            snapshot.append({
                "instance_id": f"rival-{rival_id}-{item_id}-{len(snapshot) + 1}",
                "item_id": item_id,
                "quantity": amount,
                "owner_eid": None,
                "owner_tag": "npc",
                "metadata": prepare_item_stack_metadata(item_id, metadata=metadata, quantity=amount),
            })
            remaining -= amount
        return True

    def _inventory_has_reserved_opportunity_item(self, opportunity_id):
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        if not inventory:
            return False
        target_id = int(opportunity_id or 0)
        for entry in list(getattr(inventory, "items", ()) or ()):
            metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
            try:
                if int(metadata.get("quest_opportunity_id", 0) or 0) == target_id:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _player_is_committed_to_opportunity(self, entry):
        if not isinstance(entry, dict):
            return False
        opportunity_id = int(entry.get("id", 0) or 0)
        if opportunity_id <= 0:
            return False
        if self._inventory_has_reserved_opportunity_item(opportunity_id):
            return True
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        if bool(requirements.get("player_accepted")):
            return True
        intel = opportunity_intel_for_observer(self.sim, self.player_eid, opportunity_id)
        awareness = str((intel or {}).get("awareness_state", "")).strip().lower()
        if awareness != "confirmed":
            return False
        player_chunk = self._player_chunk_coord()
        target_chunk = self._normalize_chunk(entry.get("chunk"), fallback=player_chunk)
        return self._chunk_distance(player_chunk, target_chunk) <= 1

    def _seed_rivals(self):
        state = self._state()
        if state.get("seeded") and state.get("rivals"):
            for rival in state.get("rivals", ()):
                self._normalize_rival_runtime_state(rival)
            return state["rivals"]

        origin = self._player_chunk_coord()
        rivals = []
        used_names = set()
        for idx in range(self.RIVAL_COUNT):
            rng = random.Random(f"{self.sim.seed}:rival-seed:{idx}")
            name = _generate_human_personal_name(
                self.sim,
                rng,
                avoid_names=used_names,
            )
            if not str(name).strip():
                name = f"Operator {idx + 1}"
            used_names.add(name)

            home = origin
            for _attempt in range(24):
                dx = rng.randint(-self.HOME_MAX_DISTANCE, self.HOME_MAX_DISTANCE)
                dy = rng.randint(-self.HOME_MAX_DISTANCE, self.HOME_MAX_DISTANCE)
                if self.HOME_MIN_DISTANCE <= abs(dx) + abs(dy) <= self.HOME_MAX_DISTANCE:
                    home = (origin[0] + dx, origin[1] + dy)
                    break

            rival = {
                "id": idx + 1,
                "name": name,
                "public_mask": rng.choice(self.PUBLIC_MASKS),
                "reputation": rng.choice(self.REPUTATIONS),
                "hustle": rng.choice(self.HUSTLES),
                "honesty": round(rng.uniform(0.2, 0.9), 2),
                "aggression": round(rng.uniform(0.18, 0.88), 2),
                "caution": round(rng.uniform(0.18, 0.88), 2),
                "discipline": round(rng.uniform(0.2, 0.9), 2),
                "nerve": round(rng.uniform(0.24, 0.92), 2),
                "greed": round(rng.uniform(0.25, 0.94), 2),
                "charm": round(rng.uniform(0.2, 0.9), 2),
                "violence": round(rng.uniform(0.08, 0.9), 2),
                "gear_tier": rng.randint(1, 4),
                "credits": rng.randint(36, 110),
                "standing": rng.randint(0, 4),
                "intel": rng.randint(0, 3),
                "heat": rng.randint(0, 18),
                "home_chunk": home,
                "current_chunk": home,
                "target_chunk": home,
                "target_opportunity_id": 0,
                "last_decision_tick": -10_000,
                "last_move_tick": -10_000,
                "last_action_tick": -10_000,
                "last_rumor_tick": -10_000,
                "resolved_count": 0,
                "status": "hustling",
                "materialized_eid": None,
                "last_materialized_tick": -10_000,
                "last_spotted_tick": -10_000,
                "recover_until_tick": -1,
                "inventory_snapshot": [],
                "weapon_loadout_snapshot": {},
                "armor_loadout_snapshot": {},
                "vitality_snapshot": {},
            }
            self._normalize_rival_runtime_state(rival)
            rivals.append(rival)

        state["rivals"] = rivals
        state["seeded"] = True
        state["seed_tick"] = int(self.sim.tick)
        self.sim.emit(Event(
            "rival_operator_seeded",
            eid=self.player_eid,
            count=len(rivals),
        ))
        return rivals

    def _entry_score_for_rival(self, rival, entry):
        if not isinstance(entry, dict):
            return -999.0
        if self._is_rival_followup_entry(entry):
            return -999.0
        if self._player_is_committed_to_opportunity(entry):
            return -999.0

        current_chunk = self._normalize_chunk(rival.get("current_chunk"))
        target_chunk = self._normalize_chunk(entry.get("chunk"), fallback=current_chunk)
        player_chunk = self._player_chunk_coord()
        distance = self._chunk_distance(current_chunk, target_chunk)
        player_distance = self._chunk_distance(player_chunk, target_chunk)
        styles = {
            str(style).strip().lower()
            for style in entry.get("playstyles", ())
            if str(style).strip()
        }
        reward = dict(entry.get("reward", {}))
        risk = str(entry.get("risk", "low")).strip().lower() or "low"
        kind = str(entry.get("kind", "")).strip().lower()
        hustle = str(rival.get("hustle", "cash")).strip().lower()
        credits = max(0, int(reward.get("credits", 0) or 0))
        standing = max(0, int(reward.get("standing", 0) or 0))
        intel = max(0, int(reward.get("intel", 0) or 0))

        score = 1.0
        score += max(0.0, 3.2 - (distance * 0.48))
        if hustle == "cash":
            score += min(3.2, credits / 11.0)
            if "economic" in styles:
                score += 1.3
        elif hustle == "network":
            score += min(3.0, standing * 1.5)
            if "social" in styles:
                score += 1.2
        elif hustle == "intel":
            score += min(3.4, intel * 1.7)
            if "stealth" in styles:
                score += 1.2
        else:
            if "combat" in styles:
                score += 1.45
            if kind == "contract_kill":
                score += 1.2
            score += float(rival.get("violence", 0.4)) * 1.1

        if "stealth" in styles:
            score += float(rival.get("caution", 0.5)) * 0.7
            score += float(rival.get("discipline", 0.5)) * 0.4
        if "social" in styles:
            score += float(rival.get("charm", 0.5)) * 0.7
        if "combat" in styles:
            score += float(rival.get("aggression", 0.5)) * 0.8
            score += float(rival.get("nerve", 0.5)) * 0.45

        if risk == "hazardous":
            score += (float(rival.get("aggression", 0.5)) * 0.5) + (float(rival.get("nerve", 0.5)) * 0.6)
            score -= float(rival.get("caution", 0.5)) * 0.45
        elif risk == "exposed":
            score += float(rival.get("discipline", 0.5)) * 0.3
            score -= float(rival.get("honesty", 0.5)) * 0.08
        else:
            score += float(rival.get("caution", 0.5)) * 0.2

        if kind == "contract_kill" and float(rival.get("violence", 0.0)) < 0.38:
            score -= 1.6
        if player_distance <= 1:
            score -= 1.25
        elif player_distance == 2:
            score -= 0.45

        intel = opportunity_intel_for_observer(self.sim, self.player_eid, int(entry.get("id", 0) or 0))
        awareness = str((intel or {}).get("awareness_state", "")).strip().lower()
        if awareness == "confirmed" and player_distance <= 2:
            score -= 0.75
        return score

    def _choose_target_for_rival(self, rival):
        scored = []
        for entry in self._active_opportunities():
            score = self._entry_score_for_rival(rival, entry)
            if score <= 0.05:
                continue
            scored.append((score, int(entry.get("id", 0) or 0), entry))
        if not scored:
            return None

        scored.sort(key=lambda row: (row[0], -row[1]), reverse=True)
        shortlist = scored[: min(3, len(scored))]
        total = sum(max(0.1, row[0]) for row in shortlist)
        chooser = self._rival_rng(rival, "choose_target")
        pick = chooser.uniform(0.0, total)
        cursor = 0.0
        selected = shortlist[0][2]
        for score, _opp_id, entry in shortlist:
            cursor += max(0.1, score)
            if pick <= cursor:
                selected = entry
                break
        return selected

    def _choose_wander_chunk(self, rival):
        home = self._normalize_chunk(rival.get("home_chunk"))
        chooser = self._rival_rng(rival, "wander")
        for _attempt in range(10):
            dx = chooser.randint(-2, 2)
            dy = chooser.randint(-2, 2)
            if dx == 0 and dy == 0:
                continue
            return (home[0] + dx, home[1] + dy)
        return home

    def _refresh_target_for_rival(self, rival):
        target = self._target_entry(rival)
        if target is not None:
            age = int(self.sim.tick) - int(rival.get("last_decision_tick", -10_000))
            if age <= self.TARGET_DECAY_TICKS:
                rival["target_chunk"] = self._normalize_chunk(target.get("chunk"), fallback=rival.get("current_chunk"))
                return target

        selected = self._choose_target_for_rival(rival)
        if selected is None:
            rival["target_opportunity_id"] = 0
            rival["target_chunk"] = self._choose_wander_chunk(rival)
            rival["status"] = "circling"
            rival["last_decision_tick"] = int(self.sim.tick)
            return None

        rival["target_opportunity_id"] = int(selected.get("id", 0) or 0)
        rival["target_chunk"] = self._normalize_chunk(selected.get("chunk"), fallback=rival.get("current_chunk"))
        rival["status"] = "working"
        rival["last_decision_tick"] = int(self.sim.tick)
        return selected

    def _step_toward(self, current_chunk, target_chunk, *, chooser):
        current = self._normalize_chunk(current_chunk)
        target = self._normalize_chunk(target_chunk, fallback=current)
        if current == target:
            return current
        dx = int(target[0]) - int(current[0])
        dy = int(target[1]) - int(current[1])
        if dx != 0 and dy != 0:
            if chooser.random() < 0.5:
                return (current[0] + (1 if dx > 0 else -1), current[1])
            return (current[0], current[1] + (1 if dy > 0 else -1))
        if dx != 0:
            return (current[0] + (1 if dx > 0 else -1), current[1])
        return (current[0], current[1] + (1 if dy > 0 else -1))

    def _move_rival(self, rival):
        current = self._normalize_chunk(rival.get("current_chunk"))
        target = self._normalize_chunk(rival.get("target_chunk"), fallback=current)
        if current == target:
            return current
        chooser = self._rival_rng(rival, "move")
        next_chunk = self._step_toward(current, target, chooser=chooser)
        rival["current_chunk"] = next_chunk
        rival["last_move_tick"] = int(self.sim.tick)
        return next_chunk

    def _candidate_street_tiles(self, chunk_coord, *, reserved=None, min_player_distance=0):
        chunk = self._normalize_chunk(chunk_coord)
        reserved = {
            (int(pos[0]), int(pos[1]), int(pos[2]))
            for pos in (reserved or ())
            if isinstance(pos, (tuple, list)) and len(pos) >= 3
        }
        origin_x, origin_y = self.sim.chunk_origin(chunk[0], chunk[1])
        center_x = origin_x + max(2, self.sim.chunk_size // 2)
        center_y = origin_y + max(2, self.sim.chunk_size // 2)
        player_pos = self._player_pos()
        candidates = []
        for y in range(origin_y + 1, origin_y + self.sim.chunk_size - 1):
            for x in range(origin_x + 1, origin_x + self.sim.chunk_size - 1):
                pos = (x, y, 0)
                if pos in reserved:
                    continue
                if not self.sim.tilemap.is_walkable(x, y, 0):
                    continue
                if self.sim.structure_at(x, y, 0):
                    continue
                if self.sim.property_covering(x, y, 0):
                    continue
                if self.sim.tilemap.entities_at(x, y, 0):
                    continue
                if player_pos and _manhattan(player_pos.x, player_pos.y, x, y) < int(min_player_distance):
                    continue
                dist_center = _manhattan(x, y, center_x, center_y)
                candidates.append((dist_center, x, y, 0))
        candidates.sort(key=lambda row: (row[0], row[2], row[1]))
        return [(x, y, z) for _dist, x, y, z in candidates]

    def _chunk_focus_tile(self, chunk_coord):
        candidates = self._candidate_street_tiles(chunk_coord, min_player_distance=0)
        if candidates:
            return candidates[0]
        chunk = self._normalize_chunk(chunk_coord)
        origin_x, origin_y = self.sim.chunk_origin(chunk[0], chunk[1])
        center = (
            origin_x + max(2, self.sim.chunk_size // 2),
            origin_y + max(2, self.sim.chunk_size // 2),
            0,
        )
        if self.sim.tilemap.is_walkable(center[0], center[1], center[2]):
            return center
        return None

    def _opportunity_property(self, entry):
        if not isinstance(entry, dict):
            return None
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        property_id = requirements.get("property_id") or entry.get("property_id")
        if not property_id:
            key = str(entry.get("key", "")).strip().lower()
            if ":" in key:
                prefix, raw_value = key.split(":", 1)
                if prefix in {"contact", "intel"}:
                    try:
                        property_id = int(raw_value)
                    except (TypeError, ValueError):
                        property_id = raw_value
        if not property_id:
            return None
        return self.sim.properties.get(property_id)

    def _opportunity_focus(self, rival, entry, *, fallback_chunk=None):
        if not isinstance(entry, dict):
            return self._chunk_focus_tile(fallback_chunk or rival.get("current_chunk"))

        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        kill_target_eid = int(requirements.get("kill_target_eid", 0) or 0)
        if kill_target_eid > 0:
            pos = self.sim.ecs.get(Position).get(kill_target_eid)
            if pos:
                return (int(pos.x), int(pos.y), int(pos.z))

        prop = self._opportunity_property(entry)
        if prop:
            focus = _property_focus_position(prop)
            if focus:
                return focus

        visit_chunk = self._normalize_chunk(requirements.get("visit_chunk"), fallback=entry.get("chunk"))
        return self._chunk_focus_tile(visit_chunk or fallback_chunk or rival.get("current_chunk"))

    def _pick_materialize_spawn(self, rival, entry):
        current_chunk = self._normalize_chunk(rival.get("current_chunk"))
        focus = self._opportunity_focus(rival, entry, fallback_chunk=current_chunk)
        player_pos = self._player_pos()
        candidates = self._candidate_street_tiles(
            current_chunk,
            min_player_distance=self.SPAWN_MIN_PLAYER_DISTANCE,
        )
        if not candidates:
            candidates = self._candidate_street_tiles(current_chunk, min_player_distance=0)
        if not candidates:
            return focus or self._chunk_focus_tile(current_chunk)

        def _rank(pos):
            fx, fy, _fz = focus or pos
            player_dist = _manhattan(player_pos.x, player_pos.y, pos[0], pos[1]) if player_pos else 0
            focus_dist = _manhattan(pos[0], pos[1], fx, fy)
            return (-focus_dist, -player_dist, pos[1], pos[0])

        candidates.sort(key=_rank)
        shortlist = candidates[: min(18, len(candidates))]
        chooser = self._rival_rng(rival, "materialize")
        return chooser.choice(shortlist)

    def _add_rival_item(self, eid, item_id, *, quantity=1, metadata=None):
        inventory = self.sim.ecs.get(Inventory).get(eid)
        item_def = ITEM_CATALOG.get(item_id)
        if not inventory or not item_def:
            return False
        added, _instance_id = inventory.add_item(
            item_id=item_id,
            quantity=max(1, int(quantity)),
            stack_max=item_def.get("stack_max", 1),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="npc",
            metadata=metadata,
        )
        return bool(added)

    def _seed_rival_inventory(self, rival, eid):
        starting_credits = max(12, int(rival.get("credits", 0) or 0))
        self._add_rival_item(
            eid,
            "credstick_chip",
            quantity=1,
            metadata={"stored_credits": int(starting_credits)},
        )
        if float(rival.get("discipline", 0.5)) >= 0.58 or float(rival.get("caution", 0.5)) >= 0.6:
            self._add_rival_item(eid, "lockpick_kit")
        if float(rival.get("charm", 0.5)) >= 0.62 or float(rival.get("honesty", 0.5)) <= 0.36:
            self._add_rival_item(eid, "forged_badge")
        if float(rival.get("violence", 0.5)) >= 0.58 or int(rival.get("gear_tier", 1) or 1) >= 3:
            self._add_rival_item(eid, "smoke_tab")
        if int(rival.get("gear_tier", 1) or 1) >= 2:
            self._add_rival_item(eid, "micro_medkit")

    def _configure_materialized_rival(self, rival, eid, focus):
        identity = self.sim.ecs.get(CreatureIdentity).get(eid)
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        traits = self.sim.ecs.get(NPCTraits).get(eid)
        routine = self.sim.ecs.get(NPCRoutine).get(eid)
        occupation = self.sim.ecs.get(Occupation).get(eid)
        throttle = self.sim.ecs.get(MovementThrottle).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)

        if identity:
            identity.common_name = "operator"

        if occupation:
            occupation.career = "operator"
            occupation.workplace = None
            occupation.shift_start = 0
            occupation.shift_end = 0

        if routine:
            if routine.home is None:
                pos = self.sim.ecs.get(Position).get(eid)
                if pos:
                    routine.home = (int(pos.x), int(pos.y), int(pos.z))
            routine.work = focus

        if traits:
            traits.bravery = _clamp(
                (float(rival.get("nerve", 0.5)) * 0.55) + (float(rival.get("aggression", 0.5)) * 0.25),
                lo=0.2,
                hi=0.95,
            )
            traits.empathy = _clamp(
                (float(rival.get("charm", 0.5)) * 0.6) + (float(rival.get("honesty", 0.5)) * 0.2),
                lo=0.1,
                hi=0.9,
            )
            traits.loyalty = _clamp(
                (float(rival.get("discipline", 0.5)) * 0.55) + (float(rival.get("honesty", 0.5)) * 0.2),
                lo=0.12,
                hi=0.92,
            )
            traits.discipline = _clamp(float(rival.get("discipline", 0.5)), lo=0.18, hi=0.96)

        if throttle:
            throttle.speed_multiplier = _clamp(
                0.92 + (float(rival.get("discipline", 0.5)) * 0.18) + (float(rival.get("nerve", 0.5)) * 0.1),
                lo=0.8,
                hi=1.45,
            )

        restored_state = self._restore_materialized_state(rival, eid)
        if vitality and not restored_state:
            base_hp = max(int(vitality.max_hp), 10 + (int(rival.get("gear_tier", 1) or 1) * 2))
            vitality.max_hp = base_hp
            vitality.hp = min(base_hp, max(int(vitality.hp), base_hp - 1))
        elif vitality and bool(getattr(vitality, "downed", False)):
            vitality.downed = False
            vitality.downed_tick = None
            vitality.hp = max(1, min(int(vitality.max_hp), max(int(vitality.hp), int(vitality.recover_to_hp))))

        if ai and focus:
            ai.state = "patrolling"
            ai.target = focus
            ai.target_eid = None
        if will and focus:
            will.intent = "patrolling"
            will.score = 48.0
            will.target = focus
            will.target_eid = None

        if not restored_state:
            self._seed_rival_inventory(rival, eid)
            self._capture_materialized_state(rival)

    def _materialize_rival(self, rival):
        current_chunk = self._normalize_chunk(rival.get("current_chunk"))
        if current_chunk != self._player_chunk_coord():
            return None
        if not self._rival_is_available(rival):
            return None
        if self._materialized_eid(rival):
            return self._materialized_eid(rival)

        entry = self._target_entry(rival)
        focus = self._opportunity_focus(rival, entry, fallback_chunk=current_chunk)
        spawn_pos = self._pick_materialize_spawn(rival, entry)
        if not spawn_pos:
            return None

        spawn_rng = self._rival_rng(
            rival,
            f"spawn:{spawn_pos[0]}:{spawn_pos[1]}:{int(self.sim.tick) // 8}",
        )
        eid = _spawn_human(
            self.sim,
            spawn_rng,
            "thief",
            spawn_pos,
            career="operator",
            home=spawn_pos,
            work=focus or spawn_pos,
            shift_window=(0, 0),
            personal_name=str(rival.get("name", "Operator")).strip() or "Operator",
        )
        rival["materialized_eid"] = int(eid)
        rival["last_materialized_tick"] = int(self.sim.tick)
        self._configure_materialized_rival(rival, eid, focus or spawn_pos)
        return eid

    def _dematerialize_rival(self, rival):
        eid = self._materialized_eid(rival)
        if eid:
            self._capture_materialized_state(rival)
            self.sim.remove_entity(eid)
        rival["materialized_eid"] = None

    def _player_can_notice_rival(self, rival):
        eid = self._materialized_eid(rival)
        if not eid:
            return False
        player_pos = self._player_pos()
        rival_pos = self.sim.ecs.get(Position).get(eid)
        if not player_pos or not rival_pos:
            return False
        if int(player_pos.z) == int(rival_pos.z) and _manhattan(player_pos.x, player_pos.y, rival_pos.x, rival_pos.y) <= 8:
            return True
        return bool(_shared_observer_can_see_position(
            self.sim,
            observer_eid=self.player_eid,
            observer_x=player_pos.x,
            observer_y=player_pos.y,
            observer_z=player_pos.z,
            target_x=rival_pos.x,
            target_y=rival_pos.y,
            target_z=rival_pos.z,
            radius=10,
        ))

    def _spotted_summary(self, rival, entry):
        if not isinstance(entry, dict):
            return "working the block"
        intel = opportunity_intel_for_observer(self.sim, self.player_eid, int(entry.get("id", 0) or 0))
        title = str(entry.get("title", "a local lead")).strip() or "a local lead"
        if not intel:
            title = "a local lead"
        hustle = str(rival.get("hustle", "cash")).strip().lower() or "cash"
        if hustle == "intel":
            return f"casing {title}"
        if hustle == "network":
            return f"working people around {title}"
        if hustle == "predator":
            return f"stalking {title}"
        return f"circling {title}"

    def _maybe_emit_spotted_event(self, rival):
        if not self._player_can_notice_rival(rival):
            return
        if int(self.sim.tick) - int(rival.get("last_spotted_tick", -10_000)) < self.LOCAL_SPOTTED_COOLDOWN:
            return
        entry = self._target_entry(rival)
        self.sim.emit(Event(
            "rival_operator_spotted",
            eid=self.player_eid,
            rival_id=int(rival.get("id", 0) or 0),
            rival_name=str(rival.get("name", "operator")).strip() or "operator",
            rival_mask=str(rival.get("public_mask", "quiet")).strip().lower() or "quiet",
            rival_reputation=str(rival.get("reputation", "steady")).strip().lower() or "steady",
            hustle=str(rival.get("hustle", "cash")).strip().lower() or "cash",
            chunk=self._normalize_chunk(rival.get("current_chunk")),
            summary=self._spotted_summary(rival, entry),
        ))
        rival["last_spotted_tick"] = int(self.sim.tick)

    def _steer_materialized_rival(self, rival):
        eid = self._materialized_eid(rival)
        if not eid:
            return
        pos = self.sim.ecs.get(Position).get(eid)
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        routine = self.sim.ecs.get(NPCRoutine).get(eid)
        if not pos:
            rival["materialized_eid"] = None
            return

        rival["current_chunk"] = self._normalize_chunk(self.sim.chunk_coords(pos.x, pos.y), fallback=rival.get("current_chunk"))
        entry = self._target_entry(rival)
        focus = self._opportunity_focus(rival, entry, fallback_chunk=rival.get("current_chunk"))
        if routine:
            if routine.home is None:
                routine.home = (int(pos.x), int(pos.y), int(pos.z))
            routine.work = focus
        if ai and focus and ai.state not in {"downed", "surrendered", "protecting", "investigating"}:
            ai.state = "patrolling"
            ai.target = focus
            ai.target_eid = None
        if will and focus:
            will.intent = "patrolling"
            will.score = max(42.0, float(getattr(will, "score", 0.0) or 0.0))
            will.target = focus
            will.target_eid = None
        self._maybe_emit_spotted_event(rival)

    def _sync_materialization(self, rival):
        self._normalize_rival_runtime_state(rival)
        current_chunk = self._normalize_chunk(rival.get("current_chunk"))
        if current_chunk != self._player_chunk_coord() or not self._rival_is_available(rival):
            if self._materialized_eid(rival):
                self._dematerialize_rival(rival)
            return
        if not self._materialized_eid(rival):
            self._materialize_rival(rival)
        if self._materialized_eid(rival):
            self._steer_materialized_rival(rival)

    def _local_resolution_ready(self, rival, entry):
        eid = self._materialized_eid(rival)
        if not eid:
            return False
        pos = self.sim.ecs.get(Position).get(eid)
        if not pos:
            return False
        focus = self._opportunity_focus(rival, entry, fallback_chunk=rival.get("current_chunk"))
        if not focus:
            return True
        return int(pos.z) == int(focus[2]) and _manhattan(pos.x, pos.y, int(focus[0]), int(focus[1])) <= int(self.LOCAL_RESOLVE_DISTANCE)

    def _apply_rival_reward(self, rival, reward):
        reward = dict(reward or {})
        rival["credits"] = int(rival.get("credits", 0) or 0) + max(0, int(reward.get("credits", 0) or 0))
        rival["standing"] = int(rival.get("standing", 0) or 0) + max(0, int(reward.get("standing", 0) or 0))
        rival["intel"] = int(rival.get("intel", 0) or 0) + max(0, int(reward.get("intel", 0) or 0))

    def _mirror_reward_to_materialized_inventory(self, rival, reward):
        eid = self._materialized_eid(rival)
        reward = dict(reward or {})
        credits = max(0, int(reward.get("credits", 0) or 0))
        if credits > 0:
            metadata = {"stored_credits": int(credits)}
            self._add_rival_snapshot_item(rival, "credstick_chip", quantity=1, metadata=metadata)
            if eid:
                self._add_rival_item(eid, "credstick_chip", quantity=1, metadata=metadata)
        if max(0, int(reward.get("intel", 0) or 0)) > 0:
            self._add_rival_snapshot_item(rival, "forged_badge")
            if eid:
                self._add_rival_item(eid, "forged_badge")

    def _resolution_for_rival(self, rival, entry):
        risk = str(entry.get("risk", "low")).strip().lower() or "low"
        kind = str(entry.get("kind", "")).strip().lower()
        styles = {
            str(style).strip().lower()
            for style in entry.get("playstyles", ())
            if str(style).strip()
        }
        pressure = 0.0
        if risk == "hazardous":
            pressure = 0.23
        elif risk == "exposed":
            pressure = 0.12

        score = 0.28
        score += float(rival.get("discipline", 0.5)) * 0.18
        score += float(rival.get("nerve", 0.5)) * 0.15
        score += float(rival.get("gear_tier", 1)) * 0.08
        if "social" in styles:
            score += float(rival.get("charm", 0.5)) * 0.1
        if "combat" in styles:
            score += float(rival.get("aggression", 0.5)) * 0.1
        if "stealth" in styles:
            score += float(rival.get("caution", 0.5)) * 0.08
        if kind == "contract_kill":
            score += float(rival.get("violence", 0.5)) * 0.18
        score -= pressure

        roll = self._rival_rng(rival, f"resolve:{int(entry.get('id', 0) or 0)}").random()
        final = score + (roll * 0.24)
        if final >= 0.62:
            return "claimed"
        if final >= 0.42:
            return "burned"
        return "scouted"

    def _offscreen_casualty_outcome(self, rival, entry, *, resolution):
        if resolution not in {"claimed", "burned"}:
            return ""
        if self._materialized_eid(rival):
            return ""

        risk = str(entry.get("risk", "low")).strip().lower() or "low"
        kind = str(entry.get("kind", "")).strip().lower()
        styles = {
            str(style).strip().lower()
            for style in entry.get("playstyles", ())
            if str(style).strip()
        }

        injury_chance = 0.0
        if risk == "hazardous":
            injury_chance += 0.22
        elif risk == "exposed":
            injury_chance += 0.1
        if kind == "contract_kill":
            injury_chance += 0.16
        if "combat" in styles:
            injury_chance += 0.08
        if resolution == "burned":
            injury_chance += 0.08
        injury_chance += min(0.08, max(0.0, float(rival.get("heat", 0) or 0)) / 100.0)
        injury_chance -= float(rival.get("caution", 0.5)) * 0.1
        injury_chance -= float(rival.get("discipline", 0.5)) * 0.08
        injury_chance -= float(rival.get("nerve", 0.5)) * 0.04
        injury_chance -= int(rival.get("gear_tier", 1) or 1) * 0.025
        injury_chance = float(_clamp(injury_chance, lo=0.0, hi=0.52))

        lethal_chance = injury_chance * 0.22
        if risk == "hazardous":
            lethal_chance += 0.04
        if kind == "contract_kill":
            lethal_chance += 0.07
        if "combat" in styles:
            lethal_chance += 0.03
        if resolution == "burned":
            lethal_chance += 0.02
        lethal_chance -= int(rival.get("gear_tier", 1) or 1) * 0.01
        lethal_chance -= float(rival.get("caution", 0.5)) * 0.02
        lethal_chance = float(_clamp(lethal_chance, lo=0.0, hi=min(0.28, injury_chance)))

        roll = self._rival_rng(rival, f"casualty:{int(entry.get('id', 0) or 0)}:{resolution}").random()
        if roll < lethal_chance:
            return "dead"
        if roll < injury_chance:
            return "wounded"
        return ""

    def _offscreen_casualty_reason(self, entry, *, resolution, casualty):
        risk = str(entry.get("risk", "low")).strip().lower() or "low"
        kind = str(entry.get("kind", "")).strip().lower()
        if casualty == "dead":
            if kind == "contract_kill":
                return "contract_backfire"
            if risk == "hazardous":
                return "job_went_bad"
            return "ambushed_offscreen"
        if kind == "contract_kill":
            return "wounded_on_contract"
        if resolution == "burned":
            return "burned_on_scene"
        return "job_gone_loud"

    def _apply_offscreen_casualty(self, rival, entry, *, resolution):
        casualty = self._offscreen_casualty_outcome(rival, entry, resolution=resolution)
        if not casualty:
            return ""

        tick = int(self.sim.tick)
        rival["target_opportunity_id"] = 0
        rival["last_action_tick"] = tick
        rival["last_decision_tick"] = tick
        reason = self._offscreen_casualty_reason(entry, resolution=resolution, casualty=casualty)

        if casualty == "dead":
            rival["status"] = "dead"
            rival["recover_until_tick"] = -1
            rival["materialized_eid"] = None
            self.sim.emit(Event(
                "rival_operator_removed",
                eid=self.player_eid,
                rival_id=int(rival.get("id", 0) or 0),
                rival_name=str(rival.get("name", "rival")).strip() or "rival",
                source_eid=None,
                by_player=False,
                reason=reason,
            ))
            return casualty

        rival["status"] = "wounded"
        rival["recover_until_tick"] = tick + int(self.RECOVERY_TICKS) + 60
        rival["target_chunk"] = self._normalize_chunk(rival.get("home_chunk"), fallback=rival.get("current_chunk"))
        self.sim.emit(Event(
            "rival_operator_wounded",
            eid=self.player_eid,
            rival_id=int(rival.get("id", 0) or 0),
            rival_name=str(rival.get("name", "rival")).strip() or "rival",
            reason=reason,
            recover_until_tick=int(rival.get("recover_until_tick", tick)),
        ))
        return casualty

    def _rival_followup_reward(self, rival, resolved, *, resolution, casualty=""):
        reward = {
            "credits": 10,
            "intel": 1,
        }
        risk = str((resolved or {}).get("risk", "low")).strip().lower() or "low"
        hustle = str(rival.get("hustle", "cash")).strip().lower() or "cash"
        if resolution == "burned":
            reward["credits"] += 8
        if casualty == "dead":
            reward["credits"] += 16
            reward["intel"] += 1
        if risk == "hazardous":
            reward["credits"] += 8
            reward["intel"] += 1
        elif risk == "exposed":
            reward["credits"] += 4
        if hustle == "network":
            reward["standing"] = reward.get("standing", 0) + 1
        elif hustle == "intel":
            reward["intel"] += 1
        else:
            reward["credits"] += 6
        return {key: int(value) for key, value in reward.items() if int(value) > 0}

    def _spawn_rival_followup(self, rival, resolved, *, resolution, casualty=""):
        if not isinstance(resolved, dict):
            return None
        if self._is_rival_followup_entry(resolved):
            return None
        chunk = self._normalize_chunk(resolved.get("chunk"), fallback=rival.get("current_chunk"))
        rival_name = str(rival.get("name", "rival")).strip() or "rival"
        title = self._collapse_repeated_rival_followup_labels(resolved.get("title", "Opportunity")) or "Opportunity"
        risk = str(resolved.get("risk", "low")).strip().lower() or "low"

        if casualty == "dead":
            followup_title = f"Last Trace: {rival_name}"
            summary = (
                f"{rival_name} may have died working {title}. Loose gear, chatter, or "
                "panicked contacts could still be in play if you move fast."
            )
        elif resolution == "burned":
            followup_title = f"Burned Trail: {title}"
            summary = (
                f"{rival_name} scorched {title}. The scene may still pay in salvage, "
                "fresh intel, or a quick opening if you get there first."
            )
        else:
            followup_title = f"Rival Aftermath: {title}"
            summary = (
                f"{rival_name} got to {title} first. Their wake may still hold loose intel, "
                "rattled contacts, or quick margin if you move before it cools."
            )

        if casualty == "dead":
            risk_label = "exposed" if risk == "low" else risk
        elif resolution == "burned":
            risk_label = "hazardous" if risk == "hazardous" else "exposed"
        else:
            risk_label = risk

        hustle = str(rival.get("hustle", "cash")).strip().lower() or "cash"
        playstyles = ("economic", "stealth")
        if hustle == "network":
            playstyles = ("social", "stealth")
        elif hustle == "intel":
            playstyles = ("stealth", "social")

        added = append_external_opportunity(
            self.sim,
            {
                "key": f"rival_followup:{int(resolved.get('id', 0) or 0)}",
                "title": followup_title,
                "summary": summary,
                "kind": "rival_followup",
                "source": "rival_operator",
                "chunk": chunk,
                "playstyles": playstyles,
                "reward": self._rival_followup_reward(rival, resolved, resolution=resolution, casualty=casualty),
                "risk": risk_label,
                "pressure": 3 if risk_label == "hazardous" else 2 if risk_label == "exposed" else 1,
                "requirements": {
                    "visit_chunk": chunk,
                    "rival_followup": True,
                    "followup_from_opportunity_id": int(resolved.get("id", 0) or 0),
                },
                "seed_tick": int(self.sim.tick),
            },
            observer_eid=self.player_eid,
            awareness_state="heard",
            confidence=0.66 if casualty else 0.6,
            source="rival_operator",
        )
        if not isinstance(added, dict):
            return None
        self.sim.emit(Event(
            "rival_followup_seeded",
            eid=self.player_eid,
            rival_id=int(rival.get("id", 0) or 0),
            rival_name=rival_name,
            opportunity_id=int(resolved.get("id", 0) or 0),
            followup_id=int(added.get("id", 0) or 0),
            followup_title=str(added.get("title", "Opportunity")).strip() or "Opportunity",
            chunk=chunk,
            resolution=resolution,
            casualty=casualty,
        ))
        return added

    def _resolution_confidence(self, rival, *, resolution, player_distance, known_to_player):
        confidence = 0.48 + (float(rival.get("honesty", 0.5)) * 0.22)
        confidence += min(0.14, max(0, 4 - int(player_distance)) * 0.03)
        if known_to_player:
            confidence += 0.08
        if resolution == "burned":
            confidence -= 0.05
        return max(0.38, min(0.92, confidence))

    def _emit_rival_activity(self, rival, *, entry=None, summary="", confidence=0.5, truthful=True):
        chunk = self._normalize_chunk((entry or {}).get("chunk"), fallback=rival.get("current_chunk"))
        player_distance = self._chunk_distance(self._player_chunk_coord(), chunk)
        known_to_player = False
        if isinstance(entry, dict):
            intel = opportunity_intel_for_observer(self.sim, self.player_eid, int(entry.get("id", 0) or 0))
            known_to_player = bool(intel)
        self.sim.emit(Event(
            "rival_operator_activity",
            eid=self.player_eid,
            rival_id=int(rival.get("id", 0) or 0),
            rival_name=str(rival.get("name", "operator")).strip() or "operator",
            rival_mask=str(rival.get("public_mask", "quiet")).strip().lower() or "quiet",
            rival_reputation=str(rival.get("reputation", "steady")).strip().lower() or "steady",
            hustle=str(rival.get("hustle", "cash")).strip().lower() or "cash",
            chunk=chunk,
            player_distance=player_distance,
            known_to_player=bool(known_to_player),
            confidence=max(0.0, min(1.0, float(confidence))),
            summary=str(summary).strip(),
            truthful=bool(truthful),
        ))

    def _maybe_emit_rival_rumor(self, rival):
        if int(self.sim.tick) - int(rival.get("last_rumor_tick", -10_000)) < self.RUMOR_INTERVAL:
            return
        if self._materialized_eid(rival) and self._player_can_notice_rival(rival):
            return
        target = self._target_entry(rival)
        if not isinstance(target, dict):
            return

        truthful_threshold = 0.24 + (float(rival.get("honesty", 0.5)) * 0.62)
        chooser = self._rival_rng(rival, "rumor")
        truthful = chooser.random() <= truthful_threshold
        reported = target
        if not truthful:
            alternatives = [
                entry
                for entry in self._active_opportunities()
                if int(entry.get("id", 0) or 0) != int(target.get("id", 0) or 0)
            ]
            if alternatives:
                alternatives.sort(key=lambda entry: int(entry.get("id", 0) or 0))
                reported = chooser.choice(alternatives)

        report_chunk = self._normalize_chunk(reported.get("chunk"), fallback=rival.get("current_chunk"))
        player_chunk = self._player_chunk_coord()
        distance_text = opportunity_distance_text(
            self._chunk_distance(player_chunk, report_chunk),
            self._step_direction(player_chunk, report_chunk),
        )
        summary = (
            f"{rival.get('name', 'Someone')} is said to be working "
            f"{str(reported.get('title', 'a lead')).strip() or 'a lead'} {distance_text}"
        )
        confidence = 0.42 + (float(rival.get("honesty", 0.5)) * 0.18) + (float(rival.get("charm", 0.5)) * 0.08)
        if not truthful:
            confidence -= 0.12
        self._emit_rival_activity(
            rival,
            entry=reported,
            summary=summary,
            confidence=max(0.32, min(0.82, confidence)),
            truthful=truthful,
        )
        rival["last_rumor_tick"] = int(self.sim.tick)

    def _step_direction(self, origin_chunk, target_chunk):
        origin = self._normalize_chunk(origin_chunk)
        target = self._normalize_chunk(target_chunk, fallback=origin)
        dx = int(target[0]) - int(origin[0])
        dy = int(target[1]) - int(origin[1])
        parts = []
        if dy < 0:
            parts.append("N")
        elif dy > 0:
            parts.append("S")
        if dx > 0:
            parts.append("E")
        elif dx < 0:
            parts.append("W")
        return "".join(parts) if parts else "HERE"

    def _resolve_target_for_rival(self, rival):
        entry = self._target_entry(rival)
        if not isinstance(entry, dict):
            rival["target_opportunity_id"] = 0
            return

        target_chunk = self._normalize_chunk(entry.get("chunk"), fallback=rival.get("current_chunk"))
        player_chunk = self._player_chunk_coord()
        player_distance = self._chunk_distance(player_chunk, target_chunk)
        if player_distance <= 0 and not self._materialized_eid(rival):
            self._emit_rival_activity(
                rival,
                entry=entry,
                summary=(
                    f"{rival.get('name', 'Someone')} is rumored to be circling "
                    f"{str(entry.get('title', 'a local lead')).strip() or 'a local lead'} nearby"
                ),
                confidence=0.58,
                truthful=True,
            )
            rival["last_action_tick"] = int(self.sim.tick)
            return

        resolution = self._resolution_for_rival(rival, entry)
        if resolution == "scouted":
            rival["intel"] = int(rival.get("intel", 0) or 0) + 1
            self._emit_rival_activity(
                rival,
                entry=entry,
                summary=(
                    f"{rival.get('name', 'Someone')} looks to be casing "
                    f"{str(entry.get('title', 'a lead')).strip() or 'a lead'}"
                ),
                confidence=0.54 + (float(rival.get("honesty", 0.5)) * 0.1),
                truthful=True,
            )
            rival["last_action_tick"] = int(self.sim.tick)
            return

        known_before = bool(opportunity_intel_for_observer(self.sim, self.player_eid, int(entry.get("id", 0) or 0)))
        reward = dict(entry.get("reward", {}))
        if resolution == "claimed":
            self._apply_rival_reward(rival, reward)
            self._mirror_reward_to_materialized_inventory(rival, reward)
            rival["heat"] = int(_clamp(int(rival.get("heat", 0) or 0) + max(2, int(reward.get("standing", 0) or 0)), 0, 100))
            reason = f"claimed by {rival.get('name', 'a rival')} ({rival.get('hustle', 'cash')})"
            status = "completed"
        else:
            rival["heat"] = int(_clamp(int(rival.get("heat", 0) or 0) + 5, 0, 100))
            reason = f"burned by {rival.get('name', 'a rival')}"
            status = "spoiled"

        resolved = resolve_external_opportunity(
            self.sim,
            int(entry.get("id", 0) or 0),
            status=status,
            completion_reason=reason,
            reward_applied={},
            extra={
                "resolved_by": "rival_operator",
                "resolved_by_id": int(rival.get("id", 0) or 0),
                "resolved_by_name": str(rival.get("name", "rival")).strip() or "rival",
                "resolved_by_hustle": str(rival.get("hustle", "cash")).strip().lower() or "cash",
                "resolved_by_mask": str(rival.get("public_mask", "quiet")).strip().lower() or "quiet",
                "resolved_by_reputation": str(rival.get("reputation", "steady")).strip().lower() or "steady",
            },
        )
        if resolved is None:
            rival["target_opportunity_id"] = 0
            return

        rival["resolved_count"] = int(rival.get("resolved_count", 0) or 0) + 1
        rival["last_action_tick"] = int(self.sim.tick)
        rival["target_opportunity_id"] = 0
        casualty = self._apply_offscreen_casualty(rival, entry, resolution=resolution)
        if not casualty:
            rival["status"] = "resetting"
        followup = self._spawn_rival_followup(rival, resolved, resolution=resolution, casualty=casualty)

        confidence = self._resolution_confidence(
            rival,
            resolution=resolution,
            player_distance=player_distance,
            known_to_player=known_before,
        )
        self.sim.emit(Event(
            "rival_opportunity_resolved",
            eid=self.player_eid,
            rival_id=int(rival.get("id", 0) or 0),
            rival_name=str(rival.get("name", "rival")).strip() or "rival",
            rival_mask=str(rival.get("public_mask", "quiet")).strip().lower() or "quiet",
            rival_reputation=str(rival.get("reputation", "steady")).strip().lower() or "steady",
            hustle=str(rival.get("hustle", "cash")).strip().lower() or "cash",
            opportunity_id=int(resolved.get("id", 0) or 0),
            title=str(resolved.get("title", "Opportunity")).strip() or "Opportunity",
            summary=str(resolved.get("summary", "")).strip(),
            chunk=self._normalize_chunk(resolved.get("chunk"), fallback=target_chunk),
            resolution=resolution,
            reward_text=format_reward_text(reward),
            player_distance=player_distance,
            known_to_player=bool(known_before),
            confidence=confidence,
            casualty=str(casualty or "").strip().lower(),
            followup_id=int((followup or {}).get("id", 0) or 0),
            followup_title=str((followup or {}).get("title", "")).strip(),
        ))

    def on_npc_downed(self, event):
        rival = self._rival_for_materialized_eid(event.data.get("target_eid"))
        if rival is None:
            return
        if str(rival.get("status", "")).strip().lower() in {"dead", "retired"}:
            return
        self._capture_materialized_state(rival)
        rival["status"] = "wounded"
        rival["recover_until_tick"] = int(self.sim.tick) + int(self.RECOVERY_TICKS)
        rival["target_opportunity_id"] = 0
        rival["target_chunk"] = self._normalize_chunk(rival.get("home_chunk"), fallback=rival.get("current_chunk"))
        rival["last_action_tick"] = int(self.sim.tick)
        rival["last_decision_tick"] = int(self.sim.tick)

    def on_npc_killed(self, event):
        rival = self._rival_for_materialized_eid(event.data.get("target_eid"))
        if rival is None:
            return
        rival["status"] = "dead"
        rival["recover_until_tick"] = -1
        rival["target_opportunity_id"] = 0
        rival["materialized_eid"] = None
        self.sim.emit(Event(
            "rival_operator_removed",
            eid=self.player_eid,
            rival_id=int(rival.get("id", 0) or 0),
            rival_name=str(rival.get("name", "rival")).strip() or "rival",
            source_eid=event.data.get("source_eid"),
            by_player=event.data.get("source_eid") == self.player_eid,
            reason=str(event.data.get("reason", "killed")).strip() or "killed",
        ))

    def update(self):
        self._normalize_rival_followup_opportunities()
        rivals = self._seed_rivals()
        if not rivals:
            return

        tick = int(getattr(self.sim, "tick", 0))
        for rival in rivals:
            self._normalize_rival_runtime_state(rival)
            self._recover_rival_if_ready(rival)
            if not self._rival_is_available(rival):
                self._sync_materialization(rival)
                continue

            if tick - int(rival.get("last_decision_tick", -10_000)) >= self.DECISION_INTERVAL:
                self._refresh_target_for_rival(rival)
            elif int(rival.get("target_opportunity_id", 0) or 0) > 0 and self._target_entry(rival) is None:
                self._refresh_target_for_rival(rival)
            if tick - int(rival.get("last_move_tick", -10_000)) >= self.TRAVEL_INTERVAL:
                self._move_rival(rival)
            self._sync_materialization(rival)
            self._maybe_emit_rival_rumor(rival)

            target = self._target_entry(rival)
            if not isinstance(target, dict):
                continue
            target_chunk = self._normalize_chunk(target.get("chunk"), fallback=rival.get("current_chunk"))
            current_chunk = self._normalize_chunk(rival.get("current_chunk"), fallback=target_chunk)
            if current_chunk != target_chunk:
                continue
            action_interval = self.LOCAL_ACTION_INTERVAL if self._materialized_eid(rival) else self.ACTION_INTERVAL
            if tick - int(rival.get("last_action_tick", -10_000)) < int(action_interval):
                continue
            if current_chunk == self._player_chunk_coord() and self._materialized_eid(rival):
                if not self._local_resolution_ready(rival, target):
                    continue
            self._resolve_target_for_rival(rival)

class FinalOperationSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.last_unlock_tick = -10_000
        self.sim.events.subscribe("player_downed", self.on_player_downed)
        self.sim.events.subscribe("player_killed", self.on_player_killed)
        self.sim.events.subscribe("item_picked_up", self.on_item_picked_up)

    def _conclude_run(self, *, outcome, reason, objective_title, summary_lines):
        archive_failed_run_bones(
            self.sim,
            self.player_eid,
            outcome=outcome,
            reason=reason,
            objective_title=objective_title,
            summary_lines=summary_lines,
        )
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        if not isinstance(traits.get("run_end"), dict):
            traits["run_end"] = {}
        run_end = traits["run_end"]
        run_end["active"] = True
        run_end["outcome"] = str(outcome or "").strip().lower() or "unknown"
        run_end["reason"] = str(reason or "").strip().lower()
        run_end["objective_title"] = str(objective_title or "Run Objective").strip() or "Run Objective"
        run_end["summary_lines"] = [str(line).strip() for line in (summary_lines or ()) if str(line).strip()]
        run_end["tick"] = int(getattr(self.sim, "tick", 0))
        run_end["show_post_curses"] = True

        self.sim.emit(Event(
            "run_concluded",
            eid=self.player_eid,
            outcome=run_end["outcome"],
            reason=run_end["reason"],
            objective_title=run_end["objective_title"],
            summary_lines=tuple(run_end["summary_lines"]),
            tick=run_end["tick"],
        ))
        self.sim.running = False

    def _final_op_downed_fails_run(self):
        traits = getattr(self.sim, "world_traits", {})
        if not isinstance(traits, dict):
            return True
        rules = traits.get("rules", {})
        if not isinstance(rules, dict):
            return True
        value = rules.get("final_op_downed_fails_run", True)
        return bool(value)

    def on_player_downed(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        if not self._final_op_downed_fails_run():
            return
        failed = try_fail_final_operation(
            self.sim,
            self.player_eid,
            reason="downed_during_final_operation",
        )
        if not failed:
            return
        self.sim.emit(Event(
            "final_operation_failed",
            eid=self.player_eid,
            objective_id=str(failed.get("objective_id", "")),
            objective_title=str(failed.get("objective_title", "")),
            target_chunk=tuple(failed.get("target_chunk", (0, 0))),
            target_label=str(failed.get("target_label", "")),
            fail_tick=int(failed.get("fail_tick", 0)),
            fail_reason=str(failed.get("fail_reason", "")),
            summary_lines=tuple(failed.get("summary_lines", ())),
        ))
        self._conclude_run(
            outcome="failed",
            reason="final_operation_failed",
            objective_title=str(failed.get("objective_title", "")),
            summary_lines=failed.get("summary_lines", ()),
        )

    def _generic_death_objective_title(self):
        traits = getattr(self.sim, "world_traits", {})
        if isinstance(traits, dict):
            final_state = traits.get("final_operation", {})
            if isinstance(final_state, dict):
                title = str(final_state.get("objective_title", "")).strip()
                if title and not bool(final_state.get("completed", False)):
                    return title
        return "Open Run"

    def _generic_death_summary_lines(self, event):
        lines = []
        source_name = str(event.data.get("source_name", "") or "").strip()
        if source_name:
            lines.append(f"Killed by {source_name}.")
        else:
            lines.append("You were killed.")

        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if pos:
            prop = _property_covering(self.sim, pos.x, pos.y, pos.z)
            prop_name = str((prop or {}).get("name", "")).strip()
            if prop_name:
                lines.append(f"Last seen near {prop_name}.")
            else:
                cx, cy = self.sim.chunk_coords(int(pos.x), int(pos.y))
                lines.append(f"Last seen in chunk {int(cx)},{int(cy)}.")
        return tuple(lines[:5])

    def on_player_killed(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return

        failed = try_fail_final_operation(
            self.sim,
            self.player_eid,
            reason="killed_during_final_operation",
        )
        if failed:
            self.sim.emit(Event(
                "final_operation_failed",
                eid=self.player_eid,
                objective_id=str(failed.get("objective_id", "")),
                objective_title=str(failed.get("objective_title", "")),
                target_chunk=tuple(failed.get("target_chunk", (0, 0))),
                target_label=str(failed.get("target_label", "")),
                fail_tick=int(failed.get("fail_tick", 0)),
                fail_reason=str(failed.get("fail_reason", "")),
                summary_lines=tuple(failed.get("summary_lines", ())),
            ))
            self._conclude_run(
                outcome="failed",
                reason="final_operation_failed",
                objective_title=str(failed.get("objective_title", "")),
                summary_lines=failed.get("summary_lines", ()),
            )
            return

        self._conclude_run(
            outcome="failed",
            reason="player_killed",
            objective_title=self._generic_death_objective_title(),
            summary_lines=self._generic_death_summary_lines(event),
        )

    def _remember_target_property(self, property_id):
        property_id = str(property_id or "").strip()
        if not property_id:
            return
        knowledge = self.sim.ecs.get(PropertyKnowledge).get(self.player_eid)
        if knowledge is None:
            return
        prop = self.sim.properties.get(property_id)
        if not isinstance(prop, dict):
            return
        knowledge.remember(
            property_id,
            owner_eid=prop.get("owner_eid"),
            owner_tag=prop.get("owner_tag"),
            confidence=1.0,
            tick=int(getattr(self.sim, "tick", 0)),
            anchored=True,
            anchor_kind="final_operation",
        )
        knowledge.unhide(property_id)

    def _finish_completed(self, completed):
        self.sim.emit(Event(
            "final_operation_completed",
            eid=self.player_eid,
            objective_id=str(completed.get("objective_id", "")),
            objective_title=str(completed.get("objective_title", "")),
            target_chunk=tuple(completed.get("target_chunk", (0, 0))),
            target_label=str(completed.get("target_label", "")),
            target_property_id=str(completed.get("target_property_id", "")),
            target_property_name=str(completed.get("target_property_name", "")),
            target_item_name=str(completed.get("target_item_name", "")),
            complete_tick=int(completed.get("complete_tick", 0)),
            summary_lines=tuple(completed.get("summary_lines", ())),
        ))
        self._conclude_run(
            outcome="success",
            reason="final_operation_success",
            objective_title=str(completed.get("objective_title", "")),
            summary_lines=completed.get("summary_lines", ()),
        )

    def on_item_picked_up(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        recovered = mark_final_operation_target_recovered(
            self.sim,
            self.player_eid,
            instance_id=event.data.get("instance_id"),
        )
        if not recovered:
            return

        self.sim.emit(Event(
            "final_operation_target_recovered",
            eid=self.player_eid,
            objective_id=str(recovered.get("objective_id", "")),
            objective_title=str(recovered.get("objective_title", "")),
            target_chunk=tuple(recovered.get("target_chunk", (0, 0))),
            target_label=str(recovered.get("target_label", "")),
            target_property_id=str(recovered.get("target_property_id", "")),
            target_property_name=str(recovered.get("target_property_name", "")),
            target_item_id=str(recovered.get("target_item_id", "")),
            target_item_name=str(recovered.get("target_item_name", "")),
            target_recovered_tick=int(recovered.get("target_recovered_tick", 0)),
        ))

        completed = try_complete_final_operation(self.sim, self.player_eid)
        if completed:
            self._finish_completed(completed)

    def update(self):
        objective_eval = evaluate_run_objective(self.sim, self.player_eid)
        unlocked = ensure_final_operation_unlocked(
            self.sim,
            self.player_eid,
            objective_eval=objective_eval,
        )
        if unlocked:
            self.last_unlock_tick = int(getattr(self.sim, "tick", 0))
            self.sim.emit(Event(
                "final_operation_unlocked",
                eid=self.player_eid,
                objective_id=str(unlocked.get("objective_id", "")),
                objective_title=str(unlocked.get("objective_title", "")),
                target_chunk=tuple(unlocked.get("target_chunk", (0, 0))),
                target_label=str(unlocked.get("target_label", "")),
            ))
            return

        if int(getattr(self.sim, "tick", 0)) <= self.last_unlock_tick:
            return
        target_identified = sync_final_operation_runtime(self.sim, self.player_eid)
        if target_identified:
            self._remember_target_property(target_identified.get("target_property_id"))
            self.sim.emit(Event(
                "final_operation_target_identified",
                eid=self.player_eid,
                objective_id=str(target_identified.get("objective_id", "")),
                objective_title=str(target_identified.get("objective_title", "")),
                target_chunk=tuple(target_identified.get("target_chunk", (0, 0))),
                target_label=str(target_identified.get("target_label", "")),
                target_property_id=str(target_identified.get("target_property_id", "")),
                target_property_name=str(target_identified.get("target_property_name", "")),
                target_item_id=str(target_identified.get("target_item_id", "")),
                target_item_name=str(target_identified.get("target_item_name", "")),
                target_reason=str(target_identified.get("target_reason", "")),
                target_quality_label=str(target_identified.get("target_quality_label", "")),
                target_value_bonus=int(target_identified.get("target_value_bonus", 0) or 0),
                target_intel_score=int(target_identified.get("target_intel_score", 0) or 0),
                target_entry_label=str(target_identified.get("target_entry_label", "")),
                target_entry_detail=str(target_identified.get("target_entry_detail", "")),
            ))
        completed = try_complete_final_operation(self.sim, self.player_eid)
        if not completed:
            return
        self._finish_completed(completed)
