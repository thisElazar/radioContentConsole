#!/usr/bin/env python3
"""Generate multi-slot sample-player.pd with 8-sample bank.

Keeps the original playback engine (pd player) byte-for-byte.
Replaces the file-loader with a slot-manager that stores 8 filenames
in symbol objects and reloads on slot switch.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'puredata-compiler'))
from puredata_compiler.parser import parse
from puredata_compiler.serializer import serialize


class PdBuilder:
    """Builds a Pd canvas with tracked object indices."""
    def __init__(self):
        self.lines = []
        self.idx = 0

    def obj(self, x, y, text):
        i = self.idx; self.idx += 1
        self.lines.append(f"#X obj {x} {y} {text};")
        return i

    def msg(self, x, y, text):
        i = self.idx; self.idx += 1
        self.lines.append(f"#X msg {x} {y} {text};")
        return i

    def text(self, x, y, text):
        i = self.idx; self.idx += 1
        self.lines.append(f"#X text {x} {y} {text};")
        return i

    def floatatom(self, x, y, width, lo, hi, flag, label, send, recv):
        i = self.idx; self.idx += 1
        self.lines.append(f"#X floatatom {x} {y} {width} {lo} {hi} {flag} {label} {send} {recv} 0;")
        return i

    def symbolatom(self, x, y, width, lo, hi, flag, label, send, recv):
        i = self.idx; self.idx += 1
        self.lines.append(f"#X symbolatom {x} {y} {width} {lo} {hi} {flag} {label} {send} {recv} 0;")
        return i

    def connect(self, src, src_out, dst, dst_in):
        self.lines.append(f"#X connect {src} {src_out} {dst} {dst_in};")

    def raw(self, line):
        """Add a raw line (e.g. canvas header, restore). Does NOT increment index."""
        self.lines.append(line)

    def subpatch_placeholder(self, x, y, name):
        """Reserve an index for a subpatch (canvas...restore counts as one object)."""
        i = self.idx; self.idx += 1
        # The actual content is injected separately; this just reserves the index.
        return i

    def output(self):
        return '\n'.join(self.lines) + '\n'


def build_init_subpatch():
    """Init subpatch — sets defaults on loadbang."""
    lines = []
    lines.append("#N canvas 0 0 600 300 init 0;")
    lines.append("#X obj 30 30 loadbang;")                          # 0
    lines.append("#X obj 30 70 t b b b b b b b;")                  # 1
    lines.append("#X obj 30 120 f 1;")                              # 2: speed
    lines.append("#X obj 100 120 f 0;")                             # 3: loop
    lines.append("#X obj 170 120 f 0;")                             # 4: lstart
    lines.append("#X obj 240 120 f 100;")                           # 5: lend
    lines.append("#X obj 310 120 f 0;")                             # 6: direction
    lines.append("#X obj 380 120 f -6;")                            # 7: level
    lines.append("#X obj 450 120 f 0;")                             # 8: cur-slot init
    lines.append("#X obj 30 160 s $0-ctl-speed;")                   # 9
    lines.append("#X obj 100 160 s $0-ctl-loop;")                   # 10
    lines.append("#X obj 170 160 s $0-ctl-lstart;")                 # 11
    lines.append("#X obj 240 160 s $0-ctl-lend;")                   # 12
    lines.append("#X obj 310 160 s $0-ctl-direction;")              # 13
    lines.append("#X obj 380 160 s $0-ctl-level;")                  # 14
    lines.append("#X obj 450 160 s $0-cur-slot;")                   # 15  # init sends to system name
    # connections
    lines.append("#X connect 0 0 1 0;")
    for i in range(7):
        lines.append(f"#X connect 1 {i} {i+2} 0;")
    for i in range(7):
        lines.append(f"#X connect {i+2} 0 {i+9} 0;")
    return lines


def build_sample_graph():
    """Sample waveform display array."""
    lines = []
    lines.append("#N canvas 0 0 450 350 sample-graph 0;")
    lines.append("#X array $0-sample 190409 float 2;")
    lines.append("#A color 0;")
    lines.append("#A width 2;")
    lines.append("#X coords 0 1 190409 -1 400 100 1;")
    return lines


def build_slot_manager():
    """Slot manager subpatch — 8 filename slots, store/recall, sfload."""
    b = PdBuilder()
    b.raw("#N canvas 0 0 900 700 slot-manager 0;")

    # --- Inlets ---
    inp = b.obj(30, 30, "inlet")                                # 0: bang from Load button

    # --- Openpanel ---
    opnl = b.obj(30, 70, "openpanel")                           # 1

    # --- Slot state ---
    r_slot = b.obj(400, 30, "r $0-cur-slot")                    # 2
    f_slot = b.obj(400, 60, "f 0")                              # 3: stored current slot

    # --- Filename trigger ---
    # t b s s: outlets 0=b, 1=s, 2=s
    # Fire order (R→L): 2(filename→load+display), 1(filename→pack cold), 0(bang→f→pack hot)
    trig = b.obj(30, 110, "t b s s")                            # 4

    # --- Store path ---
    pack = b.obj(30, 180, "pack f s")                           # 5
    route = b.obj(30, 210, "route 0 1 2 3 4 5 6 7")            # 6

    # --- Bank (8 symbol objects) ---
    bank = []
    for i in range(8):
        s = b.obj(30 + i * 100, 260, "symbol empty")           # 7-14
        bank.append(s)

    # --- Recall path ---
    r_slot2 = b.obj(400, 140, "r $0-cur-slot")                 # 15
    sel_recall = b.obj(400, 170, "sel 0 1 2 3 4 5 6 7")        # 16

    # --- Empty filter ---
    sel_empty = b.obj(30, 340, "sel empty")                     # 17

    # --- Load + display (shared by openpanel and recall) ---
    t_load = b.obj(30, 400, "t s s")                            # 18
    s_fname = b.obj(30, 440, "s $0-cur-filename")               # 19
    msg_load = b.msg(200, 440, "load \\$1")                     # 20
    sfload = b.obj(200, 470, "else/sfload $0-sample")           # 21
    unpack = b.obj(200, 510, "unpack f")                        # 22
    s_frames = b.obj(200, 540, "s $0-frames")                   # 23

    # --- Empty slot handling ---
    msg_empty = b.msg(200, 340, "empty")                        # 24
    s_fname2 = b.obj(200, 370, "s $0-cur-filename")             # 25
    zero = b.obj(350, 340, "0")                                 # 26
    s_frames2 = b.obj(350, 370, "s $0-frames")                  # 27

    # ===== CONNECTIONS =====

    # Load button → openpanel
    b.connect(inp, 0, opnl, 0)
    # openpanel → trigger
    b.connect(opnl, 0, trig, 0)
    # cur-slot → f right inlet (cold store)
    b.connect(r_slot, 0, f_slot, 1)

    # t b s s:
    # outlet 2 (s, fires first) → load+display
    b.connect(trig, 2, t_load, 0)
    # outlet 1 (s, fires second) → pack right inlet (cold, filename)
    b.connect(trig, 1, pack, 1)
    # outlet 0 (b, fires last) → f (bang recall slot number)
    b.connect(trig, 0, f_slot, 0)

    # f → pack left inlet (hot, triggers with slot number)
    b.connect(f_slot, 0, pack, 0)
    # pack → route
    b.connect(pack, 0, route, 0)

    # route outlets → bank symbol RIGHT inlets (cold store)
    for i in range(8):
        b.connect(route, i, bank[i], 1)

    # recall: r cur-slot → sel
    b.connect(r_slot2, 0, sel_recall, 0)
    # sel outlets → bank symbol LEFT inlets (bang recall)
    for i in range(8):
        b.connect(sel_recall, i, bank[i], 0)

    # bank outputs → empty filter
    for i in range(8):
        b.connect(bank[i], 0, sel_empty, 0)

    # empty filter rejection → load+display
    b.connect(sel_empty, 1, t_load, 0)

    # t s s load+display:
    # outlet 1 (fires first) → display filename
    b.connect(t_load, 1, s_fname, 0)
    # outlet 0 (fires second) → sfload
    b.connect(t_load, 0, msg_load, 0)
    b.connect(msg_load, 0, sfload, 0)
    b.connect(sfload, 0, unpack, 0)
    b.connect(unpack, 0, s_frames, 0)

    # empty slot handling
    b.connect(sel_empty, 0, msg_empty, 0)
    b.connect(msg_empty, 0, s_fname2, 0)
    b.connect(sel_empty, 0, zero, 0)
    b.connect(zero, 0, s_frames2, 0)

    return b.lines


def build_player():
    """Read the original player subpatch from existing sample-player.pd."""
    src = os.path.join(os.path.dirname(__file__), '..', 'modules', 'sample-player.pd')
    with open(src) as f:
        text = f.read()
    model = parse(text)
    # Find the player subpatch
    for node in model.nodes:
        from puredata_compiler.model import Canvas
        if isinstance(node, Canvas) and node.name == 'player':
            # Re-serialize just this subpatch
            lines = []
            from puredata_compiler.serializer import _serialize_canvas
            _serialize_canvas(node, lines, top_level=False)
            lines.append(f"#X restore {node.restore_x} {node.restore_y} pd {node.name};")
            return lines
    raise RuntimeError("Could not find pd player subpatch in sample-player.pd")


def build_sample_player():
    """Build the complete sample-player.pd file."""
    p = PdBuilder()
    p.raw("#N canvas 175 86 850 750 12;")

    # --- Core objects ---
    desc = p.text(20, 10,
        "sample-player \u2014 Multi-slot sample player with 8 banks. "
        "Load audio files into numbered slots and switch between them. "
        "Speed \\, pitch \\, loop \\, and level controls. "
        "Use for field recordings \\, vocal snippets \\, spoken legal IDs \\, or found sounds.")
    # 0: text

    gate = p.obj(20, 60, "r tk-source\\$1-gate")               # 1
    panic = p.obj(155, 59, "r tk-panic")                        # 2

    # --- Subpatches (each counts as 1 object) ---
    # Init
    init_lines = build_init_subpatch()
    for line in init_lines:
        p.raw(line)
    p.raw("#X restore 240 60 pd init;")
    init_idx = 3
    p.idx = 4

    # Sample graph
    graph_lines = build_sample_graph()
    for line in graph_lines:
        p.raw(line)
    p.raw("#X restore 20 173 pd sample-graph;")
    graph_idx = 4
    p.idx = 5

    # Slot manager
    slot_lines = build_slot_manager()
    for line in slot_lines:
        p.raw(line)
    p.raw("#X restore 20 230 pd slot-manager;")
    slot_idx = 5
    p.idx = 6

    # Player (from original)
    player_lines = build_player()
    for line in player_lines:
        p.raw(line)
    player_idx = 6
    p.idx = 7

    # --- Signal + control wiring ---
    s_play = p.obj(20, 104, "s $0-gui-play")                   # 7
    panic_t = p.obj(142, 85, "t b")                             # 8
    stop_f = p.obj(67, 82, "f 0")                               # 9
    throw_l = p.obj(20, 310, "throw~ tk-source\\$1-L")          # 10
    throw_r = p.obj(20, 340, "throw~ tk-source\\$1-R")          # 11

    # --- GUI section ---
    hdr = p.obj(453, 14, "cnv 15 260 20 empty empty SAMPLE\\ PLAYER 4 10 0 14 #e0f0fc #000000 0")  # 12
    sep1 = p.obj(453, 44, "cnv 5 260 2 empty empty empty 0 0 0 12 #fc0400 #000000 0")              # 13

    # Slot selector
    slot_label = p.text(453, 62, "Slot")                        # 14
    # IMPORTANT: send and receive MUST differ or Pd creates an infinite loop.
    # send=$0-cur-slot (user clicks → system), recv=$0-cur-slot-gui (system → display)
    slot_radio = p.obj(490, 58, "hradio 20 1 0 8 $0-cur-slot $0-cur-slot-gui empty 0 -8 0 10 #fcfcfc #000000 #000000 0")  # 15

    # Load button
    load_bng = p.obj(347, 90, "bng 19 250 50 0 empty empty empty 0 -10 0 12 #fcfcfc #000000 #000000")  # 16

    # Filename display
    fname_lbl = p.text(453, 84, "File:")                        # 17
    fname = p.symbolatom(490, 84, 20, 0, 0, 0, "$0-cur-filename", "-", "-")  # 18

    # Duration
    dur_cnv = p.obj(453, 109, "cnv 15 130 15 empty empty Duration: 4 8 0 10 #e0f0fc #000000 0")  # 19
    dur_val = p.floatatom(598, 123, 6, 0, 0, 0, "$0-duration", "-", "-")  # 20
    dur_txt = p.text(653, 123, "sec")                           # 21

    # Play/Stop
    play_tgl = p.obj(453, 134, "tgl 25 1 $0-ctl-play $0-gui-play Play/Stop 30 10 0 4 #000000 #ffffff #fcfcfc 1 1")  # 22

    # Speed
    spd_cnv = p.obj(453, 169, "cnv 15 260 20 empty empty SPEED 4 10 0 12 #e0f0fc #000000 0")  # 23
    spd_sl = p.obj(453, 194, "hsl 128 15 0.25 2 0 1 $0-ctl-speed $0-ctl-speed Speed -2 -8 0 4 #000000 #ffffff #ffffff 12700 1")  # 24
    spd_val = p.floatatom(593, 194, 5, 0.25, 2, 1, "-", "$0-ctl-speed", "-")  # 25
    spd_txt = p.text(643, 194, "x")                             # 26

    # Direction
    dir_cnv = p.obj(453, 224, "cnv 15 260 20 empty empty DIRECTION 4 10 0 12 #e0f0fc #000000 0")  # 27
    dir_rad = p.obj(453, 249, "hradio 20 1 1 2 $0-ctl-direction $0-ctl-direction empty 0 0 0 12 #fcfcfc #000000 #000000 1")  # 28
    dir_txt = p.text(503, 251, "Fwd\\ /\\ Rev")                # 29

    # Loop
    loop_cnv = p.obj(453, 284, "cnv 15 260 20 empty empty LOOP 4 10 0 12 #e0f0fc #000000 0")  # 30
    loop_tgl = p.obj(453, 309, "tgl 20 1 $0-ctl-loop $0-ctl-loop Loop 24 8 0 4 #000000 #ffffff #fcfcfc 0 1")  # 31

    # Loop start
    ls_cnv = p.obj(453, 339, "cnv 15 260 20 empty empty LOOP\\ START 4 10 0 12 #e0f0fc #000000 0")  # 32
    ls_sl = p.obj(453, 364, "hsl 128 15 0 100 0 1 $0-ctl-lstart $0-ctl-lstart Start -2 -8 0 4 #000000 #ffffff #fcfcfc 3300 1")  # 33
    ls_val = p.floatatom(593, 364, 5, 0, 100, 1, "-", "$0-ctl-lstart", "-")  # 34
    ls_txt = p.text(643, 364, "%")                              # 35

    # Loop end
    le_cnv = p.obj(453, 389, "cnv 15 260 20 empty empty LOOP\\ END 4 10 0 12 #e0f0fc #000000 0")  # 36
    le_sl = p.obj(453, 414, "hsl 128 15 0 100 0 1 $0-ctl-lend $0-ctl-lend End -2 -8 0 4 #000000 #ffffff #bcbcbc 9300 1")  # 37
    le_val = p.floatatom(593, 414, 5, 0, 100, 1, "-", "$0-ctl-lend", "-")  # 38
    le_txt = p.text(643, 414, "%")                              # 39

    # Output level
    lv_cnv = p.obj(453, 444, "cnv 15 260 20 empty empty OUTPUT\\ LEVEL 4 10 0 12 #e0f0fc #000000 0")  # 40
    lv_sl = p.obj(453, 469, "hsl 128 15 -60 0 0 1 $0-ctl-level $0-ctl-level Level -2 -8 0 4 #000000 #ffffff #ffffff 11430 1")  # 41
    lv_val = p.floatatom(593, 469, 5, -60, 0, 1, "-", "$0-ctl-level", "-")  # 42
    lv_txt = p.text(643, 469, "dB")                             # 43

    # Bottom separator
    sep2 = p.obj(453, 499, "cnv 5 260 2 empty empty empty 0 0 0 12 #fc0400 #000000 0")  # 44
    chain = p.text(19, 394, "Chain:\\ File\\ >\\ Slot\\ Bank\\ >\\ Array\\ >\\ tabread4~\\ >\\ Level\\ >\\ Out")  # 45

    # ===== CONNECTIONS =====
    # gate → play trigger
    p.connect(gate, 0, s_play, 0)
    # panic → t b → f 0 → play trigger
    p.connect(panic, 0, panic_t, 0)
    p.connect(panic_t, 0, stop_f, 0)
    p.connect(stop_f, 0, s_play, 0)
    # player → throw~
    p.connect(player_idx, 0, throw_l, 0)
    p.connect(player_idx, 0, throw_r, 0)
    # Load button → slot-manager
    p.connect(load_bng, 0, slot_idx, 0)

    return p.output()


if __name__ == '__main__':
    content = build_sample_player()
    outpath = os.path.join(os.path.dirname(__file__), '..', 'modules', 'sample-player.pd')
    with open(outpath, 'w') as f:
        f.write(content)
    print(f"Generated {outpath}")
    print(f"Total lines: {len(content.strip().split(chr(10)))}")
