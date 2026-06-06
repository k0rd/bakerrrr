from dataclasses import dataclass

from game.items import (
    item_inventory_slot_cost,
    merge_item_stack_metadata,
    prepare_item_stack_metadata,
    split_item_stack_metadata,
)


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

    def __init__(
        self,
        ratings=None,
        *,
        baselines=None,
        birth_biases=None,
        practice=None,
        last_practiced=None,
        last_decay=None,
        recent_changes=None,
        **skills,
    ):
        self.ratings = {}
        self.baselines = {}
        self.birth_biases = {}
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
        return tuple(sorted(set(self.ratings) | set(self.baselines) | set(self.practice) | set(self.last_practiced) | set(self.last_decay)))

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

    def floor(self, skill_id, ratio=None, default=1.0):
        base = self.ensure_baseline(skill_id, value=self.get(skill_id, default=default))
        if base is None:
            return _clamp_stat(default)
        try:
            floor_ratio = float(self.DEFAULT_FLOOR_RATIO if ratio is None else ratio)
        except (TypeError, ValueError):
            floor_ratio = float(self.DEFAULT_FLOOR_RATIO)
        floor_ratio = max(0.1, min(1.0, floor_ratio))
        return max(1.0, min(10.0, float(base) * floor_ratio))

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

    def taxonomy_glyph(self, fallback="N"):
        return self.GLYPH_BY_TAXONOMY.get(self.taxonomy_class, str(fallback or "N")[:1].upper() or "N")

    def display_name(self):
        return self.personal_name or self.common_name or self.creature_type

    def descriptive_name(self):
        return self.common_name or self.creature_type

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
        "chasing": 1,
        "scavenging": 2,
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
    def __init__(self, energy=85.0, safety=75.0, social=65.0, hunger=86.0, thirst=90.0):
        self.energy = float(energy)
        self.safety = float(safety)
        self.social = float(social)
        self.hunger = float(hunger)
        self.thirst = float(thirst)
        self.critical = set()


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
        severity=0,
        x=None,
        y=None,
        z=None,
        official_item_links=None,
        official_item_link_counts=None,
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

        record = dict(existing) if isinstance(existing, dict) else {}
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
            "severity": int(severity),
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


@dataclass
class AnimalPhysicalProfile:
    size_score: float
    speed_score: float
    injury_score: float = 0.0
    juvenile: bool = False


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


class VehicleState:
    def __init__(self, active_vehicle_id=None, in_vehicle=False):
        vehicle_id = str(active_vehicle_id).strip() if active_vehicle_id else ""
        self.active_vehicle_id = vehicle_id or None
        self.in_vehicle = bool(in_vehicle)
        self.last_vehicle_id = self.active_vehicle_id
        self.last_changed_tick = -1

    def set_active_vehicle(self, vehicle_id, tick=0):
        vehicle_id = str(vehicle_id).strip() if vehicle_id else ""
        self.active_vehicle_id = vehicle_id or None
        if self.active_vehicle_id:
            self.last_vehicle_id = self.active_vehicle_id
        self.last_changed_tick = int(tick)
        return self.active_vehicle_id

    def set_in_vehicle(self, active, tick=0):
        self.in_vehicle = bool(active)
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

        # policy keys: money, item, medical
        self.policies = {}
        self.total_claims_paid = 0
        self.claim_count = 0

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

    def __init__(self, slots=None, body_overrides=None):
        self.slots = self._clean_slots(slots)
        self.body_overrides = self._clean_overrides(body_overrides)

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
    def _clean_overrides(body_overrides=None):
        clean = {}
        if isinstance(body_overrides, dict):
            for key, value in body_overrides.items():
                clean_key = str(key or "").strip().lower()
                clean_value = str(value or "").strip()
                if clean_key and clean_value:
                    clean[clean_key] = clean_value
        return clean

    def normalize(self):
        self.slots = self._clean_slots(getattr(self, "slots", None))
        self.body_overrides = self._clean_overrides(getattr(self, "body_overrides", None))
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
