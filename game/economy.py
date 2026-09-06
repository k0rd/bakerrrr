from engine.systems import System
from game.items import ITEM_CATALOG, item_display_name


LEGAL_TAGS = {"legal", "restricted", "illegal"}
LOCAL_TRADE_PRESSURE_HALF_LIFE_HOURS = 24
LOCAL_TRADE_PRESSURE_PRUNE_HOURS = 72
LOCAL_TRADE_PROPERTY_WEIGHT = 1.0
LOCAL_TRADE_CHUNK_WEIGHT = 0.34
LOCAL_TRADE_TAG_WEIGHT = 0.52
LOCAL_TRADE_CHUNK_READ_WEIGHT = 0.42
NOISY_TRADE_PRESSURE_TAGS = {
    "",
    "legal",
    "restricted",
    "illegal",
    "stolen",
    "unknown",
    "cash",
    "credit",
    "misc",
}


DISTRICT_CONTEXTS = {
    "industrial": {
        "label": "factory and haulage blocks",
        "family_profile": "shift-worker households",
        "tag_weights": {"tool": 1.2, "restricted": 0.4, "medical": 0.3, "energy": 0.5},
        "archetype_weights": {
            "warehouse": 0.6,
            "factory": 1.0,
            "machine_shop": 0.9,
            "freight_depot": 0.7,
            "auto_garage": 0.4,
            "cold_storage": 0.8,
            "tool_depot": 0.5,
            "electronics_shop": 0.35,
            "comms_shop": 0.22,
            "drone_shop": 0.35,
            "wire_shop": 0.38,
        },
        "career_keywords": ("operator", "tech", "machin", "yard", "freight"),
        "stock_mult": 1.05,
        "price_mult": 0.98,
    },
    "residential": {
        "label": "service-heavy neighborhood",
        "family_profile": "apartment families and block services",
        "tag_weights": {"food": 0.8, "drink": 0.5, "medical": 0.6, "token": 0.3},
        "archetype_weights": {
            "corner_store": 0.5,
            "restaurant": 0.3,
            "daycare": 0.4,
            "laundromat": 0.4,
            "pharmacy": 0.4,
            "bookshop": 0.5,
            "hardware_store": 0.5,
            "electronics_shop": 0.35,
            "comms_shop": 0.2,
            "drone_shop": 0.18,
            "wire_shop": 0.22,
            "outfitter": 0.6,
            "surplus_store": 0.35,
        },
        "stock_mult": 1.02,
        "price_mult": 0.99,
    },
    "downtown": {
        "label": "office and retail center",
        "family_profile": "commuter households and service workers",
        "tag_weights": {"token": 1.1, "drink": 0.4, "medical": 0.4, "restricted": 0.3},
        "archetype_weights": {
            "office": 0.9,
            "bank": 0.8,
            "restaurant": 0.5,
            "hotel": 0.6,
            "courier_office": 0.6,
            "gallery": 0.4,
            "brokerage": 0.7,
            "casino": 0.45,
            "tavern": 0.35,
            "electronics_shop": 0.45,
            "comms_shop": 0.34,
            "drone_shop": 0.18,
            "wire_shop": 0.5,
            "outfitter": 0.14,
        },
        "career_keywords": ("analyst", "manager", "controller", "desk"),
        "stock_mult": 1.0,
        "price_mult": 1.03,
    },
    "slums": {
        "label": "salvage and survival district",
        "family_profile": "scrap families and informal renters",
        "tag_weights": {"tool": 0.8, "illegal": 1.0, "stimulant": 0.8, "food": 0.5},
        "archetype_weights": {
            "pawn_shop": 0.7,
            "backroom_clinic": 0.5,
            "chop_shop": 0.8,
            "junk_market": 1.0,
            "soup_kitchen": 0.5,
            "flophouse": 0.7,
            "street_kitchen": 0.6,
            "wire_shop": 0.2,
        },
        "career_keywords": ("salvage", "repair", "scrap", "fence", "lookout"),
        "stock_mult": 0.95,
        "price_mult": 1.05,
    },
    "corporate": {
        "label": "managed corporate enclave",
        "family_profile": "credentialed workers and contractor flats",
        "tag_weights": {"discipline": 1.0, "restricted": 0.6, "token": 0.8, "medical": 0.4},
        "archetype_weights": {
            "tower": 1.0,
            "lab": 0.8,
            "server_hub": 0.8,
            "data_center": 0.6,
            "brokerage": 0.7,
            "media_lab": 0.7,
            "electronics_shop": 0.7,
            "comms_shop": 0.55,
            "drone_shop": 0.42,
            "wire_shop": 0.72,
        },
        "career_keywords": ("engineer", "compliance", "operator", "specialist"),
        "stock_mult": 0.98,
        "price_mult": 1.08,
    },
    "military": {
        "label": "garrison service zone",
        "family_profile": "barracks staff and patrol families",
        "tag_weights": {"discipline": 1.2, "restricted": 0.9, "medical": 0.8, "tool": 0.4},
        "archetype_weights": {
            "barracks": 1.0,
            "armory": 1.0,
            "checkpoint": 1.0,
            "field_hospital": 0.8,
            "motor_pool": 0.7,
            "recruitment_office": 0.6,
            "supply_bunker": 0.7,
            "comms_shop": 0.35,
            "drone_shop": 0.4,
            "wire_shop": 0.42,
            "outfitter": 0.25,
            "surplus_store": 0.7,
        },
        "career_keywords": ("guard", "officer", "sergeant", "armorer", "medic"),
        "stock_mult": 0.94,
        "price_mult": 1.1,
    },
    "entertainment": {
        "label": "night-trade strip",
        "family_profile": "hospitality workers and late-shift renters",
        "tag_weights": {"drink": 1.2, "social": 1.0, "stimulant": 0.6, "token": 0.4},
        "archetype_weights": {
            "nightclub": 0.9,
            "arcade": 0.7,
            "bar": 0.8,
            "tavern": 0.95,
            "music_venue": 0.8,
            "gaming_hall": 0.7,
            "casino": 0.85,
            "karaoke_box": 0.8,
            "pool_hall": 0.8,
            "gallery": 0.4,
            "electronics_shop": 0.22,
            "wire_shop": 0.24,
        },
        "career_keywords": ("bartender", "dj", "sound", "host", "tour"),
        "stock_mult": 1.04,
        "price_mult": 1.04,
    },
}


