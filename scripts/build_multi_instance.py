#!/usr/bin/env python3
"""Build multi-instance module support for the station audio toolkit.

Changes:
Part A — Multi-Instance Abstraction Support:
  A1. Replace literal 1004- → $0- in osc-bank.pd and chord-pad.pd
  A2. Parameterize module receivers: hardcoded strip → $1
  A3. Parameterize audio output: throw~ → per-strip names
  A4. Update mixer catch~ in console.pd to per-strip names
  A5. Add abstraction objects to console.pd (one per strip)
  A6. Module name bus uses $1

Part B — Robustness Fixes:
  B1. Sequencer gate-off on stop
  B2. Console init: add tk-gate 0
  B3. MCP server: bang → trig for transport
"""

import sys
import os
import re

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "puredata-compiler")
)

from puredata_compiler import Patch, Canvas, Obj, Msg, Connection
from puredata_compiler.model import GuiElement, FloatAtom, SymbolAtom, Comment, ArrayElement

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_subpatch(canvas, name):
    for n in canvas.nodes:
        if isinstance(n, Canvas) and n.name == name:
            return n
    raise ValueError(f"subpatch '{name}' not found")


def walk_nodes(canvas):
    """Yield all nodes recursively (canvas + all subpatches)."""
    for n in canvas.nodes:
        yield n
        if isinstance(n, Canvas):
            yield from walk_nodes(n)


# ── A1: Fix 1004- → $0- ──────────────────────────────────────────────


def fix_dollarzero(patch, prefix, label):
    """Replace all {prefix} prefixes with $0- in Obj tokens and GuiElement raw_params."""
    count = 0
    for node in walk_nodes(patch.canvas):
        if isinstance(node, Obj):
            for i, tok in enumerate(node.tokens):
                if prefix in tok:
                    node.tokens[i] = tok.replace(prefix, "$0-")
                    count += 1
        elif isinstance(node, GuiElement):
            for i, p in enumerate(node.raw_params):
                if prefix in p:
                    node.raw_params[i] = p.replace(prefix, "$0-")
                    count += 1
        elif isinstance(node, FloatAtom):
            for i, p in enumerate(node.raw_params):
                if prefix in p:
                    node.raw_params[i] = p.replace(prefix, "$0-")
                    count += 1
        elif isinstance(node, SymbolAtom):
            for i, p in enumerate(node.raw_params):
                if prefix in p:
                    node.raw_params[i] = p.replace(prefix, "$0-")
                    count += 1
        elif isinstance(node, ArrayElement):
            for i, p in enumerate(node.raw_params):
                if prefix in p:
                    node.raw_params[i] = p.replace(prefix, "$0-")
                    count += 1
        elif isinstance(node, Msg):
            if prefix in node.raw_text:
                node.raw_text = node.raw_text.replace(prefix, "$0-")
                count += 1
    print(f"  {label}: {count} {prefix} → $0- replacements")
    return count


def fix_hradio_sends(patch, bus_names, label):
    """Wire up hradio elements that have empty send/receive.

    bus_names is a list of bus name strings, matched by order of appearance
    to hradios with send=empty AND receive=empty.
    hradio raw_params: [size, new_and_old, init, number, send, receive, label, ...]
    """
    matched = 0
    for node in walk_nodes(patch.canvas):
        if isinstance(node, GuiElement) and node.gui_type == "hradio" \
                and len(node.raw_params) >= 6:
            if node.raw_params[4] == "empty" and node.raw_params[5] == "empty":
                if matched < len(bus_names):
                    bus = bus_names[matched]
                    node.raw_params[4] = bus
                    node.raw_params[5] = bus
                    matched += 1
    print(f"  {label}: {matched} hradio(s) wired")
    return matched


