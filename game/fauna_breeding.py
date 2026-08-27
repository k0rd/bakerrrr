"""Loaded-state fauna reproduction and inherited offspring realization."""

from __future__ import annotations

import copy
import hashlib
import random

from engine.events import Event
from engine.systems import System
from game.components import (
    AI,
    AnimalBehaviorContext,
    AnimalGenome,
    AnimalMemory,
    AnimalPhysicalProfile,
    AnimalReproduction,
    AnimalSocialProfile,
    Collider,
    CoverState,
    CreatureIdentity,
    EcologyProfile,
    ItemUseProfile,
    MovementThrottle,
    NoiseProfile,
    NPCNeeds,
    NPCRoutine,
    NPCWill,
    Position,
    Render,
    StatusEffects,
    Vitality,
    WildlifeBehavior,
    WildlifeSocialState,
)
from game.ecology_registry import ecology_registry_write_batch, register_native_fauna_line
from game.fauna_genetics import (
    GENERIC_BODY_CHANNELS,
    animal_descendant_is_emergent_species,
    animal_emergent_species_id,
    animal_genome_from_payload,
    animal_genome_payload,
    apply_animal_genome_expression,
    fauna_genomes_compatible,
    inherit_animal_genome,
    taxonomy_for_animal_genome,
)
from game.fauna_naming import (
    apply_fauna_phenotype_descriptor,
    generate_fauna_line_name,
    generate_fauna_species_name,
)


BREEDING_UPDATE_INTERVAL = 120
BREEDING_PAIR_RADIUS = 3
BREEDING_CYCLE_TICKS = 7200
MAX_CONCEPTIONS_PER_UPDATE = 3
MAX_BIRTHS_PER_UPDATE = 6


