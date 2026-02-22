#!/usr/bin/env python3
"""Build per-module note/gate routing for the station audio toolkit.

Changes:
1. Sequencer sends to dedicated tk-seq-{note,gate,velocity} buses
2. Module receivers renamed to per-source tk-source{N}-{note,gate,vel}
3. Note-router subpatch in console.pd forwards manual + gated seq input
4. Seq toggles added to each source strip in console GUI
5. Init defaults for tk-source{N}-seq 0
"""

import sys
import os

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "puredata-compiler")
)

from puredata_compiler import Patch, Canvas, Obj, Msg, Connection
from puredata_compiler.model import GuiElement

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STRIP_X = [20, 256, 492, 728, 964]


def find_subpatch(canvas, name):
    for n in canvas.nodes:
        if isinstance(n, Canvas) and n.name == name:
            return n
    raise ValueError(f"subpatch '{name}' not found")


# ── Phase 1: Sequencer sends ────────────────────────────────────────


def rename_sequencer_sends(patch):
    """Rename s tk-{note,gate,velocity} → s tk-seq-* in engine subpatch."""
    engine = find_subpatch(patch.canvas, "engine")
    renames = {
        "tk-note": "tk-seq-note",
        "tk-gate": "tk-seq-gate",
        "tk-velocity": "tk-seq-velocity",
    }
    count = 0
    for node in engine.nodes:
        if isinstance(node, Obj) and len(node.tokens) == 2 and node.tokens[0] == "s":
            if node.tokens[1] in renames:
                node.tokens[1] = renames[node.tokens[1]]
                count += 1
    print(f"  sequencer.pd: {count} sends renamed")
    assert count == 5, f"Expected 5 renames, got {count}"


# ── Phase 2: Module receivers ────────────────────────────────────────

MODULE_RENAMES = {
    "modules/osc-bank.pd": {
        "tk-note": "tk-source1-note",
        "tk-gate": "tk-source1-gate",
        "tk-velocity": "tk-source1-vel",
    },
    "modules/chord-pad.pd": {
        "tk-note": "tk-source2-note",
    },
    "modules/fm-voice.pd": {
        "tk-note": "tk-source3-note",
        "tk-gate": "tk-source3-gate",
    },
    "modules/noise-sculptor.pd": {
        "tk-gate": "tk-source4-gate",
    },
    "modules/sample-player.pd": {
        "tk-gate": "tk-source5-gate",
    },
}


def rename_module_receivers(patch, renames):
    """Rename top-level r tk-{note,gate,velocity} → per-source receivers."""
    count = 0
    for node in patch.canvas.nodes:
        if isinstance(node, Obj) and len(node.tokens) == 2 and node.tokens[0] == "r":
            if node.tokens[1] in renames:
                node.tokens[1] = renames[node.tokens[1]]
                count += 1
    return count


# ── Phase 3: Note-router subpatch ────────────────────────────────────


