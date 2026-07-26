"""Durable, player-facing corporate neighborhood and product presence.

Corporate expansion already owns acquisition decisions and organization pressure.
This module turns the resulting holdings into a recognizable street footprint and
lets the same durable manufacturing identity reach ordinary store goods.
"""

from __future__ import annotations

from hashlib import blake2b
import random

from engine.events import Event
from game.organization_production import (
    organization_manufacturing_identity,
    organization_manufacturing_modifiers,
    organization_production_profile,
)
from game.organizations import (
    organization_policy_snapshot,
    organization_profile,
    property_org_links,
    record_organization_pressure,
)


CORPORATE_PRESENCE_SCHEMA_VERSION = 1

CORPORATE_FOOTPRINT_TIERS = (
    (8.0, 4, "managed_enclave", "Managed Enclave"),
    (5.0, 3, "advertising_hub", "Advertising Hub"),
    (3.0, 2, "branded_corridor", "Branded Corridor"),
    (1.0, 1, "foothold", "Corporate Foothold"),
)

CORPORATE_BRANDABLE_FIXTURES = frozenset(
    {
        "atm_kiosk",
        "banking_kiosk",
        "bench",
        "bus_stop",
        "charging_pillar",
        "claim_terminal",
        "mailbox",
        "news_rack",
        "notice_board",
        "service_terminal",
        "streetlamp",
        "utility_pole",
        "vending_machine",
    }
)

CORPORATE_PRODUCT_EXCLUDED_TAGS = frozenset(
    {
        "animal_part",
        "carcass",
        "corpse",
        "critical",
        "data",
        "evidence",
        "flora",
        "key",
        "personal",
        "quest",
        "raw_meat",
        "scrap",
        "seed",
        "species_part",
        "unique",
    }
)


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower().replace(" ", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, low, high):
    return max(float(low), min(float(high), float(value)))


def _hash_int(*parts):
    payload = "|".join(_text(part) for part in parts).encode("utf-8")
    return int.from_bytes(blake2b(payload, digest_size=12).digest(), "big")


