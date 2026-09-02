"""Shared vocabulary for player-visible service categories.

The dialogue locator and the neighborhood survey intentionally consume this
same registry.  Adding a service the player can ask about therefore gives the
chunk economy an explicit category too, without either system importing the
other.
"""

from __future__ import annotations

from game.property_access import JUSTICE_CASHIER_SERVICE_ID
from game.service_runtime import CASINO_GAME_SERVICE_IDS, TRANSIT_SERVICE_IDS


OUTFITTER_LOCATOR_ARCHETYPES = ("outfitter", "surplus_store")
DRONE_PARTS_LOCATOR_ARCHETYPES = ("electronics_shop", "comms_shop", "drone_shop")
WIRE_GEAR_LOCATOR_ARCHETYPES = ("wire_shop", "electronics_shop", "comms_shop")
CIVIC_RECORDS_LOCATOR_ARCHETYPES = ("courthouse", "civic_office", "city_hall")
JUSTICE_LOCATOR_ARCHETYPES = ("jail", "courthouse", "prison")


# Economic metadata deliberately lives beside the player-facing vocabulary.
# Callers should use ``service_category_definition`` rather than teaching a
# second subsystem which topics overlap or which capabilities are protected.
_CATEGORY_GROUPS = {
    "service_transit": "transit",
    "service_rail": "transit",
    "service_bus": "transit",
    "service_shuttle": "transit",
    "service_ferry": "transit",
    "service_coach": "transit",
    "service_work": "work",
    "service_courier": "work",
    "service_agency": "work",
    "service_bounty": "work",
    "service_vehicle_sales": "vehicle_sales",
    "service_used_cars": "vehicle_sales",
}

_CATEGORY_ACTIONS = {
    "service_transit": "transit",
    "service_rail": "transit",
    "service_bus": "transit",
    "service_shuttle": "transit",
    "service_ferry": "transit",
    "service_coach": "transit",
    "service_work": "work_board",
    "service_courier": "work_board",
    "service_agency": "work_board",
    "service_bounty": "work_board",
    "service_rest": "lodging",
    "service_vehicle_sales": "vehicle_sale",
    "service_used_cars": "vehicle_sale",
    "service_vehicle_fetch": "vehicle_fetch",
    "service_gaming": "gaming",
}

_PROTECTED_CAPABILITY_TOPICS = frozenset({
    "service_transit",
    "service_rail",
    "service_bus",
    "service_shuttle",
    "service_ferry",
    "service_coach",
    "service_records",
    "service_justice",
})


