"""Wildlife runtime extracted from ``game/systems.py``.

This seam keeps animal memory, wildlife ecology scoring, and creature hazard
behavior together while ``game/systems.py`` remains a compatibility facade for
the rest of the project.
"""

import random

from engine.events import Event
from engine.systems import System
from game import systems as _systems
from game.system_support.actor_runtime import _detail_tick_allowed, _entity_is_downed

AI = _systems.AI
AnimalBehaviorContext = _systems.AnimalBehaviorContext
AnimalMemory = _systems.AnimalMemory
AnimalPhysicalProfile = _systems.AnimalPhysicalProfile
AnimalSocialProfile = _systems.AnimalSocialProfile
CreatureIdentity = _systems.CreatureIdentity
EcologyProfile = _systems.EcologyProfile
HumanWildlifePresence = _systems.HumanWildlifePresence
ITEM_CATALOG = _systems.ITEM_CATALOG
NPCNeeds = _systems.NPCNeeds
Position = _systems.Position
QUIET_NOISE_CAUSES = _systems.QUIET_NOISE_CAUSES
StatusEffects = _systems.StatusEffects
Vitality = _systems.Vitality
WildlifeSocialState = _systems.WildlifeSocialState
WeaponLoadout = _systems.WeaponLoadout
_actor_is_animal_or_wildlife = _systems._actor_is_animal_or_wildlife
_clamp = _systems._clamp
_grid_distance = _systems._grid_distance
_has_line_of_sight = _systems._has_line_of_sight
_manhattan = _systems._manhattan
_property_covering = _systems._property_covering
_weapon_is_melee = _systems._weapon_is_melee
_world_hour = _systems._world_hour
weapon_by_id = _systems.weapon_by_id


_WILDLIFE_PHYSICAL_DEFAULTS = {
    "canine": {"size_score": 45.0, "speed_score": 50.0},
    "feline": {"size_score": 20.0, "speed_score": 56.0},
    "rodent": {"size_score": 5.0, "speed_score": 58.0},
    "ungulate": {"size_score": 70.0, "speed_score": 60.0},
    "avian": {"size_score": 10.0, "speed_score": 64.0},
    "reptile": {"size_score": 12.0, "speed_score": 34.0},
    "amphibian": {"size_score": 8.0, "speed_score": 28.0},
    "insect": {"size_score": 2.0, "speed_score": 48.0},
    "other": {"size_score": 18.0, "speed_score": 32.0},
}

_WILDLIFE_ECOLOGY_DEFAULTS = {
    "canine": {"predator_score": 42.0, "prey_score": 24.0, "scavenger_score": 34.0, "territorial_score": 28.0, "pack_score": 54.0, "flee_bias": 38.0, "chase_bias": 52.0},
    "feline": {"predator_score": 34.0, "prey_score": 42.0, "scavenger_score": 22.0, "territorial_score": 34.0, "pack_score": 8.0, "flee_bias": 62.0, "chase_bias": 54.0},
    "rodent": {"predator_score": 5.0, "prey_score": 48.0, "scavenger_score": 32.0, "territorial_score": 8.0, "pack_score": 40.0, "flee_bias": 82.0, "chase_bias": 10.0},
    "ungulate": {"predator_score": 0.0, "prey_score": 56.0, "scavenger_score": 4.0, "territorial_score": 22.0, "pack_score": 60.0, "flee_bias": 80.0, "chase_bias": 4.0},
    "avian": {"predator_score": 8.0, "prey_score": 34.0, "scavenger_score": 28.0, "territorial_score": 16.0, "pack_score": 48.0, "flee_bias": 76.0, "chase_bias": 20.0},
    "other": {"predator_score": 10.0, "prey_score": 24.0, "scavenger_score": 28.0, "territorial_score": 18.0, "pack_score": 18.0, "flee_bias": 58.0, "chase_bias": 18.0},
}

_WILDLIFE_SOCIAL_DEFAULTS = {
    "canine": {"sociability": 48.0, "same_species_affinity": 44.0, "human_affinity": 22.0, "domesticity": 42.0, "companionship_drive": 54.0, "follow_drive": 58.0},
    "feline": {"sociability": 24.0, "same_species_affinity": 14.0, "human_affinity": 12.0, "domesticity": 28.0, "companionship_drive": 30.0, "follow_drive": 14.0},
    "rodent": {"sociability": 34.0, "same_species_affinity": 38.0, "human_affinity": 0.0, "domesticity": 0.0, "companionship_drive": 14.0, "follow_drive": 0.0},
    "ungulate": {"sociability": 46.0, "same_species_affinity": 54.0, "human_affinity": 0.0, "domesticity": 0.0, "companionship_drive": 24.0, "follow_drive": 0.0},
    "avian": {"sociability": 38.0, "same_species_affinity": 46.0, "human_affinity": 2.0, "domesticity": 6.0, "companionship_drive": 18.0, "follow_drive": 6.0},
    "other": {"sociability": 20.0, "same_species_affinity": 18.0, "human_affinity": 2.0, "domesticity": 4.0, "companionship_drive": 10.0, "follow_drive": 4.0},
}


def _actor_is_human(identity):
    if not identity:
        return False
    creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
    return creature_type == "human" or taxonomy == "hominid"


def _species_key(identity, ecology=None):
    species = str(getattr(ecology, "species", "") or "").strip().lower()
    if species:
        return species
    if identity:
        species = str(getattr(identity, "species", "") or "").strip().lower()
        if species:
            return species
        return str(getattr(identity, "taxonomy_class", "other") or "other").strip().lower() or "other"
    return "other"


class AnimalSocialSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("noise", self.on_noise)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("animal_socialized", self.on_animal_socialized)

    def _remember_impression(self, eid, actor_eid, *, regard, strength, via):
        if actor_eid is None or eid is None or actor_eid == eid:
            return
        memory = self.sim.ecs.get(AnimalMemory).get(eid)
        if memory is None:
            return
        memory.remember(
            tick=self.sim.tick,
            kind="actor_impression",
            strength=max(0.08, min(1.0, float(strength))),
            actor_eid=actor_eid,
            regard=max(-1.0, min(1.0, float(regard))),
            via=str(via or "ambient").strip().lower() or "ambient",
        )

    def on_noise(self, event):
        source_eid = event.data.get("source_eid")
        nx = event.data.get("x")
        ny = event.data.get("y")
        nz = event.data.get("z")
        radius = int(event.data.get("radius", 0) or 0)
        cause = str(event.data.get("cause", "") or "").strip().lower()
        if nx is None or ny is None or nz is None or cause in QUIET_NOISE_CAUSES:
            return

        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(AnimalMemory)
        for eid, memory in memories.items():
            if not _actor_is_animal_or_wildlife(self.sim, eid):
                continue
            pos = positions.get(eid)
            if not pos or int(pos.z) != int(nz):
                continue
            dist = _manhattan(pos.x, pos.y, nx, ny)
            if dist > radius + 3:
                continue
            intensity = max(0.12, 1.0 - (dist / float(max(1, radius + 1))))
            memory.remember(
                tick=self.sim.tick,
                kind="threat",
                strength=min(1.0, intensity * (1.18 if cause in {"fire_weapon", "gunshot", "explosion"} else 0.82)),
                source_eid=source_eid,
                x=nx,
                y=ny,
                z=nz,
                cause=cause,
            )
            if cause in {"fire_weapon", "gunshot", "explosion"} and source_eid is not None:
                self._remember_impression(eid, source_eid, regard=-0.42, strength=intensity * 0.9, via="loud_threat")

    def on_entity_damaged(self, event):
        source_eid = event.data.get("source_eid")
        target_eid = event.data.get("target_eid")
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        damage = int(event.data.get("damage", 0) or 0)
        if source_eid is None or target_eid is None or x is None or y is None or z is None or damage <= 0:
            return

        memories = self.sim.ecs.get(AnimalMemory)
        positions = self.sim.ecs.get(Position)
        socials = self.sim.ecs.get(WildlifeSocialState)

        target_memory = memories.get(target_eid)
        if target_memory is not None and _actor_is_animal_or_wildlife(self.sim, target_eid):
            impact = min(1.0, 0.24 + (damage / 18.0))
            target_memory.remember(
                tick=self.sim.tick,
                kind="threat",
                strength=impact,
                source_eid=source_eid,
                target_eid=target_eid,
                x=x,
                y=y,
                z=z,
                via="damaged",
            )
            self._remember_impression(target_eid, source_eid, regard=-0.72, strength=impact, via="damaged")

        for eid, social in socials.items():
            if not _actor_is_animal_or_wildlife(self.sim, eid):
                continue
            if eid in {source_eid, target_eid}:
                continue
            bond = social.bonds.get(target_eid) if social else None
            if not bond:
                continue
            closeness = float(bond.get("closeness", 0.0) or 0.0)
            trust = float(bond.get("trust", 0.0) or 0.0)
            if closeness < 0.34 and trust < 0.34:
                continue
            pos = positions.get(eid)
            if not pos or int(pos.z) != int(z):
                continue
            if _manhattan(pos.x, pos.y, x, y) > 7:
                continue
            memory = memories.get(eid)
            if memory is None:
                continue
            impact = min(1.0, 0.18 + (damage / 24.0) + (closeness * 0.22) + (trust * 0.18))
            memory.remember(
                tick=self.sim.tick,
                kind="threat",
                strength=impact,
                source_eid=source_eid,
                target_eid=target_eid,
                x=x,
                y=y,
                z=z,
                via="bonded_observer",
            )
            self._remember_impression(eid, source_eid, regard=-0.58, strength=impact, via="bonded_observer")

    def on_animal_socialized(self, event):
        left_eid = event.data.get("eid")
        right_eid = event.data.get("partner_eid")
        if left_eid is None or right_eid is None:
            return
        for eid, other_eid in ((left_eid, right_eid), (right_eid, left_eid)):
            memory = self.sim.ecs.get(AnimalMemory).get(eid)
            if memory is None:
                continue
            strength = float(event.data.get("bond_strength", 0.36) or 0.36)
            memory.remember(
                tick=self.sim.tick,
                kind="comfort",
                strength=max(0.12, min(1.0, strength)),
                partner_eid=other_eid,
                x=event.data.get("x"),
                y=event.data.get("y"),
                z=event.data.get("z"),
                via=str(event.data.get("kind", "companionship") or "companionship"),
            )
            self._remember_impression(eid, other_eid, regard=0.44, strength=strength, via="companionship")

    def update(self):
        memories = self.sim.ecs.get(AnimalMemory)
        positions = self.sim.ecs.get(Position)
        socials = self.sim.ecs.get(WildlifeSocialState)
        contexts = self.sim.ecs.get(AnimalBehaviorContext)

        for eid, memory in memories.items():
            pos = positions.get(eid)
            if pos and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=4):
                continue
            memory.decay(
                amount=0.006,
                by_kind={
                    "threat": 0.0032,
                    "comfort": 0.0024,
                    "actor_impression": 0.0018,
                },
            )

        for eid, social in socials.items():
            trimmed = {}
            for other_eid, bond in list(getattr(social, "bonds", {}).items()):
                closeness = max(0.0, float(bond.get("closeness", 0.0) or 0.0) - 0.0005)
                trust = max(0.0, float(bond.get("trust", 0.0) or 0.0) - 0.00035)
                comfort = max(0.0, float(bond.get("comfort", 0.0) or 0.0) - 0.00045)
                if max(closeness, trust, comfort) <= 0.08:
                    continue
                trimmed[other_eid] = {
                    "kind": str(bond.get("kind", "companion") or "companion").strip().lower() or "companion",
                    "closeness": closeness,
                    "trust": trust,
                    "comfort": comfort,
                }
            social.bonds = trimmed

            context = contexts.get(eid)
            if context is None:
                continue
            strongest = social.strongest_bond(min_closeness=0.58, min_trust=0.5)
            context.bonded_to_eid = strongest if strongest in positions else None


class CreatureHazardSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.rng = random.Random(f"{sim.seed}:creature_hazards")
        self.contact_cooldowns = {}
        self.condition_cooldowns = {}
        self.runs_without_turn = True
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)

    def _toxic_cat_coat(self):
        traits = getattr(self.sim, "world_traits", {}) or {}
        return str(traits.get("toxic_cat_coat", "")).strip().lower()

    def _contact_chance(self):
        traits = getattr(self.sim, "world_traits", {}) or {}
        try:
            chance = float(traits.get("toxic_cat_contact_chance", 0.33))
        except (TypeError, ValueError):
            chance = 0.33
        return max(0.05, min(0.95, chance))

    def _contact_cooldown_ticks(self):
        traits = getattr(self.sim, "world_traits", {}) or {}
        try:
            ticks = int(traits.get("toxic_cat_contact_cooldown", 18))
        except (TypeError, ValueError):
            ticks = 18
        return max(3, min(120, ticks))

    def _world_conditions(self):
        traits = getattr(self.sim, "world_traits", {}) or {}
        raw = traits.get("world_conditions", [])
        return raw if isinstance(raw, list) else []

    def _entity_matches_condition(self, eid, condition, identities, ais):
        kind = str(condition.get("target_kind", "")).strip().lower()
        target_value = str(condition.get("target_value", "")).strip().lower()
        if not kind or not target_value:
            return False

        if kind == "taxonomy":
            identity = identities.get(eid)
            if not identity:
                return False
            return str(identity.taxonomy_class).strip().lower() == target_value

        if kind == "human_role":
            identity = identities.get(eid)
            if not identity:
                return False
            if str(identity.taxonomy_class).strip().lower() != "hominid":
                return False
            ai = ais.get(eid)
            if not ai:
                return False
            return str(ai.role).strip().lower() == target_value

        return False

    def _apply_world_condition(self, eid, pos, condition):
        statuses = self.sim.ecs.get(StatusEffects)
        needs_map = self.sim.ecs.get(NPCNeeds)
        vitalities = self.sim.ecs.get(Vitality)

        target_status = statuses.get(eid)
        if not target_status:
            return False

        condition_id = str(condition.get("id", condition.get("topic", "condition")))
        topic = str(condition.get("topic", "world_condition")).strip().lower()
        target_value = str(condition.get("target_value", "")).strip().lower()
        is_positive = bool(condition.get("is_positive", False))
        status_name = str(condition.get("status", "world_condition")).strip().lower()
        duration = int(max(4, int(condition.get("duration", 16))))
        modifiers = dict(condition.get("modifiers", {}) or {})
        chip_damage = int(max(0, int(condition.get("chip_damage", 0))))
        source_tag = str(condition.get("source_tag", topic or "world_condition"))

        is_new = target_status.add(
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
            new=is_new,
        ))

        needs = needs_map.get(eid)
        if needs:
            safety_hit = float(condition.get("safety_hit", 0.0))
            energy_hit = float(condition.get("energy_hit", 0.0))
            social_hit = float(condition.get("social_hit", 0.0))
            needs.safety = _clamp(needs.safety + safety_hit)
            needs.energy = _clamp(needs.energy + energy_hit)
            needs.social = _clamp(needs.social + social_hit)

        vitality = vitalities.get(eid)
        if vitality and chip_damage > 0:
            vitality.hp = max(1, vitality.hp - chip_damage)
            self.sim.emit(Event(
                "entity_damaged",
                target_eid=eid,
                source_eid=None,
                weapon_id=f"{condition_id}_ambient",
                damage_kind="condition",
                raw_damage=chip_damage,
                damage=chip_damage,
                cover_absorb=0.0,
                hp=vitality.hp,
                max_hp=vitality.max_hp,
                x=pos.x,
                y=pos.y,
                z=pos.z,
            ))

        self.sim.emit(Event(
            "world_condition_triggered",
            eid=eid,
            condition_id=condition_id,
            topic=topic,
            target_kind=str(condition.get("target_kind", "")),
            target_value=target_value,
            is_positive=is_positive,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        ))
        return True

    def _is_toxic_feline(self, identity, toxic_coat):
        if not identity:
            return False
        if str(identity.taxonomy_class).strip().lower() != "feline":
            return False
        coat = str(identity.coat_variant or "").strip().lower()
        return bool(coat and toxic_coat and coat == toxic_coat)

    def _apply_toxin(self, source_eid, target_eid, source_pos, target_pos, toxic_coat):
        statuses = self.sim.ecs.get(StatusEffects)
        needs_map = self.sim.ecs.get(NPCNeeds)
        vitalities = self.sim.ecs.get(Vitality)

        target_status = statuses.get(target_eid)
        if not target_status:
            return False

        source_tag = f"{toxic_coat}_cat_toxin"
        is_new = target_status.add(
            status="coat_toxin",
            duration=20,
            modifiers={
                "safety_tick_delta": -0.18,
                "energy_tick_delta": -0.07,
                "move_speed_mult": -0.16,
            },
            source_item=source_tag,
        )
        self.sim.emit(Event(
            "status_applied",
            eid=target_eid,
            status="coat_toxin",
            duration=20,
            source_item=source_tag,
            new=is_new,
        ))

        needs = needs_map.get(target_eid)
        if needs:
            needs.safety = _clamp(needs.safety - 3.8)
            needs.energy = _clamp(needs.energy - 1.2)

        vitality = vitalities.get(target_eid)
        if vitality:
            vitality.hp = max(1, vitality.hp - 1)
            self.sim.emit(Event(
                "entity_damaged",
                target_eid=target_eid,
                source_eid=source_eid,
                weapon_id="toxin_contact",
                damage_kind="toxin",
                raw_damage=1,
                damage=1,
                cover_absorb=0.0,
                hp=vitality.hp,
                max_hp=vitality.max_hp,
                x=target_pos.x,
                y=target_pos.y,
                z=target_pos.z,
            ))

        self.sim.emit(Event(
            "creature_hazard_triggered",
            source_eid=source_eid,
            target_eid=target_eid,
            coat_variant=toxic_coat,
            x=target_pos.x,
            y=target_pos.y,
            z=target_pos.z,
        ))
        return True

    def on_entity_moved(self, event):
        moved_eid = event.data.get("eid")
        if moved_eid is None:
            return

        positions = self.sim.ecs.get(Position)
        identities = self.sim.ecs.get(CreatureIdentity)
        vitalities = self.sim.ecs.get(Vitality)
        moved_pos = positions.get(moved_eid)
        if not moved_pos:
            return
        if self.sim.detail_for_xy(moved_pos.x, moved_pos.y) == "unloaded":
            return

        moved_vitality = vitalities.get(moved_eid)
        if moved_vitality and moved_vitality.downed:
            return

        ais = self.sim.ecs.get(AI)

        toxic_coat = self._toxic_cat_coat()
        if toxic_coat:
            chance = self._contact_chance()
            cooldown_ticks = self._contact_cooldown_ticks()
            moved_identity = identities.get(moved_eid)
            moved_is_toxic = self._is_toxic_feline(moved_identity, toxic_coat)

            for other_eid, other_pos in positions.items():
                if other_eid == moved_eid:
                    continue
                if other_pos.z != moved_pos.z:
                    continue
                if _manhattan(moved_pos.x, moved_pos.y, other_pos.x, other_pos.y) > 1:
                    continue

                other_vitality = vitalities.get(other_eid)
                if other_vitality and other_vitality.downed:
                    continue

                other_identity = identities.get(other_eid)
                other_is_toxic = self._is_toxic_feline(other_identity, toxic_coat)

                if moved_is_toxic and not other_is_toxic:
                    source_eid = moved_eid
                    source_pos = moved_pos
                    target_eid = other_eid
                    target_pos = other_pos
                elif other_is_toxic and not moved_is_toxic:
                    source_eid = other_eid
                    source_pos = other_pos
                    target_eid = moved_eid
                    target_pos = moved_pos
                else:
                    continue

                key = (source_eid, target_eid)
                if self.sim.tick < self.contact_cooldowns.get(key, -10_000):
                    continue
                if self.rng.random() > chance:
                    continue

                if self._apply_toxin(
                    source_eid=source_eid,
                    target_eid=target_eid,
                    source_pos=source_pos,
                    target_pos=target_pos,
                    toxic_coat=toxic_coat,
                ):
                    self.contact_cooldowns[key] = self.sim.tick + cooldown_ticks
                    break

        for condition in self._world_conditions():
            if not self._entity_matches_condition(moved_eid, condition, identities, ais):
                continue

            condition_id = str(condition.get("id", condition.get("topic", "condition")))
            key = (moved_eid, condition_id)
            if self.sim.tick < self.condition_cooldowns.get(key, -10_000):
                continue

            try:
                chance = float(condition.get("chance", 0.05))
            except (TypeError, ValueError):
                chance = 0.05
            chance = max(0.005, min(0.75, chance))
            if self.rng.random() > chance:
                continue

            if self._apply_world_condition(moved_eid, moved_pos, condition):
                try:
                    cooldown = int(condition.get("cooldown", 40))
                except (TypeError, ValueError):
                    cooldown = 40
                cooldown = max(4, min(220, cooldown))
                self.condition_cooldowns[key] = self.sim.tick + cooldown
                break

    def update(self):
        if not self.contact_cooldowns and not self.condition_cooldowns:
            return
        if self.sim.tick % 30 != 0:
            return
        self.contact_cooldowns = {
            key: tick
            for key, tick in self.contact_cooldowns.items()
            if tick > self.sim.tick
        }
        self.condition_cooldowns = {
            key: tick
            for key, tick in self.condition_cooldowns.items()
            if tick > self.sim.tick
        }


def _default_animal_physical_profile(identity):
    taxonomy = str(getattr(identity, "taxonomy_class", "other") or "other").strip().lower() or "other"
    payload = _WILDLIFE_PHYSICAL_DEFAULTS.get(taxonomy, _WILDLIFE_PHYSICAL_DEFAULTS["other"])
    return AnimalPhysicalProfile(
        size_score=float(payload["size_score"]),
        speed_score=float(payload["speed_score"]),
    )


