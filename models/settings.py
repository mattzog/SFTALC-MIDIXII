"""Application settings — keybindings, count-in, click config. Saved as JSON."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".midi_performer_settings.json")

DEFAULT_KEYS: Dict[str, str] = {
    "play":         "Space",
    "stop":         "S",
    "pause":        "P",
    "restart":      "R",
    "next_song":    "Down",
    "prev_song":    "Up",
    "panic":        "Escape",
}


@dataclass
class AppSettings:
    keybindings: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYS))
    count_in_bars: int = 0          # 0 = disabled
    click_channel: int = 9          # 0-indexed, channel 10 in musician terms
    click_note: int = 76            # Hi Wood Block

    def save(self, filepath: str = SETTINGS_PATH):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, filepath: str = SETTINGS_PATH) -> "AppSettings":
        if not os.path.exists(filepath):
            return cls()
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            s = cls()
            s.keybindings = {**DEFAULT_KEYS, **data.get("keybindings", {})}
            s.count_in_bars = data.get("count_in_bars", 0)
            s.click_channel = data.get("click_channel", 9)
            s.click_note = data.get("click_note", 76)
            return s
        except Exception:
            return cls()

    def key_for_action(self, action: str) -> str:
        return self.keybindings.get(action, DEFAULT_KEYS.get(action, ""))