SERVICE_LOCATOR_TOPICS = {
    "service_fuel": {
        "services": ("fuel",),
        "service_label": "fuel",
        "offer_label": "fuel",
        "lead_kind": "service_fuel",
    },
    "service_repair": {
        "services": ("repair",),
        "service_label": "repair shop",
        "offer_label": "vehicle repair",
        "lead_kind": "service_repair",
    },
    "service_contractor": {
        "services": ("building_repair", "business_remodel"),
        "service_label": "contractor",
        "offer_label": "building repair or remodel",
        "lead_kind": "service_contractor",
    },
    "service_banking": {
        "services": ("banking",),
        "service_label": "bank or broker",
        "offer_label": "banking or brokerage",
        "lead_kind": "service_banking",
    },
    "service_business_desk": {
        "services": ("business_management",),
        "service_label": "business desk",
        "offer_label": "business operations",
        "lead_kind": "service_business_desk",
        "local_summary": "In this chunk, {names_text} can handle business operations: owned-business policy and staff wages.",
        "near_summary": "Nearest business desk I know is {distance_phrase} at {names_text}.",
    },
    "service_insurance": {
        "services": ("insurance",),
        "service_label": "insurer",
        "offer_label": "coverage or claims",
        "lead_kind": "service_insurance",
    },
    "service_rest": {
        "services": ("rest", "shelter"),
        "service_label": "lodging",
        "offer_label": "lodging",
        "lead_kind": "service_rest",
    },
    "service_transit": {
        "services": tuple(TRANSIT_SERVICE_IDS),
        "service_label": "transit stop",
        "offer_label": "transit",
        "lead_kind": "service_transit",
        "local_summary": "In this chunk, {names_text} can put you onto the transit network.",
        "near_summary": "Nearest transit stop I know is {distance_phrase} at {names_text}.",
    },
    "service_rail": {
        "services": ("rail_transit",),
        "service_label": "rail station",
        "offer_label": "rail travel",
        "lead_kind": "service_rail",
        "local_summary": "In this chunk, {names_text} can put you on a rail line.",
        "near_summary": "Nearest rail station I know is {distance_phrase} at {names_text}.",
    },
    "service_bus": {
        "services": ("bus_transit",),
        "service_label": "bus stop",
        "offer_label": "bus travel",
        "lead_kind": "service_bus",
        "local_summary": "In this chunk, {names_text} posts bus routes.",
        "near_summary": "Nearest bus stop I know is {distance_phrase} at {names_text}.",
    },
    "service_shuttle": {
        "services": ("shuttle_transit",),
        "service_label": "shuttle stop",
        "offer_label": "shuttle travel",
        "lead_kind": "service_shuttle",
        "local_summary": "In this chunk, {names_text} posts shuttle transfers.",
        "near_summary": "Nearest shuttle stop I know is {distance_phrase} at {names_text}.",
    },
    "service_ferry": {
        "services": ("ferry_transit",),
        "service_label": "ferry landing",
        "offer_label": "ferry travel",
        "lead_kind": "service_ferry",
        "local_summary": "In this chunk, {names_text} posts ferry departures.",
        "near_summary": "Nearest ferry landing I know is {distance_phrase} at {names_text}.",
    },
    "service_coach": {
        "services": ("coach_transit",),
        "service_label": "coach stop",
        "offer_label": "regional coach travel",
        "lead_kind": "service_coach",
        "local_summary": "In this chunk, {names_text} posts coach departures.",
        "near_summary": "Nearest coach stop I know is {distance_phrase} at {names_text}.",
    },
    "service_intel": {
        "services": ("intel",),
        "service_label": "intel",
        "offer_label": "intel",
        "lead_kind": "service_intel",
    },
    "service_work": {
        "services": ("courier_jobs", "agency_jobs", "bounty_jobs"),
        "service_label": "posted work",
        "offer_label": "posted work",
        "lead_kind": "service_work",
        "local_summary": "In this chunk, {names_text} has work posted.",
        "near_summary": "Nearest work board I know is {distance_phrase} at {names_text}.",
    },
    "service_courier": {
        "services": ("courier_jobs",),
        "service_label": "courier board",
        "offer_label": "courier jobs",
        "lead_kind": "service_courier",
        "local_summary": "In this chunk, {names_text} posts courier runs.",
        "near_summary": "Nearest courier board I know is {distance_phrase} at {names_text}.",
    },
    "service_agency": {
        "services": ("agency_jobs",),
        "service_label": "agency work",
        "offer_label": "agency jobs",
        "lead_kind": "service_agency",
        "local_summary": "In this chunk, {names_text} posts agency work.",
        "near_summary": "Nearest agency work I know is {distance_phrase} at {names_text}.",
    },
    "service_bounty": {
        "services": ("bounty_jobs",),
        "service_label": "bounty board",
        "offer_label": "bounty jobs",
        "lead_kind": "service_bounty",
        "local_summary": "In this chunk, {names_text} posts bounty work.",
        "near_summary": "Nearest bounty board I know is {distance_phrase} at {names_text}.",
    },
    "service_trade": {
        "services": (),
        "service_label": "shopping spot",
        "offer_label": "shopping",
        "lead_kind": "service_trade",
        "storefront": True,
    },
    "service_discreet_trade": {
        "services": (),
        "service_label": "discreet seller",
        "offer_label": "quiet trade",
        "lead_kind": "service_trade",
        "archetypes": ("backroom_market",),
        "covert": True,
        "hidden_lead": True,
        "local_summary": "If you need quiet trade, {names_text} is the kind of door people mention in this chunk.",
        "near_summary": "Nearest discreet seller I know is {distance_phrase} at {names_text}.",
    },
    "service_street_doctor": {
        "services": (),
        "service_label": "quiet doctor",
        "offer_label": "off-book medical help",
        "lead_kind": "service_medical",
        "archetypes": ("backroom_clinic",),
        "covert": True,
        "hidden_lead": True,
        "local_summary": "If you need help without paperwork, {names_text} is the kind of door people use in this chunk.",
        "near_summary": "Nearest quiet doctor I know is {distance_phrase} at {names_text}.",
    },
    "service_herbal": {
        "services": ("herbal_care", "herbal_prepare", "herbal_recipe_sales"),
        "service_label": "herbal care",
        "offer_label": "herbal care",
        "lead_kind": "service_herbal",
        "local_summary": "In this chunk, {names_text} can handle herbal care.",
        "near_summary": "Nearest herbal care I know is {distance_phrase} at {names_text}.",
    },
    "service_butcher": {
        "services": ("butcher_prepare",),
        "service_label": "butcher",
        "offer_label": "meat prep",
        "lead_kind": "service_butcher",
        "local_summary": "In this chunk, {names_text} can prepare game meat.",
        "near_summary": "Nearest butcher I know is {distance_phrase} at {names_text}.",
    },
    "service_appearance": {
        "services": ("appearance_style",),
        "service_label": "styling",
        "offer_label": "hair, makeup, or tattoo work",
        "lead_kind": "service_appearance",
        "local_summary": "In this chunk, {names_text} can handle styling.",
        "near_summary": "Nearest styling service I know is {distance_phrase} at {names_text}.",
    },
    "service_outfitter": {
        "services": (),
        "service_label": "outfitter",
        "offer_label": "gear and clothing",
        "lead_kind": "service_outfitter",
        "archetypes": OUTFITTER_LOCATOR_ARCHETYPES,
    },
    "service_drone_parts": {
        "services": (),
        "service_label": "drone parts counter",
        "offer_label": "drone parts and electronics",
        "lead_kind": "service_drone_parts",
        "archetypes": DRONE_PARTS_LOCATOR_ARCHETYPES,
        "local_summary": "In this chunk, {names_text} sells drone parts, radios, or electronics.",
        "near_summary": "Nearest drone or electronics counter I know is {distance_phrase} at {names_text}.",
    },
    "service_wire_gear": {
        "services": (),
        "service_label": "Wire gear counter",
        "offer_label": "Wire decks and software",
        "lead_kind": "service_wire_gear",
        "archetypes": WIRE_GEAR_LOCATOR_ARCHETYPES,
        "local_summary": "In this chunk, {names_text} sells Wire decks, interfaces, or software.",
        "near_summary": "Nearest Wire gear counter I know is {distance_phrase} at {names_text}.",
    },
    "service_records": {
        "services": ("civic_records",),
        "service_label": "civic records office",
        "offer_label": "public records",
        "lead_kind": "service_records",
        "archetypes": CIVIC_RECORDS_LOCATOR_ARCHETYPES,
        "local_summary": "In this chunk, {names_text} keeps the public civic ledgers.",
        "near_summary": "Nearest civic records counter I know is {distance_phrase} at {names_text}.",
    },
    "service_justice": {
        "services": (JUSTICE_CASHIER_SERVICE_ID,),
        "service_label": "justice cashier",
        "offer_label": "justice debt payment or held-property release",
        "lead_kind": "service_justice",
        "archetypes": JUSTICE_LOCATOR_ARCHETYPES,
        "local_summary": "In this chunk, {names_text} can take justice-debt payments and release held property.",
        "near_summary": "Nearest justice cashier I know is {distance_phrase} at {names_text}.",
    },
    "service_vehicle_sales": {
        "services": ("vehicle_sales_new", "vehicle_sales_used"),
        "service_label": "vehicle seller",
        "offer_label": "vehicle sales",
        "lead_kind": "service_vehicle_sales",
        "local_summary": "In this chunk, {names_text} has vehicles for sale.",
        "near_summary": "Nearest vehicle seller I know is {distance_phrase} at {names_text}.",
    },
    "service_used_cars": {
        "services": ("vehicle_sales_used",),
        "service_label": "used-car spot",
        "offer_label": "used vehicles",
        "lead_kind": "service_used_cars",
    },
    "service_vehicle_fetch": {
        "services": ("vehicle_fetch",),
        "service_label": "vehicle retrieval service",
        "offer_label": "vehicle retrieval",
        "lead_kind": "service_vehicle_fetch",
    },
    "service_gaming": {
        "services": tuple(CASINO_GAME_SERVICE_IDS),
        "service_label": "gaming spot",
        "offer_label": "gaming",
        "lead_kind": "service_gaming",
        "archetypes": ("casino", "gaming_hall"),
    },
}