def fix_floatatom_receive(patch, label):
    """Set floatatom receive to match send, so number boxes update from sliders.

    Floatatom raw_params: [width, lower, upper, label_pos, label, receive, send, oldstyle]
    If receive (index 5) is '-' and send (index 6) is a bus name, move send to receive
    and clear send to '-'. This makes the number box display-only (receives from bus,
    doesn't re-send — avoids Pd's "infinite loop" error for same send/receive).
    """
    count = 0
    for node in walk_nodes(patch.canvas):
        if isinstance(node, FloatAtom) and len(node.raw_params) >= 7:
            recv = node.raw_params[5]
            send = node.raw_params[6]
            if recv == "-" and send != "-" and send.startswith("$0-"):
                node.raw_params[5] = send
                node.raw_params[6] = "-"
                count += 1
    print(f"  {label}: {count} floatatom receive(s) wired")
    return count


# Map of GUI elements whose send symbol should be changed.
# Key: current send symbol, Value: replacement send symbol.
GUI_SEND_FIXES = {
    "modules/sample-player.pd": {
        "$0-gui-speed": "$0-ctl-speed",
        "$0-gui-dir": "$0-ctl-direction",
        "$0-gui-loop": "$0-ctl-loop",
        "$0-gui-lstart": "$0-ctl-lstart",
        "$0-gui-lend": "$0-ctl-lend",
        "$0-gui-level": "$0-ctl-level",
    },
}


def fix_gui_send_receive(patch, send_map, label):
    """Fix GUI elements whose send symbol should point to the engine bus.

    For hsl/tgl/hradio, raw_params send index varies by type:
      hsl: index 7 = send, index 8 = receive
      tgl: index 3 = send, index 4 = receive
      hradio: index 4 = send, index 5 = receive
    """
    send_idx_map = {"hsl": 7, "tgl": 3, "hradio": 4}
    count = 0
    for node in walk_nodes(patch.canvas):
        if isinstance(node, GuiElement) and node.gui_type in send_idx_map:
            si = send_idx_map[node.gui_type]
            if len(node.raw_params) > si and node.raw_params[si] in send_map:
                node.raw_params[si] = send_map[node.raw_params[si]]
                count += 1
    print(f"  {label}: {count} GUI send(s) fixed")
    return count


# ── A2: Parameterize module receivers ─────────────────────────────────

MODULE_RECEIVER_MAP = {
    "modules/osc-bank.pd": {
        "r tk-source1-note": "r tk-source$1-note",
        "r tk-source1-gate": "r tk-source$1-gate",
        "r tk-source1-vel": "r tk-source$1-vel",
    },
    "modules/chord-pad.pd": {
        "r tk-source2-note": "r tk-source$1-note",
    },
    "modules/fm-voice.pd": {
        "r tk-source3-note": "r tk-source$1-note",
        "r tk-source3-gate": "r tk-source$1-gate",
    },
    "modules/noise-sculptor.pd": {
        "r tk-source4-gate": "r tk-source$1-gate",
    },
    "modules/sample-player.pd": {
        "r tk-source5-gate": "r tk-source$1-gate",
    },
}


def parameterize_receivers(patch, renames, label):
    """Replace hardcoded per-source receivers with $1-parameterized ones."""
    count = 0
    for node in patch.canvas.nodes:
        if isinstance(node, Obj) and len(node.tokens) == 2:
            key = f"{node.tokens[0]} {node.tokens[1]}"
            if key in renames:
                new_val = renames[key].split(" ", 1)[1]
                node.tokens[1] = new_val
                count += 1
    print(f"  {label}: {count} receivers parameterized")
    return count


# ── A3: Parameterize throw~ outputs ──────────────────────────────────

