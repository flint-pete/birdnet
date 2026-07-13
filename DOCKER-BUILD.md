# Docker Build Guide

> **Status (2026-07-10):** The Thor/arm64 ECR build blocker (buildkit
> `/proc/acpi` runc bug) is **fixed** — birdnet is now built by the standard
> ECR "Register and Build" pipeline (release 0.2.1, from git tag `v0.2.1`) and
> runs as an official SES job. The local-build + side-load path below is kept
> for local testing and as a historical fallback, not the primary deploy route.
> Remaining known platform notes are tracked in
> `~/AI-projects/sage-design-planning/Infra-problems-to-fix.md`.

## Quick Build

```bash
docker build -t birdnet-species:0.2.1 .
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
  birdnet-species:0.2.1 \
  --input /data/search_sample.mp3 --dry-run

# With geo-filtering (Chicago)
docker run --rm \
  -v $(pwd)/tests/audio:/data \
  birdnet-species:0.2.1 \
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

This is the production deployment path — a scheduler-managed one-shot
cron job (every 10 min) instead of a hand-deployed continuous pod. It
replaces the `pluginctl deploy` approach, which dies on reboot and is
invisible to the scheduler. Capture audio → classify → publish → exit,
each cycle.

### Deploy path: ECR "Register and Build" (standard)

The Thor buildkit bug is fixed, so birdnet deploys the standard way:

1. **Tag the release** (version must match `sage.yaml`):
   ```bash
   git tag -a v0.2.1 -m "birdnet-species 0.2.1" && git push origin v0.2.1
   ```
2. **Register + Build** via the ECR portal (Portal → My Apps → birdnet-species →
   add version from GitHub) or `scripts/register-ecr-version.py`. ECR builds
   `linux/arm64` from `flint-pete/birdnet` using `sage.yaml` + `Dockerfile`
   (`python:3.12-slim`, CPU-only — no CUDA/QEMU path). Make the app **public**.
3. **Create + submit the SES cron job:**
   ```bash
   sesctl --server https://es.sagecontinuum.org --token "$SES_USER_TOKEN" \
       create -f jobs/birdnet-reolink.yaml      # returns a numeric job ID
   sesctl --server https://es.sagecontinuum.org --token "$SES_USER_TOKEN" \
       submit -j <job-id>
   ```
   > `create` uses `-f`/`--file-path`; `submit` takes `-j <numeric-id>` (not the
   > name). `rm -s <id>` suspends, `rm <id>` removes.
4. **Verify it fires and publishes** (see below).

**Currently deployed:** job `birdnet-reolink` (id 5678), image
`registry.sagecontinuum.org/beckman/birdnet-species:0.2.1`, on H00F, `*/10` cron.

### Verifying it fires and publishes (the heartbeat)

The pod appears in the `ses` namespace each tick, runs ~30-40s, exits (one-shot),
and is GC'd — so it's invisible between ticks. Confirm via the data API instead.
Since 0.2.0 the plugin publishes `env.detection.audio.summary` **every cycle**
(a heartbeat with `total_detections: 0` on quiet cycles), so the data API
confirms liveness even when no birds are detected:

```bash
curl -s -X POST https://data.sagecontinuum.org/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"start":"-30m","filter":{"vsn":"H00F","name":"env.detection.audio.summary"}}'
```

A record every ~10 min = the job is alive. Per-species topics
(`env.detection.audio.<scientific_name>`) appear only on actual detections. The
record metadata identifies the job/image: `"job": "birdnet-species-<id>"` and
`"plugin": "registry.sagecontinuum.org/beckman/birdnet-species:0.2.1"`.

### Re-deploying after a code change (new version)

Bump the version everywhere (`sage.yaml`, `Makefile`, job YAML), tag it, push the
tag, and re-Register and Build in ECR. Update the job YAML's `image:` to the new
tag and re-submit. No node-local steps needed.

### Local build + side-load (historical fallback — normally NOT needed)

> Retained for local testing and offline/air-gapped bring-up. Not the deploy
> route now that ECR builds birdnet. It was the workaround while the Thor build
> was broken (buildkit `/proc/acpi` runc bug + pull-only portal tokens).

<details>
<summary>Expand: build natively on the node → import into k3s</summary>

Build on the node (arm64, no QEMU) tagged with the FULL registry path, import
into k3s containerd (SES uses `imagePullPolicy: IfNotPresent`, so a locally
present image under the exact tag is used without a registry pull), then register
a catalog metadata record so SES validation passes:

```bash
cd ~/AI-projects/birdnet && git pull
sudo docker build -t registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 .
sudo docker save registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 \
  | sudo k3s ctr images import -
sudo k3s ctr images ls | grep birdnet-species:0.2.1   # expect io.cri-containerd.image=managed

# catalog metadata record (only needed for a deliberately side-loaded image):
python3 scripts/register-ecr-version.py \
    --namespace beckman --name birdnet-species \
    --from-version 0.2.0 --version 0.2.1 \
    --git-url https://github.com/flint-pete/birdnet.git \
    --token "$SAGE_TOKEN"
```

Then create + submit the job as usual. The pod events show *"already present on
machine"*, confirming the side-loaded image was used.
</details>

See: https://sagecontinuum.org/docs/tutorials/edge-apps/publishing-to-ecr
