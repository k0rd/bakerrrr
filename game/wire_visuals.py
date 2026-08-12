"""Procedural visual vocabulary for bounded WireScene projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import blake2b


WIRE_VISUAL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class WireVisual:
    kind: str
    glyph: str
    color: str
    pygame_shape: str
    label: str


def _visual(kind, glyph, color, label=None):
    clean_kind = str(kind)
    return WireVisual(
        kind=clean_kind,
        glyph=str(glyph or "?")[:1],
        color=str(color or "default"),
        pygame_shape=f"wire_{clean_kind}",
        label=str(label or clean_kind.replace("_", " ")),
    )


CURRENT_WIRE_VISUAL_KINDS = (
    "entry_jack",
    "diagnostic",
    "controller",
    "sensor_relay",
    "vehicle_lock_bus",
    "vehicle_tracker",
    "vehicle_ignition",
    "door_alarm_relay",
    "service_index",
    "records",
    "exit",
    "walkable_route",
    "void",
    "boundary",
    "noise_residue",
    "avatar",
    "wire_user",
    "wire_broker_user",
    "wire_sysadmin_user",
    "wire_rival_intruder",
    "wire_honeypot_user",
    "wire_echo_user",
    "program_talk",
    "program_route_probe",
    "program_handshake_breaker",
    "program_door_latch",
    "program_camera_loop",
    "program_data_siphon",
    "program_spike",
    "program_ice_cutter",
    "program_trace_scrubber",
    "program_signal_cloak",
    "program_proxy_route",
    "program_tunnel_route",
    "program_panic_eject",
    "program_checksum_ward",
    "program_sacrificial_shell",
    "ice_camera_watchdog",
    "ice_door_arbiter",
    "ice_trace_sentinel",
    "ice_compliance_daemon",
    "ice_quarantine_gate",
    "ice_corruptor",
    "effect_trace_sweep",
    "effect_corruption_flecks",
    "effect_buffer_shield",
    "effect_lock_bars",
    "effect_packet_pulse",
)


FUTURE_WIRE_VISUAL_KINDS = (
    "data_packet",
    "credential_access_key",
    "license",
    "backup",
    "trace",
    "corrupted_file",
)


WIRE_NODE_VISUAL_KIND_BY_NODE_KIND = {
    "entry": "entry_jack",
    "diagnostic": "diagnostic",
    "controller": "controller",
    "sensor_relay": "sensor_relay",
    "vehicle_lock_bus": "vehicle_lock_bus",
    "vehicle_tracker": "vehicle_tracker",
    "vehicle_ignition": "vehicle_ignition",
    "door_alarm_relay": "door_alarm_relay",
    "service_index": "service_index",
    "records": "records",
    "exit": "exit",
}


WIRE_VISUAL_CATALOG = {
    "entry_jack": _visual("entry_jack", ">", "player", "entry jack"),
    "diagnostic": _visual("diagnostic", "?", "property_fixture", "diagnostic node"),
    "controller": _visual("controller", "C", "objective", "controller node"),
    "sensor_relay": _visual("sensor_relay", ")", "property_service", "sensor/radio relay"),
    "vehicle_lock_bus": _visual("vehicle_lock_bus", "L", "feature_door", "vehicle lock controller"),
    "vehicle_tracker": _visual("vehicle_tracker", "T", "feature_window", "vehicle tracker controller"),
    "vehicle_ignition": _visual("vehicle_ignition", "I", "world_object_gold", "vehicle ignition controller"),
    "door_alarm_relay": _visual("door_alarm_relay", "R", "property_asset", "door/alarm relay"),
    "service_index": _visual("service_index", "S", "property_service", "service index"),
    "records": _visual("records", "D", "item_paper", "records node"),
    "exit": _visual("exit", "<", "player", "exit route"),
    "walkable_route": _visual("walkable_route", ".", "feature_window", "wire route"),
    "void": _visual("void", " ", "building_fill_dark", "signal void"),
    "boundary": _visual("boundary", "#", "building_edge", "bounded edge"),
    "noise_residue": _visual("noise_residue", "~", "human_slate", "noise residue"),
    "avatar": _visual("avatar", "@", "player", "wire avatar"),
    "wire_user": _visual("wire_user", "u", "human_denim", "wire user"),
    "wire_broker_user": _visual("wire_broker_user", "$", "world_object_gold", "wire broker"),
    "wire_sysadmin_user": _visual("wire_sysadmin_user", "&", "property_service", "wire sysadmin"),
    "wire_rival_intruder": _visual("wire_rival_intruder", "i", "projectile", "rival intruder"),
    "wire_honeypot_user": _visual("wire_honeypot_user", "?", "survival_meter_low", "honeypot"),
    "wire_echo_user": _visual("wire_echo_user", "'", "human_slate", "session echo"),
    "data_packet": _visual("data_packet", "d", "item_objective", "data packet"),
    "credential_access_key": _visual("credential_access_key", "k", "item_access", "access key"),
    "license": _visual("license", "l", "item_paper", "license"),
    "backup": _visual("backup", "b", "item_glass", "backup"),
    "trace": _visual("trace", "t", "survival_meter_low", "trace"),
    "corrupted_file": _visual("corrupted_file", "x", "projectile", "corrupted file"),
    "program_talk": _visual("program_talk", "T", "human_wine", "talk"),
    "program_route_probe": _visual("program_route_probe", "r", "feature_window", "route probe"),
    "program_handshake_breaker": _visual("program_handshake_breaker", "H", "survival_meter_low", "handshake breaker"),
    "program_door_latch": _visual("program_door_latch", "L", "feature_door", "door latch"),
    "program_camera_loop": _visual("program_camera_loop", "o", "property_fixture", "camera loop"),
    "program_data_siphon": _visual("program_data_siphon", "s", "item_objective", "data siphon"),
    "program_spike": _visual("program_spike", "!", "projectile", "spike"),
    "program_ice_cutter": _visual("program_ice_cutter", "/", "feature_breach", "ICE cutter"),
    "program_trace_scrubber": _visual("program_trace_scrubber", "u", "property_service", "trace scrubber"),
    "program_signal_cloak": _visual("program_signal_cloak", "c", "human_slate", "signal cloak"),
    "program_proxy_route": _visual("program_proxy_route", "p", "feature_window", "proxy route"),
    "program_tunnel_route": _visual("program_tunnel_route", "n", "item_glass", "tunnel route"),
    "program_panic_eject": _visual("program_panic_eject", "P", "survival_meter_low", "panic eject"),
    "program_checksum_ward": _visual("program_checksum_ward", "w", "item_access", "checksum ward"),
    "program_sacrificial_shell": _visual("program_sacrificial_shell", "h", "world_object_silver", "sacrificial shell"),
    "ice_camera_watchdog": _visual("ice_camera_watchdog", "W", "guard", "camera watchdog"),
    "ice_door_arbiter": _visual("ice_door_arbiter", "A", "property_asset", "door arbiter"),
    "ice_trace_sentinel": _visual("ice_trace_sentinel", "T", "survival_meter_low", "trace sentinel"),
    "ice_compliance_daemon": _visual("ice_compliance_daemon", "M", "world_object_gold", "compliance daemon"),
    "ice_quarantine_gate": _visual("ice_quarantine_gate", "Q", "world_object_purple", "quarantine gate"),
    "ice_corruptor": _visual("ice_corruptor", "X", "projectile", "corruptor"),
    "effect_trace_sweep": _visual("effect_trace_sweep", "|", "survival_meter_low", "trace sweep"),
    "effect_corruption_flecks": _visual("effect_corruption_flecks", "*", "projectile", "corruption flecks"),
    "effect_buffer_shield": _visual("effect_buffer_shield", ")", "item_glass", "buffer shield"),
    "effect_lock_bars": _visual("effect_lock_bars", "=", "building_edge", "lock bars"),
    "effect_packet_pulse": _visual("effect_packet_pulse", "*", "objective", "packet pulse"),
}


WIRE_INTERFACE_THEME_BY_KEY = {
    "plain": {
        "id": "plain",
        "label": "plain",
        "biome_style": "quiet_signal",
        "tokens": {
            "surface": "building_fill_dark",
            "surface_alt": "building_fill",
            "border": "building_edge",
            "accent": "player",
            "title": "objective",
            "body": "default",
            "muted": "human_slate",
            "divider": "building_edge",
            "selection": "player",
            "warning": "survival_meter_low",
            "footer": "human_slate",
        },
    },
    "streetline": {
        "id": "streetline",
        "label": "streetline",
        "biome_style": "patched_signal",
        "tokens": {
            "surface": "building_fill_dark",
            "surface_alt": "human_charcoal",
            "border": "world_object_purple",
            "accent": "world_object_gold",
            "title": "world_object_gold",
            "body": "default",
            "muted": "human_wine",
            "divider": "world_object_purple",
            "selection": "world_object_gold",
            "warning": "projectile",
            "footer": "human_wine",
        },
    },
    "neuroline": {
        "id": "neuroline",
        "label": "neuroline",
        "biome_style": "neural_strata",
        "tokens": {
            "surface": "building_fill_dark",
            "surface_alt": "human_charcoal",
            "border": "world_object_purple",
            "accent": "feature_window",
            "title": "feature_window",
            "body": "default",
            "muted": "human_denim",
            "divider": "world_object_purple",
            "selection": "feature_window",
            "warning": "survival_meter_low",
            "footer": "human_denim",
        },
    },
    "civictek": {
        "id": "civictek",
        "label": "civictek",
        "biome_style": "civic_grid",
        "tokens": {
            "surface": "building_fill_dark",
            "surface_alt": "building_fill_gray_c",
            "border": "guard",
            "accent": "property_fixture",
            "title": "guard",
            "body": "default",
            "muted": "human_slate",
            "divider": "property_fixture",
            "selection": "property_fixture",
            "warning": "survival_meter_low",
            "footer": "human_slate",
        },
    },
    "omnicorp": {
        "id": "omnicorp",
        "label": "omnicorp",
        "biome_style": "corporate_lattice",
        "tokens": {
            "surface": "building_fill_dark",
            "surface_alt": "building_fill_gray_a",
            "border": "world_object_gold",
            "accent": "property_asset",
            "title": "world_object_gold",
            "body": "default",
            "muted": "human_charcoal",
            "divider": "property_asset",
            "selection": "world_object_gold",
            "warning": "projectile",
            "footer": "human_charcoal",
        },
    },
    "relaytech": {
        "id": "relaytech",
        "label": "relaytech",
        "biome_style": "relay_basin",
        "tokens": {
            "surface": "building_fill_dark",
            "surface_alt": "human_olive",
            "border": "property_service",
            "accent": "property_service",
            "title": "property_service",
            "body": "default",
            "muted": "human_olive",
            "divider": "property_service",
            "selection": "property_service",
            "warning": "survival_meter_low",
            "footer": "human_olive",
        },
    },
    "unknown": {
        "id": "unknown",
        "label": "unknown",
        "biome_style": "noisy_signal",
        "tokens": {
            "surface": "building_fill_dark",
            "surface_alt": "building_fill",
            "border": "human_slate",
            "accent": "human_slate",
            "title": "objective",
            "body": "default",
            "muted": "human_slate",
            "divider": "human_slate",
            "selection": "player",
            "warning": "survival_meter_low",
            "footer": "human_slate",
        },
    },
}


WIRE_HOST_THEME_BY_FAMILY = {
    "access_control": {
        "id": "access_control",
        "label": "access-control lattice",
        "tokens": {"route": "feature_door", "noise": "property_asset", "border": "building_edge"},
    },
    "commercial_service": {
        "id": "commercial_service",
        "label": "commercial service mesh",
        "tokens": {"route": "property_service", "noise": "feature_window", "border": "property_fixture"},
    },
    "civic_service": {
        "id": "civic_service",
        "label": "civic service grid",
        "tokens": {"route": "guard", "noise": "property_fixture", "border": "building_edge"},
    },
    "finance_mask": {
        "id": "finance_mask",
        "label": "financial mask chain",
        "tokens": {"route": "world_object_gold", "noise": "item_access", "border": "property_asset"},
    },
    "drone_radio": {
        "id": "drone_radio",
        "label": "drone radio lattice",
        "tokens": {"route": "human_denim", "noise": "property_service", "border": "feature_window"},
    },
    "vehicle_bus": {
        "id": "vehicle_bus",
        "label": "vehicle bus rails",
        "tokens": {"route": "world_object_silver", "noise": "human_olive", "border": "building_edge"},
    },
    "local_controller": {
        "id": "local_controller",
        "label": "local controller mesh",
        "tokens": {"route": "feature_window", "noise": "human_slate", "border": "building_edge"},
    },
}


def _clean_key(value, default="unknown"):
    text = str(value or "").strip().lower()
    return text if text else str(default)


def _hash_int(*parts):
    data = ":".join(str(part or "") for part in parts).encode("utf-8", errors="replace")
    return int.from_bytes(blake2b(data, digest_size=8).digest(), "big")


def wire_visual_catalog():
    return dict(WIRE_VISUAL_CATALOG)


def wire_visual_for_kind(kind):
    key = _clean_key(kind, "void")
    visual = WIRE_VISUAL_CATALOG.get(key) or WIRE_VISUAL_CATALOG["void"]
    return {
        "kind": visual.kind,
        "glyph": visual.glyph,
        "color": visual.color,
        "pygame_shape": visual.pygame_shape,
        "semantic_id": visual.pygame_shape,
        "label": visual.label,
    }


def wire_visual_kind_for_node_kind(node_kind):
    return WIRE_NODE_VISUAL_KIND_BY_NODE_KIND.get(_clean_key(node_kind), "controller")


def wire_interface_theme(style=None, manufacturer=None, theme_profile=None):
    if isinstance(theme_profile, Mapping) and isinstance(theme_profile.get("tokens"), Mapping):
        return {
            "id": _clean_key(theme_profile.get("id"), "organization"),
            "label": str(theme_profile.get("label") or manufacturer or "organization line").strip(),
            "biome_style": _clean_key(theme_profile.get("biome_style"), "quiet_signal"),
            "motif": str(theme_profile.get("motif") or "").strip(),
            "tokens": dict(theme_profile.get("tokens") or {}),
        }
    style_key = _clean_key(style, "")
    manufacturer_key = _clean_key(manufacturer, "")
    candidates = []
    if style_key and style_key != "plain":
        candidates.append(style_key)
    if manufacturer_key:
        candidates.append(manufacturer_key)
    if style_key:
        candidates.append(style_key)
    candidates.append("unknown")
    for candidate in candidates:
        if candidate in WIRE_INTERFACE_THEME_BY_KEY:
            return {
                "id": WIRE_INTERFACE_THEME_BY_KEY[candidate]["id"],
                "label": WIRE_INTERFACE_THEME_BY_KEY[candidate]["label"],
                "biome_style": WIRE_INTERFACE_THEME_BY_KEY[candidate]["biome_style"],
                "tokens": dict(WIRE_INTERFACE_THEME_BY_KEY[candidate]["tokens"]),
            }
    return dict(WIRE_INTERFACE_THEME_BY_KEY["unknown"])


def wire_host_theme(network_family=None):
    key = _clean_key(network_family, "local_controller")
    row = WIRE_HOST_THEME_BY_FAMILY.get(key) or WIRE_HOST_THEME_BY_FAMILY["local_controller"]
    return {"id": row["id"], "label": row["label"], "tokens": dict(row.get("tokens") or {})}


def wire_visual_metadata(
    scene_id,
    target_class,
    interface_style,
    manufacturer,
    *,
    security=1,
    theme_profile=None,
    network_family=None,
):
    theme = wire_interface_theme(interface_style, manufacturer, theme_profile=theme_profile)
    if not str(network_family or "").strip():
        network_family = {
            "access_panel": "access_control",
            "service_terminal": "commercial_service",
            "drone_radio": "drone_radio",
            "vehicle_controller": "vehicle_bus",
        }.get(_clean_key(target_class, ""), "local_controller")
    host_theme = wire_host_theme(network_family)
    seed = _hash_int(scene_id, target_class, theme["id"], host_theme["id"], int(security or 0))
    return {
        "visual_schema_version": WIRE_VISUAL_SCHEMA_VERSION,
        "visual_seed": int(seed % 2_147_483_647),
        "interface_theme": theme,
        "host_theme": host_theme,
        "biome_style": theme.get("biome_style", "quiet_signal"),
    }


def apply_wire_scene_visuals(scene, *, security=1):
    if not isinstance(scene, dict):
        return scene
    metadata = wire_visual_metadata(
        scene.get("scene_id", ""),
        scene.get("target_class", ""),
        scene.get("interface_style", ""),
        scene.get("interface_manufacturer", ""),
        security=security,
        theme_profile=scene.get("interface_theme_profile"),
        network_family=scene.get("network_family"),
    )
    scene.update(metadata)
    for node in scene.get("nodes", ()) or ():
        if not isinstance(node, dict):
            continue
        visual_kind = wire_visual_kind_for_node_kind(node.get("kind"))
        visual = wire_visual_for_kind(visual_kind)
        node["visual_kind"] = visual_kind
        node["glyph"] = visual["glyph"]
        node["color"] = visual["color"]
        node["semantic_id"] = visual["semantic_id"]
    return scene


def wire_scene_theme(scene, base_theme=None):
    theme = dict(base_theme or {})
    base_tokens = dict(theme.get("tokens", {}) if isinstance(theme.get("tokens"), Mapping) else {})
    interface_theme = scene.get("interface_theme") if isinstance(scene, Mapping) else {}
    wire_tokens = dict(interface_theme.get("tokens", {}) if isinstance(interface_theme, Mapping) else {})
    if wire_tokens:
        base_tokens.update(wire_tokens)
    theme["tokens"] = base_tokens
    if isinstance(interface_theme, Mapping):
        theme["id"] = f"wire_{interface_theme.get('id', 'unknown')}"
        theme["label"] = f"Wire: {interface_theme.get('label', 'unknown')}"
    return theme


def _noise_variant(scene, x, y):
    seed = int((scene or {}).get("visual_seed", 0) or 0)
    return _hash_int(seed, int(x), int(y)) % 17


def _host_colored_visual(scene, visual, token):
    result = dict(visual or {})
    host_theme = scene.get("host_theme") if isinstance(scene, Mapping) and isinstance(scene.get("host_theme"), Mapping) else {}
    tokens = host_theme.get("tokens") if isinstance(host_theme.get("tokens"), Mapping) else {}
    color = str(tokens.get(token, "") or "").strip()
    if color:
        result["color"] = color
    return result


def wire_visual_for_cell(scene, x, y, *, walkable=False, node=None, avatar=False, width=0, height=0):
    if avatar:
        return wire_visual_for_kind("avatar")
    if isinstance(node, Mapping):
        visual_kind = node.get("visual_kind") or wire_visual_kind_for_node_kind(node.get("kind"))
        return wire_visual_for_kind(visual_kind)
    if walkable:
        kind = "noise_residue" if _noise_variant(scene, x, y) == 0 else "walkable_route"
        token = "noise" if kind == "noise_residue" else "route"
        return _host_colored_visual(scene, wire_visual_for_kind(kind), token)
    if x <= 0 or y <= 0 or (width and x >= int(width) - 1) or (height and y >= int(height) - 1):
        return _host_colored_visual(scene, wire_visual_for_kind("boundary"), "border")
    if _noise_variant(scene, x, y) in {1, 9}:
        return _host_colored_visual(scene, wire_visual_for_kind("noise_residue"), "noise")
    return wire_visual_for_kind("void")


def wire_scene_hud_lines(scene):
    if not isinstance(scene, Mapping):
        return []
    avatar = scene.get("avatar") if isinstance(scene.get("avatar"), Mapping) else {}
    node_label = "signal path"
    for node in scene.get("nodes", ()) or ():
        if not isinstance(node, Mapping):
            continue
        if int(node.get("x", -999)) == int(avatar.get("x", -1)) and int(node.get("y", -999)) == int(avatar.get("y", -1)):
            node_label = str(node.get("label", node_label))
            break
    lines = [
        (
            f"Target: {scene.get('target_name', 'wire target')} "
            f"[{str(scene.get('target_class', 'wire')).replace('_', ' ')} / "
            f"{str(scene.get('network_family', 'local_controller')).replace('_', ' ')}]"
        ),
        f"Interface: {scene.get('interface_name', 'interface')} / {scene.get('interface_style', 'plain')}",
        f"Node: {node_label}",
        "Body: anchored in meatspace; link active",
    ]
    action_effects = [
        effect
        for effect in scene.get("wire_action_effects", ()) or ()
        if isinstance(effect, Mapping) and str(effect.get("label", "") or "").strip()
    ]
    if action_effects:
        recent = [str(effect.get("label")) for effect in action_effects[-2:]]
        lines.append("Activity: " + " / ".join(recent))
    live_ice = [
        entity
        for entity in scene.get("wire_entities", ()) or ()
        if isinstance(entity, Mapping)
        and str(entity.get("source", "") or "").strip().lower() == "ice"
        and not bool(entity.get("destroyed"))
        and int(entity.get("hp", 0) or 0) > 0
    ]
    effects = [
        f"{effect.get('kind')}:{effect.get('turns')}"
        for effect in scene.get("active_effects", ()) or ()
        if isinstance(effect, Mapping) and int(effect.get("turns", 0) or 0) > 0
    ]
    if scene.get("buffer"):
        lines.append(f"Buffer: {scene.get('buffer')}")
    if scene.get("trace"):
        lines.append(f"Trace: {scene.get('trace')}")
    if live_ice:
        lines.append(f"ICE: {len(live_ice)} active")
    if scene.get("clean_exit_blocked"):
        lines.append("Exit: quarantined")
    if effects:
        lines.append("Effects: " + ", ".join(effects[:3]))
    for key, label in (("running_program", "Program"), ("alert_state", "Alert")):
        value = scene.get(key)
        if value not in (None, "", (), []):
            lines.append(f"{label}: {value}")
    return lines
