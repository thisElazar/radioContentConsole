#!/usr/bin/env python3
"""Fix sample-player speed when using loop start/end, and add loop region visual.

Speed bug: phasor frequency is based on total file length, so restricting the
loop region makes playback slower. Fix: divide phasor freq by (lend - lstart).

Visual: add a colored bar below the waveform showing the active loop region.
Uses dynamic cnv pos/size messages.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'puredata-compiler'))
from puredata_compiler.parser import parse
from puredata_compiler.serializer import serialize
from puredata_compiler.model import (
    Canvas, Obj, Msg, FloatAtom, Comment,
    GuiElement, Connection, RawLine,
)


def insert_before_connections(canvas, node):
    for i, n in enumerate(canvas.nodes):
        if isinstance(n, Connection):
            canvas.nodes.insert(i, node)
            return
    canvas.nodes.append(node)


def element_index(canvas, target):
    idx = 0
    for node in canvas.nodes:
        if node is target:
            return idx
        if not isinstance(node, Connection):
            idx += 1
    return None


def fix_player_speed(model):
    """Fix the phasor frequency to account for loop region size."""
    # Find the player subpatch
    player = None
    for node in model.nodes:
        if isinstance(node, Canvas) and node.name == 'player':
            player = node
            break
    if not player:
        print("  [!] Could not find player subpatch")
        return

    # Current objects (by index within player):
    # 12: line~ (speed Hz output)
    # 16: line~ (lstart 0-1)
    # 20: line~ (lend 0-1)
    # 21: phasor~ (receives freq on inlet 0)
    #
    # Current connection: 12→21 (speed line~ → phasor~)
    # Fix: insert correction between 12 and 21
    #   12 → *~ (new) → phasor~
    #   (lend - lstart) → clip → 1/x → *~ right inlet

    # Remove connection 12→21
    player.nodes = [n for n in player.nodes
                    if not (isinstance(n, Connection) and
                            n.src_idx == 12 and n.dst_idx == 21)]

    # Add new objects (after existing objects, before connections)
    # 37: -~ (lend - lstart)
    sub_sig = Obj(700, 160, ['-~'])
    insert_before_connections(player, sub_sig)
    sub_idx = element_index(player, sub_sig)

    # 38: clip~ (prevent divide by zero)
    clip_sig = Obj(700, 190, ['clip~', '0.01', '1'])
    insert_before_connections(player, clip_sig)
    clip_idx = element_index(player, clip_sig)

    # 39: expr~ 1/$v1 (invert)
    inv_sig = Obj(700, 220, ['expr~', '1/$v1'])
    insert_before_connections(player, inv_sig)
    inv_idx = element_index(player, inv_sig)

    # 40: *~ (corrected speed = speed * 1/(lend-lstart))
    mul_sig = Obj(700, 250, ['*~', '1'])
    insert_before_connections(player, mul_sig)
    mul_idx = element_index(player, mul_sig)

    # Add connections
    # lend (20) → -~ left inlet
    player.nodes.append(Connection(20, 0, sub_idx, 0))
    # lstart (16) → -~ right inlet
    player.nodes.append(Connection(16, 0, sub_idx, 1))
    # -~ → clip~
    player.nodes.append(Connection(sub_idx, 0, clip_idx, 0))
    # clip~ → expr~ 1/$v1
    player.nodes.append(Connection(clip_idx, 0, inv_idx, 0))
    # speed line~ (12) → *~ left inlet
    player.nodes.append(Connection(12, 0, mul_idx, 0))
    # expr~ 1/$v1 → *~ right inlet
    player.nodes.append(Connection(inv_idx, 0, mul_idx, 1))
    # *~ → phasor~ (21)
    player.nodes.append(Connection(mul_idx, 0, 21, 0))

    print("  [+] Fixed player speed: phasor freq now compensates for loop region size")


def add_region_visual(model):
    """Add a colored bar below the waveform showing the loop region."""

    # Add background bar (gray, full width, static)
    bg_bar = GuiElement(
        x_pos=20, y_pos=278, gui_type='cnv',
        raw_params=['1', '400', '8', 'empty', 'empty', 'empty',
                    '0', '0', '0', '10', '#808080', '#000000', '0']
    )
    insert_before_connections(model, bg_bar)

    # Add foreground bar (green, dynamically positioned/sized)
    fg_bar = GuiElement(
        x_pos=20, y_pos=278, gui_type='cnv',
        raw_params=['1', '400', '8', 'empty', '$0-region-bar', 'empty',
                    '0', '0', '0', '10', '#00cc44', '#000000', '0']
    )
    insert_before_connections(model, fg_bar)

    # Add pd region-display subpatch that updates the bar
    region_sub = Canvas(x=0, y=0, width=500, height=350, name='region-display', open_on_load=0)
    region_sub.restore_x = 350
    region_sub.restore_y = 155

    nodes = []
    conns = []
    idx = 0

    # Receive lstart and lend
    r_lstart = idx; idx += 1
    nodes.append(Obj(30, 30, ['r', '$0-ctl-lstart']))           # 0
    f_lstart = idx; idx += 1
    nodes.append(Obj(30, 60, ['f', '0']))                       # 1
    conns.append(Connection(r_lstart, 0, f_lstart, 0))

    r_lend = idx; idx += 1
    nodes.append(Obj(200, 30, ['r', '$0-ctl-lend']))            # 2
    f_lend = idx; idx += 1
    nodes.append(Obj(200, 60, ['f', '100']))                    # 3
    conns.append(Connection(r_lend, 0, f_lend, 0))

    # Either change triggers recalc
    s_recalc = idx; idx += 1
    nodes.append(Obj(130, 90, ['s', '$0-region-recalc']))       # 4
    conns.append(Connection(f_lstart, 0, s_recalc, 0))
    conns.append(Connection(f_lend, 0, s_recalc, 0))

    r_recalc = idx; idx += 1
    nodes.append(Obj(30, 130, ['r', '$0-region-recalc']))       # 5

    # On recalc: bang both f objects to recall values
    t_recalc = idx; idx += 1
    nodes.append(Obj(30, 160, ['t', 'b', 'b']))                # 6
    conns.append(Connection(r_recalc, 0, t_recalc, 0))
    # outlet 1 (fires first) → f_lend
    conns.append(Connection(t_recalc, 1, f_lend, 0))
    # outlet 0 (fires second) → f_lstart (triggers computation chain)
    conns.append(Connection(t_recalc, 0, f_lstart, 0))

    # Compute position: pos_x = lstart * 4 + 20
    expr_pos = idx; idx += 1
    nodes.append(Obj(30, 210, ['expr', 'int($f1', '*', '4', '+', '20)']))  # 7
    conns.append(Connection(f_lstart, 0, expr_pos, 0))

    # Compute width: width = max((lend - lstart) * 4, 1)
    expr_width = idx; idx += 1
    nodes.append(Obj(30, 250, ['expr', 'max(($f2', '-', '$f1)', '*', '4', '\\,', '1)']))  # 8
    conns.append(Connection(f_lstart, 0, expr_width, 0))  # hot inlet, triggers
    conns.append(Connection(f_lend, 0, expr_width, 1))    # cold inlet

    # Build pos message: "pos $pos_x 278"
    msg_pos = idx; idx += 1
    nodes.append(Msg(250, 210, 'pos \\$1 278'))              # 9
    conns.append(Connection(expr_pos, 0, msg_pos, 0))

    # Build size message: "size $width 8"
    msg_size = idx; idx += 1
    nodes.append(Msg(250, 250, 'size \\$1 8'))               # 10
    conns.append(Connection(expr_width, 0, msg_size, 0))

    # Send both to the region bar cnv
    s_bar = idx; idx += 1
    nodes.append(Obj(250, 290, ['s', '$0-region-bar']))       # 11
    conns.append(Connection(msg_pos, 0, s_bar, 0))

    s_bar2 = idx; idx += 1
    nodes.append(Obj(380, 290, ['s', '$0-region-bar']))       # 12
    conns.append(Connection(msg_size, 0, s_bar2, 0))

    region_sub.nodes = nodes + conns
    insert_before_connections(model, region_sub)

    print("  [+] Added loop region visual bar below waveform")


def main():
    src = os.path.join(os.path.dirname(__file__), '..', 'modules', 'sample-player.pd')
    with open(src) as f:
        original = f.read()

    model = parse(original)

    fix_player_speed(model)
    add_region_visual(model)

    result = serialize(model)
    with open(src, 'w') as f:
        f.write(result)

    orig_lines = original.strip().split('\n')
    result_lines = result.strip().split('\n')
    print(f"Original: {len(orig_lines)} lines, Modified: {len(result_lines)} lines")


if __name__ == '__main__':
    main()
