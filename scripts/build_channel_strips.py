#!/usr/bin/env python3
"""
Build per-source channel strips for the station audio toolkit.

Rewires 5 source modules to dedicated throw~/catch~ buses and builds a
mixer subpatch in console.pd with on/off, level, pan, and send controls
per channel.  Also adds a 5th GUI strip for sample-player.

Writes modified files to analysis/ — originals are untouched.
"""

import sys
import os

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "puredata-compiler")
)

from puredata_compiler import Patch, Canvas, Obj, Msg, Connection
from puredata_compiler.model import GuiElement, SymbolAtom, Comment

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "analysis")

# ── Configuration ────────────────────────────────────────────────────

CHANNELS = [
    # (strip_num, bus_name, module_file, handler)
    (1, "oscbank", "modules/osc-bank.pd", "standard"),
    (2, "chordpad", "modules/chord-pad.pd", "standard"),
    (3, "fmvoice", "modules/fm-voice.pd", "standard"),
    (4, "noise", "modules/noise-sculptor.pd", "noise"),
    (5, "sampler", "modules/sample-player.pd", "sampler"),
]

STRIP_X = [20, 256, 492, 728, 964]
STRIP_W = 220
HSL_W = 80
BNG_OFF = 115  # bng/symbolatom offset from strip left
OBJS_PER_CH = 28  # objects per mixer channel strip


# ── Helpers ──────────────────────────────────────────────────────────


def find_subpatch(canvas, name):
    for n in canvas.nodes:
        if isinstance(n, Canvas) and n.name == name:
            return n
    raise ValueError(f"subpatch '{name}' not found")


def remove_elements_and_reindex(canvas, indices_to_remove):
    """Remove elements at given indices; drop/re-index connections."""
    if not indices_to_remove:
        return
    drop = set(indices_to_remove)
    idx_map = {}
    ni = 0
    for oi in range(len(canvas.elements)):
        if oi in drop:
            idx_map[oi] = None
        else:
            idx_map[oi] = ni
            ni += 1
    new_nodes = []
    ei = 0
    for node in canvas.nodes:
        if isinstance(node, Connection):
            ns = idx_map.get(node.src_idx)
            nd = idx_map.get(node.dst_idx)
            if ns is not None and nd is not None:
                new_nodes.append(
                    Connection(ns, node.src_outlet, nd, node.dst_inlet)
                )
        else:
            if ei not in drop:
                new_nodes.append(node)
            ei += 1
    canvas.nodes = new_nodes


def bfs_forward(canvas, start):
    """All element indices reachable via connections from start."""
    reached = {start}
    frontier = {start}
    while frontier:
        nxt = set()
        for c in canvas.connections:
            if c.src_idx in frontier and c.dst_idx not in reached:
                reached.add(c.dst_idx)
                nxt.add(c.dst_idx)
        frontier = nxt
    return reached


# ── Phase A — Module output rewiring ─────────────────────────────────


def rewire_throws(elements, bus_name, skip=None):
    """Rename tk-insert-* throws → tk-{bus}-*; return send throw indices."""
    skip = skip or set()
    send_idx = []
    for i, el in enumerate(elements):
        if i in skip:
            continue
        if isinstance(el, Obj) and el.tokens and el.tokens[0] == "throw~":
            if el.tokens[1] == "tk-insert-L":
                el.tokens[1] = f"tk-{bus_name}-L"
            elif el.tokens[1] == "tk-insert-R":
                el.tokens[1] = f"tk-{bus_name}-R"
            elif el.tokens[1] in ("tk-send-L", "tk-send-R"):
                send_idx.append(i)
    return send_idx


def rewire_standard(canvas, bus):
    sub = find_subpatch(canvas, "output")
    send_idx = rewire_throws(sub.elements, bus)
    remove_elements_and_reindex(sub, send_idx)


def rewire_noise(canvas, bus):
    sub = find_subpatch(canvas, "output")
    # Find r $0-send-amt
    send_amt = None
    for i, el in enumerate(sub.elements):
        if (
            isinstance(el, Obj)
            and el.tokens
            and el.tokens[0] == "r"
            and len(el.tokens) > 1
            and el.tokens[1].endswith("-send-amt")
        ):
            send_amt = i
            break
    remove_set = bfs_forward(sub, send_amt)
    rewire_throws(sub.elements, bus, skip=remove_set)
    remove_elements_and_reindex(sub, remove_set)


