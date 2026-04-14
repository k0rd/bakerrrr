import random

from engine.events import Event
from engine.systems import System
from game.components import Inventory, NPCNeeds, PlayerAssets, Position, StatusEffects, VehicleState, Vitality
from game.items import ITEM_CATALOG, item_display_name
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_keys import can_receive_property_key, ensure_actor_has_property_key, ensure_property_lock
from game.property_runtime import (
    property_is_vehicle as _property_is_vehicle,
    property_metadata as _property_metadata,
    site_services_for_property as _site_services_for_property,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
    vehicle_profile_from_property as _vehicle_profile_from_property,
)
from game.service_runtime import (
    CASINO_GAME_SERVICE_IDS,
    CASINO_PLINKO_LANE_COUNT,
    _casino_apply_round_result,
    _casino_game_profile,
    _casino_plinko_resolve,
    _casino_round_seed,
    _casino_slots_resolve,
    _clamp,
    _int_or_default,
    _manhattan,
    _overworld_discovery_profile,
    _overworld_discovery_summary_bits,
    _overworld_legend_line,
    _overworld_travel_profile,
    _overworld_travel_summary_bits,
    _site_service_roll_index,
    _site_service_state,
    _vehicle_sale_lookup_offer,
    _vehicle_sale_quality,
    _vehicle_sale_remove_offer,
)
from game.skills import intel_skill_terms as _intel_skill_terms, mobility_service_skill_terms as _mobility_service_skill_terms
from game.vehicles import vehicle_metadata


def _property_power_is_cut(sim, prop):
    """Return True when the property's electrical supply is currently cut."""
    if not isinstance(prop, dict):
        return False
    power_cuts = getattr(sim, "fixture_power_cuts", {})
    if not power_cuts:
        return False
    tick = int(getattr(sim, "tick", 0))
    prop_id = str(prop.get("id", "")).strip()
    if prop_id and power_cuts.get(prop_id, 0) > tick:
        return True
    # Also check all properties that cover this prop's position.
    cover_index = getattr(sim, "property_cover_index", {})
    px = int(prop.get("x", 0))
    py = int(prop.get("y", 0))
    pz = int(prop.get("z", 0))
    for pid in cover_index.get((px, py, pz), ()):
        if power_cuts.get(pid, 0) > tick:
            return True
    return False


def _fixture_is_electronic(prop):
    """Return True when this property is an electronic fixture."""
    metadata = prop.get("metadata") or {} if isinstance(prop, dict) else {}
    fixture_kind = str(metadata.get("fixture_kind", "") or "").strip().lower()
    return fixture_kind in {"electronic", "electrical", "camera", "alarm"}


def _build_vending_item_pool():
    pool = []
    for item_id, item_def in ITEM_CATALOG.items():
        if not isinstance(item_def, dict):
            continue
        tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
        if "consumable" not in tags:
            continue
        if str(item_def.get("legal_status", "legal")).strip().lower() != "legal":
            continue
        if "medical" in tags:
            continue
        if not tags.intersection({"food", "drink", "social", "energy"}):
            continue
        pool.append(str(item_id).strip().lower())
    return tuple(sorted(set(pool)))


VENDING_ITEM_POOL = _build_vending_item_pool()


