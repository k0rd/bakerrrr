"""Combat-support systems extracted from ``game.systems``."""

import random

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight as _has_line_of_sight
from game.components import (
    AI,
    AnimalPhysicalProfile,
    ArmorLoadout,
    Collider,
    CoverState,
    CreatureIdentity,
    EcologyProfile,
    Inventory,
    ItemUseProfile,
    JusticeProfile,
    NPCNeeds,
    NPCSocial,
    NPCTraits,
    NPCWill,
    Occupation,
    Position,
    Render,
    StatusEffects,
    SubstanceUseState,
    SuppressionState,
    Vitality,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.items import ITEM_CATALOG, credstick_total_credits, is_credstick_item, item_display_name
from game.quick_travel_ramps import local_interactions_suspended_for_actor
from game.checks import (
    crime_sensitivity as _crime_sensitivity,
    justice_level as _justice_level,
)
from game.dialogue_runtime import active_contractor_record
from game.skills import actor_skill as _actor_skill
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
    _recover_downed_actor_state,
)
from game.system_support.combat_targeting_runtime import (
    _aim_confirm_label,
    _aim_open_label,
    _appearance_with_effect,
    _clamp,
    _dir_label,
    _entity_should_blink_in_combat,
    _entity_uses_melee_aim,
    _entity_is_weapon_targetable,
    _first_targetable_entity_at,
    _int_or_default,
    _float_or_default,
    _grid_distance,
    _manual_fire_preview,
    _npc_combat_metrics,
    _projectile_path_points,
    _shatter_window_for_projectile,
    _target_condition_descriptor,
    _weapon_ammo_type_label,
    _weapon_context_for_entity,
    _weapon_is_melee,
    _weapon_reserve_ammo,
    _weapon_target_viability,
)
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.cover_runtime import _effective_cover_value
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import _direction_step, _manhattan
from game.system_support.item_provenance_runtime import CLAIM_PRIVATE_EFFECT, stamp_item_provenance
from game.system_support.item_runtime import (
    _apply_item_effects_to_entity,
    _default_weapon_reserve_ammo,
    _item_can_recover_downed_actor as _runtime_item_can_recover_downed_actor,
    _item_tags,
    _smallest_recovery_item_for_downed_actor,
    _weapon_uses_ammo,
)
from game.system_support.player_feedback import _log_player_feedback
from game.system_support.offense_runtime import (
    ACTION_OFFENSE_BASE,
    ACTION_OFFENSE_CONTEXT_BONUS,
    _offense_notice_radius,
    _offense_tier,
)
from game.system_support.status_runtime import (
    _npc_status_metric_args,
    _status_int_offset,
    _status_modifier_total,
    _status_multiplier,
    _status_tick_step,
)
from game.system_support.structure_damage_runtime import (
    apply_structural_damage as _apply_structural_damage,
    structural_surface_kind as _structural_surface_kind,
    structural_surface_label as _structural_surface_label,
)
from game.weapons import weapon_by_id

THREAT_STATES = {"protecting", "investigating"}
PEST_WILDLIFE_TAXONOMIES = frozenset({"insect", "arachnid"})
MAJOR_WILDLIFE_TAXONOMIES = frozenset({"canine", "feline", "ungulate"})