MODULE_THROW_MAP = {
    "modules/osc-bank.pd": {
        "tk-oscbank-L": "tk-source$1-L",
        "tk-oscbank-R": "tk-source$1-R",
    },
    "modules/chord-pad.pd": {
        "tk-chordpad-L": "tk-source$1-L",
        "tk-chordpad-R": "tk-source$1-R",
    },
    "modules/fm-voice.pd": {
        "tk-fmvoice-L": "tk-source$1-L",
        "tk-fmvoice-R": "tk-source$1-R",
    },
    "modules/noise-sculptor.pd": {
        "tk-noise-L": "tk-source$1-L",
        "tk-noise-R": "tk-source$1-R",
    },
    "modules/sample-player.pd": {
        "tk-sampler-L": "tk-source$1-L",
        "tk-sampler-R": "tk-source$1-R",
    },
}


def parameterize_throws(patch, renames, label):
    """Replace hardcoded throw~ names with per-strip $1 names."""
    count = 0
    for node in walk_nodes(patch.canvas):
        if isinstance(node, Obj) and len(node.tokens) == 2 and node.tokens[0] == "throw~":
            if node.tokens[1] in renames:
                node.tokens[1] = renames[node.tokens[1]]
                count += 1
    print(f"  {label}: {count} throw~ renamed")
    return count


# ── A4: Update mixer catch~ in console.pd ────────────────────────────

CATCH_RENAMES = {
    "tk-oscbank-L": "tk-source1-L",
    "tk-oscbank-R": "tk-source1-R",
    "tk-chordpad-L": "tk-source2-L",
    "tk-chordpad-R": "tk-source2-R",
    "tk-fmvoice-L": "tk-source3-L",
    "tk-fmvoice-R": "tk-source3-R",
    "tk-noise-L": "tk-source4-L",
    "tk-noise-R": "tk-source4-R",
    "tk-sampler-L": "tk-source5-L",
    "tk-sampler-R": "tk-source5-R",
}


def rename_mixer_catches(patch):
    """Rename catch~ objects in the mixer subpatch."""
    mixer = find_subpatch(patch.canvas, "mixer")
    count = 0
    for node in mixer.nodes:
        if isinstance(node, Obj) and len(node.tokens) == 2 and node.tokens[0] == "catch~":
            if node.tokens[1] in CATCH_RENAMES:
                node.tokens[1] = CATCH_RENAMES[node.tokens[1]]
                count += 1
    print(f"  console.pd mixer: {count} catch~ renamed")
    if count == 0:
        print("    (already applied)")
    else:
        assert count == 10, f"Expected 10 catch~ renames, got {count}"


# ── A5: Add abstraction objects to console.pd ────────────────────────

MODULE_DEFAULTS = [
    ("modules/osc-bank", 1),
    ("modules/chord-pad", 2),
    ("modules/fm-voice", 3),
    ("modules/noise-sculptor", 4),
    ("modules/sample-player", 5),
]


def add_abstraction_objects(patch):
    """Add module abstraction objects with strip number arguments."""
    canvas = patch.canvas

    # Check if already applied
    existing = {
        tuple(n.tokens) for n in canvas.nodes
        if isinstance(n, Obj) and len(n.tokens) == 2
    }
    needed = [(m, s) for m, s in MODULE_DEFAULTS if (m, str(s)) not in existing]
    if not needed:
        print(f"  console.pd: abstraction objects already present (skipped)")
        return

    # Find insertion point: before connections
    insert_idx = len(canvas.nodes)
    for i, node in enumerate(canvas.nodes):
        if isinstance(node, Connection):
            insert_idx = i
            break

    # Place them below the strip area, spaced out
    for j, (module, strip) in enumerate(needed):
        obj = Obj(20 + j * 230, 175, [module, str(strip)])
        canvas.nodes.insert(insert_idx + j, obj)

    print(f"  console.pd: {len(MODULE_DEFAULTS)} abstraction objects added")


# ── B1: Sequencer gate-off on stop ───────────────────────────────────