def _default_ecology_profile(identity):
    taxonomy = str(getattr(identity, "taxonomy_class", "other") or "other").strip().lower() or "other"
    payload = _WILDLIFE_ECOLOGY_DEFAULTS.get(taxonomy, _WILDLIFE_ECOLOGY_DEFAULTS["other"])
    return EcologyProfile(
        species=_species_key(identity),
        predator_score=float(payload["predator_score"]),
        prey_score=float(payload["prey_score"]),
        scavenger_score=float(payload["scavenger_score"]),
        territorial_score=float(payload["territorial_score"]),
        pack_score=float(payload["pack_score"]),
        flee_bias=float(payload["flee_bias"]),
        chase_bias=float(payload["chase_bias"]),
    )


def _default_animal_social_profile(identity):
    taxonomy = str(getattr(identity, "taxonomy_class", "other") or "other").strip().lower() or "other"
    payload = _WILDLIFE_SOCIAL_DEFAULTS.get(taxonomy, _WILDLIFE_SOCIAL_DEFAULTS["other"])
    return AnimalSocialProfile(
        sociability=float(payload["sociability"]),
        same_species_affinity=float(payload["same_species_affinity"]),
        human_affinity=float(payload["human_affinity"]),
        domesticity=float(payload["domesticity"]),
        companionship_drive=float(payload["companionship_drive"]),
        follow_drive=float(payload["follow_drive"]),
    )


def _animal_physical_profile_for_actor(sim, eid):
    profile = sim.ecs.get(AnimalPhysicalProfile).get(eid)
    if profile is not None:
        return profile
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if not identity or _actor_is_human(identity):
        return None
    return _default_animal_physical_profile(identity)


def _animal_ecology_profile_for_actor(sim, eid):
    profile = sim.ecs.get(EcologyProfile).get(eid)
    if profile is not None:
        return profile
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if not identity or _actor_is_human(identity):
        return None
    return _default_ecology_profile(identity)


def _animal_behavior_context_for_actor(sim, eid):
    profile = sim.ecs.get(AnimalBehaviorContext).get(eid)
    if profile is not None:
        return profile
    return AnimalBehaviorContext()


def _animal_social_profile_for_actor(sim, eid):
    profile = sim.ecs.get(AnimalSocialProfile).get(eid)
    if profile is not None:
        return profile
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if not identity or _actor_is_human(identity):
        return None
    return _default_animal_social_profile(identity)


def _animal_memory_for_actor(sim, eid):
    return sim.ecs.get(AnimalMemory).get(eid)


def _wildlife_social_state_for_actor(sim, eid):
    return sim.ecs.get(WildlifeSocialState).get(eid)


