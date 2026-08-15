"""Small, cached procedural-audio runtime for the pygame frontend.

The synthesis is intentionally modest: standard-library math produces a tiny
PCM bank once per game session, pygame owns playback, and real simulation events
select cues. Nothing is generated in the frame loop.
"""

from __future__ import annotations

import io
import math
import os
import random
import struct
import sys
import time
import wave
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable


SAMPLE_WIDTH = 2
DEFAULT_SAMPLE_RATE = 22_050
DEFAULT_CHANNEL_COUNT = 2
DEFAULT_MIXER_BUFFER = 512
MIN_MIXER_CHANNEL_COUNT = 24
OPEN_RUN_BPM = 92
OPEN_RUN_BEATS = 16
OPEN_RUN_DURATION = OPEN_RUN_BEATS * (60.0 / OPEN_RUN_BPM)
MUSIC_SILENCE_MIN_SECONDS = 150.0
MUSIC_SILENCE_MAX_SECONDS = 300.0
MUSIC_HOME_CUE_NAMES = (
    "home_theme_brief",
    "home_theme_roam",
    "home_theme_wide",
)
MUSIC_BIOME_CUE_BY_KEY = {
    "city": "biome_theme_city",
    "frontier": "biome_theme_frontier",
    "wilderness": "biome_theme_wilderness",
    "coastal": "biome_theme_coastal",
    "underground": "biome_theme_underground",
}
MUSIC_CUE_NAMES = MUSIC_HOME_CUE_NAMES + tuple(MUSIC_BIOME_CUE_BY_KEY.values())
ENVIRONMENT_SAMPLE_INTERVAL = 0.35
ENVIRONMENT_FADE_SECONDS = 0.65
AMBIENT_ATTACK_SECONDS_BY_GROUP = {
    "water": 2.25,
    "engine": 0.16,
}
AMBIENT_RELEASE_SECONDS_BY_GROUP = {
    "engine": 0.12,
}
AMBIENT_CHANNEL_INDEX = {
    "water": 1,
    "campfire": 2,
    "time": 3,
    "biome": 4,
    "crowd": 5,
    "engine": 6,
}
RESERVED_CHANNEL_COUNT = 1 + len(AMBIENT_CHANNEL_INDEX)
CROWD_CHATTER_RADIUS = 7
CROWD_CHATTER_MIN_NPCS = 4
GLASS_AUDIBLE_RADIUS = 10
EXPLOSION_MIN_AUDIBLE_RADIUS = 14
WILDERNESS_DAY_CICADA_BOUT_STARTS = (0.08,)
WILDERNESS_NIGHT_CRICKET_CLUSTER_STARTS = (0.07,)
AMBIENT_ONE_SHOT_REST_SECONDS_BY_CUE = {
    "ambient_water": (5.2, 6.0),
    "ambient_campfire": (5.2, 6.0),
    "ambient_biome_wilderness_day": (24.0, 90.0),
    "ambient_biome_wilderness_night": (20.0, 78.0),
}
AMBIENT_ONE_SHOT_REST_MODE_SECONDS_BY_CUE = {
    "ambient_biome_wilderness_day": 64.0,
    "ambient_biome_wilderness_night": 56.0,
}
AMBIENT_ONE_SHOT_INITIAL_DELAY_SECONDS_BY_CUE = {
    "ambient_biome_wilderness_day": (2.0, 8.0),
    "ambient_biome_wilderness_night": (2.0, 8.0),
}
ENVIRONMENT_DIRTY_EVENTS = {
    "player_moved",
    "vehicle_entered",
    "vehicle_exited",
    "vehicle_action_blocked",
    "vehicle_local_controlled",
    "vehicle_local_moved",
}
WORLD_SOUND_EVENTS = {
    "structure_broken",
    "explosion_triggered",
}
CASINO_SOUND_EVENTS = {
    "casino_chips_bet",
    "casino_menu_backed",
    "casino_menu_confirmed",
    "casino_menu_moved",
    "holdem_cash_actor_left",
    "holdem_cash_action",
    "holdem_cash_actor_seated",
    "holdem_cash_hand_settled",
    "holdem_cash_hand_started",
    "site_service_used",
}
CASINO_MACHINE_SERVICE_IDS = frozenset({
    "slots",
    "video_poker",
    "keno",
    "plinko",
    "crash",
})
CASINO_GAME_SERVICE_IDS = CASINO_MACHINE_SERVICE_IDS | frozenset({
    "baccarat",
    "bloom_cards",
    "casino_holdem",
    "craps",
    "roulette",
    "texas_holdem_cash",
    "three_bones",
    "three_bright",
    "three_card_poker",
    "twenty_one",
})


@dataclass(frozen=True)
class CueDefinition:
    name: str
    duration: float
    builder: Callable[[float, int], list[float]]
    gain: float = 1.0
    cooldown: float = 0.0
    loop: bool = False
    bus: str = "sfx"


@dataclass(frozen=True)
class RenderedCue:
    definition: CueDefinition
    pcm: bytes
    wav: bytes
    sample_rate: int
    channel_count: int
    peak: float

    @property
    def frame_count(self) -> int:
        return len(self.pcm) // (SAMPLE_WIDTH * self.channel_count)

    @property
    def duration(self) -> float:
        return self.frame_count / float(self.sample_rate)


def _sample_count(seconds: float, sample_rate: int) -> int:
    return max(1, int(round(float(seconds) * int(sample_rate))))


def _blank(seconds: float, sample_rate: int) -> list[float]:
    return [0.0] * _sample_count(seconds, sample_rate)


def _oscillator(phase: float, shape: str) -> float:
    phase %= 1.0
    sine = math.sin(math.tau * phase)
    if shape == "sine":
        return sine
    if shape == "triangle":
        return (4.0 * abs(phase - 0.5)) - 1.0
    if shape == "soft_square":
        return math.tanh(2.2 * sine) / math.tanh(2.2)
    raise ValueError(f"unknown oscillator shape: {shape}")


def _envelope(index: int, count: int, attack: float, release: float, sample_rate: int) -> float:
    attack_frames = max(1, _sample_count(attack, sample_rate))
    release_frames = max(1, _sample_count(release, sample_rate))
    attack_gain = min(1.0, index / attack_frames)
    release_gain = min(1.0, (count - index - 1) / release_frames)
    return max(0.0, min(attack_gain, release_gain))


def _add_tone(
    samples: list[float],
    *,
    sample_rate: int,
    start: float,
    duration: float,
    frequency: float,
    amplitude: float,
    shape: str = "sine",
    end_frequency: float | None = None,
    attack: float = 0.004,
    release: float = 0.025,
    decay: float = 0.0,
    phase_offset: float = 0.0,
) -> None:
    start_frame = max(0, int(round(start * sample_rate)))
    count = min(_sample_count(duration, sample_rate), max(0, len(samples) - start_frame))
    if count <= 0:
        return
    phase = float(phase_offset)
    target_frequency = float(frequency if end_frequency is None else end_frequency)
    ratio = target_frequency / float(frequency) if frequency > 0.0 else 1.0
    for offset in range(count):
        progress = offset / max(1, count - 1)
        current_frequency = float(frequency) * (ratio ** progress)
        gain = _envelope(offset, count, attack, release, sample_rate)
        if decay > 0.0:
            gain *= math.exp(-float(decay) * progress)
        samples[start_frame + offset] += _oscillator(phase, shape) * float(amplitude) * gain
        phase += current_frequency / sample_rate


def _add_noise(
    samples: list[float],
    *,
    sample_rate: int,
    start: float,
    duration: float,
    amplitude: float,
    seed: int,
    color: str = "white",
    attack: float = 0.002,
    release: float = 0.025,
    decay: float = 0.0,
) -> None:
    start_frame = max(0, int(round(start * sample_rate)))
    count = min(_sample_count(duration, sample_rate), max(0, len(samples) - start_frame))
    if count <= 0:
        return
    rng = random.Random(int(seed))
    low = 0.0
    for offset in range(count):
        white = rng.uniform(-1.0, 1.0)
        low += 0.12 * (white - low)
        if color == "low":
            value = low
        elif color == "high":
            value = white - low
        elif color == "white":
            value = white
        else:
            raise ValueError(f"unknown noise color: {color}")
        progress = offset / max(1, count - 1)
        gain = _envelope(offset, count, attack, release, sample_rate)
        if decay > 0.0:
            gain *= math.exp(-float(decay) * progress)
        samples[start_frame + offset] += value * float(amplitude) * gain


def _footstep(duration: float, sample_rate: int) -> list[float]:
    """A damped heel-and-gravel crunch with no hard, glassy contact."""

    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.13, amplitude=0.115, seed=11, color="low", attack=0.010, release=0.072, decay=2.5)
    _add_noise(samples, sample_rate=sample_rate, start=0.010, duration=0.105, amplitude=0.028, seed=12, color="white", attack=0.012, release=0.060, decay=1.8)
    gravel = (
        (0.020, 0.032, 0.040),
        (0.043, 0.028, 0.030),
        (0.067, 0.035, 0.035),
        (0.094, 0.030, 0.026),
    )
    for index, (start, grain_duration, amplitude) in enumerate(gravel):
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=grain_duration, amplitude=amplitude, seed=13 + index, color="white", attack=0.008, release=grain_duration * 0.76, decay=1.9)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.118, frequency=70.0, end_frequency=45.0, amplitude=0.052, attack=0.010, release=0.070, decay=2.7)
    return samples


def _door(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.17, frequency=96.0, end_frequency=57.0, amplitude=0.24, shape="soft_square", release=0.065, decay=3.2)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.12, amplitude=0.14, seed=21, color="low", release=0.045, decay=4.5)
    _add_tone(samples, sample_rate=sample_rate, start=0.135, duration=0.075, frequency=730.0, end_frequency=490.0, amplitude=0.075, shape="triangle", release=0.035, decay=4.0)
    return samples


def _pickup(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.09, amplitude=0.09, seed=31, color="high", release=0.035, decay=4.5)
    _add_tone(samples, sample_rate=sample_rate, start=0.018, duration=0.13, frequency=410.0, end_frequency=535.0, amplitude=0.10, shape="triangle", release=0.05, decay=3.0)
    return samples


def _transaction(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.085, frequency=440.0, amplitude=0.105, shape="triangle", decay=2.8)
    _add_tone(samples, sample_rate=sample_rate, start=0.058, duration=0.10, frequency=659.25, amplitude=0.12, shape="triangle", decay=3.2)
    _add_noise(samples, sample_rate=sample_rate, start=0.055, duration=0.025, amplitude=0.025, seed=41, color="high", release=0.012, decay=5.0)
    return samples


def _casino_menu_move(duration: float, sample_rate: int) -> list[float]:
    """A tiny dry cursor pip, audible without becoming a menu melody."""

    samples = _blank(duration, sample_rate)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.045, frequency=920.0, end_frequency=980.0, amplitude=0.050, shape="triangle", attack=0.003, release=0.022, decay=2.5)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.018, amplitude=0.010, seed=43, color="high", release=0.010, decay=5.0)
    return samples


def _casino_menu_confirm(duration: float, sample_rate: int) -> list[float]:
    """Two restrained terminal pips for accepting a casino-menu choice."""

    samples = _blank(duration, sample_rate)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.065, frequency=690.0, end_frequency=730.0, amplitude=0.052, shape="triangle", attack=0.004, release=0.030, decay=2.8)
    _add_tone(samples, sample_rate=sample_rate, start=0.045, duration=0.070, frequency=930.0, end_frequency=990.0, amplitude=0.046, shape="triangle", attack=0.004, release=0.032, decay=2.8)
    return samples


def _casino_menu_back(duration: float, sample_rate: int) -> list[float]:
    """A very short downward answer for backing out of casino UI."""

    samples = _blank(duration, sample_rate)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.090, frequency=670.0, end_frequency=430.0, amplitude=0.047, shape="triangle", attack=0.004, release=0.040, decay=2.5)
    return samples


