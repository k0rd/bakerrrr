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
OPEN_RUN_BPM = 92
OPEN_RUN_BEATS = 16
OPEN_RUN_DURATION = OPEN_RUN_BEATS * (60.0 / OPEN_RUN_BPM)
ENVIRONMENT_SAMPLE_INTERVAL = 0.35
ENVIRONMENT_FADE_SECONDS = 0.65
AMBIENT_CHANNEL_INDEX = {
    "water": 1,
    "campfire": 2,
    "time": 3,
    "biome": 4,
}
RESERVED_CHANNEL_COUNT = 1 + len(AMBIENT_CHANNEL_INDEX)


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
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.09, amplitude=0.16, seed=11, color="low", release=0.04, decay=4.5)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.105, frequency=118.0, end_frequency=72.0, amplitude=0.19, release=0.05, decay=4.0)
    _add_noise(samples, sample_rate=sample_rate, start=0.055, duration=0.055, amplitude=0.055, seed=12, color="high", release=0.025, decay=4.0)
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


def _work(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=0.055, amplitude=0.09, seed=51, color="high", release=0.025, decay=5.5)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.25, frequency=684.0, end_frequency=603.0, amplitude=0.12, shape="triangle", release=0.09, decay=4.0)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=0.19, frequency=1_382.0, end_frequency=1_103.0, amplitude=0.055, release=0.075, decay=5.0)
    _add_tone(samples, sample_rate=sample_rate, start=0.075, duration=0.11, frequency=174.0, end_frequency=108.0, amplitude=0.12, release=0.05, decay=3.5)
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


def _open_run_sketch(duration: float, sample_rate: int) -> list[float]:
    """Four sparse bars honoring the existing 92 BPM ``open_run`` brief."""

    samples = _blank(duration, sample_rate)
    beat = 60.0 / OPEN_RUN_BPM
    for beat_index, base in ((0, 73.42), (4, 65.41), (8, 77.78), (12, 73.42)):
        start = beat_index * beat
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 2.3, frequency=base, amplitude=0.09, attack=0.035, release=0.28, decay=2.0)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 1.55, frequency=base * 2.0, amplitude=0.045, shape="triangle", attack=0.025, release=0.24, decay=2.5)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 1.1, frequency=base * 4.0, amplitude=0.026, shape="triangle", attack=0.018, release=0.20, decay=3.0)

    plucks = (
        (0.50, 293.66),
        (2.75, 220.00),
        (4.50, 261.63),
        (7.00, 220.00),
        (8.50, 311.13),
        (10.75, 261.63),
        (12.50, 293.66),
        (14.75, 220.00),
    )
    for index, (beat_index, frequency) in enumerate(plucks):
        start = beat_index * beat
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 0.58, frequency=frequency, amplitude=0.105, shape="triangle", release=0.12, decay=4.2)
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=beat * 0.42, frequency=frequency * 2.003, amplitude=0.026, release=0.09, decay=5.0)
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.026, amplitude=0.018, seed=100 + index, color="high", release=0.012, decay=6.0)

    for index, beat_index in enumerate((0.0, 3.0, 6.0, 8.0, 11.0, 14.0)):
        start = beat_index * beat
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.19, frequency=94.0, end_frequency=48.0, amplitude=0.105, release=0.07, decay=3.8)
        _add_noise(samples, sample_rate=sample_rate, start=start, duration=0.065, amplitude=0.035, seed=200 + index, color="low", release=0.028, decay=5.0)

    for index, beat_index in enumerate((1.5, 5.5, 9.5, 13.5)):
        _add_noise(samples, sample_rate=sample_rate, start=beat_index * beat, duration=0.052, amplitude=0.028, seed=300 + index, color="high", release=0.025, decay=6.0)
    return samples


def _ambient_water(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.105, seed=401, color="low", attack=0.22, release=0.24)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.022, seed=402, color="high", attack=0.28, release=0.28)
    for index, start in enumerate((0.46, 1.58, 2.31)):
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.32, frequency=196.0 + (index * 24.0), end_frequency=154.0 + (index * 18.0), amplitude=0.026, attack=0.055, release=0.17, decay=1.6)
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
    for index, start in enumerate((0.68, 2.54)):
        base = 932.0 + index * 112.0
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.12, frequency=base, end_frequency=base * 1.19, amplitude=0.040, shape="sine", attack=0.018, release=0.06, decay=2.8)
        _add_tone(samples, sample_rate=sample_rate, start=start + 0.14, duration=0.10, frequency=base * 1.08, end_frequency=base * 1.29, amplitude=0.031, attack=0.015, release=0.05, decay=3.1)
    return samples


