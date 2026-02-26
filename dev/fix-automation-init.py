#!/usr/bin/env python3
"""Fix automation panel sliders: set INIT=1 with sensible defaults.

Problem: rate and depth sliders had INIT=0, so param-lfo never received
initial values. With rate=0, phase never advances (no modulation).
With depth=0, modulation amplitude is zero.

Fix: INIT=1, rate default ~1Hz (position 5653), depth default 50% (position 4000).
"""

import re
from pathlib import Path

modules_dir = Path(__file__).parent.parent / "modules"

# Pattern for automation rate sliders:
# hsl 100 12 0.05 10 1 0 $0-gui-lfo-*-rate $0-lfo-*-rate empty ... 0 1;
# Need: change INIT (field 6 after hsl) from 0→1, default (second-to-last) from 0→5653
RATE_PAT = re.compile(
    r'(#X obj \d+ \d+ hsl 100 12 0\.05 10 1 )0'  # INIT 0→1
    r'( \$0-gui-lfo-\S+-rate \$0-lfo-\S+-rate )'
    r'(empty -2 -8 10 -262144 -1 -1 )0( 1;)'      # default 0→5653
)

# Pattern for automation depth sliders:
# hsl 80 12 0 100 0 0 $0-gui-lfo-*-depth $0-lfo-*-depth empty ... 0 1;
# Need: change INIT from 0→1, default from 0→4000
DEPTH_PAT = re.compile(
    r'(#X obj \d+ \d+ hsl 80 12 0 100 0 )0'       # INIT 0→1
    r'( \$0-gui-lfo-\S+-depth \$0-lfo-\S+-depth )'
    r'(empty -2 -8 10 -262144 -1 -1 )0( 1;)'       # default 0→4000
)

total_rate = 0
total_depth = 0

for pd_file in sorted(modules_dir.glob("*.pd")):
    content = pd_file.read_text()
    if "param-lfo" not in content:
        continue

    new_content = content
    rate_count = len(RATE_PAT.findall(new_content))
    depth_count = len(DEPTH_PAT.findall(new_content))

    new_content = RATE_PAT.sub(r'\g<1>1\g<2>\g<3>5653\g<4>', new_content)
    new_content = DEPTH_PAT.sub(r'\g<1>1\g<2>\g<3>4000\g<4>', new_content)

    if new_content != content:
        pd_file.write_text(new_content)
        print(f"  {pd_file.name}: {rate_count} rate + {depth_count} depth sliders fixed")
        total_rate += rate_count
        total_depth += depth_count
    else:
        print(f"  {pd_file.name}: no changes needed")

print(f"\nTotal: {total_rate} rate + {total_depth} depth sliders updated")