def _casino_chip_bet(duration: float, sample_rate: int) -> list[float]:
    """Three ceramic contacts: lift, toss, and a chip settling on felt."""

    samples = _blank(duration, sample_rate)
    for index, (start, frequency, amplitude) in enumerate((
        (0.000, 1_620.0, 0.080),
        (0.058, 1_940.0, 0.092),
        (0.116, 1_480.0, 0.068),
    )):
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.022, amplitude=0.034, seed=45 + index, color="high", release=0.012, decay=5.5)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.052, frequency=frequency, end_frequency=frequency * 0.82, amplitude=amplitude, shape="triangle", attack=0.002, release=0.027, decay=4.3)
    _add_noise(samples, sample_rate=sample_rate, start=0.108, duration=0.066, amplitude=0.022, seed=48, color="low", attack=0.006, release=0.040, decay=3.8)
    return samples


def _casino_chip_stack(duration: float, sample_rate: int) -> list[float]:
    """A dealer raking loose chips into a compact stack."""

    samples = _blank(duration, sample_rate)
    contacts = (0.000, 0.041, 0.076, 0.107, 0.134, 0.158, 0.180, 0.204, 0.230)
    for index, start in enumerate(contacts):
        frequency = 1_310.0 + ((index % 3) * 230.0)
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.027, amplitude=0.032, seed=81 + index, color="high", release=0.014, decay=5.0)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.055, frequency=frequency, end_frequency=frequency * 0.78, amplitude=0.061, shape="triangle", attack=0.002, release=0.030, decay=4.0)
    _add_noise(samples, sample_rate=sample_rate, start=0.012, duration=0.250, amplitude=0.019, seed=90, color="low", attack=0.010, release=0.065, decay=1.8)
    return samples


def _casino_chip_payout(duration: float, sample_rate: int) -> list[float]:
    """A slightly wider chip cascade that reads as chips coming back."""

    samples = _blank(duration, sample_rate)
    contacts = (0.000, 0.048, 0.091, 0.130, 0.166, 0.200, 0.232, 0.263, 0.293)
    for index, start in enumerate(contacts):
        frequency = 1_220.0 + ((index % 4) * 205.0) + (index * 24.0)
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.029, amplitude=0.034, seed=93 + index, color="high", release=0.015, decay=5.2)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.060, frequency=frequency, end_frequency=frequency * 0.84, amplitude=0.065, shape="triangle", attack=0.002, release=0.033, decay=3.9)
    _add_noise(samples, sample_rate=sample_rate, start=0.025, duration=0.315, amplitude=0.019, seed=102, color="low", attack=0.012, release=0.075, decay=1.7)
    return samples


def _casino_machine_win(duration: float, sample_rate: int) -> list[float]:
    """A modest electromechanical win ding, deliberately short of a fanfare."""

    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.026, amplitude=0.026, seed=105, color="high", release=0.014, decay=6.0)
    for start, frequency, amplitude in (
        (0.010, 783.99, 0.070),
        (0.112, 987.77, 0.061),
        (0.226, 1_174.66, 0.052),
    ):
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.245, frequency=frequency, end_frequency=frequency * 0.997, amplitude=amplitude, shape="triangle", attack=0.004, release=0.145, decay=3.0)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.190, frequency=frequency * 2.01, end_frequency=frequency * 2.00, amplitude=amplitude * 0.24, attack=0.003, release=0.120, decay=3.5)
    return samples


def _work(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.055, amplitude=0.09, seed=51, color="high", release=0.025, decay=5.5)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.25, frequency=684.0, end_frequency=603.0, amplitude=0.12, shape="triangle", release=0.09, decay=4.0)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.19, frequency=1_382.0, end_frequency=1_103.0, amplitude=0.055, release=0.075, decay=5.0)
    _add_tone(samples, sample_rate=sample_rate, start=0.075, duration=0.11, frequency=174.0, end_frequency=108.0, amplitude=0.12, release=0.05, decay=3.5)
    return samples


def _gunfire(duration: float, sample_rate: int) -> list[float]:
    """A compact double report: dry pop, short body, then a lighter second pop."""

    samples = _blank(duration, sample_rate)
    for index, (start, scale) in enumerate(((0.0, 1.0), (0.108, 0.82))):
        _add_noise(
            samples,
            sample_rate=sample_rate,
            start=start,
            duration=0.052,
            amplitude=0.44 * scale,
            seed=56 + index,
            color="high",
            attack=0.001,
            release=0.034,
            decay=6.8,
        )
        _add_tone(
            samples,
            sample_rate=sample_rate,
            start=start,
            duration=0.082,
            frequency=218.0 - index * 17.0,
            end_frequency=94.0 - index * 8.0,
            amplitude=0.30 * scale,
            shape="soft_square",
            attack=0.001,
            release=0.052,
            decay=5.0,
        )
        _add_tone(
            samples,
            sample_rate=sample_rate,
            start=start + 0.006,
            duration=0.105,
            frequency=86.0 - index * 6.0,
            end_frequency=48.0,
            amplitude=0.18 * scale,
            attack=0.002,
            release=0.068,
            decay=4.2,
        )
    _add_noise(samples, sample_rate=sample_rate, start=0.19, duration=0.11, amplitude=0.038, seed=58, color="low", attack=0.012, release=0.07, decay=3.8)
    return samples


def _flora_sparkle(duration: float, sample_rate: int) -> list[float]:
    """Two quiet glassy flecks, intentionally short of a magical flourish."""

    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.018, duration=0.048, amplitude=0.020, seed=59, color="high", attack=0.008, release=0.028, decay=3.8)
    _add_tone(samples, sample_rate=sample_rate, start=0.018, duration=0.14, frequency=987.77, end_frequency=1_046.5, amplitude=0.047, shape="triangle", attack=0.018, release=0.075, decay=2.6)
    _add_tone(samples, sample_rate=sample_rate, start=0.082, duration=0.13, frequency=1_318.51, end_frequency=1_395.0, amplitude=0.034, attack=0.022, release=0.072, decay=2.8)
    return samples


def _flora_plant_tinkle(duration: float, sample_rate: int) -> list[float]:
    """A small descending glass gesture that settles rather than announces."""

    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.016, duration=0.052, amplitude=0.016, seed=60, color="high", attack=0.010, release=0.030, decay=3.6)
    _add_tone(samples, sample_rate=sample_rate, start=0.014, duration=0.17, frequency=1_318.51, end_frequency=1_174.66, amplitude=0.030, shape="triangle", attack=0.020, release=0.090, decay=2.5)
    _add_tone(samples, sample_rate=sample_rate, start=0.072, duration=0.17, frequency=1_046.50, end_frequency=987.77, amplitude=0.037, shape="triangle", attack=0.022, release=0.090, decay=2.7)
    _add_tone(samples, sample_rate=sample_rate, start=0.136, duration=0.13, frequency=783.99, end_frequency=698.46, amplitude=0.026, shape="triangle", attack=0.024, release=0.074, decay=2.9)
    return samples


def _flora_harvest_tinkle(duration: float, sample_rate: int) -> list[float]:
    """A light rising gather gesture, related to but calmer than crossbreeding."""

    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.012, duration=0.050, amplitude=0.017, seed=63, color="high", attack=0.008, release=0.030, decay=3.8)
    _add_tone(samples, sample_rate=sample_rate, start=0.012, duration=0.15, frequency=783.99, end_frequency=880.00, amplitude=0.038, shape="triangle", attack=0.018, release=0.080, decay=2.7)
    _add_tone(samples, sample_rate=sample_rate, start=0.074, duration=0.15, frequency=1_046.50, end_frequency=1_174.66, amplitude=0.032, shape="triangle", attack=0.020, release=0.080, decay=2.8)
    _add_tone(samples, sample_rate=sample_rate, start=0.132, duration=0.13, frequency=1_395.00, end_frequency=1_567.98, amplitude=0.024, shape="triangle", attack=0.022, release=0.072, decay=3.0)
    return samples


def _impact(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.14, amplitude=0.26, seed=61, color="low", release=0.06, decay=5.5)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.19, frequency=91.0, end_frequency=39.0, amplitude=0.34, release=0.07, decay=3.0)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.052, amplitude=0.12, seed=62, color="high", release=0.025, decay=7.0)
    return samples


def _danger(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    for start, base in ((0.0, 78.0), (0.31, 73.0)):
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.31, frequency=base, end_frequency=base * 0.91, amplitude=0.25, attack=0.012, release=0.11, decay=1.8)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.25, frequency=base * 2.0, end_frequency=base * 1.82, amplitude=0.11, shape="triangle", attack=0.008, release=0.09, decay=2.2)
    return samples


def _tire_scrub(duration: float, sample_rate: int) -> list[float]:
    """Restrained dusty tire scrub; duration is supplied by the cached variant."""

    samples = _blank(duration, sample_rate)
    body = max(0.10, float(duration) - 0.025)
    release = min(0.12, max(0.065, body * 0.38))
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=body, amplitude=0.105, seed=71 + int(round(duration * 100)), color="high", attack=0.022, release=release, decay=0.8)
    _add_noise(samples, sample_rate=sample_rate, start=0.008, duration=body * 0.92, amplitude=0.080, seed=72 + int(round(duration * 100)), color="low", attack=0.020, release=release, decay=1.0)
    _add_tone(samples, sample_rate=sample_rate, start=0.012, duration=body * 0.88, frequency=930.0, end_frequency=610.0, amplitude=0.040, shape="triangle", attack=0.030, release=release, decay=1.2)
    _add_tone(samples, sample_rate=sample_rate, start=0.020, duration=body * 0.78, frequency=1_390.0, end_frequency=920.0, amplitude=0.010, attack=0.035, release=release, decay=1.4)
    return samples


def _breaking_glass(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.16, amplitude=0.30, seed=81, color="high", attack=0.001, release=0.10, decay=4.4)
    _add_noise(samples, sample_rate=sample_rate, start=0.055, duration=0.37, amplitude=0.075, seed=82, color="high", attack=0.008, release=0.19, decay=2.1)
    shards = (
        (0.012, 2_280.0, 0.105),
        (0.047, 3_420.0, 0.085),
        (0.091, 2_760.0, 0.075),
        (0.144, 4_180.0, 0.058),
        (0.211, 3_090.0, 0.050),
        (0.284, 2_510.0, 0.040),
    )
    for index, (start, frequency, amplitude) in enumerate(shards):
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.16 + (index % 2) * 0.045, frequency=frequency, end_frequency=frequency * 0.72, amplitude=amplitude, shape="triangle", attack=0.002, release=0.105, decay=3.4)
    return samples


def _explosion(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.72, amplitude=0.40, seed=91, color="low", attack=0.001, release=0.30, decay=3.0)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.31, amplitude=0.34, seed=92, color="white", attack=0.001, release=0.17, decay=5.8)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.67, frequency=88.0, end_frequency=31.0, amplitude=0.43, shape="soft_square", attack=0.001, release=0.29, decay=2.8)
    _add_tone(samples, sample_rate=sample_rate, start=0.018, duration=0.48, frequency=47.0, end_frequency=28.0, amplitude=0.29, attack=0.003, release=0.24, decay=2.2)
    _add_noise(samples, sample_rate=sample_rate, start=0.29, duration=0.59, amplitude=0.075, seed=93, color="low", attack=0.025, release=0.30, decay=2.4)
    return samples


_MUSIC_STYLE_SPECS = {
    "city": {"root": 65.41, "scale": (0, 3, 5, 7, 10), "bpm": 96.0, "brightness": 1.00},
    "frontier": {"root": 73.42, "scale": (0, 2, 5, 7, 9), "bpm": 92.0, "brightness": 0.82},
    "wilderness": {"root": 65.41, "scale": (0, 4, 7, 9, 12), "bpm": 86.0, "brightness": 0.68},
    "coastal": {"root": 73.42, "scale": (0, 2, 7, 9, 14), "bpm": 84.0, "brightness": 0.72},
    "underground": {"root": 55.00, "scale": (0, 3, 5, 7, 10), "bpm": 78.0, "brightness": 0.48},
}


def _music_note_count(beat_count: int, *, armed: bool) -> int:
    bar_notes = math.ceil(max(4, int(beat_count)) / 4.0) * 3
    melody_step = 1 if armed else 2
    melody_notes = math.ceil(max(4, int(beat_count)) / melody_step) * 2
    bass_notes = max(4, int(round(max(4, int(beat_count)) * 0.375)))
    return int(bar_notes + melody_notes + bass_notes)


