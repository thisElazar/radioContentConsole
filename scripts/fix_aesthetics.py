#!/usr/bin/env python3
"""Fix visual aesthetics across all toolkit .pd files:
1. Automation section backgrounds → lavender (#e0d0f0)
2. Invisible sliders (bg == fg) → fix fg to #ffffff
3. Slider font size 4 → 8
4. Convert old Pd integer colors to hex strings for consistency
"""

import os, re, glob

LAVENDER = '#e0d0f0'

# Old Pd 6-bit color format → hex
def decode_old_color(val):
    """Decode old Pd IEM color integer to #rrggbb hex."""
    val = int(val)
    if val >= 0:
        return None  # not an old-format color
    n = -val - 1
    r6 = n // 4096
    g6 = (n % 4096) // 64
    b6 = n % 64
    r = min(r6 * 4 + 3, 255)
    g = min(g6 * 4 + 3, 255)
    b = min(b6 * 4 + 3, 255)
    return f'#{r:02x}{g:02x}{b:02x}'


# Identify automation-related cnv panels by label keywords
AUTOMATION_LABELS = ['AUTOMATION', 'LFO']


def is_automation_cnv(line):
    """Check if a cnv line is an automation section header."""
    for kw in AUTOMATION_LABELS:
        if kw in line:
            return True
    return False


