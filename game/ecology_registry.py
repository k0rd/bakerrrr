"""Installation-local native ecology registry.

This file is intentionally separate from character saves.  A bred biological
possibility belongs to the local installation immediately and can therefore
appear in later worlds even if the originating roguelike run ends badly.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Mapping

from engine.events import Event
from engine.persistence import SAVE_DIR
from game.components import (
    AnimalGenome,
    AnimalPhysicalProfile,
    AnimalReproduction,
    AnimalSocialProfile,
    CreatureIdentity,
    EcologyProfile,
    PlayerAssets,
    Position,
    Vitality,
)
from game.fauna_genetics import animal_genome_payload
from game.flora_genetics import normalize_flora_genetics


ECOLOGY_REGISTRY_VERSION = 1
ECOLOGY_REGISTRY_JSON_PATH = SAVE_DIR / "ecology_registry.json"
ECOLOGY_REGISTRY_DB_PATH = SAVE_DIR / "ecology_registry.sqlite3"
# Public compatibility name: the canonical registry is now SQLite.  The JSON
# path remains separately named as the one-time migration source.
ECOLOGY_REGISTRY_PATH = ECOLOGY_REGISTRY_DB_PATH
FAUNA_CULL_STEP = 20
FAUNA_CULL_FEE = 25
FAUNA_VALUE_MULTIPLIERS = {
    100: 1.0,
    80: 1.15,
    60: 1.4,
    40: 2.2,
    20: 5.0,
    0: 8.0,
}


def _key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or str(fallback or "").strip().lower().replace(" ", "_").replace("-", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(inner) for inner in value]
    return str(value)


def empty_ecology_registry():
    return {
        "version": ECOLOGY_REGISTRY_VERSION,
        "flora": {},
        "fauna": {},
        "eradication_history": [],
    }


def normalize_ecology_registry(payload):
    rows = empty_ecology_registry()
    if not isinstance(payload, Mapping):
        return rows
    for domain in ("flora", "fauna"):
        source = payload.get(domain)
        if isinstance(source, Mapping):
            rows[domain] = {
                str(native_id): copy.deepcopy(dict(record))
                for native_id, record in source.items()
                if str(native_id).strip() and isinstance(record, Mapping)
            }
    history = payload.get("eradication_history")
    if isinstance(history, list):
        rows["eradication_history"] = [copy.deepcopy(dict(row)) for row in history if isinstance(row, Mapping)][-128:]
    return rows


def _is_json_registry_path(path):
    return Path(path).suffix.lower() == ".json"


def _load_json_registry(path):
    source = Path(path)
    if not source.exists():
        return empty_ecology_registry()
    try:
        return normalize_ecology_registry(json.loads(source.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return empty_ecology_registry()


def _save_json_registry(registry, path):
    target = Path(path)
    payload = normalize_ecology_registry(registry)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return target


def _connect_ecology_db(path, *, wal=True):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(target), timeout=5.0)
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute(f"PRAGMA journal_mode = {'WAL' if wal else 'DELETE'}")
    # Lineage birth is an installation-durable event. FULL still keeps these
    # tiny row transactions sub-millisecond while covering sudden power loss,
    # not merely process crashes.
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ecology_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ecology_lineages (
            domain TEXT NOT NULL,
            native_id TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY (domain, native_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ecology_eradication_history (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            record_json TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _record_json(record):
    return json.dumps(_json_safe(record), separators=(",", ":"), sort_keys=True)


def _load_sqlite_registry(path):
    source = Path(path)
    if not source.exists():
        return empty_ecology_registry()
    try:
        connection = _connect_ecology_db(source)
        try:
            registry = empty_ecology_registry()
            for domain, native_id, record_json in connection.execute(
                "SELECT domain, native_id, record_json FROM ecology_lineages"
            ):
                if domain not in {"flora", "fauna"}:
                    continue
                record = json.loads(record_json)
                if isinstance(record, Mapping):
                    registry[domain][str(native_id)] = dict(record)
            for (record_json,) in connection.execute(
                "SELECT record_json FROM ecology_eradication_history ORDER BY sequence"
            ):
                record = json.loads(record_json)
                if isinstance(record, Mapping):
                    registry["eradication_history"].append(dict(record))
            return normalize_ecology_registry(registry)
        finally:
            connection.close()
    except (OSError, sqlite3.Error, json.JSONDecodeError):
        return empty_ecology_registry()


def load_ecology_registry(path=None):
    source = Path(path) if path is not None else ECOLOGY_REGISTRY_PATH
    if _is_json_registry_path(source):
        return _load_json_registry(source)
    return _load_sqlite_registry(source)


def _replace_sqlite_registry(registry, path, *, wal=True):
    target = Path(path)
    payload = normalize_ecology_registry(registry)
    connection = _connect_ecology_db(target, wal=wal)
    try:
        with connection:
            connection.execute("DELETE FROM ecology_lineages")
            connection.execute("DELETE FROM ecology_eradication_history")
            lineage_rows = []
            for domain in ("flora", "fauna"):
                for native_id, record in payload[domain].items():
                    lineage_rows.append((domain, str(native_id), _record_json(record)))
            connection.executemany(
                "INSERT INTO ecology_lineages (domain, native_id, record_json) VALUES (?, ?, ?)",
                lineage_rows,
            )
            connection.executemany(
                "INSERT INTO ecology_eradication_history (record_json) VALUES (?)",
                [(_record_json(record),) for record in payload["eradication_history"]],
            )
            connection.execute(
                "INSERT INTO ecology_meta (key, value) VALUES ('version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(ECOLOGY_REGISTRY_VERSION),),
            )
    finally:
        connection.close()
    return target


def save_ecology_registry(registry, path=None):
    target = Path(path) if path is not None else ECOLOGY_REGISTRY_PATH
    if _is_json_registry_path(target):
        return _save_json_registry(registry, target)
    return _replace_sqlite_registry(registry, target)


def migrate_ecology_registry_json(json_path=None, db_path=None):
    """Atomically import a legacy JSON registry while retaining its source."""

    source = Path(json_path) if json_path is not None else ECOLOGY_REGISTRY_JSON_PATH
    target = Path(db_path) if db_path is not None else ECOLOGY_REGISTRY_DB_PATH
    if target.exists() or not source.exists():
        return False
    registry = _load_json_registry(source)
    temporary = target.with_suffix(target.suffix + ".migrating")
    temporary.unlink(missing_ok=True)
    try:
        _replace_sqlite_registry(registry, temporary, wal=False)
        verified = _load_sqlite_registry(temporary)
        for domain in ("flora", "fauna"):
            if set(verified[domain]) != set(registry[domain]):
                raise ValueError(f"ecology registry migration lost {domain} lineages")
        if len(verified["eradication_history"]) != len(registry["eradication_history"]):
            raise ValueError("ecology registry migration lost eradication history")
        if verified != registry:
            raise ValueError("ecology registry migration changed lineage payloads")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return True


def prime_ecology_registry(sim, *, registry_path=None):
    if sim is None:
        return empty_ecology_registry()
    path = Path(registry_path) if registry_path is not None else ECOLOGY_REGISTRY_PATH
    migrated = False
    if not _is_json_registry_path(path) and not path.exists():
        legacy_path = ECOLOGY_REGISTRY_JSON_PATH if registry_path is None else path.with_suffix(".json")
        migrated = migrate_ecology_registry_json(legacy_path, path)
        if not migrated:
            save_ecology_registry(empty_ecology_registry(), path)
    runtime = {
        "path": str(path),
        "registry": load_ecology_registry(path),
        "primed": True,
        "backend": "json" if _is_json_registry_path(path) else "sqlite",
        "migrated_from_json": bool(migrated),
        "batch_depth": 0,
        "pending_lineages": set(),
        "history_dirty": False,
        "full_sync_pending": False,
    }
    sim.ecology_registry_runtime = runtime
    _prime_native_flora_profiles(sim)
    return runtime["registry"]


def ecology_registry_for_sim(sim):
    runtime = getattr(sim, "ecology_registry_runtime", None) if sim is not None else None
    if not isinstance(runtime, dict) or not bool(runtime.get("primed")):
        return None
    registry = runtime.get("registry")
    if not isinstance(registry, dict):
        registry = empty_ecology_registry()
        runtime["registry"] = registry
    return registry


def _persist_sqlite_changes(path, registry, lineage_keys, *, history_dirty=False):
    connection = _connect_ecology_db(path)
    try:
        with connection:
            for domain, native_id in sorted(set(lineage_keys)):
                if domain not in {"flora", "fauna"}:
                    continue
                record = (registry.get(domain) or {}).get(native_id)
                if isinstance(record, Mapping):
                    connection.execute(
                        """
                        INSERT INTO ecology_lineages (domain, native_id, record_json)
                        VALUES (?, ?, ?)
                        ON CONFLICT(domain, native_id)
                        DO UPDATE SET record_json=excluded.record_json
                        """,
                        (domain, native_id, _record_json(record)),
                    )
                else:
                    connection.execute(
                        "DELETE FROM ecology_lineages WHERE domain=? AND native_id=?",
                        (domain, native_id),
                    )
            if history_dirty:
                connection.execute("DELETE FROM ecology_eradication_history")
                connection.executemany(
                    "INSERT INTO ecology_eradication_history (record_json) VALUES (?)",
                    [(_record_json(record),) for record in registry.get("eradication_history", ())],
                )
            connection.execute(
                "INSERT INTO ecology_meta (key, value) VALUES ('version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(ECOLOGY_REGISTRY_VERSION),),
            )
    finally:
        connection.close()
    return Path(path)


def _flush_runtime_registry(sim):
    runtime = getattr(sim, "ecology_registry_runtime", None) if sim is not None else None
    registry = ecology_registry_for_sim(sim)
    if not isinstance(runtime, dict) or registry is None:
        return None
    path = Path(runtime.get("path"))
    pending = set(runtime.get("pending_lineages") or ())
    history_dirty = bool(runtime.get("history_dirty"))
    full_sync = bool(runtime.get("full_sync_pending"))
    if not pending and not history_dirty and not full_sync:
        return path
    if str(runtime.get("backend", "")).lower() == "sqlite" and not full_sync:
        result = _persist_sqlite_changes(path, registry, pending, history_dirty=history_dirty)
    else:
        result = save_ecology_registry(registry, path=path)
    runtime["pending_lineages"] = set()
    runtime["history_dirty"] = False
    runtime["full_sync_pending"] = False
    return result


def _save_runtime_registry(sim, *, lineage_keys=(), history_dirty=False, full_sync=False):
    runtime = getattr(sim, "ecology_registry_runtime", None) if sim is not None else None
    registry = ecology_registry_for_sim(sim)
    if not isinstance(runtime, dict) or registry is None:
        return None
    pending = runtime.get("pending_lineages")
    if not isinstance(pending, set):
        pending = set(pending or ())
        runtime["pending_lineages"] = pending
    for domain, native_id in tuple(lineage_keys or ()):
        domain = _key(domain)
        native_id = str(native_id or "").strip()
        if domain in {"flora", "fauna"} and native_id:
            pending.add((domain, native_id))
    runtime["history_dirty"] = bool(runtime.get("history_dirty")) or bool(history_dirty)
    runtime["full_sync_pending"] = bool(runtime.get("full_sync_pending")) or bool(full_sync)
    if not lineage_keys and not history_dirty:
        runtime["full_sync_pending"] = True
    if _safe_int(runtime.get("batch_depth"), 0) > 0:
        return Path(runtime.get("path"))
    return _flush_runtime_registry(sim)


@contextmanager
def ecology_registry_write_batch(sim):
    """Commit all registry mutations in one transaction at pulse end."""

    runtime = getattr(sim, "ecology_registry_runtime", None) if sim is not None else None
    if not isinstance(runtime, dict) or not bool(runtime.get("primed")):
        yield
        return
    runtime["batch_depth"] = _safe_int(runtime.get("batch_depth"), 0) + 1
    try:
        yield
    finally:
        runtime["batch_depth"] = max(0, _safe_int(runtime.get("batch_depth"), 1) - 1)
        if runtime["batch_depth"] == 0:
            _flush_runtime_registry(sim)


def fauna_abundance_status(abundance):
    abundance = max(0, min(100, (_safe_int(abundance, 100) // FAUNA_CULL_STEP) * FAUNA_CULL_STEP))
    if abundance <= 0:
        return "extinct"
    if abundance <= 20:
        return "protected"
    if abundance <= 40:
        return "endangered"
    if abundance <= 60:
        return "scarce"
    if abundance <= 80:
        return "reduced"
    return "common"


def fauna_value_multiplier(abundance):
    abundance = max(0, min(100, (_safe_int(abundance, 100) // FAUNA_CULL_STEP) * FAUNA_CULL_STEP))
    return float(FAUNA_VALUE_MULTIPLIERS.get(abundance, 1.0))


def _fauna_population_payload(record):
    source = record.get("population") if isinstance((record or {}).get("population"), Mapping) else {}
    abundance = max(0, min(100, (_safe_int(source.get("abundance"), 100) // FAUNA_CULL_STEP) * FAUNA_CULL_STEP))
    history = source.get("cull_history")
    history = [copy.deepcopy(dict(row)) for row in history if isinstance(row, Mapping)][-16:] if isinstance(history, list) else []
    return {
        "abundance": abundance,
        "status": fauna_abundance_status(abundance),
        "value_multiplier": fauna_value_multiplier(abundance),
        "cull_history": history,
    }


def fauna_population_snapshot(sim, native_id):
    native_id = str(native_id or "").strip().lower()
    registry = ecology_registry_for_sim(sim)
    record = (registry.get("fauna") or {}).get(native_id) if registry is not None and native_id else None
    if not isinstance(record, Mapping):
        return {
            "native_id": native_id,
            "abundance": 100,
            "status": "unmanaged",
            "value_multiplier": 1.0,
            "cull_history": (),
        }
    return {"native_id": native_id, **_fauna_population_payload(record)}


def fauna_cull_active_for_run(sim, native_id):
    snapshot = fauna_population_snapshot(sim, native_id)
    run_seed = _safe_int(getattr(sim, "seed", 0), 0)
    return any(
        _safe_int(row.get("run_seed"), -1) == run_seed
        and str(row.get("action", "") or "").strip().lower() == "cull_declared"
        for row in tuple(snapshot.get("cull_history", ()) or ())
        if isinstance(row, Mapping)
    )


def initiate_fauna_cull(
    sim,
    native_id,
    *,
    actor_eid,
    authority_name="Civic Authority",
    authority_key="",
    fee=FAUNA_CULL_FEE,
    require_hunting_license=True,
):
    """Declare one durable 20-point fauna cull for this run.

    A lineage can move only one population tier per run seed.  Reaching zero
    therefore requires deliberate policy across five distinct runs rather than
    repeated clicks at one counter.
    """

    native_id = str(native_id or "").strip().lower()
    registry = ecology_registry_for_sim(sim)
    record = (registry.get("fauna") or {}).get(native_id) if registry is not None and native_id else None
    if not isinstance(record, dict):
        return {"ok": False, "reason": "unknown_lineage", "native_id": native_id}
    population = _fauna_population_payload(record)
    before = int(population["abundance"])
    if before <= 0:
        return {"ok": False, "reason": "extinct", "native_id": native_id, **population}
    run_seed = _safe_int(getattr(sim, "seed", 0), 0)
    if fauna_cull_active_for_run(sim, native_id):
        return {"ok": False, "reason": "already_declared", "native_id": native_id, **population}
    if require_hunting_license:
        from game.civic_records import civic_license_is_active

        if not civic_license_is_active(sim, actor_eid, "hunting"):
            return {"ok": False, "reason": "license_required", "native_id": native_id, **population}
    assets = sim.ecs.get(PlayerAssets).get(actor_eid)
    fee = max(0, _safe_int(fee, FAUNA_CULL_FEE))
    credits = max(0, _safe_int(getattr(assets, "credits", 0), 0)) if assets is not None else 0
    if fee and (assets is None or credits < fee):
        return {
            "ok": False,
            "reason": "no_credits",
            "native_id": native_id,
            "fee": fee,
            "credits": credits,
            **population,
        }
    after = max(0, before - FAUNA_CULL_STEP)
    presentation = record.get("presentation") if isinstance(record.get("presentation"), Mapping) else {}
    lineage_name = str(record.get("lineage_name") or presentation.get("common_name") or "local creature").strip()
    history_row = {
        "action": "cull_declared",
        "actor_eid": _safe_int(actor_eid, -1),
        "authority_name": str(authority_name or "Civic Authority").strip() or "Civic Authority",
        "authority_key": str(authority_key or "").strip().lower(),
        "run_seed": run_seed,
        "tick": _safe_int(getattr(sim, "tick", 0), 0),
        "before_abundance": before,
        "after_abundance": after,
    }
    population["abundance"] = after
    population["status"] = fauna_abundance_status(after)
    population["value_multiplier"] = fauna_value_multiplier(after)
    population["cull_history"] = (list(population.get("cull_history", ())) + [history_row])[-16:]
    record["population"] = population
    if fee and assets is not None:
        assets.credits = max(0, credits - fee)
    if after <= 0:
        registry.setdefault("eradication_history", []).append({
            "native_id": native_id,
            "lineage_name": lineage_name,
            **history_row,
        })
        registry["eradication_history"] = registry["eradication_history"][-128:]
    _save_runtime_registry(
        sim,
        lineage_keys=(("fauna", native_id),),
        history_dirty=after <= 0,
    )
    payload = {
        "ok": True,
        "native_id": native_id,
        "lineage_name": lineage_name,
        "before_abundance": before,
        "after_abundance": after,
        "status": population["status"],
        "value_multiplier": population["value_multiplier"],
        "fee": fee,
        "credits": max(0, _safe_int(getattr(assets, "credits", 0), 0)) if assets is not None else credits,
        "run_seed": run_seed,
        "authority_name": history_row["authority_name"],
        "authority_key": history_row["authority_key"],
    }
    sim.emit(Event("fauna_cull_declared", actor_eid=actor_eid, **payload))
    return payload


def _flora_identity_genetics(profile):
    genetics = profile.get("genetics") if isinstance(profile.get("genetics"), Mapping) else {}
    expressed = genetics.get("expressed") if isinstance(genetics.get("expressed"), Mapping) else {}
    visual = expressed.get("visual") if isinstance(expressed.get("visual"), Mapping) else {}
    color = visual.get("color") if isinstance(visual.get("color"), Mapping) else {}
    shape = visual.get("shape") if isinstance(visual.get("shape"), Mapping) else {}
    identity = {
        "hue_family": _key(color.get("word") or profile.get("color_word")),
    }
    for field in ("petal_shape", "blade_shape", "stem_shape", "leaf_shape", "habit", "texture"):
        if shape.get(field):
            identity[field] = _key(shape.get(field))
    return {key: value for key, value in identity.items() if value}


def _flora_identity_genome(profile):
    """Retain visual/recessive heredity without pinning the effect channel."""

    genetics = profile.get("genetics") if isinstance(profile.get("genetics"), Mapping) else {}
    genome = copy.deepcopy(dict(genetics))
    if not genome:
        return {}
    for field in ("genes", "carried", "expressed"):
        groups = genome.get(field)
        if not isinstance(groups, dict):
            continue
        groups.pop("chemistry", None)
        groups.pop("effects", None)
    genome.pop("effect_cost_used", None)
    genome["identity_only"] = True
    return genome


def _flora_native_id(profile):
    signature = _key(
        profile.get("hybrid_signature")
        or (profile.get("lineage") or {}).get("lineage_hash")
        or (profile.get("genetics") or {}).get("genome_id")
        or profile.get("plant_id")
    )
    return f"flora:{signature}" if signature else ""


def register_native_flora_line(sim, profile, *, source="bred"):
    """Persist a bred flora identity and its effect channel separately."""

    registry = ecology_registry_for_sim(sim)
    if registry is None or not isinstance(profile, Mapping):
        return None
    native_id = _flora_native_id(profile)
    plant_id = _key(profile.get("plant_id") or profile.get("id"))
    if not native_id or not plant_id:
        return None
    existing = (registry.get("flora") or {}).get(native_id) or {}
    identity = {
        "plant_id": plant_id,
        "name": str(profile.get("name") or profile.get("plant_name") or plant_id.replace("_", " ")).strip(),
        "plant_name": str(profile.get("plant_name") or profile.get("name") or plant_id.replace("_", " ")).strip(),
        "parent_line_name": str(profile.get("parent_line_name") or "").strip(),
        "parent_plant_ids": list(profile.get("parent_plant_ids") or ()),
        "hybrid_generation": _safe_int(profile.get("hybrid_generation"), 0),
        "hybrid_signature": _key(profile.get("hybrid_signature")),
        "lineage": copy.deepcopy(dict(profile.get("lineage") or {})),
        "growth_form": _key(profile.get("growth_form"), "flower"),
        "glyph": str(profile.get("glyph") or "'")[:1],
        "render_key": _key(profile.get("render_key") or profile.get("color_key"), "flora_leaf"),
        "color_key": _key(profile.get("color_key") or profile.get("render_key"), "flora_leaf"),
        "color_word": _key(profile.get("color_word")),
        "colors": list(profile.get("colors") or (profile.get("color_key") or profile.get("render_key") or "flora_leaf",)),
        "rarity": _key(profile.get("rarity"), "uncommon"),
        "tags": list(profile.get("tags") or ()),
        "crossbreed_tags": list(profile.get("crossbreed_tags") or ()),
        "genetics_identity": _flora_identity_genetics(profile),
        "identity_genome": _flora_identity_genome(profile),
    }
    effect_channel = {
        "chemistry_class": _key(profile.get("chemistry_class")),
        "secondary_traits": list(profile.get("secondary_traits") or ()),
        "stability_band": _key(profile.get("stability_band")),
        "notability": _key(profile.get("notability")),
    }
    record = {
        "native_id": native_id,
        "domain": "flora",
        "source": _key(source, "bred"),
        "identity": identity,
        "effect_channel": effect_channel,
        "times_realized": max(1, _safe_int(existing.get("times_realized"), 0) + 1),
    }
    registry.setdefault("flora", {})[native_id] = record
    _save_runtime_registry(sim, lineage_keys=(("flora", native_id),))
    # The hybrid is already a complete current-run profile. Mark and register
    # only this cultivar instead of rebuilding every installation-native flora
    # genome after each cross (an O(history) multi-second pulse on mature
    # registries). Future runs still reconstruct detached effects during prime.
    from game.flora_runtime import register_dynamic_flora_profile

    live_profile = copy.deepcopy(dict(profile))
    live_profile["native_lineage_id"] = native_id
    live_profile["dynamic_flora"] = True
    register_dynamic_flora_profile(sim, live_profile)
    sim.emit(Event(
        "ecology_lineage_native",
        domain="flora",
        native_id=native_id,
        lineage_name=identity["name"],
        source=record["source"],
        newly_native=not bool(existing),
    ))
    return copy.deepcopy(record)


def native_flora_profiles(sim):
    registry = ecology_registry_for_sim(sim)
    if registry is None:
        return {}
    rows = {}
    for native_id, record in (registry.get("flora") or {}).items():
        if not isinstance(record, Mapping):
            continue
        identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
        plant_id = _key(identity.get("plant_id"))
        if not plant_id:
            continue
        profile = copy.deepcopy(dict(identity))
        profile["id"] = plant_id
        profile["plant_id"] = plant_id
        identity_genome = copy.deepcopy(dict(identity.get("identity_genome") or identity.get("genetics_identity") or {}))
        # Registry records deliberately strip chemistry/effect loci.  Rebuild a
        # complete current-run genome before this cultivar can enter seed and
        # cultivation metadata, then graft its durable identity loci back in.
        # Herbal chemistry still treats the profile as detached and resolves
        # its actual hidden effects from this run's independent pool.
        fresh_row = dict(profile)
        fresh_row["genetics"] = {
            "hue_family": profile.get("color_word") or (identity.get("genetics_identity") or {}).get("hue_family"),
        }
        fresh_genome = normalize_flora_genetics(
            plant_id,
            fresh_row,
            seed=getattr(sim, "seed", 0),
        )
        identity_genes = identity_genome.get("genes") if isinstance(identity_genome.get("genes"), Mapping) else {}
        for group in ("visual", "handling", "social"):
            if isinstance(identity_genes.get(group), Mapping):
                fresh_genome["genes"][group] = copy.deepcopy(dict(identity_genes[group]))
        if isinstance(identity_genome.get("lineage"), Mapping):
            fresh_genome["lineage"] = copy.deepcopy(dict(identity_genome["lineage"]))
        if str(identity_genome.get("genome_id") or "").strip():
            fresh_genome["genome_id"] = str(identity_genome["genome_id"])
        fresh_genome["identity_only_source"] = True
        profile["genetics"] = normalize_flora_genetics(
            plant_id,
            {**profile, "genetics": fresh_genome},
            seed=getattr(sim, "seed", 0),
        )
        profile["dynamic_flora"] = True
        profile["native_lineage_id"] = str(native_id)
        profile["effect_pool_detached"] = True
        rows[plant_id] = profile
    return rows


def native_flora_effect_channels(sim):
    registry = ecology_registry_for_sim(sim)
    if registry is None:
        return ()
    rows = []
    for native_id, record in sorted((registry.get("flora") or {}).items()):
        if not isinstance(record, Mapping):
            continue
        channel = record.get("effect_channel") if isinstance(record.get("effect_channel"), Mapping) else {}
        rows.append({"native_id": str(native_id), **copy.deepcopy(dict(channel))})
    return tuple(rows)


def _prime_native_flora_profiles(sim):
    if sim is None:
        return 0
    from game.flora_runtime import register_dynamic_flora_profile

    count = 0
    for profile in native_flora_profiles(sim).values():
        if register_dynamic_flora_profile(sim, profile):
            count += 1
    return count


def _fauna_area_profile(sim, eid):
    pos = sim.ecs.get(Position).get(eid) if sim is not None else None
    if pos is None or getattr(sim, "world", None) is None:
        return {"areas": {"wilderness": 1.0}, "terrains": {}, "districts": {}}
    try:
        cx, cy = sim.chunk_coords(pos.x, pos.y)
        descriptor = sim.world.overworld_descriptor(cx, cy)
    except Exception:
        descriptor = {}
    area = _key(descriptor.get("area_type"), "wilderness")
    terrain = _key(descriptor.get("terrain"))
    district = _key(descriptor.get("district_type"))
    return {
        "areas": {area: 1.0},
        "terrains": {terrain: 0.6} if terrain else {},
        "districts": {district: 0.35} if district else {},
    }


def register_native_fauna_line(sim, eid, genome=None, *, source="natural_breeding"):
    registry = ecology_registry_for_sim(sim)
    if registry is None or sim is None:
        return None
    genome = genome or sim.ecs.get(AnimalGenome).get(eid)
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if genome is None or identity is None:
        return None
    native_id = str(getattr(genome, "lineage_id", "") or "").strip().lower()
    if not native_id:
        return None
    physical = sim.ecs.get(AnimalPhysicalProfile).get(eid)
    ecology = sim.ecs.get(EcologyProfile).get(eid)
    social = sim.ecs.get(AnimalSocialProfile).get(eid)
    reproduction = sim.ecs.get(AnimalReproduction).get(eid)
    vitality = sim.ecs.get(Vitality).get(eid)
    existing = (registry.get("fauna") or {}).get(native_id) or {}
    common_name = str(getattr(identity, "common_name", "") or "local creature").strip()
    if common_name.lower().startswith("young "):
        common_name = common_name[6:].strip() or common_name
    adult_size = float(getattr(reproduction, "adult_size_score", getattr(physical, "size_score", 18.0)) or 18.0)
    adult_speed = float(getattr(reproduction, "adult_speed_score", getattr(physical, "speed_score", 32.0)) or 32.0)
    adult_ecology = getattr(reproduction, "adult_ecology_profile", None)
    adult_ecology = adult_ecology if isinstance(adult_ecology, Mapping) else {}
    adult_max_hp = int(getattr(reproduction, "adult_max_hp", getattr(vitality, "max_hp", max(6, round(adult_size * 0.5)))) or max(6, round(adult_size * 0.5)))
    record = {
        "native_id": native_id,
        "domain": "fauna",
        "source": _key(source, "natural_breeding"),
        "root_animal_id": _key(getattr(genome, "root_animal_id", ""), "other_root"),
        "genome": animal_genome_payload(genome),
        "presentation": {
            "taxonomy_class": _key(getattr(identity, "taxonomy_class", ""), "other"),
            "species": str(getattr(identity, "species", "") or "local creature").strip().lower(),
            "common_name": common_name,
            "coat_variant": _key(getattr(identity, "coat_variant", "")),
            "size_score": adult_size,
            "speed_score": adult_speed,
            "max_hp": adult_max_hp,
            "ecology": {
                "species": str(getattr(ecology, "species", "") or "local creature").strip().lower() if ecology is not None else "local creature",
                "predator_score": float(adult_ecology.get("predator_score", getattr(ecology, "predator_score", 10.0)) or 0.0),
                "prey_score": float(adult_ecology.get("prey_score", getattr(ecology, "prey_score", 24.0)) or 0.0),
                "scavenger_score": float(adult_ecology.get("scavenger_score", getattr(ecology, "scavenger_score", 18.0)) or 0.0),
                "territorial_score": float(adult_ecology.get("territorial_score", getattr(ecology, "territorial_score", 18.0)) or 0.0),
                "pack_score": float(adult_ecology.get("pack_score", getattr(ecology, "pack_score", 18.0)) or 0.0),
                "flee_bias": float(adult_ecology.get("flee_bias", getattr(ecology, "flee_bias", 58.0)) or 0.0),
                "chase_bias": float(adult_ecology.get("chase_bias", getattr(ecology, "chase_bias", 18.0)) or 0.0),
            },
            "social": {
                "sociability": float(getattr(social, "sociability", 20.0) or 0.0) if social is not None else 20.0,
                "same_species_affinity": float(getattr(social, "same_species_affinity", 28.0) or 0.0) if social is not None else 28.0,
                "human_affinity": float(getattr(social, "human_affinity", 0.0) or 0.0) if social is not None else 0.0,
                "domesticity": float(getattr(social, "domesticity", 0.0) or 0.0) if social is not None else 0.0,
                "companionship_drive": float(getattr(social, "companionship_drive", 10.0) or 0.0) if social is not None else 10.0,
                "follow_drive": float(getattr(social, "follow_drive", 4.0) or 0.0) if social is not None else 4.0,
            },
        },
        "habitat": _fauna_area_profile(sim, eid),
        "times_realized": max(1, _safe_int(existing.get("times_realized"), 0) + 1),
        "population": _fauna_population_payload(existing),
    }
    record["genome"]["native_lineage_id"] = native_id
    registry.setdefault("fauna", {})[native_id] = record
    _save_runtime_registry(sim, lineage_keys=(("fauna", native_id),))
    sim.emit(Event(
        "ecology_lineage_native",
        domain="fauna",
        native_id=native_id,
        lineage_name=record["presentation"]["common_name"],
        root_animal_id=record["root_animal_id"],
        source=record["source"],
        newly_native=not bool(existing),
    ))
    return copy.deepcopy(record)


def native_fauna_profiles(sim):
    registry = ecology_registry_for_sim(sim)
    if registry is None:
        return ()
    rows = []
    for native_id, record in sorted((registry.get("fauna") or {}).items()):
        if not isinstance(record, Mapping):
            continue
        population = _fauna_population_payload(record)
        abundance = int(population["abundance"])
        if abundance <= 0:
            continue
        presentation = record.get("presentation") if isinstance(record.get("presentation"), Mapping) else {}
        habitat = record.get("habitat") if isinstance(record.get("habitat"), Mapping) else {}
        ecology = presentation.get("ecology") if isinstance(presentation.get("ecology"), Mapping) else {}
        social = presentation.get("social") if isinstance(presentation.get("social"), Mapping) else {}
        genome = record.get("genome") if isinstance(record.get("genome"), Mapping) else {}
        native_slug = _key(native_id).replace(":", "_")[-52:]
        common_name = str(presentation.get("common_name") or record.get("root_animal_id") or "local creature").strip()
        size = max(2.0, float(presentation.get("size_score", 18.0) or 18.0))
        speed = max(2.0, float(presentation.get("speed_score", 32.0) or 32.0))
        max_hp = max(6, _safe_int(presentation.get("max_hp"), round(size * 0.5)))
        rows.append({
            "id": f"native_{native_slug}",
            "root_animal_id": _key(record.get("root_animal_id"), "other_root"),
            "native_lineage_id": str(native_id),
            "native_genome": copy.deepcopy(dict(genome)),
            "taxonomy_class": _key(presentation.get("taxonomy_class"), "other"),
            "species": str(presentation.get("species") or "local creature").strip().lower(),
            "common_names": (common_name,),
            "coat_variant": _key(presentation.get("coat_variant")),
            "areas": dict(habitat.get("areas") or {"wilderness": 0.45, "frontier": 0.35}),
            "terrains": dict(habitat.get("terrains") or {}),
            "districts": dict(habitat.get("districts") or {}),
            "spawn_zones": ("perimeter", "street"),
            "color": _key((genome.get("expressed") or {}).get("color_word"), "other"),
            "max_hp": (max(6, int(round(max_hp * 0.92))), max(8, int(round(max_hp * 1.08)))),
            "speed": (max(0.7, speed / 62.0), max(0.78, speed / 50.0)),
            "physical_profile": {"size_score": size, "speed_score": speed},
            "ecology_profile": dict(ecology),
            "social_profile": dict(social),
            "trait_budget": _safe_int(genome.get("trait_budget"), 6),
            "native_weight": 0.44 * (abundance / 100.0),
            "population_abundance": abundance,
            "population_status": population["status"],
            "ecology_value_multiplier": population["value_multiplier"],
        })
    return tuple(rows)


def _appearance_words(value):
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def _fauna_registry_appearance(record):
    genome = record.get("genome") if isinstance(record.get("genome"), Mapping) else {}
    expressed = genome.get("expressed") if isinstance(genome.get("expressed"), Mapping) else {}
    color = _appearance_words(expressed.get("color_word")) or "unknown-color"
    accent = _appearance_words(expressed.get("accent_color_word"))
    pattern = _appearance_words(expressed.get("pattern"))
    build = _appearance_words(expressed.get("build"))
    display = _appearance_words(expressed.get("display"))
    root = _appearance_words(record.get("root_animal_id"))

    coat = " ".join(bit for bit in (color, pattern if pattern != "plain" else "") if bit).strip()
    bits = [f"{coat} coat"]
    if accent and accent != color:
        bits.append(f"{accent} accents")
    if build:
        bits.append(f"{build} build")
    if display and display != "none":
        bits.append(f"{display} display")
    if root:
        bits.append(f"{root} body plan")
    return "; ".join(bits)


def _flora_registry_appearance(record):
    identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
    genetics = identity.get("genetics_identity") if isinstance(identity.get("genetics_identity"), Mapping) else {}
    color = _appearance_words(identity.get("color_word") or genetics.get("hue_family"))
    growth_form = _appearance_words(identity.get("growth_form")) or "plant"
    bits = [" ".join(bit for bit in (color, growth_form) if bit).strip()]
    for field, suffix in (
        ("petal_shape", "petals"),
        ("leaf_shape", "leaves"),
        ("blade_shape", "blades"),
        ("stem_shape", "stems"),
        ("habit", "habit"),
        ("texture", "texture"),
    ):
        value = _appearance_words(genetics.get(field))
        if value:
            bits.append(f"{value} {suffix}")
    return "; ".join(dict.fromkeys(bit for bit in bits if bit)) or "appearance not recorded"


def ecology_species_registry_rows(sim, domain):
    """Return stable installation-native name/appearance rows for one domain."""

    domain = _key(domain)
    if domain not in {"flora", "fauna"}:
        return ()
    registry = ecology_registry_for_sim(sim)
    if registry is None:
        return ()
    rows = []
    for native_id, record in (registry.get(domain) or {}).items():
        if not isinstance(record, Mapping):
            continue
        population = None
        if domain == "fauna":
            presentation = record.get("presentation") if isinstance(record.get("presentation"), Mapping) else {}
            name = str(record.get("lineage_name") or presentation.get("common_name") or "local creature").strip()
            appearance = _fauna_registry_appearance(record)
            population = _fauna_population_payload(record)
        else:
            identity = record.get("identity") if isinstance(record.get("identity"), Mapping) else {}
            name = str(record.get("lineage_name") or identity.get("name") or identity.get("plant_name") or "local plant").strip()
            appearance = _flora_registry_appearance(record)
        rows.append({
            "native_id": str(native_id),
            "domain": domain,
            "name": name,
            "appearance": appearance,
            "times_realized": max(0, _safe_int(record.get("times_realized"), 0)),
            **(
                {
                    "abundance": population["abundance"],
                    "population_status": population["status"],
                    "value_multiplier": population["value_multiplier"],
                    "cull_active_this_run": fauna_cull_active_for_run(sim, native_id),
                }
                if domain == "fauna"
                else {}
            ),
        })
    rows.sort(key=lambda row: (str(row["name"]).casefold(), str(row["native_id"])))
    return tuple(rows)


__all__ = [
    "ECOLOGY_REGISTRY_DB_PATH",
    "ECOLOGY_REGISTRY_JSON_PATH",
    "ECOLOGY_REGISTRY_PATH",
    "ECOLOGY_REGISTRY_VERSION",
    "ecology_registry_write_batch",
    "ecology_registry_for_sim",
    "ecology_species_registry_rows",
    "empty_ecology_registry",
    "fauna_abundance_status",
    "fauna_cull_active_for_run",
    "fauna_population_snapshot",
    "fauna_value_multiplier",
    "initiate_fauna_cull",
    "load_ecology_registry",
    "migrate_ecology_registry_json",
    "native_fauna_profiles",
    "native_flora_effect_channels",
    "native_flora_profiles",
    "prime_ecology_registry",
    "register_native_fauna_line",
    "register_native_flora_line",
    "save_ecology_registry",
]
