#!/usr/bin/env python3
"""Add presets + automation to a Pd module file.

Reads the existing .pd file, identifies processing chain receives,
renames them with -a suffix, inserts param-lfo instances, preset
save/load subpatches, and automation panel GUI.

Usage:
  python3 add-presets-automation.py MODULE.pd PARAM1:MIN:MAX ... [--noauto PARAM ...]

Example:
  python3 add-presets-automation.py modules/chorus.pd rate:0.1:3 depth:0:100 delay:5:30 fb:0:40 width:0:100 mix:0:100 bypass:0:1 --noauto bypass
"""

import sys
import re
import os


def parse_pd_file(filepath):
    """Parse a .pd file into top-level objects and connections."""
    with open(filepath) as f:
        content = f.read()
    lines = content.split("\n")

    header = []  # canvas declaration
    objects = []  # list of (line_text, is_subpatch, subpatch_lines)
    connections = []
    depth = 0
    current_subpatch = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if depth == 0 and line.startswith("#N canvas"):
            header.append(line)
            depth = 1
        elif depth == 1 and line.startswith("#N canvas"):
            current_subpatch = [line]
            depth = 2
        elif depth >= 2:
            current_subpatch.append(line)
            if line.startswith("#N canvas"):
                depth += 1
            elif line.startswith("#X restore"):
                depth -= 1
                if depth == 1:
                    objects.append(("subpatch", current_subpatch))
                    current_subpatch = []
        elif depth == 1 and line.startswith("#X connect"):
            connections.append(line)
        elif depth == 1 and (line.startswith("#X obj") or line.startswith("#X text")
                            or line.startswith("#X msg") or line.startswith("#X floatatom")):
            objects.append(("object", [line]))
        elif line.strip() == "":
            pass
        i += 1

    return header, objects, connections


def find_processing_receives(objects, param_names):
    """Find object indices that are processing chain receives for the given params.
    These are `r $0-ctl-PARAM` objects that feed into /100 or other processing."""
    rename_indices = {}
    for idx, (kind, lines) in enumerate(objects):
        if kind == "object":
            line = lines[0]
            for pname in param_names:
                # Match r $0-ctl-PARAM (but not r $0-ctl-PARAM-a, and not inside GUI)
                if f"r $0-ctl-{pname};" in line and "obj" in line:
                    # Check if this is a processing receive (not in GUI section)
                    # Processing receives typically have x < 500 (left side)
                    m = re.match(r"#X obj (\d+)", line)
                    if m and int(m.group(1)) < 500:
                        rename_indices[idx] = pname
    return rename_indices


def rename_receives(objects, rename_indices):
    """Rename processing chain receives by adding -a suffix."""
    for idx, pname in rename_indices.items():
        kind, lines = objects[idx]
        lines[0] = lines[0].replace(f"r $0-ctl-{pname};", f"r $0-ctl-{pname}-a;")