def _run_theme_passage(
    duration: float,
    sample_rate: int,
    *,
    style_key: str,
    armed: bool,
    variant: int,
    beat_count: int,
) -> list[float]:
    """One coherent passage shaped by the run's home or a visited biome."""

    spec = _MUSIC_STYLE_SPECS.get(style_key, _MUSIC_STYLE_SPECS["frontier"])
    root = float(spec["root"])
    scale = tuple(int(value) for value in spec["scale"])
    brightness = float(spec["brightness"])
    beat_count = max(4, int(beat_count))
    beat = float(duration) / float(beat_count)
    samples = _blank(duration, sample_rate)
    rng = random.Random(f"run-theme:{style_key}:{int(bool(armed))}:{variant}:{beat_count}")

    def degree_frequency(degree: int, octave: int = 0) -> float:
        semitones = scale[int(degree) % len(scale)] + (12 * int(octave))
        return root * (2.0 ** (semitones / 12.0))

    bar_count = math.ceil(beat_count / 4.0)
    for bar_index in range(bar_count):
        start = bar_index * 4.0 * beat
        base = degree_frequency((bar_index + variant) % len(scale))
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 2.55, frequency=base, amplitude=0.070 + (0.012 if armed else 0.0), shape="soft_square" if style_key == "city" or armed else "sine", attack=0.040, release=beat * 0.54, decay=1.7)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 1.85, frequency=base * 2.0, amplitude=0.037 * brightness, shape="triangle", attack=0.030, release=beat * 0.46, decay=2.2)
        _add_tone(samples, sample_rate=sample_rate, start=start + beat * 0.12, duration=beat * 1.15, frequency=base * 4.0, amplitude=0.018 * brightness, shape="triangle", attack=0.025, release=beat * 0.34, decay=2.8)

    melody_step = 1 if armed else 2
    melody_index = 0
    melody_beat = 0.50 + (0.25 if style_key == "city" else 0.0)
    while melody_beat < beat_count - 0.45:
        degree = rng.randrange(len(scale))
        frequency = degree_frequency(degree, octave=2)
        start = melody_beat * beat
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * (0.44 if armed else 0.58), frequency=frequency, amplitude=(0.088 if armed else 0.073) * brightness, shape="triangle", attack=0.012, release=beat * 0.22, decay=3.6)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 0.34, frequency=frequency * 2.002, amplitude=(0.020 if armed else 0.015) * brightness, attack=0.010, release=beat * 0.18, decay=4.3)
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.024, amplitude=0.012 * brightness, seed=610 + (variant * 100) + melody_index, color="high", release=0.012, decay=5.0)
        melody_index += 1
        melody_beat += melody_step

    bass_count = max(4, int(round(beat_count * 0.375)))
    for bass_index in range(bass_count):
        start = (bass_index * beat_count / float(bass_count)) * beat
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.20, frequency=root * (1.34 if armed else 1.18), end_frequency=root * 0.64, amplitude=0.105 if armed else 0.080, shape="soft_square" if armed else "sine", attack=0.004, release=0.075, decay=3.5)
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.062, amplitude=0.032 if armed else 0.022, seed=710 + (variant * 100) + bass_index, color="low", release=0.030, decay=4.5)

    accent_step = 2 if style_key == "city" or armed else 4
    for accent_index, accent_beat in enumerate(range(1, beat_count, accent_step)):
        _add_noise(samples, sample_rate=sample_rate, start=(accent_beat + 0.5) * beat, duration=0.043, amplitude=(0.024 if armed else 0.015) * brightness, seed=810 + (variant * 100) + accent_index, color="high", attack=0.006, release=0.025, decay=5.2)
    return samples


def _ambient_water(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.105, seed=401, color="low", attack=0.72, release=0.24)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.022, seed=402, color="high", attack=0.86, release=0.28)
    for index, start in enumerate((0.46, 1.58, 2.31)):
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.42, frequency=196.0 + (index * 24.0), end_frequency=154.0 + (index * 18.0), amplitude=0.026, attack=0.16, release=0.17, decay=1.6)
    return samples


def _ambient_campfire(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.052, seed=411, color="low", attack=0.20, release=0.22)
    for index, start in enumerate((0.28, 0.91, 1.47, 2.16, 2.49)):
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.055 + (index % 2) * 0.025, amplitude=0.17, seed=412 + index, color="high", release=0.04, decay=5.5)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.075, frequency=122.0 + index * 9.0, end_frequency=61.0, amplitude=0.075, release=0.045, decay=4.0)
    return samples


def _ambient_day(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.019, seed=421, color="low", attack=0.28, release=0.30)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.006, seed=422, color="high", attack=0.42, release=0.44)
    return samples


def _ambient_night(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.021, seed=431, color="low", attack=0.30, release=0.32)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=82.41, amplitude=0.035, attack=0.32, release=0.34)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=123.47, amplitude=0.018, shape="triangle", attack=0.36, release=0.36)
    return samples


def _ambient_biome_city(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.024, seed=441, color="low", attack=0.24, release=0.26)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=55.0, amplitude=0.052, attack=0.26, release=0.28)
    _add_tone(samples, sample_rate=sample_rate, start=0.44, duration=1.75, frequency=110.0, amplitude=0.018, shape="soft_square", attack=0.22, release=0.30)
    _add_tone(samples, sample_rate=sample_rate, start=2.12, duration=0.18, frequency=784.0, end_frequency=698.0, amplitude=0.020, release=0.10)
    return samples


def _ambient_biome_frontier(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.035, seed=451, color="low", attack=0.28, release=0.30)
    _add_tone(samples, sample_rate=sample_rate, start=0.34, duration=1.92, frequency=146.83, amplitude=0.036, attack=0.20, release=0.38)
    _add_tone(samples, sample_rate=sample_rate, start=0.82, duration=1.38, frequency=220.0, amplitude=0.018, shape="triangle", attack=0.18, release=0.32)
    return samples


def _ambient_biome_wilderness_day(duration: float, sample_rate: int) -> list[float]:
    """One restrained daytime cicada bout for intermittent playback."""

    samples = _blank(duration, sample_rate)
    for bout_index, start in enumerate(WILDERNESS_DAY_CICADA_BOUT_STARTS):
        for pulse in range(18):
            pulse_start = float(start) + (pulse * 0.036)
            contour = math.sin(math.pi * (pulse + 1) / 19.0)
            amplitude = 0.008 + (0.010 * contour)
            frequency = 4_280.0 + ((pulse % 3) * 145.0)
            _add_tone(
                samples,
                sample_rate=sample_rate,
                start=pulse_start,
                duration=0.046,
                frequency=frequency,
                end_frequency=frequency * 0.98,
                amplitude=amplitude,
                shape="soft_square",
                attack=0.011,
                release=0.017,
                decay=0.5,
                phase_offset=(bout_index + pulse) * 0.13,
            )
            _add_noise(
                samples,
                sample_rate=sample_rate,
                start=pulse_start,
                duration=0.040,
                amplitude=amplitude * 0.34,
                seed=462 + (bout_index * 40) + pulse,
                color="high",
                attack=0.010,
                release=0.016,
                decay=0.8,
            )
    return samples


def _ambient_biome_wilderness_night(duration: float, sample_rate: int) -> list[float]:
    """One small nighttime cricket cluster for intermittent playback."""

    samples = _blank(duration, sample_rate)
    for cluster_index, start in enumerate(WILDERNESS_NIGHT_CRICKET_CLUSTER_STARTS):
        for chirp in range(3):
            chirp_start = float(start) + (chirp * 0.145)
            base = 3_080.0 + (chirp * 95.0)
            _add_tone(
                samples,
                sample_rate=sample_rate,
                start=chirp_start,
                duration=0.060,
                frequency=base,
                end_frequency=base * 1.17,
                amplitude=0.025 - (chirp * 0.002),
                shape="sine",
                attack=0.010,
                release=0.032,
                decay=1.8,
                phase_offset=(cluster_index + chirp) * 0.17,
            )
            _add_tone(
                samples,
                sample_rate=sample_rate,
                start=chirp_start + 0.012,
                duration=0.040,
                frequency=base * 1.42,
                end_frequency=base * 1.31,
                amplitude=0.009,
                shape="triangle",
                attack=0.008,
                release=0.020,
                decay=2.2,
            )
    return samples


def _ambient_one_shot_rest_seconds(cue_name: str, rng: random.Random) -> float:
    rest_min, rest_max = AMBIENT_ONE_SHOT_REST_SECONDS_BY_CUE.get(
        cue_name,
        (6.0, 12.0),
    )
    mode = AMBIENT_ONE_SHOT_REST_MODE_SECONDS_BY_CUE.get(cue_name)
    if mode is None:
        return float(rng.uniform(float(rest_min), float(rest_max)))
    return float(rng.triangular(float(rest_min), float(rest_max), float(mode)))


def _ambient_biome_coastal(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.060, seed=471, color="low", attack=0.34, release=0.36)
    _add_tone(samples, sample_rate=sample_rate, start=0.18, duration=2.22, frequency=82.41, end_frequency=76.0, amplitude=0.034, attack=0.34, release=0.44)
    _add_tone(samples, sample_rate=sample_rate, start=0.62, duration=1.64, frequency=123.47, amplitude=0.018, attack=0.26, release=0.40)
    return samples


def _ambient_biome_underground(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.027, seed=481, color="low", attack=0.28, release=0.30)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=61.74, amplitude=0.048, attack=0.30, release=0.32)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=92.50, amplitude=0.022, shape="triangle", attack=0.34, release=0.34)
    _add_tone(samples, sample_rate=sample_rate, start=1.63, duration=0.24, frequency=1_180.0, end_frequency=510.0, amplitude=0.033, release=0.16, decay=2.2)
    return samples


def _ambient_crowd_chatter(duration: float, sample_rate: int) -> list[float]:
    """Low nonverbal voice texture for a nearby gathering, not canned speech."""

    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.026, seed=491, color="low", attack=0.30, release=0.32)
    voices = (
        (0.22, 0.46, 174.0),
        (0.61, 0.34, 226.0),
        (0.94, 0.51, 193.0),
        (1.38, 0.40, 248.0),
        (1.72, 0.48, 166.0),
        (2.13, 0.37, 213.0),
        (2.49, 0.52, 184.0),
        (2.96, 0.32, 236.0),
    )
    for index, (start, voice_duration, base) in enumerate(voices):
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=voice_duration, frequency=base, end_frequency=base * (1.04 if index % 2 else 0.96), amplitude=0.028, shape="soft_square", attack=0.055, release=0.11, decay=0.5)
        _add_tone(samples, sample_rate=sample_rate, start=start + 0.018, duration=voice_duration * 0.82, frequency=base * 2.35, end_frequency=base * 2.18, amplitude=0.009, attack=0.065, release=0.12, decay=0.8)
    return samples


def _combustion_engine(
    duration: float,
    sample_rate: int,
    *,
    base_frequency: float,
    pulse_interval: float,
    seed: int,
) -> list[float]:
    """A small, rough engine loop whose pulse rate rises with vehicle speed."""

    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.060, seed=seed, color="low", attack=0.045, release=0.055)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=base_frequency, amplitude=0.105, shape="soft_square", attack=0.040, release=0.050)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=base_frequency * 2.03, amplitude=0.044, shape="triangle", attack=0.045, release=0.055)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=base_frequency * 3.01, amplitude=0.018, attack=0.050, release=0.060)
    pulse_index = 0
    start = 0.055
    while start < duration - 0.10:
        scale = 0.92 + (0.08 if pulse_index % 3 == 0 else 0.0)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.075, frequency=base_frequency * 0.91, end_frequency=base_frequency * 0.66, amplitude=0.105 * scale, shape="soft_square", attack=0.004, release=0.045, decay=3.2)
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.052, amplitude=0.050 * scale, seed=seed + 1 + pulse_index, color="low", attack=0.003, release=0.034, decay=4.0)
        pulse_index += 1
        start += pulse_interval
    return samples


def _ambient_engine_idle(duration: float, sample_rate: int) -> list[float]:
    return _combustion_engine(duration, sample_rate, base_frequency=43.0, pulse_interval=0.235, seed=501)


def _ambient_engine_cruise(duration: float, sample_rate: int) -> list[float]:
    return _combustion_engine(duration, sample_rate, base_frequency=61.0, pulse_interval=0.145, seed=521)


