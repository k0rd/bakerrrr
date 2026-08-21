"""WireScene social user and dialogue helpers."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import blake2b

from engine.events import Event
from game.components import Position, Vitality


WIRE_USER_SCHEMA_VERSION = 1
WIRE_IDENTITY_LINK_SCHEMA_VERSION = 1
WIRE_DIALOGUE_SCHEMA_VERSION = 1

SUPPORTED_PROVENANCE_KINDS = {
    "embodied_actor",
    "institutional_endpoint",
    "synthetic_mask",
    "foreign_intruder",
    "honeypot",
    "echo",
}

WIRE_DIALOGUE_TOPICS = (
    ("ping", "Ping"),
    ("bluff_credential", "Bluff Credential"),
    ("ask_for_help", "Ask For Help"),
    ("stall", "Stall"),
    ("offer_data", "Offer Data"),
    ("trade_rumor", "Trade Rumor"),
    ("warn_threaten", "Warn/Threaten"),
    ("retreat", "Retreat"),
)

WIRE_USER_PROFILES = {
    "dispatcher": {
        "label": "dispatch endpoint",
        "visual_kind": "wire_sysadmin_user",
        "provenance_kind": "institutional_endpoint",
        "node": "controller",
        "disposition": "wary",
    },
    "contractor_tech": {
        "label": "contractor tech",
        "visual_kind": "wire_user",
        "provenance_kind": "institutional_endpoint",
        "node": "diagnostic",
        "disposition": "practical",
    },
    "sysadmin": {
        "label": "sysadmin",
        "visual_kind": "wire_sysadmin_user",
        "provenance_kind": "institutional_endpoint",
        "node": "controller",
        "disposition": "guarded",
    },
    "clerk": {
        "label": "service clerk",
        "visual_kind": "wire_user",
        "provenance_kind": "institutional_endpoint",
        "node": "near_entry",
        "disposition": "neutral",
    },
    "data_broker": {
        "label": "data broker",
        "visual_kind": "wire_broker_user",
        "provenance_kind": "institutional_endpoint",
        "node": "records",
        "disposition": "interested",
    },
    "gang_lookout": {
        "label": "gang lookout",
        "visual_kind": "wire_user",
        "provenance_kind": "institutional_endpoint",
        "node": "door_alarm_relay",
        "disposition": "suspicious",
    },
    "cult_recruiter": {
        "label": "cult recruiter",
        "visual_kind": "wire_user",
        "provenance_kind": "institutional_endpoint",
        "node": "records",
        "disposition": "inviting",
    },
    "rival_intruder": {
        "label": "rival intruder",
        "visual_kind": "wire_rival_intruder",
        "provenance_kind": "foreign_intruder",
        "node": "records",
        "disposition": "busy",
    },
    "drone_operator": {
        "label": "drone operator",
        "visual_kind": "wire_user",
        "provenance_kind": "institutional_endpoint",
        "node": "controller",
        "disposition": "focused",
    },
    "service_worker": {
        "label": "service worker",
        "visual_kind": "wire_user",
        "provenance_kind": "institutional_endpoint",
        "node": "near_entry",
        "disposition": "neutral",
    },
    "helpdesk_mask": {
        "label": "helpdesk mask",
        "visual_kind": "wire_honeypot_user",
        "provenance_kind": "synthetic_mask",
        "node": "diagnostic",
        "disposition": "scripted",
    },
    "honeypot": {
        "label": "friendly endpoint",
        "visual_kind": "wire_honeypot_user",
        "provenance_kind": "honeypot",
        "node": "controller",
        "disposition": "too_helpful",
    },
    "echo": {
        "label": "session echo",
        "visual_kind": "wire_echo_user",
        "provenance_kind": "echo",
        "node": "exit",
        "disposition": "fading",
    },
}


def _clean_text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _clean_key(value, default=""):
    return _clean_text(value, default).lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _hash_int(*parts):
    data = ":".join(str(part or "") for part in parts).encode("utf-8", errors="replace")
    return int.from_bytes(blake2b(data, digest_size=8).digest(), "big")


def _scene_mid(scene):
    bounds = scene.get("bounds") if isinstance(scene.get("bounds"), Mapping) else {}
    return max(1, _int(bounds.get("height"), 15) // 2)


def _node_by_id_or_kind(scene, key):
    needle = _clean_key(key)
    for node in scene.get("nodes", ()) or ():
        if not isinstance(node, Mapping):
            continue
        if _clean_key(node.get("node_id")) == needle or _clean_key(node.get("kind")) == needle:
            return dict(node)
    return None


def _walkable_points(scene):
    return {
        (int(point[0]), int(point[1]))
        for point in scene.get("walkable", ()) or ()
        if isinstance(point, (list, tuple)) and len(point) >= 2
    }


def _node_points(scene):
    return {
        (int(node.get("x", -999)), int(node.get("y", -999)))
        for node in scene.get("nodes", ()) or ()
        if isinstance(node, Mapping)
    }


def _adjacent_route_point(scene, node):
    if not isinstance(node, Mapping):
        return None
    x = _int(node.get("x"), 0)
    y = _int(node.get("y"), 0)
    walkable = _walkable_points(scene)
    node_points = _node_points(scene)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        point = (x + dx, y + dy)
        if point in walkable and point not in node_points:
            return point
    return None


def _position_for_profile(scene, profile):
    node_key = _clean_key(profile.get("node"), "near_entry")
    if node_key == "near_entry":
        return {"x": 4, "y": _scene_mid(scene), "node_id": "entry"}
    node = _node_by_id_or_kind(scene, node_key)
    if node is None and node_key == "door_alarm_relay":
        node = _node_by_id_or_kind(scene, "service_index")
    if node is None:
        node = _node_by_id_or_kind(scene, "controller") or _node_by_id_or_kind(scene, "entry")
    route_point = _adjacent_route_point(scene, node)
    if route_point is not None:
        return {
            "x": int(route_point[0]),
            "y": int(route_point[1]),
            "node_id": _clean_text((node or {}).get("node_id"), "entry"),
        }
    return {
        "x": _int((node or {}).get("x"), 4),
        "y": _int((node or {}).get("y"), _scene_mid(scene)),
        "node_id": _clean_text((node or {}).get("node_id"), "entry"),
    }


def _prop_context(prop):
    if not isinstance(prop, Mapping):
        return {}
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), Mapping) else {}
    org_key = (
        metadata.get("organization_key")
        or metadata.get("org_key")
        or metadata.get("organization_id")
        or metadata.get("faction_key")
        or prop.get("organization_key")
        or prop.get("owner_tag")
    )
    org_name = (
        metadata.get("organization_name")
        or metadata.get("org_name")
        or metadata.get("faction_name")
        or prop.get("owner_name")
        or org_key
    )
    return {
        "property_id": _clean_text(prop.get("id")),
        "property_name": _clean_text(prop.get("name"), "wire property"),
        "archetype": _clean_text(metadata.get("archetype") or metadata.get("service_archetype") or prop.get("kind")),
        "owner_tag": _clean_text(prop.get("owner_tag") or metadata.get("owner_tag")),
        "organization_key": _clean_text(org_key),
        "organization_name": _clean_text(org_name),
    }


def _context_text(scene, source_context=None, linked_context=None):
    parts = [
        scene.get("target_class"),
        scene.get("target_name"),
        scene.get("linked_name"),
        scene.get("target_archetype"),
        scene.get("linked_archetype"),
        scene.get("source_org_key"),
        scene.get("source_org_name"),
    ]
    for context in (source_context or {}, linked_context or {}):
        if isinstance(context, Mapping):
            parts.extend(context.values())
    return " ".join(str(part or "").lower() for part in parts)


def _candidate_user_kinds(scene, source_context=None, linked_context=None):
    text = _context_text(scene, source_context, linked_context)
    target_class = _clean_key(scene.get("target_class"))
    security = _int(scene.get("security_tier"), 1)
    candidates = []

    def add(kind):
        if kind in WIRE_USER_PROFILES and kind not in candidates:
            candidates.append(kind)

    if any(word in text for word in ("broker", "data", "media", "office", "tower", "corp", "tech")):
        add("data_broker")
        add("sysadmin")
    if any(word in text for word in ("justice", "security", "military", "checkpoint", "civic")) or security >= 3:
        add("dispatcher")
        add("sysadmin")
    if "gang" in text:
        add("gang_lookout")
    if "cult" in text:
        add("cult_recruiter")
    if "contractor" in text or "tool" in text or "service shop" in text:
        add("contractor_tech")
        add("service_worker")
    if target_class == "service_terminal" or "service" in text:
        add("clerk")
    if "drone" in text:
        add("drone_operator")
    if security >= 4:
        add("honeypot")
    if _hash_int(scene.get("scene_id"), text, "rival") % 5 == 0:
        add("rival_intruder")
    if _hash_int(scene.get("scene_id"), text, "echo") % 4 == 0:
        add("echo")
    if not candidates and security <= 1:
        add("service_worker")
    if not candidates and security > 1:
        add("helpdesk_mask")
    return candidates[:3]


def normalize_wire_identity_link(link=None, *, scene=None, user=None):
    link = dict(link or {}) if isinstance(link, Mapping) else {}
    user = dict(user or {}) if isinstance(user, Mapping) else {}
    profile = WIRE_USER_PROFILES.get(_clean_key(user.get("kind")), {})
    provenance = _clean_key(link.get("provenance_kind") or profile.get("provenance_kind"), "institutional_endpoint")
    if provenance not in SUPPORTED_PROVENANCE_KINDS:
        provenance = "institutional_endpoint"
    wire_handle = _clean_text(link.get("wire_handle") or user.get("wire_handle") or f"{_clean_key(user.get('kind'), 'user')}@local")
    meat_actor_ref = dict(link.get("meat_actor_ref") or {}) if isinstance(link.get("meat_actor_ref"), Mapping) else {}
    loaded_eid = link.get("loaded_eid", meat_actor_ref.get("eid"))
    if loaded_eid not in (None, ""):
        meat_actor_ref["eid"] = loaded_eid
        meat_actor_ref.setdefault("actor_uid", f"actor:{loaded_eid}")
        meat_actor_ref.setdefault("name_exposure", "unknown")
    elif "actor_uid" in meat_actor_ref:
        meat_actor_ref.setdefault("name_exposure", "unknown")
    org_ref = dict(link.get("org_ref") or {}) if isinstance(link.get("org_ref"), Mapping) else {}
    scene = scene or {}
    if not org_ref:
        org_ref = {
            "organization_key": _clean_text(scene.get("source_org_key")),
            "organization_name": _clean_text(scene.get("source_org_name")),
            "property_id": _clean_text(scene.get("linked_property_id") or scene.get("target_property_id")),
            "property_name": _clean_text(scene.get("linked_name") or scene.get("target_name")),
            "role": _clean_text(user.get("kind"), "endpoint"),
        }
    return {
        "schema_version": WIRE_IDENTITY_LINK_SCHEMA_VERSION,
        "provenance_kind": provenance,
        "wire_handle": wire_handle,
        "meat_actor_ref": meat_actor_ref,
        "loaded_eid": loaded_eid,
        "org_ref": org_ref,
        "wire_contact_ref": _clean_text(link.get("wire_contact_ref") or f"wire:{wire_handle}"),
        "meat_contact_ref": _clean_text(link.get("meat_contact_ref")),
        "org_contact_ref": _clean_text(link.get("org_contact_ref") or (f"org:{org_ref.get('organization_key')}" if org_ref.get("organization_key") else "")),
        "verified_link": bool(link.get("verified_link")),
        "link_confidence": max(0.0, min(1.0, float(link.get("link_confidence", 0.0) or 0.0))),
        "link_state": _clean_key(link.get("link_state"), "unknown"),
    }


def normalize_wire_user(user, *, scene=None):
    user = dict(user or {}) if isinstance(user, Mapping) else {}
    kind = _clean_key(user.get("kind"), "service_worker")
    profile = WIRE_USER_PROFILES.get(kind, WIRE_USER_PROFILES["service_worker"])
    pos = user.get("position") if isinstance(user.get("position"), Mapping) else user
    link = normalize_wire_identity_link(user.get("wire_identity_link"), scene=scene, user={**user, "kind": kind})
    visual_kind = _clean_key(user.get("visual_kind") or profile.get("visual_kind"), "wire_user")
    return {
        "schema_version": WIRE_USER_SCHEMA_VERSION,
        "user_id": _clean_text(user.get("user_id")),
        "kind": kind,
        "label": _clean_text(user.get("label") or profile.get("label"), kind.replace("_", " ")),
        "wire_handle": _clean_text(user.get("wire_handle") or link.get("wire_handle")),
        "visual_kind": visual_kind,
        "x": _int(pos.get("x"), 0),
        "y": _int(pos.get("y"), 0),
        "node_id": _clean_text(user.get("node_id") or pos.get("node_id")),
        "source_refs": dict(user.get("source_refs") or {}) if isinstance(user.get("source_refs"), Mapping) else {},
        "disposition": _clean_key(user.get("disposition") or profile.get("disposition"), "neutral"),
        "dialogue_topics": tuple(str(topic) for topic in (user.get("dialogue_topics") or [topic for topic, _label in WIRE_DIALOGUE_TOPICS])),
        "wire_identity_link": link,
        "available": bool(user.get("available", True)),
        "suspicion": _int(user.get("suspicion"), 0),
    }


def seed_wire_users_for_scene(scene, *, sim=None, source_prop=None, linked_prop=None):
    if not isinstance(scene, dict):
        return []
    source_context = _prop_context(source_prop)
    linked_context = _prop_context(linked_prop)
    scene.setdefault("wire_user_schema_version", WIRE_USER_SCHEMA_VERSION)
    scene.setdefault("target_archetype", source_context.get("archetype") or linked_context.get("archetype") or "local system")
    scene.setdefault("linked_archetype", linked_context.get("archetype") or "")
    scene.setdefault("source_org_key", linked_context.get("organization_key") or source_context.get("organization_key") or "")
    scene.setdefault("source_org_name", linked_context.get("organization_name") or source_context.get("organization_name") or "")
    scene.setdefault("wire_contact_refs", {})
    users = []
    for index, kind in enumerate(_candidate_user_kinds(scene, source_context, linked_context)):
        profile = WIRE_USER_PROFILES[kind]
        pos = _position_for_profile(scene, profile)
        handle_seed = _clean_key(scene.get("source_org_key") or scene.get("linked_name") or scene.get("target_name"), "local").replace(" ", "-")
        handle = f"{kind.replace('_', '-')}.{index}@{handle_seed}"
        user = {
            "user_id": f"user-{kind}-{_hash_int(scene.get('scene_id'), kind, index) % 100000}",
            "kind": kind,
            "label": profile.get("label", kind.replace("_", " ")),
            "wire_handle": handle,
            "visual_kind": profile.get("visual_kind", "wire_user"),
            "x": pos["x"],
            "y": pos["y"],
            "node_id": pos.get("node_id", ""),
            "source_refs": {
                "target_property_id": scene.get("target_property_id"),
                "linked_property_id": scene.get("linked_property_id"),
                "node_id": pos.get("node_id", ""),
            },
            "disposition": profile.get("disposition", "neutral"),
            "dialogue_topics": tuple(topic for topic, _label in WIRE_DIALOGUE_TOPICS),
            "wire_identity_link": normalize_wire_identity_link(
                {
                    "provenance_kind": profile.get("provenance_kind"),
                    "wire_handle": handle,
                    "org_ref": {
                        "organization_key": scene.get("source_org_key", ""),
                        "organization_name": scene.get("source_org_name", ""),
                        "property_id": scene.get("linked_property_id") or scene.get("target_property_id"),
                        "property_name": scene.get("linked_name") or scene.get("target_name"),
                        "role": kind,
                    },
                    "link_state": "active",
                    "link_confidence": 0.35 if profile.get("provenance_kind") == "institutional_endpoint" else 0.0,
                },
                scene=scene,
                user={"kind": kind, "wire_handle": handle},
            ),
        }
        users.append(normalize_wire_user(user, scene=scene))
    scene["wire_users"] = resolve_wire_identity_links(sim, {"wire_users": users}, mutate=False) if sim is not None else users
    return list(scene["wire_users"])


def _entity_exists(sim, eid):
    if sim is None or eid in (None, ""):
        return False
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return False
    for bucket in getattr(getattr(sim, "ecs", None), "components", {}).values():
        if eid in bucket:
            return True
    return False


def _resolved_link_state(sim, link):
    provenance = _clean_key((link or {}).get("provenance_kind"), "institutional_endpoint")
    if provenance in {"synthetic_mask", "honeypot", "echo", "foreign_intruder"}:
        return "masked" if provenance in {"synthetic_mask", "honeypot"} else provenance
    meat_ref = (link or {}).get("meat_actor_ref") if isinstance((link or {}).get("meat_actor_ref"), Mapping) else {}
    eid = (link or {}).get("loaded_eid", meat_ref.get("eid"))
    if eid in (None, ""):
        return "active" if provenance == "institutional_endpoint" else "unknown"
    try:
        eid_int = int(eid)
    except (TypeError, ValueError):
        return "stale"
    if not _entity_exists(sim, eid_int):
        return "stale"
    vitality = sim.ecs.get(Vitality).get(eid_int)
    if vitality is not None and _int(getattr(vitality, "hp", 1), 1) <= 0:
        return "dead"
    if sim.ecs.get(Position).get(eid_int) is None:
        return "unloaded"
    return "active"


def resolve_wire_identity_links(sim, scene, *, mutate=True):
    if not isinstance(scene, Mapping):
        return [] if not mutate else scene
    users = []
    for user in scene.get("wire_users", ()) or ():
        clean = normalize_wire_user(user, scene=scene)
        link = dict(clean.get("wire_identity_link") or {})
        link["link_state"] = _resolved_link_state(sim, link)
        clean["wire_identity_link"] = link
        if link["link_state"] in {"dead", "stale"} and link.get("provenance_kind") == "embodied_actor":
            clean["available"] = False
            clean["disposition"] = "silent"
            clean["label"] = "dead account" if link["link_state"] == "dead" else "stale account"
            clean["kind"] = "echo"
            clean["visual_kind"] = "wire_echo_user"
        users.append(clean)
    if mutate and isinstance(scene, dict):
        scene["wire_users"] = users
        return scene
    return users


def wire_users_for_scene(sim, scene):
    if not isinstance(scene, Mapping):
        return []
    return resolve_wire_identity_links(sim, scene, mutate=False)


def _avatar(scene):
    return scene.get("avatar") if isinstance(scene.get("avatar"), Mapping) else {}


def _distance_from_avatar(scene, user):
    avatar = _avatar(scene)
    return abs(_int(avatar.get("x"), 0) - _int(user.get("x"), 0)) + abs(_int(avatar.get("y"), 0) - _int(user.get("y"), 0))


def wire_user_target_rows(sim, scene, *, range_limit=4):
    rows = []
    for user in wire_users_for_scene(sim, scene):
        if not bool(user.get("available", True)):
            continue
        distance = _distance_from_avatar(scene, user)
        if distance > int(range_limit):
            continue
        link = user.get("wire_identity_link") if isinstance(user.get("wire_identity_link"), Mapping) else {}
        label = f"User: {user.get('label')} [{link.get('provenance_kind', 'unknown')}; {distance}]"
        rows.append({
            "kind": "user",
            "target_id": user.get("user_id"),
            "label": label,
            "user": dict(user),
            "distance": distance,
        })
    rows.sort(key=lambda row: (int(row.get("distance", 0)), str(row.get("target_id", ""))))
    return rows


def resolve_wire_user_target(sim, scene, target=None):
    target_id = _clean_text((target or {}).get("target_id") if isinstance(target, Mapping) else "")
    users = wire_users_for_scene(sim, scene)
    if target_id:
        for user in users:
            if _clean_text(user.get("user_id")) == target_id:
                return {"kind": "user", "user": dict(user), "label": str(user.get("label", "wire user"))}
    near = wire_user_target_rows(sim, scene)
    if near:
        user = dict(near[0].get("user") or {})
        return {"kind": "user", "user": user, "label": str(user.get("label", "wire user"))}
    return {"kind": "user", "user": None, "label": "wire user"}


def validate_wire_user_target(scene, target, *, range_limit=4):
    user = target.get("user") if isinstance(target, Mapping) else None
    if not isinstance(user, Mapping):
        return False, "missing_user_target"
    if not bool(user.get("available", True)):
        return False, "wire_user_unavailable"
    if _distance_from_avatar(scene, user) > int(range_limit):
        return False, "wire_user_out_of_range"
    if _clean_key(user.get("disposition")) == "silent":
        return False, "wire_user_silent"
    return True, None


def _dialogue_rows_for_user(user):
    available = set(user.get("dialogue_topics") or ())
    rows = []
    for topic_id, label in WIRE_DIALOGUE_TOPICS:
        if topic_id in available:
            rows.append({"topic_id": topic_id, "label": label})
    return rows


def open_wire_dialogue(sim, actor_eid, scene, user_target):
    if not isinstance(scene, dict):
        return {"ok": False, "reason": "missing_scene"}
    user = user_target.get("user") if isinstance(user_target, Mapping) else None
    if not isinstance(user, Mapping):
        return {"ok": False, "reason": "missing_user_target"}
    rows = _dialogue_rows_for_user(user)
    if not rows:
        return {"ok": False, "reason": "wire_user_refused"}
    link = user.get("wire_identity_link") if isinstance(user.get("wire_identity_link"), Mapping) else {}
    dialogue = {
        "schema_version": WIRE_DIALOGUE_SCHEMA_VERSION,
        "open": True,
        "user_id": user.get("user_id"),
        "user_label": user.get("label", "wire user"),
        "wire_handle": link.get("wire_handle") or user.get("wire_handle"),
        "provenance_kind": link.get("provenance_kind", "unknown"),
        "link_state": link.get("link_state", "unknown"),
        "selected_index": 0,
        "rows": rows,
        "last_response": f"{user.get('label', 'wire user')} acknowledges the ping.",
        "contact_refs": {
            "wire_contact_ref": link.get("wire_contact_ref", ""),
            "meat_contact_ref": link.get("meat_contact_ref", ""),
            "org_contact_ref": link.get("org_contact_ref", ""),
        },
    }
    scene["wire_dialogue"] = dialogue
    scene["last_feedback"] = f"Talk channel open: {dialogue['user_label']}."
    sim.emit(Event(
        "wire_dialogue_opened",
        eid=actor_eid,
        user_id=user.get("user_id"),
        user_kind=user.get("kind"),
        provenance_kind=dialogue["provenance_kind"],
        link_state=dialogue["link_state"],
        source_kind="wire_dialogue",
        observation_channel="wire_social",
        firsthand=False,
    ))
    return {"ok": True, "reason": None, "dialogue": dialogue, "feedback": scene["last_feedback"]}


def wire_dialogue_state(scene):
    if not isinstance(scene, Mapping):
        return {}
    dialogue = scene.get("wire_dialogue") if isinstance(scene.get("wire_dialogue"), Mapping) else {}
    return dict(dialogue) if bool(dialogue.get("open")) else {}


def wire_dialogue_rows(scene):
    dialogue = wire_dialogue_state(scene)
    return [dict(row) for row in dialogue.get("rows", ()) or () if isinstance(row, Mapping)]


def _wire_data_count(state):
    return sum(1 for entry in getattr(state, "kit_entries", ()) or () if isinstance(entry, Mapping) and _clean_key(entry.get("item_id")) == "wire_data_cache")


def handle_wire_dialogue_choice(sim, actor_eid, *, row_index=0, topic_id=None):
    from game.wire_kit import wire_state_for_actor

    state = wire_state_for_actor(sim, actor_eid, create=False)
    scene = getattr(state, "active_scene", None) if state is not None else None
    if not isinstance(scene, dict):
        return {"ok": False, "reason": "missing_scene"}
    dialogue = wire_dialogue_state(scene)
    if not dialogue:
        return {"ok": False, "reason": "missing_dialogue"}
    rows = wire_dialogue_rows(scene)
    if topic_id:
        row = next((row for row in rows if _clean_key(row.get("topic_id")) == _clean_key(topic_id)), None)
    else:
        row = rows[int(max(0, min(len(rows) - 1, int(row_index or 0))))] if rows else None
    if row is None:
        return {"ok": False, "reason": "missing_dialogue_row"}
    topic = _clean_key(row.get("topic_id"))
    user = next((dict(user) for user in scene.get("wire_users", ()) or () if isinstance(user, Mapping) and _clean_text(user.get("user_id")) == _clean_text(dialogue.get("user_id"))), {})
    link = user.get("wire_identity_link") if isinstance(user.get("wire_identity_link"), Mapping) else {}
    response = "The channel gives back static."
    close = False
    if topic == "ping":
        response = f"{dialogue.get('wire_handle', 'handle')} answers as {dialogue.get('provenance_kind', 'unknown')}; link reads {dialogue.get('link_state', 'unknown')}."
    elif topic == "bluff_credential":
        if dialogue.get("provenance_kind") == "honeypot":
            response = "The endpoint accepts too quickly and tags the session for review."
            user["suspicion"] = _int(user.get("suspicion"), 0) + 2
        else:
            response = "The credential bluff buys a few seconds, not trust."
            user["suspicion"] = _int(user.get("suspicion"), 0) + 1
    elif topic == "ask_for_help":
        response = "They surface the cleanest contact handle they are willing to admit."
        dialogue.setdefault("contact_refs", {})["org_contact_ref"] = link.get("org_contact_ref", "")
    elif topic == "stall":
        if user.get("stall_cover_spent"):
            response = "They have already spent the harmless traffic they could hide you inside."
        elif dialogue.get("provenance_kind") == "honeypot":
            response = "The friendly delay is part of the trap; the endpoint keeps measuring you."
            user["suspicion"] = _int(user.get("suspicion"), 0) + 1
            user["stall_cover_spent"] = True
        else:
            from game.wire_security_runtime import wire_alert_level_for_score

            alert = dict(scene.get("session_alert") or {})
            before = _int(alert.get("score"), 0)
            after = max(0, before - 8)
            alert["score"] = after
            alert["level"] = wire_alert_level_for_score(after)
            scene["session_alert"] = alert
            scene["alert_state"] = alert["level"]
            user["stall_cover_spent"] = True
            response = f"They fold your signal into harmless chatter; host attention slips {before - after} points."
    elif topic == "offer_data":
        data_count = _wire_data_count(state)
        response = "They might buy a packet later." if data_count else "They ask what data you think you are offering."
    elif topic == "trade_rumor":
        response = "A wire-side rumor shakes loose: useful handles travel through places like this."
        dialogue.setdefault("contact_refs", {})["wire_contact_ref"] = link.get("wire_contact_ref", "")
    elif topic == "warn_threaten":
        if dialogue.get("provenance_kind") in {"synthetic_mask", "honeypot"}:
            response = "The mask records the threat as pressure, not fear."
            user["suspicion"] = _int(user.get("suspicion"), 0) + 2
        else:
            response = "The warning lands, but it makes the channel colder."
            user["suspicion"] = _int(user.get("suspicion"), 0) + 1
    elif topic == "retreat":
        response = "You let the channel go quiet."
        close = True
    if user:
        updated = []
        for existing in scene.get("wire_users", ()) or ():
            if isinstance(existing, Mapping) and _clean_text(existing.get("user_id")) == _clean_text(user.get("user_id")):
                merged = dict(existing)
                merged.update(user)
                updated.append(merged)
            else:
                updated.append(dict(existing) if isinstance(existing, Mapping) else existing)
        scene["wire_users"] = updated
    dialogue["selected_index"] = _int(row_index, 0)
    dialogue["last_response"] = response
    dialogue["open"] = not close
    scene["wire_dialogue"] = dialogue
    scene["last_feedback"] = response
    state.active_scene = dict(scene)
    sim.emit(Event(
        "wire_dialogue_choice",
        eid=actor_eid,
        user_id=dialogue.get("user_id"),
        topic_id=topic,
        provenance_kind=dialogue.get("provenance_kind", "unknown"),
        source_kind="wire_dialogue",
        observation_channel="wire_social",
        firsthand=False,
    ))
    return {"ok": True, "reason": None, "feedback": response, "closed": close, "dialogue": dict(dialogue)}
