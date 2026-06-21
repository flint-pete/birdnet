# Docker Build Guide

## Quick Build

```bash
docker build -t birdnet-species:0.1.1 .
```

Build takes ~5-10 minutes. The Dockerfile:
1. Starts from `python:3.12-slim` (aarch64 or amd64)
2. Installs ffmpeg and libsndfile1 for audio processing
3. Installs Python deps (birdnet, librosa, pywaggle)
4. Pre-downloads BirdNET V2.4 acoustic + geo models (~125 MB)
5. Copies app.py

## Image Size

Expect ~2-3 GB due to TensorFlow (pulled in by birdnet).

## Test Run

```bash
# Dry-run with a test audio file
docker run --rm \
  -v $(pwd)/tests/audio:/data \
  birdnet-species:0.1.1 \
  --input /data/search_sample.mp3 --dry-run

# With geo-filtering (Chicago)
docker run --rm \
  -v $(pwd)/tests/audio:/data \
  birdnet-species:0.1.1 \
  --input /data/soundscape.wav --dry-run \
  --lat 41.88 --lon -87.62 --week 22
```

## Multi-Arch

The image builds natively on both aarch64 (DGX Spark, Thor) and
amd64 (standard x86 servers). No cross-compilation needed — the
`python:3.12-slim` base and all pip packages have native wheels
for both architectures.

## Model Storage

BirdNET models are pre-downloaded into the container at build time:
- Acoustic model V2.4 (TFLite FP32): ~77 MB
- Geo model V2.4: ~46 MB

Stored at `/root/.local/share/birdnet/` inside the container.
No internet access needed at runtime.

## Notes

- **CPU-only inference.** The birdnet library on ARM64 uses TFLite
  (CPU). GPU inference via TensorFlow ProtoBuf is not supported on
  ARM64 in the standard package. CPU inference is fast enough for
  real-time on 3-second audio chunks (proven on Raspberry Pi 4).
- **No NVIDIA base image needed.** Unlike sage-yolo and sage-bioclip
  (which need GPU), BirdNET runs on CPU. This means simpler builds,
  smaller images, and no CUDA dependency.