def _metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _property_chunk(sim, prop):
    if not isinstance(prop, dict):
        return None
    chunk = _metadata(prop).get("chunk")
    if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
        try:
            return (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            pass
    try:
        return sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (AttributeError, TypeError, ValueError):
        return None


def _presence_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("corporate_presence")
    if not isinstance(state, dict):
        state = {}
        traits["corporate_presence"] = state
    state["schema_version"] = CORPORATE_PRESENCE_SCHEMA_VERSION
    if not isinstance(state.get("neighborhoods"), dict):
        state["neighborhoods"] = {}
    return state


def ensure_corporate_presence_state(sim):
    """Return the save-compatible corporate neighborhood presence ledger."""

    return _presence_state(sim)


def _corporate_root(sim, organization_eid):
    organization_eid = _safe_int(organization_eid, 0)
    if organization_eid <= 0 or organization_profile(sim, organization_eid) is None:
        return None
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    family = _key(policy.get("family"))
    profile = organization_profile(sim, organization_eid)
    kind = _key(getattr(profile, "kind", "")) if profile is not None else ""
    tags = {_key(tag) for tag in getattr(profile, "tags", ()) or () if _key(tag)} if profile is not None else set()
    if family != "corporate" and kind not in {"corporation", "corporate"} and not tags.intersection({"corporate", "corpsec"}):
        return None
    root_eid = _safe_int(policy.get("root_organization_eid"), organization_eid)
    return root_eid if organization_profile(sim, root_eid) is not None else organization_eid


def corporate_organization_for_property(sim, prop):
    """Return the corporate root visibly attached to a property, if any."""

    if not isinstance(prop, dict):
        return None
    candidates = []
    for link in property_org_links(sim, prop, active_only=True):
        root_eid = _corporate_root(sim, link.get("organization_eid"))
        if root_eid is None:
            continue
        priority = 0
        if bool(link.get("primary")):
            priority += 20
        if _key(link.get("link_kind")) == "operates":
            priority += 10
        elif _key(link.get("link_kind")) == "service_host":
            priority += 6
        candidates.append((priority, int(root_eid)))
    if candidates:
        return sorted(candidates, key=lambda row: (-row[0], row[1]))[0][1]

    acquisition = _metadata(prop).get("corporate_acquisition")
    if isinstance(acquisition, dict):
        return _corporate_root(sim, acquisition.get("corporate_org_eid"))
    return None


def _links_for_corporation(sim, prop, corporate_org_eid):
    corporate_org_eid = _corporate_root(sim, corporate_org_eid)
    if corporate_org_eid is None:
        return ()
    return tuple(
        link
        for link in property_org_links(sim, prop, active_only=True)
        if _corporate_root(sim, link.get("organization_eid")) == corporate_org_eid
    )


def _anchor_weight(sim, prop, corporate_org_eid):
    if not isinstance(prop, dict) or _key(prop.get("kind")) != "building":
        return 0.0
    weight = 0.0
    for link in _links_for_corporation(sim, prop, corporate_org_eid):
        kind = _key(link.get("link_kind"))
        candidate = 0.75
        if kind == "operates":
            candidate = 2.0 if bool(link.get("primary")) else 1.55
        elif kind in {"service_host", "oversight"}:
            candidate = 1.25
        elif kind in {"meeting_place", "territory"}:
            candidate = 0.85
        weight = max(weight, candidate)
    acquisition = _metadata(prop).get("corporate_acquisition")
    if isinstance(acquisition, dict) and _corporate_root(sim, acquisition.get("corporate_org_eid")) == _corporate_root(sim, corporate_org_eid):
        weight = max(weight, 0.75)
        if _key(acquisition.get("status")) in {"acquired", "branch_linked", "franchise_linked"}:
            weight = max(weight, 1.4)
    return float(weight)


def _tier_for_score(score):
    score = _safe_float(score, 0.0)
    for minimum, tier, key, label in CORPORATE_FOOTPRINT_TIERS:
        if score >= minimum:
            return int(tier), key, label
    return 0, "absent", "No Corporate Footprint"


def _neighborhood_key(corporate_org_eid, chunk):
    return f"corporate:{int(corporate_org_eid)}:{int(chunk[0])}:{int(chunk[1])}"


def _campaign_kind(sim, corporate_org_eid):
    production = organization_production_profile(sim, corporate_org_eid)
    specialties = {_key(value) for value in (production.get("manufacturing", {}) or {}).get("specialties", ())}
    if specialties.intersection({"security_systems", "drone_frames"}):
        return "compliance_blanket"
    if specialties.intersection({"consumer_electronics", "power_systems"}):
        return "lifestyle_saturation"
    if "wire_gear" in specialties:
        return "connected_corridor"
    return "redevelopment_campaign"


def _campaign_copy(identity, campaign_kind):
    brand = _text(identity.get("manufacturer")) or _text(identity.get("organization_name")) or "The company"
    motif = _text(identity.get("product_motif")) or "house mark"
    copies = {
        "compliance_blanket": f"{brand} keeps the block moving. Verified access. Predictable service.",
        "lifestyle_saturation": f"Live inside the {brand} line. Look for the {motif} mark.",
        "connected_corridor": f"One block, one signal, one accountable line: {brand}.",
        "redevelopment_campaign": f"A cleaner block begins with consistent choices. {brand} is already here.",
    }
    return copies.get(campaign_kind, copies["redevelopment_campaign"])


def _brand_row(sim, corporate_org_eid, *, tier, tier_key, tier_label, campaign_kind):
    identity = organization_manufacturing_identity(sim, corporate_org_eid)
    return {
        "organization_eid": int(corporate_org_eid),
        "organization_key": _text(identity.get("organization_key")),
        "organization_name": _text(identity.get("organization_name")),
        "brand": _text(identity.get("manufacturer")) or _text(identity.get("organization_name")) or "Corporate line",
        "manufacturing_signature": _text(identity.get("manufacturing_signature")),
        "primary_color_word": _text(identity.get("primary_color_word")),
        "secondary_color_word": _text(identity.get("secondary_color_word")),
        "accent_color_word": _text(identity.get("accent_color_word")),
        "primary_render_key": _text(identity.get("primary_render_key")) or "property_service",
        "motif": _text(identity.get("product_motif")),
        "geometry": _text(identity.get("product_geometry")),
        "finish": _text(identity.get("product_finish")),
        "tier": int(tier),
        "tier_key": _key(tier_key),
        "tier_label": _text(tier_label),
        "campaign_kind": _key(campaign_kind),
        "ad_copy": _campaign_copy(identity, campaign_kind),
    }


def _stamp_anchor_branding(prop, brand_row):
    metadata = _metadata(prop)
    if "corporate_original_display_color" not in metadata:
        metadata["corporate_original_display_color"] = metadata.get("display_color")
    metadata["display_color"] = brand_row.get("primary_render_key") or "property_service"
    metadata["corporate_branding_active"] = True
    metadata["corporate_branding"] = dict(brand_row)
    signage = metadata.get("signage")
    if isinstance(signage, dict):
        if "corporate_original_text" not in signage:
            signage["corporate_original_text"] = signage.get("text")
        local_text = _text(signage.get("corporate_original_text")) or _text(prop.get("name"))
        brand = _text(brand_row.get("brand"))
        signage["text"] = f"{brand} / {local_text}" if local_text and local_text.lower() != brand.lower() else brand
        signage["corporate_branding"] = dict(brand_row)


def _fixture_is_brandable(prop):
    if not isinstance(prop, dict) or _key(prop.get("kind")) not in {"fixture", "asset"}:
        return False
    metadata = _metadata(prop)
    fixture_type = _key(metadata.get("fixture_type") or metadata.get("archetype"))
    if fixture_type not in CORPORATE_BRANDABLE_FIXTURES:
        return False
    if bool(metadata.get("corporate_branding_blocked")):
        return False
    owner_tag = _key(prop.get("owner_tag"))
    return bool(metadata.get("public")) or owner_tag in {"city", "public", "municipal", "unowned"}


def _fixture_brand_rank(sim, prop, corporate_org_eid, chunk):
    return _hash_int(
        getattr(sim, "seed", 0),
        corporate_org_eid,
        chunk[0],
        chunk[1],
        prop.get("id"),
        "corporate-ad-fixture",
    )


def _stamp_fixture_branding(sim, prop, brand_row, *, chunk):
    metadata = _metadata(prop)
    existing = metadata.get("corporate_branding")
    if isinstance(existing, dict) and _safe_int(existing.get("organization_eid"), 0) not in {0, int(brand_row["organization_eid"])}:
        return False
    if "corporate_original_display_color" not in metadata:
        metadata["corporate_original_display_color"] = metadata.get("display_color")
    if "corporate_original_display_description" not in metadata:
        metadata["corporate_original_display_description"] = metadata.get("display_description")
    metadata["display_color"] = brand_row.get("primary_render_key") or "property_service"
    metadata["corporate_branding_active"] = True
    metadata["corporate_branding"] = dict(brand_row)
    metadata["corporate_sponsor_organization_eid"] = int(brand_row["organization_eid"])
    metadata["corporate_campaign_kind"] = brand_row.get("campaign_kind")
    metadata["corporate_ad_copy"] = brand_row.get("ad_copy")
    metadata["display_description"] = (
        f"{_text(prop.get('name')) or 'The fixture'} is wrapped in "
        f"{brand_row.get('brand', 'corporate')} {brand_row.get('motif', 'house-mark')} advertising. "
        f"{brand_row.get('ad_copy', '')}"
    ).strip()
    cue = (
        f"{brand_row.get('brand', 'Corporate')} colors repeat across public fixtures; "
        f"this one carries the {brand_row.get('motif', 'house')} mark"
    )
    record_organization_pressure(
        sim,
        organization_eid=int(brand_row["organization_eid"]),
        pressure_kind=f"corporate_{brand_row.get('tier_key', 'advertising')}",
        stance="transactional",
        reason_tags=("corporate_presence", brand_row.get("tier_key"), brand_row.get("campaign_kind"), "advertising"),
        anchor_property_id=_text(prop.get("id")),
        visible=True,
        visible_cue=cue,
        confidence=min(0.95, 0.52 + (int(brand_row.get("tier", 1)) * 0.1)),
        source_event="corporate_neighborhood_presence",
        expires_tick=0,
        pressure_key=f"corporate_presence:{brand_row['organization_eid']}:{chunk[0]}:{chunk[1]}:{prop.get('id')}",
    )
    return True


def _materialize_branding(sim, row):
    chunk = tuple(row.get("chunk", ()))
    if len(chunk) != 2:
        return ()
    corporate_org_eid = _safe_int(row.get("corporate_org_eid"), 0)
    tier = _safe_int(row.get("tier"), 0)
    if corporate_org_eid <= 0 or tier <= 0:
        return ()
    brand_row = _brand_row(
        sim,
        corporate_org_eid,
        tier=tier,
        tier_key=row.get("tier_key"),
        tier_label=row.get("tier_label"),
        campaign_kind=row.get("campaign_kind"),
    )
    for property_id in tuple(row.get("anchor_property_ids", ()) or ()):
        prop = getattr(sim, "properties", {}).get(property_id)
        if isinstance(prop, dict):
            _stamp_anchor_branding(prop, brand_row)

    target_count = {1: 0, 2: 1, 3: 3, 4: 5}.get(tier, 0)
    if target_count <= 0:
        return ()
    candidates = []
    for prop in getattr(sim, "properties", {}).values():
        if _property_chunk(sim, prop) != chunk or not _fixture_is_brandable(prop):
            continue
        existing = _metadata(prop).get("corporate_branding")
        if isinstance(existing, dict) and _safe_int(existing.get("organization_eid"), 0) not in {0, corporate_org_eid}:
            continue
        candidates.append(prop)
    candidates.sort(key=lambda prop: (_fixture_brand_rank(sim, prop, corporate_org_eid, chunk), _text(prop.get("id"))))
    branded = []
    for prop in candidates[:target_count]:
        if _stamp_fixture_branding(sim, prop, brand_row, chunk=chunk):
            branded.append(_text(prop.get("id")))
    return tuple(branded)


def refresh_corporate_neighborhood_presence(sim, corporate_org_eid, chunk, *, materialize=True):
    """Rebuild one corporation's durable footprint in a loaded neighborhood."""

    corporate_org_eid = _corporate_root(sim, corporate_org_eid)
    if corporate_org_eid is None or not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return None
    chunk = (int(chunk[0]), int(chunk[1]))
    anchors = []
    score = 0.0
    action_kinds = set()
    for prop in getattr(sim, "properties", {}).values():
        if _property_chunk(sim, prop) != chunk:
            continue
        weight = _anchor_weight(sim, prop, corporate_org_eid)
        if weight <= 0.0:
            continue
        property_id = _text(prop.get("id"))
        anchors.append(property_id)
        score += weight
        acquisition = _metadata(prop).get("corporate_acquisition")
        if isinstance(acquisition, dict):
            action_kind = _key(acquisition.get("action_kind"))
            if action_kind:
                action_kinds.add(action_kind)

    tier, tier_key, tier_label = _tier_for_score(score)
    state = ensure_corporate_presence_state(sim)
    key = _neighborhood_key(corporate_org_eid, chunk)
    previous = state["neighborhoods"].get(key)
    previous = dict(previous) if isinstance(previous, dict) else {}
    profile = organization_profile(sim, corporate_org_eid)
    campaign_kind = _campaign_kind(sim, corporate_org_eid)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    row = {
        "presence_key": key,
        "corporate_org_eid": int(corporate_org_eid),
        "corporate_org_key": _text(getattr(profile, "key", "")) if profile is not None else "",
        "corporate_org_name": _text(getattr(profile, "name", "")) if profile is not None else "Corporate organization",
        "chunk": chunk,
        "score": round(float(score), 3),
        "tier": int(tier),
        "tier_key": tier_key,
        "tier_label": tier_label,
        "campaign_kind": campaign_kind,
        "anchor_property_ids": tuple(sorted(set(anchors))),
        "action_kinds": tuple(sorted(action_kinds)),
        "branded_fixture_ids": tuple(previous.get("branded_fixture_ids", ()) or ()),
        "created_tick": _safe_int(previous.get("created_tick"), now),
        "last_update_tick": now,
        "active": bool(tier > 0),
    }
    state["neighborhoods"][key] = row
    if materialize and tier > 0:
        row["branded_fixture_ids"] = _materialize_branding(sim, row)
        state["neighborhoods"][key] = row

    previous_tier = _safe_int(previous.get("tier"), 0)
    if tier > previous_tier:
        identity = organization_manufacturing_identity(sim, corporate_org_eid)
        sim.emit(
            Event(
                "corporate_neighborhood_presence_changed",
                organization_eid=int(corporate_org_eid),
                organization_name=row["corporate_org_name"],
                brand=identity.get("manufacturer") or row["corporate_org_name"],
                chunk=chunk,
                old_tier=previous_tier,
                tier=int(tier),
                tier_key=tier_key,
                tier_label=tier_label,
                campaign_kind=campaign_kind,
                anchor_property_ids=row["anchor_property_ids"],
                branded_fixture_ids=row["branded_fixture_ids"],
            )
        )
    return dict(row)


def refresh_all_corporate_neighborhood_presence(sim, *, materialize=True):
    """Refresh loaded corporate/chunk pairs without an organization x property scan."""

    pairs = set()
    for prop in getattr(sim, "properties", {}).values():
        chunk = _property_chunk(sim, prop)
        if chunk is None:
            continue
        corporate_org_eid = corporate_organization_for_property(sim, prop)
        if corporate_org_eid is not None:
            pairs.add((int(corporate_org_eid), tuple(chunk)))
    rows = []
    for corporate_org_eid, chunk in sorted(pairs, key=lambda row: (row[1], row[0])):
        refreshed = refresh_corporate_neighborhood_presence(
            sim,
            corporate_org_eid,
            chunk,
            materialize=materialize,
        )
        if refreshed:
            rows.append(refreshed)
    return tuple(rows)


def corporate_neighborhood_presence_rows(sim, *, corporate_org_eid=None, chunk=None, active_only=True):
    state = ensure_corporate_presence_state(sim)
    wanted_root = _corporate_root(sim, corporate_org_eid) if corporate_org_eid is not None else None
    wanted_chunk = tuple(chunk) if isinstance(chunk, (tuple, list)) and len(chunk) >= 2 else None
    rows = []
    for raw in state.get("neighborhoods", {}).values():
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        if active_only and not bool(row.get("active", True)):
            continue
        if wanted_root is not None and _safe_int(row.get("corporate_org_eid"), 0) != int(wanted_root):
            continue
        if wanted_chunk is not None and tuple(row.get("chunk", ())) != wanted_chunk:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (-_safe_int(row.get("tier"), 0), -_safe_float(row.get("score"), 0.0), _text(row.get("corporate_org_name")).lower()))
    return tuple(rows)