def _ambient_engine_fast(duration: float, sample_rate: int) -> list[float]:
    return _combustion_engine(duration, sample_rate, base_frequency=79.0, pulse_interval=0.098, seed=541)


TIRE_SCRUB_CUE_NAMES = (
    "tire_scrub_short",
    "tire_scrub_medium",
    "tire_scrub_long",
)


DEFAULT_MUSIC_PROFILE = {
    "home_biome": "frontier",
    "armed": False,
    "home_passage_beats": (12, 16, 20),
    "theme_seed": "default-frontier",
    "label": "frontier home",
}


def _music_bpm(style_key: str, *, armed: bool) -> float:
    spec = _MUSIC_STYLE_SPECS.get(style_key, _MUSIC_STYLE_SPECS["frontier"])
    return float(spec["bpm"]) + (10.0 if armed else 0.0)


def _music_passage_builder(*, style_key: str, armed: bool, variant: int, beat_count: int):
    def build(duration: float, sample_rate: int) -> list[float]:
        return _run_theme_passage(
            duration,
            sample_rate,
            style_key=style_key,
            armed=armed,
            variant=variant,
            beat_count=beat_count,
        )

    return build


def _music_cue_definitions(profile: dict[str, object]) -> tuple[CueDefinition, ...]:
    profile = dict(profile or DEFAULT_MUSIC_PROFILE)
    home_biome = str(profile.get("home_biome", "frontier") or "frontier")
    if home_biome not in _MUSIC_STYLE_SPECS:
        home_biome = "frontier"
    armed = bool(profile.get("armed"))
    home_beats = tuple(int(value) for value in profile.get("home_passage_beats", (12, 16, 20)))
    if len(home_beats) != len(MUSIC_HOME_CUE_NAMES):
        home_beats = (12, 16, 20)

    definitions = []
    home_bpm = _music_bpm(home_biome, armed=armed)
    for variant, (cue_name, beat_count) in enumerate(zip(MUSIC_HOME_CUE_NAMES, home_beats)):
        definitions.append(CueDefinition(
            cue_name,
            max(4, beat_count) * (60.0 / home_bpm),
            _music_passage_builder(
                style_key=home_biome,
                armed=armed,
                variant=variant,
                beat_count=max(4, beat_count),
            ),
            gain=0.58 if armed else 0.55,
            loop=False,
            bus="music",
        ))

    representative_beats = {
        "city": 12,
        "frontier": 12,
        "wilderness": 12,
        "coastal": 12,
        "underground": 12,
    }
    for variant, (biome, cue_name) in enumerate(MUSIC_BIOME_CUE_BY_KEY.items(), start=10):
        beat_count = representative_beats[biome]
        definitions.append(CueDefinition(
            cue_name,
            beat_count * (60.0 / _music_bpm(biome, armed=False)),
            _music_passage_builder(
                style_key=biome,
                armed=False,
                variant=variant,
                beat_count=beat_count,
            ),
            gain=0.52,
            loop=False,
            bus="music",
        ))
    return tuple(definitions)


SFX_CUE_DEFINITIONS: tuple[CueDefinition, ...] = (
    CueDefinition("footstep", 0.14, _footstep, gain=0.50, cooldown=0.055),
    CueDefinition("door", 0.24, _door, gain=0.74, cooldown=0.08),
    CueDefinition("pickup", 0.17, _pickup, gain=0.72, cooldown=0.06),
    CueDefinition("transaction", 0.18, _transaction, gain=0.72, cooldown=0.12),
    CueDefinition("casino_menu_move", 0.06, _casino_menu_move, gain=0.42, cooldown=0.025),
    CueDefinition("casino_menu_confirm", 0.13, _casino_menu_confirm, gain=0.46, cooldown=0.06),
    CueDefinition("casino_menu_back", 0.11, _casino_menu_back, gain=0.42, cooldown=0.06),
    CueDefinition("casino_chip_bet", 0.19, _casino_chip_bet, gain=0.64, cooldown=0.10),
    CueDefinition("casino_chip_stack", 0.31, _casino_chip_stack, gain=0.60, cooldown=0.18),
    CueDefinition("casino_chip_payout", 0.40, _casino_chip_payout, gain=0.63, cooldown=0.20),
    CueDefinition("casino_machine_win", 0.55, _casino_machine_win, gain=0.58, cooldown=0.30),
    CueDefinition("work", 0.29, _work, gain=0.74, cooldown=0.15),
    CueDefinition("gunfire", 0.32, _gunfire, gain=0.86, cooldown=0.055),
    CueDefinition("flora_sparkle", 0.24, _flora_sparkle, gain=0.62, cooldown=0.16),
    CueDefinition("flora_plant_tinkle", 0.28, _flora_plant_tinkle, gain=0.56, cooldown=0.16),
    CueDefinition("flora_harvest_tinkle", 0.27, _flora_harvest_tinkle, gain=0.58, cooldown=0.16),
    CueDefinition("impact", 0.23, _impact, gain=0.88, cooldown=0.08),
    CueDefinition("danger", 0.68, _danger, gain=0.82, cooldown=1.0),
    CueDefinition("tire_scrub_short", 0.18, _tire_scrub, gain=0.48, cooldown=0.30),
    CueDefinition("tire_scrub_medium", 0.27, _tire_scrub, gain=0.47, cooldown=0.30),
    CueDefinition("tire_scrub_long", 0.36, _tire_scrub, gain=0.46, cooldown=0.30),
    CueDefinition("breaking_glass", 0.55, _breaking_glass, gain=0.76, cooldown=0.10),
    CueDefinition("explosion", 0.90, _explosion, gain=0.92, cooldown=0.12),
)