def fix_sequencer_stop_gate(patch):
    """Add gate-off (0 → s tk-seq-gate) on the stop path in sequencer engine."""
    engine = find_subpatch(patch.canvas, "engine")

    # Check if already applied
    for node in engine.nodes:
        if isinstance(node, Obj) and node.tokens == ["s", "tk-seq-gate"]:
            print(f"  sequencer.pd: gate-off on stop already present (skipped)")
            return

    # Find the stop inlet (inlet index 1 in engine) and the running sender
    # The stop path: inlet 1 → sends 0 to $0-running
    # We need to also send 0 to tk-seq-gate when stop is received.
    #
    # Strategy: find the `0` object connected to `s $0-running` on the stop path
    # and add a parallel path: inlet 1 → t b → 0 → s tk-seq-gate
    #
    # Actually, looking at the engine, inlet 1 is the stop inlet.
    # It connects to `15 0` (the metro). Let's find a simpler approach.
    #
    # The engine has nodes[68-70]:
    #   68: obj `0`     -> s $0-running
    #   69: obj `0`     -> ...
    #   70: obj `s $0-running`
    # Looking at line 208-211: connect 69 0 70 0, connect 70 0 71 0
    #
    # Let me look more carefully at the stop path in the engine.
    # From the connections:
    #   connect 1 0 15 0  -- stop inlet → metro (stops it)
    # But we need gate-off too.
    #
    # Simplest approach: add two new objects after connections:
    #   t b  (triggered by stop inlet)
    #   0    (sends zero)
    #   s tk-seq-gate  (sends gate off)
    # And wire: inlet 1 → t b, t b → 0, 0 → s tk-seq-gate

    # Count current elements to get indices
    elems = engine.elements
    n = len(elems)

    # Add new objects before connections
    insert_idx = len(engine.nodes)
    for i, node in enumerate(engine.nodes):
        if isinstance(node, Connection):
            insert_idx = i
            break

    # We need 3 objects: t b, 0, s tk-seq-gate
    tb = Obj(130, 300, ["t", "b"])
    zero = Obj(130, 330, ["0"])
    send = Obj(130, 360, ["s", "tk-seq-gate"])

    engine.nodes.insert(insert_idx, tb)       # index n
    engine.nodes.insert(insert_idx + 1, zero)  # index n+1
    engine.nodes.insert(insert_idx + 2, send)  # index n+2

    # Wire: stop inlet (1) → tb, tb → zero, zero → send
    engine.nodes.append(Connection(1, 0, n, 0))
    engine.nodes.append(Connection(n, 0, n + 1, 0))
    engine.nodes.append(Connection(n + 1, 0, n + 2, 0))

    print(f"  sequencer.pd: gate-off on stop added (3 new objects)")


# ── B2: Console init: add tk-gate 0 ──────────────────────────────────


def fix_console_init_gate(patch):
    """Add tk-gate 0 to the init message in console.pd."""
    init = find_subpatch(patch.canvas, "init")

    # Find the msg that contains "tk-velocity" and "tk-note" — that's the
    # DSP/note init message. Add tk-gate 0 to it.
    for node in init.nodes:
        if isinstance(node, Msg) and "tk-velocity" in node.raw_text:
            if "tk-gate 0" in node.raw_text:
                print(f"  console.pd init: tk-gate 0 already present (skipped)")
                return
            node.raw_text = node.raw_text.replace(
                "\\; tk-velocity",
                "\\; tk-gate 0 \\; tk-velocity"
            )
            print(f"  console.pd init: tk-gate 0 added")
            return

    raise ValueError("Could not find velocity init message")


# ── B3: MCP server transport fix ──────────────────────────────────────


def fix_mcp_transport():
    """Fix bang → trig in pd-mcp-server.py transport function."""
    path = os.path.join(BASE, "scripts", "pd-mcp-server.py")
    with open(path) as f:
        content = f.read()

    old = 'send_fudi(f"bang {target}")'
    new = 'send_fudi(f"trig {target}")'

    if old not in content:
        if new in content:
            print(f"  pd-mcp-server.py: already fixed (skipped)")
            return
        raise ValueError(f"Expected to find '{old}' or '{new}' in pd-mcp-server.py")
    content = content.replace(old, new)

    with open(path, "w") as f:
        f.write(content)

    print(f"  pd-mcp-server.py: bang → trig on line 137")


