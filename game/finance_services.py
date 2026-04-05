import random

from engine.events import Event
from engine.systems import System
from game.components import AI, ContactLedger, CreatureIdentity, FinancialProfile, Inventory, PlayerAssets, Position, Vitality
from game.player_businesses import (
    player_owned_businesses_for_actor as _player_owned_businesses_for_actor,
    player_business_state as _player_business_state,
    property_supports_player_business as _property_supports_player_business,
)
from game.items import ITEM_CATALOG, item_display_name
from game.organization_reputation import organization_terms_for_property as _organization_terms_for_property
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import (
    finance_services_for_property as _finance_services_for_property,
    property_distance as _property_distance,
    property_infrastructure_role as _property_infrastructure_role,
    property_is_storefront as _property_is_storefront,
)
from game.run_pressure import pressure_snapshot as _pressure_snapshot
from game.skills import insurance_skill_terms as _insurance_skill_terms


def _finance_property_contact_entry(sim, viewer_eid, prop):
    if viewer_eid is None or not prop:
        return None

    ledger = sim.ecs.get(ContactLedger).get(viewer_eid)
    if not ledger:
        return None
    return ledger.property_entry(prop["id"])


def _finance_entity_display_name(sim, eid, title_case=False):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    ai = sim.ecs.get(AI).get(eid)

    if identity:
        label = str(identity.display_name()).replace("_", " ").strip()
    elif ai:
        label = str(ai.role or "entity").replace("_", " ").strip()
    else:
        label = "entity"

    if not label:
        label = "entity"
    return label.title() if title_case else label


def _insurance_contact_terms(sim, viewer_eid, prop):
    entry = _finance_property_contact_entry(sim, viewer_eid, prop)
    pressure = _pressure_snapshot(sim)
    effects = pressure.get("effects", {})
    pressure_tier = str(pressure.get("tier", "low")).strip().lower()
    pressure_mult = float(effects.get("insurance_premium_mult", 1.0))
    skill_terms = _insurance_skill_terms(sim, viewer_eid)
    org_terms = _organization_terms_for_property(sim, prop)
    note_bits = []
    skill_note = str(skill_terms.get("note", "")).strip()
    if skill_note:
        note_bits.append(skill_note)
    org_note = str(org_terms.get("note", "")).strip()
    if org_note:
        note_bits.append(org_note)
    base = {
        "premium_mult": max(
            0.75,
            min(
                1.8,
                pressure_mult
                * float(skill_terms.get("premium_mult", 1.0))
                * float(org_terms.get("premium_mult", 1.0)),
            ),
        ),
        "source_eid": None,
        "note": "",
    }
    if pressure_tier in {"medium", "high"}:
        note_bits.append(f"city attention {pressure_tier}")
    if note_bits:
        base["note"] = "; ".join(note_bits)
    if not entry:
        return base

    benefits = set(entry.get("benefits", ()))
    if "insurance_discount" not in benefits:
        return base

    standing = max(0.0, min(1.0, float(entry.get("standing", 0.0))))
    source_eid = entry.get("source_eid")
    premium_mult = max(0.82, 1.0 - (0.04 + (standing * 0.1)))
    premium_mult = max(
        0.75,
        min(
            1.8,
            premium_mult
            * pressure_mult
            * float(skill_terms.get("premium_mult", 1.0))
            * float(org_terms.get("premium_mult", 1.0)),
        ),
    )
    source_name = _finance_entity_display_name(sim, source_eid, title_case=True) if source_eid is not None else "Local contact"
    note_bits = [f"{source_name}: policy rate eased"]
    if skill_note:
        note_bits.append(skill_note)
    if org_note:
        note_bits.append(org_note)
    if pressure_tier in {"medium", "high"}:
        note_bits.append(f"attention {pressure_tier}")
    return {
        "premium_mult": premium_mult,
        "source_eid": source_eid,
        "note": "; ".join(note_bits),
    }


def _nearest_property_with_finance_service(sim, viewer_eid, pos, service, radius=2):
    if sim is None or pos is None:
        return None

    nearby = sim.properties_in_radius(pos.x, pos.y, pos.z, r=radius)
    if not nearby:
        return None

    candidates = []
    for prop in nearby:
        services = _finance_services_for_property(prop)
        if service not in services:
            continue
        access = _evaluate_property_access(
            sim,
            viewer_eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        if not access.can_use_services:
            continue
        dist = _property_distance(pos.x, pos.y, prop)
        candidates.append((dist, prop))

    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0])
    return candidates[0][1]