class WeaponSystem(System):

    NPC_BLEEDOUT_TICKS = 18
    PLAYER_BLEEDOUT_TICKS = 8

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.rng = random.Random(f"{sim.seed}:weapon_system")
        setattr(self.sim, "player_bleedout_ticks", int(self.PLAYER_BLEEDOUT_TICKS))
        self.sim.events.subscribe("weapon_cycle_request", self.on_weapon_cycle_request)
        self.sim.events.subscribe("weapon_fire_request", self.on_weapon_fire_request)
        self.sim.events.subscribe("melee_attack_request", self.on_melee_attack_request)

    def _first_projectile_hit_entity_at(self, x, y, z, *, exclude_eid=None, skip_downed=False):
        for other_eid in sorted(self.sim.tilemap.entities_at(x, y, z)):
            if other_eid == exclude_eid:
                continue
            if skip_downed and _entity_is_downed(self.sim, other_eid):
                continue
            if _entity_is_weapon_targetable(self.sim, other_eid, current_tick=self.sim.tick):
                return other_eid
        return None

    def _offense_score_for(self, action, context="ordinary"):
        base = ACTION_OFFENSE_BASE.get(action, 0)
        bonus = ACTION_OFFENSE_CONTEXT_BONUS.get(context, 0)
        return max(0, min(100, base + bonus))

    def _emit_action_offense(self, eid, action, x, y, z, context="ordinary", score=None, **extra):
        if score is None:
            score = self._offense_score_for(action, context=context)
        if score <= 0:
            return

        payload = {
            "offender_eid": eid,
            "action": action,
            "context": context,
            "offense_score": score,
            "offense_tier": _offense_tier(score),
            "x": x,
            "y": y,
            "z": z,
            "radius": _offense_notice_radius(score),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        if not any(
            key in payload
            for key in ("observer_eids", "accountable_observer_eids", "observation_channels", "witnessed", "witnesses")
        ):
            payload.update(
                observation_payload_for_position(
                    self.sim,
                    x,
                    y,
                    z,
                    exclude_eid=eid,
                    offender_eid=eid,
                    observation_channels=("actor_witness",),
                )
            )
        self.sim.emit(Event(
            "action_offense",
            **payload,
        ))

    def _wildlife_offense_profile(self, target_eid, *, action):
        if target_eid is None:
            return None
        ai = self.sim.ecs.get(AI).get(target_eid)
        identity = self.sim.ecs.get(CreatureIdentity).get(target_eid)
        role = str(getattr(ai, "role", "") or "").strip().lower()
        creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
        if role != "wildlife" and creature_type != "animal":
            return None

        taxonomy = str(getattr(identity, "taxonomy_class", "other") or "other").strip().lower() or "other"
        target_name = _entity_display_name(self.sim, target_eid, title_case=False)
        if taxonomy in PEST_WILDLIFE_TAXONOMIES and str(action or "").strip().lower() == "melee_attack":
            return {
                "context": "pest_control",
                "score": 0,
                "target_name": target_name,
                "target_taxonomy": taxonomy,
            }

        context = "wildlife_hunting" if (
            str(action or "").strip().lower() == "fire_weapon"
            or taxonomy in MAJOR_WILDLIFE_TAXONOMIES
        ) else "wildlife_harassment"
        return {
            "context": context,
            "score": self._offense_score_for(action, context=context),
            "target_name": target_name,
            "target_taxonomy": taxonomy,
        }


    def _weapon_instance_data(self, loadout, weapon_id):
        if not loadout:
            return {}
        return loadout.weapon_instance(weapon_id)

    def _consume_player_weapon_ammo(self, eid, loadout, weapon):
        if eid != self.player_eid:
            return True, None
        if not _weapon_uses_ammo(weapon):
            return True, None

        weapon_id = str(weapon.get("id", ""))
        current = int(loadout.reserve_ammo_value(
            weapon_id,
            default=_default_weapon_reserve_ammo(weapon),
        ))
        if loadout.reserve_ammo_value(weapon_id, default=None) is None:
            loadout.set_reserve_ammo_value(weapon_id, current)

        ammo_per_shot = int(max(1, weapon.get("ammo_per_shot", 1)))
        if current < ammo_per_shot:
            return False, current

        remaining = loadout.set_reserve_ammo_value(
            weapon_id,
            max(0, current - ammo_per_shot),
        )
        return True, int(remaining)

    def _best_player_death_save_entry(self):
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        if not inventory:
            return None, None

        best_entry = None
        best_item_def = None
        best_restore = -1
        for entry in list(getattr(inventory, "items", ()) or ()):
            item_id = str(entry.get("item_id", "")).strip().lower()
            item_def = ITEM_CATALOG.get(item_id, {})
            if "death_save" not in _item_tags(item_def):
                continue
            restore_total = 0
            for effect in item_def.get("effects", ()):
                if not isinstance(effect, dict) or effect.get("type") != "restore_hp":
                    continue
                try:
                    restore_total += int(effect.get("delta", 0))
                except (TypeError, ValueError):
                    continue
            if restore_total <= best_restore:
                continue
            best_restore = restore_total
            best_entry = entry
            best_item_def = item_def
        return best_entry, best_item_def

    def _try_consume_player_death_save(self, *, source_eid, weapon_id, x, y, z):
        entry, item_def = self._best_player_death_save_entry()
        if not entry or not item_def:
            return False

        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        if not inventory:
            return False

        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=1)
        if not removed:
            return False

        removed_metadata = removed.get("metadata") if isinstance(removed.get("metadata"), dict) else {}
        applied = _apply_item_effects_to_entity(
            self.sim,
            self.player_eid,
            item_def,
            item_metadata=removed_metadata,
        )
        vitality = self.sim.ecs.get(Vitality).get(self.player_eid)
        if not vitality or int(getattr(vitality, "hp", 0)) <= 0:
            return False

        vitality.downed = False
        vitality.downed_tick = None

        item_name = item_display_name(item_def["id"], metadata=removed_metadata, item_catalog=ITEM_CATALOG)
        self.sim.emit(Event(
            "item_used",
            eid=self.player_eid,
            item_id=item_def["id"],
            item_name=item_name,
            reason="critical_auto",
            applied=applied,
            item_metadata=dict(removed_metadata),
            source_property_id=str(removed_metadata.get("source_property_id", "") or "").strip() or None,
            source_organization_eid=removed_metadata.get("source_organization_eid"),
            source_organization_key=str(removed_metadata.get("source_organization_key", "") or "").strip() or None,
            source_practice_key=str(removed_metadata.get("source_practice_key", "") or "").strip() or None,
        ))
        self.sim.emit(Event(
            "player_critical_saved",
            target_eid=self.player_eid,
            source_eid=source_eid,
            weapon_id=weapon_id,
            item_id=item_def["id"],
            item_name=item_name,
            recovered_hp=int(vitality.hp),
            max_hp=int(vitality.max_hp),
            x=x,
            y=y,
            z=z,
        ))
        return True

    def _melee_damage_for(self, eid):
        athletics = float(_actor_skill(self.sim, eid, "athletics"))
        perception = float(_actor_skill(self.sim, eid, "perception"))
        base = 3.0 + (athletics * 0.42) + (perception * 0.08)
        return int(max(2, min(12, round(base))))

    def _manual_melee_target(self, eid, source_pos, target_x=None, target_y=None, target_z=None):
        if target_x is None or target_y is None or target_z is None:
            return None, "no_direction"
        try:
            tx = int(target_x)
            ty = int(target_y)
            tz = int(target_z)
        except (TypeError, ValueError):
            return None, "no_direction"
        if tz != int(source_pos.z):
            return None, "wrong_floor"

        dist = _grid_distance(source_pos.x, source_pos.y, tx, ty)
        if dist <= 0:
            return None, "no_direction"
        if dist > 1:
            return None, "out_of_range"

        target_eid = _first_targetable_entity_at(self.sim, tx, ty, tz, exclude_eid=eid)
        if target_eid is None:
            prop = self.sim.property_covering(tx, ty, tz) if hasattr(self.sim, "property_covering") else None
            kind = _structural_surface_kind(self.sim, prop, tx, ty, tz)
            if kind:
                return {
                    "target_eid": None,
                    "structure": True,
                    "surface_kind": kind,
                    "x": tx,
                    "y": ty,
                    "z": tz,
                    "dist": dist,
                    "property_id": (prop or {}).get("id") if isinstance(prop, dict) else None,
                }, None
            return None, "no_target"

        return {
            "target_eid": target_eid,
            "x": tx,
            "y": ty,
            "z": tz,
            "dist": dist,
        }, None

    def _acquire_melee_target(self, eid, source_pos, preferred_target_eid=None):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)

        if preferred_target_eid is not None:
            target = self._is_valid_target(preferred_target_eid, eid, source_pos, max_range=1)
            if target:
                return target

        candidates = []
        if eid == self.player_eid:
            for other_eid, ai in ais.items():
                if ai.state not in THREAT_STATES:
                    continue
                target = self._is_valid_target(other_eid, eid, source_pos, max_range=1)
                if target:
                    candidates.append(target)
        else:
            source_ai = ais.get(eid)
            if source_ai and source_ai.target_eid is not None:
                target = self._is_valid_target(source_ai.target_eid, eid, source_pos, max_range=1)
                if target:
                    candidates.append(target)

            # Fallback: hit any adjacent hostile target if explicit target is missing.
            if not candidates:
                for other_eid, other_pos in positions.items():
                    if other_eid == eid or int(other_pos.z) != int(source_pos.z):
                        continue
                    target = self._is_valid_target(other_eid, eid, source_pos, max_range=1)
                    if target:
                        candidates.append(target)

        if not candidates:
            return None
        candidates.sort(key=lambda row: row["dist"])
        return candidates[0]

    def _resolve_structure_melee_attack(
        self,
        *,
        eid,
        source_pos,
        target,
        melee_weapon_id,
        melee_weapon_name,
        raw_damage,
        cooldown_ticks,
        loadout,
        manual_aim,
    ):
        tx = int(target.get("x", source_pos.x))
        ty = int(target.get("y", source_pos.y))
        tz = int(target.get("z", source_pos.z))
        prop = self.sim.property_covering(tx, ty, tz) if hasattr(self.sim, "property_covering") else None
        result = _apply_structural_damage(
            self.sim,
            prop,
            tx,
            ty,
            tz,
            amount=max(1, int(raw_damage)),
            kind=str(target.get("surface_kind", "") or ""),
            cause="melee_attack",
            damage_kind="melee",
            weapon_id=melee_weapon_id,
            offender_eid=eid,
        )
        if not isinstance(result, dict) or not result.get("damaged"):
            self.sim.emit(Event(
                "weapon_fire_blocked",
                eid=eid,
                reason=result.get("reason", "no_target") if isinstance(result, dict) else "no_target",
            ))
            return True

        if loadout:
            loadout.last_fire_tick = int(self.sim.tick)
            loadout.cooldown_until_tick = int(self.sim.tick) + int(max(1, cooldown_ticks))

        kind = _structural_surface_label(result.get("surface_kind"))
        if eid == self.player_eid:
            if result.get("broken"):
                _log_player_feedback(self.sim, f"You smash through the {kind}.", kind="combat")
            else:
                _log_player_feedback(
                    self.sim,
                    f"You strike the {kind} ({int(result.get('hp', 0))}/{int(result.get('max_hp', 1))}).",
                    kind="combat",
                )
        self.sim.emit(Event(
            "structure_melee_attack",
            eid=eid,
            source_eid=eid,
            weapon_id=melee_weapon_id,
            weapon_name=melee_weapon_name,
            target_eid=None,
            x=tx,
            y=ty,
            z=tz,
            target_x=tx,
            target_y=ty,
            target_z=tz,
            target_dist=target.get("dist", 1),
            damage=int(raw_damage),
            target_downed=False,
            manual_aim=manual_aim,
            structure=True,
            surface_kind=result.get("surface_kind"),
            property_id=result.get("property_id"),
        ))
        self.sim.emit(Event(
            "noise",
            source_eid=eid,
            x=source_pos.x,
            y=source_pos.y,
            z=source_pos.z,
            radius=2,
            cause="structure_melee",
            target_x=tx,
            target_y=ty,
            target_z=tz,
        ))
        return True

    def _resolve_melee_attack(self, event, *, eid, source_pos, melee_weapon=None):
        if melee_weapon is None:
            melee_weapon = event.data.get("melee_weapon")
        melee_weapon_id = "unarmed"
        melee_weapon_name = "Unarmed"
        raw_damage = self._melee_damage_for(eid)
        cooldown_ticks = 1
        if isinstance(melee_weapon, dict):
            melee_weapon_id = str(melee_weapon.get("id", "unarmed")).strip() or "unarmed"
            melee_weapon_name = str(melee_weapon.get("name", melee_weapon_id)).strip() or melee_weapon_id
            try:
                weapon_damage = int(melee_weapon.get("base_damage", raw_damage))
            except (TypeError, ValueError):
                weapon_damage = raw_damage
            raw_damage = int(max(2, weapon_damage))
            cooldown_ticks = int(max(1, melee_weapon.get("cooldown_ticks", 1)))
        raw_damage = int(max(1, round(raw_damage * _status_multiplier(
            self.sim,
            eid,
            "melee_damage_mult",
            minimum=0.2,
            maximum=3.0,
        ))))
        cooldown_ticks = max(1, int(round(cooldown_ticks * _status_multiplier(
            self.sim,
            eid,
            "melee_cooldown_mult",
            minimum=0.35,
            maximum=3.0,
        ))))

        loadout = self.sim.ecs.get(WeaponLoadout).get(eid)
        if loadout and self.sim.tick < int(loadout.cooldown_until_tick):
            self.sim.emit(Event(
                "weapon_fire_blocked",
                eid=eid,
                reason="cooldown",
                ready_in=max(0, int(loadout.cooldown_until_tick) - int(self.sim.tick)),
            ))
            return True

        manual_aim = bool(event.data.get("manual_aim", False))
        if manual_aim:
            target, blocked_reason = self._manual_melee_target(
                eid=eid,
                source_pos=source_pos,
                target_x=event.data.get("target_x"),
                target_y=event.data.get("target_y"),
                target_z=event.data.get("target_z", source_pos.z),
            )
            if not target:
                self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason=blocked_reason or "no_target"))
                return True
        else:
            target = self._acquire_melee_target(
                eid=eid,
                source_pos=source_pos,
                preferred_target_eid=event.data.get("target_eid"),
            )
            if not target:
                self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason="no_target"))
                return True

        if bool(target.get("structure", False)):
            return self._resolve_structure_melee_attack(
                eid=eid,
                source_pos=source_pos,
                target=target,
                melee_weapon_id=melee_weapon_id,
                melee_weapon_name=melee_weapon_name,
                raw_damage=raw_damage,
                cooldown_ticks=cooldown_ticks,
                loadout=loadout,
                manual_aim=manual_aim,
            )

        target_eid = target.get("target_eid")
        target_pos = self.sim.ecs.get(Position).get(target_eid)
        if target_pos is None:
            self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason="no_target"))
            return True
        offense_profile = self._wildlife_offense_profile(target_eid, action="melee_attack")
        target_name = _entity_display_name(self.sim, target_eid, title_case=False)

        hit = self._damage_entity(
            target_eid=target_eid,
            source_eid=eid,
            weapon_id=melee_weapon_id,
            raw_damage=raw_damage,
            x=target_pos.x,
            y=target_pos.y,
            z=target_pos.z,
            cover_penetration=0.0,
            damage_kind="melee",
        )
        if not hit:
            self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason="no_target"))
            return True

        target_vitality = self.sim.ecs.get(Vitality).get(target_eid)
        self.sim.emit(Event(
            "melee_attack",
            eid=eid,
            source_eid=eid,
            weapon_id=melee_weapon_id,
            weapon_name=melee_weapon_name,
            target_eid=target_eid,
            x=target.get("x"),
            y=target.get("y"),
            z=target.get("z"),
            target_x=target.get("x"),
            target_y=target.get("y"),
            target_z=target.get("z"),
            target_dist=target.get("dist", 1),
            damage=raw_damage,
            target_downed=bool(target_vitality and target_vitality.downed),
            manual_aim=manual_aim,
        ))
        self.sim.emit(Event(
            "noise",
            source_eid=eid,
            x=source_pos.x,
            y=source_pos.y,
            z=source_pos.z,
            radius=2,
            cause="melee_attack",
            target_eid=target_eid,
        ))

        if loadout:
            loadout.last_fire_tick = int(self.sim.tick)
            loadout.cooldown_until_tick = int(self.sim.tick) + int(max(1, cooldown_ticks))

        context = "unarmed_assault" if melee_weapon_id == "unarmed" else "melee_assault"
        score = None
        target_taxonomy = ""
        if isinstance(offense_profile, dict):
            context = str(offense_profile.get("context", context) or context).strip().lower() or context
            score = int(offense_profile.get("score", 0) or 0)
            target_taxonomy = str((offense_profile or {}).get("target_taxonomy", "") or "").strip().lower()
        target_prop = self.sim.property_covering(target.get("x"), target.get("y"), target.get("z", 0)) if hasattr(self.sim, "property_covering") else None
        self._emit_action_offense(
            eid=eid,
            action="melee_attack",
            context=context,
            score=score,
            x=source_pos.x,
            y=source_pos.y,
            z=source_pos.z,
            target_eid=target_eid,
            victim_eid=target_eid,
            victim_name=target_name,
            target_name=target_name,
            target_x=target.get("x"),
            target_y=target.get("y"),
            target_z=target.get("z", 0),
            property_id=(target_prop or {}).get("id"),
            property_name=(target_prop or {}).get("name"),
            target_taxonomy=target_taxonomy,
        )
        return True

    def _weapon_label(self, loadout, weapon):
        instance = self._weapon_instance_data(loadout, weapon["id"])
        custom = str(instance.get("custom_name", "")).strip()
        if custom:
            return custom
        return weapon["name"]

    def _is_valid_target(self, target_eid, source_eid, source_pos, max_range):
        if local_interactions_suspended_for_actor(self.sim, target_eid):
            return None

        positions = self.sim.ecs.get(Position)
        vitalities = self.sim.ecs.get(Vitality)

        target_pos = positions.get(target_eid)
        if not target_pos or target_pos.z != source_pos.z:
            return None
        if target_eid == source_eid:
            return None

        vitality = vitalities.get(target_eid)
        if vitality and vitality.downed:
            return None

        dist = _grid_distance(source_pos.x, source_pos.y, target_pos.x, target_pos.y)
        if dist > max_range:
            return None

        return {
            "target_eid": target_eid,
            "x": target_pos.x,
            "y": target_pos.y,
            "z": target_pos.z,
            "dist": dist,
        }

    def _manual_target(self, eid, source_pos, weapon, target_x=None, target_y=None, target_z=None):
        if target_x is None or target_y is None or target_z is None:
            return None, "no_direction"

        try:
            tx = int(target_x)
            ty = int(target_y)
            tz = int(target_z)
        except (TypeError, ValueError):
            return None, "no_direction"

        if tz != int(source_pos.z):
            return None, "wrong_floor"

        dist = _grid_distance(source_pos.x, source_pos.y, tx, ty)
        if dist <= 0:
            return None, "no_direction"

        max_range = int(max(1, weapon.get("range", 1)))
        if dist > max_range:
            return None, "out_of_range"

        return {
            "target_eid": _first_targetable_entity_at(self.sim, tx, ty, tz, exclude_eid=eid),
            "x": tx,
            "y": ty,
            "z": tz,
            "dist": dist,
        }, None

    def _acquire_target(self, eid, source_pos, weapon, preferred_target_eid=None):
        max_range = int(max(1, weapon.get("range", 1)))
        if preferred_target_eid is not None:
            target = self._is_valid_target(preferred_target_eid, eid, source_pos, max_range)
            if target:
                return target

        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        vitalities = self.sim.ecs.get(Vitality)

        candidates = []
        if eid == self.player_eid:
            for other_eid, ai in ais.items():
                if ai.state not in THREAT_STATES:
                    continue
                target = self._is_valid_target(other_eid, eid, source_pos, max_range)
                if not target:
                    continue
                candidates.append(target)
        else:
            source_ai = ais.get(eid)
            if source_ai and source_ai.target_eid is not None:
                ai_target = self._is_valid_target(source_ai.target_eid, eid, source_pos, max_range)
                if ai_target:
                    candidates.append(ai_target)

        if not candidates:
            return None
        candidates.sort(key=lambda row: row["dist"])
        return candidates[0]

    def _projectile_step(self, sx, sy, tx, ty, spread=0):
        if spread > 0:
            tx += self.rng.randint(-spread, spread)
            ty += self.rng.randint(-spread, spread)

        dx, dy = _direction_step(sx, sy, tx, ty)
        if dx == 0 and dy == 0:
            dx, dy = self.rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        return dx, dy

    def _spawn_projectiles(self, eid, pos, loadout, weapon, target, *, shot_mode="free_aim"):
        projectile_ids = []
        pellets = int(max(1, weapon.get("pellets", 1)))
        spread = int(max(0, weapon.get("spread", 0)))
        trajectory = weapon.get("trajectory", "ballistic")
        max_range = int(max(1, weapon.get("range", 1)))
        shot_mode = str(shot_mode or "free_aim").strip().lower()
        if shot_mode not in {"locked", "free_aim"}:
            shot_mode = "free_aim"

        instance = self._weapon_instance_data(loadout, weapon["id"])
        spread_mod = int(instance.get("spread_mod", 0))
        spread += _status_int_offset(self.sim, eid, "projectile_spread_mod", default=0)
        spread = max(0, spread + spread_mod)
        damage_mult = float(instance.get("damage_mult", 1.0))
        damage_mult *= _status_multiplier(
            self.sim,
            eid,
            "ranged_damage_mult",
            minimum=0.2,
            maximum=3.0,
        )

        for _ in range(pellets):
            path = _projectile_path_points(
                pos.x,
                pos.y,
                target["x"],
                target["y"],
                max_steps=max_range,
                spread=spread,
                rng=self.rng,
            )
            if not path:
                continue
            first_x, first_y = path[0]
            dx = int(first_x) - int(pos.x)
            dy = int(first_y) - int(pos.y)

            speed = float(weapon.get("speed", 1.0))
            if trajectory == "beam":
                speed = max(speed, 3.0)
            speed *= _status_multiplier(
                self.sim,
                eid,
                "projectile_speed_mult",
                minimum=0.25,
                maximum=3.0,
            )

            projectile_id = self.sim.register_projectile({
                "source_eid": eid,
                "weapon_id": weapon["id"],
                "x": pos.x,
                "y": pos.y,
                "z": pos.z,
                "dx": dx,
                "dy": dy,
                "path": path,
                "path_index": 0,
                "speed": speed,
                "travel_bank": 0.0,
                "remaining_range": len(path),
                "damage": int(max(1, round(float(weapon.get("base_damage", 5)) * damage_mult))),
                "trajectory": trajectory,
                "explosion_radius": int(max(0, weapon.get("explosion_radius", 0))),
                "aoe_falloff": float(max(0.0, min(1.0, weapon.get("aoe_falloff", 0.0)))),
                "cover_penetration": float(max(0.0, min(1.0, weapon.get("cover_penetration", 0.0)))),
                "projectile_glyph": weapon.get("projectile_glyph", "."),
                "shot_mode": shot_mode,
                "target_eid": target.get("target_eid"),
                "target_x": target.get("x"),
                "target_y": target.get("y"),
                "target_z": target.get("z"),
                "ignore_walls": trajectory == "lobbed",
            })
            projectile_ids.append(projectile_id)

        return projectile_ids

    def _damage_entity(
        self,
        target_eid,
        source_eid,
        weapon_id,
        raw_damage,
        x,
        y,
        z,
        cover_penetration=0.0,
        damage_kind="ballistic",
    ):
        if local_interactions_suspended_for_actor(self.sim, target_eid):
            return False

        armor_loadouts = self.sim.ecs.get(ArmorLoadout)
        vitalities = self.sim.ecs.get(Vitality)
        positions = self.sim.ecs.get(Position)
        covers = self.sim.ecs.get(CoverState)
        colliders = self.sim.ecs.get(Collider)
        renders = self.sim.ecs.get(Render)

        vitality = vitalities.get(target_eid)
        if not vitality:
            return False
        if vitality.downed:
            if target_eid == self.player_eid:
                if getattr(vitality, "death_reported_tick", None) is not None:
                    return False
                setattr(vitality, "last_attacker_eid", source_eid)
                setattr(vitality, "death_reason", "executed_while_downed")
                setattr(vitality, "death_reported_tick", int(self.sim.tick))
                self.sim.emit(Event(
                    "player_killed",
                    target_eid=target_eid,
                    source_eid=source_eid,
                    source_name=_entity_display_name(self.sim, source_eid, title_case=True) or "",
                    weapon_id=weapon_id,
                    reason="executed_while_downed",
                    damage_kind=damage_kind,
                    x=x,
                    y=y,
                    z=z,
                ))
                return True
            else:
                downed_tick = vitality.downed_tick
                try:
                    downed_tick = int(downed_tick)
                except (TypeError, ValueError):
                    downed_tick = int(self.sim.tick)
                vitality.downed_tick = min(downed_tick, int(self.sim.tick) - int(self.NPC_BLEEDOUT_TICKS))
                setattr(vitality, "last_attacker_eid", source_eid)
                setattr(vitality, "death_reason", "executed_while_downed")
                return True

        source_pos = positions.get(source_eid)
        target_pos = positions.get(target_eid)
        cover_absorb = 0.0
        if source_pos and target_pos and source_pos.z == target_pos.z:
            cover = covers.get(target_eid)
            if cover and cover.active:
                cover_effect = _effective_cover_value(
                    cover,
                    target_pos.x,
                    target_pos.y,
                    source_pos.x,
                    source_pos.y,
                )
                cover_absorb = cover_effect * max(0.0, 1.0 - cover_penetration)
        cover_absorb = max(
            0.0,
            min(
                0.95,
                cover_absorb + _status_modifier_total(self.sim, target_eid, "cover_absorb_bonus", default=0.0),
            ),
        )

        armor_absorb = 0.0
        armor_name = None
        armor_loadout = armor_loadouts.get(target_eid)
        if armor_loadout and armor_loadout.equipped_instance_id:
            armor_absorb = max(0.0, min(0.85, float(armor_loadout.damage_reduction)))
            armor_name = str(armor_loadout.equipped_name or armor_loadout.equipped_item_id or "").strip() or None
        armor_absorb = max(
            0.0,
            min(
                0.9,
                armor_absorb + _status_modifier_total(self.sim, target_eid, "armor_absorb_bonus", default=0.0),
            ),
        )

        raw_damage = int(max(1, raw_damage))
        after_cover_damage = raw_damage * (1.0 - cover_absorb)
        incoming_damage_mult = _status_multiplier(
            self.sim,
            target_eid,
            "incoming_damage_mult",
            minimum=0.2,
            maximum=3.0,
        )
        final_damage = int(max(1, round(after_cover_damage * (1.0 - armor_absorb) * incoming_damage_mult)))
        vitality.hp = max(0, vitality.hp - final_damage)

        self.sim.emit(Event(
            "entity_damaged",
            target_eid=target_eid,
            source_eid=source_eid,
            weapon_id=weapon_id,
            damage_kind=damage_kind,
            raw_damage=raw_damage,
            damage=final_damage,
            cover_absorb=round(cover_absorb, 3),
            armor_absorb=round(armor_absorb, 3),
            armor_name=armor_name,
            hp=vitality.hp,
            max_hp=vitality.max_hp,
            x=x,
            y=y,
            z=z,
        ))

        if vitality.hp > 0:
            return True

        vitality.downed_count += 1
        setattr(vitality, "last_attacker_eid", source_eid)

        if target_eid == self.player_eid:
            if self._try_consume_player_death_save(
                source_eid=source_eid,
                weapon_id=weapon_id,
                x=x,
                y=y,
                z=z,
            ):
                return True

            vitality.downed = True
            vitality.downed_tick = self.sim.tick
            setattr(vitality, "death_reason", "bled_out")
            setattr(vitality, "death_reported_tick", None)
            cover = covers.get(target_eid)
            if cover and cover.active:
                cover.clear(tick=self.sim.tick)
                self.sim.emit(Event("cover_left", eid=target_eid, reason="downed"))
            self.sim.emit(Event(
                "player_downed",
                target_eid=target_eid,
                source_eid=source_eid,
                source_name=_entity_display_name(self.sim, source_eid, title_case=True) or "",
                weapon_id=weapon_id,
                reason="lethal_damage",
                bleedout_ticks=int(self.PLAYER_BLEEDOUT_TICKS),
                bleedout_at_tick=int(self.sim.tick) + int(self.PLAYER_BLEEDOUT_TICKS),
                damage_kind=damage_kind,
                x=x,
                y=y,
                z=z,
            ))
            return True

        vitality.downed = True
        vitality.downed_tick = self.sim.tick
        setattr(vitality, "death_reason", "bled_out")
        _apply_downed_actor_state(self.sim, target_eid, tick=self.sim.tick)

        collider = colliders.get(target_eid)
        if collider:
            collider.blocks = False

        render = renders.get(target_eid)
        if render:
            render.glyph = "x"

        self.sim.emit(Event(
            "npc_downed",
            target_eid=target_eid,
            source_eid=source_eid,
            weapon_id=weapon_id,
            x=x,
            y=y,
            z=z,
        ))
        return True

    def _resolve_downed_player_death(self):
        vitality = self.sim.ecs.get(Vitality).get(self.player_eid)
        if not vitality or not bool(getattr(vitality, "downed", False)):
            return
        if getattr(vitality, "death_reported_tick", None) is not None:
            return

        downed_tick = getattr(vitality, "downed_tick", None)
        try:
            downed_tick = int(downed_tick)
        except (TypeError, ValueError):
            downed_tick = int(self.sim.tick)
        if int(self.sim.tick) - downed_tick < int(self.PLAYER_BLEEDOUT_TICKS):
            return

        source_eid = getattr(vitality, "last_attacker_eid", None)
        setattr(vitality, "death_reason", "bled_out")
        setattr(vitality, "death_reported_tick", int(self.sim.tick))
        self.sim.emit(Event(
            "player_killed",
            target_eid=self.player_eid,
            source_eid=source_eid,
            source_name=_entity_display_name(self.sim, source_eid, title_case=True) or "",
            weapon_id=None,
            reason="bled_out",
            damage_kind="bleedout",
            x=None,
            y=None,
            z=None,
        ))

    def _resolve_downed_npc_deaths(self):
        vitalities = self.sim.ecs.get(Vitality)
        positions = self.sim.ecs.get(Position)
        inventories = self.sim.ecs.get(Inventory)
        loadouts = self.sim.ecs.get(WeaponLoadout)
        ais = self.sim.ecs.get(AI)

        for eid, vitality in list(vitalities.items()):
            if eid == self.player_eid:
                continue
            if not vitality or not bool(getattr(vitality, "downed", False)):
                continue

            downed_tick = getattr(vitality, "downed_tick", None)
            try:
                downed_tick = int(downed_tick)
            except (TypeError, ValueError):
                downed_tick = int(self.sim.tick)

            if int(self.sim.tick) - downed_tick < int(self.NPC_BLEEDOUT_TICKS):
                continue

            pos = positions.get(eid)
            source_eid = getattr(vitality, "last_attacker_eid", None)
            reason = str(getattr(vitality, "death_reason", "bled_out")).strip() or "bled_out"
            target_name = _entity_display_name(self.sim, eid, title_case=True) or None

            drop_x = int(pos.x) if pos else 0
            drop_y = int(pos.y) if pos else 0
            drop_z = int(pos.z) if pos else 0

            dropped_items = []
            inv = inventories.get(eid)
            if inv:
                for entry in list(inv.items):
                    item_id = str(entry.get("item_id", "")).strip()
                    if not item_id:
                        continue
                    qty = int(entry.get("quantity", 1))
                    meta = dict(entry.get("metadata") or {})
                    meta = stamp_item_provenance(
                        self.sim,
                        {
                            **entry,
                            "x": drop_x,
                            "y": drop_y,
                            "z": drop_z,
                            "metadata": meta,
                        },
                        source_context="corpse_drop",
                        claim_class=CLAIM_PRIVATE_EFFECT,
                        source_owner_eid=eid,
                        source_owner_tag="npc",
                        source_actor_eid=eid,
                        source_victim_eid=eid,
                        source_property_id=str((self.sim.property_covering(drop_x, drop_y, drop_z) or {}).get("id", "")).strip() or None,
                        latent_claim_violation=bool(meta.get("latent_claim_violation", False)),
                        last_transfer_tick=int(getattr(self.sim, "tick", 0)),
                        last_transfer_kind="corpse_drop",
                        last_holder_eid=eid,
                    )
                    self.sim.register_ground_item(
                        item_id=item_id,
                        x=drop_x,
                        y=drop_y,
                        z=drop_z,
                        quantity=qty,
                        owner_eid=None,
                        owner_tag=None,
                        metadata=meta,
                    )
                    dropped_items.append({"item_id": item_id, "quantity": qty})

            loadout = loadouts.get(eid)
            if loadout and loadout.reserve_ammo:
                total_reserve = sum(int(v) for v in loadout.reserve_ammo.values() if int(v) > 0)
                if total_reserve > 0:
                    self.sim.register_ground_item(
                        item_id="light_ammo_box",
                        x=drop_x,
                        y=drop_y,
                        z=drop_z,
                        quantity=1,
                        owner_eid=None,
                        owner_tag=None,
                    )
                    dropped_items.append({"item_id": "light_ammo_box", "quantity": 1})

            ai = ais.get(eid)
            npc_role = str(getattr(ai, "role", "")).strip().lower() if ai else ""
            animal_payload = {}
            identity = self.sim.ecs.get(CreatureIdentity).get(eid)
            physical = self.sim.ecs.get(AnimalPhysicalProfile).get(eid)
            ecology = self.sim.ecs.get(EcologyProfile).get(eid)
            if identity and str(getattr(identity, "creature_type", "") or "").strip().lower() == "animal":
                animal_payload = {
                    "creature_type": str(getattr(identity, "creature_type", "") or "").strip().lower(),
                    "taxonomy_class": str(getattr(identity, "taxonomy_class", "") or "").strip().lower(),
                    "species": str(getattr(identity, "species", "") or "").strip().lower(),
                    "common_name": str(getattr(identity, "common_name", "") or "").strip(),
                    "display_name": str(identity.display_name() or "").strip(),
                }
                if physical:
                    animal_payload["size_score"] = float(getattr(physical, "size_score", 0.0) or 0.0)
                    animal_payload["juvenile"] = bool(getattr(physical, "juvenile", False))
                if ecology:
                    animal_payload["ecology_species"] = str(getattr(ecology, "species", "") or "").strip().lower()
            npc_credits = 0
            if inv:
                for entry in list(inv.items):
                    if is_credstick_item(entry.get("item_id")):
                        npc_credits += credstick_total_credits(
                            quantity=entry.get("quantity", 1),
                            metadata=entry.get("metadata"),
                        )

            p2p_bonus = 0
            if source_eid == self.player_eid and npc_credits > 0:
                streetwise = _actor_skill(self.sim, self.player_eid, "streetwise", default=5.0)
                if streetwise >= 6.0:
                    bonus_chips = max(1, int(round((streetwise - 5.0) * 0.6)))
                    self.sim.register_ground_item(
                        item_id="credstick_chip",
                        x=drop_x,
                        y=drop_y,
                        z=drop_z,
                        quantity=bonus_chips,
                        owner_eid=None,
                        owner_tag=None,
                        metadata={"source": "p2p_transfer", "stored_credits": bonus_chips * 20},
                    )
                    p2p_bonus = bonus_chips * 20
                    dropped_items.append({"item_id": "credstick_chip", "quantity": bonus_chips})

            self.sim.remove_entity(eid)
            self.sim.emit(Event(
                "npc_killed",
                target_eid=eid,
                target_name=target_name,
                source_eid=source_eid,
                reason=reason,
                x=drop_x,
                y=drop_y,
                z=drop_z,
                dropped_items=dropped_items,
                npc_role=npc_role,
                npc_credits=npc_credits,
                p2p_bonus=p2p_bonus,
                animal_payload=animal_payload,
            ))

    def _explode(self, projectile, x, y, z):
        radius = int(max(0, projectile.get("explosion_radius", 0)))
        if radius <= 0:
            return 0

        source_eid = projectile.get("source_eid")
        weapon_id = projectile.get("weapon_id")
        base_damage = int(max(1, projectile.get("damage", 1)))
        falloff = float(max(0.0, min(1.0, projectile.get("aoe_falloff", 0.5))))
        cover_penetration = float(max(0.0, min(1.0, projectile.get("cover_penetration", 0.0))))
        positions = self.sim.ecs.get(Position)

        hit_count = 0
        for target_eid, pos in positions.items():
            if pos.z != z:
                continue
            if target_eid == source_eid:
                continue
            dist = _manhattan(x, y, pos.x, pos.y)
            if dist > radius:
                continue

            dist_factor = dist / float(max(1, radius))
            damage_mult = max(0.2, 1.0 - (falloff * dist_factor))
            damage = int(max(1, round(base_damage * damage_mult)))
            hit = self._damage_entity(
                target_eid=target_eid,
                source_eid=source_eid,
                weapon_id=weapon_id,
                raw_damage=damage,
                x=pos.x,
                y=pos.y,
                z=pos.z,
                cover_penetration=cover_penetration,
                damage_kind="explosive",
            )
            if hit:
                hit_count += 1

        self.sim.emit(Event(
            "explosion_triggered",
            source_eid=source_eid,
            weapon_id=weapon_id,
            x=x,
            y=y,
            z=z,
            radius=radius,
            hits=hit_count,
            fire_intensity=int(max(0, projectile.get("fire_intensity", 0) or 0)),
            smoke_intensity=int(max(0, projectile.get("smoke_intensity", 0) or 0)),
            thrown_item_id=projectile.get("thrown_item_id"),
            thrown_item_name=projectile.get("thrown_item_name"),
        ))
        return hit_count

    def _release_projectile_cloud(self, projectile, x, y, z):
        smoke_intensity = int(max(0, projectile.get("smoke_intensity", 0) or 0))
        cloud_radius = int(max(0, projectile.get("cloud_radius", 0) or 0))
        cloud_duration = int(max(0, projectile.get("cloud_duration", 0) or 0))
        aerosol_status = str(projectile.get("aerosol_status", "") or "").strip().lower()
        aerosol_modifiers = projectile.get("aerosol_modifiers") if isinstance(projectile.get("aerosol_modifiers"), dict) else {}
        if smoke_intensity <= 0 and not aerosol_status:
            return False
        radius = max(0, cloud_radius)
        payload = {
            "source_eid": projectile.get("source_eid"),
            "weapon_id": projectile.get("weapon_id"),
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "radius": radius,
            "smoke_intensity": max(1, smoke_intensity),
            "cloud_duration": cloud_duration,
            "thrown_item_id": projectile.get("thrown_item_id"),
            "thrown_item_name": projectile.get("thrown_item_name"),
        }
        if aerosol_status:
            payload.update({
                "aerosol_status": aerosol_status,
                "aerosol_duration": int(max(1, projectile.get("aerosol_duration", 1) or 1)),
                "aerosol_modifiers": dict(aerosol_modifiers),
                "aerosol_exposure_cooldown": int(max(1, projectile.get("aerosol_exposure_cooldown", 6) or 6)),
                "aerosol_label": str(projectile.get("aerosol_label", "") or "").strip(),
            })
        self.sim.emit(Event("smoke_cloud_released", **payload))
        if aerosol_status:
            self.sim.emit(Event("aerosol_cloud_released", **payload))
        return True

    def _impact_projectile(self, projectile_id, projectile, x, y, z, hit_eid=None, reason="impact"):
        hit_count = 0
        source_eid = projectile.get("source_eid")
        weapon_id = projectile.get("weapon_id")
        cover_penetration = float(max(0.0, min(1.0, projectile.get("cover_penetration", 0.0))))

        if hit_eid is not None and int(max(0, projectile.get("damage", 0) or 0)) > 0:
            if self._damage_entity(
                target_eid=hit_eid,
                source_eid=source_eid,
                weapon_id=weapon_id,
                raw_damage=int(max(1, projectile.get("damage", 1))),
                x=x,
                y=y,
                z=z,
                cover_penetration=cover_penetration,
            ):
                hit_count += 1

        if int(projectile.get("explosion_radius", 0)) > 0:
            hit_count += self._explode(projectile, x=x, y=y, z=z)
        cloud_released = self._release_projectile_cloud(projectile, x, y, z)

        self.sim.emit(Event(
            "projectile_impact",
            projectile_id=projectile_id,
            source_eid=source_eid,
            weapon_id=weapon_id,
            x=x,
            y=y,
            z=z,
            hit_eid=hit_eid,
            reason=reason,
            hits=hit_count,
            shatter=bool(projectile.get("shatter", False)),
            thrown_item_id=projectile.get("thrown_item_id"),
            thrown_item_name=projectile.get("thrown_item_name"),
            smoke_cloud=bool(cloud_released),
            aerosol_status=str(projectile.get("aerosol_status", "") or "").strip().lower(),
        ))
        self.sim.remove_projectile(projectile_id)

    def on_weapon_cycle_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return

        loadout = self.sim.ecs.get(WeaponLoadout).get(eid)
        if not loadout or not loadout.weapon_ids:
            self.sim.emit(Event("weapon_cycle_blocked", eid=eid, reason="no_weapons"))
            return

        step = int(event.data.get("step", 1))
        previous = loadout.current_weapon()
        equipped = loadout.cycle(step=step)
        weapon = weapon_by_id(equipped)
        self.sim.emit(Event(
            "weapon_equipped",
            eid=eid,
            previous_weapon_id=previous,
            weapon_id=equipped,
            weapon_name=self._weapon_label(loadout, weapon),
        ))

    def on_weapon_fire_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return

        positions = self.sim.ecs.get(Position)
        vitalities = self.sim.ecs.get(Vitality)
        loadouts = self.sim.ecs.get(WeaponLoadout)

        pos = positions.get(eid)
        loadout = loadouts.get(eid)
        vitality = vitalities.get(eid)
        if not pos or not loadout:
            self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason="no_loadout"))
            return

        if vitality and vitality.downed:
            self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason="downed"))
            return

        weapon_id = loadout.current_weapon()
        if not weapon_id:
            self._resolve_melee_attack(event, eid=eid, source_pos=pos)
            return

        weapon = weapon_by_id(weapon_id)
        weapon_tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
        if "melee" in weapon_tags:
            self._resolve_melee_attack(
                event,
                eid=eid,
                source_pos=pos,
                melee_weapon=weapon,
            )
            return

        instance = self._weapon_instance_data(loadout, weapon_id)
        cooldown_mod = int(instance.get("cooldown_mod", 0))
        cooldown_ticks = max(1, int(weapon.get("cooldown_ticks", 1) + cooldown_mod))
        cooldown_ticks = max(1, int(round(cooldown_ticks * _status_multiplier(
            self.sim,
            eid,
            "weapon_cooldown_mult",
            minimum=0.35,
            maximum=3.0,
        ))))
        if self.sim.tick < loadout.cooldown_until_tick:
            self.sim.emit(Event(
                "weapon_fire_blocked",
                eid=eid,
                reason="cooldown",
                ready_in=max(0, loadout.cooldown_until_tick - self.sim.tick),
            ))
            return

        manual_aim = bool(event.data.get("manual_aim", False))
        if manual_aim:
            target, blocked_reason = self._manual_target(
                eid=eid,
                source_pos=pos,
                weapon=weapon,
                target_x=event.data.get("target_x"),
                target_y=event.data.get("target_y"),
                target_z=event.data.get("target_z", pos.z),
            )
            if not target:
                self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason=blocked_reason or "no_direction"))
                return
        else:
            target = self._acquire_target(
                eid=eid,
                source_pos=pos,
                weapon=weapon,
                preferred_target_eid=event.data.get("target_eid"),
            )
        if not target:
            self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason="no_target"))
            return

        ammo_ok, ammo_remaining = self._consume_player_weapon_ammo(
            eid=eid,
            loadout=loadout,
            weapon=weapon,
        )
        if not ammo_ok:
            self.sim.emit(Event(
                "weapon_fire_blocked",
                eid=eid,
                reason="no_ammo",
                weapon_id=weapon_id,
                ammo_remaining=int(ammo_remaining or 0),
            ))
            return

        projectile_ids = self._spawn_projectiles(
            eid=eid,
            pos=pos,
            loadout=loadout,
            weapon=weapon,
            target=target,
            shot_mode="free_aim" if manual_aim else "locked",
        )
        if not projectile_ids:
            self.sim.emit(Event("weapon_fire_blocked", eid=eid, reason="no_direction"))
            return
        loadout.last_fire_tick = self.sim.tick
        loadout.cooldown_until_tick = self.sim.tick + cooldown_ticks

        preview = _manual_fire_preview(self.sim, eid=eid, x=target["x"], y=target["y"], z=target["z"])
        direction_short = str(preview.get("direction_short", "")).strip()
        direction_label = _dir_label(preview.get("direction_step"), short=False)
        target_name = ""
        impact_eid = preview.get("impact_eid")
        target_eid = impact_eid if impact_eid is not None else target.get("target_eid")
        if target_eid is not None:
            target_name = f"{_entity_display_name(self.sim, target_eid, title_case=False)}#{target_eid}"

        self.sim.emit(Event(
            "weapon_fired",
            eid=eid,
            weapon_id=weapon["id"],
            weapon_name=self._weapon_label(loadout, weapon),
            projectile_count=len(projectile_ids),
            target_eid=target_eid,
            target_x=target.get("x"),
            target_y=target.get("y"),
            target_z=target.get("z"),
            target_dist=target.get("dist"),
            target_name=target_name,
            manual_aim=manual_aim,
            shot_mode="free_aim" if manual_aim else "locked",
            direction_short=direction_short,
            direction_label=direction_label,
            trajectory=weapon.get("trajectory", "ballistic"),
            ammo_remaining=ammo_remaining,
        ))

        self.sim.emit(Event(
            "noise",
            source_eid=eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            radius=int(max(1, weapon.get("noise_radius", 6))),
            cause="fire_weapon",
            target_eid=target_eid,
        ))

        context = "explosive_discharge" if int(weapon.get("explosion_radius", 0)) > 0 else "armed_assault"
        score = None
        offense_profile = None
        if int(weapon.get("explosion_radius", 0)) <= 0:
            offense_profile = self._wildlife_offense_profile(target_eid, action="fire_weapon")
            if isinstance(offense_profile, dict):
                context = str(offense_profile.get("context", context) or context).strip().lower() or context
                score = int(offense_profile.get("score", 0) or 0)
        target_x = int(target.get("x", pos.x))
        target_y = int(target.get("y", pos.y))
        target_z = int(target.get("z", pos.z))
        target_prop = self.sim.property_covering(target_x, target_y, target_z) if hasattr(self.sim, "property_covering") else None
        self._emit_action_offense(
            eid=eid,
            action="fire_weapon",
            context=context,
            score=score,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            target_eid=target_eid,
            victim_eid=target_eid,
            victim_name=target_name,
            target_name=target_name,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
            property_id=(target_prop or {}).get("id"),
            property_name=(target_prop or {}).get("name"),
            target_taxonomy=str((offense_profile or {}).get("target_taxonomy", "") or "").strip().lower(),
        )

    def on_melee_attack_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return
        pos = self.sim.ecs.get(Position).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        if not pos:
            return
        if vitality and vitality.downed:
            return
        self._resolve_melee_attack(event, eid=eid, source_pos=pos)

    def update(self):
        self._resolve_downed_player_death()
        self._resolve_downed_npc_deaths()
        if not self.sim.projectiles:
            return

        for projectile_id, projectile in list(self.sim.projectiles.items()):
            projectile["travel_bank"] = float(projectile.get("travel_bank", 0.0)) + float(projectile.get("speed", 1.0))
            steps = int(projectile["travel_bank"])
            projectile["travel_bank"] -= steps
            if steps <= 0:
                continue

            z = int(projectile.get("z", 0))
            path = list(projectile.get("path", []) or [])
            path_index = int(projectile.get("path_index", 0))
            for _ in range(steps):
                if path_index >= len(path):
                    self._impact_projectile(
                        projectile_id,
                        projectile,
                        x=int(projectile.get("x", 0)),
                        y=int(projectile.get("y", 0)),
                        z=z,
                        reason="range_end",
                    )
                    break

                nx, ny = path[path_index]
                path_index += 1
                if self.sim.detail_for_xy(nx, ny) == "unloaded" or not self.sim.tilemap.in_bounds(nx, ny):
                    self._impact_projectile(
                        projectile_id,
                        projectile,
                        x=int(projectile.get("x", 0)),
                        y=int(projectile.get("y", 0)),
                        z=z,
                        reason="out_of_bounds",
                    )
                    break

                tile = self.sim.tilemap.tile_at(nx, ny, z)
                blocked_tile = bool(tile and not tile.walkable)
                if blocked_tile and not projectile.get("ignore_walls"):
                    shattered_window = False
                    damaged_structure = False
                    breached_structure = False
                    if tile and tile.transparent:
                        shattered_window = _shatter_window_for_projectile(
                            self.sim,
                            projectile.get("source_eid"),
                            nx,
                            ny,
                            z,
                            damage_amount=projectile.get("damage", 1),
                            weapon_id=projectile.get("weapon_id", ""),
                        )
                    if not shattered_window:
                        prop = self.sim.property_covering(nx, ny, z) if hasattr(self.sim, "property_covering") else None
                        kind = _structural_surface_kind(self.sim, prop, nx, ny, z, tile=tile)
                        if kind:
                            result = _apply_structural_damage(
                                self.sim,
                                prop,
                                nx,
                                ny,
                                z,
                                amount=max(1, int(projectile.get("damage", 1) or 1)),
                                kind=kind,
                                cause="projectile_impact",
                                damage_kind="ballistic",
                                weapon_id=projectile.get("weapon_id", ""),
                                offender_eid=projectile.get("source_eid"),
                            )
                            damaged_structure = bool(isinstance(result, dict) and result.get("damaged"))
                            breached_structure = bool(isinstance(result, dict) and result.get("broken"))
                    self._impact_projectile(
                        projectile_id,
                        projectile,
                        x=nx,
                        y=ny,
                        z=z,
                        reason=(
                            "shattered_window"
                            if shattered_window
                            else "breached_structure"
                            if breached_structure
                            else "damaged_structure"
                            if damaged_structure
                            else "blocked_tile"
                        ),
                    )
                    break

                shot_mode = str(projectile.get("shot_mode", "free_aim") or "free_aim").strip().lower()
                hit_eid = self._first_projectile_hit_entity_at(
                    nx,
                    ny,
                    z,
                    exclude_eid=projectile.get("source_eid"),
                    skip_downed=shot_mode == "locked",
                )

                projectile["x"] = nx
                projectile["y"] = ny
                projectile["path_index"] = path_index
                projectile["remaining_range"] = max(0, len(path) - path_index)
                if hit_eid is not None:
                    self._impact_projectile(
                        projectile_id,
                        projectile,
                        x=nx,
                        y=ny,
                        z=z,
                        hit_eid=hit_eid,
                        reason="entity_hit",
                    )
                    break