# ── Verification ─────────────────────────────────────────────────────


def verify_roundtrip(path):
    from puredata_compiler import parse, serialize

    with open(path) as f:
        t1 = f.read()
    c1 = parse(t1)
    t2 = serialize(c1)
    c2 = parse(t2)
    t3 = serialize(c2)
    assert t2 == t3, f"Round-trip fail: {path}"
    print(f"  ✓ {os.path.basename(path)}")


def verify_connections(canvas, label=""):
    n = len(canvas.elements)
    for c in canvas.connections:
        assert 0 <= c.src_idx < n, (
            f"{label}: src_idx {c.src_idx} out of range (0..{n - 1})"
        )
        assert 0 <= c.dst_idx < n, (
            f"{label}: dst_idx {c.dst_idx} out of range (0..{n - 1})"
        )
    for node in canvas.nodes:
        if isinstance(node, Canvas):
            verify_connections(node, f"{label}/{node.name}")


def collect_throw_catch(canvas, throws, catches):
    for n in canvas.nodes:
        if isinstance(n, Canvas):
            collect_throw_catch(n, throws, catches)
        elif isinstance(n, Obj) and n.tokens and len(n.tokens) >= 2:
            if n.tokens[0] == "throw~":
                throws.add(n.tokens[1])
            elif n.tokens[0] == "catch~":
                catches.add(n.tokens[1])


