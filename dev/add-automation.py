#!/usr/bin/env python3
"""Add param-lfo automation to all modules.

For each module:
1. Rename processing-chain receives with -a suffix (so DSP reads modulated values)
2. Add param-lfo instances (one per automatable parameter)
3. Add automation panel GUI (toggle, rate slider, depth slider per param)
4. Wire: automation panel → param-lfo inlets
5. Wire: param-lfo outlet → slider + numbox (visual feedback via 'set' message)

No preset save/load — just automation.
"""

import re
import os
from pathlib import Path

# ── Module specs ──────────────────────────────────────────────────────
# For each module: list of (param_name, min, max, automatable)
# The bus name is prefix + param_name
# prefix is auto-detected from hsl receive names

MODULES = {
    "chorus.pd": {
        "params": [
            ("rate", "0.1", "3", True),
            ("depth", "0", "100", True),
            ("delay", "5", "30", True),
            ("fb", "0", "40", True),
            ("width", "0", "100", True),
            ("mix", "0", "100", True),
            ("bypass", "0", "1", False),
        ],
    },
    "space.pd": {
        "params": [
            ("size", "0", "80", True),
            ("damp", "0", "100", True),
            ("width", "0", "100", True),
            ("mix", "0", "50", True),
            ("bypass", "0", "1", False),
        ],
    },
    "filter.pd": {
        "params": [
            ("mode", "0", "2", False),
            ("cutoff", "40", "10000", True),
            ("reso", "0", "85", True),
            ("lforate", "0.01", "5", False),
            ("lfodepth", "0", "100", True),
            ("envfol", "0", "100", True),
            ("mix", "0", "100", True),
        ],
    },
    "tape-warmth.pd": {
        "params": [
            ("drive", "0", "60", True),
            ("tone", "-6", "6", True),
            ("hbump", "0", "4", True),
            ("frate", "0.5", "6", True),
            ("fdepth", "0", "15", True),
            ("mix", "0", "100", True),
            ("bypass", "0", "1", False),
        ],
    },
    "tremolo-gate.pd": {
        "params": [
            ("rate", "1", "12", True),
            ("sync", "0", "1", False),
            ("syncrate", "0", "3", False),
            ("shape", "0", "100", True),
            ("depth", "0", "100", True),
            ("phase", "0", "180", True),
            ("mix", "0", "100", True),
            ("bypass", "0", "1", False),
        ],
    },
    "fm-voice.pd": {
        "params": [
            ("mod-index", "0", "8", True),
            ("env-amount", "0", "10", True),
            ("env-decay", "20", "2000", True),
            ("output-db", "-60", "6", True),
        ],
    },
    "osc-bank.pd": {
        "params": [
            ("fine1", "-1200", "1200", True),
            ("drift1", "0", "50", True),
            ("fine2", "-1200", "1200", True),
            ("drift2", "0", "50", True),
            ("mix-pct", "0", "100", True),
            ("cutoff", "50", "20000", True),
            ("reso", "0", "100", True),
            ("output-db", "-60", "6", True),
        ],
    },
    "chord-pad.pd": {
        "params": [
            ("detune", "0", "100", True),
            ("cutoff", "200", "8000", True),
            ("reso", "0", "100", True),
            ("lfo-rate", "0.1", "10", True),
            ("lfo-depth", "0", "100", True),
            ("output-db", "-60", "6", True),
        ],
    },
    "noise-sculptor.pd": {
        "params": [
            ("cutoff", "40", "8000", True),
            ("reso", "0", "75", True),
            ("lfo-rate", "0.01", "2", True),
            ("lfo-depth", "0", "100", True),
            ("output-db", "-60", "6", True),
        ],
    },
    "drum-machine.pd": {
        "params": [
            ("master-level", "-60", "6", True),
            ("kick-level", "-30", "0", True),
            ("snare-level", "-30", "0", True),
            ("clap-level", "-30", "0", True),
            ("rim-level", "-30", "0", True),
            ("chh-level", "-30", "0", True),
            ("ohh-level", "-30", "0", True),
            ("ltom-level", "-30", "0", True),
            ("htom-level", "-30", "0", True),
        ],
    },
    "sequencer.pd": {
        "params": [
            ("bpm", "40", "240", True),
        ],
    },
}