TERRAIN_CONTEXTS = {
    "hills": {
        "label": "quarry and haulage town",
        "family_profile": "miners and rig families",
        "tag_weights": {"tool": 1.2, "stimulant": 0.4, "medical": 0.4, "restricted": 0.2},
        "archetype_weights": {
            "warehouse": 0.4,
            "factory": 0.8,
            "machine_shop": 1.0,
            "freight_depot": 0.9,
            "auto_garage": 0.7,
            "outfitter": 0.45,
            "surplus_store": 0.3,
        },
        "career_keywords": ("ore", "quarry", "drill", "smelter", "rig", "haul"),
        "stock_mult": 0.96,
        "price_mult": 1.05,
    },
    "badlands": {
        "label": "pit-road extraction town",
        "family_profile": "miners and convoy families",
        "tag_weights": {"tool": 1.3, "stimulant": 0.5, "medical": 0.3, "food": -0.3},
        "archetype_weights": {
            "factory": 0.9,
            "machine_shop": 1.1,
            "freight_depot": 1.0,
            "auto_garage": 0.8,
            "outfitter": 0.2,
            "surplus_store": 0.75,
        },
        "career_keywords": ("ore", "quarry", "drill", "hauler", "rig"),
        "stock_mult": 0.9,
        "price_mult": 1.08,
    },
    "cliffs": {
        "label": "cliffside rig settlement",
        "family_profile": "rig crews and maintenance families",
        "tag_weights": {"tool": 1.0, "medical": 0.3, "restricted": 0.3},
        "archetype_weights": {"machine_shop": 0.8, "freight_depot": 0.8, "auto_garage": 0.6, "outfitter": 0.25, "surplus_store": 0.45},
        "career_keywords": ("rig", "drill", "technician", "hauler"),
        "stock_mult": 0.93,
        "price_mult": 1.06,
    },
    "shore": {
        "label": "dock and ferry quarter",
        "family_profile": "dockhands and waterside families",
        "tag_weights": {"food": 0.9, "drink": 0.5, "token": 0.4, "medical": 0.2},
        "archetype_weights": {"warehouse": 0.7, "freight_depot": 0.9, "restaurant": 0.5, "hotel": 0.4},
        "career_keywords": ("dock", "route", "freight", "dispatch"),
        "stock_mult": 1.04,
        "price_mult": 0.98,
    },
    "shoals": {
        "label": "tidal freight edge",
        "family_profile": "dockhands and shuttle crews",
        "tag_weights": {"food": 0.7, "drink": 0.4, "token": 0.3},
        "archetype_weights": {"warehouse": 0.6, "freight_depot": 0.8, "hotel": 0.3},
        "career_keywords": ("dock", "freight", "dispatch"),
        "stock_mult": 0.98,
        "price_mult": 1.0,
    },
    "marsh": {
        "label": "wetland fringe town",
        "family_profile": "repair crews and floodplain households",
        "tag_weights": {"medical": 0.6, "food": 0.5, "tool": 0.4},
        "archetype_weights": {"backroom_clinic": 0.5, "recycling_plant": 0.5, "warehouse": 0.3},
        "career_keywords": ("repair", "maintenance", "reclamation"),
        "stock_mult": 0.94,
        "price_mult": 1.04,
    },
    "forest": {
        "label": "timber edge service town",
        "family_profile": "camp families and supply crews",
        "tag_weights": {"food": 0.6, "medical": 0.6, "tool": 0.3},
        "archetype_weights": {"restaurant": 0.4, "pharmacy": 0.5, "auto_garage": 0.3, "outfitter": 0.65},
        "career_keywords": ("supply", "maintenance", "service"),
        "stock_mult": 1.0,
        "price_mult": 1.0,
    },
    "dunes": {
        "label": "caravan and salvage outpost",
        "family_profile": "haulers and salvage families",
        "tag_weights": {"tool": 0.8, "token": 0.4, "food": -0.2, "illegal": 0.4},
        "archetype_weights": {"freight_depot": 0.7, "junk_market": 0.8, "auto_garage": 0.5, "chop_shop": 0.4, "outfitter": 0.2, "surplus_store": 0.5},
        "career_keywords": ("haul", "salvage", "yard", "driver"),
        "stock_mult": 0.9,
        "price_mult": 1.1,
    },
    "salt_flats": {
        "label": "salt-road supply town",
        "family_profile": "haulers and depot families",
        "tag_weights": {"tool": 0.7, "food": -0.2, "token": 0.3},
        "archetype_weights": {"warehouse": 0.5, "freight_depot": 0.8, "auto_garage": 0.4, "surplus_store": 0.35},
        "career_keywords": ("haul", "depot", "driver"),
        "stock_mult": 0.92,
        "price_mult": 1.08,
    },
    "ruins": {
        "label": "ruin-salvage settlement",
        "family_profile": "scrappers and rebuild families",
        "tag_weights": {"tool": 0.9, "illegal": 0.4, "medical": 0.2},
        "archetype_weights": {"junk_market": 0.8, "pawn_shop": 0.6, "recycling_plant": 0.6, "chop_shop": 0.5, "surplus_store": 0.25},
        "career_keywords": ("salvage", "scrap", "repair"),
        "stock_mult": 0.93,
        "price_mult": 1.06,
    },
    "industrial_waste": {
        "label": "reclamation belt",
        "family_profile": "reclaimer crews and hard-luck households",
        "tag_weights": {"medical": 0.8, "tool": 0.7, "illegal": 0.4, "food": -0.2},
        "archetype_weights": {"recycling_plant": 1.0, "backroom_clinic": 0.5, "junk_market": 0.5},
        "career_keywords": ("reclamation", "sorting", "scrap", "hazmat"),
        "stock_mult": 0.9,
        "price_mult": 1.09,
    },
}


