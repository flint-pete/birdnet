#!/usr/bin/env python3
"""
Capture audio from a Mobotix M16 camera via RTSP.

Records from the camera's built-in microphone, saves as a
48kHz mono WAV file ready for BirdNET analysis.

Usage:
    python3 capture-audio.py --ip 130.202.23.119 --user admin --pass PASSWORD --duration 60
"""
import argparse
import subprocess
import sys
import os
from datetime import datetime


def probe_stream(rtsp_url: str):
    """Probe the RTSP stream to show available tracks."""
    print("── Probing RTSP stream...")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", rtsp_url],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if any(k in line for k in ["codec_type", "codec_name", "sample_rate", "channels"]):
                print(f"   {line.strip()}")
        if result.returncode != 0 and result.stderr:
            print(f"   probe stderr: {result.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        print("   (probe timed out — will try capture anyway)")
    except Exception as e:
        print(f"   (probe failed: {e})")
    print()


def capture_audio(rtsp_url: str, duration: int, outfile: str) -> bool:
    """Capture audio from RTSP stream to WAV file."""
    cmd = [
        "ffmpeg", "-y",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # raw PCM
        "-ar", "48000",           # 48kHz (BirdNET native rate)
        "-ac", "1",               # mono
        "-t", str(duration),
        outfile,
    ]
    print(f"── Recording {duration}s of audio...")
    print(f"   cmd: {' '.join(cmd[:6])} ... {outfile}")
    print()

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 30)

    if result.returncode != 0:
        print(f"   ffmpeg stderr:\n{result.stderr[-500:]}")
        return False
    return True


def verify_output(outfile: str):
    """Show info about the captured WAV file."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", outfile],
        capture_output=True, text=True, timeout=10,
    )
    print("── Output file info:")
    for line in result.stdout.splitlines():
        if any(k in line for k in ["codec_name", "sample_rate", "channels", "duration", "size"]):
            print(f"   {line.strip()}")


def main():
    parser = argparse.ArgumentParser(description="Capture audio from Mobotix M16 via RTSP")
    parser.add_argument("--ip", required=True, help="Camera IP address")
    parser.add_argument("--user", default="admin", help="Camera username")
    parser.add_argument("--password", "--pass", dest="password", default="", help="Camera password")
    parser.add_argument("--duration", type=int, default=60, help="Recording duration in seconds")
    parser.add_argument("--output", default="", help="Output filename (auto-generated if empty)")
    parser.add_argument("--rtsp-path", default="mobotix.sdp", help="RTSP path on camera")
    args = parser.parse_args()

    # Build RTSP URL
    if args.password:
        rtsp_url = f"rtsp://{args.user}:{args.password}@{args.ip}/{args.rtsp_path}"
    else:
        rtsp_url = f"rtsp://{args.ip}/{args.rtsp_path}"

    # Output filename
    if args.output:
        outfile = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = f"m16_audio_{ts}.wav"

    print("==========================================")
    print(" Mobotix M16 Audio Capture")
    print("==========================================")
    print(f"  Camera:   {args.ip}")
    print(f"  Duration: {args.duration}s")
    print(f"  RTSP:     rtsp://{args.user}:****@{args.ip}/{args.rtsp_path}")
    print(f"  Output:   {outfile}")
    print()

    # Probe
    probe_stream(rtsp_url)

    # Capture
    if not capture_audio(rtsp_url, args.duration, outfile):
        print()
        print("==========================================")
        print(" ✗ FAILED — ffmpeg returned an error")
        print()
        print(" Troubleshooting:")
        print(f"   1. ping {args.ip}")
        print(f"   2. Try: ffprobe rtsp://{args.user}:****@{args.ip}/{args.rtsp_path}")
        print(f"   3. Try alternate paths: /video1.sdp  /live.sdp  /stream.sdp")
        print(f"   4. Check camera web UI: http://{args.ip}/")
        print("==========================================")
        sys.exit(1)

    # Verify
    if os.path.exists(outfile) and os.path.getsize(outfile) > 1000:
        size = os.path.getsize(outfile)
        print()
        verify_output(outfile)
        print()
        print("==========================================")
        print(f" ✓ DONE: {outfile} ({size:,} bytes)")
        print("==========================================")
    else:
        print()
        print(" ✗ FAILED: output file is missing or too small")
        sys.exit(1)


if __name__ == "__main__":
    main()