def _ambient_night(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.021, seed=431, color="low", attack=0.30, release=0.32)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=82.41, amplitude=0.035, attack=0.32, release=0.34)
    _add_tone(samples, sample_rate=sample_rate, start=0.0, duration=duration, frequency=123.47, amplitude=0.018, shape="triangle", attack=0.36, release=0.36)
    for index, start in enumerate((1.12, 1.30, 2.83, 3.01)):
        _add_tone(samples, sample_rate=sample_rate, start=start, duration=0.065, frequency=1_640.0 + index * 41.0, amplitude=0.025, release=0.035, decay=3.8)
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


def _ambient_biome_wilderness(duration: float, sample_rate: int) -> list[float]:
    samples = _blank(duration, sample_rate)
    _add_noise(samples, sample_rate=sample_rate, start=0.0, duration=duration, amplitude=0.031, seed=461, color="low", attack=0.28, release=0.30)
    _add_tone(samples, sample_rate=sample_rate, start=0.38, duration=1.78, frequency=196.0, amplitude=0.030, attack=0.22, release=0.36)
    _add_tone(samples, sample_rate=sample_rate, start=0.75, duration=1.44, frequency=293.66, amplitude=0.017, shape="triangle", attack=0.18, release=0.32)
    return samples


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


CUE_DEFINITIONS: tuple[CueDefinition, ...] = (
    CueDefinition("footstep", 0.14, _footstep, gain=0.62, cooldown=0.055),
    CueDefinition("door", 0.24, _door, gain=0.74, cooldown=0.08),
    CueDefinition("pickup", 0.17, _pickup, gain=0.72, cooldown=0.06),
    CueDefinition("transaction", 0.18, _transaction, gain=0.72, cooldown=0.12),
    CueDefinition("work", 0.29, _work, gain=0.74, cooldown=0.15),
    CueDefinition("impact", 0.23, _impact, gain=0.88, cooldown=0.08),
    CueDefinition("danger", 0.68, _danger, gain=0.82, cooldown=1.0),
    CueDefinition("open_run_sketch", OPEN_RUN_DURATION, _open_run_sketch, gain=0.62, loop=True, bus="music"),
    CueDefinition("ambient_water", 2.8, _ambient_water, gain=0.30, loop=True, bus="ambient"),
    CueDefinition("ambient_campfire", 2.8, _ambient_campfire, gain=0.34, loop=True, bus="ambient"),
    CueDefinition("ambient_day", 3.5, _ambient_day, gain=0.27, loop=True, bus="ambient"),
    CueDefinition("ambient_night", 3.5, _ambient_night, gain=0.26, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_city", 2.8, _ambient_biome_city, gain=0.22, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_frontier", 2.8, _ambient_biome_frontier, gain=0.23, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_wilderness", 2.8, _ambient_biome_wilderness, gain=0.23, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_coastal", 2.8, _ambient_biome_coastal, gain=0.22, loop=True, bus="ambient"),
    CueDefinition("ambient_biome_underground", 2.8, _ambient_biome_underground, gain=0.22, loop=True, bus="ambient"),
)

AMBIENT_CUE_BY_GROUP: dict[str, tuple[str, ...]] = {
    "water": ("ambient_water",),
    "campfire": ("ambient_campfire",),
    "time": ("ambient_day", "ambient_night"),
    "biome": (
        "ambient_biome_city",
        "ambient_biome_frontier",
        "ambient_biome_wilderness",
        "ambient_biome_coastal",
        "ambient_biome_underground",
    ),
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
    "entity_damaged": "impact",
    "combat_overlay_entered": "danger",
}


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
) -> tuple[RenderedCue, ...]:
    sample_rate = max(8_000, int(sample_rate))
    channel_count = max(1, min(2, int(channel_count)))
    rendered = []
    for definition in CUE_DEFINITIONS:
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
    return tuple(rendered)


