#!/bin/bash
# Test audio capture from Reolink RLC-811A on H00F
#
# Run from H00F to determine the right audio source and quality.
#
# Step 1: Find the RTSP port
#   The HTTP API is on port 10000 (mapped). RTSP may be on 554 (unmapped)
#   or on a different mapped port. Check the Reolink web UI under
#   Settings > Network > Port Settings for the RTSP port.
#
# Step 2: Test RTSP audio stream
#   Replace RTSP_URL with the actual URL (try these in order):
#
#   # Direct RTSP (if port 554 is reachable):
#   RTSP_URL="rtsp://sage:SageCam!@10.107.0.221/Preview_01_main"
#
#   # Port-mapped RTSP (if mapped, e.g. to 10554):
#   RTSP_URL="rtsp://sage:SageCam!@10.107.0.221:10554/Preview_01_main"
#
# Step 3: Probe the stream to check audio codec/sample rate
#   ffprobe -v quiet -show_streams "$RTSP_URL" 2>&1 | grep -E "codec|sample_rate|channels"
#
# Step 4: Capture test audio (30 seconds)
#   ffmpeg -rtsp_transport tcp -i "$RTSP_URL" -vn -acodec pcm_s16le -ar 48000 -ac 1 -t 30 reolink_test.wav
#
# Step 5: Run BirdNET on it
#   python3 ~/birdnet/app.py --input reolink_test.wav --min-confidence 0.25 --dry-run -o reolink_results.csv
#
# Step 6: If RTSP works, test the --camera flag end-to-end
#   python3 ~/birdnet/app.py --camera "$RTSP_URL" --duration 30 --min-confidence 0.50 --dry-run
#
# Audio quality comparison:
#   Mobotix M16:    pcm_alaw 8 kHz (4 kHz Nyquist) — poor for birdsong
#   Reolink 811A:   AAC-LC 16 kHz (8 kHz Nyquist) — better, covers most passerines
#   USB mic (ETS):  PCM 48 kHz (24 kHz Nyquist) — best, full bandwidth

echo "=== Reolink Audio Test ==="
echo ""
echo "First, check if RTSP port 554 is reachable from H00F:"
echo "  nc -zv 10.107.0.221 554 2>&1"
echo ""
echo "If not, check the HTTP API for port info:"
echo '  curl -s "http://10.107.0.221:10000/api.cgi?cmd=GetNetPort&user=sage&password=PASS" -d '\''[{"cmd":"GetNetPort","action":0,"param":{"channel":0}}]'\'''
echo ""
echo "Then follow the steps above to test audio capture."
