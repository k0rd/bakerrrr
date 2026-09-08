"""Bounded, opportunistic shop quotes and purchased notebook editions.

Quote collection never opens a shop or generates stock. Report reads examine
at most 12 shops with six quotes each, using only the requested chunk bucket.
"""

from copy import deepcopy

from game.components import PlayerAssets
from game.item_valuation import item_fair_value
from game.items import ITEM_CATALOG
from game.knowledge_notebook import emit_notebook_knowledge_update
from game.local_service_demand import neighborhood_service_market_read
from game.player_businesses import business_record_direct_sale
from game.property_access import property_access_level


MARKET_REPORT_COST = 5
MARKET_CACHE_CHUNKS = 64
MARKET_CACHE_SHOPS = 12
MARKET_QUOTES_PER_SIDE = 2
MARKET_QUOTE_HOURS = 24
MARKET_REFRESH_QUOTES = 4
MARKET_REPORT_COUNTERS = frozenset({"corner_store", "pawn_shop", "hardware_store"})


def _chunk_key(sim, prop):
    cx, cy = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))[:2]
    return f"{cx},{cy}"


def report_counter(prop):
    return isinstance(prop, dict) and str((prop.get("metadata") or {}).get("archetype", "")) in MARKET_REPORT_COUNTERS


def _public_shop(prop):
    if not isinstance(prop, dict):
        return False
    metadata = prop.get("metadata") or {}
    return (
        property_access_level(prop) == "public"
        and not any(metadata.get(key) for key in ("dialogue_trade_only", "covert", "economic_closed"))
        and str(metadata.get("archetype", "")) != "backroom_market"
    )


def _shops(sim, prop, *, create=False):
    cache = getattr(sim, "market_quote_cache", None)
    if not isinstance(cache, dict):
        if not create:
            return {}
        cache = {}
        sim.market_quote_cache = cache
    key = _chunk_key(sim, prop)
    if create:
        # Insertion order is a bounded recency queue, including across saves.
        bucket = cache.pop(key, {})
        cache[key] = bucket
        while len(cache) > MARKET_CACHE_CHUNKS:
            cache.pop(next(iter(cache)))
        return bucket
    return cache.get(key, {})


def reset_shop_quotes(sim, prop):
    """Discard superseded quotes when the existing stock refresh runs."""
    _shops(sim, prop).pop(str(prop.get("id", "")), None)


def record_shop_quote(sim, prop, entry, price, *, side="buy", audience=None, item_name="", fair_value=None):
    if not _public_shop(prop) or price <= 0:
        return
    item_id = str(entry.get("item_id", ""))
    metadata = entry.get("metadata") or {}
    if metadata.get("appearance_service") or entry.get("source_container") == "wire_kit":
        return
    if side == "buy" and int(entry.get("stock", 0)) <= 0:
        return
    fair = max(1, int(fair_value or item_fair_value(item_id, metadata, item_catalog=ITEM_CATALOG)))
    quote = {
        "item_id": item_id,
        "item_name": item_name or str(metadata.get("display_name") or ITEM_CATALOG.get(item_id, {}).get("name", item_id)),
        "stock_id": str(entry.get("stock_id") or entry.get("instance_id") or item_id),
        "price": int(price), "fair_value": fair, "ratio": float(price) / fair,
        "stock": int(entry.get("stock", 0)), "side": side, "audience": audience,
        "tick": int(sim.tick), "property_id": str(prop["id"]),
        "shop_name": str(prop.get("name", prop["id"])),
        "x": int(prop.get("x", 0)), "y": int(prop.get("y", 0)), "z": int(prop.get("z", 0)),
    }
    shops = _shops(sim, prop, create=True)
    shop_id = str(prop["id"])
    rows = shops.pop(shop_id, [])
    identity = (side, quote["stock_id"], audience)
    rows = [row for row in rows if (row["side"], row["stock_id"], row["audience"]) != identity]
    rows.append(quote)
    buys = sorted((row for row in rows if row["side"] == "buy"), key=lambda row: (row["ratio"], row["stock_id"]))
    sells = sorted((row for row in rows if row["side"] == "sell"), key=lambda row: (-row["ratio"], row["stock_id"]))
    # Two favorable shelf quotes, two expensive ones, and two real offers.
    selected = buys[:MARKET_QUOTES_PER_SIDE]
    selected += [row for row in buys[-MARKET_QUOTES_PER_SIDE:] if row not in selected]
    shops[shop_id] = selected + sells[:MARKET_QUOTES_PER_SIDE]
    while len(shops) > MARKET_CACHE_SHOPS:
        shops.pop(next(iter(shops)))


def invalidate_item_quotes(sim, prop, item_id):
    """Transactions retire old prices/offers; sold-out stock is never a tip."""
    shops = _shops(sim, prop)
    shop_id = str(prop.get("id", ""))
    rows = shops.get(shop_id)
    if rows is not None:
        shops[shop_id] = [row for row in rows if row["item_id"] != item_id]


def _clock_label(sim, tick):
    clock = (getattr(sim, "world_traits", {}) or {}).get("clock", {})
    per_hour = max(1, int(clock.get("ticks_per_hour", 600)))
    hour = int(tick) // per_hour + int(clock.get("start_hour", 0))
    minute = (int(tick) % per_hour) * 60 // per_hour
    return f"day {hour // 24 + 1}, {hour % 24:02d}:{minute:02d}"


