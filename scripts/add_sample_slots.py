#!/usr/bin/env python3
"""Add 8-slot sample bank to the existing sample-player.pd.

Conservative approach: modifies the original file in-place using the
puredata-compiler. Keeps the player subpatch, file-loader, and all GUI
completely untouched. Adds:
  1. A hradio slot selector (GUI)
  2. A pd slot-bank subpatch (filename storage + recall)
  3. Minor wiring to connect them

The slot-bank stores filenames in 8 msg boxes (set/bang pattern).
When a file is loaded via the existing Load button, the slot-bank
intercepts the filename (via r $0-filename) and stores it.
When the slot changes, it recalls the stored filename and reloads.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'puredata-compiler'))
from puredata_compiler.parser import parse
from puredata_compiler.serializer import serialize
from puredata_compiler.model import (
    Canvas, Obj, Msg, FloatAtom, SymbolAtom, Comment,
    GuiElement, Connection, RawLine,
)


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


def build_slot_bank():
    """Build the slot-bank subpatch.

    Logic:
    - Intercepts filenames via r $0-filename (sent by existing file-loader)
    - Stores in current slot's msg box via spigots
    - On slot change, recalls stored filename and reloads via its own sfload
    """
    sub = Canvas(x=0, y=0, width=900, height=600, name='slot-bank', open_on_load=0)
    sub.restore_x = 350
    sub.restore_y = 130
    nodes = []
    conns = []
    idx = 0

    # === STORE PATH ===
    # Intercept filename from existing file-loader
    r_fname = idx; idx += 1
    nodes.append(Obj(30, 30, ['r', '$0-filename']))                  # 0

    # Prepend "set" to make a set-message for msg boxes
    prepend = idx; idx += 1
    nodes.append(Obj(30, 60, ['list', 'prepend', 'set']))            # 1
    conns.append(Connection(r_fname, 0, prepend, 0))

    # Current slot number
    r_slot = idx; idx += 1
    nodes.append(Obj(300, 30, ['r', '$0-cur-slot']))                 # 2
    f_slot = idx; idx += 1
    nodes.append(Obj(300, 60, ['f', '0']))                           # 3
    conns.append(Connection(r_slot, 0, f_slot, 1))  # cold store

    # Gate: 8 spigots, each open when slot matches
    # When a filename arrives, it passes through the open spigot
    # to the corresponding msg box (store)
    spigots = []
    eq_objs = []
    msgs = []

    for i in range(8):
        x = 30 + i * 100

        # == comparison: is current slot == i?
        eq = idx; idx += 1
        nodes.append(Obj(x, 120, ['==', str(i)]))
        eq_objs.append(eq)

        # spigot gated by the comparison
        sp = idx; idx += 1
        nodes.append(Obj(x, 150, ['spigot', '0']))
        spigots.append(sp)

        # Connect: eq output → spigot right inlet (gate)
        conns.append(Connection(eq, 0, sp, 1))

        # Connect: prepend output → spigot left inlet (data)
        conns.append(Connection(prepend, 0, sp, 0))

        # msg box: stores filename, outputs on bang
        mg = idx; idx += 1
        nodes.append(Msg(x, 200, 'empty'))
        msgs.append(mg)

        # spigot → msg box (set message stores without output)
        conns.append(Connection(sp, 0, mg, 0))

    # When slot changes, update all gates
    # r $0-cur-slot → f → fan out to all == objects
    t_gate = idx; idx += 1
    nodes.append(Obj(300, 90, ['t'] + ['f'] * 8))
    conns.append(Connection(f_slot, 0, t_gate, 0))  # f outputs on bang (from store path)

    # Also need to update gates on slot change (not just on filename)
    # r $0-cur-slot sends to f_slot cold inlet. But f_slot only outputs when
    # banged (left inlet). We need it to output on slot change too.
    # Solution: r $0-cur-slot → t f b → b bangs f_slot, f stores in cold
    # Actually simpler: just connect r $0-cur-slot to t_gate directly
    # and also to f_slot cold inlet
    # Wait, we need the slot VALUE to reach the == objects. Let me restructure.

    # Better: r $0-cur-slot → t f f
    #   outlet 1 (fires first): → f_slot right inlet (cold store for store path)
    #   outlet 0 (fires second): → all == objects (for gate update + recall)
    t_slot = idx; idx += 1
    nodes.append(Obj(300, 30, ['t', 'f', 'f']))
    # Reconnect: r_slot → t_slot instead of r_slot → f_slot
    # Remove old connection r_slot → f_slot
    conns = [c for c in conns if not (c.src_idx == r_slot and c.dst_idx == f_slot)]
    conns.append(Connection(r_slot, 0, t_slot, 0))
    conns.append(Connection(t_slot, 1, f_slot, 1))   # cold store for store path

    # t_slot outlet 0 → all == objects
    for i in range(8):
        conns.append(Connection(t_slot, 0, eq_objs[i], 0))

    # Remove the t_gate and f_slot → t_gate connection (not needed anymore)
    # Actually, t_gate was for fanning out f_slot to eq's. We replaced that with
    # t_slot outlet 0 → eq's directly. Remove t_gate.
    nodes = [n for j, n in enumerate(nodes) if j != t_gate]
    conns = [c for c in conns if c.src_idx != t_gate and c.dst_idx != t_gate]
    # Fix indices: t_gate was removed, everything after shifts down
    idx -= 1
    # Renumber: t_slot was at t_gate+1, now it's at t_gate
    # This is getting messy. Let me rebuild the indices properly.

    # Actually, this index manipulation is error-prone. Let me just rebuild
    # the whole subpatch cleanly.
    pass

    # ---- CLEAN REBUILD ----
    sub.nodes = []
    nodes = []
    conns = []
    idx = 0

    # -- Slot state --
    r_slot = idx; idx += 1
    nodes.append(Obj(30, 30, ['r', '$0-cur-slot']))                  # 0
    t_slot = idx; idx += 1
    nodes.append(Obj(30, 60, ['t', 'f', 'f']))                      # 1
    f_slot = idx; idx += 1
    nodes.append(Obj(30, 100, ['f', '0']))                           # 2 (stores slot for store path)
    conns.append(Connection(r_slot, 0, t_slot, 0))
    # t_slot outlet 1 (f, fires first): slot → f cold store
    conns.append(Connection(t_slot, 1, f_slot, 1))

    # -- Filename intercept --
    r_fname = idx; idx += 1
    nodes.append(Obj(30, 160, ['r', '$0-filename']))                 # 3
    # "list prepend set symbol" so msg boxes store "symbol /path/..."
    # which outputs as a proper Pd symbol type when banged
    prepend = idx; idx += 1
    nodes.append(Obj(30, 190, ['list', 'prepend', 'set', 'symbol'])) # 4
    conns.append(Connection(r_fname, 0, prepend, 0))

    # When filename arrives, also bang f_slot to recall current slot
    # so spigot gates are set. Use t a b:
    t_fname = idx; idx += 1
    nodes.append(Obj(30, 220, ['t', 'a', 'b']))                     # 5
    conns.append(Connection(prepend, 0, t_fname, 0))
    # t_fname outlet 1 (b, fires first): bang f_slot → updates gates
    conns.append(Connection(t_fname, 1, f_slot, 0))
    # f_slot output → all eq objects (see below)

    # -- Bank: 8 msg boxes with spigot gates --
    eq_objs = []
    spigots = []
    msgs = []

    for i in range(8):
        x = 30 + i * 95

        eq = idx; idx += 1
        nodes.append(Obj(x, 300, ['==', str(i)]))
        eq_objs.append(eq)

        sp = idx; idx += 1
        nodes.append(Obj(x, 330, ['spigot', '0']))
        spigots.append(sp)
        conns.append(Connection(eq, 0, sp, 1))  # gate

        mg = idx; idx += 1
        nodes.append(Msg(x, 370, 'symbol empty'))
        msgs.append(mg)
        conns.append(Connection(sp, 0, mg, 0))  # set msg stores

    # f_slot output → all eq objects (update gates)
    for i in range(8):
        conns.append(Connection(f_slot, 0, eq_objs[i], 0))

    # t_fname outlet 0 (a, fires second): "set filename" → all spigots
    # Only the one with gate=1 passes through
    for i in range(8):
        conns.append(Connection(t_fname, 0, spigots[i], 0))

    # === RECALL PATH ===
    # On slot change, bang the right msg box → filename → sfload
    # t_slot outlet 0 (f, fires second): slot number → sel → bang msg
    sel_recall = idx; idx += 1
    nodes.append(Obj(400, 100, ['sel', '0', '1', '2', '3', '4', '5', '6', '7']))
    conns.append(Connection(t_slot, 0, sel_recall, 0))

    # sel outlets → bang msg boxes
    for i in range(8):
        conns.append(Connection(sel_recall, i, msgs[i], 0))

    # All msg outputs merge → check if empty → if not, reload
    sel_empty = idx; idx += 1
    nodes.append(Obj(30, 430, ['sel', 'empty']))
    for i in range(8):
        conns.append(Connection(msgs[i], 0, sel_empty, 0))

    # Non-empty → load via sfload
    t_load = idx; idx += 1
    nodes.append(Obj(30, 470, ['t', 's', 's']))
    conns.append(Connection(sel_empty, 1, t_load, 0))  # rejection = has filename

    # Display filename
    s_disp = idx; idx += 1
    nodes.append(Obj(30, 510, ['s', '$0-filename']))
    conns.append(Connection(t_load, 1, s_disp, 0))

    # Load via sfload
    msg_load = idx; idx += 1
    nodes.append(Msg(200, 510, 'load \\$1'))
    conns.append(Connection(t_load, 0, msg_load, 0))

    sfload = idx; idx += 1
    nodes.append(Obj(200, 540, ['else/sfload', '$0-sample']))
    conns.append(Connection(msg_load, 0, sfload, 0))

    unpack = idx; idx += 1
    nodes.append(Obj(200, 570, ['unpack', 'f']))
    conns.append(Connection(sfload, 0, unpack, 0))

    s_frames = idx; idx += 1
    nodes.append(Obj(200, 600, ['s', '$0-frames']))
    conns.append(Connection(unpack, 0, s_frames, 0))

    # Empty slot → clear display
    msg_empty = idx; idx += 1
    nodes.append(Msg(200, 430, 'symbol empty'))
    conns.append(Connection(sel_empty, 0, msg_empty, 0))

    s_disp2 = idx; idx += 1
    nodes.append(Obj(200, 460, ['s', '$0-filename']))
    conns.append(Connection(msg_empty, 0, s_disp2, 0))

    sub.nodes = nodes + conns
    return sub


def modify_sample_player():
    src = os.path.join(os.path.dirname(__file__), '..', 'modules', 'sample-player.pd')
    with open(src) as f:
        original = f.read()

    model = parse(original)

    # 1. Add slot-bank subpatch
    bank = build_slot_bank()
    insert_before_connections(model, bank)
    print("  [+] Added pd slot-bank subpatch")

    # 2. Add hradio slot selector to GUI
    # Place above the Load button area
    slot_label = Comment(453, 62, 'Slot')
    # hradio: send=$0-cur-slot, recv=$0-cur-slot-gui (different to avoid loop)
    slot_radio = GuiElement(
        x_pos=490, y_pos=58, gui_type='hradio',
        raw_params=['20', '1', '0', '8', '$0-cur-slot', '$0-cur-slot-gui',
                    'empty', '0', '-8', '0', '10', '#fcfcfc', '#000000', '#000000', '0']
    )
    insert_before_connections(model, slot_label)
    insert_before_connections(model, slot_radio)
    print("  [+] Added slot selector hradio")

    # 3. Add $0-cur-slot init (slot 0) to the init subpatch
    for node in model.nodes:
        if isinstance(node, Canvas) and node.name == 'init':
            init = node
            # Find the trigger object
            for n in init.nodes:
                if isinstance(n, Obj) and n.tokens and n.tokens[0] == 't':
                    trig = n
                    trig_idx = element_index(init, n)
                    break
            # Add one more outlet
            trig.tokens.append('b')
            new_outlet = len(trig.tokens) - 2

            # Add init msg
            init_msg = Msg(380, 160, '\\; $0-cur-slot 0')
            insert_before_connections(init, init_msg)
            msg_idx = element_index(init, init_msg)

            init.nodes.append(Connection(trig_idx, new_outlet, msg_idx, 0))
            print("  [+] Added $0-cur-slot init")
            break

    # 4. Update description
    for node in model.nodes:
        if isinstance(node, Comment) and 'sample-player' in node.raw_text and 'Load any' in node.raw_text:
            node.raw_text = (
                'sample-player — Multi-slot sample player with 8 banks. '
                'Load audio files into numbered slots and switch between them. '
                'Speed \\, pitch \\, loop \\, and level controls. '
                'Use for field recordings \\, vocal snippets \\, spoken legal IDs \\, or found sounds.'
            )
            print("  [+] Updated description")
            break

    result = serialize(model)
    with open(src, 'w') as f:
        f.write(result)

    orig_lines = original.strip().split('\n')
    result_lines = result.strip().split('\n')
    print(f"Original: {len(orig_lines)} lines, Modified: {len(result_lines)} lines")
    print(f"Written to {src}")


if __name__ == '__main__':
    modify_sample_player()
