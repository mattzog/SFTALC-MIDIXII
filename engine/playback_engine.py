"""High-level coordinator: song player, idle loop, clock, and MIDI input."""

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .router import MidiRouter
from .clock import ClockThread
from .player import PlayerThread
from .idle_loop import IdleLoopThread
from .midi_input import MidiInputHandler
from .midi_file import parse_midi_file


class PlaybackEngine(QObject):
    # UI signals
    status_changed = pyqtSignal(str)         # 'idle', 'playing', 'paused', 'stopped'
    bar_changed = pyqtSignal(int, int)        # bars_remaining, total_bars
    tempo_changed = pyqtSignal(float)         # BPM
    song_finished = pyqtSignal()

    STATUS_IDLE = 'idle'
    STATUS_PLAYING = 'playing'
    STATUS_PAUSED = 'paused'
    STATUS_STOPPED = 'stopped'

    def __init__(self):
        super().__init__()
        self.router = MidiRouter()
        self.clock = ClockThread(self.router)
        self.input_handler = MidiInputHandler(self.router)

        self._player: Optional[PlayerThread] = None
        self._idle_loop: Optional[IdleLoopThread] = None
        self._status = self.STATUS_STOPPED

        self._song_events = []
        self._song_bar_times = []
        self._song_total_bars = 0
        self._song_duration = 0.0
        self._song_tpb = 480
        self._song_tempo_map = []
        self._song_has_tempo = False

        self._loop_events = []
        self._loop_duration = 0.0
        self._loop_tempo_map = []

        self._idle_loop_enabled = True
        self._count_in_bars = 0
        self._click_channel = 9
        self._click_note = 76

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_song(self, filepath: str) -> Optional[str]:
        """Load a MIDI file as the current song. Returns error string or None."""
        try:
            (self._song_events, self._song_total_bars,
             self._song_bar_times, self._song_duration,
             self._song_tpb, self._song_tempo_map,
             self._song_has_tempo) = parse_midi_file(filepath)
            return None
        except Exception as e:
            return str(e)

    def load_idle_loop(self, filepath: str) -> Optional[str]:
        """Load a MIDI file as the idle loop. Returns error string or None."""
        try:
            events, _, _, duration, _, tempo_map, _ = parse_midi_file(filepath)
            self._loop_events = events
            self._loop_duration = duration
            self._loop_tempo_map = tempo_map

            # Restart idle loop with new file
            if self._idle_loop and self._idle_loop.isRunning():
                self._restart_idle_loop()
            return None
        except Exception as e:
            return str(e)

    def set_idle_loop_enabled(self, enabled: bool):
        self._idle_loop_enabled = enabled
        if enabled:
            self._resume_idle_loop()
        else:
            self._stop_idle_loop()
            self.router.silence()

    def set_count_in(self, bars: int, click_channel: int = 9, click_note: int = 76):
        self._count_in_bars = bars
        self._click_channel = click_channel
        self._click_note = click_note

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    def start_engine(self):
        """Start or reconfigure the engine. Safe to call multiple times."""
        self._stop_player()
        self._stop_idle_loop()
        if not self.clock.isRunning():
            self.clock.start()
        self._start_idle_loop()

    def stop_engine(self):
        """Shutdown everything cleanly."""
        self._stop_player()
        self._stop_idle_loop()
        self.clock.stop_thread()
        self.clock.wait(1000)
        self.input_handler.close()
        self.router.close_ports()

    def play(self):
        """Start playing the loaded song."""
        if not self._song_events:
            return
        if self._status == self.STATUS_PAUSED and self._player:
            self._player.resume_playback()
            self._set_status(self.STATUS_PLAYING)
            return

        self._stop_player()
        self._pause_idle_loop()
        self.router.silence()

        self._player = PlayerThread(
            events=self._song_events,
            bar_start_times=self._song_bar_times,
            total_bars=self._song_total_bars,
            duration=self._song_duration,
            tpb=self._song_tpb,
            tempo_map=self._song_tempo_map,
            router=self.router,
            count_in_bars=self._count_in_bars,
            click_channel=self._click_channel,
            click_note=self._click_note,
        )
        self._player.bar_changed.connect(self.bar_changed)
        self._player.tempo_changed.connect(self._on_tempo_changed)
        self._player.finished.connect(self._on_song_finished)
        self._player.start()
        self._set_status(self.STATUS_PLAYING)

    def stop(self):
        """Stop song playback, silence notes, and return to idle loop."""
        self._stop_player()
        self.router.silence()
        self._resume_idle_loop()
        self._set_status(self.STATUS_IDLE)

    def pause(self):
        if self._status == self.STATUS_PLAYING and self._player:
            self._player.pause_playback()
            self._set_status(self.STATUS_PAUSED)

    def resume(self):
        if self._status == self.STATUS_PAUSED and self._player:
            self._player.resume_playback()
            self._set_status(self.STATUS_PLAYING)

    def restart(self):
        """Restart the current song from the beginning."""
        self._stop_player()
        self.router.silence()
        self.play()

    def panic(self):
        """Immediately silence all notes and stop all playback."""
        self._stop_player()       # thread exits → sends silence + MIDI Stop internally
        self._stop_idle_loop()
        self.router.panic()       # belt-and-suspenders: silence + MIDI Stop again
        self._set_status(self.STATUS_STOPPED)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_status(self, status: str):
        self._status = status
        self.status_changed.emit(status)

    def _on_tempo_changed(self, tempo_us: int):
        self.clock.tempo_us = tempo_us
        if self._song_has_tempo:
            self.tempo_changed.emit(60_000_000 / tempo_us)
        else:
            self.tempo_changed.emit(-1.0)  # sentinel: no embedded tempo

    def _on_song_finished(self):
        # If a new player was already started (e.g. user pressed play again),
        # don't touch the idle loop or status — the new player owns those now.
        if self._player is not None:
            return
        self._resume_idle_loop()
        self._set_status(self.STATUS_IDLE)
        self.song_finished.emit()

    def _stop_player(self):
        if self._player:
            player = self._player
            self._player = None   # clear first so _on_song_finished sees None
            player.stop_playback()
            player.wait(500)

    def _start_idle_loop(self):
        if not self._loop_events:
            self.clock.start_clock()
            return
        self._idle_loop = IdleLoopThread(
            events=self._loop_events,
            duration=self._loop_duration,
            tempo_map=self._loop_tempo_map,
            router=self.router,
        )
        self._idle_loop.tempo_changed.connect(self._on_tempo_changed)
        self._idle_loop.start()
        self.clock.start_clock()

    def _stop_idle_loop(self):
        if self._idle_loop:
            self._idle_loop.stop_thread()
            self._idle_loop.wait(2000)
            self._idle_loop = None

    def _restart_idle_loop(self):
        self._stop_idle_loop()
        self._start_idle_loop()

    def _pause_idle_loop(self):
        if self._idle_loop:
            self._idle_loop.pause_and_save()

    def _resume_idle_loop(self):
        if not self._idle_loop_enabled:
            return
        if self._idle_loop:
            self._idle_loop.resume()
        elif self._loop_events:
            self._start_idle_loop()
