#!/usr/bin/env bash
#
# Double-click this file to process your recorded WAVs into
# broadcast-ready MP3s in the EXPORTS/ folder.
#

# Navigate to the toolkit directory (where this file lives)
cd "$(dirname "$0")"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   91.9 KXST — Export Session Audio   ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Check for bash 4+ (needed for the post-session script)
bash_version="${BASH_VERSINFO[0]}"
if [[ "$bash_version" -lt 4 ]]; then
    if [[ -x /opt/homebrew/bin/bash ]]; then
        exec /opt/homebrew/bin/bash "$0" "$@"
    elif [[ -x /usr/local/bin/bash ]]; then
        exec /usr/local/bin/bash "$0" "$@"
    else
        echo "  This tool requires Bash 4+."
        echo "  Install it with: brew install bash"
        echo ""
        echo "  Press any key to close."
        read -n 1 -s
        exit 1
    fi
fi

# Check for ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "  This tool requires ffmpeg."
    echo "  Install it with: brew install ffmpeg"
    echo ""
    echo "  Press any key to close."
    read -n 1 -s
    exit 1
fi

# Run the post-session script
./scripts/post-session.sh

echo ""
echo "  Press any key to close."
read -n 1 -s