class FinanceSystem(System):

    ITEM_LOSS_BASE_CHANCE = 0.14
    ITEM_LOSS_PER_DOWNED = 0.04
    ITEM_LOSS_MAX_CHANCE = 0.42
    POLICY_RENEW_NOTICE_TICKS = 600

    BANK_PRODUCTS = (
        {
            "policy_key": "money",
            "tier": "bank_basic",
            "quality": 1,
            "name": "Bank Loss Shield",
            "premium": 26,
            "duration_ticks": 7200,
            "coverage_ratio": 0.65,
            "claim_pool": 180,
            "max_claim_per_event": 58,
            "channel": "banking",
        },
        {
            "policy_key": "item",
            "tier": "bank_locker",
            "quality": 1,
            "name": "Locker Rider",
            "premium": 22,
            "duration_ticks": 7200,
            "item_save_charges": 2,
            "channel": "banking",
        },
    )

    INSURANCE_PRODUCTS = (
        {
            "policy_key": "money",
            "tier": "agency_plus",
            "quality": 2,
            "name": "Wallet Guard Plus",
            "premium": 34,
            "duration_ticks": 8400,
            "coverage_ratio": 0.82,
            "claim_pool": 300,
            "max_claim_per_event": 90,
            "channel": "insurance",
        },
        {
            "policy_key": "item",
            "tier": "agency_item",
            "quality": 2,
            "name": "Cargo Guard",
            "premium": 28,
            "duration_ticks": 8400,
            "item_save_charges": 4,
            "channel": "insurance",
        },
        {
            "policy_key": "medical",
            "tier": "agency_medical",
            "quality": 2,
            "name": "Trauma Plan",
            "premium": 24,
            "duration_ticks": 4800,
            "medical_bonus_hp": 14,
            "channel": "insurance",
        },
    )

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.rng = random.Random(f"{sim.seed}:finance")
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("finance_service_request", self.on_finance_service_request)
        self.sim.events.subscribe("player_downed", self.on_player_downed)

    def _assets_for(self, eid):
        return self.sim.ecs.get(PlayerAssets).get(eid)

    def _profile_for(self, eid):
        return self.sim.ecs.get(FinancialProfile).get(eid)

    def _position_for(self, eid):
        return self.sim.ecs.get(Position).get(eid)

    def _insurance_terms(self, eid, prop):
        return _insurance_contact_terms(self.sim, eid, prop)

    def _active_policy(self, profile, policy_key):
        if not profile:
            return None
        policy = profile.policies.get(policy_key)
        if not policy:
            return None
        if int(policy.get("expires_tick", 0)) <= self.sim.tick:
            return None
        return policy

    def _policy_needs_renew(self, policy):
        if not policy:
            return True

        expires_tick = int(policy.get("expires_tick", 0))
        if expires_tick <= self.sim.tick + int(self.POLICY_RENEW_NOTICE_TICKS):
            return True

        key = policy.get("policy_key")
        if key == "money":
            remaining_pool = int(policy.get("remaining_pool", 0))
            max_claim = int(policy.get("max_claim_per_event", 0))
            if max_claim > 0 and remaining_pool < max_claim:
                return True
        elif key == "item":
            if int(policy.get("item_save_charges", 0)) <= 0:
                return True
        return False

    def _nearest_property_with_service(self, pos, service, radius=2):
        return _nearest_property_with_finance_service(
            self.sim,
            self.player_eid,
            pos,
            service,
            radius=radius,
        )

    def _preferred_property_service(self, eid, prop):
        services = set(_finance_services_for_property(prop))
        if not services:
            return None

        if "insurance" in services:
            profile = self._profile_for(eid)
            offers = self._offer_book_for_property(prop)
            if offers and self._insurance_attention_needed(profile, offers):
                return "insurance"

        if "banking" in services:
            return "banking"
        if "insurance" in services:
            return "insurance"
        return None

    def _offer_book_for_property(self, prop):
        services = set(_finance_services_for_property(prop))
        by_policy = {}

        if "banking" in services:
            for product in self.BANK_PRODUCTS:
                key = product["policy_key"]
                current = by_policy.get(key)
                if not current or product["quality"] > current["quality"]:
                    by_policy[key] = dict(product)

        if "insurance" in services:
            for product in self.INSURANCE_PRODUCTS:
                key = product["policy_key"]
                current = by_policy.get(key)
                if not current or product["quality"] > current["quality"]:
                    by_policy[key] = dict(product)

        ordered = []
        for key in ("money", "item", "medical"):
            if key in by_policy:
                ordered.append(by_policy[key])
        return ordered

    def _pick_offer(self, profile, offers):
        by_key = {offer["policy_key"]: offer for offer in offers}
        for policy_key in ("money", "item", "medical"):
            offer = by_key.get(policy_key)
            if not offer:
                continue

            active = self._active_policy(profile, policy_key)
            if not active:
                return offer

            if int(active.get("quality", 0)) < int(offer.get("quality", 0)):
                return offer

            if self._policy_needs_renew(active):
                return offer

        if not offers:
            return None
        return min(
            offers,
            key=lambda offer: int(profile.policies.get(offer["policy_key"], {}).get("expires_tick", 0)),
        )

    def _insurance_attention_needed(self, profile, offers):
        if not profile:
            return bool(offers)

        for offer in offers:
            policy_key = offer.get("policy_key")
            if not policy_key:
                continue
            active = self._active_policy(profile, policy_key)
            if not active:
                return True
            if int(active.get("quality", 0)) < int(offer.get("quality", 0)):
                return True
            if self._policy_needs_renew(active):
                return True
        return False

    def _buy_or_renew_policy(self, eid, provider_prop):
        assets = self._assets_for(eid)
        profile = self._profile_for(eid)
        if not assets or not profile:
            self.sim.emit(Event("insurance_action_blocked", eid=eid, reason="missing_finance_profile"))
            return

        offers = self._offer_book_for_property(provider_prop)
        if not offers:
            self.sim.emit(
                Event(
                    "insurance_action_blocked",
                    eid=eid,
                    reason="provider_no_products",
                    property_id=provider_prop["id"],
                )
            )
            return

        offer = self._pick_offer(profile, offers)
        if not offer:
            self.sim.emit(Event("insurance_action_blocked", eid=eid, reason="no_offer"))
            return

        terms = self._insurance_terms(eid, provider_prop)
        base_premium = int(max(1, offer["premium"]))
        premium = max(1, int(round(base_premium * float(terms.get("premium_mult", 1.0)))))
        if assets.credits < premium:
            self.sim.emit(Event(
                "insurance_action_blocked",
                eid=eid,
                reason="insufficient_funds",
                premium=premium,
                credits=assets.credits,
                policy_name=offer["name"],
            ))
            return

        assets.credits -= premium
        policy_key = offer["policy_key"]
        policy = {
            "policy_key": policy_key,
            "tier": offer["tier"],
            "quality": int(offer["quality"]),
            "name": offer["name"],
            "premium": premium,
            "channel": offer.get("channel", "insurance"),
            "provider_property_id": provider_prop["id"],
            "provider_name": provider_prop.get("name", provider_prop["id"]),
            "purchased_tick": self.sim.tick,
            "expires_tick": self.sim.tick + int(max(20, offer.get("duration_ticks", 120))),
            "remaining_pool": int(max(0, offer.get("claim_pool", 0))),
            "max_claim_per_event": int(max(0, offer.get("max_claim_per_event", 0))),
            "coverage_ratio": float(max(0.0, min(1.0, offer.get("coverage_ratio", 0.0)))),
            "item_save_charges": int(max(0, offer.get("item_save_charges", 0))),
            "medical_bonus_hp": int(max(0, offer.get("medical_bonus_hp", 0))),
            "expired_notified": False,
        }

        replaced = policy_key in profile.policies
        profile.policies[policy_key] = policy

        self.sim.emit(Event(
            "insurance_policy_purchased",
            eid=eid,
            property_id=provider_prop["id"],
            provider_name=provider_prop.get("name", provider_prop["id"]),
            policy_key=policy_key,
            policy_name=policy["name"],
            premium=premium,
            base_premium=base_premium,
            expires_tick=policy["expires_tick"],
            duration_ticks=int(max(20, offer.get("duration_ticks", 120))),
            replaced=replaced,
            channel=policy["channel"],
            contact_source_eid=terms.get("source_eid"),
            contact_note=terms.get("note", ""),
        ))

    def _bank_transaction(self, eid, provider_prop, *, kind=None, amount=None, account_kind=None, business_property_id=None):
        assets = self._assets_for(eid)
        if not assets:
            self.sim.emit(Event("banking_action_blocked", eid=eid, reason="missing_finance_profile"))
            return

        requested_kind = str(kind or "").strip().lower()
        account_kind = str(account_kind or "personal").strip().lower() or "personal"
        try:
            requested_amount = int(amount)
        except (TypeError, ValueError):
            requested_amount = 0

        if account_kind == "business":
            business_prop = None
            if business_property_id:
                business_prop = self.sim.properties.get(business_property_id)
            if not _property_supports_player_business(business_prop):
                pos = self._position_for(eid)
                owned_businesses = _player_owned_businesses_for_actor(self.sim, eid, pos=pos)
                business_prop = owned_businesses[0] if owned_businesses else None
            if not _property_supports_player_business(business_prop) or business_prop.get("owner_eid") != eid:
                self.sim.emit(Event(
                    "banking_action_blocked",
                    eid=eid,
                    property_id=provider_prop["id"],
                    reason="no_business_account",
                ))
                return

            state = _player_business_state(business_prop, create=True)
            business_name = str(business_prop.get("metadata", {}).get("business_name", business_prop.get("name", "Business"))).strip() or "Business"
            current_balance = int(state.get("account_balance", 0))
            requested_amount = max(0, requested_amount)
            if requested_amount <= 0:
                self.sim.emit(Event(
                    "banking_action_blocked",
                    eid=eid,
                    property_id=provider_prop["id"],
                    reason="invalid_amount",
                    kind=requested_kind,
                    amount=requested_amount,
                    account_kind="business",
                    business_property_id=business_prop.get("id"),
                    business_name=business_name,
                ))
                return
            if requested_kind not in {"deposit", "withdraw"}:
                self.sim.emit(Event(
                    "banking_action_blocked",
                    eid=eid,
                    property_id=provider_prop["id"],
                    reason="invalid_amount",
                    kind=requested_kind,
                    amount=requested_amount,
                    account_kind="business",
                    business_property_id=business_prop.get("id"),
                    business_name=business_name,
                ))
                return

            if requested_kind == "withdraw":
                if current_balance < requested_amount:
                    self.sim.emit(Event(
                        "banking_action_blocked",
                        eid=eid,
                        property_id=provider_prop["id"],
                        reason="insufficient_business_balance",
                        kind=requested_kind,
                        amount=requested_amount,
                        account_kind="business",
                        business_property_id=business_prop.get("id"),
                        business_name=business_name,
                        business_balance=current_balance,
                    ))
                    return
                state["account_balance"] = max(0, current_balance - requested_amount)
                assets.credits += requested_amount
                self.sim.emit(Event(
                    "bank_transaction",
                    eid=eid,
                    property_id=provider_prop["id"],
                    provider_name=provider_prop.get("name", provider_prop["id"]),
                    kind="withdraw",
                    amount=requested_amount,
                    wallet_credits=assets.credits,
                    bank_balance=int(getattr(self._profile_for(eid), "bank_balance", 0)) if self._profile_for(eid) else 0,
                    account_kind="business",
                    business_property_id=business_prop.get("id"),
                    business_name=business_name,
                    business_balance=int(state.get("account_balance", 0)),
                ))
                return

            if assets.credits < requested_amount:
                self.sim.emit(Event(
                    "banking_action_blocked",
                    eid=eid,
                    property_id=provider_prop["id"],
                    reason="insufficient_wallet_funds",
                    kind=requested_kind,
                    amount=requested_amount,
                    credits=assets.credits,
                    account_kind="business",
                    business_property_id=business_prop.get("id"),
                    business_name=business_name,
                ))
                return
            assets.credits -= requested_amount
            state["account_balance"] = current_balance + requested_amount
            self.sim.emit(Event(
                "bank_transaction",
                eid=eid,
                property_id=provider_prop["id"],
                provider_name=provider_prop.get("name", provider_prop["id"]),
                kind="deposit",
                amount=requested_amount,
                wallet_credits=assets.credits,
                bank_balance=int(getattr(self._profile_for(eid), "bank_balance", 0)) if self._profile_for(eid) else 0,
                account_kind="business",
                business_property_id=business_prop.get("id"),
                business_name=business_name,
                business_balance=int(state.get("account_balance", 0)),
            ))
            return

        profile = self._profile_for(eid)
        if not profile:
            self.sim.emit(Event("banking_action_blocked", eid=eid, reason="missing_finance_profile"))
            return

        if requested_kind in {"deposit", "withdraw"}:
            requested_amount = max(0, requested_amount)
            if requested_amount <= 0:
                self.sim.emit(Event(
                    "banking_action_blocked",
                    eid=eid,
                    reason="invalid_amount",
                    kind=requested_kind,
                    amount=requested_amount,
                ))
                return
            if requested_kind == "withdraw":
                if profile.bank_balance < requested_amount:
                    self.sim.emit(Event(
                        "banking_action_blocked",
                        eid=eid,
                        reason="insufficient_bank_balance",
                        kind=requested_kind,
                        amount=requested_amount,
                        bank_balance=profile.bank_balance,
                    ))
                    return
                profile.bank_balance -= requested_amount
                assets.credits += requested_amount
                self.sim.emit(Event(
                    "bank_transaction",
                    eid=eid,
                    property_id=provider_prop["id"],
                    provider_name=provider_prop.get("name", provider_prop["id"]),
                    kind="withdraw",
                    amount=requested_amount,
                    wallet_credits=assets.credits,
                    bank_balance=profile.bank_balance,
                    account_kind="personal",
                ))
                return

            if assets.credits < requested_amount:
                self.sim.emit(Event(
                    "banking_action_blocked",
                    eid=eid,
                    reason="insufficient_wallet_funds",
                    kind=requested_kind,
                    amount=requested_amount,
                    credits=assets.credits,
                ))
                return
            assets.credits -= requested_amount
            profile.bank_balance += requested_amount
            self.sim.emit(Event(
                "bank_transaction",
                eid=eid,
                property_id=provider_prop["id"],
                provider_name=provider_prop.get("name", provider_prop["id"]),
                kind="deposit",
                amount=requested_amount,
                wallet_credits=assets.credits,
                bank_balance=profile.bank_balance,
                account_kind="personal",
            ))
            return

        floor_target = max(0, profile.wallet_buffer)
        low_wallet = assets.credits < max(18, floor_target // 2)

        if low_wallet and profile.bank_balance > 0:
            amount = min(profile.withdraw_step, profile.bank_balance)
            if amount <= 0:
                self.sim.emit(Event("banking_action_blocked", eid=eid, reason="no_bank_balance"))
                return
            profile.bank_balance -= amount
            assets.credits += amount
            self.sim.emit(Event(
                "bank_transaction",
                eid=eid,
                property_id=provider_prop["id"],
                provider_name=provider_prop.get("name", provider_prop["id"]),
                kind="withdraw",
                amount=amount,
                wallet_credits=assets.credits,
                bank_balance=profile.bank_balance,
                account_kind="personal",
            ))
            return

        if assets.credits > floor_target + 10:
            amount = min(profile.deposit_step, assets.credits - floor_target)
            if amount <= 0:
                self.sim.emit(Event("banking_action_blocked", eid=eid, reason="deposit_not_needed"))
                return
            assets.credits -= amount
            profile.bank_balance += amount
            self.sim.emit(Event(
                "bank_transaction",
                eid=eid,
                property_id=provider_prop["id"],
                provider_name=provider_prop.get("name", provider_prop["id"]),
                kind="deposit",
                amount=amount,
                wallet_credits=assets.credits,
                bank_balance=profile.bank_balance,
                account_kind="personal",
            ))
            return

        if profile.bank_balance > 0:
            amount = min(max(1, profile.withdraw_step // 2), profile.bank_balance)
            profile.bank_balance -= amount
            assets.credits += amount
            self.sim.emit(Event(
                "bank_transaction",
                eid=eid,
                property_id=provider_prop["id"],
                provider_name=provider_prop.get("name", provider_prop["id"]),
                kind="withdraw",
                amount=amount,
                wallet_credits=assets.credits,
                bank_balance=profile.bank_balance,
                account_kind="personal",
            ))
            return

        self.sim.emit(Event("banking_action_blocked", eid=eid, reason="no_funds_to_manage"))

    def _try_item_loss_roll(self, eid):
        profile = self._profile_for(eid)
        inventory = self.sim.ecs.get(Inventory).get(eid)
        position = self._position_for(eid)
        vitalities = self.sim.ecs.get(Vitality)
        vitality = vitalities.get(eid)

        if not profile or not inventory or not inventory.items or not position:
            return

        downed_count = max(1, int(vitality.downed_count)) if vitality else 1
        loss_chance = min(
            self.ITEM_LOSS_MAX_CHANCE,
            self.ITEM_LOSS_BASE_CHANCE + (self.ITEM_LOSS_PER_DOWNED * max(0, downed_count - 1)),
        )
        if self.rng.random() > loss_chance:
            return

        item_policy = self._active_policy(profile, "item")
        if item_policy and int(item_policy.get("item_save_charges", 0)) > 0:
            item_policy["item_save_charges"] = max(0, int(item_policy["item_save_charges"]) - 1)
            self.sim.emit(Event(
                "insurance_item_saved",
                eid=eid,
                policy_name=item_policy.get("name", "item policy"),
                charges_left=int(item_policy.get("item_save_charges", 0)),
            ))
            return

        victim_entry = self.rng.choice(list(inventory.items))
        removed = inventory.remove_item(instance_id=victim_entry["instance_id"], quantity=1)
        if not removed:
            return

        item_id = removed["item_id"]
        item_name = item_display_name(item_id, metadata=removed.get("metadata"), item_catalog=ITEM_CATALOG)
        metadata = dict(removed.get("metadata") or {})
        metadata["lost_on_downed"] = True

        self.sim.register_ground_item(
            item_id=item_id,
            x=position.x,
            y=position.y,
            z=position.z,
            quantity=removed.get("quantity", 1),
            owner_eid=None,
            owner_tag="unowned",
            instance_id=removed.get("instance_id"),
            metadata=metadata,
        )

        self.sim.emit(Event(
            "downed_item_lost",
            eid=eid,
            item_id=item_id,
            item_name=item_name,
            quantity=removed.get("quantity", 1),
            x=position.x,
            y=position.y,
            z=position.z,
        ))

    def _apply_money_claim(self, event):
        eid = event.data.get("target_eid")
        if eid != self.player_eid:
            return

        profile = self._profile_for(eid)
        assets = self._assets_for(eid)
        if not profile or not assets:
            return

        penalty = int(max(0, event.data.get("credits_penalty", 0)))
        if penalty <= 0:
            return

        policy = self._active_policy(profile, "money")
        if not policy:
            return

        coverage = float(max(0.0, min(1.0, policy.get("coverage_ratio", 0.0))))
        remaining_pool = int(max(0, policy.get("remaining_pool", 0)))
        max_claim = int(max(0, policy.get("max_claim_per_event", 0)))
        if coverage <= 0.0 or remaining_pool <= 0:
            self.sim.emit(Event(
                "insurance_claim_blocked",
                eid=eid,
                policy_key="money",
                policy_name=policy.get("name", "money policy"),
                reason="policy_depleted",
            ))
            return

        payout = int(round(penalty * coverage))
        if max_claim > 0:
            payout = min(payout, max_claim)
        payout = min(payout, remaining_pool)
        payout = max(0, payout)
        if payout <= 0:
            self.sim.emit(Event(
                "insurance_claim_blocked",
                eid=eid,
                policy_key="money",
                policy_name=policy.get("name", "money policy"),
                reason="claim_zero",
            ))
            return

        assets.credits += payout
        policy["remaining_pool"] = max(0, remaining_pool - payout)
        profile.total_claims_paid += payout
        profile.claim_count += 1

        self.sim.emit(Event(
            "insurance_claim_paid",
            eid=eid,
            policy_key="money",
            policy_name=policy.get("name", "money policy"),
            payout=payout,
            penalty=penalty,
            remaining_pool=policy["remaining_pool"],
        ))

    def _apply_medical_claim(self, event):
        eid = event.data.get("target_eid")
        if eid != self.player_eid:
            return

        profile = self._profile_for(eid)
        if not profile:
            return

        policy = self._active_policy(profile, "medical")
        if not policy:
            return

        bonus = int(max(0, policy.get("medical_bonus_hp", 0)))
        if bonus <= 0:
            return

        vitality = self.sim.ecs.get(Vitality).get(eid)
        if not vitality:
            return

        before = vitality.hp
        after = min(vitality.max_hp, before + bonus)
        gained = after - before
        if gained <= 0:
            return

        vitality.hp = after
        self.sim.emit(Event(
            "insurance_medical_boost",
            eid=eid,
            policy_key="medical",
            policy_name=policy.get("name", "medical policy"),
            hp_bonus=gained,
            hp=after,
            max_hp=vitality.max_hp,
        ))

    def on_player_downed(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        self._apply_money_claim(event)
        self._apply_medical_claim(event)
        self._try_item_loss_roll(self.player_eid)

    def on_player_action(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return

        action = event.data.get("action")
        if action not in {"banking", "insurance"}:
            return

        pos = self._position_for(eid)
        if not pos:
            return

        if action == "banking":
            provider = self._nearest_property_with_service(pos, "banking", radius=2)
            if not provider:
                self.sim.emit(Event("banking_action_blocked", eid=eid, reason="no_banking_service"))
                return
            self._bank_transaction(eid, provider)
            return

        provider = self._nearest_property_with_service(pos, "insurance", radius=2)
        if not provider:
            provider = self._nearest_property_with_service(pos, "banking", radius=2)
        if not provider:
            self.sim.emit(Event("insurance_action_blocked", eid=eid, reason="no_insurance_service"))
            return
        self._buy_or_renew_policy(eid, provider)

    def on_property_interact(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        if not prop or _property_is_storefront(prop):
            return
        if _property_infrastructure_role(prop) == "service_terminal":
            return
        pos = self._position_for(eid)
        if pos:
            access = _evaluate_property_access(
                self.sim,
                eid,
                prop,
                x=pos.x,
                y=pos.y,
                z=pos.z,
            )
            if not access.can_use_services:
                return

        service = self._preferred_property_service(eid, prop)
        if service == "banking":
            self._bank_transaction(eid, prop)
            return
        if service == "insurance":
            self._buy_or_renew_policy(eid, prop)

    def on_finance_service_request(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return

        service = str(event.data.get("service", "") or "").strip().lower()
        if service not in {"banking", "insurance"}:
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        event_name = "banking_action_blocked" if service == "banking" else "insurance_action_blocked"
        blocked_reason = "no_banking_service" if service == "banking" else "no_insurance_service"
        if not prop:
            self.sim.emit(Event(event_name, eid=eid, reason=blocked_reason))
            return

        services = set(_finance_services_for_property(prop))
        if service not in services:
            self.sim.emit(Event(event_name, eid=eid, reason=blocked_reason))
            return

        pos = self._position_for(eid)
        if pos:
            access = _evaluate_property_access(
                self.sim,
                eid,
                prop,
                x=pos.x,
                y=pos.y,
                z=pos.z,
            )
            if not access.can_use_services:
                self.sim.emit(Event(event_name, eid=eid, reason=blocked_reason))
                return

        if service == "banking":
            self._bank_transaction(
                eid,
                prop,
                kind=event.data.get("kind"),
                amount=event.data.get("amount"),
                account_kind=event.data.get("account_kind"),
                business_property_id=event.data.get("business_property_id"),
            )
            return
        self._buy_or_renew_policy(eid, prop)

    def update(self):
        profile = self._profile_for(self.player_eid)
        if not profile:
            return

        if float(getattr(profile, "interest_rate", 0.0)) != 0.0:
            profile.interest_rate = 0.0
        if int(getattr(profile, "next_interest_tick", 0)) != 0:
            profile.next_interest_tick = 0

        for policy_key, policy in profile.policies.items():
            if not isinstance(policy, dict):
                continue
            expires_tick = int(policy.get("expires_tick", 0))
            if expires_tick > self.sim.tick:
                continue
            if policy.get("expired_notified"):
                continue
            policy["expired_notified"] = True
            self.sim.emit(Event(
                "insurance_policy_expired",
                eid=self.player_eid,
                policy_key=policy_key,
                policy_name=policy.get("name", policy_key),
            ))
