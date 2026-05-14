"""MIDI output routing: channel → port mapping, clock/panic broadcast."""

import threading
import rtmidi
from collections import defaultdict
from typing import Dict, List, Optional, Set


class MidiRouter:
    MAX_PORTS = 3

    def __init__(self):
        self._ports: List[Optional[rtmidi.MidiOut]] = [None] * self.MAX_PORTS
        # channel (0-15) → port index (0-2); default all to port 0
        self.channel_map: Dict[int, int] = {ch: 0 for ch in range(16)}
        # active_notes[port_slot][channel] = set of sounding note numbers
        self._active_notes: Dict[int, Dict[int, Set[int]]] = defaultdict(lambda: defaultdict(set))
        self._notes_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def available_output_ports(self) -> List[str]:
        probe = rtmidi.MidiOut()
        names = probe.get_ports()
        del probe
        return names

    def open_ports(self, port_names: List[str]) -> List[str]:
        """Open up to MAX_PORTS output ports by name. Returns list of errors."""
        self.close_ports()
        errors = []
        available = self.available_output_ports()
        for slot, name in enumerate(port_names[:self.MAX_PORTS]):
            if not name:
                continue
            try:
                idx = available.index(name)
                port = rtmidi.MidiOut()
                port.open_port(idx)
                self._ports[slot] = port
            except (ValueError, rtmidi.RtMidiError) as e:
                errors.append(f"Port {slot+1} '{name}': {e}")
        return errors

    def close_ports(self):
        for i, port in enumerate(self._ports):
            if port:
                port.close_port()
                self._ports[i] = None
        with self._notes_lock:
            self._active_notes.clear()

    def is_open(self, slot: int = 0) -> bool:
        return self._ports[slot] is not None

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self, msg) -> None:
        """Route a mido Message to the correct output port by channel."""
        channel = getattr(msg, 'channel', None)
        if channel is None:
            return
        slot = self.channel_map.get(channel, 0)
        port = self._ports[slot]
        if port:
            try:
                port.send_message(msg.bytes())
                self._track_note(slot, msg)
            except rtmidi.RtMidiError:
                pass

    def _track_note(self, slot: int, msg) -> None:
        """Update the active-note table based on note-on / note-off messages."""
        t = msg.type
        if t == 'note_on' and msg.velocity > 0:
            with self._notes_lock:
                self._active_notes[slot][msg.channel].add(msg.note)
        elif t == 'note_off' or (t == 'note_on' and msg.velocity == 0):
            with self._notes_lock:
                self._active_notes[slot][msg.channel].discard(msg.note)

    def send_raw(self, slot: int, raw: List[int]) -> None:
        port = self._ports[slot]
        if port:
            try:
                port.send_message(raw)
            except rtmidi.RtMidiError:
                pass

    def send_realtime(self, status: int) -> None:
        """Broadcast a single-byte real-time message (clock, start, stop, continue) to all ports."""
        for port in self._ports:
            if port:
                try:
                    port.send_message([status])
                except rtmidi.RtMidiError:
                    pass

    def send_to_all(self, msg) -> None:
        """Send a mido Message to every open port (ignores channel map)."""
        raw = msg.bytes()
        for port in self._ports:
            if port:
                try:
                    port.send_message(raw)
                except rtmidi.RtMidiError:
                    pass

    # ------------------------------------------------------------------
    # Silence / panic
    # ------------------------------------------------------------------

    def silence(self) -> None:
        """Send note-off for every tracked sounding note, then clear the table."""
        with self._notes_lock:
            for slot, channels in self._active_notes.items():
                port = self._ports[slot]
                if not port:
                    continue
                for ch, notes in channels.items():
                    for note in notes:
                        try:
                            port.send_message([0x80 | ch, note, 0])
                        except rtmidi.RtMidiError:
                            pass
            self._active_notes.clear()

    def panic(self) -> None:
        """Silence all tracked notes and send MIDI Stop."""
        self.silence()
        self.send_realtime(0xFC)  # MIDI Stop
