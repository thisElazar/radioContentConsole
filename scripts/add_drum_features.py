#!/usr/bin/env python3
"""Add pattern length (4/8/16) and shared accent row to drum-machine.pd.

Uses puredata-compiler for safe modification.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'puredata-compiler'))
from puredata_compiler.parser import parse
from puredata_compiler.serializer import serialize
from puredata_compiler.model import (
    Canvas, Obj, Msg, FloatAtom, Comment,
    GuiElement, ArrayElement, Connection, RawLine,
)


def find_subpatch(canvas, name):
    for node in canvas.nodes:
        if isinstance(node, Canvas) and node.name == name:
            return node
    return None


def element_index(canvas, target):
    idx = 0
    for node in canvas.nodes:
        if node is target:
            return idx
        if not isinstance(node, Connection):
            idx += 1
    return None


def insert_before_connections(canvas, node):
    for i, n in enumerate(canvas.nodes):
        if isinstance(n, Connection):
            canvas.nodes.insert(i, node)
            return
    canvas.nodes.append(node)


def add_accent_array(model):
    """Add 1020-accent-pat array to pd arrays subpatch."""
    arrays = find_subpatch(model, 'arrays')
    if not arrays:
        print("  [!] Could not find pd arrays")
        return

    # Add a new graph subpatch with the accent array (same pattern as existing)
    accent_graph = Canvas(x=0, y=0, width=200, height=140, name='(subpatch)', open_on_load=0)
    accent_graph.restore_x = 20
    accent_graph.restore_y = 300
    accent_graph.restore_type = 'graph'
    accent_graph.nodes = [
        ArrayElement(0, 0, ['1020-accent-pat', '16', 'float', '2']),
        RawLine('#A color 0'),
        RawLine('#A width 2'),
        RawLine('#X coords 0 1 15 0 200 50 1'),
    ]
    insert_before_connections(arrays, accent_graph)
    print("  [+] Added 1020-accent-pat array")


def fix_engine_pattern_length(model):
    """Replace hardcoded mod 16 with dynamic pattern length in pd engine."""
    engine = find_subpatch(model, 'engine')
    if not engine:
        print("  [!] Could not find pd engine")
        return

    # Find the mod 16 that wraps the step counter (obj 11 in engine)
    # It's connected: + 1 (obj 10) → mod 16 (obj 11) → f (obj 8, right inlet)
    mod_obj = None
    mod_idx = None
    for node in engine.nodes:
        if isinstance(node, Obj) and node.tokens == ['mod', '16']:
            idx = element_index(engine, node)
            # Check if this is the step counter mod (connected from + 1)
            for c in engine.connections:
                if c.dst_idx == idx and c.src_idx == idx - 1:  # + 1 → mod
                    mod_obj = node
                    mod_idx = idx
                    break
            if mod_obj:
                break

    if not mod_obj:
        print("  [!] Could not find step counter mod 16 in engine")
        return

    # Add r 1020-pat-length → f 16, connect to mod's right inlet
    r_patlen = Obj(400, 250, ['r', '1020-pat-length'])
    insert_before_connections(engine, r_patlen)
    r_patlen_idx = element_index(engine, r_patlen)

    f_patlen = Obj(400, 280, ['f', '16'])
    insert_before_connections(engine, f_patlen)
    f_patlen_idx = element_index(engine, f_patlen)

    engine.nodes.append(Connection(r_patlen_idx, 0, f_patlen_idx, 0))
    # f output → mod right inlet (sets the modulus)
    engine.nodes.append(Connection(f_patlen_idx, 0, mod_idx, 1))

    # Add accent read: tabread 1020-accent-pat at current step → s 1020-accent-val
    # The current step is output by obj 9 (t f f f), outlet 1 goes to pattern reads.
    # I'll tap from the same step value.
    # Find the t f f f object (obj 9)
    t_step = None
    t_step_idx = None
    idx = 0
    for node in engine.nodes:
        if isinstance(node, Obj) and node.tokens == ['t', 'f', 'f', 'f']:
            t_step = node
            t_step_idx = element_index(engine, node)
            break

    if t_step:
        # Add tabread for accent
        accent_read = Obj(730, 370, ['tabread', '1020-accent-pat'])
        insert_before_connections(engine, accent_read)
        accent_read_idx = element_index(engine, accent_read)

        accent_send = Obj(730, 400, ['s', '1020-accent-val'])
        insert_before_connections(engine, accent_send)
        accent_send_idx = element_index(engine, accent_send)

        # Connect: t f f f outlet 1 (step number) → accent tabread
        engine.nodes.append(Connection(t_step_idx, 1, accent_read_idx, 0))
        engine.nodes.append(Connection(accent_read_idx, 0, accent_send_idx, 0))

    print("  [+] Engine: dynamic pattern length + accent read")


def add_accent_gain(model):
    """Add accent gain stage in pd drum-mix."""
    mix = find_subpatch(model, 'drum-mix')
    if not mix:
        print("  [!] Could not find pd drum-mix")
        return

    # Current flow: 8 voice inlets → cascading +~ → master level (*~) → throw~
    # The cascading +~ chain ends at the last +~ before master level.
    # I need to find the master level *~ and insert accent *~ before it.
    #
    # Current objects in drum-mix (from earlier read):
    # 0-7: inlet~ (8 voices)
    # 8-14: +~ (cascading sum, 7 additions)
    # 15: r 1020-master-level-a
    # 16: expr pow(10, $f1/20)
    # 17: pack f 30
    # 18: line~
    # 19: *~ (master level)
    # 20: throw~ tk-drums-L
    # 21: throw~ tk-drums-R
    #
    # Connection: 14→19 (last +~ → master *~) and 18→19 (level line~ → *~ right inlet)
    # I need to insert: 14 → accent_*~ → 19, and remove 14→19

    # Find the connection from last +~ to master *~
    # The last +~ output goes to master *~ left inlet
    elems = mix.elements
    master_mult_idx = None
    last_plus_idx = None

    for c in mix.connections:
        dst = elems[c.dst_idx] if c.dst_idx < len(elems) else None
        src = elems[c.src_idx] if c.src_idx < len(elems) else None
        if (dst and hasattr(dst, 'tokens') and dst.tokens == ['*~'] and
            src and hasattr(src, 'tokens') and src.tokens == ['+~']):
            last_plus_idx = c.src_idx
            master_mult_idx = c.dst_idx

    if master_mult_idx is None:
        print("  [!] Could not find master *~ in drum-mix")
        return

    # Remove connection: last +~ → master *~
    mix.nodes = [n for n in mix.nodes
                 if not (isinstance(n, Connection) and
                         n.src_idx == last_plus_idx and n.dst_idx == master_mult_idx)]

    # Add accent gain objects
    r_accent = Obj(30, 275, ['r', '1020-accent-val'])
    insert_before_connections(mix, r_accent)
    r_accent_idx = element_index(mix, r_accent)

    # if accent=1 → 1.5 (boost), if accent=0 → 1.0 (unity)
    expr_accent = Obj(30, 305, ['expr', 'if($f1', '\\,', '1.5', '\\,', '1)'])
    insert_before_connections(mix, expr_accent)
    expr_accent_idx = element_index(mix, expr_accent)

    pack_accent = Obj(30, 335, ['pack', 'f', '5'])
    insert_before_connections(mix, pack_accent)
    pack_accent_idx = element_index(mix, pack_accent)

    line_accent = Obj(30, 365, ['line~'])
    insert_before_connections(mix, line_accent)
    line_accent_idx = element_index(mix, line_accent)

    mult_accent = Obj(30, 395, ['*~'])
    insert_before_connections(mix, mult_accent)
    mult_accent_idx = element_index(mix, mult_accent)

    # Connect accent chain
    mix.nodes.append(Connection(r_accent_idx, 0, expr_accent_idx, 0))
    mix.nodes.append(Connection(expr_accent_idx, 0, pack_accent_idx, 0))
    mix.nodes.append(Connection(pack_accent_idx, 0, line_accent_idx, 0))
    mix.nodes.append(Connection(line_accent_idx, 0, mult_accent_idx, 1))

    # Reconnect: last +~ → accent *~ → master *~
    mix.nodes.append(Connection(last_plus_idx, 0, mult_accent_idx, 0))
    mix.nodes.append(Connection(mult_accent_idx, 0, master_mult_idx, 0))

    print("  [+] Drum-mix: accent gain stage (1.5x on accent)")


def add_ui_elements(model):
    """Add pattern length selector and accent toggle row to UI."""

    # --- Pattern length selector ---
    # Add in TRANSPORT section area (around y=180)
    # hradio 3 positions → sel 0 1 2 → msg 4/8/16 → s 1020-pat-length

    # Build a small subpatch for the hradio→length mapping
    patlen_sub = Canvas(x=0, y=0, width=400, height=250, name='pattern-length', open_on_load=0)
    patlen_sub.restore_x = 700
    patlen_sub.restore_y = 180
    patlen_sub.nodes = [
        Obj(30, 30, ['inlet']),           # 0
        Obj(30, 60, ['sel', '0', '1', '2']),  # 1
        Msg(30, 100, '4'),                # 2
        Msg(130, 100, '8'),               # 3
        Msg(230, 100, '16'),              # 4
        Obj(30, 140, ['s', '1020-pat-length']),  # 5
        Connection(0, 0, 1, 0),
        Connection(1, 0, 2, 0),
        Connection(1, 1, 3, 0),
        Connection(1, 2, 4, 0),
        Connection(2, 0, 5, 0),
        Connection(3, 0, 5, 0),
        Connection(4, 0, 5, 0),
    ]
    insert_before_connections(model, patlen_sub)
    patlen_sub_idx = element_index(model, patlen_sub)

    # hradio for pattern length
    patlen_label = Comment(630, 183, 'Steps:')
    insert_before_connections(model, patlen_label)

    patlen_radio = GuiElement(
        x_pos=680, y_pos=180, gui_type='hradio',
        raw_params=['18', '1', '0', '3', 'empty', 'empty',
                    'empty', '0', '-8', '0', '10', '#fcfcfc', '#000000', '#000000', '2']
    )
    insert_before_connections(model, patlen_radio)
    patlen_radio_idx = element_index(model, patlen_radio)

    # Label the 3 options
    patlen_labels = Comment(682, 200, '4\\ \\ \\ \\ 8\\ \\ \\ 16')
    insert_before_connections(model, patlen_labels)

    # Connect hradio → pattern-length subpatch
    model.nodes.append(Connection(patlen_radio_idx, 0, patlen_sub_idx, 0))

    # --- Accent toggle row ---
    # Add between STEP POSITION and PATTERN sections
    # Create a section header
    accent_header = GuiElement(
        x_pos=20, y_pos=365, gui_type='cnv',
        raw_params=['12', '1160', '20', 'empty', 'empty', 'ACCENT',
                    '20', '12', '0', '12', '#e0e0e0', '#404040', '0']
    )
    insert_before_connections(model, accent_header)

    # 16 accent toggles (gold color)
    for i in range(16):
        x = 80 + i * 35
        tgl = GuiElement(
            x_pos=x, y_pos=390, gui_type='tgl',
            raw_params=['18', '0', f'1020-accent-s{i}', f'1020-accent-s{i}',
                        'empty', '0', '0', '0', '8', '#fccc00', '#000000', '#a0a0a0', '0', '1']
        )
        insert_before_connections(model, tgl)

    # Label
    accent_label = Comment(20, 393, 'ACC')
    insert_before_connections(model, accent_label)

    # --- Accent sync subpatch (toggle ↔ array) ---
    # Same pattern as existing voice sync subpatches
    accent_sync = Canvas(x=0, y=0, width=700, height=400, name='accent-sync', open_on_load=0)
    accent_sync.restore_x = 700
    accent_sync.restore_y = 350
    nodes = []
    conns = []
    idx = 0

    for i in range(16):
        # r 1020-accent-sN → tabwrite 1020-accent-pat at index N
        r_s = idx; idx += 1
        nodes.append(Obj(30 + i * 40, 30, ['r', f'1020-accent-s{i}']))
        tw = idx; idx += 1
        nodes.append(Obj(30 + i * 40, 70, ['tabwrite', '1020-accent-pat']))
        set_idx_msg = idx; idx += 1
        nodes.append(Msg(30 + i * 40, 100, f'set {i}'))
        # loadbang to set the index
        lb = idx; idx += 1
        nodes.append(Obj(30 + i * 40, 130, ['loadbang']))
        conns.append(Connection(r_s, 0, tw, 0))       # value → tabwrite
        conns.append(Connection(set_idx_msg, 0, tw, 1))  # set index → tabwrite right inlet
        conns.append(Connection(lb, 0, set_idx_msg, 0))   # loadbang → set msg

    accent_sync.nodes = nodes + conns
    insert_before_connections(model, accent_sync)

    print("  [+] UI: pattern length selector + 16 accent toggles")


def update_init(model):
    """Add pattern length and accent init."""
    init = find_subpatch(model, 'init')
    if not init:
        print("  [!] Could not find pd init")
        return

    # Find the trigger object
    trig = None
    trig_idx = None
    for node in init.nodes:
        if isinstance(node, Obj) and node.tokens and node.tokens[0] == 't':
            trig = node
            trig_idx = element_index(init, node)
            break

    if not trig:
        print("  [!] Could not find trigger in init")
        return

    # Add pattern length init
    trig.tokens.append('b')
    new_outlet = len(trig.tokens) - 2

    patlen_msg = Msg(400, 480, '\\; 1020-pat-length 16')
    insert_before_connections(init, patlen_msg)
    patlen_msg_idx = element_index(init, patlen_msg)
    init.nodes.append(Connection(trig_idx, new_outlet, patlen_msg_idx, 0))

    # Add accent array init (zeros) — append to the existing pattern init msg
    # Find the msg that sets the pattern arrays
    for node in init.nodes:
        if isinstance(node, Msg) and '1020-kick-pat' in node.raw_text:
            node.raw_text += ' \\; array set 1020-accent-pat 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0'
            break

    # Add accent refresh to the refresh-ui trigger
    # The refresh-ui bang should also trigger accent UI refresh
    # But this is handled by the accent-sync loadbang already

    print("  [+] Init: pattern length 16 + accent array zeros")


def add_accent_refresh(model):
    """Add accent row to refresh-ui so preset loads update the accent toggles."""
    refresh = find_subpatch(model, 'refresh-ui')
    if not refresh:
        print("  [!] Could not find pd refresh-ui")
        return

    # Find the trigger object (t b b b b b b b b = 8 bangs for 8 voices)
    trig = None
    trig_idx = None
    for node in refresh.nodes:
        if isinstance(node, Obj) and node.tokens and node.tokens[0] == 't':
            trig = node
            trig_idx = element_index(refresh, node)
            break

    if not trig:
        return

    # Add one more outlet for accent refresh
    trig.tokens.append('b')
    new_outlet = len(trig.tokens) - 2

    # Add accent refresh block (same pattern as voice refresh)
    # until → f 0 → t f f f → makefilename → tabread → send → +1 → mod 16 → loop
    until_obj = Obj(830, 100, ['until'])
    insert_before_connections(refresh, until_obj)
    until_idx = element_index(refresh, until_obj)

    f_obj = Obj(830, 130, ['f', '0'])
    insert_before_connections(refresh, f_obj)
    f_idx = element_index(refresh, f_obj)

    t_obj = Obj(830, 160, ['t', 'f', 'f', 'f'])
    insert_before_connections(refresh, t_obj)
    t_idx = element_index(refresh, t_obj)

    mkfmt = Obj(960, 190, ['makefilename', '1020-accent-s%d'])
    insert_before_connections(refresh, mkfmt)
    mkfmt_idx = element_index(refresh, mkfmt)

    tabrd = Obj(830, 220, ['tabread', '1020-accent-pat'])
    insert_before_connections(refresh, tabrd)
    tabrd_idx = element_index(refresh, tabrd)

    send_obj = Obj(830, 250, ['send'])
    insert_before_connections(refresh, send_obj)
    send_idx = element_index(refresh, send_obj)

    plus1 = Obj(830, 280, ['+', '1'])
    insert_before_connections(refresh, plus1)
    plus1_idx = element_index(refresh, plus1)

    mod_obj = Obj(830, 310, ['mod', '16'])
    insert_before_connections(refresh, mod_obj)
    mod_idx = element_index(refresh, mod_obj)

    t2_obj = Obj(830, 340, ['t', 'f', 'f'])
    insert_before_connections(refresh, t2_obj)
    t2_idx = element_index(refresh, t2_obj)

    sel0 = Obj(830, 370, ['sel', '0'])
    insert_before_connections(refresh, sel0)
    sel0_idx = element_index(refresh, sel0)

    # Connections within refresh block
    # trig new outlet → until
    refresh.nodes.append(Connection(trig_idx, new_outlet, until_idx, 0))
    # until → f
    refresh.nodes.append(Connection(until_idx, 0, f_idx, 0))
    # f → t f f f
    refresh.nodes.append(Connection(f_idx, 0, t_idx, 0))
    # t outlet 0 → tabread (step index)
    refresh.nodes.append(Connection(t_idx, 0, tabrd_idx, 0))
    # t outlet 1 → +1
    refresh.nodes.append(Connection(t_idx, 1, plus1_idx, 0))
    # t outlet 2 → makefilename
    refresh.nodes.append(Connection(t_idx, 2, mkfmt_idx, 0))
    # makefilename → send (right inlet, sets target)
    refresh.nodes.append(Connection(mkfmt_idx, 0, send_idx, 1))
    # tabread → send (left inlet, value)
    refresh.nodes.append(Connection(tabrd_idx, 0, send_idx, 0))
    # +1 → mod 16
    refresh.nodes.append(Connection(plus1_idx, 0, mod_idx, 0))
    # mod → t f f
    refresh.nodes.append(Connection(mod_idx, 0, t2_idx, 0))
    # t f f outlet 0 → f right inlet (loop counter update)
    refresh.nodes.append(Connection(t2_idx, 0, f_idx, 1))
    # t f f outlet 1 → sel 0
    refresh.nodes.append(Connection(t2_idx, 1, sel0_idx, 0))
    # sel 0 → until (stop when counter wraps to 0)
    refresh.nodes.append(Connection(sel0_idx, 0, until_idx, 1))

    print("  [+] refresh-ui: accent row refresh added")


def main():
    src = os.path.join(os.path.dirname(__file__), '..', 'modules', 'drum-machine.pd')
    with open(src) as f:
        original = f.read()

    model = parse(original)

    add_accent_array(model)
    fix_engine_pattern_length(model)
    add_accent_gain(model)
    add_ui_elements(model)
    update_init(model)
    add_accent_refresh(model)

    result = serialize(model)
    with open(src, 'w') as f:
        f.write(result)

    print(f"\nOriginal: {len(original.strip().splitlines())} lines")
    print(f"Modified: {len(result.strip().splitlines())} lines")


if __name__ == '__main__':
    main()
