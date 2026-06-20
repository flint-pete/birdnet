"""
BirdNET Audio Species Classifier Plugin for Sage/Waggle

Records audio from the node microphone, a network camera, or reads
audio files, then runs BirdNET V2.4 inference (6,522 species — birds,
frogs, insects) and publishes per-species detections with confidence.

Audio sources (in priority order):
  --input FILE     Read from a local audio file
  --camera URL     Capture from a network camera via ffmpeg
                   e.g. 'http://user:pass@IP/control/faststream.jpg?stream=MxPEG&needlength'
  (default)        Record from the node's USB microphone via pywaggle

Uses eBird geo-filtering when --lat/--lon are provided to restrict
predictions to species expected at the node's location and time.

Model: BirdNET V2.4 (EfficientNetB0-like, 77 MB TFLite FP32, 0.826 GFLOPs)
Audio: 3-second chunks at 48 kHz, dual mel-spectrograms

Measurement topics:
  env.detection.audio.<scientific_name>  — confidence (0–1) per species
  env.detection.audio.summary            — JSON summary of all detections
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("birdnet-species")


# ── classifier ──────────────────────────────────────────────────────
class BirdNETClassifier:
    """Wraps the birdnet library for Sage plugin use."""

    def __init__(
        self,
        min_confidence: float = 0.25,
        sensitivity: float = 1.0,
        overlap: float = 0.0,
        top_k: int = 5,
        lat: float = -1.0,
        lon: float = -1.0,
        week: int = -1,
        sf_thresh: float = 0.03,
        bandpass_fmin: int = 0,
        bandpass_fmax: int = 15000,
        batch_size: int = 1,
    ):
        import birdnet

        self.min_confidence = min_confidence
        self.sensitivity = sensitivity
        self.overlap = overlap
        self.top_k = top_k
        self.lat = lat
        self.lon = lon
        self.week = week
        self.sf_thresh = sf_thresh
        self.bandpass_fmin = bandpass_fmin
        self.bandpass_fmax = bandpass_fmax
        self.batch_size = batch_size

        # Load acoustic model (auto-downloads on first use)
        logger.info("Loading BirdNET V2.4 acoustic model...")
        self.model = birdnet.load("acoustic", "2.4", "tf")
        logger.info(
            "Acoustic model loaded (sample rate: %d Hz)",
            self.model.get_sample_rate(),
        )

        # Build species filter from geo model if coordinates provided
        self.species_filter = None
        if lat > -1 and lon > -1:
            logger.info(
                "Loading geo model for species filtering (%.4f, %.4f, week=%s)...",
                lat, lon, week if week > 0 else "all",
            )
            geo = birdnet.load("geo", "2.4", "tf")
            geo_week = week if 1 <= week <= 48 else None
            species_result = geo.predict(
                lat, lon, week=geo_week, min_confidence=sf_thresh,
            )
            self.species_filter = species_result.to_set()
            logger.info(
                "Geo filter: %d species expected at this location/time",
                len(self.species_filter),
            )

    def classify_file(self, audio_path: str) -> list[dict]:
        """Classify an audio file. Returns list of detection dicts."""
        predictions = self.model.predict(
            audio_path,
            top_k=self.top_k,
            overlap_duration_s=self.overlap,
            apply_sigmoid=True,
            sigmoid_sensitivity=self.sensitivity,
            default_confidence_threshold=self.min_confidence,
            custom_species_list=self.species_filter,
            bandpass_fmin=self.bandpass_fmin,
            bandpass_fmax=self.bandpass_fmax,
            batch_size=self.batch_size,
        )

        df = predictions.to_dataframe()
        if df.empty:
            return []

        detections = []
        for _, row in df.iterrows():
            species_name = row["species_name"]
            parts = species_name.split("_", 1)
            scientific = parts[0] if len(parts) > 0 else species_name
            common = parts[1] if len(parts) > 1 else ""

            detections.append({
                "scientific_name": scientific,
                "common_name": common,
                "confidence": float(row["confidence"]),
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]),
            })

        return detections


# ── audio sources ───────────────────────────────────────────────────
def record_from_microphone(duration_s: float, sample_rate: int = 48000) -> str:
    """Record audio from the node's USB microphone via pywaggle."""
    from waggle.data.audio import Microphone

    mic = Microphone(samplerate=sample_rate)
    logger.info("Recording %g seconds from USB microphone at %d Hz...", duration_s, sample_rate)
    sample = mic.record(duration_s)

    tmpdir = tempfile.mkdtemp(prefix="birdnet_")
    wav_path = os.path.join(tmpdir, "recording.wav")
    sample.save(wav_path)
    logger.info("Audio saved to %s", wav_path)
    return wav_path