# ── Main ─────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("Multi-Instance Module Support + Robustness Fixes")
    print("=" * 60)

    # ── Part A: Multi-Instance ──

    print("\nA1: Fix 1004- → $0- in osc-bank and chord-pad...")
    for fn in ("modules/osc-bank.pd", "modules/chord-pad.pd"):
        path = os.path.join(BASE, fn)
        p = Patch.read(path)
        fix_dollarzero(p, "1004-", os.path.basename(fn))
        p.write(path)

    print("\nA1b: Fix prefix → $0- in fm-voice, noise-sculptor, sample-player...")
    module_prefixes = [
        ("modules/fm-voice.pd", "1006-"),
        ("modules/noise-sculptor.pd", "1007-"),
        ("modules/sample-player.pd", "1008-"),
    ]
    for fn, prefix in module_prefixes:
        path = os.path.join(BASE, fn)
        p = Patch.read(path)
        fix_dollarzero(p, prefix, os.path.basename(fn))
        p.write(path)

    print("\nA1c: Wire empty hradio send/receive...")
    # fm-voice: 1 hradio with 8 buttons (CHARACTER)
    path = os.path.join(BASE, "modules/fm-voice.pd")
    p = Patch.read(path)
    fix_hradio_sends(p, ["$0-ratio-sel"], "fm-voice")
    p.write(path)

    # noise-sculptor: 2 hradios with 8 buttons (NOISE SOURCE, FILTER TYPE)
    path = os.path.join(BASE, "modules/noise-sculptor.pd")
    p = Patch.read(path)
    fix_hradio_sends(p, ["$0-noise-color", "$0-filt-type"], "noise-sculptor")
    p.write(path)

    print("\nA1d: Wire floatatom receive symbols...")
    path = os.path.join(BASE, "modules/fm-voice.pd")
    p = Patch.read(path)
    count = fix_floatatom_receive(p, "fm-voice")
    if count > 0:
        p.write(path)

    print("\nA1e: Fix sample-player GUI send/receive...")
    for fn, send_map in GUI_SEND_FIXES.items():
        path = os.path.join(BASE, fn)
        p = Patch.read(path)
        count = fix_gui_send_receive(p, send_map, os.path.basename(fn))
        if count > 0:
            p.write(path)

    print("\nA2: Parameterize module receivers...")
    for fn, renames in MODULE_RECEIVER_MAP.items():
        path = os.path.join(BASE, fn)
        p = Patch.read(path)
        count = parameterize_receivers(p, renames, os.path.basename(fn))
        if count > 0:
            p.write(path)

    print("\nA3: Parameterize throw~ outputs...")
    for fn, renames in MODULE_THROW_MAP.items():
        path = os.path.join(BASE, fn)
        p = Patch.read(path)
        count = parameterize_throws(p, renames, os.path.basename(fn))
        if count > 0:
            p.write(path)

    print("\nA4: Update mixer catch~ in console.pd...")
    console_path = os.path.join(BASE, "console.pd")
    p = Patch.read(console_path)
    rename_mixer_catches(p)
    p.write(console_path)

    print("\nA5: Add abstraction objects to console.pd...")
    p = Patch.read(console_path)
    add_abstraction_objects(p)
    p.write(console_path)

    # ── Part B: Robustness ──

    print("\nB1: Sequencer gate-off on stop...")
    seq_path = os.path.join(BASE, "modules", "sequencer.pd")
    p = Patch.read(seq_path)
    fix_sequencer_stop_gate(p)
    p.write(seq_path)

    print("\nB2: Console init: add tk-gate 0...")
    p = Patch.read(console_path)
    fix_console_init_gate(p)
    p.write(console_path)

    print("\nB3: MCP server transport fix...")
    fix_mcp_transport()

    # ── Verification ──

    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)

    print("\nRound-trip integrity...")
    all_pd_files = [
        "console.pd",
        "modules/sequencer.pd",
        "modules/osc-bank.pd",
        "modules/chord-pad.pd",
        "modules/fm-voice.pd",
        "modules/noise-sculptor.pd",
        "modules/sample-player.pd",
    ]
    for fn in all_pd_files:
        verify_roundtrip(os.path.join(BASE, fn))

    print("\nConnection index validity...")
    for fn in all_pd_files:
        path = os.path.join(BASE, fn)
        p = Patch.read(path)
        verify_connections(p.canvas, fn)
    print("  ✓ all connections valid")

    print("\nBus pairing: throw~/catch~...")
    throws, catches = set(), set()
    for fn in os.listdir(os.path.join(BASE, "modules")):
        if fn.endswith(".pd"):
            p = Patch.read(os.path.join(BASE, "modules", fn))
            collect_throw_catch(p.canvas, throws, catches)
    p = Patch.read(os.path.join(BASE, "console.pd"))
    collect_throw_catch(p.canvas, throws, catches)

    # Every throw~ from modules should have a catch~ in console
    source_throws = {t for t in throws if t.startswith("tk-source") and ("-L" in t or "-R" in t)}
    unmatched = source_throws - catches
    if unmatched:
        print(f"  ⚠ throws without catches: {unmatched}")
    else:
        print("  ✓ all module throw~ have matching catch~")

    # Check catch~ names are the new per-strip format
    old_catches = {c for c in catches if any(
        c.startswith(prefix) for prefix in
        ("tk-oscbank-", "tk-chordpad-", "tk-fmvoice-", "tk-noise-", "tk-sampler-")
    )}
    if old_catches:
        print(f"  ⚠ old module-specific catch~ still present: {old_catches}")
    else:
        print("  ✓ no old module-specific catch~ names remain")

    # Verify MCP fix
    with open(os.path.join(BASE, "scripts", "pd-mcp-server.py")) as f:
        mcp_content = f.read()
    assert 'send_fudi(f"trig {target}")' in mcp_content, "MCP fix not applied"
    assert 'send_fudi(f"bang {target}")' not in mcp_content, "Old bang still present"
    print("  ✓ MCP transport fix verified")

    print("\n" + "=" * 60)
    print("Done. All files modified in-place.")
    print("=" * 60)


if __name__ == "__main__":
    main()
