from __future__ import annotations

from engine.events import Event
from engine.systems import System
from game.components import NPCNeeds, SkillProfile
from game.skills import ALL_SKILL_IDS, ensure_actor_skill_profile, normalize_skill_id


class SkillProgressionSystem(System):
    PRACTICE_GROWTH_STEP = 0.1
    PRACTICE_THRESHOLD_BASE = 1.05
    PRACTICE_THRESHOLD_SCALE = 0.13
    PRACTICE_THRESHOLD_ABOVE_BASE_SCALE = 0.38

    NEGLECT_GRACE_TICKS = 1080
    NEGLECT_INTERVAL_TICKS = 300
    NEGLECT_DECAY_STEP = 0.05
    NEGLECT_SCAN_INTERVAL_TICKS = 60

    DIALOG_TOPIC_COOLDOWN = 24
    TRADE_COOLDOWN = 8
    INSURANCE_COOLDOWN = 24
    SITE_SERVICE_COOLDOWN = 16
    RECENT_AWARD_RETENTION_TICKS = 256

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self._last_decay_scan_tick = -10_000
        self._recent_award_ticks = {}

        self.sim.events.subscribe("skill_practice", self.on_skill_practice)
        self.sim.events.subscribe("dialog_topic_request", self.on_dialog_topic_request)
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("melee_attack", self.on_melee_attack)

    def _profile_for(self, eid, *, create=False):
        profiles = self.sim.ecs.get(SkillProfile)
        profile = profiles.get(eid) if profiles else None
        if isinstance(profile, SkillProfile):
            return profile
        if not create:
            return None
        return ensure_actor_skill_profile(self.sim, eid, skill_ids=ALL_SKILL_IDS)

    def _normalize_profile(self, profile, *, tick):
        if not isinstance(profile, SkillProfile):
            return
        for skill_id in tuple(profile.skill_ids() or ALL_SKILL_IDS):
            key = normalize_skill_id(skill_id)
            if not key:
                continue
            profile.ensure_baseline(key, value=profile.get(key, default=5.0))
            if profile.last_practiced_tick(key) is None:
                profile.mark_last_practiced(key, tick)
            if profile.last_decay_tick(key) is None:
                profile.mark_last_decay(key, tick)

    def _practice_threshold(self, profile, skill_id):
        current = float(profile.get(skill_id, 5.0))
        baseline = float(profile.ensure_baseline(skill_id, value=current) or current)
        threshold = float(self.PRACTICE_THRESHOLD_BASE)
        threshold += max(0.0, current) * float(self.PRACTICE_THRESHOLD_SCALE)
        threshold += max(0.0, current - baseline) * float(self.PRACTICE_THRESHOLD_ABOVE_BASE_SCALE)
        return max(0.8, threshold)

    def _practice_energy_multiplier(self, eid):
        needs_map = self.sim.ecs.get(NPCNeeds)
        needs = needs_map.get(eid) if needs_map else None
        if not isinstance(needs, NPCNeeds):
            return 1.0
        try:
            energy = max(0.0, min(100.0, float(getattr(needs, "energy", 100.0))))
        except (TypeError, ValueError):
            return 1.0
        if energy >= 70.0:
            return 1.0
        if energy >= 50.0:
            return 0.92
        if energy >= 30.0:
            return 0.78
        return 0.6

    def _emit_skill_change(self, eid, skill_id, *, delta, reason, tick, profile):
        skill_key = normalize_skill_id(skill_id)
        if not skill_key or abs(float(delta)) <= 1e-9:
            return
        value = float(profile.get(skill_key, 5.0))
        baseline = float(profile.baseline(skill_key, value))
        floor = float(profile.floor(skill_key))
        self.sim.emit(Event(
            "skill_rating_changed",
            eid=eid,
            skill_id=skill_key,
            delta=float(delta),
            reason=str(reason or "").strip().lower(),
            tick=int(tick),
            value=float(value),
            baseline=float(baseline),
            floor=float(floor),
        ))

    def _cooldown_ready(self, eid, skill_id, *, source, key, cooldown):
        cooldown = int(max(0, cooldown))
        if cooldown <= 0:
            return True

        tick = int(getattr(self.sim, "tick", 0))
        cooldown_key = (
            int(eid),
            normalize_skill_id(skill_id),
            str(source or "").strip().lower(),
            str(key or "").strip().lower(),
        )
        last_tick = int(self._recent_award_ticks.get(cooldown_key, -10_000))
        if tick - last_tick < cooldown:
            return False

        self._recent_award_ticks[cooldown_key] = tick
        if len(self._recent_award_ticks) > 512:
            stale_before = tick - int(self.RECENT_AWARD_RETENTION_TICKS)
            self._recent_award_ticks = {
                award_key: int(award_tick)
                for award_key, award_tick in self._recent_award_ticks.items()
                if int(award_tick) >= stale_before
            }
        return True

    def _apply_practice(self, eid, skill_id, amount, *, reason="", cooldown_key="", cooldown=0):
        skill_key = normalize_skill_id(skill_id)
        if eid is None or not skill_key:
            return False
        try:
            raw_amount = float(amount)
        except (TypeError, ValueError):
            raw_amount = 0.0
        if raw_amount <= 0.0:
            return False

        profile = self._profile_for(eid, create=True)
        if not isinstance(profile, SkillProfile):
            return False

        tick = int(getattr(self.sim, "tick", 0))
        self._normalize_profile(profile, tick=tick)
        # Any real use should keep the skill fresh, even when fatigue or cooldowns
        # reduce how much practice progress the action yields.
        profile.mark_last_practiced(skill_key, tick)

        practice_amount = raw_amount
        practice_amount *= float(self._practice_energy_multiplier(eid))
        if practice_amount <= 0.0:
            return False
        if not self._cooldown_ready(eid, skill_key, source=reason, key=cooldown_key, cooldown=cooldown):
            return False

        profile.add_practice(skill_key, practice_amount, tick=tick)

        grew = False
        while float(profile.get(skill_key, 5.0)) < 10.0 - 1e-9:
            threshold = self._practice_threshold(profile, skill_key)
            stored = float(profile.practice_amount(skill_key, default=0.0))
            if stored + 1e-9 < threshold:
                break
            profile.set_practice(skill_key, stored - threshold)
            before = float(profile.get(skill_key, 5.0))
            after = min(10.0, before + float(self.PRACTICE_GROWTH_STEP))
            if after <= before + 1e-9:
                break
            profile.set(skill_key, after)
            profile.note_change(skill_key, delta=(after - before), tick=tick, reason=f"practice_{reason}", value=after)
            self._emit_skill_change(eid, skill_key, delta=(after - before), reason=f"practice_{reason}", tick=tick, profile=profile)
            grew = True
        return grew

    def _apply_neglect_decay(self, eid, profile, skill_id, *, tick):
        skill_key = normalize_skill_id(skill_id)
        if not skill_key:
            return False

        current = float(profile.get(skill_key, 5.0))
        floor = float(profile.floor(skill_key))
        if current <= floor + 1e-9:
            profile.mark_last_decay(skill_key, tick)
            return False

        last_practiced = profile.last_practiced_tick(skill_key)
        if last_practiced is None:
            profile.mark_last_practiced(skill_key, tick)
            profile.mark_last_decay(skill_key, tick)
            return False
        if int(tick) - int(last_practiced) < int(self.NEGLECT_GRACE_TICKS):
            return False

        grace_anchor = int(last_practiced) + int(self.NEGLECT_GRACE_TICKS)
        last_decay = profile.last_decay_tick(skill_key, default=grace_anchor)
        if last_decay is None:
            last_decay = int(grace_anchor)
        last_decay = max(int(last_decay), int(grace_anchor))
        elapsed = int(tick) - int(last_decay)
        interval = int(self.NEGLECT_INTERVAL_TICKS)
        if elapsed < interval:
            return False

        steps = max(1, elapsed // interval)
        total_delta = 0.0
        after = current
        for _ in range(int(steps)):
            if after <= floor + 1e-9:
                break
            next_value = max(floor, after - float(self.NEGLECT_DECAY_STEP))
            if next_value >= after - 1e-9:
                break
            total_delta += next_value - after
            after = next_value

        profile.mark_last_decay(skill_key, int(last_decay) + (int(steps) * interval))
        if total_delta >= -1e-9:
            return False

        profile.set(skill_key, after)
        profile.note_change(skill_key, delta=total_delta, tick=tick, reason="neglect_decay", value=after)
        self._emit_skill_change(eid, skill_key, delta=total_delta, reason="neglect_decay", tick=tick, profile=profile)
        return True

    def on_skill_practice(self, event):
        eid = event.data.get("eid")
        skill_id = event.data.get("skill_id")
        amount = event.data.get("amount", 0.0)
        source = str(event.data.get("source", "practice") or "practice").strip().lower()
        cooldown_key = str(event.data.get("cooldown_key", "") or "").strip().lower()
        cooldown = int(event.data.get("cooldown", 0) or 0)
        self._apply_practice(
            eid,
            skill_id,
            amount,
            reason=source,
            cooldown_key=cooldown_key,
            cooldown=cooldown,
        )

    def on_dialog_topic_request(self, event):
        eid = event.data.get("eid")
        topic_id = str(event.data.get("topic_id", "") or "").strip().lower()
        npc_eid = event.data.get("npc_eid")
        if not topic_id or topic_id in {"bye", "leave", "trade"}:
            return
        key = f"{npc_eid}:{topic_id}"
        self._apply_practice(eid, "conversation", 0.12, reason="dialogue", cooldown_key=key, cooldown=self.DIALOG_TOPIC_COOLDOWN)
        self._apply_practice(eid, "streetwise", 0.06, reason="dialogue", cooldown_key=key, cooldown=self.DIALOG_TOPIC_COOLDOWN)
        self._apply_practice(eid, "perception", 0.05, reason="dialogue", cooldown_key=key, cooldown=self.DIALOG_TOPIC_COOLDOWN)

    def on_trade_bought(self, event):
        eid = event.data.get("eid")
        property_id = str(event.data.get("property_id", "") or "").strip()
        item_id = str(event.data.get("item_id", "") or "").strip().lower()
        key = f"{property_id}:buy:{item_id}"
        self._apply_practice(eid, "conversation", 0.1, reason="trade_buy", cooldown_key=key, cooldown=self.TRADE_COOLDOWN)
        self._apply_practice(eid, "streetwise", 0.14, reason="trade_buy", cooldown_key=key, cooldown=self.TRADE_COOLDOWN)
        self._apply_practice(eid, "perception", 0.05, reason="trade_buy", cooldown_key=key, cooldown=self.TRADE_COOLDOWN)

    def on_trade_sold(self, event):
        eid = event.data.get("eid")
        property_id = str(event.data.get("property_id", "") or "").strip()
        item_id = str(event.data.get("item_id", "") or "").strip().lower()
        key = f"{property_id}:sell:{item_id}"
        self._apply_practice(eid, "conversation", 0.12, reason="trade_sell", cooldown_key=key, cooldown=self.TRADE_COOLDOWN)
        self._apply_practice(eid, "streetwise", 0.18, reason="trade_sell", cooldown_key=key, cooldown=self.TRADE_COOLDOWN)
        self._apply_practice(eid, "perception", 0.05, reason="trade_sell", cooldown_key=key, cooldown=self.TRADE_COOLDOWN)

    def on_insurance_policy_purchased(self, event):
        eid = event.data.get("eid")
        property_id = str(event.data.get("property_id", "") or "").strip()
        policy_key = str(event.data.get("policy_key", "") or "").strip().lower()
        key = f"{property_id}:{policy_key}"
        self._apply_practice(eid, "conversation", 0.16, reason="insurance", cooldown_key=key, cooldown=self.INSURANCE_COOLDOWN)
        self._apply_practice(eid, "perception", 0.12, reason="insurance", cooldown_key=key, cooldown=self.INSURANCE_COOLDOWN)
        self._apply_practice(eid, "streetwise", 0.05, reason="insurance", cooldown_key=key, cooldown=self.INSURANCE_COOLDOWN)

    def on_site_service_used(self, event):
        eid = event.data.get("eid")
        service = str(event.data.get("service", "") or "").strip().lower()
        property_id = str(event.data.get("property_id", "") or "").strip()
        if not service:
            return
        key = f"{property_id}:{service}"
        if service == "fuel":
            self._apply_practice(eid, "mechanics", 0.16, reason="site_service", cooldown_key=key, cooldown=self.SITE_SERVICE_COOLDOWN)
            return
        if service == "repair":
            self._apply_practice(eid, "mechanics", 0.22, reason="site_service", cooldown_key=key, cooldown=self.SITE_SERVICE_COOLDOWN)
            self._apply_practice(eid, "streetwise", 0.06, reason="site_service", cooldown_key=key, cooldown=self.SITE_SERVICE_COOLDOWN)
            return
        if service == "intel":
            self._apply_practice(eid, "streetwise", 0.14, reason="site_service", cooldown_key=key, cooldown=self.SITE_SERVICE_COOLDOWN)
            self._apply_practice(eid, "perception", 0.14, reason="site_service", cooldown_key=key, cooldown=self.SITE_SERVICE_COOLDOWN)
            return
        if service in {"vehicle_fetch", "vehicle_sales_new", "vehicle_sales_used"}:
            self._apply_practice(eid, "conversation", 0.08, reason="site_service", cooldown_key=key, cooldown=self.SITE_SERVICE_COOLDOWN)
            self._apply_practice(eid, "streetwise", 0.12, reason="site_service", cooldown_key=key, cooldown=self.SITE_SERVICE_COOLDOWN)

    def on_melee_attack(self, event):
        eid = event.data.get("eid")
        hit_eid = event.data.get("hit_eid")
        amount = 0.18 if hit_eid is not None else 0.08
        weapon_id = str(event.data.get("weapon_id", "unarmed") or "unarmed").strip().lower()
        target_key = str(hit_eid) if hit_eid is not None else "miss"
        self._apply_practice(
            eid,
            "athletics",
            amount,
            reason="melee_attack",
            cooldown_key=f"{weapon_id}:{target_key}:{int(getattr(self.sim, 'tick', 0))}",
            cooldown=0,
        )

    def update(self):
        tick = int(getattr(self.sim, "tick", 0))
        if tick - int(self._last_decay_scan_tick) < int(self.NEGLECT_SCAN_INTERVAL_TICKS):
            return
        self._last_decay_scan_tick = tick

        profiles = self.sim.ecs.get(SkillProfile)
        for eid, profile in list(profiles.items()):
            if not isinstance(profile, SkillProfile):
                continue
            self._normalize_profile(profile, tick=tick)
            for skill_id in tuple(profile.skill_ids() or ALL_SKILL_IDS):
                self._apply_neglect_decay(eid, profile, skill_id, tick=tick)