def fix_line(line, filepath, linenum, changes):
    """Fix a single line. Returns the fixed line."""
    original = line

    # === CNV: Automation backgrounds → lavender ===
    if '#X obj' in line and ' cnv ' in line and is_automation_cnv(line):
        # cnv format: #X obj x y cnv size w h send recv label lx ly lfont lsize bg_color label_color vis;
        # Replace bg_color with lavender
        parts = line.rstrip(';\n').split()
        # Find color fields — they're near the end
        # The bg_color is the 3rd-to-last field, label_color is 2nd-to-last
        if len(parts) >= 3:
            bg_idx = len(parts) - 3
            old_bg = parts[bg_idx]
            if old_bg != LAVENDER:
                parts[bg_idx] = LAVENDER
                # Also fix label color if it's old format
                lbl_idx = len(parts) - 2
                old_lbl = parts[lbl_idx]
                if old_lbl.lstrip('-').isdigit():
                    hex_lbl = decode_old_color(old_lbl)
                    if hex_lbl:
                        parts[lbl_idx] = hex_lbl
                line = ' '.join(parts) + ';\n'
                changes.append(f'  {filepath}:{linenum}: automation cnv bg {old_bg} → {LAVENDER}')

    # === Also fix cnv divider lines near automation sections (red dividers) ===
    # Convert old integer colors to hex on ALL cnv objects
    if '#X obj' in line and ' cnv ' in line:
        parts = line.rstrip(';\n').split()
        changed = False
        if len(parts) >= 3:
            for i in range(len(parts) - 3, len(parts)):
                if i < len(parts) and parts[i].lstrip('-').isdigit() and int(parts[i]) < 0:
                    hex_color = decode_old_color(parts[i])
                    if hex_color:
                        parts[i] = hex_color
                        changed = True
            if changed:
                line = ' '.join(parts) + ';\n'

    # === HSL/VSL: Fix invisible sliders (bg == fg) and font size 4 → 8 ===
    if '#X obj' in line and (' hsl ' in line or ' vsl ' in line):
        parts = line.rstrip(';\n').split()
        # hsl format: #X obj x y hsl width height min max log init send recv label lx ly lfont lsize bg fg label_color saved steady
        # Find hsl/vsl keyword position
        try:
            sl_pos = parts.index('hsl') if 'hsl' in parts else parts.index('vsl')
        except ValueError:
            return line

        # Parameters after hsl/vsl keyword:
        # 0:width 1:height 2:min 3:max 4:log 5:init 6:send 7:recv 8:label 9:lx 10:ly 11:lfont 12:lsize 13:bg 14:fg 15:label_color 16:saved 17:steady
        params_start = sl_pos + 1
        params = parts[params_start:]

        if len(params) >= 18:
            lfont_idx = params_start + 11
            lsize_idx = params_start + 12
            bg_idx = params_start + 13
            fg_idx = params_start + 14
            lblcolor_idx = params_start + 15

            # Fix font size 4 → 8
            if parts[lsize_idx] == '4':
                parts[lsize_idx] = '8'
                changes.append(f'  {filepath}:{linenum}: slider font size 4 → 8')

            # Fix invisible slider (bg == fg)
            bg = parts[bg_idx]
            fg = parts[fg_idx]
            if bg == fg:
                # Make fg white if bg is dark, or black if bg is light
                if bg in ['#000000', '#040404', '#202020', '#303030']:
                    parts[fg_idx] = '#ffffff'
                else:
                    parts[fg_idx] = '#000000'
                changes.append(f'  {filepath}:{linenum}: invisible slider fixed (bg={bg}, fg was same)')

            # Convert old integer colors to hex
            for ci in [bg_idx, fg_idx, lblcolor_idx]:
                if ci < len(parts) and parts[ci].lstrip('-').isdigit() and int(parts[ci]) < 0:
                    hex_c = decode_old_color(parts[ci])
                    if hex_c:
                        parts[ci] = hex_c

            line = ' '.join(parts) + ';\n'

    # === TGL: Fix font size 4 → 8, convert old colors ===
    if '#X obj' in line and ' tgl ' in line:
        parts = line.rstrip(';\n').split()
        try:
            tgl_pos = parts.index('tgl')
        except ValueError:
            return line
        # tgl format after keyword: size init send recv label lx ly lfont lsize bg fg label_color default steady
        params_start = tgl_pos + 1
        params = parts[params_start:]
        if len(params) >= 14:
            lsize_idx = params_start + 8
            bg_idx = params_start + 9
            fg_idx = params_start + 10
            lblcolor_idx = params_start + 11

            # Fix font size 4 → 8
            if parts[lsize_idx] == '4':
                parts[lsize_idx] = '8'
                changes.append(f'  {filepath}:{linenum}: toggle font size 4 → 8')

            # Convert old colors
            for ci in [bg_idx, fg_idx, lblcolor_idx]:
                if ci < len(parts) and parts[ci].lstrip('-').isdigit() and int(parts[ci]) < 0:
                    hex_c = decode_old_color(parts[ci])
                    if hex_c:
                        parts[ci] = hex_c

            line = ' '.join(parts) + ';\n'

    # === HRADIO: convert old colors ===
    if '#X obj' in line and ' hradio ' in line:
        parts = line.rstrip(';\n').split()
        changed = False
        for i in range(len(parts)):
            if parts[i].lstrip('-').isdigit() and int(parts[i]) < 0 and i > 5:
                hex_c = decode_old_color(parts[i])
                if hex_c:
                    parts[i] = hex_c
                    changed = True
        if changed:
            line = ' '.join(parts) + ';\n'

    # === BNG: convert old colors ===
    if '#X obj' in line and ' bng ' in line:
        parts = line.rstrip(';\n').split()
        changed = False
        for i in range(len(parts)):
            if parts[i].lstrip('-').isdigit() and int(parts[i]) < 0 and i > 5:
                hex_c = decode_old_color(parts[i])
                if hex_c:
                    parts[i] = hex_c
                    changed = True
        if changed:
            line = ' '.join(parts) + ';\n'

    return line


def process_file(filepath):
    """Process a single .pd file."""
    with open(filepath) as f:
        lines = f.readlines()

    changes = []
    new_lines = []
    for i, line in enumerate(lines, 1):
        new_lines.append(fix_line(line, os.path.basename(filepath), i, changes))

    if changes:
        with open(filepath, 'w') as f:
            f.writelines(new_lines)
        print(f'{os.path.basename(filepath)}: {len(changes)} fixes')
        for c in changes:
            print(c)
    else:
        print(f'{os.path.basename(filepath)}: no changes needed')


def main():
    base = os.path.join(os.path.dirname(__file__), '..')
    files = [os.path.join(base, 'console.pd')]
    files += sorted(glob.glob(os.path.join(base, 'modules', '*.pd')))

    for f in files:
        if os.path.exists(f):
            process_file(f)


if __name__ == '__main__':
    main()
