"""Idle loop thread — seamless looping MIDI file with position save/restore."""

import time
from typing import List, Tuple

import mido
from PyQt6.QtCore import QThread, pyqtSignal


class IdleLoopThread(QThread):
    tempo_changed = pyqtSignal(int)  # tempo_us

    def __init__(
        self,
        events: List[Tuple[float, mido.Message]],
        duration: float,
        tempo_map: List[Tuple[int, int]],
        router,
    ):
        super().__init__()
        self._events = events
        self._duration = duration
        self._tempo_map = tempo_map
        self._router = router

        self._stop_flag = False
        self._should_pause = False
        self._saved_loop_time = 0.0
        self.is_paused = False  # readable from main thread

    # ------------------------------------------------------------------
    # Control (main thread)
    # ------------------------------------------------------------------

    def pause_and_save(self):
        """Signal the loop to pause; block until it has actually paused."""
        self._should_pause = True
        deadline = time.perf_counter() + 0.1  # 100 ms max wait
        while time.perf_counter() < deadline:
            if self.is_paused:
                break
            time.sleep(0.001)

    def resume(self):
        """Resume from saved position."""
        self._should_pause = False

    def stop_thread(self):
        self._stop_flag = True
        self._should_pause = False

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self):
        if self._tempo_map:
            self.tempo_changed.emit(self._tempo_map[0][1])

        loop_time = self._saved_loop_time
        self._router.send_realtime(0xFA)  # MIDI Start

        while not self._stop_flag:
            if self._should_pause:
                # Silence before parking so no notes hang
                self._router.silence()
                self.is_paused = True
                while self._should_pause and not self._stop_flag:
                    time.sleep(0.005)
                self.is_paused = False
                if self._stop_flag:
                    break
                # Resume
                if self._tempo_map:
                    self.tempo_changed.emit(self._tempo_map[0][1])
                self._router.send_realtime(0xFB)  # MIDI Continue
                loop_time = self._saved_loop_time

            if not self._events:
                time.sleep(0.1)
                continue

            # Find starting event index for saved loop_time
            start_idx = 0
            for i, (t, _) in enumerate(self._events):
                if t >= loop_time:
                    break
                start_idx = i + 1
            else:
                start_idx = len(self._events)

            wall_start = time.perf_counter() - loop_time

            idx = start_idx
            while not self._stop_flag and not self._should_pause:
                now = time.perf_counter()
                elapsed = now - wall_start

                while idx < len(self._events) and self._events[idx][0] <= elapsed:
                    self._router.send(self._events[idx][1])
                    idx += 1

                # Seamless wrap
                if idx >= len(self._events):
                    if self._duration > 0 and elapsed >= self._duration:
                        loop_time = 0.0
                        break
                    remain = self._duration - elapsed
                    if remain > 0.001:
                        time.sleep(min(remain, 0.001))
                    continue

                next_t = self._events[idx][0]
                sleep = min(next_t - elapsed, 0.001)
                if sleep > 0.0001:
                    time.sleep(sleep)

            if self._should_pause:
                if idx < len(self._events):
                    self._saved_loop_time = self._events[idx][0]
                else:
                    self._saved_loop_time = 0.0

        self._router.silence()
        self._router.send_realtime(0xFC)  # MIDI Stop