def build_note_router():
    """Build pd note-router: forwards manual + gated seq to per-source buses.

    Layout:
      0-2:  r tk-note, r tk-gate, r tk-velocity  (global/manual)
      3-5:  r tk-seq-note, r tk-seq-gate, r tk-seq-velocity

    Per source N (1-5), base index b = 6 + (N-1)*10:
      b+0:  r tk-sourceN-seq        (toggle receiver)
      b+1:  spigot 0                (seq-note gate)
      b+2:  spigot 0                (seq-gate gate)
      b+3:  spigot 0                (seq-vel gate)
      b+4:  s tk-sourceN-note       (manual send)
      b+5:  s tk-sourceN-gate       (manual send)
      b+6:  s tk-sourceN-vel        (manual send)
      b+7:  s tk-sourceN-note       (seq send)
      b+8:  s tk-sourceN-gate       (seq send)
      b+9:  s tk-sourceN-vel        (seq send)
    """
    nr = Canvas(
        x=0, y=0, width=1050, height=750,
        name="note-router", open_on_load=0,
        restore_x=700, restore_y=210,
    )

    # Global receivers (0-2)
    nr.nodes.append(Obj(30, 30, ["r", "tk-note"]))         # 0
    nr.nodes.append(Obj(200, 30, ["r", "tk-gate"]))        # 1
    nr.nodes.append(Obj(370, 30, ["r", "tk-velocity"]))    # 2
    # Seq receivers (3-5)
    nr.nodes.append(Obj(540, 30, ["r", "tk-seq-note"]))    # 3
    nr.nodes.append(Obj(710, 30, ["r", "tk-seq-gate"]))    # 4
    nr.nodes.append(Obj(880, 30, ["r", "tk-seq-velocity"]))  # 5

    for n in range(1, 6):
        y = 80 + (n - 1) * 120
        b = 6 + (n - 1) * 10

        nr.nodes.extend([
            Obj(30,  y,      ["r", f"tk-source{n}-seq"]),         # b+0
            Obj(540, y + 30, ["spigot", "0"]),                    # b+1
            Obj(710, y + 30, ["spigot", "0"]),                    # b+2
            Obj(880, y + 30, ["spigot", "0"]),                    # b+3
            Obj(30,  y + 60, ["s", f"tk-source{n}-note"]),        # b+4
            Obj(200, y + 60, ["s", f"tk-source{n}-gate"]),        # b+5
            Obj(370, y + 60, ["s", f"tk-source{n}-vel"]),         # b+6
            Obj(540, y + 60, ["s", f"tk-source{n}-note"]),        # b+7
            Obj(710, y + 60, ["s", f"tk-source{n}-gate"]),        # b+8
            Obj(880, y + 60, ["s", f"tk-source{n}-vel"]),         # b+9
        ])

        # Manual path: global receivers → manual sends
        nr.nodes.append(Connection(0, 0, b + 4, 0))
        nr.nodes.append(Connection(1, 0, b + 5, 0))
        nr.nodes.append(Connection(2, 0, b + 6, 0))

        # Seq path: seq receivers → spigots → seq sends
        nr.nodes.append(Connection(3, 0, b + 1, 0))
        nr.nodes.append(Connection(4, 0, b + 2, 0))
        nr.nodes.append(Connection(5, 0, b + 3, 0))
        nr.nodes.append(Connection(b + 1, 0, b + 7, 0))
        nr.nodes.append(Connection(b + 2, 0, b + 8, 0))
        nr.nodes.append(Connection(b + 3, 0, b + 9, 0))

        # Toggle → spigot right inlets
        nr.nodes.append(Connection(b, 0, b + 1, 1))
        nr.nodes.append(Connection(b, 0, b + 2, 1))
        nr.nodes.append(Connection(b, 0, b + 3, 1))

    return nr


# ── Phase 4: Console modifications ──────────────────────────────────


