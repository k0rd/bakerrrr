"""Shared session-awareness and protected-route rules for Wire scenes.

This module deliberately owns neither program effects nor ICE combat.  It turns
Wire actions into local observations and alert state; ``wire_combat`` consumes
that state when deciding which installed countermeasures become active.
"""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event


WIRE_SECURITY_SESSION_SCHEMA_VERSION = 1
WIRE_ALERT_LEVELS = ("quiet", "suspicious", "alert", "lockdown")
WIRE_ALERT_THRESHOLDS = {
    "quiet": 0,
    "suspicious": 20,
    "alert": 55,
    "lockdown": 85,
}


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _key(value, default=""):
    return _text(value, default).lower()


def _int(value, default=0, *, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    if minimum is not None:
        number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return int(number)


def _point(value, default=(0, 0)):
    if isinstance(value, Mapping):
        return (_int(value.get("x"), default[0]), _int(value.get("y"), default[1]))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (_int(value[0], default[0]), _int(value[1], default[1]))
    return (int(default[0]), int(default[1]))


def wire_alert_level_for_score(score):
    score = _int(score, 0, minimum=0, maximum=100)
    if score >= WIRE_ALERT_THRESHOLDS["lockdown"]:
        return "lockdown"
    if score >= WIRE_ALERT_THRESHOLDS["alert"]:
        return "alert"
    if score >= WIRE_ALERT_THRESHOLDS["suspicious"]:
        return "suspicious"
    return "quiet"


def _persistent_start_score(level):
    """Translate remembered host posture into behavior, never extra HP."""

    return {
        1: 0,
        2: 8,
        3: 24,
        4: 58,
        5: 90,
    }.get(_int(level, 1, minimum=1, maximum=5), 0)


def normalize_wire_session_security(scene, *, interface_metadata=None, persistent_security=None):
    if not isinstance(scene, dict):
        return scene
    interface_metadata = dict(interface_metadata or {})
    persistent_security = dict(persistent_security or {}) if isinstance(persistent_security, Mapping) else {}
    persistent_level = _int(
        persistent_security.get("level"),
        scene.get("persistent_security_level", 1),
        minimum=1,
        maximum=5,
    )
    scene["persistent_security_level"] = persistent_level
    scene["persistent_security_label"] = _text(
        persistent_security.get("label") or scene.get("persistent_security_label"),
        {1: "quiet", 2: "logged", 3: "investigating", 4: "alert", 5: "locked"}.get(persistent_level, "quiet"),
    )
    scene["interface_warning_rating"] = _int(
        interface_metadata.get("warning_rating"),
        scene.get("interface_warning_rating", 1),
        minimum=0,
        maximum=5,
    )
    scene["interface_signature_leakage"] = _int(
        interface_metadata.get("signature_leakage"),
        scene.get("interface_signature_leakage", 0),
        minimum=0,
    )
    scene["interface_noise_floor"] = _int(
        interface_metadata.get("noise_floor"),
        scene.get("interface_noise_floor", 0),
        minimum=0,
    )
    existing = scene.get("session_alert") if isinstance(scene.get("session_alert"), Mapping) else {}
    score = _int(existing.get("score"), _persistent_start_score(persistent_level), minimum=0, maximum=100)
    level = wire_alert_level_for_score(score)
    last_anomaly = existing.get("last_anomaly")
    known_avatar = existing.get("known_avatar")
    history = [dict(row) for row in existing.get("history", ()) or () if isinstance(row, Mapping)][-8:]
    crossed = tuple(dict.fromkeys(_text(edge_id) for edge_id in existing.get("crossed_edges", ()) or () if _text(edge_id)))
    authorized = tuple(dict.fromkeys(_text(edge_id) for edge_id in existing.get("authorized_edges", ()) or () if _text(edge_id)))
    scene["session_alert"] = {
        "schema_version": WIRE_SECURITY_SESSION_SCHEMA_VERSION,
        "score": score,
        "level": level,
        "last_event": _key(existing.get("last_event")),
        "last_anomaly": list(_point(last_anomaly)) if last_anomaly is not None else None,
        "known_avatar": list(_point(known_avatar)) if known_avatar is not None else None,
        "known_avatar_tick": _int(existing.get("known_avatar_tick"), -1, minimum=-1),
        "crossed_edges": list(crossed),
        "authorized_edges": list(authorized),
        "history": history,
    }
    scene["alert_state"] = wire_alert_read(scene)
    return scene


def wire_session_alert(scene):
    if not isinstance(scene, Mapping):
        return {}
    alert = scene.get("session_alert")
    return dict(alert) if isinstance(alert, Mapping) else {}


def wire_alert_rank(scene_or_level):
    if isinstance(scene_or_level, Mapping):
        alert = scene_or_level.get("session_alert") if isinstance(scene_or_level.get("session_alert"), Mapping) else {}
        level = _key(alert.get("level"), "quiet")
    else:
        level = _key(scene_or_level, "quiet")
    try:
        return WIRE_ALERT_LEVELS.index(level)
    except ValueError:
        return 0


def wire_alert_read(scene):
    alert = wire_session_alert(scene)
    level = _key(alert.get("level"), "quiet")
    score = _int(alert.get("score"), 0, minimum=0, maximum=100)
    warning = _int((scene or {}).get("interface_warning_rating"), 1, minimum=0, maximum=5)
    if warning <= 1:
        return {
            "quiet": "unclear / probably quiet",
            "suspicious": "the host may have noticed something",
            "alert": "hostile attention on the layer",
            "lockdown": "lockdown signals everywhere",
        }.get(level, "unclear")
    if warning <= 3:
        return level
    return f"{level} {score}/100"


def wire_trace_read(scene):
    trace = _int((scene or {}).get("trace_current"), 0, minimum=0)
    limit = max(1, _int((scene or {}).get("trace_limit"), 12, minimum=1))
    warning = _int((scene or {}).get("interface_warning_rating"), 1, minimum=0, maximum=5)
    if warning <= 1:
        if trace <= 0:
            return "unclear / no strong return"
        if trace * 4 < limit:
            return "possibly rising"
        return "dangerously close"
    if warning <= 3:
        if trace <= 0:
            return "clear"
        if trace * 4 < limit:
            return "low"
        if trace * 4 < limit * 3:
            return "rising"
        return "hot"
    return f"{trace}/{limit}"


def wire_raise_session_alert(
    sim,
    actor_eid,
    scene,
    amount,
    *,
    reason="wire_action",
    position=None,
    known_position=None,
    acquire_avatar=False,
    signature=0,
):
    if not isinstance(scene, dict):
        return {"before": "quiet", "after": "quiet", "delta": 0}
    normalize_wire_session_security(scene)
    alert = dict(scene.get("session_alert") or {})
    before_score = _int(alert.get("score"), 0, minimum=0, maximum=100)
    before_level = wire_alert_level_for_score(before_score)
    delta = max(0, _int(amount, 0))
    after_score = min(100, before_score + delta)
    after_level = wire_alert_level_for_score(after_score)
    point = _point(position or scene.get("avatar"))
    alert["score"] = after_score
    alert["level"] = after_level
    alert["last_event"] = _key(reason, "wire_action")
    alert["last_anomaly"] = [int(point[0]), int(point[1])]
    if acquire_avatar:
        known_point = _point(known_position if known_position is not None else point)
        alert["known_avatar"] = [int(known_point[0]), int(known_point[1])]
        alert["known_avatar_tick"] = _int(getattr(sim, "tick", 0), 0)
    history = [dict(row) for row in alert.get("history", ()) or () if isinstance(row, Mapping)]
    history.append({
        "tick": _int(getattr(sim, "tick", 0), 0),
        "reason": alert["last_event"],
        "position": [int(point[0]), int(point[1])],
        "signature": _int(signature, 0, minimum=0),
        "before": before_score,
        "after": after_score,
    })
    alert["history"] = history[-8:]
    scene["session_alert"] = alert
    scene["alert_state"] = wire_alert_read(scene)
    if sim is not None:
        sim.emit(Event(
            "wire_session_alert_changed",
            eid=actor_eid,
            before=before_level,
            after=after_level,
            before_score=before_score,
            after_score=after_score,
            delta=after_score - before_score,
            reason=alert["last_event"],
            x=int(point[0]),
            y=int(point[1]),
            acquired=bool(acquire_avatar),
            signature=_int(signature, 0, minimum=0),
        ))
    return {
        "before": before_level,
        "after": after_level,
        "before_score": before_score,
        "after_score": after_score,
        "delta": after_score - before_score,
    }


def wire_acquire_avatar(sim, actor_eid, scene, *, reason="wire_contact", position=None, alert_amount=18):
    return wire_raise_session_alert(
        sim,
        actor_eid,
        scene,
        alert_amount,
        reason=reason,
        position=position or scene.get("avatar"),
        acquire_avatar=True,
        signature=0,
    )


def wire_forget_avatar(scene):
    if not isinstance(scene, dict):
        return False
    normalize_wire_session_security(scene)
    alert = dict(scene.get("session_alert") or {})
    if alert.get("known_avatar") is None:
        return False
    alert["known_avatar"] = None
    alert["known_avatar_tick"] = -1
    scene["session_alert"] = alert
    return True


def wire_security_edges(scene):
    if not isinstance(scene, Mapping):
        return []
    return [dict(edge) for edge in scene.get("security_edges", ()) or () if isinstance(edge, Mapping)]


def wire_security_edge_for_step(scene, source, target):
    source_point = _point(source)
    target_point = _point(target)
    for edge in wire_security_edges(scene):
        path = [_point(point) for point in edge.get("path", ()) or ()]
        for index in range(max(0, len(path) - 1)):
            left = path[index]
            right = path[index + 1]
            if (left == source_point and right == target_point) or (left == target_point and right == source_point):
                return edge
    return None


def _replace_security_edge(scene, updated):
    edge_id = _text((updated or {}).get("edge_id"))
    rows = []
    for edge in scene.get("security_edges", ()) or ():
        row = dict(edge) if isinstance(edge, Mapping) else {}
        if edge_id and _text(row.get("edge_id")) == edge_id:
            row.update(dict(updated))
        rows.append(row)
    scene["security_edges"] = rows


def wire_reveal_security_edge(scene, edge_id):
    edge_id = _text(edge_id)
    if not edge_id or not isinstance(scene, dict):
        return False
    for edge in wire_security_edges(scene):
        if _text(edge.get("edge_id")) != edge_id:
            continue
        changed = not bool(edge.get("revealed"))
        edge["revealed"] = True
        _replace_security_edge(scene, edge)
        return changed
    return False


def wire_reveal_all_security_edges(scene):
    changed = 0
    for edge in wire_security_edges(scene):
        if not bool(edge.get("revealed")):
            edge["revealed"] = True
            changed += 1
        _replace_security_edge(scene, edge)
    return changed


def wire_security_visual_kind_at(scene, x, y):
    point = (int(x), int(y))
    best = None
    ranks = {"public": 0, "authenticated": 1, "restricted": 2, "privileged": 3}
    for edge in wire_security_edges(scene):
        if not bool(edge.get("revealed")):
            continue
        if point not in {_point(raw) for raw in edge.get("path", ()) or ()}:
            continue
        access_class = _key(edge.get("access_class"), "public")
        if best is None or ranks.get(access_class, 0) > ranks.get(best, 0):
            best = access_class
    return {
        "authenticated": "wire_route_authenticated",
        "restricted": "wire_route_restricted",
        "privileged": "wire_route_privileged",
    }.get(best, "")


def resolve_wire_action_security(
    sim,
    actor_eid,
    scene,
    *,
    kind,
    source=None,
    target=None,
    edge=None,
    base_signature=0,
    hostile=False,
    authorized=False,
    cloak_strength=0,
    acquire_avatar=False,
    avatar_position=None,
):
    """Resolve one action into observation/alert without changing trace."""

    if not isinstance(scene, dict):
        return {"detected": False, "signature": 0, "alert_delta": 0}
    normalize_wire_session_security(scene)
    edge = dict(edge or {}) if isinstance(edge, Mapping) else {}
    edge_id = _text(edge.get("edge_id"))
    access_class = _key(edge.get("access_class"), "public")
    monitoring = _int(edge.get("monitoring"), 0, minimum=0, maximum=5)
    crossed = set(_text(value) for value in (scene.get("session_alert") or {}).get("crossed_edges", ()) or ())
    first_crossing = bool(edge_id and edge_id not in crossed)
    access_violation = bool(access_class != "public" and not authorized)
    if edge_id and first_crossing:
        alert = dict(scene.get("session_alert") or {})
        alert["crossed_edges"] = list(dict.fromkeys([*alert.get("crossed_edges", ()), edge_id]))
        scene["session_alert"] = alert
        wire_reveal_security_edge(scene, edge_id)

    base = max(0, _int(base_signature, 0))
    signature = base
    if base > 0 or monitoring > 0 or access_violation or hostile:
        signature += _int(scene.get("interface_signature_leakage"), 0, minimum=0)
        signature += _int(scene.get("interface_noise_floor"), 0, minimum=0)
    signature = max(0, signature - max(0, _int(cloak_strength, 0)))
    monitoring_pressure = monitoring if (signature or access_violation or hostile) else 0
    if not (signature or monitoring_pressure or access_violation or hostile):
        return {
            "detected": False,
            "signature": 0,
            "alert_delta": 0,
            "edge": edge,
            "access_violation": False,
            "authorized": bool(authorized),
        }

    persistent_level = _int(scene.get("persistent_security_level"), 1, minimum=1, maximum=5)
    alert_delta = signature * 4
    alert_delta += monitoring_pressure * 3
    alert_delta += max(0, persistent_level - 1) * 2
    if access_violation:
        alert_delta += 12
    if hostile:
        alert_delta += 28
    detected = alert_delta >= 8
    result = {"before": wire_session_alert(scene).get("level", "quiet"), "after": wire_session_alert(scene).get("level", "quiet")}
    if detected:
        result = wire_raise_session_alert(
            sim,
            actor_eid,
            scene,
            alert_delta,
            reason=f"{_key(kind, 'wire_action')}{'_violation' if access_violation else ''}",
            position=target or source or scene.get("avatar"),
            known_position=avatar_position if avatar_position is not None else scene.get("avatar"),
            acquire_avatar=bool(acquire_avatar),
            signature=signature,
        )
    return {
        "detected": bool(detected),
        "signature": int(signature),
        "alert_delta": int(result.get("delta", 0)),
        "before": result.get("before", "quiet"),
        "after": result.get("after", "quiet"),
        "edge": edge,
        "access_violation": bool(access_violation),
        "authorized": bool(authorized),
    }


def wire_security_debug_snapshot(scene):
    alert = wire_session_alert(scene)
    return {
        "security_tier": _int((scene or {}).get("security_tier"), 0, minimum=0),
        "persistent_level": _int((scene or {}).get("persistent_security_level"), 1, minimum=1, maximum=5),
        "persistent_label": _text((scene or {}).get("persistent_security_label"), "quiet"),
        "alert_level": _key(alert.get("level"), "quiet"),
        "alert_score": _int(alert.get("score"), 0, minimum=0, maximum=100),
        "last_anomaly": alert.get("last_anomaly"),
        "known_avatar": alert.get("known_avatar"),
        "trace_current": _int((scene or {}).get("trace_current"), 0, minimum=0),
        "trace_limit": _int((scene or {}).get("trace_limit"), 0, minimum=0),
        "avatar": dict((scene or {}).get("avatar") or {}),
        "security_edges": wire_security_edges(scene),
        "ice": [
            {
                "entity_id": entity.get("entity_id"),
                "kind": entity.get("kind"),
                "state": entity.get("state"),
                "revealed": bool(entity.get("revealed")),
                "x": entity.get("x"),
                "y": entity.get("y"),
            }
            for entity in (scene or {}).get("wire_entities", ()) or ()
            if isinstance(entity, Mapping)
        ],
    }
