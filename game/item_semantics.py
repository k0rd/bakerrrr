"""Item semantic helpers for canonical item truth vs actor-facing interpretation.

This layer keeps "what the item really is" separate from "what this actor
currently knows about it". The first slice focuses on run-randomized
appearances for identifiable item families and actor-side identification /
appraisal state.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Iterable, Mapping

from engine.events import Event

from game.components import ItemKnowledge
from game.items import ITEM_CATALOG, item_display_name, item_instance_condition


LEGAL_STATUSES = {"legal", "restricted", "suspicious", "illegal", "stolen", "unknown"}
PHONE_TAGS = {"phone", "cellular", "communication", "radio", "comms"}
PHONE_ITEM_IDS = {"mobile_phone", "burner_phone", "unregistered_mobile_phone", "cell_phone", "phone", "radio", "walkie_talkie", "two_way_radio"}

_APPEARANCE_SLOT_VALUES = {
    "color": (
        "amber",
        "ashen",
        "cobalt",
        "crimson",
        "ivory",
        "jade",
        "obsidian",
        "olive",
        "saffron",
        "teal",
        "violet",
        "white",
    ),
    "symbol": (
        "triangle",
        "circle",
        "square",
        "chevron",
        "diamond",
        "bar",
        "dot",
        "star",
        "cross",
        "wave",
    ),
    "marking": (
        "banded",
        "bar-marked",
        "chevron-marked",
        "crosshatched",
        "dotted",
        "grid-marked",
        "notched",
        "ring-marked",
        "spiral-marked",
        "striped",
    ),
    "liquid_color": (
        "amber",
        "black",
        "blue",
        "clear",
        "green",
        "red",
        "smoke-gray",
        "teal",
        "violet",
        "yellow",
    ),
}

_FAMILY_APPEARANCE_PROFILES = {
    "ammo": {
        "default_slots": ("color", "marking"),
        "observation_template": "{package} with {color} coloring and {marking} markings",
    },
    "medical": {
        "default_slots": ("color", "symbol"),
        "observation_template": "{form} with a {symbol} symbol and {color} markings",
    },
    "injectable": {
        "default_slots": ("symbol", "liquid_color"),
        "observation_template": "injectable with a {symbol} symbol, contains {liquid_color} liquid",
    },
    "drug": {
        "default_slots": ("color", "symbol"),
        "observation_template": "{form} with {color} labeling and a {symbol} stamp",
    },
}


def _key(value) -> str:
    return str(value or "").strip().lower()


def _entry_item_id(item_or_entry) -> str:
    if isinstance(item_or_entry, Mapping):
        return _key(item_or_entry.get("item_id") or item_or_entry.get("id"))
    return _key(item_or_entry)


def _entry_metadata(item_or_entry) -> dict:
    if isinstance(item_or_entry, Mapping) and isinstance(item_or_entry.get("metadata"), Mapping):
        return dict(item_or_entry.get("metadata") or {})
    return {}


def _entry_quantity(item_or_entry) -> int:
    if isinstance(item_or_entry, Mapping):
        try:
            return max(1, int(item_or_entry.get("quantity", 1)))
        except (TypeError, ValueError):
            return 1
    return 1


def _entry_instance_id(item_or_entry) -> str:
    if isinstance(item_or_entry, Mapping):
        return str(item_or_entry.get("instance_id", "") or "").strip()
    return ""


def _family_profile(family) -> dict:
    return dict(_FAMILY_APPEARANCE_PROFILES.get(_key(family), {}) or {})


def _symbol_mark(symbol) -> str:
    token = str(symbol or "").strip().lower()
    if not token:
        return "marked"
    return f"{token}-marked"


def _ammo_package_label(item_id, item_def) -> str:
    item_text = _key(item_id)
    name_text = _key(item_def.get("name"))
    if "bandolier" in item_text or "bandolier" in name_text:
        return "bandolier"
    if "crate" in item_text or "crate" in name_text:
        return "ammo crate"
    if "tube" in item_text or "tube" in name_text:
        return "tube pack"
    if "box" in item_text or "box" in name_text:
        return "ammo box"
    return "ammo pack"


def _medical_form_label(item_id, item_def) -> str:
    item_text = _key(item_id)
    name_text = _key(item_def.get("name"))
    if "joint" in item_text or "joint" in name_text or "smoke" in item_text:
        return "rolled smoke"
    if "blotter" in item_text or "blotter" in name_text:
        return "blotter tab"
    if "bindle" in item_text or "bindle" in name_text or "powder" in name_text:
        return "powder bindle"
    if "capsule" in item_text or "capsule" in name_text:
        return "capsule"
    if "patch" in item_text or "patch" in name_text:
        return "patch packet"
    if "gel" in item_text or "gel" in name_text:
        return "gel tube"
    if "salts" in item_text or "salts" in name_text:
        return "powder sachet"
    if "vial" in item_text or "vial" in name_text or "serum" in item_text:
        return "vial"
    if "syringe" in item_text or "syringe" in name_text:
        return "syringe"
    if "medkit" in item_text or "medkit" in name_text:
        return "med kit"
    if "foam" in item_text or "foam" in name_text:
        return "foam canister"
    if "bandage" in item_text or "bandage" in name_text:
        return "bandage roll"
    if "dressing" in item_text or "dressing" in name_text:
        return "field dressing"
    if "blocker" in item_text or "blocker" in name_text or "tab" in item_text or "tab" in name_text:
        return "tablet sleeve"
    if "inhaler" in item_text or "inhaler" in name_text:
        return "inhaler"
    if "stim" in item_text:
        return "stimulant packet"
    return "medical pack"


def _drug_form_label(item_id, item_def) -> str:
    item_text = _key(item_id)
    name_text = _key(item_def.get("name"))
    if "joint" in item_text or "joint" in name_text or "smoke" in item_text:
        return "rolled smoke"
    if "blotter" in item_text or "blotter" in name_text:
        return "blotter tab"
    if "bindle" in item_text or "bindle" in name_text or "powder" in name_text:
        return "powder bindle"
    if "capsule" in item_text or "capsule" in name_text:
        return "capsule"
    if "tablet" in item_text or "tablet" in name_text or "tabs" in item_text:
        return "tablet sleeve"
    if "patch" in item_text or "patch" in name_text:
        return "patch packet"
    if "syringe" in item_text or "syringe" in name_text:
        return "syringe"
    if "vial" in item_text or "vial" in name_text or "serum" in item_text:
        return "vial"
    if "stim" in item_text:
        return "stimulant packet"
    return "drug packet"


def _fixed_family_traits(item_id, item_def, family) -> dict:
    family_key = _key(family)
    if family_key == "ammo":
        return {"package": _ammo_package_label(item_id, item_def)}
    if family_key == "medical":
        return {"form": _medical_form_label(item_id, item_def)}
    if family_key == "drug":
        return {"form": _drug_form_label(item_id, item_def)}
    return {}


def _appearance_state(sim, item_catalog=None) -> dict:
    catalog = item_catalog or ITEM_CATALOG
    seed = getattr(sim, "seed", 0)
    marker = (id(catalog), len(catalog))
    current = getattr(sim, "item_appearance_state", None)
    if isinstance(current, dict) and current.get("seed") == seed and current.get("catalog_marker") == marker:
        return current

    assignments = {}
    by_family = {}
    for item_id, item_def in catalog.items():
        profile = item_identification_profile(item_id, item_catalog=catalog)
        family = _key(profile.get("family"))
        if not profile.get("requires_identification") or family not in _FAMILY_APPEARANCE_PROFILES:
            continue
        by_family.setdefault(family, []).append(item_id)

    for family, item_ids in by_family.items():
        family_profile = _family_profile(family)
        slot_names = tuple(
            slot
            for slot in item_appearance_slots(item_ids[0], item_catalog=catalog) or family_profile.get("default_slots", ())
            if slot in _APPEARANCE_SLOT_VALUES
        )
        combos = [
            dict(zip(slot_names, values))
            for values in itertools.product(*(_APPEARANCE_SLOT_VALUES[slot] for slot in slot_names))
        ] or [{}]
        rng = random.Random(f"{seed}:item-appearance:{family}")
        rng.shuffle(combos)
        for idx, item_id in enumerate(sorted(item_ids)):
            item_def = dict(catalog.get(item_id, {}) or {})
            trait_map = dict(combos[idx % len(combos)])
            trait_map.update(_fixed_family_traits(item_id, item_def, family))
            trait_map["family"] = family
            assignments[item_id] = trait_map

    current = {
        "seed": seed,
        "catalog_marker": marker,
        "assignments": assignments,
    }
    sim.item_appearance_state = current
    return current


def _appearance_traits(sim, item_or_entry, item_catalog=None) -> dict:
    item_id = _entry_item_id(item_or_entry)
    state = _appearance_state(sim, item_catalog=item_catalog)
    return dict(state.get("assignments", {}).get(item_id, {}) or {})


def _knowledge_for_actor(sim, actor_eid, *, create=False):
    if actor_eid is None or not hasattr(sim, "ecs"):
        return None
    knowledge_store = sim.ecs.get(ItemKnowledge)
    knowledge = knowledge_store.get(actor_eid)
    if knowledge is None and create:
        knowledge = ItemKnowledge()
        sim.ecs.add(actor_eid, knowledge)
    return knowledge


def item_def(item_or_entry, item_catalog=None) -> dict:
    catalog = item_catalog or ITEM_CATALOG
    return dict(catalog.get(_entry_item_id(item_or_entry), {}) or {})


def item_tags(item_or_entry, item_catalog=None) -> set[str]:
    raw = item_def(item_or_entry, item_catalog=item_catalog).get("tags", ())
    return {_key(tag) for tag in raw if _key(tag)}


def has_item_tag(item_or_entry, tags, item_catalog=None) -> bool:
    wanted = {_key(tag) for tag in (tags if isinstance(tags, Iterable) and not isinstance(tags, str) else (tags,)) if _key(tag)}
    return bool(wanted and item_tags(item_or_entry, item_catalog=item_catalog).intersection(wanted))


def item_category(item_or_entry, item_catalog=None) -> str:
    return _key(item_def(item_or_entry, item_catalog=item_catalog).get("category")) or "misc"


def item_legal_status(item_or_entry, item_catalog=None) -> str:
    status = _key(_entry_metadata(item_or_entry).get("legal_status")) or _key(item_def(item_or_entry, item_catalog=item_catalog).get("legal_status"))
    return status if status in LEGAL_STATUSES else "unknown"


def item_appearance_family(item_or_entry, item_catalog=None) -> str:
    return _key(item_def(item_or_entry, item_catalog=item_catalog).get("appearance_family"))


def item_appearance_slots(item_or_entry, item_catalog=None) -> tuple[str, ...]:
    raw = item_def(item_or_entry, item_catalog=item_catalog).get("appearance_slots", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(_key(slot) for slot in raw if _key(slot))


def item_runtime_property(item_or_entry, key, default=None):
    metadata = _entry_metadata(item_or_entry)
    return metadata.get(str(key), default)


def item_identification_profile(item_or_entry, item_catalog=None) -> dict:
    item_details = item_def(item_or_entry, item_catalog=item_catalog)
    profile = item_details.get("identification_profile")
    if not isinstance(profile, Mapping):
        profile = {}
    family = _key(profile.get("family")) or item_appearance_family(item_or_entry, item_catalog=item_catalog)
    return {
        "family": family,
        "requires_identification": bool(profile.get("requires_identification", False)),
        "auto_identify_on_use": bool(profile.get("auto_identify_on_use", False)),
        "appraisal_fields": tuple(
            _key(field)
            for field in profile.get("appraisal_fields", ())
            if _key(field)
        ),
    }


def item_requires_identification(item_or_entry, item_catalog=None) -> bool:
    return bool(item_identification_profile(item_or_entry, item_catalog=item_catalog).get("requires_identification", False))


def item_is_identified_for_actor(sim, actor_eid, item_or_entry, *, item_catalog=None) -> bool:
    if not item_requires_identification(item_or_entry, item_catalog=item_catalog):
        return True
    knowledge = _knowledge_for_actor(sim, actor_eid, create=False)
    if knowledge is None:
        return False
    return bool(knowledge.is_identified(_entry_item_id(item_or_entry)))


def identify_item_for_actor(sim, actor_eid, item_or_entry, *, source_kind="direct", tick=None, item_catalog=None) -> bool:
    if actor_eid is None or not item_requires_identification(item_or_entry, item_catalog=item_catalog):
        return False
    knowledge = _knowledge_for_actor(sim, actor_eid, create=True)
    item_id = _entry_item_id(item_or_entry)
    learned_tick = int(getattr(sim, "tick", 0) if tick is None else tick)
    was_new = knowledge.identify(
        item_id,
        tick=learned_tick,
        source_kind=source_kind,
    )
    if was_new and hasattr(sim, "emit"):
        sim.emit(Event(
            "item_identified",
            eid=actor_eid,
            item_id=item_id,
            item_name=item_display_name(item_id, metadata=_entry_metadata(item_or_entry), item_catalog=item_catalog or ITEM_CATALOG),
            source_kind=str(source_kind or "direct").strip().lower() or "direct",
        ))
    return was_new


def appraise_item_for_actor(sim, actor_eid, item_or_entry, *, tick=None, item_catalog=None) -> tuple[str, ...]:
    if actor_eid is None:
        return ()
    instance_id = _entry_instance_id(item_or_entry)
    if not instance_id:
        return ()
    knowledge = _knowledge_for_actor(sim, actor_eid, create=True)
    metadata = _entry_metadata(item_or_entry)
    profile = item_identification_profile(item_or_entry, item_catalog=item_catalog)
    condition = item_instance_condition(
        _entry_item_id(item_or_entry),
        metadata=metadata,
        item_catalog=item_catalog or ITEM_CATALOG,
    )
    condition_profile = condition.get("profile", {}) if isinstance(condition.get("profile"), dict) else {}
    wanted = tuple(profile.get("appraisal_fields", ()))
    if not wanted:
        wanted = ("item_quality", "item_durability", "item_max_durability")
    revealed = []
    for field in wanted:
        token = _key(field)
        if token == "item_quality":
            if token in metadata or condition_profile.get("supports_quality"):
                revealed.append(token)
            continue
        if token in {"item_durability", "item_max_durability"}:
            if token in metadata or condition_profile.get("supports_durability"):
                revealed.append(token)
            continue
        if token in metadata:
            revealed.append(token)
    if not revealed:
        return ()
    learned_tick = int(getattr(sim, "tick", 0) if tick is None else tick)
    knowledge.appraise(
        instance_id,
        item_id=_entry_item_id(item_or_entry),
        tick=learned_tick,
        detail_keys=revealed,
    )
    if hasattr(sim, "emit"):
        sim.emit(Event(
            "item_appraised",
            eid=actor_eid,
            item_id=_entry_item_id(item_or_entry),
            instance_id=instance_id,
            detail_keys=tuple(sorted(set(revealed))),
        ))
    return tuple(sorted(set(revealed)))


def item_is_appraised_for_actor(sim, actor_eid, item_or_entry, detail_key=None) -> bool:
    knowledge = _knowledge_for_actor(sim, actor_eid, create=False)
    if knowledge is None:
        return False
    instance_id = _entry_instance_id(item_or_entry)
    if not instance_id:
        return False
    return bool(knowledge.knows_appraisal(instance_id, detail_key=detail_key))


def item_observation_summary_for_actor(sim, actor_eid, item_or_entry, *, item_catalog=None) -> str:
    del actor_eid
    profile = item_identification_profile(item_or_entry, item_catalog=item_catalog)
    family = _key(profile.get("family"))
    family_profile = _family_profile(family)
    if not family_profile:
        return ""
    traits = _appearance_traits(sim, item_or_entry, item_catalog=item_catalog)
    template = str(family_profile.get("observation_template", "") or "").strip()
    if not template:
        return ""
    try:
        return template.format(**traits)
    except KeyError:
        return ""


def item_unknown_name_for_actor(sim, actor_eid, item_or_entry, *, item_catalog=None) -> str:
    del actor_eid
    metadata = _entry_metadata(item_or_entry)
    custom = str(metadata.get("perceived_name", "") or "").strip()
    if custom:
        return custom
    traits = _appearance_traits(sim, item_or_entry, item_catalog=item_catalog)
    family = _key(traits.get("family")) or item_appearance_family(item_or_entry, item_catalog=item_catalog)
    if family == "injectable":
        return f"{traits.get('liquid_color', 'unknown')} {_symbol_mark(traits.get('symbol'))} injectable".strip()
    if family == "medical":
        return f"{traits.get('color', 'unknown')} {_symbol_mark(traits.get('symbol'))} {traits.get('form', 'medical pack')}".strip()
    if family == "drug":
        return f"{traits.get('color', 'unknown')} {_symbol_mark(traits.get('symbol'))} {traits.get('form', 'drug packet')}".strip()
    if family == "ammo":
        return f"{traits.get('color', 'unknown')} {traits.get('marking', 'marked')} {traits.get('package', 'ammo pack')}".strip()
    return "unidentified item"


def item_appraisal_summary_for_actor(sim, actor_eid, item_or_entry, *, item_catalog=None) -> str:
    metadata = _entry_metadata(item_or_entry)
    condition = item_instance_condition(
        _entry_item_id(item_or_entry),
        metadata=metadata,
        item_catalog=item_catalog or ITEM_CATALOG,
    )
    condition_profile = condition.get("profile", {}) if isinstance(condition.get("profile"), dict) else {}
    details = []
    if (
        item_is_appraised_for_actor(sim, actor_eid, item_or_entry, "item_quality")
        and (condition_profile.get("supports_quality") or "item_quality" in metadata)
    ):
        quality = _key(metadata.get("item_quality")) or "standard"
        details.append(f"quality {quality}")
    if (
        item_is_appraised_for_actor(sim, actor_eid, item_or_entry, "item_durability")
        or item_is_appraised_for_actor(sim, actor_eid, item_or_entry, "item_max_durability")
    ):
        if condition.get("profile", {}).get("supports_durability") and int(condition.get("max_durability", 0) or 0) > 0:
            details.append(
                f"condition {int(condition.get('durability', 0) or 0)}/{int(condition.get('max_durability', 0) or 0)}"
            )
    return ", ".join(details)


def item_unknown_inspect_text_for_actor(sim, actor_eid, item_or_entry, *, item_catalog=None) -> str:
    name = item_display_name_for_actor(sim, actor_eid, item_or_entry, item_catalog=item_catalog)
    quantity = _entry_quantity(item_or_entry)
    observation = item_observation_summary_for_actor(sim, actor_eid, item_or_entry, item_catalog=item_catalog)
    appraisal = item_appraisal_summary_for_actor(sim, actor_eid, item_or_entry, item_catalog=item_catalog)
    bits = [bit for bit in (observation, appraisal) if str(bit).strip()]
    detail_text = "; ".join(bits) if bits else "identity unknown"
    return f"{name} x{quantity} [identity unknown] - {detail_text}"


def _herbal_trait_label_for_actor(sim, actor_eid, item_or_entry) -> str:
    item_id = _entry_item_id(item_or_entry)
    metadata = _entry_metadata(item_or_entry)
    if item_id not in {"fresh_blossoms", "leaf_clippings", "moss_scrapings", "vine_cuttings"}:
        return ""
    plant_id = _key(metadata.get("source_plant_id"))
    class_id = _key(metadata.get("chemistry_class"))
    if not plant_id or not class_id:
        return ""
    state = getattr(sim, "herbal_known_plant_traits", None)
    if not isinstance(state, dict):
        return ""
    try:
        actor_key = str(int(actor_eid))
    except (TypeError, ValueError):
        actor_key = str(actor_eid or "").strip()
    actor_rows = state.get(actor_key, {})
    if not isinstance(actor_rows, dict) or plant_id not in actor_rows:
        return ""
    row = actor_rows.get(plant_id, {})
    if isinstance(row, dict):
        class_id = _key(row.get("chemistry_class")) or class_id
    return class_id.replace("_", " ")


def item_display_name_for_actor(sim, actor_eid, item_or_entry, *, identified=None, item_catalog=None) -> str:
    """Return what an actor should call an item."""
    item_id = _entry_item_id(item_or_entry)
    metadata = _entry_metadata(item_or_entry)
    if identified is None:
        identified = item_is_identified_for_actor(sim, actor_eid, item_or_entry, item_catalog=item_catalog)
    if item_requires_identification(item_or_entry, item_catalog=item_catalog) and not identified:
        return item_unknown_name_for_actor(sim, actor_eid, item_or_entry, item_catalog=item_catalog)
    name = item_display_name(item_id, metadata=metadata, item_catalog=item_catalog or ITEM_CATALOG)
    herbal_trait = _herbal_trait_label_for_actor(sim, actor_eid, item_or_entry)
    if herbal_trait and f"[{herbal_trait}]" not in name.lower():
        return f"{name} [{herbal_trait}]"
    return name


def is_phone_item(item_or_entry, item_catalog=None) -> bool:
    item_id = _entry_item_id(item_or_entry)
    return item_id in PHONE_ITEM_IDS or has_item_tag(item_or_entry, PHONE_TAGS, item_catalog=item_catalog)


def inventory_has_item_matching(inventory, *, tags=(), item_ids=(), item_catalog=None) -> bool:
    if not inventory:
        return False
    wanted_ids = {_key(item_id) for item_id in item_ids if _key(item_id)}
    wanted_tags = {_key(tag) for tag in tags if _key(tag)}
    for entry in getattr(inventory, "items", ()) or ():
        item_id = _entry_item_id(entry)
        if wanted_ids and item_id in wanted_ids:
            return True
        if wanted_tags and has_item_tag(entry, wanted_tags, item_catalog=item_catalog):
            return True
    return False


def inventory_has_phone(inventory, item_catalog=None) -> bool:
    return inventory_has_item_matching(inventory, tags=PHONE_TAGS, item_ids=PHONE_ITEM_IDS, item_catalog=item_catalog)
