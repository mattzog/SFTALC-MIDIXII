"""Settings dialog — keybindings and count-in configuration."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton,
    QGroupBox, QDialogButtonBox, QKeySequenceEdit,
)

from models.settings import AppSettings, DEFAULT_KEYS

ACTION_LABELS = {
    "play":      "Play",
    "stop":      "Stop",
    "pause":     "Pause / Resume",
    "restart":   "Restart Song",
    "next_song": "Next Song",
    "prev_song": "Previous Song",
    "panic":     "MIDI Panic",
}


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Keybindings group
        kb_group = QGroupBox("Keyboard Shortcuts")
        kb_layout = QFormLayout(kb_group)
        self._key_edits = {}
        for action, label in ACTION_LABELS.items():
            editor = QKeySequenceEdit()
            editor.setMaximumSequenceLength(1)
            self._key_edits[action] = editor
            kb_layout.addRow(label + ":", editor)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_keys)
        kb_layout.addRow("", reset_btn)
        layout.addWidget(kb_group)

        # Count-in group
        ci_group = QGroupBox("Count-in")
        ci_layout = QFormLayout(ci_group)

        self._count_in_spin = QSpinBox()
        self._count_in_spin.setRange(0, 8)
        self._count_in_spin.setSpecialValueText("Off")
        ci_layout.addRow("Count-in bars:", self._count_in_spin)

        self._click_channel_spin = QSpinBox()
        self._click_channel_spin.setRange(1, 16)
        ci_layout.addRow("Click MIDI channel:", self._click_channel_spin)

        self._click_note_spin = QSpinBox()
        self._click_note_spin.setRange(0, 127)
        ci_layout.addRow("Click MIDI note:", self._click_note_spin)

        layout.addWidget(ci_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self):
        for action, editor in self._key_edits.items():
            key = self._settings.keybindings.get(action, "")
            editor.setKeySequence(QKeySequence(key))
        self._count_in_spin.setValue(self._settings.count_in_bars)
        self._click_channel_spin.setValue(self._settings.click_channel + 1)  # display 1-16
        self._click_note_spin.setValue(self._settings.click_note)

    def _reset_keys(self):
        for action, editor in self._key_edits.items():
            editor.setKeySequence(QKeySequence(DEFAULT_KEYS.get(action, "")))

    def _save_and_accept(self):
        for action, editor in self._key_edits.items():
            seq = editor.keySequence()
            self._settings.keybindings[action] = seq.toString() if not seq.isEmpty() else ""
        self._settings.count_in_bars = self._count_in_spin.value()
        self._settings.click_channel = self._click_channel_spin.value() - 1
        self._settings.click_note = self._click_note_spin.value()
        self.accept()
