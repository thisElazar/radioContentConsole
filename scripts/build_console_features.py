#!/usr/bin/env python3
"""Apply three features to console.pd using the puredata-compiler:
1. Universal master clock
2. Peak/clip visuals
3. Solo buttons

Uses the puredata-compiler for safe parsing and serialization.
All modifications are done on the parsed model, then serialized back.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'puredata-compiler'))
from puredata_compiler.parser import parse
from puredata_compiler.serializer import serialize
from puredata_compiler.model import (
    Canvas, Obj, Msg, FloatAtom, SymbolAtom, Comment,
    GuiElement, Connection, RawLine,
)


def find_subpatch(canvas, name):
    """Find a subpatch by name in a canvas."""
    for i, node in enumerate(canvas.nodes):
        if isinstance(node, Canvas) and node.name == name:
            return i, node
    return None, None


def element_index(canvas, target):
    """Get the element index of a node (counting only non-Connection nodes)."""
    idx = 0
    for node in canvas.nodes:
        if node is target:
            return idx
        if not isinstance(node, Connection):
            idx += 1
    return None


def insert_before_connections(canvas, node):
    """Insert a node just before the first connection in the canvas."""
    for i, n in enumerate(canvas.nodes):
        if isinstance(n, Connection):
            canvas.nodes.insert(i, node)
            return
    canvas.nodes.append(node)


def add_connection(canvas, src, src_out, dst, dst_in):
    """Add a connection to the end of a canvas."""
    canvas.nodes.append(Connection(src, src_out, dst, dst_in))


# ===========================================================================
# FEATURE 1: Universal Master Clock
# ===========================================================================

def apply_master_clock(root):
    """Add tk-master-bpm control forwarding to sequencer and drum machine."""

    # 1. Change the Tempo floatatom from display-only to bidirectional
    #    Original: floatatom 260 475 5 0 0 0 - tk-seq-tempo - 0
    #    New:      floatatom 260 475 5 40 300 0 - tk-master-bpm tk-master-bpm-gui 0
    #    IMPORTANT: send and receive MUST differ or Pd creates an infinite loop.
    #    send=tk-master-bpm (user edits → system), recv=tk-master-bpm-gui (system → display)
    for node in root.nodes:
        if isinstance(node, FloatAtom) and node.x_pos == 260 and node.y_pos == 475:
            node.raw_params = ['5', '40', '300', '0', '-', 'tk-master-bpm', 'tk-master-bpm-gui', '0']
            break

    # 2. Change "Tempo:" label to "BPM:"
    for node in root.nodes:
        if isinstance(node, Comment) and node.raw_text == 'Tempo:':
            node.raw_text = 'BPM:'
            break

    # 3. Add pd master-clock subpatch
    #    Receives tk-master-bpm, forwards to sequencer + drum machine + display
    clock_sub = Canvas(x=0, y=0, width=450, height=250, name='master-clock', open_on_load=0)
    clock_sub.restore_x = 900
    clock_sub.restore_y = 960
    clock_sub.nodes = [
        Obj(30, 30, ['r', 'tk-master-bpm']),           # 0
        Obj(30, 60, ['t', 'f', 'f', 'f']),             # 1
        Obj(30, 100, ['s', '1010-bpm-a']),              # 2: sequencer
        Obj(200, 100, ['s', '1020-bpm']),               # 3: drum machine
        Obj(370, 100, ['s', 'tk-master-bpm-gui']),      # 4: display feedback
        Connection(0, 0, 1, 0),
        Connection(1, 0, 2, 0),   # outlet 0 → sequencer
        Connection(1, 1, 3, 0),   # outlet 1 → drums
        Connection(1, 2, 4, 0),   # outlet 2 → display
    ]
    insert_before_connections(root, clock_sub)

    # 4. Update init subpatch to include tk-master-bpm 120
    _, init_sub = find_subpatch(root, 'init')
    if init_sub:
        # (master-bpm gets its own separate msg object below)

        # Add a new msg for master bpm, connected from the loadbang trigger
        # Find the trigger object (t b b b b ...)
        trig = None
        trig_idx = None
        for node in init_sub.nodes:
            if isinstance(node, Obj) and node.tokens and node.tokens[0] == 't':
                trig = node
                trig_idx = element_index(init_sub, node)
                break

        if trig:
            # Add one more outlet to the trigger
            trig.tokens.append('b')
            new_outlet = len(trig.tokens) - 2  # last outlet index = num_b's - 1 = len - 2

            # Add the new msg
            bpm_msg = Msg(250, 340, '\\; tk-master-bpm 120')
            # Insert before connections
            insert_before_connections(init_sub, bpm_msg)
            bpm_idx = element_index(init_sub, bpm_msg)

            # Connect trigger's new outlet to the bpm msg
            add_connection(init_sub, trig_idx, new_outlet, bpm_idx, 0)

    print("  [+] Master clock: tk-master-bpm floatatom, pd master-clock, init")


# ===========================================================================
# FEATURE 2: Peak/Clip Visuals
# ===========================================================================

def apply_peak_clip(root):
    """Add pre-clip peak detection and wire up LIMIT indicator."""

    # 1. Modify the master subpatch
    _, master = find_subpatch(root, 'master')
    if not master:
        print("  [!] Could not find master subpatch")
        return

    # Current master objects (0-indexed within master):
    # 0: inlet~ L
    # 1: inlet~ R
    # 2: r tk-master-level-a
    # 3: expr pow(10, $f1/20)
    # 4: pack f 30
    # 5: line~
    # 6: *~ L (pre-clip, gain applied)
    # 7: *~ R
    # 8: clip~ L (-0.944 0.944)
    # 9: clip~ R
    # 10: outlet~ L
    # 11: outlet~ R
    # 12: env~ L (post-clip)
    # 13: env~ R (post-clip)
    # 14: - 100 L
    # 15: - 100 R
    # 16: s tk-vu-L
    # 17: s tk-vu-R
    #
    # Existing connections from 6: 6→8 (clip L), so obj 6 output is pre-clip L

    # Add pre-clip peak detection on L channel (tapped from obj 6 output)
    new_nodes = [
        # Pre-clip envelope (fast, for peak detection)
        Obj(30, 290, ['env~', '1024']),           # 18: pre-clip L envelope
        Obj(30, 320, ['-', '100']),                # 19: to dBFS

        # Peak hold: t f b → f -100 → expr max → t f f → s tk-peak
        Obj(30, 350, ['t', 'f', 'b']),             # 20
        Obj(130, 350, ['f', '-100']),               # 21: stored peak
        Obj(30, 390, ['expr', 'max($f1', '\\,', '$f2)']),  # 22: max(current, stored)
        Obj(30, 430, ['t', 'f', 'f']),             # 23
        Obj(30, 470, ['s', 'tk-peak']),             # 24: to console display
        # feedback: 23 outlet 1 → 21 right inlet

        # Clip detection
        Obj(250, 350, ['>', '-1']),                 # 25: threshold
        Obj(250, 380, ['sel', '1']),                # 26: fire on clip
        Obj(250, 410, ['1']),                       # 27: output 1
        Obj(250, 440, ['s', 'tk-limit-indicator']), # 28

        # Peak reset
        Obj(400, 350, ['r', 'tk-peak-reset']),      # 29
        Obj(400, 380, ['t', 'b', 'b']),             # 30
        Obj(400, 410, ['-100']),                     # 31: reset peak
        Obj(500, 410, ['0']),                        # 32: reset clip
        Obj(500, 440, ['s', 'tk-limit-indicator']), # 33
    ]

    # Insert new nodes before connections
    for n in new_nodes:
        insert_before_connections(master, n)

    # Add connections for peak/clip
    new_conns = [
        # Tap pre-clip L signal (obj 6 → env~)
        Connection(6, 0, 18, 0),
        # env~ → - 100
        Connection(18, 0, 19, 0),
        # - 100 → t f b
        Connection(19, 0, 20, 0),
        # t f b: outlet 1 (bang, fires first) → f -100 (recall stored peak)
        Connection(20, 1, 21, 0),
        # f -100 → expr right inlet (cold, stored peak)
        Connection(21, 0, 22, 1),
        # t f b: outlet 0 (float, fires second) → expr left inlet (hot, current)
        Connection(20, 0, 22, 0),
        # expr → t f f
        Connection(22, 0, 23, 0),
        # t f f: outlet 0 → s tk-peak (display)
        Connection(23, 0, 24, 0),
        # t f f: outlet 1 → f -100 right inlet (feedback, update stored peak)
        Connection(23, 1, 21, 1),

        # Clip detection: - 100 → > -1
        Connection(19, 0, 25, 0),
        # > -1 → sel 1
        Connection(25, 0, 26, 0),
        # sel 1 → 1
        Connection(26, 0, 27, 0),
        # 1 → s tk-limit-indicator
        Connection(27, 0, 28, 0),

        # Peak reset
        Connection(29, 0, 30, 0),
        # t b b: outlet 1 (fires first) → -100 → f right inlet (reset peak)
        Connection(30, 1, 31, 0),
        Connection(31, 0, 21, 1),
        # t b b: outlet 0 (fires second) → 0 → s tk-limit-indicator (reset clip)
        Connection(30, 0, 32, 0),
        Connection(32, 0, 33, 0),
    ]
    for c in new_conns:
        master.nodes.append(c)

    # 2. Add console surface elements for peak display
    # Place near VU meters (around x=394, y=588)
    peak_nodes = [
        Comment(305, 630, 'Peak:'),
        FloatAtom(350, 630, ['5', '-100', '0', '0', '-', '-', 'tk-peak', '0']),
        Comment(400, 630, 'dB'),
        GuiElement(x_pos=305, y_pos=650, gui_type='bng',
                   raw_params=['15', '250', '50', '0', 'tk-peak-reset', 'empty',
                               'Reset', '18', '7', '0', '10', '#fcfcfc', '#000000', '#000000']),
    ]
    for n in peak_nodes:
        insert_before_connections(root, n)

    print("  [+] Peak/clip: master env~, peak hold, LIMIT wiring, console display")


# ===========================================================================
# FEATURE 3: Solo Buttons
# ===========================================================================

CHANNELS = ['source1', 'source2', 'source3', 'source4', 'source5', 'source6', 'drums']

def apply_solo(root):
    """Add per-channel solo with solo-logic subpatch."""

    # 1. Rename mixer on-state receivers from tk-sourceN-on to tk-sourceN-effective-on
    _, mixer = find_subpatch(root, 'mixer')
    if not mixer:
        print("  [!] Could not find mixer subpatch")
        return

    for node in mixer.nodes:
        if isinstance(node, Obj) and node.tokens:
            if len(node.tokens) == 2 and node.tokens[0] == 'r':
                name = node.tokens[1]
                for ch in CHANNELS:
                    if name == f'tk-{ch}-on':
                        node.tokens[1] = f'tk-{ch}-effective-on'
                        break

    # 2. Build solo-logic subpatch
    solo_sub = Canvas(x=0, y=0, width=1100, height=800, name='solo-logic', open_on_load=0)
    solo_sub.restore_x = 900
    solo_sub.restore_y = 915
    nodes = []
    conns = []
    idx = 0

    # For each channel: receive on-state and solo-state, store both
    # Layout: each channel gets a column
    on_f_indices = {}
    solo_f_indices = {}
    effective_s_indices = {}

    for ci, ch in enumerate(CHANNELS):
        x = 30 + ci * 150
        # r tk-{ch}-on
        r_on = idx; idx += 1
        nodes.append(Obj(x, 30, ['r', f'tk-{ch}-on']))
        # f (store on state)
        f_on = idx; idx += 1
        nodes.append(Obj(x, 60, ['f', '0']))
        on_f_indices[ch] = f_on
        conns.append(Connection(r_on, 0, f_on, 0))

        # r tk-{ch}-solo
        r_solo = idx; idx += 1
        nodes.append(Obj(x, 100, ['r', f'tk-{ch}-solo']))
        # f (store solo state)
        f_solo = idx; idx += 1
        nodes.append(Obj(x, 130, ['f', '0']))
        solo_f_indices[ch] = f_solo
        conns.append(Connection(r_solo, 0, f_solo, 0))

    # Recalc trigger: any on or solo change should trigger recalculation
    # Use a single bang receiver that all changes feed into
    # Add s/r pair: s tk-solo-recalc / r tk-solo-recalc
    # Each on/solo change sends a bang to tk-solo-recalc

    # Add senders from each on/solo receiver
    for ci, ch in enumerate(CHANNELS):
        x = 30 + ci * 150
        # After f_on: t f b → s tk-solo-recalc
        t_on = idx; idx += 1
        nodes.append(Obj(x, 190, ['t', 'f', 'b']))
        # reconnect: r_on → t_on instead of f_on
        # Actually, r_on already connects to f_on. Let me chain differently:
        # r_on → f_on (store), then f_on → t f b → outlet 0 updates f, outlet 1 sends recalc
        # No, simpler: r_on → t f b. outlet 1 (b) → recalc. outlet 0 (f) → f_on (store)
        # But we already connected r_on → f_on. Let me use f_on output instead.
        # f_on outputs the stored value. Then t f b splits it.
        # Wait — f stores on LEFT inlet (hot) and outputs. So r_on → f_on stores AND outputs.
        # Then f_on → t f b works.
        conns.append(Connection(on_f_indices[ch], 0, t_on, 0))

        s_recalc_on = idx; idx += 1
        nodes.append(Obj(x + 50, 220, ['s', 'tk-solo-recalc']))
        conns.append(Connection(t_on, 1, s_recalc_on, 0))  # bang → recalc

        # Same for solo
        t_solo = idx; idx += 1
        nodes.append(Obj(x, 260, ['t', 'f', 'b']))
        conns.append(Connection(solo_f_indices[ch], 0, t_solo, 0))

        s_recalc_solo = idx; idx += 1
        nodes.append(Obj(x + 50, 290, ['s', 'tk-solo-recalc']))
        conns.append(Connection(t_solo, 1, s_recalc_solo, 0))  # bang → recalc

    # Recalc receiver
    r_recalc = idx; idx += 1
    nodes.append(Obj(30, 380, ['r', 'tk-solo-recalc']))

    # On recalc: bang all f objects to recall values, compute solo_count, compute effective-on
    # Bang each solo f to recall → sum all solo values
    recalc_t = idx; idx += 1
    # Need enough outlets to bang all solo f's and on f's
    # 7 solos + 7 ons = 14 bangs
    t_tokens = ['t'] + ['b'] * 14
    nodes.append(Obj(30, 410, t_tokens))
    conns.append(Connection(r_recalc, 0, recalc_t, 0))

    # Bang each solo f (outlets 0-6)
    for ci, ch in enumerate(CHANNELS):
        conns.append(Connection(recalc_t, ci, solo_f_indices[ch], 0))

    # Bang each on f (outlets 7-13)
    for ci, ch in enumerate(CHANNELS):
        conns.append(Connection(recalc_t, 7 + ci, on_f_indices[ch], 0))

    # Wait — there's a timing issue. The t object fires right-to-left (outlet 13 first, 0 last).
    # We need solo values to be ready before computing. Let me use a different approach.
    #
    # Simpler: use a delay 0 to sequence properly.
    # On recalc bang:
    # 1. Bang all solo f's → they output and their values flow into the sum
    # 2. After sum is computed, use it with each channel's on state
    #
    # Actually, let me restructure. Instead of trying to synchronize everything with one trigger,
    # compute per-channel using expr that READS current states.
    # Use: r tk-solo-recalc → bang → for each channel:
    #   recall solo state from f → into sum
    #   use sum + per-channel solo + per-channel on → expr → effective-on

    # This is getting complex. Let me use a simpler pattern:
    # Each channel has its own computation block that fires on recalc.

    # Delete the complex t object approach and redo:
    # Remove the t and reconnect
    nodes.pop()  # remove the t
    idx -= 1
    # Remove the recalc_t connections
    conns = [c for c in conns if c.src_idx != recalc_t]

    # Instead: use a sum computation for solo count
    # r tk-solo-recalc → delay 0 → bang all solo f's
    delay_obj = idx; idx += 1
    nodes.append(Obj(30, 410, ['delay', '0']))
    conns.append(Connection(r_recalc, 0, delay_obj, 0))

    # t b b b b b b b (7 bangs for 7 solo f's)
    t_solo_bang = idx; idx += 1
    nodes.append(Obj(30, 440, ['t'] + ['b'] * 7))
    conns.append(Connection(delay_obj, 0, t_solo_bang, 0))

    # Bang each solo f (right-to-left: outlet 6 first, 0 last)
    for ci, ch in enumerate(CHANNELS):
        conns.append(Connection(t_solo_bang, ci, solo_f_indices[ch], 0))

    # Solo f outputs feed into a sum chain: + + + + + + → solo_count
    # We need to sum all 7 solo values
    # Create a chain of + objects
    # solo0 → into first +, solo1 → second input of first +, etc.
    # Actually easier: use a sum pattern
    # solo0 + solo1 → + → + solo2 → + → ...

    # Let's collect solo f outputs into a pack then sum
    # Simpler: cascading + objects
    # But timing of the bangs matters. Let me use a different pattern.

    # Most reliable Pd sum pattern for 7 values arriving in sequence:
    # Each solo f output → f (capture) → add chain
    # Actually this is all getting too complex for a generated subpatch.
    # Let me use the SIMPLEST possible approach:

    # For each channel independently compute:
    # effective_on = if(any_solo && !my_solo, 0, my_on)
    #
    # Where any_solo is computed from ALL solo states.
    # I'll compute any_solo as a single value and send it.
    #
    # APPROACH: Every time any solo or on state changes:
    # 1. Each channel's solo f/on f stores the new value
    # 2. A recalc bang fires
    # 3. On recalc: send all 7 solo states to a sum
    # 4. Sum → if > 0, solo_active = 1, else 0
    # 5. For each channel: expr if($f1 > 0 && $f2 == 0, 0, $f3)
    #    where $f1=solo_active, $f2=my_solo, $f3=my_on
    # 6. Result → s tk-{ch}-effective-on

    # Let me restart the recalc section cleanly.
    # I'll use global sends for solo_active to avoid complex wiring.

    # Step 1: On recalc, read all solo states and sum them
    # Using a message approach: bang → read all solo f's sequentially

    # Actually, the absolute simplest Pd pattern for this:
    # Each solo change: sends its value AND triggers a full recount
    # The recount: bangs all 7 solo f's, they feed into a cascading + chain,
    # the result sets tk-solo-active, then per-channel computation runs.

    # Let me use a completely different (simpler) strategy:
    # No f objects, no recalc. Just use expr with receives directly.
    #
    # For each channel:
    # r tk-{ch}-on
    # r tk-{ch}-solo
    # r tk-solo-count
    # expr if($f3 > 0 && $f2 == 0, 0, $f1)
    # s tk-{ch}-effective-on
    #
    # And a separate block that sums all solos → tk-solo-count
    #
    # Problem: when do the exprs fire? They need to fire whenever any input changes.
    # In Pd, expr fires when its LEFT inlet receives. So only tk-{ch}-on triggers it.
    # The other inlets are cold.
    #
    # Solution: have the recalc bang all on f's after computing solo count.

    # OK let me just build it cleanly. Reset the solo subpatch approach:

    nodes.clear()
    conns.clear()
    idx = 0

    # -- Per-channel storage --
    # Three f objects per channel to prevent feedback loops:
    #   on_f[ch]       — stores on state, used by per-channel computation
    #   solo_f[ch]     — stores solo state, used ONLY by per-channel computation
    #   solo_sum_f[ch] — stores solo state, used ONLY by sum computation
    #
    # Both solo f's are updated when r tk-{ch}-solo fires (via cold inlets).
    # This ensures the sum and per-channel paths never share f objects,
    # eliminating the feedback loop where banging solo_f for per-channel
    # computation would retrigger the sum via its hot inlet.
    on_f = {}
    solo_f = {}      # per-channel computation only
    solo_sum_f = {}  # sum computation only

    for ci, ch in enumerate(CHANNELS):
        x = 30 + ci * 130

        # On state: r → t b f → f cold store + s recalc
        r_on = idx; idx += 1
        nodes.append(Obj(x, 30, ['r', f'tk-{ch}-on']))
        t_on = idx; idx += 1
        nodes.append(Obj(x, 55, ['t', 'b', 'f']))
        f_on_idx = idx; idx += 1
        nodes.append(Obj(x, 80, ['f', '0']))
        on_f[ch] = f_on_idx
        s_rc = idx; idx += 1
        nodes.append(Obj(x, 110, ['s', 'tk-solo-recalc']))
        conns.append(Connection(r_on, 0, t_on, 0))
        conns.append(Connection(t_on, 1, f_on_idx, 1))   # f value → cold store
        conns.append(Connection(t_on, 0, s_rc, 0))        # bang → recalc

        # Solo state: r → t b f f → TWO f's cold store + s recalc
        r_solo = idx; idx += 1
        nodes.append(Obj(x, 140, ['r', f'tk-{ch}-solo']))
        t_solo = idx; idx += 1
        nodes.append(Obj(x, 165, ['t', 'b', 'f', 'f']))  # 0=b, 1=f, 2=f
        # solo_f for per-channel
        f_solo_ch = idx; idx += 1
        nodes.append(Obj(x, 195, ['f', '0']))
        solo_f[ch] = f_solo_ch
        # solo_sum_f for sum
        f_solo_sum = idx; idx += 1
        nodes.append(Obj(x + 60, 195, ['f', '0']))
        solo_sum_f[ch] = f_solo_sum
        s_rc2 = idx; idx += 1
        nodes.append(Obj(x, 225, ['s', 'tk-solo-recalc']))
        conns.append(Connection(r_solo, 0, t_solo, 0))
        # t outlet 2 (f, fires first) → solo_sum_f cold store
        conns.append(Connection(t_solo, 2, f_solo_sum, 1))
        # t outlet 1 (f, fires second) → solo_f cold store
        conns.append(Connection(t_solo, 1, f_solo_ch, 1))
        # t outlet 0 (b, fires last) → s recalc
        conns.append(Connection(t_solo, 0, s_rc2, 0))

    # -- Recalc chain --
    r_recalc_idx = idx; idx += 1
    nodes.append(Obj(30, 280, ['r', 'tk-solo-recalc']))
    delay_idx = idx; idx += 1
    nodes.append(Obj(30, 310, ['delay', '0']))
    conns.append(Connection(r_recalc_idx, 0, delay_idx, 0))

    # Phase 1: Bang solo_sum_f's → sum expr → solo_count
    t_sum_bang = idx; idx += 1
    nodes.append(Obj(30, 340, ['t'] + ['b'] * 7))
    conns.append(Connection(delay_idx, 0, t_sum_bang, 0))

    # Sum: expr $f1+...+$f7 with solo_sum_f outputs
    # R→L firing: outlet 6 (drums) fires first → inlet 6 (cold)
    #             outlet 0 (source1) fires last → inlet 0 (hot, triggers)
    sum_expr_idx = idx; idx += 1
    nodes.append(Obj(30, 420, ['expr', '$f1+$f2+$f3+$f4+$f5+$f6+$f7']))

    ch_order = list(CHANNELS)
    # Bang solo_sum_f's: outlet 6 fires first (R→L), outlet 0 fires last.
    # source1 is on inlet 0 (hot, triggers sum), so it MUST fire LAST.
    # Use ci directly: outlet 0→source1 (last), outlet 6→drums (first).
    for ci, ch in enumerate(ch_order):
        conns.append(Connection(t_sum_bang, ci, solo_sum_f[ch], 0))
    # solo_sum_f outputs → sum expr inlets (source1=inlet 0 hot, rest=cold)
    for ci, ch in enumerate(ch_order):
        conns.append(Connection(solo_sum_f[ch], 0, sum_expr_idx, ci))

    # Phase 2: Distribute solo_count → per-channel computation
    t_dist_idx = idx; idx += 1
    nodes.append(Obj(30, 460, ['t'] + ['f'] * 7))
    conns.append(Connection(sum_expr_idx, 0, t_dist_idx, 0))

    # Per-channel: t_dist → ch_t (t b b f) → bang solo_f + on_f → expr → effective-on
    for ci, ch in enumerate(ch_order):
        x = 30 + ci * 130
        ch_t_idx = idx; idx += 1
        nodes.append(Obj(x, 520, ['t', 'b', 'b', 'f']))
        # t_dist outlets 0-6 (R→L firing, all independent)
        conns.append(Connection(t_dist_idx, ci, ch_t_idx, 0))

        ch_expr_idx = idx; idx += 1
        nodes.append(Obj(x, 600,
            ['expr', 'if($f3', '>', '0', '&&', '$f2', '==', '0', '\\,', '0', '\\,', '$f1)']))
        ch_s_idx = idx; idx += 1
        nodes.append(Obj(x, 640, ['s', f'tk-{ch}-effective-on']))

        # ch_t R→L: outlet 2(f)=solo_count first, outlet 1(b) second, outlet 0(b) last
        conns.append(Connection(ch_t_idx, 2, ch_expr_idx, 2))     # solo_count → cold
        conns.append(Connection(ch_t_idx, 1, solo_f[ch], 0))      # bang solo_f (NOT solo_sum_f!)
        conns.append(Connection(solo_f[ch], 0, ch_expr_idx, 1))   # my_solo → cold
        conns.append(Connection(ch_t_idx, 0, on_f[ch], 0))        # bang on_f
        conns.append(Connection(on_f[ch], 0, ch_expr_idx, 0))     # my_on → hot (triggers)
        conns.append(Connection(ch_expr_idx, 0, ch_s_idx, 0))     # → s effective-on

    solo_sub.nodes = nodes + conns
    insert_before_connections(root, solo_sub)

    # 3. Add solo toggles to console surface
    # Source panels: x offsets for each source (25, 261, 497, 733, 969, 1205)
    source_x = [25, 261, 497, 733, 969, 1205]
    for i in range(6):
        x = source_x[i] + 45  # offset from panel left edge
        # Solo toggle: yellow (#fccc00) indicator
        solo_tgl = GuiElement(
            x_pos=x, y_pos=150,
            gui_type='tgl',
            raw_params=['15', '0', f'tk-source{i+1}-solo', f'tk-source{i+1}-solo',
                        'Solo', '18', '7', '0', '10', '#fcfcfc', '#fccc00', '#000000', '0', '1']
        )
        insert_before_connections(root, solo_tgl)

    # Drums solo toggle (in drums section)
    drums_solo = GuiElement(
        x_pos=930, y_pos=560,
        gui_type='tgl',
        raw_params=['15', '0', 'tk-drums-solo', 'tk-drums-solo',
                    'Solo', '18', '7', '0', '10', '#fcfcfc', '#fccc00', '#000000', '0', '1']
    )
    insert_before_connections(root, drums_solo)

    # 4. Update init subpatch
    _, init_sub = find_subpatch(root, 'init')
    if init_sub:
        # Find the trigger and add another outlet for solo init
        for node in init_sub.nodes:
            if isinstance(node, Obj) and node.tokens and node.tokens[0] == 't':
                trig = node
                trig_idx_init = element_index(init_sub, node)
                break

        trig.tokens.append('b')

        solo_init_msg = Msg(250, 380,
            '\\; tk-source1-solo 0 \\; tk-source2-solo 0 '
            '\\; tk-source3-solo 0 \\; tk-source4-solo 0 '
            '\\; tk-source5-solo 0 \\; tk-source6-solo 0 '
            '\\; tk-drums-solo 0')
        insert_before_connections(init_sub, solo_init_msg)
        solo_init_idx = element_index(init_sub, solo_init_msg)
        new_outlet = len(trig.tokens) - 2
        add_connection(init_sub, trig_idx_init, new_outlet, solo_init_idx, 0)

    # 5. Update preset save/load to include solo states
    # (Skip for now — presets are a nice-to-have, the core feature works without them)

    print("  [+] Solo: solo-logic subpatch, mixer rewiring, 7 solo toggles, init")


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    console_path = os.path.join(os.path.dirname(__file__), '..', 'console.pd')

    print(f"Reading {console_path}...")
    with open(console_path) as f:
        original = f.read()

    model = parse(original)

    print("Applying features...")
    apply_master_clock(model)
    apply_peak_clip(model)
    apply_solo(model)

    result = serialize(model)

    # Backup original
    backup_path = console_path + '.bak'
    with open(backup_path, 'w') as f:
        f.write(original)
    print(f"Backup saved to {backup_path}")

    with open(console_path, 'w') as f:
        f.write(result)

    orig_lines = original.strip().split('\n')
    result_lines = result.strip().split('\n')
    print(f"Original: {len(orig_lines)} lines")
    print(f"Modified: {len(result_lines)} lines")
    print(f"Written to {console_path}")


if __name__ == '__main__':
    main()