def _forced_attack_active(ai, tick):
    if ai is None:
        return False
    reason = str(getattr(ai, "force_attack_reason", "") or "").strip().lower()
    if not reason:
        return False
    try:
        until_tick = int(getattr(ai, "force_attack_until_tick", 0) or 0)
    except (TypeError, ValueError):
        until_tick = 0
    return until_tick >= int(tick)


def _clear_forced_attack(ai):
    if ai is None:
        return
    ai.force_attack_until_tick = 0
    ai.force_attack_reason = ""


class NPCWeaponSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.rng = random.Random(f"{sim.seed}:npc_weapon_system")

    def update(self):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        loadouts = self.sim.ecs.get(WeaponLoadout)
        profiles = self.sim.ecs.get(WeaponUseProfile)
        vitalities = self.sim.ecs.get(Vitality)
        needs_map = self.sim.ecs.get(NPCNeeds)
        traits_map = self.sim.ecs.get(NPCTraits)
        suppressions = self.sim.ecs.get(SuppressionState)

        for eid, ai in ais.items():
            if eid == self.player_eid:
                continue
            loadout = loadouts.get(eid)
            pos = positions.get(eid)
            profile = profiles.get(eid)
            vitality = vitalities.get(eid)
            if not ai or not pos:
                continue
            if vitality and vitality.downed:
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                continue
            if ai.state != "protecting":
                continue
            if ai.target_eid is None:
                continue
            forced_attack = _forced_attack_active(ai, self.sim.tick)
            if not forced_attack and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue

            target_eid = ai.target_eid
            if local_interactions_suspended_for_actor(self.sim, target_eid):
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
                continue
            target_pos = positions.get(target_eid)
            target_vitality = vitalities.get(target_eid)
            if not target_pos or target_pos.z != pos.z:
                continue
            if target_vitality and target_vitality.downed:
                continue

            suppression = suppressions.get(eid)
            if suppression and suppression.surrendered:
                continue

            needs = needs_map.get(eid)
            traits = traits_map.get(eid) or NPCTraits()
            has_weapon = bool(loadout and loadout.weapon_ids and loadout.current_weapon())
            if not has_weapon:
                dist = _grid_distance(pos.x, pos.y, target_pos.x, target_pos.y)
                if dist > 1:
                    continue
                if not forced_attack:
                    metrics = _npc_combat_metrics(
                        needs=needs,
                        traits=traits,
                        vitality=vitality,
                        suppression=suppression,
                        weapon=None,
                        **_npc_status_metric_args(self.sim, eid),
                    )
                    if metrics["retreat_bias"] < 0.38:
                        aggression = float(getattr(profile, "aggression", 0.55) if profile else 0.55)
                        commit = (aggression * 0.55) + (metrics["assault_bias"] * 0.6) - (metrics["retreat_bias"] * 0.7)
                        if self.rng.random() > max(0.32, min(0.92, commit + 0.24)):
                            continue
                self.sim.emit(Event(
                    "melee_attack_request",
                    eid=eid,
                    target_eid=target_eid,
                    reason="justice_vehicle_misuse_forced" if forced_attack else "npc_auto_melee",
                ))
                if forced_attack:
                    _clear_forced_attack(ai)
                continue

            if self.sim.tick < loadout.cooldown_until_tick:
                continue
            if not profile:
                continue

            # Suppressed NPCs hesitate; pinned NPCs won't fire at all.
            if not forced_attack and suppression and suppression.pinned():
                if self.rng.random() < 0.82:
                    continue

            dist = _grid_distance(pos.x, pos.y, target_pos.x, target_pos.y)
            weapon = weapon_by_id(loadout.current_weapon())
            if _weapon_is_melee(weapon) and dist > 1:
                best_alt = None
                best_alt_range = -1
                for weapon_id in loadout.weapon_ids:
                    alt_weapon = weapon_by_id(weapon_id)
                    if _weapon_is_melee(alt_weapon):
                        continue
                    alt_range = int(max(1, alt_weapon.get("range", 1)))
                    if alt_range > best_alt_range:
                        best_alt = weapon_id
                        best_alt_range = alt_range
                if best_alt:
                    loadout.equip(best_alt)
                    weapon = weapon_by_id(loadout.current_weapon())

            metrics = _npc_combat_metrics(
                needs=needs,
                traits=traits,
                vitality=vitality,
                suppression=suppression,
                weapon=weapon,
                **_npc_status_metric_args(self.sim, eid),
            )
            if int(weapon.get("explosion_radius", 0)) > 0 and not profile.allow_explosives:
                continue

            max_range = min(int(weapon.get("range", 1)), int(profile.max_range))
            if dist < profile.min_range or dist > max_range:
                continue

            viability = _weapon_target_viability(
                self.sim,
                source_eid=eid,
                source_pos=pos,
                weapon=weapon,
                target_x=target_pos.x,
                target_y=target_pos.y,
                target_z=target_pos.z,
                target_eid=target_eid,
            )
            if not viability.get("ok"):
                continue

            accuracy = profile.aim_bias - ((dist / float(max(1, max_range))) * 0.35)
            accuracy *= _status_multiplier(
                self.sim,
                eid,
                "ranged_accuracy_mult",
                minimum=0.25,
                maximum=2.0,
            )
            # Suppression degrades accuracy.
            if suppression and suppression.shaken():
                steady = _status_modifier_total(self.sim, eid, "suppression_resist_mult", default=0.0)
                suppression_penalty = max(0.15, suppression.pressure * max(0.18, 0.55 - steady))
                accuracy *= max(0.25, 1.0 - suppression_penalty)
            aggression_roll = profile.aggression * 0.85
            if _weapon_is_melee(weapon):
                aggression_roll *= max(0.35, 0.45 + (metrics["assault_bias"] * 0.8) - (metrics["retreat_bias"] * 0.5))
            if not forced_attack and self.rng.random() > max(0.12, min(0.96, accuracy * aggression_roll + 0.18)):
                continue

            if not forced_attack and profile.cooldown_jitter > 0 and self.rng.randint(0, profile.cooldown_jitter) > 0:
                continue

            self.sim.emit(Event(
                "weapon_fire_request",
                eid=eid,
                target_eid=target_eid,
                reason="justice_vehicle_misuse_forced" if forced_attack else "npc_auto",
            ))
            if forced_attack:
                _clear_forced_attack(ai)