def market_tips(sim, prop, viewer_eid):
    clock = (getattr(sim, "world_traits", {}) or {}).get("clock", {})
    max_age = MARKET_QUOTE_HOURS * max(1, int(clock.get("ticks_per_hour", 600)))
    rows = []
    for shop_id, quotes in _shops(sim, prop).items():
        # Point lookups only: never resolve saved chunks or materialize stores.
        shop = sim.properties.get(shop_id)
        if not _public_shop(shop) or _chunk_key(sim, shop) != _chunk_key(sim, prop):
            continue
        rows.extend(row for row in quotes if row["audience"] in (None, viewer_eid)
                    and 0 <= int(sim.tick) - row["tick"] <= max_age)
    buys = sorted((row for row in rows if row["side"] == "buy" and row["stock"] > 0),
                  key=lambda row: (row["ratio"], row["price"], row["property_id"], row["stock_id"]))
    sells = sorted((row for row in rows if row["side"] == "sell"),
                   key=lambda row: (-row["ratio"], -row["price"], row["property_id"], row["stock_id"]))
    tips = []
    if buys:
        tips.append({**buys[0], "label": "Best reported shelf value"})
    if sells:
        tips.append({**sells[0], "label": "Buying offer"})
    if len(buys) > 1 and buys[-1]["ratio"] >= 1.25 and buys[-1]["item_id"] != buys[0]["item_id"]:
        tips.append({**buys[-1], "label": "High asking price"})
    return tips


def _directions(quote, report):
    dx, dy = quote["x"] - report["x"], quote["y"] - report["y"]
    parts = []
    if dy:
        parts.append(f"{abs(dy)} steps {'south' if dy > 0 else 'north'}")
    if dx:
        parts.append(f"{abs(dx)} steps {'east' if dx > 0 else 'west'}")
    if quote["z"] != report["z"]:
        parts.append(f"floor {quote['z']}")
    return ", ".join(parts) + f" from {report['source']}" if parts else f"At {report['source']}"


def report_lines(sim, report):
    lines = [f"Neighborhood {report['chunk']} | {report['source']}",
             f"Issued {_clock_label(sim, report['tick'])}. Saved edition; prices and stock may change.", ""]
    for tip in report["tips"]:
        lines += [f"{tip['label']}: {tip['item_name']} — {tip['price']} cr at {tip['shop_name']} (typical value {tip['fair_value']} cr).",
                  _directions(tip, report) + ".",
                  f"Quoted {_clock_label(sim, tip['tick'])}. " + (
                      "Offer for the item you showed; condition and personal terms apply." if tip["side"] == "sell" else
                      f"{tip['stock']} in stock then. " + ("Your quoted terms." if tip["audience"] is not None else "Standard shelf terms; your terms may differ.")), ""]
    if not report["tips"]:
        lines += ["No recent shop quotes reported here.", ""]
    lines += ["Local market outlook", "Demand and supply are local estimates; pressure compares the two."]
    for row in report["market"]:
        lines.append(f"{row['label']}: demand {row['demand']:.1f} | supply {row['supply']:.1f} | pressure {row['pressure']:.2f}")
    return lines


def buy_market_report(sim, prop, viewer_eid):
    """Called after the service menu revalidates counter access and proximity."""
    assets = sim.ecs.get(PlayerAssets).get(viewer_eid)
    if not report_counter(prop) or assets is None:
        return None, "This counter does not issue market reports."
    if assets.credits < MARKET_REPORT_COST:
        return None, f"A market report costs {MARKET_REPORT_COST} cr."
    chunk = tuple(sim.chunk_coords(int(prop["x"]), int(prop["y"]))[:2])
    tips = market_tips(sim, prop, viewer_eid)
    # Avoid charging for an empty tips page; category statistics alone are not
    # the reason this service is sold.
    if not tips:
        return None, "No recent shop quotes here yet. Keep your money; try again after local trading picks up."
    from game.service_category_registry import service_category_label
    market = [{"label": service_category_label(row["topic_id"]),
               "demand": float(row.get("effective_demand", 0)),
               "supply": float(row.get("effective_supply", 0)),
               "pressure": float(row.get("opportunity_pressure", 0))}
              for row in neighborhood_service_market_read(sim, chunk)]
    report = deepcopy({"chunk": f"{chunk[0]},{chunk[1]}", "tick": int(sim.tick),
                       "source": str(prop.get("name", prop["id"])), "source_id": str(prop["id"]),
                       "x": int(prop["x"]), "y": int(prop["y"]), "z": int(prop.get("z", 0)),
                       "tips": tips, "market": market})
    reports = getattr(sim, "player_market_reports", None)
    if not isinstance(reports, dict):
        reports = {}
        sim.player_market_reports = reports
    reports.setdefault(viewer_eid, {})[report["chunk"]] = report
    assets.credits -= MARKET_REPORT_COST
    business_record_direct_sale(sim, prop, MARKET_REPORT_COST, buyer_eid=viewer_eid, item_name="Local market report")
    emit_notebook_knowledge_update(sim, viewer_eid, notebook_kind="market_reports", subject_id=report["chunk"],
                                  subject_name="Local market report", change_kind="refreshed")
    return report, ""


def build_market_notebook(sim, viewer_eid):
    reports = (getattr(sim, "player_market_reports", {}) or {}).get(viewer_eid, {})
    lines = []
    for report in sorted(reports.values(), key=lambda row: (-row["tick"], row["chunk"])):
        lines.extend(report_lines(sim, report) + [""])
    return {"title": "Market Reports", "lines": lines or [
        "No market reports copied yet.",
        "Ask at a corner store, pawn shop, or hardware store counter.",
        f"A report costs {MARKET_REPORT_COST} cr and stays in this notebook until you replace it with a fresh edition.",
    ]}
