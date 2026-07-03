"""Successful-run reward file exporter.

The exporter writes ordinary custom-content examples into ``saves/rewards`` and
records a signed first-party receipt. The exported JSON stays optional: loading
it still goes through the public custom-content validator.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

from engine.persistence import SAVE_DIR
from game.json_metadata import SCHEMA_VERSION, wrap_object_document
from game.meaningful_objects_runtime import reward_object_profile
from game.public_content import public_area_types, public_building_archetype_ids, public_district_types


RUN_REWARD_GENERATOR_VERSION = "run_rewards_v1"
RUN_REWARD_SCHEMA_VERSION = 1
RUN_REWARD_SIGNATURE_SALT = b"bakerrrr-earned-run-reward-v1"
REWARD_ROOT = SAVE_DIR / "rewards"
LEDGER_FILENAME = "earned_rewards.json"

_IDENTIFIER_RE = re.compile(r"[^a-z0-9_]+")


_ITEM_FAMILIES = (
    {
        "kind": "steady_charm",
        "label": "steady charm",
        "name_words": ("Steady", "Anchor", "Old Route", "Quiet Count"),
        "glyph": "*",
        "tags": ("consumable", "keepsake", "earned", "focus"),
        "effects": ({"type": "modify_need", "need": "safety", "delta": 14},),
    },
    {
        "kind": "runner_patch",
        "label": "runner patch",
        "name_words": ("Runner", "Back-Street", "Late Shift", "Lucky Walk"),
        "glyph": "=",
        "tags": ("consumable", "keepsake", "earned", "energy"),
        "effects": ({"type": "modify_need", "need": "energy", "delta": 12},),
    },
    {
        "kind": "pocket_ration",
        "label": "pocket ration",
        "name_words": ("Pocket", "Last Counter", "Warm Shelf", "Good-Enough"),
        "glyph": "%",
        "tags": ("consumable", "keepsake", "earned", "food"),
        "effects": ({"type": "modify_need", "need": "hunger", "delta": -16},),
    },
    {
        "kind": "rain_token",
        "label": "rain token",
        "name_words": ("Rain", "Canal", "Spare Cup", "Clear Bottle"),
        "glyph": "!",
        "tags": ("consumable", "keepsake", "earned", "drink"),
        "effects": ({"type": "modify_need", "need": "thirst", "delta": -16},),
    },
    {
        "kind": "soft_wrap",
        "label": "soft wrap",
        "name_words": ("Soft Wrap", "Field Wrap", "Clean Rag", "Little Mercy"),
        "glyph": "+",
        "tags": ("consumable", "keepsake", "earned", "medical"),
        "effects": ({"type": "restore_hp", "delta": 7},),
    },
    {
        "kind": "calling_card",
        "label": "calling card",
        "name_words": ("Calling", "Known Door", "Table Talk", "Friendly Counter"),
        "glyph": "?",
        "tags": ("consumable", "keepsake", "earned", "social"),
        "effects": ({"type": "modify_need", "need": "social", "delta": 12},),
    },
)

_ITEM_OBJECT_PROFILE_FAMILY = {
    "steady_charm": "tokens_charms",
    "runner_patch": "textiles",
    "pocket_ration": "containers",
    "rain_token": "tokens_charms",
    "soft_wrap": "medical_herbal",
    "calling_card": "paper_books",
}


_PROFILE_FAMILIES = (
    {
        "kind": "market_afterglow",
        "label_words": ("After-Hours Market", "Back-Aisle Market", "Bright Counter"),
        "area_types": ("city",),
        "district_types": ("downtown", "entertainment", "residential"),
        "population_density": "high",
        "building_density": "medium",
        "water": "low",
        "building_weights": {
            "clothing_superstore": 1.8,
            "corner_store": 1.4,
            "restaurant": 1.3,
            "arcade": 1.2,
            "salon": 1.1,
            "tattoo_parlor": 1.0,
        },
        "service_building_weights": {
            "courier_office": 1.4,
            "employment_agency": 1.2,
            "restaurant": 1.2,
        },
    },
    {
        "kind": "canal_work",
        "label_words": ("Canal Work Blocks", "Wet Freight Row", "Low Bridge"),
        "area_types": ("city", "coastal"),
        "district_types": ("industrial", "slums", "downtown"),
        "population_density": "medium",
        "building_density": "high",
        "water": "medium",
        "building_weights": {
            "warehouse": 1.7,
            "freight_depot": 1.5,
            "machine_shop": 1.3,
            "laundromat": 1.1,
            "pawn_shop": 1.1,
        },
        "service_building_weights": {
            "tool_depot": 1.5,
            "courier_office": 1.3,
            "service_station": 1.2,
        },
    },
    {
        "kind": "quiet_residential",
        "label_words": ("Quiet Porch Grid", "Warm Window Blocks", "Close Stair"),
        "area_types": ("city", "frontier"),
        "district_types": ("residential", "downtown", "corporate"),
        "population_density": "medium",
        "building_density": "medium",
        "water": "low",
        "building_weights": {
            "apartment": 1.6,
            "house": 1.4,
            "bookshop": 1.1,
            "pharmacy": 1.2,
            "barbershop": 1.1,
        },
        "service_building_weights": {
            "recruitment_office": 1.2,
            "courier_office": 1.1,
            "pharmacy": 1.2,
        },
    },
    {
        "kind": "security_shadow",
        "label_words": ("Guarded Row", "Checkpoint Weather", "Clean Badge"),
        "area_types": ("city", "frontier"),
        "district_types": ("corporate", "military", "industrial"),
        "population_density": "medium",
        "building_density": "high",
        "water": "none",
        "building_weights": {
            "checkpoint": 1.5,
            "office": 1.4,
            "bank": 1.2,
            "courthouse": 1.1,
            "data_center": 1.1,
        },
        "service_building_weights": {
            "bounty_office": 1.4,
            "contractor_office": 1.2,
            "employment_agency": 1.1,
        },
    },
    {
        "kind": "roadside_favor",
        "label_words": ("Roadside Favor", "Relay Dust", "Truck-Stop Mercy"),
        "area_types": ("frontier", "wilderness", "coastal"),
        "district_types": ("industrial", "residential", "slums"),
        "population_density": "low",
        "building_density": "low",
        "water": "low",
        "building_weights": {
            "service_station": 1.8,
            "outfitter": 1.4,
            "surplus_store": 1.3,
            "tool_depot": 1.2,
            "street_kitchen": 1.1,
        },
        "service_building_weights": {
            "courier_office": 1.4,
            "employment_agency": 1.2,
            "service_station": 1.3,
        },
    },
    {
        "kind": "night_lights",
        "label_words": ("Night Lights", "Music Block", "Cheap Sign Glow"),
        "area_types": ("city",),
        "district_types": ("entertainment", "downtown", "slums"),
        "population_density": "high",
        "building_density": "medium",
        "water": "none",
        "building_weights": {
            "tavern": 1.5,
            "casino": 1.3,
            "music_venue": 1.4,
            "karaoke_box": 1.2,
            "restaurant": 1.2,
            "arcade": 1.2,
        },
        "service_building_weights": {
            "tavern": 1.4,
            "casino": 1.2,
            "courier_office": 1.1,
        },
    },
)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean_identifier(value: str, *, fallback: str = "reward") -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = _IDENTIFIER_RE.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def _short_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()[: int(length)]


def _path_display(path: Path) -> str:
    try:
        return path.resolve().relative_to(SAVE_DIR.parent.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _json_write(path: Path, value: Any) -> str:
    data = _pretty_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha256_bytes(data)


def _text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).strip()
    return text or fallback


def _safe_facilitator_context(*sources: Any) -> dict[str, Any]:
    allowed_text = ("role", "role_id", "career", "domain", "archetype", "service", "area_type", "district_type")
    allowed_lists = ("style_tags", "tags")
    safe: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in allowed_text:
            value = _text(source.get(key))
            if value:
                safe[key] = value[:64]
        for key in allowed_lists:
            values = source.get(key)
            if not isinstance(values, (list, tuple, set)):
                continue
            clean = []
            for value in values:
                text = _clean_identifier(value)
                if text and text not in clean:
                    clean.append(text)
                if len(clean) >= 6:
                    break
            if clean:
                safe[key] = clean
    return safe


def _source_payload(sim, player_eid, event_data: dict[str, Any]) -> dict[str, Any]:
    traits = getattr(sim, "world_traits", None)
    run_end = traits.get("run_end", {}) if isinstance(traits, dict) else {}
    stats = getattr(sim, "run_epilogue_stats", None)
    player_pos = None
    if player_eid is not None:
        try:
            from game.components import Position

            pos = sim.ecs.get(Position).get(player_eid)
            if pos is not None:
                player_pos = {"x": int(pos.x), "y": int(pos.y), "z": int(getattr(pos, "z", 0))}
        except Exception:
            player_pos = None
    objective_title = _text(event_data.get("objective_title"), _text(run_end.get("objective_title"), "Run Objective"))
    payload = {
        "seed": int(getattr(sim, "seed", 0) or 0),
        "outcome": _text(event_data.get("outcome"), _text(run_end.get("outcome"), "")).lower(),
        "reason": _text(event_data.get("reason"), _text(run_end.get("reason"), "")),
        "objective_title": objective_title,
        "tick": int(event_data.get("tick", getattr(sim, "tick", 0) or 0) or 0),
        "player_eid": int(player_eid) if player_eid is not None else None,
        "player_position": player_pos,
        "stats": {
            "facts": int((stats or {}).get("facts", 0) or 0) if isinstance(stats, dict) else 0,
            "visited_chunks": int((stats or {}).get("visited_chunks", 0) or 0) if isinstance(stats, dict) else 0,
            "casino_net": int((stats or {}).get("casino_net", 0) or 0) if isinstance(stats, dict) else 0,
        },
    }
    facilitator = _safe_facilitator_context(
        event_data.get("facilitator_context"),
        run_end.get("facilitator_context") if isinstance(run_end, dict) else None,
    )
    if facilitator:
        payload["facilitator_context"] = facilitator
    return payload


def _variant_index(seed_payload: Any, count: int, *, salt: str = "") -> int:
    if count <= 0:
        return 0
    digest = _short_hash({"salt": salt, "payload": seed_payload}, 12)
    return int(digest, 16) % int(count)


def _valid_subset(values, valid_values, fallback):
    valid = {str(value) for value in valid_values}
    result = [str(value) for value in values if str(value) in valid]
    if result:
        return result
    return [str(fallback)] if str(fallback) in valid else []


def _valid_weight_map(weights: dict[str, float], valid_ids) -> dict[str, float]:
    valid = {str(value) for value in valid_ids}
    return {
        str(key): float(value)
        for key, value in sorted((weights or {}).items())
        if str(key) in valid and float(value) > 0.0
    }


def _build_item_definition(reward_id: str, source_payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    family = _ITEM_FAMILIES[_variant_index(source_payload, len(_ITEM_FAMILIES), salt="item-family")]
    word = family["name_words"][_variant_index(source_payload, len(family["name_words"]), salt="item-name")]
    objective = _clean_identifier(source_payload.get("objective_title", "run")).replace("_", " ").title()
    item_id = f"{reward_id}_keepsake"
    name = f"{word} Keepsake"
    if len(name) < 18 and objective and objective != "Run Objective":
        name = f"{word} Keepsake"
    item = {
        "name": name,
        "glyph": str(family["glyph"]),
        "stack_max": 1,
        "tags": list(family["tags"]),
        "category": "consumable",
        "legal_status": "legal",
        "object_profile": reward_object_profile(
            source_payload,
            reward_id,
            family_hint=_ITEM_OBJECT_PROFILE_FAMILY.get(str(family["kind"]), ""),
        ),
        "effects": [dict(effect) for effect in family["effects"]],
        "lead_profile": {
            "summary": f"Earned after {source_payload.get('objective_title') or 'a successful run'}.",
            "tags": ["earned_reward", str(family["kind"])],
        },
    }
    return item_id, item, str(family["label"])


def _build_world_profile(reward_id: str, source_payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    family = _PROFILE_FAMILIES[_variant_index(source_payload, len(_PROFILE_FAMILIES), salt="profile-family")]
    label_word = family["label_words"][_variant_index(source_payload, len(family["label_words"]), salt="profile-label")]
    profile_id = f"{reward_id}_area"
    valid_buildings = public_building_archetype_ids()
    profile = {
        "label": f"{label_word} Area Profile",
        "selection_weight": 1.25,
        "area_types": _valid_subset(family["area_types"], public_area_types(), "city"),
        "district_types": _valid_subset(family["district_types"], public_district_types(), "downtown"),
        "population_density": str(family["population_density"]),
        "building_density": str(family["building_density"]),
        "water": str(family["water"]),
        "building_weights": _valid_weight_map(family["building_weights"], valid_buildings),
        "service_building_weights": _valid_weight_map(family["service_building_weights"], valid_buildings),
    }
    return profile_id, profile, str(family["kind"])


def _read_ledger(ledger_path: Path) -> dict[str, Any]:
    if not ledger_path.exists():
        return {"schema_version": RUN_REWARD_SCHEMA_VERSION, "rewards": []}
    try:
        raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": RUN_REWARD_SCHEMA_VERSION, "rewards": []}
    if not isinstance(raw, dict):
        return {"schema_version": RUN_REWARD_SCHEMA_VERSION, "rewards": []}
    rewards = raw.get("rewards")
    if not isinstance(rewards, list):
        rewards = []
    return {
        "schema_version": int(raw.get("schema_version", RUN_REWARD_SCHEMA_VERSION) or RUN_REWARD_SCHEMA_VERSION),
        "rewards": [row for row in rewards if isinstance(row, dict)],
    }


def load_reward_ledger(*, export_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(export_root) if export_root is not None else REWARD_ROOT
    return _read_ledger(root / LEDGER_FILENAME)


def _receipt_signature_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(receipt)
    payload.pop("signature", None)
    return payload


def sign_reward_receipt(receipt: dict[str, Any]) -> str:
    return hmac.new(
        RUN_REWARD_SIGNATURE_SALT,
        _canonical_json_bytes(_receipt_signature_payload(receipt)),
        hashlib.sha256,
    ).hexdigest()


def _ledger_row_from_receipt(receipt: dict[str, Any], *, receipt_path: Path, readme_path: Path) -> dict[str, Any]:
    row = copy.deepcopy(receipt)
    row["receipt_path"] = _path_display(receipt_path)
    row["readme_path"] = _path_display(readme_path)
    return row


def _existing_row_for_source(ledger: dict[str, Any], source_run_id: str) -> dict[str, Any] | None:
    for row in ledger.get("rewards", ()) or ():
        if isinstance(row, dict) and str(row.get("source_run_id", "")) == str(source_run_id):
            return row
    return None


def _summary_lines(label: str, item_path: Path, profile_path: Path, receipt_path: Path, readme_path: Path) -> list[str]:
    return [
        "Generated reward files:",
        f"  {label} exported as optional custom content.",
        f"  Item: {_path_display(item_path)}",
        f"  Area profile: {_path_display(profile_path)}",
        f"  Receipt: {_path_display(receipt_path)}",
        f"  Install note: {_path_display(readme_path)}",
    ]


def _readme_text(label: str, item_path: Path, profile_path: Path, receipt_path: Path) -> str:
    return "\n".join(
        (
            f"Generated reward: {label}",
            "",
            "These files are optional. They are not enabled automatically.",
            "",
            "To try the item in a future run, copy:",
            f"  {_path_display(item_path)}",
            "to:",
            "  config/custom_content/items/",
            "",
            "To try the area profile in a future run, copy:",
            f"  {_path_display(profile_path)}",
            "to:",
            "  config/custom_content/world_profiles/",
            "",
            "The receipt proves this bundle was generated by BAKERRRR:",
            f"  {_path_display(receipt_path)}",
            "",
            "The item and area profile are normal custom-content examples. You can inspect them,",
            "edit copies for your own experiments, or leave them unused.",
            "",
        )
    )


def _result_from_row(row: dict[str, Any], *, export_root: Path) -> dict[str, Any]:
    reward_id = str(row.get("reward_id", "") or "")
    artifacts = list(row.get("artifacts", ()) or ())
    item_artifact = next((artifact for artifact in artifacts if artifact.get("domain") == "items"), {})
    profile_artifact = next((artifact for artifact in artifacts if artifact.get("domain") == "world_profiles"), {})
    item_path = export_root / str(item_artifact.get("path", f"items/{reward_id}.json"))
    profile_path = export_root / str(profile_artifact.get("path", f"world_profiles/{reward_id}.json"))
    receipt_path = export_root / "receipts" / f"{reward_id}.json"
    readme_path = Path(str(row.get("readme_path", export_root / f"{reward_id}_README.txt")))
    label = str(row.get("reward_label", reward_id.replace("_", " ").title()) or reward_id)
    return {
        "exported": False,
        "reward_id": reward_id,
        "reward_label": label,
        "files": [
            {"domain": "items", "path": str(item_path), "loaded_ids": list(item_artifact.get("loaded_ids", ()) or ())},
            {"domain": "world_profiles", "path": str(profile_path), "loaded_ids": list(profile_artifact.get("loaded_ids", ()) or ())},
        ],
        "receipt": copy.deepcopy(row),
        "receipt_path": str(receipt_path),
        "ledger_path": str(export_root / LEDGER_FILENAME),
        "readme_path": str(readme_path),
        "summary_lines": _summary_lines(label, item_path, profile_path, receipt_path, readme_path),
    }


def export_success_reward_bundle(sim, player_eid=None, event_data=None, *, export_root: Path | str | None = None) -> dict[str, Any]:
    """Export one optional reward bundle for a successful non-tutorial run.

    The caller is responsible for tutorial gating. This function still refuses
    non-success outcomes so tests and duplicate conclusion paths stay harmless.
    """

    event_data = dict(event_data or {})
    outcome = _text(event_data.get("outcome")).lower()
    if outcome != "success":
        return {"exported": False, "reason": "not_success", "summary_lines": []}
    from game.custom_content import custom_content_allows_post_game_traces, custom_content_post_game_block_lines

    if not custom_content_allows_post_game_traces(sim):
        return {
            "exported": False,
            "reason": "unreceipted_custom_content",
            "summary_lines": custom_content_post_game_block_lines(sim),
        }
    root = Path(export_root or getattr(sim, "run_reward_export_root", None) or REWARD_ROOT)
    source_payload = _source_payload(sim, player_eid, event_data)
    source_payload["outcome"] = "success"
    source_run_id = f"run_{_short_hash({'source': source_payload, 'version': RUN_REWARD_GENERATOR_VERSION}, 20)}"
    reward_id = f"earned_{_short_hash({'source_run_id': source_run_id, 'domain': 'reward_bundle'}, 16)}"

    ledger_path = root / LEDGER_FILENAME
    ledger = _read_ledger(ledger_path)
    existing = _existing_row_for_source(ledger, source_run_id)
    if existing is not None:
        return _result_from_row(existing, export_root=root)

    item_id, item_def, item_label = _build_item_definition(reward_id, source_payload)
    profile_id, profile_def, profile_kind = _build_world_profile(reward_id, source_payload)
    reward_label = f"{item_label.title()} and {profile_def['label']}"

    item_doc = wrap_object_document({item_id: item_def}, schema_version=SCHEMA_VERSION)
    profile_doc = wrap_object_document({profile_id: profile_def}, schema_version=SCHEMA_VERSION)

    item_path = root / "items" / f"{reward_id}.json"
    profile_path = root / "world_profiles" / f"{reward_id}.json"
    receipt_path = root / "receipts" / f"{reward_id}.json"
    readme_path = root / f"{reward_id}_README.txt"

    item_hash = _json_write(item_path, item_doc)
    profile_hash = _json_write(profile_path, profile_doc)

    receipt = {
        "schema_version": RUN_REWARD_SCHEMA_VERSION,
        "reward_id": reward_id,
        "reward_label": reward_label,
        "source_run_id": source_run_id,
        "generator_version": RUN_REWARD_GENERATOR_VERSION,
        "content_domain": "custom_content",
        "custom_content_schema_version": SCHEMA_VERSION,
        "reward_family": {
            "item": item_label,
            "world_profile": profile_kind,
        },
        "source": source_payload,
        "artifacts": [
            {
                "domain": "items",
                "path": f"items/{reward_id}.json",
                "loaded_ids": [item_id],
                "sha256": item_hash,
            },
            {
                "domain": "world_profiles",
                "path": f"world_profiles/{reward_id}.json",
                "loaded_ids": [profile_id],
                "sha256": profile_hash,
            },
        ],
    }
    receipt["signature"] = sign_reward_receipt(receipt)
    _json_write(receipt_path, receipt)
    readme_path.write_text(_readme_text(reward_label, item_path, profile_path, receipt_path), encoding="utf-8")

    ledger["schema_version"] = RUN_REWARD_SCHEMA_VERSION
    ledger["rewards"] = [row for row in ledger.get("rewards", ()) or () if str(row.get("source_run_id", "")) != source_run_id]
    ledger["rewards"].append(_ledger_row_from_receipt(receipt, receipt_path=receipt_path, readme_path=readme_path))
    _json_write(ledger_path, ledger)

    return {
        "exported": True,
        "reward_id": reward_id,
        "reward_label": reward_label,
        "item_id": item_id,
        "profile_id": profile_id,
        "files": [
            {"domain": "items", "path": str(item_path), "loaded_ids": [item_id]},
            {"domain": "world_profiles", "path": str(profile_path), "loaded_ids": [profile_id]},
        ],
        "receipt": copy.deepcopy(receipt),
        "receipt_path": str(receipt_path),
        "ledger_path": str(ledger_path),
        "readme_path": str(readme_path),
        "summary_lines": _summary_lines(reward_label, item_path, profile_path, receipt_path, readme_path),
    }


def verify_reward_receipt(receipt: dict[str, Any] | str | Path, *, export_root: Path | str | None = None) -> bool:
    """Return True when a receipt signature and artifact hashes still match."""

    root = Path(export_root) if export_root is not None else REWARD_ROOT
    if isinstance(receipt, (str, Path)):
        try:
            receipt = json.loads(Path(receipt).read_text(encoding="utf-8"))
        except Exception:
            return False
    if not isinstance(receipt, dict):
        return False
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            return False
        rel_path = Path(str(artifact.get("path", "") or ""))
        if rel_path.is_absolute() or ".." in rel_path.parts:
            return False
        path = root / rel_path
        if not path.exists():
            return False
        actual_hash = _sha256_bytes(path.read_bytes())
        if not hmac.compare_digest(actual_hash, str(artifact.get("sha256", "") or "")):
            return False
    signature = str(receipt.get("signature", "") or "")
    if not signature:
        return False
    return hmac.compare_digest(signature, sign_reward_receipt(receipt))
