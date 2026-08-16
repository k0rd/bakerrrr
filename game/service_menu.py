import random

from engine.events import Event
from engine.systems import System
from game.appearance_loadout import STYLE_SERVICE_OPTIONS, style_service_kinds_for_property
from game.bodyguard_runtime import (
    BODYGUARD_MAX_CHANNEL_GUARDS,
    BODYGUARD_SERVICE_ID,
    BODYGUARD_TIER_PROFILES,
    active_bodyguard_contracts,
    bodyguard_channel_summary,
)
from game.cult_runtime import CULT_SERVICE_IDS, cult_property_association, cult_services_for_property
from game.civic_records import (
    CIVIC_RECORDS_SERVICE_ID,
    LICENSE_FEES,
    civic_census_lines,
    civic_license_is_active,
    civic_license_ledger_lines,
    civic_people_records,
    civic_person_record_lines,
    civic_records_authority,
    purchase_civic_license,
    remember_civic_record_inspection,
)
from game.components import FinancialProfile, Inventory, NPCNeeds, NPCSettlement, NPCRoutine, Occupation, PlayerAssets, Position
from game.casino_ui_runtime import (
    CASINO_FLOOR_ARCHETYPES,
    CASINO_MACHINE_SERVICE_IDS,
    CASINO_TABLE_SERVICE_IDS,
    casino_host_style,
    default_casino_ui_state,
    ensure_casino_ui_state,
)
from game.holdem_cash_runtime import (
    HOLDEM_CASH_SERVICE_ID,
    holdem_cash_join,
    holdem_cash_leave,
    holdem_cash_public_snapshot,
    holdem_cash_submit_action,
    holdem_cash_table_for_property,
)
from game.finance_services import _nearest_property_with_finance_service
from game.ecology_registry import (
    FAUNA_CULL_FEE,
    ecology_species_registry_rows,
    initiate_fauna_cull,
)
from game.herbal_chemistry_runtime import secondary_trait_labels
from game.justice_runtime import held_property_snapshot as _justice_held_property_snapshot
from game.opportunities import SERVICE_JOB_BOARD_SERVICES, service_job_board_offers
from game.player_businesses import (
    player_business_account_balance,
    player_business_customer_policy,
    player_business_customer_policy_label,
    player_business_employee_wage_level_label,
    player_business_employee_wage_rows,
    player_business_hours_mode,
    player_business_hours_mode_label,
    player_business_markup_mode,
    player_business_markup_mode_label,
    player_business_next_employee_wage_level,
    player_business_next_customer_policy,
    player_business_next_hours_mode,
    player_business_next_markup_mode,
    player_business_remodel_options,
    player_business_remodel_quote,
    player_business_set_customer_policy,
    player_business_set_employee_wage_level,
    player_business_set_hours_mode,
    player_business_set_markup_mode,
    player_business_status_snapshot,
    player_business_summary,
    player_owned_businesses_for_actor,
)
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import (
    finance_services_for_property as _finance_services_for_property,
    property_covering as _property_covering,
    property_infrastructure_role as _property_infrastructure_role,
    property_is_storefront as _property_is_storefront,
    property_metadata as _property_metadata,
    resolve_property_record as _resolve_property_record,
    site_services_for_property as _site_services_for_property,
)
from game.justice_dispatch_runtime import request_player_justice_dispatch
from game.service_runtime import (
    CASINO_CRASH_MAX_MULTIPLIER,
    CASINO_CRASH_STEP_TICKS,
    CASINO_KENO_DRAW_COUNT,
    CASINO_KENO_MAX_PICKS,
    CASINO_KENO_NUMBER_COUNT,
    CASINO_KENO_PAYOUT_MULTIPLIERS,
    CASINO_ROULETTE_NUMBER_MAX,
    CASINO_GAME_SERVICE_IDS,
    CASINO_PLINKO_LANE_COUNT,
    TRANSIT_SERVICE_IDS,
    _casino_apply_round_result,
    _casino_ascii_card_block,
    _casino_ascii_keno_board,
    _casino_ascii_plinko_board,
    _casino_baccarat_normalize_session,
    _casino_baccarat_resolve,
    _casino_baccarat_start,
    _casino_blackjack_line,
    _casino_blackjack_total,
    _casino_cards_text,
    _casino_craps_normalize_session,
    _casino_craps_market_from_key,
    _casino_craps_remove_bet,
    _casino_craps_resolve,
    _casino_craps_stage_bet,
    _casino_craps_start,
    _casino_crash_adjust_auto,
    _casino_crash_advance,
    _casino_crash_cashout,
    _casino_crash_cycle_auto_step,
    _casino_crash_launch,
    _casino_crash_multiplier_for_step,
    _casino_crash_normalize_session,
    _casino_crash_resolve,
    _casino_crash_setup,
    _casino_crash_toggle_auto,
    _casino_bloom_cards_cashout,
    _casino_bloom_cards_grow,
    _casino_bloom_cards_normalize_session,
    _casino_bloom_cards_score,
    _casino_bloom_cards_start,
    _casino_game_profile,
    _casino_game_title,
    _casino_keno_draw,
    _casino_keno_multiplier_text,
    _casino_keno_normalize_session,
    _casino_keno_payout_multiplier,
    _casino_keno_start,
    _casino_keno_toggle_pick,
    _casino_holdem_resolve,
    _casino_holdem_start,
    _casino_plinko_resolve,
    _casino_roulette_normalize_session,
    _casino_roulette_market_from_key,
    _casino_roulette_remove_bet,
    _casino_roulette_resolve,
    _casino_roulette_stage_bet,
    _casino_roulette_start,
    _casino_round_seed,
    _casino_slot_round_contract,
    _casino_slots_resolve,
    _casino_table_context,
    _casino_three_bones_market_from_key,
    _casino_three_bones_market_order,
    _casino_three_bones_normalize_session,
    _casino_three_bones_remove_bet,
    _casino_three_bones_resolve,
    _casino_three_bones_stage_bet,
    _casino_three_bones_start,
    _casino_three_bright_market_from_key,
    _casino_three_bright_market_order,
    _casino_three_bright_normalize_session,
    _casino_three_bright_remove_bet,
    _casino_three_bright_resolve,
    _casino_three_bright_stage_bet,
    _casino_three_bright_start,
    _casino_three_card_poker_normalize_session,
    _casino_three_card_poker_resolve,
    _casino_three_card_poker_start,
    _casino_twenty_one_action_ids,
    _casino_twenty_one_normalize_session,
    _casino_twenty_one_resolve,
    _casino_twenty_one_start,
    _casino_video_poker_draw,
    _casino_video_poker_normalize_session,
    _casino_video_poker_start,
    _casino_video_poker_toggle_hold,
    _credit_amount_label,
    _int_or_default,
    _line_text,
    _sentence_from_note,
    _service_menu_option_label,
    _site_service_label,
    _site_service_roll_index,
    _storefront_service_profile,
    _tick_duration_label,
    _transit_destinations as _shared_transit_destinations,
    _transit_fare_label,
    _transit_inventory_label,
    _transit_payment_profile,
    _transit_service_profile,
    _transit_service_title,
    _transit_travel_ticks,
    _vehicle_sale_offer_label,
    _vehicle_sale_offers,
    _vehicle_sale_quality,
    _vehicle_sale_quality_title,
    _vehicle_sale_stats_text,
)
from game.skills import skill_label as _skill_label
from game.signal_jammer_runtime import electronic_fixture_interference_status
from game.system_support.building_repair_runtime import owned_repairable_buildings as _owned_repairable_buildings
from game.system_support.npc_behavior_runtime import (
    _nutrition_capabilities_for_property,
    _receive_nutrition_at_actor,
)


