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

This is the production deployment path — a scheduler-managed one-shot
cron job (every 10 min) instead of a hand-deployed continuous pod. It
replaces the `pluginctl deploy` approach, which dies on reboot and is
invisible to the scheduler. Capture audio → classify → publish → exit,
each cycle.

### Why you build locally and sideload (not the ECR portal)

The documented Sage workflow is "Create App → Register and Build App" and
the ECR portal builds the image from your GitHub repo. For Thor-targeted
plugins that path is unreliable, for two reasons:

- **The portal build can't make arm64 NVIDIA images.** The ECR/Jenkins
  pipeline runs on **x86_64** and cross-builds `linux/arm64` under **QEMU
  emulation**, which crashes on the NVIDIA base image (`signal 6 / exit
  134`). BirdNET itself uses `python:3.12-slim` (CPU-only) so it does not
  hit the QEMU crash — but sage-yolo and sage-bioclip do, and we keep all
  three plugins on one identical deploy path so there is **one procedure to
  learn**, not a special case per plugin.
- **You cannot `docker push` to the registry.** A Sage portal access token
  logs in fine but is **read/pull-only**; pushes return
  `denied: requested access to the resource is denied`. Registry writes are
  reserved for the Jenkins pipeline.

So the reliable, uniform path for every Thor plugin is: build natively on
Thor, tag with the full registry path, and sideload into k3s. This works
because SES pods use **`imagePullPolicy: IfNotPresent`** — the scheduler
uses a locally-cached image if one is already present in k3s containerd
under the exact registry-qualified name, and never has to pull.

### Step 1 — build natively on Thor (arm64, no QEMU)

```bash
cd ~/AI-projects/birdnet
git pull
sudo docker build -t registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 .
```

Note the tag is the **full registry path**, not the bare
`birdnet-species:0.1.1`. This must exactly match the `image:` field in the
job YAML so k3s finds the cached copy.

### Step 2 — sideload into k3s containerd

```bash
sudo docker save registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 \
  | sudo k3s ctr images import -
```

### Step 3 — verify it landed (and is CRI-managed)

```bash
sudo k3s ctr images ls | grep birdnet-species
# Expect registry.sagecontinuum.org/beckman/birdnet-species:0.1.1
# with io.cri-containerd.image=managed  (that label = k8s/SES can see it)
```

### Step 4 — register the app in the ECR portal (metadata only)

The app must exist in the ECR *catalog* so the SES scheduler's validation
passes (SES checks the app catalog, not the raw Docker registry). The
portal *build* may fail or be skipped — that's fine, we only need the app +
version record registered. Make the app **public** or SES returns
`registry does not exist in ECR`.

### Step 5 — create + submit the SES cron job

Needs a write-scoped SES token in your interactive shell. The job YAML
(`jobs/birdnet-reolink.yaml`) already points at `:0.1.1`:

```bash
sesctl --server https://es.sagecontinuum.org --token "$SES_USER_TOKEN" \
    create -f jobs/birdnet-reolink.yaml      # returns a numeric job ID
sesctl --server https://es.sagecontinuum.org --token "$SES_USER_TOKEN" \
    submit -j <job-id>
```

### Step 6 — verify it fires and publishes (the heartbeat)

The pod appears in the `ses` namespace each tick, runs ~30-40s, exits
(one-shot), and is GC'd — so it's invisible between ticks. Confirm via the
data API instead. As of 0.1.1 the plugin publishes
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
The proof it's the SES job (not a leftover hand-deployed pod) is in the
record metadata: `"job": "birdnet-species-<id>"` and
`"plugin": "registry.sagecontinuum.org/beckman/birdnet-species:0.1.1"`
("already present on machine" in the pod events confirms the sideload hit).

### Re-deploying after a code change (new version)

Bump the version everywhere (sage.yaml, Makefile, job YAML), then repeat
build → sideload with the new tag. Because the tag changes, k3s uses the
new local image on the next tick automatically; no job re-submit needed if
the job YAML already points at the new tag (otherwise update + re-submit).

### Systemic fix (escalate to the ECR/cyberinfra team)

The sideload workaround is manual and per-node. The durable fix is one of:

- **(a)** Grant push/write access to `registry.sagecontinuum.org/beckman/`
  for a Sage portal token, so `docker push` works after a native Thor build; or
- **(b)** Add a **native arm64 build node** to the Jenkins ECR pipeline so
  the portal "Register and Build" path works without QEMU.

Either unblocks every Thor-targeted plugin (yolo, bioclip, birdnet) and
removes the manual sideload step entirely.

See: https://sagecontinuum.org/docs/tutorials/edge-apps/publishing-to-ecr
