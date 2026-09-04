"""Player-facing world-event presentation policy.

This module is intentionally independent of ``game.systems`` so extracted
runtime seams can share wording and policy without creating facade import loops.
"""

DIRECT_ROW_EVENT_KEYS = frozenset({
    "black_market_window",
    "campout",
    "hunter_party",
    "market_day",
    "security_sweep",
})

BUSINESS_SCENE_BIAS_EVENT_KEYS = frozenset({
    "faction_clash",
    "power_outage",
    "supply_shortage",
})

_BUSINESS_SCENE_PHASE_BIASES = {
    "supply_shortage": {
        "grumbling_front": 0.92,
        "supplier_drop": 0.62,
        "delivery_run": 0.58,
        "supply_run": 0.58,
        "loading_push": 0.52,
        "dispatch_surge": 0.44,
        "counter_queue": 0.74,
        "manifest_check": 0.32,
    },
    "power_outage": {
        "maintenance_loop": 0.92,
        "reset_scramble": 0.76,
        "barback_reset": 0.48,
        "owner_closed_turnover": 0.44,
        "visitor_screening": 0.34,
        "guard_rotation": 0.34,
        "quiet_handoff": 0.26,
    },
    "faction_clash": {
        "taped_off_front": 0.94,
        "cleanup_detail": 0.78,
        "guard_rotation": 0.72,
        "visitor_screening": 0.54,
        "owner_screening": 0.44,
        "manifest_check": 0.36,
    },
}

_BUSINESS_SCENE_NOTES = {
    "supply_shortage": "the shortage is showing at this business",
    "power_outage": "the outage is shaping how this businessg handled",
    "faction_clash": "local clash pressure is tightening this business"
}


def _text(value):
    return str(value or "").strip()


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def world_event_key(event_or_key):
    if isinstance(event_or_key, dict):
        event_or_key = event_or_key.get("key")
    return _text(event_or_key).lower()


def world_event_presentation_policy(event_or_key):
    key = world_event_key(event_or_key)
    if key in DIRECT_ROW_EVENT_KEYS:
        return "direct_row"
    if key in BUSINESS_SCENE_BIAS_EVENT_KEYS:
        return "business_scene_bias"
    return "modifier_only"


def world_event_uses_direct_row(event_or_key):
    return world_event_presentation_policy(event_or_key) == "direct_row"


def world_event_uses_business_scene_bias(event_or_key):
    return world_event_presentation_policy(event_or_key) == "business_scene_bias"


def _trade_effect_bits(event, *, ending=False):
    buy_mult = _float((event or {}).get("trade_buy_mult"), 1.0)
    sell_mult = _float((event or {}).get("trade_sell_mult"), 1.0)
    if ending:
        if abs(buy_mult - 1.0) > 0.02 or abs(sell_mult - 1.0) > 0.02:
            return ("trade terms are settling back toward normal",)
        return ()

    bits = []
    if buy_mult >= 1.08:
        bits.append("store prices are running higher")
    elif buy_mult <= 0.92:
        bits.append("store prices are softer")
    if sell_mult >= 1.08:
        bits.append("sell offers are better")
    elif sell_mult <= 0.92:
        bits.append("sell offers are lower")
    return tuple(bits)