def modify_console(patch):
    """Add note-router, seq toggles, and init defaults to console."""
    canvas = patch.canvas

    # A) Seq toggles for each strip
    toggles = []
    for n in range(1, 6):
        bx = STRIP_X[n - 1]
        toggles.append(GuiElement(
            bx + 10, 150, "tgl",
            ["15", "0", f"tk-source{n}-seq", f"tk-source{n}-seq",
             "Seq", "18", "7", "0", "10", "-262144", "-1", "-1", "0", "1"],
        ))

    # B) Note-router subpatch
    router = build_note_router()

    # C) Init: add seq defaults
    init = find_subpatch(canvas, "init")

    seq_msg = Msg(250, 300, raw_text=(
        "\\; tk-source1-seq 0"
        " \\; tk-source2-seq 0"
        " \\; tk-source3-seq 0"
        " \\; tk-source4-seq 0"
        " \\; tk-source5-seq 0"
    ))

    # Add 'b' to trigger for new outlet
    for node in init.nodes:
        if isinstance(node, Obj) and node.tokens and node.tokens[0] == "t":
            node.tokens.append("b")
            break

    # Insert msg before connections in init
    init_insert = len(init.nodes)
    for i, node in enumerate(init.nodes):
        if isinstance(node, Connection):
            init_insert = i
            break
    init.nodes.insert(init_insert, seq_msg)
    new_msg_idx = len(init.elements) - 1
    init.nodes.append(Connection(1, 8, new_msg_idx, 0))

    # D) Insert toggles + router into console before connections
    console_insert = len(canvas.nodes)
    for i, node in enumerate(canvas.nodes):
        if isinstance(node, Connection):
            console_insert = i
            break

    new_items = toggles + [router]
    for j, item in enumerate(new_items):
        canvas.nodes.insert(console_insert + j, item)

    print(f"  Added 5 seq toggles + note-router to console")
    print(f"  Updated init with seq defaults")


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
    print(f"  \u2713 {os.path.basename(path)}")


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


def collect_sr(canvas, sends, recvs):
    for n in canvas.nodes:
        if isinstance(n, Canvas):
            collect_sr(n, sends, recvs)
        elif isinstance(n, Obj) and n.tokens and len(n.tokens) > 1:
            if n.tokens[0] == "s":
                sends.add(n.tokens[1])
            elif n.tokens[0] == "r":
                recvs.add(n.tokens[1])


# ── Main ─────────────────────────────────────────────────────────────


def main():
    print("Phase 1: Sequencer sends...")
    path = os.path.join(BASE, "modules/sequencer.pd")
    p = Patch.read(path)
    rename_sequencer_sends(p)
    p.write(path)
    verify_roundtrip(path)

    print("\nPhase 2: Module receivers...")
    for rel, renames in MODULE_RENAMES.items():
        path = os.path.join(BASE, rel)
        p = Patch.read(path)
        c = rename_module_receivers(p, renames)
        p.write(path)
        print(f"  {os.path.basename(rel)}: {c} renamed")
        verify_roundtrip(path)

    print("\nPhase 3: Console (router + toggles + init)...")
    path = os.path.join(BASE, "console.pd")
    p = Patch.read(path)
    modify_console(p)
    p.write(path)
    verify_roundtrip(path)

    print("\nVerifying connections...")
    all_files = ["console.pd", "modules/sequencer.pd"] + list(MODULE_RENAMES.keys())
    for fn in all_files:
        path = os.path.join(BASE, fn)
        p = Patch.read(path)
        verify_connections(p.canvas, fn)
    print("  \u2713 all connections valid")

    print("\nVerifying bus pairing...")
    sends, recvs = set(), set()
    for fn in os.listdir(os.path.join(BASE, "modules")):
        if fn.endswith(".pd"):
            p = Patch.read(os.path.join(BASE, "modules", fn))
            collect_sr(p.canvas, sends, recvs)
    p = Patch.read(os.path.join(BASE, "console.pd"))
    collect_sr(p.canvas, sends, recvs)

    # Every module receiver should have a matching send
    suffixes = ("-note", "-gate", "-vel")
    src_recvs = {r for r in recvs
                 if r.startswith("tk-source") and any(r.endswith(s) for s in suffixes)}
    unmatched = src_recvs - sends
    if unmatched:
        print(f"  \u26a0 receivers without sends: {unmatched}")
    else:
        print("  \u2713 all module receivers have matching sends")

    # Seq sends should have receivers in note-router
    seq_sends = {s for s in sends if s.startswith("tk-seq-")}
    seq_unmatched = seq_sends - recvs
    if seq_unmatched:
        print(f"  \u26a0 seq sends without receivers: {seq_unmatched}")
    else:
        print("  \u2713 all tk-seq-* sends have receivers")

    print("\nDone. Files modified in-place.")


if __name__ == "__main__":
    main()