def _human_wildlife_presence_for_actor(sim, eid):
    presence = sim.ecs.get(HumanWildlifePresence).get(eid)
    if presence is not None:
        return presence
    if eid == getattr(sim, "player_eid", None):
        return HumanWildlifePresence()
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if not _actor_is_human(identity):
        return None
    ai = sim.ecs.get(AI).get(eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    return HumanWildlifePresence(
        perceived_predator_score=72.0 if role in {"guard", "scout"} else 60.0,
        firearm_threat_bonus=36.0 if role in {"guard", "scout"} else 30.0,
        calm_animal_skill=8.0 if role in {"worker", "resident"} else 2.0,
        hunting_intent=False,
        companionship_openness=34.0 if role in {"resident", "worker"} else (18.0 if role in {"civilian", "drunk"} else 6.0),
        gentle_presence=26.0 if role in {"worker", "resident"} else (12.0 if role in {"civilian", "drunk"} else 4.0),
    )


def _wildlife_bond_for_actor(sim, eid, other_eid):
    social = _wildlife_social_state_for_actor(sim, eid)
    if not social or other_eid is None:
        return None
    return social.bonds.get(other_eid)


def _wildlife_bond_score(bond):
    if not isinstance(bond, dict):
        return 0.0
    return (
        (float(bond.get("closeness", 0.0) or 0.0) * 0.44)
        + (float(bond.get("trust", 0.0) or 0.0) * 0.34)
        + (float(bond.get("comfort", 0.0) or 0.0) * 0.22)
    )


def _animal_memory_regard(memory, actor_eid, *, max_age=320):
    if memory is None or actor_eid is None:
        return 0.0
    total = 0.0
    weight = 0.0
    for entry in list(getattr(memory, "entries", ()) or ()):
        if str(entry.get("kind", "")).strip().lower() != "actor_impression":
            continue
        age = int(getattr(memory, "sim_tick", 0) or 0)
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        if data.get("actor_eid") != actor_eid:
            continue
        strength = float(entry.get("strength", 0.0) or 0.0)
        regard = max(-1.0, min(1.0, float(data.get("regard", 0.0) or 0.0)))
        total += regard * strength
        weight += strength
    if weight <= 0.0:
        return 0.0
    return _clamp(total / weight, lo=-1.0, hi=1.0)


def _sync_wildlife_bond_pair(sim, left_eid, right_eid, *, kind="companion", closeness_delta=0.0, trust_delta=0.0, comfort_delta=0.0):
    if left_eid is None or right_eid is None or left_eid == right_eid:
        return 0.0
    updated = 0.0
    socials = sim.ecs.get(WildlifeSocialState)
    for actor_eid, other_eid in ((left_eid, right_eid), (right_eid, left_eid)):
        social = socials.get(actor_eid)
        if social is None:
            continue
        current = dict(social.bonds.get(other_eid, {}))
        closeness = _clamp(float(current.get("closeness", 0.18) or 0.18) + float(closeness_delta), lo=0.0, hi=1.0)
        trust = _clamp(float(current.get("trust", 0.16) or 0.16) + float(trust_delta), lo=0.0, hi=1.0)
        comfort = _clamp(float(current.get("comfort", 0.18) or 0.18) + float(comfort_delta), lo=0.0, hi=1.0)
        social.add_bond(other_eid, kind=kind, closeness=closeness, trust=trust, comfort=comfort)
        updated = max(updated, _wildlife_bond_score(social.bonds.get(other_eid)))
    return updated


def _actors_use_wildlife_social(sim, left_eid, right_eid):
    if left_eid is None or right_eid is None:
        return False
    if not _actor_is_animal_or_wildlife(sim, left_eid) and not _actor_is_animal_or_wildlife(sim, right_eid):
        return False
    return _wildlife_social_state_for_actor(sim, left_eid) is not None and _wildlife_social_state_for_actor(sim, right_eid) is not None


def _actor_injury_score(sim, eid, physical):
    base = float(getattr(physical, "injury_score", 0.0) or 0.0) if physical is not None else 0.0
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is None or int(getattr(vitality, "max_hp", 0) or 0) <= 0:
        return base
    max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
    hp = max(0, min(max_hp, int(getattr(vitality, "hp", max_hp) or max_hp)))
    missing_ratio = 1.0 - (float(hp) / float(max_hp))
    return base + (missing_ratio * 35.0)


def _actor_has_ranged_weapon(sim, eid):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout or not callable(getattr(loadout, "current_weapon", None)):
        return False
    weapon_id = loadout.current_weapon()
    if not weapon_id:
        return False
    weapon = weapon_by_id(weapon_id)
    return bool(isinstance(weapon, dict) and not _weapon_is_melee(weapon))


def _wildlife_can_observe(sim, observer_pos, target_pos, *, radius):
    if observer_pos is None or target_pos is None:
        return False
    if int(observer_pos.z) != int(target_pos.z):
        return False
    if _grid_distance(observer_pos.x, observer_pos.y, target_pos.x, target_pos.y) > int(max(1, radius)):
        return False
    return _has_line_of_sight(
        sim,
        observer_pos.x,
        observer_pos.y,
        observer_pos.z,
        target_pos.x,
        target_pos.y,
        target_pos.z,
    )


def _wildlife_group_alarm_target(sim, eid, pos, identity, ecology, behavior):
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    identities = sim.ecs.get(CreatureIdentity)
    ecologies = sim.ecs.get(EcologyProfile)
    radius = max(2, int(getattr(behavior, "flock_radius", 3)) + 1)
    species = _species_key(identity, ecology)
    best = None
    best_dist = None

    for other_eid, other_pos in positions.items():
        if other_eid == eid or int(other_pos.z) != int(pos.z):
            continue
        if _grid_distance(pos.x, pos.y, other_pos.x, other_pos.y) > radius:
            continue
        other_ai = ais.get(other_eid)
        if str(getattr(other_ai, "role", "") or "").strip().lower() != "wildlife":
            continue
        if str(getattr(other_ai, "state", "") or "").strip().lower() != "seeking_safety":
            continue
        if not isinstance(getattr(other_ai, "target", None), (tuple, list)) or len(other_ai.target) < 3:
            continue
        other_identity = identities.get(other_eid)
        other_ecology = ecologies.get(other_eid)
        same_species = _species_key(other_identity, other_ecology) == species
        same_taxonomy = str(getattr(other_identity, "taxonomy_class", "") or "").strip().lower() == str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
        if not same_species and not same_taxonomy:
            continue
        dist = _grid_distance(pos.x, pos.y, other_pos.x, other_pos.y)
        if best is None or dist < best_dist:
            best = tuple(other_ai.target)
            best_dist = dist

    return best


def _wildlife_best_scavenge_target(sim, pos, ecology, context):
    if pos is None or ecology is None:
        return None
    hunger = float(getattr(context, "hunger", 50.0) or 50.0)
    if float(getattr(ecology, "scavenger_score", 0.0) or 0.0) <= 0.0:
        return None

    radius = max(2, min(4, int(round(float(getattr(ecology, "scavenger_score", 0.0) or 0.0) / 24.0)) + 2))
    best = None
    best_score = float("-inf")
    for ground in sim.ground_items_in_radius(pos.x, pos.y, pos.z, r=radius):
        item_def = ITEM_CATALOG.get(str(ground.get("item_id", "")).strip())
        tags = {
            str(tag).strip().lower()
            for tag in ((item_def or {}).get("tags", ()) or ())
            if str(tag).strip()
        }
        if not tags:
            continue
        food_bonus = 16.0 if "food" in tags else (9.0 if "drink" in tags else 0.0)
        if food_bonus <= 0.0:
            continue
        dist = _grid_distance(pos.x, pos.y, int(ground.get("x", pos.x)), int(ground.get("y", pos.y)))
        score = (float(getattr(ecology, "scavenger_score", 0.0) or 0.0) * 0.72) + (hunger * 0.34) + food_bonus - (dist * 6.0)
        if score > best_score:
            best_score = score
            best = {
                "score": score,
                "target": (int(ground.get("x", pos.x)), int(ground.get("y", pos.y)), int(ground.get("z", pos.z))),
                "ground_item_id": str(ground.get("ground_item_id", "")).strip() or None,
            }
    return best


def _wildlife_threat_score(sim, self_eid, other_eid, *, self_identity, self_physical, self_ecology, self_context, distance):
    other_identity = sim.ecs.get(CreatureIdentity).get(other_eid)
    presence = _human_wildlife_presence_for_actor(sim, other_eid)
    bond = _wildlife_bond_for_actor(sim, self_eid, other_eid)
    bond_score = _wildlife_bond_score(bond)
    regard = _animal_memory_regard(_animal_memory_for_actor(sim, self_eid), other_eid)
    if other_identity is None and presence is None:
        return None

    if _actor_is_human(other_identity) or presence is not None:
        if presence is None:
            return None
        threat = float(getattr(presence, "perceived_predator_score", 60.0) or 60.0)
        threat -= float(getattr(presence, "calm_animal_skill", 0.0) or 0.0) * 0.45
        if bool(getattr(presence, "hunting_intent", False)):
            threat += float(getattr(presence, "firearm_threat_bonus", 30.0) or 30.0)
        elif _actor_has_ranged_weapon(sim, other_eid):
            threat += float(getattr(presence, "firearm_threat_bonus", 30.0) or 30.0) * 0.65
        threat += max(0.0, float(getattr(self_ecology, "prey_score", 0.0) or 0.0) * 0.12)
        threat -= distance * 2.0
        threat -= (bond_score * 28.0) + (max(0.0, regard) * 12.0)
        threat += max(0.0, -regard) * 8.0
        if bool(getattr(presence, "hunting_intent", False)):
            threat += max(0.0, bond_score * 10.0)
        return {
            "score": threat,
            "kind": "human",
        }

    other_physical = _animal_physical_profile_for_actor(sim, other_eid)
    other_ecology = _animal_ecology_profile_for_actor(sim, other_eid)
    other_context = _animal_behavior_context_for_actor(sim, other_eid)
    if other_physical is None or other_ecology is None:
        return None

    aggression = (float(getattr(other_ecology, "predator_score", 0.0) or 0.0) * 0.48) + (float(getattr(other_ecology, "chase_bias", 0.0) or 0.0) * 0.34) + (float(getattr(other_ecology, "territorial_score", 0.0) or 0.0) * 0.2)
    if bool(getattr(other_context, "territorial_context", False)):
        aggression += float(getattr(other_ecology, "territorial_score", 0.0) or 0.0) * 0.28
    if bool(getattr(other_context, "cornered", False)):
        aggression += 12.0
    if bool(getattr(other_physical, "juvenile", False)):
        aggression -= 10.0

    size_pressure = max(0.0, float(getattr(other_physical, "size_score", 0.0) or 0.0) - float(getattr(self_physical, "size_score", 0.0) or 0.0)) * 0.72
    speed_pressure = max(0.0, float(getattr(other_physical, "speed_score", 0.0) or 0.0) - float(getattr(self_physical, "speed_score", 0.0) or 0.0)) * 0.15
    prey_bonus = float(getattr(self_ecology, "prey_score", 0.0) or 0.0) * 0.1
    injury_penalty = _actor_injury_score(sim, self_eid, self_physical) * 0.32
    threat = aggression + size_pressure + speed_pressure + prey_bonus + injury_penalty - (distance * 2.1)
    threat -= (bond_score * 24.0) + (max(0.0, regard) * 10.0)
    threat += max(0.0, -regard) * 8.0
    return {
        "score": threat,
        "kind": "animal",
    }


def _wildlife_chase_drive(sim, self_eid, other_eid, *, self_identity, self_physical, self_ecology, self_context, distance):
    other_identity = sim.ecs.get(CreatureIdentity).get(other_eid)
    if other_identity is None or _actor_is_human(other_identity):
        return None

    other_physical = _animal_physical_profile_for_actor(sim, other_eid)
    other_ecology = _animal_ecology_profile_for_actor(sim, other_eid)
    if other_physical is None or other_ecology is None:
        return None

    if _species_key(other_identity, other_ecology) == _species_key(self_identity, self_ecology) and not bool(getattr(self_context, "territorial_context", False)):
        return None

    hunger = float(getattr(self_context, "hunger", 50.0) or 50.0)
    hunger_factor = 0.38 + (max(0.0, min(100.0, hunger)) / 100.0 * 0.72)
    predatory = (float(getattr(self_ecology, "predator_score", 0.0) or 0.0) * 0.46) + (float(getattr(self_ecology, "chase_bias", 0.0) or 0.0) * 0.38)
    predatory += max(0.0, float(getattr(self_physical, "size_score", 0.0) or 0.0) - float(getattr(other_physical, "size_score", 0.0) or 0.0)) * 0.72
    predatory += max(0.0, float(getattr(self_physical, "speed_score", 0.0) or 0.0) - float(getattr(other_physical, "speed_score", 0.0) or 0.0)) * 0.18
    caution = max(0.0, float(getattr(other_physical, "size_score", 0.0) or 0.0) - float(getattr(self_physical, "size_score", 0.0) or 0.0)) * 0.55
    caution += float(getattr(other_ecology, "predator_score", 0.0) or 0.0) * 0.16
    caution += _actor_injury_score(sim, self_eid, self_physical) * 0.28
    caution += distance * 2.4
    restraint = (float(getattr(self_context, "trained_restraint", 0.0) or 0.0) * 0.45)
    if bool(getattr(self_context, "leashed", False)):
        restraint += 22.0
    if getattr(self_context, "bonded_to_eid", None) == other_eid:
        restraint += 18.0
    return {
        "score": (predatory * hunger_factor) - caution - restraint,
        "kind": "animal",
    }


def _wildlife_guardian_bonus(sim, eid, pos, identity, ecology, behavior):
    positions = sim.ecs.get(Position)
    identities = sim.ecs.get(CreatureIdentity)
    physical_profiles = sim.ecs.get(AnimalPhysicalProfile)
    radius = max(2, int(getattr(behavior, "flock_radius", 3)))
    species = _species_key(identity, ecology)
    bonus = 0.0

    for other_eid, other_pos in positions.items():
        if other_eid == eid or int(other_pos.z) != int(pos.z):
            continue
        if _grid_distance(pos.x, pos.y, other_pos.x, other_pos.y) > radius:
            continue
        other_identity = identities.get(other_eid)
        other_physical = physical_profiles.get(other_eid)
        if other_identity is None or other_physical is None:
            continue
        if not bool(getattr(other_physical, "juvenile", False)):
            continue
        if _species_key(other_identity) != species:
            continue
        bonus += 24.0

    return min(48.0, bonus)


def _wildlife_pack_support(sim, eid, pos, identity, ecology, behavior):
    positions = sim.ecs.get(Position)
    identities = sim.ecs.get(CreatureIdentity)
    radius = max(2, int(getattr(behavior, "flock_radius", 3)))
    species = _species_key(identity, ecology)
    count = 0

    for other_eid, other_pos in positions.items():
        if other_eid == eid or int(other_pos.z) != int(pos.z):
            continue
        if _grid_distance(pos.x, pos.y, other_pos.x, other_pos.y) > radius:
            continue
        if _species_key(identities.get(other_eid)) != species:
            continue
        count += 1

    return min(3, count)


def _wildlife_social_target_score(sim, self_eid, other_eid, *, pos, other_pos, identity, ecology, social_profile, needs):
    if other_eid == self_eid or other_pos is None or int(other_pos.z) != int(pos.z):
        return None
    if _entity_is_downed(sim, other_eid):
        return None

    observe_radius = max(4, int(max(2.0, float(getattr(social_profile, "companionship_drive", 0.0) or 0.0) / 14.0)) + 2)
    if not _wildlife_can_observe(sim, pos, other_pos, radius=observe_radius):
        return None

    distance = _grid_distance(pos.x, pos.y, other_pos.x, other_pos.y)
    if distance > observe_radius:
        return None

    other_identity = sim.ecs.get(CreatureIdentity).get(other_eid)
    if other_identity is None:
        return None

    bond = _wildlife_bond_for_actor(sim, self_eid, other_eid)
    bond_score = _wildlife_bond_score(bond)
    regard = _animal_memory_regard(_animal_memory_for_actor(sim, self_eid), other_eid)
    safety_read = float(needs.safety if needs is not None else 60.0)
    social_need = max(0.0, 100.0 - float(needs.social if needs is not None else 40.0))

    if _actor_is_human(other_identity):
        presence = _human_wildlife_presence_for_actor(sim, other_eid)
        if presence is None:
            return None
        threat = _wildlife_threat_score(
            sim,
            self_eid,
            other_eid,
            self_identity=identity,
            self_physical=_animal_physical_profile_for_actor(sim, self_eid),
            self_ecology=ecology,
            self_context=_animal_behavior_context_for_actor(sim, self_eid),
            distance=distance,
        )
        threat_score = float((threat or {}).get("score", 0.0) or 0.0)
        score = (social_need * 0.42) + (float(getattr(social_profile, "sociability", 0.0) or 0.0) * 0.3)
        score += float(getattr(social_profile, "human_affinity", 0.0) or 0.0) * 0.52
        score += float(getattr(social_profile, "domesticity", 0.0) or 0.0) * 0.68
        score += float(getattr(presence, "calm_animal_skill", 0.0) or 0.0) * 0.85
        score += float(getattr(presence, "companionship_openness", 0.0) or 0.0) * 0.55
        score += float(getattr(presence, "gentle_presence", 0.0) or 0.0) * 0.5
        score += bond_score * 42.0
        score += max(0.0, regard) * 18.0
        score -= max(0.0, -regard) * 22.0
        score -= threat_score * 0.58
        score -= max(0.0, 52.0 - safety_read) * 0.6
        score -= distance * 5.8
        if bool(getattr(presence, "hunting_intent", False)):
            score -= 34.0
        return {
            "score": score,
            "distance": distance,
            "bond_score": bond_score,
            "kind": "human",
        }

    other_ecology = _animal_ecology_profile_for_actor(sim, other_eid)
    other_social = _animal_social_profile_for_actor(sim, other_eid)
    if other_ecology is None:
        return None

    same_species = _species_key(other_identity, other_ecology) == _species_key(identity, ecology)
    same_taxonomy = str(getattr(other_identity, "taxonomy_class", "") or "").strip().lower() == str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
    if not same_species and not same_taxonomy and bond_score <= 0.24 and regard <= 0.08:
        return None

    threat = _wildlife_threat_score(
        sim,
        self_eid,
        other_eid,
        self_identity=identity,
        self_physical=_animal_physical_profile_for_actor(sim, self_eid),
        self_ecology=ecology,
        self_context=_animal_behavior_context_for_actor(sim, self_eid),
        distance=distance,
    )
    threat_score = float((threat or {}).get("score", 0.0) or 0.0)
    score = (social_need * 0.36) + (float(getattr(social_profile, "sociability", 0.0) or 0.0) * 0.34)
    score += float(getattr(social_profile, "companionship_drive", 0.0) or 0.0) * 0.28
    score += (float(getattr(social_profile, "same_species_affinity", 0.0) or 0.0) * (0.88 if same_species else 0.42))
    score += (float(getattr(other_social, "sociability", 0.0) or 0.0) * 0.12) if other_social is not None else 0.0
    score += bond_score * 38.0
    score += max(0.0, regard) * 16.0
    score -= max(0.0, -regard) * 18.0
    score -= threat_score * 0.46
    score -= distance * 4.8
    score -= max(0.0, 50.0 - safety_read) * 0.55
    return {
        "score": score,
        "distance": distance,
        "bond_score": bond_score,
        "kind": "animal",
    }


def _wildlife_social_intent(sim, eid, pos, identity, ecology, needs):
    social_profile = _animal_social_profile_for_actor(sim, eid)
    social_state = _wildlife_social_state_for_actor(sim, eid)
    if social_profile is None or social_state is None or needs is None:
        return None
    if float(needs.safety) < 42.0:
        return None

    positions = sim.ecs.get(Position)
    context = _animal_behavior_context_for_actor(sim, eid)
    best = None

    for other_eid, other_pos in positions.items():
        scored = _wildlife_social_target_score(
            sim,
            eid,
            other_eid,
            pos=pos,
            other_pos=other_pos,
            identity=identity,
            ecology=ecology,
            social_profile=social_profile,
            needs=needs,
        )
        if scored is None:
            continue
        if best is None or float(scored["score"]) > float(best["score"]):
            best = {
                "eid": other_eid,
                "target": (int(other_pos.x), int(other_pos.y), int(other_pos.z)),
                **scored,
            }

    if best is None:
        return None
    if float(best["score"]) < 26.0:
        return None

    bonded_target = getattr(context, "bonded_to_eid", None)
    follow_drive = float(getattr(social_profile, "follow_drive", 0.0) or 0.0)
    if bonded_target == best["eid"] and best["kind"] == "human" and best["distance"] >= 2:
        follow_score = float(best["score"]) + (follow_drive * 0.4) + (float(best.get("bond_score", 0.0) or 0.0) * 24.0)
        if follow_score >= 44.0:
            return {
                "intent": "following",
                "score": min(92.0, follow_score),
                "target": best["target"],
                "target_eid": best["eid"],
            }

    return {
        "intent": "seeking_companionship",
        "score": min(88.0, float(best["score"])),
        "target": best["target"],
        "target_eid": best["eid"],
    }


def _wildlife_ecology_intent(sim, eid, pos, routine, behavior, identity, needs):
    ecology = _animal_ecology_profile_for_actor(sim, eid)
    physical = _animal_physical_profile_for_actor(sim, eid)
    if ecology is None or physical is None or identity is None:
        return None

    context = _animal_behavior_context_for_actor(sim, eid)
    observe_radius = max(4, int(getattr(behavior, "flee_radius", 5)) + 2, int(getattr(behavior, "home_radius", 4)) + 1)
    positions = sim.ecs.get(Position)
    best_threat = None
    best_chase = None

    for other_eid, other_pos in positions.items():
        if other_eid == eid or int(other_pos.z) != int(pos.z):
            continue
        if _entity_is_downed(sim, other_eid):
            continue
        if not _wildlife_can_observe(sim, pos, other_pos, radius=observe_radius):
            continue
        distance = _grid_distance(pos.x, pos.y, other_pos.x, other_pos.y)
        threat = _wildlife_threat_score(
            sim,
            eid,
            other_eid,
            self_identity=identity,
            self_physical=physical,
            self_ecology=ecology,
            self_context=context,
            distance=distance,
        )
        if threat is not None and (best_threat is None or threat["score"] > best_threat["score"]):
            best_threat = {
                "eid": other_eid,
                "pos": (other_pos.x, other_pos.y, other_pos.z),
                **threat,
            }

        chase = _wildlife_chase_drive(
            sim,
            eid,
            other_eid,
            self_identity=identity,
            self_physical=physical,
            self_ecology=ecology,
            self_context=context,
            distance=distance,
        )
        if chase is not None and (best_chase is None or chase["score"] > best_chase["score"]):
            best_chase = {
                "eid": other_eid,
                "pos": (other_pos.x, other_pos.y, other_pos.z),
                **chase,
            }

    scavenge = _wildlife_best_scavenge_target(sim, pos, ecology, context)
    group_alarm = _wildlife_group_alarm_target(sim, eid, pos, identity, ecology, behavior)

    if best_threat and best_threat["score"] >= 34.0:
        guardian_bonus = _wildlife_guardian_bonus(sim, eid, pos, identity, ecology, behavior)
        pack_support = _wildlife_pack_support(sim, eid, pos, identity, ecology, behavior)
        hold_drive = float(getattr(ecology, "territorial_score", 0.0) or 0.0) * (1.15 if bool(getattr(context, "territorial_context", False)) else 0.45)
        hold_drive += guardian_bonus
        hold_drive += pack_support * 4.5
        if bool(getattr(context, "cornered", False)):
            hold_drive += 12.0
        if bool(getattr(physical, "juvenile", False)):
            hold_drive -= 26.0
        hold_drive -= _actor_injury_score(sim, eid, physical) * 0.45

        if hold_drive >= max(42.0, best_threat["score"] - 6.0) and (
            best_threat["kind"] == "animal" or best_threat["score"] <= 68.0
        ):
            return {
                "intent": "holding",
                "score": min(96.0, hold_drive),
                "target": (int(pos.x), int(pos.y), int(pos.z)),
                "target_eid": None,
            }

        escape_target = _pick_wildlife_escape_target(
            sim,
            pos,
            best_threat["pos"],
            routine,
            behavior,
        )
        return {
            "intent": "seeking_safety",
            "score": min(98.0, max(40.0, best_threat["score"] + float(getattr(ecology, "flee_bias", 0.0) or 0.0) * 0.12)),
            "target": escape_target or _wildlife_home_position(pos, routine) or (int(pos.x), int(pos.y), int(pos.z)),
            "target_eid": None,
        }

    if group_alarm:
        return {
            "intent": "seeking_safety",
            "score": 72.0 + (float(getattr(ecology, "pack_score", 0.0) or 0.0) * 0.12),
            "target": tuple(group_alarm),
            "target_eid": None,
        }

    if scavenge and scavenge["score"] >= max(36.0, (best_chase["score"] + 8.0) if best_chase else 36.0):
        return {
            "intent": "scavenging",
            "score": min(88.0, scavenge["score"]),
            "target": scavenge["target"],
            "target_eid": None,
        }

    if best_chase and best_chase["score"] >= 26.0:
        return {
            "intent": "chasing",
            "score": min(90.0, best_chase["score"]),
            "target": best_chase["pos"],
            "target_eid": best_chase["eid"],
        }

    return None


def _wildlife_home_position(pos, routine):
    if routine and isinstance(getattr(routine, "home", None), (list, tuple)) and len(routine.home) >= 3:
        try:
            return (int(routine.home[0]), int(routine.home[1]), int(routine.home[2]))
        except (TypeError, ValueError):
            pass
    if pos is None:
        return None
    return (int(pos.x), int(pos.y), int(pos.z))


def _wildlife_walkable_tiles(sim, origin, *, radius=4, outside_only=True, include_origin=False):
    if not isinstance(origin, (list, tuple)) or len(origin) < 3:
        return []
    ox, oy, oz = int(origin[0]), int(origin[1]), int(origin[2])
    radius = max(1, int(radius))
    seen = set()
    tiles = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if not include_origin and dx == 0 and dy == 0:
                continue
            if max(abs(dx), abs(dy)) > radius:
                continue
            tx = ox + dx
            ty = oy + dy
            if not sim.tilemap.is_walkable(tx, ty, oz):
                continue
            if outside_only and _property_covering(sim, tx, ty, oz):
                continue
            tile = (tx, ty, oz)
            if tile in seen:
                continue
            seen.add(tile)
            tiles.append(tile)
    return tiles


def _wildlife_is_active(behavior, hour):
    period = str(getattr(behavior, "activity_period", "any") or "any").strip().lower()
    try:
        hour = int(hour) % 24
    except (TypeError, ValueError):
        hour = 12
    if period == "day":
        return 6 <= hour < 19
    if period == "night":
        return hour >= 19 or hour < 6
    if period == "crepuscular":
        return (5 <= hour < 8) or (17 <= hour < 20)
    return True


def _wildlife_flock_anchor(sim, eid, pos, identity, behavior):
    if not pos or not identity or not getattr(behavior, "flocking", False):
        return None
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    identities = sim.ecs.get(CreatureIdentity)
    flock_radius = max(1, int(getattr(behavior, "flock_radius", 3)))
    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
    if not taxonomy:
        return None

    samples = []
    for other_eid, other_pos in positions.items():
        if other_eid == eid or int(other_pos.z) != int(pos.z):
            continue
        if _manhattan(pos.x, pos.y, other_pos.x, other_pos.y) > flock_radius:
            continue
        other_ai = ais.get(other_eid)
        if str(getattr(other_ai, "role", "") or "").strip().lower() != "wildlife":
            continue
        other_identity = identities.get(other_eid)
        other_taxonomy = str(getattr(other_identity, "taxonomy_class", "") or "").strip().lower()
        if other_taxonomy != taxonomy:
            continue
        samples.append((int(other_pos.x), int(other_pos.y)))

    if not samples:
        return None
    avg_x = int(round(sum(x for x, _y in samples) / float(len(samples))))
    avg_y = int(round(sum(y for _x, y in samples) / float(len(samples))))
    return (avg_x, avg_y, int(pos.z))


def _pick_wildlife_patrol_target(sim, eid, pos, routine, behavior, identity):
    home = _wildlife_home_position(pos, routine)
    if not home:
        return None

    radius = max(2, int(getattr(behavior, "home_radius", 4)))
    candidates = _wildlife_walkable_tiles(
        sim,
        home,
        radius=radius,
        outside_only=True,
        include_origin=False,
    )
    if not candidates:
        return home

    flock_anchor = _wildlife_flock_anchor(sim, eid, pos, identity, behavior)
    rest_bias = float(getattr(behavior, "rest_bias", 0.3) or 0.3)
    rng = random.Random(f"{sim.seed}:{eid}:{sim.tick}:wildlife_patrol")
    best_tile = None
    best_score = float("-inf")

    for tile in candidates:
        tx, ty, tz = tile
        if tz != int(pos.z):
            continue
        dist_from_pos = _manhattan(pos.x, pos.y, tx, ty)
        dist_from_home = _manhattan(home[0], home[1], tx, ty)
        score = rng.random()
        score += min(2.8, float(dist_from_pos) * 0.42)
        score -= float(dist_from_home) * rest_bias * 0.22
        if dist_from_pos <= 1:
            score -= 0.75
        if flock_anchor:
            cluster_dist = _manhattan(tx, ty, flock_anchor[0], flock_anchor[1])
            score += max(0.0, float(getattr(behavior, "flock_radius", 3)) - float(cluster_dist)) * 0.35
        if score > best_score:
            best_score = score
            best_tile = tile

    return best_tile or home


def _pick_wildlife_escape_target(sim, pos, threat, routine, behavior):
    if pos is None or not isinstance(threat, (list, tuple)) or len(threat) < 3:
        return None
    home = _wildlife_home_position(pos, routine)
    if not home:
        home = (int(pos.x), int(pos.y), int(pos.z))

    search_radius = max(
        int(getattr(behavior, "home_radius", 4)) + 2,
        int(getattr(behavior, "flee_radius", 5)) + 2,
    )
    candidate_map = {}
    for tile in _wildlife_walkable_tiles(sim, home, radius=search_radius, outside_only=True, include_origin=True):
        candidate_map[tile] = tile
    for tile in _wildlife_walkable_tiles(
        sim,
        (int(pos.x), int(pos.y), int(pos.z)),
        radius=max(2, int(getattr(behavior, "flee_radius", 5)) + 1),
        outside_only=True,
        include_origin=True,
    ):
        candidate_map[tile] = tile

    if not candidate_map:
        return home

    tx, ty, tz = int(threat[0]), int(threat[1]), int(threat[2])
    current_threat_dist = _manhattan(pos.x, pos.y, tx, ty)
    rng = random.Random(f"{sim.seed}:{int(pos.x)}:{int(pos.y)}:{int(pos.z)}:{tx}:{ty}:{sim.tick}:wildlife_escape")
    best_tile = None
    best_score = float("-inf")

    for tile in candidate_map.values():
        cx, cy, cz = tile
        if cz != int(pos.z):
            continue
        threat_dist = _manhattan(cx, cy, tx, ty)
        if threat_dist <= 1:
            continue
        home_dist = _manhattan(home[0], home[1], cx, cy)
        step_dist = _manhattan(pos.x, pos.y, cx, cy)
        score = rng.random() * 0.5
        score += float(threat_dist) * 2.4
        score -= float(home_dist) * 0.16
        score -= float(step_dist) * 0.08
        if threat_dist <= current_threat_dist:
            score -= 1.2
        if score > best_score:
            best_score = score
            best_tile = tile

    return best_tile or home


def _relocate_indoor_wildlife_outdoors(sim, eid, pos, routine):
    if pos is None:
        return False
    covered = _property_covering(sim, pos.x, pos.y, pos.z)
    if not (covered and str(covered.get("kind", "building")).strip().lower() == "building"):
        return False

    search_origins = [
        (int(pos.x), int(pos.y), int(pos.z)),
        _wildlife_home_position(pos, routine),
    ]
    candidates = []
    seen = set()
    for origin in search_origins:
        for radius in (4, 6, 8):
            for tile in _wildlife_walkable_tiles(
                sim,
                origin,
                radius=radius,
                outside_only=True,
                include_origin=False,
            ):
                if tile in seen:
                    continue
                seen.add(tile)
                candidates.append(tile)
            if candidates:
                break
        if candidates:
            break

    if not candidates:
        return False

    candidates.sort(key=lambda tile: (_manhattan(pos.x, pos.y, tile[0], tile[1]), abs(int(tile[2]) - int(pos.z))))
    new_x, new_y, new_z = candidates[0]
    sim.tilemap.move_entity(
        eid,
        oldx=pos.x,
        oldy=pos.y,
        oldz=pos.z,
        newx=new_x,
        newy=new_y,
        newz=new_z,
    )
    pos.x = int(new_x)
    pos.y = int(new_y)
    pos.z = int(new_z)
    if routine and isinstance(getattr(routine, "home", None), (list, tuple)) and len(routine.home) >= 3:
        home_prop = _property_covering(sim, routine.home[0], routine.home[1], routine.home[2])
        if home_prop and str(home_prop.get("kind", "building")).strip().lower() == "building":
            routine.home = (int(new_x), int(new_y), int(new_z))
    return True
