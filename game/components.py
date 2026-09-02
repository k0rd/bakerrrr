from dataclasses import dataclass

from game.drone_runtime import drone_loadout_summary, normalize_packed_drone_metadata
from game.items import (
    item_metadata_has_scratch_roll,
    item_metadata_with_creation_seed,
    item_inventory_slot_cost,
    item_stacks_are_compatible,
    merge_item_stack_metadata,
    prepare_item_stack_metadata,
    split_item_stack_metadata,
)
from game.incident_runtime import incident_category_label, incident_kind_label


_UNCHANGED = object()


class Position:
    def __init__(self, x, y, z=0):
        self.x = x
        self.y = y
        self.z = z


class Render:
    def __init__(
        self,
        glyph,
        color=None,
        *,
        color_word=None,
        semantic_id=None,
        layer=None,
        priority=None,
        effects=None,
        overlays=None,
        attrs=0,
        visible=True,
    ):
        self.glyph = str(glyph)[:1] or "?"
        self.color = color
        self.color_word = str(color_word).strip().lower() if str(color_word or "").strip() else None
        self.semantic_id = str(semantic_id).strip() if semantic_id else None
        self.layer = str(layer).strip().lower() if str(layer or "").strip() else None
        self.priority = None if priority is None else int(priority)
        self.effects = tuple(
            dict.fromkeys(
                str(effect).strip().lower()
                for effect in (effects or ())
                if str(effect).strip()
            )
        )
        self.overlays = tuple(overlay for overlay in (overlays or ()) if isinstance(overlay, dict))
        self.attrs = int(attrs or 0)
        self.visible = bool(visible)

    def set_appearance(
        self,
        *,
        glyph=_UNCHANGED,
        color=_UNCHANGED,
        color_word=_UNCHANGED,
        semantic_id=_UNCHANGED,
        layer=_UNCHANGED,
        priority=_UNCHANGED,
        effects=_UNCHANGED,
        overlays=_UNCHANGED,
        attrs=_UNCHANGED,
        visible=_UNCHANGED,
    ):
        if glyph is not _UNCHANGED:
            self.glyph = str(glyph)[:1] or "?"
        if color is not _UNCHANGED:
            self.color = color
        if color_word is not _UNCHANGED:
            self.color_word = str(color_word).strip().lower() if str(color_word or "").strip() else None
        if semantic_id is not _UNCHANGED:
            semantic_text = str(semantic_id).strip()
            self.semantic_id = semantic_text or None
        if layer is not _UNCHANGED:
            layer_text = str(layer).strip().lower()
            self.layer = layer_text or None
        if priority is not _UNCHANGED:
            self.priority = None if priority is None else int(priority)
        if effects is not _UNCHANGED:
            self.effects = tuple(
                dict.fromkeys(
                    str(effect).strip().lower()
                    for effect in effects
                    if str(effect).strip()
                )
            )
        if overlays is not _UNCHANGED:
            self.overlays = tuple(overlay for overlay in overlays if isinstance(overlay, dict))
        if attrs is not _UNCHANGED:
            self.attrs = int(attrs or 0)
        if visible is not _UNCHANGED:
            self.visible = bool(visible)


class PlayerControlled:
    pass


class Collider:
    def __init__(self, blocks=True):
        self.blocks = blocks


class NoiseProfile:
    def __init__(self, move_radius=5):
        self.move_radius = move_radius


class Faction:
    def __init__(self, name):
        self.name = name


def _clamp_stat(value, lo=1.0, hi=10.0, default=5.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(lo, min(hi, number)))


def _clamp_unit(value, default=0.5):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(0.0, min(1.0, number)))


def _clamp_signed_unit(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(-1.0, min(1.0, number)))


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


class InsightStats:
    """Player/NPC social insight profile for reading rumor quality.

    - perception: notices details and inconsistencies.
    - charisma: elicits clearer responses.
    - streetwise: practical lie-detection in local culture.

    Modern aliases:
    - charm -> charisma
    - common_sense -> blended perception/streetwise
    """

    def __init__(
        self,
        perception=5.0,
        charisma=5.0,
        streetwise=5.0,
        charm=None,
        common_sense=None,
    ):
        if charm is not None:
            charisma = charm
        self.perception = _clamp_stat(perception)
        self.charisma = _clamp_stat(charisma)
        self.streetwise = _clamp_stat(streetwise)
        if common_sense is not None:
            self.common_sense = common_sense

    @property
    def charm(self):
        return self.charisma

    @charm.setter
    def charm(self, value):
        self.charisma = _clamp_stat(value)

    @property
    def common_sense(self):
        return (self.perception + self.streetwise) / 2.0

    @common_sense.setter
    def common_sense(self, value):
        v = _clamp_stat(value)
        self.perception = v
        self.streetwise = v


class CoreStats:
    """Modern baseline actor stats.

    These are intentionally plain-language and can back both player progression
    and NPC generation.
    """

    def __init__(
        self,
        brawn=5.0,
        athleticism=5.0,
        dexterity=5.0,
        access=5.0,
        charm=5.0,
        common_sense=5.0,
        manual_dexterity=None,
    ):
        if manual_dexterity is not None:
            dexterity = manual_dexterity
        self.brawn = _clamp_stat(brawn)
        self.athleticism = _clamp_stat(athleticism)
        self.dexterity = _clamp_stat(dexterity)
        self.access = _clamp_stat(access)
        self.charm = _clamp_stat(charm)
        self.common_sense = _clamp_stat(common_sense)

    @property
    def manual_dexterity(self):
        return self.dexterity

    @manual_dexterity.setter
    def manual_dexterity(self, value):
        self.dexterity = _clamp_stat(value)

    # Legacy RPG aliases for interoperability while systems migrate.
    @property
    def strength(self):
        return self.brawn

    @strength.setter
    def strength(self, value):
        self.brawn = _clamp_stat(value)

    @property
    def agility(self):
        return self.athleticism

    @agility.setter
    def agility(self, value):
        self.athleticism = _clamp_stat(value)

    @property
    def charisma(self):
        return self.charm

    @charisma.setter
    def charisma(self, value):
        self.charm = _clamp_stat(value)

    @property
    def wisdom(self):
        return self.common_sense

    @wisdom.setter
    def wisdom(self, value):
        self.common_sense = _clamp_stat(value)


