"""Persistent, spatial Texas Hold'em cash tables.

The table owns the hand.  UI code only asks for a public snapshot and submits
an action, which lets the surrounding simulation continue while a player is
watching the felt.
"""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from engine.tilemap import Tile
from game.components import (
    AI,
    CreatureIdentity,
    FinancialProfile,
    Inventory,
    NPCNeeds,
    NPCWill,
    Occupation,
    PlayerAssets,
    Position,
    Vitality,
)
from game.population import _spawn_human
from game.property_access import (
    HOLDEM_CASH_SERVICE_ID,
    site_services_for_property,
    site_services_with_holdem_mode,
)
from game.service_runtime import (
    CASINO_CARD_RANKS,
    CASINO_CARD_SUITS,
    _casino_best_poker_hand,
)
from game.system_support.npc_income_runtime import (
    grant_npc_wallet_credits,
    inventory_liquid_credits,
    spend_npc_wallet_credits,
)


HOLDEM_CASH_MAX_SEATS = 8
HOLDEM_CASH_SMALL_BLIND = 2
HOLDEM_CASH_BIG_BLIND = 4
HOLDEM_CASH_BUY_IN = 40
HOLDEM_CASH_ACTION_DELAY_TICKS = 6
HOLDEM_CASH_PLAYER_CLOCK_TICKS = 300
HOLDEM_CASH_BETWEEN_HAND_TICKS = 14

# Eight real player chairs around a five-by-three table, plus the dealer.
_SEAT_OFFSETS = (
    (-2, -2),
    (2, -2),
    (3, -1),
    (3, 1),
    (2, 2),
    (0, 2),
    (-2, 2),
    (-3, 0),
)
_DEALER_OFFSET = (0, -2)
_TABLE_OFFSETS = tuple((dx, dy) for dy in range(-1, 2) for dx in range(-2, 3))


def _tables(sim, *, create=True):
    state = getattr(sim, "holdem_cash_tables", None)
    if not isinstance(state, dict):
        if not create:
            return {}
        state = {}
        sim.holdem_cash_tables = state
    return state


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _name_for_actor(sim, actor_eid, fallback="Player"):
    if actor_eid is None:
        return fallback
    identity = sim.ecs.get(CreatureIdentity).get(actor_eid)
    if identity is not None:
        name = str(identity.display_name() or "").strip()
        if name:
            return name
    if int(actor_eid) == int(getattr(sim, "player_eid", -1)):
        traits = getattr(sim, "world_traits", {})
        if isinstance(traits, dict):
            name = str(traits.get("character_name", "") or "").strip()
            if name:
                return name
    return fallback


def _property_archetype(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) else None
    return str((metadata or {}).get("archetype", "") or "").strip().lower()


def _table_for_property_id(sim, property_id):
    property_id = str(property_id or "").strip()
    if not property_id:
        return None
    for table in _tables(sim, create=False).values():
        if isinstance(table, dict) and str(table.get("property_id", "")) == property_id:
            return table
    return None


def holdem_cash_table_for_property(sim, prop_or_id, *, ensure=False):
    property_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    table = _table_for_property_id(sim, property_id)
    if table is not None or not ensure:
        return table
    prop = prop_or_id if isinstance(prop_or_id, dict) else getattr(sim, "properties", {}).get(property_id)
    return _create_table_for_property(sim, prop)


def _room_cells_for_property(sim, prop):
    if not isinstance(prop, dict):
        return ()
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    building_id = str(metadata.get("building_id", "") or "").strip()
    if not building_id:
        return ()
    dedicated = []
    preferred = {"gaming_floor", "main_floor"}
    rows = []
    fallback = []
    for (x, y, z), info in getattr(sim, "structure_cells", {}).items():
        if str((info or {}).get("building_id", "") or "").strip() != building_id:
            continue
        tile = sim.tilemap.tile_at(int(x), int(y), int(z))
        if tile is None or not bool(getattr(tile, "walkable", False)):
            continue
        semantic = str(getattr(tile, "semantic_id", "") or "").strip().lower()
        if semantic.startswith("feature_"):
            continue
        row = (int(x), int(y), int(z))
        fallback.append(row)
        room_kind = str((info or {}).get("room_kind", "") or "").strip().lower()
        if room_kind == "poker_room":
            dedicated.append(row)
        elif room_kind in preferred:
            rows.append(row)
    return tuple(dedicated or rows or fallback)


def _set_cash_service_available(prop, available):
    if not isinstance(prop, dict):
        return False
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    before = tuple(site_services_for_property(prop))
    services = site_services_with_holdem_mode(before, live_cash_available=available)
    changed = before != services
    metadata["site_services"] = list(services)
    metadata["site_services_replace_defaults"] = True
    metadata["holdem_cash_available"] = bool(available)
    metadata["holdem_offer_mode"] = "live_cash" if bool(available) else "casino_holdem"
    return changed


def _retrofit_open_gaming_floor(sim, prop):
    """Migrate already-generated casino shells to the new open-floor contract."""
    metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    footprint = metadata.get("footprint") if isinstance(metadata.get("footprint"), dict) else None
    building_id = str(metadata.get("building_id", "") or "").strip()
    if not footprint or not building_id:
        return False
    try:
        left = int(footprint.get("left")) + 1
        right = int(footprint.get("right")) - 1
        top = int(footprint.get("top")) + 1
        bottom = int(footprint.get("bottom")) - 1
        z = int(prop.get("z", 0))
    except (TypeError, ValueError):
        return False
    if right - left + 1 < 7 or bottom - top + 1 < 5:
        return False
    changed = False
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            info = getattr(sim, "structure_cells", {}).get((x, y, z))
            if not isinstance(info, dict) or str(info.get("building_id", "") or "").strip() != building_id:
                continue
            tile = sim.tilemap.tile_at(x, y, z)
            if str(getattr(tile, "glyph", "") or "")[:1] in {"S", "E"}:
                continue
            door_states = getattr(sim, "door_states", None)
            if isinstance(door_states, dict):
                door_states.pop((x, y, z), None)
            sim.tilemap.set_tile(x, y, Tile(
                walkable=True,
                transparent=True,
                glyph=".",
                color="building_fill",
                semantic_id="floor_building_fill",
            ), z=z)
            info["room_index"] = 0
            info["room_kind"] = "gaming_floor" if _property_archetype(prop) == "casino" else "main_floor"
            info["common_area_kind"] = info["room_kind"]
            changed = True
    return changed


def _geometry_at(center, room_set, sim):
    cx, cy, cz = center
    seats = [(cx + dx, cy + dy, cz) for dx, dy in _SEAT_OFFSETS]
    surface = [(cx + dx, cy + dy, cz) for dx, dy in _TABLE_OFFSETS]
    dealer = (cx + _DEALER_OFFSET[0], cy + _DEALER_OFFSET[1], cz)
    required = tuple(seats) + tuple(surface) + (dealer,)
    if any(cell not in room_set for cell in required):
        return None
    for x, y, z in required:
        tile = sim.tilemap.tile_at(x, y, z)
        if tile is None or not bool(getattr(tile, "walkable", False)):
            return None
        glyph = str(getattr(tile, "glyph", "") or "")[:1]
        if glyph in {"S", "E", "+", "'"}:
            return None
    return seats, surface, dealer