LANDMARK_CONTEXTS = {
    "stone_spine": {
        "label": "stone-spine quarry belt",
        "family_profile": "quarry crews and ore-haul families",
        "tag_weights": {"tool": 1.6, "stimulant": 0.5, "medical": 0.4},
        "archetype_weights": {"factory": 1.0, "machine_shop": 1.2, "freight_depot": 1.0, "auto_garage": 0.8, "surplus_store": 0.45},
        "career_keywords": ("ore", "quarry", "drill", "smelter", "haul", "rig"),
        "stock_mult": 0.92,
        "price_mult": 1.08,
    },
    "crater_lake": {
        "label": "reservoir service town",
        "family_profile": "waterfront crews and depot families",
        "tag_weights": {"food": 0.7, "drink": 0.6, "medical": 0.2},
        "archetype_weights": {"warehouse": 0.5, "restaurant": 0.5, "hotel": 0.4},
        "career_keywords": ("route", "dispatch", "service"),
        "stock_mult": 1.03,
        "price_mult": 0.99,
    },
    "shatter_ruins": {
        "label": "shatter-ruins salvage belt",
        "family_profile": "salvagers and patchwork households",
        "tag_weights": {"tool": 1.0, "illegal": 0.5, "medical": 0.3},
        "archetype_weights": {"junk_market": 0.9, "pawn_shop": 0.7, "chop_shop": 0.6, "recycling_plant": 0.8},
        "career_keywords": ("salvage", "scrap", "fence", "repair"),
        "stock_mult": 0.91,
        "price_mult": 1.08,
    },
    "red_dunes": {
        "label": "red-dunes caravan route",
        "family_profile": "haulers and salvage camps",
        "tag_weights": {"tool": 0.9, "token": 0.5, "illegal": 0.3},
        "archetype_weights": {"freight_depot": 0.8, "junk_market": 0.7, "auto_garage": 0.5, "surplus_store": 0.35},
        "career_keywords": ("haul", "driver", "yard", "salvage"),
        "stock_mult": 0.9,
        "price_mult": 1.1,
    },
    "ancient_grove": {
        "label": "grove-edge refuge",
        "family_profile": "camp workers and service families",
        "tag_weights": {"food": 0.6, "medical": 0.7, "drink": 0.3},
        "archetype_weights": {"pharmacy": 0.4, "restaurant": 0.4, "daycare": 0.2, "outfitter": 0.45},
        "career_keywords": ("care", "service", "supply"),
        "stock_mult": 1.0,
        "price_mult": 0.99,
    },
}


INFRASTRUCTURE_CONTEXTS = {
    "power_station": {
        "tag_weights": {"restricted": 0.5, "discipline": 0.5, "tool": 0.5},
        "archetype_weights": {"factory": 0.4, "server_hub": 0.3, "data_center": 0.4},
        "career_keywords": ("engineer", "power", "technician"),
    },
    "network_hub": {
        "tag_weights": {"token": 0.5, "discipline": 0.4, "restricted": 0.3},
        "archetype_weights": {"office": 0.3, "server_hub": 0.4, "data_center": 0.5, "electronics_shop": 0.35, "comms_shop": 0.45, "drone_shop": 0.25, "wire_shop": 0.5},
        "career_keywords": ("network", "operator", "controller"),
    },
    "clinic": {
        "tag_weights": {"medical": 0.8, "food": 0.2},
        "archetype_weights": {"pharmacy": 0.5, "backroom_clinic": 0.6, "field_hospital": 0.4},
        "career_keywords": ("medic", "nurse", "clinical"),
    },
    "police_hub": {
        "tag_weights": {"discipline": 0.7, "restricted": 0.5, "medical": 0.2},
        "archetype_weights": {"checkpoint": 0.6, "armory": 0.5, "courthouse": 0.4},
        "career_keywords": ("guard", "officer", "scanner"),
    },
}


