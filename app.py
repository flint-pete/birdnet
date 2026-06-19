"""
BirdNET Audio Species Classifier Plugin for Sage/Waggle

Records audio from the node microphone (or reads audio files), runs
BirdNET V2.4 inference (6,522 species — birds, frogs, insects), and
publishes per-species detections with confidence scores.

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


# ── audio recording ─────────────────────────────────────────────────
def record_audio(duration_s: float, sample_rate: int = 48000) -> str:
    """Record audio from the Waggle microphone and return path to WAV file."""
    from waggle.data.audio import Microphone

    mic = Microphone(samplerate=sample_rate)
    logger.info("Recording %g seconds of audio at %d Hz...", duration_s, sample_rate)
    sample = mic.record(duration_s)

    tmpdir = tempfile.mkdtemp(prefix="birdnet_")
    wav_path = os.path.join(tmpdir, "recording.wav")
    sample.save(wav_path)
    logger.info("Audio saved to %s", wav_path)
    return wav_path


# ── publishing ──────────────────────────────────────────────────────
def publish_detections(plugin, detections: list[dict], timestamp: int):
    """Publish detections to Waggle."""
    # Publish individual species detections
    for det in detections:
        # Normalize scientific name for topic: lowercase, underscores
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
        logger.info(
            "  %s (%s): %.4f [%.1f-%.1fs]",
            det["scientific_name"],
            det["common_name"],
            det["confidence"],
            det["start_time"],
            det["end_time"],
        )

    # Publish a JSON summary
    if detections:
        # Group by species, keep highest confidence
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


# ── main loop ───────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BirdNET V2.4 audio species classifier for Sage/Waggle",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Audio input
    audio = parser.add_argument_group("audio input")
    audio.add_argument(
        "--input", "-i",
        help="Path to audio file or directory. If not specified, records from microphone.",
    )
    audio.add_argument(
        "--duration", type=float, default=15.0,
        help="Recording duration in seconds (microphone mode).",
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
        help="Seconds between recording cycles (0 = run once).",
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
    )

    # Use Plugin context if not dry-run
    if args.dry_run:
        logger.info("DRY RUN — will not publish to Waggle")

    # Import Plugin only when needed (allows testing without pywaggle)
    if not args.dry_run:
        from waggle.plugin import Plugin
        plugin_ctx = Plugin()
    else:
        plugin_ctx = None

    def run_once():
        """Record/read audio, classify, publish."""
        timestamp = int(time.time_ns())

        # Get audio
        if args.input:
            audio_path = args.input
            cleanup = False
        else:
            audio_path = record_audio(args.duration, args.sample_rate)
            cleanup = True

        try:
            # Classify
            t0 = time.time()
            detections = classifier.classify_file(audio_path)
            elapsed = time.time() - t0

            logger.info(
                "Classified %s: %d detections in %.2fs",
                os.path.basename(audio_path), len(detections), elapsed,
            )

            # Publish
            if detections:
                if plugin_ctx is not None:
                    publish_detections(plugin_ctx, detections, timestamp)
                else:
                    # Dry-run: just log
                    for det in detections:
                        logger.info(
                            "  %s (%s): %.4f [%.1f-%.1fs]",
                            det["scientific_name"],
                            det["common_name"],
                            det["confidence"],
                            det["start_time"],
                            det["end_time"],
                        )
            else:
                logger.info("  No detections above threshold %.2f", args.min_confidence)

            # Save CSV if requested
            if args.output and detections:
                _save_csv(detections, args.output, audio_path)

            return detections

        finally:
            if cleanup and os.path.exists(audio_path):
                import shutil
                shutil.rmtree(os.path.dirname(audio_path), ignore_errors=True)

    # Main loop
    try:
        if plugin_ctx is not None:
            with plugin_ctx as plugin:
                # Reassign so publish_detections uses the entered context
                nonlocal_hack = {"plugin": plugin}

                # Monkey-patch plugin_ctx for publish_detections
                orig_run = run_once

                def run_with_plugin():
                    timestamp = int(time.time_ns())
                    if args.input:
                        audio_path = args.input
                        cleanup = False
                    else:
                        audio_path = record_audio(args.duration, args.sample_rate)
                        cleanup = True

                    try:
                        t0 = time.time()
                        detections = classifier.classify_file(audio_path)
                        elapsed = time.time() - t0
                        logger.info(
                            "Classified %s: %d detections in %.2fs",
                            os.path.basename(audio_path), len(detections), elapsed,
                        )
                        if detections:
                            publish_detections(plugin, detections, timestamp)
                        else:
                            logger.info("  No detections above threshold %.2f", args.min_confidence)
                        if args.output and detections:
                            _save_csv(detections, args.output, audio_path)
                        return detections
                    finally:
                        if cleanup and os.path.exists(audio_path):
                            import shutil
                            shutil.rmtree(os.path.dirname(audio_path), ignore_errors=True)

                if args.interval > 0:
                    cycle = 0
                    while True:
                        cycle += 1
                        logger.info("── Cycle %d ──", cycle)
                        run_with_plugin()
                        logger.info("Sleeping %.1fs...", args.interval)
                        time.sleep(args.interval)
                else:
                    run_with_plugin()
        else:
            # Dry-run mode
            if args.interval > 0:
                cycle = 0
                while True:
                    cycle += 1
                    logger.info("── Cycle %d ──", cycle)
                    run_once()
                    logger.info("Sleeping %.1fs...", args.interval)
                    time.sleep(args.interval)
            else:
                run_once()

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
