"""Performance set data model — songs, routing, idle loop, saved as JSON sidecar."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional


@dataclass
class Song:
    name: str
    file: str  # path relative to the set file, or absolute


@dataclass
class PerformanceSet:
    name: str = "Untitled Set"
    songs: List[Song] = field(default_factory=list)
    idle_loop_file: str = ""

    # channel (str key "0"-"15") → port index (0-2)
    channel_routing: Dict[str, int] = field(
        default_factory=lambda: {str(ch): 0 for ch in range(16)}
    )

    # Port names by slot index (list of up to 3 strings)
    output_port_names: List[str] = field(default_factory=lambda: ["", "", ""])
    input_port_name: str = ""

    _filepath: str = field(default="", repr=False, compare=False)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, filepath: str):
        data = {
            "name": self.name,
            "songs": [asdict(s) for s in self.songs],
            "idle_loop_file": self.idle_loop_file,
            "channel_routing": self.channel_routing,
            "output_port_names": self.output_port_names,
            "input_port_name": self.input_port_name,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self._filepath = filepath

    @classmethod
    def load(cls, filepath: str) -> "PerformanceSet":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        ps = cls(
            name=data.get("name", "Untitled Set"),
            songs=[Song(**s) for s in data.get("songs", [])],
            idle_loop_file=data.get("idle_loop_file", ""),
            channel_routing=data.get("channel_routing", {str(ch): 0 for ch in range(16)}),
            output_port_names=data.get("output_port_names", ["", "", ""]),
            input_port_name=data.get("input_port_name", ""),
        )
        ps._filepath = filepath
        return ps

    @classmethod
    def new(cls) -> "PerformanceSet":
        return cls()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def resolve_path(self, relative: str) -> str:
        """Resolve a song path relative to the set file's directory."""
        if os.path.isabs(relative) or not self._filepath:
            return relative
        base = os.path.dirname(self._filepath)
        return os.path.normpath(os.path.join(base, relative))

    def song_path(self, index: int) -> str:
        if 0 <= index < len(self.songs):
            return self.resolve_path(self.songs[index].file)
        return ""

    def add_song(self, name: str, filepath: str):
        if self._filepath:
            base = os.path.dirname(self._filepath)
            try:
                rel = os.path.relpath(filepath, base)
                filepath = rel
            except ValueError:
                pass  # Windows cross-drive — keep absolute
        self.songs.append(Song(name=name, file=filepath))

    def remove_song(self, index: int):
        if 0 <= index < len(self.songs):
            self.songs.pop(index)

    def move_song(self, from_idx: int, to_idx: int):
        if 0 <= from_idx < len(self.songs) and 0 <= to_idx < len(self.songs):
            song = self.songs.pop(from_idx)
            self.songs.insert(to_idx, song)
