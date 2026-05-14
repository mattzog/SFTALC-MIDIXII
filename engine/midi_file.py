"""MIDI file parsing: tempo maps, event scheduling, bar counting."""

import mido
from typing import List, Tuple


def build_tempo_map(mid: mido.MidiFile):
    """Return (tempo_map, has_tempo) where tempo_map is [(abs_tick, us_per_beat), ...]
    and has_tempo is True if the file contained an explicit set_tempo event."""
    raw = []
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == 'set_tempo':
                raw.append((abs_tick, msg.tempo))
    raw.sort(key=lambda x: x[0])

    tempo_map = [(0, 500000)]  # 120 BPM default
    for tick, tempo in raw:
        if tick == 0:
            tempo_map[0] = (0, tempo)
        elif tick != tempo_map[-1][0]:
            tempo_map.append((tick, tempo))
        else:
            tempo_map[-1] = (tick, tempo)
    return tempo_map, len(raw) > 0


def ticks_to_seconds(tick: int, tpb: int, tempo_map: List[Tuple[int, int]]) -> float:
    """Convert an absolute tick position to wall-clock seconds."""
    seconds = 0.0
    prev_tick = 0
    prev_tempo = tempo_map[0][1]

    for map_tick, tempo in tempo_map:
        if map_tick >= tick:
            break
        seconds += ((min(map_tick, tick) - prev_tick) / tpb) * (prev_tempo / 1_000_000)
        prev_tick = map_tick
        prev_tempo = tempo

    seconds += ((tick - prev_tick) / tpb) * (prev_tempo / 1_000_000)
    return seconds


def _build_bar_start_ticks(
    max_tick: int,
    tpb: int,
    time_sig_events: List[Tuple[int, int, int]],
) -> List[int]:
    """Return absolute tick at the start of each bar."""
    bar_ticks = []
    tick = 0
    ts_idx = 0

    while tick <= max_tick:
        bar_ticks.append(tick)
        while ts_idx + 1 < len(time_sig_events) and time_sig_events[ts_idx + 1][0] <= tick:
            ts_idx += 1
        _, numerator, denominator = time_sig_events[ts_idx]
        ticks_per_bar = int(numerator * tpb * 4 / denominator)
        tick += ticks_per_bar

    return bar_ticks


def parse_midi_file(filepath: str):
    """
    Parse a standard MIDI file.

    Returns
    -------
    events : list of (time_seconds: float, msg: mido.Message)
        All non-meta channel messages sorted by time.
    total_bars : int
    bar_start_times : list of float
        Wall-clock seconds at the start of each bar.
    duration : float
        Total duration in seconds.
    tpb : int
        Ticks per beat (from file header).
    tempo_map : list of (tick, tempo_us)
    has_tempo : bool
        True if the file contained an explicit set_tempo event.
    """
    mid = mido.MidiFile(filepath)
    tpb = mid.ticks_per_beat

    # Merge all tracks into (abs_tick, msg) list
    merged: List[Tuple[int, mido.Message]] = []
    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            merged.append((abs_tick, msg))
    merged.sort(key=lambda x: x[0])

    tempo_map, has_tempo = build_tempo_map(mid)

    # Collect time signature events; mido gives denominator as actual value (4, 8, …)
    time_sig_events: List[Tuple[int, int, int]] = [(0, 4, 4)]
    for abs_tick, msg in merged:
        if msg.type == 'time_signature':
            time_sig_events.append((abs_tick, msg.numerator, msg.denominator))
    time_sig_events.sort(key=lambda x: x[0])

    max_tick = max((t for t, _ in merged), default=0)
    bar_start_ticks = _build_bar_start_ticks(max_tick, tpb, time_sig_events)
    total_bars = len(bar_start_ticks)
    bar_start_times = [ticks_to_seconds(t, tpb, tempo_map) for t in bar_start_ticks]
    duration = ticks_to_seconds(max_tick, tpb, tempo_map)

    events = []
    for abs_tick, msg in merged:
        if msg.is_meta:
            continue
        if msg.type == 'sysex':
            continue
        time_s = ticks_to_seconds(abs_tick, tpb, tempo_map)
        events.append((time_s, msg))

    return events, total_bars, bar_start_times, duration, tpb, tempo_map, has_tempo


def get_tempo_at_time(time_s: float, tpb: int, tempo_map: List[Tuple[int, int]]) -> int:
    """Return the MIDI tempo (µs/beat) in effect at the given wall-clock time."""
    current_tempo = tempo_map[0][1]
    elapsed = 0.0
    prev_tick = 0

    for map_tick, tempo in tempo_map:
        delta_ticks = map_tick - prev_tick
        delta_secs = (delta_ticks / tpb) * (current_tempo / 1_000_000)
        if elapsed + delta_secs >= time_s:
            break
        elapsed += delta_secs
        prev_tick = map_tick
        current_tempo = tempo

    return current_tempo