class StatusEffectSystem(System):

    def update(self):
        effects_map = self.sim.ecs.get(StatusEffects)
        substance_map = self.sim.ecs.get(SubstanceUseState)
        needs_map = self.sim.ecs.get(NPCNeeds)
        positions = self.sim.ecs.get(Position)
        vitalities = self.sim.ecs.get(Vitality)

        for eid, effects in effects_map.items():
            pos = positions.get(eid)
            if pos and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue

            modifiers = effects.modifiers_sum()
            needs = needs_map.get(eid)
            if needs:
                energy_delta = _float_or_default(modifiers.get("energy_tick_delta", 0.0), 0.0)
                safety_delta = _float_or_default(modifiers.get("safety_tick_delta", 0.0), 0.0)
                social_delta = _float_or_default(modifiers.get("social_tick_delta", 0.0), 0.0)
                hunger_delta = _float_or_default(modifiers.get("hunger_tick_delta", 0.0), 0.0)
                thirst_delta = _float_or_default(modifiers.get("thirst_tick_delta", 0.0), 0.0)

                if energy_delta:
                    needs.energy = _clamp(needs.energy + energy_delta)
                if safety_delta:
                    needs.safety = _clamp(needs.safety + safety_delta)
                if social_delta:
                    needs.social = _clamp(needs.social + social_delta)
                if hunger_delta and hasattr(needs, "hunger"):
                    needs.hunger = _clamp(needs.hunger + hunger_delta)
                if thirst_delta and hasattr(needs, "thirst"):
                    needs.thirst = _clamp(needs.thirst + thirst_delta)

            vitality = vitalities.get(eid)
            hp_tick_delta = _float_or_default(modifiers.get("hp_tick_delta", 0.0), 0.0)
            if vitality and not vitality.downed and hp_tick_delta:
                hp_step = _status_tick_step(effects, "hp_tick_delta", hp_tick_delta)
                if hp_step > 0 and vitality.hp < vitality.max_hp:
                    vitality.hp = min(vitality.max_hp, vitality.hp + hp_step)
                elif hp_step < 0 and vitality.hp > 1:
                    vitality.hp = max(1, vitality.hp + hp_step)
            toxicity_tick_delta = max(0.0, _float_or_default(modifiers.get("toxicity_tick_delta", 0.0), 0.0))
            if vitality and not vitality.downed and toxicity_tick_delta:
                toxin_step = _status_tick_step(effects, "toxicity_tick_delta", toxicity_tick_delta)
                if toxin_step > 0 and vitality.hp > 1:
                    vitality.hp = max(1, vitality.hp - toxin_step)

            expired = effects.tick()
            for status in expired:
                self.sim.emit(Event(
                    "status_expired",
                    eid=eid,
                    status=status,
                ))

        for eid, substance_state in substance_map.items():
            pos = positions.get(eid)
            if pos and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue
            statuses = effects_map.get(eid)
            if not statuses or not substance_state:
                continue
            pending = substance_state.advance(
                int(getattr(self.sim, "tick", 0) or 0),
                statuses=statuses,
            )
            for queued in pending:
                status = str(queued.get("status", "") or "").strip().lower()
                if not status:
                    continue
                duration = max(1, _int_or_default(queued.get("duration", 1), 1))
                modifiers = queued.get("modifiers", {})
                if not isinstance(modifiers, dict):
                    modifiers = {}
                is_new = statuses.add(
                    status=status,
                    duration=duration,
                    modifiers=modifiers,
                    source_item=str(queued.get("substance_id", "") or "").strip().lower() or None,
                )
                self.sim.emit(Event(
                    "status_applied",
                    eid=eid,
                    status=status,
                    duration=duration,
                    source_item=str(queued.get("substance_id", "") or "").strip().lower(),
                    modifiers=dict(modifiers),
                    new=is_new,
                ))


