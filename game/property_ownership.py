"""Atomic actor-neutral property ownership transfers.

Ownership used to be mutated independently by real-estate purchases, vehicle
trade-ins, and simulation-side plans.  This transaction keeps portfolios,
credentials, money, the market cache, and the public event synchronized.
"""

from __future__ import annotations

from engine.events import Event
from game.components import FinancialProfile, Inventory, PlayerAssets, PropertyPortfolio
from game.property_keys import ensure_actor_has_property_credential, remove_actor_property_credentials
from game.system_support.npc_income_runtime import inventory_liquid_credits, spend_npc_wallet_credits


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _actor_funds(sim, eid):
    if eid is None:
        return 0
    assets = sim.ecs.get(PlayerAssets).get(int(eid))
    if assets is not None:
        return max(0, _int(getattr(assets, "credits", 0)))
    inventory = sim.ecs.get(Inventory).get(int(eid))
    finance = sim.ecs.get(FinancialProfile).get(int(eid))
    return (
        max(0, inventory_liquid_credits(inventory) if inventory is not None else 0)
        + max(0, _int(getattr(finance, "bank_balance", 0), 0) if finance is not None else 0)
    )


def _debit_actor(sim, eid, amount):
    amount = max(0, _int(amount, 0))
    if amount <= 0 or eid is None:
        return True
    eid = int(eid)
    if _actor_funds(sim, eid) < amount:
        return False
    assets = sim.ecs.get(PlayerAssets).get(eid)
    if assets is not None:
        assets.credits = max(0, _int(getattr(assets, "credits", 0)) - amount)
        return True
    inventory = sim.ecs.get(Inventory).get(eid)
    finance = sim.ecs.get(FinancialProfile).get(eid)
    wallet_spent = spend_npc_wallet_credits(inventory, amount) if inventory is not None else 0
    remainder = max(0, amount - wallet_spent)
    if remainder and finance is not None:
        finance.bank_balance = max(0, _int(getattr(finance, "bank_balance", 0)) - remainder)
    return remainder <= 0 or finance is not None


def _credit_actor(sim, eid, amount):
    amount = max(0, _int(amount, 0))
    if amount <= 0 or eid is None:
        return
    eid = int(eid)
    assets = sim.ecs.get(PlayerAssets).get(eid)
    if assets is not None:
        assets.credits = max(0, _int(getattr(assets, "credits", 0))) + amount
        return
    finance = sim.ecs.get(FinancialProfile).get(eid)
    if finance is None:
        finance = FinancialProfile()
        sim.ecs.add(eid, finance)
    finance.bank_balance = max(0, _int(getattr(finance, "bank_balance", 0))) + amount


def _sync_portfolio(sim, eid, property_id, *, owned):
    if eid is None:
        return
    eid = int(eid)
    assets = sim.ecs.get(PlayerAssets).get(eid)
    if assets is not None:
        if owned:
            assets.owned_property_ids.add(property_id)
        else:
            assets.owned_property_ids.discard(property_id)
    portfolio = sim.ecs.get(PropertyPortfolio).get(eid)
    if owned and portfolio is None and assets is None:
        portfolio = PropertyPortfolio()
        sim.ecs.add(eid, portfolio)
    if portfolio is not None:
        if owned:
            portfolio.owned_property_ids.add(property_id)
        else:
            portfolio.owned_property_ids.discard(property_id)


def transfer_property_ownership(
    sim,
    property_id,
    *,
    new_owner_eid=None,
    new_owner_tag=None,
    price=0,
    reason="transfer",
    issue_credential=True,
):
    """Transfer one property or return ``None`` without partial mutation."""

    property_id = str(property_id or "").strip()
    prop = getattr(sim, "properties", {}).get(property_id)
    if not isinstance(prop, dict):
        return None
    old_owner_eid = prop.get("owner_eid")
    old_owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
    if new_owner_eid is not None:
        try:
            new_owner_eid = int(new_owner_eid)
        except (TypeError, ValueError):
            return None
    if old_owner_eid is not None:
        try:
            old_owner_eid = int(old_owner_eid)
        except (TypeError, ValueError):
            old_owner_eid = None
    if new_owner_tag is None:
        new_owner_tag = "player" if new_owner_eid == getattr(sim, "player_eid", None) else ("npc" if new_owner_eid is not None else "public")
    new_owner_tag = str(new_owner_tag or "public").strip().lower() or "public"
    price = max(0, _int(price, 0))

    if price and not _debit_actor(sim, new_owner_eid, price):
        return None

    if old_owner_eid is not None and old_owner_eid != new_owner_eid:
        remove_actor_property_credentials(sim, old_owner_eid, prop)
        _sync_portfolio(sim, old_owner_eid, property_id, owned=False)
    if not sim.assign_property_owner(property_id, owner_eid=new_owner_eid, owner_tag=new_owner_tag):
        if price:
            _credit_actor(sim, new_owner_eid, price)
        return None
    if price:
        _credit_actor(sim, old_owner_eid, price)
    _sync_portfolio(sim, new_owner_eid, property_id, owned=True)

    credential_issued = False
    if issue_credential and new_owner_eid is not None:
        credential_issued, _instance_id, _created = ensure_actor_has_property_credential(
            sim,
            new_owner_eid,
            prop,
            owner_tag=new_owner_tag,
        )

    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    if isinstance(metadata, dict):
        metadata["economic_listed"] = False
        if str(prop.get("kind", "") or "").strip().lower() == "vehicle":
            metadata["vehicle_owner_tag"] = new_owner_tag
    from game.local_service_demand import refresh_property_market_supply
    refresh_property_market_supply(sim, prop)
    from game.neighborhood_businesses import record_neighborhood_ownership_change
    record_neighborhood_ownership_change(
        sim,
        property_id=property_id,
        old_owner_eid=old_owner_eid,
        old_owner_tag=old_owner_tag,
        new_owner_eid=new_owner_eid,
        new_owner_tag=new_owner_tag,
        price=price,
        reason=str(reason or "transfer").strip().lower(),
    )
    sim.emit(Event(
        "property_owner_changed",
        property_id=property_id,
        old_owner_eid=old_owner_eid,
        old_owner_tag=old_owner_tag,
        new_owner_eid=new_owner_eid,
        new_owner_tag=new_owner_tag,
        price=price,
        reason=str(reason or "transfer").strip().lower(),
        credential_issued=bool(credential_issued),
    ))
    return {
        "property_id": property_id,
        "old_owner_eid": old_owner_eid,
        "old_owner_tag": old_owner_tag,
        "new_owner_eid": new_owner_eid,
        "new_owner_tag": new_owner_tag,
        "price": price,
        "credential_issued": bool(credential_issued),
    }


__all__ = ["transfer_property_ownership"]
