#!/usr/bin/env python3
"""
MCP server for live debugging Pure Data patches in the Station Audio Toolkit.

Communicates with debug-bridge.pd via UDP FUDI protocol:
  - Sends commands on port 9000
  - Receives monitoring reports on port 9001
"""

import asyncio
import socket
import threading
import time

from mcp.server.fastmcp import FastMCP

PD_HOST = "127.0.0.1"
SEND_PORT = 9000
RECV_PORT = 9001


def send_fudi(message: str):
    """Send a FUDI message to Pd via UDP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(f"{message};\n".encode(), (PD_HOST, SEND_PORT))
    sock.close()


class StatusBuffer:
    """Background listener that buffers monitoring reports from Pd."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", RECV_PORT))
        sock.settimeout(1.0)
        while self._running:
            try:
                data, _ = sock.recvfrom(4096)
                text = data.decode().strip().rstrip(";").strip()
                parts = text.split(None, 1)
                if len(parts) == 2:
                    with self.lock:
                        self.data[parts[0]] = parts[1]
            except socket.timeout:
                continue
            except OSError:
                break

    def get_all(self) -> dict[str, str]:
        with self.lock:
            return dict(self.data)

    def clear(self):
        with self.lock:
            self.data.clear()


status = StatusBuffer()
# Tell Pd to (re)connect netsend to our listener port
send_fudi("trig tk-reconnect")
mcp = FastMCP("pd-debug")


@mcp.tool()
def pd_send(name: str, value: str) -> str:
    """Send a value to any named Pd receiver bus.

    Examples:
      pd_send("tk-note", "60")           -> send note 60
      pd_send("tk-master-level", "-6")    -> set master to -6 dB
      pd_send("tk-source1-on", "1")       -> enable source 1
      pd_send("tk-source1-level", "-12")  -> set source 1 level
      pd_send("tk-chorus-return", "50")   -> set chorus return to 50%
    """
    send_fudi(f"set {name} {value}")
    return f"Sent {value} to {name}"


@mcp.tool()
def pd_bang(name: str) -> str:
    """Send a bang to any named Pd receiver bus.

    Examples:
      pd_bang("tk-play")   -> trigger play
      pd_bang("tk-stop")   -> trigger stop
      pd_bang("tk-panic")  -> all notes off + DSP off
    """
    send_fudi(f"trig {name}")
    return f"Banged {name}"


@mcp.tool()
def pd_note(note: int, velocity: int = 100, gate_ms: int = 200) -> str:
    """Play a MIDI note through the toolkit.

    Sends velocity, note number, and gate on/off to the tk-* buses
    that source modules (osc-bank, fm-voice, etc.) listen to.

    Args:
        note: MIDI note number (0-127). Middle C = 60.
        velocity: Note velocity (0-127). Default 100.
        gate_ms: Gate duration in milliseconds. 0 = note on only (no off).
    """
    send_fudi(f"set tk-velocity {velocity}")
    send_fudi(f"set tk-note {note}")
    send_fudi(f"set tk-gate 1")
    if gate_ms > 0:
        time.sleep(gate_ms / 1000.0)
        send_fudi(f"set tk-gate 0")
    return f"Played note {note} vel={velocity} gate={gate_ms}ms"


@mcp.tool()
def pd_transport(action: str) -> str:
    """Control transport: play, stop, or panic.

    - play: starts DSP and triggers play
    - stop: stops sequencer
    - panic: all notes off + DSP off
    """
    actions = {
        "play": "tk-play",
        "stop": "tk-stop",
        "panic": "tk-panic",
    }
    target = actions.get(action.lower())
    if not target:
        return f"Unknown action '{action}'. Use: play, stop, panic"
    send_fudi(f"trig {target}")
    return f"Transport: {action}"


@mcp.tool()
def pd_dsp(on: bool) -> str:
    """Toggle Pd DSP audio processing on or off."""
    send_fudi(f"pd dsp {1 if on else 0}")
    return f"DSP {'on' if on else 'off'}"


@mcp.tool()
def pd_status() -> dict:
    """Read the latest monitoring state from Pd.

    Returns buffered reports including:
      vu-L, vu-R         - VU meter levels (dB, typically -100 to 0)
      seq-step            - current sequencer step number
      seq-tempo           - sequencer tempo in BPM
      seq-status          - sequencer status (Stopped/Running/etc.)
      limit-indicator     - limiter active (0 or 1)
      rec-timer           - recording timer in seconds
    """
    return status.get_all()


if __name__ == "__main__":
    mcp.run()