def parse_top_level(lines):
    """Parse Pd file, return top-level objects with indices.
    Returns list of (obj_index, line_number, line_text).
    Subcanvas contents are skipped; #X restore counts as one object.
    """
    objects = []
    depth = 0
    idx = 0
    for line_num, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#N canvas"):
            if depth == 0:
                depth = 1  # root canvas header
            else:
                depth += 1
            continue
        if s.startswith("#X restore"):
            depth -= 1
            if depth == 1:
                objects.append((idx, line_num, s))
                idx += 1
            continue
        if depth == 1:
            if s.startswith("#X connect"):
                continue
            if s.startswith("#X"):
                objects.append((idx, line_num, s))
                idx += 1
    return objects


def detect_bus_name(objects, param_name):
    """Find the full bus name for a parameter by scanning hsl/floatatom receive names."""
    for _, _, line in objects:
        # hsl: ... SEND RECEIVE ...
        m = re.match(r'#X obj \d+ \d+ hsl \S+ \S+ \S+ \S+ \S+ \S+ \S+ (\S+)', line)
        if m:
            recv = m.group(1)
            if recv.endswith("-" + param_name) or recv.endswith("ctl-" + param_name):
                return recv
        # tgl: ... SEND RECEIVE ...
        m = re.match(r'#X obj \d+ \d+ tgl \S+ \S+ \S+ \S+ \S+ (\S+)', line)
        if m:
            recv = m.group(1)
            if recv.endswith("-" + param_name) or recv.endswith("ctl-" + param_name):
                return recv
        # hradio: ... SEND RECEIVE ...
        m = re.match(r'#X obj \d+ \d+ hradio \S+ \S+ \S+ \S+ \S+ (\S+)', line)
        if m:
            recv = m.group(1)
            if recv.endswith("-" + param_name) or recv.endswith("ctl-" + param_name):
                return recv
    return None


def find_iemgui_by_receive(objects, bus_name):
    """Find hsl object indices that receive on bus_name.
    Only returns iemgui objects (hsl, vsl, nbx), NOT floatatom/gatom —
    Pd doesn't allow abstraction outlet → gatom connections.
    """
    results = []
    for idx, _, line in objects:
        # hsl receive is field 8 (after hsl + 7 fields)
        m = re.match(r'#X obj \d+ \d+ hsl \S+ \S+ \S+ \S+ \S+ \S+ \S+ (\S+)', line)
        if m and m.group(1) == bus_name:
            results.append(idx)
            continue
        # vsl receive
        m = re.match(r'#X obj \d+ \d+ vsl \S+ \S+ \S+ \S+ \S+ \S+ \S+ (\S+)', line)
        if m and m.group(1) == bus_name:
            results.append(idx)
            continue
        # nbx (number box 2) receive
        m = re.match(r'#X obj \d+ \d+ nbx \S+ \S+ \S+ \S+ \S+ \S+ \S+ (\S+)', line)
        if m and m.group(1) == bus_name:
            results.append(idx)
            continue
    return results


def find_processing_receives(lines, bus_name):
    """Find line numbers of [r BUS_NAME] objects in the processing chain (x < 500).
    These need to be renamed to BUS_NAME-a.
    Works at all nesting levels (processing receives can be inside subcanvases).
    """
    results = []
    # Try both escaped (\$0) and unescaped ($0) forms
    patterns = [f"r {bus_name};"]
    escaped = bus_name.replace("$0", "\\$0")
    if escaped != bus_name:
        patterns.append(f"r {escaped};")
    for i, line in enumerate(lines):
        s = line.strip()
        if not s.startswith("#X obj"):
            continue
        for pat in patterns:
            if pat in s:
                m = re.match(r'#X obj (\d+)', s)
                if m and int(m.group(1)) < 500:
                    results.append(i)
                break
    return results


