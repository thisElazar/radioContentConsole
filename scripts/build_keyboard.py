#!/usr/bin/env python3
"""Add a 2-octave chromatic keyboard (C2–B3) to the console.

Inserts a GOP (Graph-On-Parent) subpatch below the source strips at y=210,
shifts all existing sections down by 85px to make room, and re-indexes
top-level connections.

Each key sends its MIDI note number to tk-note and triggers tk-gate 1.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'puredata-compiler'))

from puredata_compiler import Patch
from puredata_compiler.model import (
    Canvas, Obj, Msg, Comment, GuiElement, Connection, RawLine,
    FloatAtom, SymbolAtom, ArrayElement,
)

CONSOLE = os.path.join(os.path.dirname(__file__), '..', 'console.pd')
Y_SHIFT = 85          # pixels to push everything down
Y_THRESHOLD = 205     # shift elements at or below this y

# ── Piano layout constants ──────────────────────────────────────────

# White keys: note name → MIDI number
WHITE_NOTES = [
    ("C2", 36), ("D2", 38), ("E2", 40), ("F2", 41),
    ("G2", 43), ("A2", 45), ("B2", 47),
    ("C3", 48), ("D3", 50), ("E3", 52), ("F3", 53),
    ("G3", 55), ("A3", 57), ("B3", 59),
]

# Black keys: note name → MIDI number, position index (between which white keys)
# Index N means the black key sits between white key N and N+1
BLACK_NOTES = [
    ("C#2", 37, 0), ("D#2", 39, 1),
    ("F#2", 42, 3), ("G#2", 44, 4), ("A#2", 46, 5),
    ("C#3", 49, 7), ("D#3", 51, 8),
    ("F#3", 54, 10), ("G#3", 56, 11), ("A#3", 58, 12),
]

WHITE_W = 62          # white key cnv width
WHITE_H = 68          # white key cnv height
WHITE_SPACING = 66    # center-to-center spacing
WHITE_X0 = 4          # x start within subpatch

BLACK_W = 36          # black key cnv width
BLACK_H = 40          # black key cnv height

BNG_WHITE = 20        # bng size for white keys
BNG_BLACK = 16        # bng size for black keys

DISPLAY_W = 940       # GOP display width
DISPLAY_H = 78        # GOP display height


def build_keyboard_subpatch():
    """Build the keyboard GOP subpatch."""
    c = Canvas(x=0, y=0, width=1000, height=500, name="keyboard", open_on_load=0)

    nodes = c.nodes
    elem_idx = 0  # track element index for connections

    # ── Shared output objects (hidden in GOP) ──

    # elem 0: s tk-note
    nodes.append(Obj(x_pos=30, y_pos=400, tokens=["s", "tk-note"]))
    s_note_idx = elem_idx; elem_idx += 1

    # elem 1: s tk-gate
    nodes.append(Obj(x_pos=200, y_pos=400, tokens=["s", "tk-gate"]))
    s_gate_idx = elem_idx; elem_idx += 1

    # elem 2: msg 1 (for gate trigger)
    nodes.append(Msg(x_pos=200, y_pos=370, raw_text="1"))
    gate_msg_idx = elem_idx; elem_idx += 1

    # Connect gate msg → s tk-gate
    nodes.append(Connection(src_idx=gate_msg_idx, src_outlet=0,
                            dst_idx=s_gate_idx, dst_inlet=0))

    # ── Section label cnv (visible in GOP) ──

    # elem 3: section header background
    nodes.append(GuiElement(
        x_pos=0, y_pos=0, gui_type="cnv",
        raw_params=["8", str(DISPLAY_W), "14", "empty", "empty",
                     "KEYBOARD", "6", "4", "0", "10", "-258113", "-1", "0"],
    ))
    elem_idx += 1

    # ── Pd color encoding: color = -((R>>2)*4096 + (G>>2)*64 + (B>>2)) - 1 ──
    COLOR_WHITE = -262144     # (252, 252, 252)
    COLOR_DARK  = -4162       # (4, 4, 4) near-black
    COLOR_GOLD  = -261313     # (252, 204, 0)

    # ── White key backgrounds (cnv) ──

    white_cnv_start = elem_idx
    white_x_positions = []
    for i in range(14):
        x = WHITE_X0 + i * WHITE_SPACING
        white_x_positions.append(x)
        nodes.append(GuiElement(
            x_pos=x, y_pos=16, gui_type="cnv",
            raw_params=["1", str(WHITE_W), str(WHITE_H), "empty", "empty",
                        "empty", "0", "-7", "0", "10",
                        str(COLOR_WHITE), "-262144", "0"],
        ))
        elem_idx += 1

    # ── Black key backgrounds (cnv) — drawn AFTER white so they overlap ──

    black_cnv_start = elem_idx
    black_x_positions = []
    for name, midi, between in BLACK_NOTES:
        # Position between white keys 'between' and 'between+1'
        wx1 = white_x_positions[between] + WHITE_W
        wx2 = white_x_positions[between + 1]
        bx = (wx1 + wx2) // 2 - BLACK_W // 2
        black_x_positions.append(bx)
        nodes.append(GuiElement(
            x_pos=bx, y_pos=16, gui_type="cnv",
            raw_params=["1", str(BLACK_W), str(BLACK_H), "empty", "empty",
                        "empty", "0", "-7", "0", "10",
                        str(COLOR_DARK), "-1", "0"],
        ))
        elem_idx += 1

    # ── White key bng objects ──

    white_bng_start = elem_idx
    for i, (name, midi) in enumerate(WHITE_NOTES):
        x = white_x_positions[i] + (WHITE_W - BNG_WHITE) // 2
        y = 16 + WHITE_H - BNG_WHITE - 4
        # Label only C notes
        label = name if name.startswith("C") else "empty"
        nodes.append(GuiElement(
            x_pos=x, y_pos=y, gui_type="bng",
            raw_params=[str(BNG_WHITE), "250", "50", "0",
                        "empty", "empty", label,
                        "0", "-7", "0", "10",
                        str(COLOR_GOLD), "-262144", "-1"],
        ))
        elem_idx += 1

    # ── Black key bng objects ──

    black_bng_start = elem_idx
    for i, (name, midi, between) in enumerate(BLACK_NOTES):
        x = black_x_positions[i] + (BLACK_W - BNG_BLACK) // 2
        y = 16 + BLACK_H - BNG_BLACK - 4
        nodes.append(GuiElement(
            x_pos=x, y_pos=y, gui_type="bng",
            raw_params=[str(BNG_BLACK), "250", "50", "0",
                        "empty", "empty", "empty",
                        "0", "-7", "0", "10",
                        str(COLOR_GOLD), "-262144", "-1"],
        ))
        elem_idx += 1

    # ── Message objects for each key (hidden in GOP) ──

    white_msg_start = elem_idx
    for i, (name, midi) in enumerate(WHITE_NOTES):
        x = 30 + i * 60
        nodes.append(Msg(x_pos=x, y_pos=300,
                         raw_text=f"\\; tk-note {midi} \\; tk-gate 1"))
        elem_idx += 1

    black_msg_start = elem_idx
    for i, (name, midi, between) in enumerate(BLACK_NOTES):
        x = 30 + i * 60
        nodes.append(Msg(x_pos=x, y_pos=340,
                         raw_text=f"\\; tk-note {midi} \\; tk-gate 1"))
        elem_idx += 1

    # ── Connections: bng → msg ──

    for i in range(14):
        bng_idx = white_bng_start + i
        msg_idx = white_msg_start + i
        nodes.append(Connection(src_idx=bng_idx, src_outlet=0,
                                dst_idx=msg_idx, dst_inlet=0))

    for i in range(10):
        bng_idx = black_bng_start + i
        msg_idx = black_msg_start + i
        nodes.append(Connection(src_idx=bng_idx, src_outlet=0,
                                dst_idx=msg_idx, dst_inlet=0))

    # ── GOP coords ──
    # #X coords x1 y1 x2 y2 display_w display_h gop margin_x margin_y
    nodes.append(RawLine(raw=f"#X coords 0 -1 1 1 {DISPLAY_W} {DISPLAY_H} 2 0 0"))

    c.restore_x = 20
    c.restore_y = 210
    c.restore_type = "pd"
    return c


def shift_element_y(node, dy):
    """Shift a node's y position by dy if it's at or below Y_THRESHOLD."""
    if isinstance(node, (Obj, Msg, Comment, FloatAtom, SymbolAtom)):
        if node.y_pos >= Y_THRESHOLD:
            node.y_pos += dy
    elif isinstance(node, GuiElement):
        if node.y_pos >= Y_THRESHOLD:
            node.y_pos += dy
    elif isinstance(node, Canvas):
        # Subpatch restore position
        if node.restore_y >= Y_THRESHOLD:
            node.restore_y += dy


def main():
    patch = Patch.read(CONSOLE)
    canvas = patch.canvas

    # ── Step 1: Increase canvas height ──
    canvas.height = canvas.height + Y_SHIFT
    print(f"Canvas height: {canvas.height - Y_SHIFT} → {canvas.height}")

    # ── Step 2: Shift y positions of existing elements at y ≥ Y_THRESHOLD ──
    elements = canvas.elements  # non-connection nodes
    shifted = 0
    for node in elements:
        old_y = getattr(node, 'y_pos', getattr(node, 'restore_y', None))
        if old_y is not None and old_y >= Y_THRESHOLD:
            shift_element_y(node, Y_SHIFT)
            shifted += 1
    print(f"Shifted {shifted} elements down by {Y_SHIFT}px")

    # ── Step 3: Find insertion point ──
    # Insert keyboard subpatch just before the first element at y ≥ 210 + Y_SHIFT
    # (which was originally at y ≥ 210, now shifted)
    insert_idx = None
    for i, node in enumerate(canvas.nodes):
        if isinstance(node, Connection):
            continue
        y = getattr(node, 'y_pos', getattr(node, 'restore_y', None))
        if y is not None and y >= 210 + Y_SHIFT:
            insert_idx = i
            break

    if insert_idx is None:
        insert_idx = len(canvas.nodes)

    # Count how many elements come before insert_idx (for connection re-indexing)
    elem_count_before = sum(
        1 for n in canvas.nodes[:insert_idx]
        if not isinstance(n, Connection)
    )
    print(f"Inserting keyboard subpatch at node position {insert_idx} "
          f"(element index {elem_count_before})")

    # ── Step 4: Build and insert keyboard subpatch ──
    keyboard = build_keyboard_subpatch()
    canvas.nodes.insert(insert_idx, keyboard)

    # ── Step 5: Re-index connections ──
    # The keyboard subpatch is 1 new element at index elem_count_before.
    # All elements at indices >= elem_count_before shift by +1.
    for node in canvas.nodes:
        if isinstance(node, Connection):
            if node.src_idx >= elem_count_before:
                node.src_idx += 1
            if node.dst_idx >= elem_count_before:
                node.dst_idx += 1

    # ── Step 6: Write ──
    patch.write(CONSOLE)
    print(f"Wrote updated console to {CONSOLE}")

    # ── Verification ──
    verify = Patch.read(CONSOLE)
    elems = verify.canvas.elements
    conns = verify.canvas.connections
    print(f"Verification: {len(elems)} elements, {len(conns)} connections")

    # Check keyboard subpatch exists
    keyboards = [e for e in elems if isinstance(e, Canvas) and e.name == "keyboard"]
    if keyboards:
        kb = keyboards[0]
        kb_elems = kb.elements
        kb_conns = kb.connections
        print(f"Keyboard subpatch: {len(kb_elems)} elements, {len(kb_conns)} connections")
        print(f"  Position: ({kb.restore_x}, {kb.restore_y})")
    else:
        print("ERROR: Keyboard subpatch not found!")

    # Check connection validity
    max_idx = len(elems) - 1
    bad = [c for c in conns if c.src_idx > max_idx or c.dst_idx > max_idx]
    if bad:
        print(f"ERROR: {len(bad)} connections reference invalid indices!")
        for b in bad:
            print(f"  {b.src_idx} {b.src_outlet} → {b.dst_idx} {b.dst_inlet}")
    else:
        print("All connections valid.")


if __name__ == "__main__":
    main()
