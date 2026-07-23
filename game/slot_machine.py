"""Deterministic five-reel slot math for the Cheeky Star Aster cabinet.

The cabinet deliberately keeps its math independent from UI and wallet code.
One round token owns the base window and every possible bonus continuation, so
the same token always resolves to the same complete result.  The weighted
without-replacement windows and the three feature shapes are adapted from
Adri's standalone slot-machine experiment, without carrying its verifier or
external client-seed machinery into the game.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache


SLOT_REEL_COUNT = 5
SLOT_ROW_COUNT = 4
SLOT_MAX_FEATURE_SPINS = 512
# Four independent 100,000-pull panels place this setting near 95% aggregate
# RTP while retaining the standalone machine's rare four-figure tails.
SLOT_BONUS_WILD_WEIGHT_SCALE = 1.125
SLOT_WILD = "ASTER"
SLOT_SCATTER = "SIGNAL"


# Four horizontal paths followed by the thirty-six shaped paths used by the
# standalone machine.  Rows are zero-based here; every line runs left to right.
SLOT_PAYLINES = (
    (0, 0, 0, 0, 0),
    (1, 1, 1, 1, 1),
    (2, 2, 2, 2, 2),
    (3, 3, 3, 3, 3),
    (3, 2, 1, 2, 3),
    (2, 1, 0, 1, 2),
    (0, 1, 2, 1, 0),
    (1, 2, 3, 2, 1),
    (3, 2, 3, 2, 3),
    (2, 1, 2, 1, 2),
    (1, 0, 1, 0, 1),
    (0, 1, 0, 1, 0),
    (1, 2, 1, 2, 1),
    (2, 3, 2, 3, 2),
    (1, 1, 0, 1, 1),
    (2, 2, 1, 2, 2),
    (3, 3, 2, 3, 3),
    (2, 2, 3, 2, 2),
    (1, 1, 2, 1, 1),
    (0, 0, 1, 0, 0),
    (3, 3, 0, 3, 3),
    (3, 3, 1, 3, 3),
    (2, 2, 0, 2, 2),
    (0, 0, 3, 0, 0),
    (0, 0, 2, 0, 0),
    (1, 1, 3, 1, 1),
    (3, 1, 3, 1, 3),
    (2, 0, 2, 0, 2),
    (0, 2, 0, 2, 0),
    (1, 3, 1, 3, 1),
    (0, 1, 1, 1, 0),
    (1, 2, 2, 2, 1),
    (2, 3, 3, 3, 2),
    (3, 2, 2, 2, 3),
    (2, 1, 1, 1, 2),
    (1, 0, 0, 0, 1),
    (3, 0, 3, 0, 3),
    (0, 3, 0, 3, 0),
    (3, 0, 0, 0, 3),
    (0, 3, 3, 3, 0),
)


# Low symbols are objects and flora.  The three high symbols are people the
# Pygame cabinet renders as tiny Bakerrrr inhabitants.
SLOT_SYMBOL_PROFILES = {
    "SCRAP": {"label": "Scrap", "kind": "item", "tier": 0},
    "PETAL": {"label": "Petal", "kind": "flora", "tier": 1},
    "CREDIT": {"label": "Credit", "kind": "item", "tier": 2},
    "KEY": {"label": "Key", "kind": "item", "tier": 3},
    "MASK": {"label": "Mask", "kind": "item", "tier": 4},
    "DRONE": {"label": "Drone", "kind": "item", "tier": 5},
    "WIRE": {"label": "Wire", "kind": "item", "tier": 6},
    "HUNTER": {"label": "Hunter", "kind": "major", "tier": 7},
    "TINKERER": {"label": "Tinkerer", "kind": "major", "tier": 8},
    "RUNNER": {"label": "Runner", "kind": "major", "tier": 9},
    SLOT_WILD: {"label": "Star aster", "kind": "wild", "tier": 10},
    SLOT_SCATTER: {"label": "Wire signal", "kind": "scatter", "tier": 11},
}


_PAYTABLE_BY_TIER = (
    {3: 0.05, 4: 0.25, 5: 0.625},
    {3: 0.05, 4: 0.25, 5: 1.0},
    {3: 0.1, 4: 0.3, 5: 1.25},
    {3: 0.125, 4: 0.375, 5: 1.875},
    {3: 0.25, 4: 0.5, 5: 2.5},
    {3: 0.25, 4: 1.25, 5: 5.0},
    {3: 0.3, 4: 1.5, 5: 7.5},
    {3: 0.375, 4: 1.875, 5: 10.0},
    {3: 0.5, 4: 2.0, 5: 12.5},
    {3: 0.5, 4: 3.125, 5: 25.0},
)
SLOT_LINE_PAYTABLE = {
    symbol: dict(_PAYTABLE_BY_TIER[int(profile["tier"])])
    for symbol, profile in SLOT_SYMBOL_PROFILES.items()
    if int(profile["tier"]) < len(_PAYTABLE_BY_TIER)
}
SLOT_LINE_PAYTABLE[SLOT_WILD] = {3: 0.625, 4: 3.75, 5: 37.5}
SLOT_SCATTER_PAYTABLE = {2: 0.05, 3: 1.875, 4: 6.25, 5: 62.5}


_BASE_COUNTS = {
    "SCRAP": 8,
    "PETAL": 8,
    "CREDIT": 8,
    "KEY": 8,
    "MASK": 8,
    "DRONE": 6,
    "WIRE": 6,
    "HUNTER": 6,
    "TINKERER": 5,
    "RUNNER": 5,
}


def _window_specs(*, wild_count, wild_weights, scatter_weights=None):
    specs = []
    for reel_index in range(SLOT_REEL_COUNT):
        reel = {
            symbol: (int(count), 1_000_000)
            for symbol, count in _BASE_COUNTS.items()
        }
        reel[SLOT_WILD] = (
            int(wild_count),
            max(1, int(round(float(wild_weights[reel_index]) * 1_000_000))),
        )
        if scatter_weights is not None:
            reel[SLOT_SCATTER] = (
                1,
                max(1, int(round(float(scatter_weights[reel_index]) * 1_000_000))),
            )
        specs.append(reel)
    return tuple(specs)


_MAIN_WINDOW_SPECS = _window_specs(
    wild_count=5,
    wild_weights=(1.0, 1.0, 1.0, 1.0, 1.0),
    scatter_weights=(1.0, 2.0, 1.0, 2.0, 1.0),
)
_BONUS_WILD_WEIGHTS = {
    "overgrowth": (0.93, 0.93064, 0.93, 0.94, 0.93),
    "wire_lock": (0.76, 0.76458, 0.76, 0.76, 0.76),
    "constellation": (0.77, 0.78, 0.77, 0.78, 0.77),
}


SLOT_FEATURE_PROFILES = {
    "overgrowth": {
        "title": "Overgrowth",
        "note": "Star asters add a spin and raise the multiplier as the feature grows.",
    },
    "wire_lock": {
        "title": "Wire Lock",
        "note": "Wilds stick in place and every line pays double.",
    },
    "constellation": {
        "title": "Constellation",
        "note": "Sticky asters grow reel multipliers and can build a very long tail.",
    },
}


class _HashStream:
    """Small stable random stream built only from SHA-256 and integer math."""

    def __init__(self, seed):
        self.seed = str(seed).encode("utf-8")
        self.counter = 0

    def number(self):
        digest = hashlib.sha256(self.seed + b":" + str(self.counter).encode("ascii")).digest()
        self.counter += 1
        return int.from_bytes(digest, "big")

    def below(self, ceiling):
        ceiling = max(1, int(ceiling))
        return self.number() % ceiling


class DeterministicWindowStrategy:
    """Draw four visible symbols per reel without replacement."""

    def __init__(self, reel_specs):
        self.reel_specs = tuple(dict(spec) for spec in reel_specs)

    @staticmethod
    def _weighted_symbol(stream, counts, weights):
        total = sum(int(counts[symbol]) * int(weights[symbol]) for symbol in counts if int(counts[symbol]) > 0)
        ticket = stream.below(total)
        for symbol in sorted(counts):
            span = int(counts[symbol]) * int(weights[symbol])
            if ticket < span:
                return symbol
            ticket -= span
        return sorted(counts)[-1]

    def get_window(self, seed):
        stream = _HashStream(seed)
        window = []
        for reel_spec in self.reel_specs:
            counts = {symbol: int(parts[0]) for symbol, parts in reel_spec.items()}
            weights = {symbol: int(parts[1]) for symbol, parts in reel_spec.items()}
            reel = []
            for _row in range(SLOT_ROW_COUNT):
                symbol = self._weighted_symbol(stream, counts, weights)
                reel.append(symbol)
                counts[symbol] -= 1
                if counts[symbol] <= 0:
                    counts.pop(symbol, None)
                    weights.pop(symbol, None)
            for index in range(len(reel) - 1, 0, -1):
                other = stream.below(index + 1)
                reel[index], reel[other] = reel[other], reel[index]
            window.append(tuple(reel))
        return tuple(window)


_WINDOW_STRATEGIES = {
    "main": DeterministicWindowStrategy(_MAIN_WINDOW_SPECS),
}


def normalize_slot_bonus_wild_weight_scale(value):
    """Return the bounded multiplier used by every bonus-window wild weight."""

    try:
        value = float(value)
    except (TypeError, ValueError):
        value = SLOT_BONUS_WILD_WEIGHT_SCALE
    return max(0.05, min(3.0, value))


@lru_cache(maxsize=32)
def _feature_window_strategy(feature_key, scale_key):
    scale = float(scale_key) / 1_000_000.0
    weights = tuple(float(weight) * scale for weight in _BONUS_WILD_WEIGHTS[feature_key])
    return DeterministicWindowStrategy(_window_specs(wild_count=2, wild_weights=weights))


def slot_seed_contract(world_seed, cabinet_seed, nonce, *, sequence=0):
    """Build the cabinet's internal server/client/nonce counterpart.

    ``world_seed`` is the hidden world-side value, ``cabinet_seed`` is stable
    for the physical host, and the simulation tick is the nonce.  ``sequence``
    only prevents duplicate pulls while a paused casino modal shares one tick.
    """

    world_hash = hashlib.sha256(f"bakerrrr-world:{world_seed}".encode("utf-8")).hexdigest()
    cabinet_hash = hashlib.sha256(f"bakerrrr-cabinet:{cabinet_seed}".encode("utf-8")).hexdigest()
    nonce = int(nonce)
    sequence = max(0, int(sequence))
    token = f"{world_hash}:{cabinet_hash}:{nonce}:{sequence}"
    return {
        "world_hash": world_hash,
        "cabinet_hash": cabinet_hash,
        "nonce": nonce,
        "sequence": sequence,
        "token": token,
    }


def _seed_token(value):
    if isinstance(value, dict):
        token = str(value.get("token", "")).strip()
        if token:
            return token
        return slot_seed_contract(
            value.get("world_seed", ""),
            value.get("cabinet_seed", ""),
            value.get("nonce", 0),
            sequence=value.get("sequence", 0),
        )["token"]
    return str(value)


def _cabinet_seed(seed_token, stream, nonce):
    material = f"{seed_token}:cheeky-star-aster:{stream}:{int(nonce)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def slot_window(seed_token, *, stream="main", nonce=0, bonus_wild_weight_scale=SLOT_BONUS_WILD_WEIGHT_SCALE):
    stream = str(stream or "main").strip().lower()
    if stream == "main":
        strategy = _WINDOW_STRATEGIES["main"]
    elif stream in _BONUS_WILD_WEIGHTS:
        scale_key = int(round(normalize_slot_bonus_wild_weight_scale(bonus_wild_weight_scale) * 1_000_000))
        strategy = _feature_window_strategy(stream, scale_key)
    else:
        raise ValueError(f"unknown slot stream: {stream}")
    return strategy.get_window(_cabinet_seed(_seed_token(seed_token), stream, nonce))


def _window_tuple(window):
    columns = tuple(tuple(str(symbol).strip().upper() for symbol in reel) for reel in tuple(window or ()))
    if len(columns) != SLOT_REEL_COUNT or any(len(reel) != SLOT_ROW_COUNT for reel in columns):
        raise ValueError("slot windows must contain five reels of four symbols")
    return columns


def score_slot_window(window, *, line_factor=1.0, cell_factors=None):
    """Score all forty left-to-right lines and the all-window scatter."""

    window = _window_tuple(window)
    factors = dict(cell_factors or {})
    hits = []
    winning_cells = set()
    line_total = 0.0

    for line_index, payline in enumerate(SLOT_PAYLINES, start=1):
        symbols = tuple(window[reel][row] for reel, row in enumerate(payline))
        base = next((symbol for symbol in symbols if symbol != SLOT_WILD), SLOT_WILD)
        if base == SLOT_SCATTER:
            continue
        match_count = 0
        for symbol in symbols:
            if symbol == base or symbol == SLOT_WILD:
                match_count += 1
            else:
                break
        base_multiplier = float(SLOT_LINE_PAYTABLE.get(base, {}).get(match_count, 0.0))
        if base_multiplier <= 0.0:
            continue
        cells = tuple((reel, int(payline[reel])) for reel in range(match_count))
        cell_factor = 1.0
        for cell in cells:
            cell_factor *= max(1.0, float(factors.get(cell, 1.0)))
        payout_multiplier = base_multiplier * max(0.0, float(line_factor)) * cell_factor
        line_total += payout_multiplier
        winning_cells.update(cells)
        hits.append({
            "line": int(line_index),
            "symbol": str(base),
            "count": int(match_count),
            "base_multiplier": float(base_multiplier),
            "payout_multiplier": float(payout_multiplier),
            "cells": cells,
        })

    scatter_count = sum(symbol == SLOT_SCATTER for reel in window for symbol in reel)
    scatter_multiplier = float(SLOT_SCATTER_PAYTABLE.get(scatter_count, 0.0))
    if scatter_multiplier > 0.0:
        winning_cells.update(
            (reel_index, row_index)
            for reel_index, reel in enumerate(window)
            for row_index, symbol in enumerate(reel)
            if symbol == SLOT_SCATTER
        )
    wild_count = sum(symbol == SLOT_WILD for reel in window for symbol in reel)
    return {
        "window": window,
        "line_hits": tuple(hits),
        "line_hit_count": len(hits),
        "line_multiplier": float(line_total),
        "scatter_count": int(scatter_count),
        "scatter_multiplier": float(scatter_multiplier),
        "wild_count": int(wild_count),
        "total_multiplier": float(line_total + scatter_multiplier),
        "winning_cells": tuple(sorted(winning_cells)),
    }


@dataclass
class _FeatureState:
    remaining: int = 10
    spins_played: int = 0
    multiplier: float = 1.0
    wilds_seen: int = 0
    extra_awarded: bool = False
    locked: dict | None = None

    def __post_init__(self):
        if self.locked is None:
            self.locked = {}


def _locked_window(window, locked):
    reels = [list(reel) for reel in _window_tuple(window)]
    for (reel_index, row_index), _value in dict(locked or {}).items():
        reels[int(reel_index)][int(row_index)] = SLOT_WILD
    return tuple(tuple(reel) for reel in reels)


def _lock_visible_wilds(window, state):
    for reel_index, reel in enumerate(window):
        for row_index, symbol in enumerate(reel):
            if symbol == SLOT_WILD:
                state.locked[(int(reel_index), int(row_index))] = SLOT_WILD


def run_slot_feature(
    feature_key,
    seed_token,
    *,
    start_nonce=0,
    spin_cap=SLOT_MAX_FEATURE_SPINS,
    bonus_wild_weight_scale=SLOT_BONUS_WILD_WEIGHT_SCALE,
):
    """Resolve one of the cabinet's three deterministic free-spin features."""

    feature_key = str(feature_key or "").strip().lower()
    if feature_key not in SLOT_FEATURE_PROFILES:
        raise ValueError(f"unknown slot feature: {feature_key}")
    state = _FeatureState()
    total_multiplier = 0.0
    nonce = int(start_nonce)
    final_score = None
    best_spin_multiplier = 0.0
    spin_cap = max(1, int(spin_cap))

    while state.remaining > 0 and state.spins_played < spin_cap:
        raw_window = slot_window(
            seed_token,
            stream=feature_key,
            nonce=nonce,
            bonus_wild_weight_scale=bonus_wild_weight_scale,
        )
        state.remaining -= 1
        state.spins_played += 1

        if feature_key == "overgrowth":
            wilds = sum(symbol == SLOT_WILD for reel in raw_window for symbol in reel)
            if wilds > 0:
                state.multiplier += float(wilds)
                state.remaining += int(wilds)
                state.wilds_seen += int(wilds)
            if not state.extra_awarded and state.wilds_seen >= 15:
                state.remaining += 5
                state.extra_awarded = True
            score = score_slot_window(raw_window, line_factor=state.multiplier)
        elif feature_key == "wire_lock":
            merged = _locked_window(raw_window, state.locked)
            _lock_visible_wilds(merged, state)
            if not state.extra_awarded and {cell[0] for cell in state.locked} == set(range(SLOT_REEL_COUNT)):
                state.remaining += 5
                state.extra_awarded = True
            score = score_slot_window(merged, line_factor=2.0)
        else:
            merged = _locked_window(raw_window, state.locked)
            _lock_visible_wilds(merged, state)
            reel_counts = {}
            for reel_index, _row_index in state.locked:
                reel_counts[reel_index] = reel_counts.get(reel_index, 0) + 1
            cell_factors = {
                cell: float(max(1, reel_counts.get(cell[0], 1)))
                for cell in state.locked
            }
            score = score_slot_window(merged, cell_factors=cell_factors)

        total_multiplier += float(score["total_multiplier"])
        best_spin_multiplier = max(best_spin_multiplier, float(score["total_multiplier"]))
        final_score = score
        nonce += 1

    final_score = final_score or score_slot_window(slot_window(
        seed_token,
        stream=feature_key,
        nonce=start_nonce,
        bonus_wild_weight_scale=bonus_wild_weight_scale,
    ))
    profile = SLOT_FEATURE_PROFILES[feature_key]
    return {
        "key": feature_key,
        "title": str(profile["title"]),
        "note": str(profile["note"]),
        "total_multiplier": float(total_multiplier),
        "spins_played": int(state.spins_played),
        "finish_nonce": int(nonce),
        "best_spin_multiplier": float(best_spin_multiplier),
        "final_window": tuple(final_score["window"]),
        "final_line_hits": tuple(final_score["line_hits"]),
        "final_winning_cells": tuple(final_score["winning_cells"]),
        "multiplier": float(state.multiplier),
        "wilds_seen": int(state.wilds_seen),
        "locked_count": len(state.locked),
        "locked_cells": tuple(sorted(state.locked)),
        "extra_awarded": bool(state.extra_awarded),
        "capped": bool(state.remaining > 0),
        "bonus_wild_weight_scale": float(normalize_slot_bonus_wild_weight_scale(bonus_wild_weight_scale)),
    }