def corporate_neighborhood_presence_for_property(sim, prop):
    if not isinstance(prop, dict):
        return None
    metadata = _metadata(prop)
    branding = metadata.get("corporate_branding")
    corporate_org_eid = _safe_int((branding or {}).get("organization_eid"), 0) if isinstance(branding, dict) else 0
    if corporate_org_eid <= 0:
        corporate_org_eid = corporate_organization_for_property(sim, prop) or 0
    chunk = _property_chunk(sim, prop)
    rows = corporate_neighborhood_presence_rows(
        sim,
        corporate_org_eid=corporate_org_eid or None,
        chunk=chunk,
        active_only=True,
    )
    return dict(rows[0]) if rows else None


def _item_specialty_fit(item_id, item_def, specialties):
    item_id = _key(item_id)
    item_def = item_def if isinstance(item_def, dict) else {}
    tags = {_key(tag) for tag in item_def.get("tags", ()) or () if _key(tag)}
    category = _key(item_def.get("category"))
    if tags.intersection(CORPORATE_PRODUCT_EXCLUDED_TAGS):
        return "", tags
    specialties = {_key(value) for value in specialties or () if _key(value)}
    checks = (
        ("wire_gear", bool(tags.intersection({"wire", "wire_gear", "wire_software", "interface"})) or item_id.startswith("wire_")),
        ("drone_frames", "drone" in tags or category == "drone_part" or item_id.startswith("drone_")),
        ("power_systems", bool(tags.intersection({"battery", "energy", "electrical", "power"})) or "battery" in item_id),
        ("consumer_electronics", bool(tags.intersection({"phone", "radio", "communication", "comms", "electronic"}))),
        ("security_systems", bool(tags.intersection({"weapon", "armor", "security", "intrusion", "surveillance"})) or category in {"weapon", "armor"}),
    )
    for specialty, matched in checks:
        if specialty in specialties and matched:
            return specialty, tags
    return "", tags


