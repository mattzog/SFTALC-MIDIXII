"""Performance set editor — songs, routing, idle loop, MIDI ports."""

import os

import rtmidi
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QDialogButtonBox, QComboBox, QFileDialog,
    QTabWidget, QWidget, QSpinBox, QMessageBox,
)

from models.performance_set import PerformanceSet


def _available_output_ports():
    probe = rtmidi.MidiOut()
    ports = probe.get_ports()
    del probe
    return ["(none)"] + ports


def _available_input_ports():
    probe = rtmidi.MidiIn()
    ports = probe.get_ports()
    del probe
    return ["(none)"] + ports


class SetEditorDialog(QDialog):
    def __init__(self, perf_set: PerformanceSet, parent=None):
        super().__init__(parent)
        self._set = perf_set
        self.setWindowTitle("Edit Performance Set")
        self.setMinimumSize(560, 500)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # ---- Songs tab ----
        songs_tab = QWidget()
        sl = QVBoxLayout(songs_tab)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Set name:"))
        self._name_edit = QLineEdit()
        name_row.addWidget(self._name_edit)
        sl.addLayout(name_row)

        self._song_list = QListWidget()
        self._song_list.setFont(QFont("Monospace", 10))
        sl.addWidget(self._song_list)

        song_btns = QHBoxLayout()
        btn_add = QPushButton("Add Song…")
        btn_remove = QPushButton("Remove")
        btn_up = QPushButton("▲ Up")
        btn_down = QPushButton("▼ Down")
        for b in (btn_add, btn_remove, btn_up, btn_down):
            song_btns.addWidget(b)
        sl.addLayout(song_btns)

        btn_add.clicked.connect(self._add_song)
        btn_remove.clicked.connect(self._remove_song)
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)

        tabs.addTab(songs_tab, "Songs")

        # ---- Idle Loop tab ----
        loop_tab = QWidget()
        ll = QFormLayout(loop_tab)
        loop_row = QHBoxLayout()
        self._loop_edit = QLineEdit()
        self._loop_edit.setPlaceholderText("(none)")
        loop_btn = QPushButton("Browse…")
        loop_btn.clicked.connect(self._browse_loop)
        loop_row.addWidget(self._loop_edit)
        loop_row.addWidget(loop_btn)
        ll.addRow("Idle loop file:", loop_row)
        tabs.addTab(loop_tab, "Idle Loop")

        # ---- MIDI Ports tab ----
        ports_tab = QWidget()
        pl = QFormLayout(ports_tab)

        out_ports = _available_output_ports()
        self._out_combos = []
        for i in range(3):
            cb = QComboBox()
            cb.addItems(out_ports)
            self._out_combos.append(cb)
            pl.addRow(f"Output {i+1}:", cb)

        in_ports = _available_input_ports()
        self._in_combo = QComboBox()
        self._in_combo.addItems(in_ports)
        pl.addRow("MIDI Input (controller):", self._in_combo)

        tabs.addTab(ports_tab, "MIDI Ports")

        # ---- Routing tab ----
        route_tab = QWidget()
        rl = QVBoxLayout(route_tab)
        rl.addWidget(QLabel("Assign each MIDI channel to an output port:"))
        self._route_combos = {}
        form = QFormLayout()
        for ch in range(16):
            cb = QComboBox()
            cb.addItems(["Output 1", "Output 2", "Output 3"])
            self._route_combos[ch] = cb
            form.addRow(f"Channel {ch+1}:", cb)
        rl.addLayout(form)
        tabs.addTab(route_tab, "Routing")

        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self):
        self._name_edit.setText(self._set.name)
        self._refresh_song_list()

        self._loop_edit.setText(self._set.idle_loop_file)

        out_ports = _available_output_ports()
        for i, cb in enumerate(self._out_combos):
            name = self._set.output_port_names[i] if i < len(self._set.output_port_names) else ""
            idx = out_ports.index(name) if name in out_ports else 0
            cb.setCurrentIndex(idx)

        in_ports = _available_input_ports()
        in_name = self._set.input_port_name
        in_idx = in_ports.index(in_name) if in_name in in_ports else 0
        self._in_combo.setCurrentIndex(in_idx)

        for ch, cb in self._route_combos.items():
            port_idx = self._set.channel_routing.get(str(ch), 0)
            cb.setCurrentIndex(min(port_idx, 2))

    def _refresh_song_list(self):
        self._song_list.clear()
        for i, song in enumerate(self._set.songs):
            self._song_list.addItem(f"{i+1:02d}. {song.name}  [{song.file}]")

    def _add_song(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add MIDI Files", "", "MIDI Files (*.mid *.midi *.MID *.MIDI);;All Files (*)"
        )
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            self._set.add_song(name, path)
        self._refresh_song_list()

    def _remove_song(self):
        row = self._song_list.currentRow()
        if row >= 0:
            self._set.remove_song(row)
            self._refresh_song_list()

    def _move_up(self):
        row = self._song_list.currentRow()
        if row > 0:
            self._set.move_song(row, row - 1)
            self._refresh_song_list()
            self._song_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._song_list.currentRow()
        if 0 <= row < len(self._set.songs) - 1:
            self._set.move_song(row, row + 1)
            self._refresh_song_list()
            self._song_list.setCurrentRow(row + 1)

    def _browse_loop(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Idle Loop", "", "MIDI Files (*.mid *.midi *.MID *.MIDI);;All Files (*)"
        )
        if path:
            self._loop_edit.setText(path)

    def _save_and_accept(self):
        self._set.name = self._name_edit.text().strip() or "Untitled Set"
        self._set.idle_loop_file = self._loop_edit.text().strip()

        out_ports = _available_output_ports()
        self._set.output_port_names = []
        for cb in self._out_combos:
            name = cb.currentText()
            self._set.output_port_names.append("" if name == "(none)" else name)

        in_name = self._in_combo.currentText()
        self._set.input_port_name = "" if in_name == "(none)" else in_name

        for ch, cb in self._route_combos.items():
            self._set.channel_routing[str(ch)] = cb.currentIndex()

        self.accept()