def _key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or str(fallback or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _distance(left, right):
    if left is None or right is None or int(left.z) != int(right.z):
        return 10_000
    return abs(int(left.x) - int(right.x)) + abs(int(left.y) - int(right.y))


def _loaded_actor(sim, eid):
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return False
    try:
        return str(sim.detail_for_xy(pos.x, pos.y)).strip().lower() != "unloaded"
    except Exception:
        return True


def _reproduction_roles_compatible(left, right):
    if left is None or right is None:
        return False
    if left.mode == "none" or right.mode == "none":
        return False
    if "any_pair" in {left.mode, right.mode} or "any" in {left.gamete_role, right.gamete_role}:
        return True
    return {left.gamete_role, right.gamete_role} == {"a", "b"}


def _adult_and_well(sim, eid, reproduction):
    if reproduction is None or int(sim.tick) < int(reproduction.maturity_tick):
        return False
    physical = sim.ecs.get(AnimalPhysicalProfile).get(eid)
    if physical is not None and bool(getattr(physical, "juvenile", False)):
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and (bool(getattr(vitality, "downed", False)) or int(getattr(vitality, "hp", 0) or 0) <= 0):
        return False
    needs = sim.ecs.get(NPCNeeds).get(eid)
    if needs is not None:
        if float(getattr(needs, "energy", 0.0) or 0.0) < 54.0:
            return False
        if float(getattr(needs, "safety", 0.0) or 0.0) < 48.0:
            return False
        if float(getattr(needs, "hunger", 0.0) or 0.0) < 48.0:
            return False
        if float(getattr(needs, "thirst", 0.0) or 0.0) < 48.0:
            return False
    return True


def fauna_pair_compatibility(sim, left_eid, right_eid, *, ignore_schedule=False):
    if left_eid == right_eid:
        return {"ok": False, "reason": "same_actor"}
    genomes = sim.ecs.get(AnimalGenome)
    reproductions = sim.ecs.get(AnimalReproduction)
    positions = sim.ecs.get(Position)
    left_genome = genomes.get(left_eid)
    right_genome = genomes.get(right_eid)
    left_reproduction = reproductions.get(left_eid)
    right_reproduction = reproductions.get(right_eid)
    if left_genome is None or right_genome is None:
        return {"ok": False, "reason": "missing_genome"}
    if not fauna_genomes_compatible(left_genome, right_genome):
        return {"ok": False, "reason": "different_root_animals"}
    if not _reproduction_roles_compatible(left_reproduction, right_reproduction):
        return {"ok": False, "reason": "reproductive_roles_incompatible"}
    if not _adult_and_well(sim, left_eid, left_reproduction) or not _adult_and_well(sim, right_eid, right_reproduction):
        return {"ok": False, "reason": "not_mature_or_well"}
    if left_reproduction.gestation or right_reproduction.gestation:
        return {"ok": False, "reason": "already_gestating"}
    if not ignore_schedule and (
        int(sim.tick) < int(left_reproduction.next_breed_tick)
        or int(sim.tick) < int(right_reproduction.next_breed_tick)
    ):
        return {"ok": False, "reason": "breeding_cycle"}
    left_pos = positions.get(left_eid)
    right_pos = positions.get(right_eid)
    if _distance(left_pos, right_pos) > BREEDING_PAIR_RADIUS:
        return {"ok": False, "reason": "too_far"}
    return {
        "ok": True,
        "left_genome": left_genome,
        "right_genome": right_genome,
        "left_reproduction": left_reproduction,
        "right_reproduction": right_reproduction,
    }


def _carrier_for_pair(left_eid, right_eid, left_reproduction, right_reproduction):
    if left_reproduction.gamete_role == "b" and right_reproduction.gamete_role != "b":
        return left_eid, right_eid
    if right_reproduction.gamete_role == "b" and left_reproduction.gamete_role != "b":
        return right_eid, left_eid
    return (left_eid, right_eid) if int(left_eid) < int(right_eid) else (right_eid, left_eid)


def begin_fauna_gestation(sim, left_eid, right_eid, *, assisted_by_eid=None, ignore_schedule=False):
    result = fauna_pair_compatibility(sim, left_eid, right_eid, ignore_schedule=ignore_schedule)
    if not result.get("ok"):
        return result
    left_reproduction = result["left_reproduction"]
    right_reproduction = result["right_reproduction"]
    carrier_eid, co_parent_eid = _carrier_for_pair(left_eid, right_eid, left_reproduction, right_reproduction)
    carrier = sim.ecs.get(AnimalReproduction)[carrier_eid]
    co_parent_genome = sim.ecs.get(AnimalGenome)[co_parent_eid]
    brood_lo = max(1, int(carrier.brood_min))
    brood_hi = max(brood_lo, int(carrier.brood_max))
    rng = random.Random(f"{sim.seed}:{sim.tick}:{carrier_eid}:{co_parent_eid}:fauna-gestation")
    brood_size = rng.randint(brood_lo, brood_hi)
    carrier.gestation = {
        "carrier_eid": int(carrier_eid),
        "co_parent_eid": int(co_parent_eid),
        "co_parent_genome": animal_genome_payload(co_parent_genome),
        "conceived_tick": int(sim.tick),
        "due_tick": int(sim.tick) + max(1, int(carrier.gestation_ticks)),
        "brood_size": brood_size,
        "assisted_by_eid": assisted_by_eid,
    }
    cycle_due = int(sim.tick) + BREEDING_CYCLE_TICKS
    left_reproduction.next_breed_tick = cycle_due
    right_reproduction.next_breed_tick = cycle_due
    left_reproduction.assisted_by_eid = assisted_by_eid
    right_reproduction.assisted_by_eid = assisted_by_eid
    positions = sim.ecs.get(Position)
    pos = positions.get(carrier_eid)
    sim.emit(Event(
        "fauna_conceived",
        carrier_eid=carrier_eid,
        co_parent_eid=co_parent_eid,
        root_animal_id=result["left_genome"].root_animal_id,
        brood_size=brood_size,
        due_tick=carrier.gestation["due_tick"],
        assisted_by_eid=assisted_by_eid,
        x=getattr(pos, "x", None),
        y=getattr(pos, "y", None),
        z=getattr(pos, "z", None),
    ))
    return {
        "ok": True,
        "carrier_eid": carrier_eid,
        "co_parent_eid": co_parent_eid,
        "brood_size": brood_size,
        "due_tick": carrier.gestation["due_tick"],
        "assisted_by_eid": assisted_by_eid,
    }


def assist_fauna_breeding(sim, actor_eid, left_eid, right_eid):
    """Player/NPC husbandry seam: bypass timing, never compatibility or health."""

    return begin_fauna_gestation(
        sim,
        left_eid,
        right_eid,
        assisted_by_eid=actor_eid,
        ignore_schedule=True,
    )


def _adjacent_birth_position(sim, parent_pos, *, token):
    options = (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (-1, 1),
        (1, -1),
        (-1, -1),
        (0, 0),
    )
    digest = hashlib.sha256(str(token).encode("utf-8")).digest()
    start = int.from_bytes(digest[:4], "big") % len(options)
    for offset in range(len(options)):
        dx, dy = options[(start + offset) % len(options)]
        x, y, z = int(parent_pos.x) + dx, int(parent_pos.y) + dy, int(parent_pos.z)
        tile = sim.tilemap.tile_at(x, y, z)
        if tile is None or not bool(getattr(tile, "walkable", False)):
            continue
        if sim.tilemap.entities_at(x, y, z):
            continue
        return (x, y, z)
    return (int(parent_pos.x), int(parent_pos.y), int(parent_pos.z))


def _average(left, right, field, default):
    values = []
    for obj in (left, right):
        try:
            values.append(float(getattr(obj, field)))
        except (AttributeError, TypeError, ValueError):
            pass
    return sum(values) / len(values) if values else float(default)


def _fauna_species_id(identity, ecology=None):
    explicit = _key(getattr(identity, "fauna_species_id", "")) if identity is not None else ""
    if explicit:
        return explicit
    ecological = _key(getattr(ecology, "species", "")) if ecology is not None else ""
    if ecological:
        return ecological
    return _key(getattr(identity, "species", ""), "local_creature") if identity is not None else "local_creature"


def _fauna_ancestry(identity):
    values = tuple(getattr(identity, "ancestral_species", ()) or ()) if identity is not None else ()
    if not values and identity is not None:
        values = (getattr(identity, "species", "local creature"),)
    return tuple(dict.fromkeys(
        str(value).strip().lower()
        for value in values
        if str(value).strip()
    ))


def _descendant_species_profile(child, left, right, left_identity, right_identity, left_ecology, right_ecology):
    parent_species_ids = tuple(dict.fromkeys((
        _fauna_species_id(left_identity, left_ecology),
        _fauna_species_id(right_identity, right_ecology),
    )))
    parent_taxonomies = (
        getattr(left_identity, "taxonomy_class", "other"),
        getattr(right_identity, "taxonomy_class", "other"),
    )
    emergent = animal_descendant_is_emergent_species(
        child,
        left,
        right,
        parent_species=parent_species_ids,
        parent_taxonomies=parent_taxonomies,
    )
    if emergent:
        species_id = animal_emergent_species_id(
            child,
            left,
            right,
            parent_species_ids=parent_species_ids,
        )
        species_name = generate_fauna_species_name(
            child,
            parent_species_ids=parent_species_ids,
            mixed_parent_species=len(set(parent_species_ids)) > 1,
        )
    else:
        species_id = parent_species_ids[0] if parent_species_ids else "local_creature"
        species_name = str(
            getattr(left_identity, "species", "")
            or getattr(right_identity, "species", "")
            or species_id
        ).strip().lower()
    ancestry = tuple(dict.fromkeys(_fauna_ancestry(left_identity) + _fauna_ancestry(right_identity)))
    return {
        "emergent": emergent,
        "species_id": species_id,
        "species_name": species_name or "local creature",
        "taxonomy_class": taxonomy_for_animal_genome(child, fallback=parent_taxonomies[0]),
        "ancestral_species": ancestry,
        "population_key": f"species:{species_id}",
    }


def _spawn_fauna_offspring(sim, carrier_eid, co_parent_eid, co_parent_genome_payload, *, brood_index, assisted_by_eid=None):
    positions = sim.ecs.get(Position)
    parent_pos = positions.get(carrier_eid)
    carrier_genome = sim.ecs.get(AnimalGenome).get(carrier_eid)
    if parent_pos is None or carrier_genome is None:
        return None
    co_parent_genome = sim.ecs.get(AnimalGenome).get(co_parent_eid)
    if co_parent_genome is None:
        co_parent_genome = animal_genome_from_payload(
            co_parent_genome_payload,
            seed=sim.seed,
            identity_token=f"gestation:{carrier_eid}:{co_parent_eid}:{brood_index}",
        )
    if co_parent_genome is None:
        return None
    token = f"{sim.seed}:{sim.tick}:{carrier_eid}:{co_parent_eid}:{brood_index}"
    child_genome = inherit_animal_genome(
        carrier_genome,
        co_parent_genome,
        seed=sim.seed,
        birth_token=token,
        body_channels=GENERIC_BODY_CHANNELS,
    )
    if child_genome is None:
        return None
    child_pos = _adjacent_birth_position(sim, parent_pos, token=token)
    identities = sim.ecs.get(CreatureIdentity)
    parent_identity = identities.get(carrier_eid)
    co_parent_identity = identities.get(co_parent_eid)
    parent_physical = sim.ecs.get(AnimalPhysicalProfile).get(carrier_eid)
    co_parent_physical = sim.ecs.get(AnimalPhysicalProfile).get(co_parent_eid)
    parent_ecology = sim.ecs.get(EcologyProfile).get(carrier_eid)
    co_parent_ecology = sim.ecs.get(EcologyProfile).get(co_parent_eid)
    parent_social = sim.ecs.get(AnimalSocialProfile).get(carrier_eid)
    co_parent_social = sim.ecs.get(AnimalSocialProfile).get(co_parent_eid)
    parent_behavior = sim.ecs.get(WildlifeBehavior).get(carrier_eid)
    parent_throttle = sim.ecs.get(MovementThrottle).get(carrier_eid)
    parent_noise = sim.ecs.get(NoiseProfile).get(carrier_eid)
    adult_size = _average(parent_physical, co_parent_physical, "size_score", 18.0)
    adult_speed = _average(parent_physical, co_parent_physical, "speed_score", 32.0)
    parent_common_names = (
        str(getattr(parent_identity, "fauna_line_name", "") or getattr(parent_identity, "common_name", "") or "local creature").strip(),
        str(getattr(co_parent_identity, "fauna_line_name", "") or getattr(co_parent_identity, "common_name", "") or "local creature").strip(),
    )
    line_name = generate_fauna_line_name(
        child_genome,
        parent_names=parent_common_names,
        seed_token=token,
    )
    species_profile = _descendant_species_profile(
        child_genome,
        carrier_genome,
        co_parent_genome,
        parent_identity,
        co_parent_identity,
        parent_ecology,
        co_parent_ecology,
    )
    identity = CreatureIdentity(
        taxonomy_class=species_profile["taxonomy_class"],
        species=species_profile["species_name"],
        creature_type="animal",
        common_name=f"young {line_name}",
        coat_variant=None,
        fauna_line_name=line_name,
        fauna_species_id=species_profile["species_id"],
        ancestral_species=species_profile["ancestral_species"],
        fauna_population_key=species_profile["population_key"],
    )
    physical = AnimalPhysicalProfile(
        size_score=max(1.0, adult_size * 0.58),
        speed_score=max(1.0, adult_speed * 0.9),
        juvenile=True,
    )
    ecology = EcologyProfile(
        species=species_profile["species_id"],
        predator_score=_average(parent_ecology, co_parent_ecology, "predator_score", 10.0),
        prey_score=_average(parent_ecology, co_parent_ecology, "prey_score", 24.0),
        scavenger_score=_average(parent_ecology, co_parent_ecology, "scavenger_score", 18.0),
        territorial_score=_average(parent_ecology, co_parent_ecology, "territorial_score", 18.0) * 0.55,
        pack_score=_average(parent_ecology, co_parent_ecology, "pack_score", 18.0),
        flee_bias=min(100.0, _average(parent_ecology, co_parent_ecology, "flee_bias", 58.0) + 12.0),
        chase_bias=_average(parent_ecology, co_parent_ecology, "chase_bias", 18.0) * 0.6,
    )
    social = AnimalSocialProfile(
        sociability=_average(parent_social, co_parent_social, "sociability", 20.0),
        same_species_affinity=_average(parent_social, co_parent_social, "same_species_affinity", 28.0) + 8.0,
        human_affinity=_average(parent_social, co_parent_social, "human_affinity", 0.0),
        domesticity=_average(parent_social, co_parent_social, "domesticity", 0.0),
        companionship_drive=_average(parent_social, co_parent_social, "companionship_drive", 10.0),
        follow_drive=_average(parent_social, co_parent_social, "follow_drive", 4.0),
    )
    carrier_reproduction = sim.ecs.get(AnimalReproduction).get(carrier_eid)
    reproduction = AnimalReproduction(
        mode=str(getattr(carrier_reproduction, "mode", "paired") or "paired"),
        gamete_role="a" if random.Random(f"{token}:gamete-role").random() < 0.5 else "b",
        maturity_tick=int(sim.tick) + 2400,
        next_breed_tick=int(sim.tick) + 9600,
        gestation_ticks=max(480, int(getattr(carrier_reproduction, "gestation_ticks", 1200) or 1200)),
        brood_min=max(1, int(getattr(carrier_reproduction, "brood_min", 1) or 1)),
        brood_max=max(1, int(getattr(carrier_reproduction, "brood_max", 1) or 1)),
        assisted_by_eid=assisted_by_eid,
    )
    reproduction.adult_size_score = adult_size
    reproduction.adult_speed_score = adult_speed

    eid = sim.ecs.create()
    components = (
        Position(*child_pos),
        Render(CreatureIdentity.GLYPH_BY_TAXONOMY.get(identity.taxonomy_class, "O"), color=getattr(sim.ecs.get(Render).get(carrier_eid), "color", None)),
        identity,
        AI("wildlife"),
        MovementThrottle(
            default_cooldown=int(getattr(parent_throttle, "default_cooldown", 3) or 3),
            state_cooldowns=dict(getattr(parent_throttle, "state_cooldowns", {}) or {}),
            speed_multiplier=max(0.35, float(getattr(parent_throttle, "speed_multiplier", 1.0) or 1.0) * 0.9),
        ),
        Collider(blocks=True),
        NoiseProfile(move_radius=max(1, int(getattr(parent_noise, "move_radius", 2) or 2))),
        NPCNeeds(energy=76.0, safety=78.0, social=62.0, hunger=82.0, thirst=84.0),
        NPCWill(),
        StatusEffects(),
        Vitality(max_hp=max(4, int(round(adult_size * 0.28)))),
        CoverState(),
        physical,
        ecology,
        AnimalBehaviorContext(hunger=38.0),
        social,
        AnimalMemory(),
        WildlifeSocialState(),
        ItemUseProfile(willingness=0.0, risk_tolerance=0.04, auto_use=False, cooldown_ticks=30),
        NPCRoutine(home=child_pos, work=None),
        copy.deepcopy(parent_behavior) if parent_behavior is not None else WildlifeBehavior(),
        child_genome,
        reproduction,
    )
    for component in components:
        sim.ecs.add(eid, component)
    sim.tilemap.add_entity(eid, *child_pos)
    social_state = sim.ecs.get(WildlifeSocialState).get(eid)
    if social_state is not None:
        social_state.add_bond(carrier_eid, kind="parent", closeness=0.82, trust=0.86, comfort=0.9)
        social_state.add_bond(co_parent_eid, kind="parent", closeness=0.68, trust=0.7, comfort=0.72)
    apply_animal_genome_expression(sim, eid, child_genome)
    # Maturity restores the adult expression of this child's own build rather
    # than merely snapping it to an unexpressed parental average.
    reproduction.adult_size_score = max(1.0, float(physical.size_score) / 0.58)
    reproduction.adult_speed_score = max(1.0, float(physical.speed_score) / 0.9)
    child_vitality = sim.ecs.get(Vitality).get(eid)
    reproduction.adult_max_hp = max(
        int(getattr(child_vitality, "max_hp", 1) or 1),
        int(round(float(getattr(child_vitality, "max_hp", 1) or 1) / 0.58)),
    )
    child_abilities = set((child_genome.expressed or {}).get("abilities") or ())
    reproduction.adult_ecology_profile = {
        "predator_score": _average(parent_ecology, co_parent_ecology, "predator_score", 10.0),
        "prey_score": max(0.0, _average(parent_ecology, co_parent_ecology, "prey_score", 24.0) - (14.0 if "camouflage" in child_abilities else 0.0)),
        "scavenger_score": _average(parent_ecology, co_parent_ecology, "scavenger_score", 18.0),
        "territorial_score": min(100.0, _average(parent_ecology, co_parent_ecology, "territorial_score", 18.0) + (12.0 if "fright_display" in child_abilities else 0.0)),
        "pack_score": min(100.0, _average(parent_ecology, co_parent_ecology, "pack_score", 18.0) + (18.0 if "herd_mind" in child_abilities else 0.0)),
        "flee_bias": min(100.0, _average(parent_ecology, co_parent_ecology, "flee_bias", 58.0) + (8.0 if "keen_senses" in child_abilities else 0.0)),
        "chase_bias": min(100.0, _average(parent_ecology, co_parent_ecology, "chase_bias", 18.0) + (5.0 if "keen_senses" in child_abilities else 0.0)),
    }
    register_native_fauna_line(
        sim,
        eid,
        child_genome,
        source="assisted_breeding" if assisted_by_eid is not None else "natural_breeding",
    )
    sim.emit(Event(
        "fauna_born",
        eid=eid,
        carrier_eid=carrier_eid,
        co_parent_eid=co_parent_eid,
        assisted_by_eid=assisted_by_eid,
        root_animal_id=child_genome.root_animal_id,
        lineage_id=child_genome.lineage_id,
        genome_id=child_genome.genome_id,
        generation=child_genome.generation,
        mutation_signature=child_genome.mutation_signature,
        color_word=child_genome.expressed.get("color_word"),
        pattern=child_genome.expressed.get("pattern"),
        abilities=tuple(child_genome.expressed.get("abilities") or ()),
        taxonomy_class=species_profile["taxonomy_class"],
        species=species_profile["species_name"],
        species_id=species_profile["species_id"],
        emergent_species=species_profile["emergent"],
        ancestral_species=species_profile["ancestral_species"],
        population_key=species_profile["population_key"],
        x=child_pos[0],
        y=child_pos[1],
        z=child_pos[2],
    ))
    return eid


class FaunaBreedingSystem(System):
    """Bounded breeding over currently realized animals only."""

    def _mature_juveniles(self):
        physicals = self.sim.ecs.get(AnimalPhysicalProfile)
        identities = self.sim.ecs.get(CreatureIdentity)
        matured = 0
        for eid, reproduction in tuple(self.sim.ecs.get(AnimalReproduction).items()):
            physical = physicals.get(eid)
            if physical is None or not bool(getattr(physical, "juvenile", False)):
                continue
            if int(self.sim.tick) < int(reproduction.maturity_tick):
                continue
            physical.juvenile = False
            if hasattr(reproduction, "adult_size_score"):
                physical.size_score = max(float(physical.size_score), float(reproduction.adult_size_score))
            if hasattr(reproduction, "adult_speed_score"):
                physical.speed_score = max(float(physical.speed_score), float(reproduction.adult_speed_score))
            vitality = self.sim.ecs.get(Vitality).get(eid)
            if vitality is not None and hasattr(reproduction, "adult_max_hp"):
                old_max = max(1, int(getattr(vitality, "max_hp", 1) or 1))
                health_fraction = max(0.0, min(1.0, float(getattr(vitality, "hp", old_max) or 0) / old_max))
                vitality.max_hp = max(old_max, int(reproduction.adult_max_hp))
                vitality.hp = max(1, int(round(vitality.max_hp * health_fraction)))
            ecology = self.sim.ecs.get(EcologyProfile).get(eid)
            adult_ecology = getattr(reproduction, "adult_ecology_profile", None)
            if ecology is not None and isinstance(adult_ecology, dict):
                for field, value in adult_ecology.items():
                    if hasattr(ecology, field):
                        setattr(ecology, field, float(value))
            identity = identities.get(eid)
            if identity is not None:
                common = str(getattr(identity, "common_name", "") or "").strip()
                if common.lower().startswith("young "):
                    identity.common_name = common[6:].strip() or common
                apply_fauna_phenotype_descriptor(
                    identity,
                    self.sim.ecs.get(AnimalGenome).get(eid),
                )
            self.sim.emit(Event("fauna_matured", eid=eid))
            matured += 1
        return matured

    def _birth_due_gestations(self):
        with ecology_registry_write_batch(self.sim):
            return self._birth_due_gestations_batched()

    def _birth_due_gestations_batched(self):
        births = 0
        for carrier_eid, reproduction in tuple(self.sim.ecs.get(AnimalReproduction).items()):
            gestation = reproduction.gestation if isinstance(reproduction.gestation, dict) else {}
            if not gestation or int(self.sim.tick) < _safe_int(gestation.get("due_tick"), 0):
                continue
            brood_size = max(1, min(6, _safe_int(gestation.get("brood_size"), 1)))
            co_parent_eid = _safe_int(gestation.get("co_parent_eid"), -1)
            payload = gestation.get("co_parent_genome") if isinstance(gestation.get("co_parent_genome"), dict) else {}
            assisted_by_eid = gestation.get("assisted_by_eid")
            reproduction.gestation = {}
            for brood_index in range(brood_size):
                if births >= MAX_BIRTHS_PER_UPDATE:
                    break
                eid = _spawn_fauna_offspring(
                    self.sim,
                    carrier_eid,
                    co_parent_eid,
                    payload,
                    brood_index=brood_index,
                    assisted_by_eid=assisted_by_eid,
                )
                if eid is not None:
                    births += 1
        return births

    def _natural_conceptions(self):
        genomes = self.sim.ecs.get(AnimalGenome)
        positions = self.sim.ecs.get(Position)
        eligible = [
            eid
            for eid in sorted(genomes)
            if _loaded_actor(self.sim, eid)
            and eid in positions
            and _adult_and_well(self.sim, eid, self.sim.ecs.get(AnimalReproduction).get(eid))
        ]
        used = set()
        conceptions = 0
        for left_index, left_eid in enumerate(eligible):
            if left_eid in used or conceptions >= MAX_CONCEPTIONS_PER_UPDATE:
                continue
            for right_eid in eligible[left_index + 1:]:
                if right_eid in used:
                    continue
                result = fauna_pair_compatibility(self.sim, left_eid, right_eid)
                if not result.get("ok"):
                    continue
                started = begin_fauna_gestation(self.sim, left_eid, right_eid)
                if started.get("ok"):
                    used.update((left_eid, right_eid))
                    conceptions += 1
                    break
        return conceptions

    def update(self):
        if int(self.sim.tick) % BREEDING_UPDATE_INTERVAL != 0:
            return
        self._mature_juveniles()
        self._birth_due_gestations()
        self._natural_conceptions()


__all__ = [
    "BREEDING_CYCLE_TICKS",
    "BREEDING_PAIR_RADIUS",
    "BREEDING_UPDATE_INTERVAL",
    "FaunaBreedingSystem",
    "assist_fauna_breeding",
    "begin_fauna_gestation",
    "fauna_pair_compatibility",
]