def _create_table_for_property(sim, prop):
    if not isinstance(prop, dict) or _property_archetype(prop) not in {"casino", "gaming_hall"}:
        return None
    existing = _table_for_property_id(sim, prop.get("id"))
    if existing is not None:
        _stamp_table(sim, existing)
        return existing

    room_cells = _room_cells_for_property(sim, prop)
    if not room_cells:
        return None
    room_set = set(room_cells)
    avg_x = sum(cell[0] for cell in room_cells) / len(room_cells)
    avg_y = sum(cell[1] for cell in room_cells) / len(room_cells)
    candidates = sorted(room_cells, key=lambda cell: (abs(cell[0] - avg_x) + abs(cell[1] - avg_y), cell[2], cell[1], cell[0]))
    geometry = None
    center = None
    for candidate in candidates:
        geometry = _geometry_at(candidate, room_set, sim)
        if geometry is not None:
            center = candidate
            break
    if geometry is None and _retrofit_open_gaming_floor(sim, prop):
        room_cells = _room_cells_for_property(sim, prop)
        room_set = set(room_cells)
        avg_x = sum(cell[0] for cell in room_cells) / len(room_cells)
        avg_y = sum(cell[1] for cell in room_cells) / len(room_cells)
        candidates = sorted(room_cells, key=lambda cell: (abs(cell[0] - avg_x) + abs(cell[1] - avg_y), cell[2], cell[1], cell[0]))
        for candidate in candidates:
            geometry = _geometry_at(candidate, room_set, sim)
            if geometry is not None:
                center = candidate
                break
    if geometry is None or center is None:
        return None

    seat_cells, surface_cells, dealer_cell = geometry
    table_id = f"holdem_cash:{prop.get('id')}:0"
    seats = []
    for index, (x, y, z) in enumerate(seat_cells):
        seats.append({
            "index": index,
            "x": x,
            "y": y,
            "z": z,
            "actor_eid": None,
            "actor_kind": "",
            "name": "Open",
            "stack": 0,
            "hole": [],
            "folded": False,
            "all_in": False,
            "acted": False,
            "street_bet": 0,
            "total_bet": 0,
            "leaving_after_hand": False,
            "reserved_eid": None,
            "reserved_tick": 0,
            "last_action": "",
        })
    table = {
        "id": table_id,
        "service": HOLDEM_CASH_SERVICE_ID,
        "property_id": prop.get("id"),
        "property_name": str(prop.get("name", "Casino") or "Casino"),
        "center": [int(center[0]), int(center[1]), int(center[2])],
        "surface_cells": [list(cell) for cell in surface_cells],
        "dealer_cell": list(dealer_cell),
        "dealer_eid": None,
        "seats": seats,
        "small_blind": HOLDEM_CASH_SMALL_BLIND,
        "big_blind": HOLDEM_CASH_BIG_BLIND,
        "buy_in": HOLDEM_CASH_BUY_IN,
        "phase": "waiting",
        "hand_number": 0,
        "button": -1,
        "small_blind_seat": None,
        "big_blind_seat": None,
        "acting_seat": None,
        "action_deadline_tick": 0,
        "next_tick": int(getattr(sim, "tick", 0)) + 2,
        "deck": [],
        "board": [],
        "current_bet": 0,
        "min_raise": HOLDEM_CASH_BIG_BLIND,
        "last_raise_size": HOLDEM_CASH_BIG_BLIND,
        "last_aggressor": None,
        "last_hand_summary": "The dealer is opening the table.",
        "showdown_reveal": [],
        "revision": 1,
    }
    _tables(sim)[table_id] = table
    _stamp_table(sim, table)
    sim.emit(Event("holdem_cash_table_opened", table_id=table_id, property_id=prop.get("id"), x=center[0], y=center[1], z=center[2]))
    return table


def _stamp_table(sim, table):
    def _already_stamped(x, y, z, semantic_id, *, walkable):
        tile = sim.tilemap.tile_at(x, y, z)
        return bool(
            tile is not None
            and str(getattr(tile, "semantic_id", "") or "") == semantic_id
            and bool(getattr(tile, "walkable", False)) is bool(walkable)
        )

    def _may_stamp(x, y, z, semantic_id):
        tile = sim.tilemap.tile_at(x, y, z)
        if tile is None:
            return True
        current = str(getattr(tile, "semantic_id", "") or "").strip().lower()
        return current in {"", "floor_building_fill", semantic_id}

    for raw in list(table.get("surface_cells", ()) or ()):
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            continue
        x, y, z = _int(raw[0]), _int(raw[1]), _int(raw[2])
        if _already_stamped(x, y, z, "fixture_holdem_cash_felt", walkable=False):
            continue
        if not _may_stamp(x, y, z, "fixture_holdem_cash_felt"):
            continue
        sim.tilemap.set_tile(x, y, Tile(
            walkable=False,
            transparent=True,
            glyph="=",
            color="casino_felt",
            semantic_id="fixture_holdem_cash_felt",
            layer="fixture",
            priority=34,
        ), z=z)
    for seat in list(table.get("seats", ()) or ()):
        if not isinstance(seat, dict):
            continue
        x, y, z = _int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z"))
        if _already_stamped(x, y, z, "fixture_holdem_cash_seat", walkable=True):
            continue
        if not _may_stamp(x, y, z, "fixture_holdem_cash_seat"):
            continue
        sim.tilemap.set_tile(x, y, Tile(
            walkable=True,
            transparent=True,
            glyph="o",
            color="casino_gold",
            semantic_id="fixture_holdem_cash_seat",
            layer="fixture",
            priority=35,
        ), z=z)
    dealer = table.get("dealer_cell")
    if isinstance(dealer, (list, tuple)) and len(dealer) >= 3:
        x, y, z = _int(dealer[0]), _int(dealer[1]), _int(dealer[2])
        if _already_stamped(x, y, z, "fixture_holdem_cash_dealer", walkable=True):
            return
        if not _may_stamp(x, y, z, "fixture_holdem_cash_dealer"):
            return
        sim.tilemap.set_tile(x, y, Tile(
            walkable=True,
            transparent=True,
            glyph="d",
            color="casino_gold",
            semantic_id="fixture_holdem_cash_dealer",
            layer="fixture",
            priority=35,
        ), z=z)


def holdem_cash_seat_at(sim, x, y, z=0, *, include_surface=True):
    target = (_int(x), _int(y), _int(z))
    for table in _tables(sim, create=False).values():
        if not isinstance(table, dict):
            continue
        for seat in list(table.get("seats", ()) or ()):
            if (_int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z"))) == target:
                return table, seat
        if include_surface:
            for raw in list(table.get("surface_cells", ()) or ()):
                if isinstance(raw, (list, tuple)) and len(raw) >= 3 and tuple(_int(bit) for bit in raw[:3]) == target:
                    return table, None
    return None, None


def _open_seat_near(table, x, y, z):
    candidates = []
    for seat in list(table.get("seats", ()) or ()):
        if seat.get("actor_eid") is not None or seat.get("reserved_eid") is not None:
            continue
        if _int(seat.get("z")) != _int(z):
            continue
        distance = abs(_int(seat.get("x")) - _int(x)) + abs(_int(seat.get("y")) - _int(y))
        candidates.append((distance, _int(seat.get("index")), seat))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][2] if candidates else None