def world_event_effect_bits(event, *, ending=False, include_handles=True):
    if not isinstance(event, dict):
        return ()
    key = world_event_key(event)
    bits = list(_trade_effect_bits(event, ending=ending))

    fixture_light_mult = _float(event.get("fixture_light_mult"), 1.0)
    if fixture_light_mult < 0.85:
        bits.append(
            "lights are coming back toward normal"
            if ending
            else (
                "grid lights are out"
                if fixture_light_mult <= 0.05
                else ("lights are badly dimmed" if fixture_light_mult <= 0.3 else "lights are dimmed")
            )
        )

    notice_delta = _int(event.get("observer_notice_delta"), 0)
    if notice_delta > 0:
        bits.append("patrol notice is easing back" if ending else "patrol notice reaches farther")
    elif notice_delta < 0:
        bits.append("watchers are losing their crowd cover" if ending else "crowds make watchers easier to lose")

    pressure_delta = _int(event.get("pressure_delta"), 0)
    if pressure_delta > 0:
        bits.append("local pressure is easing" if ending else "local pressure is up")
    elif pressure_delta < 0:
        bits.append("local pressure is tightening again" if ending else "local pressure is easing")

    if include_handles:
        if bool(event.get("spawn_market_stall")) or event.get("spawned_property_ids"):
            if key == "black_market_window":
                bits.append("the off-book seller is packing up" if ending else "an off-book seller is present")
            elif key == "market_day":
                bits.append("temporary stalls are clearing out" if ending else "temporary stalls are present")
            else:
                bits.append("temporary handles are clearing out" if ending else "temporary handles are present")
        if _int(event.get("guard_count"), 0) > 0 or key == "security_sweep":
            bits.append("extra guards are thinning out" if ending else "extra guards are on the block")
        if key == "hunter_party":
            bits.append("the field rack is clearing out" if ending else "a game rack and field crew are present")
        elif key == "campout":
            bits.append("the camp is breaking down" if ending else "a campfire ring and travelers are present")

    unique = []
    for bit in bits:
        clean = _text(bit)
        if clean and clean not in unique:
            unique.append(clean)
    return tuple(unique)


def world_event_effect_summary(event, *, ending=False, include_handles=True):
    return "; ".join(world_event_effect_bits(event, ending=ending, include_handles=include_handles))


def _active_world_event_store(sim):
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    state = traits.get("world_events") if isinstance(traits, dict) else None
    active = state.get("active", ()) if isinstance(state, dict) else ()
    return tuple(event for event in active if isinstance(event, dict))


def _event_chunk(event):
    try:
        return (int(event.get("cx", -999999)), int(event.get("cy", -999999)))
    except (TypeError, ValueError):
        return None


def active_world_event_business_scene_contexts(sim, chunk):
    if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return ()
    try:
        target = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return ()
    contexts = []
    for event in _active_world_event_store(sim):
        if _event_chunk(event) != target:
            continue
        if not world_event_uses_business_scene_bias(event):
            continue
        key = world_event_key(event)
        contexts.append({
            "key": key,
            "label": _text(event.get("label")) or "World Event",
            "effect_summary": world_event_effect_summary(event, include_handles=False),
            "note": _BUSINESS_SCENE_NOTES.get(key, "a world event is shaping this business")
        })
    return tuple(contexts)


def world_event_business_scene_context(sim, chunk, event_phase, category=""):
    phase = _text(event_phase).lower()
    category = _text(category).lower()
    if not phase:
        return {}
    best = None
    best_score = 0.0
    for context in active_world_event_business_scene_contexts(sim, chunk):
        key = context.get("key")
        phase_biases = _BUSINESS_SCENE_PHASE_BIASES.get(key, {})
        bias = _float(phase_biases.get(phase), 0.0)
        if key == "supply_shortage" and category in {"retail", "medical", "hospitality"}:
            bias += 0.12 if phase in {"counter_queue", "supplier_drop", "supply_run", "grumbling_front"} else 0.0
        elif key == "power_outage" and category in {"secure", "medical", "industrial", "transit"}:
            bias += 0.1 if phase in {"maintenance_loop", "guard_rotation", "visitor_screening"} else 0.0
        elif key == "faction_clash" and category in {"secure", "industrial", "transit"}:
            bias += 0.1 if phase in {"guard_rotation", "manifest_check", "visitor_screening"} else 0.0
        if bias <= 0.0:
            continue
        if best is None or bias > best_score or (bias == best_score and context.get("key", "") < best.get("key", "")):
            best = dict(context)
            best_score = float(bias)
    if best is None:
        return {}
    best["bias"] = round(best_score, 3)
    return best