def rewire_sampler(canvas, bus):
    send_idx = rewire_throws(canvas.elements, bus)
    remove_elements_and_reindex(canvas, send_idx)


# ── Phase B — Mixer subpatch ─────────────────────────────────────────


def add_channel_strip(nodes, strip_num, bus, base_x, base_idx):
    """Append one channel strip's 28 objects + internal connections."""
    rx = base_x + 110
    b = base_idx

    objects = [
        Obj(base_x, 30, ["catch~", f"tk-{bus}-L"]),  # 0
        Obj(rx, 30, ["catch~", f"tk-{bus}-R"]),  # 1
        Obj(base_x, 80, ["r", f"tk-source{strip_num}-on"]),  # 2
        Obj(base_x, 110, ["pack", "f", "30"]),  # 3
        Obj(base_x, 140, ["line~"]),  # 4
        Obj(base_x, 170, ["*~"]),  # 5  gate L
        Obj(rx, 170, ["*~"]),  # 6  gate R
        Obj(base_x, 210, ["r", f"tk-source{strip_num}-level"]),  # 7
        Obj(base_x, 240, ["expr", "pow(10", "\\,", "$f1/20)"]),  # 8
        Obj(base_x, 270, ["pack", "f", "30"]),  # 9
        Obj(base_x, 300, ["line~"]),  # 10
        Obj(base_x, 330, ["*~"]),  # 11 level L
        Obj(rx, 330, ["*~"]),  # 12 level R
        Obj(base_x, 370, ["r", f"tk-source{strip_num}-pan"]),  # 13
        Obj(base_x, 400, ["expr", "cos($f1", "*", "3.14159", "/", "254)"]),  # 14
        Obj(base_x, 430, ["pack", "f", "30"]),  # 15
        Obj(base_x, 460, ["line~"]),  # 16
        Obj(rx, 400, ["expr", "sin($f1", "*", "3.14159", "/", "254)"]),  # 17
        Obj(rx, 430, ["pack", "f", "30"]),  # 18
        Obj(rx, 460, ["line~"]),  # 19
        Obj(base_x, 490, ["*~"]),  # 20 pan-L out
        Obj(rx, 490, ["*~"]),  # 21 pan-R out
        Obj(base_x, 530, ["r", f"tk-source{strip_num}-send"]),  # 22
        Obj(base_x, 560, ["/", "100"]),  # 23
        Obj(base_x, 590, ["pack", "f", "30"]),  # 24
        Obj(base_x, 620, ["line~"]),  # 25
        Obj(base_x, 650, ["*~"]),  # 26 send-L out
        Obj(rx, 650, ["*~"]),  # 27 send-R out
    ]
    nodes.extend(objects)

    conns = [
        (0, 0, 5, 0),
        (1, 0, 6, 0),  # catch → gate
        (2, 0, 3, 0),
        (3, 0, 4, 0),  # on → pack → line
        (4, 0, 5, 1),
        (4, 0, 6, 1),  # line → gate *~
        (5, 0, 11, 0),
        (6, 0, 12, 0),  # gate → level
        (7, 0, 8, 0),
        (8, 0, 9, 0),
        (9, 0, 10, 0),  # level chain
        (10, 0, 11, 1),
        (10, 0, 12, 1),  # → level *~
        (11, 0, 20, 0),
        (12, 0, 21, 0),  # level → pan
        (13, 0, 14, 0),
        (13, 0, 17, 0),  # pan → cos, sin
        (14, 0, 15, 0),
        (15, 0, 16, 0),
        (16, 0, 20, 1),  # cos chain → pan-L
        (17, 0, 18, 0),
        (18, 0, 19, 0),
        (19, 0, 21, 1),  # sin chain → pan-R
        (20, 0, 26, 0),
        (21, 0, 27, 0),  # pan → send (post-fader)
        (22, 0, 23, 0),
        (23, 0, 24, 0),
        (24, 0, 25, 0),  # send chain
        (25, 0, 26, 1),
        (25, 0, 27, 1),  # → send *~
    ]
    for s, so, d, di in conns:
        nodes.append(Connection(b + s, so, b + d, di))