def rename_receives(lines, line_numbers, bus_name):
    """Rename [r BUS_NAME] to [r BUS_NAME-a] at specified line numbers."""
    for ln in line_numbers:
        # Handle both escaped and unescaped $0
        lines[ln] = lines[ln].replace(f"r {bus_name};", f"r {bus_name}-a;")
        escaped = bus_name.replace("$0", "\\$0")
        if escaped != bus_name:
            lines[ln] = lines[ln].replace(f"r {escaped};", f"r {escaped}-a;")


def gen_automation_panel(auto_params, bus_names, start_y):
    """Generate automation panel GUI objects.
    Returns list of (line_text, role) tuples.
    role is 'gui' for display objects, or ('tgl', name), ('rate', name), ('depth', name) for controls.
    """
    objects = []
    # Separator + header
    objects.append((f"#X obj 540 {start_y} cnv 5 480 2 empty empty empty 0 0 0 12 -258113 -1 0;", "gui"))
    objects.append((f"#X obj 540 {start_y+20} cnv 15 480 20 empty empty AUTOMATION 4 10 0 14 -233280 -1 0;", "gui"))
    if auto_params:
        objects.append((f"#X text 540 {start_y+45} On;", "gui"))
        objects.append((f"#X text 570 {start_y+45} Rate;", "gui"))
        objects.append((f"#X text 680 {start_y+45} Depth;", "gui"))
        objects.append((f"#X text 770 {start_y+45} Param;", "gui"))

    row_y = start_y + 65
    for name, mn, mx in auto_params:
        bus = bus_names[name]
        file_bus = bus.replace("$0", "$0")  # In iemgui properties, $0 is NOT escaped
        objects.append((
            f"#X obj 540 {row_y} tgl 15 0 $0-lfo-{name}-on $0-lfo-{name}-on empty 0 -8 0 10 -262144 -1 -1 0 1;",
            ("tgl", name)
        ))
        objects.append((
            f"#X obj 565 {row_y} hsl 100 12 0.05 10 1 1 $0-gui-lfo-{name}-rate $0-lfo-{name}-rate empty -2 -8 10 -262144 -1 -1 5653 1;",
            ("rate", name)
        ))
        objects.append((
            f"#X obj 675 {row_y} hsl 80 12 0 100 0 1 $0-gui-lfo-{name}-depth $0-lfo-{name}-depth empty -2 -8 10 -262144 -1 -1 4000 1;",
            ("depth", name)
        ))
        objects.append((f"#X text 770 {row_y} {name};", "gui"))
        row_y += 25

    # Footer separator
    objects.append((f"#X obj 540 {row_y+10} cnv 5 480 2 empty empty empty 0 0 0 12 -258113 -1 0;", "gui"))
    return objects