def gen_preset_save_subpatch(module_name, params, x=540, y=490):
    """Generate preset-save subpatch lines."""
    lines = []
    lines.append("#N canvas 0 0 700 600 preset-save 0;")

    obj_idx = 0
    latch_indices = {}
    for i, (name, _, _) in enumerate(params):
        px = (i % 3) * 170 + 30
        py = (i // 3) * 90 + 30
        lines.append(f"#X obj {px} {py} r \\$0-ctl-{name};")
        obj_idx += 1
        lines.append(f"#X obj {px} {py+30} f;")
        latch_indices[name] = obj_idx
        obj_idx += 1

    base_y = (len(params) // 3 + 1) * 90 + 30
    inlet_idx = obj_idx; lines.append(f"#X obj 30 {base_y} inlet;"); obj_idx += 1
    save_idx = obj_idx; lines.append(f"#X obj 30 {base_y+30} savepanel;"); obj_idx += 1
    tsb_idx = obj_idx; lines.append(f"#X obj 30 {base_y+60} t s b;"); obj_idx += 1
    tf_idx = obj_idx; lines.append(f"#X obj 30 {base_y+100} textfile;"); obj_idx += 1
    n_out = len(params) + 1
    trig_idx = obj_idx; lines.append(f"#X obj 30 {base_y+140} t {' '.join(['b']*n_out)};"); obj_idx += 1
    clr_idx = obj_idx; lines.append(f"#X msg 30 {base_y+180} clear;"); obj_idx += 1

    msg_indices = {}
    for i, (name, _, _) in enumerate(params):
        mid = obj_idx
        lines.append(f"#X msg {(i+1)*90+30} {base_y+180} add param {name} \\$1;")
        msg_indices[name] = mid
        obj_idx += 1

    wr_idx = obj_idx; lines.append(f"#X msg 200 {base_y+90} write \\$1;"); obj_idx += 1

    # Connections
    for i, (name, _, _) in enumerate(params):
        lines.append(f"#X connect {i*2} 0 {i*2+1} 1;")
    lines.append(f"#X connect {inlet_idx} 0 {save_idx} 0;")
    lines.append(f"#X connect {save_idx} 0 {tsb_idx} 0;")
    lines.append(f"#X connect {tsb_idx} 1 {trig_idx} 0;")
    lines.append(f"#X connect {tsb_idx} 0 {wr_idx} 0;")
    lines.append(f"#X connect {wr_idx} 0 {tf_idx} 0;")
    mo = n_out - 1
    lines.append(f"#X connect {trig_idx} {mo} {clr_idx} 0;")
    lines.append(f"#X connect {clr_idx} 0 {tf_idx} 0;")
    for i, (name, _, _) in enumerate(params):
        out = mo - 1 - i
        fi = latch_indices[name]
        mi = msg_indices[name]
        lines.append(f"#X connect {trig_idx} {out} {fi} 0;")
        lines.append(f"#X connect {fi} 0 {mi} 0;")
        lines.append(f"#X connect {mi} 0 {tf_idx} 0;")

    lines.append(f"#X restore {x} {y} pd preset-save;")
    return lines


def gen_preset_load_subpatch(module_name, params, x=620, y=490):
    """Generate preset-load subpatch lines."""
    lines = []
    lines.append("#N canvas 0 0 700 500 preset-load 0;")
    lines.append("#X obj 30 30 inlet;")
    lines.append("#X obj 30 60 openpanel;")
    lines.append("#X obj 30 100 t b s b;")
    lines.append("#X obj 30 140 textfile;")
    lines.append("#X msg 30 180 clear;")
    lines.append("#X msg 200 140 read \\$1 cr;")
    lines.append("#X obj 30 220 route param;")
    pnames = " ".join(p[0] for p in params)
    lines.append(f"#X obj 30 260 route {pnames};")
    ss = 8
    for i, (name, _, _) in enumerate(params):
        lines.append(f"#X obj {i*90+30} 310 s \\$0-ctl-{name};")
    di = ss + len(params)
    lines.append(f"#X obj 300 220 delay 0;")
    lines.append("#X connect 0 0 1 0;")
    lines.append("#X connect 1 0 2 0;")
    lines.append("#X connect 2 2 4 0;")
    lines.append("#X connect 4 0 3 0;")
    lines.append("#X connect 2 1 5 0;")
    lines.append("#X connect 5 0 3 0;")
    lines.append("#X connect 2 0 3 0;")
    lines.append("#X connect 3 0 6 0;")
    lines.append(f"#X connect 3 0 {di} 0;")
    lines.append(f"#X connect {di} 0 3 0;")
    lines.append("#X connect 6 0 7 0;")
    for i in range(len(params)):
        lines.append(f"#X connect 7 {i} {ss+i} 0;")
    lines.append(f"#X restore {x} {y} pd preset-load;")
    return lines


def add_features(filepath, param_specs, noauto_params):
    """Main function: add presets + automation to a module."""
    module_name = os.path.splitext(os.path.basename(filepath))[0]

    params = []  # (name, min, max)
    auto_params = []  # (name, min, max) - automatable only
    for spec in param_specs:
        parts = spec.split(":")
        name, mn, mx = parts[0], parts[1], parts[2]
        params.append((name, mn, mx))
        if name not in noauto_params:
            auto_params.append((name, mn, mx))

    header, objects, connections = parse_pd_file(filepath)

    # Find and rename processing chain receives
    param_names_to_auto = [p[0] for p in auto_params]
    rename_map = find_processing_receives(objects, param_names_to_auto)
    rename_receives(objects, rename_map)

    # Find where to insert new objects (before GUI section)
    # GUI typically starts at x >= 500
    gui_start = None
    for idx, (kind, lines) in enumerate(objects):
        if kind == "object":
            m = re.match(r"#X obj (\d+)", lines[0])
            if m and int(m.group(1)) >= 500:
                gui_start = idx
                break

    if gui_start is None:
        gui_start = len(objects)

    # Find old preset section to remove (apply-preset subpatch, msg boxes, preset texts)
    old_preset_indices = set()
    for idx, (kind, lines) in enumerate(objects):
        if kind == "subpatch" and "apply-preset" in lines[-1]:
            old_preset_indices.add(idx)
        elif kind == "object":
            line = lines[0]
            # Old preset msg boxes (contain unpack or multiple numbers)
            if line.startswith("#X msg") and idx >= gui_start:
                # Check if it's connected to apply-preset
                for c in connections:
                    m = re.match(r"#X connect (\d+) 0 (\d+) 0", c)
                    if m and int(m.group(1)) == idx:
                        target = int(m.group(2))
                        if target < len(objects):
                            tk, tl = objects[target]
                            if tk == "subpatch" and "apply-preset" in tl[-1]:
                                old_preset_indices.add(idx)

    # Find old preset labels
    for idx, (kind, lines) in enumerate(objects):
        if kind == "object" and lines[0].startswith("#X text"):
            text = lines[0]
            for label in ["Studio\\ Room", "Broadcast\\ Booth", "Open\\ Hall", "Warm\\ Chamber",
                         "Ensemble", "Gentle\\ Drift", "Thick\\ Swirl", "Shimmer\\ Wash",
                         "Slow\\ Sweep", "Underwater", "Radio\\ Dial", "Wah\\ Pulse",
                         "High\\ Pass\\ Rise", "Classic\\ Tremolo", "Stereo\\ Pulse",
                         "Hard\\ Gate", "Slow\\ Breathe", "Choppy\\ Swing"]:
                if label in text:
                    old_preset_indices.add(idx)

    # Build new object list
    new_objects = []
    # Keep everything up to and including bypass toggle section
    # But remove old presets and apply-preset

    # Find the last parameter control object before PRESETS section
    presets_text_idx = None
    for idx, (kind, lines) in enumerate(objects):
        if kind == "object" and "PRESETS" in lines[0] and lines[0].startswith("#X text"):
            presets_text_idx = idx
            break

    # Copy objects, skip old preset-related ones
    for idx, (kind, lines) in enumerate(objects):
        if idx in old_preset_indices:
            continue
        # Skip old PRESETS text and separator before it (already handled by new section)
        new_objects.append((kind, lines))

    # Now insert LFO instances, preset buttons, subpatches, and automation panel
    # We need to figure out where to insert them

    # For now, just output the modified file with new additions appended
    # The user can then manually position things or we do it programmatically

    # Actually, let's build the output properly
    output_lines = list(header)

    # Increase canvas height
    if output_lines:
        output_lines[0] = re.sub(r'(\d+) (\d+);$',
                                  lambda m: f"{max(int(m.group(1)), 1080)} {max(int(m.group(2)), 1100)};",
                                  output_lines[0])

    # Write existing objects (minus old presets)
    kept_objects = []
    for idx, (kind, lines) in enumerate(objects):
        if idx in old_preset_indices:
            continue
        kept_objects.append((idx, kind, lines))

    # Build index mapping: old_idx -> new_idx
    old_to_new = {}
    new_idx = 0
    insert_point = None  # where to insert new objects

    for old_idx, kind, lines in kept_objects:
        old_to_new[old_idx] = new_idx
        new_idx += 1

    # Insert new objects at the right place
    # Find where PRESETS text was (or end of GUI controls)
    insert_new_idx = new_idx  # default: append at end

    # LFO instances
    lfo_start_idx = new_idx
    lfo_indices = {}
    for name, mn, mx in auto_params:
        lfo_indices[name] = new_idx
        new_idx += 1

    # Preset buttons
    save_bng_idx = new_idx; new_idx += 1
    load_bng_idx = new_idx; new_idx += 1

    # Preset subpatches
    save_sp_idx = new_idx; new_idx += 1
    load_sp_idx = new_idx; new_idx += 1

    # Automation panel objects
    auto_sep_idx = new_idx; new_idx += 1  # separator
    auto_hdr_idx = new_idx; new_idx += 1  # header
    auto_labels_start = new_idx
    if auto_params:
        new_idx += 4  # On, Rate, Depth, Param labels
    auto_row_start = new_idx
    auto_row_indices = {}  # name -> (tgl_idx, rate_idx, depth_idx, text_idx)
    for name, mn, mx in auto_params:
        auto_row_indices[name] = (new_idx, new_idx+1, new_idx+2, new_idx+3)
        new_idx += 4

    # Footer separator
    footer_sep_idx = new_idx; new_idx += 1
    footer_text1_idx = new_idx; new_idx += 1
    footer_text2_idx = new_idx; new_idx += 1

    # Now write all objects
    for old_idx, kind, lines in kept_objects:
        # Skip old footer texts (chain description, bypass description)
        # We'll add them at the new position
        for l in lines:
            output_lines.append(l)

    # Write LFO instances
    y = 540
    for name, mn, mx in auto_params:
        output_lines.append(f"#X obj 20 {y} param-lfo $0-ctl-{name} {mn} {mx};")
        y += 30

    # Preset section
    output_lines.append(f"#X obj 540 470 bng 20 250 50 0 empty empty Save 25 7 0 12 -262144 -1 -1;")
    output_lines.append(f"#X obj 620 470 bng 20 250 50 0 empty empty Load 25 7 0 12 -262144 -1 -1;")

    # Preset save subpatch
    save_lines = gen_preset_save_subpatch(module_name, params)
    output_lines.extend(save_lines)

    # Preset load subpatch
    load_lines = gen_preset_load_subpatch(module_name, params)
    output_lines.extend(load_lines)

    # Automation panel
    auto_y = 520
    output_lines.append(f"#X obj 540 {auto_y} cnv 5 480 2 empty empty empty 0 0 0 12 -258113 -1 0;")
    output_lines.append(f"#X obj 540 {auto_y+20} cnv 15 480 20 empty empty AUTOMATION 4 10 0 14 -233280 -1 0;")
    if auto_params:
        output_lines.append(f"#X text 540 {auto_y+45} On;")
        output_lines.append(f"#X text 570 {auto_y+45} Rate;")
        output_lines.append(f"#X text 680 {auto_y+45} Depth;")
        output_lines.append(f"#X text 770 {auto_y+45} Param;")

    row_y = auto_y + 65
    for name, mn, mx in auto_params:
        output_lines.append(f"#X obj 540 {row_y} tgl 15 0 $0-lfo-{name}-on $0-lfo-{name}-on empty 0 -8 0 10 -262144 -1 -1 0 1;")
        output_lines.append(f"#X obj 565 {row_y} hsl 100 12 0.05 10 1 0 $0-gui-lfo-{name}-rate $0-lfo-{name}-rate empty -2 -8 10 -262144 -1 -1 0 1;")
        output_lines.append(f"#X obj 675 {row_y} hsl 80 12 0 100 0 0 $0-gui-lfo-{name}-depth $0-lfo-{name}-depth empty -2 -8 10 -262144 -1 -1 0 1;")
        output_lines.append(f"#X text 770 {row_y} {name};")
        row_y += 25

    # Footer
    output_lines.append(f"#X obj 540 {row_y+10} cnv 5 480 2 empty empty empty 0 0 0 12 -258113 -1 0;")

    # Remap connections
    for conn in connections:
        m = re.match(r"#X connect (\d+) (\d+) (\d+) (\d+);", conn)
        if m:
            src, so, dst, di = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if src in old_to_new and dst in old_to_new:
                output_lines.append(f"#X connect {old_to_new[src]} {so} {old_to_new[dst]} {di};")

    # Add new connections
    # Save/Load buttons → subpatches
    output_lines.append(f"#X connect {save_bng_idx} 0 {save_sp_idx} 0;")
    output_lines.append(f"#X connect {load_bng_idx} 0 {load_sp_idx} 0;")

    # Automation toggles/sliders → param-lfo instances
    for name, mn, mx in auto_params:
        tgl_idx, rate_idx, depth_idx, _ = auto_row_indices[name]
        lfo_idx = lfo_indices[name]
        output_lines.append(f"#X connect {tgl_idx} 0 {lfo_idx} 0;")
        output_lines.append(f"#X connect {rate_idx} 0 {lfo_idx} 1;")
        output_lines.append(f"#X connect {depth_idx} 0 {lfo_idx} 2;")

    output_lines.append("")

    # Write output
    with open(filepath, "w") as f:
        f.write("\n".join(output_lines))

    print(f"Updated {filepath}:")
    print(f"  - Renamed {len(rename_map)} processing receives with -a suffix")
    print(f"  - Added {len(auto_params)} param-lfo instances")
    print(f"  - Added preset save/load subpatches ({len(params)} params)")
    print(f"  - Added automation panel ({len(auto_params)} rows)")
    print(f"  - Removed {len(old_preset_indices)} old preset objects")


if __name__ == "__main__":
    args = sys.argv[1:]
    filepath = args[0]
    noauto = set()
    param_specs = []
    i = 1
    while i < len(args):
        if args[i] == "--noauto":
            i += 1
            while i < len(args) and not args[i].startswith("-"):
                noauto.add(args[i])
                i += 1
        else:
            param_specs.append(args[i])
            i += 1

    add_features(filepath, param_specs, noauto)
