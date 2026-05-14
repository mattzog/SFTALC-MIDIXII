"""MIDI input handler — listens on one port and passes all messages to the router."""

import rtmidi
from typing import Optional


class MidiInputHandler:
    def __init__(self, router):
        self._router = router
        self._midi_in: Optional[rtmidi.MidiIn] = None
        self._port_name = ""

    def available_ports(self):
        probe = rtmidi.MidiIn()
        names = probe.get_ports()
        del probe
        return names

    def open_port(self, port_name: str) -> Optional[str]:
        """Open input port by name. Returns error string or None on success."""
        self.close()
        available = self.available_ports()
        try:
            idx = available.index(port_name)
        except ValueError:
            return f"Input port not found: '{port_name}'"

        try:
            self._midi_in = rtmidi.MidiIn()
            self._midi_in.ignore_types(sysex=True, timing=True, active_sense=True)
            self._midi_in.open_port(idx)
            self._midi_in.set_callback(self._callback)
            self._port_name = port_name
            return None
        except rtmidi.RtMidiError as e:
            return str(e)

    def close(self):
        if self._midi_in:
            self._midi_in.cancel_callback()
            self._midi_in.close_port()
            self._midi_in = None
        self._port_name = ""

    def is_open(self) -> bool:
        return self._midi_in is not None

    def current_port(self) -> str:
        return self._port_name

    def _callback(self, event, data=None):
        """Called from rtmidi background thread on every incoming message."""
        raw_bytes, _delta_time = event
        if not raw_bytes:
            return
        # Pass through to all output ports
        for slot in range(self._router.MAX_PORTS):
            self._router.send_raw(slot, list(raw_bytes))