PRESSURE_DEFAULTS = {
    "war_tension": {
        "summary": "worries about war holding up freight",
        "tag_weights": {"restricted": 1.0, "medical": 0.6, "tool": 0.5, "food": -0.3},
        "stock_mult": 0.88,
        "price_mult": 1.12,
    },
    "illness_wave": {
        "summary": "medicine getting harder to find with so many people ill",
        "tag_weights": {"medical": 1.2, "food": 0.3, "drink": -0.2},
        "stock_mult": 0.93,
        "price_mult": 1.08,
    },
    "ambient_contamination": {
        "summary": "contamination making clean supplies harder to find",
        "tag_weights": {"medical": 1.0, "food": -0.5, "drink": -0.3, "tool": 0.2},
        "stock_mult": 0.9,
        "price_mult": 1.09,
    },
    "lucky_currents": {
        "summary": "a lucky run of supplies coming through",
        "tag_weights": {"food": 0.4, "drink": 0.4, "token": 0.3},
        "stock_mult": 1.1,
        "price_mult": 0.94,
    },
}


def _num(value, default):
    try:
        if value is None:
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, lo, hi):
    return max(float(lo), min(float(hi), float(value)))


def _merge_scaled(target, source, scale=1.0):
    if not isinstance(source, dict):
        return
    for key, value in source.items():
        try:
            delta = float(value) * float(scale)
        except (TypeError, ValueError):
            continue
        target[key] = float(target.get(key, 0.0)) + delta


def _merge_keywords(existing, new_values):
    for value in new_values or ():
        text = str(value).strip().lower()
        if text and text not in existing:
            existing.append(text)


def _clock_ticks_per_hour(sim):
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    return max(1, int(_num(clock.get("ticks_per_hour", 600), 600)))


def _local_trade_pressure_state(sim):
    state = getattr(sim, "local_trade_pressures", None)
    if not isinstance(state, dict):
        state = {}
        sim.local_trade_pressures = state
    properties = state.get("properties")
    if not isinstance(properties, dict):
        properties = {}
        state["properties"] = properties
    chunks = state.get("chunks")
    if not isinstance(chunks, dict):
        chunks = {}
        state["chunks"] = chunks
    return state


def _pressure_bucket(container, key):
    key = str(key or "").strip()
    if not key:
        return None
    bucket = container.get(key)
    if not isinstance(bucket, dict):
        bucket = {}
        container[key] = bucket
    for field in ("items", "tags", "shelf_items", "shelf_tags"):
        if not isinstance(bucket.get(field), dict):
            bucket[field] = {}
    return bucket


def _chunk_key(cx, cy):
    return f"{int(cx)},{int(cy)}"


def _chunk_key_for_property(sim, prop):
    if sim is None or not isinstance(prop, dict):
        return ""
    try:
        cx, cy = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except Exception:
        return ""
    return _chunk_key(cx, cy)


def _pressure_decay_factor(sim, last_tick, now_tick=None):
    now_tick = int(getattr(sim, "tick", 0) if now_tick is None else now_tick)
    try:
        elapsed = max(0, now_tick - int(last_tick or 0))
    except (TypeError, ValueError):
        elapsed = 0
    if elapsed <= 0:
        return 1.0
    half_life = max(1, _clock_ticks_per_hour(sim) * LOCAL_TRADE_PRESSURE_HALF_LIFE_HOURS)
    return 0.5 ** (float(elapsed) / float(half_life))


def _decayed_pressure_value(sim, row, now_tick=None):
    if not isinstance(row, dict):
        return 0.0
    return float(_num(row.get("value", 0.0), 0.0)) * _pressure_decay_factor(sim, row.get("last_tick", 0), now_tick=now_tick)


def _decay_pressure_rows(sim, rows, now_tick=None):
    if not isinstance(rows, dict):
        return
    now_tick = int(getattr(sim, "tick", 0) if now_tick is None else now_tick)
    prune_ticks = max(1, _clock_ticks_per_hour(sim) * LOCAL_TRADE_PRESSURE_PRUNE_HOURS)
    for key, row in list(rows.items()):
        if not isinstance(row, dict):
            rows.pop(key, None)
            continue
        value = _decayed_pressure_value(sim, row, now_tick=now_tick)
        try:
            elapsed = max(0, now_tick - int(row.get("last_tick", 0) or 0))
        except (TypeError, ValueError):
            elapsed = 0
        if abs(value) < 0.05 or (elapsed >= prune_ticks and abs(value) < 0.35):
            rows.pop(key, None)
            continue
        row["value"] = round(float(value), 4)
        row["last_tick"] = now_tick


def _decay_pressure_bucket(sim, bucket, now_tick=None):
    if not isinstance(bucket, dict):
        return
    for field in ("items", "tags", "shelf_items", "shelf_tags"):
        _decay_pressure_rows(sim, bucket.get(field), now_tick=now_tick)


def _pressure_tags_for_item(item_id):
    item = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    tags = {
        str(tag or "").strip().lower()
        for tag in tuple(item.get("tags", ()) or ())
        if str(tag or "").strip()
    }
    category = str(item.get("category", "") or "").strip().lower()
    if category:
        tags.add(category)
    legal_status = str(item.get("legal_status", "") or "").strip().lower()
    tags.discard(legal_status)
    return tuple(sorted(tag for tag in tags if tag not in NOISY_TRADE_PRESSURE_TAGS))