def process_module(filepath, spec):
    """Add automation to a single module."""
    with open(filepath) as f:
        content = f.read()
    lines = content.rstrip("\n").split("\n")
    objects = parse_top_level(lines)

    all_params = spec["params"]
    auto_params = [(n, mn, mx) for n, mn, mx, auto in all_params if auto]

    if not auto_params:
        return False, "no automatable params"

    # Detect bus names from existing sliders
    bus_names = {}  # param_name -> full bus name (e.g., "$0-ctl-rate" or "1005-cutoff")
    for name, mn, mx, auto in all_params:
        bus = detect_bus_name(objects, name)
        if bus:
            bus_names[name] = bus

    # Check we found bus names for all auto params
    missing = [n for n, _, _ in auto_params if n not in bus_names]
    if missing:
        return False, f"could not detect bus names for: {missing}"

    # Step 1: Rename processing-chain receives with -a suffix
    rename_count = 0
    for name, mn, mx in auto_params:
        bus = bus_names[name]
        proc_lines = find_processing_receives(lines, bus)
        if proc_lines:
            rename_receives(lines, proc_lines, bus)
            rename_count += len(proc_lines)

    # Step 2: Find slider/numbox indices for visual feedback wiring
    slider_indices = {}  # param_name -> list of obj indices (hsl + floatatom)
    for name, mn, mx in auto_params:
        bus = bus_names[name]
        indices = find_iemgui_by_receive(objects, bus)
        if indices:
            slider_indices[name] = indices

    # Step 3: Find where to append new objects
    # Count existing top-level objects to know next available index
    next_idx = max(idx for idx, _, _ in objects) + 1 if objects else 0

    # Find Y position for automation panel (below existing GUI)
    max_y = 0
    for _, _, line in objects:
        m = re.match(r'#X obj \d+ (\d+)', line) or re.match(r'#X floatatom \d+ (\d+)', line) or re.match(r'#X text \d+ (\d+)', line)
        if m:
            max_y = max(max_y, int(m.group(1)))
    panel_y = max_y + 50

    # Step 4: Generate new objects
    new_lines = []

    # param-lfo instances
    lfo_indices = {}  # param_name -> obj index
    lfo_y = panel_y - len(auto_params) * 30 - 20
    for name, mn, mx in auto_params:
        bus = bus_names[name]
        file_bus = bus.replace("$0", "$0")  # $0 not escaped in obj args
        lfo_indices[name] = next_idx
        new_lines.append(f"#X obj 20 {lfo_y} param-lfo {file_bus} {mn} {mx};")
        next_idx += 1
        lfo_y += 30

    # Automation panel
    panel_objects = gen_automation_panel(auto_params, bus_names, panel_y)
    panel_indices = {}  # ("tgl"|"rate"|"depth", param_name) -> obj index
    for line_text, role in panel_objects:
        if isinstance(role, tuple):
            panel_indices[role] = next_idx
        new_lines.append(line_text)
        next_idx += 1

    # Step 5: Generate connections
    new_connections = []

    # Automation panel → param-lfo inlets
    for name, mn, mx in auto_params:
        lfo_idx = lfo_indices[name]
        tgl_idx = panel_indices.get(("tgl", name))
        rate_idx = panel_indices.get(("rate", name))
        depth_idx = panel_indices.get(("depth", name))
        if tgl_idx is not None:
            new_connections.append(f"#X connect {tgl_idx} 0 {lfo_idx} 0;")
        if rate_idx is not None:
            new_connections.append(f"#X connect {rate_idx} 0 {lfo_idx} 1;")
        if depth_idx is not None:
            new_connections.append(f"#X connect {depth_idx} 0 {lfo_idx} 2;")

    # param-lfo outlet → sliders/numboxes (visual feedback)
    for name, mn, mx in auto_params:
        lfo_idx = lfo_indices[name]
        targets = slider_indices.get(name, [])
        for target_idx in targets:
            new_connections.append(f"#X connect {lfo_idx} 0 {target_idx} 0;")

    # Step 6: Write output
    # Insert new objects before connections, append new connections at end
    # Find last non-connection, non-empty line
    insert_point = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if s.startswith("#X connect") or s == "":
            insert_point = i
        else:
            break

    output = lines[:insert_point] + new_lines + lines[insert_point:] + new_connections

    # Clean trailing empty lines
    while output and output[-1].strip() == "":
        output.pop()
    output.append("")

    with open(filepath, "w") as f:
        f.write("\n".join(output))

    return True, f"{len(auto_params)} LFOs, {rename_count} receives renamed, {len(new_connections)} connections"


def main():
    modules_dir = Path(__file__).parent.parent / "modules"

    for filename, spec in sorted(MODULES.items()):
        filepath = modules_dir / filename
        if not filepath.exists():
            print(f"  {filename}: SKIP (not found)")
            continue

        # Check if already has automation
        content = filepath.read_text()
        if "param-lfo" in content:
            print(f"  {filename}: SKIP (already has param-lfo)")
            continue

        ok, msg = process_module(filepath, spec)
        print(f"  {filename}: {msg}")


if __name__ == "__main__":
    main()