def service_category_label(topic_id):
    """Return the short player vocabulary label for one service category."""

    topic = SERVICE_LOCATOR_TOPICS.get(str(topic_id or "").strip().lower(), {})
    return str(topic.get("offer_label") or topic.get("service_label") or topic_id).strip()


def service_category_definition(topic_id):
    """Return one normalized social/economic category definition."""

    topic_id = str(topic_id or "").strip().lower()
    configured = SERVICE_LOCATOR_TOPICS.get(topic_id)
    if not isinstance(configured, dict):
        return {}
    row = dict(configured)
    row.update({
        "topic_id": topic_id,
        "market_group": str(row.get("market_group") or _CATEGORY_GROUPS.get(topic_id, topic_id)).strip().lower(),
        "consumer_action": str(row.get("consumer_action") or _CATEGORY_ACTIONS.get(topic_id, "patronage")).strip().lower(),
        "base_capacity": max(0.05, float(row.get("base_capacity", 1.0) or 1.0)),
        "protected_capability": bool(row.get("protected_capability", topic_id in _PROTECTED_CAPABILITY_TOPICS)),
    })
    return row


def service_category_supply_keys(topic_id):
    """Return exact cached supply keys represented by a locator category."""

    topic = SERVICE_LOCATOR_TOPICS.get(str(topic_id or "").strip().lower(), {})
    keys = [str(value).strip().lower() for value in tuple(topic.get("services", ()) or ())]
    keys.extend(
        f"business:{str(value).strip().lower()}"
        for value in tuple(topic.get("archetypes", ()) or ())
        if str(value).strip()
    )
    return tuple(dict.fromkeys(key for key in keys if key))