def _quality_shift(quality, shift):
    tiers = ("poor", "rough", "standard", "good", "excellent")
    quality = _key(quality) or "standard"
    index = tiers.index(quality) if quality in tiers else 2
    return tiers[max(0, min(len(tiers) - 1, index + int(shift)))]


def corporate_branded_item_metadata(sim, prop, item_id, base_metadata, *, seed_token=""):
    """Stamp one eligible shelf item with corporate identity and real tendencies."""

    from game.items import ITEM_CATALOG, item_condition_profile, item_display_name

    metadata = dict(base_metadata or {})
    if metadata.get("manufacturer_organization_eid") or metadata.get("corporate_product_signature"):
        return metadata
    corporate_org_eid = corporate_organization_for_property(sim, prop)
    if corporate_org_eid is None:
        return metadata
    production = organization_production_profile(sim, corporate_org_eid, include_hidden=True)
    manufacturing = dict(production.get("manufacturing") or {})
    specialty, tags = _item_specialty_fit(item_id, ITEM_CATALOG.get(item_id), manufacturing.get("specialties", ()))
    if not specialty:
        return metadata

    presence = corporate_neighborhood_presence_for_property(sim, prop) or {}
    tier = max(1, _safe_int(presence.get("tier"), 1))
    links = _links_for_corporation(sim, prop, corporate_org_eid)
    primary = any(bool(link.get("primary")) and _key(link.get("link_kind")) == "operates" for link in links)
    chance = {1: 0.52, 2: 0.68, 3: 0.82, 4: 0.94}.get(tier, 0.52) + (0.12 if primary else 0.0)
    rng = random.Random(
        _hash_int(
            getattr(sim, "seed", 0),
            seed_token,
            corporate_org_eid,
            item_id,
            "corporate-product",
        )
    )
    if rng.random() > min(0.98, chance):
        return metadata

    identity = organization_manufacturing_identity(sim, corporate_org_eid)
    modifiers = organization_manufacturing_modifiers(sim, corporate_org_eid)
    relevant_axis = {
        "wire_gear": "signal_integrity",
        "drone_frames": "durability",
        "power_systems": "power_efficiency",
        "consumer_electronics": "signal_integrity",
        "security_systems": "durability",
    }.get(specialty, "quality_bias")
    quality_score = _safe_int(modifiers.get("quality_bias"), 0) + (0.5 * _safe_int(modifiers.get(relevant_axis), 0))
    quality_shift = 1 if quality_score >= 1.75 else -1 if quality_score <= -1.75 else 0
    if quality_shift:
        metadata["item_quality"] = _quality_shift(metadata.get("item_quality"), quality_shift)

    condition = item_condition_profile(item_id, item_catalog=ITEM_CATALOG)
    durability_axis = _safe_int(modifiers.get("durability"), 0)
    if condition.get("supports_durability"):
        base_max = _safe_int(metadata.get("item_max_durability"), _safe_int(condition.get("max_durability"), 1))
        adjusted_max = max(1, base_max + durability_axis)
        metadata["item_max_durability"] = adjusted_max
        metadata["item_durability"] = adjusted_max

    quality_axis = _safe_int(modifiers.get("quality_bias"), 0)
    consistency_axis = _safe_int(modifiers.get("consistency"), 0)
    relevant_value = _safe_int(modifiers.get(relevant_axis), 0)
    effect_scalar = _clamp(1.0 + (quality_axis * 0.035) + (relevant_value * 0.025), 0.78, 1.24)
    if tags.intersection({"consumable", "medical", "stimulant", "food", "drink"}):
        metadata["item_positive_effect_scalar"] = round(effect_scalar, 3)
        metadata["item_negative_effect_scalar"] = round(
            _clamp(1.0 - (consistency_axis * 0.035) - (quality_axis * 0.015), 0.78, 1.3),
            3,
        )
    if "tool" in tags or specialty in {"power_systems", "security_systems"}:
        repairability = _safe_int(modifiers.get("repairability"), 0)
        metadata["tool_wear_mult"] = round(_clamp(1.0 - (repairability * 0.06) - (durability_axis * 0.035), 0.68, 1.42), 3)
    if tags.intersection({"intrusion", "surveillance"}):
        concealment = _safe_int(modifiers.get("concealment"), 0)
        metadata["tamper_severity_mult"] = round(_clamp(1.0 - (concealment * 0.06), 0.72, 1.34), 3)

    manufacturer = _text(identity.get("manufacturer")) or _text(identity.get("organization_name")) or "Corporate"
    base_name = item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG)
    if not base_name.lower().startswith(manufacturer.lower()):
        metadata["display_name"] = f"{manufacturer} {base_name}"
    metadata.update(
        {
            "manufacturer": manufacturer,
            "manufacturer_organization_eid": int(corporate_org_eid),
            "manufacturer_organization_key": _text(identity.get("organization_key")),
            "manufacturer_organization_name": _text(identity.get("organization_name")),
            "manufacturing_signature": _text(identity.get("manufacturing_signature")),
            "corporate_product_signature": f"corp-product:{corporate_org_eid}:{identity.get('manufacturing_signature')}:{_key(item_id)}",
            "corporate_product_specialty": specialty,
            "corporate_product_tier": int(tier),
            "product_motif": _text(identity.get("product_motif")),
            "product_geometry": _text(identity.get("product_geometry")),
            "product_finish": _text(identity.get("product_finish")),
            "product_color_word": _text(identity.get("primary_color_word")),
        }
    )
    return metadata


__all__ = [
    "CORPORATE_BRANDABLE_FIXTURES",
    "CORPORATE_FOOTPRINT_TIERS",
    "CORPORATE_PRESENCE_SCHEMA_VERSION",
    "corporate_branded_item_metadata",
    "corporate_neighborhood_presence_for_property",
    "corporate_neighborhood_presence_rows",
    "corporate_organization_for_property",
    "ensure_corporate_presence_state",
    "refresh_all_corporate_neighborhood_presence",
    "refresh_corporate_neighborhood_presence",
]