def holdem_cash_interact_at(sim, actor_eid, x, y, z=0):
    table, seat = holdem_cash_seat_at(sim, x, y, z, include_surface=True)
    if table is None:
        return False
    if seat is None:
        seat = _open_seat_near(table, x, y, z)
    if seat is not None and seat.get("actor_eid") is None and seat.get("reserved_eid") is None:
        holdem_cash_join(sim, table, actor_eid, seat_index=seat.get("index"), actor_kind="player")
    sim.emit(Event(
        "holdem_cash_view_request",
        eid=actor_eid,
        table_id=table.get("id"),
        property_id=table.get("property_id"),
    ))
    return True


def _move_actor_to_seat(sim, actor_eid, seat):
    pos = sim.ecs.get(Position).get(actor_eid)
    if pos is None:
        return False
    x, y, z = _int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z"))
    if (int(pos.x), int(pos.y), int(pos.z)) != (x, y, z):
        sim.tilemap.move_entity(actor_eid, pos.x, pos.y, x, y, pos.z, z)
        pos.x, pos.y, pos.z = x, y, z
    return True


def _player_assets(sim, actor_eid):
    return sim.ecs.get(PlayerAssets).get(actor_eid)


def _npc_wallet(sim, actor_eid):
    return inventory_liquid_credits(sim.ecs.get(Inventory).get(actor_eid))


