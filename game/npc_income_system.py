"""Recurring real-income support for employed NPCs."""

from __future__ import annotations

from engine.systems import System
from engine.events import Event
from game.components import AI, FinancialProfile, Inventory, NPCWill, Occupation, Position, Vitality
from game.player_businesses import actor_player_business_employment
from game.local_service_demand import (
    record_actor_local_service_demand_sample,
    record_unmet_local_service_demand,
)
from game.population import work_shift_active
from game.property_access import property_is_open
from game.property_runtime import (
    finance_services_for_property,
    property_distance,
    property_focus_position,
    resolve_property_record,
)
from game.system_support.npc_income_runtime import (
    ensure_financial_income_fields,
    grant_npc_wallet_credits,
    inventory_liquid_credits,
    npc_hourly_wage,
    spend_npc_wallet_credits,
)


NPC_BANK_SEARCH_RADIUS = 18
NPC_BANKING_AVAILABLE_STATES = frozenset({
    "idle",
    "lounging",
    "patrolling",
    "resting",
    "seeking_social",
    "socializing",
})


def _text(value):
    return str(value or "").strip()


def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _ticks_per_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    return max(60, _int_or(clock.get("ticks_per_hour", 600), default=600))


def _absolute_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    start_hour = _int_or(clock.get("start_hour", 9), default=9)
    return start_hour + (_int_or(getattr(sim, "tick", 0), default=0) // _ticks_per_hour(sim))


def _detail_loaded(sim, pos):
    if sim is None or pos is None:
        return False
    try:
        return str(sim.detail_for_xy(pos.x, pos.y)).strip().lower() != "unloaded"
    except Exception:
        return False


def _occupation_is_jobbed(occupation):
    if occupation is None:
        return False
    workplace = getattr(occupation, "workplace", None)
    if not isinstance(workplace, dict) or not _text(workplace.get("property_id")):
        return False
    career = _text(getattr(occupation, "career", "")).lower()
    return career not in {"", "resident", "unemployed", "drunk", "thief"}


class NPCIncomeSystem(System):
    """Pay loaded workers and turn excess carried cash into real banking trips."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("npc_banking_arrived", self.on_npc_banking_arrived)

    def _nearest_banking_property(self, actor_eid, pos):
        candidates = []
        for prop in self.sim.properties_in_radius(
            int(pos.x),
            int(pos.y),
            int(pos.z),
            r=NPC_BANK_SEARCH_RADIUS,
        ):
            if "banking" not in finance_services_for_property(prop):
                continue
            if property_is_open(self.sim, prop) is False:
                continue
            target = property_focus_position(prop)
            if not isinstance(target, (tuple, list)) or len(target) < 3:
                continue
            try:
                target = (int(target[0]), int(target[1]), int(target[2]))
            except (TypeError, ValueError):
                continue
            if target[2] != int(pos.z):
                continue
            candidates.append((property_distance(pos.x, pos.y, prop), str(prop.get("id", "")), prop, target))
        candidates.sort(key=lambda row: (row[0], row[1]))
        return (candidates[0][2], candidates[0][3]) if candidates else (None, None)

    def _maybe_schedule_banking(self, eid, profile, inventory, pos, *, on_shift):
        now = _int_or(getattr(self.sim, "tick", 0), default=0)
        if now < _int_or(getattr(profile, "next_bank_check_tick", 0), default=0):
            return False
        profile.next_bank_check_tick = now + _ticks_per_hour(self.sim)

        wallet = inventory_liquid_credits(inventory)
        wallet_buffer = max(0, _int_or(getattr(profile, "wallet_buffer", 0), default=0))
        deposit_step = max(1, _int_or(getattr(profile, "deposit_step", 48), default=48))
        excess = max(0, wallet - wallet_buffer)
        if excess < deposit_step or on_shift:
            return False

        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        if ai is None:
            return False
        state = _text(getattr(ai, "state", "")).lower()
        if state == "seeking_bank" and getattr(ai, "target", None):
            return True
        if state not in NPC_BANKING_AVAILABLE_STATES:
            return False

        bank_prop, target = self._nearest_banking_property(eid, pos)
        demand_fields = {
            "npc_eid": int(eid),
            "service": "banking",
            "motive": "excess_carried_cash",
            "amount": int(excess),
            "x": int(pos.x),
            "y": int(pos.y),
            "z": int(pos.z),
            "search_radius": NPC_BANK_SEARCH_RADIUS,
            "provider_property_id": bank_prop.get("id") if isinstance(bank_prop, dict) else None,
        }
        record_actor_local_service_demand_sample(
            self.sim,
            actor_eid=eid,
            x=pos.x,
            y=pos.y,
            service="banking",
            motive="excess_carried_cash",
            intensity=min(3.0, max(0.25, float(excess) / float(deposit_step))),
            tick=now,
        )
        self.sim.emit(Event("npc_service_demand_registered", available=bool(bank_prop), **demand_fields))
        if not isinstance(bank_prop, dict) or target is None:
            record_unmet_local_service_demand(
                self.sim,
                x=pos.x,
                y=pos.y,
                service="banking",
                motive="excess_carried_cash",
                amount=excess,
                tick=now,
            )
            self.sim.emit(Event("npc_service_demand_unmet", **demand_fields))
            return False

        ai.state = "seeking_bank"
        ai.target = target
        ai.target_eid = None
        ai.banking_property_id = bank_prop.get("id")
        if will is not None:
            will.intent = "seeking_bank"
            will.target = target
            will.target_eid = None
            will.last_tick = now
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=int(eid),
            intent="seeking_bank",
            score=float(excess),
            target=target,
            target_eid=None,
        ))
        return True

    def on_npc_banking_arrived(self, event):
        try:
            eid = int(event.data.get("npc_eid"))
        except (TypeError, ValueError):
            return
        profile = self.sim.ecs.get(FinancialProfile).get(eid)
        inventory = self.sim.ecs.get(Inventory).get(eid)
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        property_id = _text(event.data.get("property_id"))
        prop = resolve_property_record(self.sim, property_id, include_saved=False)
        valid_provider = bool(
            isinstance(prop, dict)
            and "banking" in finance_services_for_property(prop)
            and property_is_open(self.sim, prop) is not False
        )
        if profile is not None and inventory is not None and valid_provider:
            wallet_before = inventory_liquid_credits(inventory)
            wallet_buffer = max(0, _int_or(getattr(profile, "wallet_buffer", 0), default=0))
            requested = max(0, wallet_before - wallet_buffer)
            deposited = spend_npc_wallet_credits(inventory, requested)
            if deposited > 0:
                profile.bank_balance = max(0, _int_or(getattr(profile, "bank_balance", 0), default=0)) + deposited
                self.sim.emit(Event(
                    "npc_bank_deposit",
                    npc_eid=eid,
                    property_id=property_id,
                    amount=int(deposited),
                    wallet_before=int(wallet_before),
                    wallet_after=int(inventory_liquid_credits(inventory)),
                    bank_balance=int(profile.bank_balance),
                ))
        if ai is not None:
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None
            if hasattr(ai, "banking_property_id"):
                delattr(ai, "banking_property_id")
        if will is not None and _text(getattr(will, "intent", "")).lower() == "seeking_bank":
            will.intent = "idle"
            will.target = None
            will.target_eid = None
            will.last_tick = _int_or(getattr(self.sim, "tick", 0), default=0)

    def update(self):
        current_hour = int(_absolute_hour(self.sim))
        current_clock_hour = int(current_hour % 24)
        positions = self.sim.ecs.get(Position)
        occupations = self.sim.ecs.get(Occupation)
        profiles = self.sim.ecs.get(FinancialProfile)
        inventories = self.sim.ecs.get(Inventory)
        vitalities = self.sim.ecs.get(Vitality)
        player_eid = getattr(self.sim, "player_eid", None)

        for eid, occupation in tuple(occupations.items()):
            if eid == player_eid:
                continue
            if not _occupation_is_jobbed(occupation):
                continue
            pos = positions.get(eid)
            if not _detail_loaded(self.sim, pos):
                continue
            vitality = vitalities.get(eid)
            if vitality is not None and bool(getattr(vitality, "downed", False)):
                continue
            profile = profiles.get(eid)
            inventory = inventories.get(eid)
            if profile is None or inventory is None:
                continue
            ensure_financial_income_fields(profile)
            workplace = getattr(occupation, "workplace", None)
            property_id = _text(workplace.get("property_id")) if isinstance(workplace, dict) else ""
            prop = resolve_property_record(self.sim, property_id, include_saved=False)
            if not isinstance(prop, dict):
                continue
            on_shift = work_shift_active(
                self.sim,
                occupation=occupation,
                workplace_prop=prop,
                hour=current_clock_hour,
            )
            self._maybe_schedule_banking(
                eid,
                profile,
                inventory,
                pos,
                on_shift=on_shift,
            )
            if getattr(profile, "last_income_hour", None) is None:
                profile.last_income_hour = current_hour
                continue
            if int(getattr(profile, "last_income_hour", current_hour) or current_hour) >= current_hour:
                continue
            if player_eid is not None and actor_player_business_employment(self.sim, eid, owner_eid=player_eid) is not None:
                continue

            if not on_shift:
                continue

            wage = npc_hourly_wage(
                self.sim,
                eid,
                career=getattr(occupation, "career", ""),
                workplace_prop=prop,
            )
            grant_npc_wallet_credits(
                self.sim,
                eid,
                wage,
                source="ambient_job",
                property_id=property_id,
                property_name=str(prop.get("name", property_id)).strip() or property_id,
                wage_due=wage,
                wage_paid=wage,
                hour=current_hour,
            )


__all__ = ["NPCIncomeSystem"]
