"""Reusable environmental hazard system for fixture-based danger zones."""

from __future__ import annotations

from engine.events import Event
from engine.systems import System
from game.components import NPCNeeds, Position, StatusEffects, Vitality
from game.system_support.environment_hazard_runtime import (
    environment_hazard_player_note,
    environment_hazard_profile,
)


def _clamp(value, lo=0.0, hi=100.0):
    return max(float(lo), min(float(hi), float(value)))


class EnvironmentalHazardSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.contact_cooldowns = {}
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)

    def _hazard_properties(self):
        for prop in tuple(getattr(self.sim, "properties", {}).values()):
            if str((prop or {}).get("kind", "")).strip().lower() != "asset":
                continue
            metadata = (prop or {}).get("metadata")
            if not isinstance(metadata, dict):
                continue
            profile_id = str(metadata.get("hazard_profile", "") or "").strip().lower()
            if not profile_id:
                continue
            yield prop

    def _hazards_at(self, x, y, z):
        for prop in self._hazard_properties():
            try:
                if (
                    int(prop.get("x", 0)) == int(x)
                    and int(prop.get("y", 0)) == int(y)
                    and int(prop.get("z", 0)) == int(z)
                ):
                    yield prop
            except (TypeError, ValueError):
                continue

    def _apply_hazard(self, prop, eid, pos):
        if prop is None or pos is None:
            return False
        metadata = prop.get("metadata") if isinstance(prop, dict) else None
        if not isinstance(metadata, dict):
            return False

        profile_id = str(metadata.get("hazard_profile", "") or "").strip().lower()
        profile = environment_hazard_profile(profile_id)
        if not profile:
            return False

        cooldown_ticks = max(1, int(metadata.get("hazard_cooldown_ticks", profile.get("cooldown_ticks", 10)) or 10))
        cooldown_key = (str(prop.get("id", "")).strip(), int(eid))
        if int(self.sim.tick) < int(self.contact_cooldowns.get(cooldown_key, -1)):
            return False

        status_map = self.sim.ecs.get(StatusEffects)
        vitality_map = self.sim.ecs.get(Vitality)
        needs_map = self.sim.ecs.get(NPCNeeds)
        effects = status_map.get(eid) if status_map else None
        vitality = vitality_map.get(eid) if vitality_map else None
        needs = needs_map.get(eid) if needs_map else None
        if effects is None and vitality is None and needs is None:
            return False

        status_name = str(metadata.get("hazard_status", profile.get("status", "")) or "").strip().lower()
        duration = max(1, int(metadata.get("hazard_duration", profile.get("duration", 1)) or 1))
        modifiers = dict(profile.get("modifiers", {}) or {})
        source_tag = str(metadata.get("fixture_type", metadata.get("hazard_profile", "environment_hazard")) or "environment_hazard").strip().lower() or "environment_hazard"

        if effects is not None and status_name:
            is_new = effects.add(
                status=status_name,
                duration=duration,
                modifiers=modifiers,
                source_item=source_tag,
            )
            self.sim.emit(Event(
                "status_applied",
                eid=eid,
                status=status_name,
                duration=duration,
                source_item=source_tag,
                modifiers=dict(modifiers),
                new=is_new,
            ))

        immediate_needs = metadata.get("hazard_immediate_needs")
        if needs is not None and isinstance(immediate_needs, dict):
            if "energy" in immediate_needs:
                needs.energy = _clamp(needs.energy + float(immediate_needs.get("energy", 0.0) or 0.0))
            if "safety" in immediate_needs:
                needs.safety = _clamp(needs.safety + float(immediate_needs.get("safety", 0.0) or 0.0))
            if "social" in immediate_needs:
                needs.social = _clamp(needs.social + float(immediate_needs.get("social", 0.0) or 0.0))

        actual_damage = 0
        if vitality is not None and not bool(getattr(vitality, "downed", False)):
            damage = max(0, int(metadata.get("hazard_damage", profile.get("damage", 0)) or 0))
            if damage > 0 and int(vitality.hp) > 1:
                new_hp = max(1, int(vitality.hp) - int(damage))
                actual_damage = max(0, int(vitality.hp) - int(new_hp))
                vitality.hp = int(new_hp)
                if actual_damage > 0:
                    self.sim.emit(Event(
                        "entity_damaged",
                        target_eid=eid,
                        source_eid=None,
                        weapon_id=source_tag,
                        damage_kind=str(metadata.get("hazard_damage_kind", profile.get("damage_kind", "condition")) or "condition").strip().lower() or "condition",
                        raw_damage=actual_damage,
                        damage=actual_damage,
                        cover_absorb=0.0,
                        armor_absorb=0.0,
                        hp=int(vitality.hp),
                        max_hp=int(vitality.max_hp),
                        x=int(pos.x),
                        y=int(pos.y),
                        z=int(pos.z),
                    ))

        self.sim.emit(Event(
            "environmental_hazard_triggered",
            eid=eid,
            target_eid=eid,
            property_id=str(prop.get("id", "")).strip() or None,
            property_name=str(prop.get("name", "")).strip() or str(metadata.get("hazard_label", profile.get("name", "Hazard"))).strip() or "Hazard",
            hazard_profile=profile_id,
            hazard_name=str(metadata.get("hazard_label", profile.get("name", "Hazard"))).strip() or str(profile.get("name", "Hazard")).strip() or "Hazard",
            hazard_note=environment_hazard_player_note(profile_id, name=str(metadata.get("hazard_label", ""))),
            damage=actual_damage,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        self.contact_cooldowns[cooldown_key] = int(self.sim.tick) + int(cooldown_ticks)
        return True

    def on_entity_moved(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return
        pos = self.sim.ecs.get(Position).get(eid)
        if pos is None:
            return
        for prop in self._hazards_at(pos.x, pos.y, pos.z):
            self._apply_hazard(prop, eid, pos)

    def update(self):
        positions = self.sim.ecs.get(Position)
        if not positions:
            return
        for prop in self._hazard_properties():
            try:
                px = int(prop.get("x", 0))
                py = int(prop.get("y", 0))
                pz = int(prop.get("z", 0))
            except (TypeError, ValueError):
                continue
            for eid in tuple(self.sim.tilemap.entities_at(px, py, pz) or ()):
                pos = positions.get(eid)
                if pos is None or (int(pos.x), int(pos.y), int(pos.z)) != (px, py, pz):
                    continue
                self._apply_hazard(prop, eid, pos)
