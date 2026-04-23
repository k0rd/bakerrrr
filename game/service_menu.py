from engine.events import Event
from engine.systems import System
from game.components import FinancialProfile, Inventory, PlayerAssets, Position
from game.finance_services import _nearest_property_with_finance_service
from game.player_businesses import (
    player_business_account_balance,
    player_business_customer_policy,
    player_business_customer_policy_label,
    player_business_hours_mode,
    player_business_hours_mode_label,
    player_business_next_customer_policy,
    player_business_next_hours_mode,
    player_business_set_customer_policy,
    player_business_set_hours_mode,
    player_business_status_snapshot,
    player_business_summary,
    player_owned_businesses_for_actor,
)
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import (
    finance_services_for_property as _finance_services_for_property,
    property_infrastructure_role as _property_infrastructure_role,
    property_is_storefront as _property_is_storefront,
    site_services_for_property as _site_services_for_property,
)
from game.service_runtime import (
    CASINO_KENO_DRAW_COUNT,
    CASINO_KENO_MAX_PICKS,
    CASINO_KENO_NUMBER_COUNT,
    CASINO_ROULETTE_NUMBER_MAX,
    CASINO_GAME_SERVICE_IDS,
    CASINO_PLINKO_LANE_COUNT,
    TRANSIT_SERVICE_IDS,
    _casino_apply_round_result,
    _casino_baccarat_normalize_session,
    _casino_baccarat_resolve,
    _casino_baccarat_start,
    _casino_blackjack_line,
    _casino_blackjack_total,
    _casino_cards_text,
    _casino_craps_normalize_session,
    _casino_craps_resolve,
    _casino_craps_start,
    _casino_game_profile,
    _casino_game_title,
    _casino_keno_draw,
    _casino_keno_normalize_session,
    _casino_keno_start,
    _casino_keno_toggle_pick,
    _casino_holdem_resolve,
    _casino_holdem_start,
    _casino_plinko_resolve,
    _casino_roulette_normalize_session,
    _casino_roulette_resolve,
    _casino_roulette_start,
    _casino_round_seed,
    _casino_slots_resolve,
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
    _vehicle_sale_offer_label,
    _vehicle_sale_offers,
    _vehicle_sale_quality,
    _vehicle_sale_quality_title,
    _vehicle_sale_stats_text,
)
from game.skills import skill_label as _skill_label


class ServiceMenuSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.pending_service_result = None
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("dialog_close_request", self.on_dialog_close_request)
        self.sim.events.subscribe("service_menu_execute_request", self.on_service_menu_execute_request)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("site_service_blocked", self.on_site_service_blocked)
        self.sim.events.subscribe("site_intel_report", self.on_site_intel_report)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("banking_action_blocked", self.on_banking_action_blocked)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("insurance_action_blocked", self.on_insurance_action_blocked)

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
        prop = self.sim.properties.get(property_id) if property_id is not None else None
        if isinstance(prop, dict):
            name = str(prop.get("name", prop.get("id", fallback))).strip()
            if name:
                return name
        name = str(pending.get("property_name", fallback)).strip()
        return name or fallback

    def _wallet_credits(self):
        assets = self._assets_for(self.player_eid)
        return int(getattr(assets, "credits", 0)) if assets else 0

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

    def _casino_session(self):
        state = self._dialog_ui_state()
        session = state.get("casino_session")
        return session if isinstance(session, dict) else None

    def _set_casino_session(self, session):
        state = self._dialog_ui_state()
        state["casino_session"] = dict(session) if isinstance(session, dict) else None

    def _clear_casino_session(self):
        state = self._dialog_ui_state()
        state["casino_session"] = None

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
        return True, credits

    def _open_casino_modal(self, prop, service, *, subtitle="", transcript=None, topics=None, hint="", mode="root", session=None):
        state = self._dialog_ui_state()
        prop_name = self._casino_prop_name(prop)
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id") if isinstance(prop, dict) else None,
            "title": f"{_casino_game_title(service)}: {prop_name}",
            "subtitle": str(subtitle or "").strip(),
            "transcript": list(transcript or ()),
            "topics": list(topics or ()),
            "selected_index": 0,
            "scroll": 0,
            "hint": str(hint or "").strip(),
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": str(mode or "root").strip() or "root",
            "casino_session": dict(session) if isinstance(session, dict) else None,
        })

    def _emit_casino_blocked(self, prop, service, reason, **data):
        prop_name = self._casino_prop_name(prop)
        self._begin_pending_service_result(
            channel="site",
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            property_name=prop_name,
            service=service,
        )
        payload = {
            "eid": self.player_eid,
            "property_id": prop.get("id") if isinstance(prop, dict) else None,
            "property_name": prop_name,
            "service": str(service or "").strip().lower(),
            "reason": str(reason or "blocked").strip().lower(),
        }
        payload.update(data)
        self.sim.emit(Event("site_service_blocked", **payload))

    def _emit_casino_round(self, prop, service, round_result, *, show_result=True):
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

    def _open_plinko_lane_menu(self, prop, service, wager):
        session = {
            "service": service,
            "property_id": prop.get("id"),
            "property_name": self._casino_prop_name(prop),
            "wager": int(wager),
            "stake": int(wager),
            "seed_token": self._casino_round_seed(prop, service, wager),
        }
        topics = [
            {"id": f"plinko:lane:{lane}", "label": f"Drop lane {lane + 1}"}
            for lane in range(CASINO_PLINKO_LANE_COUNT)
        ]
        transcript = [
            f"Choose a lane for {_credit_amount_label(wager)}.",
            "Center buckets pay best if the pegs keep the disc alive.",
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
        )

    def _open_twenty_one_table(self, prop, session):
        session = _casino_twenty_one_normalize_session(session)
        dealer_cards = list(session.get("dealer_cards", ()) or ()) if isinstance(session, dict) else []
        hands = list(session.get("hands", ()) or ()) if isinstance(session, dict) else []
        active_idx = int(session.get("active_hand_index", -1)) if isinstance(session, dict) else -1
        transcript = [
            f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is on the felt.",
            _casino_blackjack_line("Dealer", dealer_cards, hide_hole=True),
        ]
        for idx, hand in enumerate(hands):
            label = f"Hand {idx + 1}"
            if idx == active_idx:
                label += " *"
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
            f"Your hand: {_casino_cards_text(session.get('player_cards', ())) }".rstrip(),
            f"Flop: {_casino_cards_text(session.get('flop', ())) }".rstrip(),
            "Dealer: ?? ??",
            f"Call adds {_credit_amount_label(wager)} more; fold surrenders the ante.",
            "Dealer qualifies with pair of 4s or better. Straight or better pays an ante bonus.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ]
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

    def _open_video_poker_table(self, prop, session):
        session = _casino_video_poker_normalize_session(session)
        cards = list(session.get("cards", ()) or ()) if isinstance(session, dict) else []
        holds = list(session.get("holds", ()) or ()) if isinstance(session, dict) else []
        held_slots = [str(idx + 1) for idx, held in enumerate(holds) if held]
        transcript = [f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted."]
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
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        transcript.extend([
            f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted.",
            f"Mark up to {CASINO_KENO_MAX_PICKS} spots from 01-{CASINO_KENO_NUMBER_COUNT:02d}.",
            (
                f"Selected ({len(picks)}/{CASINO_KENO_MAX_PICKS}): "
                f"{' '.join(f'{number:02d}' for number in picks)}."
                if picks
                else f"Selected (0/{CASINO_KENO_MAX_PICKS}): none."
            ),
            f"The house will draw {CASINO_KENO_DRAW_COUNT} balls.",
            f"Wallet {_credit_amount_label(self._wallet_credits())}.",
        ])
        topics = [
            {
                "id": f"keno:toggle:{number}",
                "label": f"[{'X' if number in pick_set else ' '}] {number:02d}",
            }
            for number in range(1, CASINO_KENO_NUMBER_COUNT + 1)
        ]
        topics.append({"id": "keno:clear", "label": "Clear Ticket"})
        topics.append({"id": "keno:draw", "label": "Draw Ticket"})
        self._open_casino_modal(
            prop,
            "keno",
            subtitle="Mark your ticket",
            transcript=transcript,
            topics=topics,
            hint="Mark up to five numbers, then draw once. Esc forfeits the posted stake.",
            mode="casino:keno:ticket",
            session=session,
        )

    def _open_roulette_table(self, prop, session, *, notice=""):
        session = _casino_roulette_normalize_session(session)
        view = str(session.get("view", "board") or "board").strip().lower() if isinstance(session, dict) else "board"
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        transcript.append(f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted.")

        if view == "numbers":
            transcript.extend([
                "Straight-up board: pick one number from 00-36.",
                "Single number bets pay 35 to 1 plus the posted chip back.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": f"roulette:straight:{number}", "label": f"{number:02d} (x36 return)"}
                for number in range(0, CASINO_ROULETTE_NUMBER_MAX + 1)
            ]
            topics.append({"id": "roulette:back", "label": "Back to Outside Bets"})
            subtitle = "Straight-up board"
            hint = "Pick a single number for the spin. Esc forfeits the posted stake."
            mode = "casino:roulette:numbers"
        else:
            transcript.extend([
                "Outside board: colors, parity, ranges, dozens, and columns.",
                "Even-money bets return x2; dozens and columns return x3. Zero beats the outside board.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": "roulette:view:numbers", "label": "Straight Up Number (35:1)"},
                {"id": "roulette:red", "label": "Red (x2 return)"},
                {"id": "roulette:black", "label": "Black (x2 return)"},
                {"id": "roulette:odd", "label": "Odd (x2 return)"},
                {"id": "roulette:even", "label": "Even (x2 return)"},
                {"id": "roulette:low", "label": "1-18 (x2 return)"},
                {"id": "roulette:high", "label": "19-36 (x2 return)"},
                {"id": "roulette:dozen:1", "label": "1st Dozen 1-12 (x3 return)"},
                {"id": "roulette:dozen:2", "label": "2nd Dozen 13-24 (x3 return)"},
                {"id": "roulette:dozen:3", "label": "3rd Dozen 25-36 (x3 return)"},
                {"id": "roulette:column:1", "label": "Column 1 (x3 return)"},
                {"id": "roulette:column:2", "label": "Column 2 (x3 return)"},
                {"id": "roulette:column:3", "label": "Column 3 (x3 return)"},
            ]
            subtitle = "Place your chip"
            hint = "Choose a pocket or an outside section. Esc forfeits the posted stake."
            mode = "casino:roulette:board"

        self._open_casino_modal(
            prop,
            "roulette",
            subtitle=subtitle,
            transcript=transcript,
            topics=topics,
            hint=hint,
            mode=mode,
            session=session,
        )

    def _open_craps_table(self, prop, session, *, notice=""):
        session = _casino_craps_normalize_session(session)
        view = str(session.get("view", "layout") or "layout").strip().lower() if isinstance(session, dict) else "layout"
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        transcript.append(f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted.")
        wager = int(session.get("wager", 0))

        if view == "pass_odds":
            transcript.extend([
                "Back the pass line with extra odds if a point goes up.",
                "True odds pay 2:1 on 4/10, 3:2 on 5/9, and 6:5 on 6/8.",
                "Reserved odds chips are returned untouched when the come-out resolves before a point.",
                "Mixed-ratio pays are rounded to the nearest credit.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": f"craps:pass_odds:{mult}", "label": f"Pass + {mult}x Odds (+{_credit_amount_label(wager * mult)})"}
                for mult in (1, 2, 3)
            ]
            topics.append({"id": "craps:back", "label": "Back to Main Layout"})
            subtitle = "Pass odds"
            hint = "Choose how much odds action to tuck behind the pass line. Esc forfeits the posted base chip."
        elif view == "dont_pass_odds":
            transcript.extend([
                "Lay odds behind the don't pass once the point could go up.",
                "Lay odds win 1:2 on 4/10, 2:3 on 5/9, and 5:6 on 6/8.",
                "Reserved odds chips are returned untouched when the come-out resolves before a point.",
                "Mixed-ratio pays are rounded to the nearest credit.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": f"craps:dont_pass_odds:{mult}", "label": f"Don't Pass + {mult}x Odds (+{_credit_amount_label(wager * mult)})"}
                for mult in (1, 2, 3)
            ]
            topics.append({"id": "craps:back", "label": "Back to Main Layout"})
            subtitle = "Don't pass odds"
            hint = "Choose how much lay odds to park behind the don't pass line. Esc forfeits the posted base chip."
        elif view == "place":
            transcript.extend([
                "Place bets win if the chosen number lands before any 7.",
                "4/10 pay 9:5, 5/9 pay 7:5, and 6/8 pay 7:6.",
                "Mixed-ratio pays are rounded to the nearest credit.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": f"craps:place:{number}", "label": f"Place {number}"}
                for number in (4, 5, 6, 8, 9, 10)
            ]
            topics.append({"id": "craps:back", "label": "Back to Main Layout"})
            subtitle = "Place bets"
            hint = "Pick a place number and ride it against the seven. Esc forfeits the posted chip."
        elif view == "hardways":
            transcript.extend([
                "Hardways need doubles before an easy way of the same number or any 7.",
                "Hard 4/10 pay 7:1. Hard 6/8 pay 9:1.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": f"craps:hard:{number}", "label": f"Hard {number}"}
                for number in (4, 6, 8, 10)
            ]
            topics.append({"id": "craps:back", "label": "Back to Main Layout"})
            subtitle = "Hardways"
            hint = "Pick a hardway and sweat the doubles. Esc forfeits the posted chip."
        elif view == "props":
            transcript.extend([
                "Center-table props are one-roll shots with loud payoffs.",
                "2/12 pay 30:1, 3/11 pay 15:1, any craps pays 7:1, and any seven pays 4:1.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": "craps:prop:2", "label": "Snake Eyes 2 (x31 return)"},
                {"id": "craps:prop:3", "label": "Ace-Deuce 3 (x16 return)"},
                {"id": "craps:prop:11", "label": "Yo 11 (x16 return)"},
                {"id": "craps:prop:12", "label": "Boxcars 12 (x31 return)"},
                {"id": "craps:prop:any_craps", "label": "Any Craps (x8 return)"},
                {"id": "craps:prop:any_seven", "label": "Any Seven (x5 return)"},
                {"id": "craps:back", "label": "Back to Main Layout"},
            ]
            subtitle = "Prop bets"
            hint = "Take a one-roll prop shot. Esc forfeits the posted chip."
        else:
            transcript.extend([
                "Choose pass line, don't pass, or field before the shooter takes the dice.",
                "Pass line and don't pass can also be backed with odds. Place bets, hardways, and props are on side boards.",
                "Mixed-ratio pays are rounded to the nearest credit when the math lands between whole credits.",
                f"Wallet {_credit_amount_label(self._wallet_credits())}.",
            ])
            topics = [
                {"id": "craps:pass", "label": "Pass Line"},
                {"id": "craps:dont_pass", "label": "Don't Pass"},
                {"id": "craps:field", "label": "Field"},
                {"id": "craps:view:pass_odds", "label": "Pass Odds"},
                {"id": "craps:view:dont_pass_odds", "label": "Don't Pass Odds"},
                {"id": "craps:view:place", "label": "Place Bets"},
                {"id": "craps:view:hardways", "label": "Hardways"},
                {"id": "craps:view:props", "label": "Prop Bets"},
            ]
            subtitle = "Place your bet"
            hint = "Pick a line bet or open a side board. Esc forfeits the posted stake."

        self._open_casino_modal(
            prop,
            "craps",
            subtitle=subtitle,
            transcript=transcript,
            topics=topics,
            hint=hint,
            mode=f"casino:craps:{view}",
            session=session,
        )

    def _open_baccarat_table(self, prop, session, *, notice=""):
        session = _casino_baccarat_normalize_session(session)
        transcript = []
        notice = str(notice or "").strip()
        if notice:
            transcript.append(notice)
        transcript.extend([
            f"Stake {_credit_amount_label(session.get('stake', session.get('wager', 0)))} is posted.",
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
        )

    def _start_casino_round(self, prop, service, wager):
        wager = int(wager)
        prop_name = self._casino_prop_name(prop)
        profile = _casino_game_profile(service)
        valid_wagers = {int(amount) for amount in profile.get("bet_options", ())} if profile else set()
        if wager <= 0 or (valid_wagers and wager not in valid_wagers):
            self._emit_casino_blocked(prop, service, "invalid_wager", wager=wager)
            return

        if service == "slots":
            seed_token = self._casino_round_seed(prop, service, wager)
            self._emit_casino_round(prop, service, _casino_slots_resolve(seed_token, wager))
            return

        if service == "plinko":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            self._open_plinko_lane_menu(prop, service, wager)
            return

        if service == "video_poker":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _casino_video_poker_start(self._casino_round_seed(prop, service, wager), wager)
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
            session = _casino_keno_start(self._casino_round_seed(prop, service, wager), wager)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_keno_table(prop, session)
            return

        if service == "roulette":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _casino_roulette_start(self._casino_round_seed(prop, service, wager), wager)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_roulette_table(prop, session)
            return

        if service == "craps":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _casino_craps_start(self._casino_round_seed(prop, service, wager), wager)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_craps_table(prop, session)
            return

        if service == "baccarat":
            ok, credits = self._casino_commit_stake(wager)
            if not ok:
                self._emit_casino_blocked(prop, service, "no_credits", cost=wager, credits=credits, wager=wager)
                return
            session = _casino_baccarat_start(self._casino_round_seed(prop, service, wager), wager)
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
            session = _casino_three_card_poker_start(self._casino_round_seed(prop, service, wager), wager)
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
            session = _casino_twenty_one_start(self._casino_round_seed(prop, service, wager), wager)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            next_session, round_result = _casino_twenty_one_resolve(session, "start")
            if round_result:
                self._emit_casino_round(prop, service, round_result)
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
            session = _casino_holdem_start(self._casino_round_seed(prop, service, wager), wager)
            session.update({
                "property_id": prop.get("id"),
                "property_name": prop_name,
            })
            self._open_holdem_table(prop, session)
            return

        self._present_service_result("Casino", ["That game is not available right now."], property_id=prop.get("id"))

    def _handle_active_casino_option(self, prop, option_id):
        session = self._casino_session()
        if not session:
            return False
        if not isinstance(prop, dict):
            self._present_service_result("Casino", ["That table is not available right now."], property_id=prop.get("id") if isinstance(prop, dict) else None)
            return True

        service = str(session.get("service", "")).strip().lower()
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
            self._emit_casino_round(prop, service, round_result)
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
                self._present_service_result("Video Poker", ["That hand cannot be resolved cleanly right now."], property_id=prop.get("id"))
                return True
            self._emit_casino_round(prop, service, round_result)
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
                self._open_keno_table(prop, current, notice="The ticket could not be resolved cleanly. Try that draw again.")
                return True
            self._emit_casino_round(prop, service, round_result)
            return True

        if service == "roulette" and option_id == "roulette:view:numbers":
            current = _casino_roulette_normalize_session(session)
            if current:
                current["view"] = "numbers"
                self._open_roulette_table(prop, current)
            return True

        if service == "roulette" and option_id == "roulette:back":
            current = _casino_roulette_normalize_session(session)
            if current:
                current["view"] = "board"
                self._open_roulette_table(prop, current)
            return True

        if service == "roulette":
            current = _casino_roulette_normalize_session(session)
            bet_kind = ""
            bet_value = None
            if option_id in {"roulette:red", "roulette:black"}:
                bet_kind = "color"
                bet_value = option_id.rsplit(":", 1)[-1]
            elif option_id in {"roulette:odd", "roulette:even"}:
                bet_kind = "parity"
                bet_value = option_id.rsplit(":", 1)[-1]
            elif option_id in {"roulette:low", "roulette:high"}:
                bet_kind = "range"
                bet_value = option_id.rsplit(":", 1)[-1]
            elif option_id.startswith("roulette:dozen:"):
                bet_kind = "dozen"
                try:
                    bet_value = int(option_id.rsplit(":", 1)[-1])
                except (TypeError, ValueError):
                    bet_value = None
            elif option_id.startswith("roulette:column:"):
                bet_kind = "column"
                try:
                    bet_value = int(option_id.rsplit(":", 1)[-1])
                except (TypeError, ValueError):
                    bet_value = None
            elif option_id.startswith("roulette:straight:"):
                bet_kind = "straight"
                try:
                    bet_value = int(option_id.rsplit(":", 1)[-1])
                except (TypeError, ValueError):
                    bet_value = None
            if bet_kind:
                round_result = _casino_roulette_resolve(current, bet_kind, bet_value)
                if not round_result:
                    self._open_roulette_table(prop, current or session, notice="That bet could not be resolved cleanly. Try another spin.")
                    return True
                self._emit_casino_round(prop, service, round_result)
                return True

        if service == "craps" and option_id.startswith("craps:view:"):
            current = _casino_craps_normalize_session(session)
            if not current:
                self._present_service_result("Craps", ["That table is not available right now."], property_id=prop.get("id"))
                return True
            next_view = option_id.rsplit(":", 1)[-1]
            current["view"] = next_view
            self._open_craps_table(prop, current)
            return True

        if service == "craps" and option_id == "craps:back":
            current = _casino_craps_normalize_session(session)
            if current:
                current["view"] = "layout"
                self._open_craps_table(prop, current)
            return True

        if service == "craps":
            current = _casino_craps_normalize_session(session)
            if not current:
                self._present_service_result("Craps", ["That table is not available right now."], property_id=prop.get("id"))
                return True
            bet_kind = ""
            bet_value = None
            odds_extra = 0
            if option_id in {"craps:pass", "craps:dont_pass", "craps:field"}:
                bet_kind = option_id.rsplit(":", 1)[-1]
            elif option_id.startswith("craps:pass_odds:"):
                bet_kind = "pass_odds"
                try:
                    bet_value = max(1, int(option_id.rsplit(":", 1)[-1]))
                except (TypeError, ValueError):
                    bet_value = None
                odds_extra = int(current.get("wager", 0)) * int(bet_value or 0)
            elif option_id.startswith("craps:dont_pass_odds:"):
                bet_kind = "dont_pass_odds"
                try:
                    bet_value = max(1, int(option_id.rsplit(":", 1)[-1]))
                except (TypeError, ValueError):
                    bet_value = None
                odds_extra = int(current.get("wager", 0)) * int(bet_value or 0)
            elif option_id.startswith("craps:place:"):
                bet_kind = "place"
                try:
                    bet_value = int(option_id.rsplit(":", 1)[-1])
                except (TypeError, ValueError):
                    bet_value = None
            elif option_id.startswith("craps:hard:"):
                bet_kind = "hardway"
                try:
                    bet_value = int(option_id.rsplit(":", 1)[-1])
                except (TypeError, ValueError):
                    bet_value = None
            elif option_id.startswith("craps:prop:"):
                bet_kind = "prop"
                bet_value = option_id.split(":", 2)[-1]
            if bet_kind:
                if odds_extra > 0:
                    ok, credits = self._casino_commit_stake(odds_extra)
                    if not ok:
                        self._emit_casino_blocked(prop, service, "no_credits", cost=odds_extra, credits=credits, wager=int(current.get("wager", 0)))
                        return True
                    current["stake"] = int(current.get("stake", current.get("wager", 0))) + odds_extra
                round_result = _casino_craps_resolve(current, bet_kind, bet_value)
                if not round_result:
                    self._open_craps_table(prop, current, notice="That roll sequence could not be resolved cleanly. Try another shooter.")
                    return True
                self._emit_casino_round(prop, service, round_result)
                return True

        if service == "baccarat" and option_id in {"baccarat:player", "baccarat:banker", "baccarat:tie"}:
            current = _casino_baccarat_normalize_session(session)
            if not current:
                self._present_service_result("Baccarat", ["That shoe is not available right now."], property_id=prop.get("id"))
                return True
            bet_side = option_id.rsplit(":", 1)[-1]
            round_result = _casino_baccarat_resolve(current, bet_side)
            if not round_result:
                self._open_baccarat_table(prop, current, notice="That wager could not be resolved cleanly. Try another hand.")
                return True
            self._emit_casino_round(prop, service, round_result)
            return True

        if service == "three_card_poker" and option_id in {"three_card_poker:play", "three_card_poker:fold"}:
            current = _casino_three_card_poker_normalize_session(session)
            if not current:
                self._present_service_result("Three-Card Poker", ["That table is not available right now."], property_id=prop.get("id"))
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
                self._open_three_card_poker_table(prop, current, notice="That hand could not be resolved cleanly. Try another deal.")
                return True
            self._emit_casino_round(prop, service, round_result)
            return True

        if service == "twenty_one" and option_id in {"twenty_one:hit", "twenty_one:stand"}:
            action = "hit" if option_id.endswith(":hit") else "stand"
            next_session, round_result = _casino_twenty_one_resolve(session, action)
            if round_result:
                self._emit_casino_round(prop, service, round_result)
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
            if round_result:
                self._emit_casino_round(prop, service, round_result)
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
            self._emit_casino_round(prop, service, round_result)
            return True

        return False

    def _forfeit_active_casino_session(self):
        session = self._casino_session()
        if not isinstance(session, dict):
            return
        service = str(session.get("service", "")).strip().lower()
        if service not in {"plinko", "video_poker", "keno", "roulette", "craps", "baccarat", "three_card_poker", "twenty_one", "casino_holdem"}:
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
        open_roles = tuple(
            str(role).strip().lower()
            for role in tuple(snapshot.get("open_roles", ()) or ())
            if str(role).strip()
        )
        role_fit = dict(snapshot.get("role_fit", {})) if isinstance(snapshot.get("role_fit"), dict) else {}

        lines = [
            f"{business_name}: account {_credit_amount_label(account_balance)}.",
            f"Staffing: {staff_total}/{required_staff} total | managers {manager_count} | staff {staff_count}.",
        ]
        for role_name, fit in (("Manager", role_fit.get("manager")), ("Staff", role_fit.get("staff"))):
            fit_line = self._business_role_fit_line(role_name, fit)
            if fit_line:
                lines.append(fit_line)
        lines.append(f"Policy: {customer_policy_label}.")
        lines.append(f"Hours: {hours_mode_label} | {hours_text}.")
        lines.append(f"Status: {'open' if open_now else 'closed'} | {note}.")
        if open_roles:
            role_labels = ["manager" if role == "manager" else "staff" for role in open_roles]
            if len(role_labels) == 1:
                lines.append(f"Hiring: open {role_labels[0]} slot.")
            else:
                lines.append(f"Hiring: open {'/'.join(role_labels)} slots.")
        else:
            lines.append("Hiring: no immediate open slot.")
        if market_note:
            lines.append(f"Market: {market_note}.")

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
            f"{business_name} customer policy set to {label}.",
            detail,
        ]

    def _business_hours_result_lines(self, prop, result):
        business_name = str(prop.get("metadata", {}).get("business_name", prop.get("name", "Business"))).strip() or "Business"
        if not isinstance(result, dict):
            return [f"{business_name} hours could not be updated right now."]
        hours_mode = str(result.get("hours_mode", "")).strip()
        hours_label = player_business_hours_mode_label(hours_mode)
        hours_text = str(result.get("hours_text", "")).strip() or self._business_hours_text(result.get("opening_window"))
        return [
            f"{business_name} hours set to {hours_label}.",
            f"Open window: {hours_text}.",
        ]

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
                return f"{role_name} fit: {label}{coverage} | strengths {strength_text} | missing {weak_text}."
            return f"{role_name} fit: {label}{coverage} | missing {weak_text}."
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
        return options

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
        service = _storefront_service_profile(self.sim, prop)
        mode = str(service.get("mode", "")).strip().lower()
        if mode == "automated" or bool(service.get("fallback_self_serve")):
            return service
        return None

    def _service_menu_options(self, eid, prop, pos):
        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        if not access.can_use_services:
            return [], None

        options = []
        storefront_service = None
        if _property_is_storefront(prop):
            storefront_service = _storefront_service_profile(self.sim, prop)
            if storefront_service.get("available") and not self._machine_service_profile(prop):
                options.append({"id": "trade_buy", "label": _service_menu_option_label("trade_buy")})
                options.append({"id": "trade_sell", "label": _service_menu_option_label("trade_sell")})

        finance_services = set(_finance_services_for_property(prop))
        if "banking" in finance_services:
            options.append({"id": "banking", "label": _service_menu_option_label("banking")})
        if "insurance" in finance_services:
            options.append({"id": "insurance", "label": _service_menu_option_label("insurance")})

        for site_service in _site_services_for_property(prop):
            options.append({"id": site_service, "label": _service_menu_option_label(site_service)})

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
        wallet_credits = int(getattr(assets, "credits", 0)) if assets else 0
        bank_balance = int(getattr(profile, "bank_balance", 0)) if profile else 0
        options = self._bank_menu_options(self.player_eid, business_contexts=business_contexts)
        transcript = [
            f"Choose how much to move at {prop_name}.",
            f"Wallet {_credit_amount_label(wallet_credits)} | Bank {_credit_amount_label(bank_balance)}.",
        ]
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
                hours_text = str(summary.get("hours_text", "")).strip() or self._business_hours_text(summary.get("opening_window"))
                transcript.append(
                    f"{business_name}: account {_credit_amount_label(business_balance)} | staff {staff_total}/{required_staff} | {note}."
                )
                transcript.append(f"Policy {policy_label} | Hours {hours_label} ({hours_text}).")
            remaining_businesses = max(0, len(business_contexts) - 3)
            if remaining_businesses > 0:
                transcript.append(f"... and {remaining_businesses} more business account{'s' if remaining_businesses != 1 else ''}.")
        if not profile and not business_contexts:
            self._present_service_result(
                f"Banking: {prop_name}",
                ["No finance profile available."],
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
        state = self._dialog_ui_state()
        self._clear_pending_service_result()
        self._clear_casino_session()
        profile = _casino_game_profile(service)
        if not profile:
            self._present_service_result("Casino", ["That game is not available right now."], property_id=prop.get("id"))
            return

        prop_name = str(prop.get("name", prop.get("id", "Casino"))).strip() or "Casino"
        assets = self._assets_for(self.player_eid)
        wallet_credits = int(getattr(assets, "credits", 0)) if assets else 0
        wager_options = [
            {
                "id": f"{str(service).strip().lower()}:bet:{int(amount)}",
                "label": f"Bet {_credit_amount_label(amount)}",
            }
            for amount in profile.get("bet_options", ())
        ]
        transcript = [
            str(profile.get("prompt", "Choose a wager.")).strip() or "Choose a wager.",
            str(profile.get("note", "")).strip() or "Pick a stake and play a round.",
            f"Wallet {_credit_amount_label(wallet_credits)}.",
        ]

        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": prop.get("id"),
            "title": f"{_casino_game_title(service)}: {prop_name}",
            "subtitle": "Choose a wager",
            "transcript": transcript,
            "topics": wager_options,
            "selected_index": 0,
            "scroll": 0,
            "hint": "Pick a stake to play one round. Esc closes; Space clears result messages.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": f"casino:{str(service).strip().lower()}",
            "casino_session": None,
        })

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
            transcript.append("M opens the unattended machine directly.")
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
            "hint": "Pick a service. Staffed counters are routed here; M is for machines.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": machine_action,
            "service_menu_mode": "root",
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
        if service == "vending":
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            credits_spent = int(event.data.get("credits_spent", 0))
            return f"Vending: {prop_name}", [
                f"Bought {item_name} for {_credit_amount_label(credits_spent)}.",
                f"{item_name} drops into your bag.",
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
            gain_bits = []
            if hp_gain > 0:
                gain_bits.append(f"HP +{hp_gain}")
            if energy_gain > 0:
                gain_bits.append(f"E +{energy_gain}")
            if safety_gain > 0:
                gain_bits.append(f"S +{safety_gain}")
            if social_gain > 0:
                gain_bits.append(f"So +{social_gain}")
            lines = [
                f"{prop_name} gives you a safe place to steady up.",
                " ".join(gain_bits) if gain_bits else "You settle yourself and recover a little.",
            ]
            if time_advanced_ticks > 0:
                lines.append(f"You lay low for {_tick_duration_label(self.sim, time_advanced_ticks)}.")
            return f"Shelter: {prop_name}", lines
        if service == "rest":
            hp_gain = int(event.data.get("hp_gain", 0))
            energy_gain = int(event.data.get("energy_gain", 0))
            safety_gain = int(event.data.get("safety_gain", 0))
            social_gain = int(event.data.get("social_gain", 0))
            credits_spent = int(event.data.get("credits_spent", 0))
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0))
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
                lines.append(f"You sleep through {_tick_duration_label(self.sim, time_advanced_ticks)}.")
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
        return f"Service: {prop_name}", [f"{prop_name} provides {_site_service_label(service)}."]

    def _site_service_blocked_lines(self, event):
        service = str(event.data.get("service", "")).strip().lower()
        prop_name = str(event.data.get("property_name", self._pending_property_name("Service"))).strip() or self._pending_property_name("Service")
        reason = str(event.data.get("reason", "blocked")).strip().lower()
        title = f"{_casino_game_title(service)}: {prop_name}" if service in CASINO_GAME_SERVICE_IDS else f"Service: {prop_name}"
        if reason == "invalid_wager" and service in CASINO_GAME_SERVICE_IDS:
            return f"{_casino_game_title(service)}: {prop_name}", ["The house refuses that stake.", "Choose one of the posted wager sizes."]
        if reason == "invalid_round" and service in CASINO_GAME_SERVICE_IDS:
            return title, ["That hand cannot be resolved cleanly right now.", "Step away and try a fresh round."]
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
        if reason == "no_leads" and service == "intel":
            return f"Intel: {prop_name}", [f"{prop_name} has no fresh routes or leads right now."]
        if reason == "no_vehicle" and service == "fuel":
            return f"Fuel: {prop_name}", [f"{prop_name} can only refuel a vehicle you own or have set active."]
        if reason == "no_vehicle" and service == "repair":
            return f"Repair: {prop_name}", [f"{prop_name} can only work on a vehicle you own or have set active."]
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
        if reason == "no_credits" and service == "vending":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            return f"Vending: {prop_name}", [
                f"{item_name} costs {_credit_amount_label(cost)} here.",
                f"You only have {_credit_amount_label(credits)} on hand.",
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
        if reason == "no_credits":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            return title, [f"Need {_credit_amount_label(cost)} for this service.", f"You have {_credit_amount_label(credits)} on hand."]
        if reason == "no_space" and service in {"vehicle_sales_new", "vehicle_sales_used"}:
            return f"Vehicles: {prop_name}", ["There is no clear space nearby to place a vehicle."]
        if reason == "key_storage_full" and service in {"vehicle_sales_new", "vehicle_sales_used"}:
            return f"Vehicles: {prop_name}", ["You need a free inventory slot for the vehicle key."]
        if reason == "no_vehicle" and service == "vehicle_fetch":
            return f"Fetch: {prop_name}", [f"You do not own a vehicle for {prop_name} to retrieve."]
        return title, [f"{prop_name} cannot provide {_site_service_label(service)} right now."]

    def _bank_transaction_lines(self, event):
        provider_name = str(event.data.get("provider_name", self._pending_property_name("Banking"))).strip() or self._pending_property_name("Banking")
        kind = str(event.data.get("kind", "deposit")).strip().lower()
        account_kind = str(event.data.get("account_kind", "personal")).strip().lower() or "personal"
        amount = int(event.data.get("amount", 0))
        wallet = int(event.data.get("wallet_credits", 0))
        bank = int(event.data.get("bank_balance", 0))
        business_balance = int(event.data.get("business_balance", 0))
        business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
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
        title = f"Banking: {self._pending_property_name('Banking')}"
        if reason == "no_banking_service":
            return title, ["No banking service is nearby."]
        if reason == "no_business_account":
            return title, ["No owned business account is available."]
        if reason == "no_bank_balance":
            return title, ["Bank account is empty."]
        if reason == "missing_finance_profile":
            return title, ["No finance profile is available."]
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
            return title, ["Choose a non-zero banking amount."]
        return title, ["Banking action blocked."]

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
        title = f"Insurance: {self._pending_property_name('Insurance')}"
        if reason == "no_insurance_service":
            return title, ["No insurance provider is nearby."]
        if reason == "insufficient_funds":
            premium = int(event.data.get("premium", 0))
            credits = int(event.data.get("credits", 0))
            policy_name = str(event.data.get("policy_name", "policy")).strip() or "policy"
            return title, [f"Need {_credit_amount_label(premium)} for {policy_name}.", f"You have {_credit_amount_label(credits)} on hand."]
        if reason == "provider_no_products":
            return title, ["This provider has no policies to offer right now."]
        if reason == "no_offer":
            return title, ["No policy offer is available right now."]
        if reason == "missing_finance_profile":
            return title, ["No finance profile is available."]
        return title, ["Insurance action blocked."]

    def on_property_interact(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        if not isinstance(prop, dict):
            return
        infrastructure_role = _property_infrastructure_role(prop)
        if infrastructure_role in {"access_panel", "security_post"}:
            return

        pos = self._position_for(eid)
        if not pos:
            return

        options, storefront_service = self._service_menu_options(eid, prop, pos)
        if not options:
            return

        event.data["handled"] = True
        option_ids = [str(option.get("id", "")).strip().lower() for option in options]
        if infrastructure_role == "service_terminal" and option_ids == ["banking"]:
            self._open_banking_menu(prop)
            return
        self._open_service_menu(prop, options, storefront_service=storefront_service)

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
            self._present_service_result("Banking", ["No banking service is nearby."])
            return
        self._open_banking_menu(prop)

    def on_dialog_close_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        state = self._dialog_ui_state()
        if str(state.get("kind", "")).strip().lower() == "service_menu":
            if self._casino_session() and not bool(state.get("close_pending")):
                self._forfeit_active_casino_session()
            self._close_service_menu()
            return
        self._clear_pending_service_result()

    def on_service_menu_execute_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        state = self._dialog_ui_state()
        if not state.get("open") or str(state.get("kind", "")).strip().lower() != "service_menu":
            return

        option_id = str(event.data.get("option_id", "") or "").strip().lower()
        property_id = event.data.get("property_id") or state.get("property_id")
        if not option_id or not property_id:
            return

        prop = self.sim.properties.get(property_id)
        if option_id == "trade_buy":
            self._close_service_menu()
            self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="buy", property_id=property_id))
            return
        if option_id == "trade_sell":
            self._close_service_menu()
            self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="sell", property_id=property_id))
            return
        if option_id == "banking":
            if isinstance(prop, dict):
                self._open_banking_menu(prop)
            else:
                self._present_service_result("Banking", ["No banking service is available right now."])
            return
        if option_id in TRANSIT_SERVICE_IDS:
            if isinstance(prop, dict):
                self._open_transit_menu(prop, option_id)
            else:
                self._present_service_result(_transit_service_title(option_id), ["That transit service is not available right now."])
            return
        if option_id in {"vehicle_sales_new", "vehicle_sales_used"}:
            if isinstance(prop, dict):
                self._open_vehicle_sale_menu(prop, "new" if option_id == "vehicle_sales_new" else "used")
            else:
                self._present_service_result("Vehicles", ["That vehicle service is not available right now."])
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
            title = _transit_service_title(transit_service)
            if not isinstance(prop, dict):
                self._present_service_result(title, ["That transit destination is not available right now."])
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
                self._present_service_result(title, ["That transit destination could not be resolved cleanly."])
                return
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
                self._present_service_result("Vehicles", ["That vehicle offering is not available right now."])
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
                self._present_service_result("Banking", ["No banking service is available right now."])
                return
            transfer_kind = str(parts[1]).strip().lower()
            try:
                amount = int(parts[2])
            except (TypeError, ValueError):
                amount = 0
            if transfer_kind not in {"deposit", "withdraw"} or amount <= 0:
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
        if option_id.startswith("banking_business:"):
            parts = option_id.split(":")
            if len(parts) != 4:
                self._present_service_result("Banking", ["That business banking option is invalid."])
                return
            if not isinstance(prop, dict):
                self._present_service_result("Banking", ["No banking service is available right now."])
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
            business_prop = self.sim.properties.get(business_property_id)
            if not isinstance(business_prop, dict):
                self._present_service_result("Business status", ["That business is not available right now."])
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
            business_prop = self.sim.properties.get(business_property_id)
            if not isinstance(business_prop, dict):
                self._present_service_result("Business policy", ["That business is not available right now."])
                return
            policy = player_business_set_customer_policy(business_prop, next_policy)
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
            business_prop = self.sim.properties.get(business_property_id)
            if not isinstance(business_prop, dict):
                self._present_service_result("Business hours", ["That business is not available right now."])
                return
            result = player_business_set_hours_mode(self.sim, business_prop, next_mode)
            business_name = str(business_prop.get("metadata", {}).get("business_name", business_prop.get("name", "Business"))).strip() or "Business"
            self._present_service_result(
                f"Business hours: {business_name}",
                self._business_hours_result_lines(business_prop, result),
                property_id=property_id,
            )
            return
        if option_id == "insurance":
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
                self._present_service_result("Casino", ["That table is not available right now."])
            return
        for service in CASINO_GAME_SERVICE_IDS:
            prefix = f"{service}:bet:"
            if not option_id.startswith(prefix):
                continue
            if not isinstance(prop, dict):
                self._present_service_result(_casino_game_title(service), ["That table is not available right now."])
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
