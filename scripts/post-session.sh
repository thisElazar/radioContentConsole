#!/usr/bin/env bash
#
# post-session.sh — Scan recorded WAVs, normalize, convert to MP3, tag, and
#                   export to EXPORTS/ with a tracking manifest.
#
# Usage:
#   ./scripts/post-session.sh
#   ./scripts/post-session.sh --skip-normalize
#   ./scripts/post-session.sh --station "Delta Community Radio"
#   ./scripts/post-session.sh --force            # reprocess everything
#
# Scans export/<type>/ directories for WAV files recorded by the console,
# processes them into EXPORTS/<type>/*.mp3, and maintains EXPORTS/manifest.txt
# to track what's been processed. If a WAV is moved to a different type folder,
# the next run detects the change and reprocesses with the updated genre tag.
#
# Requires: ffmpeg (with libmp3lame), md5sum or md5

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
EXPORT_SRC="$TOOLKIT_DIR/export"
EXPORT_DST="$TOOLKIT_DIR/EXPORTS"
MANIFEST="$EXPORT_DST/manifest.txt"

# Asset type directories the console writes to
ASSET_DIRS=(jingles stingers sweepers beds bumpers station-id promos psa other)

# Defaults
SKIP_NORMALIZE=false
FORCE=false
STATION_NAME="91.9 KXST"
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
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--skip-normalize] [--station \"Station Name\"] [--force]"
            echo ""
            echo "Scans export/<type>/ for WAV files and processes them:"
            echo "  1. Two-pass loudness normalization (-16 LUFS, -1 dBTP)"
            echo "  2. MP3 conversion (320 kbps CBR)"
            echo "  3. ID3 tagging (title, artist, album, genre, comment, year)"
            echo "  4. Outputs to EXPORTS/<type>/ with tracking manifest"
            echo ""
            echo "Options:"
            echo "  --skip-normalize   Skip loudness normalization"
            echo "  --station NAME     Station name for ID3 artist tag (default: \"Station\")"
            echo "  --force            Reprocess all files, even if unchanged"
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

# Cross-platform md5
file_md5() {
    if command -v md5sum &>/dev/null; then
        md5sum "$1" | cut -d' ' -f1
    else
        md5 -q "$1"
    fi
}

# Map directory name back to genre tag for ID3
dir_to_genre() {
    case "$1" in
        jingles)    echo "Jingle" ;;
        stingers)   echo "Stinger" ;;
        sweepers)   echo "Sweeper" ;;
        beds)       echo "Bed" ;;
        bumpers)    echo "Bumper" ;;
        station-id) echo "Station ID" ;;
        promos)     echo "Promo" ;;
        psa)        echo "PSA" ;;
        other)      echo "Other" ;;
        *)          echo "Other" ;;
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

# Load existing manifest into associative arrays
declare -A MANIFEST_MD5      # keyed by source relative path
declare -A MANIFEST_GENRE    # keyed by source relative path
declare -A MANIFEST_MP3      # keyed by source relative path

