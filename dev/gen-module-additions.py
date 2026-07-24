#!/usr/bin/env python3
"""Generate Pd subpatch code for preset save/load and automation panel.

Usage: python3 gen-module-additions.py MODULE_NAME PARAM1:MIN:MAX PARAM2:MIN:MAX ...

Params marked with :noauto suffix skip automation (e.g. bypass:0:1:noauto, mode:0:2:noauto)

Example:
  python3 gen-module-additions.py chorus rate:0.1:3 depth:0:100 delay:5:30 fb:0:40 width:0:100 mix:0:100 bypass:0:1:noauto
"""

import sys

def gen_preset_save(module_name, params):
    """Generate preset-save subpatch content."""
    lines = []
    lines.append(f"#N canvas 0 0 700 600 preset-save 0;")

    # Latch objects: r + f for each param
    obj_idx = 0
    latch_indices = {}  # param_name -> f_object_index
    for i, (name, _, _, _) in enumerate(params):
        x = (i % 3) * 170 + 30
        y = (i // 3) * 90 + 30
        lines.append(f"#X obj {x} {y} r \\$0-ctl-{name};")
        obj_idx += 1
        lines.append(f"#X obj {x} {y+30} f;")
        latch_indices[name] = obj_idx
        obj_idx += 1

    # Control objects
    inlet_idx = obj_idx
    lines.append(f"#X obj 30 {(len(params)//3 + 1) * 90 + 30} inlet;")
    obj_idx += 1

    savepanel_idx = obj_idx
    lines.append(f"#X obj 30 {(len(params)//3 + 1) * 90 + 60} savepanel;")
    obj_idx += 1

    tsb_idx = obj_idx
    lines.append(f"#X obj 30 {(len(params)//3 + 1) * 90 + 90} t s b;")
    obj_idx += 1

    textfile_idx = obj_idx
    lines.append(f"#X obj 30 {(len(params)//3 + 1) * 90 + 130} textfile;")
    obj_idx += 1

    # Trigger for chain: clear + N params
    n_outlets = len(params) + 1  # +1 for clear
    trigger_spec = " ".join(["b"] * n_outlets)
    trigger_idx = obj_idx
    lines.append(f"#X obj 30 {(len(params)//3 + 1) * 90 + 170} t {trigger_spec};")
    obj_idx += 1

    # Clear message
    clear_idx = obj_idx
    lines.append(f"#X msg 30 {(len(params)//3 + 1) * 90 + 210} clear;")
    obj_idx += 1

    # Add param messages
    msg_indices = {}
    for i, (name, _, _, _) in enumerate(params):
        x = (i + 1) * 90 + 30
        msg_idx = obj_idx
        lines.append(f"#X msg {x} {(len(params)//3 + 1) * 90 + 210} add param {name} \\$1;")
        msg_indices[name] = msg_idx
        obj_idx += 1

    # Write message
    write_idx = obj_idx
    lines.append(f"#X msg 200 {(len(params)//3 + 1) * 90 + 120} write \\$1;")
    obj_idx += 1

    # Connections
    # Latch receivers → f right inlet
    for i, (name, _, _, _) in enumerate(params):
        r_idx = i * 2
        f_idx = i * 2 + 1
        lines.append(f"#X connect {r_idx} 0 {f_idx} 1;")

    # Inlet → savepanel → t s b
    lines.append(f"#X connect {inlet_idx} 0 {savepanel_idx} 0;")
    lines.append(f"#X connect {savepanel_idx} 0 {tsb_idx} 0;")

    # t s b: outlet 1 (b, right, first) → trigger chain
    lines.append(f"#X connect {tsb_idx} 1 {trigger_idx} 0;")
    # t s b: outlet 0 (s, left, second) → write msg → textfile
    lines.append(f"#X connect {tsb_idx} 0 {write_idx} 0;")
    lines.append(f"#X connect {write_idx} 0 {textfile_idx} 0;")

    # Trigger chain: rightmost outlet = clear, then params left to right
    max_outlet = n_outlets - 1
    lines.append(f"#X connect {trigger_idx} {max_outlet} {clear_idx} 0;")
    lines.append(f"#X connect {clear_idx} 0 {textfile_idx} 0;")

    for i, (name, _, _, _) in enumerate(params):
        outlet = max_outlet - 1 - i
        f_idx = latch_indices[name]
        msg_idx = msg_indices[name]
        lines.append(f"#X connect {trigger_idx} {outlet} {f_idx} 0;")
        lines.append(f"#X connect {f_idx} 0 {msg_idx} 0;")
        lines.append(f"#X connect {msg_idx} 0 {textfile_idx} 0;")

    lines.append(f"#X restore 540 490 pd preset-save;")
    return "\n".join(lines)


def gen_preset_load(module_name, params):
    """Generate preset-load subpatch content."""
    lines = []
    lines.append(f"#N canvas 0 0 700 500 preset-load 0;")

    # 0: inlet
    lines.append("#X obj 30 30 inlet;")
    # 1: openpanel
    lines.append("#X obj 30 60 openpanel;")
    # 2: t b s b
    lines.append("#X obj 30 100 t b s b;")
    # 3: textfile
    lines.append("#X obj 30 140 textfile;")
    # 4: msg clear
    lines.append("#X msg 30 180 clear;")
    # 5: msg read
    lines.append("#X msg 200 140 read \\$1 cr;")
    # 6: route param
    lines.append("#X obj 30 220 route param;")

    # 7: route param_names
    param_names = " ".join(p[0] for p in params)
    lines.append(f"#X obj 30 260 route {param_names};")

    # 8+: sends for each param
    send_start = 8
    for i, (name, _, _, _) in enumerate(params):
        x = i * 90 + 30
        lines.append(f"#X obj {x} 310 s \\$0-ctl-{name};")

    # delay 0 for iteration
    delay_idx = send_start + len(params)
    lines.append(f"#X obj 300 220 delay 0;")

    # Connections
    lines.append("#X connect 0 0 1 0;")   # inlet → openpanel
    lines.append("#X connect 1 0 2 0;")   # openpanel → t b s b
    lines.append("#X connect 2 2 4 0;")   # t outlet 2 (b, first) → clear
    lines.append("#X connect 4 0 3 0;")   # clear → textfile
    lines.append("#X connect 2 1 5 0;")   # t outlet 1 (s, second) → read msg
    lines.append("#X connect 5 0 3 0;")   # read → textfile
    lines.append("#X connect 2 0 3 0;")   # t outlet 0 (b, last) → bang textfile
    lines.append("#X connect 3 0 6 0;")   # textfile → route param
    lines.append(f"#X connect 3 0 {delay_idx} 0;")   # textfile → delay
    lines.append(f"#X connect {delay_idx} 0 3 0;")   # delay → textfile (iterate)
    lines.append("#X connect 6 0 7 0;")   # route param → route names

    for i in range(len(params)):
        lines.append(f"#X connect 7 {i} {send_start + i} 0;")

    lines.append(f"#X restore 620 490 pd preset-load;")
    return "\n".join(lines)


def gen_automation_panel(params, start_y=540):
    """Generate automation panel GUI objects and param-lfo instances.
    Returns (objects_text, lfo_objects_text, auto_params_list)
    auto_params_list contains (name, min, max, lfo_obj_idx) for connectable params.
    """
    auto_params = [(n, mn, mx) for n, mn, mx, auto in params if auto]

    lines = []
    # Separator + header
    lines.append(f"#X obj 540 {start_y} cnv 5 480 2 empty empty empty 0 0 0 12 -258113 -1 0;")
    lines.append(f"#X obj 540 {start_y+20} cnv 15 480 20 empty empty AUTOMATION 4 10 0 14 -233280 -1 0;")

    if auto_params:
        lines.append(f"#X text 540 {start_y+45} On;")
        lines.append(f"#X text 570 {start_y+45} Rate;")
        lines.append(f"#X text 680 {start_y+45} Depth;")
        lines.append(f"#X text 770 {start_y+45} Param;")

    # Rows
    row_y = start_y + 65
    for name, mn, mx in auto_params:
        lines.append(f"#X obj 540 {row_y} tgl 15 0 $0-lfo-{name}-on $0-lfo-{name}-on empty 0 -8 0 10 -262144 -1 -1 0 1;")
        lines.append(f"#X obj 565 {row_y} hsl 100 12 0.05 10 1 0 $0-gui-lfo-{name}-rate $0-lfo-{name}-rate empty -2 -8 10 -262144 -1 -1 0 1;")
        lines.append(f"#X obj 675 {row_y} hsl 80 12 0 100 0 0 $0-gui-lfo-{name}-depth $0-lfo-{name}-depth empty -2 -8 10 -262144 -1 -1 0 1;")
        lines.append(f"#X text 770 {row_y} {name};")
        row_y += 25

    return "\n".join(lines), auto_params


def gen_lfo_instances(auto_params, start_y=540):
    """Generate param-lfo object lines."""
    lines = []
    y = start_y
    for name, mn, mx in auto_params:
        lines.append(f"#X obj 20 {y} param-lfo $0-ctl-{name} {mn} {mx};")
        y += 30
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    module_name = sys.argv[1]
    params = []
    for arg in sys.argv[2:]:
        parts = arg.split(":")
        name = parts[0]
        mn = parts[1] if len(parts) > 1 else "0"
        mx = parts[2] if len(parts) > 2 else "100"
        auto = not (len(parts) > 3 and parts[3] == "noauto")
        params.append((name, mn, mx, auto))

    print("=== PRESET SAVE SUBPATCH ===")
    print(gen_preset_save(module_name, params))
    print()
    print("=== PRESET LOAD SUBPATCH ===")
    print(gen_preset_load(module_name, params))
    print()
    print("=== LFO INSTANCES ===")
    auto_params = [(n, mn, mx) for n, mn, mx, a in params if a]
    print(gen_lfo_instances(auto_params))
    print()
    print("=== AUTOMATION PANEL ===")
    panel_text, _ = gen_automation_panel(params)
    print(panel_text)
