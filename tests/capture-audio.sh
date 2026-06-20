#!/bin/bash
# ============================================================
# capture-audio.sh — Grab audio from a Mobotix M16 camera
#
# Records audio from the camera's built-in microphone via RTSP,
# saves as a WAV file for quality evaluation.
#
# Usage:
#   ./capture-audio.sh CAMERA_IP [DURATION] [USER] [PASS]
#
# Examples:
#   ./capture-audio.sh 10.31.81.20
#   ./capture-audio.sh 10.31.81.20 30
#   ./capture-audio.sh 10.31.81.20 15 admin mypassword
#
# Output: audio_YYYYMMDD_HHMMSS.wav in current directory
# ============================================================
set -euo pipefail

CAMERA_IP="${1:?Usage: $0 CAMERA_IP [DURATION_SEC] [USER] [PASS]}"
DURATION="${2:-15}"
USER="${3:-admin}"
PASS="${4:-}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTFILE="audio_${TIMESTAMP}.wav"

# Mobotix RTSP URL (standard path)
if [ -n "$PASS" ]; then
    RTSP_URL="rtsp://${USER}:${PASS}@${CAMERA_IP}/mobotix.sdp"
else
    RTSP_URL="rtsp://${CAMERA_IP}/mobotix.sdp"
fi

echo "=========================================="
echo " Mobotix M16 Audio Capture"
echo "=========================================="
echo "  Camera:   $CAMERA_IP"
echo "  Duration: ${DURATION}s"
echo "  Output:   $OUTFILE"
echo ""

# First, probe the stream to see what's available
echo "── Probing RTSP stream..."
ffprobe -v error -show_streams "$RTSP_URL" 2>&1 | \
    grep -E "codec_type|codec_name|sample_rate|channels|bit_rate" || \
    echo "  (probe failed — will try capture anyway)"
echo ""

# Capture audio only, convert to 48kHz mono WAV (BirdNET-ready)
echo "── Recording ${DURATION}s of audio..."
ffmpeg -y \
    -rtsp_transport tcp \
    -i "$RTSP_URL" \
    -vn \
    -acodec pcm_s16le \
    -ar 48000 \
    -ac 1 \
    -t "$DURATION" \
    "$OUTFILE" 2>&1 | tail -5

if [ -f "$OUTFILE" ]; then
    SIZE=$(stat -c%s "$OUTFILE" 2>/dev/null || stat -f%z "$OUTFILE" 2>/dev/null)
    echo ""
    echo "── Verifying output..."
    ffprobe -v error -show_format -show_streams "$OUTFILE" 2>&1 | \
        grep -E "codec_name|sample_rate|channels|duration|bit_rate|size"
    echo ""
    echo "=========================================="
    echo " ✓ DONE: $OUTFILE ($(numfmt --to=iec $SIZE 2>/dev/null || echo "${SIZE} bytes"))"
    echo ""
    echo " To copy back to your machine:"
    echo "   scp beckman@node-H00F.sage:$(pwd)/$OUTFILE ."
    echo "=========================================="
else
    echo ""
    echo "=========================================="
    echo " ✗ FAILED: No output file produced"
    echo ""
    echo " Troubleshooting:"
    echo "   1. Check camera IP: ping $CAMERA_IP"
    echo "   2. Try alternate RTSP paths:"
    echo "      rtsp://$CAMERA_IP/mobotix.sdp"
    echo "      rtsp://$CAMERA_IP/video1.sdp"
    echo "      rtsp://$CAMERA_IP:554/live.sdp"
    echo "   3. Check credentials (user/pass)"
    echo "   4. Verify audio is enabled in camera web UI"
    echo "=========================================="
    exit 1
fi