class SiteServiceSystem(System):

    SHELTER_COOLDOWN_TICKS = 180
    INTEL_COOLDOWN_TICKS = 45
    INTEL_RADIUS = 2
    FUEL_UNIT_PRICE = 3
    REPAIR_POINT_PRICE = 18
    VENDING_BASE_COST = 6
    REST_COST = 25
    REST_COOLDOWN_TICKS = 1800
    REST_WELL_RESTED_TICKS = 900
    FETCH_BASE_COST = 15
    FETCH_DISTANCE_MULT = 4
    FETCH_EMPTY_SURCHARGE = 20
    FETCH_DELIVERY_TICKS = 600

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        if not hasattr(self.sim, "site_service_state"):
            self.sim.site_service_state = {
                "cooldowns": {},
            }
        if not hasattr(self.sim, "pending_vehicle_deliveries"):
            self.sim.pending_vehicle_deliveries = []
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("site_service_request", self.on_site_service_request)

    def _state(self):
        return _site_service_state(self.sim)

    def _cooldown_key(self, eid, prop, service):
        return (int(eid), str(prop.get("id")), str(service).strip().lower())

    def _service_ready_in(self, eid, prop, service):
        cooldowns = self._state()["cooldowns"]
        ready_tick = int(cooldowns.get(self._cooldown_key(eid, prop, service), 0))
        return max(0, ready_tick - int(self.sim.tick))

    def _set_service_cooldown(self, eid, prop, service, duration):
        cooldowns = self._state()["cooldowns"]
        cooldowns[self._cooldown_key(eid, prop, service)] = int(self.sim.tick) + max(1, int(duration))

    def _next_service_roll_index(self, eid, prop, service):
        return _site_service_roll_index(self.sim, eid, prop, service)

    def _position_for(self, eid):
        return self.sim.ecs.get(Position).get(eid)

    def _assets_for(self, eid):
        return self.sim.ecs.get(PlayerAssets).get(eid)

    def _inventory_for(self, eid):
        return self.sim.ecs.get(Inventory).get(eid)

    def _vehicle_state_for(self, eid):
        return self.sim.ecs.get(VehicleState).get(eid)

    def _choose_vending_item(self, eid, prop):
        if not VENDING_ITEM_POOL:
            return None
        roll_index = self._next_service_roll_index(eid, prop, "vending")
        seed_token = (
            f"vending:{int(getattr(self.sim, 'seed', 0) or 0)}:{int(eid)}:"
            f"{str(prop.get('id', 'fixture')).strip()}:{int(roll_index)}"
        )
        rng = random.Random(seed_token)
        item_id = VENDING_ITEM_POOL[rng.randrange(len(VENDING_ITEM_POOL))]
        return ITEM_CATALOG.get(item_id)

    def _vending_price_for(self, item_def):
        tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
        price = int(self.VENDING_BASE_COST)
        if "food" in tags:
            price += 2
        if "drink" in tags:
            price += 1
        if "social" in tags:
            price += 1
        if "energy" in tags:
            price += 1
        return max(4, int(price))

    def _active_vehicle_property(self, eid, pos=None, radius=2):
        state = self._vehicle_state_for(eid)
        if state and state.active_vehicle_id:
            prop = self.sim.properties.get(state.active_vehicle_id)
            if _property_is_vehicle(prop):
                return prop

        if pos is None:
            return None

        best = None
        best_dist = 999999
        for prop in self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=radius):
            if not _property_is_vehicle(prop):
                continue
            if prop.get("owner_eid") != eid and str(prop.get("owner_tag", "")).strip().lower() != "player":
                continue
            dist = _manhattan(pos.x, pos.y, int(prop.get("x", 0)), int(prop.get("y", 0)))
            if dist < best_dist:
                best = prop
                best_dist = dist
        if best and state:
            state.set_active_vehicle(best.get("id"), tick=self.sim.tick)
        return best

    def _vehicle_spawn_tile_near(self, x, y, z=0, radius=6):
        x = int(x)
        y = int(y)
        z = int(z)
        if self.sim.tilemap.is_walkable(x, y, z) and not self.sim.property_at(x, y, z):
            return x, y

        for r in range(1, max(1, int(radius)) + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    nx = x + dx
                    ny = y + dy
                    if self.sim.detail_for_xy(nx, ny) == "unloaded":
                        continue
                    if self.sim.structure_at(nx, ny, z):
                        continue
                    if self.sim.property_at(nx, ny, z):
                        continue
                    if self.sim.tilemap.is_walkable(nx, ny, z):
                        return nx, ny
        return None

    def _apply_fuel_service(self, eid, prop, pos):
        vehicle_prop = self._active_vehicle_property(eid, pos=pos, radius=2)
        if not vehicle_prop:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="fuel",
                reason="no_vehicle",
            ))
            return

        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        missing = max(0, fuel_capacity - fuel)
        if missing <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="fuel",
                reason="tank_full",
                vehicle_name=_vehicle_label(vehicle_prop),
                fuel=int(fuel),
                fuel_capacity=int(fuel_capacity),
            ))
            return

        profile = _vehicle_profile_from_property(vehicle_prop)
        fuel_efficiency = max(1, min(10, _int_or_default(profile.get("fuel_efficiency"), 5)))
        base_unit_price = max(1, int(round(float(self.FUEL_UNIT_PRICE) - (float(fuel_efficiency) * 0.12))))
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        unit_price = max(1, int(round(float(base_unit_price) * float(skill_terms.get("price_mult", 1.0)))))
        skill_note = str(skill_terms.get("note", "") or "").strip() if unit_price < base_unit_price else ""
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        affordable = min(missing, credits // unit_price if unit_price > 0 else 0)
        if affordable <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="fuel",
                reason="no_credits",
                cost=unit_price,
                credits=credits,
                vehicle_name=_vehicle_label(vehicle_prop),
                fuel=int(fuel),
                fuel_capacity=int(fuel_capacity),
            ))
            return

        credits_spent = int(affordable * unit_price)
        if assets:
            assets.credits = max(0, int(assets.credits) - credits_spent)

        metadata = _property_metadata(vehicle_prop)
        metadata["fuel"] = int(fuel + affordable)
        new_fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="fuel",
            fuel_gain=int(affordable),
            base_unit_price=int(base_unit_price),
            unit_price=int(unit_price),
            base_credits_spent=int(affordable * base_unit_price),
            credits_spent=int(credits_spent),
            fuel=int(new_fuel),
            fuel_capacity=int(fuel_capacity),
            vehicle_id=vehicle_prop.get("id"),
            vehicle_name=_vehicle_label(vehicle_prop),
            skill_note=skill_note,
        ))

    def _apply_repair_service(self, eid, prop, pos):
        vehicle_prop = self._active_vehicle_property(eid, pos=pos, radius=2)
        if not vehicle_prop:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="repair",
                reason="no_vehicle",
            ))
            return

        profile = _vehicle_profile_from_property(vehicle_prop)
        durability = max(1, min(10, _int_or_default(profile.get("durability"), 5)))
        max_durability = 10
        missing = max(0, max_durability - durability)
        if missing <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="repair",
                reason="fully_repaired",
                vehicle_name=_vehicle_label(vehicle_prop),
                durability=int(durability),
                durability_max=int(max_durability),
            ))
            return

        power = max(1, min(10, _int_or_default(profile.get("power"), 5)))
        base_unit_price = max(8, int(self.REPAIR_POINT_PRICE) + max(0, int(power) - 4))
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        unit_price = max(1, int(round(float(base_unit_price) * float(skill_terms.get("price_mult", 1.0)))))
        skill_note = str(skill_terms.get("note", "") or "").strip() if unit_price < base_unit_price else ""
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        affordable = min(missing, credits // unit_price if unit_price > 0 else 0)
        if affordable <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="repair",
                reason="no_credits",
                cost=unit_price,
                credits=credits,
                vehicle_name=_vehicle_label(vehicle_prop),
                durability=int(durability),
                durability_max=int(max_durability),
            ))
            return

        credits_spent = int(affordable * unit_price)
        if assets:
            assets.credits = max(0, int(assets.credits) - credits_spent)

        metadata = _property_metadata(vehicle_prop)
        metadata["durability"] = int(min(max_durability, durability + affordable))
        metadata["vehicle_usable"] = True
        new_durability = max(1, min(max_durability, _int_or_default(metadata.get("durability"), durability)))
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="repair",
            durability_gain=int(affordable),
            durability_before=int(durability),
            durability=int(new_durability),
            durability_max=int(max_durability),
            base_unit_price=int(base_unit_price),
            unit_price=int(unit_price),
            base_credits_spent=int(affordable * base_unit_price),
            credits_spent=int(credits_spent),
            vehicle_id=vehicle_prop.get("id"),
            vehicle_name=_vehicle_label(vehicle_prop),
            skill_note=skill_note,
        ))

    def _apply_vending_service(self, eid, prop):
        item_def = self._choose_vending_item(eid, prop)
        if not isinstance(item_def, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="unavailable",
            ))
            return

        item_id = str(item_def.get("id", "")).strip().lower()
        item_name = item_display_name(item_id, item_catalog=ITEM_CATALOG)
        price = self._vending_price_for(item_def)
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < price:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="no_credits",
                cost=int(price),
                credits=int(credits),
                item_id=item_id,
                item_name=item_name,
            ))
            return

        inventory = self._inventory_for(eid)
        if inventory is None:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="inventory_full",
                item_id=item_id,
                item_name=item_name,
            ))
            return

        added, instance_id = inventory.add_item(
            item_id,
            quantity=1,
            stack_max=max(1, int(item_def.get("stack_max", 1))),
            owner_eid=eid,
            owner_tag="player",
        )
        if not added:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="inventory_full",
                item_id=item_id,
                item_name=item_name,
            ))
            return

        if assets:
            assets.credits = max(0, int(assets.credits) - int(price))

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="vending",
            item_id=item_id,
            item_name=item_name,
            instance_id=str(instance_id or "").strip(),
            credits_spent=int(price),
        ))

    def _apply_vehicle_sale(self, eid, prop, pos, quality, request=None):
        quality = _vehicle_sale_quality(quality)
        request = dict(request or {}) if isinstance(request, dict) else {}
        requested_offering_id = str(request.get("offering_id", "") or "").strip().lower()
        selected_offer = _vehicle_sale_lookup_offer(
            self.sim,
            prop,
            quality,
            offering_id=requested_offering_id,
        )
        if (
            not isinstance(selected_offer, dict)
            or (
                requested_offering_id
                and str(selected_offer.get("offering_id", "")).strip().lower() != requested_offering_id
            )
        ):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="unavailable",
            ))
            return

        base_price = int(max(80, _int_or_default(selected_offer.get("price"), 500)))
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        price = int(max(80, round(float(base_price) * float(skill_terms.get("price_mult", 1.0)))))
        skill_note = str(skill_terms.get("note", "") or "").strip() if price < base_price else ""

        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < price:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="no_credits",
                cost=price,
                credits=credits,
            ))
            return

        spawn_tile = self._vehicle_spawn_tile_near(pos.x, pos.y, z=pos.z, radius=6)
        if not spawn_tile:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="no_space",
            ))
            return

        sx, sy = spawn_tile
        chunk_coord = self.sim.chunk_coords(sx, sy)
        vehicle_name = str(selected_offer.get("vehicle_name", "Vehicle")).strip() or "Vehicle"
        vehicle_token = (
            f"veh:purchase:{chunk_coord[0]}:{chunk_coord[1]}:{self.sim.tick}:{quality}:"
            f"{str(selected_offer.get('offering_id', 'offer')).strip() or 'offer'}"
        )
        profile = {
            "quality": quality,
            "paint": str(selected_offer.get("paint", "")).strip(),
            "make": str(selected_offer.get("make", "Unknown")).strip() or "Unknown",
            "model": str(selected_offer.get("model", "Vehicle")).strip() or "Vehicle",
            "vehicle_class": str(selected_offer.get("vehicle_class", "sedan")).strip().lower() or "sedan",
            "power": max(1, min(10, _int_or_default(selected_offer.get("power"), 5))),
            "durability": max(1, min(10, _int_or_default(selected_offer.get("durability"), 5))),
            "fuel_efficiency": max(1, min(10, _int_or_default(selected_offer.get("fuel_efficiency"), 5))),
            "fuel_capacity": max(10, _int_or_default(selected_offer.get("fuel_capacity"), 60)),
            "fuel": max(0, _int_or_default(selected_offer.get("fuel"), _int_or_default(selected_offer.get("fuel_capacity"), 60))),
            "price": price,
            "glyph": str(selected_offer.get("glyph", "&"))[:1] or "&",
        }
        metadata = vehicle_metadata(
            profile,
            chunk=chunk_coord,
            owner_tag="player",
            display_color=str(selected_offer.get("display_color", "")).strip() or "vehicle_player",
            locked=True,
            key_id=vehicle_token,
            key_label=vehicle_name,
            lock_tier=3 if quality == "new" else 2,
        )
        metadata["vehicle_id"] = vehicle_token
        preview_prop = {
            "id": vehicle_token,
            "name": vehicle_name,
            "kind": "vehicle",
            "metadata": metadata,
        }
        if not can_receive_property_key(self.sim, eid, preview_prop):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="key_storage_full",
            ))
            return
        vehicle_id = self.sim.register_property(
            name=vehicle_name,
            kind="vehicle",
            x=int(sx),
            y=int(sy),
            z=int(pos.z),
            owner_eid=eid,
            owner_tag="player",
            metadata=metadata,
        )
        self.sim.chunk_property_records.setdefault(chunk_coord, []).append({
            "id": vehicle_id,
            "kind": "vehicle",
            "x": int(sx),
            "y": int(sy),
            "z": int(pos.z),
            "archetype": "vehicle",
            "building_id": None,
        })
        vehicle_prop = self.sim.properties.get(vehicle_id)
        key_ok, _instance_id, _created = ensure_actor_has_property_key(self.sim, eid, vehicle_prop, owner_tag="player")
        if not key_ok and vehicle_prop:
            ensure_property_lock(vehicle_prop, locked=False)

        if assets:
            assets.credits = max(0, int(assets.credits) - int(price))
        _vehicle_sale_remove_offer(self.sim, prop, quality, selected_offer.get("offering_id"))
        vehicle_state = self._vehicle_state_for(eid)
        if vehicle_state and not vehicle_state.active_vehicle_id:
            vehicle_state.set_active_vehicle(vehicle_id, tick=self.sim.tick)

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service=f"vehicle_sales_{quality}",
            vehicle_id=vehicle_id,
            vehicle_name=vehicle_name,
            base_price=int(base_price),
            price=int(price),
            quality=quality,
            offering_id=str(selected_offer.get("offering_id", "")).strip(),
            vehicle_class=str(profile.get("vehicle_class", "sedan")).strip().lower() or "sedan",
            power=int(profile.get("power", 5)),
            durability=int(profile.get("durability", 5)),
            fuel_efficiency=int(profile.get("fuel_efficiency", 5)),
            fuel=int(profile.get("fuel", 0)),
            fuel_capacity=int(profile.get("fuel_capacity", 0)),
            key_issued=bool(key_ok),
            skill_note=skill_note,
        ))

    def _chunk_direction(self, from_chunk, to_chunk):
        dx = int(to_chunk[0]) - int(from_chunk[0])
        dy = int(to_chunk[1]) - int(from_chunk[1])
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

    def _choose_site_service(self, eid, prop):
        services = list(_site_services_for_property(prop))
        if not services:
            return None

        pos = self._position_for(eid)
        vehicle_prop = self._active_vehicle_property(eid, pos=pos, radius=2) if pos else None
        if "fuel" in services and vehicle_prop:
            fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
            if fuel < max(4, int(round(float(fuel_capacity) * 0.92))):
                return "fuel"
        if "repair" in services and vehicle_prop:
            durability = max(1, min(10, _int_or_default(_vehicle_profile_from_property(vehicle_prop).get("durability"), 5)))
            if durability < 9:
                return "repair"

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        wants_shelter = False
        if needs:
            wants_shelter = (
                float(needs.energy) < 82.0
                or float(needs.safety) < 78.0
                or float(needs.social) < 52.0
            )
        if vitality and int(vitality.hp) < int(vitality.max_hp):
            wants_shelter = True

        if "vehicle_sales_new" in services:
            return "vehicle_sales_new"
        if "vehicle_sales_used" in services:
            return "vehicle_sales_used"
        if "rest" in services and wants_shelter:
            return "rest"
        if "shelter" in services and wants_shelter:
            return "shelter"
        if "vehicle_fetch" in services:
            return "vehicle_fetch"
        if "intel" in services:
            return "intel"
        if "fuel" in services and vehicle_prop:
            return "fuel"
        return services[0]

    def _apply_casino_game(self, eid, prop, service, request=None):
        service = str(service or "").strip().lower()
        profile = _casino_game_profile(service)
        if not profile:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="unavailable",
            ))
            return

        raw_wager = 0 if not isinstance(request, dict) else request.get("wager", 0)
        try:
            wager = int(raw_wager)
        except (TypeError, ValueError):
            wager = 0
        valid_wagers = {int(amount) for amount in profile.get("bet_options", ())}
        if wager <= 0 or (valid_wagers and wager not in valid_wagers):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="invalid_wager",
                wager=wager,
            ))
            return
        round_result = dict(request.get("round_result", {}) or {}) if isinstance(request, dict) else {}
        if not round_result:
            roll_index = self._next_service_roll_index(eid, prop, service)
            seed_token = _casino_round_seed(self.sim, eid, prop, service, wager, roll_index)
            if service == "slots":
                round_result = _casino_slots_resolve(seed_token, wager)
            elif service == "plinko":
                drop_lane = CASINO_PLINKO_LANE_COUNT // 2
                if isinstance(request, dict):
                    try:
                        drop_lane = int(request.get("drop_lane", drop_lane))
                    except (TypeError, ValueError):
                        drop_lane = CASINO_PLINKO_LANE_COUNT // 2
                round_result = _casino_plinko_resolve(seed_token, wager, drop_lane)
            else:
                self.sim.emit(Event(
                    "site_service_blocked",
                    eid=eid,
                    property_id=prop["id"],
                    property_name=prop.get("name", prop["id"]),
                    service=service,
                    reason="invalid_round",
                ))
                return

        payload, blocked = _casino_apply_round_result(self.sim, eid, prop, service, round_result)
        if blocked:
            self.sim.emit(Event("site_service_blocked", **blocked))
            return
        self.sim.emit(Event("site_service_used", **payload))

    def _run_site_service(self, eid, prop, pos, service, request=None):
        service = str(service or "").strip().lower()
        # Electronic fixtures are offline when their power supply is cut.
        if _fixture_is_electronic(prop) and _property_power_is_cut(self.sim, prop):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="power_cut",
            ))
            from game.systems import _log_player_feedback
            _log_player_feedback(
                self.sim,
                f"The {prop.get('name', 'terminal')} is offline — power is out.",
                kind="interaction",
            )
            return True
        if service == "shelter":
            self._apply_shelter(eid, prop)
            return True
        if service == "rest":
            self._apply_rest(eid, prop)
            return True
        if service == "intel":
            self._emit_intel(eid, prop, pos)
            return True
        if service in CASINO_GAME_SERVICE_IDS:
            self._apply_casino_game(eid, prop, service, request=request)
            return True
        if service == "vending":
            self._apply_vending_service(eid, prop)
            return True
        if service == "fuel":
            self._apply_fuel_service(eid, prop, pos)
            return True
        if service == "repair":
            self._apply_repair_service(eid, prop, pos)
            return True
        if service == "vehicle_sales_new":
            self._apply_vehicle_sale(eid, prop, pos, quality="new", request=request)
            return True
        if service == "vehicle_sales_used":
            self._apply_vehicle_sale(eid, prop, pos, quality="used", request=request)
            return True
        if service == "vehicle_fetch":
            self._apply_vehicle_fetch(eid, prop, pos)
            return True
        return False

    def _apply_shelter(self, eid, prop):
        ready_in = self._service_ready_in(eid, prop, "shelter")
        if ready_in > 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="shelter",
                reason="cooldown",
                ready_in=ready_in,
            ))
            return

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        energy_gain = safety_gain = social_gain = hp_gain = 0

        if needs:
            if float(needs.energy) < 95.0:
                energy_gain = min(18, max(4, int(round((100.0 - float(needs.energy)) * 0.32))))
                needs.energy = _clamp(float(needs.energy) + energy_gain)
            if float(needs.safety) < 92.0:
                safety_gain = min(14, max(3, int(round((100.0 - float(needs.safety)) * 0.24))))
                needs.safety = _clamp(float(needs.safety) + safety_gain)
            if float(needs.social) < 70.0:
                social_gain = min(8, max(2, int(round((72.0 - float(needs.social)) * 0.18))))
                needs.social = _clamp(float(needs.social) + social_gain)

        if vitality and int(vitality.hp) < int(vitality.max_hp):
            hp_gain = min(2, int(vitality.max_hp) - int(vitality.hp))
            vitality.hp = min(int(vitality.max_hp), int(vitality.hp) + hp_gain)

        if energy_gain <= 0 and safety_gain <= 0 and social_gain <= 0 and hp_gain <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="shelter",
                reason="no_need",
            ))
            return

        self._set_service_cooldown(eid, prop, "shelter", self.SHELTER_COOLDOWN_TICKS)
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="shelter",
            energy_gain=energy_gain,
            safety_gain=safety_gain,
            social_gain=social_gain,
            hp_gain=hp_gain,
            cooldown_ticks=self.SHELTER_COOLDOWN_TICKS,
        ))

    def _apply_rest(self, eid, prop):
        ready_in = self._service_ready_in(eid, prop, "rest")
        if ready_in > 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="rest",
                reason="cooldown",
                ready_in=ready_in,
            ))
            return

        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < self.REST_COST:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="rest",
                reason="no_credits",
                cost=self.REST_COST,
                credits=credits,
            ))
            return

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        energy_gain = safety_gain = social_gain = hp_gain = 0

        if needs:
            energy_gain = min(40, max(10, int(round((100.0 - float(needs.energy)) * 0.7))))
            needs.energy = _clamp(float(needs.energy) + energy_gain)
            safety_gain = min(30, max(8, int(round((100.0 - float(needs.safety)) * 0.55))))
            needs.safety = _clamp(float(needs.safety) + safety_gain)
            social_gain = min(12, max(3, int(round((75.0 - float(needs.social)) * 0.25))))
            needs.social = _clamp(float(needs.social) + social_gain)

        if vitality:
            missing_hp = max(0, int(vitality.max_hp) - int(vitality.hp))
            hp_gain = min(missing_hp, max(5, int(round(missing_hp * 0.6))))
            vitality.hp = min(int(vitality.max_hp), int(vitality.hp) + hp_gain)

        effects = self.sim.ecs.get(StatusEffects).get(eid)
        if effects:
            effects.add(
                "well_rested",
                self.REST_WELL_RESTED_TICKS,
                modifiers={
                    "perception_buff": 0.8,
                    "athletics_buff": 0.5,
                    "energy_tick_delta": 0.01,
                },
            )

        if assets:
            assets.credits = max(0, int(assets.credits) - int(self.REST_COST))

        self._set_service_cooldown(eid, prop, "rest", self.REST_COOLDOWN_TICKS)
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="rest",
            energy_gain=energy_gain,
            safety_gain=safety_gain,
            social_gain=social_gain,
            hp_gain=hp_gain,
            credits_spent=self.REST_COST,
            well_rested_ticks=self.REST_WELL_RESTED_TICKS,
            cooldown_ticks=self.REST_COOLDOWN_TICKS,
        ))

    def _player_vehicle_properties(self, eid):
        assets = self._assets_for(eid)
        if not assets:
            return []
        vehicles = []
        for pid in assets.owned_property_ids:
            prop = self.sim.properties.get(pid)
            if prop and _property_is_vehicle(prop):
                vehicles.append(prop)
        return vehicles

    def _apply_vehicle_fetch(self, eid, prop, pos):
        vehicles = self._player_vehicle_properties(eid)
        if not vehicles:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vehicle_fetch",
                reason="no_vehicle",
            ))
            return

        player_chunk = self.sim.chunk_coords(pos.x, pos.y)
        best = None
        best_dist = -1
        for vp in vehicles:
            vx = int(vp.get("x", 0))
            vy = int(vp.get("y", 0))
            vc = self.sim.chunk_coords(vx, vy)
            dist = abs(vc[0] - player_chunk[0]) + abs(vc[1] - player_chunk[1])
            if dist > best_dist:
                best = vp
                best_dist = dist

        if best is None:
            return

        fuel, fuel_capacity = _vehicle_fuel_values(best)
        distance_cost = max(0, best_dist) * self.FETCH_DISTANCE_MULT
        empty_surcharge = self.FETCH_EMPTY_SURCHARGE if fuel <= 0 else 0
        base_total_cost = self.FETCH_BASE_COST + distance_cost + empty_surcharge
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        total_cost = max(1, int(round(float(base_total_cost) * float(skill_terms.get("price_mult", 1.0)))))
        skill_note = str(skill_terms.get("note", "") or "").strip() if total_cost < base_total_cost else ""

        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < total_cost:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vehicle_fetch",
                reason="no_credits",
                cost=total_cost,
                credits=credits,
                vehicle_name=_vehicle_label(best),
            ))
            return

        if assets:
            assets.credits = max(0, int(assets.credits) - int(total_cost))

        delivery_tick = int(self.sim.tick) + self.FETCH_DELIVERY_TICKS
        delivery = {
            "vehicle_id": best.get("id"),
            "vehicle_name": _vehicle_label(best),
            "eid": eid,
            "site_prop_id": prop.get("id"),
            "site_prop_name": prop.get("name", prop["id"]),
            "target_x": int(pos.x),
            "target_y": int(pos.y),
            "target_z": int(pos.z),
            "ready_at_tick": delivery_tick,
        }
        self.sim.pending_vehicle_deliveries.append(delivery)

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="vehicle_fetch",
            vehicle_id=best.get("id"),
            vehicle_name=_vehicle_label(best),
            base_credits_spent=int(base_total_cost),
            credits_spent=total_cost,
            distance=best_dist,
            empty_surcharge=empty_surcharge,
            delivery_ticks=self.FETCH_DELIVERY_TICKS,
            skill_note=skill_note,
        ))

    def update(self):
        deliveries = getattr(self.sim, "pending_vehicle_deliveries", None)
        if not deliveries:
            return
        completed = []
        for idx, delivery in enumerate(deliveries):
            if int(self.sim.tick) < int(delivery.get("ready_at_tick", 0)):
                continue
            vehicle_prop = self.sim.properties.get(delivery.get("vehicle_id"))
            if not vehicle_prop:
                completed.append(idx)
                continue
            tx = int(delivery.get("target_x", 0))
            ty = int(delivery.get("target_y", 0))
            tz = int(delivery.get("target_z", 0))
            spawn = self._vehicle_spawn_tile_near(tx, ty, z=tz, radius=8)
            if not spawn:
                spawn = (tx, ty)
            sx, sy = spawn
            vehicle_prop["x"] = sx
            vehicle_prop["y"] = sy
            vehicle_prop["z"] = tz
            self.sim.property_anchor_index[(sx, sy, tz)] = vehicle_prop.get("id")
            eid = delivery.get("eid")
            vehicle_state = self._vehicle_state_for(eid) if eid else None
            if vehicle_state and not vehicle_state.active_vehicle_id:
                vehicle_state.set_active_vehicle(vehicle_prop.get("id"), tick=self.sim.tick)
            self.sim.emit(Event(
                "vehicle_delivered",
                eid=eid,
                vehicle_id=vehicle_prop.get("id"),
                vehicle_name=delivery.get("vehicle_name", "vehicle"),
                site_prop_name=delivery.get("site_prop_name", "site"),
                x=sx,
                y=sy,
                z=tz,
            ))
            completed.append(idx)
        for idx in reversed(completed):
            deliveries.pop(idx)

    def _intel_lines(self, origin_chunk, *, radius=None, line_limit=4, detail_level=0):
        radius = max(1, int(self.INTEL_RADIUS if radius is None else radius))
        line_limit = max(1, int(line_limit))
        detail_level = max(0, int(detail_level))
        candidates = []
        ox, oy = origin_chunk
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                dist = _manhattan(0, 0, dx, dy)
                if dist > radius:
                    continue

                cx = ox + dx
                cy = oy + dy
                desc = self.sim.world.overworld_descriptor(cx, cy)
                interest = self.sim.world.overworld_interest(cx, cy, descriptor=desc)
                landmark = desc.get("landmark") or {}
                landmark_name = str(landmark.get("name", "")).strip()
                interest_detail = str(interest.get("detail", "")).strip()
                path = str(desc.get("path", "")).strip()

                if not landmark_name and not interest_detail and not path:
                    continue

                area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
                terrain = str(desc.get("terrain", area_type)).replace("_", " ").strip()
                score = int(interest.get("prominence", 0)) * 3
                if landmark_name:
                    score += 4
                if path:
                    score += 1

                bits = [
                    f"{self._chunk_direction(origin_chunk, (cx, cy))} {dist}c",
                    f"{area_type}/{terrain}",
                ]
                if path:
                    bits.append(f"path:{path}")
                if landmark_name:
                    bits.append(f"landmark:{landmark_name}")
                if interest_detail:
                    bits.append(f"poi:{interest_detail}")
                if detail_level >= 1:
                    bits.extend(_overworld_travel_summary_bits(_overworld_travel_profile(self.sim, cx, cy, desc=desc, interest=interest)))
                    bits.extend(_overworld_discovery_summary_bits(_overworld_discovery_profile(self.sim, cx, cy, desc=desc, interest=interest, travel=_overworld_travel_profile(self.sim, cx, cy, desc=desc, interest=interest))))
                if detail_level >= 2:
                    region_name = str(desc.get("region_name", "")).strip()
                    settlement_name = str(desc.get("settlement_name", "")).strip()
                    if region_name:
                        bits.append(f"region:{region_name}")
                    if settlement_name:
                        bits.append(f"city:{settlement_name}")

                text = " ".join(bit for bit in bits if bit)
                candidates.append((
                    -score,
                    dist,
                    cx,
                    cy,
                    _overworld_legend_line(self.sim, cx, cy, text),
                ))

        candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        return [row[4] for row in candidates[:line_limit]]

    def _emit_intel(self, eid, prop, pos):
        ready_in = self._service_ready_in(eid, prop, "intel")
        if ready_in > 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="intel",
                reason="cooldown",
                ready_in=ready_in,
            ))
            return

        origin_chunk = self.sim.chunk_coords(pos.x, pos.y)
        terms = _intel_skill_terms(self.sim, eid)
        radius = int(self.INTEL_RADIUS) + int(terms.get("radius_bonus", 0))
        line_limit = int(terms.get("line_limit", 4))
        detail_level = int(terms.get("detail_level", 0))
        lines = self._intel_lines(
            origin_chunk,
            radius=radius,
            line_limit=line_limit,
            detail_level=detail_level,
        )
        if not lines:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="intel",
                reason="no_leads",
            ))
            return

        self._set_service_cooldown(eid, prop, "intel", self.INTEL_COOLDOWN_TICKS)
        self.sim.emit(Event(
            "site_intel_report",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="intel",
            lines=lines,
            radius=radius,
            display_limit=line_limit,
            detail_level=detail_level,
            skill_note=str(terms.get("note", "") or "").strip(),
        ))

    def on_property_interact(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        if not prop:
            return

        services = _site_services_for_property(prop)
        if not services:
            return

        pos = self._position_for(eid)
        if not pos:
            return

        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        if not access.can_use_services:
            return

        service = self._choose_site_service(eid, prop)
        self._run_site_service(eid, prop, pos, service, request=event.data)

    def on_site_service_request(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        service = str(event.data.get("service", "") or "").strip().lower()
        if not prop or service not in set(_site_services_for_property(prop)):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=event.data.get("property_id"),
                property_name=str(event.data.get("property_name", "site") or "site"),
                service=service,
                reason="unavailable",
            ))
            return

        pos = self._position_for(eid)
        if not pos:
            return

        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        if not access.can_use_services:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="unavailable",
            ))
            return

        self._run_site_service(eid, prop, pos, service, request=event.data)


__all__ = ["SiteServiceSystem"]
