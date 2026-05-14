"""MIDI master clock thread — sends F8 at 24 PPQ, drift-corrected."""

import time
from PyQt6.QtCore import QThread


CLOCKS_PER_BEAT = 24


class ClockThread(QThread):
    def __init__(self, router):
        super().__init__()
        self._router = router
        self._stop = False
        self._running = False
        self.tempo_us = 500000  # microseconds per beat (120 BPM default)

    # ------------------------------------------------------------------
    # Control (call from any thread — simple flag-based, GIL-safe)
    # ------------------------------------------------------------------

    def start_clock(self):
        self._running = True

    def stop_clock(self):
        self._running = False

    def stop_thread(self):
        self._stop = True
        self._running = False

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self):
        next_clock = time.perf_counter()

        while not self._stop:
            if not self._running:
                time.sleep(0.002)
                next_clock = time.perf_counter()  # reset so no burst on resume
                continue

            now = time.perf_counter()
            if now >= next_clock:
                self._router.send_realtime(0xF8)  # MIDI Clock
                secs_per_clock = (self.tempo_us / 1_000_000) / CLOCKS_PER_BEAT
                next_clock += secs_per_clock
            else:
                remaining = next_clock - now
                if remaining > 0.0005:
                    time.sleep(remaining * 0.8)