def holdem_cash_join(sim, table_or_id, actor_eid, *, seat_index=None, actor_kind="npc", house_funded=False):
    table = table_or_id if isinstance(table_or_id, dict) else _tables(sim, create=False).get(str(table_or_id))
    if not isinstance(table, dict) or actor_eid is None:
        return {"ok": False, "reason": "missing_table"}
    actor_eid = int(actor_eid)
    for existing in list(table.get("seats", ()) or ()):
        if existing.get("actor_eid") == actor_eid:
            return {"ok": True, "table": table, "seat": existing, "already_seated": True}
    open_seats = [seat for seat in list(table.get("seats", ()) or ()) if seat.get("actor_eid") is None and seat.get("reserved_eid") in {None, actor_eid}]
    if seat_index is not None:
        open_seats = [seat for seat in open_seats if _int(seat.get("index"), -1) == _int(seat_index, -2)]
    if not open_seats:
        return {"ok": False, "reason": "table_full"}
    seat = open_seats[0]
    buy_in = max(_int(table.get("big_blind"), HOLDEM_CASH_BIG_BLIND) * 10, _int(table.get("buy_in"), HOLDEM_CASH_BUY_IN))
    kind = str(actor_kind or "npc").strip().lower()
    if kind == "player":
        assets = _player_assets(sim, actor_eid)
        if assets is None or _int(getattr(assets, "credits", 0)) < buy_in:
            return {"ok": False, "reason": "insufficient_funds", "need": buy_in}
        assets.credits -= buy_in
    elif not house_funded:
        inventory = sim.ecs.get(Inventory).get(actor_eid)
        if _npc_wallet(sim, actor_eid) < buy_in:
            return {"ok": False, "reason": "insufficient_funds", "need": buy_in}
        if spend_npc_wallet_credits(inventory, buy_in) < buy_in:
            return {"ok": False, "reason": "wallet_changed"}

    seat.update({
        "actor_eid": actor_eid,
        "actor_kind": "house_regular" if house_funded else kind,
        "name": _name_for_actor(sim, actor_eid, fallback="Player" if kind == "player" else "Guest"),
        "stack": buy_in,
        "hole": [],
        "folded": False,
        "all_in": False,
        "acted": False,
        "street_bet": 0,
        "total_bet": 0,
        "leaving_after_hand": False,
        "reserved_eid": None,
        "reserved_tick": 0,
        "last_action": "sits in",
    })
    _move_actor_to_seat(sim, actor_eid, seat)
    ai = sim.ecs.get(AI).get(actor_eid)
    will = sim.ecs.get(NPCWill).get(actor_eid)
    if ai is not None:
        ai.state = "playing_poker"
        ai.target = (_int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z")))
        ai.target_eid = None
    if will is not None:
        will.intent = "playing_poker"
        will.target = ai.target if ai is not None else None
        will.target_eid = None
        will.last_tick = _int(getattr(sim, "tick", 0))
    table["revision"] = _int(table.get("revision")) + 1
    sim.emit(Event("holdem_cash_actor_seated", table_id=table.get("id"), property_id=table.get("property_id"), actor_eid=actor_eid, seat_index=seat.get("index"), house_regular=bool(house_funded)))
    return {"ok": True, "table": table, "seat": seat}


def _cash_out(sim, table, seat):
    actor_eid = seat.get("actor_eid")
    if actor_eid is None:
        return 0
    chips = max(0, _int(seat.get("stack")))
    kind = str(seat.get("actor_kind", "") or "").strip().lower()
    if kind == "player":
        assets = _player_assets(sim, actor_eid)
        if assets is not None:
            assets.credits += chips
    elif kind != "house_regular" and chips > 0:
        profile = sim.ecs.get(FinancialProfile).get(actor_eid)
        if profile is not None:
            profile.wallet_buffer = max(
                _int(getattr(profile, "wallet_buffer", 0)),
                _npc_wallet(sim, actor_eid) + chips,
            )
        grant_npc_wallet_credits(
            sim,
            actor_eid,
            chips,
            source="casino_cashout",
            property_id=table.get("property_id"),
            property_name=table.get("property_name", "Casino"),
            emit_event=False,
        )
    ai = sim.ecs.get(AI).get(actor_eid)
    will = sim.ecs.get(NPCWill).get(actor_eid)
    if ai is not None and str(getattr(ai, "state", "") or "") in {"playing_poker", "seeking_poker_table"}:
        ai.state = "idle"
        ai.target = None
        ai.target_eid = None
    if will is not None and str(getattr(will, "intent", "") or "") in {"playing_poker", "seeking_poker_table"}:
        will.intent = "idle"
        will.target = None
        will.target_eid = None
        will.last_tick = _int(getattr(sim, "tick", 0))
    sim.emit(Event("holdem_cash_actor_left", table_id=table.get("id"), property_id=table.get("property_id"), actor_eid=actor_eid, seat_index=seat.get("index"), chips=chips))
    seat.update({
        "actor_eid": None,
        "actor_kind": "",
        "name": "Open",
        "stack": 0,
        "hole": [],
        "folded": False,
        "all_in": False,
        "acted": False,
        "street_bet": 0,
        "total_bet": 0,
        "leaving_after_hand": False,
        "reserved_eid": None,
        "reserved_tick": 0,
        "last_action": "",
    })
    table["revision"] = _int(table.get("revision")) + 1
    return chips


def holdem_cash_leave(sim, table_or_id, actor_eid, *, immediate=False):
    table = table_or_id if isinstance(table_or_id, dict) else _tables(sim, create=False).get(str(table_or_id))
    if not isinstance(table, dict):
        return {"ok": False, "reason": "missing_table"}
    seat = next((row for row in list(table.get("seats", ()) or ()) if row.get("actor_eid") == actor_eid), None)
    if seat is None:
        return {"ok": False, "reason": "not_seated"}
    in_hand = bool(seat.get("hole")) and str(table.get("phase", "waiting")) not in {"waiting", "settling"}
    if in_hand and immediate:
        seat["folded"] = True
        seat["acted"] = True
        seat["last_action"] = "stands and folds"
        seat["leaving_after_hand"] = True
        table["revision"] = _int(table.get("revision")) + 1
        return {"ok": True, "pending": True}
    if in_hand:
        seat["leaving_after_hand"] = True
        seat["last_action"] = "leaving after hand"
        table["revision"] = _int(table.get("revision")) + 1
        return {"ok": True, "pending": True}
    chips = _cash_out(sim, table, seat)
    return {"ok": True, "chips": chips}


def _occupied(table, *, eligible=False):
    rows = [seat for seat in list(table.get("seats", ()) or ()) if seat.get("actor_eid") is not None]
    if eligible:
        rows = [seat for seat in rows if _int(seat.get("stack")) > 0 and not bool(seat.get("leaving_after_hand"))]
    return rows


def _seat_map(table):
    return {_int(seat.get("index")): seat for seat in list(table.get("seats", ()) or ())}


def _next_seat_index(table, start, predicate):
    seats = _seat_map(table)
    for offset in range(1, HOLDEM_CASH_MAX_SEATS + 1):
        index = (_int(start) + offset) % HOLDEM_CASH_MAX_SEATS
        seat = seats.get(index)
        if seat is not None and predicate(seat):
            return index
    return None


def _post_blind(seat, amount):
    paid = min(max(0, _int(amount)), max(0, _int(seat.get("stack"))))
    seat["stack"] = _int(seat.get("stack")) - paid
    seat["street_bet"] = _int(seat.get("street_bet")) + paid
    seat["total_bet"] = _int(seat.get("total_bet")) + paid
    seat["all_in"] = _int(seat.get("stack")) <= 0
    seat["last_action"] = f"posts {paid}"
    return paid


def _fresh_deck(table, sim):
    deck = [f"{rank}{suit}" for suit in CASINO_CARD_SUITS for rank in CASINO_CARD_RANKS]
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:{table.get('id')}:{_int(table.get('hand_number'))}:cash_holdem")
    rng.shuffle(deck)
    return deck


def _draw(table, count):
    cards = []
    deck = table.get("deck") if isinstance(table.get("deck"), list) else []
    for _ in range(max(0, _int(count))):
        if deck:
            cards.append(deck.pop())
    return cards


def _start_hand(sim, table):
    eligible = _occupied(table, eligible=True)
    if len(eligible) < 2:
        table["phase"] = "waiting"
        table["acting_seat"] = None
        table["last_hand_summary"] = "Waiting for another player."
        table["next_tick"] = _int(getattr(sim, "tick", 0)) + 8
        table["revision"] = _int(table.get("revision")) + 1
        return False
    table["hand_number"] = _int(table.get("hand_number")) + 1
    table["button"] = _next_seat_index(table, table.get("button", -1), lambda seat: seat in eligible)
    button = _int(table.get("button"), -1)
    table["deck"] = _fresh_deck(table, sim)
    table["board"] = []
    table["showdown_reveal"] = []
    table["phase"] = "preflop"
    table["current_bet"] = 0
    table["min_raise"] = _int(table.get("big_blind"), HOLDEM_CASH_BIG_BLIND)
    table["last_raise_size"] = _int(table.get("big_blind"), HOLDEM_CASH_BIG_BLIND)
    table["last_aggressor"] = None
    for seat in list(table.get("seats", ()) or ()):
        seat["hole"] = _draw(table, 2) if seat in eligible else []
        seat["folded"] = seat not in eligible
        seat["all_in"] = False
        seat["acted"] = False
        seat["street_bet"] = 0
        seat["total_bet"] = 0
        seat["last_action"] = ""
    if len(eligible) == 2:
        sb_index = button
        bb_index = _next_seat_index(table, sb_index, lambda seat: seat in eligible)
    else:
        sb_index = _next_seat_index(table, button, lambda seat: seat in eligible)
        bb_index = _next_seat_index(table, sb_index, lambda seat: seat in eligible)
    table["small_blind_seat"] = sb_index
    table["big_blind_seat"] = bb_index
    seats = _seat_map(table)
    _post_blind(seats[sb_index], table.get("small_blind"))
    posted_big = _post_blind(seats[bb_index], table.get("big_blind"))
    table["current_bet"] = posted_big
    table["last_aggressor"] = bb_index
    if len(eligible) == 2:
        first = sb_index
    else:
        first = _next_seat_index(table, bb_index, lambda seat: seat in eligible and not seat.get("all_in"))
    table["acting_seat"] = first
    _set_action_clock(sim, table)
    table["last_hand_summary"] = f"Hand {table['hand_number']}: blinds {table.get('small_blind')}/{table.get('big_blind')}."
    table["revision"] = _int(table.get("revision")) + 1
    sim.emit(Event("holdem_cash_hand_started", table_id=table.get("id"), property_id=table.get("property_id"), hand_number=table.get("hand_number"), button=button))
    return True


def _set_action_clock(sim, table):
    seat = _seat_map(table).get(table.get("acting_seat"))
    delay = HOLDEM_CASH_ACTION_DELAY_TICKS
    if seat is not None and str(seat.get("actor_kind", "")) == "player":
        delay = HOLDEM_CASH_PLAYER_CLOCK_TICKS
    table["action_deadline_tick"] = _int(getattr(sim, "tick", 0)) + delay


def _can_act(seat):
    return bool(seat and seat.get("actor_eid") is not None and not seat.get("folded") and not seat.get("all_in") and seat.get("hole"))


def holdem_cash_legal_actions(table, actor_eid):
    seat = next((row for row in list(table.get("seats", ()) or ()) if row.get("actor_eid") == actor_eid), None)
    if seat is None or _int(table.get("acting_seat"), -1) != _int(seat.get("index"), -2) or not _can_act(seat):
        return []
    to_call = max(0, _int(table.get("current_bet")) - _int(seat.get("street_bet")))
    stack = max(0, _int(seat.get("stack")))
    actions = ["fold"]
    actions.append("check" if to_call <= 0 else "call")
    minimum_total = _int(table.get("current_bet")) + max(_int(table.get("last_raise_size")), _int(table.get("big_blind")))
    if stack > to_call and _int(seat.get("street_bet")) + stack >= minimum_total:
        actions.extend(["raise_small", "raise_pot", "all_in"])
    elif stack > to_call:
        actions.append("all_in")
    return actions


def _betting_round_complete(table):
    contenders = [seat for seat in _occupied(table) if seat.get("hole") and not seat.get("folded")]
    live = [seat for seat in contenders if not seat.get("all_in")]
    if len(contenders) <= 1:
        return True
    return all(bool(seat.get("acted")) and _int(seat.get("street_bet")) == _int(table.get("current_bet")) for seat in live)


def _advance_actor(sim, table, from_index):
    if _betting_round_complete(table):
        _advance_street_or_showdown(sim, table)
        return
    next_index = _next_seat_index(table, from_index, _can_act)
    table["acting_seat"] = next_index
    if next_index is None:
        _advance_street_or_showdown(sim, table)
        return
    _set_action_clock(sim, table)


def holdem_cash_submit_action(sim, table_or_id, actor_eid, action):
    table = table_or_id if isinstance(table_or_id, dict) else _tables(sim, create=False).get(str(table_or_id))
    if not isinstance(table, dict):
        return {"ok": False, "reason": "missing_table"}
    seats = list(table.get("seats", ()) or ())
    seat = next((row for row in seats if row.get("actor_eid") == actor_eid), None)
    if seat is None or _int(table.get("acting_seat"), -1) != _int(seat.get("index"), -2):
        return {"ok": False, "reason": "not_your_turn"}
    action = str(action or "").strip().lower()
    legal = holdem_cash_legal_actions(table, actor_eid)
    if action not in legal:
        return {"ok": False, "reason": "illegal_action", "legal": legal}
    current_bet = _int(table.get("current_bet"))
    seat_bet = _int(seat.get("street_bet"))
    stack = _int(seat.get("stack"))
    to_call = max(0, current_bet - seat_bet)
    paid = 0
    if action == "fold":
        seat["folded"] = True
        seat["acted"] = True
        seat["last_action"] = "folds"
    elif action in {"check", "call"}:
        paid = min(stack, to_call)
        seat["stack"] = stack - paid
        seat["street_bet"] = seat_bet + paid
        seat["total_bet"] = _int(seat.get("total_bet")) + paid
        seat["all_in"] = _int(seat.get("stack")) <= 0
        seat["acted"] = True
        seat["last_action"] = "checks" if paid <= 0 else (f"calls {paid}" if paid == to_call else f"calls all-in {paid}")
    else:
        if action == "all_in":
            target_total = seat_bet + stack
        elif action == "raise_pot":
            pot = sum(_int(row.get("total_bet")) for row in seats)
            target_total = current_bet + max(_int(table.get("last_raise_size")), pot + to_call)
        else:
            target_total = current_bet + max(_int(table.get("last_raise_size")), _int(table.get("big_blind")) * 2)
        target_total = min(seat_bet + stack, target_total)
        paid = max(0, target_total - seat_bet)
        previous_bet = current_bet
        seat["stack"] = stack - paid
        seat["street_bet"] = target_total
        seat["total_bet"] = _int(seat.get("total_bet")) + paid
        seat["all_in"] = _int(seat.get("stack")) <= 0
        seat["acted"] = True
        if target_total > previous_bet:
            raise_size = target_total - previous_bet
            full_raise = raise_size >= max(_int(table.get("last_raise_size")), _int(table.get("big_blind")))
            table["current_bet"] = target_total
            table["last_aggressor"] = seat.get("index")
            if full_raise:
                table["last_raise_size"] = raise_size
                for other in seats:
                    if other is not seat and _can_act(other):
                        other["acted"] = False
            seat["last_action"] = f"raises to {target_total}" if not seat.get("all_in") else f"raises all-in to {target_total}"
        else:
            seat["last_action"] = f"calls all-in {paid}"
    table["last_hand_summary"] = f"{seat.get('name', 'Player')} {seat.get('last_action', action)}."
    table["revision"] = _int(table.get("revision")) + 1
    sim.emit(Event("holdem_cash_action", table_id=table.get("id"), property_id=table.get("property_id"), actor_eid=actor_eid, seat_index=seat.get("index"), action=action, paid=paid, phase=table.get("phase")))
    _advance_actor(sim, table, _int(seat.get("index")))
    return {"ok": True, "table": table}


def _remaining_contenders(table):
    return [seat for seat in _occupied(table) if seat.get("hole") and not seat.get("folded")]


def _advance_street_or_showdown(sim, table):
    contenders = _remaining_contenders(table)
    if len(contenders) <= 1:
        _settle_showdown(sim, table)
        return
    phase = str(table.get("phase", "preflop"))
    if phase == "preflop":
        _draw(table, 1)  # burn
        table["board"].extend(_draw(table, 3))
        next_phase = "flop"
    elif phase == "flop":
        _draw(table, 1)
        table["board"].extend(_draw(table, 1))
        next_phase = "turn"
    elif phase == "turn":
        _draw(table, 1)
        table["board"].extend(_draw(table, 1))
        next_phase = "river"
    else:
        _settle_showdown(sim, table)
        return
    table["phase"] = next_phase
    table["current_bet"] = 0
    table["last_raise_size"] = _int(table.get("big_blind"), HOLDEM_CASH_BIG_BLIND)
    table["last_aggressor"] = None
    for seat in list(table.get("seats", ()) or ()):
        seat["street_bet"] = 0
        seat["acted"] = False if _can_act(seat) else True
        if seat.get("hole") and not seat.get("folded"):
            seat["last_action"] = ""
    first = _next_seat_index(table, table.get("button", -1), _can_act)
    table["acting_seat"] = first
    table["last_hand_summary"] = f"{next_phase.title()}: the board is {' '.join(table.get('board', ())) }."
    table["revision"] = _int(table.get("revision")) + 1
    if first is None:
        _advance_street_or_showdown(sim, table)
    else:
        _set_action_clock(sim, table)


def _side_pots(table):
    contributors = [seat for seat in _occupied(table) if _int(seat.get("total_bet")) > 0]
    levels = sorted({_int(seat.get("total_bet")) for seat in contributors if _int(seat.get("total_bet")) > 0})
    pots = []
    previous = 0
    for level in levels:
        involved = [seat for seat in contributors if _int(seat.get("total_bet")) >= level]
        amount = (level - previous) * len(involved)
        eligible = [seat for seat in involved if not seat.get("folded")]
        if amount > 0 and eligible:
            pots.append({"amount": amount, "eligible": eligible})
        previous = level
    return pots


def _seat_order_from_button(table, seats):
    by_index = {_int(seat.get("index")): seat for seat in seats}
    ordered = []
    start = _int(table.get("button"), -1)
    for offset in range(1, HOLDEM_CASH_MAX_SEATS + 1):
        seat = by_index.get((start + offset) % HOLDEM_CASH_MAX_SEATS)
        if seat is not None:
            ordered.append(seat)
    return ordered


def _settle_showdown(sim, table):
    contenders = _remaining_contenders(table)
    awards = {}
    hand_names = {}
    scores = {}
    if len(contenders) == 1:
        lone = contenders[0]
        total = sum(_int(seat.get("total_bet")) for seat in _occupied(table))
        awards[_int(lone.get("index"))] = total
        summary = f"{lone.get('name', 'Player')} wins {total} uncontested."
        reveal = []
    else:
        for seat in contenders:
            hand = _casino_best_poker_hand(list(seat.get("hole", ())) + list(table.get("board", ())))
            scores[_int(seat.get("index"))] = tuple(hand.get("score", (0, 0)))
            hand_names[_int(seat.get("index"))] = str(hand.get("name", "hand"))
        for pot in _side_pots(table):
            eligible = list(pot.get("eligible", ()))
            best = max(scores[_int(seat.get("index"))] for seat in eligible)
            winners = [seat for seat in eligible if scores[_int(seat.get("index"))] == best]
            ordered = _seat_order_from_button(table, winners)
            share, odd = divmod(_int(pot.get("amount")), len(winners))
            for seat in winners:
                index = _int(seat.get("index"))
                awards[index] = awards.get(index, 0) + share
            for seat in ordered[:odd]:
                index = _int(seat.get("index"))
                awards[index] = awards.get(index, 0) + 1
        reveal = [_int(seat.get("index")) for seat in contenders]
        winner_bits = []
        for index, amount in sorted(awards.items()):
            seat = _seat_map(table).get(index, {})
            winner_bits.append(f"{seat.get('name', 'Player')} {amount} with {hand_names.get(index, 'a hand')}")
        summary = "Showdown: " + "; ".join(winner_bits) + "."
    for index, amount in awards.items():
        seat = _seat_map(table).get(index)
        if seat is not None:
            seat["stack"] = _int(seat.get("stack")) + _int(amount)
            seat["last_action"] = f"wins {_int(amount)}"
    table["showdown_reveal"] = reveal
    table["phase"] = "settling"
    table["acting_seat"] = None
    table["last_hand_summary"] = summary
    table["next_tick"] = _int(getattr(sim, "tick", 0)) + HOLDEM_CASH_BETWEEN_HAND_TICKS
    table["revision"] = _int(table.get("revision")) + 1
    sim.emit(Event("holdem_cash_hand_settled", table_id=table.get("id"), property_id=table.get("property_id"), hand_number=table.get("hand_number"), summary=summary, awards=dict(awards)))


def _finish_settlement(sim, table):
    for seat in list(table.get("seats", ()) or ()):
        seat["hole"] = []
        seat["street_bet"] = 0
        seat["total_bet"] = 0
        seat["folded"] = False
        seat["all_in"] = False
        seat["acted"] = False
    table["board"] = []
    table["showdown_reveal"] = []
    for seat in list(table.get("seats", ()) or ()):
        if seat.get("actor_eid") is None:
            continue
        if seat.get("leaving_after_hand") or (_int(seat.get("stack")) <= 0 and str(seat.get("actor_kind", "")) != "house_regular"):
            _cash_out(sim, table, seat)
        elif str(seat.get("actor_kind", "")) == "house_regular" and _int(seat.get("stack")) < _int(table.get("big_blind")) * 10:
            seat["stack"] = _int(table.get("buy_in"), HOLDEM_CASH_BUY_IN)
            seat["last_action"] = "buys back in"
    table["phase"] = "waiting"
    table["next_tick"] = _int(getattr(sim, "tick", 0)) + 2
    table["revision"] = _int(table.get("revision")) + 1


def _preflop_strength(hole):
    hole = list(hole or ())
    if len(hole) < 2:
        return 0.0
    rank_map = {rank: index + 2 for index, rank in enumerate(CASINO_CARD_RANKS)}
    a = rank_map.get(str(hole[0])[:1], 0)
    b = rank_map.get(str(hole[1])[:1], 0)
    high, low = max(a, b), min(a, b)
    score = (high + low) / 28.0
    if high == low:
        score += 0.34 + (high / 70.0)
    if str(hole[0])[1:2] == str(hole[1])[1:2]:
        score += 0.08
    gap = max(0, high - low - 1)
    score += max(0.0, 0.08 - gap * 0.025)
    return max(0.0, min(1.0, score))


def _npc_action(sim, table, seat):
    to_call = max(0, _int(table.get("current_bet")) - _int(seat.get("street_bet")))
    pot = max(1, sum(_int(row.get("total_bet")) for row in list(table.get("seats", ()) or ())))
    if str(table.get("phase")) == "preflop":
        strength = _preflop_strength(seat.get("hole"))
    else:
        visible = list(seat.get("hole", ())) + list(table.get("board", ()))
        hand = _casino_best_poker_hand(visible) if len(visible) >= 5 else {"score": (0, 0)}
        category = _int((hand.get("score") or (0,))[0])
        strength = min(1.0, 0.16 + category * 0.12 + _preflop_strength(seat.get("hole")) * 0.22)
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:{table.get('id')}:{table.get('hand_number')}:{table.get('phase')}:{seat.get('index')}:{seat.get('total_bet')}")
    jitter = rng.uniform(-0.11, 0.11)
    pressure = to_call / max(1.0, pot + to_call)
    legal = holdem_cash_legal_actions(table, seat.get("actor_eid"))
    if to_call > 0 and strength + jitter < pressure + 0.18 and "fold" in legal:
        return "fold"
    if strength + jitter > 0.76:
        for candidate in ("raise_pot", "raise_small", "all_in"):
            if candidate in legal:
                return candidate
    if strength + jitter > 0.58 and rng.random() < 0.34:
        for candidate in ("raise_small", "raise_pot"):
            if candidate in legal:
                return candidate
    return "check" if "check" in legal else ("call" if "call" in legal else legal[0])


def holdem_cash_public_snapshot(sim, table_or_id, viewer_eid=None):
    table = table_or_id if isinstance(table_or_id, dict) else _tables(sim, create=False).get(str(table_or_id))
    if not isinstance(table, dict):
        return None
    reveal = {_int(index) for index in list(table.get("showdown_reveal", ()) or ())}
    seats = []
    for seat in list(table.get("seats", ()) or ()):
        actor_eid = seat.get("actor_eid")
        shown = actor_eid == viewer_eid or _int(seat.get("index")) in reveal
        hole = list(seat.get("hole", ()) or ())
        seats.append({
            "index": _int(seat.get("index")),
            "x": _int(seat.get("x")),
            "y": _int(seat.get("y")),
            "z": _int(seat.get("z")),
            "actor_eid": actor_eid,
            "name": str(seat.get("name", "Open") or "Open"),
            "stack": _int(seat.get("stack")),
            "cards": hole if shown else (["??", "??"] if hole else []),
            "folded": bool(seat.get("folded")),
            "all_in": bool(seat.get("all_in")),
            "button": _int(table.get("button"), -1) == _int(seat.get("index")),
            "acting": _int(table.get("acting_seat"), -1) == _int(seat.get("index")),
            "street_bet": _int(seat.get("street_bet")),
            "total_bet": _int(seat.get("total_bet")),
            "last_action": str(seat.get("last_action", "") or ""),
            "leaving_after_hand": bool(seat.get("leaving_after_hand")),
        })
    hero = next((seat for seat in seats if seat.get("actor_eid") == viewer_eid), None)
    return {
        "service": HOLDEM_CASH_SERVICE_ID,
        "table_id": table.get("id"),
        "property_id": table.get("property_id"),
        "phase": table.get("phase", "waiting"),
        "hand_number": _int(table.get("hand_number")),
        "small_blind": _int(table.get("small_blind")),
        "big_blind": _int(table.get("big_blind")),
        "buy_in": _int(table.get("buy_in")),
        "board": list(table.get("board", ()) or ()),
        "pot": sum(_int(seat.get("total_bet")) for seat in list(table.get("seats", ()) or ())),
        "current_bet": _int(table.get("current_bet")),
        "acting_seat": table.get("acting_seat"),
        "action_deadline_tick": _int(table.get("action_deadline_tick")),
        "last_hand_summary": str(table.get("last_hand_summary", "") or ""),
        "seats": seats,
        "hero_seat": hero.get("index") if isinstance(hero, dict) else None,
        "hero_cards": list(hero.get("cards", ())) if isinstance(hero, dict) else [],
        "legal_actions": holdem_cash_legal_actions(table, viewer_eid) if viewer_eid is not None else [],
        "revision": _int(table.get("revision")),
    }


class HoldemCashSystem(System):
    """Owns spatial tables, house starters, NPC attendance, and live hands."""

    runs_without_turn = True

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("npc_holdem_seat_arrived", self.on_npc_seat_arrived)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self._next_property_scan_tick = 0
        self._next_guest_scan_tick = 0

    def update(self):
        tick = _int(getattr(self.sim, "tick", 0))
        if tick >= self._next_property_scan_tick:
            self._ensure_loaded_tables()
            self._next_property_scan_tick = tick + 24
        if tick >= self._next_guest_scan_tick:
            self._invite_guests()
            self._next_guest_scan_tick = tick + 60
        for table in list(_tables(self.sim, create=False).values()):
            if not isinstance(table, dict):
                continue
            self._reassert_seated_actors(table)
            self._expire_reservations(table)
            self._advance_table(table, tick)

    def _ensure_loaded_tables(self):
        for prop in list(getattr(self.sim, "properties", {}).values()):
            if _property_archetype(prop) not in {"casino", "gaming_hall"}:
                continue
            table = holdem_cash_table_for_property(self.sim, prop, ensure=True)
            if table is None:
                _set_cash_service_available(prop, False)
                continue
            _set_cash_service_available(prop, True)
            _stamp_table(self.sim, table)
            self._ensure_dealer(table, prop)
            self._ensure_house_regulars(table, prop)

    def _spawn_staff(self, table, prop, *, career, position):
        rng = random.Random(f"{getattr(self.sim, 'seed', 0)}:{table.get('id')}:{career}:{position}")
        eid = _spawn_human(
            self.sim,
            rng,
            "civilian",
            tuple(position),
            career=career,
            workplace=prop.get("id"),
            home=tuple(position),
            work=tuple(position),
            shift_window=(0, 0),
            workplace_prop=prop,
        )
        if str(career or "").strip().lower() == "proposition_player":
            identity = self.sim.ecs.get(CreatureIdentity).get(eid)
            if identity is not None:
                # The employment relationship exists, but the person reads as
                # an ordinary patron unless the player uncovers it socially.
                identity.common_name = "casino patron"
        return eid

    def _ensure_dealer(self, table, prop):
        dealer_eid = table.get("dealer_eid")
        if dealer_eid is not None and self.sim.ecs.get(Position).get(dealer_eid) is not None:
            return
        cell = table.get("dealer_cell")
        if not isinstance(cell, (list, tuple)) or len(cell) < 3:
            return
        if self.sim.tilemap.entities_at(_int(cell[0]), _int(cell[1]), _int(cell[2])):
            return
        dealer_eid = self._spawn_staff(table, prop, career="table_dealer", position=cell[:3])
        table["dealer_eid"] = dealer_eid
        ai = self.sim.ecs.get(AI).get(dealer_eid)
        will = self.sim.ecs.get(NPCWill).get(dealer_eid)
        if ai is not None:
            ai.state = "playing_poker"
            ai.target = tuple(cell[:3])
        if will is not None:
            will.intent = "playing_poker"
            will.target = tuple(cell[:3])
        table["revision"] = _int(table.get("revision")) + 1

    def _ensure_house_regulars(self, table, prop):
        current = [seat for seat in _occupied(table) if str(seat.get("actor_kind", "")) == "house_regular"]
        organic_count = len([seat for seat in _occupied(table) if str(seat.get("actor_kind", "")) != "house_regular"])
        target_regulars = 1 if organic_count >= 5 else 2
        if len(current) > target_regulars:
            if not bool(current[-1].get("leaving_after_hand")):
                current[-1]["leaving_after_hand"] = True
                current[-1]["last_action"] = "racking up after the hand"
                table["revision"] = _int(table.get("revision")) + 1
        for _ in range(max(0, target_regulars - len(current))):
            seat = next((row for row in list(table.get("seats", ()) or ()) if row.get("actor_eid") is None and row.get("reserved_eid") is None), None)
            if seat is None:
                return
            if self.sim.tilemap.entities_at(_int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z"))):
                continue
            eid = self._spawn_staff(
                table,
                prop,
                career="proposition_player",
                position=(_int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z"))),
            )
            holdem_cash_join(self.sim, table, eid, seat_index=seat.get("index"), actor_kind="npc", house_funded=True)

    def _reassert_seated_actors(self, table):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        vitalities = self.sim.ecs.get(Vitality)
        dealer_eid = table.get("dealer_eid")
        dealer_cell = table.get("dealer_cell")
        dealer_pos = positions.get(dealer_eid) if dealer_eid is not None else None
        if dealer_pos is not None and isinstance(dealer_cell, (list, tuple)) and len(dealer_cell) >= 3:
            target = (_int(dealer_cell[0]), _int(dealer_cell[1]), _int(dealer_cell[2]))
            dealer_ai = ais.get(dealer_eid)
            dealer_will = wills.get(dealer_eid)
            at_station = (int(dealer_pos.x), int(dealer_pos.y), int(dealer_pos.z)) == target
            emergency = str(getattr(dealer_ai, "state", "") or "") in {"protecting", "chasing", "seeking_safety", "seeking_medical_aid"}
            if dealer_ai is not None and not emergency:
                dealer_ai.state = "playing_poker" if at_station else "working"
                dealer_ai.target = target
                dealer_ai.target_eid = None
            if dealer_will is not None and not emergency:
                dealer_will.intent = "playing_poker" if at_station else "working"
                dealer_will.target = target
                dealer_will.target_eid = None
                dealer_will.last_tick = _int(getattr(self.sim, "tick", 0))
        for seat in list(table.get("seats", ()) or ()):
            eid = seat.get("actor_eid")
            if eid is None:
                continue
            pos = positions.get(eid)
            if pos is None:
                continue  # actor may be held in a streamed chunk snapshot
            vitality = vitalities.get(eid)
            interrupted = bool(vitality and (getattr(vitality, "downed", False) or _int(getattr(vitality, "hp", 1)) <= 0))
            on_seat = (int(pos.x), int(pos.y), int(pos.z)) == (_int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z")))
            if interrupted or not on_seat:
                if seat.get("hole") and not seat.get("folded"):
                    seat["folded"] = True
                    seat["acted"] = True
                    seat["leaving_after_hand"] = True
                    seat["last_action"] = "is pulled away and folds"
                else:
                    seat["leaving_after_hand"] = True
                table["revision"] = _int(table.get("revision")) + 1
                continue
            if str(seat.get("actor_kind", "")) == "player":
                continue
            ai = ais.get(eid)
            will = wills.get(eid)
            if ai is not None and str(getattr(ai, "state", "") or "") not in {"protecting", "chasing", "seeking_safety", "seeking_medical_aid"}:
                ai.state = "playing_poker"
                ai.target = (int(pos.x), int(pos.y), int(pos.z))
                ai.target_eid = None
            if will is not None and str(getattr(ai, "state", "") or "") == "playing_poker":
                will.intent = "playing_poker"
                will.target = (int(pos.x), int(pos.y), int(pos.z))
                will.target_eid = None
                will.last_tick = _int(getattr(self.sim, "tick", 0))

    def _expire_reservations(self, table):
        now = _int(getattr(self.sim, "tick", 0))
        for seat in list(table.get("seats", ()) or ()):
            reserved = seat.get("reserved_eid")
            if reserved is None:
                continue
            if now - _int(seat.get("reserved_tick")) <= 120:
                continue
            seat["reserved_eid"] = None
            seat["reserved_tick"] = 0
            table["revision"] = _int(table.get("revision")) + 1

    def _invite_guests(self):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        identities = self.sim.ecs.get(CreatureIdentity)
        occupations = self.sim.ecs.get(Occupation)
        needs_map = self.sim.ecs.get(NPCNeeds)
        seated = {seat.get("actor_eid") for table in _tables(self.sim, create=False).values() for seat in list(table.get("seats", ()) or ()) if isinstance(seat, dict)}
        dealers = {table.get("dealer_eid") for table in _tables(self.sim, create=False).values() if isinstance(table, dict)}
        for table in list(_tables(self.sim, create=False).values()):
            prop = getattr(self.sim, "properties", {}).get(table.get("property_id"))
            if not isinstance(prop, dict) or len(_occupied(table)) >= HOLDEM_CASH_MAX_SEATS:
                continue
            center = table.get("center", (0, 0, 0))
            candidates = []
            for eid, pos in positions.items():
                if eid in seated or eid in dealers or eid == getattr(self.sim, "player_eid", None):
                    continue
                ai = ais.get(eid)
                identity = identities.get(eid)
                if ai is None or identity is None or str(getattr(identity, "taxonomy_class", "")) != "hominid":
                    continue
                if str(getattr(ai, "state", "") or "") not in {"idle", "lounging", "socializing"}:
                    continue
                if int(pos.z) != _int(center[2]) or abs(int(pos.x) - _int(center[0])) + abs(int(pos.y) - _int(center[1])) > 14:
                    continue
                career = str(getattr(occupations.get(eid), "career", "") or "").strip().lower()
                if career in {"table_dealer", "proposition_player"} or _npc_wallet(self.sim, eid) < _int(table.get("buy_in")):
                    continue
                social = float(getattr(needs_map.get(eid), "social", 50.0) or 50.0)
                rng = random.Random(f"{getattr(self.sim, 'seed', 0)}:{table.get('id')}:guest:{eid}:{_int(getattr(self.sim, 'tick', 0)) // 60}")
                desire = 0.05 + max(0.0, (65.0 - social) / 250.0)
                if rng.random() <= desire:
                    candidates.append((rng.random(), int(eid), pos))
            if not candidates:
                continue
            candidates.sort()
            _roll, eid, pos = candidates[0]
            seat = _open_seat_near(table, pos.x, pos.y, pos.z)
            if seat is None:
                continue
            seat["reserved_eid"] = eid
            seat["reserved_tick"] = _int(getattr(self.sim, "tick", 0))
            ai = ais.get(eid)
            will = self.sim.ecs.get(NPCWill).get(eid)
            target = (_int(seat.get("x")), _int(seat.get("y")), _int(seat.get("z")))
            ai.state = "seeking_poker_table"
            ai.target = target
            ai.target_eid = None
            ai.holdem_cash_table_id = table.get("id")
            ai.holdem_cash_seat_index = seat.get("index")
            if will is not None:
                will.intent = "seeking_poker_table"
                will.target = target
                will.target_eid = None
                will.last_tick = _int(getattr(self.sim, "tick", 0))
            table["revision"] = _int(table.get("revision")) + 1

    def on_npc_seat_arrived(self, event):
        eid = event.data.get("npc_eid")
        table = _tables(self.sim, create=False).get(str(event.data.get("table_id", "")))
        if not isinstance(table, dict):
            return
        seat_index = event.data.get("seat_index")
        result = holdem_cash_join(self.sim, table, eid, seat_index=seat_index, actor_kind="npc")
        if not result.get("ok"):
            seat = _seat_map(table).get(_int(seat_index, -1))
            if seat is not None and seat.get("reserved_eid") == eid:
                seat["reserved_eid"] = None
                seat["reserved_tick"] = 0

    def on_entity_damaged(self, event):
        target_eid = event.data.get("target_eid")
        if target_eid is None:
            target_eid = event.data.get("eid")
        for table in list(_tables(self.sim, create=False).values()):
            seat = next((row for row in list(table.get("seats", ()) or ()) if row.get("actor_eid") == target_eid), None)
            if seat is None:
                continue
            if seat.get("hole") and not seat.get("folded"):
                seat["folded"] = True
                seat["acted"] = True
                seat["last_action"] = "is interrupted and folds"
            seat["leaving_after_hand"] = True
            table["revision"] = _int(table.get("revision")) + 1

    def _advance_table(self, table, tick):
        phase = str(table.get("phase", "waiting") or "waiting")
        if phase == "settling":
            if tick >= _int(table.get("next_tick")):
                _finish_settlement(self.sim, table)
            return
        if phase == "waiting":
            if tick >= _int(table.get("next_tick")):
                _start_hand(self.sim, table)
            return
        contenders = _remaining_contenders(table)
        if len(contenders) <= 1:
            _settle_showdown(self.sim, table)
            return
        acting = _seat_map(table).get(table.get("acting_seat"))
        if not _can_act(acting):
            _advance_actor(self.sim, table, _int(table.get("acting_seat"), -1))
            return
        if tick < _int(table.get("action_deadline_tick")):
            return
        if str(acting.get("actor_kind", "")) == "player":
            legal = holdem_cash_legal_actions(table, acting.get("actor_eid"))
            timeout_action = "check" if "check" in legal else "fold"
            holdem_cash_submit_action(self.sim, table, acting.get("actor_eid"), timeout_action)
            return
        holdem_cash_submit_action(self.sim, table, acting.get("actor_eid"), _npc_action(self.sim, table, acting))


__all__ = [
    "HOLDEM_CASH_SERVICE_ID",
    "HoldemCashSystem",
    "holdem_cash_interact_at",
    "holdem_cash_join",
    "holdem_cash_leave",
    "holdem_cash_legal_actions",
    "holdem_cash_public_snapshot",
    "holdem_cash_seat_at",
    "holdem_cash_submit_action",
    "holdem_cash_table_for_property",
]