class SkillProfile:
    """Actor skill ratings on the same 1-10 scale as core stats.

    Ratings are explicit when authored or seeded. Systems can still derive
    fallback skill values from CoreStats/InsightStats when no profile exists.
    """

    DEFAULT_FLOOR_RATIO = 0.7
    DEFAULT_DECAY_RATE = 1.0
    DEFAULT_DECAY_RATES = {
        "perception": 0.0,
        "athletics": 1.35,
        "conversation": 0.55,
        "streetwise": 1.0,
        "intrusion": 0.65,
        "mechanics": 0.55,
        "tactics": 0.9,
    }

    def __init__(
        self,
        ratings=None,
        *,
        baselines=None,
        birth_biases=None,
        floors=None,
        decay_rates=None,
        practice=None,
        last_practiced=None,
        last_decay=None,
        recent_changes=None,
        **skills,
    ):
        self.ratings = {}
        self.baselines = {}
        self.birth_biases = {}
        self.floors = {}
        self.decay_rates = {}
        self.practice = {}
        self.last_practiced = {}
        self.last_decay = {}
        self.recent_changes = {}

        if isinstance(baselines, dict):
            for skill_id, value in baselines.items():
                key = self._skill_key(skill_id)
                if not key:
                    continue
                self.baselines[key] = _clamp_stat(value)
        if isinstance(birth_biases, dict):
            for skill_id, value in birth_biases.items():
                key = self._skill_key(skill_id)
                if not key:
                    continue
                try:
                    delta = float(value)
                except (TypeError, ValueError):
                    continue
                if abs(delta) <= 1e-9:
                    continue
                self.birth_biases[key] = delta
        if isinstance(floors, dict):
            for skill_id, value in floors.items():
                key = self._skill_key(skill_id)
                if not key:
                    continue
                self.floors[key] = _clamp_stat(value)
        if isinstance(decay_rates, dict):
            for skill_id, value in decay_rates.items():
                key = self._skill_key(skill_id)
                if not key:
                    continue
                try:
                    rate = float(value)
                except (TypeError, ValueError):
                    continue
                self.decay_rates[key] = max(0.0, min(3.0, rate))
        if isinstance(practice, dict):
            for skill_id, value in practice.items():
                key = self._skill_key(skill_id)
                if not key:
                    continue
                try:
                    amount = float(value)
                except (TypeError, ValueError):
                    amount = 0.0
                self.practice[key] = max(0.0, amount)
        if isinstance(last_practiced, dict):
            for skill_id, value in last_practiced.items():
                key = self._skill_key(skill_id)
                if not key:
                    continue
                try:
                    self.last_practiced[key] = int(value)
                except (TypeError, ValueError):
                    continue
        if isinstance(last_decay, dict):
            for skill_id, value in last_decay.items():
                key = self._skill_key(skill_id)
                if not key:
                    continue
                try:
                    self.last_decay[key] = int(value)
                except (TypeError, ValueError):
                    continue
        if isinstance(recent_changes, dict):
            for skill_id, entry in recent_changes.items():
                key = self._skill_key(skill_id)
                if not key or not isinstance(entry, dict):
                    continue
                sanitized = {}
                try:
                    sanitized["delta"] = float(entry.get("delta", 0.0))
                except (TypeError, ValueError):
                    sanitized["delta"] = 0.0
                try:
                    sanitized["tick"] = int(entry.get("tick", 0))
                except (TypeError, ValueError):
                    sanitized["tick"] = 0
                sanitized["reason"] = str(entry.get("reason", "") or "").strip().lower()
                if entry.get("value") is not None:
                    sanitized["value"] = _clamp_stat(entry.get("value"))
                self.recent_changes[key] = sanitized

        merged = {}
        if isinstance(ratings, dict):
            merged.update(ratings)
        merged.update(skills)
        for skill_id, value in merged.items():
            self.set(skill_id, value, update_baseline=(self._skill_key(skill_id) not in self.baselines))

    def _skill_key(self, skill_id):
        key = str(skill_id or "").strip().lower()
        return key

    def get(self, skill_id, default=None):
        key = self._skill_key(skill_id)
        if not key:
            return default
        if key not in self.ratings:
            return default
        return float(self.ratings[key])

    def set(self, skill_id, value, *, update_baseline=False):
        key = self._skill_key(skill_id)
        if not key:
            return
        clamped = _clamp_stat(value)
        self.ratings[key] = clamped
        if update_baseline or key not in self.baselines:
            self.baselines[key] = clamped

    def update(self, ratings=None, **skills):
        merged = {}
        if isinstance(ratings, dict):
            merged.update(ratings)
        merged.update(skills)
        for skill_id, value in merged.items():
            self.set(skill_id, value, update_baseline=(self._skill_key(skill_id) not in self.baselines))

    def skill_ids(self):
        return tuple(sorted(
            set(self.ratings)
            | set(self.baselines)
            | set(self.floors)
            | set(self.decay_rates)
            | set(self.practice)
            | set(self.last_practiced)
            | set(self.last_decay)
        ))

    def baseline(self, skill_id, default=None):
        key = self._skill_key(skill_id)
        if not key:
            return default
        if key not in self.baselines:
            return default
        return float(self.baselines[key])

    def birth_bias(self, skill_id, default=0.0):
        key = self._skill_key(skill_id)
        if not key:
            return float(default)
        try:
            return float((getattr(self, "birth_biases", {}) or {}).get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def set_baseline(self, skill_id, value):
        key = self._skill_key(skill_id)
        if not key:
            return
        self.baselines[key] = _clamp_stat(value)

    def ensure_baseline(self, skill_id, value=None):
        key = self._skill_key(skill_id)
        if not key:
            return None
        if key not in self.baselines:
            if value is None:
                value = self.get(key, default=5.0)
            self.baselines[key] = _clamp_stat(value)
        return float(self.baselines[key])

    @classmethod
    def default_floor_for_skill(cls, skill_id, baseline, default=1.0):
        try:
            base = _clamp_stat(baseline)
        except (TypeError, ValueError):
            base = _clamp_stat(default)
        key = str(skill_id or "").strip().lower()
        if key == "perception":
            return base
        if key == "athletics":
            return 1.0
        if key == "conversation":
            return max(1.0, min(10.0, base - 0.8))
        if key == "streetwise":
            return max(1.0, min(10.0, base * 0.5))
        if key in {"intrusion", "mechanics"}:
            return max(1.0, min(10.0, base * 0.72))
        if key == "tactics":
            return max(1.0, min(10.0, base * 0.62))
        return max(1.0, min(10.0, base * float(cls.DEFAULT_FLOOR_RATIO)))

    @classmethod
    def default_decay_rate_for_skill(cls, skill_id):
        key = str(skill_id or "").strip().lower()
        try:
            return float(cls.DEFAULT_DECAY_RATES.get(key, cls.DEFAULT_DECAY_RATE))
        except (TypeError, ValueError):
            return float(cls.DEFAULT_DECAY_RATE)

    def set_floor(self, skill_id, value):
        key = self._skill_key(skill_id)
        if not key:
            return
        self.floors[key] = _clamp_stat(value)

    def ensure_floor(self, skill_id, value=None, default=1.0):
        key = self._skill_key(skill_id)
        if not key:
            return None
        if key not in self.floors:
            if value is None:
                value = self.ensure_baseline(key, value=self.get(key, default=default))
            self.floors[key] = _clamp_stat(self.default_floor_for_skill(key, value, default=default))
        return float(self.floors[key])

    def floor(self, skill_id, ratio=None, default=1.0):
        key = self._skill_key(skill_id)
        if not key:
            return _clamp_stat(default)
        if ratio is None and key in self.floors:
            return float(self.floors[key])
        base = self.ensure_baseline(skill_id, value=self.get(skill_id, default=default))
        if base is None:
            return _clamp_stat(default)
        if ratio is None:
            return float(self.ensure_floor(key, value=base, default=default))
        try:
            floor_ratio = float(ratio)
        except (TypeError, ValueError):
            floor_ratio = float(self.DEFAULT_FLOOR_RATIO)
        floor_ratio = max(0.1, min(1.0, floor_ratio))
        return max(1.0, min(10.0, float(base) * floor_ratio))

    def set_decay_rate(self, skill_id, value):
        key = self._skill_key(skill_id)
        if not key:
            return
        try:
            rate = float(value)
        except (TypeError, ValueError):
            rate = self.default_decay_rate_for_skill(key)
        self.decay_rates[key] = max(0.0, min(3.0, rate))

    def decay_rate(self, skill_id, default=None):
        key = self._skill_key(skill_id)
        if not key:
            return float(self.DEFAULT_DECAY_RATE if default is None else default)
        if key not in self.decay_rates:
            self.decay_rates[key] = max(0.0, min(3.0, self.default_decay_rate_for_skill(key)))
        return float(self.decay_rates[key])

    def practice_amount(self, skill_id, default=0.0):
        key = self._skill_key(skill_id)
        if not key:
            return float(default)
        try:
            return float(self.practice.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def set_practice(self, skill_id, amount):
        key = self._skill_key(skill_id)
        if not key:
            return
        try:
            value = float(amount)
        except (TypeError, ValueError):
            value = 0.0
        self.practice[key] = max(0.0, value)

    def add_practice(self, skill_id, amount, *, tick=None):
        key = self._skill_key(skill_id)
        if not key:
            return 0.0
        current = self.practice_amount(key, default=0.0)
        try:
            delta = float(amount)
        except (TypeError, ValueError):
            delta = 0.0
        updated = max(0.0, current + delta)
        self.practice[key] = updated
        if tick is not None:
            self.mark_last_practiced(key, tick)
        return updated

    def last_practiced_tick(self, skill_id, default=None):
        key = self._skill_key(skill_id)
        if not key:
            return default
        if key not in self.last_practiced:
            return default
        return int(self.last_practiced[key])

    def mark_last_practiced(self, skill_id, tick):
        key = self._skill_key(skill_id)
        if not key:
            return
        try:
            self.last_practiced[key] = int(tick)
        except (TypeError, ValueError):
            return

    def last_decay_tick(self, skill_id, default=None):
        key = self._skill_key(skill_id)
        if not key:
            return default
        if key not in self.last_decay:
            return default
        return int(self.last_decay[key])

    def mark_last_decay(self, skill_id, tick):
        key = self._skill_key(skill_id)
        if not key:
            return
        try:
            self.last_decay[key] = int(tick)
        except (TypeError, ValueError):
            return

    def note_change(self, skill_id, *, delta, tick, reason="", value=None):
        key = self._skill_key(skill_id)
        if not key:
            return
        try:
            change_delta = float(delta)
        except (TypeError, ValueError):
            change_delta = 0.0
        try:
            change_tick = int(tick)
        except (TypeError, ValueError):
            change_tick = 0
        entry = {
            "delta": change_delta,
            "tick": change_tick,
            "reason": str(reason or "").strip().lower(),
        }
        if value is not None:
            entry["value"] = _clamp_stat(value)
        self.recent_changes[key] = entry

    def recent_change(self, skill_id, default=None):
        key = self._skill_key(skill_id)
        if not key:
            return default
        return self.recent_changes.get(key, default)

    def as_dict(self):
        return dict(self.ratings)


class AI:
    def __init__(self, role):
        self.role = role
        self.state = "idle"
        self.target = None
        self.target_eid = None


class NPCEmergencyState:
    """Sparse, persistent state for an unresolved immediate threat.

    Ordinary NPC intent may deliberate on a broad set of concerns.  This
    component exists only while an actor must keep producing survival actions,
    including when the fight is outside the player's local detail bubble.
    """

    def __init__(self, threat_eid=None, *, tick=0, damage=0):
        try:
            self.threat_eid = int(threat_eid) if threat_eid is not None else None
        except (TypeError, ValueError):
            self.threat_eid = None
        self.active = self.threat_eid is not None
        self.started_tick = int(tick or 0)
        self.last_damage_tick = int(tick or 0)
        self.expires_tick = int(tick or 0) + 36
        self.damage_count = 1 if int(damage or 0) > 0 else 0
        self.response = "assessing"
        self.last_position = None
        self.last_safer_tick = int(tick or 0)
        self.last_threat_distance = None
        self.force_attack_after_tick = int(tick or 0)


class CreatureIdentity:
    GLYPH_BY_TAXONOMY = {
        "hominid": "H",
        "feline": "F",
        "canine": "C",
        "avian": "A",
        "reptile": "R",
        "amphibian": "M",
        "insect": "I",
        "arachnid": "X",
        "rodent": "D",
        "fish": "S",
        "ungulate": "U",
        "other": "O",
    }

    def __init__(
        self,
        taxonomy_class="hominid",
        species="homo sapiens",
        creature_type="human",
        common_name=None,
        personal_name=None,
        coat_variant=None,
        assigned_sex=None,
        gender_identity=None,
        pronoun_set=None,
        name_gender_score=None,
        gender_inference_source=None,
        phenotype_descriptor=None,
        fauna_line_name=None,
        fauna_species_id=None,
        ancestral_species=None,
        fauna_population_key=None,
    ):
        self.taxonomy_class = str(taxonomy_class or "other").strip().lower() or "other"
        self.species = str(species or "unknown species").strip().lower() or "unknown species"
        self.creature_type = str(creature_type or "creature").strip().lower() or "creature"
        self.common_name = str(common_name).strip() if common_name else None
        self.personal_name = str(personal_name).strip() if personal_name else None
        self.coat_variant = (
            str(coat_variant).strip().lower().replace(" ", "_")
            if coat_variant
            else None
        )
        self.assigned_sex = str(assigned_sex).strip().lower() if assigned_sex else None
        self.gender_identity = str(gender_identity).strip().lower() if gender_identity else None
        self.pronoun_set = str(pronoun_set).strip().lower() if pronoun_set else None
        try:
            self.name_gender_score = None if name_gender_score is None else float(name_gender_score)
        except (TypeError, ValueError):
            self.name_gender_score = None
        self.gender_inference_source = (
            str(gender_inference_source).strip().lower()
            if gender_inference_source
            else None
        )
        # Animals receive this from their expressed genome.  It deliberately
        # contains only outwardly readable traits; hidden alleles and lineage
        # bookkeeping never leak through an ordinary entity label.
        self.phenotype_descriptor = (
            str(phenotype_descriptor).replace("_", " ").strip().lower()
            if phenotype_descriptor
            else None
        )
        self.fauna_line_name = (
            str(fauna_line_name).replace("_", " ").strip().lower()
            if fauna_line_name
            else None
        )
        self.fauna_species_id = (
            str(fauna_species_id).strip().lower().replace(" ", "_")
            if fauna_species_id
            else None
        )
        if isinstance(ancestral_species, str):
            ancestral_species = (ancestral_species,)
        self.ancestral_species = tuple(dict.fromkeys(
            str(value).strip().lower()
            for value in tuple(ancestral_species or ())
            if str(value).strip()
        ))
        self.fauna_population_key = (
            str(fauna_population_key).strip().lower().replace(" ", "_")
            if fauna_population_key
            else None
        )

    def taxonomy_glyph(self, fallback="N"):
        return self.GLYPH_BY_TAXONOMY.get(self.taxonomy_class, str(fallback or "N")[:1].upper() or "N")

    def display_name(self):
        return self.personal_name or getattr(self, "phenotype_descriptor", None) or self.common_name or self.creature_type

    def descriptive_name(self):
        return getattr(self, "phenotype_descriptor", None) or self.common_name or self.creature_type

    def label(self):
        creature = self.display_name()
        descriptor = self.descriptive_name()
        coat = self.coat_variant.replace("_", " ") if self.coat_variant else None
        descriptor_text = ""
        if descriptor and descriptor != creature:
            descriptor_text = f" ({descriptor})"
        if coat:
            return f"{creature}{descriptor_text} [{self.taxonomy_class}] {self.species} coat:{coat}"
        return f"{creature}{descriptor_text} [{self.taxonomy_class}] {self.species}"


class CoverState:
    def __init__(self):
        self.active = False
        self.cover_kind = "none"
        self.cover_value = 0.0
        self.source = None
        self.source_kind = None
        self.block_dir = None
        self.exposure = 1.0
        self.threat_count = 0
        self.nearest_threat_dist = None
        self.last_changed_tick = -1

    def clear(self, tick=0):
        self.active = False
        self.cover_kind = "none"
        self.cover_value = 0.0
        self.source = None
        self.source_kind = None
        self.block_dir = None
        self.exposure = 1.0
        self.last_changed_tick = tick

    def engage(self, cover_kind, cover_value, source, source_kind, block_dir=None, tick=0):
        self.active = True
        self.cover_kind = str(cover_kind or "low")
        self.cover_value = float(max(0.0, min(0.95, cover_value)))
        self.source = source
        self.source_kind = source_kind
        self.block_dir = block_dir
        self.last_changed_tick = tick


class PlayerModeState:
    def __init__(self, sneak=False, hidden=False):
        self.sneak = bool(sneak)
        self.hidden = bool(hidden)
        self.last_changed_tick = -1

    def toggle_sneak(self, tick=0):
        self.sneak = not self.sneak
        if not self.sneak:
            self.hidden = False
        self.last_changed_tick = int(tick)
        return self.sneak

    def set_hidden(self, active, tick=0):
        self.hidden = bool(active)
        self.last_changed_tick = int(tick)
        return self.hidden


class MovementThrottle:
    DEFAULT_STATE_COOLDOWNS = {
        "investigating": 2,
        "protecting": 1,
        "ejecting_target": 1,
        "leaving_property": 1,
        "chasing": 1,
        "scavenging": 2,
        "shopping": 3,
        "following": 1,
        "holding": 1,
        "seeking_social": 2,
        "seeking_companionship": 2,
        "seeking_safety": 1,
        "patrolling": 3,
        "resting": 4,
    }

    def __init__(self, default_cooldown=2, state_cooldowns=None, speed_multiplier=1.0):
        self.default_cooldown = int(max(1, default_cooldown))
        self.state_cooldowns = dict(self.DEFAULT_STATE_COOLDOWNS)
        if state_cooldowns:
            for key, value in state_cooldowns.items():
                try:
                    ivalue = int(value)
                except (TypeError, ValueError):
                    continue
                self.state_cooldowns[str(key)] = max(1, ivalue)
        try:
            speed_multiplier = float(speed_multiplier)
        except (TypeError, ValueError):
            speed_multiplier = 1.0
        self.speed_multiplier = max(0.25, min(3.0, speed_multiplier))
        self.next_move_tick = 0

    def effective_speed(self, status_multiplier=1.0):
        try:
            status_multiplier = float(status_multiplier)
        except (TypeError, ValueError):
            status_multiplier = 1.0
        status_multiplier = max(0.1, status_multiplier)
        return max(0.25, min(3.0, self.speed_multiplier * status_multiplier))

    def cooldown_for(self, state, status_multiplier=1.0):
        base = float(max(1, self.state_cooldowns.get(state, self.default_cooldown)))
        speed = self.effective_speed(status_multiplier=status_multiplier)
        return int(max(1, round(base / speed)))


class NPCNeeds:
    def __init__(
        self,
        energy=85.0,
        safety=75.0,
        social=65.0,
        hunger=86.0,
        thirst=90.0,
        wakefulness=100.0,
    ):
        self.energy = float(energy)
        self.safety = float(safety)
        self.social = float(social)
        self.hunger = float(hunger)
        self.thirst = float(thirst)
        self.wakefulness = float(wakefulness)
        # Stimulants spend this reserve before actual sleep debt.  It is stored
        # in wakefulness points so it survives saves without depending on a
        # particular world's clock scale.
        self.chemical_wake_reserve = 0.0
        self.critical = set()


class LeisureDrive:
    """Sparse persistent wants for voluntary leisure activities.

    Activity runtimes own their particular scoring.  The component only keeps
    stable affinity, accumulated urge, and cooldown state so a person can want
    something over time instead of being selected by a one-tick random roll.
    """

    def __init__(self, affinities=None, urges=None, cooldown_until=None):
        self.affinities = {
            str(key): max(0.0, min(1.0, float(value)))
            for key, value in dict(affinities or {}).items()
        }
        self.urges = {
            str(key): max(0.0, min(1.0, float(value)))
            for key, value in dict(urges or {}).items()
        }
        self.cooldown_until = {
            str(key): int(value)
            for key, value in dict(cooldown_until or {}).items()
        }

    def affinity_for(self, activity, default=0.5):
        return float(self.affinities.get(str(activity), default))

    def urge_for(self, activity):
        return float(self.urges.get(str(activity), 0.0))

    def add_urge(self, activity, amount):
        key = str(activity)
        value = max(0.0, min(1.0, self.urge_for(key) + float(amount)))
        self.urges[key] = value
        return value

    def available(self, activity, tick):
        return int(tick) >= int(self.cooldown_until.get(str(activity), 0))

    def resolve(self, activity, *, tick, cooldown_ticks, residual=0.0):
        key = str(activity)
        self.urges[key] = max(0.0, min(1.0, float(residual)))
        self.cooldown_until[key] = int(tick) + max(0, int(cooldown_ticks))


class NPCTraits:
    def __init__(self, bravery=0.5, empathy=0.5, loyalty=0.5, discipline=0.5):
        self.bravery = float(bravery)
        self.empathy = float(empathy)
        self.loyalty = float(loyalty)
        self.discipline = float(discipline)


class NPCWill:
    def __init__(self):
        self.intent = "idle"
        self.score = 0.0
        self.target = None
        self.target_eid = None
        self.last_tick = -1


class NPCOpportunityKnowledge:
    def __init__(
        self,
        leads_by_kind=None,
        lead_cooldowns=None,
        active_targets=None,
        failed_target_keys=None,
        last_refresh_tick_by_kind=None,
    ):
        self.leads_by_kind = dict(leads_by_kind or {})
        self.lead_cooldowns = dict(lead_cooldowns or {})
        self.active_targets = dict(active_targets or {})
        self.failed_target_keys = dict(failed_target_keys or {})
        self.last_refresh_tick_by_kind = dict(last_refresh_tick_by_kind or {})


class SocialKnowledge:
    def __init__(self, max_records=32, max_social=12):
        self.max_records = max(4, int(max_records or 32))
        self.max_social = max(1, int(max_social or 12))
        self.entries = {}
        self.social_queue = []
        self.last_shared = {}

    def _entry_key(self, source_domain, subject_key):
        domain = str(source_domain or "").strip().lower()
        subject = str(subject_key or "").strip()
        if not domain or not subject:
            return None
        return f"{domain}:{subject}"

    def remember(
        self,
        source_domain,
        subject_key,
        *,
        learned_tick=0,
        source_kind="",
        source_eid=None,
        confidence=0.5,
        firsthand=False,
        propagation_depth=0,
        social_interest=0.0,
        summary="",
        detail="",
        tags=(),
        refs=None,
    ):
        entry_key = self._entry_key(source_domain, subject_key)
        if entry_key is None:
            return None
        try:
            learned_tick = int(learned_tick)
        except (TypeError, ValueError):
            learned_tick = 0
        incoming_learned_tick = int(learned_tick)
        try:
            source_eid = int(source_eid) if source_eid is not None else None
        except (TypeError, ValueError):
            source_eid = None
        try:
            propagation_depth = max(0, int(propagation_depth))
        except (TypeError, ValueError):
            propagation_depth = 0

        confidence = _clamp_unit(confidence, default=0.5)
        social_interest = _clamp_unit(social_interest, default=0.0)
        source_kind = str(source_kind or "").strip().lower()
        source_domain = str(source_domain or "").strip().lower()
        subject_key = str(subject_key or "").strip()
        summary = str(summary or "").strip()
        detail = str(detail or "").strip()

        existing = self.entries.get(entry_key)
        first_tick = learned_tick
        if isinstance(existing, dict):
            first_tick = _safe_int(existing.get("learned_tick"), learned_tick)
            learned_tick = min(learned_tick, first_tick)
            confidence = max(confidence, float(existing.get("confidence", 0.0) or 0.0))
            social_interest = max(social_interest, float(existing.get("social_interest", 0.0) or 0.0))
            firsthand = bool(firsthand or existing.get("firsthand", False))
            if not source_kind:
                source_kind = str(existing.get("source_kind", "") or "").strip().lower()
            if source_eid is None:
                source_eid = existing.get("source_eid")
            propagation_depth = min(
                propagation_depth,
                _safe_int(existing.get("propagation_depth"), propagation_depth),
            )
            if not summary:
                summary = str(existing.get("summary", "") or "").strip()
            if not detail:
                detail = str(existing.get("detail", "") or "").strip()

        tag_set = {
            str(tag).strip().lower()
            for tag in tuple((existing or {}).get("tags", ()) if isinstance(existing, dict) else ()) or ()
            if str(tag).strip()
        }
        for tag in tuple(tags or ()) or ():
            token = str(tag).strip().lower()
            if token:
                tag_set.add(token)

        clean_refs = {}
        if isinstance(existing, dict) and isinstance(existing.get("refs"), dict):
            clean_refs.update(existing.get("refs") or {})
        if isinstance(refs, dict):
            for raw_key, raw_value in refs.items():
                key = str(raw_key or "").strip()
                if key:
                    clean_refs[key] = raw_value

        record = dict(existing) if isinstance(existing, dict) else {}
        record.update({
            "key": entry_key,
            "source_domain": source_domain,
            "subject_key": subject_key,
            "learned_tick": int(learned_tick),
            "last_learned_tick": int(
                incoming_learned_tick
                if not isinstance(existing, dict)
                else max(
                    _safe_int(existing.get("last_learned_tick"), _safe_int(existing.get("learned_tick"), learned_tick)),
                    _safe_int(existing.get("learned_tick"), learned_tick),
                    int(incoming_learned_tick),
                )
            ),
            "source_kind": source_kind,
            "source_eid": source_eid,
            "confidence": float(confidence),
            "firsthand": bool(firsthand),
            "propagation_depth": int(propagation_depth),
            "social_interest": float(social_interest),
            "summary": summary,
            "detail": detail,
            "tags": tuple(sorted(tag_set)),
            "refs": clean_refs,
        })
        self.entries[entry_key] = record
        self._trim_records()
        return record

    def queue_entry(self, entry_key, *, score=0.0, tick=0):
        key = str(entry_key or "").strip()
        if not key or key not in self.entries:
            return False
        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0
        score = _clamp_unit(score, default=0.0)

        existing = None
        for entry in self.social_queue:
            if str(entry.get("key", "") or "").strip() == key:
                existing = entry
                break
        if existing is None:
            self.social_queue.append({
                "key": key,
                "score": float(score),
                "queued_tick": int(tick),
            })
        else:
            existing["score"] = max(float(existing.get("score", 0.0) or 0.0), float(score))
            existing["queued_tick"] = max(int(existing.get("queued_tick", tick) or tick), int(tick))
        self._trim_queue()
        return True

    def mark_shared(self, entry_key, *, tick=0, channel="social"):
        key = str(entry_key or "").strip()
        if not key:
            return False
        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0
        channel_key = str(channel or "social").strip().lower() or "social"
        shared = self.last_shared.get(key)
        if not isinstance(shared, dict):
            shared = {}
            self.last_shared[key] = shared
        shared[channel_key] = int(tick)
        return True

    def forget(self, entry_key):
        key = str(entry_key or "").strip()
        if not key:
            return False
        removed = key in self.entries
        self.entries.pop(key, None)
        self.social_queue = [
            entry for entry in self.social_queue
            if str(entry.get("key", "") or "").strip() != key
        ]
        self.last_shared.pop(key, None)
        return removed

    def _trim_records(self):
        if len(self.entries) <= self.max_records:
            return
        ranked = sorted(
            self.entries.values(),
            key=lambda record: (
                float(record.get("social_interest", 0.0) or 0.0),
                float(record.get("confidence", 0.0) or 0.0),
                bool(record.get("firsthand", False)),
                int(record.get("last_learned_tick", 0) or 0),
            ),
            reverse=True,
        )
        keep_keys = {
            str(record.get("key", "") or "").strip()
            for record in ranked[: self.max_records]
        }
        for entry_key in tuple(self.entries.keys()):
            if entry_key not in keep_keys:
                self.forget(entry_key)

    def _trim_queue(self):
        filtered = []
        seen = set()
        for entry in sorted(
            self.social_queue,
            key=lambda row: (
                float(row.get("score", 0.0) or 0.0),
                int(row.get("queued_tick", 0) or 0),
            ),
            reverse=True,
        ):
            key = str(entry.get("key", "") or "").strip()
            if not key or key in seen or key not in self.entries:
                continue
            filtered.append({
                "key": key,
                "score": _clamp_unit(entry.get("score", 0.0), default=0.0),
                "queued_tick": int(entry.get("queued_tick", 0) or 0),
            })
            seen.add(key)
            if len(filtered) >= self.max_social:
                break
        self.social_queue = filtered


class BehaviorProfile:
    def __init__(self, behaviors=None, preferences=None, tags=None):
        self.behaviors = {}
        self.preferences = dict(preferences or {})
        if isinstance(behaviors, dict):
            for name, value in behaviors.items():
                self.set(name, value)
        elif behaviors:
            self.add(*behaviors)
        if tags:
            self.add(*tags)

    @staticmethod
    def _token(name):
        return str(name or "").strip().lower()

    @staticmethod
    def _value(value, default=0.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float(default)
        return float(max(0.0, min(1.0, number)))

    @property
    def tags(self):
        return {
            name
            for name, value in self.behaviors.items()
            if self._value(value) > 0.0
        }

    def set(self, name, value=1.0):
        token = self._token(name)
        if not token:
            return 0.0
        amount = self._value(value)
        if amount <= 0.0:
            self.behaviors.pop(token, None)
            return 0.0
        self.behaviors[token] = amount
        return amount

    def add(self, *tags, value=1.0):
        amount = self._value(value, default=1.0)
        for tag in tags:
            token = self._token(tag)
            if token:
                self.behaviors[token] = max(self.get(token, 0.0), amount)

    def get(self, tag, default=0.0):
        token = self._token(tag)
        if not token:
            return float(default)
        return self._value(self.behaviors.get(token, default), default=default)

    def has(self, tag, minimum=0.05):
        token = self._token(tag)
        if not token:
            return False
        return self.get(token, 0.0) >= self._value(minimum, default=0.05)


class NPCMemory:
    def __init__(self, max_entries=32):
        self.max_entries = max_entries
        self.entries = []

    def remember(self, tick, kind, strength=1.0, **data):
        self.entries.append({
            "tick": tick,
            "kind": kind,
            "strength": float(strength),
            "data": data,
        })
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def strongest(self, kind):
        best = None
        for entry in self.entries:
            if entry["kind"] != kind:
                continue
            if not best or entry["strength"] > best["strength"]:
                best = entry
        return best

    def decay(self, amount=0.02, by_kind=None, entry_decay=None):
        rates = by_kind if isinstance(by_kind, dict) else {}
        keep = []
        for entry in self.entries:
            kind = str(entry.get("kind", "")).strip().lower()
            decay_amount = rates.get(kind, amount)
            if callable(entry_decay):
                try:
                    decay_amount = float(entry_decay(entry, decay_amount))
                except Exception:
                    pass
            entry["strength"] = max(0.0, entry["strength"] - float(decay_amount))
            if entry["strength"] > 0.05:
                keep.append(entry)
        self.entries = keep


class IncidentKnowledge:
    def __init__(self, max_records=24, max_urgent=6, max_social=10):
        self.max_records = max(4, int(max_records or 24))
        self.max_urgent = max(1, int(max_urgent or 6))
        self.max_social = max(1, int(max_social or 10))
        self.records = {}
        self.urgent_queue = []
        self.social_queue = []
        self.last_shared = {}

    def _source_quality(self, *, source_kind="", firsthand=False, propagation_depth=0, confidence=0.0):
        kind = str(source_kind or "").strip().lower()
        if kind == "self":
            source_rank = 0
        elif bool(firsthand) or kind in {"witnessed", "camera"}:
            source_rank = 1
        elif kind in {"authority_report", "official_report"}:
            source_rank = 2
        elif kind == "social_rumor":
            source_rank = 4
        else:
            source_rank = 3
        return (
            max(0, _safe_int(propagation_depth, 0)),
            int(source_rank),
            -_clamp_unit(confidence, default=0.0),
        )

    def _incident_key(self, incident_id):
        try:
            return int(incident_id)
        except (TypeError, ValueError):
            return None

    def remember(
        self,
        incident_id,
        *,
        learned_tick=0,
        source_kind="",
        source_eid=None,
        confidence=0.5,
        firsthand=False,
        propagation_depth=0,
        urgency=0.0,
        social_interest=0.0,
        category="other",
        kind=None,
        action=None,
        context=None,
        tags=None,
        category_label=None,
        kind_label=None,
        severity=0,
        incident_tick=None,
        x=None,
        y=None,
        z=None,
        official_item_links=None,
        official_item_link_counts=None,
        subject_account=None,
        participant_accounts=None,
    ):
        incident_key = self._incident_key(incident_id)
        if incident_key is None:
            return None

        try:
            learned_tick = int(learned_tick)
        except (TypeError, ValueError):
            learned_tick = 0
        incoming_learned_tick = int(learned_tick)
        try:
            incident_tick = int(incident_tick) if incident_tick is not None else None
        except (TypeError, ValueError):
            incident_tick = None
        try:
            source_eid = int(source_eid) if source_eid is not None else None
        except (TypeError, ValueError):
            source_eid = None
        try:
            propagation_depth = max(0, int(propagation_depth))
        except (TypeError, ValueError):
            propagation_depth = 0
        try:
            severity = max(0, min(100, int(severity)))
        except (TypeError, ValueError):
            severity = 0

        confidence = _clamp_unit(confidence, default=0.5)
        urgency = _clamp_unit(urgency, default=0.0)
        social_interest = _clamp_unit(social_interest, default=0.0)
        category = str(category or "other").strip().lower() or "other"
        source_kind = str(source_kind or "").strip().lower()
        incident_kind = str(kind or "").strip().lower()
        action_key = str(action or "").strip().lower()
        context_key = str(context or "").strip().lower()
        tag_values = tuple(
            str(tag or "").strip().lower()
            for tag in tuple(tags or ())
            if str(tag or "").strip()
        )
        requested_category_label = str(category_label or "").strip()
        requested_kind_label = str(kind_label or "").strip()
        generic_categories = {"official", "other", "self", "social", "social_rumor", "witnessed", "witnessed_event"}
        incoming_has_semantic = bool(
            incident_kind
            or action_key
            or context_key
            or tag_values
            or (category and category not in generic_categories)
        )

        existing = self.records.get(incident_key)
        incoming_quality = self._source_quality(
            source_kind=source_kind,
            firsthand=firsthand,
            propagation_depth=propagation_depth,
            confidence=confidence,
        )
        prefer_incoming_source = True
        if isinstance(existing, dict):
            existing_learned_tick = _safe_int(existing.get("learned_tick"), learned_tick)
            existing_last_learned_tick = _safe_int(
                existing.get("last_learned_tick"),
                existing_learned_tick,
            )
            existing_depth = max(0, _safe_int(existing.get("propagation_depth"), propagation_depth))
            existing_quality = self._source_quality(
                source_kind=existing.get("source_kind", ""),
                firsthand=bool(existing.get("firsthand", False)),
                propagation_depth=existing_depth,
                confidence=existing.get("confidence", 0.0),
            )
            if existing_quality < incoming_quality:
                prefer_incoming_source = False
            elif existing_quality == incoming_quality and existing_last_learned_tick > learned_tick:
                prefer_incoming_source = False

            confidence = max(confidence, float(existing.get("confidence", 0.0) or 0.0))
            urgency = max(urgency, float(existing.get("urgency", 0.0) or 0.0))
            social_interest = max(social_interest, float(existing.get("social_interest", 0.0) or 0.0))
            severity = max(severity, int(existing.get("severity", 0) or 0))
            firsthand = bool(firsthand or existing.get("firsthand", False))
            existing_category = str(existing.get("category", "") or "").strip().lower()
            if category != "official" and existing_category == "official":
                category = "official"
            elif existing_category and not category:
                category = existing_category
            learned_tick = min(learned_tick, existing_learned_tick)

            if prefer_incoming_source:
                if not source_kind:
                    source_kind = str(existing.get("source_kind", "") or "").strip().lower()
                if source_eid is None:
                    source_eid = existing.get("source_eid")
                if x is None:
                    x = existing.get("x")
                if y is None:
                    y = existing.get("y")
                if z is None:
                    z = existing.get("z")
            else:
                source_kind = str(existing.get("source_kind", "") or "").strip().lower() or source_kind
                source_eid = existing.get("source_eid")
                propagation_depth = existing_depth
                x = existing.get("x")
                y = existing.get("y")
                z = existing.get("z")
            existing_incident_tick = existing.get("incident_tick")
            if incident_tick is None or not prefer_incoming_source:
                try:
                    incident_tick = int(existing_incident_tick) if existing_incident_tick is not None else incident_tick
                except (TypeError, ValueError):
                    pass

        if isinstance(existing, dict):
            if not incident_kind:
                incident_kind = str(existing.get("incident_kind", "") or "").strip().lower()
            if not action_key:
                action_key = str(existing.get("action", "") or "").strip().lower()
            if not context_key:
                context_key = str(existing.get("context", "") or "").strip().lower()
            if not tag_values:
                tag_values = tuple(
                    str(tag or "").strip().lower()
                    for tag in tuple(existing.get("tags", ()) or ())
                    if str(tag or "").strip()
                )
        category_label = (
            requested_category_label
            or (
                str(existing.get("category_label", existing.get("friendly_category", "")) or "").strip()
                if isinstance(existing, dict) and not incoming_has_semantic
                else ""
            )
            or incident_category_label(category)
        )
        kind_label = (
            requested_kind_label
            or (
                str(existing.get("kind_label", existing.get("friendly_kind", "")) or "").strip()
                if isinstance(existing, dict) and not incoming_has_semantic
                else ""
            )
            or incident_kind_label(
                incident_kind or category,
                category=category,
                action=action_key,
                context=context_key,
                tags=tag_values,
            )
        )

        record = dict(existing) if isinstance(existing, dict) else {}
        existing_subject_account = record.get("subject_account") if isinstance(record.get("subject_account"), dict) else {}
        incoming_subject_account = dict(subject_account) if isinstance(subject_account, dict) else {}
        rank = {
            "unknown": 0,
            "described": 1,
            "reported": 2,
            "recognized": 3,
            "verified": 4,
        }
        if incoming_subject_account:
            old_rank = rank.get(str(existing_subject_account.get("identification", "unknown") or "unknown").strip().lower(), 0)
            new_rank = rank.get(str(incoming_subject_account.get("identification", "unknown") or "unknown").strip().lower(), 0)
            old_quality = float((existing_subject_account.get("observation") or {}).get("quality", existing_subject_account.get("identity_confidence", 0.0)) or 0.0)
            new_quality = float((incoming_subject_account.get("observation") or {}).get("quality", incoming_subject_account.get("identity_confidence", 0.0)) or 0.0)
            if not existing_subject_account or new_rank > old_rank or (new_rank == old_rank and new_quality > old_quality):
                record["subject_account"] = incoming_subject_account
        existing_participants = (
            dict(record.get("participant_accounts") or {})
            if isinstance(record.get("participant_accounts"), dict)
            else {}
        )
        incoming_participants = participant_accounts if isinstance(participant_accounts, dict) else {}
        for raw_role, raw_account in incoming_participants.items():
            role = str(raw_role or "").strip().lower().replace(" ", "_")
            if not role or not isinstance(raw_account, dict):
                continue
            old_account = existing_participants.get(role) if isinstance(existing_participants.get(role), dict) else {}
            old_rank = rank.get(str(old_account.get("identification", "unknown") or "unknown").strip().lower(), 0)
            new_rank = rank.get(str(raw_account.get("identification", "unknown") or "unknown").strip().lower(), 0)
            old_quality = float((old_account.get("observation") or {}).get("quality", old_account.get("identity_confidence", 0.0)) or 0.0)
            new_quality = float((raw_account.get("observation") or {}).get("quality", raw_account.get("identity_confidence", 0.0)) or 0.0)
            if not old_account or new_rank > old_rank or (new_rank == old_rank and new_quality > old_quality):
                existing_participants[role] = dict(raw_account)
        if existing_participants:
            record["participant_accounts"] = existing_participants
        record.update({
            "incident_id": incident_key,
            "learned_tick": int(learned_tick),
            "last_learned_tick": int(
                incoming_learned_tick
                if not isinstance(existing, dict)
                else max(
                    _safe_int(existing.get("last_learned_tick"), _safe_int(existing.get("learned_tick"), incoming_learned_tick)),
                    _safe_int(existing.get("learned_tick"), incoming_learned_tick),
                    int(incoming_learned_tick),
                )
            ),
            "source_kind": source_kind,
            "source_eid": source_eid,
            "confidence": float(confidence),
            "firsthand": bool(firsthand),
            "propagation_depth": int(propagation_depth),
            "urgency": float(urgency),
            "social_interest": float(social_interest),
            "category": category,
            "category_label": category_label,
            "friendly_category": category_label,
            "incident_kind": incident_kind or None,
            "action": action_key or None,
            "context": context_key or None,
            "tags": tag_values,
            "kind_label": kind_label,
            "friendly_kind": kind_label,
            "severity": int(severity),
            "incident_tick": incident_tick,
            "x": x,
            "y": y,
            "z": z,
            "dismissed": bool((existing or {}).get("dismissed", False)) if isinstance(existing, dict) else False,
        })
        if category == "official" or str(record.get("category", "")).strip().lower() == "official":
            if isinstance(official_item_link_counts, dict):
                counts = {}
                for raw_key, raw_value in official_item_link_counts.items():
                    key = str(raw_key or "").strip().lower().replace(" ", "_")
                    if not key:
                        continue
                    counts[key] = max(0, _safe_int(raw_value, 0))
                record["official_item_link_counts"] = counts
            elif isinstance(existing, dict) and isinstance(existing.get("official_item_link_counts"), dict):
                record["official_item_link_counts"] = dict(existing.get("official_item_link_counts") or {})

            if official_item_links is not None and source_kind != "social_rumor":
                cleaned = []
                seen = set()
                for raw_row in tuple(official_item_links or ()):
                    if not isinstance(raw_row, dict):
                        continue
                    instance_id = str(raw_row.get("instance_id", "") or "").strip()
                    if not instance_id or instance_id in seen:
                        continue
                    seen.add(instance_id)
                    cleaned.append({
                        "instance_id": instance_id,
                        "item_id": str(raw_row.get("item_id", "") or "").strip().lower() or None,
                        "link_kind": str(raw_row.get("link_kind", "") or "").strip().lower() or None,
                        "property_id": str(raw_row.get("property_id", "") or "").strip() or None,
                        "victim_eid": raw_row.get("victim_eid"),
                        "summary_label": str(raw_row.get("summary_label", "") or "").strip() or None,
                    })
                record["official_item_links"] = tuple(cleaned)
            elif isinstance(existing, dict) and existing.get("official_item_links") is not None:
                record["official_item_links"] = tuple(existing.get("official_item_links") or ())
        self.records[incident_key] = record
        self._trim_records()
        return record

    def queue_incident(self, incident_id, *, queue="urgent", score=0.0, tick=0):
        incident_key = self._incident_key(incident_id)
        if incident_key is None:
            return False
        if incident_key not in self.records:
            return False
        queue_key = str(queue or "urgent").strip().lower()
        if queue_key not in {"urgent", "social"}:
            queue_key = "urgent"
        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0
        score = _clamp_unit(score, default=0.0)
        target = self.urgent_queue if queue_key == "urgent" else self.social_queue

        existing = None
        for entry in target:
            if int(entry.get("incident_id", -1) or -1) == incident_key:
                existing = entry
                break

        if existing is None:
            target.append({
                "incident_id": incident_key,
                "score": float(score),
                "queued_tick": int(tick),
            })
        else:
            existing["score"] = max(float(existing.get("score", 0.0) or 0.0), float(score))
            existing["queued_tick"] = max(int(existing.get("queued_tick", tick) or tick), int(tick))

        self._trim_queue(queue_key)
        return True

    def forget(self, incident_id):
        incident_key = self._incident_key(incident_id)
        if incident_key is None:
            return False
        removed = incident_key in self.records
        self.records.pop(incident_key, None)
        self.urgent_queue = [
            entry for entry in self.urgent_queue
            if int(entry.get("incident_id", -1) or -1) != incident_key
        ]
        self.social_queue = [
            entry for entry in self.social_queue
            if int(entry.get("incident_id", -1) or -1) != incident_key
        ]
        self.last_shared.pop(incident_key, None)
        return removed

    def mark_shared(self, incident_id, *, tick=0, channel="social"):
        incident_key = self._incident_key(incident_id)
        if incident_key is None:
            return False
        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0
        channel_key = str(channel or "social").strip().lower() or "social"
        shared = self.last_shared.get(incident_key)
        if not isinstance(shared, dict):
            shared = {}
            self.last_shared[incident_key] = shared
        shared[channel_key] = int(tick)
        return True

    def _trim_records(self):
        if len(self.records) <= self.max_records:
            return
        ranked = sorted(
            self.records.values(),
            key=lambda record: (
                max(
                    float(record.get("urgency", 0.0) or 0.0),
                    float(record.get("social_interest", 0.0) or 0.0),
                ),
                float(record.get("confidence", 0.0) or 0.0),
                bool(record.get("firsthand", False)),
                int(record.get("severity", 0) or 0),
                int(record.get("last_learned_tick", 0) or 0),
            ),
            reverse=True,
        )
        keep_ids = {
            int(record.get("incident_id", -1) or -1)
            for record in ranked[: self.max_records]
        }
        for incident_id in tuple(self.records.keys()):
            if incident_id not in keep_ids:
                self.forget(incident_id)

    def _trim_queue(self, queue_key):
        target = self.urgent_queue if queue_key == "urgent" else self.social_queue
        max_len = self.max_urgent if queue_key == "urgent" else self.max_social
        filtered = []
        seen = set()
        for entry in sorted(
            target,
            key=lambda row: (
                float(row.get("score", 0.0) or 0.0),
                int(row.get("queued_tick", 0) or 0),
            ),
            reverse=True,
        ):
            incident_id = self._incident_key(entry.get("incident_id"))
            if incident_id is None or incident_id in seen or incident_id not in self.records:
                continue
            filtered.append({
                "incident_id": incident_id,
                "score": _clamp_unit(entry.get("score", 0.0), default=0.0),
                "queued_tick": int(entry.get("queued_tick", 0) or 0),
            })
            seen.add(incident_id)
            if len(filtered) >= max_len:
                break
        if queue_key == "urgent":
            self.urgent_queue = filtered
        else:
            self.social_queue = filtered


class BusinessKnowledge:
    def __init__(self, max_records=24, max_social=10):
        self.max_records = max(4, int(max_records or 24))
        self.max_social = max(1, int(max_social or 10))
        self.records = {}
        self.social_queue = []
        self.last_shared = {}

    def _property_key(self, property_id):
        token = str(property_id or "").strip()
        return token or None

    def remember(
        self,
        property_id,
        *,
        learned_tick=0,
        source_kind="",
        source_eid=None,
        confidence=0.5,
        firsthand=False,
        propagation_depth=0,
        coherence=1.0,
        familiarity_delta=0.0,
        trust_delta=0.0,
        reliability_delta=0.0,
        fear_delta=0.0,
        heat_delta=0.0,
        price_fairness_delta=0.0,
        loyalty_delta=0.0,
        resentment_delta=0.0,
        social_interest=0.0,
        tags=(),
        incident_id=None,
    ):
        property_key = self._property_key(property_id)
        if property_key is None:
            return None

        try:
            learned_tick = int(learned_tick)
        except (TypeError, ValueError):
            learned_tick = 0
        incoming_learned_tick = int(learned_tick)
        try:
            source_eid = int(source_eid) if source_eid is not None else None
        except (TypeError, ValueError):
            source_eid = None
        try:
            propagation_depth = max(0, int(propagation_depth))
        except (TypeError, ValueError):
            propagation_depth = 0

        confidence = _clamp_unit(confidence, default=0.5)
        coherence = _clamp_unit(coherence, default=1.0)
        social_interest = _clamp_unit(social_interest, default=0.0)
        source_kind = str(source_kind or "").strip().lower()

        existing = self.records.get(property_key)
        first_tick = learned_tick
        if isinstance(existing, dict):
            first_tick = _safe_int(existing.get("learned_tick"), learned_tick)
            learned_tick = min(learned_tick, first_tick)
            confidence = max(confidence, float(existing.get("confidence", 0.0) or 0.0))
            coherence = max(coherence, float(existing.get("coherence", 0.0) or 0.0))
            social_interest = max(social_interest, float(existing.get("social_interest", 0.0) or 0.0))
            firsthand = bool(firsthand or existing.get("firsthand", False))
            if not source_kind:
                source_kind = str(existing.get("source_kind", "") or "").strip().lower()
            if source_eid is None:
                source_eid = existing.get("source_eid")

        record = dict(existing) if isinstance(existing, dict) else {}
        incident_ids = set()
        for raw_id in tuple(record.get("incident_ids", ()) or ()):
            clean_id = _safe_int(raw_id, default=0)
            if clean_id > 0:
                incident_ids.add(clean_id)
        clean_incident_id = _safe_int(incident_id, default=0)
        if clean_incident_id > 0:
            incident_ids.add(clean_incident_id)

        tag_set = {
            str(tag).strip().lower()
            for tag in tuple(record.get("tags", ()) or ())
            if str(tag).strip()
        }
        for tag in tuple(tags or ()) or ():
            clean = str(tag).strip().lower()
            if clean:
                tag_set.add(clean)

        record.update({
            "property_id": property_key,
            "learned_tick": int(learned_tick),
            "last_learned_tick": int(
                incoming_learned_tick
                if not isinstance(existing, dict)
                else max(
                    _safe_int(existing.get("last_learned_tick"), _safe_int(existing.get("learned_tick"), incoming_learned_tick)),
                    _safe_int(existing.get("learned_tick"), incoming_learned_tick),
                    int(incoming_learned_tick),
                )
            ),
            "source_kind": source_kind,
            "source_eid": source_eid,
            "confidence": float(confidence),
            "firsthand": bool(firsthand),
            "propagation_depth": int(
                min(
                    propagation_depth,
                    _safe_int(existing.get("propagation_depth"), propagation_depth) if isinstance(existing, dict) else propagation_depth,
                )
            ),
            "coherence": float(coherence),
            "familiarity": _clamp_unit(float(record.get("familiarity", 0.0) or 0.0) + float(familiarity_delta), default=0.0),
            "trust": _clamp_unit(float(record.get("trust", 0.0) or 0.0) + float(trust_delta), default=0.0),
            "reliability": _clamp_unit(float(record.get("reliability", 0.0) or 0.0) + float(reliability_delta), default=0.0),
            "fear": _clamp_unit(float(record.get("fear", 0.0) or 0.0) + float(fear_delta), default=0.0),
            "heat": _clamp_unit(float(record.get("heat", 0.0) or 0.0) + float(heat_delta), default=0.0),
            "price_fairness": _clamp_signed_unit(float(record.get("price_fairness", 0.0) or 0.0) + float(price_fairness_delta), default=0.0),
            "loyalty": _clamp_unit(float(record.get("loyalty", 0.0) or 0.0) + float(loyalty_delta), default=0.0),
            "resentment": _clamp_unit(float(record.get("resentment", 0.0) or 0.0) + float(resentment_delta), default=0.0),
            "social_interest": float(social_interest),
            "incident_ids": tuple(sorted(incident_ids)),
            "tags": tuple(sorted(tag_set)),
        })
        self.records[property_key] = record
        self._trim_records()
        return record

    def queue_property(self, property_id, *, score=0.0, tick=0):
        property_key = self._property_key(property_id)
        if property_key is None or property_key not in self.records:
            return False
        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0
        score = _clamp_unit(score, default=0.0)

        existing = None
        for entry in self.social_queue:
            if str(entry.get("property_id", "") or "").strip() == property_key:
                existing = entry
                break

        if existing is None:
            self.social_queue.append({
                "property_id": property_key,
                "score": float(score),
                "queued_tick": int(tick),
            })
        else:
            existing["score"] = max(float(existing.get("score", 0.0) or 0.0), float(score))
            existing["queued_tick"] = max(int(existing.get("queued_tick", tick) or tick), int(tick))
        self._trim_queue()
        return True

    def mark_shared(self, property_id, *, tick=0, channel="social"):
        property_key = self._property_key(property_id)
        if property_key is None:
            return False
        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0
        channel_key = str(channel or "social").strip().lower() or "social"
        shared = self.last_shared.get(property_key)
        if not isinstance(shared, dict):
            shared = {}
            self.last_shared[property_key] = shared
        shared[channel_key] = int(tick)
        return True

    def forget(self, property_id):
        property_key = self._property_key(property_id)
        if property_key is None:
            return False
        removed = property_key in self.records
        self.records.pop(property_key, None)
        self.social_queue = [
            entry for entry in self.social_queue
            if str(entry.get("property_id", "") or "").strip() != property_key
        ]
        self.last_shared.pop(property_key, None)
        return removed

    def _trim_records(self):
        if len(self.records) <= self.max_records:
            return
        ranked = sorted(
            self.records.values(),
            key=lambda record: (
                float(record.get("social_interest", 0.0) or 0.0),
                float(record.get("coherence", 0.0) or 0.0),
                float(record.get("familiarity", 0.0) or 0.0),
                max(
                    float(record.get("trust", 0.0) or 0.0),
                    float(record.get("reliability", 0.0) or 0.0),
                    float(record.get("fear", 0.0) or 0.0),
                    float(record.get("heat", 0.0) or 0.0),
                    float(record.get("loyalty", 0.0) or 0.0),
                    float(record.get("resentment", 0.0) or 0.0),
                    abs(float(record.get("price_fairness", 0.0) or 0.0)),
                ),
                int(record.get("last_learned_tick", 0) or 0),
            ),
            reverse=True,
        )
        keep_ids = {
            str(record.get("property_id", "") or "").strip()
            for record in ranked[: self.max_records]
        }
        for property_id in tuple(self.records.keys()):
            if property_id not in keep_ids:
                self.forget(property_id)

    def _trim_queue(self):
        filtered = []
        seen = set()
        for entry in sorted(
            self.social_queue,
            key=lambda row: (
                float(row.get("score", 0.0) or 0.0),
                int(row.get("queued_tick", 0) or 0),
            ),
            reverse=True,
        ):
            property_key = self._property_key(entry.get("property_id"))
            if property_key is None or property_key in seen or property_key not in self.records:
                continue
            filtered.append({
                "property_id": property_key,
                "score": _clamp_unit(entry.get("score", 0.0), default=0.0),
                "queued_tick": int(entry.get("queued_tick", 0) or 0),
            })
            seen.add(property_key)
            if len(filtered) >= self.max_social:
                break
        self.social_queue = filtered


class ItemKnowledge:
    def __init__(self):
        self.identified = {}
        self.appraised = {}

    def identify(self, item_id, *, tick=0, source_kind="direct"):
        key = str(item_id or "").strip().lower()
        if not key:
            return False
        existing = self.identified.get(key)
        tick = _safe_int(tick, 0)
        self.identified[key] = {
            "item_id": key,
            "tick": tick if existing is None else min(_safe_int(existing.get("tick"), tick), tick),
            "last_tick": tick if existing is None else max(_safe_int(existing.get("last_tick"), tick), tick),
            "source_kind": str(source_kind or "direct").strip().lower() or "direct",
        }
        return existing is None

    def is_identified(self, item_id):
        key = str(item_id or "").strip().lower()
        if not key:
            return False
        return key in self.identified

    def appraise(self, instance_id, *, item_id=None, tick=0, detail_keys=()):
        key = str(instance_id or "").strip()
        if not key:
            return False
        details = {
            str(detail).strip().lower()
            for detail in detail_keys
            if str(detail).strip()
        }
        existing = self.appraised.get(key)
        merged_details = set(existing.get("detail_keys", ())) if isinstance(existing, dict) else set()
        merged_details.update(details)
        tick = _safe_int(tick, 0)
        if isinstance(existing, dict):
            known_item_id = str(existing.get("item_id", "") or "").strip().lower() or None
        else:
            known_item_id = None
        item_id_text = str(item_id or known_item_id or "").strip().lower() or None
        self.appraised[key] = {
            "instance_id": key,
            "item_id": item_id_text,
            "tick": tick if existing is None else min(_safe_int(existing.get("tick"), tick), tick),
            "last_tick": tick if existing is None else max(_safe_int(existing.get("last_tick"), tick), tick),
            "detail_keys": tuple(sorted(merged_details)),
        }
        return existing is None or merged_details != set(existing.get("detail_keys", ()))

    def knows_appraisal(self, instance_id, detail_key=None):
        key = str(instance_id or "").strip()
        if not key:
            return False
        record = self.appraised.get(key)
        if not isinstance(record, dict):
            return False
        token = str(detail_key or "").strip().lower()
        if not token:
            return True
        return token in set(record.get("detail_keys", ()))


class NPCSocial:
    DEFAULT_PROTECT = {
        "family": 0.95,
        "partner": 0.9,
        "friend": 0.7,
        "coworker": 0.6,
        "neighbor": 0.45,
    }

    def __init__(self):
        self.bonds = {}

    def add_bond(self, other_eid, kind="friend", closeness=0.5, trust=0.5, protectiveness=None):
        if protectiveness is None:
            protectiveness = self.DEFAULT_PROTECT.get(kind, 0.5)

        self.bonds[other_eid] = {
            "kind": kind,
            "closeness": float(closeness),
            "trust": float(trust),
            "protectiveness": float(protectiveness),
        }

    def strongest_bond(self, min_closeness=0.0):
        best_eid = None
        best = None

        for eid, bond in self.bonds.items():
            if bond["closeness"] < min_closeness:
                continue
            score = bond["closeness"] * 0.65 + bond["trust"] * 0.35
            if not best or score > best:
                best = score
                best_eid = eid

        return best_eid


class NPCRoutine:
    def __init__(self, home=None, work=None):
        self.home = home
        self.work = work


class NPCSettlement:
    def __init__(
        self,
        arrived_tick=0,
        origin="",
        phase="arriving",
        housing_status="unhoused",
        employment_status="unemployed",
        home_property_id="",
        work_property_id="",
        last_housing_tick=0,
        last_job_tick=0,
        last_social_tick=0,
        last_life_tick=0,
        last_move_tick=0,
        drift_preferred=False,
        story_id="",
        life_goal="",
        life_review_stage="",
        life_review_candidates=None,
        life_review_cursor=0,
        life_review_next_tick=0,
        life_review_failures=0,
    ):
        self.arrived_tick = int(arrived_tick or 0)
        self.origin = str(origin or "").strip().lower()
        self.phase = str(phase or "arriving").strip().lower() or "arriving"
        self.housing_status = str(housing_status or "unhoused").strip().lower() or "unhoused"
        self.employment_status = str(employment_status or "unemployed").strip().lower() or "unemployed"
        self.home_property_id = str(home_property_id or "").strip()
        self.work_property_id = str(work_property_id or "").strip()
        self.last_housing_tick = int(last_housing_tick or 0)
        self.last_job_tick = int(last_job_tick or 0)
        self.last_social_tick = int(last_social_tick or 0)
        self.last_life_tick = int(last_life_tick or 0)
        self.last_move_tick = int(last_move_tick or 0)
        self.drift_preferred = bool(drift_preferred)
        self.story_id = str(story_id or "").strip()
        self.life_goal = str(life_goal or "").strip().lower()
        self.life_review_stage = str(life_review_stage or "").strip().lower()
        self.life_review_candidates = list(life_review_candidates or [])
        self.life_review_cursor = int(life_review_cursor or 0)
        self.life_review_next_tick = int(life_review_next_tick or 0)
        self.life_review_failures = int(life_review_failures or 0)


class WildlifeBehavior:
    def __init__(
        self,
        home_radius=4,
        flee_radius=5,
        flock_radius=3,
        flocking=False,
        activity_period="any",
        rest_bias=0.3,
        threat_response="flee",
        movement_style="roam",
    ):
        self.home_radius = max(1, int(home_radius))
        self.flee_radius = max(1, int(flee_radius))
        self.flock_radius = max(1, int(flock_radius))
        self.flocking = bool(flocking)
        period = str(activity_period or "any").strip().lower() or "any"
        if period not in {"day", "night", "any", "crepuscular"}:
            period = "any"
        self.activity_period = period
        try:
            rest_bias = float(rest_bias)
        except (TypeError, ValueError):
            rest_bias = 0.3
        self.rest_bias = max(0.0, min(1.0, rest_bias))
        response = str(threat_response or "flee").strip().lower() or "flee"
        self.threat_response = response if response in {"flee", "freeze_bolt", "brace", "display"} else "flee"
        movement = str(movement_style or "roam").strip().lower() or "roam"
        self.movement_style = movement if movement in {"roam", "dart", "stalk", "amble"} else "roam"


@dataclass
class AnimalPhysicalProfile:
    size_score: float
    speed_score: float
    injury_score: float = 0.0
    juvenile: bool = False


class AnimalGenome:
    """Save-safe inherited identity for one non-human animal.

    ``root_animal_id`` is the reproductive compatibility boundary.  It is a
    generic body-plan lineage (herd grazer, swarm scuttler, and so on), not a
    requirement that the world use an Earth species name.  ``genes`` retains
    inherited alleles while ``expressed`` owns the phenotype used by the live
    simulation and renderer.
    """

    SCHEMA_VERSION = 1

    def __init__(
        self,
        *,
        genome_id,
        root_animal_id,
        lineage_id,
        genes=None,
        expressed=None,
        parent_genome_ids=None,
        parent_lineage_ids=None,
        generation=0,
        trait_budget=6,
        trait_cost_used=0,
        mutation_signature="",
        native_lineage_id="",
    ):
        self.schema_version = self.SCHEMA_VERSION
        self.genome_id = str(genome_id or "").strip()
        self.root_animal_id = str(root_animal_id or "other_root").strip().lower() or "other_root"
        self.lineage_id = str(lineage_id or self.genome_id).strip() or self.genome_id
        self.genes = dict(genes or {})
        self.expressed = dict(expressed or {})
        self.parent_genome_ids = tuple(
            str(value).strip()
            for value in tuple(parent_genome_ids or ())
            if str(value).strip()
        )
        self.parent_lineage_ids = tuple(
            str(value).strip()
            for value in tuple(parent_lineage_ids or ())
            if str(value).strip()
        )
        self.generation = max(0, int(generation or 0))
        self.trait_budget = max(0, int(trait_budget or 0))
        self.trait_cost_used = max(0, int(trait_cost_used or 0))
        self.mutation_signature = str(mutation_signature or "").strip().lower()
        self.native_lineage_id = str(native_lineage_id or "").strip().lower()


class AnimalReproduction:
    """Sparse reproductive state for a fauna actor.

    Roles are deliberately neutral (``a``/``b``) because root animals may be
    invented, sex-changing, or otherwise unlike familiar Earth examples.
    """

    def __init__(
        self,
        *,
        mode="paired",
        gamete_role="a",
        maturity_tick=0,
        next_breed_tick=0,
        gestation_ticks=1200,
        brood_min=1,
        brood_max=1,
        gestation=None,
        assisted_by_eid=None,
    ):
        mode = str(mode or "paired").strip().lower() or "paired"
        self.mode = mode if mode in {"paired", "any_pair", "none"} else "paired"
        role = str(gamete_role or "a").strip().lower() or "a"
        self.gamete_role = role if role in {"a", "b", "any"} else "a"
        self.maturity_tick = max(0, int(maturity_tick or 0))
        self.next_breed_tick = max(0, int(next_breed_tick or 0))
        self.gestation_ticks = max(1, int(gestation_ticks or 1))
        self.brood_min = max(1, int(brood_min or 1))
        self.brood_max = max(self.brood_min, int(brood_max or self.brood_min))
        self.gestation = dict(gestation or {}) if isinstance(gestation, dict) else {}
        try:
            self.assisted_by_eid = int(assisted_by_eid) if assisted_by_eid is not None else None
        except (TypeError, ValueError):
            self.assisted_by_eid = None


@dataclass
class EcologyProfile:
    species: str
    predator_score: float = 0.0
    prey_score: float = 0.0
    scavenger_score: float = 0.0
    territorial_score: float = 0.0
    pack_score: float = 0.0
    flee_bias: float = 0.0
    chase_bias: float = 0.0


@dataclass
class AnimalBehaviorContext:
    hunger: float = 50.0
    territorial_context: bool = False
    cornered: bool = False
    trained_restraint: float = 0.0
    leashed: bool = False
    bonded_to_eid: int | None = None


@dataclass
class HumanWildlifePresence:
    perceived_predator_score: float = 60.0
    firearm_threat_bonus: float = 30.0
    calm_animal_skill: float = 0.0
    hunting_intent: bool = False
    companionship_openness: float = 0.0
    gentle_presence: float = 0.0


@dataclass
class AnimalSocialProfile:
    sociability: float = 20.0
    same_species_affinity: float = 28.0
    human_affinity: float = 0.0
    domesticity: float = 0.0
    companionship_drive: float = 0.0
    follow_drive: float = 0.0


class AnimalMemory:
    def __init__(self, max_entries=24):
        self.max_entries = max(4, int(max_entries or 24))
        self.entries = []

    def remember(self, tick, kind, strength=1.0, **data):
        self.entries.append({
            "tick": int(tick or 0),
            "kind": str(kind or "").strip().lower(),
            "strength": float(strength),
            "data": data,
        })
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def strongest(self, kind):
        kind = str(kind or "").strip().lower()
        best = None
        for entry in self.entries:
            if str(entry.get("kind", "")).strip().lower() != kind:
                continue
            if best is None or float(entry.get("strength", 0.0) or 0.0) > float(best.get("strength", 0.0) or 0.0):
                best = entry
        return best

    def decay(self, amount=0.02, by_kind=None):
        rates = by_kind if isinstance(by_kind, dict) else {}
        keep = []
        for entry in self.entries:
            kind = str(entry.get("kind", "")).strip().lower()
            decay_amount = float(rates.get(kind, amount) or amount)
            entry["strength"] = max(0.0, float(entry.get("strength", 0.0) or 0.0) - decay_amount)
            if float(entry.get("strength", 0.0) or 0.0) > 0.05:
                keep.append(entry)
        self.entries = keep


class WildlifeSocialState:
    def __init__(self):
        self.bonds = {}
        self.last_contact_ticks = {}

    def add_bond(self, other_eid, kind="companion", closeness=0.25, trust=0.25, comfort=0.25):
        self.bonds[other_eid] = {
            "kind": str(kind or "companion").strip().lower() or "companion",
            "closeness": float(closeness),
            "trust": float(trust),
            "comfort": float(comfort),
        }

    def strongest_bond(self, min_closeness=0.0, min_trust=0.0):
        best_eid = None
        best = None

        for eid, bond in self.bonds.items():
            closeness = float(bond.get("closeness", 0.0) or 0.0)
            trust = float(bond.get("trust", 0.0) or 0.0)
            if closeness < float(min_closeness) or trust < float(min_trust):
                continue
            score = (closeness * 0.48) + (trust * 0.34) + (float(bond.get("comfort", 0.0) or 0.0) * 0.18)
            if best is None or score > best:
                best = score
                best_eid = eid

        return best_eid

    def note_contact(self, other_eid, tick):
        try:
            other_key = int(other_eid)
            contact_tick = int(tick)
        except (TypeError, ValueError):
            return
        contacts = getattr(self, "last_contact_ticks", None)
        if not isinstance(contacts, dict):
            contacts = {}
            self.last_contact_ticks = contacts
        contacts[other_key] = contact_tick

    def last_contact_tick(self, other_eid, default=None):
        try:
            other_key = int(other_eid)
        except (TypeError, ValueError):
            return default
        contacts = getattr(self, "last_contact_ticks", None)
        if not isinstance(contacts, dict) or other_key not in contacts:
            return default
        try:
            return int(contacts[other_key])
        except (TypeError, ValueError):
            return default


class Occupation:
    def __init__(self, career, workplace=None, shift_start=None, shift_end=None):
        self.career = career
        self.workplace = workplace
        self.shift_start = shift_start
        self.shift_end = shift_end


class OrganizationProfile:
    def __init__(self, name, kind="other", key=None, tags=None, parent_org_eid=None):
        self.name = str(name or "Organization").strip() or "Organization"
        self.kind = str(kind or "other").strip().lower() or "other"
        self.key = str(key or "").strip()
        self.tags = set(str(tag).strip().lower() for tag in (tags or ()) if str(tag).strip())
        try:
            self.parent_org_eid = int(parent_org_eid) if parent_org_eid is not None else None
        except (TypeError, ValueError):
            self.parent_org_eid = None
        self.site_property_ids = set()
        self.site_building_ids = set()
        self.member_eids = set()
        self.site_links = []
        self.relations = []
        # Durable authored/generated culture shared by every product this
        # organization puts into the world.  Hidden manufacturing tendencies
        # live inside this profile too, but are not an in-fiction fact known to
        # the organization unless another system explicitly discovers them.
        self.production_profile = {}
        # Optional culture shared by community members.  This is separate from
        # operational OrganizationVocabulary: generated slang is social color,
        # not a source of actionable instructions or discovered knowledge.
        self.culture_profile = {}


class OrganizationAffiliations:
    def __init__(self):
        self.memberships = {}

    def assign(
        self,
        organization_eid,
        role="member",
        kind="member",
        site_property_id=None,
        site_building_id=None,
        title=None,
        primary=False,
        authority_rank=70,
        supervisor_eid=None,
        active=True,
    ):
        try:
            organization_eid = int(organization_eid)
        except (TypeError, ValueError):
            return False
        try:
            authority_rank = int(authority_rank)
        except (TypeError, ValueError):
            authority_rank = 70
        try:
            supervisor_eid = int(supervisor_eid) if supervisor_eid is not None else None
        except (TypeError, ValueError):
            supervisor_eid = None

        self.memberships[organization_eid] = {
            "organization_eid": organization_eid,
            "role": str(role or "member").strip().lower() or "member",
            "kind": str(kind or "member").strip().lower() or "member",
            "site_property_id": str(site_property_id or "").strip() or None,
            "site_building_id": str(site_building_id or "").strip() or None,
            "title": str(title or "").strip() or None,
            "primary": bool(primary),
            "authority_rank": authority_rank,
            "supervisor_eid": supervisor_eid,
            "active": bool(active),
        }
        return True


class OrganizationVocabulary:
    def __init__(self, max_entries=64):
        self.max_entries = max(8, int(max_entries or 64))
        self.next_entry_id = 1
        self.entries = {}


class OrganizationPractices:
    def __init__(self, max_entries=48):
        self.max_entries = max(8, int(max_entries or 48))
        self.next_entry_id = 1
        self.entries = {}


class OrganizationPracticeProgress:
    def __init__(self, max_entries=96):
        self.max_entries = max(8, int(max_entries or 96))
        self.entries = {}


class OrganizationCrimePlans:
    def __init__(self, max_entries=24):
        self.max_entries = max(4, int(max_entries or 24))
        self.next_entry_id = 1
        self.entries = {}


class OrganizationWatchlists:
    def __init__(self, max_entries=48):
        self.max_entries = max(8, int(max_entries or 48))
        self.next_entry_id = 1
        self.entries = {}


class PropertyPortfolio:
    def __init__(self):
        self.owned_property_ids = set()


class CriminalDriveState:
    def __init__(
        self,
        pressure=0.0,
        confidence=0.0,
        affiliation_interest=0.0,
        last_eval_tick=0,
        last_attempt_tick=0,
        last_success_tick=0,
        last_failure_tick=0,
        last_affiliation_seek_tick=0,
        cooldown_until_tick=0,
        current_plan_key=None,
        current_target_property_id=None,
    ):
        self.pressure = float(pressure)
        self.confidence = float(confidence)
        self.affiliation_interest = float(affiliation_interest)
        self.last_eval_tick = int(last_eval_tick or 0)
        self.last_attempt_tick = int(last_attempt_tick or 0)
        self.last_success_tick = int(last_success_tick or 0)
        self.last_failure_tick = int(last_failure_tick or 0)
        self.last_affiliation_seek_tick = int(last_affiliation_seek_tick or 0)
        self.cooldown_until_tick = int(cooldown_until_tick or 0)
        self.current_plan_key = str(current_plan_key or "").strip() or None
        self.current_target_property_id = str(current_target_property_id or "").strip() or None
        self.opportunistic_crime_score = 0.0
        self.planned_crime_score = 0.0
        self.affiliation_seek_score = 0.0
        self.current_target_ground_item_id = None
        self.current_target_building_id = None
        self.current_target_x = None
        self.current_target_y = None
        self.current_target_z = None
        self.current_disposal_property_id = None
        self.current_affiliation_target_property_id = None
        self.current_affiliation_organization_eid = None
        self.current_activity_kind = None
        self.current_activity_stage = None
        self.current_activity_summary = None
        self.current_target_was_cased = False
        self.cased_property_knowledge = {}
        self.target_scan_tick = 0
        self.target_scan_signature = None
        self.cached_opportunistic_target = None
        self.cached_affiliation_targets = ()


class PropertyKnowledge:
    def __init__(self):
        self.known = {}
        self.hidden_property_ids = set()

    def property_entry(self, property_id):
        property_id = str(property_id or "").strip()
        if not property_id:
            return None
        known = getattr(self, "known", None)
        if not isinstance(known, dict):
            self.known = {}
            known = self.known
        return known.get(property_id)

    def remember(
        self,
        property_id,
        owner_eid=None,
        owner_tag=None,
        confidence=0.5,
        tick=0,
        source_eid=None,
        lead_kind=None,
        anchored=None,
        anchor_kind=None,
        first_tick=None,
    ):
        existing = self.known.get(property_id)
        if existing:
            confidence = max(confidence, existing["confidence"])
            if source_eid is None:
                source_eid = existing.get("source_eid")
            if lead_kind is None:
                lead_kind = existing.get("lead_kind")
            if anchored is None:
                anchored = existing.get("anchored")
            if anchor_kind is None:
                anchor_kind = existing.get("anchor_kind")
            if first_tick is None:
                first_tick = existing.get("first_tick")

        if anchored is None:
            anchored = False
        if first_tick is None and anchored:
            first_tick = tick

        self.known[property_id] = {
            "owner_eid": owner_eid,
            "owner_tag": owner_tag,
            "confidence": float(confidence),
            "tick": tick,
            "source_eid": source_eid,
            "lead_kind": lead_kind,
            "anchored": bool(anchored),
            "anchor_kind": str(anchor_kind or "").strip().lower() or None,
            "first_tick": int(first_tick) if first_tick is not None else None,
        }

    def hide(self, property_id):
        property_id = str(property_id or "").strip()
        if not property_id:
            return False
        hidden_ids = getattr(self, "hidden_property_ids", None)
        if hidden_ids is None:
            hidden_ids = set()
            self.hidden_property_ids = hidden_ids
        before = len(hidden_ids)
        hidden_ids.add(property_id)
        return len(hidden_ids) > before

    def unhide(self, property_id):
        property_id = str(property_id or "").strip()
        hidden_ids = getattr(self, "hidden_property_ids", None)
        if hidden_ids is None:
            hidden_ids = set()
            self.hidden_property_ids = hidden_ids
        if not property_id or property_id not in hidden_ids:
            return False
        hidden_ids.discard(property_id)
        return True

    def is_hidden(self, property_id):
        property_id = str(property_id or "").strip()
        hidden_ids = getattr(self, "hidden_property_ids", None)
        if hidden_ids is None:
            hidden_ids = set()
            self.hidden_property_ids = hidden_ids
        return bool(property_id) and property_id in hidden_ids


class ContactLedger:
    PERSON_EPISODE_LIMIT = 12
    PERSON_EPISODE_DEDUPE_WINDOW = 14400

    def __init__(self):
        self.by_property = {}
        self.by_person = {}

    def _ensure_maps(self):
        if not isinstance(getattr(self, "by_property", None), dict):
            self.by_property = {}
        if not isinstance(getattr(self, "by_person", None), dict):
            self.by_person = {}

    def property_entry(self, property_id):
        self._ensure_maps()
        return self.by_property.get(property_id)

    def person_entry(self, person_eid):
        self._ensure_maps()
        try:
            key = int(person_eid)
        except (TypeError, ValueError):
            key = person_eid
        return self.by_person.get(key)

    def _normalize_person_episode(self, episode):
        if not isinstance(episode, dict):
            return None
        kind = str(episode.get("kind", "") or "").strip().lower()
        summary = str(episode.get("summary", "") or "").strip()
        if not kind or not summary:
            return None
        valence = str(episode.get("valence", "neutral") or "neutral").strip().lower() or "neutral"
        if valence not in {"positive", "negative", "neutral"}:
            valence = "neutral"
        try:
            tick = int(episode.get("tick", 0) or 0)
        except (TypeError, ValueError):
            tick = 0
        normalized = {
            "kind": kind,
            "tick": tick,
            "valence": valence,
            "summary": summary,
        }
        property_id = str(episode.get("property_id", "") or "").strip()
        if property_id:
            normalized["property_id"] = property_id
        other_person_eid = episode.get("other_person_eid")
        if other_person_eid is not None:
            try:
                normalized["other_person_eid"] = int(other_person_eid)
            except (TypeError, ValueError):
                normalized["other_person_eid"] = other_person_eid
        source_topic = str(episode.get("source_topic", "") or "").strip().lower()
        if source_topic:
            normalized["source_topic"] = source_topic
        return normalized

    def _normalize_person_episodes(self, episodes, *, limit=None):
        cleaned = []
        seen = set()
        for raw in tuple(episodes or ()):
            episode = self._normalize_person_episode(raw)
            if not episode:
                continue
            key = (
                episode.get("kind"),
                int(episode.get("tick", 0) or 0),
                episode.get("summary"),
                episode.get("property_id"),
                episode.get("other_person_eid"),
                episode.get("source_topic"),
            )
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(episode)
        cleaned.sort(key=lambda record: int(record.get("tick", 0) or 0), reverse=True)
        max_items = self.PERSON_EPISODE_LIMIT if limit is None else max(1, int(limit))
        return tuple(cleaned[:max_items])

    def remember_person_episode(
        self,
        person_eid,
        *,
        kind,
        tick=0,
        valence="neutral",
        summary="",
        property_id=None,
        other_person_eid=None,
        source_topic=None,
        dedupe_window=None,
        limit=None,
    ):
        self._ensure_maps()
        try:
            key = int(person_eid)
        except (TypeError, ValueError):
            key = person_eid

        existing = self.by_person.get(key)
        if not isinstance(existing, dict):
            existing = {
                "source_eid": None,
                "relation_kind": None,
                "standing": 0.0,
                "tick": int(tick or 0),
                "property_id": None,
                "benefits": (),
                "introduced": False,
                "met_directly": False,
                "first_met_tick": None,
                "last_met_tick": None,
                "identity_snapshot": None,
                "episodes": (),
            }
        records = list(self._normalize_person_episodes(existing.get("episodes", ()), limit=limit))
        candidate = self._normalize_person_episode({
            "kind": kind,
            "tick": tick,
            "valence": valence,
            "summary": summary,
            "property_id": property_id,
            "other_person_eid": other_person_eid,
            "source_topic": source_topic,
        })
        if not candidate:
            self.by_person[key] = existing
            return False

        window = self.PERSON_EPISODE_DEDUPE_WINDOW if dedupe_window is None else max(0, int(dedupe_window))
        replaced = False
        for idx, record in enumerate(list(records)):
            if str(record.get("kind", "") or "").strip().lower() != candidate["kind"]:
                continue
            if str(record.get("property_id", "") or "").strip() != str(candidate.get("property_id", "") or "").strip():
                continue
            if record.get("other_person_eid") != candidate.get("other_person_eid"):
                continue
            if abs(int(candidate.get("tick", 0) or 0) - int(record.get("tick", 0) or 0)) > window:
                continue
            if int(candidate.get("tick", 0) or 0) >= int(record.get("tick", 0) or 0):
                records[idx] = candidate
            else:
                candidate = record
            replaced = True
            break
        if not replaced:
            records.append(candidate)

        existing = dict(existing)
        existing["tick"] = max(int(existing.get("tick", 0) or 0), int(candidate.get("tick", 0) or 0))
        existing["episodes"] = self._normalize_person_episodes(records, limit=limit)
        self.by_person[key] = existing
        return True

    def remember(
        self,
        property_id,
        source_eid=None,
        contact_kind=None,
        standing=0.5,
        tick=0,
        benefits=None,
    ):
        self._ensure_maps()
        existing = self.by_property.get(property_id)
        merged_benefits = set()
        if existing:
            merged_benefits.update(existing.get("benefits", ()))
            standing = max(float(existing.get("standing", 0.0)), float(standing))
            if source_eid is None:
                source_eid = existing.get("source_eid")
            if contact_kind is None:
                contact_kind = existing.get("contact_kind")

        if benefits:
            merged_benefits.update(str(bit).strip().lower() for bit in benefits if str(bit).strip())

        self.by_property[property_id] = {
            "source_eid": source_eid,
            "contact_kind": contact_kind,
            "standing": _clamp_unit(standing, default=0.5),
            "tick": int(tick),
            "benefits": tuple(sorted(merged_benefits)),
        }

    def remember_person(
        self,
        person_eid,
        source_eid=None,
        relation_kind=None,
        standing=0.5,
        tick=0,
        property_id=None,
        benefits=None,
        introduced=False,
        met_directly=None,
        first_met_tick=None,
        last_met_tick=None,
        identity_snapshot=None,
        episodes=None,
    ):
        self._ensure_maps()
        try:
            key = int(person_eid)
        except (TypeError, ValueError):
            key = person_eid

        existing = self.by_person.get(key)
        merged_benefits = set()
        introduced = bool(introduced)
        met_directly = None if met_directly is None else bool(met_directly)
        first_met_tick = None if first_met_tick is None else int(first_met_tick)
        last_met_tick = None if last_met_tick is None else int(last_met_tick)
        snapshot = dict(identity_snapshot) if isinstance(identity_snapshot, dict) else None
        normalized_episodes = self._normalize_person_episodes(episodes) if episodes is not None else None
        if existing:
            merged_benefits.update(existing.get("benefits", ()))
            standing = max(float(existing.get("standing", 0.0)), float(standing))
            introduced = bool(existing.get("introduced", False)) or introduced
            if source_eid is None:
                source_eid = existing.get("source_eid")
            if relation_kind is None:
                relation_kind = existing.get("relation_kind")
            if property_id is None:
                property_id = existing.get("property_id")
            if met_directly is None:
                met_directly = existing.get("met_directly")
            if first_met_tick is None:
                first_met_tick = existing.get("first_met_tick")
            if last_met_tick is None:
                last_met_tick = existing.get("last_met_tick")
            if snapshot is None:
                snapshot = existing.get("identity_snapshot")
            if normalized_episodes is None:
                normalized_episodes = self._normalize_person_episodes(existing.get("episodes", ()))

        if normalized_episodes is None:
            normalized_episodes = ()

        if benefits:
            merged_benefits.update(str(bit).strip().lower() for bit in benefits if str(bit).strip())

        if met_directly:
            if first_met_tick is None:
                first_met_tick = int(tick)
            if last_met_tick is None:
                last_met_tick = int(tick)

        self.by_person[key] = {
            "source_eid": source_eid,
            "relation_kind": relation_kind,
            "standing": _clamp_unit(standing, default=0.5),
            "tick": int(tick),
            "property_id": property_id,
            "benefits": tuple(sorted(merged_benefits)),
            "introduced": introduced,
            "met_directly": bool(met_directly),
            "first_met_tick": first_met_tick,
            "last_met_tick": last_met_tick,
            "identity_snapshot": dict(snapshot) if isinstance(snapshot, dict) else None,
            "episodes": normalized_episodes,
        }


class JusticeProfile:
    def __init__(self, enforce_all=False, justice=0.5, corruption=0.0, crime_sensitivity=None):
        self.enforce_all = bool(enforce_all)
        self.justice = _clamp_unit(justice, default=0.5)
        if crime_sensitivity is None:
            crime_sensitivity = justice
        self.crime_sensitivity = _clamp_unit(crime_sensitivity, default=self.justice)
        self.corruption = _clamp_unit(corruption, default=0.0)


class PlayerAssets:
    def __init__(self, credits=100):
        self.credits = int(credits)
        self.owned_property_ids = set()


class DroneState:
    def __init__(
        self,
        *,
        owner_eid=None,
        owner_tag=None,
        controller_eid=None,
        controller_tag=None,
        faction_id=None,
        legal_owner_tag=None,
        chassis_item_id=None,
        chassis_class=None,
        power_center_item_id=None,
        battery_item_id=None,
        battery_charge=0,
        battery_charge_max=0,
        hull_hp=1,
        hull_hp_max=1,
        modules=None,
        cargo=None,
        paint=None,
        mode="packed",
        procedure_key=None,
        home=None,
        range_limit=0,
        deployed_tick=None,
        last_command=None,
        target=None,
        target_eid=None,
        procedure_program_id=None,
        procedure_program=None,
        procedure_bindings=None,
        procedure_pc=None,
        procedure_status=None,
        procedure_last_result=None,
        procedure_last_reason=None,
        procedure_last_tick=None,
        observation_context=None,
        last_watch_report=None,
        source_item_id="packed_drone",
        source_item_instance_id=None,
        source_metadata=None,
        loadout_errors=None,
    ):
        self.owner_eid = owner_eid
        self.owner_tag = str(owner_tag or "").strip() or None
        self.controller_eid = controller_eid
        self.controller_tag = str(controller_tag or "").strip() or None
        self.faction_id = str(faction_id or "").strip() or None
        self.legal_owner_tag = str(legal_owner_tag or "").strip() or None
        self.chassis_item_id = str(chassis_item_id or "").strip().lower() or None
        self.chassis_class = str(chassis_class or "").strip().upper() or None
        self.power_center_item_id = str(power_center_item_id or "").strip().lower() or None
        self.battery_item_id = str(battery_item_id or "").strip().lower() or None
        self.battery_charge = int(max(0, battery_charge or 0))
        self.battery_charge_max = int(max(0, battery_charge_max or 0))
        self.hull_hp_max = int(max(1, hull_hp_max or 1))
        try:
            hull_value = int(hull_hp if hull_hp is not None else self.hull_hp_max)
        except (TypeError, ValueError):
            hull_value = self.hull_hp_max
        self.hull_hp = int(max(0, min(self.hull_hp_max, hull_value)))
        self.modules = [dict(module) for module in (modules or ()) if isinstance(module, dict)]
        self.cargo = [dict(entry) for entry in (cargo or ()) if isinstance(entry, dict)]
        self.paint = dict(paint or {})
        self.mode = str(mode or "packed").strip().lower() or "packed"
        self.procedure_key = str(procedure_key or "").strip().lower() or None
        self.home = tuple(home) if isinstance(home, (list, tuple)) else None
        self.range_limit = int(max(0, range_limit or 0))
        self.deployed_tick = None if deployed_tick is None else int(deployed_tick)
        self.last_command = str(last_command or "").strip().lower() or None
        self.target = tuple(target) if isinstance(target, (list, tuple)) else None
        self.target_eid = target_eid
        self.procedure_program_id = str(procedure_program_id or "").strip().lower() or None
        self.procedure_program = dict(procedure_program or {}) if isinstance(procedure_program, dict) else None
        self.procedure_bindings = dict(procedure_bindings or {}) if isinstance(procedure_bindings, dict) else {}
        self.procedure_pc = None if procedure_pc is None else int(procedure_pc)
        self.procedure_status = str(procedure_status or "").strip().lower() or None
        self.procedure_last_result = str(procedure_last_result or "").strip().lower() or None
        self.procedure_last_reason = str(procedure_last_reason or "").strip().lower() or None
        self.procedure_last_tick = None if procedure_last_tick is None else int(procedure_last_tick)
        # Live watch/search state belongs to the deployed actor.  Chunk and
        # whole-simulation persistence pickle it normally, while repacking a
        # drone deliberately ends the physical pursuit instead of hiding one
        # inside an inventory item.
        self.observation_context = dict(observation_context or {}) if isinstance(observation_context, dict) else None
        self.last_watch_report = dict(last_watch_report or {}) if isinstance(last_watch_report, dict) else None
        self.source_item_id = str(source_item_id or "packed_drone").strip().lower() or "packed_drone"
        self.source_item_instance_id = str(source_item_instance_id or "").strip() or None
        self.source_metadata = dict(source_metadata or {})
        self.loadout_errors = tuple(str(error) for error in (loadout_errors or ()) if str(error).strip())

    @classmethod
    def from_packed_metadata(
        cls,
        metadata=None,
        *,
        source_item_instance_id=None,
        source_item_id="packed_drone",
        owner_eid=None,
        owner_tag=None,
        controller_eid=None,
        controller_tag=None,
        deployed_tick=None,
        item_catalog=None,
    ):
        normalized = normalize_packed_drone_metadata(metadata, item_catalog=item_catalog)
        summary = drone_loadout_summary(normalized, item_catalog=item_catalog)
        return cls(
            owner_eid=owner_eid if owner_eid is not None else normalized.get("owner_eid"),
            owner_tag=owner_tag if owner_tag is not None else normalized.get("owner_tag"),
            controller_eid=controller_eid if controller_eid is not None else normalized.get("controller_eid"),
            controller_tag=controller_tag if controller_tag is not None else normalized.get("controller_tag"),
            faction_id=normalized.get("faction_id"),
            legal_owner_tag=normalized.get("legal_owner_tag"),
            chassis_item_id=normalized.get("chassis_item_id"),
            chassis_class=summary.get("chassis_class") or normalized.get("chassis_class"),
            power_center_item_id=normalized.get("power_center_item_id"),
            battery_item_id=normalized.get("battery_item_id"),
            battery_charge=summary.get("battery_charge", normalized.get("battery_charge", 0)),
            battery_charge_max=summary.get("battery_charge_max", normalized.get("battery_charge_max", 0)),
            hull_hp=summary.get("hull_hp", normalized.get("hull_hp", 1)),
            hull_hp_max=summary.get("hull_hp_max", normalized.get("hull_hp_max", 1)),
            modules=normalized.get("modules", ()),
            cargo=normalized.get("cargo", ()),
            paint=normalized.get("paint", {}),
            mode=normalized.get("mode", "packed"),
            procedure_key=normalized.get("procedure_key"),
            home=normalized.get("home"),
            range_limit=summary.get("range_limit", normalized.get("range_limit", 0)),
            deployed_tick=deployed_tick,
            last_command=normalized.get("last_command"),
            target=normalized.get("target"),
            target_eid=normalized.get("target_eid"),
            procedure_program_id=normalized.get("procedure_program_id"),
            procedure_program=normalized.get("procedure_program"),
            procedure_bindings=normalized.get("procedure_bindings"),
            procedure_pc=normalized.get("procedure_pc"),
            procedure_status=normalized.get("procedure_status"),
            procedure_last_result=normalized.get("procedure_last_result"),
            procedure_last_reason=normalized.get("procedure_last_reason"),
            procedure_last_tick=normalized.get("procedure_last_tick"),
            source_item_id=source_item_id,
            source_item_instance_id=source_item_instance_id or normalized.get("source_item_instance_id"),
            source_metadata=normalized,
            loadout_errors=summary.get("errors", ()),
        )


class DroneWorkshopState:
    """Player-owned loose drone part storage.

    Chassis use bounded bay slots. Power cores and modules use a generous
    point budget so early drone experimentation does not crowd the backpack.
    """

    def __init__(
        self,
        *,
        chassis_slots=None,
        parts=None,
        chassis_capacity=4,
        parts_capacity_points=60,
    ):
        self.chassis_capacity = int(max(1, chassis_capacity or 4))
        self.parts_capacity_points = int(max(1, parts_capacity_points or 60))
        self.chassis_slots = [
            dict(entry)
            for entry in (chassis_slots or ())
            if isinstance(entry, dict)
        ]
        self.parts = [
            dict(entry)
            for entry in (parts or ())
            if isinstance(entry, dict)
        ]


class WireState:
    """Player-owned wireware/data storage and future active rig state."""

    def __init__(
        self,
        *,
        kit_entries=None,
        capacity_points=0,
        program_slots=0,
        ram_slots=None,
        equipped_interface_instance_id=None,
        active_connection=None,
        active_scene=None,
        connection_status="offline",
        last_wire_feedback="",
        last_ejection_state=None,
        schema_version=1,
    ):
        self.schema_version = int(schema_version or 1)
        self.capacity_points = int(max(0, capacity_points or 0))
        self.program_slots = int(max(0, program_slots or 0))
        self.kit_entries = [
            dict(entry)
            for entry in (kit_entries or ())
            if isinstance(entry, dict)
        ]
        self.ram_slots = [
            dict(entry)
            for entry in (ram_slots or ())
            if isinstance(entry, dict)
        ][: self.program_slots]
        self.equipped_interface_instance_id = (
            str(equipped_interface_instance_id).strip()
            if equipped_interface_instance_id
            else None
        )
        self.active_connection = dict(active_connection) if isinstance(active_connection, dict) else None
        self.active_scene = dict(active_scene) if isinstance(active_scene, dict) else None
        self.connection_status = str(connection_status or "offline").strip().lower() or "offline"
        self.last_wire_feedback = str(last_wire_feedback or "")
        self.last_ejection_state = dict(last_ejection_state) if isinstance(last_ejection_state, dict) else None


class VehicleState:
    def __init__(
        self,
        active_vehicle_id=None,
        in_vehicle=False,
        *,
        heading_dx=0,
        heading_dy=-1,
        speed=0,
        medium="land",
        headlights_on=True,
    ):
        vehicle_id = str(active_vehicle_id).strip() if active_vehicle_id else ""
        self.active_vehicle_id = vehicle_id or None
        self.in_vehicle = bool(in_vehicle)
        self.last_vehicle_id = self.active_vehicle_id
        self.last_changed_tick = -1
        self.heading_dx, self.heading_dy = self._normalized_heading(heading_dx, heading_dy)
        self.speed = max(0, min(4, int(speed or 0)))
        self.medium = str(medium or "land").strip().lower() or "land"
        self.headlights_on = bool(headlights_on)

    @staticmethod
    def _normalized_heading(dx, dy):
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        if step_x == 0 and step_y == 0:
            return 0, -1
        return step_x, step_y

    def ensure_motion_defaults(self):
        self.heading_dx, self.heading_dy = self._normalized_heading(
            getattr(self, "heading_dx", 0),
            getattr(self, "heading_dy", -1),
        )
        try:
            speed = int(getattr(self, "speed", 0) or 0)
        except (TypeError, ValueError):
            speed = 0
        self.speed = max(0, min(4, speed))
        self.medium = str(getattr(self, "medium", "land") or "land").strip().lower() or "land"
        if not hasattr(self, "headlights_on"):
            self.headlights_on = True
        else:
            self.headlights_on = bool(getattr(self, "headlights_on", True))
        return self

    def heading(self):
        self.ensure_motion_defaults()
        return int(self.heading_dx), int(self.heading_dy)

    def set_heading(self, dx, dy, tick=0):
        self.heading_dx, self.heading_dy = self._normalized_heading(dx, dy)
        self.last_changed_tick = int(tick)
        return self.heading()

    def set_speed(self, speed, tick=0):
        try:
            speed = int(speed or 0)
        except (TypeError, ValueError):
            speed = 0
        self.speed = max(0, min(4, speed))
        self.last_changed_tick = int(tick)
        return int(self.speed)

    def reset_motion(self, tick=0):
        self.set_speed(0, tick=tick)
        return self

    def set_headlights(self, active, tick=0):
        self.ensure_motion_defaults()
        self.headlights_on = bool(active)
        self.last_changed_tick = int(tick)
        return bool(self.headlights_on)

    def toggle_headlights(self, tick=0):
        self.ensure_motion_defaults()
        return self.set_headlights(not bool(getattr(self, "headlights_on", True)), tick=tick)

    def set_active_vehicle(self, vehicle_id, tick=0):
        self.ensure_motion_defaults()
        vehicle_id = str(vehicle_id).strip() if vehicle_id else ""
        self.active_vehicle_id = vehicle_id or None
        if self.active_vehicle_id:
            self.last_vehicle_id = self.active_vehicle_id
        self.last_changed_tick = int(tick)
        return self.active_vehicle_id

    def set_in_vehicle(self, active, tick=0):
        self.ensure_motion_defaults()
        self.in_vehicle = bool(active)
        if not self.in_vehicle:
            self.speed = 0
        self.last_changed_tick = int(tick)
        return self.in_vehicle


class DoorWaitState:
    """Tracks when an NPC is waiting at a door after being summoned by knock."""
    def __init__(
        self,
        aperture_x=0,
        aperture_y=0,
        aperture_z=0,
        *,
        wait_x=None,
        wait_y=None,
        wait_z=None,
        property_id="",
        caller_eid=None,
        start_tick=0,
        timeout_ticks=3000,
        mood="neutral",
        answer_role="resident",
        allow_hours=True,
        allow_services=False,
        close_on_finish=True,
    ):
        self.aperture_x = int(aperture_x)
        self.aperture_y = int(aperture_y)
        self.aperture_z = int(aperture_z)
        self.wait_x = int(aperture_x if wait_x is None else wait_x)
        self.wait_y = int(aperture_y if wait_y is None else wait_y)
        self.wait_z = int(aperture_z if wait_z is None else wait_z)
        self.property_id = str(property_id or "").strip()
        self.caller_eid = caller_eid
        self.start_tick = int(start_tick)
        self.timeout_ticks = int(timeout_ticks)  # ~50 seconds at 60 ticks/second
        self.mood = str(mood or "neutral").strip().lower() or "neutral"
        self.answer_role = str(answer_role or "resident").strip().lower() or "resident"
        self.allow_hours = bool(allow_hours)
        self.allow_services = bool(allow_services)
        self.close_on_finish = bool(close_on_finish)

    def is_expired(self, current_tick):
        return current_tick - self.start_tick >= self.timeout_ticks


class FinancialProfile:
    def __init__(
        self,
        bank_balance=0,
        debt_balance=0,
        debts=None,
        wallet_buffer=90,
        deposit_step=48,
        withdraw_step=40,
        interest_rate=0.0,
        interest_interval=120,
        last_income_hour=None,
    ):
        self.bank_balance = int(max(0, bank_balance))
        self.debt_balance = int(max(0, debt_balance))
        self.debts = {}
        if isinstance(debts, dict):
            for key, amount in debts.items():
                debt_key = str(key or "").strip().lower()
                if not debt_key:
                    continue
                try:
                    debt_amount = int(amount)
                except (TypeError, ValueError):
                    debt_amount = 0
                if debt_amount > 0:
                    self.debts[debt_key] = debt_amount
        if self.debt_balance > 0 and "general" not in self.debts:
            self.debts["general"] = int(self.debt_balance)
        self.debt_balance = self.total_debt()
        self.wallet_buffer = int(max(0, wallet_buffer))
        self.deposit_step = int(max(1, deposit_step))
        self.withdraw_step = int(max(1, withdraw_step))
        # Deposits are a persistence/safety mechanic, not an income source.
        self.interest_rate = float(max(0.0, min(0.08, interest_rate)))
        self.interest_interval = int(max(20, interest_interval))
        self.next_interest_tick = 0
        try:
            self.last_income_hour = None if last_income_hour in {None, ""} else int(last_income_hour)
        except (TypeError, ValueError):
            self.last_income_hour = None
        self.next_bank_check_tick = 0

        # policy keys: money, item, medical
        self.policies = {}
        self.total_claims_paid = 0
        self.claim_count = 0

    def ensure_income_fields(self):
        if not hasattr(self, "last_income_hour"):
            self.last_income_hour = None
        elif self.last_income_hour == "":
            self.last_income_hour = None
        elif self.last_income_hour is not None:
            try:
                self.last_income_hour = int(self.last_income_hour)
            except (TypeError, ValueError):
                self.last_income_hour = None
        if not hasattr(self, "next_bank_check_tick"):
            self.next_bank_check_tick = 0
        else:
            try:
                self.next_bank_check_tick = max(0, int(self.next_bank_check_tick))
            except (TypeError, ValueError):
                self.next_bank_check_tick = 0
        return self

    def _ensure_debts(self):
        debts = getattr(self, "debts", None)
        if isinstance(debts, dict):
            cleaned = {}
            for key, amount in debts.items():
                debt_key = str(key or "").strip().lower()
                if not debt_key:
                    continue
                try:
                    debt_amount = int(amount)
                except (TypeError, ValueError):
                    debt_amount = 0
                if debt_amount > 0:
                    cleaned[debt_key] = debt_amount
            self.debts = cleaned
        else:
            self.debts = {}
        legacy_balance = int(max(0, getattr(self, "debt_balance", 0) or 0))
        if legacy_balance > 0 and not self.debts:
            self.debts["general"] = legacy_balance
        self.debt_balance = int(sum(int(amount) for amount in self.debts.values()))
        return self.debts

    def total_debt(self):
        self._ensure_debts()
        return int(getattr(self, "debt_balance", 0) or 0)

    def debt_amount(self, debt_key="general"):
        debts = self._ensure_debts()
        debt_key = str(debt_key or "general").strip().lower() or "general"
        return int(max(0, debts.get(debt_key, 0) or 0))

    def add_debt(self, debt_key, amount):
        amount = int(max(0, amount or 0))
        if amount <= 0:
            return self.total_debt()
        debts = self._ensure_debts()
        debt_key = str(debt_key or "general").strip().lower() or "general"
        debts[debt_key] = int(max(0, debts.get(debt_key, 0) or 0)) + amount
        self.debt_balance = int(sum(int(value) for value in debts.values()))
        return int(self.debt_balance)

    def pay_debt(self, debt_key, amount):
        amount = int(max(0, amount or 0))
        if amount <= 0:
            return 0
        debts = self._ensure_debts()
        debt_key = str(debt_key or "general").strip().lower() or "general"
        current = int(max(0, debts.get(debt_key, 0) or 0))
        paid = min(current, amount)
        remaining = max(0, current - paid)
        if remaining > 0:
            debts[debt_key] = remaining
        else:
            debts.pop(debt_key, None)
        self.debt_balance = int(sum(int(value) for value in debts.values()))
        return int(paid)


class Inventory:
    def __init__(self, capacity=10):
        self.capacity = int(max(1, capacity))
        self.items = []

    def slot_count(self, entries=None):
        source = self.items if entries is None else list(entries or ())
        return sum(item_inventory_slot_cost(entry) for entry in source)

    def add_item(
        self,
        item_id,
        quantity=1,
        stack_max=1,
        instance_id=None,
        instance_factory=None,
        owner_eid=None,
        owner_tag=None,
        metadata=None,
    ):
        quantity = int(quantity)
        stack_max = max(1, int(stack_max))
        if quantity <= 0:
            return False, None

        created_instance_id = None
        reserved_instance_id = None
        if not item_metadata_has_scratch_roll(item_id, metadata):
            if instance_id:
                scratch_seed = instance_id
            elif instance_factory:
                reserved_instance_id = instance_factory()
                scratch_seed = reserved_instance_id
            else:
                scratch_seed = f"inventory:{item_id}:{len(self.items)}:{quantity}:{stack_max}"
            metadata = item_metadata_with_creation_seed(item_id, metadata, scratch_seed)
        remaining_metadata = prepare_item_stack_metadata(item_id, metadata=metadata, quantity=quantity)
        remaining_quantity = int(quantity)

        if stack_max > 1:
            for entry in self.items:
                if entry["item_id"] != item_id:
                    continue
                if entry["quantity"] >= stack_max:
                    continue
                if entry.get("owner_eid") != owner_eid:
                    continue
                if entry.get("owner_tag") != owner_tag:
                    continue
                if not item_stacks_are_compatible(
                    item_id,
                    existing_metadata=entry.get("metadata"),
                    incoming_metadata=remaining_metadata,
                ):
                    continue

                room = stack_max - entry["quantity"]
                amount = min(room, quantity)
                portion_metadata, remaining_metadata = split_item_stack_metadata(
                    item_id,
                    metadata=remaining_metadata,
                    stack_quantity=remaining_quantity,
                    removed_quantity=amount,
                )
                previous_quantity = int(entry["quantity"])
                entry["quantity"] += amount
                entry["metadata"] = merge_item_stack_metadata(
                    item_id,
                    existing_metadata=entry.get("metadata"),
                    existing_quantity=previous_quantity,
                    incoming_metadata=portion_metadata,
                    incoming_quantity=amount,
                )
                quantity -= amount
                remaining_quantity -= amount
                created_instance_id = entry["instance_id"]
                if quantity <= 0:
                    return True, created_instance_id

        while quantity > 0:
            amount = min(stack_max, quantity)
            portion_metadata, remaining_metadata = split_item_stack_metadata(
                item_id,
                metadata=remaining_metadata,
                stack_quantity=remaining_quantity,
                removed_quantity=amount,
            )
            slot_cost = item_inventory_slot_cost({
                "item_id": item_id,
                "metadata": portion_metadata,
            })
            if slot_cost > 0 and (self.slot_count() + slot_cost) > self.capacity:
                return False, created_instance_id
            if instance_id and created_instance_id is None:
                iid = instance_id
            elif reserved_instance_id and created_instance_id is None:
                iid = reserved_instance_id
            elif instance_factory:
                iid = instance_factory()
            else:
                iid = f"item-stack-{len(self.items) + 1}"

            self.items.append({
                "instance_id": iid,
                "item_id": item_id,
                "quantity": amount,
                "owner_eid": owner_eid,
                "owner_tag": owner_tag,
                "metadata": prepare_item_stack_metadata(item_id, metadata=portion_metadata, quantity=amount),
            })

            if created_instance_id is None:
                created_instance_id = iid
            quantity -= amount
            remaining_quantity -= amount

        return True, created_instance_id

    def find(self, instance_id=None, item_id=None):
        for entry in self.items:
            if instance_id and entry["instance_id"] != instance_id:
                continue
            if item_id and entry["item_id"] != item_id:
                continue
            return entry
        return None

    def remove_item(self, instance_id=None, item_id=None, quantity=1):
        quantity = int(max(1, quantity))
        for idx, entry in enumerate(self.items):
            if instance_id and entry["instance_id"] != instance_id:
                continue
            if item_id and entry["item_id"] != item_id:
                continue

            removed_qty = min(quantity, entry["quantity"])
            removed_metadata, remaining_metadata = split_item_stack_metadata(
                entry.get("item_id"),
                metadata=entry.get("metadata"),
                stack_quantity=entry.get("quantity", 1),
                removed_quantity=removed_qty,
            )
            removed = {
                "instance_id": entry["instance_id"],
                "item_id": entry["item_id"],
                "quantity": removed_qty,
                "owner_eid": entry.get("owner_eid"),
                "owner_tag": entry.get("owner_tag"),
                "metadata": removed_metadata,
            }

            entry["quantity"] -= removed_qty
            if entry["quantity"] <= 0:
                self.items.pop(idx)
            else:
                entry["metadata"] = prepare_item_stack_metadata(
                    entry["item_id"],
                    metadata=remaining_metadata,
                    quantity=entry["quantity"],
                )
            return removed
        return None

    def update_item_metadata(self, instance_id, metadata=None, *, replace=False):
        target = self.find(instance_id=instance_id)
        if not target:
            return None
        updated = {} if replace else dict(target.get("metadata") or {})
        if metadata is not None:
            updated.update(dict(metadata))
        target["metadata"] = prepare_item_stack_metadata(
            target["item_id"],
            metadata=updated,
            quantity=target.get("quantity", 1),
        )
        return target["metadata"]

    def first_usable(self, catalog):
        for entry in self.items:
            item_def = catalog.get(entry["item_id"], {})
            effects = item_def.get("effects", [])
            if effects:
                return entry
        return None


class StatusEffects:
    def __init__(self):
        self.active = {}

    def add(self, status, duration, modifiers=None, source_item=None):
        if not status:
            return False

        status = str(status)
        duration = int(max(1, duration))
        modifiers = modifiers or {}

        if status in self.active:
            current = self.active[status]
            current["remaining"] = max(current["remaining"], duration)
            for key, value in modifiers.items():
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                prior = float(current["modifiers"].get(key, 0.0))
                if abs(value) >= abs(prior):
                    current["modifiers"][key] = value
            if source_item:
                current["source_item"] = source_item
            return False

        parsed_modifiers = {}
        for key, value in modifiers.items():
            try:
                parsed_modifiers[key] = float(value)
            except (TypeError, ValueError):
                continue

        self.active[status] = {
            "remaining": duration,
            "modifiers": parsed_modifiers,
            "source_item": source_item,
        }
        return True

    def has(self, status):
        return status in self.active

    def remove(self, status):
        status = str(status or "").strip()
        if not status:
            return None
        return self.active.pop(status, None)

    def tick(self):
        return self.advance(1)

    def advance(self, ticks):
        try:
            ticks = int(ticks)
        except (TypeError, ValueError):
            ticks = 0
        ticks = max(0, ticks)
        if ticks <= 0:
            return []

        expired = []
        for status, state in list(self.active.items()):
            state["remaining"] -= ticks
            if state["remaining"] <= 0:
                expired.append(status)
                self.active.pop(status)
        return expired

    def modifiers_sum(self):
        total = {}
        for state in self.active.values():
            for key, value in state["modifiers"].items():
                total[key] = total.get(key, 0.0) + float(value)
        return total


class SubstanceUseState:
    def __init__(self):
        self.substances = {}

    def _entry_for(self, substance_id):
        token = str(substance_id or "").strip().lower()
        if not token:
            return None
        entry = self.substances.get(token)
        if isinstance(entry, dict):
            return entry
        entry = {
            "substance_id": token,
            "dependence": 0.0,
            "dependence_decay": 0.0,
            "withdrawal_threshold": 1.0,
            "withdrawal_status": "",
            "withdrawal_duration": 0,
            "withdrawal_cooldown": 0,
            "withdrawal_modifiers": {},
            "active_until_tick": -1,
            "withdrawal_ready_tick": -1,
            "last_tick": 0,
        }
        self.substances[token] = entry
        return entry

    def record_use(
        self,
        substance_id,
        *,
        tick=0,
        intoxication_duration=0,
        dependence_gain=0.0,
        dependence_decay=0.0,
        withdrawal_threshold=1.0,
        withdrawal_status="",
        withdrawal_duration=0,
        withdrawal_cooldown=0,
        withdrawal_modifiers=None,
        statuses=None,
    ):
        entry = self._entry_for(substance_id)
        if entry is None:
            return None

        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0
        try:
            intoxication_duration = max(0, int(intoxication_duration))
        except (TypeError, ValueError):
            intoxication_duration = 0
        try:
            dependence_gain = max(0.0, float(dependence_gain))
        except (TypeError, ValueError):
            dependence_gain = 0.0
        try:
            dependence_decay = max(0.0, float(dependence_decay))
        except (TypeError, ValueError):
            dependence_decay = 0.0
        try:
            withdrawal_threshold = max(0.0, min(1.0, float(withdrawal_threshold)))
        except (TypeError, ValueError):
            withdrawal_threshold = 1.0
        try:
            withdrawal_duration = max(0, int(withdrawal_duration))
        except (TypeError, ValueError):
            withdrawal_duration = 0
        try:
            withdrawal_cooldown = max(0, int(withdrawal_cooldown))
        except (TypeError, ValueError):
            withdrawal_cooldown = 0

        entry["dependence"] = max(0.0, min(1.0, float(entry.get("dependence", 0.0)) + dependence_gain))
        entry["dependence_decay"] = dependence_decay
        entry["withdrawal_threshold"] = withdrawal_threshold
        entry["withdrawal_status"] = str(withdrawal_status or "").strip().lower()
        entry["withdrawal_duration"] = withdrawal_duration
        entry["withdrawal_cooldown"] = withdrawal_cooldown
        entry["withdrawal_modifiers"] = (
            dict(withdrawal_modifiers)
            if isinstance(withdrawal_modifiers, dict)
            else {}
        )
        entry["active_until_tick"] = max(
            int(entry.get("active_until_tick", -1)),
            int(tick + intoxication_duration),
        )
        entry["withdrawal_ready_tick"] = max(
            int(entry.get("withdrawal_ready_tick", -1)),
            int(tick + intoxication_duration),
        )
        entry["last_tick"] = tick

        if statuses:
            withdrawal_state = entry["withdrawal_status"]
            if withdrawal_state:
                statuses.remove(withdrawal_state)
        return dict(entry)

    def advance(self, tick, *, statuses=None):
        try:
            tick = int(tick)
        except (TypeError, ValueError):
            tick = 0

        pending = []
        empty_keys = []
        for substance_id, entry in list(self.substances.items()):
            if not isinstance(entry, dict):
                empty_keys.append(substance_id)
                continue

            last_tick = entry.get("last_tick", tick)
            try:
                last_tick = int(last_tick)
            except (TypeError, ValueError):
                last_tick = tick
            elapsed = max(0, tick - last_tick)
            dependence = max(0.0, min(1.0, float(entry.get("dependence", 0.0) or 0.0)))
            active_until_tick = int(entry.get("active_until_tick", -1) or -1)
            if elapsed > 0 and tick >= active_until_tick:
                decay = max(0.0, float(entry.get("dependence_decay", 0.0) or 0.0))
                if decay > 0.0:
                    dependence = max(0.0, dependence - (decay * float(elapsed)))
            entry["dependence"] = dependence
            entry["last_tick"] = tick

            threshold = max(0.0, min(1.0, float(entry.get("withdrawal_threshold", 1.0) or 1.0)))
            withdrawal_status = str(entry.get("withdrawal_status", "") or "").strip().lower()
            if not withdrawal_status:
                if dependence <= 0.0:
                    empty_keys.append(substance_id)
                continue
            if tick < int(entry.get("withdrawal_ready_tick", -1) or -1):
                continue
            if tick < active_until_tick:
                continue
            if dependence < threshold:
                if dependence <= 0.0:
                    empty_keys.append(substance_id)
                continue
            if statuses and statuses.has(withdrawal_status):
                continue

            duration = max(1, int(entry.get("withdrawal_duration", 1) or 1))
            cooldown = max(0, int(entry.get("withdrawal_cooldown", 0) or 0))
            entry["withdrawal_ready_tick"] = int(tick + duration + cooldown)
            pending.append({
                "substance_id": substance_id,
                "status": withdrawal_status,
                "duration": duration,
                "modifiers": dict(entry.get("withdrawal_modifiers", {}) or {}),
            })

        for substance_id in empty_keys:
            self.substances.pop(substance_id, None)
        return pending


class ItemUseProfile:
    def __init__(
        self,
        willingness=0.5,
        risk_tolerance=0.4,
        auto_use=True,
        cooldown_ticks=10,
        preferred_tags=None,
        avoid_tags=None,
    ):
        self.willingness = float(willingness)
        self.risk_tolerance = float(risk_tolerance)
        self.auto_use = bool(auto_use)
        self.cooldown_ticks = int(max(1, cooldown_ticks))
        self.last_use_tick = -10_000
        self.preferred_tags = set(preferred_tags or [])
        self.avoid_tags = set(avoid_tags or [])


class Vitality:
    def __init__(
        self,
        max_hp=100,
        hp=None,
        downed=False,
        recover_to_hp=28,
    ):
        self.max_hp = int(max(1, max_hp))
        if hp is None:
            hp = self.max_hp
        self.hp = int(max(0, min(self.max_hp, hp)))
        self.downed = bool(downed)
        self.recover_to_hp = int(max(1, min(self.max_hp, recover_to_hp)))
        self.downed_tick = None
        self.downed_count = 0


class WeaponLoadout:
    def __init__(self, weapon_ids=None, equipped_weapon_id=None, reserve_ammo=None):
        self.weapon_ids = list(weapon_ids or [])
        self.reserve_ammo = dict(reserve_ammo or {})
        self.weapon_instances = {}
        self.cooldown_until_tick = 0
        self.last_fire_tick = -10_000

        if equipped_weapon_id and equipped_weapon_id not in self.weapon_ids:
            self.weapon_ids.append(equipped_weapon_id)

        if self.weapon_ids:
            self.equipped_weapon_id = equipped_weapon_id or self.weapon_ids[0]
        else:
            self.equipped_weapon_id = None

    def add_weapon(self, weapon_id, instance=None):
        weapon_id = str(weapon_id)
        if weapon_id not in self.weapon_ids:
            self.weapon_ids.append(weapon_id)
        if self.equipped_weapon_id is None:
            self.equipped_weapon_id = weapon_id
        if instance:
            self.weapon_instances[weapon_id] = dict(instance)

    def equip(self, weapon_id):
        weapon_id = str(weapon_id)
        if weapon_id not in self.weapon_ids:
            self.weapon_ids.append(weapon_id)
        self.equipped_weapon_id = weapon_id
        return self.equipped_weapon_id

    def remove_weapon(self, weapon_id):
        weapon_id = str(weapon_id)
        removed = False
        if weapon_id in self.weapon_ids:
            self.weapon_ids = [wid for wid in self.weapon_ids if wid != weapon_id]
            removed = True
        self.weapon_instances.pop(weapon_id, None)

        if self.equipped_weapon_id == weapon_id:
            self.equipped_weapon_id = self.weapon_ids[0] if self.weapon_ids else None
            removed = True
        elif self.equipped_weapon_id not in self.weapon_ids:
            self.equipped_weapon_id = self.weapon_ids[0] if self.weapon_ids else None
        return removed

    def weapon_instance(self, weapon_id):
        weapon_id = str(weapon_id or "").strip()
        if not weapon_id:
            return {}
        instance = self.weapon_instances.get(weapon_id, {})
        return instance if isinstance(instance, dict) else {}

    def weapon_inventory_instance_id(self, weapon_id):
        instance = self.weapon_instance(weapon_id)
        return str(instance.get("inventory_instance_id", "") or "").strip()

    def reserve_ammo_key(self, weapon_id, *, instance_id=None):
        weapon_id = str(weapon_id or "").strip()
        if not weapon_id:
            return ""
        raw_instance_id = str(
            instance_id
            or self.weapon_inventory_instance_id(weapon_id)
            or ""
        ).strip()
        if raw_instance_id:
            return f"{weapon_id}::{raw_instance_id}"
        return weapon_id

    def reserve_ammo_value(self, weapon_id, default=None, *, instance_id=None):
        weapon_id = str(weapon_id or "").strip()
        if not weapon_id:
            return default
        key = self.reserve_ammo_key(weapon_id, instance_id=instance_id)
        if key in self.reserve_ammo:
            try:
                return int(self.reserve_ammo.get(key, default if default is not None else 0))
            except (TypeError, ValueError):
                return default

        if key != weapon_id and weapon_id in self.reserve_ammo:
            try:
                value = int(self.reserve_ammo.get(weapon_id, default if default is not None else 0))
            except (TypeError, ValueError):
                return default
            self.reserve_ammo[key] = value
            self.reserve_ammo.pop(weapon_id, None)
            return value
        return default

    def set_reserve_ammo_value(self, weapon_id, value, *, instance_id=None):
        weapon_id = str(weapon_id or "").strip()
        if not weapon_id:
            return None
        key = self.reserve_ammo_key(weapon_id, instance_id=instance_id)
        try:
            ammo = int(value)
        except (TypeError, ValueError):
            ammo = 0
        ammo = max(0, ammo)
        if key != weapon_id:
            self.reserve_ammo.pop(weapon_id, None)
        self.reserve_ammo[key] = ammo
        return ammo

    def current_weapon(self):
        return self.equipped_weapon_id

    def cycle(self, step=1):
        if not self.weapon_ids:
            self.equipped_weapon_id = None
            return None
        if self.equipped_weapon_id not in self.weapon_ids:
            self.equipped_weapon_id = self.weapon_ids[0]
            return self.equipped_weapon_id

        idx = self.weapon_ids.index(self.equipped_weapon_id)
        idx = (idx + int(step)) % len(self.weapon_ids)
        self.equipped_weapon_id = self.weapon_ids[idx]
        return self.equipped_weapon_id


class ArmorLoadout:
    def __init__(
        self,
        equipped_instance_id=None,
        equipped_item_id=None,
        equipped_name=None,
        damage_reduction=0.0,
        slot="body",
    ):
        self.slot = str(slot or "body").strip().lower() or "body"
        self.equipped_instance_id = str(equipped_instance_id).strip() if equipped_instance_id else None
        self.equipped_item_id = str(equipped_item_id).strip() if equipped_item_id else None
        self.equipped_name = str(equipped_name).strip() if equipped_name else None
        try:
            reduction = float(damage_reduction)
        except (TypeError, ValueError):
            reduction = 0.0
        self.damage_reduction = max(0.0, min(0.85, reduction))

    def equip(self, instance_id, item_id, name=None, damage_reduction=0.0, slot=None):
        if slot:
            self.slot = str(slot).strip().lower() or self.slot
        self.equipped_instance_id = str(instance_id).strip() if instance_id else None
        self.equipped_item_id = str(item_id).strip() if item_id else None
        self.equipped_name = str(name).strip() if name else None
        try:
            reduction = float(damage_reduction)
        except (TypeError, ValueError):
            reduction = 0.0
        self.damage_reduction = max(0.0, min(0.85, reduction))
        return self.equipped_instance_id

    def clear(self):
        self.equipped_instance_id = None
        self.equipped_item_id = None
        self.equipped_name = None
        self.damage_reduction = 0.0

    def is_equipped(self, instance_id):
        return bool(instance_id) and self.equipped_instance_id == str(instance_id).strip()


class AppearanceLoadout:
    VALID_SLOTS = (
        "base_top",
        "base_bottom",
        "hat",
        "earrings",
        "necklace",
        "bracelet",
        "ring_left",
        "ring_right",
        "top",
        "bottom",
        "full_body",
        "shoes",
        "outer",
    )
    BASEWEAR_SLOTS = (
        "base_top",
        "base_bottom",
    )

    def __init__(
        self,
        slots=None,
        body_overrides=None,
        skin_marks=None,
        makeup_regions=None,
        basewear=None,
        basewear_initialized=False,
        skin_marks_seeded=False,
        description_appearance_seeded=False,
    ):
        self.slots = self._clean_slots(slots)
        # ``basewear`` is retained only as a compatibility input for saves
        # made before base garments became ordinary worn inventory items.
        self.basewear = self._clean_basewear(basewear)
        self.basewear_initialized = bool(basewear_initialized)
        self.body_overrides = self._clean_overrides(body_overrides)
        self.skin_marks = self._clean_skin_marks(skin_marks)
        self.makeup_regions = self._clean_overrides(makeup_regions)
        self.skin_marks_seeded = bool(skin_marks_seeded)
        self.description_appearance_seeded = bool(description_appearance_seeded)

    @classmethod
    def _clean_slots(cls, slots=None):
        clean = {slot: None for slot in cls.VALID_SLOTS}
        if isinstance(slots, dict):
            for slot, value in slots.items():
                key = str(slot or "").strip().lower()
                if key not in clean:
                    continue
                text = str(value or "").strip()
                clean[key] = text or None
        return clean

    @staticmethod
    def _clean_basewear(basewear=None):
        clean = {slot: None for slot in AppearanceLoadout.BASEWEAR_SLOTS}
        if not isinstance(basewear, dict):
            return clean
        for slot, value in basewear.items():
            clean_slot = str(slot or "").strip().lower()
            if clean_slot not in clean or not isinstance(value, dict):
                continue
            row = {
                str(key or "").strip().lower(): stored
                for key, stored in value.items()
                if str(key or "").strip()
            }
            if not row:
                continue
            row["slot"] = clean_slot
            clean[clean_slot] = row
        return clean

    @staticmethod
    def _clean_overrides(body_overrides=None):
        clean = {}
        if isinstance(body_overrides, dict):
            for key, value in body_overrides.items():
                clean_key = str(key or "").strip().lower()
                clean_value = str(value or "").strip()
                if clean_key and clean_value:
                    clean[clean_key] = clean_value
        return clean

    @staticmethod
    def _clean_skin_marks(skin_marks=None):
        clean = {}
        if isinstance(skin_marks, dict):
            for slot, value in skin_marks.items():
                clean_slot = str(slot or "").strip().lower()
                if not clean_slot:
                    continue
                if isinstance(value, dict):
                    row = {
                        str(key or "").strip().lower(): stored
                        for key, stored in value.items()
                        if str(key or "").strip()
                    }
                    kind = str(row.get("kind", "") or "").strip().lower()
                    row["kind"] = kind
                    row["slot"] = str(row.get("slot", clean_slot) or clean_slot).strip().lower() or clean_slot
                    if kind:
                        clean[clean_slot] = row
                else:
                    text = str(value or "").strip()
                    if text:
                        clean[clean_slot] = {"kind": "mark", "slot": clean_slot, "description": text}
        return clean

    def normalize(self):
        self.slots = self._clean_slots(getattr(self, "slots", None))
        self.basewear = self._clean_basewear(getattr(self, "basewear", None))
        self.basewear_initialized = bool(getattr(self, "basewear_initialized", False))
        self.body_overrides = self._clean_overrides(getattr(self, "body_overrides", None))
        self.skin_marks = self._clean_skin_marks(getattr(self, "skin_marks", None))
        self.makeup_regions = self._clean_overrides(getattr(self, "makeup_regions", None))
        self.skin_marks_seeded = bool(getattr(self, "skin_marks_seeded", False))
        self.description_appearance_seeded = bool(getattr(self, "description_appearance_seeded", False))
        return self

    def worn_instance_ids(self):
        self.normalize()
        return {str(value).strip() for value in self.slots.values() if str(value or "").strip()}


class SuppressionState:
    """Tracks how suppressed an NPC is by incoming fire.

    pressure: 0.0 (calm) to 1.0 (fully pinned).
    surrendered: True once the NPC gives up.
    """

    def __init__(self):
        self.pressure = 0.0
        self.surrendered = False
        self.surrender_tick = -1
        self.last_spike_tick = -1

    def spike(self, amount, tick):
        self.pressure = min(1.0, self.pressure + float(amount))
        self.last_spike_tick = int(tick)

    def decay(self, rate, bravery, discipline):
        resist = 0.3 + (bravery * 0.4) + (discipline * 0.3)
        self.pressure = max(0.0, self.pressure - (rate * resist))

    def pinned(self):
        return self.pressure >= 0.6 and not self.surrendered

    def shaken(self):
        return self.pressure >= 0.3 and not self.surrendered


class WeaponUseProfile:
    def __init__(
        self,
        aggression=0.55,
        aim_bias=0.62,
        min_range=1,
        max_range=11,
        cooldown_jitter=1,
        allow_explosives=True,
    ):
        self.aggression = float(max(0.0, min(1.0, aggression)))
        self.aim_bias = float(max(0.0, min(1.0, aim_bias)))
        self.min_range = int(max(0, min_range))
        self.max_range = int(max(self.min_range, max_range))
        self.cooldown_jitter = int(max(0, cooldown_jitter))
        self.allow_explosives = bool(allow_explosives)