def build_mixer():
    """Build the complete pd mixer subpatch (5 channel strips + summing)."""
    mx = Canvas(
        x=0, y=0, width=1200, height=850,
        name="mixer", open_on_load=0,
        restore_x=600, restore_y=210,
    )

    for ch, (sn, bus, _, _) in enumerate(CHANNELS):
        add_channel_strip(mx.nodes, sn, bus, 30 + ch * 220, ch * OBJS_PER_CH)

    # Summing: 4 +~ per bus × 4 buses = 16, then 4 outlet~
    S = 5 * OBJS_PER_CH  # 140
    for bus in range(4):
        for i in range(4):
            mx.nodes.append(
                Obj(30 + bus * 280 + i * 50, 720 + (bus % 2) * 30, ["+~"])
            )
    for i in range(4):
        mx.nodes.append(Obj(30 + i * 280, 790, ["outlet~"]))

    # Wire summing
    # per-channel output element offsets: pan-L=20, pan-R=21, send-L=26, send-R=27
    out_off = [20, 21, 26, 27]
    for bus_idx in range(4):
        ss = S + bus_idx * 4  # start of this bus's +~ chain
        off = out_off[bus_idx]
        # ch0 → +~[0] inlet 0,  ch1 → +~[0] inlet 1
        mx.nodes.append(Connection(off, 0, ss, 0))
        mx.nodes.append(Connection(OBJS_PER_CH + off, 0, ss, 1))
        # ch2..4 chain through +~[1..3]
        for i in range(1, 4):
            mx.nodes.append(Connection(ss + i - 1, 0, ss + i, 0))
            mx.nodes.append(
                Connection((i + 1) * OBJS_PER_CH + off, 0, ss + i, 1)
            )
        # last +~ → outlet~
        mx.nodes.append(Connection(ss + 3, 0, S + 16 + bus_idx, 0))

    return mx


# ── Phase C — Console modifications ──────────────────────────────────


def modify_strip_gui(elements):
    """Reposition/resize the 4 existing GUI strips for 5-strip layout."""
    strips = [
        (3, 7, 8, 9, 10, 11, 12, 31),
        (4, 13, 14, 15, 16, 17, 18, 32),
        (5, 19, 20, 21, 22, 23, 24, 33),
        (6, 25, 26, 27, 28, 29, 30, 34),
    ]
    for si, (cnv, tgl, lev, pan, snd, bng, sym, cvs) in enumerate(strips):
        bx = STRIP_X[si]
        elements[cnv].x_pos = bx
        elements[cnv].raw_params[1] = str(STRIP_W)
        elements[tgl].x_pos = bx + 10
        for idx in (lev, pan, snd):
            elements[idx].x_pos = bx + (30 if idx == lev else 10)
            elements[idx].raw_params[0] = str(HSL_W)
        elements[bng].x_pos = bx + BNG_OFF
        elements[sym].x_pos = bx + BNG_OFF
        elements[sym].raw_params[0] = "10"
        elements[cvs].restore_x = bx + BNG_OFF


def build_strip5():
    """Create the 8 elements for the 5th channel strip (sample-player)."""
    bx = STRIP_X[4]
    return [
        GuiElement(
            bx, 55, "cnv",
            ["8", str(STRIP_W), "145", "empty", "empty",
             "Source\\ 5", "6", "10", "0", "12", "-261689", "-1", "0"],
        ),
        GuiElement(
            bx + 10, 75, "tgl",
            ["15", "0", "tk-source5-on", "tk-source5-on", "On",
             "18", "7", "0", "10", "-262144", "-1", "-1", "0", "1"],
        ),
        GuiElement(
            bx + 30, 75, "hsl",
            [str(HSL_W), "15", "-60", "0", "0", "1",
             "tk-source5-level", "tk-source5-level", "Level",
             "-2", "-8", "0", "10", "-262144", "-1", "-1", "8677", "1"],
        ),
        GuiElement(
            bx + 10, 100, "hsl",
            [str(HSL_W), "15", "0", "127", "0", "1",
             "tk-source5-pan", "tk-source5-pan", "Pan",
             "-2", "-8", "0", "10", "-262144", "-1", "-1", "6451", "1"],
        ),
        GuiElement(
            bx + 10, 125, "hsl",
            [str(HSL_W), "15", "0", "100", "0", "1",
             "tk-source5-send", "tk-source5-send", "Send",
             "-2", "-8", "0", "10", "-262144", "-1", "-1", "0", "1"],
        ),
        GuiElement(
            bx + BNG_OFF, 75, "bng",
            ["15", "250", "50", "0", "empty", "empty", "Open",
             "18", "7", "0", "10", "-262144", "-1", "-1"],
        ),
        SymbolAtom(
            bx + BNG_OFF, 100,
            ["10", "0", "0", "0", "-", "tk-source5-name", "-"],
        ),
        Canvas(
            x=200, y=200, width=450, height=300,
            name="open-module-5", open_on_load=0,
            restore_x=bx + BNG_OFF, restore_y=155,
            nodes=[
                Obj(30, 30, ["inlet"]),
                Obj(30, 70, ["openpanel"]),
                Obj(30, 110, ["t", "s", "s"]),
                Msg(30, 150, raw_text="\\; pd open \\$1 ."),
                Obj(200, 110, ["s", "tk-source5-name"]),
                Comment(30, 190, raw_text="Opens a module .pd file"),
                Connection(0, 0, 1, 0),
                Connection(1, 0, 2, 0),
                Connection(2, 0, 3, 0),
                Connection(2, 1, 4, 0),
            ],
        ),
    ]


