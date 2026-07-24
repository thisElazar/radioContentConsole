#!/usr/bin/env python3
"""
Wire param-lfo visual feedback outlets to corresponding sliders and number boxes.

param-lfo now has an outlet that sends "set VALUE" for visual feedback.
This script connects each param-lfo outlet 0 to the matching hsl and
floatatom objects (matched by bus name = iemgui receive name).

Pd object indexing: at each canvas level, objects are numbered sequentially.
Subcanvas contents are invisible to the parent's numbering — only the
#X restore line counts as one object in the parent.
"""

import re
import sys
from pathlib import Path


def parse_top_level_objects(lines):
    """Parse a Pd file and return top-level objects with their indices.

    Returns list of (index, line_number, line_content) tuples for
    top-level objects only.
    """
    objects = []
    depth = 0
    idx = 0

    for line_num, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("#N canvas"):
            if depth == 0:
                # Root canvas header — not an object
                depth = 1
            else:
                # Nested subcanvas opening — increases depth
                depth += 1
            continue

        if stripped.startswith("#X restore"):
            depth -= 1
            if depth == 1:
                # This restore is a top-level object (the subcanvas itself)
                objects.append((idx, line_num, stripped))
                idx += 1
            continue

        if depth == 1:
            # Top-level content
            if stripped.startswith("#X connect"):
                continue  # connections aren't objects
            if stripped.startswith("#X"):
                objects.append((idx, line_num, stripped))
                idx += 1

    return objects


def extract_param_lfo_bus(obj_line):
    """Extract the bus name ($1 argument) from a param-lfo object line."""
    m = re.match(r'#X obj \d+ \d+ param-lfo (\S+)', obj_line)
    if m:
        return m.group(1)
    return None


def extract_hsl_receive(obj_line):
    """Extract the receive name from an hsl object line.

    hsl format: #X obj X Y hsl W H MIN MAX LOG INIT SEND RECEIVE LABEL ...
    Fields after 'hsl': 1=W 2=H 3=MIN 4=MAX 5=LOG 6=INIT 7=SEND 8=RECEIVE
    """
    m = re.match(r'#X obj \d+ \d+ hsl \S+ \S+ \S+ \S+ \S+ \S+ \S+ (\S+)', obj_line)
    if m:
        recv = m.group(1)
        if recv != "empty" and recv != "-":
            return recv
    return None


def extract_floatatom_receive(obj_line):
    """Extract the receive name from a floatatom line.

    floatatom format: #X floatatom X Y WIDTH LOWER UPPER LABEL_POS LABEL RECEIVE SEND FLAG
    Note: RECEIVE comes before SEND (opposite of hsl).
    """
    m = re.match(r'#X floatatom \d+ \d+ \d+ \S+ \S+ \S+ \S+ (\S+)', obj_line)
    if m:
        recv = m.group(1)
        if recv != "empty" and recv != "-":
            return recv
    return None


def extract_nbx_receive(obj_line):
    """Extract the receive name from an nbx (number box 2) object line.

    nbx format: #X obj X Y nbx W H MIN MAX LOG INIT SEND RECEIVE ...
    """
    m = re.match(r'#X obj \d+ \d+ nbx \S+ \S+ \S+ \S+ \S+ \S+ \S+ (\S+)', obj_line)
    if m:
        recv = m.group(1)
        if recv != "empty" and recv != "-":
            return recv
    return None


def process_file(filepath):
    """Process a single Pd file, adding param-lfo outlet connections."""
    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.rstrip('\n').split('\n')
    objects = parse_top_level_objects(lines)

    # Find param-lfo instances and their bus names
    param_lfos = {}  # bus_name -> obj_index
    for idx, line_num, line in objects:
        bus = extract_param_lfo_bus(line)
        if bus:
            param_lfos[bus] = idx

    if not param_lfos:
        return False, 0

    # Find hsl, floatatom, nbx objects and their receive names
    receivers = {}  # bus_name -> list of obj_indices
    for idx, line_num, line in objects:
        recv = extract_hsl_receive(line)
        if recv is None:
            recv = extract_floatatom_receive(line)
        if recv is None:
            recv = extract_nbx_receive(line)
        if recv and recv in param_lfos:
            receivers.setdefault(recv, []).append(idx)

    if not receivers:
        return False, 0

    # Generate new connections
    new_connections = []
    for bus_name, target_indices in sorted(receivers.items()):
        lfo_idx = param_lfos[bus_name]
        for target_idx in target_indices:
            new_connections.append(f"#X connect {lfo_idx} 0 {target_idx} 0;")

    # Find where to insert connections (before the last line or at end)
    # Connections go at the end of the file, before any trailing empty lines
    # In Pd files, connections are at the end of their canvas level
    # We append to the end of the file
    while lines and lines[-1].strip() == '':
        lines.pop()

    for conn in new_connections:
        lines.append(conn)
    lines.append('')  # trailing newline

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))

    return True, len(new_connections)


def main():
    modules_dir = Path(__file__).parent.parent / "modules"
    module_files = sorted(modules_dir.glob("*.pd"))

    total_connections = 0
    modified = []

    for filepath in module_files:
        content = filepath.read_text()
        if "param-lfo" not in content:
            continue

        success, count = process_file(filepath)
        if success:
            modified.append((filepath.name, count))
            total_connections += count
            print(f"  {filepath.name}: added {count} connections")

    if modified:
        print(f"\nModified {len(modified)} files, {total_connections} total connections added")
    else:
        print("No files needed modification.")


if __name__ == "__main__":
    main()
