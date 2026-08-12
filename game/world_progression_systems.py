"""Extracted systems from ``game.systems``: WorldStreamingSystem, OpportunitySystem, RivalOperatorSystem, FinalOperationSystem."""

import random
import re
from engine.buildings import building_exterior_profile, layout_chunk_building, world_building_id
from engine.events import Event
from engine.fixtures import generate_chunk_fixture_records
from engine.underground import (
    ACCESS_TUNNEL_NETWORK_KIND,
    UNDERGROUND_ACCESS_SERVICE,
    chunk_underground_network_plan,
    chunk_underground_site_plans,
)
from engine.persistence import restore_chunk_state
from engine.sites import layout_chunk_site, site_gameplay_profile
from engine.systems import System
from engine.tilemap import Tile
from engine.visibility import (
    has_line_of_sight as _shared_has_line_of_sight,
    observer_can_see_position as _shared_observer_can_see_position,
    update_player_visibility as _update_player_visibility,
)
from engine.world import normalize_building_levels
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
from game.run_echoes import maybe_seed_run_echo_for_chunk
from game.final_operation import (
    active_final_operation_target_property_id,
    ensure_final_operation_unlocked,
    evaluate_final_operation,
    mark_final_operation_target_recovered,
    sync_final_operation_runtime,
    try_complete_final_operation,
    try_fail_final_operation,
)
from game.flora_runtime import ensure_chunk_flora
from game.contamination_runtime import (
    BLACKWASH_PROFILE,
    ensure_underground_remediation_flora,
    materialize_contamination_release,
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
from game.large_span_places import register_large_span_child_properties
from game.opportunities import (
    SPECIALTY_OPPORTUNITY_THEMES,
    _opportunity_requirements,
    advance_opportunity_lifecycle,
    append_external_opportunity,
    evaluate_opportunity_board,
    evaluate_opportunity_facts,
    format_reward_text,
    ensure_initial_opportunities,
    opportunity_intel_for_observer,
    opportunity_distance_text,
    opportunity_known_count,
    opportunity_source_label,
    record_opportunity_kill,
    refresh_due_dynamic_opportunities,
    reveal_opportunity_to_observer,
    resolve_external_opportunity,
    seed_run_opportunities,
    stage_active_opportunities,
)
from game.organizations import (
    ensure_property_organization,
    link_property_organization,
    occupation_targets_property,
    organization_name,
    property_org_members,
    property_organization_eid,
    seed_chunk_organizations,
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
    spawn_chunk_special_population,
    work_shift_active,
)
from game.property_access import (
    COMMON_AREA_ROOM_KINDS,
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
    site_services_with_holdem_mode,
    world_hour as _world_hour,
)
from game.quick_travel_ramps import generate_quick_travel_ramp_records
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
from game.service_runtime import (
    _building_site_service_seed_token,
    _clamp,
    _int_or_default,
    _site_service_seed_token,
)
from game.system_support.environment_hazard_runtime import (
    environment_hazard_asset_metadata as _environment_hazard_asset_metadata,
    normalize_environment_hazard_specs as _normalize_environment_hazard_specs,
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


def _generate_human_personal_name(*args, **kwargs):
    from game import systems as facade

    return facade.generate_human_personal_name(*args, **kwargs)


_UNDERGROUND_CACHE_CONTENT_ROWS_BY_PROFILE = {
    "maintenance": (
        ("transit_daypass", 10, 1, 1),
        ("city_pass_token", 7, 1, 2),
        ("battery_pack", 9, 1, 1),
        ("scrap_circuit", 9, 1, 2),
        ("energy_bar", 8, 1, 2),
        ("bottled_water", 8, 1, 2),
        ("hydration_salts", 6, 1, 1),
        ("signal_jammer", 4, 1, 1),
        ("lockpick_kit", 4, 1, 1),
        ("med_gel", 6, 1, 1),
        ("micro_medkit", 3, 1, 1),
        ("credstick_chip", 8, 1, 1),
        ("pocket_notebook", 2, 1, 1),
        ("spark_brew", 2, 1, 1),
    ),
    "survival": (
        ("bottled_water", 12, 1, 2),
        ("energy_bar", 10, 1, 2),
        ("street_ration", 8, 1, 2),
        ("hydration_salts", 7, 1, 1),
        ("water_purifier_tabs", 6, 1, 1),
        ("emergency_blanket", 5, 1, 1),
        ("bandage_roll", 6, 1, 1),
        ("med_gel", 4, 1, 1),
        ("cheap_whiskey", 2, 1, 1),
        ("credstick_chip", 4, 1, 1),
    ),
    "drain": (
        ("glass_bottle", 8, 1, 2),
        ("brick", 6, 1, 2),
        ("scrap_circuit", 8, 1, 2),
        ("battery_pack", 5, 1, 1),
        ("bottled_water", 5, 1, 1),
        ("energy_bar", 5, 1, 1),
        ("lockpick_kit", 3, 1, 1),
        ("pocket_multitool", 3, 1, 1),
        ("credstick_chip", 5, 1, 1),
        ("spark_brew", 3, 1, 1),
    ),
    "contraband_light": (
        ("credstick_chip", 9, 1, 1),
        ("lockpick_kit", 6, 1, 1),
        ("signal_jammer", 5, 1, 1),
        ("black_market_stim", 5, 1, 1),
        ("cocaine_bindle", 3, 1, 1),
        ("lsd_blotter", 2, 1, 1),
        ("shiver_patch", 1, 1, 1),
        ("shiv_knife", 4, 1, 1),
        ("holdout_pistol", 1, 1, 1),
    ),
}
_UNDERGROUND_CACHE_NOTES = {
    "maintenance": "A maintenance stash tucked behind conduit panels.",
    "survival": "A dry pack of useful supplies tucked away from street traffic.",
    "drain": "A damp cache balanced above the runoff.",
    "contraband_light": "A hidden stash wrapped for a quick underground handoff.",
}

_UNDERGROUND_CACHE_ARCHETYPES = {
    "maintenance": "underpass_cache",
    "survival": "underground_survival_cache",
    "drain": "storm_drain_cache",
    "contraband_light": "underground_contraband_cache",
}

class WorldStreamingSystem(System):

    def __init__(self, sim, focus_eid):
        super().__init__(sim)
        self.focus_eid = focus_eid
        if not hasattr(self.sim, "chunk_property_records"):
            self.sim.chunk_property_records = {}
        if not hasattr(self.sim, "chunk_saved_states"):
            self.sim.chunk_saved_states = {}

    def _ensure_property_anchor(self, x, y, z=0):
        if hasattr(self.sim, "door_state_at") and hasattr(self.sim, "apply_door_state"):
            state = self.sim.door_state_at(x, y, z)
            if isinstance(state, dict):
                self.sim.apply_door_state(x, y, z)
                return
        tile = self.sim.tilemap.tile_at(x, y, z)
        if tile and tile.walkable:
            return
        self.sim.tilemap.set_tile(x, y, Tile(walkable=True, transparent=True, glyph="."), z=z)

    def _register_underground_access_asset(
        self,
        records,
        *,
        key,
        name,
        x,
        y,
        z,
        destination,
        linked_property_id=None,
        fixture_type="underpass_stairwell",
        glyph="u",
        public=True,
    ):
        self._ensure_property_anchor(x, y, z)
        metadata = {
            "archetype": str(fixture_type).strip().lower() or "underpass_stairwell",
            "fixture_type": str(fixture_type).strip().lower() or "underpass_stairwell",
            "display_glyph": str(glyph)[:1] or "u",
            "display_color": "property_service",
            "hard_traversal": True,
            "cover_kind": "low",
            "cover_value": 0.12,
            "public": bool(public),
            "site_services": [UNDERGROUND_ACCESS_SERVICE],
            "site_service_destinations": {
                UNDERGROUND_ACCESS_SERVICE: dict(destination or {}),
            },
            "chunk": key,
        }
        if linked_property_id:
            metadata["linked_property_id"] = str(linked_property_id)
        property_id = self.sim.register_property(
            name=str(name).strip() or "Stairwell",
            kind="asset",
            x=int(x),
            y=int(y),
            z=int(z),
            owner_eid=None,
            owner_tag="public" if bool(public) else "city",
            metadata=metadata,
        )
        records.append({
            "id": property_id,
            "kind": "asset",
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "archetype": metadata.get("archetype"),
            "building_id": None,
        })
        return property_id

    def _seed_underground_cache_contents(self, property_id, *, seed_token="", cache_profile="maintenance"):
        cache_items = _property_runtime_container_entries(
            self.sim,
            property_id,
            container_kind="cache",
        )
        if cache_items:
            return len(cache_items)

        cache_profile = str(cache_profile or "maintenance").strip().lower() or "maintenance"
        rows_source = _UNDERGROUND_CACHE_CONTENT_ROWS_BY_PROFILE.get(cache_profile)
        if not rows_source:
            cache_profile = "maintenance"
            rows_source = _UNDERGROUND_CACHE_CONTENT_ROWS_BY_PROFILE["maintenance"]

        rng = random.Random(
            f"{self.sim.seed}:underground_cache:{cache_profile}:{str(seed_token or '').strip() or property_id}:{property_id}"
        )
        rows = [
            row for row in rows_source
            if ITEM_CATALOG.get(str(row[0]).strip().lower())
        ]
        if not rows:
            return 0

        target_count = 2 + (1 if rng.random() < 0.7 else 0) + (1 if rng.random() < 0.24 else 0)
        while rows and len(cache_items) < target_count:
            pick_index = rng.choices(
                range(len(rows)),
                weights=[float(row[1]) for row in rows],
                k=1,
            )[0]
            item_id, _weight, quantity_lo, quantity_hi = rows.pop(int(pick_index))
            quantity = int(rng.randint(int(quantity_lo), int(max(quantity_lo, quantity_hi))))
            metadata = None
            if is_credstick_item(item_id):
                metadata = prepare_item_stack_metadata(
                    item_id,
                    metadata={"stored_credits": int(rng.randint(18, 76))},
                    quantity=quantity,
                )
            cache_items.append({
                "instance_id": self.sim.new_item_instance_id(),
                "item_id": str(item_id).strip().lower(),
                "quantity": int(max(1, quantity)),
                "name": item_display_name(item_id, item_catalog=ITEM_CATALOG),
                "metadata": metadata,
                "owner_eid": None,
                "owner_tag": "city",
            })
        return len(cache_items)

    def _seed_underpass_cache_contents(self, property_id, *, seed_token=""):
        return self._seed_underground_cache_contents(
            property_id,
            seed_token=seed_token,
            cache_profile="maintenance",
        )

    def _register_underground_cache_asset(
        self,
        records,
        *,
        key,
        name,
        x,
        y,
        z,
        linked_property_id=None,
        seed_token="",
        cache_profile="maintenance",
    ):
        self._ensure_property_anchor(x, y, z)
        cache_profile = str(cache_profile or "maintenance").strip().lower() or "maintenance"
        if cache_profile not in _UNDERGROUND_CACHE_CONTENT_ROWS_BY_PROFILE:
            cache_profile = "maintenance"
        metadata = {
            "archetype": _UNDERGROUND_CACHE_ARCHETYPES.get(cache_profile, "underpass_cache"),
            "fixture_type": "maintenance_cache_box",
            "display_glyph": "c",
            "display_color": "property_fixture",
            "cover_kind": "low",
            "cover_value": 0.18,
            "interaction_role": "cache_target",
            "fixture_kind": "cache",
            "container_kind": "cache",
            "container_label": "Cache",
            "container_note_text": _UNDERGROUND_CACHE_NOTES.get(cache_profile, _UNDERGROUND_CACHE_NOTES["maintenance"]),
            "cache_profile": cache_profile,
            "public": True,
            "chunk": key,
        }
        if linked_property_id:
            metadata["linked_property_id"] = str(linked_property_id)
        property_id = self.sim.register_property(
            name=str(name).strip() or "Maintenance Locker",
            kind="asset",
            x=int(x),
            y=int(y),
            z=int(z),
            owner_eid=None,
            owner_tag="city",
            metadata=metadata,
        )
        self._seed_underground_cache_contents(
            property_id,
            seed_token=seed_token,
            cache_profile=cache_profile,
        )
        records.append({
            "id": property_id,
            "kind": "asset",
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "archetype": metadata.get("archetype"),
            "building_id": None,
        })
        return property_id

    def _register_underground_service_asset(
        self,
        records,
        *,
        key,
        name,
        x,
        y,
        z,
        site_services=(),
        linked_property_id=None,
        fixture_type="service_terminal",
        glyph="i",
        lead_mode=None,
        display_description=None,
        route_destinations=(),
    ):
        self._ensure_property_anchor(x, y, z)
        normalized_fixture_type = str(fixture_type).strip().lower() or "service_terminal"
        metadata = {
            "archetype": normalized_fixture_type,
            "fixture_type": normalized_fixture_type,
            "interaction_role": "route_marker" if normalized_fixture_type == "underground_route_marker" else "service_terminal",
            "site_services": [
                str(service).strip().lower()
                for service in tuple(site_services or ())
                if str(service).strip()
            ],
            "display_glyph": str(glyph)[:1] or "i",
            "display_color": "property_service",
            "cover_kind": "low",
            "cover_value": 0.28,
            "public": True,
            "chunk": key,
        }
        display_description = str(display_description or "").strip()
        if display_description:
            metadata["display_description"] = display_description
        route_destinations = tuple(
            str(value or "").strip()
            for value in tuple(route_destinations or ())
            if str(value or "").strip()
        )
        if route_destinations:
            metadata["route_destinations"] = list(route_destinations)
        if linked_property_id:
            metadata["linked_property_id"] = str(linked_property_id)
        lead_mode = str(lead_mode or "").strip().lower()
        if lead_mode:
            metadata["lead_mode"] = lead_mode
        property_id = self.sim.register_property(
            name=str(name).strip() or "Signal Relay",
            kind="asset",
            x=int(x),
            y=int(y),
            z=int(z),
            owner_eid=None,
            owner_tag="public",
            metadata=metadata,
        )
        records.append({
            "id": property_id,
            "kind": "asset",
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "archetype": metadata.get("archetype"),
            "building_id": None,
        })
        return property_id

    def _register_environmental_hazard_asset(
        self,
        records,
        *,
        key,
        spec,
        linked_property_id=None,
    ):
        normalized = _normalize_environment_hazard_specs((spec,))
        if not normalized:
            return None
        spec = normalized[0]
        self._ensure_property_anchor(spec["x"], spec["y"], spec["z"])
        if str(spec.get("profile", "") or "").strip().lower() == BLACKWASH_PROFILE:
            return materialize_contamination_release(
                self.sim,
                spec,
                key=key,
                linked_property_id=linked_property_id,
                records=records,
            )
        metadata = _environment_hazard_asset_metadata(
            spec,
            key=key,
            linked_property_id=linked_property_id,
        )
        if not metadata:
            return None
        property_id = self.sim.register_property(
            name=str(spec.get("name", "Hazard")).strip() or "Hazard",
            kind="asset",
            x=int(spec["x"]),
            y=int(spec["y"]),
            z=int(spec["z"]),
            owner_eid=None,
            owner_tag="city",
            metadata=metadata,
        )
        records.append({
            "id": property_id,
            "kind": "asset",
            "x": int(spec["x"]),
            "y": int(spec["y"]),
            "z": int(spec["z"]),
            "archetype": metadata.get("archetype"),
            "building_id": None,
        })
        return property_id

    def _ensure_chunk_properties(self, cx, cy):
        key = (int(cx), int(cy))
        if restore_chunk_state(self.sim, key):
            return
        if key in self.sim.chunk_property_records:
            return

        chunk = self.sim.world.get_chunk(key[0], key[1])
        seed_chunk_organizations(self.sim, chunk)
        rng = random.Random(f"{self.sim.seed}:{key[0]}:{key[1]}:properties")
        records = []

        chunk_size = int(max(8, self.sim.chunk_size))
        origin_x = key[0] * chunk_size
        origin_y = key[1] * chunk_size
        area_type = str(chunk.get("district", {}).get("area_type", "city")).strip().lower() or "city"
        if hasattr(self.sim, "underground_plans_for_chunk"):
            underground_plans, underground_network = self.sim.underground_plans_for_chunk(
                chunk,
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
            )
        else:
            underground_plans = chunk_underground_site_plans(
                chunk,
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
            )
            underground_network = chunk_underground_network_plan(
                chunk,
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
                site_plans=underground_plans,
                world_seed=self.sim.seed,
            )
        underground_by_source = {
            str(plan.get("source_building_id", "")).strip(): plan
            for plan in underground_plans
            if isinstance(plan, dict) and str(plan.get("source_building_id", "")).strip()
        }
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
                records.extend(register_large_span_child_properties(
                    self.sim,
                    parent_source=building,
                    parent_layout=layout,
                    parent_building_id=chunk_building_id,
                    chunk_key=key,
                    area_type=area_type,
                    rng=rng,
                    ensure_walkable=self._ensure_property_anchor,
                    district=chunk.get("district"),
                ))
                service_seed_token = _building_site_service_seed_token(key[0], key[1], building, building_index=i)
                finance_services = list(finance_by_archetype.get(archetype, ()))
                site_services = list(dict.fromkeys(
                    list(_default_site_services_for_archetype(archetype, seed_token=service_seed_token))
                    + list(vehicle_services_for_archetype(archetype))
                ))
                if str(archetype or "").strip().lower() in {"casino", "gaming_hall"}:
                    site_services = list(site_services_with_holdem_mode(
                        site_services,
                        live_cash_available=bool(building.get("dedicated_poker_floor")),
                    ))
                service_destinations = {}
                underpass_plan = underground_by_source.get(chunk_building_id)
                if isinstance(underpass_plan, dict):
                    if UNDERGROUND_ACCESS_SERVICE not in site_services:
                        site_services.append(UNDERGROUND_ACCESS_SERVICE)
                    service_destinations[UNDERGROUND_ACCESS_SERVICE] = dict(
                        (underpass_plan.get("station_surface", {}) or {}).get("destination", {}) or {}
                    )
                business_name = str(building.get("business_name") or "").strip()
                span_name = str(building.get("span_name") or "").strip()
                business_founder_name = str(building.get("business_founder_name") or "").strip()
                business_founder_first_name = str(building.get("business_founder_first_name") or "").strip()
                business_founder_last_name = str(building.get("business_founder_last_name") or "").strip()
                floors, basement_levels = normalize_building_levels(
                    archetype,
                    building.get("floors", 1),
                    building.get("basement_levels", 0),
                )
                display_name = span_name or business_name or f"{archetype}:{building['building_id']}"
                metadata = {
                    "archetype": archetype,
                    "building_id": chunk_building_id,
                    "local_building_id": local_building_id or None,
                    "large_parcel": bool(building.get("large_parcel")),
                    "parcel_span_x": int(building.get("parcel_span_x", 1) or 1),
                    "parcel_span_y": int(building.get("parcel_span_y", 1) or 1),
                    "floors": int(floors),
                    "basement_levels": int(basement_levels),
                    "dedicated_poker_floor": bool(building.get("dedicated_poker_floor")),
                    "poker_floor": int(building.get("poker_floor", 1) or 1) if building.get("dedicated_poker_floor") else None,
                    "rooms": list(building.get("rooms", ())),
                    "common_area_room_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "common_area_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "span_kind": str(building.get("span_kind", "") or "").strip().lower() or None,
                    "span_id": str(building.get("span_id", "") or "").strip() or None,
                    "span_name": span_name or None,
                    "span_founder_name": str(building.get("span_founder_name", "") or "").strip() or None,
                    "span_founder_first_name": str(building.get("span_founder_first_name", "") or "").strip() or None,
                    "span_founder_last_name": str(building.get("span_founder_last_name", "") or "").strip() or None,
                    "span_parent": bool(building.get("span_kind")),
                    "tenant_specs": [dict(spec) for spec in building.get("tenant_specs", ()) if isinstance(spec, dict)],
                    "housing_specs": [dict(spec) for spec in building.get("housing_specs", ()) if isinstance(spec, dict)],
                    "footprint": dict(layout.get("footprint", {})),
                    "placement": dict(layout.get("placement", {})),
                    "placement_profile": dict(building.get("placement_profile", {})) if isinstance(building.get("placement_profile"), dict) else None,
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
                    "holdem_cash_available": bool(building.get("dedicated_poker_floor")) if archetype in {"casino", "gaming_hall"} else None,
                    "holdem_offer_mode": (
                        "live_cash" if building.get("dedicated_poker_floor") else "casino_holdem"
                    ) if archetype in {"casino", "gaming_hall"} else None,
                    "site_service_seed_token": service_seed_token,
                    "is_storefront": bool(building.get("is_storefront")),
                    "public": bool(building.get("public")),
                    "business_name": business_name or None,
                    "business_founder_name": business_founder_name or None,
                    "business_founder_first_name": business_founder_first_name or None,
                    "business_founder_last_name": business_founder_last_name or None,
                    "chunk": key,
                }
                if service_destinations:
                    metadata["site_service_destinations"] = service_destinations
                property_id = self.sim.register_property(
                    name=display_name,
                    kind="building",
                    x=x,
                    y=y,
                    z=z,
                    owner_eid=None,
                    owner_tag="city",
                    metadata=metadata,
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
            site_building_id = f"{key[0]}:{key[1]}:{site.get('site_id', idx)}"
            records.extend(register_large_span_child_properties(
                self.sim,
                parent_source=site,
                parent_layout=layout,
                parent_building_id=site_building_id,
                chunk_key=key,
                area_type=area_type,
                rng=rng,
                ensure_walkable=self._ensure_property_anchor,
                district=chunk.get("district"),
            ))
            service_seed_token = _site_service_seed_token(key[0], key[1], site, site_index=idx)
            span_name = str(site.get("span_name") or "").strip()
            site_name = span_name or str(site.get("name", site_kind.replace("_", " ").title())).strip() or "Site"
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
                    "rooms": list(site.get("rooms", ("entry", "room")) or ("entry", "room")),
                    "building_id": site_building_id,
                    "common_area_room_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "common_area_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "span_kind": str(site.get("span_kind", "") or "").strip().lower() or None,
                    "span_id": str(site.get("span_id", "") or "").strip() or None,
                    "span_name": span_name or None,
                    "span_founder_name": str(site.get("span_founder_name", "") or "").strip() or None,
                    "span_founder_first_name": str(site.get("span_founder_first_name", "") or "").strip() or None,
                    "span_founder_last_name": str(site.get("span_founder_last_name", "") or "").strip() or None,
                    "span_parent": bool(site.get("span_kind")),
                    "tenant_specs": [dict(spec) for spec in site.get("tenant_specs", ()) if isinstance(spec, dict)],
                    "housing_specs": [dict(spec) for spec in site.get("housing_specs", ()) if isinstance(spec, dict)],
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
                "building_id": site_building_id,
            })

        for plan in underground_plans:
            anchor = plan.get("anchor", {})
            footprint = plan.get("footprint", {})
            entry = plan.get("entry", {})
            x = int(anchor.get("x", entry.get("x", 0)))
            y = int(anchor.get("y", entry.get("y", 0)))
            z = int(anchor.get("z", plan.get("z", 0)))
            if self.sim.property_at(x, y, z):
                continue
            self._ensure_property_anchor(x, y, z)
            property_id = self.sim.register_property(
                name=str(plan.get("name", "Underpass")).strip() or "Underpass",
                kind="building",
                x=x,
                y=y,
                z=z,
                owner_eid=None,
                owner_tag="public",
                metadata={
                    "archetype": str(plan.get("kind", "underground_site")).strip().lower() or "underground_site",
                    "site_kind": str(plan.get("kind", "underground_site")).strip().lower() or "underground_site",
                    "building_id": str(plan.get("building_id", "")).strip() or None,
                    "source_building_id": str(plan.get("source_building_id", "")).strip() or None,
                    "floors": int(plan.get("floors", 1) or 1),
                    "rooms": list(plan.get("rooms", ())),
                    "common_area_room_kinds": sorted(COMMON_AREA_ROOM_KINDS),
                    "room_access_overrides": {
                        str(room).strip().lower(): "public"
                        for room in tuple(plan.get("rooms", ()) or ())
                        if str(room).strip()
                    },
                    "footprint": dict(footprint),
                    "footprint_excluded_cells": [
                        dict(cell)
                        for cell in tuple(plan.get("footprint_excluded_cells", ()) or ())
                        if isinstance(cell, dict)
                    ],
                    "entry": dict(entry),
                    "apertures": [dict(aperture) for aperture in plan.get("apertures", ()) if isinstance(aperture, dict)],
                    "skip_ambient_population": True,
                    "ambient_encounter_profile": str(plan.get("ambient_encounter_profile", "")).strip().lower() or None,
                    "ambient_encounter_spawns": [
                        dict(spec)
                        for spec in tuple(plan.get("ambient_encounter_spawns", ()) or ())
                        if isinstance(spec, dict)
                    ],
                    "allow_wildlife_habitation": bool(plan.get("ambient_wildlife_profile")),
                    "ambient_wildlife_profile": str(plan.get("ambient_wildlife_profile", "")).strip().lower() or None,
                    "ambient_wildlife_spawns": [
                        dict(spec)
                        for spec in tuple(plan.get("ambient_wildlife_spawns", ()) or ())
                        if isinstance(spec, dict)
                    ],
                    "ambient_hazard_profile": str(plan.get("ambient_hazard_profile", "")).strip().lower() or None,
                    "ambient_hazard_spawns": [
                        dict(spec)
                        for spec in tuple(plan.get("ambient_hazard_spawns", ()) or ())
                        if isinstance(spec, dict)
                    ],
                    "settled_sediment": dict(plan.get("settled_sediment", {}) or {}),
                    "purchase_cost": 0,
                    "finance_services": [],
                    "site_services": [],
                    "public": True,
                    "chunk": key,
                    "site_id": str(plan.get("site_id", "")).strip() or None,
                },
            )
            records.append({
                "id": property_id,
                "kind": "building",
                "x": x,
                "y": y,
                "z": z,
                "archetype": str(plan.get("kind", "underground_site")).strip().lower() or "underground_site",
                "building_id": str(plan.get("building_id", "")).strip() or None,
            })

            street_surface = plan.get("street_surface", {}) if isinstance(plan.get("street_surface"), dict) else {}
            if street_surface:
                self._register_underground_access_asset(
                    records,
                    key=key,
                    name=str(street_surface.get("name", "Street Stairwell")).strip() or "Street Stairwell",
                    x=int(street_surface.get("x", x)),
                    y=int(street_surface.get("y", y)),
                    z=int(street_surface.get("z", 0)),
                    destination=dict(street_surface.get("destination", {}) or {}),
                    linked_property_id=property_id,
                    fixture_type="street_stairwell",
                    glyph="u",
                    public=True,
                )

            for return_spec in tuple(plan.get("underground_returns", ()) or ()):
                if not isinstance(return_spec, dict):
                    continue
                self._register_underground_access_asset(
                    records,
                    key=key,
                    name=str(return_spec.get("name", "Stairs Up")).strip() or "Stairs Up",
                    x=int(return_spec.get("x", x)),
                    y=int(return_spec.get("y", y)),
                    z=int(return_spec.get("z", z)),
                    destination=dict(return_spec.get("destination", {}) or {}),
                    linked_property_id=property_id,
                    fixture_type="underpass_stairs",
                    glyph="s",
                    public=True,
                )

            for cache_index, cache_spec in enumerate(tuple(plan.get("cache_sites", ()) or ())):
                if not isinstance(cache_spec, dict):
                    continue
                self._register_underground_cache_asset(
                    records,
                    key=key,
                    name=str(cache_spec.get("name", "Maintenance Locker")).strip() or "Maintenance Locker",
                    x=int(cache_spec.get("x", x)),
                    y=int(cache_spec.get("y", y)),
                    z=int(cache_spec.get("z", z)),
                    linked_property_id=property_id,
                    seed_token=(
                        f"{str(plan.get('site_id', '')).strip() or property_id}:"
                        f"{int(cache_spec.get('x', x))}:{int(cache_spec.get('y', y))}:{int(cache_spec.get('z', z))}:"
                        f"{cache_index}"
                    ),
                    cache_profile=str(cache_spec.get("cache_profile", cache_spec.get("kind", "maintenance")) or "maintenance").strip().lower() or "maintenance",
                )
            for service_spec in tuple(plan.get("service_sites", ()) or ()):
                if not isinstance(service_spec, dict):
                    continue
                self._register_underground_service_asset(
                    records,
                    key=key,
                    name=str(service_spec.get("name", "Signal Relay")).strip() or "Signal Relay",
                    x=int(service_spec.get("x", x)),
                    y=int(service_spec.get("y", y)),
                    z=int(service_spec.get("z", z)),
                    site_services=tuple(service_spec.get("site_services", ()) or ()),
                    linked_property_id=property_id,
                    fixture_type=str(service_spec.get("fixture_type", "service_terminal")).strip().lower() or "service_terminal",
                    glyph=str(service_spec.get("glyph", "i"))[:1] or "i",
                    lead_mode=str(service_spec.get("lead_mode", "") or "").strip().lower() or None,
                )
            for hazard_spec in tuple(plan.get("ambient_hazard_spawns", ()) or ()):
                if not isinstance(hazard_spec, dict):
                    continue
                self._register_environmental_hazard_asset(
                    records,
                    key=key,
                    spec=hazard_spec,
                    linked_property_id=property_id,
                )

        if isinstance(underground_network, dict):
            anchor = underground_network.get("anchor", {}) if isinstance(underground_network.get("anchor"), dict) else {}
            footprint = underground_network.get("footprint", {}) if isinstance(underground_network.get("footprint"), dict) else {}
            network_x = int(anchor.get("x", origin_x))
            network_y = int(anchor.get("y", origin_y))
            network_z = int(anchor.get("z", underground_network.get("z", -1)))
            self._ensure_property_anchor(network_x, network_y, network_z)

            source_props = {}
            site_props = {}
            for record in tuple(records):
                prop = self.sim.properties.get(record.get("id")) if isinstance(record, dict) else None
                if not isinstance(prop, dict):
                    continue
                metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
                building_id = str(metadata.get("building_id", "") or "").strip()
                if building_id:
                    source_props.setdefault(building_id, prop)
                    site_props.setdefault(building_id, prop)
            connection_rows = tuple(
                row
                for row in tuple(underground_network.get("site_connections", ()) or ())
                if isinstance(row, dict)
            )
            interested_property_ids = []
            for connection in connection_rows:
                source_prop = source_props.get(str(connection.get("source_building_id", "") or "").strip())
                if isinstance(source_prop, dict):
                    source_property_id = str(source_prop.get("id", "") or "").strip()
                    if source_property_id and source_property_id not in interested_property_ids:
                        interested_property_ids.append(source_property_id)

            rooms = tuple(underground_network.get("rooms", ("access_tunnel",)) or ("access_tunnel",))
            route_destinations = tuple(underground_network.get("route_destinations", ()) or ())
            network_metadata = {
                "archetype": ACCESS_TUNNEL_NETWORK_KIND,
                "site_kind": ACCESS_TUNNEL_NETWORK_KIND,
                "building_id": str(underground_network.get("building_id", "") or "").strip() or None,
                "site_id": str(underground_network.get("site_id", "") or "").strip() or None,
                "floors": 1,
                "rooms": list(rooms),
                "common_area_kind": "access_tunnel",
                "common_area_room_kinds": list(dict.fromkeys(("access_tunnel",) + rooms)),
                "common_area_kinds": list(dict.fromkeys(("access_tunnel",) + rooms)),
                "room_access_overrides": {
                    str(room).strip().lower(): "public"
                    for room in rooms
                    if str(room).strip()
                },
                "footprint": dict(footprint),
                "footprint_cells": [
                    dict(cell)
                    for cell in tuple(underground_network.get("property_cells", ()) or ())
                    if isinstance(cell, dict)
                ],
                "skip_ambient_population": True,
                "ambient_encounter_profile": str(underground_network.get("ambient_encounter_profile", "") or "").strip().lower() or None,
                "ambient_encounter_spawns": [
                    dict(spec)
                    for spec in tuple(underground_network.get("ambient_encounter_spawns", ()) or ())
                    if isinstance(spec, dict)
                ],
                "allow_wildlife_habitation": bool(underground_network.get("ambient_wildlife_profile")),
                "ambient_wildlife_profile": str(underground_network.get("ambient_wildlife_profile", "") or "").strip().lower() or None,
                "ambient_wildlife_spawns": [
                    dict(spec)
                    for spec in tuple(underground_network.get("ambient_wildlife_spawns", ()) or ())
                    if isinstance(spec, dict)
                ],
                "ambient_hazard_profile": str(underground_network.get("ambient_hazard_profile", "") or "").strip().lower() or None,
                "ambient_hazard_spawns": [
                    dict(spec)
                    for spec in tuple(underground_network.get("ambient_hazard_spawns", ()) or ())
                    if isinstance(spec, dict)
                ],
                "settled_sediment": dict(underground_network.get("settled_sediment", {}) or {}),
                "route_code": str(underground_network.get("route_code", "") or "").strip() or None,
                "route_destinations": list(route_destinations),
                "layout_variant": str(underground_network.get("layout_variant", "") or "").strip() or None,
                "control_mode": "shared_infrastructure",
                "display_description": "Connected routes: " + "; ".join(str(value) for value in route_destinations),
                "shared_area_interests": ([{
                    "property_ids": list(interested_property_ids),
                    "common_area_kind": "access_tunnel",
                    "interest_kind": "shared_infrastructure",
                    "authority_reason": "connected_service_spur",
                    "protects": True,
                    "warns": True,
                }] if interested_property_ids else []),
                "purchase_cost": 0,
                "finance_services": [],
                "site_services": [],
                "public": True,
                "chunk": key,
            }
            network_property_id = self.sim.register_property(
                name=str(underground_network.get("name", "Access Tunnel Network") or "Access Tunnel Network"),
                kind="building",
                x=network_x,
                y=network_y,
                z=network_z,
                owner_eid=None,
                owner_tag="public",
                metadata=network_metadata,
            )
            network_prop = self.sim.properties.get(network_property_id)
            seed_property_organization_defaults(network_prop, district=chunk.get("district"))
            ensure_property_organization(self.sim, network_prop)
            for connection in connection_rows:
                source_prop = source_props.get(str(connection.get("source_building_id", "") or "").strip())
                if not isinstance(source_prop, dict):
                    continue
                source_org_eid = ensure_property_organization(self.sim, source_prop)
                if source_org_eid is not None:
                    link_property_organization(
                        self.sim,
                        network_prop,
                        organization_eid=source_org_eid,
                        link_kind="service_host",
                        active=True,
                    )
            records.append({
                "id": network_property_id,
                "kind": "building",
                "x": network_x,
                "y": network_y,
                "z": network_z,
                "archetype": ACCESS_TUNNEL_NETWORK_KIND,
                "building_id": network_metadata.get("building_id"),
            })

            for cache_index, cache_spec in enumerate(tuple(underground_network.get("cache_sites", ()) or ())):
                if not isinstance(cache_spec, dict):
                    continue
                self._register_underground_cache_asset(
                    records,
                    key=key,
                    name=str(cache_spec.get("name", "Tunnel Cache") or "Tunnel Cache"),
                    x=int(cache_spec.get("x", network_x)),
                    y=int(cache_spec.get("y", network_y)),
                    z=int(cache_spec.get("z", network_z)),
                    linked_property_id=network_property_id,
                    seed_token=f"{network_metadata.get('site_id')}:network:{cache_index}",
                    cache_profile=str(cache_spec.get("cache_profile", "maintenance") or "maintenance"),
                )
            for service_spec in tuple(underground_network.get("service_sites", ()) or ()):
                if not isinstance(service_spec, dict):
                    continue
                self._register_underground_service_asset(
                    records,
                    key=key,
                    name=str(service_spec.get("name", "Junction Marker") or "Junction Marker"),
                    x=int(service_spec.get("x", network_x)),
                    y=int(service_spec.get("y", network_y)),
                    z=int(service_spec.get("z", network_z)),
                    site_services=tuple(service_spec.get("site_services", ()) or ()),
                    linked_property_id=network_property_id,
                    fixture_type=str(service_spec.get("fixture_type", "underground_route_marker") or "underground_route_marker"),
                    glyph=str(service_spec.get("glyph", "j") or "j")[:1],
                    display_description=str(service_spec.get("display_description", "") or ""),
                    route_destinations=route_destinations,
                )
            for hazard_spec in tuple(underground_network.get("ambient_hazard_spawns", ()) or ()):
                if isinstance(hazard_spec, dict):
                    self._register_environmental_hazard_asset(
                        records,
                        key=key,
                        spec=hazard_spec,
                        linked_property_id=network_property_id,
                    )

            for connection in connection_rows:
                if bool(connection.get("direct")):
                    continue
                site_prop = site_props.get(str(connection.get("building_id", "") or "").strip())
                lower_linked_id = site_prop.get("id") if isinstance(site_prop, dict) else network_property_id
                lower_destination = {
                    "x": int(connection.get("network_x", connection.get("x", network_x))),
                    "y": int(connection.get("network_y", connection.get("y", network_y))),
                    "z": int(connection.get("network_z", network_z)),
                    "destination_name": str(underground_network.get("name", "access tunnels") or "access tunnels"),
                    "travel_ticks": 1,
                }
                upper_destination = {
                    "x": int(connection.get("x", network_x)),
                    "y": int(connection.get("y", network_y)),
                    "z": int(connection.get("z", network_z)),
                    "destination_name": str(connection.get("source_building_name", "lower passage") or "lower passage"),
                    "travel_ticks": 1,
                }
                self._register_underground_access_asset(
                    records,
                    key=key,
                    name="Stairs to Access Tunnels",
                    x=int(connection.get("x", network_x)),
                    y=int(connection.get("y", network_y)),
                    z=int(connection.get("z", network_z)),
                    destination=lower_destination,
                    linked_property_id=lower_linked_id,
                    fixture_type="tunnel_stairs",
                    glyph="s",
                    public=True,
                )
                self._register_underground_access_asset(
                    records,
                    key=key,
                    name=f"Stairs to {str(connection.get('source_building_name', 'Lower Passage') or 'Lower Passage')}",
                    x=int(connection.get("network_x", connection.get("x", network_x))),
                    y=int(connection.get("network_y", connection.get("y", network_y))),
                    z=int(connection.get("network_z", network_z)),
                    destination=upper_destination,
                    linked_property_id=network_property_id,
                    fixture_type="tunnel_stairs",
                    glyph="s",
                    public=True,
                )

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

        ramps = generate_quick_travel_ramp_records(
            self.sim,
            chunk,
            rng,
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
        )
        for ramp in ramps:
            x = int(ramp["x"])
            y = int(ramp["y"])
            z = int(ramp.get("z", 0) or 0)
            if self.sim.property_at(x, y, z):
                continue
            metadata = dict(ramp.get("metadata", {}))
            metadata["chunk"] = key
            kind = str(ramp.get("kind", "asset")).strip().lower() or "asset"
            property_id = self.sim.register_property(
                name=str(ramp.get("name", "Entrance Ramp")).strip() or "Entrance Ramp",
                kind=kind,
                x=x,
                y=y,
                z=z,
                owner_eid=None,
                owner_tag=str(ramp.get("owner_tag", "city")).strip() or "city",
                metadata=metadata,
            )
            records.append({
                "id": property_id,
                "kind": kind,
                "x": x,
                "y": y,
                "z": z,
                "archetype": metadata.get("archetype"),
                "building_id": None,
            })

        vehicle_target_count = max(2, chunk_size // 12) if area_type == "city" else (1 if rng.random() < 0.55 else 0)
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
        maybe_seed_run_echo_for_chunk(self.sim, chunk)

    def _ensure_chunk_population(self, cx, cy):
        key = (int(cx), int(cy))
        chunk = self.sim.world.get_chunk(key[0], key[1])
        records = self.sim.chunk_property_records.get(key, ())
        if not records:
            return
        seed_chunk_items(self.sim, chunk, records)
        spawn_chunk_npcs(self.sim, chunk, records)
        spawn_chunk_special_population(self.sim, chunk, records)

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
            ensure_chunk_flora(
                self.sim,
                loaded_data.get("chunk", loaded_data) if isinstance(loaded_data, dict) else loaded_data,
                property_records=self.sim.chunk_property_records.get((loaded_cx, loaded_cy), ()),
            )
            ensure_underground_remediation_flora(
                self.sim,
                loaded_data.get("chunk", loaded_data) if isinstance(loaded_data, dict) else loaded_data,
                property_records=self.sim.chunk_property_records.get((loaded_cx, loaded_cy), ()),
            )
        if not report.get("changed"):
            return

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
        self.sim.events.subscribe("street_buy_transaction", self.on_street_buy_transaction)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("stakeout_intel_gained", self.on_stakeout_intel_gained)
        self.sim.events.subscribe("overworld_discovery_found", self.on_overworld_discovery_found)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)

    def _ensure_seeded(self):
        return seed_run_opportunities(self.sim, player_eid=self.player_eid, rng=self.seed_rng)

    @staticmethod
    def _opportunity_chunk_text(chunk):
        if isinstance(chunk, (list, tuple)) and len(chunk) == 2:
            try:
                return f"near chunk {int(chunk[0])},{int(chunk[1])}"
            except (TypeError, ValueError):
                return "somewhere nearby"
        return "somewhere nearby"

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
                f"O{int(entry.get('id', 0))} {title}, {self._opportunity_chunk_text(chunk)}, from {source_text}"
            )

        self.sim.emit(Event(
            "opportunity_added",
            eid=self.player_eid,
            count=len(new_entries),
            lines=tuple(preview_lines),
            remaining=max(0, len(new_entries) - len(preview_lines)),
        ))

    def _emit_report(self, limit=8):
        ensure_initial_opportunities(self.sim, player_eid=self.player_eid, rng=self.seed_rng)
        board = evaluate_opportunity_board(self.sim, self.player_eid, limit=max(1, int(limit)))
        title = (
            f"Opportunities ({int(board.get('active_count', 0))} active / "
            f"{int(board.get('completed_count', 0))} done / "
            f"{int(board.get('failed_count', 0))} failed)"
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

    def _remember_opportunity_handoff_interaction(self, property_id):
        property_id = str(property_id or "").strip()
        if not property_id:
            return
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        current_tick = int(getattr(self.sim, "tick", 0))

        recent_props = traits.get("recent_handoff_property_interactions")
        if not isinstance(recent_props, dict):
            recent_props = {}
            traits["recent_handoff_property_interactions"] = recent_props
        recent_props[property_id] = current_tick

        prop = self.sim.properties.get(property_id) if hasattr(self.sim, "properties") else None
        building_id = _building_id_from_property(prop) if isinstance(prop, dict) else ""
        if building_id:
            recent_buildings = traits.get("recent_handoff_building_interactions")
            if not isinstance(recent_buildings, dict):
                recent_buildings = {}
                traits["recent_handoff_building_interactions"] = recent_buildings
            recent_buildings[building_id] = current_tick
        else:
            recent_buildings = traits.get("recent_handoff_building_interactions")

        cutoff = current_tick - 16
        for raw_property_id, raw_tick in list(recent_props.items()):
            if _int_or_default(raw_tick, default=-10_000) < cutoff:
                recent_props.pop(raw_property_id, None)
        if isinstance(recent_buildings, dict):
            for raw_building_id, raw_tick in list(recent_buildings.items()):
                if _int_or_default(raw_tick, default=-10_000) < cutoff:
                    recent_buildings.pop(raw_building_id, None)

    def _remember_required_item_transfer(self, *, item_id, quantity=1, npc_eid=None, property_id=None, building_id=None, chunk=None, source=""):
        item_id = str(item_id or "").strip().lower()
        property_id = str(property_id or "").strip()
        building_id = str(building_id or "").strip()
        npc_eid = _int_or_default(npc_eid, default=0)
        source = str(source or "").strip().lower()
        try:
            quantity = max(1, int(quantity))
        except (TypeError, ValueError):
            quantity = 1
        if isinstance(chunk, (list, tuple)) and len(chunk) == 2:
            try:
                chunk = (int(chunk[0]), int(chunk[1]))
            except (TypeError, ValueError):
                chunk = None
        else:
            chunk = None
        if not item_id:
            return

        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        records = traits.get("recent_required_item_transfers")
        if not isinstance(records, list):
            records = []
            traits["recent_required_item_transfers"] = records
        records.append({
            "tick": int(getattr(self.sim, "tick", 0)),
            "item_id": item_id,
            "quantity": int(quantity),
            "npc_eid": int(npc_eid) if npc_eid > 0 else 0,
            "property_id": property_id,
            "building_id": building_id,
            "chunk": chunk,
            "source": source,
        })
        cutoff = int(getattr(self.sim, "tick", 0)) - 24
        kept = []
        for raw in list(records):
            if not isinstance(raw, dict):
                continue
            if _int_or_default(raw.get("tick"), default=-10_000) < cutoff:
                continue
            if not str(raw.get("item_id", "") or "").strip():
                continue
            kept.append(raw)
        traits["recent_required_item_transfers"] = kept[-20:]

    def on_property_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_id = event.data.get("property_id")
        self._remember_opportunity_property_interaction(property_id)
        if bool(event.data.get("opportunity_handoff_ready")):
            self._remember_opportunity_handoff_interaction(property_id)

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
        self._remember_opportunity_handoff_interaction(property_id)
        if str(event.data.get("service", "")).strip().lower() == "intel":
            self._remember_opportunity_activity_for_property(property_id, "intel")

    def on_site_intel_report(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._remember_opportunity_activity_for_property(event.data.get("property_id"), "intel")

    def on_trade_bought(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("owner_transfer")):
            return
        self._remember_opportunity_activity_for_property(event.data.get("property_id"), "trade")

    def on_trade_sold(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("owner_transfer")):
            return
        property_id = event.data.get("property_id")
        self._remember_opportunity_activity_for_property(property_id, "trade")
        prop = self.sim.properties.get(str(property_id or "").strip()) if hasattr(self.sim, "properties") else None
        self._remember_opportunity_handoff_interaction(property_id)
        chunk = None
        if isinstance(prop, dict):
            try:
                chunk = self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
            except (TypeError, ValueError):
                chunk = None
        self._remember_required_item_transfer(
            item_id=event.data.get("item_id"),
            quantity=event.data.get("quantity", 1),
            property_id=property_id,
            building_id=_building_id_from_property(prop) if isinstance(prop, dict) else "",
            chunk=chunk,
            source="trade_sold",
        )

    def on_street_buy_transaction(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid")
        sold_items = event.data.get("sold_items", ())
        if isinstance(sold_items, dict):
            sold_items = (sold_items,)
        if not isinstance(sold_items, (list, tuple)):
            return
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        chunk = None
        if player_pos is not None:
            try:
                chunk = self.sim.chunk_coords(int(player_pos.x), int(player_pos.y))
            except (TypeError, ValueError):
                chunk = None
        for spec in sold_items:
            if not isinstance(spec, dict):
                continue
            self._remember_required_item_transfer(
                item_id=spec.get("item_id"),
                quantity=spec.get("quantity", 1),
                npc_eid=npc_eid,
                chunk=chunk,
                source="street_buy",
            )

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

    def on_npc_killed(self, event):
        record_opportunity_kill(
            self.sim,
            event.data.get("target_eid"),
            event.data.get("source_eid"),
        )

    def _emit_provided_item_log(self, item_notice):
        if not isinstance(item_notice, dict):
            return
        opp_id = _int_or_default(item_notice.get("opportunity_id"), default=0)
        title = str(item_notice.get("title", "Opportunity") or "Opportunity").strip() or "Opportunity"
        label = f"O{opp_id} {title}" if opp_id > 0 else title
        item_label = str(item_notice.get("item_label", "package") or "package").strip() or "package"
        site_name = str(item_notice.get("site_name", "pickup site") or "pickup site").strip() or "pickup site"
        status = str(item_notice.get("status", "") or "").strip().lower()
        if status == "received":
            self.sim.log.add(
                f"Pickup confirmed: {label} received {item_label} at {site_name}.",
                channel="opportunity",
                priority="high",
            )
            return
        if status == "inventory_full":
            self.sim.log.add(
                f"Pickup waiting: {label} needs room for {item_label}; ask again at {site_name}.",
                channel="opportunity",
                priority="high",
            )

    def update(self):
        self._ensure_seeded()
        tick = int(getattr(self.sim, "tick", 0))
        if tick - self.last_refresh_tick >= self.refresh_interval:
            refresh_due_dynamic_opportunities(self.sim, self.player_eid, reason="periodic")
            self.last_refresh_tick = tick
        self._emit_new_opportunity_log()
        for notice in stage_active_opportunities(self.sim, self.player_eid):
            self.sim.log.add(notice, channel="opportunity", priority="high")

        lifecycle = advance_opportunity_lifecycle(self.sim, self.player_eid)
        completed = list(lifecycle.get("completed", ())) if isinstance(lifecycle, dict) else []
        failed = list(lifecycle.get("failed", ())) if isinstance(lifecycle, dict) else []
        issued_items = list(lifecycle.get("issued_items", ())) if isinstance(lifecycle, dict) else []
        for item_notice in issued_items:
            self._emit_provided_item_log(item_notice)
        if not completed and not failed:
            return

        if completed or failed:
            refresh_due_dynamic_opportunities(self.sim, self.player_eid, reason="terminal")
            self._emit_new_opportunity_log()
            for notice in stage_active_opportunities(self.sim, self.player_eid):
                self.sim.log.add(notice, channel="opportunity", priority="high")

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
                reward_recipient_eid=entry.get("reward_recipient_eid"),
                reward_recipient_name=str(entry.get("reward_recipient_name", "") or "").strip(),
                reward_attribution=str(entry.get("reward_attribution", "") or "").strip().lower(),
                completion_reason=str(entry.get("completion_reason", "")).strip(),
                active_remaining=active_count,
            ))
        for entry in failed:
            raw_chunk = entry.get("chunk", (0, 0))
            if isinstance(raw_chunk, (list, tuple)) and len(raw_chunk) == 2:
                try:
                    chunk = (int(raw_chunk[0]), int(raw_chunk[1]))
                except (TypeError, ValueError):
                    chunk = (0, 0)
            else:
                chunk = (0, 0)

            self.sim.emit(Event(
                "opportunity_failed",
                eid=self.player_eid,
                opportunity_id=int(entry.get("id", 0)),
                title=str(entry.get("title", "Opportunity")).strip() or "Opportunity",
                summary=str(entry.get("summary", "")).strip(),
                chunk=chunk,
                source=str(entry.get("source", "unknown")).strip(),
                risk=str(entry.get("risk", "low")).strip(),
                playstyles=tuple(entry.get("playstyles", ())),
                failure_reason=str(entry.get("failure_reason", "")).strip(),
                failure_code=str(entry.get("failure_code", "")).strip().lower(),
                active_remaining=active_count,
            ))

class RivalOperatorSystem(System):

    RIVAL_COUNT = 3
    DECISION_INTERVAL = 90
    TRAVEL_INTERVAL = 55
    ACTION_INTERVAL = 210
    LOCAL_ACTION_INTERVAL = 72
    RUMOR_INTERVAL = 150
    SCENE_HOLD_HOURS = 3.0
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

    def _ticks_per_hour(self):
        traits = getattr(self.sim, "world_traits", {})
        clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
        if not isinstance(clock, dict):
            clock = {}
        try:
            ticks = int(clock.get("ticks_per_hour", 600))
        except (TypeError, ValueError):
            ticks = 600
        return max(1, ticks)

    def _scene_hold_ticks(self):
        return max(90, int(round(float(self.SCENE_HOLD_HOURS) * float(self._ticks_per_hour()))))

    def _scene_rumor_interval(self):
        return max(int(self.RUMOR_INTERVAL), max(1, int(self._scene_hold_ticks()) // 2))

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
        rival.setdefault("scene_opportunity_id", 0)
        rival.setdefault("scene_until_tick", -1)
        if not isinstance(rival.get("inventory_snapshot"), list):
            rival["inventory_snapshot"] = []
        if not isinstance(rival.get("weapon_loadout_snapshot"), dict):
            rival["weapon_loadout_snapshot"] = {}
        if not isinstance(rival.get("armor_loadout_snapshot"), dict):
            rival["armor_loadout_snapshot"] = {}
        if not isinstance(rival.get("vitality_snapshot"), dict):
            rival["vitality_snapshot"] = {}

    def _clear_scene_hold(self, rival, *, opportunity_id=None):
        if not isinstance(rival, dict):
            return
        current_scene_id = _int_or_default(rival.get("scene_opportunity_id"), default=0)
        if opportunity_id is not None and current_scene_id not in {0, int(opportunity_id)}:
            return
        rival["scene_opportunity_id"] = 0
        rival["scene_until_tick"] = -1

    def _scene_hold_active(self, rival, entry=None):
        if not isinstance(rival, dict):
            return False
        current_scene_id = _int_or_default(rival.get("scene_opportunity_id"), default=0)
        scene_until_tick = _int_or_default(rival.get("scene_until_tick"), default=-1)
        if current_scene_id <= 0 or scene_until_tick <= 0:
            return False
        if isinstance(entry, dict):
            entry_id = _int_or_default(entry.get("id"), default=0)
            if entry_id > 0 and current_scene_id != entry_id:
                return False
        return scene_until_tick > int(self.sim.tick)

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
        current_target_id = int(rival.get("target_opportunity_id", 0) or 0)
        target = self._target_entry(rival)
        if target is not None:
            age = int(self.sim.tick) - int(rival.get("last_decision_tick", -10_000))
            if age <= self.TARGET_DECAY_TICKS:
                target_id = int(target.get("id", 0) or 0)
                if target_id != current_target_id:
                    self._clear_scene_hold(rival, opportunity_id=current_target_id or None)
                rival["target_opportunity_id"] = target_id
                rival["target_chunk"] = self._normalize_chunk(target.get("chunk"), fallback=rival.get("current_chunk"))
                return target
            self._clear_scene_hold(rival, opportunity_id=current_target_id or None)

        selected = self._choose_target_for_rival(rival)
        if selected is None:
            self._clear_scene_hold(rival, opportunity_id=current_target_id or None)
            rival["target_opportunity_id"] = 0
            rival["target_chunk"] = self._choose_wander_chunk(rival)
            rival["status"] = "circling"
            rival["last_decision_tick"] = int(self.sim.tick)
            return None

        selected_id = int(selected.get("id", 0) or 0)
        if selected_id != current_target_id:
            self._clear_scene_hold(rival, opportunity_id=current_target_id or None)
        rival["target_opportunity_id"] = selected_id
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

    def _property_for_building_id(self, building_id):
        building_id = str(building_id or "").strip()
        if not building_id or not hasattr(self.sim, "properties"):
            return None
        for prop in list(self.sim.properties.values()):
            if _building_id_from_property(prop) == building_id:
                return prop
        return None

    def _opportunity_anchor_ids(self, entry):
        if not isinstance(entry, dict):
            return "", ""
        requirements = _opportunity_requirements(entry)
        for property_key, building_key in (
            ("delivery_property_id", "delivery_building_id"),
            ("property_id", "building_id"),
            ("pickup_property_id", "pickup_building_id"),
        ):
            property_id = str(requirements.get(property_key, "") or "").strip()
            building_id = str(requirements.get(building_key, "") or "").strip()
            if property_id or building_id:
                return property_id, building_id
        return str(entry.get("property_id", "") or "").strip(), str(entry.get("building_id", "") or "").strip()

    def _opportunity_property(self, entry):
        if not isinstance(entry, dict):
            return None
        property_id, building_id = self._opportunity_anchor_ids(entry)
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                return prop
        if building_id:
            prop = self._property_for_building_id(building_id)
            if isinstance(prop, dict):
                return prop
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

    def _opportunity_anchor_name(self, entry):
        prop = self._opportunity_property(entry)
        if isinstance(prop, dict):
            return str(prop.get("name", prop.get("id", "that place"))).strip() or "that place"
        title = str((entry or {}).get("title", "a local lead")).strip()
        return title or "a local lead"

    def _reveal_rival_target_to_player(self, entry, *, confidence=0.0, source="rival_activity"):
        if not isinstance(entry, dict):
            return None
        opportunity_id = int(entry.get("id", 0) or 0)
        if opportunity_id <= 0:
            return None
        awareness_state = "confirmed" if float(confidence) >= 0.84 else "heard"
        reveal_opportunity_to_observer(
            self.sim,
            self.player_eid,
            opportunity_id,
            awareness_state=awareness_state,
            confidence=max(0.0, min(1.0, float(confidence))),
            source=str(source or "rival_activity").strip().lower() or "rival_activity",
        )
        return opportunity_intel_for_observer(self.sim, self.player_eid, opportunity_id)

    def _begin_scene_hold(self, rival, entry):
        if not isinstance(rival, dict) or not isinstance(entry, dict):
            return False
        opportunity_id = int(entry.get("id", 0) or 0)
        if opportunity_id <= 0 or self._scene_hold_active(rival, entry):
            return False
        if _int_or_default(rival.get("scene_opportunity_id"), default=0) == opportunity_id and _int_or_default(rival.get("scene_until_tick"), default=-1) > 0:
            return False
        self._clear_scene_hold(rival)
        rival["scene_opportunity_id"] = opportunity_id
        rival["scene_until_tick"] = int(self.sim.tick) + int(self._scene_hold_ticks())
        target_chunk = self._normalize_chunk(entry.get("chunk"), fallback=rival.get("current_chunk"))
        distance_text = opportunity_distance_text(
            self._chunk_distance(self._player_chunk_coord(), target_chunk),
            self._step_direction(self._player_chunk_coord(), target_chunk),
        )
        self._emit_rival_activity(
            rival,
            entry=entry,
            summary=f"{rival.get('name', 'Someone')} is said to be {self._spotted_summary(rival, entry)} {distance_text}",
            confidence=0.78,
            truthful=True,
            source="rival_scene",
        )
        rival["last_rumor_tick"] = int(self.sim.tick)
        return True

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
        title = self._opportunity_anchor_name(entry)
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
        prop = self._opportunity_property(entry)
        if isinstance(entry, dict):
            self._reveal_rival_target_to_player(entry, confidence=0.96, source="rival_spotted")
        self.sim.emit(Event(
            "rival_operator_spotted",
            eid=self.player_eid,
            rival_id=int(rival.get("id", 0) or 0),
            rival_name=str(rival.get("name", "operator")).strip() or "operator",
            rival_mask=str(rival.get("public_mask", "quiet")).strip().lower() or "quiet",
            rival_reputation=str(rival.get("reputation", "steady")).strip().lower() or "steady",
            hustle=str(rival.get("hustle", "cash")).strip().lower() or "cash",
            chunk=self._normalize_chunk(rival.get("current_chunk")),
            opportunity_id=int((entry or {}).get("id", 0) or 0),
            title=str((entry or {}).get("title", "Opportunity")).strip() or "Opportunity",
            property_id=str((prop or {}).get("id", "")).strip(),
            property_name=str((prop or {}).get("name", "")).strip(),
            building_id=_building_id_from_property(prop) if isinstance(prop, dict) else "",
            confidence=0.96,
            truthful=True,
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
        requirements = _opportunity_requirements(resolved)
        tags = set(self._rival_followup_activity_tags(resolved))
        discovery_tags = {tag for tag in tags if tag == "discovery" or tag.startswith("discovery_")}
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
        if tags & {"stakeout", "intel"}:
            reward["intel"] += 1
        if tags & {"trade", "finance", "service"}:
            reward["credits"] += 4
        if tags & {"contact"} and resolution != "burned":
            reward["standing"] = max(1, int(reward.get("standing", 0) or 0))
        if discovery_tags and not (tags & {"stakeout", "intel", "trade", "finance", "service"}):
            reward["credits"] += 4
        if bool(requirements.get("require_item_id")) and casualty != "dead":
            reward["credits"] += 4
        return {key: int(value) for key, value in reward.items() if int(value) > 0}

    def _rival_followup_activity_tags(self, resolved):
        requirements = _opportunity_requirements(resolved)
        raw_tags = requirements.get("recent_activity_tags")
        if isinstance(raw_tags, str):
            raw_tags = (raw_tags,)
        tags = []
        for raw in tuple(raw_tags or ()):
            tag = str(raw or "").strip().lower()
            if tag and tag not in tags:
                tags.append(tag)
        if tags:
            return tuple(tags)

        for flag, tag in (
            ("prefer_finance_services", "finance"),
            ("prefer_site_services", "service"),
            ("prefer_storefront", "trade"),
        ):
            if bool(requirements.get(flag)) and tag not in tags:
                tags.append(tag)

        if (
            _int_or_default(requirements.get("interact_npc_eid"), default=0) > 0
            or _int_or_default(requirements.get("pickup_interact_npc_eid"), default=0) > 0
        ) and "contact" not in tags:
            tags.append("contact")

        if str(requirements.get("require_item_id", "") or "").strip().lower():
            for tag in ("trade", "contact"):
                if tag not in tags:
                    tags.append(tag)

        return tuple(tags)

    def _rival_followup_anchor(self, resolved):
        requirements = _opportunity_requirements(resolved)
        for property_key, building_key in (
            ("delivery_property_id", "delivery_building_id"),
            ("property_id", "building_id"),
            ("pickup_property_id", "pickup_building_id"),
        ):
            property_id = str(requirements.get(property_key, "") or "").strip()
            building_id = str(requirements.get(building_key, "") or "").strip()
            if property_id or building_id:
                return property_id, building_id

        issuer = resolved.get("issuer") if isinstance(resolved.get("issuer"), dict) else {}
        property_id = str(issuer.get("property_id", "") or "").strip()
        return property_id, ""

    def _rival_followup_requirements(self, resolved, *, chunk):
        requirements = _opportunity_requirements(resolved)
        activity_tags = self._rival_followup_activity_tags(resolved)
        property_id, building_id = self._rival_followup_anchor(resolved)
        followup_requirements = {
            "visit_chunk": chunk,
            "rival_followup": True,
            "followup_from_opportunity_id": int(resolved.get("id", 0) or 0),
        }
        if property_id:
            followup_requirements["property_id"] = property_id
        if building_id:
            followup_requirements["building_id"] = building_id
        if activity_tags:
            followup_requirements["recent_activity_tags"] = activity_tags
        for flag in ("prefer_storefront", "prefer_finance_services", "prefer_site_services", "prefer_public"):
            if flag in requirements:
                followup_requirements[flag] = bool(requirements.get(flag))
        return followup_requirements

    def _rival_followup_action_phrase(self, resolved):
        activity_tags = set(self._rival_followup_activity_tags(resolved))
        property_id, building_id = self._rival_followup_anchor(resolved)
        location_word = "there" if property_id or building_id else "in the area"
        discovery_tags = {tag for tag in activity_tags if tag == "discovery" or tag.startswith("discovery_")}

        if activity_tags & {"stakeout", "intel"}:
            return f"hold a quiet watch or pull intel {location_word}"
        if activity_tags & {"contact"} and activity_tags & {"trade", "finance", "service"}:
            return f"talk to locals or work the local counter {location_word}"
        if activity_tags & {"finance"} and not (activity_tags & {"contact", "intel", "stakeout"}):
            return f"lean on the local finance desk {location_word}"
        if activity_tags & {"service", "trade", "finance"}:
            return f"work the local counter or services {location_word}"
        if activity_tags & {"contact"}:
            return f"talk to people {location_word} while nerves are still hot"
        if discovery_tags:
            return f"survey the ground {location_word}"
        if bool(_opportunity_requirements(resolved).get("require_item_id")):
            return f"work the same handoff ground {location_word}"
        return f"move on the same ground {location_word}"

    def _rival_followup_playstyles(self, rival, resolved):
        playstyles = []
        for raw in tuple((resolved or {}).get("playstyles", ()) or ()):
            style = str(raw or "").strip().lower()
            if not style or style == "combat" or style in playstyles:
                continue
            playstyles.append(style)

        activity_tags = set(self._rival_followup_activity_tags(resolved))
        if activity_tags & {"trade", "finance", "service"} and "economic" not in playstyles:
            playstyles.append("economic")
        if activity_tags & {"contact"} and "social" not in playstyles:
            playstyles.append("social")
        if activity_tags & {"stakeout", "intel"} and "stealth" not in playstyles:
            playstyles.append("stealth")

        if playstyles:
            return tuple(playstyles[:3])

        hustle = str(rival.get("hustle", "cash")).strip().lower() or "cash"
        if hustle == "network":
            return ("social", "stealth")
        if hustle == "intel":
            return ("stealth", "social")
        return ("economic", "stealth")

    def _is_consumptive_rival_job(self, resolved):
        if not isinstance(resolved, dict):
            return False
        kind = str(resolved.get("kind", "")).strip().lower()
        if kind in {
            "distance_delivery",
            "distance_delivery_procure",
            "distance_pickup",
            "medical_drop",
            "dead_drop_return",
        }:
            return True
        requirements = _opportunity_requirements(resolved)
        return bool(str(requirements.get("require_item_id", "")).strip().lower())

    def _rival_followup_has_concrete_anchor(self, resolved):
        if not isinstance(resolved, dict):
            return False
        requirements = _opportunity_requirements(resolved)
        property_id, building_id = self._rival_followup_anchor(resolved)
        property_id = str(property_id or "").strip()
        building_id = str(building_id or "").strip()
        if property_id and isinstance(getattr(self.sim, "properties", {}).get(property_id), dict):
            return True
        if building_id:
            for prop in getattr(self.sim, "properties", {}).values():
                if isinstance(prop, dict) and _building_id_from_property(prop) == building_id:
                    return True
        for key in ("interact_npc_eid", "pickup_interact_npc_eid"):
            target_eid = _int_or_default(requirements.get(key), default=0)
            if target_eid > 0 and self.sim.ecs.get(Position).get(target_eid) is not None:
                return True
        return False

    def _rival_resolution_policy(self, resolved, *, resolution, casualty=""):
        if not isinstance(resolved, dict):
            return "no_followup"
        if self._is_rival_followup_entry(resolved):
            return "no_followup"

        kind = str(resolved.get("kind", "")).strip().lower()
        if kind == "contract_kill":
            return "no_followup"
        if self._is_consumptive_rival_job(resolved):
            return "hard_fail"

        requirements = _opportunity_requirements(resolved)
        failure_policy = resolved.get("failure_policy", {}) if isinstance(resolved.get("failure_policy"), dict) else {}
        explicit = failure_policy.get("allow_rival_followup")
        if explicit is None:
            explicit = requirements.get("allow_rival_followup")

        has_anchor = self._rival_followup_has_concrete_anchor(resolved)
        if explicit is not None:
            return "salvage_followup" if bool(explicit) and has_anchor else "no_followup"
        if not has_anchor:
            return "no_followup"

        if str(casualty or "").strip().lower() == "dead":
            return "salvage_followup"
        if str(resolution or "").strip().lower() in {"claimed", "burned"}:
            return "salvage_followup"
        return "no_followup"

    def _rival_resolution_reason(self, rival, resolved, *, resolution):
        rival_name = str(rival.get("name", "a rival")).strip() or "a rival"
        if not isinstance(resolved, dict):
            if resolution == "burned":
                return f"{rival_name} burned the scene"
            return f"{rival_name} got there first"

        requirements = _opportunity_requirements(resolved)
        kind = str(resolved.get("kind", "")).strip().lower()
        item_id = str(requirements.get("require_item_id", "")).strip().lower()
        acquisition_hint = str(requirements.get("acquisition_hint", "")).strip().lower()
        def _has_chunk(value):
            return isinstance(value, (tuple, list)) and len(value) >= 2

        has_delivery_leg = any(
            (
                _has_chunk(requirements.get("delivery_chunk")),
                str(requirements.get("delivery_property_id", "")).strip(),
                str(requirements.get("delivery_building_id", "")).strip(),
                _int_or_default(requirements.get("interact_npc_eid"), default=0) > 0,
            )
        )
        has_pickup_leg = any(
            (
                _has_chunk(requirements.get("pickup_chunk")),
                str(requirements.get("pickup_property_id", "")).strip(),
                str(requirements.get("pickup_building_id", "")).strip(),
                _int_or_default(requirements.get("pickup_interact_npc_eid"), default=0) > 0,
                acquisition_hint == "pickup",
            )
        )
        if resolution == "claimed":
            if kind in {"distance_delivery", "distance_delivery_procure", "medical_drop"} or (
                item_id and has_delivery_leg and acquisition_hint != "pickup"
            ):
                return f"{rival_name} completed the handoff first"
            if kind in {"distance_pickup", "dead_drop_return"} or (
                item_id and has_pickup_leg and has_delivery_leg and acquisition_hint == "pickup"
            ):
                return f"{rival_name} lifted the pickup first"
            if item_id:
                return f"{rival_name} took the objective first"
            return f"{rival_name} got there first"

        if kind in {"distance_delivery", "distance_delivery_procure", "medical_drop"} or (
            item_id and has_delivery_leg and acquisition_hint != "pickup"
        ):
            return f"{rival_name} burned the handoff route"
        if kind in {"distance_pickup", "dead_drop_return"} or (
            item_id and has_pickup_leg and has_delivery_leg and acquisition_hint == "pickup"
        ):
            return f"{rival_name} burned the pickup route"
        if item_id:
            return f"{rival_name} burned the objective trail"
        return f"{rival_name} burned the scene"

    def _should_spawn_rival_followup(self, resolved, *, resolution, casualty=""):
        return self._rival_resolution_policy(resolved, resolution=resolution, casualty=casualty) == "salvage_followup"

    def _spawn_rival_followup(self, rival, resolved, *, resolution, casualty=""):
        if not isinstance(resolved, dict):
            return None
        policy = self._rival_resolution_policy(resolved, resolution=resolution, casualty=casualty)
        resolved["rival_resolution_policy"] = policy
        if policy != "salvage_followup":
            return None
        chunk = self._normalize_chunk(resolved.get("chunk"), fallback=rival.get("current_chunk"))
        followup_requirements = self._rival_followup_requirements(resolved, chunk=chunk)
        action_phrase = self._rival_followup_action_phrase(resolved)
        rival_name = str(rival.get("name", "rival")).strip() or "rival"
        title = self._collapse_repeated_rival_followup_labels(resolved.get("title", "Opportunity")) or "Opportunity"
        risk = str(resolved.get("risk", "low")).strip().lower() or "low"

        if casualty == "dead":
            followup_title = f"Last Trace: {rival_name}"
            summary = (
                f"{rival_name} may have died working {title}. Loose gear, chatter, or a last opening "
                f"could still be in play if you {action_phrase} fast."
            )
        elif resolution == "burned":
            followup_title = f"Burned Trail: {title}"
            summary = (
                f"{rival_name} scorched {title}. The blowback may still pay if you {action_phrase} "
                "before the scene settles."
            )
        else:
            followup_title = f"Rival Aftermath: {title}"
            summary = (
                f"{rival_name} got to {title} first. Their wake may still hold rattled contacts, "
                f"loose margin, or a fresh read if you {action_phrase} before it cools."
            )

        if casualty == "dead":
            risk_label = "exposed" if risk == "low" else risk
        elif resolution == "burned":
            risk_label = "hazardous" if risk == "hazardous" else "exposed"
        else:
            risk_label = risk

        playstyles = self._rival_followup_playstyles(rival, resolved)

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
                "requirements": followup_requirements,
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

    def _emit_rival_activity(self, rival, *, entry=None, summary="", confidence=0.5, truthful=True, source="street_rumor"):
        chunk = self._normalize_chunk((entry or {}).get("chunk"), fallback=rival.get("current_chunk"))
        player_distance = self._chunk_distance(self._player_chunk_coord(), chunk)
        known_to_player = False
        prop = self._opportunity_property(entry) if isinstance(entry, dict) else None
        if isinstance(entry, dict):
            if truthful:
                intel = self._reveal_rival_target_to_player(entry, confidence=confidence, source=source)
            else:
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
            opportunity_id=int((entry or {}).get("id", 0) or 0),
            title=str((entry or {}).get("title", "Opportunity")).strip() or "Opportunity",
            property_id=str((prop or {}).get("id", "")).strip(),
            property_name=str((prop or {}).get("name", "")).strip(),
            building_id=_building_id_from_property(prop) if isinstance(prop, dict) else "",
            summary=str(summary).strip(),
            truthful=bool(truthful),
        ))

    def _maybe_emit_rival_rumor(self, rival):
        target = self._target_entry(rival)
        if not isinstance(target, dict):
            return
        current_tick = int(self.sim.tick)
        if self._scene_hold_active(rival, target):
            if current_tick - int(rival.get("last_rumor_tick", -10_000)) < self._scene_rumor_interval():
                return
            target_chunk = self._normalize_chunk(target.get("chunk"), fallback=rival.get("current_chunk"))
            distance_text = opportunity_distance_text(
                self._chunk_distance(self._player_chunk_coord(), target_chunk),
                self._step_direction(self._player_chunk_coord(), target_chunk),
            )
            self._emit_rival_activity(
                rival,
                entry=target,
                summary=f"{rival.get('name', 'Someone')} is said to be {self._spotted_summary(rival, target)} {distance_text}",
                confidence=0.72,
                truthful=True,
                source="rival_scene",
            )
            rival["last_rumor_tick"] = current_tick
            return
        if current_tick - int(rival.get("last_rumor_tick", -10_000)) < self.RUMOR_INTERVAL:
            return
        if self._materialized_eid(rival) and self._player_can_notice_rival(rival):
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
        summary = f"{rival.get('name', 'Someone')} is said to be {self._spotted_summary(rival, reported)} {distance_text}"
        confidence = 0.42 + (float(rival.get("honesty", 0.5)) * 0.18) + (float(rival.get("charm", 0.5)) * 0.08)
        if not truthful:
            confidence -= 0.12
        self._emit_rival_activity(
            rival,
            entry=reported,
            summary=summary,
            confidence=max(0.32, min(0.82, confidence)),
            truthful=truthful,
            source="street_rumor",
        )
        rival["last_rumor_tick"] = current_tick

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
            self._clear_scene_hold(rival)
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
                summary=f"{rival.get('name', 'Someone')} looks to be {self._spotted_summary(rival, entry)}",
                confidence=0.54 + (float(rival.get("honesty", 0.5)) * 0.1),
                truthful=True,
                source="rival_casing",
            )
            self._clear_scene_hold(rival, opportunity_id=int(entry.get("id", 0) or 0))
            rival["last_action_tick"] = int(self.sim.tick)
            return

        known_before = bool(opportunity_intel_for_observer(self.sim, self.player_eid, int(entry.get("id", 0) or 0)))
        reward = dict(entry.get("reward", {}))
        entry_kind = str(entry.get("kind", "")).strip().lower()
        is_followup = self._is_rival_followup_entry(entry)
        if resolution == "claimed":
            self._apply_rival_reward(rival, reward)
            self._mirror_reward_to_materialized_inventory(rival, reward)
            rival["heat"] = int(_clamp(int(rival.get("heat", 0) or 0) + max(2, int(reward.get("standing", 0) or 0)), 0, 100))
            if entry_kind == "contract_kill" or is_followup:
                rival_name = str(rival.get("name", "a rival")).strip() or "a rival"
                reason = f"claimed by {rival_name} ({rival.get('hustle', 'cash')})"
                status = "completed"
            else:
                reason = self._rival_resolution_reason(rival, entry, resolution=resolution)
                status = "rival_claimed"
        else:
            rival["heat"] = int(_clamp(int(rival.get("heat", 0) or 0) + 5, 0, 100))
            reason = self._rival_resolution_reason(rival, entry, resolution=resolution)
            status = "rival_burned"

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
            self._clear_scene_hold(rival, opportunity_id=int(entry.get("id", 0) or 0))
            rival["target_opportunity_id"] = 0
            return

        rival["resolved_count"] = int(rival.get("resolved_count", 0) or 0) + 1
        rival["last_action_tick"] = int(self.sim.tick)
        self._clear_scene_hold(rival, opportunity_id=int(entry.get("id", 0) or 0))
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
        self._clear_scene_hold(rival)
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
        self._clear_scene_hold(rival)
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

            target = self._target_entry(rival)
            if not isinstance(target, dict):
                continue
            target_chunk = self._normalize_chunk(target.get("chunk"), fallback=rival.get("current_chunk"))
            current_chunk = self._normalize_chunk(rival.get("current_chunk"), fallback=target_chunk)
            if current_chunk != target_chunk:
                self._maybe_emit_rival_rumor(rival)
                continue
            action_interval = self.LOCAL_ACTION_INTERVAL if self._materialized_eid(rival) else self.ACTION_INTERVAL
            if tick - int(rival.get("last_action_tick", -10_000)) < int(action_interval):
                self._maybe_emit_rival_rumor(rival)
                continue
            if current_chunk == self._player_chunk_coord() and self._materialized_eid(rival):
                if not self._local_resolution_ready(rival, target):
                    self._maybe_emit_rival_rumor(rival)
                    continue
            if self._scene_hold_active(rival, target):
                self._maybe_emit_rival_rumor(rival)
                continue
            if self._begin_scene_hold(rival, target):
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
        from game.custom_content import custom_content_allows_post_game_traces, custom_content_post_game_block_lines

        post_game_eligible = custom_content_allows_post_game_traces(self.sim)
        bones_record = None
        if post_game_eligible:
            bones_record = archive_failed_run_bones(
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
        run_end["bones_archived"] = bool(isinstance(bones_record, dict))
        run_end["bones_record_id"] = str((bones_record or {}).get("record_id", "")).strip() if isinstance(bones_record, dict) else ""
        run_end["post_game_content_eligible"] = bool(post_game_eligible)
        run_end["post_game_content_block_lines"] = custom_content_post_game_block_lines(self.sim) if not post_game_eligible else []
        run_end["saved"] = False

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
        _remember_property_lead_for_actor(
            self.sim,
            self.player_eid,
            prop,
            confidence=1.0,
            anchored=True,
            anchor_kind="final_operation",
            hidden=False,
        )

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
