"""Song playback thread — linear MIDI file playback with pause support."""

import time
from typing import List, Tuple, Optional

import mido
from PyQt6.QtCore import QThread, pyqtSignal

from .midi_file import get_tempo_at_time


class PlayerThread(QThread):
    bar_changed = pyqtSignal(int, int)   # bars_remaining, total_bars
    tempo_changed = pyqtSignal(int)      # tempo_us (for clock thread)
    finished = pyqtSignal()

    def __init__(
        self,
        events: List[Tuple[float, mido.Message]],
        bar_start_times: List[float],
        total_bars: int,
        duration: float,
        tpb: int,
        tempo_map: List[Tuple[int, int]],
        router,
        count_in_bars: int = 0,
        click_channel: int = 9,
        click_note: int = 76,
    ):
        super().__init__()
        self._events = events
        self._bar_start_times = bar_start_times
        self._total_bars = total_bars
        self._duration = duration
        self._tpb = tpb
        self._tempo_map = tempo_map
        self._router = router
        self._count_in_bars = count_in_bars
        self._click_channel = click_channel
        self._click_note = click_note

        self._stop_flag = False
        self._paused = False
        self._pause_start: Optional[float] = None
        self._pause_accumulated = 0.0

    # ------------------------------------------------------------------
    # Control (main thread)
    # ------------------------------------------------------------------

    def stop_playback(self):
        self._stop_flag = True

    def pause_playback(self):
        if not self._paused:
            self._paused = True
            self._pause_start = time.perf_counter()
            self._router.silence()
            self._router.send_realtime(0xFC)  # MIDI Stop

    def resume_playback(self):
        if self._paused and self._pause_start is not None:
            self._pause_accumulated += time.perf_counter() - self._pause_start
            self._pause_start = None
            self._paused = False
            self._router.send_realtime(0xFB)  # MIDI Continue

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_elapsed(self, wall_start: float) -> float:
        elapsed = time.perf_counter() - wall_start - self._pause_accumulated
        if self._paused and self._pause_start:
            elapsed -= (time.perf_counter() - self._pause_start)
        return elapsed

    def _run_count_in(self) -> bool:
        """Play count-in clicks. Returns False if stopped during count-in."""
        if self._count_in_bars <= 0:
            return True

        # Derive beat duration from first tempo
        tempo_us = self._tempo_map[0][1] if self._tempo_map else 500000
        beat_secs = tempo_us / 1_000_000
        # Assume 4/4 for count-in cadence
        total_beats = self._count_in_bars * 4

        self._router.send_realtime(0xFA)  # MIDI Start
        start = time.perf_counter()
        beat = 0
        bar = self._count_in_bars

        while beat < total_beats and not self._stop_flag:
            target = start + beat * beat_secs
            while time.perf_counter() < target and not self._stop_flag:
                time.sleep(0.001)
            if self._stop_flag:
                return False

            # Emit bar countdown
            if beat % 4 == 0:
                self.bar_changed.emit(bar, self._count_in_bars)
                bar -= 1

            # Click note on
            note_on = mido.Message('note_on', channel=self._click_channel,
                                   note=self._click_note, velocity=100)
            note_off = mido.Message('note_off', channel=self._click_channel,
                                    note=self._click_note, velocity=0)
            self._router.send(note_on)
            # Schedule note off 50 ms later (approximate — handled inline)
            beat += 1

            # note off 50ms after click
            off_time = target + 0.05
            while time.perf_counter() < off_time and not self._stop_flag:
                time.sleep(0.001)
            self._router.send(note_off)

        return not self._stop_flag

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self):
        # Build time-domain tempo map first so we can emit the correct initial tempo
        from .midi_file import ticks_to_seconds
        tempo_time_map: List[Tuple[float, int]] = []
        if self._tempo_map:
            for tick, tempo in self._tempo_map:
                t = ticks_to_seconds(tick, self._tpb, self._tempo_map)
                tempo_time_map.append((t, tempo))

        if tempo_time_map:
            self.tempo_changed.emit(tempo_time_map[0][1])

        if self._count_in_bars > 0:
            if not self._run_count_in():
                self.finished.emit()
                return
        else:
            self._router.send_realtime(0xFA)  # MIDI Start

        wall_start = time.perf_counter()
        event_idx = 0
        bar_idx = 0
        last_bar_emitted = -1
        tempo_time_idx = 0

        while not self._stop_flag:
            while self._paused and not self._stop_flag:
                time.sleep(0.005)
            if self._stop_flag:
                break

            elapsed = self._effective_elapsed(wall_start)

            # Advance tempo changes and notify clock
            while (tempo_time_idx + 1 < len(tempo_time_map)
                   and tempo_time_map[tempo_time_idx + 1][0] <= elapsed):
                tempo_time_idx += 1
                self.tempo_changed.emit(tempo_time_map[tempo_time_idx][1])

            # Update bar counter
            while bar_idx + 1 < len(self._bar_start_times) and self._bar_start_times[bar_idx + 1] <= elapsed:
                bar_idx += 1
            bars_remaining = max(0, self._total_bars - bar_idx - 1)
            if bars_remaining != last_bar_emitted:
                self.bar_changed.emit(bars_remaining, self._total_bars)
                last_bar_emitted = bars_remaining

            # Send due events
            while event_idx < len(self._events) and self._events[event_idx][0] <= elapsed:
                _, msg = self._events[event_idx]
                self._router.send(msg)
                event_idx += 1

            # Check for end of file
            if event_idx >= len(self._events) and elapsed >= self._duration:
                break

            # Sleep until next event or 1 ms
            next_event_time = self._events[event_idx][0] if event_idx < len(self._events) else elapsed + 0.1
            sleep = min(next_event_time - elapsed, 0.001)
            if sleep > 0.0001:
                time.sleep(sleep)

        self._router.silence()
        self._router.send_realtime(0xFC)  # MIDI Stop
        self.finished.emit()