class NPCItemUseSystem(System):
    FIELD_RESCUE_PROFESSION_TOKENS = frozenset({
        "biotech",
        "clinic",
        "clinician",
        "doctor",
        "medic",
        "medical",
        "nurse",
        "paramedic",
        "pharmacist",
        "pharmacy",
        "triage",
        "trauma",
    })
    FIELD_RESCUE_HOSTILE_STATES = frozenset({
        "attacking",
        "chasing",
        "ejecting_target",
        "investigating",
        "protecting",
    })
    FIELD_RESCUE_DEFER_STATES = frozenset({
        "downed",
        "evading_authority",
        "fleeing",
        "seeking_safety",
        "surrendered",
    })
    FIELD_RESCUE_PROFESSIONAL_RADIUS = 8
    FIELD_RESCUE_HERO_RADIUS = 6

    def __init__(self, sim):
        super().__init__(sim)
        self.catalog = ITEM_CATALOG
        self.sim.events.subscribe("npc_help_arrived", self.on_npc_help_arrived)

    def _item_can_recover_downed_actor(self, item_def):
        return _runtime_item_can_recover_downed_actor(item_def)

    def _field_rescue_item(self, inventory):
        entry, item_def, _restore_hp = _smallest_recovery_item_for_downed_actor(inventory, self.catalog)
        return entry, item_def

    def _occupation(self, eid):
        return self.sim.ecs.get(Occupation).get(eid)

    def _workplace_property(self, occupation):
        workplace = getattr(occupation, "workplace", None)
        property_id = ""
        if isinstance(workplace, dict):
            property_id = str(workplace.get("property_id", workplace.get("id", "")) or "").strip()
        elif workplace:
            property_id = str(workplace).strip()
        if not property_id:
            return None
        prop = getattr(self.sim, "properties", {}).get(property_id)
        return prop if isinstance(prop, dict) else None

    def _property_has_medical_role(self, prop):
        if not isinstance(prop, dict):
            return False
        metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
        fields = [
            prop.get("name"),
            prop.get("kind"),
            prop.get("category"),
            prop.get("archetype"),
            metadata.get("category"),
            metadata.get("archetype"),
            metadata.get("fixture_type"),
            metadata.get("interaction_role"),
        ]
        services = []
        for key in ("services", "site_services", "service_ids"):
            value = prop.get(key, metadata.get(key))
            if isinstance(value, (list, tuple, set)):
                services.extend(str(item) for item in value)
            elif value:
                services.append(str(value))
        fields.extend(services)
        text = " ".join(str(field or "").replace("_", " ").lower() for field in fields)
        if "medical" in {str(service).strip().lower() for service in services}:
            return True
        return any(token in text for token in self.FIELD_RESCUE_PROFESSION_TOKENS)

    def _is_field_rescue_professional(self, eid, *, ai=None):
        ai = ai or self.sim.ecs.get(AI).get(eid)
        occupation = self._occupation(eid)
        identity = self.sim.ecs.get(CreatureIdentity).get(eid)
        prop = self._workplace_property(occupation)
        fields = [
            getattr(ai, "role", ""),
            getattr(occupation, "career", ""),
            getattr(identity, "common_name", ""),
            getattr(identity, "creature_type", ""),
        ]
        text = " ".join(str(field or "").replace("_", " ").lower() for field in fields)
        return any(token in text for token in self.FIELD_RESCUE_PROFESSION_TOKENS) or self._property_has_medical_role(prop)

    def _bond_for(self, social, target_eid):
        if social is None or target_eid is None:
            return None
        bonds = getattr(social, "bonds", {})
        if not isinstance(bonds, dict):
            return None
        keys = [target_eid]
        try:
            keys.append(int(target_eid))
        except (TypeError, ValueError):
            pass
        keys.append(str(target_eid))
        for key in keys:
            bond = bonds.get(key)
            if isinstance(bond, dict):
                return bond
        return None

    def _bond_rescue_score(self, social, target_eid):
        bond = self._bond_for(social, target_eid)
        if not isinstance(bond, dict):
            return 0.0
        values = []
        for key in ("trust", "closeness", "protectiveness"):
            try:
                values.append(float(bond.get(key, 0.0) or 0.0))
            except (TypeError, ValueError):
                values.append(0.0)
        return max(values or [0.0])

    def _is_following_target(self, ai, will, target_eid):
        for state, target in (
            (getattr(ai, "state", None), getattr(ai, "target_eid", None)),
            (getattr(will, "intent", None), getattr(will, "target_eid", None)),
        ):
            if str(state or "").strip().lower() != "following":
                continue
            try:
                if int(target) == int(target_eid):
                    return True
            except (TypeError, ValueError):
                if target == target_eid:
                    return True
        return False

    def _field_rescue_tie_score(self, rescuer_eid, target_eid, *, ai=None, will=None, social=None):
        score = self._bond_rescue_score(social, target_eid)
        if self._is_following_target(ai, will, target_eid):
            score = max(score, 0.85)
        if active_contractor_record(self.sim, rescuer_eid, ally_eid=target_eid, jobs={"backup", "party"}):
            score = max(score, 0.95)
        return score

    def _eid_equal(self, left, right):
        if left is None or right is None:
            return False
        try:
            return int(left) == int(right)
        except (TypeError, ValueError):
            return left == right

    def _actor_targets_actor_hostile(self, source_eid, target_eid):
        ai = self.sim.ecs.get(AI).get(source_eid)
        will = self.sim.ecs.get(NPCWill).get(source_eid)
        checks = (
            (getattr(ai, "state", None), getattr(ai, "target_eid", None)),
            (getattr(will, "intent", None), getattr(will, "target_eid", None)),
        )
        for state, target in checks:
            if str(state or "").strip().lower() in self.FIELD_RESCUE_HOSTILE_STATES and self._eid_equal(target, target_eid):
                return True
        return False

    def _is_field_rescue_non_hostile(self, rescuer_eid, target_eid, *, rescuer_tie_to_player=0.0):
        if self._eid_equal(rescuer_eid, target_eid):
            return False
        if self._actor_targets_actor_hostile(rescuer_eid, target_eid):
            return False
        if self._actor_targets_actor_hostile(target_eid, rescuer_eid):
            return False
        player_eid = getattr(self.sim, "player_eid", None)
        if player_eid is not None:
            if self._actor_targets_actor_hostile(rescuer_eid, player_eid) and self._eid_equal(target_eid, player_eid):
                return False
            if rescuer_tie_to_player >= 0.55 and self._actor_targets_actor_hostile(target_eid, player_eid):
                return False
        return True

    def _field_rescue_has_los(self, pos, target_pos):
        if not pos or not target_pos:
            return False
        if int(pos.z) != int(target_pos.z):
            return False
        try:
            return bool(
                _has_line_of_sight(
                    self.sim,
                    int(pos.x),
                    int(pos.y),
                    int(pos.z),
                    int(target_pos.x),
                    int(target_pos.y),
                    int(target_pos.z),
                )
            )
        except Exception:  # noqa: BLE001 - malformed test maps should fail open like other local sensing
            return True

    def _field_rescue_candidate_for_target(self, rescuer_eid, target_eid, *, ai, inventory, pos, entry=None, item_def=None):
        if self._eid_equal(rescuer_eid, target_eid):
            return None
        if entry is None or item_def is None:
            entry, item_def = self._field_rescue_item(inventory)
        if entry is None or item_def is None:
            return None

        positions = self.sim.ecs.get(Position)
        vitalities = self.sim.ecs.get(Vitality)
        target_pos = positions.get(target_eid)
        target_vitality = vitalities.get(target_eid)
        if not target_pos or not target_vitality or not bool(getattr(target_vitality, "downed", False)):
            return None
        if getattr(target_vitality, "death_reported_tick", None) is not None:
            return None
        if int(target_pos.z) != int(pos.z):
            return None
        distance = _manhattan(pos.x, pos.y, target_pos.x, target_pos.y)

        will = self.sim.ecs.get(NPCWill).get(rescuer_eid)
        social = self.sim.ecs.get(NPCSocial).get(rescuer_eid)
        player_eid = getattr(self.sim, "player_eid", None)
        tie_to_player = self._field_rescue_tie_score(
            rescuer_eid,
            player_eid,
            ai=ai,
            will=will,
            social=social,
        ) if player_eid is not None else 0.0
        if not self._is_field_rescue_non_hostile(rescuer_eid, target_eid, rescuer_tie_to_player=tie_to_player):
            return None

        professional = self._is_field_rescue_professional(rescuer_eid, ai=ai)
        tie_score = self._field_rescue_tie_score(
            rescuer_eid,
            target_eid,
            ai=ai,
            will=will,
            social=social,
        )
        max_radius = self.FIELD_RESCUE_PROFESSIONAL_RADIUS if professional else self.FIELD_RESCUE_HERO_RADIUS
        if distance > max_radius:
            return None
        if distance > 1 and not self._field_rescue_has_los(pos, target_pos):
            return None
        if not professional and tie_score < 0.55:
            return None

        age = 0
        try:
            age = max(0, int(getattr(self.sim, "tick", 0)) - int(getattr(target_vitality, "downed_tick", 0) or 0))
        except (TypeError, ValueError):
            age = 0
        score = 30.0 if professional else 18.0 + (tie_score * 42.0)
        if self._eid_equal(target_eid, player_eid):
            score += 60.0
            bleedout_ticks = int(getattr(self.sim, "player_bleedout_ticks", 0) or 0)
            if bleedout_ticks > 0:
                remaining = max(0, bleedout_ticks - age)
                score += max(0.0, float(bleedout_ticks - remaining) * 3.0)
        score += min(18.0, float(age) * 0.75)
        score -= float(distance) * 3.0
        return {
            "target_eid": target_eid,
            "target_pos": target_pos,
            "target_vitality": target_vitality,
            "entry": entry,
            "item_def": item_def,
            "distance": int(distance),
            "professional": bool(professional),
            "tie_score": float(tie_score),
            "score": float(score),
        }

    def _best_field_rescue_candidate(self, rescuer_eid, *, ai, inventory, pos):
        entry, item_def = self._field_rescue_item(inventory)
        if entry is None or item_def is None:
            return None
        best = None
        for target_eid in sorted(self.sim.ecs.get(Vitality).keys()):
            candidate = self._field_rescue_candidate_for_target(
                rescuer_eid,
                target_eid,
                ai=ai,
                inventory=inventory,
                pos=pos,
                entry=entry,
                item_def=item_def,
            )
            if candidate is None:
                continue
            if best is None or (candidate["score"], -candidate["distance"], -int(candidate["target_eid"])) > (
                best["score"],
                -best["distance"],
                -int(best["target_eid"]),
            ):
                best = candidate
        return best

    def _clear_field_rescue_intent(self, eid, ai=None):
        ai = ai or self.sim.ecs.get(AI).get(eid)
        if ai and str(getattr(ai, "state", "") or "").strip().lower() == "helping_victim":
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None
        will = self.sim.ecs.get(NPCWill).get(eid)
        if will and str(getattr(will, "intent", "") or "").strip().lower() == "helping_victim":
            will.intent = "idle"
            will.score = 0.0
            will.target = None
            will.target_eid = None
            will.last_tick = int(getattr(self.sim, "tick", 0))

    def _start_field_rescue(self, rescuer_eid, candidate, *, ai, profile):
        target_pos = candidate["target_pos"]
        target = (int(target_pos.x), int(target_pos.y), int(target_pos.z))
        if str(getattr(ai, "state", "") or "").strip().lower() == "helping_victim" and self._eid_equal(
            getattr(ai, "target_eid", None),
            candidate["target_eid"],
        ):
            return True
        ai.state = "helping_victim"
        ai.target = target
        ai.target_eid = candidate["target_eid"]
        will = self.sim.ecs.get(NPCWill).get(rescuer_eid)
        if will:
            will.intent = "helping_victim"
            will.score = max(float(getattr(will, "score", 0.0) or 0.0), 76.0)
            will.target = target
            will.target_eid = candidate["target_eid"]
            will.last_tick = int(getattr(self.sim, "tick", 0))
        item_def = candidate["item_def"]
        item_name = item_display_name(
            item_def.get("id"),
            metadata=candidate["entry"].get("metadata"),
            item_catalog=self.catalog,
        )
        self.sim.emit(Event(
            "npc_medical_rescue_started",
            rescuer_eid=rescuer_eid,
            target_eid=candidate["target_eid"],
            item_id=item_def.get("id"),
            item_name=item_name,
            professional=bool(candidate.get("professional")),
            distance=int(candidate.get("distance", 0)),
            x=int(target_pos.x),
            y=int(target_pos.y),
            z=int(target_pos.z),
        ))
        return True

    def _apply_field_rescue(self, rescuer_eid, candidate, *, ai=None, profile=None):
        inventory = self.sim.ecs.get(Inventory).get(rescuer_eid)
        if not inventory:
            return False
        target_eid = candidate["target_eid"]
        target_pos = self.sim.ecs.get(Position).get(target_eid)
        rescuer_pos = self.sim.ecs.get(Position).get(rescuer_eid)
        if not target_pos or not rescuer_pos or int(target_pos.z) != int(rescuer_pos.z):
            return False
        if _manhattan(rescuer_pos.x, rescuer_pos.y, target_pos.x, target_pos.y) > 1:
            return False
        target_vitality = self.sim.ecs.get(Vitality).get(target_eid)
        if not target_vitality or not bool(getattr(target_vitality, "downed", False)):
            self._clear_field_rescue_intent(rescuer_eid, ai=ai)
            return False

        entry = inventory.find(instance_id=candidate["entry"].get("instance_id"))
        item_def = self.catalog.get((entry or {}).get("item_id"))
        if entry is None or not item_def or not self._item_can_recover_downed_actor(item_def):
            self._clear_field_rescue_intent(rescuer_eid, ai=ai)
            return False

        item_name = item_display_name(
            item_def.get("id"),
            metadata=entry.get("metadata"),
            item_catalog=self.catalog,
        )
        removed = inventory.remove_item(instance_id=entry["instance_id"], quantity=1)
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
        if profile:
            profile.last_use_tick = int(getattr(self.sim, "tick", 0))
        self._clear_field_rescue_intent(rescuer_eid, ai=ai)

        self.sim.emit(Event(
            "item_used",
            eid=rescuer_eid,
            target_eid=target_eid,
            item_id=item_def.get("id"),
            item_name=item_name,
            reason="npc_field_rescue",
            usage_kind="field_rescue",
            applied=applied,
            consumed=True,
            item_metadata=item_metadata,
            x=int(rescuer_pos.x),
            y=int(rescuer_pos.y),
            z=int(rescuer_pos.z),
        ))
        payload = {
            "rescuer_eid": rescuer_eid,
            "target_eid": target_eid,
            "item_id": item_def.get("id"),
            "item_name": item_name,
            "recovered_hp": int(recovered_hp),
            "max_hp": int(max_hp),
            "professional": bool(candidate.get("professional")),
            "applied": applied,
            "x": int(target_pos.x),
            "y": int(target_pos.y),
            "z": int(target_pos.z),
        }
        self.sim.emit(Event("npc_medical_rescue_applied", **payload))
        if self._eid_equal(target_eid, getattr(self.sim, "player_eid", None)):
            self.sim.emit(Event(
                "player_recovered_from_downed",
                eid=target_eid,
                **payload,
            ))
        else:
            self.sim.emit(Event("npc_recovered_from_downed", eid=target_eid, **payload))
        return True

    def _maybe_field_rescue(self, eid, profile, ai, inventory, pos):
        state = str(getattr(ai, "state", "") or "").strip().lower()
        if state in self.FIELD_RESCUE_DEFER_STATES:
            return False
        if state == "helping_victim" and getattr(ai, "target_eid", None) is not None:
            candidate = self._field_rescue_candidate_for_target(
                eid,
                ai.target_eid,
                ai=ai,
                inventory=inventory,
                pos=pos,
            )
            if candidate is None:
                self._clear_field_rescue_intent(eid, ai=ai)
                return False
            if candidate["distance"] <= 1:
                return self._apply_field_rescue(eid, candidate, ai=ai, profile=profile)
            return True

        candidate = self._best_field_rescue_candidate(eid, ai=ai, inventory=inventory, pos=pos)
        if candidate is None:
            return False
        if candidate["distance"] <= 1:
            return self._apply_field_rescue(eid, candidate, ai=ai, profile=profile)
        return self._start_field_rescue(eid, candidate, ai=ai, profile=profile)

    def _tactical_throw_score(self, eid, ai, item_def, throw_profile, *, dist, profile, traits, justice, workplace_prop=None):
        role = str(getattr(ai, "role", "") or "").strip().lower()
        archetype = str(((workplace_prop or {}).get("metadata", {}) or {}).get("archetype", "") or "").strip().lower()
        tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
        qualified = role in {"guard", "thief"} or archetype in {
            "checkpoint",
            "police_precinct",
            "military_post",
            "armory",
            "chop_shop",
            "junk_market",
            "warehouse",
            "factory",
        }
        if not qualified:
            return 0.0
        max_range = max(1, _int_or_default(throw_profile.get("range"), 5))
        cloud_radius = max(0, _int_or_default(throw_profile.get("cloud_radius"), 0))
        if int(dist) <= max(1, cloud_radius) or int(dist) > max_range:
            return 0.0
        score = float(profile.risk_tolerance) + (float(getattr(traits, "discipline", 0.0) or 0.0) * 0.18)
        if int(throw_profile.get("smoke_intensity", 0) or 0) > 0:
            score += 0.22
        if str(throw_profile.get("aerosol_status", "") or "").strip():
            score += 0.2
        legal_status = str(item_def.get("legal_status", "")).strip().lower()
        if role == "guard" and legal_status == "restricted":
            score += 0.16
        if int(throw_profile.get("fire_intensity", 0) or 0) > 0 or int(throw_profile.get("explosion_radius", 0) or 0) > 0:
            score += 0.1 if profile.risk_tolerance >= 0.62 else -0.28
        if "illegal" in tags or legal_status == "illegal":
            justice_severity = (
                (_justice_level(justice, default=0.4) * 0.7)
                + (_crime_sensitivity(justice, default=0.4) * 0.3)
            )
            score -= (0.38 + (justice_severity * 0.22)) * (1.0 - profile.risk_tolerance)
        return max(0.0, score)

    def _maybe_tactical_throw(self, eid, profile, ai, inventory, pos, target_pos, *, traits, justice):
        if not ai or not inventory or not pos or not target_pos:
            return False
        dist = _grid_distance(pos.x, pos.y, target_pos.x, target_pos.y)
        occupation = self._occupation(eid)
        workplace_prop = self._workplace_property(occupation)
        best_entry = None
        best_score = 0.0
        for entry in list(inventory.items):
            item_def = self.catalog.get(entry.get("item_id"))
            if not isinstance(item_def, dict):
                continue
            throw_profile = item_def.get("throw_profile") if isinstance(item_def.get("throw_profile"), dict) else None
            if not throw_profile:
                continue
            score = self._tactical_throw_score(
                eid,
                ai,
                item_def,
                throw_profile,
                dist=dist,
                profile=profile,
                traits=traits,
                justice=justice,
                workplace_prop=workplace_prop,
            )
            if score > best_score:
                best_score = score
                best_entry = entry
        if not best_entry or best_score < 0.58:
            return False
        roll = random.Random(
            f"{getattr(self.sim, 'seed', 0)}:npc_tactical_throw:{getattr(self.sim, 'tick', 0)}:{eid}:{best_entry.get('instance_id')}"
        ).random()
        if roll > min(0.72, best_score):
            return False
        profile.last_use_tick = int(getattr(self.sim, "tick", 0))
        self.sim.emit(Event(
            "throw_item_request",
            eid=eid,
            item_instance_id=best_entry.get("instance_id"),
            target_x=int(target_pos.x),
            target_y=int(target_pos.y),
            target_z=int(target_pos.z),
            reason="npc_tactical_throw",
        ))
        return True

    def on_npc_help_arrived(self, event):
        eid = event.data.get("npc_eid")
        target_eid = event.data.get("target_eid")
        if eid is None or target_eid is None:
            return
        profile = self.sim.ecs.get(ItemUseProfile).get(eid)
        if profile is None or not bool(getattr(profile, "auto_use", False)):
            return
        inventory = self.sim.ecs.get(Inventory).get(eid)
        ai = self.sim.ecs.get(AI).get(eid)
        pos = self.sim.ecs.get(Position).get(eid)
        if not inventory or not ai or not pos:
            return
        if _entity_is_downed(self.sim, eid):
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
            return
        candidate = self._field_rescue_candidate_for_target(
            eid,
            target_eid,
            ai=ai,
            inventory=inventory,
            pos=pos,
        )
        if candidate is not None and int(candidate.get("distance", 99)) <= 1:
            self._apply_field_rescue(eid, candidate, ai=ai, profile=profile)

    def _status_refresh_scale(self, effects, status, duration, modifiers):
        if not effects or not status or not isinstance(getattr(effects, "active", None), dict):
            return 1.0
        current = effects.active.get(str(status))
        if not isinstance(current, dict):
            return 1.0

        remaining = _int_or_default(current.get("remaining", 0), 0)
        duration = max(1, _int_or_default(duration, 1))
        threshold = max(3, int(round(duration * 0.45)))
        current_modifiers = current.get("modifiers", {}) if isinstance(current.get("modifiers"), dict) else {}

        stronger = False
        if isinstance(modifiers, dict):
            for key, value in modifiers.items():
                if abs(_float_or_default(value, 0.0)) > abs(_float_or_default(current_modifiers.get(key, 0.0), 0.0)):
                    stronger = True
                    break

        if stronger:
            return 0.45 if remaining > threshold else 0.8
        return 0.0 if remaining > threshold else 0.25

    def _need_benefit(self, item_def, need, effects=None):
        score = 0.0
        for effect in item_def.get("effects", []):
            kind = effect.get("type")
            if kind == "modify_need" and effect.get("need") == need:
                try:
                    score += max(0.0, float(effect.get("delta", 0.0)))
                except (TypeError, ValueError):
                    continue
            elif kind == "status":
                modifiers = effect.get("modifiers", {})
                duration = max(1.0, _float_or_default(effect.get("duration", 1.0), 1.0))
                refresh_scale = self._status_refresh_scale(
                    effects,
                    effect.get("status"),
                    duration,
                    modifiers,
                )
                if refresh_scale <= 0.0:
                    continue
                try:
                    tick_delta = float(modifiers.get(f"{need}_tick_delta", 0.0))
                    score += max(0.0, tick_delta * (duration / 4.0) * refresh_scale)
                except (TypeError, ValueError):
                    continue
                try:
                    speed_mod = float(modifiers.get("move_speed_mult", 0.0))
                except (TypeError, ValueError):
                    speed_mod = 0.0
                if speed_mod > 0:
                    if need == "safety":
                        score += speed_mod * 14.0 * refresh_scale
                    elif need == "energy":
                        score += speed_mod * 6.0 * refresh_scale
        return score

    def _combat_benefit(self, item_def, *, effects=None, vitality=None, weapon=None, dist=None):
        if not item_def.get("effects"):
            return 0.0

        hp_ratio = 1.0
        if vitality:
            hp_ratio = max(0.0, min(1.0, float(vitality.hp) / float(max(1, vitality.max_hp))))
        has_ranged = bool(isinstance(weapon, dict) and not _weapon_is_melee(weapon))
        in_melee = dist is not None and int(dist) <= 1

        score = 0.0
        for effect in item_def.get("effects", []):
            kind = effect.get("type")
            if kind == "restore_hp":
                delta = _float_or_default(effect.get("delta", 0.0), 0.0)
                if delta > 0.0:
                    score += delta * (0.45 + ((1.0 - hp_ratio) * 1.25))
                continue
            if kind != "status":
                continue

            modifiers = effect.get("modifiers", {})
            duration = max(1.0, _float_or_default(effect.get("duration", 1.0), 1.0))
            refresh_scale = self._status_refresh_scale(
                effects,
                effect.get("status"),
                duration,
                modifiers,
            )
            if refresh_scale <= 0.0:
                continue

            duration_scale = max(0.4, min(2.0, duration / 12.0))
            status_score = 0.0
            if has_ranged:
                status_score += max(0.0, _float_or_default(modifiers.get("ranged_accuracy_mult", 0.0), 0.0)) * 42.0
                status_score += max(0.0, -_float_or_default(modifiers.get("projectile_spread_mod", 0.0), 0.0)) * 11.0
                status_score += max(0.0, -_float_or_default(modifiers.get("weapon_cooldown_mult", 0.0), 0.0)) * 36.0
                status_score += max(0.0, _float_or_default(modifiers.get("ranged_damage_mult", 0.0), 0.0)) * 34.0
                status_score -= max(0.0, -_float_or_default(modifiers.get("ranged_accuracy_mult", 0.0), 0.0)) * 18.0
            if in_melee or not has_ranged:
                status_score += max(0.0, _float_or_default(modifiers.get("melee_damage_mult", 0.0), 0.0)) * 34.0
                status_score += max(0.0, -_float_or_default(modifiers.get("melee_cooldown_mult", 0.0), 0.0)) * 28.0
            status_score += max(0.0, _float_or_default(modifiers.get("suppression_resist_mult", 0.0), 0.0)) * 24.0
            status_score += max(0.0, _float_or_default(modifiers.get("move_speed_mult", 0.0), 0.0)) * 18.0
            status_score += max(0.0, _float_or_default(modifiers.get("hp_tick_delta", 0.0), 0.0)) * 26.0
            status_score += max(0.0, -_float_or_default(modifiers.get("incoming_damage_mult", 0.0), 0.0)) * 48.0
            status_score += max(0.0, _float_or_default(modifiers.get("armor_absorb_bonus", 0.0), 0.0)) * 42.0
            status_score += max(0.0, _float_or_default(modifiers.get("cover_absorb_bonus", 0.0), 0.0)) * 34.0
            status_score += max(0.0, _float_or_default(modifiers.get("assault_bias_delta", 0.0), 0.0)) * 16.0
            status_score += max(0.0, -_float_or_default(modifiers.get("retreat_bias_delta", 0.0), 0.0)) * 16.0
            status_score -= max(0.0, _float_or_default(modifiers.get("incoming_damage_mult", 0.0), 0.0)) * 24.0
            score += status_score * duration_scale * refresh_scale

        return max(0.0, score)

    def update(self):
        ais = self.sim.ecs.get(AI)
        inventories = self.sim.ecs.get(Inventory)
        profiles = self.sim.ecs.get(ItemUseProfile)
        needs_map = self.sim.ecs.get(NPCNeeds)
        traits_map = self.sim.ecs.get(NPCTraits)
        justices = self.sim.ecs.get(JusticeProfile)
        positions = self.sim.ecs.get(Position)
        vitalities = self.sim.ecs.get(Vitality)
        statuses_map = self.sim.ecs.get(StatusEffects)
        loadouts = self.sim.ecs.get(WeaponLoadout)

        for eid, profile in profiles.items():
            if not profile.auto_use:
                continue
            if self.sim.tick - profile.last_use_tick < profile.cooldown_ticks:
                continue

            ai = ais.get(eid)
            inventory = inventories.get(eid)
            pos = positions.get(eid)
            if not ai or not inventory or not pos:
                continue
            if _entity_is_downed(self.sim, eid):
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                continue
            if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue
            if not inventory.items:
                continue
            if self._maybe_field_rescue(eid, profile, ai, inventory, pos):
                continue

            needs = needs_map.get(eid)
            if not needs:
                continue

            vitality = vitalities.get(eid)
            deficits = {
                "energy": max(0.0, 55.0 - needs.energy),
                "safety": max(0.0, 55.0 - needs.safety),
                "social": max(0.0, 52.0 - needs.social),
            }
            target_pos = positions.get(ai.target_eid) if ai.target_eid is not None else None
            combat_active = bool(
                ai.state == "protecting"
                and ai.target_eid is not None
                and target_pos
                and int(target_pos.z) == int(pos.z)
            )
            if max(deficits.values()) < 8.0 and not combat_active:
                continue

            traits = traits_map.get(eid) or NPCTraits()
            justice = justices.get(eid)
            effects = statuses_map.get(eid)
            loadout = loadouts.get(eid)
            weapon = weapon_by_id(loadout.current_weapon()) if loadout and loadout.current_weapon() else None
            combat_dist = _grid_distance(pos.x, pos.y, target_pos.x, target_pos.y) if combat_active else None

            if combat_active and self._maybe_tactical_throw(
                eid,
                profile,
                ai,
                inventory,
                pos,
                target_pos,
                traits=traits,
                justice=justice,
            ):
                continue

            best_entry = None
            best_score = 0.0
            best_reason = None
            for entry in inventory.items:
                item_def = self.catalog.get(entry["item_id"])
                if not item_def:
                    continue
                if not item_def.get("effects"):
                    continue

                tags = set(item_def.get("tags", []))
                willingness = profile.willingness + (traits.discipline * 0.2)

                pressure_score = 0.0
                best_need = None
                best_need_score = 0.0
                for need, deficit in deficits.items():
                    if deficit <= 0:
                        continue
                    benefit = self._need_benefit(item_def, need, effects=effects)
                    if benefit <= 0:
                        continue
                    weighted = deficit * benefit
                    pressure_score += weighted
                    if best_need is None or weighted > best_need_score:
                        best_need = need
                        best_need_score = weighted

                combat_score = 0.0
                if combat_active:
                    combat_score = self._combat_benefit(
                        item_def,
                        effects=effects,
                        vitality=vitality,
                        weapon=weapon,
                        dist=combat_dist,
                    )

                if pressure_score <= 0.0 and combat_score <= 0.0:
                    continue

                score = willingness + (pressure_score / 260.0) + (combat_score / 140.0)
                score += 0.08 * len(profile.preferred_tags.intersection(tags))
                score -= 0.1 * len(profile.avoid_tags.intersection(tags))

                legal_status = item_def.get("legal_status", "legal")
                if legal_status == "illegal":
                    justice_severity = (
                        (_justice_level(justice, default=0.4) * 0.7)
                        + (_crime_sensitivity(justice, default=0.4) * 0.3)
                    )
                    legal_penalty = (0.45 + (justice_severity * 0.25)) * (1.0 - profile.risk_tolerance)
                    score -= legal_penalty
                elif legal_status == "restricted":
                    score -= max(0.0, 0.12 - (profile.risk_tolerance * 0.1))

                if ai.state in {"protecting", "investigating"} and best_need == "social":
                    score -= 0.15

                if score > best_score:
                    best_score = score
                    best_entry = entry
                    if combat_score > pressure_score:
                        best_reason = "npc_combat_boost"
                    else:
                        best_reason = f"npc_need_{best_need or 'general'}"

            dynamic_threshold = 0.55
            if needs.energy < 32 or needs.safety < 32 or needs.social < 32:
                dynamic_threshold = 0.4
            if combat_active:
                dynamic_threshold = min(dynamic_threshold, 0.36)

            if best_entry and best_score >= dynamic_threshold:
                profile.last_use_tick = self.sim.tick
                self.sim.emit(Event(
                    "use_item_request",
                    eid=eid,
                    item_instance_id=best_entry["instance_id"],
                    reason=best_reason or "npc_auto",
                ))
