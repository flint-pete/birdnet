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


## Production: Scheduled SES Cron Jobs on Thor (arm64)

Production deployment is a scheduler-managed one-shot cron job (every
10 min), not a hand-deployed `pluginctl` pod. Capture audio → classify →
publish → exit, each cycle.

### BirdNET is the easy case — but the registry push still blocks you

Unlike sage-yolo / sage-bioclip, **BirdNET does NOT use the NVIDIA base
image** — it's `python:3.12-slim` with native arm64 + amd64 wheels. So the
QEMU-crash problem that kills the ECR portal build for the GPU plugins
does **not** apply here: the ECR portal *could* build BirdNET arm64
cleanly.

**However**, the second blocker still bites: you cannot `docker push` your
own image to `registry.sagecontinuum.org`. A Sage portal access token
logs in fine but is **read/pull-only** — pushes return
`denied: requested access to the resource is denied`. Registry writes are
reserved for the Jenkins build pipeline.

So you have two viable paths for BirdNET:

#### Path A — ECR portal build (works for BirdNET, since no NVIDIA/QEMU)

1. Portal → My Apps → Create App → `https://github.com/flint-pete/birdnet`
2. Register and Build. Because the base is `python:3.12-slim`, the arm64
   build should succeed (no `import torch` / QEMU crash).
3. Make the app **public** (else SES returns `registry does not exist in ECR`).
4. Create + submit the job (see below). This is the cleanest path and
   avoids the manual sideload entirely — prefer it for BirdNET.

#### Path B — build locally on Thor + sideload (same as the GPU plugins)

Use this if the portal build is unavailable or you want to test a local
build immediately. SES pods use `imagePullPolicy: IfNotPresent`, so a
locally-cached image tagged with the exact registry path is used without
pulling from the registry.

```bash
# 1. Build natively on Thor, tagged with the FULL registry path
cd ~/AI-projects/birdnet
git pull
sudo docker build -t registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 .

# 2. Sideload into k3s containerd
sudo docker save registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 \
  | sudo k3s ctr images import -

# 3. Verify (look for io.cri-containerd.image=managed)
sudo k3s ctr images ls | grep birdnet-species
```

The app still needs to exist in the ECR **catalog** (metadata) so the SES
scheduler's validation passes — register it via the portal even if you
sideload the actual image.

### Create + submit the SES cron job

Needs a write-scoped SES token in your interactive shell. The job YAML
(`jobs/birdnet-reolink.yaml`) already points at `:0.1.1`:

```bash
sesctl --server https://es.sagecontinuum.org --token "$SES_USER_TOKEN" \
    create -f jobs/birdnet-reolink.yaml      # returns a numeric job ID
sesctl --server https://es.sagecontinuum.org --token "$SES_USER_TOKEN" \
    submit -j <job-id>
```

### Verify it fires and publishes (the heartbeat)

The pod appears in the `ses` namespace each tick, runs ~30-40s, exits,
and is GC'd — invisible between ticks. As of 0.1.1 the plugin publishes
`env.detection.audio.summary` **every cycle** (a heartbeat with
`total_detections: 0` on quiet cycles), so the data API can confirm
liveness even when no birds are detected:

```bash
curl -s -X POST https://data.sagecontinuum.org/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"start":"-30m","filter":{"vsn":"H00F","name":"env.detection.audio.summary"}}'
```

A record every ~10 min = the job is alive. Per-species topics
(`env.detection.audio.<scientific_name>`) appear only on actual detections.

### Systemic fix (escalate to the ECR/cyberinfra team)

The registry-push denial and (for the GPU plugins) the QEMU arm64 build
crash both trace to the same gap. The durable fix is either:

- **(a)** Grant push/write access to `registry.sagecontinuum.org/beckman/`
  for a Sage portal token, so `docker push` works after a native build; or
- **(b)** Add a **native arm64 build node** to the Jenkins ECR pipeline.

Either removes the manual sideload step for all Thor-targeted plugins.

See: https://sagecontinuum.org/docs/tutorials/edge-apps/publishing-to-ecr
