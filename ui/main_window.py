"""Main performance window."""

import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QFont, QColor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton,
    QProgressBar, QFileDialog, QMessageBox, QSizePolicy,
    QFrame,
)

from engine.playback_engine import PlaybackEngine
from models.performance_set import PerformanceSet, Song
from models.settings import AppSettings
from ui.settings_dialog import SettingsDialog


STATUS_COLORS = {
    'playing': '#00cc44',
    'paused':  '#ffaa00',
    'idle':    '#4488ff',
    'stopped': '#888888',
}

STATUS_LABELS = {
    'playing': 'PLAYING',
    'paused':  'PAUSED',
    'idle':    'IDLE LOOP',
    'stopped': 'STOPPED',
}


class MainWindow(QMainWindow):
    def __init__(self, engine: PlaybackEngine, settings: AppSettings):
        super().__init__()
        self._engine = engine
        self._settings = settings
        self._perf_set: Optional[PerformanceSet] = None
        self._selected_idx: int = -1
        self._total_bars: int = 0
        self._set_filepath: Optional[str] = None

        self.setWindowTitle("MIDI Performer")
        self.setMinimumSize(600, 500)
        self._build_ui()
        self._connect_engine()
        self._apply_keybindings()
        self._apply_dark_theme()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # Title bar row
        title_row = QHBoxLayout()
        self._set_name_label = QLabel("No Set Loaded")
        self._set_name_label.setFont(QFont("Sans", 11, QFont.Weight.Bold))
        title_row.addWidget(self._set_name_label)
        title_row.addStretch()
        self._btn_idle_loop = QPushButton("Idle Loop: ON")
        self._btn_idle_loop.setFixedHeight(28)
        self._btn_idle_loop.setCheckable(True)
        self._btn_idle_loop.setChecked(True)
        self._update_idle_loop_button(True)
        title_row.addWidget(self._btn_idle_loop)
        btn_open = QPushButton("Open Set")
        btn_new = QPushButton("New Set")
        self._btn_edit_set = QPushButton("Edit Set")
        self._btn_edit_set.setEnabled(False)
        btn_save = QPushButton("Save Set")
        btn_settings = QPushButton("Settings")
        for b in (btn_open, btn_new, self._btn_edit_set, btn_save, btn_settings):
            b.setFixedHeight(28)
            title_row.addWidget(b)
        root.addLayout(title_row)

        # Status display
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 8, 12, 8)
        status_layout.setSpacing(4)

        self._status_label = QLabel("STOPPED")
        self._status_label.setFont(QFont("Monospace", 14, QFont.Weight.Bold))
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._song_label = QLabel("—")
        self._song_label.setFont(QFont("Sans", 12))
        self._song_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bars_label = QLabel("—")
        self._bars_label.setFont(QFont("Monospace", 48, QFont.Weight.Bold))
        self._bars_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._bars_sublabel = QLabel("bars remaining")
        self._bars_sublabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bars_sublabel.setFont(QFont("Sans", 9))

        self._tempo_label = QLabel("— BPM")
        self._tempo_label.setFont(QFont("Monospace", 18, QFont.Weight.Bold))
        self._tempo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)

        for w in (self._status_label, self._song_label, self._bars_label,
                  self._bars_sublabel, self._tempo_label, self._progress):
            status_layout.addWidget(w)

        root.addWidget(status_frame)

        # Playlist
        playlist_label = QLabel("PLAYLIST")
        playlist_label.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        root.addWidget(playlist_label)

        self._playlist = QListWidget()
        self._playlist.setFont(QFont("Monospace", 11))
        self._playlist.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._playlist.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._playlist)

        # Transport buttons
        btn_row = QHBoxLayout()
        self._btn_play = QPushButton("PLAY")
        self._btn_stop = QPushButton("STOP")
        self._btn_pause = QPushButton("PAUSE")
        self._btn_restart = QPushButton("RESTART")
        self._btn_panic = QPushButton("PANIC")
        self._btn_panic.setStyleSheet("QPushButton { color: #ff4444; font-weight: bold; }")

        for b in (self._btn_play, self._btn_stop, self._btn_pause,
                  self._btn_restart, self._btn_panic):
            b.setFixedHeight(40)
            b.setFont(QFont("Sans", 10, QFont.Weight.Bold))
            btn_row.addWidget(b)
        root.addLayout(btn_row)

        # Connections
        self._btn_idle_loop.toggled.connect(self._on_idle_loop_toggled)
        btn_open.clicked.connect(self._on_open_set)
        btn_new.clicked.connect(self._on_new_set)
        self._btn_edit_set.clicked.connect(self._on_edit_set)
        btn_save.clicked.connect(self._on_save_set)
        btn_settings.clicked.connect(self._on_settings)
        self._btn_play.clicked.connect(self._action_play)
        self._btn_stop.clicked.connect(self._action_stop)
        self._btn_pause.clicked.connect(self._action_pause)
        self._btn_restart.clicked.connect(self._action_restart)
        self._btn_panic.clicked.connect(self._action_panic)
        self._playlist.currentRowChanged.connect(self._on_playlist_select)

    def _connect_engine(self):
        self._engine.status_changed.connect(self._on_status_changed)
        self._engine.bar_changed.connect(self._on_bar_changed)
        self._engine.tempo_changed.connect(self._on_tempo_changed)
        self._engine.song_finished.connect(self._on_song_finished)

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1a1a1a; color: #e0e0e0; }
            QListWidget { background-color: #222222; border: 1px solid #444; }
            QListWidget::item:selected { background-color: #2255aa; }
            QListWidget::item:hover { background-color: #333; }
            QPushButton { background-color: #333; border: 1px solid #555; padding: 4px 10px; border-radius: 3px; }
            QPushButton:hover { background-color: #444; }
            QPushButton:pressed { background-color: #222; }
            QFrame { border: 1px solid #444; border-radius: 4px; }
            QProgressBar { background-color: #333; border: none; border-radius: 3px; }
            QProgressBar::chunk { background-color: #2255aa; border-radius: 3px; }
            QLabel { border: none; }
        """)

    # ------------------------------------------------------------------
    # Keybindings
    # ------------------------------------------------------------------

    def _apply_keybindings(self):
        # Remove old shortcuts
        for shortcut in self.findChildren(QShortcut):
            shortcut.setEnabled(False)
            shortcut.deleteLater()

        bindings = {
            "play":      self._action_play,
            "stop":      self._action_stop,
            "pause":     self._action_pause,
            "restart":   self._action_restart,
            "next_song": self._action_next_song,
            "prev_song": self._action_prev_song,
            "panic":     self._action_panic,
        }
        for action, slot in bindings.items():
            key = self._settings.key_for_action(action)
            if key:
                sc = QShortcut(QKeySequence(key), self)
                sc.activated.connect(slot)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_idle_loop_toggled(self, enabled: bool):
        self._engine.set_idle_loop_enabled(enabled)
        self._update_idle_loop_button(enabled)

    def _update_idle_loop_button(self, enabled: bool):
        if enabled:
            self._btn_idle_loop.setText("Idle Loop: ON")
            self._btn_idle_loop.setStyleSheet(
                "QPushButton { color: #00cc44; font-weight: bold; }"
            )
        else:
            self._btn_idle_loop.setText("Idle Loop: OFF")
            self._btn_idle_loop.setStyleSheet(
                "QPushButton { color: #888888; }"
            )

    def _action_play(self):
        if self._selected_idx < 0:
            return
        self._engine.play()

    def _action_stop(self):
        self._engine.stop()

    def _action_pause(self):
        if self._engine._status == PlaybackEngine.STATUS_PLAYING:
            self._engine.pause()
        elif self._engine._status == PlaybackEngine.STATUS_PAUSED:
            self._engine.resume()

    def _action_restart(self):
        if self._selected_idx >= 0:
            self._engine.restart()

    def _action_panic(self):
        self._engine.panic()

    def _action_next_song(self):
        if self._perf_set and self._selected_idx < len(self._perf_set.songs) - 1:
            self._playlist.setCurrentRow(self._selected_idx + 1)

    def _action_prev_song(self):
        if self._selected_idx > 0:
            self._playlist.setCurrentRow(self._selected_idx - 1)

    # ------------------------------------------------------------------
    # Engine callbacks
    # ------------------------------------------------------------------

    def _on_status_changed(self, status: str):
        label = STATUS_LABELS.get(status, status.upper())
        color = STATUS_COLORS.get(status, '#888888')
        self._status_label.setText(label)
        self._status_label.setStyleSheet(f"color: {color}; border: none;")

    def _on_bar_changed(self, bars_remaining: int, total_bars: int):
        self._total_bars = total_bars
        self._bars_label.setText(str(bars_remaining))
        if total_bars > 0:
            pct = int(100 * (total_bars - bars_remaining) / total_bars)
            self._progress.setValue(pct)

    def _on_tempo_changed(self, bpm: float):
        if bpm > 0:
            self._tempo_label.setText(f"{bpm:.1f} BPM")
        else:
            self._tempo_label.setText("— BPM")

    def _on_song_finished(self):
        self._bars_label.setText("—")
        self._progress.setValue(0)

    # ------------------------------------------------------------------
    # Playlist
    # ------------------------------------------------------------------

    def _on_playlist_select(self, row: int):
        if not self._perf_set or row < 0 or row >= len(self._perf_set.songs):
            return
        self._selected_idx = row
        song = self._perf_set.songs[row]
        self._song_label.setText(song.name)
        self._bars_label.setText("—")
        self._progress.setValue(0)

        path = self._perf_set.song_path(row)
        err = self._engine.load_song(path)
        if err:
            QMessageBox.warning(self, "Load Error", f"Could not load '{song.name}':\n{err}")

    def _rebuild_playlist(self):
        self._playlist.clear()
        if not self._perf_set:
            return
        for i, song in enumerate(self._perf_set.songs):
            item = QListWidgetItem(f"  {i+1:02d}.  {song.name}")
            self._playlist.addItem(item)
        self._selected_idx = -1
        self._song_label.setText("—")
        self._bars_label.setText("—")
        self._progress.setValue(0)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _on_open_set(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Performance Set", "", "Performance Set (*.perfset);;All Files (*)"
        )
        if not path:
            return
        try:
            self._perf_set = PerformanceSet.load(path)
            self._set_filepath = path
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load set:\n{e}")
            return
        self._apply_set()

    def _on_new_set(self):
        self._perf_set = PerformanceSet.new()
        self._set_filepath = None
        self._apply_set()
        self._on_edit_set()

    def _on_save_set(self):
        if not self._perf_set:
            return
        if self._set_filepath:
            self._perf_set.save(self._set_filepath)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Performance Set", "", "Performance Set (*.perfset)"
            )
            if path:
                if not path.endswith(".perfset"):
                    path += ".perfset"
                self._perf_set.save(path)
                self._set_filepath = path

    def _apply_set(self):
        if not self._perf_set:
            return
        self._set_name_label.setText(self._perf_set.name)
        self.setWindowTitle(f"MIDI Performer — {self._perf_set.name}")
        self._btn_edit_set.setEnabled(True)
        self._rebuild_playlist()

        # Apply routing to engine
        routing = {int(k): v for k, v in self._perf_set.channel_routing.items()}
        self._engine.router.channel_map = routing

        # Open output ports
        errors = self._engine.router.open_ports(self._perf_set.output_port_names)
        for e in errors:
            QMessageBox.warning(self, "MIDI Port Warning", e)

        # Open input port
        if self._perf_set.input_port_name:
            err = self._engine.input_handler.open_port(self._perf_set.input_port_name)
            if err:
                QMessageBox.warning(self, "MIDI Input Warning", err)

        # Load idle loop
        if self._perf_set.idle_loop_file:
            loop_path = self._perf_set.resolve_path(self._perf_set.idle_loop_file)
            err = self._engine.load_idle_loop(loop_path)
            if err:
                QMessageBox.warning(self, "Idle Loop Warning", f"Could not load idle loop:\n{err}")

        self._engine.start_engine()

    def _on_edit_set(self):
        from ui.set_editor_dialog import SetEditorDialog
        if not self._perf_set:
            return

        # Snapshot infrastructure so we know what actually changed
        old_ports = list(self._perf_set.output_port_names)
        old_input = self._perf_set.input_port_name
        old_loop = self._perf_set.idle_loop_file
        current_song_file = (
            self._perf_set.songs[self._selected_idx].file
            if 0 <= self._selected_idx < len(self._perf_set.songs)
            else ""
        )

        dlg = SetEditorDialog(self._perf_set, parent=self)
        if not dlg.exec():
            return

        # Update UI labels
        self._set_name_label.setText(self._perf_set.name)
        self.setWindowTitle(f"MIDI Performer — {self._perf_set.name}")

        # Rebuild playlist, then silently restore the previous selection
        self._rebuild_playlist()
        if current_song_file:
            for i, song in enumerate(self._perf_set.songs):
                if song.file == current_song_file:
                    self._playlist.blockSignals(True)
                    self._playlist.setCurrentRow(i)
                    self._playlist.blockSignals(False)
                    self._selected_idx = i
                    self._song_label.setText(song.name)
                    break
            # If the current song was removed, keep the engine playing it
            # until it finishes; UI just shows no selection

        # Routing: always safe to update in-place
        self._engine.router.channel_map = {
            int(k): v for k, v in self._perf_set.channel_routing.items()
        }

        # Output ports: silence first so notes aren't stuck on hardware,
        # then close old ports and open new ones
        if self._perf_set.output_port_names != old_ports:
            self._engine.router.silence()
            errors = self._engine.router.open_ports(self._perf_set.output_port_names)
            for e in errors:
                QMessageBox.warning(self, "MIDI Port Warning", e)

        # Input port
        if self._perf_set.input_port_name != old_input:
            if self._perf_set.input_port_name:
                err = self._engine.input_handler.open_port(self._perf_set.input_port_name)
                if err:
                    QMessageBox.warning(self, "MIDI Input Warning", err)

        # Idle loop: engine.load_idle_loop() already hot-restarts the loop thread
        if self._perf_set.idle_loop_file != old_loop:
            if self._perf_set.idle_loop_file:
                loop_path = self._perf_set.resolve_path(self._perf_set.idle_loop_file)
                err = self._engine.load_idle_loop(loop_path)
                if err:
                    QMessageBox.warning(self, "Idle Loop Warning",
                                        f"Could not load idle loop:\n{err}")
            else:
                self._engine._stop_idle_loop()

        if self._set_filepath:
            self._perf_set.save(self._set_filepath)

    def _on_settings(self):
        dlg = SettingsDialog(self._settings, parent=self)
        if dlg.exec():
            self._settings.save()
            self._engine.set_count_in(
                self._settings.count_in_bars,
                self._settings.click_channel,
                self._settings.click_note,
            )
            self._apply_keybindings()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._engine.stop_engine()
        super().closeEvent(event)