def modify_init(init_canvas):
    """Add source5 defaults and all-channels-on init message."""
    elems = init_canvas.elements
    # Append source 5 to existing level/pan/send messages
    elems[2].raw_text += " \\; tk-source5-level -6"
    elems[3].raw_text += " \\; tk-source5-pan 64"
    elems[4].raw_text += " \\; tk-source5-send 0"

    # New message: all channels default on
    on_msg = Msg(
        30, 300,
        raw_text=(
            "\\; tk-source1-on 1 \\; tk-source2-on 1"
            " \\; tk-source3-on 1 \\; tk-source4-on 1"
            " \\; tk-source5-on 1"
        ),
    )
    # Insert before first connection to maintain conventional ordering
    insert_at = len(init_canvas.nodes)
    for i, node in enumerate(init_canvas.nodes):
        if isinstance(node, Connection):
            insert_at = i
            break
    init_canvas.nodes.insert(insert_at, on_msg)
    # Connect t outlet 7 → on_msg (element 9)
    init_canvas.nodes.append(Connection(1, 7, 9, 0))


def rebuild_console(canvas):
    """Phase B+C: rebuild console with mixer subpatch and 5th strip."""
    elements = canvas.elements

    # C.1: Reposition existing 4 strips
    modify_strip_gui(elements)

    # C.2: Build strip 5 elements
    strip5 = build_strip5()

    # B: Build mixer
    mixer = build_mixer()

    # C.3: Modify init subpatch (element 98)
    modify_init(elements[98])

    # Reconstruct element list
    # Old 0-34 unchanged, insert strip5 at 35, old 35-82 shifted +8,
    # old 83-88 removed (catch~/send~), mixer+sends inserted,
    # old 89-107 continue.
    new_elements = (
        elements[:35]
        + strip5                        # new indices 35-42
        + elements[35:83]               # old 35-82 → new 43-90
        + [
            mixer,                                              # 91
            Obj(800, 290, ["send~", "tk-sendfx-L"]),            # 92
            Obj(800, 310, ["send~", "tk-sendfx-R"]),            # 93
        ]
        + elements[89:]                 # old 89-107 → new 94-112
    )

    # New index reference:
    #   35-42   strip 5 (cnv, tgl, hsl×3, bng, sym, canvas)
    #   43-90   old 35-82  (shifted +8)
    #   91      pd mixer   (4 outlets: ins-L, ins-R, snd-L, snd-R)
    #   92      send~ tk-sendfx-L
    #   93      send~ tk-sendfx-R
    #   94      inline-fx   (old 89)
    #   95      send-bus    (old 90)
    #   96      master      (old 91)
    #   97      dac~        (old 92)
    #   98      writesf~    (old 93)
    #   99      recording   (old 94)
    #  100      midi        (old 95)
    #  101      +~ L        (old 96)
    #  102      +~ R        (old 97)
    #  103      init        (old 98)
    #  104      open-seq    (old 99)
    #  105      transport   (old 100)

    connections = [
        # GUI: open-module buttons
        Connection(11, 0, 31, 0),       # Open 1 → open-module-1
        Connection(17, 0, 32, 0),       # Open 2 → open-module-2
        Connection(23, 0, 33, 0),       # Open 3 → open-module-3
        Connection(29, 0, 34, 0),       # Open 4 → open-module-4
        Connection(40, 0, 42, 0),       # Open 5 → open-module-5
        Connection(65, 0, 104, 0),      # Open Seq → open-seq (old 57→99)
        # Signal chain
        Connection(91, 0, 94, 0),       # mixer ins-L → inline-fx L
        Connection(91, 1, 94, 1),       # mixer ins-R → inline-fx R
        Connection(91, 2, 92, 0),       # mixer snd-L → send~ sendfx-L
        Connection(91, 2, 95, 0),       # mixer snd-L → send-bus L
        Connection(91, 3, 93, 0),       # mixer snd-R → send~ sendfx-R
        Connection(91, 3, 95, 1),       # mixer snd-R → send-bus R
        Connection(94, 0, 101, 0),      # inline-fx L → +~ L
        Connection(94, 1, 102, 0),      # inline-fx R → +~ R
        Connection(95, 0, 101, 1),      # send-bus L → +~ L
        Connection(95, 1, 102, 1),      # send-bus R → +~ R
        Connection(101, 0, 96, 0),      # +~ L → master L
        Connection(102, 0, 96, 1),      # +~ R → master R
        Connection(96, 0, 97, 0),       # master L → dac~ L
        Connection(96, 0, 98, 0),       # master L → writesf~ L
        Connection(96, 1, 97, 1),       # master R → dac~ R
        Connection(96, 1, 98, 1),       # master R → writesf~ R
    ]

    canvas.nodes = new_elements + connections


