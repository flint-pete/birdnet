#!/bin/bash
# ============================================================
# fetch-listen-clip.sh — Grab a clip from the Reolink hummingcam
#   so a HUMAN can listen to exactly what BirdNET hears.
#
# WHY THIS EXISTS
# ---------------
# BirdNET can be "running" (pods fire, audio captured, no errors) yet detect
# zero birds. Before assuming the model is wrong, LISTEN to the audio: the
# Reolink mic is faint and has no gain control, and the sub-stream is only
# 16 kHz — so real birds may simply be too quiet/narrowband to detect. This
# script captures a clip with the SAME ffmpeg path the plugin uses
# (record_from_camera in app.py), so what you hear is what the model gets.
#
# It produces TWO files:
#   1. <name>.wav   — faithful capture (mono, matches the plugin: pcm_s16le).
#                     This is the ground truth of what BirdNET receives.
#   2. <name>.mp3   — same audio as MP3 for easy playback / sharing
#                     (per project convention, MP3 not WAV for shared assets).
# Optionally also an AMPLIFIED mp3 (--gain) so faint sounds are audible to
# you — this is for HUMAN listening only; it does NOT change what the plugin
# captures.
#
# USAGE
#   ./fetch-listen-clip.sh [DURATION_SEC] [GAIN_DB] [OUTNAME]
#
#   DURATION_SEC  length to record   (default 60)
#   GAIN_DB       extra dB for the *_amplified.mp3 (default 0 = skip)
#   OUTNAME       base file name      (default listen_<timestamp>)
#
# EXAMPLES
#   ./fetch-listen-clip.sh                 # 60s clip, wav + mp3
#   ./fetch-listen-clip.sh 30              # 30s clip
#   ./fetch-listen-clip.sh 60 20           # 60s + a +20 dB amplified mp3
#   ./fetch-listen-clip.sh 60 0 dawn-test  # named output
#
# Run this ON the node (node-H00F.sage) where the camera is reachable, OR
# from anywhere that can reach the camera IP. Then copy the mp3 back:
#   scp beckman@node-H00F.sage:~/AI-projects/birdnet/<name>.mp3 .
# ============================================================
set -euo pipefail

# ── Camera config — H00F Reolink RLC-811A hummingcam ────────────────
# Reolink FLV/BCS: credentials MUST be query params (NOT http://user:pass@…).
# Sub-stream audio is 16 kHz. Override CAMERA_URL via env to use another node.
CAMERA_URL="${CAMERA_URL:-http://10.107.0.221:10000/flv?port=1935&app=bcs&stream=channel0_sub.bcs&user=sage&password=SageCam!}"
SAMPLE_RATE="${SAMPLE_RATE:-48000}"   # plugin resamples to 48k; keep it identical

DURATION="${1:-60}"
GAIN_DB="${2:-0}"
OUTNAME="${3:-listen_$(date +%Y%m%d_%H%M%S)}"

WAV="${OUTNAME}.wav"
MP3="${OUTNAME}.mp3"
AMP="${OUTNAME}_amplified.mp3"

# Hide credentials when echoing the URL
SAFE_URL="${CAMERA_URL%%\?*}?…<creds hidden>"

echo "=========================================="
echo " Reolink hummingcam — listen clip"
echo "=========================================="
echo "  Source:   $SAFE_URL"
echo "  Duration: ${DURATION}s   Sample rate: ${SAMPLE_RATE} Hz (mono)"
echo "  Gain:     ${GAIN_DB} dB (amplified mp3 only; 0 = skip)"
echo "  Output:   $WAV  +  $MP3"
echo ""

# ── Probe what the stream actually offers (codec / rate / channels) ──
echo "── Probing stream..."
ffprobe -v error -show_streams "$CAMERA_URL" 2>&1 \
    | grep -E "codec_type|codec_name|sample_rate|channels|bit_rate" \
    || echo "  (probe inconclusive — continuing to capture anyway)"
echo ""

# ── Capture — identical ffmpeg path to app.py record_from_camera ────
echo "── Recording ${DURATION}s (this is exactly what BirdNET receives)..."
ffmpeg -y \
    -i "$CAMERA_URL" \
    -vn \
    -acodec pcm_s16le \
    -ar "$SAMPLE_RATE" \
    -ac 1 \
    -t "$DURATION" \
    "$WAV" 2>&1 | tail -4

if [ ! -f "$WAV" ] || [ "$(stat -c%s "$WAV" 2>/dev/null || stat -f%z "$WAV")" -lt 1000 ]; then
    echo ""
    echo " ✗ FAILED: no usable audio captured."
    echo "   • Check the camera is reachable:  curl -s -o /dev/null -w '%{http_code}' '${CAMERA_URL%%\?*}'"
    echo "   • Reolink needs query-param auth (&user=&password=), NOT http://user:pass@…"
    echo "   • ffmpeg 'End of file'/exit 187 == basic-auth attempt; use query params."
    exit 1
fi

# ── Make a normal MP3 (faithful, just re-encoded for playback) ──────
ffmpeg -y -i "$WAV" -codec:a libmp3lame -qscale:a 2 "$MP3" 2>&1 | tail -1

# ── Optional amplified MP3 for human listening (does NOT affect model) ─
if [ "$GAIN_DB" != "0" ]; then
    echo "── Building +${GAIN_DB} dB amplified mp3 for easier listening..."
    ffmpeg -y -i "$WAV" -filter:a "volume=${GAIN_DB}dB" \
        -codec:a libmp3lame -qscale:a 2 "$AMP" 2>&1 | tail -1
fi

# ── Report level stats so you can SEE how quiet it is ───────────────
echo ""
echo "── Audio level stats (mean/max volume — tells you if the mic is too quiet):"
ffmpeg -i "$WAV" -af volumedetect -f null /dev/null 2>&1 \
    | grep -E "mean_volume|max_volume" || true

SIZE=$(stat -c%s "$WAV" 2>/dev/null || stat -f%z "$WAV")
echo ""
echo "=========================================="
echo " ✓ DONE"
echo "   WAV (what BirdNET hears): $(pwd)/$WAV  ($(numfmt --to=iec "$SIZE" 2>/dev/null || echo "${SIZE}B"))"
echo "   MP3 (listen/share):       $(pwd)/$MP3"
[ "$GAIN_DB" != "0" ] && echo "   MP3 amplified (+${GAIN_DB}dB): $(pwd)/$AMP"
echo ""
echo " Copy the mp3 to your machine to listen:"
echo "   scp beckman@node-H00F.sage:$(pwd)/$MP3 ."
echo "=========================================="
