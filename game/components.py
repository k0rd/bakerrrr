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

    def __init__(self, ratings=None, **skills):
        self.ratings = {}
        merged = {}
        if isinstance(ratings, dict):
            merged.update(ratings)
        merged.update(skills)
        for skill_id, value in merged.items():
            self.set(skill_id, value)

    def get(self, skill_id, default=None):
        key = str(skill_id or "").strip().lower()
        if not key:
            return default
        if key not in self.ratings:
            return default
        return float(self.ratings[key])

    def set(self, skill_id, value):
        key = str(skill_id or "").strip().lower()
        if not key:
            return
        self.ratings[key] = _clamp_stat(value)

    def update(self, ratings=None, **skills):
        merged = {}
        if isinstance(ratings, dict):
            merged.update(ratings)
        merged.update(skills)
        for skill_id, value in merged.items():
            self.set(skill_id, value)

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
        "seeking_social": 2,
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
    def __init__(self, energy=85.0, safety=75.0, social=65.0):
        self.energy = float(energy)
        self.safety = float(safety)
        self.social = float(social)
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


class Occupation:
    def __init__(self, career, workplace=None, shift_start=None, shift_end=None):
        self.career = career
        self.workplace = workplace
        self.shift_start = shift_start
        self.shift_end = shift_end


class OrganizationProfile:
    def __init__(self, name, kind="organization", key=None, tags=None):
        self.name = str(name or "Organization").strip() or "Organization"
        self.kind = str(kind or "organization").strip().lower() or "organization"
        self.key = str(key or "").strip()
        self.tags = set(str(tag).strip().lower() for tag in (tags or ()) if str(tag).strip())
        self.site_property_ids = set()
        self.site_building_ids = set()
        self.member_eids = set()


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
        active=True,
    ):
        try:
            organization_eid = int(organization_eid)
        except (TypeError, ValueError):
            return False

        self.memberships[organization_eid] = {
            "organization_eid": organization_eid,
            "role": str(role or "member").strip().lower() or "member",
            "kind": str(kind or "member").strip().lower() or "member",
            "site_property_id": str(site_property_id or "").strip() or None,
            "site_building_id": str(site_building_id or "").strip() or None,
            "title": str(title or "").strip() or None,
            "active": bool(active),
        }
        return True


class PropertyPortfolio:
    def __init__(self):
        self.owned_property_ids = set()


class PropertyKnowledge:
    def __init__(self):
        self.known = {}
        self.hidden_property_ids = set()

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
    ):
        self._ensure_maps()
        try:
            key = int(person_eid)
        except (TypeError, ValueError):
            key = person_eid

        existing = self.by_person.get(key)
        merged_benefits = set()
        introduced = bool(introduced)
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

        if benefits:
            merged_benefits.update(str(bit).strip().lower() for bit in benefits if str(bit).strip())

        self.by_person[key] = {
            "source_eid": source_eid,
            "relation_kind": relation_kind,
            "standing": _clamp_unit(standing, default=0.5),
            "tick": int(tick),
            "property_id": property_id,
            "benefits": tuple(sorted(merged_benefits)),
            "introduced": introduced,
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


class FinancialProfile:
    def __init__(
        self,
        bank_balance=0,
        wallet_buffer=90,
        deposit_step=48,
        withdraw_step=40,
        interest_rate=0.0,
        interest_interval=120,
    ):
        self.bank_balance = int(max(0, bank_balance))
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


class Inventory:
    def __init__(self, capacity=10):
        self.capacity = int(max(1, capacity))
        self.items = []

    def slot_count(self):
        return len(self.items)

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
                entry["quantity"] += amount
                quantity -= amount
                created_instance_id = entry["instance_id"]
                if quantity <= 0:
                    return True, created_instance_id

        while quantity > 0:
            if len(self.items) >= self.capacity:
                return False, created_instance_id

            amount = min(stack_max, quantity)
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
                "metadata": dict(metadata or {}),
            })

            if created_instance_id is None:
                created_instance_id = iid
            quantity -= amount

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
            removed = {
                "instance_id": entry["instance_id"],
                "item_id": entry["item_id"],
                "quantity": removed_qty,
                "owner_eid": entry.get("owner_eid"),
                "owner_tag": entry.get("owner_tag"),
                "metadata": dict(entry.get("metadata") or {}),
            }

            entry["quantity"] -= removed_qty
            if entry["quantity"] <= 0:
                self.items.pop(idx)
            return removed
        return None

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

    def tick(self):
        expired = []
        for status, state in list(self.active.items()):
            state["remaining"] -= 1
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