def _write_pressure_rows(sim, rows, key, delta, *, item_id="", item_name=""):
    if not isinstance(rows, dict):
        return
    key = str(key or "").strip().lower()
    if not key:
        return
    now_tick = int(getattr(sim, "tick", 0))
    row = rows.get(key)
    if not isinstance(row, dict):
        row = {"value": 0.0, "last_tick": now_tick, "created_tick": now_tick}
        rows[key] = row
    value = _decayed_pressure_value(sim, row, now_tick=now_tick) + float(delta)
    if abs(value) < 0.05:
        rows.pop(key, None)
        return
    row["value"] = round(float(value), 4)
    row["last_tick"] = now_tick
    row.setdefault("created_tick", now_tick)
    if item_id:
        row["item_id"] = str(item_id)
    if item_name:
        row["item_name"] = str(item_name)


def _pressure_direction_value(direction, quantity):
    direction = str(direction or "").strip().lower()
    quantity = max(1, int(_num(quantity, 1)))
    if direction in {"sold_to_store", "trade_sold", "sell", "supply"}:
        return float(quantity)
    if direction in {"bought_from_store", "trade_bought", "buy", "demand"}:
        return -float(quantity)
    return 0.0


def record_local_trade_pressure(sim, prop, item_id, *, quantity=1, direction="", owner_transfer=False, item_name=""):
    """Record a decaying local pressure offset from an actual trade flow."""
    if sim is None or not isinstance(prop, dict):
        return None
    item_id = str(item_id or "").strip().lower()
    property_id = str(prop.get("id", "") or "").strip()
    if not item_id or not property_id:
        return None
    delta = _pressure_direction_value(direction, quantity)
    if abs(delta) <= 0.0:
        return None
    state = _local_trade_pressure_state(sim)
    property_bucket = _pressure_bucket(state["properties"], property_id)
    if property_bucket is None:
        return None
    _decay_pressure_bucket(sim, property_bucket)
    item_name = str(item_name or item_display_name(item_id, item_catalog=ITEM_CATALOG)).strip()
    if owner_transfer:
        _write_pressure_rows(sim, property_bucket["shelf_items"], item_id, delta, item_id=item_id, item_name=item_name)
        for tag in _pressure_tags_for_item(item_id):
            _write_pressure_rows(sim, property_bucket["shelf_tags"], tag, delta * LOCAL_TRADE_TAG_WEIGHT, item_id=item_id, item_name=item_name)
        return {"property_id": property_id, "item_id": item_id, "delta": delta, "chunk_delta": 0.0}

    _write_pressure_rows(sim, property_bucket["items"], item_id, delta * LOCAL_TRADE_PROPERTY_WEIGHT, item_id=item_id, item_name=item_name)
    for tag in _pressure_tags_for_item(item_id):
        _write_pressure_rows(sim, property_bucket["tags"], tag, delta * LOCAL_TRADE_TAG_WEIGHT, item_id=item_id, item_name=item_name)

    chunk_key = _chunk_key_for_property(sim, prop)
    if chunk_key:
        chunk_bucket = _pressure_bucket(state["chunks"], chunk_key)
        _decay_pressure_bucket(sim, chunk_bucket)
        chunk_delta = delta * LOCAL_TRADE_CHUNK_WEIGHT
        _write_pressure_rows(sim, chunk_bucket["items"], item_id, chunk_delta, item_id=item_id, item_name=item_name)
        for tag in _pressure_tags_for_item(item_id):
            _write_pressure_rows(sim, chunk_bucket["tags"], tag, chunk_delta * LOCAL_TRADE_TAG_WEIGHT, item_id=item_id, item_name=item_name)
    else:
        chunk_delta = 0.0
    return {"property_id": property_id, "item_id": item_id, "delta": delta, "chunk_delta": chunk_delta}


def _bucket_value_for_item(sim, bucket, item_id, *, tag_weight=0.32, item_weight=1.0):
    if not isinstance(bucket, dict):
        return 0.0
    item_id = str(item_id or "").strip().lower()
    total = 0.0
    item_row = (bucket.get("items") or {}).get(item_id)
    total += _decayed_pressure_value(sim, item_row) * float(item_weight)
    tag_rows = bucket.get("tags") or {}
    for tag in _pressure_tags_for_item(item_id):
        total += _decayed_pressure_value(sim, tag_rows.get(tag)) * float(tag_weight)
    return float(total)


def _pressure_label(value):
    value = float(value or 0.0)
    if value >= 5.5:
        return "overstocked"
    if value >= 1.6:
        return "well stocked"
    if value <= -4.0:
        return "wanted right now"
    if value <= -1.3:
        return "short here"
    return ""


def _pressure_note_for_label(label):
    label = str(label or "").strip().lower()
    if label == "overstocked":
        return "too much here today"
    if label == "well stocked":
        return "cheap offer"
    if label == "wanted right now":
        return "wanted right now"
    if label == "short here":
        return "short here"
    return ""


