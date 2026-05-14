"""Shared AI intent synchronization helpers."""


def _sync_ai_intent(ai, will, tick, intent, *, score=0.0, target=None, target_eid=None):
    ai.state = intent
    ai.target = target
    ai.target_eid = target_eid
    if not will:
        return
    will.intent = intent
    will.score = float(score)
    will.target = target
    will.target_eid = target_eid
    will.last_tick = int(tick)
