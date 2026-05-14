"""Entry point for MIDI Performer."""

import sys
import os

# Ensure the project root is on sys.path regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from engine.playback_engine import PlaybackEngine
from models.settings import AppSettings
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MIDI Performer")

    settings = AppSettings.load()
    engine = PlaybackEngine()
    engine.set_count_in(
        settings.count_in_bars,
        settings.click_channel,
        settings.click_note,
    )

    window = MainWindow(engine, settings)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