def local_trade_pressure_snapshot(sim, prop=None, item_id=None):
    """Return decayed local trade pressure for an item/property without creating pressure."""
    state = _local_trade_pressure_state(sim)
    prop_bucket = None
    chunk_bucket = None
    property_id = ""
    if isinstance(prop, dict):
        property_id = str(prop.get("id", "") or "").strip()
        prop_bucket = state["properties"].get(property_id)
        chunk_key = _chunk_key_for_property(sim, prop)
        chunk_bucket = state["chunks"].get(chunk_key) if chunk_key else None
    if isinstance(prop_bucket, dict):
        _decay_pressure_bucket(sim, prop_bucket)
    if isinstance(chunk_bucket, dict):
        _decay_pressure_bucket(sim, chunk_bucket)
    item_id = str(item_id or "").strip().lower()
    if not item_id:
        return {
            "property_id": property_id,
            "value": 0.0,
            "property_value": 0.0,
            "chunk_value": 0.0,
            "label": "",
            "note": "",
        }
    property_value = _bucket_value_for_item(sim, prop_bucket, item_id, tag_weight=0.36, item_weight=1.0)
    chunk_value = _bucket_value_for_item(sim, chunk_bucket, item_id, tag_weight=0.16, item_weight=LOCAL_TRADE_CHUNK_READ_WEIGHT)
    value = property_value + chunk_value
    label = _pressure_label(value)
    return {
        "property_id": property_id,
        "item_id": item_id,
        "item_name": item_display_name(item_id, item_catalog=ITEM_CATALOG),
        "value": round(float(value), 3),
        "property_value": round(float(property_value), 3),
        "chunk_value": round(float(chunk_value), 3),
        "label": label,
        "note": _pressure_note_for_label(label),
    }


def item_trade_pressure_bias(sim, prop, item_id):
    snapshot = local_trade_pressure_snapshot(sim, prop=prop, item_id=item_id)
    value = float(snapshot.get("value", 0.0) or 0.0)
    oversupply = max(0.0, min(8.0, value))
    shortage = max(0.0, min(6.0, -value))
    sell_price_mult = _clamp(1.0 - (oversupply * 0.04) + (shortage * 0.035), 0.75, 1.2)
    buy_price_mult = _clamp(1.0 - (oversupply * 0.018) + (shortage * 0.032), 0.85, 1.2)
    stock_mult = _clamp(1.0 + (oversupply * 0.055) - (shortage * 0.055), 0.68, 1.38)
    weight_mult = _clamp(1.0 + (oversupply * 0.045) - (shortage * 0.045), 0.72, 1.3)
    return {
        **snapshot,
        "sell_price_mult": round(float(sell_price_mult), 3),
        "buy_price_mult": round(float(buy_price_mult), 3),
        "stock_mult": round(float(stock_mult), 3),
        "weight_mult": round(float(weight_mult), 3),
    }


def local_trade_pressure_notes_for_property(sim, prop, *, limit=2, min_abs=1.6):
    if sim is None or not isinstance(prop, dict):
        return ()
    state = _local_trade_pressure_state(sim)
    property_id = str(prop.get("id", "") or "").strip()
    bucket = state["properties"].get(property_id)
    if not isinstance(bucket, dict):
        return ()
    _decay_pressure_bucket(sim, bucket)
    rows = []
    for item_id, row in tuple((bucket.get("items") or {}).items()):
        value = _decayed_pressure_value(sim, row)
        if abs(value) < float(min_abs):
            continue
        label = _pressure_label(value)
        if not label:
            continue
        item_name = str(row.get("item_name") or item_display_name(item_id, item_catalog=ITEM_CATALOG)).strip()
        rows.append((abs(value), value, item_name, label))
    rows.sort(key=lambda row: (-row[0], row[2]))
    notes = []
    for _abs_value, value, item_name, label in rows[: max(0, int(limit))]:
        if value >= 0:
            notes.append(f"{item_name} {label}")
        else:
            notes.append(f"{item_name} {label}")
    return tuple(notes)


def strongest_local_trade_pressure_for_property(sim, prop, *, min_abs=3.0):
    notes = local_trade_pressure_notes_for_property(sim, prop, limit=1, min_abs=min_abs)
    if not notes:
        return None
    state = _local_trade_pressure_state(sim)
    bucket = state["properties"].get(str(prop.get("id", "") or "").strip())
    best = None
    for item_id, row in tuple((bucket.get("items") or {}).items()):
        value = _decayed_pressure_value(sim, row)
        if abs(value) < float(min_abs):
            continue
        if best is None or abs(value) > abs(best["value"]):
            label = _pressure_label(value)
            best = {
                "item_id": item_id,
                "item_name": str(row.get("item_name") or item_display_name(item_id, item_catalog=ITEM_CATALOG)).strip(),
                "value": round(float(value), 3),
                "label": label,
                "note": _pressure_note_for_label(label),
            }
    return best


class LocalTradePressureSystem(System):
    """Records decaying local economy offsets from completed trade events."""

    def __init__(self, sim):
        super().__init__(sim)
        _local_trade_pressure_state(sim)
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.runs_without_turn = True

    def _property_for_event(self, event):
        property_id = str(event.data.get("property_id", "") or "").strip()
        if not property_id:
            return None
        return getattr(self.sim, "properties", {}).get(property_id)

    def on_trade_bought(self, event):
        if bool(event.data.get("owner_transfer")) or bool(event.data.get("service_stock")):
            return
        if str(event.data.get("transfer_mode", "") or "").strip().lower() == "service":
            return
        prop = self._property_for_event(event)
        record_local_trade_pressure(
            self.sim,
            prop,
            event.data.get("item_id"),
            quantity=event.data.get("quantity", 1),
            direction="bought_from_store",
            item_name=event.data.get("item_name", ""),
        )

    def on_trade_sold(self, event):
        prop = self._property_for_event(event)
        record_local_trade_pressure(
            self.sim,
            prop,
            event.data.get("item_id"),
            quantity=event.data.get("quantity", 1),
            direction="sold_to_store",
            owner_transfer=bool(event.data.get("owner_transfer")),
            item_name=event.data.get("item_name", ""),
        )


