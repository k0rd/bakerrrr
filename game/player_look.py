"""Player-facing local look and scan runtime."""

from engine.events import Event
from engine.visibility import observer_can_see_position as _shared_observer_can_see_position

from game.checks import (
    crime_read_summary as _crime_read_summary,
    rumor_truth_read as _rumor_truth_read,
)
from game.components import (
    AI,
    AnimalGenome,
    CoreStats,
    CreatureIdentity,
    DroneState,
    InsightStats,
    MovementThrottle,
    NPCMemory,
    NPCRoutine,
    Occupation,
    PlayerControlled,
    Position,
    SkillProfile,
    Vitality,
)
from game.drone_runtime import drone_link_disruption_status, drone_state_capabilities
from game.item_semantics import item_display_name_for_actor
from game.items import ITEM_CATALOG
from game.flora_runtime import flora_at, flora_look_text
from game.hunting_runtime import hunting_carcass_look_text, hunting_carcasses_at
from game.appearance_loadout import human_live_look_description_clause
from game.human_identity import is_human_identity
from game.local_situations import local_situation_look_text_for_property
from game.organization_presence import format_actor_org_presence, format_property_org_presence
from game.organizations import organization_name
from game.quick_travel_ramps import map_mode_active
from game.property_runtime import (
    building_id_from_property as _building_id_from_property,
    building_id_from_structure as _building_id_from_structure,
    finance_services_for_property as _finance_services_for_property,
    property_infrastructure_role as _property_infrastructure_role,
    property_metadata as _property_metadata,
    property_covering as _property_covering,
    property_display_position as _property_display_position,
    viewer_revealed_building_id as _viewer_revealed_building_id,
)
from game.service_runtime import _int_or_default, _legend_line
from game.situation_read import build_focus_read
from game.system_support.actor_attention_runtime import record_area_warmth
from game.system_support.altered_state_runtime import (
    hallucinated_entity_label,
    hallucinated_item_label,
    hallucinated_tile_label,
)
from game.system_support.fire_runtime import fire_cell_state
from game.system_support.crime_plan_runtime import (
    CRIME_PLAN_OBSERVATION_SCAN,
    crime_plan_surface_rows,
    record_crime_plan_observation,
)
from game.system_support.entity_naming import (
    _entity_viewer_display_name,
    _viewer_knows_entity_name,
)
from game.system_support.interaction_ordering import _manhattan


def _drone_look_detail_bits(sim, drone_eid, state):
    if state is None:
        return []
    bits = []
    chassis_class = str(getattr(state, "chassis_class", "") or "").strip().upper()
    if chassis_class:
        bits.append(f"class:{chassis_class}")

    vitality = sim.ecs.get(Vitality).get(drone_eid) if getattr(sim, "ecs", None) is not None else None
    hull_hp = int(getattr(vitality, "hp", getattr(state, "hull_hp", 0)) or 0)
    hull_hp_max = int(getattr(vitality, "max_hp", getattr(state, "hull_hp_max", 0)) or 0)
    if hull_hp_max > 0:
        bits.append(f"hull:{hull_hp}/{hull_hp_max}")

    battery_max = int(getattr(state, "battery_charge_max", 0) or 0)
    if battery_max > 0:
        battery = int(getattr(state, "battery_charge", 0) or 0)
        bits.append(f"battery:{battery}/{battery_max}")

    mode = str(getattr(state, "mode", "") or "").strip().lower()
    if mode:
        bits.append(f"mode:{mode}")
    link = drone_link_disruption_status(state, tick=int(getattr(sim, "tick", 0) or 0))
    if link.get("active"):
        bits.append(f"link:disrupted({int(link.get('remaining', 0))})")
    procedure = str(getattr(state, "procedure_key", "") or "").strip().lower()
    if procedure:
        bits.append(f"intent:{procedure}")

    capabilities = tuple(drone_state_capabilities(state, item_catalog=ITEM_CATALOG))
    if capabilities:
        shown = ",".join(capabilities[:6])
        if len(capabilities) > 6:
            shown += f",+{len(capabilities) - 6}"
        bits.append(f"caps:{shown}")

    paint = getattr(state, "paint", {}) if isinstance(getattr(state, "paint", {}), dict) else {}
    primary = str(paint.get("primary_color") or "").strip().lower()
    secondary = str(paint.get("secondary_color") or paint.get("accent_color") or "").strip().lower()
    if primary or secondary:
        bits.append(f"paint:{primary or 'bare'}/{secondary or 'none'}")

    errors = tuple(str(error) for error in (getattr(state, "loadout_errors", ()) or ()) if str(error).strip())
    if errors:
        bits.append(f"loadout:{';'.join(errors[:2])}")
    return bits


