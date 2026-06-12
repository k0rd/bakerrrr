"""Recurring real-income support for employed NPCs."""

from __future__ import annotations

from engine.systems import System
from game.components import FinancialProfile, Inventory, Occupation, Position, Vitality
from game.player_businesses import actor_player_business_employment
from game.population import work_shift_active
from game.property_runtime import resolve_property_record
from game.system_support.npc_income_runtime import (
    ensure_financial_income_fields,
    grant_npc_wallet_credits,
    npc_hourly_wage,
)


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
    """Top up loaded, on-shift non-player employees once per in-world hour."""

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
            if getattr(profile, "last_income_hour", None) is None:
                profile.last_income_hour = current_hour
                continue
            if int(getattr(profile, "last_income_hour", current_hour) or current_hour) >= current_hour:
                continue
            if player_eid is not None and actor_player_business_employment(self.sim, eid, owner_eid=player_eid) is not None:
                continue

            workplace = getattr(occupation, "workplace", None)
            property_id = _text(workplace.get("property_id")) if isinstance(workplace, dict) else ""
            prop = resolve_property_record(self.sim, property_id, include_saved=False)
            if not isinstance(prop, dict):
                continue
            if not work_shift_active(self.sim, occupation=occupation, workplace_prop=prop, hour=current_clock_hour):
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