def _active_market_pressures(sim):
    traits = getattr(sim, "world_traits", {}) or {}
    raw = traits.get("market_pressures", [])
    if not isinstance(raw, list):
        return []

    pressures = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", entry.get("id", "pressure"))).strip().lower()
        if not status:
            continue
        template = PRESSURE_DEFAULTS.get(status, {})
        intensity = _clamp(_num(entry.get("intensity", 0.5), 0.5), 0.1, 1.4)
        tag_weights = {}
        _merge_scaled(tag_weights, template.get("tag_weights", {}), scale=1.0)
        _merge_scaled(tag_weights, entry.get("tag_weights", {}), scale=1.0)
        stock_mult = _num(template.get("stock_mult", 1.0), 1.0)
        price_mult = _num(template.get("price_mult", 1.0), 1.0)
        stock_shift = (stock_mult - 1.0) * intensity
        price_shift = (price_mult - 1.0) * intensity
        summary = str(entry.get("summary") or template.get("summary") or status.replace("_", " ")).strip()
        pressures.append({
            "status": status,
            "summary": summary,
            "intensity": intensity,
            "tag_weights": tag_weights,
            "stock_mult": 1.0 + stock_shift,
            "price_mult": 1.0 + price_shift,
        })
    return pressures


def chunk_economy_profile(sim, chunk=None):
    chunk = chunk or getattr(sim, "active_chunk", None)
    if not chunk:
        return {
            "area_type": "city",
            "district_type": "unknown",
            "terrain": "urban",
            "context_label": "mixed city blocks",
            "family_profile": "mixed households",
            "pressure_note": "",
            "store_note": "mixed city blocks",
            "chunk_note": "mixed city blocks",
            "tag_weights": {},
            "archetype_weights": {},
            "career_keywords": (),
            "stock_mult": 1.0,
            "price_mult": 1.0,
            "pressures": [],
        }

    district = chunk.get("district", {}) if isinstance(chunk.get("district"), dict) else {}
    area_type = str(district.get("area_type", "city")).strip().lower() or "city"
    district_type = str(district.get("district_type", "unknown")).strip().lower() or "unknown"
    descriptor = sim.world.overworld_descriptor(int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
    terrain = str(descriptor.get("terrain", district.get("terrain", "urban"))).strip().lower() or "urban"
    nearest_landmark = descriptor.get("nearest_landmark", {}) or {}
    landmark_id = ""
    if isinstance(nearest_landmark, dict) and int(nearest_landmark.get("distance", 999)) <= 6:
        landmark_id = str(nearest_landmark.get("id", "")).strip().lower()
    infrastructure = [
        str(node).strip().lower()
        for node in chunk.get("infrastructure", ())
        if str(node).strip()
    ]

    district_context = DISTRICT_CONTEXTS.get(district_type, {})
    terrain_context = TERRAIN_CONTEXTS.get(terrain, {})
    landmark_context = LANDMARK_CONTEXTS.get(landmark_id, {})

    tag_weights = {}
    archetype_weights = {}
    career_keywords = []
    stock_mult = 1.0
    price_mult = 1.0

    for context, scale in (
        (district_context, 1.0),
        (terrain_context, 0.9),
        (landmark_context, 1.05),
    ):
        if not context:
            continue
        _merge_scaled(tag_weights, context.get("tag_weights", {}), scale=scale)
        _merge_scaled(archetype_weights, context.get("archetype_weights", {}), scale=scale)
        _merge_keywords(career_keywords, context.get("career_keywords", ()))
        stock_mult *= 1.0 + ((_num(context.get("stock_mult", 1.0), 1.0) - 1.0) * scale)
        price_mult *= 1.0 + ((_num(context.get("price_mult", 1.0), 1.0) - 1.0) * scale)

    for node in infrastructure:
        context = INFRASTRUCTURE_CONTEXTS.get(node)
        if not context:
            continue
        _merge_scaled(tag_weights, context.get("tag_weights", {}), scale=0.55)
        _merge_scaled(archetype_weights, context.get("archetype_weights", {}), scale=0.55)
        _merge_keywords(career_keywords, context.get("career_keywords", ()))

    pressure_summaries = []
    pressures = _active_market_pressures(sim)
    for pressure in pressures:
        intensity = _clamp(_num(pressure.get("intensity", 0.5), 0.5), 0.1, 1.4)
        _merge_scaled(tag_weights, pressure.get("tag_weights", {}), scale=intensity)
        stock_mult *= 1.0 + ((_num(pressure.get("stock_mult", 1.0), 1.0) - 1.0))
        price_mult *= 1.0 + ((_num(pressure.get("price_mult", 1.0), 1.0) - 1.0))
        summary = str(pressure.get("summary", "")).strip()
        if summary and summary not in pressure_summaries:
            pressure_summaries.append(summary)

    context_label = (
        str(landmark_context.get("label", "")).strip()
        or str(terrain_context.get("label", "")).strip()
        or str(district_context.get("label", "")).strip()
        or f"{district_type} district"
    )
    family_profile = (
        str(landmark_context.get("family_profile", "")).strip()
        or str(terrain_context.get("family_profile", "")).strip()
        or str(district_context.get("family_profile", "")).strip()
        or "mixed households"
    )
    pressure_note = ", ".join(pressure_summaries[:2])
    store_note = context_label if not pressure_note else f"{context_label}; {pressure_note}"
    chunk_note = context_label if not family_profile else f"{context_label}; {family_profile}"

    return {
        "area_type": area_type,
        "district_type": district_type,
        "terrain": terrain,
        "landmark_id": landmark_id,
        "infrastructure": tuple(infrastructure),
        "context_label": context_label,
        "family_profile": family_profile,
        "pressure_note": pressure_note,
        "store_note": store_note,
        "chunk_note": chunk_note,
        "tag_weights": tag_weights,
        "archetype_weights": archetype_weights,
        "career_keywords": tuple(career_keywords),
        "stock_mult": _clamp(stock_mult, 0.72, 1.4),
        "price_mult": _clamp(price_mult, 0.84, 1.28),
        "pressures": pressures,
    }


def store_supply_profile(sim, prop):
    if not prop:
        return chunk_economy_profile(sim)

    x = int(prop.get("x", 0))
    y = int(prop.get("y", 0))
    cx, cy = sim.chunk_coords(x, y)
    chunk = sim.world.get_chunk(cx, cy)
    profile = dict(chunk_economy_profile(sim, chunk))
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
    archetype = str(metadata.get("archetype", "")).strip().lower()

    favored = float(profile.get("archetype_weights", {}).get(archetype, 0.0))
    if favored > 0.0:
        profile["stock_mult"] = _clamp(_num(profile.get("stock_mult", 1.0), 1.0) + min(0.18, favored * 0.08), 0.72, 1.5)
        profile["price_mult"] = _clamp(_num(profile.get("price_mult", 1.0), 1.0) - min(0.08, favored * 0.04), 0.8, 1.3)

    context_label = str(profile.get("context_label", "local trade")).strip() or "local trade"
    pressure_note = str(profile.get("pressure_note", "")).strip()
    local_pressure_note = ", ".join(local_trade_pressure_notes_for_property(sim, prop, limit=2, min_abs=1.8))
    profile["local_trade_pressure_note"] = local_pressure_note
    combined_pressure = ", ".join(bit for bit in (pressure_note, local_pressure_note) if bit)
    profile["pressure_note"] = combined_pressure
    profile["store_note"] = context_label if not combined_pressure else f"{context_label}; {combined_pressure}"
    return profile


def item_market_bias(item_id, market_profile):
    item_def = ITEM_CATALOG.get(item_id, {})
    tags = set(item_def.get("tags", ()))
    legal_status = str(item_def.get("legal_status", "legal")).strip().lower()
    tag_weights = market_profile.get("tag_weights", {}) if isinstance(market_profile, dict) else {}

    signal = 0.0
    for tag, delta in tag_weights.items():
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            continue
        if tag in tags:
            signal += delta
            continue
        if tag in LEGAL_TAGS and legal_status == tag:
            signal += delta

    stock_base = _num(market_profile.get("stock_mult", 1.0), 1.0) if isinstance(market_profile, dict) else 1.0
    price_base = _num(market_profile.get("price_mult", 1.0), 1.0) if isinstance(market_profile, dict) else 1.0
    return {
        "signal": signal,
        "weight_mult": _clamp(1.0 + (signal * 0.18), 0.35, 2.75),
        "stock_mult": _clamp(stock_base + (signal * 0.07), 0.45, 2.35),
        "price_mult": _clamp(price_base - (signal * 0.05), 0.72, 1.55),
    }


def workplace_archetype_weight(economy_profile, archetype):
    if not economy_profile or not archetype:
        return 1.0
    weights = economy_profile.get("archetype_weights", {})
    return _clamp(1.0 + float(weights.get(archetype, 0.0)), 0.35, 2.6)


def _weighted_choice(rng, weighted_rows):
    cleaned = []
    total = 0.0
    for value, weight in weighted_rows:
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            continue
        if weight <= 0.0:
            continue
        cleaned.append((value, weight))
        total += weight

    if not cleaned:
        return None
    if total <= 0.0:
        return cleaned[-1][0]

    pick = rng.uniform(0.0, total)
    running = 0.0
    for value, weight in cleaned:
        running += weight
        if pick <= running:
            return value
    return cleaned[-1][0]


def pick_career_for_workplace(world, rng, archetype=None, economy_profile=None):
    if archetype:
        options = list(world.careers_for_building(archetype))
    else:
        options = list(getattr(world, "career_pool", ()))

    if not options:
        return world.draw_career(rng, preferred_archetype=archetype)

    keywords = tuple(
        str(value).strip().lower()
        for value in (economy_profile or {}).get("career_keywords", ())
        if str(value).strip()
    )
    weighted = []
    for career in options:
        text = str(career).strip().lower()
        weight = 1.0
        for keyword in keywords:
            if keyword and keyword in text:
                weight += 1.4
        weighted.append((career, weight))

    choice = _weighted_choice(rng, weighted)
    if choice:
        return choice
    return rng.choice(options)