def service_categories_for_raw_key(service_key):
    """Map one exact cached service/archetype key to social categories."""

    service_key = str(service_key or "").strip().lower()
    if not service_key:
        return ()
    if service_key in SERVICE_LOCATOR_TOPICS:
        return (service_key,)
    matches = {
        topic_id
        for topic_id in SERVICE_LOCATOR_TOPICS
        if service_key in service_category_supply_keys(topic_id)
    }
    # Older lived-demand records use precise storefront archetypes.  They are
    # still valid revealed shopping demand even when dialogue has no narrower
    # category for that archetype.
    if service_key.startswith("business:"):
        matches.add("service_trade")
    return tuple(topic_id for topic_id in SERVICE_LOCATOR_TOPICS if topic_id in matches)


def service_categories_for_property(prop):
    """Return every category supplied by one property, without world scans."""

    if not isinstance(prop, dict):
        return ()
    from game.property_runtime import (
        property_is_storefront,
        property_services,
        property_supports_business_relevance,
    )

    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    if bool(metadata.get("economic_service_exempt")):
        return ()
    raw_keys = {
        str(service or "").strip().lower()
        for service in tuple(property_services(prop) or ())
        if str(service or "").strip()
    }
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype and property_supports_business_relevance(prop, include_assets=True):
        raw_keys.add(f"business:{archetype}")

    categories = set()
    for service_key in raw_keys:
        categories.update(service_categories_for_raw_key(service_key))
    if property_is_storefront(prop):
        categories.add("service_trade")
    return tuple(topic_id for topic_id in SERVICE_LOCATOR_TOPICS if topic_id in categories)


def property_has_protected_market_capability(prop):
    """Whether generic economic autonomy must preserve this site's purpose."""

    if not isinstance(prop, dict):
        return False
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    if bool(metadata.get("economic_protected")):
        return True
    return any(
        bool(service_category_definition(topic_id).get("protected_capability"))
        for topic_id in service_categories_for_property(prop)
    )


__all__ = [
    "SERVICE_LOCATOR_TOPICS",
    "property_has_protected_market_capability",
    "service_categories_for_property",
    "service_categories_for_raw_key",
    "service_category_definition",
    "service_category_label",
    "service_category_supply_keys",
]