AMBIENT_CUE_DEFINITIONS: tuple[CueDefinition, ...] = (
    CueDefinition("ambient_water", 2.8, _ambient_water, gain=0.30, loop=False, bus="ambient"),
    CueDefinition("ambient_campfire", 2.8, _ambient_campfire, gain=0.34, loop=False, bus="ambient"),
    CueDefinition("ambient_day", 3.5, _ambient_day, gain=0.27, loop=True, bus="ambient"),
    CueDefinition("ambient_night", 3.5, _ambient_night, gain=0.26, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_city", 2.8, _ambient_biome_city, gain=0.22, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_frontier", 2.8, _ambient_biome_frontier, gain=0.23, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_wilderness_day", 0.82, _ambient_biome_wilderness_day, gain=0.23, loop=False, bus="ambient"),
    CueDefinition("ambient_biome_wilderness_night", 0.54, _ambient_biome_wilderness_night, gain=0.23, loop=False, bus="ambient"),
    CueDefinition("ambient_biome_coastal", 2.8, _ambient_biome_coastal, gain=0.22, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_underground", 2.8, _ambient_biome_underground, gain=0.22, loop=True, bus="ambient"),
    CueDefinition("ambient_crowd_chatter", 3.4, _ambient_crowd_chatter, gain=0.38, loop=True, bus="ambient"),
    CueDefinition("ambient_engine_idle", 2.0, _ambient_engine_idle, gain=0.30, loop=True, bus="ambient"),
    CueDefinition("ambient_engine_cruise", 2.0, _ambient_engine_cruise, gain=0.31, loop=True, bus="ambient"),
    CueDefinition("ambient_engine_fast", 2.0, _ambient_engine_fast, gain=0.32, loop=True, bus="ambient"),
)

CUE_DEFINITIONS: tuple[CueDefinition, ...] = (
    SFX_CUE_DEFINITIONS
    + _music_cue_definitions(DEFAULT_MUSIC_PROFILE)
    + AMBIENT_CUE_DEFINITIONS
)

AMBIENT_CUE_BY_GROUP: dict[str, tuple[str, ...]] = {
    "water": ("ambient_water",),
    "campfire": ("ambient_campfire",),
    "time": ("ambient_day", "ambient_night"),
    "biome": (
        "ambient_biome_city",
        "ambient_biome_frontier",
        "ambient_biome_wilderness_day",
        "ambient_biome_wilderness_night",
        "ambient_biome_coastal",
        "ambient_biome_underground",
    ),
    "crowd": ("ambient_crowd_chatter",),
    "engine": ("ambient_engine_idle", "ambient_engine_cruise", "ambient_engine_fast"),
}

EVENT_CUE_MAP: dict[str, str] = {
    "player_moved": "footstep",
    "door_interacted": "door",
    "item_picked_up": "pickup",
    "trade_bought": "transaction",
    "trade_sold": "transaction",
    "street_deal_transaction": "transaction",
    "street_buy_transaction": "transaction",
    "mechanical_device_crafted": "work",
    "herbal_medicine_crafted": "work",
    "weapon_fired": "gunfire",
    "flora_crossbred": "flora_sparkle",
    "flora_planted": "flora_plant_tinkle",
    "flora_harvested": "flora_harvest_tinkle",
    "entity_damaged": "impact",
    "combat_overlay_entered": "danger",
}

EVENT_CUE_VARIANTS: dict[str, tuple[str, ...]] = {
    # Tire scrubs remain cached for later tuning, but fast-turn routing is
    # intentionally muted because a frequent steering cue can become grating.
    # "vehicle_fast_turn": TIRE_SCRUB_CUE_NAMES,
}

WORLD_EVENT_CUE_MAP: dict[str, str] = {
    "structure_broken": "breaking_glass",
    "explosion_triggered": "explosion",
}

CASINO_EVENT_CUE_MAP: dict[str, str] = {
    "casino_chips_bet": "casino_chip_bet",
    "casino_menu_backed": "casino_menu_back",
    "casino_menu_confirmed": "casino_menu_confirm",
    "casino_menu_moved": "casino_menu_move",
}


def _tire_scrub_cue_name(event_data: dict[str, object], sequence: int) -> str:
    try:
        speed = max(2, int(event_data.get("speed_before", 2) or 2))
    except (TypeError, ValueError):
        speed = 2
    try:
        turn = int(event_data.get("turn", 0) or 0)
    except (TypeError, ValueError):
        turn = 0
    options = TIRE_SCRUB_CUE_NAMES[:2] if speed <= 2 else TIRE_SCRUB_CUE_NAMES[1:]
    offset = 1 if turn > 0 else 0
    return options[(max(0, int(sequence)) + offset) % len(options)]


def _pcm_bytes(samples: Iterable[float], channel_count: int) -> tuple[bytes, float]:
    values = list(samples)
    peak = max((abs(value) for value in values), default=0.0)
    scale = 0.92 / max(1.0, peak)
    packed = bytearray()
    for value in values:
        sample = max(-1.0, min(1.0, float(value) * scale))
        encoded = struct.pack("<h", int(round(sample * 32_767)))
        packed.extend(encoded * int(channel_count))
    return bytes(packed), peak


def _wav_bytes(pcm: bytes, sample_rate: int, channel_count: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channel_count)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def build_cues(
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channel_count: int = DEFAULT_CHANNEL_COUNT,
    music_profile: dict[str, object] | None = None,
    progress_callback=None,
) -> tuple[RenderedCue, ...]:
    sample_rate = max(8_000, int(sample_rate))
    channel_count = max(1, min(2, int(channel_count)))
    rendered = []
    definitions = (
        SFX_CUE_DEFINITIONS
        + _music_cue_definitions(music_profile or DEFAULT_MUSIC_PROFILE)
        + AMBIENT_CUE_DEFINITIONS
    )
    _report_audio_progress(progress_callback, "audio_synthesize", 0, len(definitions), "Preparing sound bank")
    for index, definition in enumerate(definitions, start=1):
        samples = definition.builder(definition.duration, sample_rate)
        pcm, peak = _pcm_bytes(samples, channel_count)
        rendered.append(RenderedCue(
            definition=definition,
            pcm=pcm,
            wav=_wav_bytes(pcm, sample_rate, channel_count),
            sample_rate=sample_rate,
            channel_count=channel_count,
            peak=peak,
        ))
        _report_audio_progress(
            progress_callback,
            "audio_synthesize",
            index,
            len(definitions),
            definition.name.replace("_", " "),
        )
    return tuple(rendered)


def validate_cues(cues: Iterable[RenderedCue], *, progress_callback=None) -> dict[str, float | int]:
    cues = tuple(cues)
    _report_audio_progress(progress_callback, "audio_validate", 0, len(cues), "Checking sound bank")
    names = [cue.definition.name for cue in cues]
    if len(names) != len(set(names)):
        raise AssertionError("cue names must be unique")
    if set(EVENT_CUE_MAP.values()) - set(names):
        raise AssertionError("an action event references an unknown cue")
    variant_names = {
        name
        for cue_names in EVENT_CUE_VARIANTS.values()
        for name in cue_names
    }
    if variant_names - set(names):
        raise AssertionError("an action event variant references an unknown cue")
    if set(WORLD_EVENT_CUE_MAP.values()) - set(names):
        raise AssertionError("a world event references an unknown cue")
    casino_cue_names = set(CASINO_EVENT_CUE_MAP.values()) | {
        "casino_chip_bet",
        "casino_chip_stack",
        "casino_chip_payout",
        "casino_machine_win",
    }
    if casino_cue_names - set(names):
        raise AssertionError("a casino event references an unknown cue")
    music_cues = tuple(cue for cue in cues if cue.definition.bus == "music")
    if tuple(cue.definition.name for cue in music_cues) != MUSIC_CUE_NAMES:
        raise AssertionError("the cached music passage family drifted")
    if any(cue.definition.loop for cue in music_cues):
        raise AssertionError("music passages must be one-shot bursts")
    ambient_names = {
        name
        for names in AMBIENT_CUE_BY_GROUP.values()
        for name in names
    }
    if ambient_names != {cue.definition.name for cue in cues if cue.definition.bus == "ambient"}:
        raise AssertionError("ambient cue groups drifted from the cached bank")
    total_pcm = 0
    largest_peak = 0
    for index, cue in enumerate(cues, start=1):
        with wave.open(io.BytesIO(cue.wav), "rb") as wav_file:
            if wav_file.getnchannels() != cue.channel_count:
                raise AssertionError(f"{cue.definition.name}: wrong channel count")
            if wav_file.getsampwidth() != SAMPLE_WIDTH:
                raise AssertionError(f"{cue.definition.name}: wrong sample width")
            if wav_file.getframerate() != cue.sample_rate:
                raise AssertionError(f"{cue.definition.name}: wrong sample rate")
            if wav_file.getnframes() != cue.frame_count:
                raise AssertionError(f"{cue.definition.name}: frame count mismatch")
        if abs(cue.duration - cue.definition.duration) > (1.5 / cue.sample_rate):
            raise AssertionError(f"{cue.definition.name}: duration drift")
        pcm_values = tuple(value[0] for value in struct.iter_unpack("<h", cue.pcm))
        audible_peak = max((abs(value) for value in pcm_values), default=0)
        if audible_peak < 128:
            raise AssertionError(f"{cue.definition.name}: effectively silent")
        if audible_peak > 30_200:
            raise AssertionError(f"{cue.definition.name}: lost synthesis headroom")
        if cue.definition.loop and (abs(pcm_values[0]) > 4 or abs(pcm_values[-1]) > 4):
            raise AssertionError(f"{cue.definition.name}: loop boundary is not at zero")
        total_pcm += len(cue.pcm)
        largest_peak = max(largest_peak, audible_peak)
        _report_audio_progress(
            progress_callback,
            "audio_validate",
            index,
            len(cues),
            cue.definition.name.replace("_", " "),
        )

    bytes_per_second = cues[0].sample_rate * cues[0].channel_count * SAMPLE_WIDTH if cues else 1
    if total_pcm > bytes_per_second * 130:
        raise AssertionError("the cached bank exceeded its one-hundred-thirty-second PCM budget")
    return {
        "cue_count": len(cues),
        "total_pcm_bytes": total_pcm,
        "largest_pcm_peak": largest_peak,
    }


def _report_audio_progress(callback, stage, completed, total, detail=""):
    if not callable(callback):
        return
    try:
        callback(str(stage), int(completed), int(total), str(detail or ""))
    except Exception:
        # Loading feedback must never be allowed to disable otherwise-valid audio.
        return


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw not in {"0", "false", "no", "off", "disabled"}


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = str(os.getenv(name, "") or "").strip()
    try:
        value = float(raw) if raw else float(default)
    except (TypeError, ValueError):
        value = float(default)
    return max(float(minimum), min(float(maximum), value))


def _player_position(sim, player_eid):
    try:
        from game.components import Position

        return sim.ecs.get(Position).get(player_eid)
    except (AttributeError, TypeError):
        return None


def _active_combustion_vehicle_context(sim, player_eid) -> dict[str, object]:
    context = {
        "active": False,
        "speed": 0,
        "top_speed": 0,
        "medium": "",
        "vehicle_id": "",
    }
    try:
        from game.components import VehicleState
        from game.property_runtime import property_metadata, vehicle_fuel_values
        from game.vehicle_motion import active_vehicle_property, vehicle_medium_for_property, vehicle_top_speed

        state = sim.ecs.get(VehicleState).get(player_eid)
        if state is None or not bool(getattr(state, "in_vehicle", False)):
            return context
        prop = active_vehicle_property(sim, state)
        if not isinstance(prop, dict):
            return context
        metadata = property_metadata(prop)
        explicit_powertrain = str(
            metadata.get("powertrain")
            or metadata.get("propulsion")
            or metadata.get("engine_type")
            or ""
        ).strip().lower()
        non_combustion = {"electric", "ev", "pedal", "human", "sail", "wind"}
        fuel, fuel_capacity = vehicle_fuel_values(prop)
        if explicit_powertrain in non_combustion or int(fuel_capacity) <= 0 or int(fuel) <= 0:
            return context
        if not bool(metadata.get("vehicle_usable", True)) or int(metadata.get("durability", 1) or 0) <= 0:
            return context
        top_speed = max(1, int(vehicle_top_speed(prop)))
        return {
            "active": True,
            "speed": max(0, min(top_speed, int(getattr(state, "speed", 0) or 0))),
            "top_speed": top_speed,
            "medium": str(vehicle_medium_for_property(prop) or "land"),
            "vehicle_id": str(prop.get("id", "") or ""),
        }
    except (AttributeError, TypeError, ValueError):
        return context


def _biome_key(area_type: str, terrain: str, z: int) -> str:
    if int(z) < 0:
        return "underground"
    area = str(area_type or "").strip().lower()
    terrain = str(terrain or "").strip().lower()
    if area in {"city", "frontier", "wilderness", "coastal"}:
        return area
    if terrain in {"shore", "shoals", "lake", "island", "ocean", "waterway", "cliffs"}:
        return "coastal"
    if terrain in {"forest", "hills", "marsh", "plains"}:
        return "wilderness"
    return "frontier"


def music_profile_for_run(sim, player_eid, *, descriptor=None) -> dict[str, object]:
    """Choose the run's musical home once from its starting player and place."""

    pos = _player_position(sim, player_eid)
    z = int(getattr(pos, "z", 0) or 0) if pos is not None else 0
    descriptor = descriptor if isinstance(descriptor, dict) else {}
    active_chunk = getattr(sim, "active_chunk", None)
    district = active_chunk.get("district", {}) if isinstance(active_chunk, dict) else {}
    if not isinstance(district, dict):
        district = {}
    area_type = str(descriptor.get("area_type", district.get("area_type", "frontier")) or "frontier")
    terrain = str(descriptor.get("terrain", district.get("terrain", "plains")) or "plains")
    home_biome = _biome_key(area_type, terrain, z)

    armed = False
    try:
        from game.components import WeaponLoadout

        loadout = sim.ecs.get(WeaponLoadout).get(player_eid)
        weapon_ids = tuple(getattr(loadout, "weapon_ids", ()) or ()) if loadout is not None else ()
        current_weapon = loadout.current_weapon() if loadout is not None and hasattr(loadout, "current_weapon") else getattr(loadout, "equipped_weapon_id", None)
        armed = bool(weapon_ids or current_weapon)
    except (AttributeError, TypeError):
        armed = False

    theme_seed = f"{getattr(sim, 'seed', 0)}:music-home:{player_eid}:{home_biome}:{int(armed)}"
    rng = random.Random(theme_seed)
    home_passage_beats = tuple(sorted(rng.sample((12, 16, 20, 24), 3)))
    label = f"{'armed ' if armed else ''}{home_biome} home"
    return {
        "home_biome": home_biome,
        "armed": armed,
        "home_passage_beats": home_passage_beats,
        "theme_seed": theme_seed,
        "label": label,
    }


def _nearby_human_npc_count(sim, player_eid, x: int, y: int, z: int) -> int:
    try:
        from game.components import AI, CreatureIdentity, Position, Vitality
        from game.human_identity import is_human_identity

        ais = sim.ecs.get(AI)
        identities = sim.ecs.get(CreatureIdentity)
        positions = sim.ecs.get(Position)
        vitalities = sim.ecs.get(Vitality)
    except (AttributeError, TypeError):
        return 0

    nearby_reader = getattr(sim, "entity_ids_in_radius", None)
    if callable(nearby_reader):
        try:
            candidates = tuple(nearby_reader(x, y, z, CROWD_CHATTER_RADIUS) or ())
        except (AttributeError, TypeError, ValueError):
            candidates = ()
    else:
        candidates = tuple(positions)

    count = 0
    for eid in candidates:
        if eid == player_eid or eid not in ais:
            continue
        pos = positions.get(eid)
        identity = identities.get(eid)
        if pos is None or identity is None or not is_human_identity(identity):
            continue
        vitality = vitalities.get(eid)
        if vitality is not None and bool(getattr(vitality, "downed", False)):
            continue
        try:
            distance = abs(int(pos.x) - x) + abs(int(pos.y) - y)
            same_floor = int(pos.z) == z
        except (AttributeError, TypeError, ValueError):
            continue
        if same_floor and distance <= CROWD_CHATTER_RADIUS:
            count += 1
    return count


def sample_environment_context(sim, player_eid, *, descriptor=None) -> dict[str, object]:
    """Read a bounded, player-local ambience snapshot from live simulation state."""

    pos = _player_position(sim, player_eid)
    if pos is None:
        return {
            "available": False,
            "phase": "day",
            "biome": "city",
            "area_type": "city",
            "terrain": "urban",
            "water": 0.0,
            "campfire": 0.0,
            "crowd": 0.0,
            "crowd_count": 0,
            "engine": False,
            "vehicle_speed": 0,
            "vehicle_top_speed": 0,
            "vehicle_medium": "",
            "indoors": False,
        }

    x, y, z = int(pos.x), int(pos.y), int(pos.z)
    descriptor = descriptor if isinstance(descriptor, dict) else {}
    active_chunk = getattr(sim, "active_chunk", None)
    district = active_chunk.get("district", {}) if isinstance(active_chunk, dict) else {}
    if not isinstance(district, dict):
        district = {}
    area_type = str(descriptor.get("area_type", district.get("area_type", "city")) or "city").strip().lower()
    terrain = str(descriptor.get("terrain", district.get("terrain", "urban")) or "urban").strip().lower()

    try:
        from game.lighting import clock_snapshot, is_interior_tile

        phase = str(clock_snapshot(sim).get("phase", "day") or "day").strip().lower()
        indoors = bool(is_interior_tile(sim, x, y, z))
    except (AttributeError, TypeError, ValueError):
        phase = "day"
        indoors = False

    water_strength = 0.0
    tilemap = getattr(sim, "tilemap", None)
    tile_at = getattr(tilemap, "tile_at", None)
    water_radius = 6
    if callable(tile_at):
        for dy in range(-water_radius, water_radius + 1):
            for dx in range(-water_radius, water_radius + 1):
                distance = abs(dx) + abs(dy)
                if distance > water_radius:
                    continue
                tile = tile_at(x + dx, y + dy, z)
                glyph = str(getattr(tile, "glyph", "") or "")[:1]
                semantic = str(getattr(tile, "semantic_id", "") or "").strip().lower()
                if glyph != "~" and "water" not in semantic:
                    continue
                water_strength = max(water_strength, (water_radius + 1 - distance) / (water_radius + 1))

    campfire_strength = 0.0
    nearby_properties = getattr(sim, "properties_in_radius", None)
    if callable(nearby_properties):
        for prop in nearby_properties(x, y, z, r=7) or ():
            if not isinstance(prop, dict):
                continue
            metadata = prop.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            fixture = str(
                metadata.get("fixture_type")
                or metadata.get("archetype")
                or prop.get("kind")
                or ""
            ).strip().lower()
            if "campfire" not in fixture:
                continue
            try:
                distance = abs(int(prop.get("x", x)) - x) + abs(int(prop.get("y", y)) - y)
            except (TypeError, ValueError):
                continue
            campfire_strength = max(campfire_strength, (8 - min(8, distance)) / 8.0)

    crowd_count = _nearby_human_npc_count(sim, player_eid, x, y, z)
    if crowd_count < CROWD_CHATTER_MIN_NPCS:
        crowd_strength = 0.0
    else:
        crowd_strength = min(1.0, 0.40 + ((crowd_count - CROWD_CHATTER_MIN_NPCS) * 0.15))

    vehicle_context = _active_combustion_vehicle_context(sim, player_eid)

    return {
        "available": True,
        "phase": phase,
        "biome": _biome_key(area_type, terrain, z),
        "area_type": area_type,
        "terrain": terrain,
        "water": round(max(0.0, min(1.0, water_strength)), 3),
        "campfire": round(max(0.0, min(1.0, campfire_strength)), 3),
        "crowd": round(max(0.0, min(1.0, crowd_strength)), 3),
        "crowd_count": int(crowd_count),
        "engine": bool(vehicle_context.get("active")),
        "vehicle_speed": int(vehicle_context.get("speed", 0) or 0),
        "vehicle_top_speed": int(vehicle_context.get("top_speed", 0) or 0),
        "vehicle_medium": str(vehicle_context.get("medium", "") or ""),
        "vehicle_id": str(vehicle_context.get("vehicle_id", "") or ""),
        "indoors": indoors,
        "position": (x, y, z),
    }


class PygameAudioRuntime:
    """Subscribe cached pygame sounds to a deliberately small event palette."""

    def __init__(
        self,
        sim,
        pygame,
        player_eid,
        *,
        mixer_buffer: int = DEFAULT_MIXER_BUFFER,
        start_music: bool | None = None,
        progress_callback=None,
    ):
        self.sim = sim
        self.pygame = pygame
        self.player_eid = player_eid
        self.mixer_buffer = max(64, int(mixer_buffer))
        self.enabled = _env_enabled("BAKERRRR_AUDIO", True)
        self.debug = _env_enabled("BAKERRRR_AUDIO_DEBUG", False)
        self.master_volume = _env_float("BAKERRRR_AUDIO_VOLUME", 0.72, minimum=0.0, maximum=1.0)
        self.music_volume = _env_float("BAKERRRR_BGM_VOLUME", 1.0, minimum=0.0, maximum=2.0)
        self.ambient_volume = _env_float("BAKERRRR_AMBIENCE_VOLUME", 1.0, minimum=0.0, maximum=2.0)
        self.music_requested = _env_enabled("BAKERRRR_BGM", True) if start_music is None else bool(start_music)
        self.ambience_requested = _env_enabled("BAKERRRR_AMBIENCE", True)
        self.disabled_reason = ""
        self.generation_ms = 0.0
        self.bank_bytes = 0
        self.sample_rate = 0
        self.channel_count = 0
        self.sample_size = 0
        self.cue_counts = Counter()
        self.event_counts = Counter()
        self.suppressed_count = 0
        self.no_channel_count = 0
        self.submit_count = 0
        self.last_submit_ms = 0.0
        self.max_submit_ms = 0.0
        self.frame_count = 0
        self.late_frame_count = 0
        self.severe_frame_count = 0
        self.last_frame_ms = 0.0
        self.max_frame_ms = 0.0
        self.last_lag_phase = ""
        self.environment_sample_count = 0
        self.last_environment_sample_ms = 0.0
        self.max_environment_sample_ms = 0.0
        self.ambient_switch_count = 0
        self._last_played_at: dict[str, float] = {}
        self._last_debug_lag_at = 0.0
        self._sounds = {}
        self._music_channel = None
        self._music_playing = False
        self._music_schedule_enabled = False
        self._music_burst_count = 0
        self._music_burst_counts = Counter()
        self._music_current_cue = ""
        self._music_last_cue = ""
        self._music_last_biome = ""
        self._music_next_at = math.inf
        self._music_last_silence_seconds = 0.0
        self._music_profile = dict(DEFAULT_MUSIC_PROFILE)
        self._music_rng = random.Random("bakerrrr-music-default")
        self._ambient_channels = {}
        self._ambient_current = {group: "" for group in AMBIENT_CHANNEL_INDEX}
        self._ambient_levels = {group: 0.0 for group in AMBIENT_CHANNEL_INDEX}
        self._ambient_desired = {group: ("", 0.0) for group in AMBIENT_CHANNEL_INDEX}
        self._ambient_one_shot_next_at = {group: math.inf for group in AMBIENT_CHANNEL_INDEX}
        self._ambient_rng = random.Random(
            f"{getattr(sim, 'seed', 0)}:ambient-schedule:{player_eid}"
        )
        self._ambient_context: dict[str, object] = {"available": False}
        self._environment_dirty = True
        self._next_environment_sample_at = 0.0
        self._last_ambient_update_at = time.perf_counter()
        self._descriptor_coord = None
        self._descriptor_cache: dict[str, object] = {}

        _report_audio_progress(progress_callback, "audio_prepare", 0, 1, "Checking audio mixer")
        if not self.enabled:
            self.disabled_reason = "BAKERRRR_AUDIO disabled"
            _report_audio_progress(progress_callback, "audio_ready", 1, 1, "Audio disabled")
            return
        mixer_init = pygame.mixer.get_init()
        if not mixer_init:
            self.enabled = False
            self.disabled_reason = "pygame mixer unavailable"
            _report_audio_progress(progress_callback, "audio_ready", 1, 1, "Audio mixer unavailable")
            return
        self.sample_rate, self.sample_size, self.channel_count = (int(value) for value in mixer_init)
        if self.sample_size != -16 or self.channel_count not in {1, 2}:
            self.enabled = False
            self.disabled_reason = f"unsupported mixer format {mixer_init}"
            _report_audio_progress(progress_callback, "audio_ready", 1, 1, "Audio format unsupported")
            return

        self._music_profile = music_profile_for_run(
            self.sim,
            self.player_eid,
            descriptor=self._descriptor_for_player(),
        )
        self._music_last_biome = str(self._music_profile.get("home_biome", "frontier") or "frontier")
        self._music_rng = random.Random(f"{self._music_profile.get('theme_seed', 'default')}:schedule")

        started = time.perf_counter()
        cues = build_cues(
            sample_rate=self.sample_rate,
            channel_count=self.channel_count,
            music_profile=self._music_profile,
            progress_callback=progress_callback,
        )
        stats = validate_cues(cues, progress_callback=progress_callback)
        self.generation_ms = (time.perf_counter() - started) * 1_000.0
        self.bank_bytes = int(stats["total_pcm_bytes"])
        self._definitions = {cue.definition.name: cue.definition for cue in cues}

        pygame.mixer.set_num_channels(max(MIN_MIXER_CHANNEL_COUNT, pygame.mixer.get_num_channels()))
        pygame.mixer.set_reserved(RESERVED_CHANNEL_COUNT)
        self._music_channel = pygame.mixer.Channel(0)
        self._ambient_channels = {
            group: pygame.mixer.Channel(index)
            for group, index in AMBIENT_CHANNEL_INDEX.items()
        }
        _report_audio_progress(progress_callback, "audio_decode", 0, len(cues), "Loading cached sounds")
        for index, cue in enumerate(cues, start=1):
            self._sounds[cue.definition.name] = pygame.mixer.Sound(file=io.BytesIO(cue.wav))
            _report_audio_progress(
                progress_callback,
                "audio_decode",
                index,
                len(cues),
                cue.definition.name.replace("_", " "),
            )
        for event_type in EVENT_CUE_MAP.keys() | EVENT_CUE_VARIANTS.keys() | WORLD_SOUND_EVENTS | ENVIRONMENT_DIRTY_EVENTS | CASINO_SOUND_EVENTS:
            sim.events.subscribe(event_type, self.on_event)
        sim.events.subscribe("quit_requested", self.on_quit_requested)

        if self.music_requested:
            self.start_music()
        if self.ambience_requested:
            self.refresh_environment(force=True)
        self._trace(
            "ready "
            f"mixer={self.sample_rate}Hz/{self.sample_size}/{self.channel_count}ch "
            f"buffer={self.mixer_buffer} bank={self.bank_bytes}B generation={self.generation_ms:.1f}ms"
        )
        _report_audio_progress(progress_callback, "audio_ready", 1, 1, "Sound bank ready")

    def _trace(self, message: str) -> None:
        if self.debug:
            print(f"[bakerrrr audio] {message}", file=sys.stderr, flush=True)

    def _event_is_for_player(self, event) -> bool:
        data = event.data
        if event.type == "entity_damaged":
            return data.get("target_eid") == self.player_eid
        if event.type == "combat_overlay_entered":
            return data.get("player_eid") == self.player_eid
        return data.get("eid") == self.player_eid

    def _event_proximity_scale(self, event, audible_radius: int) -> float:
        pos = _player_position(self.sim, self.player_eid)
        if pos is None:
            return 0.0
        data = event.data
        try:
            event_x = int(data["x"])
            event_y = int(data["y"])
            event_z = int(data.get("z", 0))
        except (KeyError, TypeError, ValueError):
            return 1.0 if data.get("source_eid") == self.player_eid else 0.0
        if int(pos.z) != event_z:
            return 0.0
        radius = max(1, int(audible_radius))
        distance = abs(int(pos.x) - event_x) + abs(int(pos.y) - event_y)
        if distance > radius:
            return 0.0
        return max(0.18, min(1.0, 1.0 - (distance / float(radius + 1))))

    def _play_world_event(self, event) -> None:
        cue_name = WORLD_EVENT_CUE_MAP.get(event.type)
        if event.type == "structure_broken":
            surface = str(event.data.get("surface_kind", "") or "").strip().lower()
            aperture = str(event.data.get("aperture_kind", "") or "").strip().lower()
            if surface != "window" and "window" not in aperture:
                return
            volume_scale = self._event_proximity_scale(event, GLASS_AUDIBLE_RADIUS)
        elif event.type == "explosion_triggered":
            active_vehicle_id = str(self._ambient_context.get("vehicle_id", "") or "")
            exploded_vehicle_id = str(
                event.data.get("vehicle_id")
                or event.data.get("source_property_id")
                or ""
            )
            if active_vehicle_id and exploded_vehicle_id == active_vehicle_id:
                self._environment_dirty = True
            try:
                blast_radius = max(0, int(event.data.get("radius", 0) or 0))
            except (TypeError, ValueError):
                blast_radius = 0
            audible_radius = max(EXPLOSION_MIN_AUDIBLE_RADIUS, min(28, blast_radius * 4))
            volume_scale = self._event_proximity_scale(event, audible_radius)
        else:
            return
        if not cue_name or volume_scale <= 0.0:
            return
        self.event_counts[event.type] += 1
        self.play(cue_name, source_event=event.type, volume_scale=volume_scale)

    def _casino_ui_matches(self, event, *, service="", table_id="") -> bool:
        state = getattr(self.sim, "casino_ui", None)
        if not isinstance(state, dict) or not bool(state.get("open")):
            return False
        event_property = str(event.data.get("property_id", "") or "")
        state_property = str(state.get("property_id", "") or "")
        if event_property and event_property != state_property:
            return False
        service = str(service or event.data.get("service", "") or "").strip().lower()
        state_service = str(state.get("service", "") or "").strip().lower()
        if service and service != state_service:
            return False
        table_id = str(table_id or event.data.get("table_id", "") or "")
        if table_id:
            art = state.get("art") if isinstance(state.get("art"), dict) else {}
            visible_table_id = str(art.get("table_id", "") or "")
            if visible_table_id != table_id:
                return False
        return True

    def _play_casino_event(self, event) -> None:
        data = event.data
        if event.type in CASINO_EVENT_CUE_MAP:
            if data.get("eid") != self.player_eid or not self._casino_ui_matches(event):
                return
            cue_name = CASINO_EVENT_CUE_MAP[event.type]
        elif event.type == "site_service_used":
            service = str(data.get("service", "") or "").strip().lower()
            if service not in CASINO_GAME_SERVICE_IDS:
                return
            if data.get("eid") != self.player_eid or not self._casino_ui_matches(event, service=service):
                return
            try:
                payout = max(0, int(data.get("payout", 0) or 0))
                net_credits = int(data.get("net_credits", 0) or 0)
            except (TypeError, ValueError):
                payout = 0
                net_credits = 0
            if service in CASINO_MACHINE_SERVICE_IDS:
                if net_credits <= 0:
                    return
                cue_name = "casino_machine_win"
            elif payout > 0:
                cue_name = "casino_chip_payout"
            else:
                cue_name = "casino_chip_stack"
        elif event.type in {
            "holdem_cash_action",
            "holdem_cash_actor_left",
            "holdem_cash_actor_seated",
            "holdem_cash_hand_started",
            "holdem_cash_hand_settled",
        }:
            actor_is_player = data.get("actor_eid") == self.player_eid
            physical_player_cash = actor_is_player and event.type in {"holdem_cash_actor_seated", "holdem_cash_actor_left"}
            if not physical_player_cash and not self._casino_ui_matches(event, service="texas_holdem_cash"):
                return
            state = getattr(self.sim, "casino_ui", {})
            art = state.get("art") if isinstance(state.get("art"), dict) else {}
            if event.type == "holdem_cash_action":
                try:
                    paid = max(0, int(data.get("paid", 0) or 0))
                except (TypeError, ValueError):
                    paid = 0
                if paid <= 0:
                    return
                cue_name = "casino_chip_bet"
            elif event.type == "holdem_cash_hand_started":
                cue_name = "casino_chip_bet"
            elif event.type == "holdem_cash_actor_seated":
                cue_name = "casino_chip_stack"
            elif event.type == "holdem_cash_actor_left":
                try:
                    chips = max(0, int(data.get("chips", 0) or 0))
                except (TypeError, ValueError):
                    chips = 0
                if chips <= 0:
                    return
                cue_name = "casino_chip_payout" if actor_is_player else "casino_chip_stack"
            else:
                awards = data.get("awards") if isinstance(data.get("awards"), dict) else {}
                try:
                    hero_seat = int(art.get("hero_seat"))
                except (TypeError, ValueError):
                    hero_seat = -1
                player_won = any(
                    str(index) == str(hero_seat) and int(amount or 0) > 0
                    for index, amount in awards.items()
                )
                cue_name = "casino_chip_payout" if player_won else "casino_chip_stack"
        else:
            return
        self.event_counts[event.type] += 1
        self.play(cue_name, source_event=event.type)

    def on_event(self, event) -> None:
        if not self.enabled:
            return
        if event.type in WORLD_SOUND_EVENTS:
            self._play_world_event(event)
            return
        if event.type in CASINO_SOUND_EVENTS:
            self._play_casino_event(event)
            return
        is_player_event = self._event_is_for_player(event)
        if event.type in ENVIRONMENT_DIRTY_EVENTS and is_player_event:
            self._environment_dirty = True
        if not is_player_event:
            return
        sequence = int(self.event_counts.get(event.type, 0))
        cooldown_key = None
        if event.type == "vehicle_fast_turn":
            cue_name = _tire_scrub_cue_name(event.data, sequence)
            cooldown_key = "tire_scrub"
        else:
            cue_name = EVENT_CUE_MAP.get(event.type)
        if not cue_name:
            return
        self.event_counts[event.type] += 1
        self.play(cue_name, source_event=event.type, cooldown_key=cooldown_key)

    def _find_sfx_channel(self):
        num_channels = int(self.pygame.mixer.get_num_channels())
        for index in range(RESERVED_CHANNEL_COUNT, num_channels):
            channel = self.pygame.mixer.Channel(index)
            if not channel.get_busy():
                return channel
        return None

    def play(
        self,
        cue_name: str,
        *,
        source_event: str = "manual",
        volume_scale: float = 1.0,
        cooldown_key: str | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        definition = self._definitions.get(str(cue_name))
        sound = self._sounds.get(str(cue_name))
        if definition is None or sound is None or definition.bus != "sfx":
            return False
        received_at = time.perf_counter()
        playback_key = str(cooldown_key or definition.name)
        last_played = self._last_played_at.get(playback_key, -10_000.0)
        if received_at - last_played < float(definition.cooldown):
            self.suppressed_count += 1
            return False
        channel = self._find_sfx_channel()
        if channel is None:
            self.no_channel_count += 1
            self._trace(f"no free channel: event={source_event} cue={definition.name}")
            return False
        channel.set_volume(min(1.0, self.master_volume * float(definition.gain) * max(0.0, min(1.0, float(volume_scale)))))
        channel.play(sound)
        submitted_at = time.perf_counter()
        submit_ms = (submitted_at - received_at) * 1_000.0
        self._last_played_at[playback_key] = submitted_at
        self.cue_counts[definition.name] += 1
        self.submit_count += 1
        self.last_submit_ms = submit_ms
        self.max_submit_ms = max(self.max_submit_ms, submit_ms)
        if submit_ms >= 4.0:
            self._trace(f"slow submit {submit_ms:.2f}ms: event={source_event} cue={definition.name}")
        return True

    def _choose_music_cue(self) -> str:
        home_biome = str(self._music_profile.get("home_biome", "frontier") or "frontier")
        current_biome = str(self._ambient_context.get("biome", home_biome) or home_biome)
        biome_changed = current_biome != self._music_last_biome
        away_from_home = current_biome != home_biome
        representative_due = away_from_home and (
            biome_changed or (self._music_burst_count > 0 and self._music_burst_count % 3 == 0)
        )
        self._music_last_biome = current_biome
        if representative_due:
            return MUSIC_BIOME_CUE_BY_KEY.get(current_biome, MUSIC_BIOME_CUE_BY_KEY["frontier"])

        choices = list(MUSIC_HOME_CUE_NAMES)
        cue_name = str(self._music_rng.choice(choices))
        if len(choices) > 1 and cue_name == self._music_last_cue:
            cue_name = choices[(choices.index(cue_name) + 1) % len(choices)]
        return cue_name

    def _play_music_burst(self) -> bool:
        if not self.enabled or self._music_channel is None or not self._music_schedule_enabled:
            return False
        cue_name = self._choose_music_cue()
        definition = self._definitions.get(cue_name)
        sound = self._sounds.get(cue_name)
        if definition is None or sound is None or definition.bus != "music":
            return False
        self._music_channel.set_volume(min(1.0, self.master_volume * self.music_volume * float(definition.gain)))
        self._music_channel.play(sound, loops=0, fade_ms=180)
        self._music_playing = True
        self._music_current_cue = cue_name
        self._music_last_cue = cue_name
        self._music_next_at = math.inf
        self._music_burst_count += 1
        self._music_burst_counts[cue_name] += 1
        self._trace(
            f"music burst {cue_name} ({definition.duration:.1f}s); "
            f"home={self._music_profile.get('label', 'run')}"
        )
        return True

    def start_music(self) -> bool:
        if not self.enabled or self._music_channel is None:
            return False
        self._music_schedule_enabled = True
        if self._music_channel.get_busy():
            return True
        self._music_next_at = 0.0
        return self._play_music_burst()

    def update_music(self, *, now: float | None = None) -> bool:
        if not self.enabled or not self._music_schedule_enabled or self._music_channel is None:
            return False
        now = time.perf_counter() if now is None else float(now)
        if self._music_playing:
            if self._music_channel.get_busy():
                return False
            self._music_playing = False
            self._music_current_cue = ""
            self._music_last_silence_seconds = self._music_rng.uniform(
                MUSIC_SILENCE_MIN_SECONDS,
                MUSIC_SILENCE_MAX_SECONDS,
            )
            self._music_next_at = now + self._music_last_silence_seconds
            self._trace(f"music resting {self._music_last_silence_seconds:.0f}s")
            return False
        if now < self._music_next_at:
            return False
        return self._play_music_burst()

    def stop_music(self, *, fade_ms: int = 250) -> None:
        self._music_schedule_enabled = False
        self._music_next_at = math.inf
        if self._music_channel is not None:
            self._music_channel.fadeout(max(0, int(fade_ms)))
        self._music_playing = False
        self._music_current_cue = ""

    def _descriptor_for_player(self) -> dict[str, object]:
        pos = _player_position(self.sim, self.player_eid)
        if pos is None:
            return {}
        chunk_coords = getattr(self.sim, "chunk_coords", None)
        try:
            coord = tuple(chunk_coords(int(pos.x), int(pos.y))) if callable(chunk_coords) else tuple(getattr(self.sim, "active_chunk_coord", ()) or ())
        except (TypeError, ValueError):
            coord = tuple(getattr(self.sim, "active_chunk_coord", ()) or ())
        if coord == self._descriptor_coord:
            return self._descriptor_cache
        descriptor = {}
        world = getattr(self.sim, "world", None)
        describe = getattr(world, "overworld_descriptor", None)
        if callable(describe) and len(coord) >= 2:
            try:
                candidate = describe(int(coord[0]), int(coord[1]))
                if isinstance(candidate, dict):
                    descriptor = dict(candidate)
            except (TypeError, ValueError):
                descriptor = {}
        self._descriptor_coord = coord
        self._descriptor_cache = descriptor
        return descriptor

    def _environment_targets(self, context: dict[str, object]) -> dict[str, tuple[str, float]]:
        if not bool(context.get("available")):
            return {group: ("", 0.0) for group in AMBIENT_CHANNEL_INDEX}
        phase = str(context.get("phase", "day") or "day").strip().lower()
        biome = str(context.get("biome", "city") or "city").strip().lower()
        indoors = bool(context.get("indoors"))
        water = float(context.get("water", 0.0) or 0.0)
        campfire = float(context.get("campfire", 0.0) or 0.0)
        crowd = float(context.get("crowd", 0.0) or 0.0)
        engine_active = bool(context.get("engine"))
        vehicle_speed = max(0, int(context.get("vehicle_speed", 0) or 0))
        vehicle_top_speed = max(1, int(context.get("vehicle_top_speed", 1) or 1))
        outside_scale = 0.28 if indoors else 1.0
        if biome == "underground":
            outside_scale = 0.18
        time_cue = "ambient_night" if phase in {"dusk", "night"} else "ambient_day"
        time_level = {"dawn": 0.78, "day": 1.0, "dusk": 0.82, "night": 1.0}.get(phase, 1.0)
        if biome == "underground":
            time_level = 0.10
        if biome == "wilderness":
            wilderness_period = "night" if phase in {"dusk", "night"} else "day"
            biome_cue = f"ambient_biome_wilderness_{wilderness_period}"
        else:
            biome_cue = f"ambient_biome_{biome}"
        if biome_cue not in self._definitions:
            biome_cue = "ambient_biome_frontier"
        if vehicle_speed <= 0:
            engine_cue = "ambient_engine_idle"
        elif vehicle_speed >= max(3, int(math.ceil(vehicle_top_speed * 0.72))):
            engine_cue = "ambient_engine_fast"
        else:
            engine_cue = "ambient_engine_cruise"
        engine_level = min(1.0, 0.58 + (0.42 * vehicle_speed / float(vehicle_top_speed)))
        return {
            "water": ("ambient_water" if water > 0.01 else "", water * outside_scale),
            "campfire": ("ambient_campfire" if campfire > 0.01 else "", campfire * (0.45 if indoors else 1.0)),
            "time": (time_cue, time_level * outside_scale),
            "biome": (biome_cue, 1.0 if biome == "underground" else (0.36 if indoors else 1.0)),
            "crowd": ("ambient_crowd_chatter" if crowd > 0.01 else "", crowd),
            "engine": (engine_cue if engine_active else "", engine_level if engine_active else 0.0),
        }

    def _play_ambient_one_shot(self, group: str, cue_name: str, now: float) -> None:
        channel = self._ambient_channels.get(group)
        sound = self._sounds.get(cue_name)
        definition = self._definitions.get(cue_name)
        if channel is None or sound is None or definition is None:
            return
        channel.play(sound, loops=0, fade_ms=90)
        rest_seconds = _ambient_one_shot_rest_seconds(cue_name, self._ambient_rng)
        self._ambient_one_shot_next_at[group] = (
            float(now) + float(definition.duration) + rest_seconds
        )

    def _start_ambient_cue(self, group: str, cue_name: str, now: float) -> None:
        channel = self._ambient_channels.get(group)
        sound = self._sounds.get(cue_name)
        definition = self._definitions.get(cue_name)
        if channel is None or sound is None or definition is None:
            return
        channel.set_volume(0.0)
        if definition.loop:
            channel.play(sound, loops=-1, fade_ms=90)
            self._ambient_one_shot_next_at[group] = math.inf
        else:
            initial_delay = AMBIENT_ONE_SHOT_INITIAL_DELAY_SECONDS_BY_CUE.get(cue_name)
            if initial_delay is None:
                self._play_ambient_one_shot(group, cue_name, now)
            else:
                delay_min, delay_max = initial_delay
                self._ambient_one_shot_next_at[group] = float(now) + self._ambient_rng.uniform(
                    float(delay_min),
                    float(delay_max),
                )
        self._ambient_current[group] = cue_name
        self._ambient_levels[group] = 0.0
        self.ambient_switch_count += 1

    def _apply_ambient_fades(self, now: float, *, immediate: bool = False) -> None:
        elapsed = max(0.0, min(0.25, float(now) - float(self._last_ambient_update_at)))
        self._last_ambient_update_at = float(now)
        for group in AMBIENT_CHANNEL_INDEX:
            desired_cue, desired_level = self._ambient_desired.get(group, ("", 0.0))
            desired_level = max(0.0, min(1.0, float(desired_level)))
            current_cue = self._ambient_current.get(group, "")
            channel = self._ambient_channels.get(group)
            if channel is None:
                continue

            if immediate and current_cue != desired_cue:
                channel.stop()
                self._ambient_current[group] = ""
                self._ambient_levels[group] = 0.0
                self._ambient_one_shot_next_at[group] = math.inf
                current_cue = ""

            if current_cue and current_cue != desired_cue:
                target = 0.0
            else:
                if not current_cue and desired_cue:
                    self._start_ambient_cue(group, desired_cue, now)
                    current_cue = desired_cue
                target = desired_level if current_cue == desired_cue else 0.0

            current_level = float(self._ambient_levels.get(group, 0.0))
            if current_level < target:
                attack_seconds = AMBIENT_ATTACK_SECONDS_BY_GROUP.get(group, ENVIRONMENT_FADE_SECONDS)
                attack_step = 1.0 if immediate else elapsed / max(0.01, float(attack_seconds))
                current_level = min(target, current_level + attack_step)
            elif current_level > target:
                release_seconds = AMBIENT_RELEASE_SECONDS_BY_GROUP.get(group, ENVIRONMENT_FADE_SECONDS)
                release_step = 1.0 if immediate else elapsed / max(0.01, float(release_seconds))
                current_level = max(target, current_level - release_step)
            self._ambient_levels[group] = current_level

            definition = self._definitions.get(current_cue)
            gain = float(definition.gain) if definition is not None else 0.0
            channel.set_volume(min(1.0, self.master_volume * self.ambient_volume * gain * current_level))

            if current_cue and current_cue != desired_cue and current_level <= 0.001:
                channel.stop()
                self._ambient_current[group] = ""
                self._ambient_one_shot_next_at[group] = math.inf
                if desired_cue:
                    self._start_ambient_cue(group, desired_cue, now)
                    if immediate:
                        self._ambient_levels[group] = desired_level
                        definition = self._definitions.get(desired_cue)
                        gain = float(definition.gain) if definition is not None else 0.0
                        channel.set_volume(min(1.0, self.master_volume * self.ambient_volume * gain * desired_level))
            elif current_cue and current_cue == desired_cue and not channel.get_busy():
                if definition is not None and definition.loop:
                    channel.play(self._sounds[current_cue], loops=-1, fade_ms=90)
                elif now >= float(self._ambient_one_shot_next_at.get(group, math.inf)):
                    self._play_ambient_one_shot(group, current_cue, now)

    def refresh_environment(self, *, force: bool = False, immediate: bool = False) -> bool:
        if not self.enabled or not self.ambience_requested:
            return False
        now = time.perf_counter()
        sampled = False
        if force or self._environment_dirty or now >= self._next_environment_sample_at:
            started = time.perf_counter()
            context = sample_environment_context(
                self.sim,
                self.player_eid,
                descriptor=self._descriptor_for_player(),
            )
            sample_ms = (time.perf_counter() - started) * 1_000.0
            self.environment_sample_count += 1
            self.last_environment_sample_ms = sample_ms
            self.max_environment_sample_ms = max(self.max_environment_sample_ms, sample_ms)
            previous_signature = tuple(self._ambient_context.get(key) for key in ("phase", "biome", "water", "campfire", "crowd_count", "engine", "vehicle_speed", "indoors"))
            next_signature = tuple(context.get(key) for key in ("phase", "biome", "water", "campfire", "crowd_count", "engine", "vehicle_speed", "indoors"))
            self._ambient_context = context
            self._ambient_desired = self._environment_targets(context)
            self._environment_dirty = False
            self._next_environment_sample_at = now + ENVIRONMENT_SAMPLE_INTERVAL
            sampled = True
            if next_signature != previous_signature:
                self._trace(
                    "ambience "
                    f"phase={context.get('phase')} biome={context.get('biome')} "
                    f"water={float(context.get('water', 0.0)):.2f} "
                    f"campfire={float(context.get('campfire', 0.0)):.2f} "
                    f"crowd={int(context.get('crowd_count', 0))} "
                    f"engine={bool(context.get('engine'))}:{int(context.get('vehicle_speed', 0))} "
                    f"indoors={bool(context.get('indoors'))} scan={sample_ms:.2f}ms"
                )
        self._apply_ambient_fades(now, immediate=immediate)
        return sampled

    def stop_ambience(self, *, fade_ms: int = 180) -> None:
        for group, channel in self._ambient_channels.items():
            channel.fadeout(max(0, int(fade_ms)))
            self._ambient_current[group] = ""
            self._ambient_levels[group] = 0.0
            self._ambient_one_shot_next_at[group] = math.inf

    def on_quit_requested(self, _event) -> None:
        self.stop_music(fade_ms=120)
        self.stop_ambience(fade_ms=120)

    def observe_frame(self, elapsed_seconds: float, *, phase: str = "play") -> None:
        observer_started = time.perf_counter()
        self.refresh_environment()
        self.update_music()
        observer_seconds = time.perf_counter() - observer_started
        elapsed_ms = max(0.0, (float(elapsed_seconds) + observer_seconds) * 1_000.0)
        self.frame_count += 1
        self.last_frame_ms = elapsed_ms
        self.max_frame_ms = max(self.max_frame_ms, elapsed_ms)
        if elapsed_ms <= 50.0:
            return
        self.late_frame_count += 1
        self.last_lag_phase = str(phase or "play")
        if elapsed_ms >= 100.0:
            self.severe_frame_count += 1
        now = time.perf_counter()
        if self.debug and now - self._last_debug_lag_at >= 1.0:
            self._last_debug_lag_at = now
            self._trace(
                f"long {self.last_lag_phase} frame {elapsed_ms:.1f}ms; "
                f"music_busy={bool(self._music_channel and self._music_channel.get_busy())}"
            )

    def snapshot(self) -> dict[str, object]:
        if not self.enabled:
            return {
                "enabled": False,
                "reason": self.disabled_reason or "disabled",
            }
        num_channels = int(self.pygame.mixer.get_num_channels())
        busy_ambient = sum(
            bool(self.pygame.mixer.Channel(index).get_busy())
            for index in AMBIENT_CHANNEL_INDEX.values()
        )
        busy_sfx = sum(
            bool(self.pygame.mixer.Channel(index).get_busy())
            for index in range(RESERVED_CHANNEL_COUNT, num_channels)
        )
        buffer_ms = (self.mixer_buffer / max(1, self.sample_rate)) * 1_000.0
        music_busy = bool(self._music_playing and self._music_channel and self._music_channel.get_busy())
        if not self._music_schedule_enabled:
            music_state = "off"
            music_rest_remaining = 0.0
        elif music_busy:
            music_state = "playing"
            music_rest_remaining = 0.0
        else:
            music_state = "resting"
            music_rest_remaining = max(0.0, float(self._music_next_at) - time.perf_counter()) if math.isfinite(self._music_next_at) else 0.0
        return {
            "enabled": True,
            "music_playing": music_busy,
            "music_state": music_state,
            "music_theme": str(self._music_profile.get("label", "run") or "run"),
            "music_home_biome": str(self._music_profile.get("home_biome", "frontier") or "frontier"),
            "music_armed_start": bool(self._music_profile.get("armed")),
            "music_current_cue": self._music_current_cue,
            "music_last_cue": self._music_last_cue,
            "music_burst_count": self._music_burst_count,
            "music_burst_counts": dict(sorted(self._music_burst_counts.items())),
            "music_rest_seconds": round(self._music_last_silence_seconds, 1),
            "music_rest_remaining_seconds": round(music_rest_remaining, 1),
            "sample_rate": self.sample_rate,
            "channel_count": self.channel_count,
            "mixer_buffer": self.mixer_buffer,
            "nominal_buffer_ms": round(buffer_ms, 2),
            "generation_ms": round(self.generation_ms, 2),
            "bank_bytes": self.bank_bytes,
            "music_volume": round(self.music_volume, 2),
            "ambient_volume": round(self.ambient_volume, 2),
            "busy_ambient_channels": busy_ambient,
            "ambient_channel_count": len(AMBIENT_CHANNEL_INDEX),
            "busy_sfx_channels": busy_sfx,
            "sfx_channel_count": max(0, num_channels - RESERVED_CHANNEL_COUNT),
            "ambient_context": dict(self._ambient_context),
            "ambient_cues": dict(self._ambient_current),
            "ambient_levels": {
                group: round(level, 3)
                for group, level in self._ambient_levels.items()
            },
            "environment_sample_count": self.environment_sample_count,
            "last_environment_sample_ms": round(self.last_environment_sample_ms, 3),
            "max_environment_sample_ms": round(self.max_environment_sample_ms, 3),
            "ambient_switch_count": self.ambient_switch_count,
            "submit_count": self.submit_count,
            "suppressed_count": self.suppressed_count,
            "no_channel_count": self.no_channel_count,
            "last_submit_ms": round(self.last_submit_ms, 3),
            "max_submit_ms": round(self.max_submit_ms, 3),
            "frame_count": self.frame_count,
            "late_frame_count": self.late_frame_count,
            "severe_frame_count": self.severe_frame_count,
            "last_frame_ms": round(self.last_frame_ms, 2),
            "max_frame_ms": round(self.max_frame_ms, 2),
            "last_lag_phase": self.last_lag_phase,
            "cue_counts": dict(sorted(self.cue_counts.items())),
            "event_counts": dict(sorted(self.event_counts.items())),
        }


__all__ = [
    "AMBIENT_ATTACK_SECONDS_BY_GROUP",
    "AMBIENT_CUE_BY_GROUP",
    "AMBIENT_RELEASE_SECONDS_BY_GROUP",
    "CASINO_EVENT_CUE_MAP",
    "CASINO_GAME_SERVICE_IDS",
    "CASINO_MACHINE_SERVICE_IDS",
    "CASINO_SOUND_EVENTS",
    "CUE_DEFINITIONS",
    "DEFAULT_MUSIC_PROFILE",
    "DEFAULT_CHANNEL_COUNT",
    "DEFAULT_MIXER_BUFFER",
    "DEFAULT_SAMPLE_RATE",
    "EVENT_CUE_MAP",
    "EVENT_CUE_VARIANTS",
    "MUSIC_BIOME_CUE_BY_KEY",
    "MUSIC_CUE_NAMES",
    "MUSIC_HOME_CUE_NAMES",
    "MUSIC_SILENCE_MAX_SECONDS",
    "MUSIC_SILENCE_MIN_SECONDS",
    "OPEN_RUN_BPM",
    "OPEN_RUN_DURATION",
    "PygameAudioRuntime",
    "RenderedCue",
    "TIRE_SCRUB_CUE_NAMES",
    "WORLD_EVENT_CUE_MAP",
    "build_cues",
    "music_profile_for_run",
    "sample_environment_context",
    "validate_cues",
]
