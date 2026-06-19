#!/bin/bash
# BirdNET plugin tests — run from repo root or tests/ directory
# Usage: ./tests/run-tests.sh [audio_file]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

# Use provided audio file or default to example
AUDIO_FILE="${1:-example/sample_0.wav}"

if [ ! -f "$AUDIO_FILE" ]; then
    echo "ERROR: Audio file not found: $AUDIO_FILE"
    echo "Usage: $0 [path/to/audio.wav]"
    exit 1
fi

echo "========================================="
echo " BirdNET Plugin Test Suite"
echo " Audio: $AUDIO_FILE"
echo "========================================="

PASS=0
FAIL=0

run_test() {
    local name="$1"
    shift
    echo ""
    echo "── TEST: $name ──"
    if "$@" 2>&1; then
        echo "✓ PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "✗ FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

# ── Test 1: Basic classification ──
run_test "Basic classification (dry-run)" \
    python3 app.py --input "$AUDIO_FILE" --dry-run --min-confidence 0.25

# ── Test 2: With geo-filtering (Chicago) ──
run_test "Geo-filtered classification (Chicago)" \
    python3 app.py --input "$AUDIO_FILE" --dry-run \
    --lat 41.88 --lon -87.62 --week 22

# ── Test 3: High sensitivity ──
run_test "High sensitivity (1.25)" \
    python3 app.py --input "$AUDIO_FILE" --dry-run \
    --sensitivity 1.25 --min-confidence 0.10

# ── Test 4: CSV output ──
CSV_OUT="/tmp/birdnet_test_$$_results.csv"
run_test "CSV output" \
    python3 app.py --input "$AUDIO_FILE" --dry-run \
    --output "$CSV_OUT"
if [ -f "$CSV_OUT" ]; then
    echo "  CSV rows: $(wc -l < "$CSV_OUT")"
    head -3 "$CSV_OUT"
    rm -f "$CSV_OUT"
fi

# ── Test 5: Overlap between windows ──
run_test "Overlap 1.5s" \
    python3 app.py --input "$AUDIO_FILE" --dry-run \
    --overlap 1.5 --min-confidence 0.30

# ── Test 6: Strict confidence threshold ──
run_test "High confidence threshold (0.50)" \
    python3 app.py --input "$AUDIO_FILE" --dry-run \
    --min-confidence 0.50

# ── Test 7: Module import ──
run_test "Module import check" \
    python3 -c "from app import BirdNETClassifier; print('BirdNETClassifier imported OK')"

# ── Summary ──
echo ""
echo "========================================="
echo " Results: $PASS passed, $FAIL failed"
echo "========================================="

[ "$FAIL" -eq 0 ] || exit 1
