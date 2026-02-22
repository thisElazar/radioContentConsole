#!/usr/bin/env bash
#
# post-session.sh — Normalize, convert to MP3, tag, and sort recorded WAV files.
#
# Usage:
#   ./scripts/post-session.sh
#   ./scripts/post-session.sh --skip-normalize
#   ./scripts/post-session.sh --station "Delta Community Radio"
#
# Reads export/raw/manifest.txt, processes each listed WAV file.
# Requires: ffmpeg (with libmp3lame)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$TOOLKIT_DIR/export/raw/manifest.txt"
RAW_DIR="$TOOLKIT_DIR/export/raw"

# Defaults
SKIP_NORMALIZE=false
STATION_NAME="Station"
TARGET_LUFS=-16
TARGET_TP=-1
TARGET_LRA=11

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-normalize)
            SKIP_NORMALIZE=true
            shift
            ;;
        --station)
            STATION_NAME="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--skip-normalize] [--station \"Station Name\"]"
            echo ""
            echo "Processes WAV files listed in export/raw/manifest.txt:"
            echo "  1. Two-pass loudness normalization (-16 LUFS, -1 dBTP)"
            echo "  2. MP3 conversion (320 kbps CBR)"
            echo "  3. ID3 tagging (title, artist, album, genre, comment, year)"
            echo "  4. Sorts into export subdirectories by asset type"
            echo ""
            echo "Options:"
            echo "  --skip-normalize   Skip loudness normalization"
            echo "  --station NAME     Station name for ID3 artist tag (default: \"Station\")"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Check dependencies
if ! command -v ffmpeg &>/dev/null; then
    echo "Error: ffmpeg is not installed or not in PATH." >&2
    exit 1
fi

# Check manifest exists
if [[ ! -f "$MANIFEST" ]]; then
    echo "No manifest found at $MANIFEST"
    echo "Record some audio in the toolkit first, then run this script."
    exit 0
fi

# Map asset type to export subdirectory
asset_type_to_dir() {
    local asset_type="$1"
    case "$asset_type" in
        Jingle)         echo "jingles" ;;
        Sweeper)        echo "sweepers" ;;
        Stinger)        echo "stingers" ;;
        Bumper)         echo "bumpers" ;;
        Bed)            echo "beds" ;;
        "Station ID Bed"|"Station-ID") echo "station-id" ;;
        "PSA Bed"|PSA)  echo "psa" ;;
        "Promo Bed"|Promo) echo "promos" ;;
        *)              echo "other" ;;
    esac
}

# Two-pass loudnorm normalization
normalize_file() {
    local input="$1"
    local output="$2"

    echo "  Analyzing loudness..."
    # Pass 1: measure
    local analysis
    analysis=$(ffmpeg -hide_banner -i "$input" \
        -af "loudnorm=I=${TARGET_LUFS}:TP=${TARGET_TP}:LRA=${TARGET_LRA}:print_format=json" \
        -f null - 2>&1 | grep -A 20 '"input_' | head -20)

    local measured_I measured_TP measured_LRA measured_thresh offset
    measured_I=$(echo "$analysis" | grep '"input_i"' | grep -o '[-0-9.]*')
    measured_TP=$(echo "$analysis" | grep '"input_tp"' | grep -o '[-0-9.]*')
    measured_LRA=$(echo "$analysis" | grep '"input_lra"' | grep -o '[-0-9.]*')
    measured_thresh=$(echo "$analysis" | grep '"input_thresh"' | grep -o '[-0-9.]*')
    offset=$(echo "$analysis" | grep '"target_offset"' | grep -o '[-0-9.]*')

    if [[ -z "$measured_I" || -z "$measured_TP" || -z "$measured_LRA" || -z "$measured_thresh" || -z "$offset" ]]; then
        echo "  Warning: Could not parse loudnorm analysis. Copying without normalization."
        cp "$input" "$output"
        return
    fi

    echo "  Normalizing to ${TARGET_LUFS} LUFS / ${TARGET_TP} dBTP..."
    # Pass 2: normalize
    ffmpeg -hide_banner -y -i "$input" \
        -af "loudnorm=I=${TARGET_LUFS}:TP=${TARGET_TP}:LRA=${TARGET_LRA}:measured_I=${measured_I}:measured_TP=${measured_TP}:measured_LRA=${measured_LRA}:measured_thresh=${measured_thresh}:offset=${offset}:linear=true" \
        -ar 44100 "$output" 2>/dev/null
}

# Process each line in the manifest
processed=0
failed=0
echo "========================================"
echo "Station Audio Toolkit — Post-Session"
echo "========================================"
echo "Station: $STATION_NAME"
echo "Normalize: $(if $SKIP_NORMALIZE; then echo 'SKIP'; else echo 'Yes (-16 LUFS)'; fi)"
echo ""

while IFS='|' read -r filename asset_type timestamp; do
    # Skip empty lines and comments
    [[ -z "$filename" || "$filename" == \#* ]] && continue

    # Trim whitespace
    filename=$(echo "$filename" | xargs)
    asset_type=$(echo "$asset_type" | xargs)
    timestamp=$(echo "$timestamp" | xargs)

    wav_path="$RAW_DIR/$filename"

    if [[ ! -f "$wav_path" ]]; then
        echo "SKIP: $filename (file not found)"
        ((failed++)) || true
        continue
    fi

    echo "Processing: $filename ($asset_type)"

    # Determine output directory
    subdir=$(asset_type_to_dir "$asset_type")
    out_dir="$TOOLKIT_DIR/export/$subdir"
    mkdir -p "$out_dir"

    # Base name without extension
    base="${filename%.wav}"
    mp3_name="${base}.mp3"
    mp3_path="$out_dir/$mp3_name"

    # Step 1: Normalize (or skip)
    if $SKIP_NORMALIZE; then
        normalized_wav="$wav_path"
    else
        normalized_wav=$(mktemp /tmp/tk-norm-XXXXXX.wav)
        normalize_file "$wav_path" "$normalized_wav"
    fi

    # Step 2 + 3: Convert to MP3 with ID3 tags
    local_date=$(echo "$timestamp" | cut -d' ' -f1 2>/dev/null || date +%Y-%m-%d)
    local_year=$(echo "$local_date" | cut -d'-' -f1 2>/dev/null || date +%Y)

    echo "  Converting to MP3 (320k CBR) with ID3 tags..."
    ffmpeg -hide_banner -y -i "$normalized_wav" \
        -codec:a libmp3lame -b:a 320k -ar 44100 \
        -metadata title="$base" \
        -metadata artist="$STATION_NAME" \
        -metadata album="Station Audio Elements" \
        -metadata genre="$asset_type" \
        -metadata comment="Generated ${local_date} via Station Audio Toolkit" \
        -metadata date="$local_year" \
        "$mp3_path" 2>/dev/null

    # Clean up temp file
    if ! $SKIP_NORMALIZE && [[ "$normalized_wav" == /tmp/tk-norm-* ]]; then
        rm -f "$normalized_wav"
    fi

    echo "  -> $subdir/$mp3_name"
    ((processed++)) || true

done < "$MANIFEST"

echo ""
echo "========================================"
echo "Done. $processed file(s) processed, $failed skipped."
echo "Output directories:"
for d in jingles sweepers stingers bumpers beds station-id psa promos other; do
    count=$(find "$TOOLKIT_DIR/export/$d" -name '*.mp3' 2>/dev/null | wc -l | xargs)
    if [[ "$count" -gt 0 ]]; then
        echo "  export/$d/ — $count file(s)"
    fi
done
echo ""
echo "The export/ directory (minus raw/) is ready for LibreTime upload."