def validate_cues(cues: Iterable[RenderedCue]) -> dict[str, float | int]:
    cues = tuple(cues)
    names = [cue.definition.name for cue in cues]
    if len(names) != len(set(names)):
        raise AssertionError("cue names must be unique")
    if set(EVENT_CUE_MAP.values()) - set(names):
        raise AssertionError("an action event references an unknown cue")
    music_loops = tuple(cue for cue in cues if cue.definition.bus == "music" and cue.definition.loop)
    if len(music_loops) != 1:
        raise AssertionError("the runtime must have exactly one music loop")
    ambient_names = {
        name
        for names in AMBIENT_CUE_BY_GROUP.values()
        for name in names
    }
    if ambient_names != {cue.definition.name for cue in cues if cue.definition.bus == "ambient"}:
        raise AssertionError("ambient cue groups drifted from the cached bank")
    if any(not cue.definition.loop for cue in cues if cue.definition.bus in {"music", "ambient"}):
        raise AssertionError("music and ambience cues must be loopable")

    total_pcm = 0
    largest_peak = 0
    for cue in cues:
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

    bytes_per_second = cues[0].sample_rate * cues[0].channel_count * SAMPLE_WIDTH if cues else 1
    if total_pcm > bytes_per_second * 40:
        raise AssertionError("the cached bank exceeded its forty-second PCM budget")
    return {
        "cue_count": len(cues),
        "total_pcm_bytes": total_pcm,
        "largest_pcm_peak": largest_peak,
    }


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

    return {
        "available": True,
        "phase": phase,
        "biome": _biome_key(area_type, terrain, z),
        "area_type": area_type,
        "terrain": terrain,
        "water": round(max(0.0, min(1.0, water_strength)), 3),
        "campfire": round(max(0.0, min(1.0, campfire_strength)), 3),
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
        self._ambient_channels = {}
        self._ambient_current = {group: "" for group in AMBIENT_CHANNEL_INDEX}
        self._ambient_levels = {group: 0.0 for group in AMBIENT_CHANNEL_INDEX}
        self._ambient_desired = {group: ("", 0.0) for group in AMBIENT_CHANNEL_INDEX}
        self._ambient_context: dict[str, object] = {"available": False}
        self._environment_dirty = True
        self._next_environment_sample_at = 0.0
        self._last_ambient_update_at = time.perf_counter()
        self._descriptor_coord = None
        self._descriptor_cache: dict[str, object] = {}

        if not self.enabled:
            self.disabled_reason = "BAKERRRR_AUDIO disabled"
            return
        mixer_init = pygame.mixer.get_init()
        if not mixer_init:
            self.enabled = False
            self.disabled_reason = "pygame mixer unavailable"
            return
        self.sample_rate, self.sample_size, self.channel_count = (int(value) for value in mixer_init)
        if self.sample_size != -16 or self.channel_count not in {1, 2}:
            self.enabled = False
            self.disabled_reason = f"unsupported mixer format {mixer_init}"
            return

        started = time.perf_counter()
        cues = build_cues(sample_rate=self.sample_rate, channel_count=self.channel_count)
        stats = validate_cues(cues)
        self.generation_ms = (time.perf_counter() - started) * 1_000.0
        self.bank_bytes = int(stats["total_pcm_bytes"])
        self._definitions = {cue.definition.name: cue.definition for cue in cues}

        pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
        pygame.mixer.set_reserved(RESERVED_CHANNEL_COUNT)
        self._music_channel = pygame.mixer.Channel(0)
        self._ambient_channels = {
            group: pygame.mixer.Channel(index)
            for group, index in AMBIENT_CHANNEL_INDEX.items()
        }
        self._sounds = {
            cue.definition.name: pygame.mixer.Sound(file=io.BytesIO(cue.wav))
            for cue in cues
        }
        for event_type in EVENT_CUE_MAP:
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

    def on_event(self, event) -> None:
        if not self.enabled or not self._event_is_for_player(event):
            return
        if event.type == "player_moved":
            self._environment_dirty = True
        cue_name = EVENT_CUE_MAP.get(event.type)
        if not cue_name:
            return
        self.event_counts[event.type] += 1
        self.play(cue_name, source_event=event.type)

    def play(self, cue_name: str, *, source_event: str = "manual") -> bool:
        if not self.enabled:
            return False
        definition = self._definitions.get(str(cue_name))
        sound = self._sounds.get(str(cue_name))
        if definition is None or sound is None or definition.loop:
            return False
        received_at = time.perf_counter()
        last_played = self._last_played_at.get(definition.name, -10_000.0)
        if received_at - last_played < float(definition.cooldown):
            self.suppressed_count += 1
            return False
        channel = self.pygame.mixer.find_channel(force=False)
        if channel is None:
            self.no_channel_count += 1
            self._trace(f"no free channel: event={source_event} cue={definition.name}")
            return False
        channel.set_volume(self.master_volume * float(definition.gain))
        channel.play(sound)
        submitted_at = time.perf_counter()
        submit_ms = (submitted_at - received_at) * 1_000.0
        self._last_played_at[definition.name] = submitted_at
        self.cue_counts[definition.name] += 1
        self.submit_count += 1
        self.last_submit_ms = submit_ms
        self.max_submit_ms = max(self.max_submit_ms, submit_ms)
        if submit_ms >= 4.0:
            self._trace(f"slow submit {submit_ms:.2f}ms: event={source_event} cue={definition.name}")
        return True

    def start_music(self) -> bool:
        if not self.enabled or self._music_channel is None:
            return False
        definition = self._definitions.get("open_run_sketch")
        sound = self._sounds.get("open_run_sketch")
        if definition is None or sound is None:
            return False
        self._music_channel.set_volume(min(1.0, self.master_volume * self.music_volume * float(definition.gain)))
        self._music_channel.play(sound, loops=-1, fade_ms=350)
        self._music_playing = True
        return True

    def stop_music(self, *, fade_ms: int = 250) -> None:
        if self._music_channel is not None:
            self._music_channel.fadeout(max(0, int(fade_ms)))
        self._music_playing = False

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
        outside_scale = 0.28 if indoors else 1.0
        if biome == "underground":
            outside_scale = 0.18
        time_cue = "ambient_night" if phase in {"dusk", "night"} else "ambient_day"
        time_level = {"dawn": 0.78, "day": 1.0, "dusk": 0.82, "night": 1.0}.get(phase, 1.0)
        if biome == "underground":
            time_level = 0.10
        biome_cue = f"ambient_biome_{biome}"
        if biome_cue not in self._definitions:
            biome_cue = "ambient_biome_frontier"
        return {
            "water": ("ambient_water" if water > 0.01 else "", water * outside_scale),
            "campfire": ("ambient_campfire" if campfire > 0.01 else "", campfire * (0.45 if indoors else 1.0)),
            "time": (time_cue, time_level * outside_scale),
            "biome": (biome_cue, 1.0 if biome == "underground" else (0.36 if indoors else 1.0)),
        }

    def _start_ambient_cue(self, group: str, cue_name: str) -> None:
        channel = self._ambient_channels.get(group)
        sound = self._sounds.get(cue_name)
        if channel is None or sound is None:
            return
        channel.set_volume(0.0)
        channel.play(sound, loops=-1, fade_ms=90)
        self._ambient_current[group] = cue_name
        self._ambient_levels[group] = 0.0
        self.ambient_switch_count += 1

    def _apply_ambient_fades(self, now: float, *, immediate: bool = False) -> None:
        elapsed = max(0.0, min(0.25, float(now) - float(self._last_ambient_update_at)))
        self._last_ambient_update_at = float(now)
        step = 1.0 if immediate else elapsed / ENVIRONMENT_FADE_SECONDS
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
                current_cue = ""

            if current_cue and current_cue != desired_cue:
                target = 0.0
            else:
                if not current_cue and desired_cue:
                    self._start_ambient_cue(group, desired_cue)
                    current_cue = desired_cue
                target = desired_level if current_cue == desired_cue else 0.0

            current_level = float(self._ambient_levels.get(group, 0.0))
            if current_level < target:
                current_level = min(target, current_level + step)
            elif current_level > target:
                current_level = max(target, current_level - step)
            self._ambient_levels[group] = current_level

            definition = self._definitions.get(current_cue)
            gain = float(definition.gain) if definition is not None else 0.0
            channel.set_volume(min(1.0, self.master_volume * self.ambient_volume * gain * current_level))

            if current_cue and current_cue != desired_cue and current_level <= 0.001:
                channel.stop()
                self._ambient_current[group] = ""
                if desired_cue:
                    self._start_ambient_cue(group, desired_cue)
                    if immediate:
                        self._ambient_levels[group] = desired_level
                        definition = self._definitions.get(desired_cue)
                        gain = float(definition.gain) if definition is not None else 0.0
                        channel.set_volume(min(1.0, self.master_volume * self.ambient_volume * gain * desired_level))
            elif current_cue and current_cue == desired_cue and not channel.get_busy():
                channel.play(self._sounds[current_cue], loops=-1, fade_ms=90)

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
            previous_signature = tuple(self._ambient_context.get(key) for key in ("phase", "biome", "water", "campfire", "indoors"))
            next_signature = tuple(context.get(key) for key in ("phase", "biome", "water", "campfire", "indoors"))
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
                    f"indoors={bool(context.get('indoors'))} scan={sample_ms:.2f}ms"
                )
        self._apply_ambient_fades(now, immediate=immediate)
        return sampled

    def stop_ambience(self, *, fade_ms: int = 180) -> None:
        for group, channel in self._ambient_channels.items():
            channel.fadeout(max(0, int(fade_ms)))
            self._ambient_current[group] = ""
            self._ambient_levels[group] = 0.0

    def on_quit_requested(self, _event) -> None:
        self.stop_music(fade_ms=120)
        self.stop_ambience(fade_ms=120)

    def observe_frame(self, elapsed_seconds: float, *, phase: str = "play") -> None:
        observer_started = time.perf_counter()
        self.refresh_environment()
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
        return {
            "enabled": True,
            "music_playing": bool(self._music_playing and self._music_channel and self._music_channel.get_busy()),
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
    "AMBIENT_CUE_BY_GROUP",
    "CUE_DEFINITIONS",
    "DEFAULT_CHANNEL_COUNT",
    "DEFAULT_MIXER_BUFFER",
    "DEFAULT_SAMPLE_RATE",
    "EVENT_CUE_MAP",
    "OPEN_RUN_BPM",
    "OPEN_RUN_DURATION",
    "PygameAudioRuntime",
    "RenderedCue",
    "build_cues",
    "sample_environment_context",
    "validate_cues",
]