class ServiceMenuSystem(System):

    ROOM_STAY_HOUR_OPTIONS = (1, 2, 4, 6, 8)

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.runs_without_turn = True
        self.player_eid = player_eid
        self.pending_service_result = None
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("casino_ui_action", self.on_casino_ui_action)
        self.sim.events.subscribe("holdem_cash_view_request", self.on_holdem_cash_view_request)
        self.sim.events.subscribe("dialog_close_request", self.on_dialog_close_request)
        self.sim.events.subscribe("service_menu_execute_request", self.on_service_menu_execute_request)
        self.sim.events.subscribe("site_service_started", self.on_site_service_started)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("site_service_blocked", self.on_site_service_blocked)
        self.sim.events.subscribe("site_intel_report", self.on_site_intel_report)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("banking_action_blocked", self.on_banking_action_blocked)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("insurance_action_blocked", self.on_insurance_action_blocked)

    def update(self):
        state = self._casino_ui_state()
        if not bool(state.get("open")):
            return
        service = str(state.get("service", "")).strip().lower()
        if service == HOLDEM_CASH_SERVICE_ID:
            prop = self.sim.properties.get(state.get("property_id"))
            table = holdem_cash_table_for_property(self.sim, state.get("property_id"), ensure=False)
            snapshot = holdem_cash_public_snapshot(self.sim, table, self.player_eid)
            current = state.get("session") if isinstance(state.get("session"), dict) else {}
            if isinstance(prop, dict) and isinstance(snapshot, dict) and int(snapshot.get("revision", 0) or 0) != int(current.get("revision", -1) or -1):
                selected = self._selected_casino_row()
                selected_id = str(selected.get("id", "") or "") if isinstance(selected, dict) else ""
                self._open_holdem_cash_table(prop, table=table, selected_id=selected_id)
            return
        if service != "crash":
            return
        session = _casino_crash_normalize_session(state.get("session"))
        if not session or session.get("phase") != "live":
            return
        prop = self.sim.properties.get(state.get("property_id"))
        if not isinstance(prop, dict):
            prop = {
                "id": session.get("property_id") or state.get("property_id"),
                "name": session.get("property_name", "Casino"),
            }
        selected = self._selected_casino_row()
        selected_id = str(selected.get("id", "")).strip().lower() if isinstance(selected, dict) else ""
        live_tick = self._crash_live_tick(session)
        next_session, round_result = _casino_crash_advance(session, live_tick)
        if round_result:
            self._settle_casino_round(prop, "crash", round_result)
            return
        if next_session and next_session != session:
            self._open_crash_table(prop, next_session, selected_id=selected_id)

    def _crash_live_tick(self, session):
        try:
            sim_tick = int(getattr(self.sim, "tick", 0) or 0)
        except (TypeError, ValueError):
            sim_tick = 0
        try:
            last_tick = session.get("last_step_tick")
            if last_tick is None:
                last_tick = session.get("launched_tick")
            last_tick = int(last_tick if last_tick is not None else sim_tick)
        except (TypeError, ValueError):
            last_tick = sim_tick
        return max(sim_tick, last_tick + CASINO_CRASH_STEP_TICKS)

    def _dialog_ui_state(self):
        state = getattr(self.sim, "dialog_ui", None)
        if state is None:
            state = {
                "open": False,
                "npc_eid": None,
                "title": "Conversation",
                "subtitle": "",
                "transcript": [],
                "topics": [],
                "selected_index": 0,
                "scroll": 0,
                "hint": "",
                "new_topic_ids": [],
                "close_pending": False,
            }
            self.sim.dialog_ui = state
        state.setdefault("kind", "conversation")
        state.setdefault("property_id", None)
        state.setdefault("close_pending", False)
        state.setdefault("machine_action", None)
        state.setdefault("service_menu_mode", "root")
        state.setdefault("casino_session", None)
        return state

    def _position_for(self, eid):
        return self.sim.ecs.get(Position).get(eid)

    def _casino_ui_state(self):
        return ensure_casino_ui_state(self.sim)

    def _close_casino_ui(self):
        state = self._casino_ui_state()
        state.update(default_casino_ui_state())
        self.sim.set_time_paused(False, reason="dialog")

    def _assets_for(self, eid):
        return self.sim.ecs.get(PlayerAssets).get(eid)

    def _profile_for(self, eid):
        return self.sim.ecs.get(FinancialProfile).get(eid)

    def _nearest_property_with_service(self, pos, service, radius=2):
        return _nearest_property_with_finance_service(
            self.sim,
            self.player_eid,
            pos,
            service,
            radius=radius,
        )

    def _clear_pending_service_result(self):
        self.pending_service_result = None

    def _pending_property_name(self, fallback="Service"):
        pending = self.pending_service_result if isinstance(self.pending_service_result, dict) else {}
        property_id = pending.get("property_id")
        prop = _resolve_property_record(self.sim, property_id) if property_id is not None else None
        if isinstance(prop, dict):
            name = str(prop.get("name", prop.get("id", fallback))).strip()
            if name:
                return name
        name = str(pending.get("property_name", fallback)).strip()
        return name or fallback

    def _wallet_credits(self):
        assets = self._assets_for(self.player_eid)
        return int(getattr(assets, "credits", 0)) if assets else 0

    def _emit_casino_audio_event(self, event_type, **data):
        state = self._casino_ui_state()
        payload = {
            "eid": self.player_eid,
            "property_id": state.get("property_id"),
            "service": str(state.get("service", "") or "").strip().lower(),
            "mode": str(state.get("mode", "") or "").strip().lower(),
        }
        payload.update(data)
        self.sim.emit(Event(str(event_type), **payload))

    def _ticks_per_hour(self):
        world_traits = getattr(self.sim, "world_traits", {})
        clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
        try:
            ticks_per_hour = int(clock.get("ticks_per_hour", 600))
        except (TypeError, ValueError, AttributeError):
            ticks_per_hour = 600
        return max(60, ticks_per_hour)

    def _current_clock_hour_float(self):
        world_traits = getattr(self.sim, "world_traits", {})
        clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
        try:
            start_hour = float(clock.get("start_hour", 9))
        except (TypeError, ValueError, AttributeError):
            start_hour = 9.0
        return (start_hour + (float(getattr(self.sim, "tick", 0) or 0) / float(self._ticks_per_hour()))) % 24.0

    def _format_clock_hour(self, hour):
        hour = float(hour) % 24.0
        total_minutes = int(round(hour * 60.0)) % (24 * 60)
        clock_hour = total_minutes // 60
        minute = total_minutes % 60
        suffix = "AM" if clock_hour < 12 else "PM"
        display_hour = clock_hour % 12
        if display_hour == 0:
            display_hour = 12
        return f"{display_hour}:{minute:02d} {suffix}"

    def _lodging_checkout_hour(self, prop):
        metadata = (prop or {}).get("metadata", {}) if isinstance(prop, dict) else {}
        raw_hour = metadata.get("lodging_checkout_hour") if isinstance(metadata, dict) else None
        try:
            hour = float(raw_hour)
        except (TypeError, ValueError):
            prop_id = str((prop or {}).get("id", "") if isinstance(prop, dict) else "").strip()
            prop_name = str((prop or {}).get("name", "") if isinstance(prop, dict) else "").strip()
            seed_text = f"{getattr(self.sim, 'seed', 0)}:lodging-checkout:{prop_id}:{prop_name}"
            hour = 9.5 + random.Random(seed_text).random()
        return hour % 24.0

    def _ticks_until_clock_hour(self, target_hour):
        current_hour = self._current_clock_hour_float()
        delta_hours = (float(target_hour) - current_hour) % 24.0
        if delta_hours <= 0.01:
            delta_hours += 24.0
        return max(1, int(round(delta_hours * float(self._ticks_per_hour()))))

    def _player_owns_property(self, prop):
        if not isinstance(prop, dict):
            return False
        owner_eid = prop.get("owner_eid")
        try:
            if owner_eid is not None and int(owner_eid) == int(self.player_eid):
                return True
        except (TypeError, ValueError):
            if owner_eid == self.player_eid:
                return True
        assets = self._assets_for(self.player_eid)
        if not assets:
            return False
        property_id = str(prop.get("id", "")).strip()
        return bool(property_id and property_id in getattr(assets, "owned_property_ids", set()))

    def _anchor_matches_property(self, anchor, prop):
        if not isinstance(prop, dict) or not anchor:
            return False
        prop_id = str(prop.get("id", "") or "").strip()
        if isinstance(anchor, dict):
            anchor_prop = str(anchor.get("property_id", "") or anchor.get("prop_id", "") or "").strip()
            if anchor_prop and anchor_prop == prop_id:
                return True
            x = anchor.get("x")
            y = anchor.get("y")
            z = anchor.get("z", prop.get("z", 0))
        elif isinstance(anchor, (tuple, list)) and len(anchor) >= 2:
            x = anchor[0]
            y = anchor[1]
            z = anchor[2] if len(anchor) >= 3 else prop.get("z", 0)
        else:
            return False
        try:
            covered = _property_covering(self.sim, int(x), int(y), int(z or 0))
        except (TypeError, ValueError):
            return False
        return isinstance(covered, dict) and str(covered.get("id", "") or "").strip() == prop_id

    def _player_can_call_justice_from_property(self, eid, prop, pos):
        if not isinstance(prop, dict):
            return False
        if self._player_owns_property(prop):
            return True
        prop_id = str(prop.get("id", "") or "").strip()
        settlement = self.sim.ecs.get(NPCSettlement).get(eid)
        if settlement is not None:
            if prop_id and prop_id == str(getattr(settlement, "home_property_id", "") or "").strip():
                return True
            if prop_id and prop_id == str(getattr(settlement, "work_property_id", "") or "").strip():
                return True
        occupation = self.sim.ecs.get(Occupation).get(eid)
        if occupation is not None:
            workplace = getattr(occupation, "workplace", None)
            if self._anchor_matches_property(workplace, prop):
                return True
            if isinstance(workplace, str) and workplace.strip() == prop_id:
                return True
        routine = self.sim.ecs.get(NPCRoutine).get(eid)
        if routine is not None:
            if self._anchor_matches_property(getattr(routine, "home", None), prop):
                return True
            if self._anchor_matches_property(getattr(routine, "work", None), prop):
                return True
        return False

    def _inventory_item_count(self, item_id):
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        if not inventory:
            return 0
        item_id = str(item_id or "").strip().lower()
        if not item_id:
            return 0
        return sum(
            int(entry.get("quantity", 0) or 0)
            for entry in list(getattr(inventory, "items", ()) or ())
            if str(entry.get("item_id", "") or "").strip().lower() == item_id
        )

    def _player_can_redeem_meal_voucher(self, prop):
        if not isinstance(prop, dict):
            return False
        caps = _nutrition_capabilities_for_property(prop)
        if not caps.get("food"):
            return False
        if self._inventory_item_count("meal_voucher") <= 0:
            return False
        needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
        if needs is None:
            return False
        hunger = getattr(needs, "hunger", 100.0)
        hunger = 100.0 if hunger is None else float(hunger)
        return hunger < 90.0

    def _redeem_meal_voucher_lines(self, prop, result, before_hunger, before_thirst):
        prop_name = str((prop or {}).get("name", (prop or {}).get("id", "Meal"))).strip() or "Meal"
        needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
        after_hunger = float(getattr(needs, "hunger", before_hunger) if needs is not None else before_hunger)
        after_thirst = float(getattr(needs, "thirst", before_thirst) if needs is not None else before_thirst)
        lines = ["Voucher redeemed for an instant meal."]
        if result and isinstance(result, dict):
            bits = []
            if abs(after_hunger - float(before_hunger)) > 0.01:
                bits.append(f"F {int(round(before_hunger))}->{int(round(after_hunger))}")
            if abs(after_thirst - float(before_thirst)) > 0.01:
                bits.append(f"W {int(round(before_thirst))}->{int(round(after_thirst))}")
            if bits:
                lines.append(" ".join(bits))
        return f"Meal Voucher: {prop_name}", lines

    def _casino_session(self):
        state = self._casino_ui_state()
        session = state.get("session")
        return session if isinstance(session, dict) else None

    def _set_casino_session(self, session):
        state = self._casino_ui_state()
        state["session"] = dict(session) if isinstance(session, dict) else None
        self._dialog_ui_state()["casino_session"] = None

    def _clear_casino_session(self):
        self._casino_ui_state()["session"] = None
        self._dialog_ui_state()["casino_session"] = None

    def _casino_prop_name(self, prop):
        if isinstance(prop, dict):
            name = str(prop.get("name", prop.get("id", "Casino"))).strip()
            if name:
                return name
        return "Casino"

    def _casino_round_seed(self, prop, service, wager):
        round_index = _site_service_roll_index(self.sim, self.player_eid, prop, service)
        return _casino_round_seed(self.sim, self.player_eid, prop, service, wager, round_index)

    def _casino_commit_stake(self, amount):
        amount = max(0, int(amount))
        assets = self._assets_for(self.player_eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < amount:
            return False, credits
        if assets and amount > 0:
            assets.credits = max(0, int(assets.credits) - amount)
            credits = int(assets.credits)
            self._emit_casino_audio_event("casino_chips_bet", amount=int(amount))
        return True, credits

    def _casino_selectable_indices(self, rows=None):
        source_rows = list(rows if rows is not None else self._casino_ui_state().get("rows", ()) or ())
        return [
            idx
            for idx, row in enumerate(source_rows)
            if isinstance(row, dict) and bool(row.get("selectable", True))
        ]

    def _normalize_casino_selection(self):
        state = self._casino_ui_state()
        rows = list(state.get("rows", ()) or ())
        selectable = self._casino_selectable_indices(rows)
        if not selectable:
            state["selected_index"] = 0
            return None
        try:
            selected = int(state.get("selected_index", 0))
        except (TypeError, ValueError):
            selected = selectable[0]
        if selected in selectable:
            state["selected_index"] = selected
            return selected
        if selected < selectable[0]:
            state["selected_index"] = selectable[0]
            return selectable[0]
        for index in reversed(selectable):
            if index <= selected:
                state["selected_index"] = index
                return index
        state["selected_index"] = selectable[0]
        return selectable[0]

    def _selected_casino_row(self):
        state = self._casino_ui_state()
        rows = list(state.get("rows", ()) or ())
        selected = self._normalize_casino_selection()
        if selected is None or selected < 0 or selected >= len(rows):
            return None
        row = rows[selected]
        return row if isinstance(row, dict) and bool(row.get("selectable", True)) else None

    def _scroll_casino_body(self, *, amount=0, edge=""):
        state = self._casino_ui_state()
        try:
            maximum = max(0, int(state.get("body_scroll_max", 0) or 0))
        except (TypeError, ValueError):
            maximum = 0
        try:
            current = int(state.get("body_scroll", 0) or 0)
        except (TypeError, ValueError):
            current = 0

        edge = str(edge or "").strip().lower()
        if edge == "home":
            current = 0
        elif edge == "end":
            current = maximum
        else:
            current += int(amount or 0)
        state["body_scroll"] = max(0, min(current, maximum))
        state["body_scroll_manual"] = True
        return int(state["body_scroll"])

    def _open_casino_ui(
        self,
        *,
        mode,
        prop,
        host_style,
        title,
        subtitle="",
        body_lines=None,
        body_focus_line=-1,
        rail_lines=None,
        rows=None,
        hint="",
        close_pending=False,
        floor_page="games",
        service="",
        session=None,
        art=None,
        return_to="",
        return_option_id="",
        selected_id="",
        pause_time=True,
    ):
        state = self._casino_ui_state()
        dialog_state = self._dialog_ui_state()
        dialog_state["open"] = False
        dialog_state["close_pending"] = False
        dialog_state["machine_action"] = None
        dialog_state["casino_session"] = None
        self.sim.set_time_paused(bool(pause_time), reason="dialog")
        state.update({
            "open": True,
            "mode": str(mode or "floor").strip().lower() or "floor",
            "host_style": str(host_style or "floor").strip().lower() or "floor",
            "property_id": prop.get("id") if isinstance(prop, dict) else None,
            "title": str(title or "Casino").strip() or "Casino",
            "subtitle": str(subtitle or "").strip(),
            "body_lines": list(body_lines or ()),
            "body_focus_line": int(body_focus_line) if str(body_focus_line).strip().lstrip("-").isdigit() else -1,
            "body_scroll": 0,
            "body_scroll_max": 0,
            "body_page_size": 1,
            "body_scroll_manual": False,
            "rail_lines": list(rail_lines or ()),
            "rows": list(rows or ()),
            "hint": str(hint or "").strip(),
            "close_pending": bool(close_pending),
            "floor_page": str(floor_page or state.get("floor_page", "games")).strip().lower() or "games",
            "service": str(service or "").strip().lower(),
            "session": dict(session) if isinstance(session, dict) else None,
            "art": dict(art) if isinstance(art, dict) else None,
            "return_to": str(return_to or "").strip().lower(),
            "return_option_id": str(return_option_id or "").strip().lower(),
        })
        if selected_id:
            selected_key = str(selected_id).strip().lower()
            for idx, row in enumerate(list(state.get("rows", ()) or ())):
                if not isinstance(row, dict) or not bool(row.get("selectable", True)):
                    continue
                if str(row.get("id", "")).strip().lower() == selected_key:
                    state["selected_index"] = idx
                    break
            else:
                state["selected_index"] = 0
        elif mode in {"floor", "services"}:
            state["selected_index"] = 0
        self._normalize_casino_selection()

    def _casino_common_rail_lines(self, prop, *, service="", session=None):
        lines = [
            "Wallet",
            _credit_amount_label(self._wallet_credits()),
        ]
        prop_name = self._casino_prop_name(prop)
        if prop_name:
            lines.extend([
                "",
                "Venue",
                prop_name,
            ])
        if service:
            lines.extend([
                "",
                "Game",
                _casino_game_title(service),
            ])
        if isinstance(session, dict):
            wager = max(0, int(session.get("wager", 0) or 0))
            stake = max(0, int(session.get("stake", wager) or 0))
            if wager > 0:
                lines.extend([
                    "",
                    "Chip",
                    _credit_amount_label(wager),
                ])
            if stake > 0:
                lines.extend([
                    "",
                    "Posted",
                    _credit_amount_label(stake),
                ])
            context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
            sponsor = str(context.get("sponsor_summary") or context.get("sponsor_kind") or "").strip()
            stake_profile = str(context.get("stake_profile", "")).strip().replace("_", " ")
            tone = str(context.get("table_tone", "")).strip().replace("_", " ")
            if sponsor or stake_profile or tone:
                table_bits = [bit for bit in (sponsor, tone, stake_profile) if bit]
                lines.extend([
                    "",
                    "Table",
                    " / ".join(table_bits[:3]),
                ])
        return lines

    def _casino_partition_rows(self, prop):
        pos = self._position_for(self.player_eid)
        if not pos or not isinstance(prop, dict):
            return [], []
        options, _storefront_service = self._service_menu_options(self.player_eid, prop, pos)
        option_map = {
            str(option.get("id", "")).strip().lower(): dict(option)
            for option in list(options or ())
            if isinstance(option, dict) and str(option.get("id", "")).strip()
        }

        game_rows = []
        machine_rows = []
        for service_id in CASINO_MACHINE_SERVICE_IDS:
            option = option_map.get(service_id)
            if option:
                machine_rows.append({
                    "id": f"game:{service_id}",
                    "label": str(option.get("label", _service_menu_option_label(service_id))).strip() or _service_menu_option_label(service_id),
                    "service": service_id,
                    "selectable": True,
                })
        table_rows = []
        for service_id in CASINO_TABLE_SERVICE_IDS:
            option = option_map.get(service_id)
            if option:
                label = str(option.get("label", _service_menu_option_label(service_id))).strip() or _service_menu_option_label(service_id)
                if service_id == HOLDEM_CASH_SERVICE_ID:
                    table = holdem_cash_table_for_property(self.sim, prop, ensure=False)
                    center = tuple((table or {}).get("center", ()) or ()) if isinstance(table, dict) else ()
                    if len(center) >= 3 and int(center[2]) != int(pos.z):
                        direction = "upstairs" if int(center[2]) > int(pos.z) else "downstairs"
                        label = f"{label} · {direction}"
                table_rows.append({
                    "id": f"game:{service_id}",
                    "label": label,
                    "service": service_id,
                    "selectable": True,
                })
        if machine_rows:
            game_rows.append({"id": "header:machines", "label": "Machines", "selectable": False, "style": "header"})
            game_rows.extend(machine_rows)
        if table_rows:
            game_rows.append({"id": "header:tables", "label": "Tables", "selectable": False, "style": "header"})
            game_rows.extend(table_rows)

        service_rows = []
        for option_id in ("trade_buy", "trade_sell", "banking", "insurance"):
            option = option_map.get(option_id)
            if option:
                service_rows.append({
                    "id": f"service:{option_id}",
                    "label": str(option.get("label", _service_menu_option_label(option_id))).strip() or _service_menu_option_label(option_id),
                    "option_id": option_id,
                    "selectable": True,
                })
        for option in list(options or ()):
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("id", "")).strip().lower()
            if not option_id or option_id in CASINO_GAME_SERVICE_IDS or option_id in {"trade_buy", "trade_sell", "banking", "insurance"}:
                continue
            service_rows.append({
                "id": f"service:{option_id}",
                "label": str(option.get("label", option_id)).strip() or option_id,
                "option_id": option_id,
                "selectable": True,
            })
        return game_rows, service_rows

    def _open_casino_floor(self, prop, *, page="games", selected_id=""):
        prop_name = self._casino_prop_name(prop)
        game_rows, service_rows = self._casino_partition_rows(prop)
        floor_page = "services" if str(page).strip().lower() == "services" else "games"
        rows = service_rows if floor_page == "services" else game_rows
        subtitle = "Floor services" if floor_page == "services" else "Games"
        body_lines = [
            f"{prop_name} keeps the game list up front so the floor reads like a real getaway.",
        ]
        if floor_page == "services":
            body_lines.append("House support and storefront actions stay here so they do not bury the tables.")
            if not self._casino_selectable_indices(rows):
                body_lines.append("No floor services are posted right now.")
        else:
            body_lines.append("Machines and tables are grouped separately for quick scanning.")
            if not self._casino_selectable_indices(rows):
                body_lines.append("No posted games are running on this floor right now.")
        rail_lines = self._casino_common_rail_lines(prop)
        rail_lines.extend([
            "",
            "Controls",
            "Tab page",
            "Enter select",
            "Esc leave",
        ])
        self._clear_pending_service_result()
        self._open_casino_ui(
            mode="services" if floor_page == "services" else "floor",
            prop=prop,
            host_style="floor",
            title=prop_name,
            subtitle=subtitle,
            body_lines=body_lines,
            rail_lines=rail_lines,
            rows=rows,
            hint="Tab switches Games and Floor services. Esc leaves the floor.",
            close_pending=False,
            floor_page=floor_page,
            service="",
            session=None,
            return_to="floor",
            selected_id=selected_id,
        )

    def _open_casino_wager(self, prop, service, *, host_style="", return_to="", selected_id=""):
        profile = _casino_game_profile(service)
        if not profile:
            self._present_service_result("Casino", ["That game is not running on this floor right now."], property_id=prop.get("id"))
            return
        if str(service or "").strip().lower() == HOLDEM_CASH_SERVICE_ID:
            table = holdem_cash_table_for_property(self.sim, prop, ensure=True)
            player_pos = self._position_for(self.player_eid)
            center = tuple((table or {}).get("center", ()) or ()) if isinstance(table, dict) else ()
            if player_pos is not None and len(center) >= 3 and int(player_pos.z) != int(center[2]):
                direction = "upstairs" if int(center[2]) > int(player_pos.z) else "downstairs"
                self._present_service_result(
                    "Texas Hold'em Cash",
                    [
                        f"The live table is {direction} in the poker room.",
                        "Take the stairs, then interact with an open gold chair to claim that exact seat.",
                    ],
                    property_id=prop.get("id") if isinstance(prop, dict) else None,
                )
                return
            self._open_holdem_cash_table(prop, table=table, selected_id=selected_id)
            return
        host_style = str(host_style or casino_host_style(prop)).strip().lower() or "floor"
        prop_name = self._casino_prop_name(prop)
        table_context = _casino_table_context(self.sim, prop, game=service)
        if not bool(table_context.get("allowed", True)):
            self._present_service_result(
                _casino_game_title(service),
                [
                    "That table is not open here.",
                    "Three Bright is a house game for gang-linked hosts, not a public casino listing.",
                ],
                property_id=prop.get("id"),
            )
            return
        context_ladder = tuple(int(amount) for amount in tuple(table_context.get("stake_ladder", ()) or ()) if int(amount) > 0)
        base_bets = context_ladder or tuple(int(amount) for amount in tuple(profile.get("bet_options", ()) or ()) if int(amount) > 0)
        owner_limit = self._player_owns_property(prop) and bool(base_bets)
        if service == "three_bright":
            owner_limit = False
        wager_values = list(base_bets)
        if owner_limit:
            high_limit = int(max(base_bets)) * 2
            if high_limit not in wager_values:
                wager_values.append(high_limit)
        wager_values = sorted(set(wager_values))
        rows = []
        for amount in wager_values:
            label = f"Bet {_credit_amount_label(amount)}"
            if owner_limit and amount > max(base_bets):
                label += " [owner limit]"
            rows.append({
                "id": f"wager:{amount}",
                "label": label,
                "wager": int(amount),
                "selectable": True,
            })
        body_lines = [
            str(profile.get("prompt", "Choose a wager.")).strip() or "Choose a wager.",
            str(profile.get("note", "")).strip() or "Pick a stake and play a round.",
        ]
        table_read = str(table_context.get("table_read", "")).strip()
        if table_read:
            body_lines.append(table_read)
        if owner_limit:
            body_lines.append("Owner perk: this floor will book one higher posted stake for you.")
        rail_lines = self._casino_common_rail_lines(prop, service=service)
        rail_lines.extend([
            "",
            "Choose",
            "one stake",
        ])
        if table_context.get("stake_profile"):
            rail_lines.extend([
                "",
                "Stakes",
                str(table_context.get("stake_profile", "standard")).replace("_", " "),
            ])
        if not rows:
            body_lines.append("No posted wager sizes are available right now.")
        self._clear_pending_service_result()
        self._open_casino_ui(
            mode="wager",
            prop=prop,
            host_style=host_style,
            title=f"{_casino_game_title(service)}: {prop_name}",
            subtitle="Choose a wager",
            body_lines=body_lines,
            rail_lines=rail_lines,
            rows=rows,
            hint="Choose a stake. Esc backs out.",
            close_pending=False,
            floor_page="games",
            service=service,
            session=None,
            return_to=str(return_to or ("floor" if host_style == "floor" else "service_menu")).strip().lower(),
            return_option_id=str(service or "").strip().lower(),
            selected_id=selected_id,
        )

    def _return_from_casino_host(self, prop):
        host_style = str(self._casino_ui_state().get("host_style", casino_host_style(prop))).strip().lower()
        if host_style == "floor":
            self._open_casino_floor(prop)
            return
        self._close_casino_ui()
        if isinstance(prop, dict):
            self._open_property_service_surface(prop)

    def _roulette_market_order(self):
        return [
            *(f"straight:{number}" for number in range(0, CASINO_ROULETTE_NUMBER_MAX + 1)),
            "color:red",
            "color:black",
            "parity:odd",
            "parity:even",
            "range:low",
            "range:high",
            "dozen:1",
            "dozen:2",
            "dozen:3",
            "column:1",
            "column:2",
            "column:3",
        ]

    def _craps_market_order(self):
        return [
            "pass",
            "dont_pass",
            "field",
            "pass_odds",
            "dont_pass_odds",
            "place:4",
            "place:5",
            "place:6",
            "place:8",
            "place:9",
            "place:10",
            "hardway:4",
            "hardway:6",
            "hardway:8",
            "hardway:10",
            "prop:2",
            "prop:3",
            "prop:11",
            "prop:12",
            "prop:any_craps",
            "prop:any_seven",
        ]

    def _three_bright_market_order(self, session=None):
        context = session.get("table_context") if isinstance(session, dict) and isinstance(session.get("table_context"), dict) else None
        return list(_casino_three_bright_market_order(context))

    def _three_bones_market_order(self, session=None):
        context = session.get("table_context") if isinstance(session, dict) and isinstance(session.get("table_context"), dict) else None
        return list(_casino_three_bones_market_order(context))

    def _move_three_bright_cursor(self, session, dx, dy):
        current = _casino_three_bright_normalize_session(session)
        if not current:
            return None
        order = list(self._three_bright_market_order(current))
        if not order:
            return current
        try:
            index = order.index(str(current.get("cursor_key", "single:red")).strip().lower())
        except ValueError:
            index = 0
        index = max(0, min(len(order) - 1, index + int(dx) + (int(dy) * 3)))
        current["cursor_key"] = order[index]
        return current

    def _move_three_bones_cursor(self, session, dx, dy):
        current = _casino_three_bones_normalize_session(session)
        if not current:
            return None
        order = list(self._three_bones_market_order(current))
        if not order:
            return current
        try:
            index = order.index(str(current.get("cursor_key", "small")).strip().lower())
        except ValueError:
            index = 0
        index = max(0, min(len(order) - 1, index + int(dx) + (int(dy) * 4)))
        current["cursor_key"] = order[index]
        return current

    def _move_casino_row_selection(self, delta):
        state = self._casino_ui_state()
        selectable = self._casino_selectable_indices()
        if not selectable:
            return False
        selected = self._normalize_casino_selection()
        if selected is None:
            state["selected_index"] = selectable[0]
            return True
        previous = int(selected)
        try:
            cursor = selectable.index(selected)
        except ValueError:
            cursor = 0
        cursor = max(0, min(len(selectable) - 1, cursor + int(delta)))
        state["selected_index"] = selectable[cursor]
        return int(state["selected_index"]) != previous

    def _move_keno_cursor(self, session, dx, dy):
        current = _casino_keno_normalize_session(session)
        if not current:
            return None
        cursor = max(1, min(CASINO_KENO_NUMBER_COUNT, int(current.get("cursor", 1) or 1)))
        row = (cursor - 1) // 5
        col = (cursor - 1) % 5
        row = max(0, min(((CASINO_KENO_NUMBER_COUNT - 1) // 5), row + int(dy)))
        col = max(0, min(4, col + int(dx)))
        next_cursor = (row * 5) + col + 1
        next_cursor = max(1, min(CASINO_KENO_NUMBER_COUNT, next_cursor))
        current["cursor"] = next_cursor
        return current

    def _move_roulette_cursor(self, session, dx, dy):
        current = _casino_roulette_normalize_session(session)
        if not current:
            return None
        order = list(self._roulette_market_order())
        if not order:
            return current
        try:
            index = order.index(str(current.get("cursor_key", "straight:0")).strip().lower())
        except ValueError:
            index = 0
        index = max(0, min(len(order) - 1, index + int(dx) + (int(dy) * 5)))
        current["cursor_key"] = order[index]
        return current

    def _move_craps_cursor(self, session, dx, dy):
        current = _casino_craps_normalize_session(session)
        if not current:
            return None
        order = list(self._craps_market_order())
        if not order:
            return current
        try:
            index = order.index(str(current.get("cursor_key", "pass")).strip().lower())
        except ValueError:
            index = 0
        index = max(0, min(len(order) - 1, index + int(dx) + (int(dy) * 3)))
        current["cursor_key"] = order[index]
        return current

    def _open_casino_modal(self, prop, service, *, subtitle="", transcript=None, topics=None, hint="", mode="root", session=None, art=None):
        prop_name = self._casino_prop_name(prop)
        host_style = str(self._casino_ui_state().get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop)
        return_to = str(self._casino_ui_state().get("return_to", "floor" if host_style == "floor" else "service_menu")).strip().lower()
        body_lines = list(transcript or ())
        context = session.get("table_context") if isinstance(session, dict) and isinstance(session.get("table_context"), dict) else {}
        table_read = str(context.get("table_read", "")).strip()
        if table_read and table_read.lower() not in {str(line).strip().lower() for line in body_lines}:
            body_lines.insert(0, table_read)
        rows = []
        for row in list(topics or ()):
            if not isinstance(row, dict):
                continue
            option_id = str(row.get("id", "")).strip().lower()
            if not option_id:
                continue
            rows.append({
                "id": option_id,
                "label": str(row.get("label", option_id)).strip() or option_id,
                "option_id": option_id,
                "selectable": True,
            })
        rail_lines = self._casino_common_rail_lines(prop, service=service, session=session)
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=host_style,
            title=f"{_casino_game_title(service)}: {prop_name}",
            subtitle=str(subtitle or "").strip(),
            body_lines=body_lines,
            rail_lines=rail_lines,
            rows=rows,
            hint=str(hint or "").strip(),
            close_pending=False,
            floor_page=self._casino_ui_state().get("floor_page", "games"),
            service=service,
            session=session,
            art=art,
            return_to=return_to,
            return_option_id=str(service or "").strip().lower(),
        )

    def _emit_casino_blocked(self, prop, service, reason, **data):
        prop_name = self._casino_prop_name(prop)
        payload = {
            "eid": self.player_eid,
            "property_id": prop.get("id") if isinstance(prop, dict) else None,
            "property_name": prop_name,
            "service": str(service or "").strip().lower(),
            "reason": str(reason or "blocked").strip().lower(),
        }
        payload.update(data)
        if bool(self._casino_ui_state().get("open")):
            self.sim.emit(Event("site_service_blocked", **payload))
            title, lines = self._site_service_blocked_lines(Event("site_service_blocked", **payload))
            self._open_casino_result(prop, service, title, lines)
            return
        self._begin_pending_service_result(
            channel="site",
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            property_name=prop_name,
            service=service,
        )
        self.sim.emit(Event("site_service_blocked", **payload))

    def _emit_casino_round(self, prop, service, round_result, *, show_result=True):
        self._ensure_casino_action_time(prop, service, round_result)
        payload, blocked = _casino_apply_round_result(self.sim, self.player_eid, prop, service, round_result)
        if blocked:
            if show_result:
                self._begin_pending_service_result(
                    channel="site",
                    property_id=blocked.get("property_id"),
                    property_name=blocked.get("property_name", self._casino_prop_name(prop)),
                    service=service,
                )
            self.sim.emit(Event("site_service_blocked", **blocked))
            return False
        self._clear_casino_session()
        if show_result:
            self._begin_pending_service_result(
                channel="site",
                property_id=payload.get("property_id"),
                property_name=payload.get("property_name", self._casino_prop_name(prop)),
                service=service,
            )
        self.sim.emit(Event("site_service_used", **payload))
        return True

    def _open_casino_result(self, prop, service, title, lines, *, subtitle="", art=None):
        state = self._casino_ui_state()
        host_style = str(state.get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop)
        body_lines = list(lines or ())
        service_key = str(service or "").strip().lower()
        result_return_wager = 0
        wager_sources = [
            art if isinstance(art, dict) else {},
            state.get("session") if isinstance(state.get("session"), dict) else {},
            self._selected_casino_row() or {},
        ]
        for source in wager_sources:
            try:
                candidate = int(source.get("wager", 0) or 0)
            except (TypeError, ValueError, AttributeError):
                candidate = 0
            if candidate > 0:
                result_return_wager = candidate
                break
        body_focus_line = -1
        if service_key == "keno":
            for index, line in enumerate(body_lines):
                text = str(line or "").strip().lower()
                if text.startswith("pay row"):
                    body_focus_line = index
                    break
            if body_focus_line < 0:
                for index, line in enumerate(body_lines):
                    if str(line or "").strip().lower().startswith("hits:"):
                        body_focus_line = index
                        break
        elif service_key == "plinko":
            for index, line in enumerate(body_lines):
                text = str(line or "").strip().lower()
                if text.startswith("bucket "):
                    body_focus_line = index
                    break
            if body_focus_line < 0:
                for index, line in enumerate(body_lines):
                    if str(line or "").strip().lower().startswith("drop lane "):
                        body_focus_line = index
                        break
        rail_lines = self._casino_common_rail_lines(prop, service=service)
        rail_lines.extend([
            "",
            "Result",
            "Space / Enter",
        ])
        self._open_casino_ui(
            mode="result",
            prop=prop,
            host_style=host_style,
            title=title,
            subtitle=str(subtitle or "").strip(),
            body_lines=body_lines,
            body_focus_line=body_focus_line,
            rail_lines=rail_lines,
            rows=[],
            hint=f"Space or Enter returns to {_casino_game_title(service_key)} stakes.",
            close_pending=True,
            floor_page=state.get("floor_page", "games"),
            service=service,
            session=None,
            art=art,
            return_to=str(state.get("return_to", "floor" if host_style == "floor" else "service_menu")).strip().lower(),
            return_option_id=str(state.get("return_option_id", service)).strip().lower(),
        )
        state["result_return_wager"] = int(result_return_wager)

    def _advance_casino_action_time(self, prop, service, *, round_result=None):
        """Spend one world tick for a valid risk-bearing casino action.

        Crash owns a live tick graph already.  Other games use this shared
        seam so instant rounds, terminal decisions, continuations, and
        forfeited posted stakes all obey the same minimum without charging
        menu navigation or staged-bet editing.
        """

        service = str(service or "").strip().lower()
        if service == "crash":
            return 0
        start_tick = int(getattr(self.sim, "tick", 0) or 0)
        advanced = int(self.sim.advance_time(
            1,
            reason="casino_gambling_action",
            actor_eid=self.player_eid,
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            service=service,
        ) or 0)
        if isinstance(round_result, dict):
            round_result["_casino_action_time_spent"] = True
            round_result["time_advanced_ticks"] = max(
                1,
                int(round_result.get("time_advanced_ticks", 0) or 0) + advanced,
            )
            round_result["casino_action_started_tick"] = int(start_tick)
            round_result["casino_action_finished_tick"] = int(getattr(self.sim, "tick", start_tick) or start_tick)
        return advanced

    def _ensure_casino_action_time(self, prop, service, round_result):
        if not isinstance(round_result, dict):
            return 0
        already_spent = bool(round_result.pop("_casino_action_time_spent", False))
        if already_spent or str(service or "").strip().lower() == "crash":
            return 0
        return self._advance_casino_action_time(prop, service, round_result=round_result)

    def _settle_casino_round(self, prop, service, round_result, *, next_session=None, continue_notice=""):
        self._ensure_casino_action_time(prop, service, round_result)
        payload, blocked = _casino_apply_round_result(self.sim, self.player_eid, prop, service, round_result)
        if blocked:
            self._clear_casino_session()
            self.sim.emit(Event("site_service_blocked", **blocked))
            title, lines = self._site_service_blocked_lines(Event("site_service_blocked", **blocked))
            self._open_casino_result(prop, service, title, lines, art=round_result if isinstance(round_result, dict) else None)
            return False
        self.sim.emit(Event("site_service_used", **payload))
        if service == "craps" and isinstance(next_session, dict):
            normalized = _casino_craps_normalize_session(next_session)
            if normalized and dict(normalized.get("bets", {}) or {}):
                self._set_casino_session(normalized)
                notice = str(continue_notice or payload.get("headline", "") or payload.get("detail", "")).strip()
                self._open_craps_table(prop, normalized, notice=notice)
                return True
        self._clear_casino_session()
        title, lines = self._site_service_result_lines(Event("site_service_used", **payload))
        self._open_casino_result(prop, service, title, lines, art=round_result if isinstance(round_result, dict) else None)
        return True

    def _open_plinko_lane_menu(self, prop, service, wager, *, table_context=None):
        session = {
            "service": service,
            "property_id": prop.get("id"),
            "property_name": self._casino_prop_name(prop),
            "wager": int(wager),
            "stake": int(wager),
            "seed_token": self._casino_round_seed(prop, service, wager),
            "table_context": dict(table_context) if isinstance(table_context, dict) else {},
        }
        topics = [
            {"id": f"plinko:lane:{lane}", "label": f"Drop lane {lane + 1}"}
            for lane in range(CASINO_PLINKO_LANE_COUNT)
        ]
        transcript = [
            f"Choose a lane for {_credit_amount_label(wager)}.",
            "Center buckets pay best if the pegs keep the disc alive.",
            "",
            *_casino_ascii_plinko_board(),
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ]
        self._open_casino_modal(
            prop,
            service,
            subtitle="Choose a drop lane",
            transcript=transcript,
            topics=topics,
            hint="Pick a lane to drop the disc. Esc walks away and forfeits the posted chip.",
            mode="casino:plinko:lane",
            session=session,
            art=session,
        )

    def _open_twenty_one_table(self, prop, session):
        session = _casino_twenty_one_normalize_session(session)
        dealer_cards = list(session.get("dealer_cards", ()) or ()) if isinstance(session, dict) else []
        hands = list(session.get("hands", ()) or ()) if isinstance(session, dict) else []
        active_idx = int(session.get("active_hand_index", -1)) if isinstance(session, dict) else -1
        transcript = [f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is on the felt."]
        transcript.extend(_casino_ascii_card_block("Dealer", dealer_cards, hide_hole=True))
        transcript.append(_casino_blackjack_line("Dealer", dealer_cards, hide_hole=True))
        for idx, hand in enumerate(hands):
            label = f"Hand {idx + 1}"
            if idx == active_idx:
                label += " *"
            transcript.extend(_casino_ascii_card_block(label, hand.get("cards", ())))
            line = _casino_blackjack_line(label, hand.get("cards", ()))
            tags = []
            if bool(hand.get("split_origin", False)):
                tags.append("split")
            if bool(hand.get("doubled", False)):
                tags.append("double")
            state = str(hand.get("state", "")).strip().lower()
            if state in {"stood", "bust"} and idx != active_idx:
                tags.append(state)
            if tags:
                line = f"{line} [{', '.join(tags)}]"
            transcript.append(line)
        transcript.append(f"Wallet {_credit_amount_label(self._wallet_credits())}.")
        topics = []
        action_ids = _casino_twenty_one_action_ids(session, self._wallet_credits())
        label_by_action = {
            "twenty_one:hit": "Hit",
            "twenty_one:stand": "Stand",
            "twenty_one:double": f"Double Down (+{_credit_amount_label(int(session.get('wager', 0)))})",
            "twenty_one:split": f"Split Pair (+{_credit_amount_label(int(session.get('wager', 0)))})",
        }
        for action_id in action_ids:
            topics.append({"id": action_id, "label": label_by_action.get(action_id, action_id)})
        self._open_casino_modal(
            prop,
            "twenty_one",
            subtitle="Play the hand",
            transcript=transcript,
            topics=topics,
            hint="Hit, stand, double, or split when the table allows it. Esc forfeits the full posted stake.",
            mode="casino:twenty_one:hand",
            session=session,
        )

    def _open_holdem_table(self, prop, session):
        wager = int(session.get("wager", 0))
        transcript = [
            f"Ante {_credit_amount_label(wager)} is posted.",
        ]
        transcript.extend(_casino_ascii_card_block("You", session.get("player_cards", ())))
        transcript.extend(_casino_ascii_card_block("Flop", session.get("flop", ())))
        transcript.extend(_casino_ascii_card_block("Dealer", ("??", "??")))
        transcript.extend([
            f"Your hand: {_casino_cards_text(session.get('player_cards', ())) }".rstrip(),
            f"Flop: {_casino_cards_text(session.get('flop', ())) }".rstrip(),
            "Dealer: ?? ??",
            f"Call adds {_credit_amount_label(wager)} more; fold surrenders the ante.",
            "Dealer qualifies with pair of 4s or better. Straight or better pays an ante bonus.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ])
        topics = [
            {"id": "casino_holdem:call", "label": f"Call {_credit_amount_label(wager)}"},
            {"id": "casino_holdem:fold", "label": "Fold"},
        ]
        self._open_casino_modal(
            prop,
            "casino_holdem",
            subtitle="Read the flop",
            transcript=transcript,
            topics=topics,
            hint="Call or fold. Esc walks away and forfeits the ante.",
            mode="casino:holdem:hand",
            session=session,
        )

    def _open_holdem_cash_table(self, prop, *, table=None, notice="", selected_id=""):
        table = table if isinstance(table, dict) else holdem_cash_table_for_property(self.sim, prop, ensure=True)
        if not isinstance(table, dict):
            self._present_service_result(
                "Texas Hold'em Cash",
                [
                    "This floor cannot fit the live table yet.",
                    "The house needs a clear seven-by-five gaming-floor footprint for the felt and all eight chairs.",
                ],
                property_id=prop.get("id") if isinstance(prop, dict) else None,
            )
            return
        snapshot = holdem_cash_public_snapshot(self.sim, table, self.player_eid)
        if not isinstance(snapshot, dict):
            return
        seats = list(snapshot.get("seats", ()) or ())
        hero_index = snapshot.get("hero_seat")
        hero = next((seat for seat in seats if seat.get("index") == hero_index), None)
        acting = next((seat for seat in seats if seat.get("acting")), None)
        body_lines = []
        if str(notice or "").strip():
            body_lines.append(str(notice).strip())
        body_lines.append(str(snapshot.get("last_hand_summary", "The table is live.") or "The table is live."))
        board = " ".join(str(card) for card in list(snapshot.get("board", ()) or ())) or "--"
        body_lines.append(f"Board {board} | Pot {_credit_amount_label(snapshot.get('pot', 0))}.")
        if isinstance(hero, dict):
            cards = " ".join(str(card) for card in list(hero.get("cards", ()) or ())) or "--"
            body_lines.append(f"Your seat {int(hero.get('index', 0)) + 1}: {cards} | stack {_credit_amount_label(hero.get('stack', 0))}.")
        else:
            body_lines.append("Walk up to an open gold chair and interact to take that exact seat.")
        if isinstance(acting, dict):
            body_lines.append(f"Action: {acting.get('name', 'Player')} at seat {int(acting.get('index', 0)) + 1}.")

        rows = []
        legal = list(snapshot.get("legal_actions", ()) or ())
        action_labels = {
            "fold": "Fold",
            "check": "Check",
            "call": f"Call {_credit_amount_label(max(0, int(snapshot.get('current_bet', 0) or 0) - int((hero or {}).get('street_bet', 0) or 0)))}",
            "raise_small": "Raise · two big blinds",
            "raise_pot": "Raise · pot",
            "all_in": "All in",
        }
        for action in legal:
            rows.append({"id": f"cash:{action}", "label": action_labels.get(action, action.replace("_", " ").title())})
        if isinstance(hero, dict):
            if not legal:
                rows.append({"id": "cash:leave_after", "label": "Stand after this hand"})
            rows.append({"id": "cash:leave_now", "label": "Stand now"})
        else:
            player_pos = self._position_for(self.player_eid)
            nearby = []
            if player_pos is not None:
                for seat in list(table.get("seats", ()) or ()):
                    if seat.get("actor_eid") is not None or seat.get("reserved_eid") is not None:
                        continue
                    distance = abs(int(seat.get("x", 0)) - int(player_pos.x)) + abs(int(seat.get("y", 0)) - int(player_pos.y))
                    if int(seat.get("z", 0)) == int(player_pos.z) and distance <= 2:
                        nearby.append((distance, int(seat.get("index", 0))))
            for _distance, seat_index in sorted(nearby):
                rows.append({
                    "id": f"cash:join:{seat_index}",
                    "label": f"Take seat {seat_index + 1} · {_credit_amount_label(snapshot.get('buy_in', 0))} buy-in",
                })

        rail_lines = [
            "Cash table",
            f"Blinds {snapshot.get('small_blind', 0)}/{snapshot.get('big_blind', 0)}",
            f"Hand {snapshot.get('hand_number', 0)}",
            str(snapshot.get("phase", "waiting")).title(),
            "",
            "Seats",
        ]
        for seat in seats:
            marker = "D" if seat.get("button") else (">" if seat.get("acting") else " ")
            if seat.get("actor_eid") is None:
                rail_lines.append(f"{marker}{int(seat.get('index', 0)) + 1} open")
                continue
            status = "fold" if seat.get("folded") else ("all-in" if seat.get("all_in") else str(seat.get("last_action", "") or "in"))
            rail_lines.append(f"{marker}{int(seat.get('index', 0)) + 1} {seat.get('name', 'Player')} {seat.get('stack', 0)} {status}".rstrip())
        state = self._casino_ui_state()
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style="floor",
            title=f"Texas Hold'em Cash: {self._casino_prop_name(prop)}",
            subtitle="Live table · the world keeps moving",
            body_lines=body_lines,
            rail_lines=rail_lines,
            rows=rows,
            hint="Choose your action. Esc stands and folds if a hand is live.",
            close_pending=False,
            floor_page=state.get("floor_page", "games"),
            service=HOLDEM_CASH_SERVICE_ID,
            session=snapshot,
            art=snapshot,
            return_to="floor",
            return_option_id=HOLDEM_CASH_SERVICE_ID,
            selected_id=selected_id,
            pause_time=False,
        )

    def on_holdem_cash_view_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        table = getattr(self.sim, "holdem_cash_tables", {}).get(str(event.data.get("table_id", "")))
        if isinstance(prop, dict) and isinstance(table, dict):
            self._open_holdem_cash_table(prop, table=table)

    def _open_video_poker_table(self, prop, session):
        session = _casino_video_poker_normalize_session(session)
        cards = list(session.get("cards", ()) or ()) if isinstance(session, dict) else []
        holds = list(session.get("holds", ()) or ()) if isinstance(session, dict) else []
        held_slots = [str(idx + 1) for idx, held in enumerate(holds) if held]
        transcript = [f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted."]
        transcript.extend(_casino_ascii_card_block("Hand", cards))
        for idx, card in enumerate(cards):
            marker = " [HELD]" if idx < len(holds) and holds[idx] else ""
            transcript.append(f"{idx + 1}. {_casino_cards_text([card])}{marker}")
        transcript.append(f"Held: {', '.join(held_slots) if held_slots else 'none'}.")
        transcript.append("Draw replaces every card not marked held.")
        transcript.append(f"Wallet {_credit_amount_label(self._wallet_credits())}.")
        topics = []
        for idx, card in enumerate(cards):
            held = idx < len(holds) and holds[idx]
            topics.append({
                "id": f"video_poker:toggle:{idx}",
                "label": f"{'Release' if held else 'Hold'} {idx + 1} ({_casino_cards_text([card])})",
            })
        topics.append({
            "id": "video_poker:draw",
            "label": "Stand Pat" if holds and all(holds) else "Draw",
        })
        self._open_casino_modal(
            prop,
            "video_poker",
            subtitle="Choose your holds",
            transcript=transcript,
            topics=topics,
            hint="Toggle any cards you want to hold, then draw once. Esc forfeits the posted stake.",
            mode="casino:video_poker:hand",
            session=session,
        )

    def _open_keno_table(self, prop, session, *, notice=""):
        session = _casino_keno_normalize_session(session)
        picks = list(session.get("picks", ()) or ()) if isinstance(session, dict) else []
        pick_set = set(picks)
        cursor = max(1, min(CASINO_KENO_NUMBER_COUNT, int(session.get("cursor", 1) or 1))) if isinstance(session, dict) else 1
        body_lines = []
        notice = str(notice or "").strip()
        if notice:
            body_lines.append(notice)
        context = session.get("table_context") if isinstance(session, dict) and isinstance(session.get("table_context"), dict) else {}
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            body_lines.append(table_read)
        body_lines.extend([
            f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted.",
            "Board: cursor () | ticket []",
        ])
        for row_start in range(1, CASINO_KENO_NUMBER_COUNT + 1, 5):
            cells = []
            for number in range(row_start, min(row_start + 5, CASINO_KENO_NUMBER_COUNT + 1)):
                if number == cursor:
                    cell = f"({number:02d})"
                elif number in pick_set:
                    cell = f"[{number:02d}]"
                else:
                    cell = f" {number:02d} "
                cells.append(cell)
            body_lines.append(" ".join(cells))
        body_lines.extend([
            f"Mark up to {CASINO_KENO_MAX_PICKS} spots from 01-{CASINO_KENO_NUMBER_COUNT:02d}.",
            (
                f"Selected ({len(picks)}/{CASINO_KENO_MAX_PICKS}): "
                f"{' '.join(f'{number:02d}' for number in picks)}."
                if picks
                else f"Selected (0/{CASINO_KENO_MAX_PICKS}): none."
            ),
            f"The house will draw {CASINO_KENO_DRAW_COUNT} balls.",
        ])
        rail_lines = self._casino_common_rail_lines(prop, service="keno", session=session)
        rail_lines.extend([
            "",
            "Ticket",
            f"{len(picks)}/{CASINO_KENO_MAX_PICKS} picks",
        ])
        if picks:
            rail_lines.extend([
                " ".join(f"{number:02d}" for number in picks[:8]),
            ])
        pay_key = max(0, min(CASINO_KENO_MAX_PICKS, len(picks)))
        if pay_key > 0:
            pay_row = CASINO_KENO_PAYOUT_MULTIPLIERS.get(pay_key, {})
            rail_lines.extend([
                "",
                f"Pay row {pay_key}",
            ])
            for hit_count, mult in sorted(pay_row.items()):
                rail_lines.append(f"{hit_count} hit -> {_casino_keno_multiplier_text(mult)}")
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=str(self._casino_ui_state().get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop),
            title=f"Keno: {self._casino_prop_name(prop)}",
            subtitle="Mark your ticket",
            body_lines=body_lines,
            rail_lines=rail_lines,
            rows=[],
            hint="Move the cursor, Space marks a spot, Backspace clears it, Enter draws, Esc forfeits.",
            close_pending=False,
            floor_page=self._casino_ui_state().get("floor_page", "games"),
            service="keno",
            session=session,
            return_to=str(self._casino_ui_state().get("return_to", "floor")).strip().lower(),
            return_option_id="keno",
        )

    def _open_roulette_table(self, prop, session, *, notice=""):
        session = _casino_roulette_normalize_session(session)
        cursor_key = str(session.get("cursor_key", "straight:0") or "straight:0").strip().lower() if isinstance(session, dict) else "straight:0"
        bets = dict(session.get("bets", {}) or {}) if isinstance(session, dict) else {}
        body_lines = []
        notice = str(notice or "").strip()
        if notice:
            body_lines.append(notice)
        context = session.get("table_context") if isinstance(session, dict) and isinstance(session.get("table_context"), dict) else {}
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            body_lines.append(table_read)
        body_lines.extend([
            f"Posted {_credit_amount_label(session.get('stake', session.get('wager', 0)))} across the slip.",
            "Space adds one chip to the focused market. Backspace pulls one chip back. Enter spins once.",
            "Straight numbers pay x36. Colors, parity, and ranges pay x2. Dozens and columns pay x3.",
            "",
            "Straight numbers",
        ])
        focus_line = -1
        straight_keys = [f"straight:{number}" for number in range(0, CASINO_ROULETTE_NUMBER_MAX + 1)]
        for row_start in range(0, len(straight_keys), 5):
            line_index = len(body_lines)
            cells = []
            group = straight_keys[row_start: row_start + 5]
            for key in group:
                market = _casino_roulette_market_from_key(key) or {"value": 0}
                label = f"{int(market.get('value', 0)):02d}"
                units = int(bets.get(key, 0) or 0)
                if units > 0:
                    label = f"{label}x{units}"
                label = label.center(8)
                if key == cursor_key:
                    cells.append(f"[{label}]")
                else:
                    cells.append(f" {label} ")
            body_lines.append(" ".join(cells))
            if cursor_key in group:
                focus_line = line_index
        body_lines.extend([
            "",
            "Outside board",
        ])
        outside_groups = [
            ("color:red", "color:black"),
            ("parity:odd", "parity:even"),
            ("range:low", "range:high"),
            ("dozen:1", "dozen:2", "dozen:3"),
            ("column:1", "column:2", "column:3"),
        ]
        for group in outside_groups:
            line_index = len(body_lines)
            cells = []
            for key in group:
                market = _casino_roulette_market_from_key(key) or {"label": key}
                label = str(market.get("label", key)).replace(" (", " ").replace(")", "")
                units = int(bets.get(key, 0) or 0)
                if units > 0:
                    label = f"{label} x{units}"
                label = label[:12].center(12)
                if key == cursor_key:
                    cells.append(f"[{label}]")
                else:
                    cells.append(f" {label} ")
            body_lines.append(" ".join(cells))
            if cursor_key in group:
                focus_line = line_index
        rail_lines = self._casino_common_rail_lines(prop, service="roulette", session=session)
        rail_lines.extend([
            "",
            "Slip",
            f"{sum(int(units) for units in bets.values())} chip(s)",
        ])
        for key, units in list(sorted(bets.items()))[:8]:
            market = _casino_roulette_market_from_key(key)
            if not market:
                continue
            rail_lines.append(f"{market['label']} x{int(units)}")
        focus_market = _casino_roulette_market_from_key(cursor_key)
        if focus_market:
            rail_lines.extend([
                "",
                "Focus",
                str(focus_market.get("label", cursor_key)),
            ])
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=str(self._casino_ui_state().get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop),
            title=f"Roulette: {self._casino_prop_name(prop)}",
            subtitle="Build a slip",
            body_lines=body_lines,
            body_focus_line=focus_line,
            rail_lines=rail_lines,
            rows=[],
            hint="Move focus, Space adds chips, Backspace removes chips, Enter spins, Esc forfeits posted chips.",
            close_pending=False,
            floor_page=self._casino_ui_state().get("floor_page", "games"),
            service="roulette",
            session=session,
            return_to=str(self._casino_ui_state().get("return_to", "floor")).strip().lower(),
            return_option_id="roulette",
        )

    def _open_craps_table(self, prop, session, *, notice=""):
        session = _casino_craps_normalize_session(session)
        if not session:
            state = self._casino_ui_state()
            host_style = str(state.get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop)
            if host_style == "floor":
                self._open_casino_floor(prop, page=state.get("floor_page", "games"), selected_id="game:craps")
            else:
                self._return_from_casino_host(prop)
            return
        cursor_key = str(session.get("cursor_key", "pass") or "pass").strip().lower() if isinstance(session, dict) else "pass"
        bets = dict(session.get("bets", {}) or {}) if isinstance(session, dict) else {}
        phase = str(session.get("phase", "come_out") or "come_out").strip().lower() if isinstance(session, dict) else "come_out"
        point_number = int(session.get("point_number", 0) or 0) if isinstance(session, dict) else 0
        roll_history = list(session.get("roll_history", ()) or ()) if isinstance(session, dict) else []
        body_lines = []
        notice = str(notice or "").strip()
        if notice:
            body_lines.append(notice)
        context = session.get("table_context") if isinstance(session, dict) and isinstance(session.get("table_context"), dict) else {}
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            body_lines.append(table_read)
        body_lines.append(
            f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} | "
            f"{'Point' if phase == 'point' else 'Come-out'} | "
            f"Point {point_number if point_number > 0 else '--'}"
        )
        body_lines.append("Markets")

        def _market_cell(key, width=12):
            market = _casino_craps_market_from_key(key) or {"label": key}
            label = str(market.get("label", key))
            units = int(bets.get(key, 0) or 0)
            if units > 0:
                label = f"{label} x{units}"
            label = label[:width].center(width)
            if key == cursor_key:
                return f"[{label}]"
            return f" {label} "

        focus_line = -1
        market_groups = (
            ("pass", "dont_pass", "field"),
            ("pass_odds", "dont_pass_odds"),
            ("place:4", "place:5", "place:6"),
            ("place:8", "place:9", "place:10"),
            ("hardway:4", "hardway:6", "hardway:8", "hardway:10"),
            ("prop:2", "prop:3", "prop:11"),
            ("prop:12", "prop:any_craps", "prop:any_seven"),
        )
        for group in market_groups:
            line_index = len(body_lines)
            body_lines.append(" ".join(_market_cell(key) for key in group))
            if cursor_key in group:
                focus_line = line_index

        rail_lines = self._casino_common_rail_lines(prop, service="craps", session=session)
        rail_lines.extend([
            "",
            "Live slip",
            f"{sum(int(units) for units in bets.values())} chip(s)",
        ])
        for key, units in list(sorted(bets.items()))[:8]:
            market = _casino_craps_market_from_key(key)
            if not market:
                continue
            rail_lines.append(f"{market['label']} x{int(units)}")
        if roll_history:
            rail_lines.extend([
                "",
                "Recent",
            ])
            for roll in roll_history[-5:]:
                rail_lines.append(f"{int(roll.get('die_one', 0))}+{int(roll.get('die_two', 0))}={int(roll.get('total', 0))}")
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=str(self._casino_ui_state().get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop),
            title=f"Craps: {self._casino_prop_name(prop)}",
            subtitle="Shooter live",
            body_lines=body_lines,
            body_focus_line=focus_line,
            rail_lines=rail_lines,
            rows=[],
            hint="Move focus, Space adds chips, Backspace removes chips, Enter rolls, Esc forfeits posted chips.",
            close_pending=False,
            floor_page=self._casino_ui_state().get("floor_page", "games"),
            service="craps",
            session=session,
            return_to=str(self._casino_ui_state().get("return_to", "floor")).strip().lower(),
            return_option_id="craps",
        )

    def _open_three_bright_table(self, prop, session, *, notice=""):
        session = _casino_three_bright_normalize_session(session)
        if not session:
            self._present_service_result("Three Bright", ["That color dice table lost the slip.", "Start a fresh round."], property_id=prop.get("id") if isinstance(prop, dict) else None)
            return
        cursor_key = str(session.get("cursor_key", "single:red") or "single:red").strip().lower()
        bets = dict(session.get("bets", {}) or {})
        context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
        colors = tuple(session.get("color_words", ()) or ())
        body_lines = []
        notice = str(notice or "").strip()
        if notice:
            body_lines.append(notice)
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            body_lines.append(table_read)
        body_lines.extend([
            f"Posted {_credit_amount_label(session.get('stake', 0))} across the color slip.",
            "Space adds one chip to the focused color market. Backspace pulls one chip back. Enter rolls.",
            "Singles return one chip per matching die. Doubles need two or more. Triples need all three.",
            "",
            "Color markets",
        ])

        def _market_cell(key, width=14):
            market = _casino_three_bright_market_from_key(key, context) or {"label": key}
            label = str(market.get("label", key)).replace("Single ", "S ").replace("Double ", "D ").replace("Triple ", "T ")
            units = int(bets.get(key, 0) or 0)
            if units > 0:
                label = f"{label} x{units}"
            label = label[:width].center(width)
            if key == cursor_key:
                return f"[{label}]"
            return f" {label} "

        focus_line = -1
        for color in colors:
            group = (f"single:{color}", f"double:{color}", f"triple:{color}")
            line_index = len(body_lines)
            body_lines.append(" ".join(_market_cell(key) for key in group))
            if cursor_key in group:
                focus_line = line_index
        special_group = ("special:rainbow", "special:all_bright", "special:all_dark")
        line_index = len(body_lines)
        body_lines.append(" ".join(_market_cell(key) for key in special_group))
        if cursor_key in special_group:
            focus_line = line_index

        rail_lines = self._casino_common_rail_lines(prop, service="three_bright", session=session)
        rail_lines.extend([
            "",
            "Slip",
            f"{sum(int(units) for units in bets.values())} chip(s)",
        ])
        for key, units in list(sorted(bets.items()))[:8]:
            market = _casino_three_bright_market_from_key(key, context)
            if not market:
                continue
            rail_lines.append(f"{market['label']} x{int(units)}")
        focus_market = _casino_three_bright_market_from_key(cursor_key, context)
        if focus_market:
            rail_lines.extend([
                "",
                "Focus",
                str(focus_market.get("label", cursor_key)),
            ])
        rail_lines.extend([
            "",
            "Dice",
            " ".join(str(color).replace("_", " ") for color in colors[:6]),
        ])
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=str(self._casino_ui_state().get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop),
            title=f"Three Bright: {self._casino_prop_name(prop)}",
            subtitle="Build a color slip",
            body_lines=body_lines,
            body_focus_line=focus_line,
            rail_lines=rail_lines,
            rows=[],
            hint="Move focus, Space adds chips, Backspace removes chips, Enter rolls, Esc forfeits posted chips.",
            close_pending=False,
            floor_page=self._casino_ui_state().get("floor_page", "games"),
            service="three_bright",
            session=session,
            art=session,
            return_to=str(self._casino_ui_state().get("return_to", "floor")).strip().lower(),
            return_option_id="three_bright",
        )

    def _open_three_bones_table(self, prop, session, *, notice=""):
        session = _casino_three_bones_normalize_session(session)
        if not session:
            self._present_service_result("Three Bones", ["That dice cup lost the slip.", "Start a fresh round."], property_id=prop.get("id") if isinstance(prop, dict) else None)
            return
        cursor_key = str(session.get("cursor_key", "small") or "small").strip().lower()
        bets = dict(session.get("bets", {}) or {})
        context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
        body_lines = []
        notice = str(notice or "").strip()
        if notice:
            body_lines.append(notice)
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            body_lines.append(table_read)
        body_lines.extend([
            f"Posted {_credit_amount_label(session.get('stake', 0))} across the bones slip.",
            "Space adds one chip to the focused market. Backspace pulls one chip back. Enter lifts the cup.",
            "Small and big lose on triples. Exact totals and triples are rare, loud hits.",
            "",
            "Main board",
        ])

        def _market_cell(key, width=13):
            market = _casino_three_bones_market_from_key(key, context) or {"label": key}
            label = str(market.get("label", key)).replace("Total ", "T ").replace("Double ", "D ").replace("Triple ", "Tri ")
            units = int(bets.get(key, 0) or 0)
            if units > 0:
                label = f"{label} x{units}"
            label = label[:width].center(width)
            if key == cursor_key:
                return f"[{label}]"
            return f" {label} "

        focus_line = -1
        market_groups = (
            ("small", "big", "any_triple"),
            ("exact:4", "exact:5", "exact:6", "exact:7"),
            ("exact:8", "exact:9", "exact:10", "exact:11"),
            ("exact:12", "exact:13", "exact:14", "exact:15"),
            ("exact:16", "exact:17"),
            ("double:1", "double:2", "double:3"),
            ("double:4", "double:5", "double:6"),
            ("triple:1", "triple:2", "triple:3"),
            ("triple:4", "triple:5", "triple:6"),
        )
        for group in market_groups:
            line_index = len(body_lines)
            body_lines.append(" ".join(_market_cell(key) for key in group))
            if cursor_key in group:
                focus_line = line_index

        rail_lines = self._casino_common_rail_lines(prop, service="three_bones", session=session)
        rail_lines.extend([
            "",
            "Slip",
            f"{sum(int(units) for units in bets.values())} chip(s)",
        ])
        for key, units in list(sorted(bets.items()))[:8]:
            market = _casino_three_bones_market_from_key(key, context)
            if not market:
                continue
            rail_lines.append(f"{market['label']} x{int(units)}")
        focus_market = _casino_three_bones_market_from_key(cursor_key, context)
        if focus_market:
            rail_lines.extend([
                "",
                "Focus",
                str(focus_market.get("label", cursor_key)),
            ])
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=str(self._casino_ui_state().get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop),
            title=f"Three Bones: {self._casino_prop_name(prop)}",
            subtitle="Build a dice slip",
            body_lines=body_lines,
            body_focus_line=focus_line,
            rail_lines=rail_lines,
            rows=[],
            hint="Move focus, Space adds chips, Backspace removes chips, Enter rolls, Esc forfeits posted chips.",
            close_pending=False,
            floor_page=self._casino_ui_state().get("floor_page", "games"),
            service="three_bones",
            session=session,
            art=session,
            return_to=str(self._casino_ui_state().get("return_to", "floor")).strip().lower(),
            return_option_id="three_bones",
        )

    def _open_bloom_cards_table(self, prop, session, *, notice=""):
        session = _casino_bloom_cards_normalize_session(session)
        if not session:
            self._present_service_result("Bloom Cards", ["That flower-card garden lost the table.", "Start a fresh round."], property_id=prop.get("id") if isinstance(prop, dict) else None)
            return
        context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
        player_cards = list(session.get("player_cards", ()) or ())
        house_cards = list(session.get("house_cards", ()) or ())
        growth_steps = int(session.get("growth_steps", 0) or 0)
        score = _casino_bloom_cards_score(player_cards, growth_steps)
        multiplier = float(score.get("multiplier", 1.0) or 1.0)
        body_lines = []
        notice = str(notice or "").strip()
        if notice:
            body_lines.append(notice)
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            body_lines.append(table_read)
        body_lines.extend([
            f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted.",
            "Garden: " + ", ".join(str(card.get("name", "bloom")) for card in player_cards[:8]),
            "House weather: two closed bloom cards.",
            "Bloom read: " + ", ".join(score.get("reasons", ()) or ("ordinary garden",)),
            f"Cash-out now: x{multiplier:.2f}.",
        ])
        if growth_steps <= 0:
            body_lines.append("The first cash-out is a safe push; profit means letting the garden grow at least once.")
        if growth_steps >= 3:
            body_lines.append("The garden is fully grown. Cash out before the table sweeps it.")
        else:
            body_lines.append(f"Growth {growth_steps}/3. Letting it grow reveals one more plant and can wither the whole stake.")
        topics = []
        if growth_steps < 3:
            topics.append({"id": "bloom_cards:grow", "label": "Let it grow"})
        topics.append({"id": "bloom_cards:cashout", "label": f"Cash out x{multiplier:.2f}"})
        self._open_casino_modal(
            prop,
            "bloom_cards",
            subtitle="Flower-card garden",
            transcript=body_lines,
            topics=topics,
            hint="Grow or cash out. Esc walks away and forfeits the posted stake.",
            mode="casino:bloom_cards:live",
            session=session,
            art=session,
        )

    def _open_baccarat_table(self, prop, session, *, notice=""):
        session = _casino_baccarat_normalize_session(session)
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        transcript.extend([
            f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted.",
            *_casino_ascii_card_block("Player", ("??", "??")),
            *_casino_ascii_card_block("Banker", ("??", "??")),
            "Choose player, banker, or tie before the dealer opens the shoe.",
            "Player pays even money. Banker pays 0.95 to 1 after commission. Tie pays 8 to 1.",
            "Two cards each are dealt and the third-card rules run automatically.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ])
        topics = [
            {"id": "baccarat:player", "label": "Player (x2 return)"},
            {"id": "baccarat:banker", "label": "Banker (x1.95 return)"},
            {"id": "baccarat:tie", "label": "Tie (x9 return)"},
        ]
        self._open_casino_modal(
            prop,
            "baccarat",
            subtitle="Back a side",
            transcript=transcript,
            topics=topics,
            hint="Pick player, banker, or tie. Esc forfeits the posted stake.",
            mode="casino:baccarat:layout",
            session=session,
        )

    def _open_three_card_poker_table(self, prop, session, *, notice=""):
        session = _casino_three_card_poker_normalize_session(session)
        wager = int(session.get("wager", 0))
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        transcript.extend([
            f"Ante {_credit_amount_label(wager)} is posted.",
            *_casino_ascii_card_block("You", session.get("player_cards", ())),
            *_casino_ascii_card_block("Dealer", ("??", "??", "??")),
            f"Your hand: {_casino_cards_text(session.get('player_cards', ())) }".rstrip(),
            "Dealer: ?? ?? ??",
            f"Play adds {_credit_amount_label(wager)} more; fold surrenders the ante.",
            "Dealer qualifies with queen-high or better. Straight or better pays an ante bonus.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ])
        topics = [
            {"id": "three_card_poker:play", "label": f"Play {_credit_amount_label(wager)}"},
            {"id": "three_card_poker:fold", "label": "Fold"},
        ]
        self._open_casino_modal(
            prop,
            "three_card_poker",
            subtitle="Read the hand",
            transcript=transcript,
            topics=topics,
            hint="Play or fold. Esc walks away and forfeits the ante.",
            mode="casino:three_card_poker:hand",
            session=session,
            art=session,
        )

    def _crash_auto_label(self, session):
        auto = float(session.get("auto_cashout_multiplier", 0.0) or 0.0) if isinstance(session, dict) else 0.0
        return "OFF" if auto <= 0.0 else f"x{auto:.2f}"

    def _open_crash_setup(self, prop, session, *, notice="", selected_id=""):
        session = _casino_crash_normalize_session(session)
        if not session:
            self._present_service_result("Crash", ["That machine lost the live graph.", "Start a fresh round."], property_id=prop.get("id") if isinstance(prop, dict) else None)
            return
        wager = int(session.get("wager", 0) or 0)
        step = float(session.get("auto_step", 0.10) or 0.10)
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            transcript.append(table_read)
        transcript.extend([
            f"Stake {_credit_amount_label(wager)} is ready, but not posted yet.",
            f"Auto cash out: {self._crash_auto_label(session)}.",
            f"Adjustment step: x{step:.2f}.",
            f"Auto range: x1.01 to x{CASINO_CRASH_MAX_MULTIPLIER:.2f}.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ])
        rows = [
            {"id": "crash:auto", "label": f"Auto cash out {self._crash_auto_label(session)}"},
            {"id": "crash:step", "label": f"Adjustment step x{step:.2f}"},
            {"id": "crash:launch", "label": f"Launch {_credit_amount_label(wager)}"},
        ]
        state = self._casino_ui_state()
        host_style = str(state.get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop)
        return_to = str(state.get("return_to", "floor" if host_style == "floor" else "service_menu")).strip().lower()
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=host_style,
            title=f"Crash: {self._casino_prop_name(prop)}",
            subtitle="Set the graph",
            body_lines=transcript,
            rail_lines=self._casino_common_rail_lines(prop, service="crash", session=session),
            rows=rows,
            hint="Left/right adjusts setup. Space toggles auto or launches. Esc backs out.",
            close_pending=False,
            floor_page=state.get("floor_page", "games"),
            service="crash",
            session=session,
            art=session,
            return_to=return_to,
            return_option_id="crash",
            selected_id=selected_id or "crash:auto",
            pause_time=True,
        )

    def _open_crash_table(self, prop, session, *, notice="", selected_id=""):
        session = _casino_crash_normalize_session(session)
        if not session:
            self._present_service_result("Crash", ["That machine lost the live graph.", "Start a fresh round."], property_id=prop.get("id") if isinstance(prop, dict) else None)
            return
        wager = int(session.get("wager", 0) or 0)
        current = float(session.get("current_multiplier", 1.0) or 1.0)
        next_multiplier = float(_casino_crash_multiplier_for_step(int(session.get("step", 0) or 0) + 1))
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
        table_read = str(context.get("table_read", "")).strip()
        if table_read:
            transcript.append(table_read)
        transcript.extend([
            f"Stake {_credit_amount_label(wager)} is posted.",
            f"Current multiplier: x{current:.2f}.",
            f"Next tick pushes toward x{next_multiplier:.2f}.",
            f"Auto cash out: {self._crash_auto_label(session)}.",
            "Cash out now to take the visible multiplier. The graph keeps running while you watch.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ])
        rows = [
            {"id": "crash:cashout", "label": f"Cash out x{current:.2f}"},
        ]
        state = self._casino_ui_state()
        host_style = str(state.get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop)
        return_to = str(state.get("return_to", "floor" if host_style == "floor" else "service_menu")).strip().lower()
        self._open_casino_ui(
            mode="live",
            prop=prop,
            host_style=host_style,
            title=f"Crash: {self._casino_prop_name(prop)}",
            subtitle="Live graph",
            body_lines=transcript,
            rail_lines=self._casino_common_rail_lines(prop, service="crash", session=session),
            rows=rows,
            hint="Space or Enter cashes out. Esc walks away and forfeits the posted stake.",
            close_pending=False,
            floor_page=state.get("floor_page", "games"),
            service="crash",
            session=session,
            art=session,
            return_to=return_to,
            return_option_id="crash",
            selected_id=selected_id or "crash:cashout",
            pause_time=False,
        )

    def _start_casino_round(self, prop, service, wager):
        wager = int(wager)
        prop_name = self._casino_prop_name(prop)
        profile = _casino_game_profile(service)
        table_context = _casino_table_context(self.sim, prop, game=service)
        if not bool(table_context.get("allowed", True)):
            self._emit_casino_blocked(prop, service, str(table_context.get("access_reason", "blocked") or "blocked"), wager=wager)
            return
        valid_wagers = {int(amount) for amount in tuple(table_context.get("stake_ladder", ()) or ())} if profile else set()
        if wager <= 0 or (valid_wagers and wager not in valid_wagers):
            self._emit_casino_blocked(prop, service, "invalid_wager", wager=wager)
            return

        def _contextual_session(session):
            if isinstance(session, dict):
                session["table_context"] = dict(table_context)
            return session

        if service == "slots":
            credits = self._wallet_credits()
            if credits < wager:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            round_index = _site_service_roll_index(self.sim, self.player_eid, prop, service)
            seed_contract = _casino_slot_round_contract(self.sim, prop, round_index)
            round_result = _casino_slots_resolve(
                seed_contract,
                wager,
                bonus_wild_weight_scale=table_context.get("bonus_wild_weight_scale"),
            )
            self._settle_casino_round(prop, service, round_result)
            return

        if service == "plinko":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            self._open_plinko_lane_menu(prop, service, wager, table_context=table_context)
            return

        if service == "crash":
            credits = self._wallet_credits()
            if credits < wager:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _contextual_session(_casino_crash_setup(self._casino_round_seed(prop, service, wager), wager, table_context=table_context))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_crash_setup(prop, session)
            return

        if service == "video_poker":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _contextual_session(_casino_video_poker_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_video_poker_table(prop, session)
            return

        if service == "keno":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _contextual_session(_casino_keno_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_keno_table(prop, session)
            return

        if service == "roulette":
            session = _contextual_session(_casino_roulette_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_roulette_table(prop, session)
            return

        if service == "craps":
            session = _contextual_session(_casino_craps_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_craps_table(prop, session)
            return

        if service == "three_bright":
            session = _casino_three_bright_start(self._casino_round_seed(prop, service, wager), wager, table_context=table_context)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_three_bright_table(prop, session)
            return

        if service == "three_bones":
            session = _casino_three_bones_start(self._casino_round_seed(prop, service, wager), wager, table_context=table_context)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_three_bones_table(prop, session)
            return

        if service == "bloom_cards":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _casino_bloom_cards_start(self._casino_round_seed(prop, service, wager), wager, table_context=table_context)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_bloom_cards_table(prop, session)
            return

        if service == "baccarat":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _contextual_session(_casino_baccarat_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_baccarat_table(prop, session)
            return

        if service == "three_card_poker":
            needed = int(wager) * 2
            if self._wallet_credits() < needed:
                self._emit_casino_blocked(prop, service, "no_credits", cost=needed, credits=self._wallet_credits(), wager=wager)
                return
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _contextual_session(_casino_three_card_poker_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_three_card_poker_table(prop, session)
            return

        if service == "twenty_one":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _contextual_session(_casino_twenty_one_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            next_session, round_result = _casino_twenty_one_resolve(session, "start")
            if round_result:
                self._settle_casino_round(prop, service, round_result)
                return
            self._open_twenty_one_table(prop, next_session or session)
            return

        if service == "casino_holdem":
            needed = int(wager) * 2
            if self._wallet_credits() < needed:
                self._emit_casino_blocked(prop, service, "no_credits", cost=needed, credits=self._wallet_credits(), wager=wager)
                return
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _contextual_session(_casino_holdem_start(self._casino_round_seed(prop, service, wager), wager))
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_holdem_table(prop, session)
            return

        self._present_service_result("Casino", ["That game is not running on this floor right now."], property_id=prop.get("id"))

    def _handle_active_casino_option(self, prop, option_id):
        session = self._casino_session()
        if not session:
            return False
        service = str(session.get("service", "")).strip().lower()
        if not isinstance(prop, dict):
            title, lines = self._stale_service_option_lines(service or option_id)
            self._present_service_result(title, lines, property_id=prop.get("id") if isinstance(prop, dict) else None)
            return True

        if service == HOLDEM_CASH_SERVICE_ID and option_id.startswith("cash:"):
            table = holdem_cash_table_for_property(self.sim, prop, ensure=False)
            if not isinstance(table, dict):
                self._present_service_result("Texas Hold'em Cash", ["That table is no longer on this floor."], property_id=prop.get("id"))
                return True
            command = option_id.partition(":")[2]
            notice = ""
            if command.startswith("join:"):
                try:
                    seat_index = int(command.rsplit(":", 1)[-1])
                except (TypeError, ValueError):
                    seat_index = -1
                result = holdem_cash_join(self.sim, table, self.player_eid, seat_index=seat_index, actor_kind="player")
                if not result.get("ok"):
                    if result.get("reason") == "insufficient_funds":
                        notice = f"You need {_credit_amount_label(result.get('need', table.get('buy_in', 0)))} to buy in."
                    else:
                        notice = "That chair is no longer open."
            elif command == "leave_after":
                holdem_cash_leave(self.sim, table, self.player_eid, immediate=False)
                notice = "You will rack up after this hand."
            elif command == "leave_now":
                holdem_cash_leave(self.sim, table, self.player_eid, immediate=True)
                notice = "You stand now; a live hand is folded."
            else:
                result = holdem_cash_submit_action(self.sim, table, self.player_eid, command)
                if not result.get("ok"):
                    notice = "The action moved before your input reached the felt."
            self._open_holdem_cash_table(prop, table=table, notice=notice)
            return True

        if service == "plinko" and option_id.startswith("plinko:lane:"):
            try:
                lane = int(option_id.rsplit(":", 1)[-1])
            except (TypeError, ValueError):
                lane = -1
            if lane < 0:
                self._present_service_result("Plinko", ["That drop lane is not valid."], property_id=prop.get("id"))
                return True
            seed_token = str(session.get("seed_token", "")).strip() or self._casino_round_seed(prop, service, session.get("wager", 0))
            round_result = _casino_plinko_resolve(seed_token, int(session.get("wager", 0)), lane)
            round_result["stake_already_paid"] = True
            self._settle_casino_round(prop, service, round_result)
            return True

        if service == "crash" and option_id in {"crash:auto", "crash:step", "crash:launch", "crash:ride", "crash:cashout"}:
            current = _casino_crash_normalize_session(session)
            if not current:
                self._present_service_result("Crash", ["That live graph lost sync.", "Start a fresh round."], property_id=prop.get("id"))
                return True
            phase = str(current.get("phase", "live") or "live").strip().lower()
            if phase == "setup":
                if option_id == "crash:auto":
                    self._open_crash_setup(prop, _casino_crash_toggle_auto(current) or current, selected_id="crash:auto")
                    return True
                if option_id == "crash:step":
                    self._open_crash_setup(prop, _casino_crash_cycle_auto_step(current) or current, selected_id="crash:step")
                    return True
                if option_id == "crash:launch":
                    wager = int(current.get("wager", 0) or 0)
                    ok, credits = self._casino_commit_stake(wager)
                    if not ok:
                        self._open_crash_setup(prop, current, notice=f"You need {_credit_amount_label(wager)} to post that stake. Wallet {_credit_amount_label(credits)}.", selected_id="crash:launch")
                        return True
                    launched = _casino_crash_launch(current, getattr(self.sim, "tick", 0)) or current
                    self._open_crash_table(prop, launched)
                    return True
                return True
            if option_id == "crash:cashout":
                next_session, round_result = _casino_crash_cashout(current)
            else:
                action = "cashout" if option_id.endswith(":cashout") else "ride"
                next_session, round_result = _casino_crash_resolve(current, action)
            if round_result:
                self._settle_casino_round(prop, service, round_result)
                return True
            if next_session:
                self._open_crash_table(prop, next_session)
                return True
            self._present_service_result("Crash", ["That live graph lost sync.", "Start a fresh round."], property_id=prop.get("id"))
            return True

        if service == "bloom_cards" and option_id in {"bloom_cards:grow", "bloom_cards:cashout"}:
            current = _casino_bloom_cards_normalize_session(session)
            if not current:
                self._present_service_result("Bloom Cards", ["That flower-card garden lost sync.", "Start a fresh round."], property_id=prop.get("id"))
                return True
            if option_id.endswith(":cashout"):
                round_result = _casino_bloom_cards_cashout(current)
                if not round_result:
                    self._present_service_result("Bloom Cards", ["That cash-out could not be read.", "Start a fresh round."], property_id=prop.get("id"))
                    return True
                self._settle_casino_round(prop, service, round_result)
                return True
            next_session, round_result = _casino_bloom_cards_grow(current)
            if next_session or round_result:
                self._advance_casino_action_time(prop, service, round_result=round_result)
            if round_result:
                self._settle_casino_round(prop, service, round_result)
                return True
            if next_session:
                drawn = list(next_session.get("player_cards", ()) or [])[-1] if list(next_session.get("player_cards", ()) or []) else {}
                drawn_name = str(drawn.get("name", "new bloom")) if isinstance(drawn, dict) else "new bloom"
                self._open_bloom_cards_table(prop, next_session, notice=f"{drawn_name} joins the garden.")
                return True
            self._present_service_result("Bloom Cards", ["That grow choice lost sync.", "Start a fresh round."], property_id=prop.get("id"))
            return True

        if service == "video_poker" and option_id.startswith("video_poker:toggle:"):
            try:
                card_index = int(option_id.rsplit(":", 1)[-1])
            except (TypeError, ValueError):
                card_index = -1
            if card_index < 0:
                self._present_service_result("Video Poker", ["That hold selection is not valid."], property_id=prop.get("id"))
                return True
            next_session = _casino_video_poker_toggle_hold(session, card_index)
            if next_session:
                self._open_video_poker_table(prop, next_session)
            return True

        if service == "video_poker" and option_id == "video_poker:draw":
            round_result = _casino_video_poker_draw(session)
            if not round_result:
                self._present_service_result(
                    "Video Poker",
                    ["That round lost sync with the table.", "Start a fresh round."],
                    property_id=prop.get("id"),
                )
                return True
            self._settle_casino_round(prop, service, round_result)
            return True

        if service == "keno" and option_id.startswith("keno:toggle:"):
            current = _casino_keno_normalize_session(session)
            try:
                ticket_number = int(option_id.rsplit(":", 1)[-1])
            except (TypeError, ValueError):
                ticket_number = -1
            if not current or ticket_number < 1 or ticket_number > CASINO_KENO_NUMBER_COUNT:
                self._open_keno_table(prop, current or session, notice="That number is not on the board.")
                return True
            picks = list(current.get("picks", ()) or ())
            if ticket_number not in picks and len(picks) >= CASINO_KENO_MAX_PICKS:
                self._open_keno_table(
                    prop,
                    current,
                    notice=f"You can only mark {CASINO_KENO_MAX_PICKS} spots on one ticket.",
                )
                return True
            next_session = _casino_keno_toggle_pick(current, ticket_number)
            if next_session:
                self._open_keno_table(prop, next_session)
            return True

        if service == "keno" and option_id == "keno:clear":
            current = _casino_keno_normalize_session(session)
            if current:
                current["picks"] = []
                self._open_keno_table(prop, current)
            return True

        if service == "keno" and option_id == "keno:draw":
            current = _casino_keno_normalize_session(session)
            if not current or not list(current.get("picks", ()) or ()):
                self._open_keno_table(prop, current or session, notice="Mark at least one number before the draw.")
                return True
            round_result = _casino_keno_draw(current)
            if not round_result:
                self._open_keno_table(prop, current, notice="That ticket lost sync with the board. Try that draw again.")
                return True
            self._settle_casino_round(prop, service, round_result)
            return True

        if service == "roulette":
            current = _casino_roulette_normalize_session(session)
            self._open_roulette_table(prop, current or session, notice="Use the board controls to add chips, remove chips, and spin.")
            return True

        if service == "craps":
            current = _casino_craps_normalize_session(session)
            if not current:
                self._present_service_result("Craps", ["That table lost the round state.", "Start a fresh round."], property_id=prop.get("id"))
                return True
            self._open_craps_table(prop, current, notice="Use the board controls to stage chips and roll the shooter.")
            return True

        if service == "baccarat" and option_id in {"baccarat:player", "baccarat:banker", "baccarat:tie"}:
            current = _casino_baccarat_normalize_session(session)
            if not current:
                self._present_service_result("Baccarat", ["That shoe lost the round state.", "Start a fresh round."], property_id=prop.get("id"))
                return True
            bet_side = option_id.rsplit(":", 1)[-1]
            round_result = _casino_baccarat_resolve(current, bet_side)
            if not round_result:
                self._open_baccarat_table(prop, current, notice="That hand lost sync with the shoe. Try another hand.")
                return True
            self._settle_casino_round(prop, service, round_result)
            return True

        if service == "three_card_poker" and option_id in {"three_card_poker:play", "three_card_poker:fold"}:
            current = _casino_three_card_poker_normalize_session(session)
            if not current:
                self._present_service_result("Three-Card Poker", ["That table lost the round state.", "Start a fresh round."], property_id=prop.get("id"))
                return True
            action = option_id.rsplit(":", 1)[-1]
            if action == "play":
                wager = int(current.get("wager", 0))
                ok, credits = self._casino_commit_stake(wager)
                if not ok:
                    self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                    return True
                current["stake"] = int(current.get("stake", wager)) + wager
            round_result = _casino_three_card_poker_resolve(current, action)
            if not round_result:
                self._open_three_card_poker_table(prop, current, notice="That hand lost sync with the table. Try another deal.")
                return True
            self._settle_casino_round(prop, service, round_result)
            return True

        if service == "twenty_one" and option_id in {"twenty_one:hit", "twenty_one:stand"}:
            action = "hit" if option_id.endswith(":hit") else "stand"
            next_session, round_result = _casino_twenty_one_resolve(session, action)
            if next_session or round_result:
                self._advance_casino_action_time(prop, service, round_result=round_result)
            if round_result:
                self._settle_casino_round(prop, service, round_result)
            elif next_session:
                self._open_twenty_one_table(prop, next_session)
            return True

        if service == "twenty_one" and option_id in {"twenty_one:double", "twenty_one:split"}:
            wager = int(session.get("wager", 0))
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return True
            action = "double" if option_id.endswith(":double") else "split"
            next_session, round_result = _casino_twenty_one_resolve(session, action)
            if next_session or round_result:
                self._advance_casino_action_time(prop, service, round_result=round_result)
            if round_result:
                self._settle_casino_round(prop, service, round_result)
            elif next_session:
                self._open_twenty_one_table(prop, next_session)
            return True

        if service == "casino_holdem" and option_id in {"casino_holdem:call", "casino_holdem:fold"}:
            if option_id.endswith(":call"):
                ok, credits = self._casino_commit_stake(int(session.get("wager", 0)))
                if not ok:
                    self._emit_casino_blocked(prop, service, "no_credits", cost=int(session.get("wager", 0)), credits=credits)
                    return True
                session = dict(session)
                session["stake"] = int(session.get("stake", session.get("wager", 0))) + int(session.get("wager", 0))
                round_result = _casino_holdem_resolve(session, "call")
            else:
                round_result = _casino_holdem_resolve(session, "fold")
            self._settle_casino_round(prop, service, round_result)
            return True

        return False

    def _forfeit_active_casino_session(self):
        session = self._casino_session()
        if not isinstance(session, dict):
            return
        service = str(session.get("service", "")).strip().lower()
        if service not in {"plinko", "crash", "video_poker", "keno", "roulette", "craps", "three_bright", "three_bones", "bloom_cards", "baccarat", "three_card_poker", "twenty_one", "casino_holdem"}:
            self._clear_casino_session()
            return
        prop = self.sim.properties.get(session.get("property_id"))
        if not isinstance(prop, dict):
            prop = {
                "id": session.get("property_id"),
                "name": session.get("property_name", "Casino"),
            }
        wager = int(session.get("wager", 0))
        stake = int(session.get("stake", wager))
        if service == "plinko":
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You pull the chip back too late.",
                "detail": "The board keeps the wager when you walk away after posting the drop.",
                "summary": f"You back out of plinko and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Drop not taken. Posted wager: {_credit_amount_label(stake)}.",
                    "The attendant sweeps the chip off the rail.",
                ],
                "drop_lane": None,
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "crash":
            current = _casino_crash_normalize_session(session)
            if isinstance(current, dict) and current.get("phase") == "setup":
                self._clear_casino_session()
                return
            multiplier = float(current.get("current_multiplier", 1.0) or 1.0) if isinstance(current, dict) else 1.0
            history = tuple(current.get("history", ()) or ()) if isinstance(current, dict) else (1.0,)
            crash_point = float(current.get("crash_point", 0.0) or 0.0) if isinstance(current, dict) else 0.0
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You step away from the graph.",
                "detail": "The posted crash stake is gone when you walk away without cashing out.",
                "summary": f"You abandon crash at x{multiplier:.2f} and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Last visible multiplier: x{multiplier:.2f}.",
                    (
                        f"Crash point: x{crash_point:.2f}."
                        if crash_point > 0.0
                        else "Crash point: unknown."
                    ),
                    "You leave without cashing out, so the machine keeps the stake.",
                ],
                "cashout_multiplier": 0.0,
                "crash_point": float(crash_point),
                "history": history,
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "video_poker":
            current = _casino_video_poker_normalize_session(session)
            cards = tuple(current.get("cards", ()) or ()) if isinstance(current, dict) else ()
            held_slots = tuple(
                idx + 1
                for idx, held in enumerate(list(current.get("holds", ()) or ()) if isinstance(current, dict) else [])
                if held
            )
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the machine mid-hand.",
                "detail": "The posted credits stay behind when you walk away before the draw.",
                "summary": f"You abandon video poker and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Cards: {_casino_cards_text(cards)}",
                    f"Held: {', '.join(str(slot) for slot in held_slots) if held_slots else 'none'}.",
                    "You step away before the draw and the wager is gone.",
                ],
                "player_cards": cards,
                "held_slots": held_slots,
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "keno":
            current = _casino_keno_normalize_session(session)
            picks = tuple(current.get("picks", ()) or ()) if isinstance(current, dict) else ()
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You crumple the ticket.",
                "detail": "The posted keno wager is gone when you walk away before the draw.",
                "summary": f"You abandon keno and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    (
                        f"Ticket: {' '.join(f'{number:02d}' for number in picks)}"
                        if picks
                        else "Ticket: blank."
                    ),
                    "You leave before the house draws the board, so the ticket dies on the rail.",
                ],
                "picked_numbers": picks,
                "pick_count": int(len(picks)),
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "roulette":
            current = _casino_roulette_normalize_session(session)
            view = str(current.get("view", "board") or "board").strip().lower() if isinstance(current, dict) else "board"
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the wheel cold.",
                "detail": "The posted roulette chip is gone when you step away before the croupier spins.",
                "summary": f"You abandon roulette and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Chip posted: {_credit_amount_label(stake)}.",
                    (
                        "You walk away from the straight-up board before the spin."
                        if view == "numbers"
                        else "You walk away from the layout before the spin."
                    ),
                ],
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "craps":
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the rail cold.",
                "detail": "The posted craps chip is gone when you step away before calling the bet.",
                "summary": f"You abandon craps and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Chip posted: {_credit_amount_label(stake)}.",
                    "You leave before choosing pass line, don't pass, or field.",
                ],
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "three_bright":
            current = _casino_three_bright_normalize_session(session)
            context = current.get("table_context", {}) if isinstance(current, dict) else {}
            bets = dict(current.get("bets", {}) or {}) if isinstance(current, dict) else {}
            slip_lines = []
            for key, units in list(sorted(bets.items()))[:6]:
                market = _casino_three_bright_market_from_key(key, context)
                if market:
                    slip_lines.append(f"{market['label']} x{int(units)}")
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the color dice cold.",
                "detail": "The posted Three Bright chips are gone when you step away before the roll.",
                "summary": f"You abandon Three Bright and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Chip posted: {_credit_amount_label(stake)}.",
                    *(slip_lines or ["Slip: no readable color markets."]),
                    "You leave before the dice tumble, so the house keeps the staged chips.",
                ],
                "table_context": dict(context) if isinstance(context, dict) else {},
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "three_bones":
            current = _casino_three_bones_normalize_session(session)
            context = current.get("table_context", {}) if isinstance(current, dict) else {}
            bets = dict(current.get("bets", {}) or {}) if isinstance(current, dict) else {}
            slip_lines = []
            for key, units in list(sorted(bets.items()))[:6]:
                market = _casino_three_bones_market_from_key(key, context)
                if market:
                    slip_lines.append(f"{market['label']} x{int(units)}")
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the cup untouched.",
                "detail": "The posted Three Bones chips are gone when you step away before the cup lifts.",
                "summary": f"You abandon Three Bones and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Chip posted: {_credit_amount_label(stake)}.",
                    *(slip_lines or ["Slip: no readable dice markets."]),
                    "You leave before the bones settle, so the house keeps the staged chips.",
                ],
                "table_context": dict(context) if isinstance(context, dict) else {},
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "bloom_cards":
            current = _casino_bloom_cards_normalize_session(session)
            garden = list(current.get("player_cards", ()) or []) if isinstance(current, dict) else []
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the garden on the table.",
                "detail": "The posted Bloom Cards stake is gone when you step away without cashing out.",
                "summary": f"You abandon Bloom Cards and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    "Garden: " + (", ".join(str(card.get("name", "bloom")) for card in garden[:6]) if garden else "--"),
                    "You leave before cashing out, so the table sweeps the garden.",
                ],
                "player_cards": tuple(dict(card) for card in garden if isinstance(card, dict)),
                "garden_cards": tuple(dict(card) for card in garden if isinstance(card, dict)),
                "table_context": dict(current.get("table_context", {}) if isinstance(current, dict) else {}),
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "baccarat":
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the shoe unopened.",
                "detail": "The posted baccarat wager stays on the felt when you walk before the hand is dealt.",
                "summary": f"You abandon baccarat and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Chip posted: {_credit_amount_label(stake)}.",
                    "You step away before choosing player, banker, or tie.",
                ],
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "three_card_poker":
            current = _casino_three_card_poker_normalize_session(session)
            player_cards = tuple(current.get("player_cards", ()) or ()) if isinstance(current, dict) else ()
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the ante in the circle.",
                "detail": "The posted three-card poker ante is gone when you walk before calling the play bet.",
                "summary": f"You abandon three-card poker and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Your hand: {_casino_cards_text(player_cards)}" if player_cards else "Your hand: --",
                    "You walk before deciding to play or fold, so the ante stays on the felt.",
                ],
                "player_cards": player_cards,
                "social_gain": 0,
                "stake_already_paid": True,
            }
        elif service == "twenty_one":
            current = _casino_twenty_one_normalize_session(session)
            hand_results = []
            if isinstance(current, dict):
                for idx, hand in enumerate(list(current.get("hands", ()) or ())):
                    cards = tuple(hand.get("cards", ()) or ())
                    total, _soft = _casino_blackjack_total(cards)
                    hand_results.append({
                        "index": idx,
                        "cards": cards,
                        "total": int(total),
                        "stake": int(hand.get("stake", wager)),
                        "doubled": bool(hand.get("doubled", False)),
                        "split_origin": bool(hand.get("split_origin", False)),
                    })
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You abandon the hand.",
                "detail": "You step away from the table and the dealer pulls in the chips.",
                "summary": f"You walk away from 21 and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    _casino_blackjack_line("Dealer", session.get("dealer_cards", ())),
                    *[
                        (
                            f"{_casino_blackjack_line(f'Hand {row['index'] + 1}', row['cards'])}"
                            f"{' [split]' if row['split_origin'] else ''}"
                            f"{' [double]' if row['doubled'] else ''}"
                        )
                        for row in hand_results
                    ],
                    "You leave the hand unfinished and the bet is gone.",
                ],
                "player_cards": tuple(hand_results[0]["cards"]) if hand_results else (),
                "player_hands": tuple(row["cards"] for row in hand_results),
                "dealer_cards": tuple(session.get("dealer_cards", ()) or ()),
                "player_total": int(hand_results[0]["total"]) if hand_results else 0,
                "player_totals": tuple(int(row["total"]) for row in hand_results),
                "dealer_total": _casino_blackjack_total(session.get("dealer_cards", ()))[0],
                "hand_results": tuple(
                    {
                        "index": int(row["index"]),
                        "total": int(row["total"]),
                        "stake": int(row["stake"]),
                        "result": "forfeit",
                        "doubled": bool(row["doubled"]),
                        "split_origin": bool(row["split_origin"]),
                    }
                    for row in hand_results
                ),
                "social_gain": 0,
                "stake_already_paid": True,
            }
        else:
            round_result = {
                "service": service,
                "wager": wager,
                "stake": stake,
                "payout": 0,
                "outcome_key": "forfeit",
                "headline": "You leave the table.",
                "detail": "The dealer rakes in the ante while you push back from the felt.",
                "summary": f"You walk away from the hold'em table and forfeit {_credit_amount_label(stake)}.",
                "result_lines": [
                    f"Your hand: {_casino_cards_text(session.get('player_cards', ())) }".rstrip(),
                    f"Flop: {_casino_cards_text(session.get('flop', ())) }".rstrip(),
                    "You leave the hand before showdown and the ante stays behind.",
                ],
                "player_cards": tuple(session.get("player_cards", ()) or ()),
                "dealer_cards": tuple(session.get("dealer_cards", ()) or ()),
                "board": tuple(session.get("flop", ()) or ()),
                "social_gain": 0,
                "stake_already_paid": True,
            }
        if service == "crash":
            self._settle_casino_round(prop, service, round_result)
        else:
            self._emit_casino_round(prop, service, round_result, show_result=False)

    def _bank_amount_choices(self, available, step):
        try:
            available_amount = int(available)
        except (TypeError, ValueError):
            available_amount = 0
        try:
            step_amount = int(step)
        except (TypeError, ValueError):
            step_amount = 1
        available_amount = max(0, available_amount)
        step_amount = max(1, step_amount)
        if available_amount <= 0:
            return []

        choices = []
        seen = set()
        for raw in (step_amount, step_amount * 2, step_amount * 4, available_amount):
            amount = max(1, min(available_amount, int(raw)))
            if amount in seen:
                continue
            seen.add(amount)
            choices.append(amount)
        return choices

    def _business_banking_contexts(self, eid):
        pos = self._position_for(eid)
        contexts = []
        for prop in player_owned_businesses_for_actor(self.sim, eid, pos=pos):
            if not isinstance(prop, dict):
                continue
            summary = player_business_summary(self.sim, prop)
            if not isinstance(summary, dict):
                continue
            contexts.append({
                "prop": prop,
                "summary": summary,
            })
        return contexts

    def _owned_repair_contexts(self, eid):
        return list(_owned_repairable_buildings(self.sim, eid) or ())

    def _justice_banking_context(self, eid):
        profile = self._profile_for(eid)
        debt_balance = 0
        if profile is not None:
            debt_amount = getattr(profile, "debt_amount", None)
            if callable(debt_amount):
                debt_balance = int(max(0, debt_amount("justice_fines") or 0))
            else:
                debt_balance = int(max(0, getattr(profile, "debt_balance", 0) or 0))
        held = _justice_held_property_snapshot(self.sim, eid)
        return {
            "debt_balance": int(debt_balance),
            "held_count": int(held.get("item_count", 0) or 0),
            "held_property_name": str(held.get("property_name", "") or "").strip(),
            "held_property_id": str(held.get("property_id", "") or "").strip(),
        }

    def _business_status_lines(self, business_context):
        if not isinstance(business_context, dict):
            return []
        prop = business_context.get("prop")
        snapshot = player_business_status_snapshot(self.sim, prop)
        if not isinstance(snapshot, dict):
            return []

        business_name = str(snapshot.get("business_name", "Business")).strip() or "Business"
        account_balance = int(snapshot.get("account_balance", 0))
        manager_count = int(snapshot.get("manager_count", 0))
        staff_count = int(snapshot.get("staff_count", 0))
        staff_total = int(snapshot.get("staff_total", 0))
        required_staff = max(1, int(snapshot.get("required_staff", 1)))
        note = str(snapshot.get("note", "")).strip() or "steady"
        market_note = str(snapshot.get("market_note", "")).strip()
        open_now = bool(snapshot.get("open_now"))
        hours_text = str(snapshot.get("hours_text", "")).strip() or self._business_hours_text(snapshot.get("opening_window"))
        hours_mode_label = str(snapshot.get("hours_mode_label", "")).strip() or player_business_hours_mode_label(snapshot.get("hours_mode"))
        customer_policy_label = str(snapshot.get("customer_policy_label", "")).strip() or player_business_customer_policy_label(snapshot.get("customer_policy"))
        markup_mode_label = str(snapshot.get("markup_mode_label", "")).strip() or player_business_markup_mode_label(snapshot.get("markup_mode"))
        open_roles = tuple(
            str(role).strip().lower()
            for role in tuple(snapshot.get("open_roles", ()) or ())
            if str(role).strip()
        )
        role_fit = dict(snapshot.get("role_fit", {})) if isinstance(snapshot.get("role_fit"), dict) else {}

        lines = [
            f"{business_name}.",
            f"Account: {_credit_amount_label(account_balance)}.",
            f"Staffing: {staff_total}/{required_staff} total | managers {manager_count} | staff {staff_count}.",
        ]
        for role_name, fit in (("Manager", role_fit.get("manager")), ("Staff", role_fit.get("staff"))):
            fit_line = self._business_role_fit_line(role_name, fit)
            if fit_line:
                lines.append(fit_line)
        lines.append(f"Policy: {customer_policy_label}.")
        lines.append(f"Hours: {hours_mode_label} | {hours_text}.")
        lines.append(f"Markup: {markup_mode_label}.")
        style_label = str(snapshot.get("operating_style_label", "")).strip()
        stock_label = str(snapshot.get("stock_identity_label", "")).strip()
        customer_mix = str(snapshot.get("customer_mix_label", "")).strip()
        staff_mood = str(snapshot.get("staff_mood_label", "")).strip()
        if style_label:
            lines.append(f"Style: {style_label}.")
        if stock_label:
            owner_stocked = int(snapshot.get("owner_stocked_count", 0) or 0)
            owner_note = f" | owner-stocked {owner_stocked}" if owner_stocked > 0 else ""
            lines.append(f"Shelf read: {stock_label}{owner_note}.")
        if customer_mix or staff_mood:
            mix_text = customer_mix or "mixed walk-ins"
            mood_text = staff_mood or "steady crew"
            lines.append(f"Customer mix: {mix_text} | Staff mood: {mood_text}.")
        wage_pressure_label = str(snapshot.get("wage_pressure_label", "")).strip()
        wage_pressure_reason = str(snapshot.get("wage_pressure_reason", "")).strip()
        if wage_pressure_label:
            wage_line = f"Wages: {wage_pressure_label}"
            if wage_pressure_reason:
                wage_line += f" | {wage_pressure_reason}"
            lines.append(wage_line + ".")
        lines.append(f"Status: {'open' if open_now else 'closed'} | {note}.")
        owner_reason = str(snapshot.get("owner_signal_reason", "")).strip()
        if owner_reason:
            lines.append(f"Owner read: {owner_reason}.")
        if open_roles:
            role_labels = ["manager" if role == "manager" else "staff" for role in open_roles]
            if len(role_labels) == 1:
                lines.append(f"Hiring: open {role_labels[0]} slot.")
            else:
                lines.append(f"Hiring: open {'/'.join(role_labels)} slots.")
        else:
            lines.append("Hiring: no immediate open slot.")
        lines.append("Staff changes: hire or fire people face to face.")
        if market_note:
            lines.append(f"Market: {market_note}.")
        reputation_note = str(snapshot.get("last_reputation_note", "")).strip() or str(snapshot.get("reputation_note", "")).strip()
        reputation_awareness = int(snapshot.get("last_reputation_awareness", snapshot.get("reputation_awareness", 0)) or 0)
        footfall_delta = int(snapshot.get("last_footfall_delta_pct", snapshot.get("footfall_delta_pct", 0)) or 0)
        churn_delta = int(snapshot.get("last_churn_delta_pct", snapshot.get("churn_delta_pct", 0)) or 0)
        if reputation_note and reputation_awareness > 0:
            lines.append(
                f"Neighborhood: {reputation_note} | footfall {footfall_delta:+d}% | churn {churn_delta:+d}%."
            )
        community_signal_note = str(snapshot.get("last_community_signal_note", "")).strip() or str(snapshot.get("community_signal_note", "")).strip()
        community_note = str(snapshot.get("last_community_note", "")).strip() or str(snapshot.get("community_note", "")).strip()
        scene_pressure_note = str(snapshot.get("last_scene_pressure_note", "")).strip() or str(snapshot.get("scene_pressure_note", "")).strip()
        scene_nuisance_note = str(snapshot.get("last_scene_nuisance_note", "")).strip()
        scene_nuisance_loss = int(snapshot.get("last_scene_nuisance_loss", 0) or 0)
        if community_signal_note and community_note:
            lines.append(f"Ripple: {community_signal_note} | block mood {community_note}.")
        elif community_signal_note:
            lines.append(f"Ripple: {community_signal_note}.")
        elif community_note:
            lines.append(f"Block mood: {community_note}.")
        if scene_pressure_note:
            lines.append(f"Frontage: {scene_pressure_note}.")
        if scene_nuisance_note:
            nuisance_line = f"Last hit: {scene_nuisance_note}"
            if scene_nuisance_loss > 0:
                nuisance_line += f" | loss {_credit_amount_label(scene_nuisance_loss)}"
            lines.append(nuisance_line + ".")

        gross_revenue = int(snapshot.get("gross_revenue", 0))
        realized_revenue = int(snapshot.get("realized_revenue", gross_revenue))
        slippage = int(snapshot.get("slippage", 0))
        wages_paid = int(snapshot.get("wages_paid", 0))
        wages_due = int(snapshot.get("wages_due", 0))
        upkeep_paid = int(snapshot.get("upkeep_paid", 0))
        upkeep_due = int(snapshot.get("upkeep_due", 0))
        unpaid_wages = int(snapshot.get("unpaid_wages", 0))
        unpaid_upkeep = int(snapshot.get("unpaid_upkeep", 0))
        service_reliability = max(0, int(round(float(snapshot.get("service_reliability", 0.0) or 0.0) * 100.0)))
        service_label = str(snapshot.get("service_reliability_label", "")).strip().lower()
        operating_note = str(snapshot.get("operating_note", "")).strip()
        last_hour = snapshot.get("last_hour")
        if last_hour is not None:
            revenue_label = _credit_amount_label(realized_revenue)
            if gross_revenue != realized_revenue:
                revenue_label = f"{revenue_label}/{_credit_amount_label(gross_revenue)}"
            lines.append(
                f"Last hour @{int(last_hour) % 24:02d}: revenue {revenue_label} | wages {_credit_amount_label(wages_paid)}/{_credit_amount_label(wages_due)} | upkeep {_credit_amount_label(upkeep_paid)}/{_credit_amount_label(upkeep_due)}."
            )
            if operating_note or service_label or slippage > 0:
                ops_label = operating_note or service_label or "steady ops"
                lines.append(
                    f"Ops: {ops_label} | reliability {service_reliability}% | slippage {_credit_amount_label(slippage)}."
                )
            if unpaid_wages > 0 or unpaid_upkeep > 0:
                short_bits = []
                if unpaid_wages > 0:
                    short_bits.append(f"payroll short {_credit_amount_label(unpaid_wages)}")
                if unpaid_upkeep > 0:
                    short_bits.append(f"upkeep short {_credit_amount_label(unpaid_upkeep)}")
                lines.append("Shortfall: " + " | ".join(short_bits) + ".")
        else:
            lines.append("No operating hour has been recorded yet.")
        return lines

    def _business_fit_skill_text(self, skill_ids):
        labels = []
        for skill_id in tuple(skill_ids or ())[:2]:
            label = str(_skill_label(skill_id)).strip()
            if label and label not in labels:
                labels.append(label)
        if not labels:
            return ""
        return " + ".join(labels)

    def _business_hours_text(self, opening):
        if not isinstance(opening, (list, tuple)) or len(opening) < 2:
            return "private"
        try:
            start_hour = int(opening[0]) % 24
            end_hour = int(opening[1]) % 24
        except (TypeError, ValueError):
            return "private"
        if start_hour == end_hour:
            return "all day"
        return f"{start_hour:02d}:00-{end_hour:02d}:00"

    def _business_policy_result_lines(self, prop, policy):
        business_name = str(prop.get("metadata", {}).get("business_name", prop.get("name", "Business"))).strip() or "Business"
        label = player_business_customer_policy_label(policy)
        if policy == "public":
            detail = "Walk-in customers can use the business services during open hours."
        elif policy == "staff_only":
            detail = "Walk-ins are turned away; only owner, staff, and credential holders can use services."
        else:
            detail = "Customer-facing service is shut down until you reopen it."
        return [
            line
            for line in (
                f"{business_name} customer policy set to {label}.",
                detail,
                self._business_street_read_line(prop),
            )
            if str(line).strip()
        ]

    def _business_hours_result_lines(self, prop, result):
        business_name = str(prop.get("metadata", {}).get("business_name", prop.get("name", "Business"))).strip() or "Business"
        if not isinstance(result, dict):
            return [f"{business_name} hours could not be updated right now."]
        hours_mode = str(result.get("hours_mode", "")).strip()
        hours_label = player_business_hours_mode_label(hours_mode)
        hours_text = str(result.get("hours_text", "")).strip() or self._business_hours_text(result.get("opening_window"))
        return [
            line
            for line in (
                f"{business_name} hours set to {hours_label}.",
                f"Open window: {hours_text}.",
                self._business_street_read_line(prop),
            )
            if str(line).strip()
        ]

    def _business_markup_result_lines(self, prop, mode):
        business_name = str(prop.get("metadata", {}).get("business_name", prop.get("name", "Business"))).strip() or "Business"
        label = player_business_markup_mode_label(mode)
        if mode == "discount":
            detail = "Public shelves run lighter margins to pull more foot traffic through the door."
        elif mode == "premium":
            detail = "The counter leans into stronger per-item margin without going full gouge."
        elif mode == "steep":
            detail = "The counter is pushing a sharp markup; margins rise, but demand tolerance gets touchier."
        else:
            detail = "The counter returns to its usual everyday pricing balance."
        return [
            line
            for line in (
                f"{business_name} markup set to {label}.",
                detail,
                self._business_street_read_line(prop),
            )
            if str(line).strip()
        ]

    def _business_street_read_line(self, prop):
        snapshot = player_business_status_snapshot(self.sim, prop)
        if not isinstance(snapshot, dict):
            return ""
        reason = str(snapshot.get("operating_style_reason", "")).strip()
        label = str(snapshot.get("operating_style_label", "")).strip()
        if reason:
            return f"Street read: {reason}."
        if label:
            return f"Street read: {label}."
        return ""

    def _business_role_fit_line(self, role_name, fit):
        if not isinstance(fit, dict):
            return ""
        label = str(fit.get("label", "unfilled")).strip().lower() or "unfilled"
        filled = bool(fit.get("filled"))
        count = max(0, int(fit.get("count", 0)))
        focus_text = self._business_fit_skill_text(fit.get("focus_skills", ()))
        strength_text = self._business_fit_skill_text(fit.get("strong_skills", ()))
        weak_text = self._business_fit_skill_text(fit.get("weak_skills", ()))

        if not filled or count <= 0:
            if focus_text:
                return f"{role_name} fit: unfilled | looking for {focus_text}."
            return f"{role_name} fit: unfilled."

        coverage = ""
        if count > 1:
            plural = "staff" if role_name.lower() == "staff" else f"{role_name.lower()}s"
            coverage = f" across {count} {plural}"
        if label in {"weak", "patchy"} and weak_text:
            if strength_text and strength_text != weak_text:
                return f"{role_name} fit: {label}{coverage} | strengths {strength_text} | needs {weak_text}."
            return f"{role_name} fit: {label}{coverage} | needs {weak_text}."
        if strength_text:
            return f"{role_name} fit: {label}{coverage} | strengths {strength_text}."
        return f"{role_name} fit: {label}{coverage}."

    def _bank_menu_options(self, eid, business_contexts=None):
        assets = self._assets_for(eid)
        profile = self._profile_for(eid)
        if not assets:
            return []

        options = []
        if profile:
            for amount in self._bank_amount_choices(profile.bank_balance, profile.withdraw_step):
                options.append({
                    "id": f"banking:withdraw:{int(amount)}",
                    "label": f"Withdraw {_credit_amount_label(amount)}",
                })
            for amount in self._bank_amount_choices(assets.credits, profile.deposit_step):
                options.append({
                    "id": f"banking:deposit:{int(amount)}",
                    "label": f"Deposit {_credit_amount_label(amount)}",
                })
            justice_context = self._justice_banking_context(eid)
            debt_balance = int(justice_context.get("debt_balance", 0) or 0)
            liquid_funds = int(max(0, getattr(assets, "credits", 0) or 0)) + int(max(0, getattr(profile, "bank_balance", 0) or 0))
            payable_cap = min(debt_balance, liquid_funds)
            for amount in self._bank_amount_choices(payable_cap, profile.withdraw_step):
                options.append({
                    "id": f"banking:pay_justice_debt:{int(amount)}",
                    "label": f"Pay justice debt {_credit_amount_label(amount)}",
                })

        for business_context in list(business_contexts or ()):
            if not isinstance(business_context, dict):
                continue
            business_prop = business_context.get("prop")
            summary = business_context.get("summary") or {}
            business_id = business_prop.get("id") if isinstance(business_prop, dict) else None
            if not business_id:
                continue
            withdraw_step = int(getattr(profile, "withdraw_step", 40) or 40)
            deposit_step = int(getattr(profile, "deposit_step", 48) or 48)
            business_balance = int(summary.get("account_balance", player_business_account_balance(business_prop)))
            business_name = str(summary.get("business_name", business_prop.get("name", "Business"))).strip() or "Business"
            current_policy = player_business_customer_policy(business_prop)
            next_policy = player_business_next_customer_policy(business_prop)
            current_hours_mode = player_business_hours_mode(business_prop)
            next_hours_mode = player_business_next_hours_mode(business_prop)
            current_markup_mode = player_business_markup_mode(business_prop)
            next_markup_mode = player_business_next_markup_mode(business_prop)
            for amount in self._bank_amount_choices(business_balance, withdraw_step):
                options.append({
                    "id": f"banking_business:withdraw:{int(amount)}:{business_id}",
                    "label": f"Business withdraw {_credit_amount_label(amount)} [{business_name}]",
                })
            for amount in self._bank_amount_choices(assets.credits, deposit_step):
                options.append({
                    "id": f"banking_business:deposit:{int(amount)}:{business_id}",
                    "label": f"Business deposit {_credit_amount_label(amount)} [{business_name}]",
                })
            options.append({
                "id": f"banking_business_status:{business_id}",
                "label": f"Business status [{business_name}]",
            })
            options.append({
                "id": f"banking_business_policy:{business_id}:{next_policy}",
                "label": (
                    f"Business policy [{business_name}]: "
                    f"{player_business_customer_policy_label(current_policy)} -> "
                    f"{player_business_customer_policy_label(next_policy)}"
                ),
            })
            options.append({
                "id": f"banking_business_hours:{business_id}:{next_hours_mode}",
                "label": (
                    f"Business hours [{business_name}]: "
                    f"{player_business_hours_mode_label(current_hours_mode)} -> "
                    f"{player_business_hours_mode_label(next_hours_mode)}"
                ),
            })
            options.append({
                "id": f"banking_business_markup:{business_id}:{next_markup_mode}",
                "label": (
                    f"Business markup [{business_name}]: "
                    f"{player_business_markup_mode_label(current_markup_mode)} -> "
                    f"{player_business_markup_mode_label(next_markup_mode)}"
                ),
            })
            employee_count = len(tuple(player_business_employee_wage_rows(self.sim, business_prop)))
            options.append({
                "id": f"banking_business_employees:{business_id}",
                "label": f"Business employees [{business_name}]: {employee_count} on roster",
            })
        return options

    def _owned_business_context_for_property(self, eid, prop):
        if not isinstance(prop, dict):
            return None
        property_id = str(prop.get("id", "") or "").strip()
        if not property_id:
            return None
        for context in self._business_banking_contexts(eid):
            candidate = context.get("prop") if isinstance(context, dict) else None
            if isinstance(candidate, dict) and str(candidate.get("id", "") or "").strip() == property_id:
                return {
                    "prop": prop,
                    "summary": player_business_summary(self.sim, prop) or context.get("summary") or {},
                }
        return None

    def _business_control_options(self, business_contexts, *, prefix="business_control", include_business_name=True, include_local_funds=False):
        options = []
        assets = self._assets_for(self.player_eid)
        profile = self._profile_for(self.player_eid)
        wallet_credits = int(getattr(assets, "credits", 0) or 0) if assets else 0
        withdraw_step = int(getattr(profile, "withdraw_step", 40) or 40)
        deposit_step = int(getattr(profile, "deposit_step", 48) or 48)
        for business_context in list(business_contexts or ()):
            if not isinstance(business_context, dict):
                continue
            business_prop = business_context.get("prop")
            summary = business_context.get("summary") or {}
            business_id = str((business_prop or {}).get("id", "") if isinstance(business_prop, dict) else "").strip()
            if not business_id:
                continue
            business_name = str(summary.get("business_name", (business_prop or {}).get("name", "Business"))).strip() or "Business"
            bracket = f" [{business_name}]" if include_business_name else ""
            current_policy = player_business_customer_policy(business_prop)
            next_policy = player_business_next_customer_policy(business_prop)
            current_hours_mode = player_business_hours_mode(business_prop)
            next_hours_mode = player_business_next_hours_mode(business_prop)
            current_markup_mode = player_business_markup_mode(business_prop)
            next_markup_mode = player_business_next_markup_mode(business_prop)
            employee_count = len(tuple(player_business_employee_wage_rows(self.sim, business_prop)))
            business_balance = int(summary.get("account_balance", player_business_account_balance(business_prop)) or 0)
            options.append({
                "id": f"{prefix}_status:{business_id}",
                "label": f"Business status{bracket}",
            })
            if include_local_funds:
                for amount in self._bank_amount_choices(business_balance, withdraw_step):
                    options.append({
                        "id": f"{prefix}_withdraw:{business_id}:{int(amount)}",
                        "label": f"Store withdraw{bracket}: {_credit_amount_label(amount)}",
                    })
                for amount in self._bank_amount_choices(wallet_credits, deposit_step):
                    options.append({
                        "id": f"{prefix}_deposit:{business_id}:{int(amount)}",
                        "label": f"Store deposit{bracket}: {_credit_amount_label(amount)}",
                    })
            options.extend((
                {
                    "id": f"{prefix}_policy:{business_id}:{next_policy}",
                    "label": (
                        f"Policy{bracket}: "
                        f"{player_business_customer_policy_label(current_policy)} -> "
                        f"{player_business_customer_policy_label(next_policy)}"
                    ),
                },
                {
                    "id": f"{prefix}_hours:{business_id}:{next_hours_mode}",
                    "label": (
                        f"Hours{bracket}: "
                        f"{player_business_hours_mode_label(current_hours_mode)} -> "
                        f"{player_business_hours_mode_label(next_hours_mode)}"
                    ),
                },
                {
                    "id": f"{prefix}_markup:{business_id}:{next_markup_mode}",
                    "label": (
                        f"Markup{bracket}: "
                        f"{player_business_markup_mode_label(current_markup_mode)} -> "
                        f"{player_business_markup_mode_label(next_markup_mode)}"
                    ),
                },
                {
                    "id": f"{prefix}_employees:{business_id}",
                    "label": f"Employees{bracket}: {employee_count} on roster",
                },
            ))
        return options

    def _business_employee_lines(self, business_prop):
        rows = tuple(player_business_employee_wage_rows(self.sim, business_prop))
        if not rows:
            return ["No rostered employees are attached to this business right now."]
        lines = []
        for row in rows:
            name = str(row.get("name", "Employee")).strip() or "Employee"
            staff_role = str(row.get("staff_role", "staff")).strip().lower() or "staff"
            career = str(row.get("career", "worker")).strip().replace("_", " ") or "worker"
            level_label = str(row.get("wage_level_label", "")).strip() or player_business_employee_wage_level_label(row.get("wage_level"))
            effective = int(row.get("effective_wage", 0) or 0)
            competitive = int(row.get("competitive_wage", effective) or effective)
            promised = int(row.get("promised_wage", 0) or 0)
            promise_text = f" | promised {_credit_amount_label(promised)}/hr" if promised > 0 else ""
            lines.append(
                f"{name}: {staff_role} | {career} | {level_label} {_credit_amount_label(effective)}/hr "
                f"(market {_credit_amount_label(competitive)}/hr){promise_text}."
            )
        return lines

    def _business_employee_wage_topics(self, business_prop, *, prefix, back_id):
        topics = [{"id": back_id, "label": "Back"}]
        business_id = str((business_prop or {}).get("id", "") or "").strip()
        if not business_id:
            return topics
        for row in player_business_employee_wage_rows(self.sim, business_prop):
            actor_eid = int(row.get("actor_eid", 0) or 0)
            if actor_eid <= 0:
                continue
            next_level = player_business_next_employee_wage_level(business_prop, actor_eid)
            next_label = player_business_employee_wage_level_label(next_level)
            name = str(row.get("name", "Employee")).strip() or "Employee"
            current_label = str(row.get("wage_level_label", "")).strip() or player_business_employee_wage_level_label(row.get("wage_level"))
            effective = int(row.get("effective_wage", 0) or 0)
            competitive = int(row.get("competitive_wage", effective) or effective)
            promised = int(row.get("promised_wage", 0) or 0)
            promise_text = f", promised {_credit_amount_label(promised)}" if promised > 0 else ""
            topics.append({
                "id": f"{prefix}_wage:{business_id}:{actor_eid}:{next_level}",
                "label": (
                    f"{name}: {current_label} {_credit_amount_label(effective)}/hr "
                    f"(market {_credit_amount_label(competitive)}{promise_text}) -> {next_label}"
                ),
            })
        return topics

    def _open_business_employee_menu(self, provider_prop, business_prop, *, prefix="business_control", return_option_id="business_management"):
        self._clear_pending_service_result()
        self._clear_casino_session()
        provider_id = (provider_prop or {}).get("id") if isinstance(provider_prop, dict) else None
        business_name = str((business_prop or {}).get("metadata", {}).get("business_name", (business_prop or {}).get("name", "Business"))).strip() or "Business"
        transcript = [f"Employee wages for {business_name}."]
        transcript.extend(self._business_employee_lines(business_prop))
        transcript.append("Fair pay is the competitive average. Lean saves payroll; premium costs more and helps staff mood.")
        topics = self._business_employee_wage_topics(
            business_prop,
            prefix=prefix,
            back_id=return_option_id,
        )
        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": provider_id,
            "title": f"Employees: {business_name}",
            "subtitle": "Wage levels",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose an employee row to cycle wage level. Esc closes the desk.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "business:employees",
            "business_employee_back_id": return_option_id,
            "business_employee_prefix": prefix,
            "casino_session": None,
        })

    def _open_business_management_menu(self, prop):
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str((prop or {}).get("name", (prop or {}).get("id", "Business desk"))).strip() or "Business desk"
        contexts = self._business_banking_contexts(self.player_eid)
        if not contexts:
            self._present_service_result(
                f"Business Desk: {prop_name}",
                ["No owned businesses are available for operational controls right now."],
                property_id=(prop or {}).get("id") if isinstance(prop, dict) else None,
            )
            return
        transcript = [
            f"Choose an owned business operation at {prop_name}.",
            "This desk handles policy, hours, markup, status, and employee wages. Account transfers stay at banking services.",
        ]
        for context in list(contexts[:3]):
            summary = context.get("summary") or {}
            business_name = str(summary.get("business_name", "Business")).strip() or "Business"
            staff_total = int(summary.get("staff_total", 0) or 0)
            required_staff = int(summary.get("required_staff", 1) or 1)
            note = str(summary.get("note", "")).strip() or "steady"
            wage_label = str(summary.get("wage_pressure_label", "")).strip() or "competitive pay"
            transcript.append(f"{business_name}: staff {staff_total}/{required_staff} | {note} | {wage_label}.")
        if len(contexts) > 3:
            transcript.append(f"... and {len(contexts) - 3} more owned business{'es' if len(contexts) - 3 != 1 else ''}.")
        topics = [{"id": "service_menu:root", "label": "Back"}]
        topics.extend(self._business_control_options(contexts, prefix="business_control", include_business_name=True))
        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": (prop or {}).get("id") if isinstance(prop, dict) else None,
            "title": f"Business Desk: {prop_name}",
            "subtitle": "Operational controls",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose status, policy, hours, markup, or employees. Esc closes the desk.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "business:management",
            "casino_session": None,
        })

    def _open_repair_target_menu(self, contractor_prop):
        self._clear_pending_service_result()
        self._clear_casino_session()
        contexts = self._owned_repair_contexts(self.player_eid)
        if not contexts:
            self._present_service_result(
                f"Repair: {contractor_prop.get('name', contractor_prop.get('id', 'Contractor'))}",
                ["No owned building currently needs shell repair."],
                property_id=contractor_prop.get("id"),
            )
            return

        transcript = ["Choose an owned building to patch up."]
        for context in list(contexts[:3]):
            target_prop = context.get("prop") or {}
            summary = context.get("summary") or {}
            name = str(target_prop.get("name", target_prop.get("id", "Building"))).strip() or "Building"
            bits = []
            if int(summary.get("window_count", 0) or 0) > 0:
                bits.append(f"{int(summary['window_count'])} window")
            if int(summary.get("door_count", 0) or 0) > 0:
                bits.append(f"{int(summary['door_count'])} door")
            if int(summary.get("wall_count", 0) or 0) > 0:
                bits.append(f"{int(summary['wall_count'])} wall")
            transcript.append(
                f"{name}: {', '.join(bits) if bits else 'damage logged'} | quote {_credit_amount_label(int(summary.get('cost', 0) or 0))}."
            )
        if len(contexts) > 3:
            transcript.append(f"{len(contexts) - 3} more owned building(s) need work.")

        topics = [{"id": "service_menu:root", "label": "Back"}]
        for context in contexts:
            target_prop = context.get("prop") or {}
            summary = context.get("summary") or {}
            target_property_id = str(target_prop.get("id", "")).strip()
            if not target_property_id:
                continue
            name = str(target_prop.get("name", target_property_id)).strip() or target_property_id
            bits = []
            if int(summary.get("window_count", 0) or 0) > 0:
                bits.append(f"{int(summary['window_count'])}w")
            if int(summary.get("door_count", 0) or 0) > 0:
                bits.append(f"{int(summary['door_count'])}d")
            if int(summary.get("wall_count", 0) or 0) > 0:
                bits.append(f"{int(summary['wall_count'])}wall")
            label = f"Repair {_credit_amount_label(int(summary.get('cost', 0) or 0))} [{name}]"
            if bits:
                label += f" ({', '.join(bits)})"
            topics.append({
                "id": f"building_repair:target|{target_property_id}",
                "label": label,
            })

        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": contractor_prop.get("id"),
            "title": f"Repair: {contractor_prop.get('name', contractor_prop.get('id', 'Contractor'))}",
            "subtitle": "Owned building shell repair",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose a building to restore its damaged shell. Esc closes the contractor desk.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "contractor:repair_targets",
            "casino_session": None,
        })

    def _open_business_remodel_business_menu(self, contractor_prop):
        self._clear_pending_service_result()
        self._clear_casino_session()
        business_contexts = self._business_banking_contexts(self.player_eid)
        if not business_contexts:
            self._present_service_result(
                f"Business Refit: {contractor_prop.get('name', contractor_prop.get('id', 'Contractor'))}",
                ["No owned business is available for a model change right now."],
                property_id=contractor_prop.get("id"),
            )
            return

        transcript = ["Choose which owned business you want to refit."]
        topics = [{"id": "service_menu:root", "label": "Back"}]
        for context in business_contexts:
            target_prop = context.get("prop") or {}
            summary = context.get("summary") or {}
            target_property_id = str(target_prop.get("id", "")).strip()
            if not target_property_id:
                continue
            business_name = str(summary.get("business_name", target_prop.get("name", target_property_id))).strip() or target_property_id
            archetype = str((target_prop.get("metadata", {}) or {}).get("archetype", "")).strip().replace("_", " ").title() or "Business"
            transcript.append(f"{business_name}: currently {archetype.lower()} | purchase {_credit_amount_label(int((target_prop.get('metadata', {}) or {}).get('purchase_cost', 0) or 0))}.")
            topics.append({
                "id": f"business_remodel:target|{target_property_id}",
                "label": f"Refit [{business_name}]",
            })

        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": contractor_prop.get("id"),
            "title": f"Business Refit: {contractor_prop.get('name', contractor_prop.get('id', 'Contractor'))}",
            "subtitle": "Owned business selection",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose a business to see contractor conversion quotes.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "contractor:remodel_targets",
            "casino_session": None,
        })

    def _open_business_remodel_option_menu(self, contractor_prop, target_prop):
        self._clear_pending_service_result()
        self._clear_casino_session()
        options = list(player_business_remodel_options(target_prop) or ())
        if not options:
            name = str(target_prop.get("name", target_prop.get("id", "Business"))).strip() or "Business"
            self._present_service_result(
                f"Business Refit: {name}",
                ["No alternate business model is available for this property right now."],
                property_id=contractor_prop.get("id"),
            )
            return

        metadata = target_prop.get("metadata", {}) if isinstance(target_prop.get("metadata"), dict) else {}
        business_name = str(metadata.get("business_name", target_prop.get("name", "Business"))).strip() or "Business"
        current_archetype = str(metadata.get("archetype", "")).strip().replace("_", " ").title() or "Business"
        current_quote = player_business_remodel_quote(target_prop, str(options[0].get("target_archetype", "")))
        purchase_cost = int(metadata.get("purchase_cost", 0) or 0)

        transcript = [
            f"{business_name} is currently set as {current_archetype.lower()}.",
            f"Source purchase {_credit_amount_label(purchase_cost)} drives the contractor baseline.",
        ]
        if isinstance(current_quote, dict):
            transcript.append("Rarer target businesses quote higher than common ones.")

        topics = [{"id": "business_remodel", "label": "Back"}]
        target_property_id = str(target_prop.get("id", "")).strip()
        for option in options:
            target_archetype = str(option.get("target_archetype", "")).strip().lower()
            if not target_archetype:
                continue
            label = (
                f"{str(option.get('target_label', target_archetype)).strip()} "
                f"({_credit_amount_label(int(option.get('cost', 0) or 0))}, {str(option.get('rarity_label', 'common')).strip()})"
            )
            topics.append({
                "id": f"business_remodel:apply|{target_property_id}|{target_archetype}",
                "label": label,
            })

        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": contractor_prop.get("id"),
            "title": f"Business Refit: {business_name}",
            "subtitle": current_archetype,
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose a new business model. The quote scales with rarity and the source property cost.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "contractor:remodel_apply",
            "casino_session": None,
        })

    def _open_vehicle_sale_menu(self, prop, quality):
        quality = _vehicle_sale_quality(quality)
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Vehicle Sales"))).strip() or "Vehicle Sales"
        offers = _vehicle_sale_offers(self.sim, prop, quality)
        if not offers:
            self._present_service_result(
                f"{_vehicle_sale_quality_title(quality)} Vehicles: {prop_name}",
                [f"No {_site_service_label(f'vehicle_sales_{quality}')} are posted right now."],
                property_id=prop.get("id"),
            )
            return

        topics = []
        for offer in offers:
            topic = dict(offer)
            topic["id"] = f"vehicle_sales_{quality}:offer:{str(offer.get('offering_id', '')).strip()}"
            topic["label"] = _vehicle_sale_offer_label(offer)
            topics.append(topic)

        state = self._dialog_ui_state()
        transcript = [
            f"Choose a {quality} vehicle at {prop_name}.",
            "Each listing shows price, class, fuel, and drive stats.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ]
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"{_vehicle_sale_quality_title(quality)} Vehicles: {prop_name}",
            "subtitle": "Available offerings",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose the exact vehicle you want. Esc closes; Space clears result messages.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": f"vehicles:{quality}",
            "casino_session": None,
        })

    def _transit_destinations(self, prop, service):
        service = str(service or "").strip().lower()
        if service not in TRANSIT_SERVICE_IDS:
            return ()
        return _shared_transit_destinations(self.sim, prop, service)

    def _open_transit_menu(self, prop, service):
        self._clear_pending_service_result()
        self._clear_casino_session()
        service = str(service or "").strip().lower()
        profile = _transit_service_profile(service) or {}
        title = _transit_service_title(service)
        prop_name = str(prop.get("name", prop.get("id", "Transit"))).strip() or "Transit"
        destinations = self._transit_destinations(prop, service)
        if not destinations:
            no_destinations_line = str(
                profile.get("no_destinations_line", "No outbound transit service is posted from {prop_name} right now.")
            ).format(prop_name=prop_name)
            self._present_service_result(
                f"{title}: {prop_name}",
                [no_destinations_line],
                property_id=prop.get("id"),
            )
            return

        city_tokens = self._inventory_item_count("city_pass_token")
        daypasses = self._inventory_item_count("transit_daypass")
        topics = []
        for index, destination in enumerate(destinations, start=1):
            payment = _transit_payment_profile(
                service,
                destination.get("distance", 1),
                city_tokens=city_tokens,
                daypasses=daypasses,
            )
            distance = int(destination.get("distance", 0) or 0)
            direction_label = str(destination.get("direction_label", "")).strip()
            destination_name = str(destination.get("destination_name", destination.get("station_name", "Transit Stop"))).strip() or "Transit Stop"
            if bool(profile.get("token_only")):
                fare_label = _transit_fare_label(
                    service,
                    fare_mode="city_pass_token",
                    token_cost=int(payment.get("token_cost", payment.get("cost", 1)) or 1),
                )
                if daypasses > 0 and bool(profile.get("allow_daypass", True)):
                    fare_label = f"{fare_label} / daypass"
            else:
                fare_label = _transit_fare_label(
                    service,
                    fare_mode=payment.get("fare_mode", "credits"),
                    cost=int(payment.get("cost", 0) or 0),
                    token_cost=int(payment.get("token_cost", 0) or 0),
                )
            bits = [f"{distance}c"]
            travel_ticks = _transit_travel_ticks(self.sim, service, distance)
            bits.append(f"ETA {_tick_duration_label(self.sim, travel_ticks)}")
            if direction_label:
                bits.append(direction_label)
            settlement_name = str(destination.get("settlement_name", "")).strip()
            if settlement_name:
                bits.append(settlement_name)
            label = f"{destination_name} [{' | '.join(bits)}] - {fare_label}"
            topics.append({
                "id": f"{service}:dest:{index}",
                "label": label,
                "destination_chunk": tuple(destination.get("chunk", ()) or ()),
                "destination_node_id": str(destination.get("node_id", "")).strip(),
                "destination_building_id": str(destination.get("building_id", "")).strip(),
                "destination_name": destination_name,
                "destination_distance": distance,
                "quoted_cost": int(payment.get("cost", 0) or 0),
                "quoted_token_cost": int(payment.get("token_cost", 0) or 0),
                "quote_mode": str(payment.get("fare_mode", "credits")).strip().lower() or "credits",
            })

        transcript = [f"Choose a {title.lower()} destination from {prop_name}."]
        transcript.extend(
            str(line).strip()
            for line in tuple(profile.get("summary_lines", ()) or ())
            if str(line).strip()
        )
        transcript.append(
            f"Wallet {_credit_amount_label(self._wallet_credits())} | "
            f"City tokens {city_tokens} | Daypasses {daypasses}."
        )
        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"{title}: {prop_name}",
            "subtitle": str(profile.get("subtitle", "Transit departures")).strip() or "Transit departures",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose the stop you want. Esc closes; Space clears result messages.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": service,
            "casino_session": None,
        })

    def _open_rail_transit_menu(self, prop):
        self._open_transit_menu(prop, "rail_transit")

    def _present_service_result(self, title, lines, *, subtitle="", property_id=None):
        state = self._dialog_ui_state()
        transcript = [str(line).strip() for line in list(lines or ()) if str(line).strip()]
        if not transcript:
            transcript = ["Done."]
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": property_id,
            "title": str(title or "Service").strip() or "Service",
            "subtitle": str(subtitle or "").strip(),
            "transcript": transcript,
            "topics": [],
            "selected_index": 0,
            "scroll": max(0, len(transcript) - 1),
            "hint": "Service result. Press Space to close.",
            "new_topic_ids": [],
            "close_pending": True,
            "machine_action": None,
            "service_menu_mode": "result",
        })
        self._clear_pending_service_result()

    def _machine_service_profile(self, prop):
        if not _property_is_storefront(prop):
            return None
        service = _storefront_service_profile(self.sim, prop, actor_eid=self.player_eid)
        mode = str(service.get("mode", "")).strip().lower()
        if mode == "automated" or bool(service.get("fallback_self_serve")):
            return service
        return None

    def _storefront_blocked_lines(self, prop, storefront_service):
        prop_name = str((prop or {}).get("name", (prop or {}).get("id", "Storefront"))).strip() or "Storefront"
        storefront_service = storefront_service if isinstance(storefront_service, dict) else {}
        reason = str(storefront_service.get("blocked_reason", "")).strip().lower()
        if reason == "no_staff":
            return f"Shopping: {prop_name}", [
                f"No clerk is serving {prop_name} right now.",
                "Try again when counter staff are present, or use an unattended self-serve kiosk directly.",
            ]
        return f"Shopping: {prop_name}", [f"No shopping counter is ready at {prop_name} right now."]

    def _open_property_service_surface(self, prop):
        if not isinstance(prop, dict):
            return ""
        pos = self._position_for(self.player_eid)
        if not pos:
            return ""
        archetype = str(((prop.get("metadata", {}) or {}).get("archetype", "") or "").strip().lower())
        if archetype in CASINO_FLOOR_ARCHETYPES:
            self._open_casino_floor(prop)
            return "ready"
        options, storefront_service = self._service_menu_options(self.player_eid, prop, pos)
        if options:
            option_ids = [str(option.get("id", "")).strip().lower() for option in options]
            if _property_infrastructure_role(prop) == "service_terminal" and option_ids == ["banking"]:
                self._open_banking_menu(prop)
            else:
                self._open_service_menu(prop, options, storefront_service=storefront_service)
            return "ready"
        if _property_is_storefront(prop) and isinstance(storefront_service, dict) and storefront_service.get("blocked_reason") and not self._machine_service_profile(prop):
            title, lines = self._storefront_blocked_lines(prop, storefront_service)
            self._present_service_result(title, lines, property_id=prop.get("id"))
            return "blocked"
        return ""

    def _service_menu_options(self, eid, prop, pos):
        dispatch_ok = self._player_can_call_justice_from_property(eid, prop, pos)
        owner_business_context = self._owned_business_context_for_property(eid, prop)
        owner_business_ok = isinstance(owner_business_context, dict)
        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        cult_assoc = cult_property_association(self.sim, prop)
        cult_contact_ok = bool(cult_assoc.get("always_contact"))
        if not access.can_use_services and not dispatch_ok and not owner_business_ok and not cult_contact_ok:
            return [], None

        options = []
        storefront_service = None
        if owner_business_ok:
            options.extend(self._business_control_options(
                (owner_business_context,),
                prefix="business_control",
                include_business_name=False,
                include_local_funds=True,
            ))
        if access.can_use_services and _property_is_storefront(prop):
            storefront_service = _storefront_service_profile(self.sim, prop, actor_eid=eid)
            if storefront_service.get("available") and not self._machine_service_profile(prop):
                options.append({"id": "trade_buy", "label": _service_menu_option_label("trade_buy")})
                options.append({"id": "trade_sell", "label": _service_menu_option_label("trade_sell")})

        finance_services = set(_finance_services_for_property(prop)) if access.can_use_services else set()
        if "banking" in finance_services:
            options.append({"id": "banking", "label": _service_menu_option_label("banking")})
        if "insurance" in finance_services:
            options.append({"id": "insurance", "label": _service_menu_option_label("insurance")})

        if access.can_use_services and self._player_can_redeem_meal_voucher(prop):
            options.append({"id": "redeem_meal_voucher", "label": "Redeem meal voucher"})

        for site_service in _site_services_for_property(prop) if access.can_use_services else ():
            if site_service == HOLDEM_CASH_SERVICE_ID and not isinstance(
                holdem_cash_table_for_property(self.sim, prop, ensure=False),
                dict,
            ):
                continue
            options.append({"id": site_service, "label": _service_menu_option_label(site_service)})
            if site_service == "fuel" and self._inventory_item_count("glass_bottle") > 0:
                options.append({"id": "fuel_fill_bottle", "label": _service_menu_option_label("fuel_fill_bottle")})
        for cult_service in cult_services_for_property(self.sim, prop, actor_eid=eid) if (access.can_use_services or cult_contact_ok) else ():
            options.append({"id": cult_service, "label": _service_menu_option_label(cult_service)})

        if dispatch_ok:
            options.append({"id": "justice_dispatch", "label": _service_menu_option_label("justice_dispatch")})

        deduped = []
        seen = set()
        for option in options:
            option_id = str(option.get("id", "")).strip().lower()
            if not option_id or option_id in seen:
                continue
            seen.add(option_id)
            deduped.append(option)
        return deduped, storefront_service

    def _open_banking_menu(self, prop):
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Banking"))).strip() or "Banking"
        assets = self._assets_for(self.player_eid)
        profile = self._profile_for(self.player_eid)
        business_contexts = self._business_banking_contexts(self.player_eid)
        justice_context = self._justice_banking_context(self.player_eid)
        wallet_credits = int(getattr(assets, "credits", 0)) if assets else 0
        bank_balance = int(getattr(profile, "bank_balance", 0)) if profile else 0
        options = self._bank_menu_options(self.player_eid, business_contexts=business_contexts)
        transcript = [
            f"Choose how much to move at {prop_name}.",
            f"Wallet {_credit_amount_label(wallet_credits)} | Bank {_credit_amount_label(bank_balance)}.",
        ]
        justice_debt = int(justice_context.get("debt_balance", 0) or 0)
        held_count = int(justice_context.get("held_count", 0) or 0)
        held_property_name = str(justice_context.get("held_property_name", "") or "").strip()
        if justice_debt > 0:
            transcript.append(f"Justice debt: {_credit_amount_label(justice_debt)}.")
        if held_count > 0:
            if justice_debt > 0:
                transcript.append(
                    f"Held property: {held_count} item(s) at {held_property_name or 'the justice desk'}; release waits on debt."
                )
            else:
                transcript.append(
                    f"Held property: {held_count} item(s) at {held_property_name or 'the justice desk'} ready for release."
                )
        if business_contexts:
            transcript.append(
                f"Business accounts: {len(business_contexts)} available from any banking service."
            )
            for business_context in list(business_contexts[:3]):
                summary = business_context.get("summary") or {}
                business_name = str(summary.get("business_name", "Business")).strip() or "Business"
                business_balance = int(summary.get("account_balance", 0))
                staff_total = int(summary.get("staff_total", 0))
                required_staff = int(summary.get("required_staff", 1))
                note = str(summary.get("note", "")).strip() or "steady"
                policy_label = str(summary.get("customer_policy_label", "")).strip() or player_business_customer_policy_label(summary.get("customer_policy"))
                hours_label = str(summary.get("hours_mode_label", "")).strip() or player_business_hours_mode_label(summary.get("hours_mode"))
                markup_label = str(summary.get("markup_mode_label", "")).strip() or player_business_markup_mode_label(summary.get("markup_mode"))
                hours_text = str(summary.get("hours_text", "")).strip() or self._business_hours_text(summary.get("opening_window"))
                transcript.append(
                    f"{business_name}: account {_credit_amount_label(business_balance)} | staff {staff_total}/{required_staff} | {note}."
                )
                transcript.append(f"Policy {policy_label} | Hours {hours_label} ({hours_text}) | Markup {markup_label}.")
            remaining_businesses = max(0, len(business_contexts) - 3)
            if remaining_businesses > 0:
                transcript.append(f"... and {remaining_businesses} more business account{'s' if remaining_businesses != 1 else ''}.")
        if not profile and not business_contexts:
            self._present_service_result(
                f"Banking: {prop_name}",
                ["No verified account record is available."],
                property_id=prop.get("id"),
            )
            return
        if not options:
            self._present_service_result(
                f"Banking: {prop_name}",
                [
                    "No funds are available to move right now.",
                    f"Wallet {_credit_amount_label(wallet_credits)} | Bank {_credit_amount_label(bank_balance)}.",
                ],
                property_id=prop.get("id"),
            )
            return

        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"Banking: {prop_name}",
            "subtitle": "",
            "transcript": transcript,
            "topics": options,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose a transfer amount or review owned-business status here.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "banking",
            "casino_session": None,
        })

    def _open_casino_game_menu(self, prop, service):
        self._clear_pending_service_result()
        self._clear_casino_session()
        self._open_casino_wager(
            prop,
            service,
            host_style=casino_host_style(prop),
            return_to="floor" if casino_host_style(prop) == "floor" else "service_menu",
        )

    def _handoff_casino_floor_service(self, prop, option_id):
        """Execute a casino floor-service row through the canonical service menu."""
        if not isinstance(prop, dict):
            title, lines = self._stale_service_option_lines(option_id)
            self._close_casino_ui()
            self._present_service_result(title, lines)
            return
        pos = self._position_for(self.player_eid)
        if pos is None:
            return
        options, storefront_service = self._service_menu_options(self.player_eid, prop, pos)
        self._close_casino_ui()
        self._open_service_menu(prop, options, storefront_service=storefront_service)
        self.on_service_menu_execute_request(Event(
            "service_menu_execute_request",
            eid=self.player_eid,
            property_id=prop.get("id"),
            option_id=option_id,
        ))

    def _open_service_menu(self, prop, options, storefront_service=None):
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Service"))).strip() or "Service"
        transcript = [f"Choose a service at {prop_name}."]
        subtitle_bits = []
        if isinstance(storefront_service, dict):
            note = str(storefront_service.get("service_note", "")).strip()
            if note:
                subtitle_bits.append(note)
        machine_profile = self._machine_service_profile(prop)
        machine_action = None
        if machine_profile:
            transcript.append("Use the unattended machine directly from its tile.")
            machine_action = {
                "property_id": prop.get("id"),
                "mode": "buy",
                "automated_only": True,
            }

        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"Services: {prop_name}",
            "subtitle": " | ".join(bit for bit in subtitle_bits if bit),
            "transcript": transcript,
            "topics": list(options),
            "selected_index": 0,
            "scroll": 0,
            "hint": "Pick a service. Staffed counters are routed here; machines open directly from their tile.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": machine_action,
            "service_menu_mode": "root",
            "casino_session": None,
        })

    def _open_lodging_stay_menu(self, prop):
        if not isinstance(prop, dict):
            title, lines = self._stale_service_option_lines("rest")
            self._present_service_result(title, lines)
            return
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Rooms"))).strip() or "Rooms"
        checkout_hour = self._lodging_checkout_hour(prop)
        checkout_ticks = self._ticks_until_clock_hour(checkout_hour)
        checkout_label = self._format_clock_hour(checkout_hour)
        transcript = [
            f"{prop_name} asks how long you want the room.",
            "The room rate is charged once; short naps recover less than a full sleep.",
            f"Checkout here is {checkout_label}.",
        ]
        topics = [{"id": "service_menu:root", "label": "Back"}]
        for hours in self.ROOM_STAY_HOUR_OPTIONS:
            topics.append({
                "id": f"rest:stay:hours:{hours}",
                "label": f"Sleep {hours}h",
            })
        topics.append({
            "id": f"rest:stay:checkout:{checkout_ticks}",
            "label": f"Stay until checkout ({checkout_label}, {_tick_duration_label(self.sim, checkout_ticks)})",
        })
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"Room: {prop_name}",
            "subtitle": "Choose stay length",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 1 if len(topics) > 1 else 0,
            "scroll": 0,
            "hint": "Choose a room stay. Esc closes the desk.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "lodging:rest",
            "casino_session": None,
        })

    def _open_appearance_style_menu(self, prop):
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Styling"))).strip() or "Styling"
        topics = [{"id": "service_menu:root", "label": "Back"}]
        label_prefix = {
            "hair_style": "Hair style",
            "hair_color": "Hair color",
            "makeup": "Makeup",
            "makeup_eyes": "Eyes",
            "makeup_lips": "Lips",
            "makeup_cheeks": "Cheeks",
        }
        for kind in style_service_kinds_for_property(prop):
            for value in STYLE_SERVICE_OPTIONS.get(kind, ()):
                topics.append({
                    "id": f"appearance_style:{kind}:{value}",
                    "label": f"{label_prefix.get(kind, kind.replace('_', ' ').title())}: {str(value).replace('_', ' ').title()}",
                })
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"Styling: {prop_name}",
            "subtitle": "",
            "transcript": [f"Choose a styling change at {prop_name}."],
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose hair, color, or makeup styling.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "appearance_style",
            "casino_session": None,
        })

    def _open_service_job_board(self, prop, service):
        service = str(service or "").strip().lower()
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Jobs"))).strip() or "Jobs"
        offers = service_job_board_offers(self.sim, self.player_eid, prop, service, limit=5)
        topics = [{"id": "service_menu:root", "label": "Back"}]
        bounty_license_active = True
        if service == "bounty_jobs":
            bounty_license_active = civic_license_is_active(self.sim, self.player_eid, "bounty")
            if not bounty_license_active:
                topics.append({
                    "id": "bounty_jobs:license_buy",
                    "label": f"File bounty credential - {int(LICENSE_FEES['bounty'])}c",
                })
        for offer in offers:
            topics.append({
                "id": f"{service}:accept|{offer.get('job_key')}",
                "label": str(offer.get("label", "Job")).strip() or "Job",
                "job_key": str(offer.get("job_key", "") or "").strip(),
                "service": service,
            })
        board_title = _service_menu_option_label(service)
        transcript = [f"{board_title} at {prop_name}."]
        if service == "bounty_jobs":
            if bounty_license_active:
                transcript.extend([
                    "Recovery credential: active.",
                    "Filed scope: matching posted targets; pursuit, unarmed recovery force, and restraint after surrender or incapacitation.",
                    "Excluded: lethal force, firearms against a non-threatening target, explosives, property search, and collateral harm.",
                ])
            else:
                transcript.extend([
                    "Recovery credential: not active.",
                    "This desk will show public postings, but it will not assign one until a bounty credential is filed.",
                ])
        if not offers:
            transcript.append("Nothing useful is posted right now.")
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"{board_title}: {prop_name}",
            "subtitle": "",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose a posted job to accept it.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": service,
            "casino_session": None,
        })

    def _open_ecology_registry(self, prop, domain):
        domain = str(domain or "").strip().lower()
        if domain not in {"flora", "fauna"}:
            return
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Registry"))).strip() or "Registry"
        rows = ecology_species_registry_rows(self.sim, domain)
        domain_title = "Flora" if domain == "flora" else "Fauna"
        transcript = [f"Installation-native {domain} recorded at {prop_name}."]
        if rows:
            if domain == "fauna":
                transcript.extend(
                    f"{row['name']} -> {row['appearance']} | population {row.get('abundance', 100)}% ({str(row.get('population_status', 'common')).replace('_', ' ')}) | value x{float(row.get('value_multiplier', 1.0) or 1.0):g}"
                    for row in rows
                )
            else:
                transcript.extend(f"{row['name']} -> {row['appearance']}" for row in rows)
        else:
            transcript.append(f"No installation-native {domain} lines have been discovered yet.")
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"{domain_title} Registry: {prop_name}",
            "subtitle": f"{len(rows)} present line{'s' if len(rows) != 1 else ''}",
            "transcript": transcript,
            "topics": [{"id": "service_menu:root", "label": "Back"}],
            "selected_index": 0,
            "scroll": 0,
            "hint": "Names and visible forms are listed here. Population actions will attach to these lines later.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": f"ecology_registry:{domain}",
            "ecology_registry_rows": [dict(row) for row in rows],
            "casino_session": None,
        })

    def _open_civic_records(self, prop):
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        authority = civic_records_authority(self.sim, prop)
        records = civic_people_records(self.sim, prop)
        prop_name = str(prop.get("name", prop.get("id", "Records Office"))).strip() or "Records Office"
        scope = str(authority.get("settlement_name", "") or "local jurisdiction").strip()
        topics = [
            {"id": "service_menu:root", "label": "Back"},
            {"id": "civic_records:census", "label": "Review census summary"},
            {"id": "civic_records:people", "label": "Browse public people records"},
            {"id": "civic_records:self", "label": "Review my civic file"},
            {"id": "civic_records:licenses", "label": "Review licenses and permits"},
            {"id": "civic_records:culls", "label": "Declare a fauna cull"},
        ]
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"Civic Records: {prop_name}",
            "subtitle": f"{authority['authority_name']} | {len(records)} file{'s' if len(records) != 1 else ''}",
            "transcript": [
                f"{authority['office_name']} exposes the public registry for {scope}.",
                "Census, residence, employment, civil status, public affiliations, property interests, permits, and docket amendments are available here.",
                "Private biology, witness identity, appearance, social history, and covert affiliations remain redacted.",
            ],
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Choose a public ledger. Restricted records remain a credentials or wire problem.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "civic_records",
            "civic_record_rows": [dict(row) for row in records],
            "casino_session": None,
        })

    def _open_civic_census(self, prop):
        state = self._dialog_ui_state()
        records = civic_people_records(self.sim, prop)
        authority = civic_records_authority(self.sim, prop)
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "title": f"Census: {authority['authority_name']}",
            "subtitle": f"{len(records)} registered file{'s' if len(records) != 1 else ''}",
            "transcript": list(civic_census_lines(self.sim, prop, records=records)),
            "topics": [{"id": "civic_records:root", "label": "Back to civic records"}],
            "selected_index": 0,
            "scroll": 0,
            "hint": "This census includes streamed-out residents without realizing their simulation chunks.",
            "service_menu_mode": "civic_records:census",
            "civic_record_rows": [dict(row) for row in records],
        })

    def _open_civic_people_directory(self, prop):
        state = self._dialog_ui_state()
        records = civic_people_records(self.sim, prop)
        authority = civic_records_authority(self.sim, prop)
        topics = [{"id": "civic_records:root", "label": "Back to civic records"}]
        for record in records:
            career = str(record.get("career", "") or "").replace("_", " ").strip()
            status = str(record.get("status", "registered") or "registered").replace("_", " ").strip()
            detail = career or status
            topics.append({
                "id": f"civic_records:person|{int(record['eid'])}",
                "label": f"{record['name']} — {detail}",
            })
        transcript = [f"Public people index maintained by {authority['authority_name']}."]
        if not records:
            transcript.append("No human records are filed in this jurisdiction yet.")
        else:
            transcript.append("Select a person to inspect the public portion of their civic file.")
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "title": "Public People Index",
            "subtitle": f"{len(records)} file{'s' if len(records) != 1 else ''}",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Selecting a file records its public identity in your notebook without telling that person who you are.",
            "service_menu_mode": "civic_records:people",
            "civic_record_rows": [dict(row) for row in records],
        })

    def _open_civic_person_record(self, prop, subject_eid):
        state = self._dialog_ui_state()
        records = civic_people_records(self.sim, prop)
        record = next((row for row in records if int(row.get("eid", -1)) == int(subject_eid)), None)
        if record is None:
            self._present_service_result(
                "Civic Record",
                ["That public file is no longer available in this jurisdiction."],
                property_id=prop.get("id"),
            )
            return
        remember_civic_record_inspection(
            self.sim,
            self.player_eid,
            record,
            property_id=prop.get("id"),
        )
        self.sim.emit(Event(
            "civic_record_inspected",
            eid=self.player_eid,
            subject_eid=int(record["eid"]),
            subject_name=record.get("name"),
            property_id=prop.get("id"),
            property_name=prop.get("name", prop.get("id")),
            record_status=record.get("status"),
            corrected_case_count=int(record.get("corrected_case_count", 0) or 0),
            license_count=len(tuple(record.get("licenses", ()) or ())),
        ))
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "title": f"Civic File: {record['name']}",
            "subtitle": f"Public record {int(record['eid'])}",
            "transcript": list(civic_person_record_lines(self.sim, record, viewer_eid=self.player_eid)),
            "topics": [{"id": "civic_records:people", "label": "Back to people index"}],
            "selected_index": 0,
            "scroll": 0,
            "hint": "This is the public file. Restricted details are not disclosed here.",
            "service_menu_mode": "civic_records:person",
            "civic_record_rows": [dict(row) for row in records],
        })

    def _open_civic_license_ledger(self, prop):
        state = self._dialog_ui_state()
        records = civic_people_records(self.sim, prop)
        authority = civic_records_authority(self.sim, prop)
        own_lines = civic_license_ledger_lines(self.sim, prop, subject_eid=self.player_eid, records=records)
        transcript = list(civic_license_ledger_lines(self.sim, prop, records=records))
        transcript.append("")
        transcript.append("Your filed credentials")
        transcript.extend(own_lines)
        self.sim.set_time_paused(True, reason="dialog")
        topics = [{"id": "civic_records:root", "label": "Back to civic records"}]
        for license_kind in ("hunting", "cultivation", "bounty"):
            active = civic_license_is_active(self.sim, self.player_eid, license_kind)
            fee = int(LICENSE_FEES[license_kind])
            label = f"{license_kind.title()} license — active" if active else f"Buy {license_kind} license — {fee}c"
            topics.append({"id": f"civic_records:license_buy|{license_kind}", "label": label})
        state.update({
            "title": f"Permit Ledger: {authority['authority_name']}",
            "subtitle": "Ecology, recovery, and civic credentials",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Licenses are identity-bound civic records, not lootable inventory cards.",
            "service_menu_mode": "civic_records:licenses",
            "civic_record_rows": [dict(row) for row in records],
        })

    def _open_civic_license_action(self, prop, license_kind, *, return_option="civic_records:licenses"):
        state = self._dialog_ui_state()
        result = purchase_civic_license(self.sim, self.player_eid, license_kind, prop=prop)
        kind_label = str(license_kind or "license").replace("_", " ").title()
        if result.get("ok"):
            lines = [
                f"{kind_label} issued for {int(result.get('fee', 0))}c.",
                f"The credential is now active in your civic file. Credits remaining {int(result.get('credits', 0))}c.",
                "The permission is tied to your identity and cannot be transferred by dropping or looting an item.",
            ]
        elif result.get("reason") == "already_active":
            lines = [f"Your {kind_label.lower()} is already active."]
        elif result.get("reason") == "no_credits":
            lines = [
                f"The {kind_label.lower()} costs {int(result.get('fee', 0))}c.",
                f"You currently have {int(result.get('credits', 0))}c.",
            ]
        elif result.get("reason") == "justice_hold":
            tier = str(result.get("wanted_tier", "active review") or "active review").replace("_", " ")
            lines = [
                f"The {kind_label.lower()} cannot be issued while your justice file reads {tier}.",
                "The recovery desk has left the application unfiled and charged nothing.",
            ]
        else:
            lines = ["That license cannot be issued at this counter."]
        state.update({
            "title": f"{kind_label} Counter",
            "subtitle": "Civic credential action",
            "transcript": lines,
            "topics": [{"id": str(return_option or "civic_records:licenses"), "label": "Back"}],
            "selected_index": 0,
            "scroll": 0,
            "hint": "The public permit ledger updates immediately after issuance.",
            "service_menu_mode": "civic_records:license_action",
        })

    def _open_civic_culls(self, prop):
        state = self._dialog_ui_state()
        lineage_rows = ecology_species_registry_rows(self.sim, "fauna")
        populations = {}
        for row in lineage_rows:
            population_key = str(row.get("population_key") or row.get("native_id") or "").strip()
            group = populations.setdefault(population_key, {**dict(row), "line_names": []})
            group["line_names"].append(str(row.get("name") or "local creature"))
        rows = tuple(populations.values())
        authority = civic_records_authority(self.sim, prop)
        topics = [{"id": "civic_records:root", "label": "Back to civic records"}]
        for row in rows:
            abundance = int(row.get("abundance", 100) or 0)
            status = str(row.get("population_status", "common") or "common").replace("_", " ")
            suffix = "declared this run" if row.get("cull_active_this_run") else f"{abundance}% {status}"
            topics.append({
                "id": f"civic_records:cull_review|{row['native_id']}",
                "label": f"{str(row.get('population_name') or row['name']).title()} — {suffix}",
            })
        transcript = [
            f"{authority['authority_name']} accepts one cull declaration per fauna species per run.",
            "A declaration lowers the whole species population by one 20-point tier; coat, pattern, and other micro-variations remain members of it.",
            "Five deliberate declarations across five distinct runs can end in extinction; the registry never treats repeated clicks as population history.",
        ]
        if not rows:
            transcript.append("No installation-native fauna species are registered for population policy yet.")
        state.update({
            "title": "Fauna Cull Declarations",
            "subtitle": f"{len(rows)} registered species population{'s' if len(rows) != 1 else ''}",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": f"An active hunting license and {FAUNA_CULL_FEE}c filing fee are required.",
            "service_menu_mode": "civic_records:culls",
            "ecology_registry_rows": [dict(row) for row in rows],
        })

    def _open_civic_cull_review(self, prop, native_id):
        state = self._dialog_ui_state()
        registry_rows = ecology_species_registry_rows(self.sim, "fauna")
        row = next((row for row in registry_rows if str(row.get("native_id")) == str(native_id)), None)
        if row is None:
            self._open_civic_culls(prop)
            return
        before = int(row.get("abundance", 100) or 0)
        after = max(0, before - 20)
        already = bool(row.get("cull_active_this_run"))
        related_lines = [
            candidate for candidate in registry_rows
            if str(candidate.get("population_key") or "") == str(row.get("population_key") or "")
        ]
        population_name = str(row.get("population_name") or row["name"]).replace("_", " ").strip().title()
        line_names = ", ".join(str(candidate.get("name") or "local line") for candidate in related_lines[:4])
        transcript = [
            f"Species population: {population_name}.",
            f"Known lines in this population: {line_names}.",
            f"Selected line appearance: {row['appearance']}.",
            f"Current population: {before}% ({str(row.get('population_status', 'common')).replace('_', ' ')}).",
        ]
        if before <= 0:
            transcript.append("This species is extinct. Its historical lines remain recorded, but no further cull can be declared.")
        elif already:
            transcript.append("A cull has already been declared for this species during this run.")
        else:
            transcript.extend([
                f"Declaration effect: {before}% -> {after}% installation abundance.",
                f"Filing fee: {FAUNA_CULL_FEE}c. This cannot be reversed inside the current run.",
                "The declaration authorizes licensed hunting across this species population for the current run; it does not excuse unsafe urban shots or unrelated offenses.",
            ])
        topics = [{"id": "civic_records:culls", "label": "Back to fauna culls"}]
        if before > 0 and not already:
            topics.append({"id": f"civic_records:cull_confirm|{row['native_id']}", "label": f"Confirm cull of {population_name}"})
        state.update({
            "title": f"Cull Review: {population_name}",
            "subtitle": "Durable installation policy",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Confirm only if you intend to alter this installation's future ecology.",
            "service_menu_mode": "civic_records:cull_review",
        })

    def _confirm_civic_cull(self, prop, native_id):
        state = self._dialog_ui_state()
        authority = civic_records_authority(self.sim, prop)
        result = initiate_fauna_cull(
            self.sim,
            native_id,
            actor_eid=self.player_eid,
            authority_name=authority.get("authority_name") or authority.get("office_name"),
            authority_key=authority.get("root_organization_key") or authority.get("organization_key"),
        )
        if result.get("ok"):
            lines = [
                f"Species cull declared from the {result.get('lineage_name', 'selected fauna')} record.",
                f"Installation abundance moved {int(result.get('before_abundance', 0))}% -> {int(result.get('after_abundance', 0))}% ({str(result.get('status', '')).replace('_', ' ')}).",
                f"Scarcity value is now x{float(result.get('value_multiplier', 1.0) or 1.0):g}; {int(result.get('fee', 0))}c filing fee paid.",
                "Licensed hunters may act under this declaration during the current run. The next population step requires a later run and a new declaration.",
            ]
        else:
            reason = str(result.get("reason", "unavailable") or "unavailable")
            if reason == "license_required":
                lines = ["An active hunting license is required before you can sponsor a cull declaration."]
            elif reason == "no_credits":
                lines = [f"The cull filing costs {int(result.get('fee', FAUNA_CULL_FEE))}c; you have {int(result.get('credits', 0))}c."]
            elif reason == "already_declared":
                lines = ["This fauna species has already moved one population tier during the current run."]
            elif reason == "extinct":
                lines = ["That fauna species is already extinct; only its historical registry remains."]
            else:
                lines = ["That cull declaration could not be filed."]
        state.update({
            "title": "Cull Declaration Result",
            "subtitle": authority.get("authority_name") or "Civic Authority",
            "transcript": lines,
            "topics": [{"id": "civic_records:culls", "label": "Back to fauna culls"}],
            "selected_index": 0,
            "scroll": 0,
            "hint": "Population and culling are species-level; line identity and pelt provenance remain more specific.",
            "service_menu_mode": "civic_records:cull_result",
        })

    def _open_bodyguard_contract_menu(self, prop):
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        prop_name = str(prop.get("name", prop.get("id", "Contractor Desk"))).strip() or "Contractor Desk"
        topics = [{"id": "service_menu:root", "label": "Back"}]
        targets = [("principal", str(self.player_eid), "Protect me")]
        pos = self._position_for(self.player_eid)
        for owned_prop in player_owned_businesses_for_actor(self.sim, self.player_eid, pos=pos):
            owned_id = str(owned_prop.get("id", "") or "").strip()
            if not owned_id:
                continue
            label = str(owned_prop.get("metadata", {}).get("business_name", owned_prop.get("name", owned_id))).strip() or owned_id
            targets.append(("property", owned_id, f"Protect {label}"))

        for target_kind, target_id, target_label in targets:
            summary_kwargs = {"assignment_kind": target_kind}
            if target_kind == "principal":
                summary_kwargs["principal_eid"] = self.player_eid
            else:
                summary_kwargs["property_id"] = target_id
            summary = bodyguard_channel_summary(self.sim, **summary_kwargs)
            active_count = int(summary.get("active_count", 0) or 0)
            available_slots = int(summary.get("available_slots", 0) or 0)
            for tier, profile in BODYGUARD_TIER_PROFILES.items():
                label = str(profile.get("label", tier)).strip().title()
                count = int(profile.get("count", 1) or 1)
                cost = int(profile.get("cost", 0) or 0)
                detail_note = f"detail {active_count}/{BODYGUARD_MAX_CHANNEL_GUARDS}"
                if active_count:
                    detail_note = f"add to detail {active_count}/{BODYGUARD_MAX_CHANNEL_GUARDS}"
                if count > available_slots:
                    detail_note = f"detail full {active_count}/{BODYGUARD_MAX_CHANNEL_GUARDS}"
                topics.append({
                    "id": f"{BODYGUARD_SERVICE_ID}:hire|{tier}|{target_kind}|{target_id}",
                    "label": f"{target_label}: {label} ({count} guard{'s' if count != 1 else ''}, {_credit_amount_label(cost)}, {detail_note})",
                })

        active = active_bodyguard_contracts(self.sim, hired_by_eid=self.player_eid)
        seen_channels = set()
        for _guard_eid, rec in active:
            channel_id = str(rec.get("protection_channel_id", "") or "").strip()
            if not channel_id or channel_id in seen_channels:
                continue
            seen_channels.add(channel_id)
            if str(rec.get("assignment_kind", "")).strip().lower() == "property":
                target_prop = self.sim.properties.get(rec.get("property_id"))
                target_name = str((target_prop or {}).get("metadata", {}).get("business_name", (target_prop or {}).get("name", "property"))).strip() or "property"
            else:
                target_name = "you"
            count = len(active_bodyguard_contracts(self.sim, hired_by_eid=self.player_eid, protection_channel_id=channel_id))
            topics.append({
                "id": f"{BODYGUARD_SERVICE_ID}:fire_channel|{channel_id}",
                "label": f"Release detail guarding {target_name} ({count} guard{'s' if count != 1 else ''})",
            })

        transcript = [
            f"{prop_name} posts protective contractors.",
            "They group by protected person or place: personal details hold outside walls, while owned-site details can post inside the business.",
            "They choose their own force if a threat presses.",
        ]
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"Bodyguards: {prop_name}",
            "subtitle": "One-time fee | independent force",
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Add guards to a protected detail or release the whole detail.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": BODYGUARD_SERVICE_ID,
            "casino_session": None,
        })

    def _close_service_menu(self):
        self._clear_pending_service_result()
        self._clear_casino_session()
        state = self._dialog_ui_state()
        self.sim.set_time_paused(False, reason="dialog")
        state.update({
            "open": False,
            "kind": "conversation",
            "npc_eid": None,
            "property_id": None,
            "title": "Conversation",
            "subtitle": "",
            "transcript": [],
            "topics": [],
            "selected_index": 0,
            "scroll": 0,
            "hint": "",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "root",
            "casino_session": None,
        })

    def _dismiss_service_menu_for_started_service(self):
        self._clear_casino_session()
        state = self._dialog_ui_state()
        self.sim.set_time_paused(False, reason="dialog")
        state.update({
            "open": False,
            "kind": "conversation",
            "npc_eid": None,
            "property_id": None,
            "title": "Conversation",
            "subtitle": "",
            "transcript": [],
            "topics": [],
            "selected_index": 0,
            "scroll": 0,
            "hint": "",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "root",
            "casino_session": None,
        })

    def _begin_pending_service_result(self, *, channel, property_id, property_name, service=""):
        self.pending_service_result = {
            "channel": str(channel or "").strip().lower(),
            "eid": self.player_eid,
            "property_id": property_id,
            "property_name": str(property_name or "").strip(),
            "service": str(service or "").strip().lower(),
        }

    def _event_matches_pending(self, event, *, channel, service=None):
        pending = self.pending_service_result
        if not isinstance(pending, dict):
            return False
        if str(pending.get("channel", "")).strip().lower() != str(channel or "").strip().lower():
            return False
        if event.data.get("eid") != pending.get("eid"):
            return False

        pending_property_id = pending.get("property_id")
        event_property_id = event.data.get("property_id")
        if pending_property_id is not None and event_property_id is not None and event_property_id != pending_property_id:
            return False

        expected_service = str(service if service is not None else pending.get("service", "")).strip().lower()
        if expected_service:
            event_service = str(event.data.get("service", "") or "").strip().lower()
            if event_service and event_service != expected_service:
                return False
        return True

    def _site_service_result_lines(self, event):
        service = str(event.data.get("service", "")).strip().lower()
        prop_name = str(event.data.get("property_name", self._pending_property_name("Service"))).strip() or self._pending_property_name("Service")
        if service in CASINO_GAME_SERVICE_IDS:
            wager = int(event.data.get("wager", 0))
            stake = int(event.data.get("stake", wager))
            payout = int(event.data.get("payout", 0))
            net_credits = int(event.data.get("net_credits", payout - stake))
            credits_after = int(event.data.get("credits_after", 0))
            social_gain = int(event.data.get("social_gain", 0))
            detail = str(event.data.get("detail", "")).strip()
            headline = str(event.data.get("headline", "")).strip() or f"You play {_site_service_label(service)}."
            lines = [
                str(line).strip()
                for line in list(event.data.get("result_lines", ()) or ())
                if str(line).strip()
            ]
            context = event.data.get("table_context_summary")
            if not isinstance(context, dict):
                context = event.data.get("table_context")
            table_read = str((context or {}).get("table_read", "") if isinstance(context, dict) else "").strip()
            if table_read and table_read.lower() not in {line.lower() for line in lines}:
                lines.insert(0, table_read)
            if not lines:
                lines = [detail or headline]
            lines.append(
                f"Stake {_credit_amount_label(stake)} | payout {_credit_amount_label(payout)} | "
                f"net {net_credits:+d}c | wallet {_credit_amount_label(credits_after)}."
            )
            if social_gain > 0:
                lines.append(f"The room livens you up a bit (So +{social_gain}).")
            return f"{_casino_game_title(service)}: {prop_name}", lines
        if service == "fuel":
            fuel_gain = int(event.data.get("fuel_gain", 0))
            credits_spent = int(event.data.get("credits_spent", 0))
            base_credits_spent = int(event.data.get("base_credits_spent", credits_spent))
            fuel = int(event.data.get("fuel", 0))
            fuel_capacity = int(event.data.get("fuel_capacity", 0))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            skill_note = _sentence_from_note(event.data.get("skill_note", ""))
            lines = [
                f"{prop_name} refuels {vehicle_name}.",
                f"+{fuel_gain} fuel for {_credit_amount_label(credits_spent)}.",
            ]
            if base_credits_spent > credits_spent:
                lines.append(f"Quoted down from {_credit_amount_label(base_credits_spent)}.")
            if skill_note:
                lines.append(skill_note)
            if fuel_capacity > 0:
                lines.append(f"Tank {fuel}/{fuel_capacity}.")
            return f"Fuel: {prop_name}", lines
        if service == "fuel_fill_bottle":
            credits_spent = int(event.data.get("credits_spent", 0))
            output_name = str(event.data.get("output_item_name", "Molotov Cocktail")).strip() or "Molotov Cocktail"
            lines = [
                f"{prop_name} fills a glass bottle with fuel.",
                f"You receive {output_name} for {_credit_amount_label(credits_spent)}.",
            ]
            return f"Fuel: {prop_name}", lines
        if service == "repair":
            durability_gain = int(event.data.get("durability_gain", 0))
            durability = int(event.data.get("durability", 0))
            durability_max = int(event.data.get("durability_max", 10))
            credits_spent = int(event.data.get("credits_spent", 0))
            base_credits_spent = int(event.data.get("base_credits_spent", credits_spent))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            skill_note = _sentence_from_note(event.data.get("skill_note", ""))
            lines = [
                f"{prop_name} patches up {vehicle_name}.",
                f"+{durability_gain} durability for {_credit_amount_label(credits_spent)}.",
            ]
            if base_credits_spent > credits_spent:
                lines.append(f"Quoted down from {_credit_amount_label(base_credits_spent)}.")
            if skill_note:
                lines.append(skill_note)
            lines.append(f"Condition {durability}/{durability_max}.")
            return f"Repair: {prop_name}", lines
        if service == "building_repair":
            target_name = str(event.data.get("target_property_name", "building")).strip() or "building"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            window_count = int(event.data.get("window_count", 0) or 0)
            door_count = int(event.data.get("door_count", 0) or 0)
            wall_count = int(event.data.get("wall_count", 0) or 0)
            bits = []
            if window_count > 0:
                bits.append(f"{window_count} window")
            if door_count > 0:
                bits.append(f"{door_count} door")
            if wall_count > 0:
                bits.append(f"{wall_count} wall")
            lines = [
                f"{prop_name} sends a contractor crew to {target_name}.",
                f"Shell repair cost {_credit_amount_label(credits_spent)}.",
            ]
            if bits:
                lines.append(f"Restored: {', '.join(bits)}.")
            return f"Building Repair: {prop_name}", lines
        if service == "business_remodel":
            target_name = str(event.data.get("target_property_name", "business")).strip() or "business"
            target_label = str(event.data.get("target_label", "New Business")).strip() or "New Business"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            rarity_label = str(event.data.get("rarity_label", "")).strip().lower()
            site_services = [
                _site_service_label(service_id)
                for service_id in tuple(event.data.get("site_services", ()) or ())
                if str(service_id).strip()
            ]
            finance_services = [str(service_id).strip().lower() for service_id in tuple(event.data.get("finance_services", ()) or ()) if str(service_id).strip()]
            lines = [
                f"{target_name} is now fitted as {target_label}.",
                f"Contractor cost {_credit_amount_label(credits_spent)}.",
            ]
            if rarity_label:
                lines.append(f"Target rarity: {rarity_label}.")
            if site_services or finance_services:
                services_text = ", ".join(site_services + finance_services)
                lines.append(f"Service profile: {services_text}.")
            return f"Business Refit: {prop_name}", lines
        if service == BODYGUARD_SERVICE_ID:
            action = str(event.data.get("bodyguard_action", "hire") or "hire").strip().lower()
            if action == "fire":
                count = int(event.data.get("guard_count", 0) or 0)
                lines = [
                    f"Released {count} bodyguard{'s' if count != 1 else ''}.",
                    "They are no longer under contract and will not hold the perimeter for you.",
                ]
                return f"Bodyguards: {prop_name}", lines
            tier_label = str(event.data.get("tier_label", "bodyguard detail")).strip() or "bodyguard detail"
            target_name = str(event.data.get("target_name", "the assignment")).strip() or "the assignment"
            count = int(event.data.get("guard_count", 0) or 0)
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            active_count = int(event.data.get("active_guard_count", count) or count)
            lines = [
                f"{prop_name} assigns a {tier_label} to {target_name}.",
                f"{count} guard{'s' if count != 1 else ''} contracted for {_credit_amount_label(credits_spent)}; detail strength is now {active_count}/{BODYGUARD_MAX_CHANNEL_GUARDS}.",
                "They sort into close, outer, and perimeter rings, warn from the close line, and answer shared threat calls.",
            ]
            return f"Bodyguards: {prop_name}", lines
        if service in CULT_SERVICE_IDS:
            lines = [
                str(line).strip()
                for line in tuple(event.data.get("lines", ()) or event.data.get("result_lines", ()) or ())
                if str(line).strip()
            ]
            if not lines:
                lines = [f"{prop_name} handles the circle request."]
            cult_name = str(event.data.get("cult_name", "") or "").strip()
            return f"{_site_service_label(service).title()}: {cult_name or prop_name}", lines
        if service == "vending":
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            credits_spent = int(event.data.get("credits_spent", 0))
            return f"Vending: {prop_name}", [
                f"Bought {item_name} for {_credit_amount_label(credits_spent)}.",
                f"{item_name} drops into your bag.",
            ]
        if service == "herbal_care":
            hp_gain = int(event.data.get("hp_gain", 0))
            hunger_gain = int(event.data.get("hunger_gain", 0))
            thirst_gain = int(event.data.get("thirst_gain", 0))
            credits_spent = int(event.data.get("credits_spent", 0))
            gain_bits = []
            if hp_gain > 0:
                gain_bits.append(f"HP +{hp_gain}")
            if hunger_gain > 0:
                gain_bits.append(f"food +{hunger_gain}")
            if thirst_gain > 0:
                gain_bits.append(f"water +{thirst_gain}")
            lines = [
                f"{prop_name} mixes a quick restorative for {_credit_amount_label(credits_spent)}.",
                " ".join(gain_bits) if gain_bits else "You come away steadier.",
            ]
            practice_note = _sentence_from_note(event.data.get("practice_note", ""))
            if practice_note:
                lines.append(practice_note)
            return f"Herbal Care: {prop_name}", lines
        if service in {"herbal_prepare", "herbal_compound", "campfire_herbal_recipe", "campfire_herbal_mix"}:
            output_name = str(event.data.get("output_item_name", "herbal medicine")).strip() or "herbal medicine"
            recipe_name = str(event.data.get("recipe_name", "recipe")).strip() or "recipe"
            ingredient_count = int(event.data.get("ingredient_count", 0) or 0)
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            experiment_result = str(event.data.get("experiment_result", "") or "").strip().lower()
            if service == "herbal_prepare":
                title = "Herbal Prep"
            elif service == "campfire_herbal_recipe":
                title = "Campfire Recipe"
            elif service == "campfire_herbal_mix":
                title = "Campfire Mixing"
            else:
                title = "Herbal Compounding"
            first = (
                f"{prop_name} prepares {output_name} from {ingredient_count} plant material{'s' if ingredient_count != 1 else ''}."
                if service == "herbal_prepare"
                else f"You compound {output_name} from {ingredient_count} plant material{'s' if ingredient_count != 1 else ''}."
            )
            lines = [first, f"Recipe: {recipe_name}."]
            if credits_spent > 0:
                lines.append(f"Fee {_credit_amount_label(credits_spent)}.")
            if bool(event.data.get("mortar_prepared")):
                lines.append("The mortar-ground preparation is good quality.")
            if experiment_result in {"diluted", "weak_toxic", "odd"}:
                if experiment_result == "diluted":
                    lines.append("The result is weaker than the recipe you were reaching for.")
                elif experiment_result == "weak_toxic":
                    lines.append("The result carries a weak toxic edge.")
                else:
                    lines.append("The result is odd and not trusted stock.")
            elif experiment_result == "useful":
                lines.append("The traits held together into a useful, unfamiliar blend.")
            else:
                if bool(event.data.get("discovered_recipe")):
                    lines.append("You worked out the recipe from the mix.")
                lines.append(f"{output_name} is now identified for you.")
            return f"{title}: {prop_name}", lines
        if service == "herbal_recipe_sales":
            recipe_name = str(event.data.get("recipe_name", "herbal recipe")).strip() or "herbal recipe"
            output_name = str(event.data.get("output_item_name", "herbal medicine")).strip() or "herbal medicine"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            revealed = tuple(event.data.get("revealed_plants", ()) or ())
            lines = [
                f"You learned {recipe_name} for {_credit_amount_label(credits_spent)}.",
                f"It teaches how to make {output_name}.",
            ]
            if revealed:
                names = []
                for row in revealed[:3]:
                    if isinstance(row, dict):
                        name = str(row.get("plant_name") or row.get("plant_id") or "").strip()
                        class_id = str(row.get("chemistry_class") or "").replace("_", " ").strip()
                        trait_labels = secondary_trait_labels(row.get("secondary_traits", ()))
                        trait_text = f" {' '.join(trait_labels)}" if trait_labels else ""
                        if name and class_id:
                            names.append(f"{name}: {class_id}{trait_text}")
                if names:
                    lines.append("Known plant affinities: " + "; ".join(names) + ".")
            return f"Herbal Recipe: {prop_name}", lines
        if service == "campfire_cook":
            input_units = int(event.data.get("input_units", 0) or 0)
            output_units = int(event.data.get("output_units", 0) or 0)
            output_item_name = str(event.data.get("output_item_name", "cooked meat")).strip() or "cooked meat"
            return f"Campfire Cooking: {prop_name}", [
                f"You cook {input_units} raw meat into {output_units} {output_item_name}.",
                "The campfire method is rough, but the result is pack-ready food.",
            ]
        if service == "butcher_prepare":
            input_units = int(event.data.get("input_units", 0) or 0)
            output_units = int(event.data.get("output_units", 0) or 0)
            output_item_name = str(event.data.get("output_item_name", "packaged meat")).strip() or "packaged meat"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            return f"Butcher Prep: {prop_name}", [
                f"{prop_name} prepares {input_units} raw meat into {output_units} {output_item_name}.",
                f"Fee {_credit_amount_label(credits_spent)}.",
            ]
        if service in {"vehicle_sales_new", "vehicle_sales_used"}:
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            price = int(event.data.get("price", 0))
            base_price = int(event.data.get("base_price", price))
            quality = "new" if service == "vehicle_sales_new" else "used"
            skill_note = _sentence_from_note(event.data.get("skill_note", ""))
            lines = [
                f"Purchased {vehicle_name}.",
                f"{quality.title()} unit for {_credit_amount_label(price)}.",
            ]
            if base_price > price:
                lines.append(f"Quoted down from {_credit_amount_label(base_price)}.")
            stats = _vehicle_sale_stats_text(event.data)
            if stats:
                lines.append(stats + ".")
            if bool(event.data.get("key_issued", False)):
                lines.append("A key was issued with the vehicle.")
            if skill_note:
                lines.append(skill_note)
            return f"Vehicles: {prop_name}", lines
        if service == "shelter":
            hp_gain = int(event.data.get("hp_gain", 0))
            energy_gain = int(event.data.get("energy_gain", 0))
            safety_gain = int(event.data.get("safety_gain", 0))
            social_gain = int(event.data.get("social_gain", 0))
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0))
            interrupted = bool(event.data.get("interrupted"))
            interruption_reason = str(event.data.get("interruption_reason", "") or "").strip().lower()
            wake_cause = str(event.data.get("wake_cause", "") or "").strip().lower()
            gain_bits = []
            if hp_gain > 0:
                gain_bits.append(f"HP +{hp_gain}")
            if energy_gain > 0:
                gain_bits.append(f"E +{energy_gain}")
            if safety_gain > 0:
                gain_bits.append(f"S +{safety_gain}")
            if social_gain > 0:
                gain_bits.append(f"So +{social_gain}")
            if interrupted:
                lines = [f"{prop_name} gives you a safe place to steady up, but the stay is cut short."]
            else:
                lines = [f"{prop_name} gives you a safe place to steady up."]
            lines.append(" ".join(gain_bits) if gain_bits else "You settle yourself and recover a little.")
            if time_advanced_ticks > 0:
                duration_line = f"You lay low for {_tick_duration_label(self.sim, time_advanced_ticks)}."
                if interrupted:
                    duration_line = f"You only manage {_tick_duration_label(self.sim, time_advanced_ticks)} before it breaks."
                lines.append(duration_line)
            if interrupted:
                if interruption_reason == "woken_by_noise" and wake_cause:
                    lines.append(f"Nearby {wake_cause.replace('_', ' ')} wakes you.")
                elif interruption_reason in {"justice_surrender", "justice_questioning", "justice_identity_check", "justice_case_canvas", "actor_detained", "justice_booking_completed"}:
                    lines.append("Justice reaches you before you can finish laying low.")
                else:
                    lines.append("Danger reaches you before you can finish laying low.")
            return f"Shelter: {prop_name}", lines
        if service == "rest":
            hp_gain = int(event.data.get("hp_gain", 0))
            energy_gain = int(event.data.get("energy_gain", 0))
            safety_gain = int(event.data.get("safety_gain", 0))
            social_gain = int(event.data.get("social_gain", 0))
            credits_spent = int(event.data.get("credits_spent", 0))
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0))
            interrupted = bool(event.data.get("interrupted"))
            interruption_reason = str(event.data.get("interruption_reason", "") or "").strip().lower()
            wake_cause = str(event.data.get("wake_cause", "") or "").strip().lower()
            well_rested_granted = bool(event.data.get("well_rested_granted"))
            gain_bits = []
            if hp_gain > 0:
                gain_bits.append(f"HP +{hp_gain}")
            if energy_gain > 0:
                gain_bits.append(f"E +{energy_gain}")
            if safety_gain > 0:
                gain_bits.append(f"S +{safety_gain}")
            if social_gain > 0:
                gain_bits.append(f"So +{social_gain}")
            lines = [f"Room rented for {_credit_amount_label(credits_spent)}."]
            lines.append(" ".join(gain_bits) if gain_bits else "You come away better rested.")
            if time_advanced_ticks > 0:
                duration_line = f"You sleep through {_tick_duration_label(self.sim, time_advanced_ticks)}."
                if interrupted:
                    duration_line = f"You only get {_tick_duration_label(self.sim, time_advanced_ticks)} before waking."
                lines.append(duration_line)
            if interrupted:
                if interruption_reason == "woken_by_noise" and wake_cause:
                    lines.append(f"Nearby {wake_cause.replace('_', ' ')} wakes you.")
                elif interruption_reason in {"justice_surrender", "justice_questioning", "justice_identity_check", "justice_case_canvas", "actor_detained", "justice_booking_completed"}:
                    lines.append("Justice reaches you before you can finish the room stay.")
                else:
                    lines.append("Danger reaches you before the room stay can finish.")
            elif well_rested_granted:
                lines.append("You wake up well rested.")
            return f"Rest: {prop_name}", lines
        if service in TRANSIT_SERVICE_IDS:
            profile = _transit_service_profile(service) or {}
            title = _transit_service_title(service)
            destination_name = str(event.data.get("destination_name", "the next stop")).strip() or "the next stop"
            distance = int(event.data.get("distance", 0) or 0)
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0) or 0)
            fare_mode = str(event.data.get("fare_mode", "credits")).strip().lower() or "credits"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            token_cost = int(event.data.get("token_cost", 0) or 0)
            skill_note = _sentence_from_note(event.data.get("skill_note", ""))
            success_lines = tuple(profile.get("success_lines", ()) or ())
            if len(success_lines) >= 2:
                lines = [
                    str(success_lines[0]).format(
                        prop_name=prop_name,
                        destination_name=destination_name,
                        distance=max(1, distance),
                    ),
                    str(success_lines[1]).format(
                        prop_name=prop_name,
                        destination_name=destination_name,
                        distance=max(1, distance),
                    ),
                ]
            else:
                lines = [
                    f"You travel out from {prop_name} and arrive at {destination_name}.",
                    f"{max(1, distance)} chunks by {_site_service_label(service)}.",
                ]
            if fare_mode == "transit_daypass":
                lines.append("You ride on a transit daypass.")
            elif fare_mode == "city_pass_token":
                lines.append(f"Fare {_transit_fare_label(service, fare_mode=fare_mode, token_cost=token_cost)}.")
            else:
                lines.append(f"Fare {_credit_amount_label(credits_spent)}.")
            if time_advanced_ticks > 0:
                lines.append(f"Travel time {_tick_duration_label(self.sim, time_advanced_ticks)}.")
            if skill_note:
                lines.append(skill_note)
            return f"{title}: {prop_name}", lines
        if service == "vehicle_fetch":
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            credits_spent = int(event.data.get("credits_spent", 0))
            base_credits_spent = int(event.data.get("base_credits_spent", credits_spent))
            skill_note = _sentence_from_note(event.data.get("skill_note", ""))
            lines = [
                f"{prop_name} sends a runner for your {vehicle_name}.",
                f"Fee: {_credit_amount_label(credits_spent)}.",
            ]
            if base_credits_spent > credits_spent:
                lines.append(f"Quoted down from {_credit_amount_label(base_credits_spent)}.")
            if skill_note:
                lines.append(skill_note)
            return f"Fetch: {prop_name}", [
                line for line in lines
            ]
        headline = str(event.data.get("headline", "") or "").strip()
        explicit_lines = [
            str(line).strip()
            for line in tuple(event.data.get("lines", ()) or ())
            if str(line).strip()
        ]
        if headline or explicit_lines:
            return f"{_site_service_label(service).title()}: {prop_name}", explicit_lines or [headline]
        return f"Service: {prop_name}", [f"{prop_name} provides {_site_service_label(service)}."]

    def _stale_service_option_lines(self, option_id):
        option_id = str(option_id or "").strip().lower()
        for service in TRANSIT_SERVICE_IDS:
            if option_id == service:
                title = _transit_service_title(service)
                service_name = str(title or "transit").strip().lower() or "transit"
                return title, [f"No active {service_name} departures are posted here."]
            if option_id.startswith(f"{service}:dest:"):
                title = _transit_service_title(service)
                return title, ["That departure is no longer posted here.", "Pick a fresh stop from the board."]
        if option_id in {"vehicle_sales_new", "vehicle_sales_used"}:
            return "Vehicles", ["Vehicle sales are no longer being offered here."]
        if option_id.startswith("vehicle_sales_new:offer:") or option_id.startswith("vehicle_sales_used:offer:"):
            return "Vehicles", ["That vehicle listing is no longer on the lot."]
        if option_id.startswith("banking_business_status:"):
            return "Business status", ["That business record is no longer available through this terminal."]
        if option_id.startswith("banking_business_policy:"):
            return "Business policy", ["That business record is no longer available through this terminal."]
        if option_id.startswith("banking_business_hours:"):
            return "Business hours", ["That business record is no longer available through this terminal."]
        if option_id.startswith("banking_business_markup:"):
            return "Business markup", ["That business record is no longer available through this terminal."]
        if option_id.startswith("banking_business_employees:") or option_id.startswith("banking_business_wage:"):
            return "Business employees", ["That employee wage record is no longer available through this terminal."]
        if option_id == "business_management":
            return "Business Desk", ["That business desk is no longer available here."]
        if option_id.startswith("business_control_status:"):
            return "Business status", ["That business record is no longer available through this desk."]
        if option_id.startswith("business_control_deposit:") or option_id.startswith("business_control_withdraw:"):
            return "Business funds", ["That business fund transfer is no longer available through this desk."]
        if option_id.startswith("business_control_policy:"):
            return "Business policy", ["That business record is no longer available through this desk."]
        if option_id.startswith("business_control_hours:"):
            return "Business hours", ["That business record is no longer available through this desk."]
        if option_id.startswith("business_control_markup:"):
            return "Business markup", ["That business record is no longer available through this desk."]
        if option_id.startswith("business_control_employees:") or option_id.startswith("business_control_wage:"):
            return "Business employees", ["That employee wage record is no longer available through this desk."]
        if option_id == "redeem_meal_voucher":
            return "Meal Voucher", ["That meal voucher counter is no longer available here."]
        if option_id == "rest" or option_id.startswith("rest:stay:"):
            return "Room", ["That room desk is no longer available here."]
        if option_id == "building_repair" or option_id.startswith("building_repair:target|"):
            return "Building Repair", ["That contractor quote is no longer available here."]
        if option_id == "business_remodel" or option_id.startswith("business_remodel:"):
            return "Business Refit", ["That contractor quote is no longer available here."]
        if option_id == "appearance_style" or option_id.startswith("appearance_style:"):
            return "Styling", ["That styling option is no longer available here."]
        for service in CASINO_GAME_SERVICE_IDS:
            if option_id == service or option_id.startswith(f"{service}:"):
                return _casino_game_title(service), ["That table is no longer open.", "Pick another seat or start a fresh round."]
        return "Service", ["That service listing is no longer available here."]

    def _business_control_prefix_and_action(self, option_id):
        option_id = str(option_id or "").strip().lower()
        for prefix in ("business_control", "banking_business"):
            for action in ("status", "deposit", "withdraw", "policy", "hours", "markup", "employees", "wage"):
                marker = f"{prefix}_{action}:"
                if option_id.startswith(marker):
                    return prefix, action, option_id[len(marker):]
        return "", "", ""

    def _business_control_employee_back_id(self, prefix, state):
        prefix = str(prefix or "").strip().lower()
        if prefix == "banking_business":
            return "banking"
        mode = str((state or {}).get("service_menu_mode", "") or "").strip().lower()
        if mode == "business:employees":
            return str((state or {}).get("business_employee_back_id", "") or "business_management").strip() or "business_management"
        if mode == "business:management":
            return "business_management"
        return "service_menu:root"

    def _handle_business_control_option(self, provider_prop, option_id, state):
        prefix, action, payload = self._business_control_prefix_and_action(option_id)
        if not prefix or not action:
            return False
        provider_id = (provider_prop or {}).get("id") if isinstance(provider_prop, dict) else None
        parts = str(payload or "").split(":")
        business_property_id = str(parts[0] if parts else "").strip()
        if not business_property_id:
            self._present_service_result("Business", ["That business option is invalid."], property_id=provider_id)
            return True
        business_prop = _resolve_property_record(self.sim, business_property_id)
        if not isinstance(business_prop, dict):
            title, lines = self._stale_service_option_lines(option_id)
            self._present_service_result(title, lines, property_id=provider_id)
            return True
        business_name = str(business_prop.get("metadata", {}).get("business_name", business_prop.get("name", "Business"))).strip() or "Business"

        if action == "status":
            lines = self._business_status_lines({"prop": business_prop})
            self._present_service_result(
                f"Business status: {business_name}",
                lines or ["No business status is available right now."],
                property_id=provider_id,
            )
            return True

        if action in {"deposit", "withdraw"}:
            amount = _int_or_default(parts[1] if len(parts) >= 2 else 0, 0)
            if amount <= 0:
                self._present_service_result("Business funds", ["That transfer amount is invalid."], property_id=provider_id)
                return True
            self._begin_pending_service_result(
                channel="banking",
                property_id=provider_id,
                property_name=(provider_prop or {}).get("name", provider_id) if isinstance(provider_prop, dict) else provider_id,
                service="banking",
            )
            self.sim.emit(Event(
                "finance_service_request",
                eid=self.player_eid,
                property_id=provider_id,
                service="banking",
                kind=action,
                amount=amount,
                account_kind="business",
                business_property_id=business_property_id,
                local_business_transfer=True,
            ))
            return True

        if action == "employees":
            self._open_business_employee_menu(
                provider_prop,
                business_prop,
                prefix=prefix,
                return_option_id=self._business_control_employee_back_id(prefix, state),
            )
            return True

        if action == "policy":
            next_policy = str(parts[1] if len(parts) >= 2 else "").strip().lower()
            if not next_policy:
                self._present_service_result("Business policy", ["That business policy option is invalid."], property_id=provider_id)
                return True
            policy = player_business_set_customer_policy(business_prop, next_policy, sim=self.sim)
            self._present_service_result(
                f"Business policy: {business_name}",
                self._business_policy_result_lines(business_prop, policy),
                property_id=provider_id,
            )
            return True

        if action == "hours":
            next_mode = str(parts[1] if len(parts) >= 2 else "").strip().lower()
            if not next_mode:
                self._present_service_result("Business hours", ["That business hours option is invalid."], property_id=provider_id)
                return True
            result = player_business_set_hours_mode(self.sim, business_prop, next_mode)
            self._present_service_result(
                f"Business hours: {business_name}",
                self._business_hours_result_lines(business_prop, result),
                property_id=provider_id,
            )
            return True

        if action == "markup":
            next_mode = str(parts[1] if len(parts) >= 2 else "").strip().lower()
            if not next_mode:
                self._present_service_result("Business markup", ["That business markup option is invalid."], property_id=provider_id)
                return True
            mode = player_business_set_markup_mode(business_prop, next_mode, sim=self.sim)
            self._present_service_result(
                f"Business markup: {business_name}",
                self._business_markup_result_lines(business_prop, mode),
                property_id=provider_id,
            )
            return True

        if action == "wage":
            if len(parts) < 3:
                self._present_service_result("Business wages", ["That wage option is invalid."], property_id=provider_id)
                return True
            actor_eid = _int_or_default(parts[1], 0)
            next_level = str(parts[2] or "").strip().lower()
            level = player_business_set_employee_wage_level(business_prop, actor_eid, next_level, sim=self.sim)
            if not level:
                self._present_service_result("Business wages", ["That employee is no longer on this business roster."], property_id=provider_id)
                return True
            self._open_business_employee_menu(
                provider_prop,
                business_prop,
                prefix=prefix,
                return_option_id=self._business_control_employee_back_id(prefix, state),
            )
            transcript = list(self.sim.dialog_ui.get("transcript", ()) or ())
            transcript.append(f"{business_name} wage level updated to {player_business_employee_wage_level_label(level)}.")
            self.sim.dialog_ui["transcript"] = transcript
            return True

        return False

    def _site_service_blocked_lines(self, event):
        service = str(event.data.get("service", "")).strip().lower()
        prop_name = str(event.data.get("property_name", self._pending_property_name("Service"))).strip() or self._pending_property_name("Service")
        reason = str(event.data.get("reason", "blocked")).strip().lower()
        title = f"{_casino_game_title(service)}: {prop_name}" if service in CASINO_GAME_SERVICE_IDS else f"Service: {prop_name}"
        event_lines = [
            str(line).strip()
            for line in tuple(event.data.get("lines", ()) or ())
            if str(line).strip()
        ]
        if event_lines and service in SERVICE_JOB_BOARD_SERVICES:
            return f"Jobs: {prop_name}", event_lines
        if reason == "invalid_wager" and service in CASINO_GAME_SERVICE_IDS:
            return f"{_casino_game_title(service)}: {prop_name}", ["The house refuses that stake.", "Choose one of the posted wager sizes."]
        if reason == "invalid_round" and service in CASINO_GAME_SERVICE_IDS:
            return title, ["That round lost sync with the table.", "Start a fresh round."]
        if reason == "cooldown":
            ready_in = int(event.data.get("ready_in", 0))
            return title, [f"{_site_service_label(service).title()} is not available again yet.", f"Ready in {ready_in}t."]
        if service in TRANSIT_SERVICE_IDS and reason == "no_destinations":
            profile = _transit_service_profile(service) or {}
            title = _transit_service_title(service)
            line = str(
                profile.get("no_destinations_line", "No outbound transit service is posted from {prop_name} right now.")
            ).format(prop_name=prop_name)
            return f"{title}: {prop_name}", [line]
        if service in TRANSIT_SERVICE_IDS and reason == "invalid_destination":
            profile = _transit_service_profile(service) or {}
            title = _transit_service_title(service)
            lines = [
                str(line).strip()
                for line in tuple(profile.get("invalid_destination_lines", ()) or ())
                if str(line).strip()
            ]
            if not lines:
                lines = ["That transit departure changed before you boarded.", "Pick a fresh stop from the board."]
            return f"{title}: {prop_name}", lines
        if service in TRANSIT_SERVICE_IDS and reason == "leave_vehicle":
            profile = _transit_service_profile(service) or {}
            title = _transit_service_title(service)
            lines = [
                str(line).strip()
                for line in tuple(profile.get("leave_vehicle_lines", ()) or ())
                if str(line).strip()
            ]
            if not lines:
                lines = ["Leave your vehicle before boarding transit.", "Transit is stop to stop, not car to stop."]
            return f"{title}: {prop_name}", lines
        if reason == "no_need" and service == "shelter":
            return title, [f"You do not need shelter at {prop_name} right now."]
        if reason == "no_need" and service == "herbal_care":
            return f"Herbal Care: {prop_name}", [f"You do not need restorative care at {prop_name} right now."]
        herbal_craft_services = {"herbal_prepare", "herbal_compound", "campfire_herbal_recipe", "campfire_herbal_mix"}
        if reason == "no_recipe" and service in herbal_craft_services:
            return title, ["You need to learn an herbal recipe before this prep makes sense.", "Herbalists can sell recipes."]
        if reason == "no_local_recipe" and service in {"herbal_prepare", "herbal_recipe_sales"}:
            return f"Herbal Recipe: {prop_name}", [f"{prop_name} has no unfamiliar recipe supported by the plants growing in this chunk."]
        if reason == "no_ingredients" and service in herbal_craft_services:
            if service in {"campfire_herbal_recipe", "campfire_herbal_mix"}:
                return title, ["The campfire herb cache needs 2-3 harvested plant materials.", "Open the herb cache and load the plants first."]
            return title, ["You do not have the known plant materials for any learned recipe.", "Harvest herbs, then learn which plants carry the needed affinities."]
        if reason == "no_matching_recipe" and service == "campfire_herbal_recipe":
            return title, ["Those cached herbs do not match any recipe you know.", "Use free-mix cached herbs if you want to experiment."]
        if reason == "invalid_mix" and service in herbal_craft_services:
            return title, ["Those plant materials do not satisfy the recipe.", "Nothing was consumed."]
        if reason == "no_tool" and service == "herbal_compound":
            return title, ["You need a mortar kit to compound herbs away from a campfire ring."]
        if reason == "all_known" and service == "herbal_recipe_sales":
            return f"Herbal Recipe: {prop_name}", ["You already know the recipes this herbalist is selling."]
        if reason == "no_meat" and service == "campfire_cook":
            return f"Campfire Cooking: {prop_name}", ["You need raw or bagged game meat to cook here."]
        if reason == "no_meat" and service == "butcher_prepare":
            return f"Butcher Prep: {prop_name}", ["Bring raw or bagged game meat for the butcher to prepare."]
        if reason == "uncertified_meat" and service == "butcher_prepare":
            animal_name = str(event.data.get("animal_name", "game") or "game").strip()
            grade = str(event.data.get("inspection_grade", "uncertified") or "uncertified").replace("_", " ").strip()
            return f"Butcher Prep: {prop_name}", [
                f"The counter refuses the {animal_name}: its harvest record reads {grade}.",
                "Clean butchers require a verified hunting permit and lawful hunt provenance; off-book buyers may still take the risk.",
            ]
        if reason == "no_leads" and service == "intel":
            return f"Intel: {prop_name}", [f"{prop_name} has no fresh routes or leads right now."]
        if reason == "no_bottle" and service == "fuel_fill_bottle":
            return f"Fuel: {prop_name}", ["You need a glass bottle to fill with fuel."]
        if reason == "no_vehicle" and service == "fuel":
            return f"Fuel: {prop_name}", [f"{prop_name} can only refuel a vehicle you own or have set active."]
        if reason == "no_vehicle" and service == "repair":
            return f"Repair: {prop_name}", [f"{prop_name} can only work on a vehicle you own or have set active."]
        if reason == "invalid_target" and service == "building_repair":
            return f"Building Repair: {prop_name}", ["That owned-building repair target is no longer valid."]
        if reason == "invalid_target" and service == "business_remodel":
            return f"Business Refit: {prop_name}", ["That business refit target is no longer valid."]
        if reason == "no_damage" and service == "building_repair":
            target_name = str(event.data.get("target_property_name", "building")).strip() or "building"
            return f"Building Repair: {prop_name}", [f"{target_name} does not currently need shell repair."]
        if reason == "tank_full" and service == "fuel":
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            fuel = int(event.data.get("fuel", 0))
            fuel_capacity = int(event.data.get("fuel_capacity", 0))
            if fuel_capacity > 0:
                return f"Fuel: {prop_name}", [f"{vehicle_name} is already topped off.", f"Tank {fuel}/{fuel_capacity}."]
            return f"Fuel: {prop_name}", [f"{vehicle_name} is already topped off."]
        if reason == "fully_repaired" and service == "repair":
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            durability = int(event.data.get("durability", 0))
            durability_max = int(event.data.get("durability_max", 10))
            return f"Repair: {prop_name}", [f"{vehicle_name} is already in solid shape.", f"Condition {durability}/{durability_max}."]
        if reason == "no_credits" and service == "fuel":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            return f"Fuel: {prop_name}", [
                f"{prop_name} charges {_credit_amount_label(cost)} per unit for {vehicle_name}.",
                f"You have {_credit_amount_label(credits)} on hand.",
            ]
        if reason == "no_credits" and service == "fuel_fill_bottle":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            return f"Fuel: {prop_name}", [
                f"{prop_name} charges {_credit_amount_label(cost)} to fill a glass bottle with fuel.",
                f"You have {_credit_amount_label(credits)} on hand.",
            ]
        if reason == "no_credits" and service == "repair":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            durability = int(event.data.get("durability", 0))
            durability_max = int(event.data.get("durability_max", 10))
            return f"Repair: {prop_name}", [
                f"{prop_name} quotes {_credit_amount_label(cost)} per repair point for {vehicle_name}.",
                f"You have {_credit_amount_label(credits)} on hand. Condition {durability}/{durability_max}.",
            ]
        if reason == "no_credits" and service == "building_repair":
            cost = int(event.data.get("cost", 0) or 0)
            credits = int(event.data.get("credits", 0) or 0)
            target_name = str(event.data.get("target_property_name", "building")).strip() or "building"
            return f"Building Repair: {prop_name}", [
                f"{target_name} repair quote is {_credit_amount_label(cost)}.",
                f"You only have {_credit_amount_label(credits)} available.",
            ]
        if reason == "no_credits" and service == "business_remodel":
            cost = int(event.data.get("cost", 0) or 0)
            credits = int(event.data.get("credits", 0) or 0)
            target_name = str(event.data.get("target_property_name", "business")).strip() or "business"
            target_label = str(event.data.get("target_label", "new business")).strip() or "new business"
            return f"Business Refit: {prop_name}", [
                f"{target_name} costs {_credit_amount_label(cost)} to refit as {target_label}.",
                f"You only have {_credit_amount_label(credits)} available.",
            ]
        if service == BODYGUARD_SERVICE_ID:
            if reason == "no_credits":
                cost = int(event.data.get("cost", 0) or 0)
                credits = int(event.data.get("credits", 0) or 0)
                return f"Bodyguards: {prop_name}", [
                    f"That protective contract costs {_credit_amount_label(cost)}.",
                    f"You only have {_credit_amount_label(credits)} on hand.",
                ]
            if reason in {"invalid_target", "invalid_assignment"}:
                return f"Bodyguards: {prop_name}", [
                    "That protective assignment is no longer valid.",
                    "Choose yourself or a current owned business.",
                ]
            if reason == "invalid_tier":
                return f"Bodyguards: {prop_name}", ["That bodyguard tier is not posted anymore."]
            if reason == "assignment_full":
                active = int(event.data.get("active_count", 0) or 0)
                maximum = int(event.data.get("max_slots", BODYGUARD_MAX_CHANNEL_GUARDS) or BODYGUARD_MAX_CHANNEL_GUARDS)
                return f"Bodyguards: {prop_name}", [
                    f"That protected detail is already full at {active}/{maximum} guards.",
                    "Release guards from the detail before adding more.",
                ]
        if service in CULT_SERVICE_IDS:
            cult_name = str(event.data.get("cult_name", "") or "").strip()
            title_name = cult_name or prop_name
            event_lines = [
                str(line).strip()
                for line in tuple(event.data.get("lines", ()) or ())
                if str(line).strip()
            ]
            if event_lines:
                return f"{_site_service_label(service).title()}: {title_name}", event_lines
            if reason == "shunned":
                return f"{_site_service_label(service).title()}: {title_name}", [
                    "The contact will not open business with you.",
                    "This is circle business, not law business.",
                ]
            if reason == "not_member":
                return f"{_site_service_label(service).title()}: {title_name}", [
                    "That part is for members only.",
                    "Ask the contact what membership would mean first.",
                ]
            if reason == "no_credits":
                cost = int(event.data.get("cost", 0) or 0)
                credits = int(event.data.get("credits", 0) or 0)
                return f"{_site_service_label(service).title()}: {title_name}", [
                    f"The ask is {_credit_amount_label(cost)}.",
                    f"You only have {_credit_amount_label(credits)} on hand.",
                ]
            return f"{_site_service_label(service).title()}: {title_name}", ["That circle request is not available right now."]
        if reason == "no_credits" and service == "vending":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            return f"Vending: {prop_name}", [
                f"{item_name} costs {_credit_amount_label(cost)} here.",
                f"You only have {_credit_amount_label(credits)} on hand.",
            ]
        if reason == "no_credits" and service == "herbal_care":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            return f"Herbal Care: {prop_name}", [
                f"{prop_name} charges {_credit_amount_label(cost)} for restorative care.",
                f"You only have {_credit_amount_label(credits)} on hand.",
            ]
        if reason == "no_credits" and service in {"herbal_prepare", "herbal_recipe_sales"}:
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            label = "herbal preparation" if service == "herbal_prepare" else "that recipe"
            return title, [
                f"{prop_name} charges {_credit_amount_label(cost)} for {label}.",
                f"You only have {_credit_amount_label(credits)} on hand.",
            ]
        if reason == "no_credits" and service == "butcher_prepare":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            return f"Butcher Prep: {prop_name}", [
                f"{prop_name} charges {_credit_amount_label(cost)} per first batch.",
                f"You only have {_credit_amount_label(credits)} on hand.",
            ]
        if reason == "inventory_full" and service in {"campfire_cook", "butcher_prepare"}:
            item_name = "cooked meat" if service == "campfire_cook" else "packaged meat"
            return title, [
                f"No room for the {item_name}.",
                "Free up inventory space before handing over the meat.",
            ]
        if reason == "inventory_full" and service == "fuel_fill_bottle":
            output_name = str(event.data.get("output_item_name", "the filled bottle")).strip() or "the filled bottle"
            return title, [
                f"No room for {output_name}.",
                "Free up inventory space before filling the bottle.",
            ]
        if reason == "inventory_full" and service in herbal_craft_services:
            return title, [
                "No room for the prepared medicine.",
                "Free up inventory space before compounding the herbs.",
            ]
        if reason == "no_tokens" and service in TRANSIT_SERVICE_IDS:
            profile = _transit_service_profile(service) or {}
            title = _transit_service_title(service)
            token_cost = int(event.data.get("token_cost", 0) or 0)
            city_tokens = int(event.data.get("city_tokens", 0) or 0)
            daypasses = int(event.data.get("daypasses", 0) or 0)
            destination_name = str(event.data.get("destination_name", "that stop")).strip() or "that stop"
            fare_label = _transit_fare_label(service, fare_mode="city_pass_token", token_cost=token_cost)
            inventory_label = _transit_inventory_label(city_tokens=city_tokens, daypasses=daypasses)
            lines = [
                str(line).format(
                    destination_name=destination_name,
                    fare_label=fare_label,
                    inventory_label=inventory_label,
                )
                for line in tuple(profile.get("blocked_no_fare_lines", ()) or ())
                if str(line).strip()
            ]
            if not lines:
                lines = [
                    f"Fare to {destination_name} is {fare_label}.",
                    f"You only have {inventory_label} on hand.",
                ]
            return f"{title}: {prop_name}", lines
        if reason == "no_credits" and service in TRANSIT_SERVICE_IDS:
            profile = _transit_service_profile(service) or {}
            title = _transit_service_title(service)
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            destination_name = str(event.data.get("destination_name", "that stop")).strip() or "that stop"
            fare_label = _credit_amount_label(cost)
            inventory_label = _credit_amount_label(credits)
            lines = [
                str(line).format(
                    destination_name=destination_name,
                    fare_label=fare_label,
                    inventory_label=inventory_label,
                )
                for line in tuple(profile.get("blocked_no_fare_lines", ()) or ())
                if str(line).strip()
            ]
            if not lines:
                lines = [
                    f"Fare to {destination_name} is {fare_label}.",
                    f"You only have {inventory_label} on hand.",
                ]
            return f"{title}: {prop_name}", lines
        if reason == "inventory_full" and service == "vending":
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            return f"Vending: {prop_name}", [
                f"No room for {item_name}.",
                "Free up an inventory slot and try again.",
            ]
        if reason == "power_cut":
            return title, [
                f"{prop_name} is offline.",
                "Power is out, so this service cannot run.",
            ]
        if reason == "no_return_path" and service == "underground_access":
            return title, [
                "That passage is not safe to enter right now.",
                "No verified way back to ground could be confirmed.",
            ]
        if reason == "unavailable":
            if service == "vending":
                return f"Vending: {prop_name}", [
                    f"{prop_name} does not dispense anything right now.",
                    "The machine looks empty or offline.",
                ]
            if service in {"vehicle_sales_new", "vehicle_sales_used"}:
                quality = "new" if service.endswith("_new") else "used"
                return f"Vehicles: {prop_name}", [
                    f"The posted {quality} vehicle offer is gone.",
                    "Check the listings again for a fresh offer.",
                ]
            return title, [f"{prop_name} is not offering {_site_service_label(service)} right now."]
        if reason == "no_credits":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            return title, [f"Need {_credit_amount_label(cost)} for this service.", f"You have {_credit_amount_label(credits)} on hand."]
        if reason == "no_space" and service in {"vehicle_sales_new", "vehicle_sales_used"}:
            return f"Vehicles: {prop_name}", [f"No clear spot near {prop_name} to place the purchase."]
        if reason == "key_storage_full" and service in {"vehicle_sales_new", "vehicle_sales_used"}:
            return f"Vehicles: {prop_name}", ["You need a free inventory slot for the vehicle key."]
        if reason == "no_vehicle" and service == "vehicle_fetch":
            return f"Fetch: {prop_name}", [f"You do not own a vehicle for {prop_name} to retrieve."]
        return title, [f"{prop_name} is not offering {_site_service_label(service)} right now."]

    def _bank_transaction_lines(self, event):
        provider_name = str(event.data.get("provider_name", self._pending_property_name("Banking"))).strip() or self._pending_property_name("Banking")
        kind = str(event.data.get("kind", "deposit")).strip().lower()
        account_kind = str(event.data.get("account_kind", "personal")).strip().lower() or "personal"
        amount = int(event.data.get("amount", 0))
        wallet = int(event.data.get("wallet_credits", 0))
        bank = int(event.data.get("bank_balance", 0))
        business_balance = int(event.data.get("business_balance", 0))
        business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
        if kind == "debt_payment":
            debt_balance = int(event.data.get("debt_balance", 0))
            wallet_paid = int(event.data.get("wallet_debt_paid", 0))
            bank_paid = int(event.data.get("bank_debt_paid", 0))
            payment_bits = []
            if wallet_paid > 0:
                payment_bits.append(f"{_credit_amount_label(wallet_paid)} wallet")
            if bank_paid > 0:
                payment_bits.append(f"{_credit_amount_label(bank_paid)} bank")
            detail = f"Paid {_credit_amount_label(amount)} toward justice debt."
            if payment_bits:
                detail += f" ({', '.join(payment_bits)})"
            return f"Banking: {provider_name}", [
                detail,
                f"Wallet {_credit_amount_label(wallet)} | Bank {_credit_amount_label(bank)} | Justice debt {_credit_amount_label(debt_balance)}.",
            ]
        verb = "Withdrew" if kind == "withdraw" else "Deposited"
        if account_kind == "business":
            return f"Banking: {provider_name}", [
                f"{verb} {_credit_amount_label(amount)} {'from' if kind == 'withdraw' else 'to'} {business_name}.",
                f"Wallet {_credit_amount_label(wallet)} | {business_name} {_credit_amount_label(business_balance)}.",
            ]
        return f"Banking: {provider_name}", [
            f"{verb} {_credit_amount_label(amount)}.",
            f"Wallet {_credit_amount_label(wallet)} | Bank {_credit_amount_label(bank)}.",
        ]

    def _bank_blocked_lines(self, event):
        reason = str(event.data.get("reason", "")).strip().lower()
        provider_name = str(event.data.get("provider_name", self._pending_property_name("Banking"))).strip() or self._pending_property_name("Banking")
        title = f"Banking: {provider_name}"
        if reason == "no_banking_service":
            return title, ["No bank or teller is nearby."]
        if reason == "no_business_account":
            return title, ["No owned business account is available."]
        if reason == "no_bank_balance":
            return title, ["Bank account is empty."]
        if reason == "missing_finance_profile":
            return title, ["No verified account record is available."]
        if reason == "no_debt_balance":
            return title, ["No justice debt is currently on the books."]
        if reason == "insufficient_liquid_funds":
            debt_balance = int(event.data.get("debt_balance", 0))
            available_liquid = int(event.data.get("available_liquid", 0))
            return title, [
                f"Cannot pay justice debt right now.",
                f"Liquid funds {_credit_amount_label(available_liquid)} | Justice debt {_credit_amount_label(debt_balance)}.",
            ]
        if reason == "deposit_not_needed":
            return title, ["Wallet reserve is already above the current bank target."]
        if reason == "no_funds_to_manage":
            return title, ["No funds are available to move right now."]
        if reason == "insufficient_business_balance":
            amount = int(event.data.get("amount", 0))
            business_balance = int(event.data.get("business_balance", 0))
            business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
            return title, [f"Cannot withdraw {_credit_amount_label(amount)}.", f"{business_name} holds {_credit_amount_label(business_balance)}."]
        if reason == "insufficient_bank_balance":
            amount = int(event.data.get("amount", 0))
            bank_balance = int(event.data.get("bank_balance", 0))
            return title, [f"Cannot withdraw {_credit_amount_label(amount)}.", f"Bank holds {_credit_amount_label(bank_balance)}."]
        if reason == "insufficient_wallet_funds":
            amount = int(event.data.get("amount", 0))
            credits = int(event.data.get("credits", 0))
            return title, [f"Cannot deposit {_credit_amount_label(amount)}.", f"Wallet holds {_credit_amount_label(credits)}."]
        if reason == "invalid_amount":
            kind = str(event.data.get("kind", "")).strip().lower()
            if kind == "pay_justice_debt":
                return title, ["Choose a non-zero payment toward justice debt."]
            return title, ["Choose a non-zero banking amount."]
        return title, [f"{provider_name} cannot process that banking request right now."]

    def _insurance_purchased_lines(self, event):
        provider_name = str(event.data.get("provider_name", self._pending_property_name("Insurance"))).strip() or self._pending_property_name("Insurance")
        policy_name = str(event.data.get("policy_name", "policy")).strip() or "policy"
        premium = int(event.data.get("premium", 0))
        expires_tick = int(event.data.get("expires_tick", 0))
        duration_ticks = int(event.data.get("duration_ticks", max(0, expires_tick - int(self.sim.tick))))
        duration_text = _tick_duration_label(self.sim, duration_ticks)
        lines = [
            f"Purchased {policy_name}.",
            f"Premium {_credit_amount_label(premium)}. Covers {duration_text}; expires t{expires_tick}.",
        ]
        contact_note = str(event.data.get("contact_note", "")).strip()
        if contact_note:
            lines.append(contact_note)
        return f"Insurance: {provider_name}", lines

    def _insurance_blocked_lines(self, event):
        reason = str(event.data.get("reason", "")).strip().lower()
        provider_name = str(event.data.get("provider_name", self._pending_property_name("Insurance"))).strip() or self._pending_property_name("Insurance")
        title = f"Insurance: {provider_name}"
        if reason == "no_insurance_service":
            return title, ["No insurer is nearby."]
        if reason == "insufficient_funds":
            premium = int(event.data.get("premium", 0))
            credits = int(event.data.get("credits", 0))
            policy_name = str(event.data.get("policy_name", "policy")).strip() or "policy"
            return title, [f"Need {_credit_amount_label(premium)} for {policy_name}.", f"You have {_credit_amount_label(credits)} on hand."]
        if reason == "provider_no_products":
            return title, [f"{provider_name} has no policies to offer right now."]
        if reason == "no_offer":
            return title, [f"{provider_name} has nothing better to write right now."]
        if reason == "missing_finance_profile":
            return title, ["No verified customer record is available for underwriting."]
        return title, [f"{provider_name} cannot issue or update coverage right now."]

    def on_property_interact(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        interaction_mode = str(event.data.get("interaction_mode", "") or "").strip().lower()
        prop = self.sim.properties.get(event.data.get("property_id"))
        if not isinstance(prop, dict):
            return
        infrastructure_role = _property_infrastructure_role(prop)
        if interaction_mode and interaction_mode != "service":
            if interaction_mode != "physical" or infrastructure_role != "service_terminal":
                return
        if infrastructure_role in {"access_panel", "security_post"}:
            return

        metadata = _property_metadata(prop)
        if infrastructure_role == "service_terminal" and (
            bool(metadata.get("fixture_broken"))
            or metadata.get("fixture_usable") is False
            or electronic_fixture_interference_status(self.sim, prop).get("active")
        ):
            event.data["handled"] = True
            name = str(prop.get("name", prop.get("id", "Terminal")) or "Terminal").strip()
            jammed = electronic_fixture_interference_status(self.sim, prop)
            line = (
                "Signal interference has the terminal dark and unresponsive."
                if jammed.get("active")
                else "The terminal is dark and unresponsive."
            )
            self._present_service_result(name, [line], property_id=prop.get("id"))
            return

        pos = self._position_for(eid)
        if not pos:
            return
        surface_result = self._open_property_service_surface(prop)
        if surface_result:
            if surface_result == "ready":
                event.data["opportunity_handoff_ready"] = True
            event.data["handled"] = True

    def on_player_action(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        if str(event.data.get("action", "")).strip().lower() != "banking":
            return

        pos = self._position_for(eid)
        if not pos:
            return

        prop = self._nearest_property_with_service(pos, "banking", radius=2)
        event.data["handled"] = True
        if not prop:
            title, lines = self._bank_blocked_lines(Event("banking_action_blocked", eid=eid, reason="no_banking_service"))
            self._present_service_result(title, lines)
            return
        self._open_banking_menu(prop)

    def on_casino_ui_action(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        state = self._casino_ui_state()
        if not bool(state.get("open")):
            return
        prop = self.sim.properties.get(state.get("property_id"))
        action = str(event.data.get("action", "") or "").strip().lower()
        mode = str(state.get("mode", "floor") or "floor").strip().lower()
        host_style = str(state.get("host_style", casino_host_style(prop))).strip().lower() or casino_host_style(prop)
        service = str(state.get("service", "") or "").strip().lower()
        dx = int(event.data.get("dx", 0) or 0)
        dy = int(event.data.get("dy", 0) or 0)
        crash_session = _casino_crash_normalize_session(state.get("session")) if service == "crash" else None
        crash_phase = str(crash_session.get("phase", "")).strip().lower() if isinstance(crash_session, dict) else ""

        if action in {"scroll_line", "scroll_page", "scroll_home", "scroll_end"}:
            if action == "scroll_home":
                self._scroll_casino_body(edge="home")
            elif action == "scroll_end":
                self._scroll_casino_body(edge="end")
            elif action == "scroll_page":
                page_size = max(1, int(state.get("body_page_size", 1) or 1) - 1)
                self._scroll_casino_body(amount=page_size * (1 if int(event.data.get("direction", 1) or 1) > 0 else -1))
            else:
                self._scroll_casino_body(amount=int(event.data.get("direction", 0) or 0))
            return

        if action in {"confirm", "primary"} and (mode == "result" or bool(state.get("close_pending"))):
            action = "back"

        if action == "tab" and host_style == "floor" and mode in {"floor", "services"}:
            self._emit_casino_audio_event("casino_menu_moved", direction="tab")
            self._open_casino_floor(prop, page="services" if mode == "floor" else "games")
            return

        if action == "back":
            self._emit_casino_audio_event("casino_menu_backed")
            if service == HOLDEM_CASH_SERVICE_ID and mode == "live":
                table = holdem_cash_table_for_property(self.sim, state.get("property_id"), ensure=False)
                if isinstance(table, dict):
                    holdem_cash_leave(self.sim, table, self.player_eid, immediate=True)
                self._close_casino_ui()
                return
            if service == "crash" and crash_phase == "setup":
                if host_style == "floor":
                    self._open_casino_floor(prop, page=state.get("floor_page", "games"), selected_id=f"game:{service}")
                else:
                    self._return_from_casino_host(prop)
                return
            if mode == "result" or bool(state.get("close_pending")):
                if isinstance(prop, dict) and service in CASINO_GAME_SERVICE_IDS and service != HOLDEM_CASH_SERVICE_ID:
                    try:
                        return_wager = int(state.get("result_return_wager", 0) or 0)
                    except (TypeError, ValueError):
                        return_wager = 0
                    self._open_casino_wager(
                        prop,
                        service,
                        host_style=host_style,
                        return_to=str(
                            state.get("return_to", "floor" if host_style == "floor" else "service_menu")
                        ).strip().lower(),
                        selected_id=f"wager:{return_wager}" if return_wager > 0 else "",
                    )
                    return
                if host_style == "floor":
                    self._open_casino_floor(prop, page=state.get("floor_page", "games"))
                else:
                    self._return_from_casino_host(prop)
                return
            if mode == "floor":
                self._close_casino_ui()
                return
            if mode == "services":
                self._open_casino_floor(prop, page="games")
                return
            if mode == "wager":
                if host_style == "floor":
                    self._open_casino_floor(prop, page=state.get("floor_page", "games"), selected_id=f"game:{service}")
                else:
                    self._return_from_casino_host(prop)
                return
            if mode == "live":
                if self._casino_session():
                    self._forfeit_active_casino_session()
                    if service == "crash":
                        return
                if host_style == "floor":
                    self._open_casino_floor(prop, page=state.get("floor_page", "games"), selected_id=f"game:{service}")
                else:
                    self._return_from_casino_host(prop)
                return

        if action == "move":
            if service == "crash" and crash_phase == "setup" and dx and not dy:
                row = self._selected_casino_row()
                row_id = str(row.get("id", "")).strip().lower() if isinstance(row, dict) else ""
                if row_id == "crash:auto":
                    self._emit_casino_audio_event("casino_menu_moved", direction=dx)
                    self._open_crash_setup(prop, _casino_crash_adjust_auto(crash_session, dx) or crash_session, selected_id="crash:auto")
                    return
                if row_id == "crash:step":
                    self._emit_casino_audio_event("casino_menu_moved", direction=dx)
                    self._open_crash_setup(prop, _casino_crash_cycle_auto_step(crash_session, dx) or crash_session, selected_id="crash:step")
                    return
            if mode in {"floor", "services", "wager"} or (mode == "live" and list(state.get("rows", ()) or ())):
                step = dy if dy else dx
                if step and self._move_casino_row_selection(step):
                    self._emit_casino_audio_event("casino_menu_moved", direction=step)
                return
            session = self._casino_session()
            if service == "keno":
                before = int((session or {}).get("cursor", 1) or 1)
                moved = self._move_keno_cursor(session, dx, dy)
                if moved:
                    if int(moved.get("cursor", before) or before) != before:
                        self._emit_casino_audio_event("casino_menu_moved", direction=dy if dy else dx)
                    self._open_keno_table(prop, moved)
                return
            if service == "roulette":
                before = str((session or {}).get("cursor_key", "") or "")
                moved = self._move_roulette_cursor(session, dx, dy)
                if moved:
                    if str(moved.get("cursor_key", "") or "") != before:
                        self._emit_casino_audio_event("casino_menu_moved", direction=dy if dy else dx)
                    self._open_roulette_table(prop, moved)
                return
            if service == "craps":
                before = str((session or {}).get("cursor_key", "") or "")
                moved = self._move_craps_cursor(session, dx, dy)
                if moved:
                    if str(moved.get("cursor_key", "") or "") != before:
                        self._emit_casino_audio_event("casino_menu_moved", direction=dy if dy else dx)
                    self._open_craps_table(prop, moved)
                return
            if service == "three_bright":
                before = str((session or {}).get("cursor_key", "") or "")
                moved = self._move_three_bright_cursor(session, dx, dy)
                if moved:
                    if str(moved.get("cursor_key", "") or "") != before:
                        self._emit_casino_audio_event("casino_menu_moved", direction=dy if dy else dx)
                    self._open_three_bright_table(prop, moved)
                return
            if service == "three_bones":
                before = str((session or {}).get("cursor_key", "") or "")
                moved = self._move_three_bones_cursor(session, dx, dy)
                if moved:
                    if str(moved.get("cursor_key", "") or "") != before:
                        self._emit_casino_audio_event("casino_menu_moved", direction=dy if dy else dx)
                    self._open_three_bones_table(prop, moved)
                return
            return

        if action == "confirm":
            if mode in {"floor", "services", "wager"} or list(state.get("rows", ()) or ()):
                row = self._selected_casino_row()
                if row:
                    self._emit_casino_audio_event("casino_menu_confirmed", option_id=row.get("id"))
                    self.on_service_menu_execute_request(Event(
                        "service_menu_execute_request",
                        eid=self.player_eid,
                        property_id=state.get("property_id"),
                        option_id=row.get("id"),
                    ))
                return
            session = self._casino_session()
            if service == "keno":
                current = _casino_keno_normalize_session(session)
                if not current or not list(current.get("picks", ()) or ()):
                    self._open_keno_table(prop, current or session, notice="Mark at least one number before the draw.")
                    return
                round_result = _casino_keno_draw(current)
                if not round_result:
                    self._open_keno_table(prop, current, notice="That ticket lost sync with the board. Try that draw again.")
                    return
                self._settle_casino_round(prop, service, round_result)
                return
            if service == "roulette":
                current = _casino_roulette_normalize_session(session)
                round_result = _casino_roulette_resolve(current)
                if not round_result:
                    self._open_roulette_table(prop, current or session, notice="Post at least one chip before the spin.")
                    return
                self._settle_casino_round(prop, service, round_result)
                return
            if service == "craps":
                current = _casino_craps_normalize_session(session)
                next_session, round_result = _casino_craps_resolve(current)
                if not round_result:
                    self._open_craps_table(prop, current or session, notice="Post at least one chip before the roll.")
                    return
                self._settle_casino_round(prop, service, round_result, next_session=next_session, continue_notice=round_result.get("headline", ""))
                return
            if service == "three_bright":
                current = _casino_three_bright_normalize_session(session)
                round_result = _casino_three_bright_resolve(current)
                if not round_result:
                    self._open_three_bright_table(prop, current or session, notice="Post at least one chip before the roll.")
                    return
                self._settle_casino_round(prop, service, round_result)
                return
            if service == "three_bones":
                current = _casino_three_bones_normalize_session(session)
                round_result = _casino_three_bones_resolve(current)
                if not round_result:
                    self._open_three_bones_table(prop, current or session, notice="Post at least one chip before lifting the cup.")
                    return
                self._settle_casino_round(prop, service, round_result)
                return
            return

        if action == "primary":
            if service == HOLDEM_CASH_SERVICE_ID and list(state.get("rows", ()) or ()):
                row = self._selected_casino_row()
                if row:
                    self._emit_casino_audio_event("casino_menu_confirmed", option_id=row.get("id"))
                    self.on_service_menu_execute_request(Event(
                        "service_menu_execute_request",
                        eid=self.player_eid,
                        property_id=state.get("property_id"),
                        option_id=row.get("id"),
                    ))
                return
            session = self._casino_session()
            if service == "crash":
                current = _casino_crash_normalize_session(session)
                if not current:
                    return
                if current.get("phase") == "live":
                    _next_session, round_result = _casino_crash_cashout(current)
                    if round_result:
                        self._settle_casino_round(prop, service, round_result)
                    return
                row = self._selected_casino_row()
                if row:
                    self._emit_casino_audio_event("casino_menu_confirmed", option_id=row.get("id"))
                    self.on_service_menu_execute_request(Event(
                        "service_menu_execute_request",
                        eid=self.player_eid,
                        property_id=state.get("property_id"),
                        option_id=row.get("id"),
                    ))
                return
            if service == "keno":
                current = _casino_keno_normalize_session(session)
                if not current:
                    return
                ticket_number = max(1, min(CASINO_KENO_NUMBER_COUNT, int(current.get("cursor", 1) or 1)))
                picks = list(current.get("picks", ()) or ())
                if ticket_number not in picks and len(picks) >= CASINO_KENO_MAX_PICKS:
                    self._open_keno_table(prop, current, notice=f"You can only mark {CASINO_KENO_MAX_PICKS} spots on one ticket.")
                    return
                next_session = _casino_keno_toggle_pick(current, ticket_number)
                if next_session:
                    self._open_keno_table(prop, next_session)
                return
            if service == "roulette":
                current = _casino_roulette_normalize_session(session)
                if not current:
                    return
                chip_value = int(current.get("wager", 0) or 0)
                ok, credits = self._casino_commit_stake(chip_value)
                if not ok:
                    self._open_roulette_table(prop, current, notice=f"You need {_credit_amount_label(chip_value)} for another chip. Wallet {_credit_amount_label(credits)}.")
                    return
                next_session = _casino_roulette_stage_bet(current, current.get("cursor_key"))
                if not next_session:
                    assets = self._assets_for(self.player_eid)
                    if assets:
                        assets.credits += chip_value
                    self._open_roulette_table(prop, current, notice="That market is not taking action right now.")
                    return
                self._open_roulette_table(prop, next_session)
                return
            if service == "craps":
                current = _casino_craps_normalize_session(session)
                if not current:
                    return
                chip_value = int(current.get("wager", 0) or 0)
                ok, credits = self._casino_commit_stake(chip_value)
                if not ok:
                    self._open_craps_table(prop, current, notice=f"You need {_credit_amount_label(chip_value)} for another chip. Wallet {_credit_amount_label(credits)}.")
                    return
                next_session = _casino_craps_stage_bet(current, current.get("cursor_key"))
                if not next_session:
                    assets = self._assets_for(self.player_eid)
                    if assets:
                        assets.credits += chip_value
                    self._open_craps_table(prop, current, notice="That market is not working right now. Odds need a live point and matching line action.")
                    return
                self._open_craps_table(prop, next_session)
                return
            if service == "three_bright":
                current = _casino_three_bright_normalize_session(session)
                if not current:
                    return
                chip_value = int(current.get("wager", 0) or 0)
                ok, credits = self._casino_commit_stake(chip_value)
                if not ok:
                    self._open_three_bright_table(prop, current, notice=f"You need {_credit_amount_label(chip_value)} for another chip. Wallet {_credit_amount_label(credits)}.")
                    return
                next_session = _casino_three_bright_stage_bet(current, current.get("cursor_key"))
                if not next_session:
                    assets = self._assets_for(self.player_eid)
                    if assets:
                        assets.credits += chip_value
                    self._open_three_bright_table(prop, current, notice="That color market is not taking action right now.")
                    return
                self._open_three_bright_table(prop, next_session)
                return
            if service == "three_bones":
                current = _casino_three_bones_normalize_session(session)
                if not current:
                    return
                chip_value = int(current.get("wager", 0) or 0)
                ok, credits = self._casino_commit_stake(chip_value)
                if not ok:
                    self._open_three_bones_table(prop, current, notice=f"You need {_credit_amount_label(chip_value)} for another chip. Wallet {_credit_amount_label(credits)}.")
                    return
                next_session = _casino_three_bones_stage_bet(current, current.get("cursor_key"))
                if not next_session:
                    assets = self._assets_for(self.player_eid)
                    if assets:
                        assets.credits += chip_value
                    self._open_three_bones_table(prop, current, notice="That bones market is not working right now.")
                    return
                self._open_three_bones_table(prop, next_session)
                return
            return

        if action == "secondary":
            session = self._casino_session()
            if service == "keno":
                current = _casino_keno_normalize_session(session)
                if not current:
                    return
                ticket_number = max(1, min(CASINO_KENO_NUMBER_COUNT, int(current.get("cursor", 1) or 1)))
                if ticket_number not in set(current.get("picks", ()) or ()):
                    self._open_keno_table(prop, current, notice="That spot is not marked on your ticket.")
                    return
                next_session = _casino_keno_toggle_pick(current, ticket_number)
                if next_session:
                    self._open_keno_table(prop, next_session)
                return
            if service == "roulette":
                current = _casino_roulette_normalize_session(session)
                if not current:
                    return
                key = str(current.get("cursor_key", "")).strip().lower()
                if int(dict(current.get("bets", {}) or {}).get(key, 0) or 0) <= 0:
                    self._open_roulette_table(prop, current, notice="No chip is staged on that market.")
                    return
                next_session = _casino_roulette_remove_bet(current, key)
                assets = self._assets_for(self.player_eid)
                if assets:
                    assets.credits += int(current.get("wager", 0) or 0)
                self._open_roulette_table(prop, next_session or current)
                return
            if service == "craps":
                current = _casino_craps_normalize_session(session)
                if not current:
                    return
                key = str(current.get("cursor_key", "")).strip().lower()
                if int(dict(current.get("bets", {}) or {}).get(key, 0) or 0) <= 0:
                    self._open_craps_table(prop, current, notice="No chip is staged on that market.")
                    return
                next_session = _casino_craps_remove_bet(current, key)
                assets = self._assets_for(self.player_eid)
                if assets:
                    assets.credits += int(current.get("wager", 0) or 0)
                self._open_craps_table(prop, next_session or current)
                return
            if service == "three_bright":
                current = _casino_three_bright_normalize_session(session)
                if not current:
                    return
                key = str(current.get("cursor_key", "")).strip().lower()
                if int(dict(current.get("bets", {}) or {}).get(key, 0) or 0) <= 0:
                    self._open_three_bright_table(prop, current, notice="No chip is staged on that color market.")
                    return
                next_session = _casino_three_bright_remove_bet(current, key)
                assets = self._assets_for(self.player_eid)
                if assets:
                    assets.credits += int(current.get("wager", 0) or 0)
                self._open_three_bright_table(prop, next_session or current)
                return
            if service == "three_bones":
                current = _casino_three_bones_normalize_session(session)
                if not current:
                    return
                key = str(current.get("cursor_key", "")).strip().lower()
                if int(dict(current.get("bets", {}) or {}).get(key, 0) or 0) <= 0:
                    self._open_three_bones_table(prop, current, notice="No chip is staged on that bones market.")
                    return
                next_session = _casino_three_bones_remove_bet(current, key)
                assets = self._assets_for(self.player_eid)
                if assets:
                    assets.credits += int(current.get("wager", 0) or 0)
                self._open_three_bones_table(prop, next_session or current)
                return

    def on_dialog_close_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        casino_state = self._casino_ui_state()
        if bool(casino_state.get("open")):
            if str(casino_state.get("service", "") or "").strip().lower() == HOLDEM_CASH_SERVICE_ID:
                table = holdem_cash_table_for_property(self.sim, casino_state.get("property_id"), ensure=False)
                if isinstance(table, dict):
                    holdem_cash_leave(self.sim, table, self.player_eid, immediate=True)
            if self._casino_session() and not bool(casino_state.get("close_pending")):
                self._forfeit_active_casino_session()
            self._close_casino_ui()
            return
        state = self._dialog_ui_state()
        if str(state.get("kind", "")).strip().lower() == "service_menu":
            if self._casino_session() and not bool(state.get("close_pending")):
                self._forfeit_active_casino_session()
            self._close_service_menu()
            return
        live_timeskip = getattr(self.sim, "live_timeskip", {})
        if isinstance(live_timeskip, dict) and bool(live_timeskip.get("result_pending")):
            return
        self._clear_pending_service_result()

    def on_site_service_started(self, event):
        if not self._event_matches_pending(event, channel="site"):
            return
        if not bool(event.data.get("live_timeskip")):
            return
        self._dismiss_service_menu_for_started_service()

    def on_service_menu_execute_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        casino_state = self._casino_ui_state()
        if bool(casino_state.get("open")):
            option_id = str(event.data.get("option_id", "") or "").strip().lower()
            property_id = event.data.get("property_id") or casino_state.get("property_id")
            casino_mode = str(casino_state.get("mode", "") or "").strip().lower()
            service = str(casino_state.get("service", "") or "").strip().lower()
            if not option_id or not property_id:
                return
            prop = self.sim.properties.get(property_id)
            if option_id.startswith("game:"):
                service_id = str(option_id.partition(":")[2] or "").strip().lower()
                if isinstance(prop, dict) and service_id:
                    self._open_casino_wager(prop, service_id, host_style=casino_host_style(prop), return_to="floor")
                return
            if option_id.startswith("service:"):
                option_id = str(option_id.partition(":")[2] or "").strip().lower()
            if option_id in CASINO_GAME_SERVICE_IDS:
                if isinstance(prop, dict):
                    self._open_casino_wager(prop, option_id, host_style=casino_host_style(prop), return_to="floor" if casino_host_style(prop) == "floor" else "service_menu")
                return
            if option_id == "trade_buy":
                self._close_casino_ui()
                self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="buy", property_id=property_id))
                return
            if option_id == "trade_sell":
                self._close_casino_ui()
                self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="sell", property_id=property_id))
                return
            if option_id == "banking":
                self._close_casino_ui()
                if isinstance(prop, dict):
                    self._open_banking_menu(prop)
                return
            if option_id == "insurance":
                self._close_casino_ui()
                if isinstance(prop, dict):
                    self._begin_pending_service_result(
                        channel="insurance",
                        property_id=property_id,
                        property_name=prop.get("name", property_id),
                        service="insurance",
                    )
                    self.sim.emit(Event(
                        "finance_service_request",
                        eid=self.player_eid,
                        property_id=property_id,
                        service="insurance",
                    ))
                return
            if self._business_control_prefix_and_action(option_id)[0]:
                self._close_casino_ui()
                if self._handle_business_control_option(prop, option_id, self._dialog_ui_state()):
                    return
            if option_id.startswith("wager:"):
                try:
                    wager = int(option_id.partition(":")[2] or 0)
                except (TypeError, ValueError):
                    wager = 0
                if isinstance(prop, dict):
                    self._start_casino_round(prop, service, wager)
                return
            if service and option_id.startswith(f"{service}:bet:"):
                try:
                    wager = int(option_id.rsplit(":", 1)[-1])
                except (TypeError, ValueError):
                    wager = 0
                if isinstance(prop, dict):
                    self._start_casino_round(prop, service, wager)
                return
            if isinstance(prop, dict) and self._handle_active_casino_option(prop, option_id):
                return
            if casino_mode == "services":
                self._handoff_casino_floor_service(prop, option_id)
                return

        state = self._dialog_ui_state()
        if not state.get("open") or str(state.get("kind", "")).strip().lower() != "service_menu":
            return

        option_id = str(event.data.get("option_id", "") or "").strip().lower()
        property_id = event.data.get("property_id") or state.get("property_id")
        if not option_id or not property_id:
            return

        prop = self.sim.properties.get(property_id)
        if option_id == "service_menu:root":
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            pos = self._position_for(self.player_eid)
            if not pos:
                return
            options, storefront_service = self._service_menu_options(self.player_eid, prop, pos)
            self._open_service_menu(prop, options, storefront_service=storefront_service)
            return
        if option_id == "trade_buy":
            self._close_service_menu()
            self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="buy", property_id=property_id))
            return
        if option_id == "trade_sell":
            self._close_service_menu()
            self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="sell", property_id=property_id))
            return
        if option_id == "campfire_herb_cache":
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            self._close_service_menu()
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service=option_id,
                property_name=prop.get("name", property_id),
            ))
            return
        if option_id == BODYGUARD_SERVICE_ID:
            if isinstance(prop, dict):
                self._open_bodyguard_contract_menu(prop)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id.startswith(f"{BODYGUARD_SERVICE_ID}:"):
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            prop_name = prop.get("name", property_id)
            payload = {
                "eid": self.player_eid,
                "property_id": property_id,
                "service": BODYGUARD_SERVICE_ID,
                "property_name": prop_name,
            }
            detail = option_id.partition(":")[2]
            if detail.startswith("hire|"):
                parts = detail.split("|")
                if len(parts) != 4:
                    self._present_service_result("Bodyguards", ["That bodyguard posting is no longer valid."])
                    return
                _verb, tier, target_kind, target_id = parts
                payload.update({
                    "bodyguard_action": "hire",
                    "tier": tier,
                    "assignment_kind": target_kind,
                })
                if target_kind == "principal":
                    payload["principal_eid"] = self.player_eid
                else:
                    payload["target_property_id"] = target_id
            elif detail.startswith("fire|"):
                team_id = detail.partition("|")[2]
                if not team_id:
                    self._present_service_result("Bodyguards", ["That bodyguard team is no longer valid."])
                    return
                payload.update({
                    "bodyguard_action": "fire",
                    "team_id": team_id,
                })
            elif detail.startswith("fire_channel|"):
                channel_id = detail.partition("|")[2]
                if not channel_id:
                    self._present_service_result("Bodyguards", ["That bodyguard detail is no longer valid."])
                    return
                payload.update({
                    "bodyguard_action": "fire",
                    "protection_channel_id": channel_id,
                })
            else:
                self._present_service_result("Bodyguards", ["That bodyguard option is no longer valid."])
                return
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop_name,
                service=BODYGUARD_SERVICE_ID,
            )
            self.sim.emit(Event("site_service_request", **payload))
            return
        if option_id in CASINO_GAME_SERVICE_IDS:
            if isinstance(prop, dict):
                self._close_service_menu()
                self._open_casino_wager(
                    prop,
                    option_id,
                    host_style=casino_host_style(prop),
                    return_to="floor" if casino_host_style(prop) == "floor" else "service_menu",
                )
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id == "banking":
            if isinstance(prop, dict):
                self._open_banking_menu(prop)
            else:
                title, lines = self._bank_blocked_lines(Event("banking_action_blocked", eid=self.player_eid, reason="no_banking_service"))
                self._present_service_result(title, lines)
            return
        if option_id == "business_management":
            if isinstance(prop, dict):
                self._open_business_management_menu(prop)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if self._business_control_prefix_and_action(option_id)[0]:
            if self._handle_business_control_option(prop, option_id, state):
                return
        if option_id == "justice_dispatch":
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            pos = self._position_for(self.player_eid)
            if pos is None:
                self._present_service_result("Dispatch", ["No valid position is available for the call."], property_id=property_id)
                return
            if not self._player_can_call_justice_from_property(self.player_eid, prop, pos):
                self._present_service_result("Dispatch", ["This place cannot place a clean dispatch call for you."], property_id=property_id)
                return
            result = request_player_justice_dispatch(
                self.sim,
                self.player_eid,
                int(pos.x),
                int(pos.y),
                int(pos.z),
                source="property_service",
                property_id=property_id,
                property_name=str(prop.get("name", property_id) or property_id).strip(),
            )
            self._present_service_result(
                "Dispatch",
                tuple(result.get("lines", ()) or ("Dispatch request sent.",)),
                property_id=property_id,
            )
            return
        if option_id == "redeem_meal_voucher":
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            pos = self._position_for(self.player_eid)
            if not pos:
                return
            needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
            if needs is None:
                self._present_service_result("Meal Voucher", ["No meal need is available right now."], property_id=property_id)
                return
            if not _nutrition_capabilities_for_property(prop).get("food"):
                self._present_service_result("Meal Voucher", ["This place is not serving meals right now."], property_id=property_id)
                return
            if self._inventory_item_count("meal_voucher") <= 0:
                self._present_service_result("Meal Voucher", ["You do not have a meal voucher to redeem."], property_id=property_id)
                return
            before_hunger = float(getattr(needs, "hunger", 100.0) if getattr(needs, "hunger", None) is not None else 100.0)
            before_thirst = float(getattr(needs, "thirst", 100.0) if getattr(needs, "thirst", None) is not None else 100.0)
            result = _receive_nutrition_at_actor(
                self.sim,
                self.player_eid,
                pos,
                prop=prop,
                redeem_meal_voucher=True,
            )
            if not result:
                self._present_service_result("Meal Voucher", ["You do not need a meal right now."], property_id=property_id)
                return
            title, lines = self._redeem_meal_voucher_lines(prop, result, before_hunger, before_thirst)
            self._present_service_result(title, lines, property_id=property_id)
            return
        if option_id == "building_repair":
            if isinstance(prop, dict):
                self._open_repair_target_menu(prop)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id == "business_remodel":
            if isinstance(prop, dict):
                self._open_business_remodel_business_menu(prop)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id == "appearance_style":
            if isinstance(prop, dict):
                self._open_appearance_style_menu(prop)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id in {CIVIC_RECORDS_SERVICE_ID, "civic_records:root"}:
            if isinstance(prop, dict):
                self._open_civic_records(prop)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id == "civic_records:census":
            if isinstance(prop, dict):
                self._open_civic_census(prop)
            return
        if option_id == "civic_records:people":
            if isinstance(prop, dict):
                self._open_civic_people_directory(prop)
            return
        if option_id == "civic_records:self":
            if isinstance(prop, dict):
                self._open_civic_person_record(prop, self.player_eid)
            return
        if option_id == "civic_records:licenses":
            if isinstance(prop, dict):
                self._open_civic_license_ledger(prop)
            return
        if option_id.startswith("civic_records:license_buy|"):
            if isinstance(prop, dict):
                self._open_civic_license_action(prop, option_id.partition("|")[2])
            return
        if option_id == "civic_records:culls":
            if isinstance(prop, dict):
                self._open_civic_culls(prop)
            return
        if option_id.startswith("civic_records:cull_review|"):
            if isinstance(prop, dict):
                self._open_civic_cull_review(prop, option_id.partition("|")[2])
            return
        if option_id.startswith("civic_records:cull_confirm|"):
            if isinstance(prop, dict):
                self._confirm_civic_cull(prop, option_id.partition("|")[2])
            return
        if option_id.startswith("civic_records:person|"):
            if isinstance(prop, dict):
                try:
                    subject_eid = int(option_id.partition("|")[2])
                except (TypeError, ValueError):
                    subject_eid = -1
                self._open_civic_person_record(prop, subject_eid)
            return
        if option_id in {"fauna_registry", "flora_registry"}:
            if isinstance(prop, dict):
                self._open_ecology_registry(prop, "fauna" if option_id == "fauna_registry" else "flora")
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id in SERVICE_JOB_BOARD_SERVICES:
            if isinstance(prop, dict):
                self._open_service_job_board(prop, option_id)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id == "bounty_jobs:license_buy":
            if isinstance(prop, dict):
                self._open_civic_license_action(prop, "bounty", return_option="bounty_jobs")
            return
        job_board_service = next(
            (service for service in SERVICE_JOB_BOARD_SERVICES if option_id.startswith(f"{service}:accept|")),
            "",
        )
        if job_board_service:
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            selected = next(
                (
                    row
                    for row in list(state.get("topics", []) or ())
                    if isinstance(row, dict) and str(row.get("id", "")).strip().lower() == option_id
                ),
                None,
            )
            job_key = str((selected or {}).get("job_key", "") or option_id.partition("|")[2]).strip()
            if not job_key:
                self._present_service_result("Jobs", ["That job posting is no longer available."], property_id=property_id)
                return
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop.get("name", property_id),
                service=job_board_service,
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service=job_board_service,
                property_name=prop.get("name", property_id),
                job_key=job_key,
            ))
            return
        if option_id.startswith("appearance_style:"):
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            parts = option_id.split(":")
            if len(parts) != 3:
                self._present_service_result("Styling", ["That styling option is invalid."], property_id=property_id)
                return
            style_kind = str(parts[1] or "").strip().lower()
            style_value = str(parts[2] or "").strip().lower()
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop.get("name", property_id),
                service="appearance_style",
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="appearance_style",
                property_name=prop.get("name", property_id),
                style_kind=style_kind,
                style_value=style_value,
            ))
            return
        if option_id.startswith("building_repair:target|"):
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            target_property_id = str(option_id.partition("|")[2] or "").strip()
            if not target_property_id:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop.get("name", property_id),
                service="building_repair",
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="building_repair",
                property_name=prop.get("name", property_id),
                target_property_id=target_property_id,
            ))
            return
        if option_id.startswith("business_remodel:target|"):
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            target_property_id = str(option_id.partition("|")[2] or "").strip()
            target_prop = self.sim.properties.get(target_property_id)
            if not isinstance(target_prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            self._open_business_remodel_option_menu(prop, target_prop)
            return
        if option_id.startswith("business_remodel:apply|"):
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            payload = str(option_id[len("business_remodel:apply|"):]).strip()
            business_property_id, sep, target_archetype = payload.partition("|")
            business_property_id = str(business_property_id or "").strip()
            target_archetype = str(target_archetype or "").strip().lower()
            if not business_property_id or not target_archetype:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop.get("name", property_id),
                service="business_remodel",
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="business_remodel",
                property_name=prop.get("name", property_id),
                target_property_id=business_property_id,
                target_archetype=target_archetype,
            ))
            return
        if option_id in TRANSIT_SERVICE_IDS:
            if isinstance(prop, dict):
                self._open_transit_menu(prop, option_id)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id in {"vehicle_sales_new", "vehicle_sales_used"}:
            if isinstance(prop, dict):
                self._open_vehicle_sale_menu(prop, "new" if option_id == "vehicle_sales_new" else "used")
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        transit_service = next(
            (
                service
                for service in TRANSIT_SERVICE_IDS
                if option_id.startswith(f"{service}:dest:")
            ),
            "",
        )
        if transit_service:
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            selected = next(
                (
                    row
                    for row in list(state.get("topics", []) or ())
                    if isinstance(row, dict) and str(row.get("id", "")).strip().lower() == option_id
                ),
                None,
            )
            if not isinstance(selected, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            title = _transit_service_title(transit_service)
            prop_name = prop.get("name", property_id)
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop_name,
                service=transit_service,
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service=transit_service,
                property_name=prop_name,
                destination_chunk=tuple(selected.get("destination_chunk", ()) or ()),
                destination_node_id=str(selected.get("destination_node_id", "")).strip(),
                destination_building_id=str(selected.get("destination_building_id", "")).strip(),
                destination_name=str(selected.get("destination_name", "")).strip(),
                distance=int(selected.get("destination_distance", 0) or 0),
                quoted_cost=int(selected.get("quoted_cost", 0) or 0),
                quoted_token_cost=int(selected.get("quoted_token_cost", 0) or 0),
                quote_mode=str(selected.get("quote_mode", "credits")).strip().lower() or "credits",
            ))
            return
        if option_id.startswith("vehicle_sales_new:offer:") or option_id.startswith("vehicle_sales_used:offer:"):
            service, _sep, offering_id = option_id.partition(":offer:")
            service = str(service or "").strip().lower()
            if service not in {"vehicle_sales_new", "vehicle_sales_used"} or not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            offering_id = str(offering_id or "").strip().lower()
            if not offering_id:
                self._present_service_result("Vehicles", ["That vehicle offering is not valid."])
                return
            prop_name = prop.get("name", property_id)
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop_name,
                service=service,
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service=service,
                property_name=prop_name,
                offering_id=offering_id,
            ))
            return
        if option_id.startswith("banking:"):
            parts = option_id.split(":")
            if len(parts) != 3:
                self._present_service_result("Banking", ["That banking option is invalid."])
                return
            if not isinstance(prop, dict):
                title, lines = self._bank_blocked_lines(Event("banking_action_blocked", eid=self.player_eid, reason="no_banking_service"))
                self._present_service_result(title, lines)
                return
            transfer_kind = str(parts[1]).strip().lower()
            try:
                amount = int(parts[2])
            except (TypeError, ValueError):
                amount = 0
            if transfer_kind not in {"deposit", "withdraw", "pay_justice_debt"} or amount <= 0:
                self._present_service_result("Banking", ["That banking option is invalid."])
                return
            self._begin_pending_service_result(
                channel="banking",
                property_id=property_id,
                property_name=prop.get("name", property_id),
                service="banking",
            )
            self.sim.emit(Event(
                "finance_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="banking",
                kind=transfer_kind,
                amount=amount,
            ))
            return
        if option_id.startswith("property_purchase:"):
            parts = option_id.split(":")
            action = str(parts[1] if len(parts) >= 2 else "").strip().lower()
            purchase_property_id = str(parts[2] if len(parts) >= 3 else property_id or "").strip()
            if action == "cancel":
                self._close_service_menu()
                return
            if action != "confirm" or not purchase_property_id:
                self._present_service_result("Property Purchase", ["That purchase option is invalid."], property_id=property_id)
                return
            self._close_service_menu()
            self.sim.emit(Event(
                "property_purchase_execute_request",
                eid=self.player_eid,
                property_id=purchase_property_id,
            ))
            return
        if option_id.startswith("banking_business:"):
            parts = option_id.split(":")
            if len(parts) != 4:
                self._present_service_result("Banking", ["That business banking option is invalid."])
                return
            if not isinstance(prop, dict):
                title, lines = self._bank_blocked_lines(Event("banking_action_blocked", eid=self.player_eid, reason="no_banking_service"))
                self._present_service_result(title, lines)
                return
            transfer_kind = str(parts[1]).strip().lower()
            try:
                amount = int(parts[2])
            except (TypeError, ValueError):
                amount = 0
            business_property_id = str(parts[3] or "").strip()
            if transfer_kind not in {"deposit", "withdraw"} or amount <= 0 or not business_property_id:
                self._present_service_result("Banking", ["That business banking option is invalid."])
                return
            self._begin_pending_service_result(
                channel="banking",
                property_id=property_id,
                property_name=prop.get("name", property_id),
                service="banking",
            )
            self.sim.emit(Event(
                "finance_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="banking",
                kind=transfer_kind,
                amount=amount,
                account_kind="business",
                business_property_id=business_property_id,
            ))
            return
        if option_id.startswith("banking_business_status:"):
            business_property_id = str(option_id.split(":", 1)[1] or "").strip()
            if not business_property_id:
                self._present_service_result("Business status", ["That business status option is invalid."])
                return
            business_prop = _resolve_property_record(self.sim, business_property_id)
            if not isinstance(business_prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            lines = self._business_status_lines({"prop": business_prop})
            business_name = str(business_prop.get("metadata", {}).get("business_name", business_prop.get("name", "Business"))).strip() or "Business"
            self._present_service_result(
                f"Business status: {business_name}",
                lines or ["No business status is available right now."],
                property_id=property_id,
            )
            return
        if option_id.startswith("banking_business_policy:"):
            parts = option_id.split(":")
            if len(parts) != 3:
                self._present_service_result("Business policy", ["That business policy option is invalid."])
                return
            business_property_id = str(parts[1] or "").strip()
            next_policy = str(parts[2] or "").strip().lower()
            if not business_property_id:
                self._present_service_result("Business policy", ["That business policy option is invalid."])
                return
            business_prop = _resolve_property_record(self.sim, business_property_id)
            if not isinstance(business_prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            policy = player_business_set_customer_policy(business_prop, next_policy, sim=self.sim)
            business_name = str(business_prop.get("metadata", {}).get("business_name", business_prop.get("name", "Business"))).strip() or "Business"
            self._present_service_result(
                f"Business policy: {business_name}",
                self._business_policy_result_lines(business_prop, policy),
                property_id=property_id,
            )
            return
        if option_id.startswith("banking_business_hours:"):
            parts = option_id.split(":")
            if len(parts) != 3:
                self._present_service_result("Business hours", ["That business hours option is invalid."])
                return
            business_property_id = str(parts[1] or "").strip()
            next_mode = str(parts[2] or "").strip().lower()
            if not business_property_id:
                self._present_service_result("Business hours", ["That business hours option is invalid."])
                return
            business_prop = _resolve_property_record(self.sim, business_property_id)
            if not isinstance(business_prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            result = player_business_set_hours_mode(self.sim, business_prop, next_mode)
            business_name = str(business_prop.get("metadata", {}).get("business_name", business_prop.get("name", "Business"))).strip() or "Business"
            self._present_service_result(
                f"Business hours: {business_name}",
                self._business_hours_result_lines(business_prop, result),
                property_id=property_id,
            )
            return
        if option_id.startswith("banking_business_markup:"):
            parts = option_id.split(":")
            if len(parts) != 3:
                self._present_service_result("Business markup", ["That business markup option is invalid."])
                return
            business_property_id = str(parts[1] or "").strip()
            next_mode = str(parts[2] or "").strip().lower()
            if not business_property_id:
                self._present_service_result("Business markup", ["That business markup option is invalid."])
                return
            business_prop = _resolve_property_record(self.sim, business_property_id)
            if not isinstance(business_prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            mode = player_business_set_markup_mode(business_prop, next_mode, sim=self.sim)
            business_name = str(business_prop.get("metadata", {}).get("business_name", business_prop.get("name", "Business"))).strip() or "Business"
            self._present_service_result(
                f"Business markup: {business_name}",
                self._business_markup_result_lines(business_prop, mode),
                property_id=property_id,
            )
            return
        if option_id == "insurance":
            if not isinstance(prop, dict):
                title, lines = self._insurance_blocked_lines(Event("insurance_action_blocked", eid=self.player_eid, reason="no_insurance_service"))
                self._present_service_result(title, lines)
                return
            prop_name = prop.get("name", property_id) if isinstance(prop, dict) else property_id
            self._begin_pending_service_result(
                channel="insurance",
                property_id=property_id,
                property_name=prop_name,
                service="insurance",
            )
            self.sim.emit(Event(
                "finance_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="insurance",
            ))
            return
        if self._handle_active_casino_option(prop, option_id):
            return
        if option_id in CASINO_GAME_SERVICE_IDS:
            if isinstance(prop, dict):
                self._open_casino_game_menu(prop, option_id)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        for service in CASINO_GAME_SERVICE_IDS:
            prefix = f"{service}:bet:"
            if not option_id.startswith(prefix):
                continue
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            try:
                wager = int(option_id.rsplit(":", 1)[-1])
            except (TypeError, ValueError):
                wager = 0
            if wager <= 0:
                self._present_service_result(_casino_game_title(service), ["That wager is not valid."])
                return
            self._start_casino_round(prop, service, wager)
            return
        prop_name = prop.get("name", property_id) if isinstance(prop, dict) else event.data.get("property_name", "site")
        if option_id == "rest":
            if isinstance(prop, dict):
                self._open_lodging_stay_menu(prop)
            else:
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
            return
        if option_id.startswith("rest:stay:"):
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            parts = option_id.split(":")
            stay_ticks = 0
            stay_kind = str(parts[2] if len(parts) >= 3 else "").strip().lower()
            if stay_kind == "hours" and len(parts) >= 4:
                try:
                    stay_ticks = int(round(float(parts[3]) * float(self._ticks_per_hour())))
                except (TypeError, ValueError):
                    stay_ticks = 0
            elif stay_kind == "checkout" and len(parts) >= 4:
                stay_ticks = _int_or_default(parts[3], 0)
            if stay_ticks <= 0:
                self._present_service_result("Room", ["That room stay is no longer valid."], property_id=property_id)
                return
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop_name,
                service="rest",
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="rest",
                property_name=prop_name,
                lodging_stay_ticks=max(1, int(stay_ticks)),
                lodging_stay_kind=stay_kind,
            ))
            return
        if option_id == "fuel_fill_bottle":
            if not isinstance(prop, dict):
                title, lines = self._stale_service_option_lines(option_id)
                self._present_service_result(title, lines)
                return
            self._begin_pending_service_result(
                channel="site",
                property_id=property_id,
                property_name=prop_name,
                service=option_id,
            )
            self.sim.emit(Event(
                "site_service_request",
                eid=self.player_eid,
                property_id=property_id,
                service="fuel",
                fuel_action="fill_bottle",
                property_name=prop_name,
            ))
            return
        self._begin_pending_service_result(
            channel="site",
            property_id=property_id,
            property_name=prop_name,
            service=option_id,
        )
        self.sim.emit(Event(
            "site_service_request",
            eid=self.player_eid,
            property_id=property_id,
            service=option_id,
            property_name=prop_name,
        ))

    def on_site_service_used(self, event):
        if not self._event_matches_pending(event, channel="site"):
            return
        title, lines = self._site_service_result_lines(event)
        self._present_service_result(title, lines, property_id=event.data.get("property_id"))

    def on_site_service_blocked(self, event):
        if not self._event_matches_pending(event, channel="site"):
            return
        title, lines = self._site_service_blocked_lines(event)
        self._present_service_result(title, lines, property_id=event.data.get("property_id"))

    def on_site_intel_report(self, event):
        if not self._event_matches_pending(event, channel="site", service="intel"):
            return
        prop_name = str(event.data.get("property_name", self._pending_property_name("Intel"))).strip() or self._pending_property_name("Intel")
        raw_lines = event.data.get("lines") or []
        display_limit = max(1, min(8, _int_or_default(event.data.get("display_limit"), 4)))
        note = _sentence_from_note(event.data.get("skill_note", ""))
        lines = []
        if note:
            lines.append(note)
        for raw in raw_lines[:display_limit]:
            text = _line_text(raw).strip()
            if text:
                lines.append(text)
        lead_item_name = str(event.data.get("lead_item_name", "") or "").strip()
        lead_delivery = str(event.data.get("lead_delivery", "") or "").strip().lower()
        if lead_item_name:
            if lead_delivery == "ground":
                lines.append(f"Dead drop: {lead_item_name} fell beside the relay.")
            else:
                lines.append(f"Dead drop: {lead_item_name} was added to your bag.")
        opportunity_title = str(event.data.get("lead_opportunity_title", "") or "").strip()
        opportunity_property_name = str(event.data.get("lead_opportunity_property_name", "") or "").strip()
        if opportunity_title:
            if opportunity_property_name:
                lines.append(f"Lead opened: {opportunity_title} at {opportunity_property_name}.")
            else:
                lines.append(f"Lead opened: {opportunity_title}.")
        if not lines:
            lines = [f"{prop_name} has nothing useful right now."]
        self._present_service_result(f"Intel: {prop_name}", lines, property_id=event.data.get("property_id"))

    def on_bank_transaction(self, event):
        if not self._event_matches_pending(event, channel="banking"):
            return
        title, lines = self._bank_transaction_lines(event)
        self._present_service_result(title, lines, property_id=event.data.get("property_id"))

    def on_banking_action_blocked(self, event):
        if not self._event_matches_pending(event, channel="banking"):
            return
        title, lines = self._bank_blocked_lines(event)
        property_id = event.data.get("property_id")
        if property_id is None and isinstance(self.pending_service_result, dict):
            property_id = self.pending_service_result.get("property_id")
        self._present_service_result(title, lines, property_id=property_id)

    def on_insurance_policy_purchased(self, event):
        if not self._event_matches_pending(event, channel="insurance"):
            return
        title, lines = self._insurance_purchased_lines(event)
        property_id = event.data.get("property_id")
        if property_id is None and isinstance(self.pending_service_result, dict):
            property_id = self.pending_service_result.get("property_id")
        self._present_service_result(title, lines, property_id=property_id)

    def on_insurance_action_blocked(self, event):
        if not self._event_matches_pending(event, channel="insurance"):
            return
        title, lines = self._insurance_blocked_lines(event)
        property_id = event.data.get("property_id")
        if property_id is None and isinstance(self.pending_service_result, dict):
            property_id = self.pending_service_result.get("property_id")
        self._present_service_result(title, lines, property_id=property_id)


__all__ = ["ServiceMenuSystem"]