def record_from_camera(url: str, duration_s: float, sample_rate: int = 48000) -> str:
    """Capture audio from a network camera via ffmpeg.

    Supports any ffmpeg-compatible source URL:
      - Mobotix MxPEG:  http://user:pass@IP/control/faststream.jpg?stream=MxPEG&needlength
      - RTSP:           rtsp://user:pass@IP/profile1/media.smp
      - HTTP streams:   http://IP/audio.cgi
    """
    tmpdir = tempfile.mkdtemp(prefix="birdnet_")
    wav_path = os.path.join(tmpdir, "camera_audio.wav")

    # Detect Mobotix MxPEG streams — need -f mxg input format
    input_args = []
    if "faststream" in url and "MxPEG" in url:
        input_args = ["-f", "mxg"]
    elif url.startswith("rtsp://"):
        input_args = ["-rtsp_transport", "tcp"]

    cmd = (
        ["ffmpeg", "-y"]
        + input_args
        + ["-i", url,
           "-vn",                     # no video
           "-acodec", "pcm_s16le",    # raw PCM output
           "-ar", str(sample_rate),   # resample to target rate
           "-ac", "1",               # mono
           "-t", str(duration_s),
           wav_path]
    )

    # Log the command without credentials
    safe_url = url.split("@")[-1] if "@" in url else url
    logger.info("Capturing %g seconds from camera %s...", duration_s, safe_url)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=int(duration_s) + 30,
    )

    if result.returncode != 0:
        logger.error("ffmpeg failed (exit %d): %s", result.returncode, result.stderr[-300:])
        raise RuntimeError(f"ffmpeg failed to capture audio from camera: {result.stderr[-200:]}")

    if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000:
        raise RuntimeError("ffmpeg produced no audio output — check camera URL and credentials")

    size = os.path.getsize(wav_path)
    logger.info("Camera audio saved to %s (%d bytes)", wav_path, size)
    return wav_path


# ── publishing ──────────────────────────────────────────────────────
def publish_detections(plugin, detections: list[dict], timestamp: int):
    """Publish detections to Waggle."""
    for det in detections:
        topic_name = det["scientific_name"].lower().replace(" ", "_")
        plugin.publish(
            f"env.detection.audio.{topic_name}",
            det["confidence"],
            timestamp=timestamp,
            meta={
                "common_name": det["common_name"],
                "start_time_s": det["start_time"],
                "end_time_s": det["end_time"],
            },
        )

    if detections:
        species_best = {}
        for det in detections:
            key = det["scientific_name"]
            if key not in species_best or det["confidence"] > species_best[key]["confidence"]:
                species_best[key] = det

        summary = {
            "total_detections": len(detections),
            "unique_species": len(species_best),
            "species": [
                {
                    "scientific_name": d["scientific_name"],
                    "common_name": d["common_name"],
                    "confidence": round(d["confidence"], 4),
                }
                for d in sorted(species_best.values(), key=lambda x: x["confidence"], reverse=True)
            ],
        }
        plugin.publish(
            "env.detection.audio.summary",
            json.dumps(summary),
            timestamp=timestamp,
        )