load_manifest() {
    if [[ ! -f "$MANIFEST" ]]; then
        return
    fi
    while IFS='|' read -r src_rel mp3_rel genre processed_date checksum; do
        [[ -z "$src_rel" || "$src_rel" == \#* ]] && continue
        src_rel=$(echo "$src_rel" | xargs)
        mp3_rel=$(echo "$mp3_rel" | xargs)
        genre=$(echo "$genre" | xargs)
        checksum=$(echo "$checksum" | xargs)
        MANIFEST_MD5["$src_rel"]="$checksum"
        MANIFEST_GENRE["$src_rel"]="$genre"
        MANIFEST_MP3["$src_rel"]="$mp3_rel"
    done < "$MANIFEST"
}

# Ensure EXPORTS directory exists
mkdir -p "$EXPORT_DST"

# Load previous manifest
load_manifest

# Collect new manifest lines as we go
declare -a NEW_MANIFEST_LINES=()

processed=0
skipped=0
updated=0

echo "========================================"
echo "Station Audio Toolkit — Post-Session"
echo "========================================"
echo "Station: $STATION_NAME"
echo "Normalize: $(if $SKIP_NORMALIZE; then echo 'SKIP'; else echo 'Yes (-16 LUFS)'; fi)"
echo "Force: $(if $FORCE; then echo 'Yes'; else echo 'No'; fi)"
echo ""

# Scan each asset type directory for WAVs
for type_dir in "${ASSET_DIRS[@]}"; do
    src_dir="$EXPORT_SRC/$type_dir"
    [[ -d "$src_dir" ]] || continue

    for wav_path in "$src_dir"/*.wav; do
        [[ -f "$wav_path" ]] || continue

        filename=$(basename "$wav_path")
        base="${filename%.wav}"
        src_rel="export/$type_dir/$filename"
        genre=$(dir_to_genre "$type_dir")

        # Compute checksum of source WAV
        current_md5=$(file_md5 "$wav_path")

        # Check if already processed and unchanged
        prev_md5="${MANIFEST_MD5[$src_rel]:-}"
        prev_genre="${MANIFEST_GENRE[$src_rel]:-}"
        prev_mp3="${MANIFEST_MP3[$src_rel]:-}"

        needs_processing=false
        reason=""

        if $FORCE; then
            needs_processing=true
            reason="forced"
        elif [[ -z "$prev_md5" ]]; then
            needs_processing=true
            reason="new"
        elif [[ "$current_md5" != "$prev_md5" ]]; then
            needs_processing=true
            reason="modified"
        elif [[ "$genre" != "$prev_genre" ]]; then
            needs_processing=true
            reason="reclassified ($prev_genre -> $genre)"
            # Note: old MP3 at previous path is left in place for manual cleanup
        elif [[ -n "$prev_mp3" && ! -f "$TOOLKIT_DIR/$prev_mp3" ]]; then
            needs_processing=true
            reason="mp3 missing"
        fi

        # Output paths
        dst_dir="$EXPORT_DST/$type_dir"
        mp3_name="${base}.mp3"
        mp3_path="$dst_dir/$mp3_name"
        mp3_rel="EXPORTS/$type_dir/$mp3_name"

        if ! $needs_processing; then
            # Still record in new manifest
            local_date="${MANIFEST_MD5[$src_rel]+$(date -r "$wav_path" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)}"
            # Preserve existing manifest line
            NEW_MANIFEST_LINES+=("$src_rel | $mp3_rel | $genre | $(date -r "$wav_path" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d) | $current_md5")
            ((skipped++)) || true
            continue
        fi

        echo "Processing: $src_rel [$reason]"
        mkdir -p "$dst_dir"

        # Step 1: Normalize (or skip)
        if $SKIP_NORMALIZE; then
            normalized_wav="$wav_path"
        else
            normalized_wav=$(mktemp /tmp/tk-norm-XXXXXX.wav)
            normalize_file "$wav_path" "$normalized_wav"
        fi

        # Get date from file modification time
        local_date=$(date -r "$wav_path" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
        local_year=$(echo "$local_date" | cut -d'-' -f1)

        # Step 2: Convert to MP3 with ID3 tags
        echo "  Converting to MP3 (320k CBR) with ID3 tags..."
        echo "    title=$base | artist=$STATION_NAME | genre=$genre"
        ffmpeg -hide_banner -y -i "$normalized_wav" \
            -codec:a libmp3lame -b:a 320k -ar 44100 \
            -metadata title="$base" \
            -metadata artist="$STATION_NAME" \
            -metadata album="Station Audio Elements" \
            -metadata genre="$genre" \
            -metadata comment="Generated ${local_date} in Pure Data via Station Audio Toolkit" \
            -metadata date="$local_year" \
            "$mp3_path" 2>/dev/null

        # Clean up temp file
        if ! $SKIP_NORMALIZE && [[ "$normalized_wav" == /tmp/tk-norm-* ]]; then
            rm -f "$normalized_wav"
        fi

        echo "  -> $mp3_rel"

        # Step 3: Archive the source WAV so the filename slot is free
        archive_dir="$src_dir/archived"
        mkdir -p "$archive_dir"
        mv "$wav_path" "$archive_dir/$filename"
        archived_rel="export/$type_dir/archived/$filename"
        echo "  Archived: $archived_rel"

        NEW_MANIFEST_LINES+=("$archived_rel | $mp3_rel | $genre | $local_date | $current_md5")

        if [[ -n "$prev_md5" ]]; then
            ((updated++)) || true
        else
            ((processed++)) || true
        fi
    done
done

# Carry forward previously processed entries from the old manifest
for src_rel in "${!MANIFEST_MP3[@]}"; do
    # Check if this entry was already re-added during processing above
    found=false
    for line in "${NEW_MANIFEST_LINES[@]}"; do
        if [[ "$line" == "$src_rel |"* ]]; then
            found=true
            break
        fi
    done
    if ! $found; then
        # Preserve the old manifest entry as-is
        mp3_rel="${MANIFEST_MP3[$src_rel]}"
        genre="${MANIFEST_GENRE[$src_rel]}"
        md5="${MANIFEST_MD5[$src_rel]}"
        local_date=$(date -r "$TOOLKIT_DIR/$src_rel" +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
        NEW_MANIFEST_LINES+=("$src_rel | $mp3_rel | $genre | $local_date | $md5")
    fi
done

# Write new manifest
{
    echo "# Station Audio Toolkit — Export Manifest"
    echo "# Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "# Format: source_wav | mp3_path | genre | processed_date | md5"
    echo "#"
    for line in "${NEW_MANIFEST_LINES[@]}"; do
        echo "$line"
    done
} > "$MANIFEST"

echo ""
echo "========================================"
echo "Done."
echo "  New:              $processed"
echo "  Reprocessed:     $updated"
echo "  Skipped:         $skipped"
echo ""
echo "Export contents:"
for d in "${ASSET_DIRS[@]}"; do
    dst="$EXPORT_DST/$d"
    if [[ -d "$dst" ]]; then
        count=$(find "$dst" -name '*.mp3' 2>/dev/null | wc -l | xargs)
        if [[ "$count" -gt 0 ]]; then
            echo "  EXPORTS/$d/ — $count file(s)"
        fi
    fi
done
echo ""
echo "EXPORTS/ is ready for LibreTime upload."
