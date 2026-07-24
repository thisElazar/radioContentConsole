#!/usr/bin/env python3
"""
Insert [route set] filters in preset-save subcanvases.

Problem: param-lfo sends "set VALUE" on the base parameter bus for visual
feedback (slider/numbox tracking). Preset-save subcanvases have
[r $0-ctl-xxx] -> [f] pairs that choke on "set" messages.

Fix: Insert [route set] between each [r] and [f]. The route object's
outlet 1 (reject) passes plain floats through to [f], while outlet 0
catches and drops "set" messages.

Strategy: Append [route set] objects AFTER all existing objects in each
preset-save subcanvas (no renumbering needed), then rewire connections.
"""

import re
import sys
from pathlib import Path


def parse_subcanvas(lines, start_idx):
    """Parse a subcanvas starting at #N canvas line, return end index (restore line)."""
    depth = 1
    i = start_idx + 1
    while i < len(lines) and depth > 0:
        line = lines[i].strip()
        if line.startswith("#N canvas"):
            depth += 1
        elif line.startswith("#X restore"):
            depth -= 1
        i += 1
    return i - 1  # index of #X restore line


def process_preset_save(lines, canvas_start, canvas_end):
    """Process a preset-save subcanvas, inserting [route set] filters.

    Returns modified lines for the subcanvas region.
    """
    # Parse objects and connections within the subcanvas
    # Objects are lines between canvas_start+1 and connections/restore
    subcanvas_lines = lines[canvas_start:canvas_end + 1]

    # Separate into: canvas header, objects, connections, restore
    header = subcanvas_lines[0]  # #N canvas ...
    restore = subcanvas_lines[-1]  # #X restore ...

    objects = []
    connections = []

    for line in subcanvas_lines[1:-1]:
        stripped = line.strip()
        if stripped.startswith("#X connect"):
            connections.append(stripped)
        elif stripped.startswith("#X obj") or stripped.startswith("#X msg") or \
             stripped.startswith("#X floatatom") or stripped.startswith("#X text") or \
             stripped.startswith("#N canvas"):
            objects.append(stripped)
        else:
            objects.append(stripped)  # catch-all

    # Find receiver objects: [r \$0-ctl-xxx] or [r NNNN-xxx]
    receiver_indices = {}
    for i, obj in enumerate(objects):
        m = re.match(r'#X obj (\d+) (\d+) r \\?\$0-\S+;', obj) or \
            re.match(r'#X obj (\d+) (\d+) r \d+-\S+;', obj)
        if m:
            receiver_indices[i] = (int(m.group(1)), int(m.group(2)))

    # Find connections from receivers to [f] objects: connect R 0 F 1
    # These are [r] -> [f] right-inlet (value storage) connections
    r_to_f_pairs = []
    remaining_connections = []

    for conn in connections:
        m = re.match(r'#X connect (\d+) (\d+) (\d+) (\d+);', conn)
        if m:
            src, src_out, dst, dst_in = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            if src in receiver_indices and src_out == 0 and dst_in == 1:
                # Check if destination is [f]
                dst_obj = objects[dst].strip()
                if re.match(r'#X obj \d+ \d+ f;', dst_obj):
                    r_to_f_pairs.append((src, dst))
                    continue
        remaining_connections.append(conn)

    if not r_to_f_pairs:
        return None  # No changes needed

    # Add [route set] objects after all existing objects
    next_idx = len(objects)
    new_objects = []
    new_connections = []

    for r_idx, f_idx in r_to_f_pairs:
        rx, ry = receiver_indices[r_idx]
        route_idx = next_idx + len(new_objects)
        # Position route set between receiver and f (offset y by 15)
        new_objects.append(f"#X obj {rx} {ry + 15} route set;")
        # Wire: receiver -> route set
        new_connections.append(f"#X connect {r_idx} 0 {route_idx} 0;")
        # Wire: route set outlet 1 (reject/float) -> f right inlet
        new_connections.append(f"#X connect {route_idx} 1 {f_idx} 1;")

    # Rebuild subcanvas
    result = [header]
    for obj in objects:
        result.append(obj)
    for obj in new_objects:
        result.append(obj)
    for conn in remaining_connections:
        result.append(conn)
    for conn in new_connections:
        result.append(conn)
    result.append(restore)

    return result


def process_file(filepath):
    """Process a single Pd file, fixing all preset-save subcanvases."""
    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')

    # Find preset-save subcanvases
    modifications = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("#N canvas") and "preset-save" in stripped:
            canvas_end = parse_subcanvas(lines, i)
            result = process_preset_save(lines, i, canvas_end)
            if result:
                modifications.append((i, canvas_end, result))
            i = canvas_end + 1
        else:
            i += 1

    if not modifications:
        return False

    # Apply modifications in reverse order to preserve line indices
    for start, end, new_lines in reversed(modifications):
        lines[start:end + 1] = new_lines

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines))

    return True


def main():
    modules_dir = Path(__file__).parent.parent / "modules"

    # All module files that have param-lfo instances
    module_files = sorted(modules_dir.glob("*.pd"))

    modified = []
    for filepath in module_files:
        content = filepath.read_text()
        if "preset-save" not in content:
            continue
        if "param-lfo" not in content:
            continue

        print(f"Processing {filepath.name}...")
        if process_file(filepath):
            modified.append(filepath.name)
            print(f"  -> Modified (added [route set] filters)")
        else:
            print(f"  -> No changes needed")

    if modified:
        print(f"\nModified {len(modified)} files: {', '.join(modified)}")
    else:
        print("\nNo files needed modification.")


if __name__ == "__main__":
    main()