# ── CLI ─────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BirdNET V2.4 audio species classifier for Sage/Waggle",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Audio input
    audio = parser.add_argument_group("audio input")
    audio.add_argument(
        "--input", "-i",
        help="Path to audio file or directory. If not specified, records from microphone or camera.",
    )
    audio.add_argument(
        "--camera",
        help="URL for network camera audio. Supports Mobotix MxPEG, RTSP, or any ffmpeg source. "
             "Example: 'http://user:pass@IP/control/faststream.jpg?stream=MxPEG&needlength'",
    )
    audio.add_argument(
        "--duration", type=float, default=15.0,
        help="Recording duration in seconds (microphone or camera mode).",
    )
    audio.add_argument(
        "--sample-rate", type=int, default=48000,
        help="Audio sample rate in Hz.",
    )

    # Model parameters
    model = parser.add_argument_group("model parameters")
    model.add_argument(
        "--min-confidence", type=float, default=0.25,
        help="Minimum confidence threshold (0.01–0.99).",
    )
    model.add_argument(
        "--sensitivity", type=float, default=1.0,
        help="Detection sensitivity (0.5–1.5). Higher = more sensitive.",
    )
    model.add_argument(
        "--overlap", type=float, default=0.0,
        help="Overlap in seconds between 3-second analysis windows (0.0–2.9).",
    )
    model.add_argument(
        "--top-k", type=int, default=5,
        help="Max predictions per 3-second chunk.",
    )
    model.add_argument(
        "--bandpass-fmin", type=int, default=0,
        help="Bandpass filter minimum frequency in Hz. Useful to cut low-frequency noise.",
    )
    model.add_argument(
        "--bandpass-fmax", type=int, default=15000,
        help="Bandpass filter maximum frequency in Hz. Set to match audio source "
             "(e.g. 4000 for 8kHz camera mic, 15000 for full-bandwidth USB mic).",
    )
    model.add_argument(
        "--batch-size", type=int, default=1,
        help="Number of 3-second chunks to process in parallel. Increase for long recordings.",
    )

    # Location filtering
    loc = parser.add_argument_group("location filtering (eBird)")
    loc.add_argument(
        "--lat", type=float, default=-1,
        help="Latitude for species range filtering. -1 to disable.",
    )
    loc.add_argument(
        "--lon", type=float, default=-1,
        help="Longitude for species range filtering. -1 to disable.",
    )
    loc.add_argument(
        "--week", type=int, default=-1,
        help="Week of year (1–48) for seasonal filtering. -1 for year-round.",
    )
    loc.add_argument(
        "--sf-thresh", type=float, default=0.03,
        help="Species filter threshold for geo model (0.0–1.0).",
    )

    # Runtime
    runtime = parser.add_argument_group("runtime")
    runtime.add_argument(
        "--interval", type=float, default=0.0,
        help="Seconds between recording cycles. 0 = run once (or --num-recordings times).",
    )
    runtime.add_argument(
        "--num-recordings", type=int, default=1,
        help="Number of recording cycles to run. 0 = loop forever (requires --interval > 0).",
    )
    runtime.add_argument(
        "--output", "-o",
        help="Path to save CSV results (optional).",
    )
    runtime.add_argument(
        "--dry-run", action="store_true",
        help="Run without publishing to Waggle (for testing).",
    )

    return parser


def _get_audio(args) -> tuple[str, bool]:
    """Get audio from the configured source. Returns (path, needs_cleanup)."""
    if args.input:
        return args.input, False
    elif args.camera:
        return record_from_camera(args.camera, args.duration, args.sample_rate), True
    else:
        return record_from_microphone(args.duration, args.sample_rate), True


def _log_detections(detections: list[dict]):
    """Log detections to console."""
    for det in detections:
        logger.info(
            "  %s (%s): %.4f [%.1f-%.1fs]",
            det["scientific_name"],
            det["common_name"],
            det["confidence"],
            det["start_time"],
            det["end_time"],
        )