def _round_credits(value):
    return max(0, int(math.floor(float(value) + 0.5)))


def _top_line_text(hit):
    profile = SLOT_SYMBOL_PROFILES.get(str(hit.get("symbol", "")), {})
    label = str(profile.get("label", hit.get("symbol", "symbol")))
    multiplier = float(hit.get("payout_multiplier", 0.0))
    return f"L{int(hit.get('line', 0)):02d} {label} x{int(hit.get('count', 0))} ({multiplier:g}x)"


def slot_feature_key(seed_token):
    """Select one feature without evaluating or comparing its possible award."""

    seed_token = _seed_token(seed_token)
    feature_keys = tuple(SLOT_FEATURE_PROFILES)
    choice_number = int.from_bytes(
        hashlib.sha256(f"{seed_token}:feature-choice".encode("utf-8")).digest(),
        "big",
    )
    return feature_keys[choice_number % len(feature_keys)]


def resolve_bakerrrr_slot(seed_token, wager, *, bonus_wild_weight_scale=SLOT_BONUS_WILD_WEIGHT_SCALE):
    """Resolve the base game and one hash-selected feature on a trigger."""

    contract = dict(seed_token) if isinstance(seed_token, dict) else None
    seed_token = _seed_token(seed_token)
    wager = max(0, int(wager))
    fingerprint = hashlib.sha256(f"{seed_token}:cheeky-star-aster".encode("utf-8")).hexdigest()[:12]
    base_window = slot_window(seed_token, stream="main", nonce=0)
    base_score = score_slot_window(base_window)
    feature = None
    candidates = ()
    if int(base_score["scatter_count"]) >= 3:
        feature_keys = tuple(SLOT_FEATURE_PROFILES)
        selected_key = slot_feature_key(seed_token)
        feature = run_slot_feature(
            selected_key,
            seed_token,
            start_nonce=0,
            bonus_wild_weight_scale=bonus_wild_weight_scale,
        )
        candidates = tuple({
            "key": str(feature_key),
            "title": str(SLOT_FEATURE_PROFILES[feature_key]["title"]),
            "selected": feature_key == selected_key,
        } for feature_key in feature_keys)

    bonus_multiplier = float(feature["total_multiplier"]) if feature else 0.0
    total_multiplier = float(base_score["total_multiplier"]) + bonus_multiplier
    payout = _round_credits(total_multiplier * float(wager))
    display_window = tuple(feature["final_window"]) if feature else tuple(base_window)
    display_winning_cells = tuple(feature["final_winning_cells"]) if feature else tuple(base_score["winning_cells"])

    if feature and total_multiplier >= 100.0:
        outcome_key = "feature_tail"
        headline = f"{feature['title']} tears open the ceiling."
        detail = "The feature keeps compounding until the cabinet's payout counter can barely keep up."
    elif feature:
        outcome_key = "feature"
        headline = f"{feature['title']} lights the cabinet."
        detail = str(feature["note"])
    elif int(base_score["line_hit_count"]) > 0:
        outcome_key = "line_hit"
        headline = f"{int(base_score['line_hit_count'])} of 40 lines connect."
        detail = "The cabinet traces each winning route from the leftmost reel."
    elif float(base_score["scatter_multiplier"]) > 0.0:
        outcome_key = "scatter_return"
        headline = "Two wire signals answer."
        detail = "The scatter return catches part of the stake, but the feature stays dark."
    else:
        outcome_key = "blank"
        headline = "The city slips past the glass."
        detail = "Nothing holds together across the forty routes."

    top_hits = sorted(
        tuple(base_score["line_hits"]),
        key=lambda hit: (-float(hit.get("payout_multiplier", 0.0)), int(hit.get("line", 0))),
    )[:4]
    result_lines = [
        "Cheeky Star Aster // five reels // forty lines",
        (
            f"Base: {int(base_score['line_hit_count'])} line hits | "
            f"{int(base_score['scatter_count'])} signals | {int(base_score['wild_count'])} star asters."
        ),
    ]
    if top_hits:
        result_lines.append("Brightest lines: " + " | ".join(_top_line_text(hit) for hit in top_hits))
    if feature:
        result_lines.extend([
            (
                f"Feature: {feature['title']} | {int(feature['spins_played'])} spins | "
                f"{float(feature['total_multiplier']):g}x bonus."
            ),
            (
                f"Best feature spin {float(feature['best_spin_multiplier']):g}x"
                + (" | the safety cap caught a surviving tail." if feature.get("capped") else ".")
            ),
        ])
    result_lines.append(detail)

    return {
        "machine": "cheeky_star_aster",
        "seed_fingerprint": fingerprint,
        "seed_contract": {
            "world_fingerprint": str((contract or {}).get("world_hash", ""))[:12],
            "cabinet_fingerprint": str((contract or {}).get("cabinet_hash", ""))[:12],
            "nonce": int((contract or {}).get("nonce", 0) or 0),
            "sequence": int((contract or {}).get("sequence", 0) or 0),
        } if contract else {},
        "wager": int(wager),
        "stake": int(wager),
        "payout": int(payout),
        "payout_multiplier": float(total_multiplier),
        "base_multiplier": float(base_score["total_multiplier"]),
        "bonus_multiplier": float(bonus_multiplier),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Cheeky Star Aster resolves at {total_multiplier:g}x. {headline}",
        "result_lines": tuple(result_lines),
        "reels": tuple(base_window),
        "grid": tuple(display_window),
        "trigger_grid": tuple(base_window),
        "winning_cells": tuple(display_winning_cells),
        "line_hits": tuple(base_score["line_hits"]),
        "line_hit_count": int(base_score["line_hit_count"]),
        "scatter_count": int(base_score["scatter_count"]),
        "wild_count": int(base_score["wild_count"]),
        "feature": dict(feature) if feature else None,
        "feature_candidates": candidates,
        "bonus_wild_weight_scale": float(normalize_slot_bonus_wild_weight_scale(bonus_wild_weight_scale)),
    }


__all__ = [
    "DeterministicWindowStrategy",
    "SLOT_FEATURE_PROFILES",
    "SLOT_BONUS_WILD_WEIGHT_SCALE",
    "SLOT_LINE_PAYTABLE",
    "SLOT_MAX_FEATURE_SPINS",
    "SLOT_PAYLINES",
    "SLOT_REEL_COUNT",
    "SLOT_ROW_COUNT",
    "SLOT_SCATTER",
    "SLOT_SCATTER_PAYTABLE",
    "SLOT_SYMBOL_PROFILES",
    "SLOT_WILD",
    "normalize_slot_bonus_wild_weight_scale",
    "resolve_bakerrrr_slot",
    "run_slot_feature",
    "score_slot_window",
    "slot_feature_key",
    "slot_seed_contract",
    "slot_window",
]