class PlayerLookRuntime:
    def __init__(
        self,
        action_system,
        *,
        tile_label,
        property_summary,
        structure_summary,
        building_street_summary,
        property_knowledge_hint,
        property_contact_hint,
        target_condition_descriptor,
        career_label,
        workplace_property,
        entity_legend_line,
        item_legend_line,
        property_legend_line,
        tile_legend_line,
        tile_prefers_feature_legend,
        manual_fire_preview,
        line_with_suffix,
        scan_skill_terms,
        access_prep_skill_terms,
        property_access_controller,
        controller_access_requirement_text,
        property_access_summary,
        site_services_for_property,
        stakeout_property_opportunity_stats,
        security_fixture_is_online,
        access_prep_detail_lines,
        entity_status_move_speed_multiplier,
        world_trait_claim_value,
        world_trait_claim_text,
    ):
        self.action_system = action_system
        self.sim = action_system.sim
        self._tile_label = tile_label
        self._property_summary = property_summary
        self._structure_summary = structure_summary
        self._building_street_summary = building_street_summary
        self._property_knowledge_hint = property_knowledge_hint
        self._property_contact_hint = property_contact_hint
        self._target_condition_descriptor = target_condition_descriptor
        self._career_label = career_label
        self._workplace_property = workplace_property
        self._entity_legend_line = entity_legend_line
        self._item_legend_line = item_legend_line
        self._property_legend_line = property_legend_line
        self._tile_legend_line = tile_legend_line
        self._tile_prefers_feature_legend = tile_prefers_feature_legend
        self._manual_fire_preview = manual_fire_preview
        self._line_with_suffix = line_with_suffix
        self._scan_skill_terms = scan_skill_terms
        self._access_prep_skill_terms = access_prep_skill_terms
        self._property_access_controller = property_access_controller
        self._controller_access_requirement_text = controller_access_requirement_text
        self._property_access_summary = property_access_summary
        self._site_services_for_property = site_services_for_property
        self._stakeout_property_opportunity_stats = stakeout_property_opportunity_stats
        self._security_fixture_is_online = security_fixture_is_online
        self._access_prep_detail_lines = access_prep_detail_lines
        self._entity_status_move_speed_multiplier = entity_status_move_speed_multiplier
        self._world_trait_claim_value = world_trait_claim_value
        self._world_trait_claim_text = world_trait_claim_text

    def set_look_inspect_text(self, text):
        state = getattr(self.sim, "look_ui", None)
        if not isinstance(state, dict):
            state = {}
            self.sim.look_ui = state
        state["inspect_text"] = text

    def observer_has_los_to_position(self, observer_eid, x, y, z):
        observer_pos = self.sim.ecs.get(Position).get(observer_eid)
        if not observer_pos:
            return True
        visibility = getattr(self.sim, "visibility_state", None)
        radius = 8
        if isinstance(visibility, dict):
            radius = max(1, int(_int_or_default(visibility.get("player_radius", 8), 8)))
        return bool(_shared_observer_can_see_position(
            self.sim,
            observer_eid=observer_eid,
            observer_x=observer_pos.x,
            observer_y=observer_pos.y,
            observer_z=observer_pos.z,
            target_x=x,
            target_y=y,
            target_z=z,
            radius=radius,
        ))

    def describe_city_cursor(self, eid, x, y, z):
        x = int(x)
        y = int(y)
        z = int(z)
        if not self.sim.tilemap.in_bounds(x, y):
            return _legend_line(f"({x},{y},{z}) is out of bounds.", glyph="?", color="human")

        detail = self.sim.detail_for_xy(x, y)
        chunk = self.sim.chunk_coords(x, y)
        if detail == "unloaded":
            return _legend_line(
                f"({x},{y},{z}) chunk {chunk} is known only at map level; current street detail is not loaded.",
                glyph="?",
                color="human",
            )

        tile = self.sim.tilemap.tile_at(x, y, z)
        revealed_building_id = _viewer_revealed_building_id(self.sim, eid, z=z)
        if tile:
            walk_text = "walkable" if tile.walkable else "blocked"
            tile_text = self._tile_label(self.sim, tile, x, y, z)
            if tile.walkable and str(tile.glyph)[:1] == ".":
                structure = self.sim.structure_at(x, y, z) if hasattr(self.sim, "structure_at") else None
                building_id = _building_id_from_structure(structure)
                if building_id and building_id != revealed_building_id:
                    tile_text = "building roof"
        else:
            walk_text = "walkable"
            tile_text = "open ground"
        tile_text = hallucinated_tile_label(self.sim, eid, x, y, z, tile_text)

        bits = [f"({x},{y},{z}) {tile_text} {walk_text} chunk:{chunk}"]

        prop = _property_covering(self.sim, x, y, z)
        if prop:
            bits.append("property:" + self._property_summary(self.sim, prop, viewer_eid=eid, x=x, y=y, z=z))
            prop_building_id = _building_id_from_property(prop)
            if str(prop.get("kind", "") or "").strip().lower() == "building":
                if prop_building_id and prop_building_id == revealed_building_id:
                    structure = self.sim.structure_at(x, y, z) if hasattr(self.sim, "structure_at") else None
                    structure_text = self._structure_summary(structure)
                    if structure_text:
                        bits.append("inside:" + structure_text)
                else:
                    street_text = self._building_street_summary(self.sim, prop)
                    if street_text:
                        bits.append("street:" + street_text)
            knowledge_hint = self._property_knowledge_hint(self.sim, eid, prop)
            if knowledge_hint:
                bits.append(knowledge_hint)
            contact_hint = self._property_contact_hint(self.sim, eid, prop)
            if contact_hint:
                bits.append(contact_hint)
            situation_hint = local_situation_look_text_for_property(self.sim, prop, viewer_eid=eid)
            if situation_hint:
                bits.append(situation_hint)
        else:
            structure = self.sim.structure_at(x, y, z) if hasattr(self.sim, "structure_at") else None
            structure_text = self._structure_summary(structure)
            if structure_text:
                bits.append("inside:" + structure_text)

        ground_items = () if map_mode_active(self.sim) else self.sim.ground_items_at(x, y, z=z)
        if ground_items:
            labels = []
            for idx, ground in enumerate(ground_items[:2]):
                item_name = item_display_name_for_actor(
                    self.sim,
                    eid,
                    ground,
                    item_catalog=ITEM_CATALOG,
                )
                item_name = hallucinated_item_label(self.sim, eid, x, y, z, idx, item_name)
                qty = int(max(1, ground.get("quantity", 1)))
                labels.append(f"{item_name}x{qty}")
            remaining = len(ground_items) - len(labels)
            item_text = ", ".join(labels)
            if remaining > 0:
                item_text += f" +{remaining}"
            bits.append(f"items:{item_text}")

        flora_rows = () if map_mode_active(self.sim) else flora_at(self.sim, x, y, z=z)
        if flora_rows:
            flora_text = flora_look_text(flora_rows, sim=self.sim)
            if flora_text:
                bits.append(flora_text)

        carcass_rows = () if map_mode_active(self.sim) else hunting_carcasses_at(self.sim, x, y, z=z)
        if carcass_rows:
            carcass_text = hunting_carcass_look_text(carcass_rows[0])
            if carcass_text:
                bits.append(carcass_text)

        projectiles = [
            projectile
            for projectile in self.sim.projectiles.values()
            if int(projectile.get("x", -999999)) == x
            and int(projectile.get("y", -999999)) == y
            and int(projectile.get("z", 0)) == z
        ]
        if projectiles:
            bits.append(f"projectiles:{len(projectiles)}")

        fire_cell = fire_cell_state(self.sim, x, y, z)
        if isinstance(fire_cell, dict):
            fire_intensity = int(fire_cell.get("fire_intensity", 0) or 0)
            smoke_intensity = int(fire_cell.get("smoke_intensity", 0) or 0)
            hazard_bits = []
            if fire_intensity > 0:
                hazard_bits.append(f"fire:{fire_intensity}")
            if smoke_intensity > 0:
                hazard_bits.append(f"smoke:{smoke_intensity}")
            aerosol_label = str(fire_cell.get("aerosol_label", "") or "").strip()
            if aerosol_label:
                hazard_bits.append("aerosol:" + aerosol_label)
            if hazard_bits:
                bits.append("hazard:" + " ".join(hazard_bits))

        entities = sorted(self.sim.tilemap.entities_at(x, y, z))
        non_player_entities = [target_eid for target_eid in entities if target_eid != eid]
        if entities:
            identities = self.sim.ecs.get(CreatureIdentity)
            labels = []
            for target_eid in entities[:3]:
                if target_eid == eid:
                    labels.append("you")
                    continue
                name = _entity_viewer_display_name(
                    self.sim,
                    target_eid,
                    viewer_eid=eid,
                    title_case=False,
                )
                name = hallucinated_entity_label(self.sim, eid, target_eid, x, y, z, name)
                labels.append(f"{name}#{target_eid}")
            remaining = len(entities) - len(labels)
            entity_text = ", ".join(labels)
            if remaining > 0:
                entity_text += f" +{remaining}"
            bits.append(f"entities:{entity_text}")

            if len(non_player_entities) == 1:
                target_eid = non_player_entities[0]
                identity = identities.get(target_eid)
                drone_state = self.sim.ecs.get(DroneState).get(target_eid)
                if drone_state is not None:
                    detail_bits = _drone_look_detail_bits(self.sim, target_eid, drone_state)
                    if detail_bits:
                        bits.append("drone:" + " ".join(detail_bits))
                else:
                    ai = self.sim.ecs.get(AI).get(target_eid)
                    occupation = self.sim.ecs.get(Occupation).get(target_eid)
                    routine = self.sim.ecs.get(NPCRoutine).get(target_eid)
                    detail_bits = []
                    if ai:
                        role = str(ai.role or "npc").replace("_", " ").strip() or "npc"
                        state = str(ai.state or "idle").replace("_", " ").strip() or "idle"
                        detail_bits.append(f"role:{role} state:{state}")
                        read_text = _crime_read_summary(self.sim, eid, target_eid, mode="look", sentence=False)
                        if read_text:
                            detail_bits.append(f"read:{read_text}")
                    if self.observer_has_los_to_position(eid, x, y, z):
                        condition = self._target_condition_descriptor(
                            self.sim,
                            eid,
                            target_eid,
                            include_uncertainty=True,
                        )
                        if condition:
                            detail_bits.append(f"condition:{condition}")
                        if is_human_identity(identity):
                            appearance = human_live_look_description_clause(
                                self.sim,
                                target_eid,
                                identity=identity,
                                personal_name=(
                                    getattr(identity, "personal_name", "")
                                    if _viewer_knows_entity_name(self.sim, eid, target_eid)
                                    else ""
                                ),
                            )
                            if appearance:
                                detail_bits.append(f"appearance:{appearance}")
                    career_text = self._career_label(occupation)
                    if career_text:
                        detail_bits.append(f"job:{career_text}")
                    workplace_prop = self._workplace_property(self.sim, occupation=occupation, routine=routine)
                    if workplace_prop:
                        detail_bits.append(f"work:{workplace_prop.get('name', workplace_prop.get('id', 'property'))}")
                    workplace = getattr(occupation, "workplace", None)
                    organization_eid = workplace.get("organization_eid") if isinstance(workplace, dict) else None
                    org_name = organization_name(self.sim, organization_eid)
                    if org_name and (not workplace_prop or org_name.lower() != str(workplace_prop.get("name", "")).strip().lower()):
                        detail_bits.append(f"org:{org_name}")
                    org_presence = format_actor_org_presence(self.sim, target_eid, include_primary=False)
                    if org_presence:
                        detail_bits.append(f"orgs:{org_presence}")
                    crew_rows = crime_plan_surface_rows(self.sim, actor_eid=target_eid)
                    if crew_rows:
                        row = crew_rows[0]
                        org = str(row.get("organization_name", "") or "").strip()
                        method = str(row.get("method_label", "") or "").strip()
                        detail_bits.append(f"crew:{row.get('actor_text')}" + (f" {org}/{method}" if org and method else ""))
                    if detail_bits:
                        bits.append("npc:" + " ".join(detail_bits))

        text = "  ".join(bits)

        if non_player_entities:
            return self._entity_legend_line(self.sim, non_player_entities[0], text, player_eid=eid)
        if ground_items:
            return self._item_legend_line(ground_items[0].get("item_id"), text)
        prop_display_pos = _property_display_position(prop) if prop else None
        if (
            prop
            and prop_display_pos
            and int(prop_display_pos[0]) == int(x)
            and int(prop_display_pos[1]) == int(y)
            and int(prop_display_pos[2]) == int(z)
            and not self._tile_prefers_feature_legend(self.sim, tile, x, y, z)
        ):
            return self._property_legend_line(prop, text)
        return self._tile_legend_line(self.sim, x, y, z, text)

    def handle_cursor_examine(self, eid, pos, event, *, announce=False, purpose="inspect"):
        x = int(event.data.get("cursor_x", pos.x))
        y = int(event.data.get("cursor_y", pos.y))
        z = int(event.data.get("cursor_z", pos.z))
        look_state = getattr(self.sim, "look_ui", None)
        if not isinstance(look_state, dict):
            look_state = {}
            self.sim.look_ui = look_state
        look_state["x"] = x
        look_state["y"] = y
        look_state["z"] = z
        if announce and purpose != "aim":
            discovered_prop = self.action_system._discovery_property_at(x, y, z)
            if discovered_prop:
                self.action_system._remember_player_property_discovery(
                    eid,
                    discovered_prop,
                    discovery_mode="sight",
                )
        text = self.describe_city_cursor(eid=eid, x=x, y=y, z=z)
        focus_read = build_focus_read(self.sim, eid, x, y, z, purpose=purpose)
        if purpose == "aim":
            preview = self._manual_fire_preview(self.sim, eid=eid, x=x, y=y, z=z)
            summary = str(preview.get("summary", "")).strip()
            if summary:
                text = self._line_with_suffix(text, f"  {summary}")
            if focus_read:
                text = self._line_with_suffix(text, f"  {focus_read}")
        elif purpose == "inspect" and self.sim.detail_for_xy(x, y) != "unloaded":
            inspected_prop = _property_covering(self.sim, x, y, z)
            if isinstance(inspected_prop, dict):
                record_area_warmth(
                    self.sim,
                    x=x,
                    y=y,
                    reason="property_inspect",
                    score_delta=0.55,
                    source_kind="property_inspect",
                    source_id=inspected_prop.get("id"),
                )
                if crime_plan_surface_rows(self.sim, prop=inspected_prop):
                    self.action_system._remember_player_property_discovery(
                        eid,
                        inspected_prop,
                        discovery_mode="inspect",
                    )
            if focus_read:
                text = self._line_with_suffix(text, f"  {focus_read}")
        elif focus_read:
            text = self._line_with_suffix(text, f"  {focus_read}")
        if purpose == "inspect":
            visibility = getattr(self.sim, "visibility_state", None)
            player_visible = visibility.get("player_visible", set()) if isinstance(visibility, dict) else set()
            if (x, y, z) in set(player_visible or ()):
                drone_states = self.sim.ecs.get(DroneState)
                radio_drone_visible = False
                for target_eid in self.sim.tilemap.entities_at(x, y, z):
                    drone_state = drone_states.get(target_eid)
                    if drone_state is None:
                        continue
                    if str(getattr(drone_state, "mode", "") or "").strip().lower() != "deployed":
                        continue
                    capabilities = set(drone_state_capabilities(drone_state, item_catalog=ITEM_CATALOG))
                    if {"radio", "comms"} & capabilities:
                        radio_drone_visible = True
                        break
                if radio_drone_visible:
                    text = self._line_with_suffix(text, "  Wire: Shift+W opens the radio handshake.")
                vehicle_visible = any(
                    isinstance(prop, dict)
                    and str(prop.get("kind", "") or "").strip().lower() == "vehicle"
                    and int(prop.get("x", -999999)) == int(x)
                    and int(prop.get("y", -999999)) == int(y)
                    and int(prop.get("z", 0)) == int(z)
                    for prop in getattr(self.sim, "properties", {}).values()
                )
                if vehicle_visible:
                    text = self._line_with_suffix(text, "  Wire: Shift+W opens the local vehicle controller.")
        self.set_look_inspect_text(text)
        self.sim.emit(Event(
            "cursor_examined",
            eid=eid,
            mode="city",
            purpose=purpose,
            x=x,
            y=y,
            z=z,
            text=text,
            announce=announce,
        ))

    def handle_scan_action(self, eid, pos, *, radius=8):
        radius = max(1, int(radius))
        scan_terms = self._scan_skill_terms(self.sim, eid)
        radius += max(0, _int_or_default(scan_terms.get("radius_bonus"), 0))
        detail_level = max(0, _int_or_default(scan_terms.get("detail_level"), 0))
        display_limit = max(1, min(8, _int_or_default(scan_terms.get("display_limit"), 5)))
        scan_note = str(scan_terms.get("note", "") or "").strip()
        access_prep_terms = self._access_prep_skill_terms(self.sim, eid)
        access_prep_reveal_tier = max(0, _int_or_default(access_prep_terms.get("reveal_tier"), 0))

        best_property = None
        best_property_dist = radius + 1
        for prop in self.sim.properties.values():
            if prop["z"] != pos.z:
                continue
            if self.sim.detail_for_xy(prop["x"], prop["y"]) == "unloaded":
                continue
            dist = _manhattan(pos.x, pos.y, prop["x"], prop["y"])
            if dist > radius or dist >= best_property_dist:
                continue
            best_property = prop
            best_property_dist = dist

        if isinstance(best_property, dict):
            record_area_warmth(
                self.sim,
                x=best_property.get("x"),
                y=best_property.get("y"),
                reason="property_scan",
                score_delta=0.45,
                source_kind="property_scan",
                source_id=best_property.get("id"),
            )

        best_item = None
        best_item_dist = radius + 1
        if not map_mode_active(self.sim):
            for ground in self.sim.ground_items.values():
                if ground.get("z", 0) != pos.z:
                    continue
                gx = int(ground.get("x", 0))
                gy = int(ground.get("y", 0))
                if self.sim.detail_for_xy(gx, gy) == "unloaded":
                    continue
                dist = _manhattan(pos.x, pos.y, gx, gy)
                if dist > radius or dist >= best_item_dist:
                    continue
                best_item = ground
                best_item_dist = dist

        best_npc = None
        best_npc_dist = radius + 1
        positions = self.sim.ecs.get(Position)
        insight = self.sim.ecs.get(SkillProfile).get(eid)
        if not insight:
            insight = self.sim.ecs.get(InsightStats).get(eid)
        if not insight:
            insight = self.sim.ecs.get(CoreStats).get(eid)
        players = self.sim.ecs.get(PlayerControlled)
        ais = self.sim.ecs.get(AI)
        memories = self.sim.ecs.get(NPCMemory)
        identities = self.sim.ecs.get(CreatureIdentity)
        move_throttles = self.sim.ecs.get(MovementThrottle)
        occupations = self.sim.ecs.get(Occupation)
        routines = self.sim.ecs.get(NPCRoutine)
        for other_eid, other_pos in positions.items():
            if other_eid == eid:
                continue
            if players.get(other_eid):
                continue
            if other_pos.z != pos.z:
                continue
            if self.sim.detail_for_xy(other_pos.x, other_pos.y) == "unloaded":
                continue
            dist = _manhattan(pos.x, pos.y, other_pos.x, other_pos.y)
            if dist > radius or dist >= best_npc_dist:
                continue
            best_npc = (
                other_eid,
                other_pos,
                ais.get(other_eid),
                memories.get(other_eid),
                move_throttles.get(other_eid),
                identities.get(other_eid),
                occupations.get(other_eid),
                routines.get(other_eid),
            )
            best_npc_dist = dist

        lines = []
        if best_property:
            crew_rows = crime_plan_surface_rows(self.sim, prop=best_property)
            self.action_system._remember_player_property_discovery(eid, best_property, discovery_mode="scan")
            property_text = f"Property {best_property_dist}t: {self._property_summary(self.sim, best_property, viewer_eid=eid)}"
            knowledge_hint = self._property_knowledge_hint(self.sim, eid, best_property)
            if knowledge_hint:
                property_text += f" {knowledge_hint}"
            contact_hint = self._property_contact_hint(self.sim, eid, best_property)
            if contact_hint:
                property_text += f" {contact_hint}"
            if crew_rows:
                row = crew_rows[0]
                property_text += (
                    f" crew:{row.get('organization_name') or 'local crew'} "
                    f"{row.get('stage_label')} {row.get('method_label')}"
                )
            lines.append(self._property_legend_line(
                best_property,
                property_text,
            ))
            if detail_level >= 1:
                detail_bits = []
                controller = self._property_access_controller(self.sim, best_property)
                controller_kind = str(controller.get("kind", "none")).strip().lower() or "none"
                if controller_kind != "none":
                    requirement = self._controller_access_requirement_text(controller)
                    if requirement:
                        detail_bits.append(f"req:{requirement}")
                access_modes = self._property_access_summary(self.sim, best_property, viewer_eid=eid)
                if access_modes:
                    detail_bits.append(f"modes:{access_modes}")
                services = []
                for service in list(_finance_services_for_property(best_property)) + list(self._site_services_for_property(best_property)):
                    label = str(service).strip().lower()
                    if label and label not in services:
                        services.append(label)
                if services:
                    detail_bits.append("services:" + ",".join(services[:4]))
                infrastructure_role = _property_infrastructure_role(best_property)
                stakeout_stats = self._stakeout_property_opportunity_stats(
                    self.sim,
                    getattr(self.sim, "player_eid", eid),
                    best_property.get("id"),
                )
                if infrastructure_role == "camera_target":
                    detection_radius = max(1, _int_or_default(_property_metadata(best_property).get("detection_radius"), 5))
                    state_text = "online" if self._security_fixture_is_online(self.sim, best_property) else "offline"
                    detail_bits.append(f"camera:{state_text} r{detection_radius}")
                elif infrastructure_role == "alarm_target":
                    state_text = "online" if self._security_fixture_is_online(self.sim, best_property) else "offline"
                    detail_bits.append(f"alarm:{state_text}")
                if isinstance(stakeout_stats, dict):
                    detail_bits.append(f"ops:{int(stakeout_stats.get('count', 0))}")
                    if bool(stakeout_stats.get("mapped")):
                        detail_bits.append("stakeout:mapped")
                    else:
                        confidence_pct = int(round(float(stakeout_stats.get("least_confidence", 0.0) or 0.0) * 100.0))
                        detail_bits.append(f"stakeout:{max(0, confidence_pct)}%")
                    tracked_surface = stakeout_stats.get("tracked_surface") if isinstance(stakeout_stats.get("tracked_surface"), dict) else None
                    tracked_summary = str((tracked_surface or {}).get("summary", "") or "").strip()
                    if tracked_summary:
                        detail_bits.append(f"pulse:{tracked_summary}")
                if detail_level >= 2:
                    org_presence = format_property_org_presence(self.sim, best_property, include_primary=True)
                    if org_presence:
                        detail_bits.append(f"orgs:{org_presence}")
                if crew_rows:
                    row = crew_rows[0]
                    detail_bits.append(f"crew:{row.get('site_role')} {row.get('method_label')} {row.get('stage_label')}")
                if detail_bits:
                    lines.append("Property detail: " + "  ".join(detail_bits))
                prep_reveal_tier = min(detail_level, access_prep_reveal_tier)
                if prep_reveal_tier > 0:
                    lines.extend(self._access_prep_detail_lines(
                        self.sim,
                        eid,
                        best_property,
                        controller=controller,
                        reveal_tier=prep_reveal_tier,
                    ))

        if best_item:
            item_id = best_item.get("item_id")
            item_def = ITEM_CATALOG.get(item_id, {})
            item_name = item_def.get("name", item_id or "item")
            lines.append(self._item_legend_line(
                item_id,
                f"Item {item_name} x{int(best_item.get('quantity', 1))} {best_item_dist}t away",
            ))
            if detail_level >= 1:
                item_tags = [
                    str(tag).strip().lower()
                    for tag in item_def.get("tags", ())
                    if str(tag).strip()
                ]
                legal_status = str(item_def.get("legal_status", "legal")).strip().lower() or "legal"
                detail_bits = [f"status:{legal_status}"]
                if item_tags:
                    detail_bits.append("tags:" + "/".join(item_tags[:4]))
                lines.append("Item detail: " + "  ".join(detail_bits))

        if best_npc:
            npc_eid, npc_pos, npc_ai, npc_memory, npc_throttle, npc_identity, npc_occupation, npc_routine = best_npc
            npc_state = npc_ai.state if npc_ai else "idle"
            status_speed_mult = self._entity_status_move_speed_multiplier(self.sim, npc_eid)
            speed = npc_throttle.effective_speed(status_multiplier=status_speed_mult) if npc_throttle else status_speed_mult
            if npc_identity:
                taxonomy = str(npc_identity.taxonomy_class).title()
                species = str(npc_identity.species)
                type_text = _entity_viewer_display_name(
                    self.sim,
                    npc_eid,
                    viewer_eid=eid,
                    title_case=True,
                )
                glyph_code = npc_identity.taxonomy_glyph(fallback="N")
                coat = str(npc_identity.coat_variant or "").replace("_", " ").strip()
            else:
                taxonomy = "Unknown"
                species = "unknown species"
                type_text = "Npc"
                glyph_code = "N"
                coat = ""
            coat_text = f" coat:{coat}" if coat else ""
            lines.append(self._entity_legend_line(
                self.sim,
                npc_eid,
                (
                    f"{type_text} {npc_eid} {best_npc_dist}t away "
                    f"@ {npc_pos.x},{npc_pos.y} state:{npc_state} speed:{speed:.2f}x "
                    f"type:{glyph_code}/{taxonomy} species:{species}{coat_text}"
                ),
                player_eid=eid,
            ))
            genome = self.sim.ecs.get(AnimalGenome).get(npc_eid)
            if genome is not None and detail_level >= 1:
                expressed = dict(getattr(genome, "expressed", {}) or {})
                phenotype_bits = [
                    str(expressed.get("color_word") or "unknown").replace("_", " "),
                    str(expressed.get("pattern") or "plain").replace("_", " "),
                    str(expressed.get("build") or "balanced").replace("_", " "),
                ]
                display = str(expressed.get("display") or "none").replace("_", " ")
                abilities = [str(value).replace("_", " ") for value in tuple(expressed.get("abilities") or ())]
                genetics_text = "phenotype:" + "/".join(phenotype_bits)
                if display != "none":
                    genetics_text += f"  display:{display}"
                if abilities:
                    genetics_text += "  biology:" + "/".join(abilities)
                genetics_text += f"  root:{str(getattr(genome, 'root_animal_id', 'other root')).replace('_', ' ')}"
                lines.append("Fauna genetics: " + genetics_text)

            career_text = self._career_label(npc_occupation)
            workplace_prop = self._workplace_property(self.sim, occupation=npc_occupation, routine=npc_routine)
            if career_text or workplace_prop or npc_ai:
                job_bits = []
                if npc_ai:
                    job_bits.append(f"role:{str(npc_ai.role).replace('_', ' ')}")
                if career_text:
                    job_bits.append(f"job:{career_text}")
                if workplace_prop:
                    job_bits.append(f"work:{workplace_prop.get('name', workplace_prop.get('id', 'property'))}")
                workplace = getattr(npc_occupation, "workplace", None)
                organization_eid = workplace.get("organization_eid") if isinstance(workplace, dict) else None
                org_name = organization_name(self.sim, organization_eid)
                if org_name and (not workplace_prop or org_name.lower() != str(workplace_prop.get("name", "")).strip().lower()):
                    job_bits.append(f"org:{org_name}")
                org_presence = format_actor_org_presence(self.sim, npc_eid, include_primary=False)
                if org_presence:
                    job_bits.append(f"orgs:{org_presence}")
                crew_rows = crime_plan_surface_rows(self.sim, actor_eid=npc_eid)
                if crew_rows:
                    row = crew_rows[0]
                    job_bits.append(f"crew:{row.get('actor_text')} {row.get('method_label')}")
                    record_crime_plan_observation(
                        self.sim,
                        row.get("plan_key"),
                        observer_eid=eid,
                        source_kind="npc_scan",
                        score_delta=CRIME_PLAN_OBSERVATION_SCAN,
                    )
                lines.append("NPC: " + "  ".join(job_bits))

            rumor = None
            if npc_memory:
                for entry in npc_memory.entries:
                    if entry["kind"] != "world_trait":
                        continue
                    if self.sim.tick - int(entry["tick"]) > 220:
                        continue
                    if rumor is None or float(entry.get("strength", 0.0)) > float(rumor.get("strength", 0.0)):
                        rumor = entry
            if rumor:
                topic = str(rumor["data"].get("topic", "")).strip().lower()
                claim_value = self._world_trait_claim_value(rumor["data"])
                claim_text = self._world_trait_claim_text(topic, claim_value)
                confidence = int(max(0.0, min(1.0, float(rumor.get("strength", 0.0)))) * 100)
                read = _rumor_truth_read(insight, rumor)
                lines.append(f"Rumor: {claim_text} ({confidence}% confidence, read: {read}).")

        if not lines:
            lines.append(f"Clear within {radius} tiles.")

        self.sim.emit(Event(
            "scan_report",
            eid=eid,
            mode="city",
            radius=radius,
            detail_level=detail_level,
            note=scan_note,
            display_limit=display_limit,
            lines=lines,
        ))
