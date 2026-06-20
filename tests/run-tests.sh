#!/bin/bash
# ============================================================
# BirdNET Plugin Test Suite
#
# Validates that BirdNET V2.4 correctly identifies North American
# bird species in test audio files. Each test checks:
#   1. The top-1 species (highest confidence) matches expected
#   2. The confidence is within ±5% of the reference value
#
# Usage:
#   ./tests/run-tests.sh              # run natively (needs venv)
#   ./tests/run-tests.sh --docker     # run in Docker container
#
# Exit code: 0 if all tests pass, 1 if any fail.
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
AUDIO_DIR="$SCRIPT_DIR/audio"
cd "$REPO_DIR"

USE_DOCKER=false
if [[ "${1:-}" == "--docker" ]]; then
    USE_DOCKER=true
fi

# Check for test audio
if [ ! -d "$AUDIO_DIR" ] || [ -z "$(ls "$AUDIO_DIR"/*.wav "$AUDIO_DIR"/*.mp3 2>/dev/null)" ]; then
    echo "ERROR: No test audio files found in $AUDIO_DIR"
    echo "Run: python3 tests/download_test_audio.py"
    exit 1
fi

if $USE_DOCKER; then
    if ! docker image inspect birdnet-species:0.1.0 >/dev/null 2>&1; then
        echo "ERROR: Docker image birdnet-species:0.1.0 not found"
        echo "Run: docker build -t birdnet-species:0.1.0 ."
        exit 1
    fi
fi

PASS=0
FAIL=0
TOTAL=0
TOLERANCE=0.05  # 5% absolute tolerance

# ── Expected results ────────────────────────────────────────
# Format: file|expected_top1_species|expected_confidence
# These are the top-1 species (highest confidence across all
# 3-second chunks) from the reference manifest.
EXPECTED=(
    "barred_owl.mp3|Strix varia|0.9999"
    "eastern_bluebird.mp3|Sialia sialis|0.9999"
    "search_sample.mp3|Cyanocitta cristata|0.9970"
    "original_XC563936_-_Soundscape.mp3|Junco hyemalis|0.9906"
    "original_sample_1.mp3|Junco hyemalis|0.9401"
    "soundscape.mp3|Poecile atricapillus|0.8395"
    "original_sample_0.mp3|Melanerpes formicivorus|0.7705"
    "original_XC558716_-_Soundscape.mp3|Geothlypis tolmiei|0.6675"
    "yellow_warbler.mp3|Setophaga petechia|0.6216"
)

echo "=========================================================="
echo " BirdNET Plugin Test Suite"
echo " Tolerance: ±${TOLERANCE} (5%)"
if $USE_DOCKER; then
    echo " Mode: Docker (birdnet-species:0.1.0)"
else
    echo " Mode: Native (Python venv)"
fi
echo "=========================================================="

for entry in "${EXPECTED[@]}"; do
    IFS='|' read -r file expected_species expected_conf <<< "$entry"
    TOTAL=$((TOTAL + 1))

    audio_path="$AUDIO_DIR/$file"
    if [ ! -f "$audio_path" ]; then
        echo ""
        echo "── TEST $TOTAL: $file ──"
        echo "   SKIP: file not found"
        continue
    fi

    echo ""
    echo "── TEST $TOTAL: $file ──"
    echo "   Expect: $expected_species @ ${expected_conf}"

    # Run classifier and capture CSV output to a temp file
    CSV_TMP=$(mktemp /tmp/birdnet_test_XXXXXX.csv)
    rm -f "$CSV_TMP"  # remove so app.py writes header

    if $USE_DOCKER; then
        # Mount audio dir and write CSV inside it (shared volume)
        CSV_NAME="__test_result_$$.csv"
        docker run --rm \
            -v "$AUDIO_DIR:/data" \
            birdnet-species:0.1.0 \
            --input "/data/$file" --dry-run \
            --min-confidence 0.10 --output "/data/$CSV_NAME" >/dev/null 2>&1
        cp "$AUDIO_DIR/$CSV_NAME" "$CSV_TMP" 2>/dev/null || true
        rm -f "$AUDIO_DIR/$CSV_NAME"
    else
        python3 app.py --input "$audio_path" --dry-run \
            --min-confidence 0.10 --output "$CSV_TMP" >/dev/null 2>&1
    fi

    # Parse CSV to find top-1 species (highest confidence)
    result=$(python3 -c "
import csv, sys

tolerance = $TOLERANCE
expected_species = '$expected_species'
expected_conf = $expected_conf

best = None
try:
    with open('$CSV_TMP') as f:
        first_line = f.readline().strip()
        f.seek(0)
        # Detect if there's a header
        if first_line.startswith('audio_file,'):
            reader = csv.DictReader(f)
            for row in reader:
                conf = float(row['confidence'])
                species = row['scientific_name']
                if best is None or conf > best[1]:
                    best = (species, conf)
        else:
            # No header — columns are: audio_file,start,end,sci,common,conf
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 6:
                    species = row[3]
                    conf = float(row[5])
                    if best is None or conf > best[1]:
                        best = (species, conf)
except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)

if best is None:
    print('NO_DETECTIONS')
    sys.exit(0)

got_species, got_conf = best
species_ok = (got_species == expected_species)
conf_diff = abs(got_conf - expected_conf)
conf_ok = (conf_diff <= tolerance)

if species_ok and conf_ok:
    print(f'PASS|{got_species}|{got_conf:.4f}|{conf_diff:.4f}')
elif not species_ok:
    print(f'FAIL_SPECIES|{got_species}|{got_conf:.4f}|{conf_diff:.4f}')
else:
    print(f'FAIL_CONF|{got_species}|{got_conf:.4f}|{conf_diff:.4f}')
")

    rm -f "$CSV_TMP"

    # Parse result
    IFS='|' read -r status got_species got_conf conf_diff <<< "$result"

    case "$status" in
        PASS)
            echo "   Got:    $got_species @ $got_conf  (drift: $conf_diff)"
            echo "   ✓ PASS"
            PASS=$((PASS + 1))
            ;;
        FAIL_SPECIES)
            echo "   Got:    $got_species @ $got_conf"
            echo "   ✗ FAIL — wrong species (expected $expected_species)"
            FAIL=$((FAIL + 1))
            ;;
        FAIL_CONF)
            echo "   Got:    $got_species @ $got_conf  (drift: $conf_diff)"
            echo "   ✗ FAIL — confidence outside ±${TOLERANCE} tolerance"
            FAIL=$((FAIL + 1))
            ;;
        NO_DETECTIONS)
            echo "   Got:    NO DETECTIONS"
            echo "   ✗ FAIL"
            FAIL=$((FAIL + 1))
            ;;
        *)
            echo "   $result"
            echo "   ✗ FAIL — unexpected error"
            FAIL=$((FAIL + 1))
            ;;
    esac
done

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "=========================================================="
if [ "$FAIL" -eq 0 ]; then
    echo " ✓ PASS — $PASS/$TOTAL tests passed"
else
    echo " ✗ FAIL — $PASS passed, $FAIL failed out of $TOTAL"
fi
echo "=========================================================="

[ "$FAIL" -eq 0 ] || exit 1