# ── Verification ─────────────────────────────────────────────────────


def verify_roundtrip(path):
    from puredata_compiler import parse, serialize

    with open(path) as f:
        text1 = f.read()
    c1 = parse(text1)
    t2 = serialize(c1)
    c2 = parse(t2)
    t3 = serialize(c2)
    assert t2 == t3, f"Round-trip mismatch: {path}"
    print(f"  \u2713 round-trip: {os.path.basename(path)}")


def collect_buses(canvas, throws, catches):
    for n in canvas.nodes:
        if isinstance(n, Canvas):
            collect_buses(n, throws, catches)
        elif isinstance(n, Obj) and n.tokens and len(n.tokens) > 1:
            if n.tokens[0] == "throw~":
                throws.add(n.tokens[1])
            elif n.tokens[0] == "catch~":
                catches.add(n.tokens[1])


def verify_buses(out_dir):
    throws, catches = set(), set()
    for fn in os.listdir(out_dir):
        if fn.endswith(".pd"):
            p = Patch.read(os.path.join(out_dir, fn))
            collect_buses(p.canvas, throws, catches)
    tk_t = {b for b in throws if b.startswith("tk-")}
    tk_c = {b for b in catches if b.startswith("tk-")}
    bad_t = tk_t - tk_c
    bad_c = tk_c - tk_t
    if bad_t:
        print(f"  \u26a0 throw~ without catch~: {bad_t}")
    if bad_c:
        print(f"  \u26a0 catch~ without throw~: {bad_c}")
    if not bad_t and not bad_c:
        print("  \u2713 all tk-* throw~/catch~ buses matched")


def verify_connections(canvas, label=""):
    n = len(canvas.elements)
    for c in canvas.connections:
        assert 0 <= c.src_idx < n, (
            f"{label}: src_idx {c.src_idx} >= {n} elements"
        )
        assert 0 <= c.dst_idx < n, (
            f"{label}: dst_idx {c.dst_idx} >= {n} elements"
        )
    for node in canvas.nodes:
        if isinstance(node, Canvas):
            verify_connections(node, f"{label}/{node.name}")


# ── Main ─────────────────────────────────────────────────────────────


def main():
    os.makedirs(OUT, exist_ok=True)

    print("Phase A: Rewiring module outputs...")
    for strip_num, bus, path, kind in CHANNELS:
        full = os.path.join(BASE, path)
        patch = Patch.read(full)
        if kind == "standard":
            rewire_standard(patch.canvas, bus)
        elif kind == "noise":
            rewire_noise(patch.canvas, bus)
        elif kind == "sampler":
            rewire_sampler(patch.canvas, bus)
        out = os.path.join(OUT, os.path.basename(path))
        patch.write(out)
        verify_roundtrip(out)

    print("\nPhase B+C: Rebuilding console...")
    patch = Patch.read(os.path.join(BASE, "console.pd"))
    rebuild_console(patch.canvas)
    out = os.path.join(OUT, "console.pd")
    patch.write(out)
    verify_roundtrip(out)

    print("\nVerification...")
    verify_buses(OUT)
    for fn in os.listdir(OUT):
        if fn.endswith(".pd"):
            p = Patch.read(os.path.join(OUT, fn))
            verify_connections(p.canvas, fn)
    print("  \u2713 all connection indices valid")

    print(f"\nDone. Modified files in {OUT}/")


if __name__ == "__main__":
    main()