def main():
    parser = build_parser()
    args = parser.parse_args()

    # Clamp parameters to valid ranges
    args.min_confidence = max(0.01, min(args.min_confidence, 0.99))
    args.sensitivity = max(0.5, min(args.sensitivity, 1.5))
    args.overlap = max(0.0, min(args.overlap, 2.9))

    logger.info("BirdNET Species Classifier starting")
    logger.info(
        "  min_confidence=%.2f  sensitivity=%.1f  overlap=%.1f  top_k=%d",
        args.min_confidence, args.sensitivity, args.overlap, args.top_k,
    )
    if args.input:
        logger.info("  source=file (%s)", args.input)
    elif args.camera:
        safe_url = args.camera.split("@")[-1] if "@" in args.camera else args.camera
        logger.info("  source=camera (%s)", safe_url)
    else:
        logger.info("  source=microphone (USB)")
    if args.lat > -1 and args.lon > -1:
        logger.info("  location=(%.4f, %.4f)  week=%s", args.lat, args.lon,
                     args.week if args.week > 0 else "all")

    # Initialize classifier
    classifier = BirdNETClassifier(
        min_confidence=args.min_confidence,
        sensitivity=args.sensitivity,
        overlap=args.overlap,
        top_k=args.top_k,
        lat=args.lat,
        lon=args.lon,
        week=args.week,
        sf_thresh=args.sf_thresh,
        bandpass_fmin=args.bandpass_fmin,
        bandpass_fmax=args.bandpass_fmax,
        batch_size=args.batch_size,
    )

    if args.dry_run:
        logger.info("DRY RUN — will not publish to Waggle")

    def run_cycle(plugin=None):
        """Single record-classify-publish cycle."""
        timestamp = int(time.time_ns())
        audio_path, cleanup = _get_audio(args)

        try:
            t0 = time.time()
            detections = classifier.classify_file(audio_path)
            elapsed = time.time() - t0

            logger.info(
                "Classified %s: %d detections in %.2fs",
                os.path.basename(audio_path), len(detections), elapsed,
            )

            if detections:
                if plugin is not None:
                    publish_detections(plugin, detections, timestamp)
                _log_detections(detections)
            else:
                logger.info("  No detections above threshold %.2f", args.min_confidence)

            if args.output and detections:
                _save_csv(detections, args.output, audio_path)

            return detections

        finally:
            if cleanup and os.path.exists(audio_path):
                shutil.rmtree(os.path.dirname(audio_path), ignore_errors=True)

    def run_loop(plugin=None):
        """Run recording cycles based on --num-recordings and --interval.

        --num-recordings 1  --interval 0    Run once and exit (default)
        --num-recordings 6  --interval 5    Run 6 cycles, 5s gap between each
        --num-recordings 0  --interval 60   Loop forever, 60s between cycles
        """
        num = args.num_recordings
        if num == 0 and args.interval <= 0:
            logger.error("--num-recordings 0 (loop forever) requires --interval > 0")
            sys.exit(1)

        cycle = 0
        while True:
            cycle += 1
            if num > 1 or num == 0:
                logger.info("── Cycle %d%s ──", cycle,
                            f"/{num}" if num > 0 else "")
            run_cycle(plugin)

            # Check if we've done enough
            if num > 0 and cycle >= num:
                break

            # Sleep between cycles
            if args.interval > 0:
                logger.info("Sleeping %.1fs...", args.interval)
                time.sleep(args.interval)
            elif num > 1:
                # Multiple recordings with no explicit interval — no gap
                pass

    try:
        if args.dry_run:
            run_loop(plugin=None)
        else:
            from waggle.plugin import Plugin
            with Plugin() as plugin:
                run_loop(plugin=plugin)
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down")


def _save_csv(detections: list[dict], output_path: str, audio_path: str):
    """Append detections to a CSV file."""
    write_header = not os.path.exists(output_path)
    with open(output_path, "a") as f:
        if write_header:
            f.write("audio_file,start_time,end_time,scientific_name,common_name,confidence\n")
        for det in detections:
            f.write(
                f"{audio_path},{det['start_time']},{det['end_time']},"
                f"{det['scientific_name']},{det['common_name']},{det['confidence']:.4f}\n"
            )
    logger.info("Results appended to %s", output_path)


if __name__ == "__main__":
    main()
