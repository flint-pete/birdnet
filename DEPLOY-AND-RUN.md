# Deploy and Run Guide

> **Status (2026-07-10):** BirdNET is now built by the standard Sage ECR
> "Register and Build" pipeline and runs as an **official SES job** on H00F
> (job `birdnet-reolink`, image `birdnet-species:0.2.1`). The Thor/arm64 build
> blocker (buildkit `/proc/acpi` runc bug) has been **fixed by the CI team** —
> so the manual side-load workaround is **no longer required**. Side-loading is
> retained below only as a historical fallback for offline/air-gapped bring-up.
> Remaining known platform notes (runtime GPS/VSN injection, data-API
> `meta.task` gotcha) are tracked in `~/AI-projects/Infra-problems-to-fix.md`.

## Prerequisites

1. **Sage portal account** — get your access token from
   [portal.sagecontinuum.org/account/access](https://portal.sagecontinuum.org/account/access)

2. **sesctl installed** — already present on Sage nodes. Verify:
   ```bash
   which sesctl
   ```

3. **App built in ECR** — check the ECR portal at
   [portal.sagecontinuum.org/apps](https://portal.sagecontinuum.org/apps)
   and find `birdnet-species`. The current release is **0.2.1**, built from the
   `v0.2.1` git tag; its registry image is
   `registry.sagecontinuum.org/beckman/birdnet-species:0.2.1`.

   > **Namespace note:** the ECR namespace is `beckman`, not `flint-pete`.

## Building via ECR (the standard path)

This is now the primary path — no node-local build, no side-load.

1. **Tag the release in git** (ECR builds a specific version from a tag matching
   `sage.yaml`'s `version:`):
   ```bash
   git tag -a v0.2.1 -m "birdnet-species 0.2.1"
   git push origin v0.2.1
   ```
2. **Register + Build** in the ECR portal (Portal → My Apps → birdnet-species →
   add version from GitHub), or via `scripts/register-ecr-version.py`. The portal
   builds `linux/arm64` from `flint-pete/birdnet` using `sage.yaml` + `Dockerfile`.
   BirdNET uses a CPU-only `python:3.12-slim` base (no CUDA/QEMU path), so the
   build is clean.
3. **Make the app public**, or SES returns `registry ... does not exist in ECR`.

Once the build succeeds, the image is pullable fleet-wide and SES can schedule it
on any node — proceed to "Scheduled Deployment (sesctl)" below.

## Side-loading (historical fallback — normally NOT needed)

> **You almost certainly do not need this.** As of 2026-07-10 the ECR pipeline
> builds birdnet natively, so use "Building via ECR" above. This section is kept
> for the record and for offline bring-up (e.g. a node that cannot reach the
> registry, or reproducing a pre-fix deployment). It was the workaround used
> while the Thor build was broken.

<details>
<summary>Expand: side-load procedure (build on-node → import into k3s)</summary>

*Side-loading* builds the container image **directly on the target edge node**
and imports it into that node's k3s containerd store, bypassing the registry.
SES pods use `imagePullPolicy: IfNotPresent`, so a locally-present image under the
exact registry-qualified tag is used without pulling.

```bash
cd ~/AI-projects/birdnet && git pull
# Build natively on the node (arm64, no QEMU), tagged with the FULL registry path:
sudo docker build -t registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 .
# Import into k3s containerd:
sudo docker save registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 \
  | sudo k3s ctr images import -
# Verify it landed and is CRI-managed:
sudo k3s ctr images ls | grep birdnet-species:0.2.1
```

The tag **must** be the full `registry.sagecontinuum.org/...` path and match the
job YAML's `image:` field exactly. You still need a catalog metadata record for
SES validation (`scripts/register-ecr-version.py`); with ECR now building, that
record is created by the normal build and this whole step is unnecessary.

**Why it was needed (historical):** the ECR/Jenkins buildkit failed on every
`RUN` step with a `/proc/acpi` runc error, and portal tokens are pull-only
(no `docker push`). Both are resolved for birdnet — the CI team fixed the
buildkit bug, and the ECR pipeline now produces the arm64 image.
</details>

## Quick Test (pluginctl, one-shot)

SSH into the target node and run the plugin once to verify it works
before scheduling. No sesctl token needed.

### USB Microphone (W-series nodes with ETS mic)

```bash
sudo pluginctl deploy -n birdnet-test \
  registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 -- \
  --duration 30 --min-confidence 0.60

# Check logs:
sudo pluginctl logs birdnet-test

# Clean up:
sudo pluginctl rm birdnet-test
```

### Reolink Camera (H00F hummingbird cam)

> **IMPORTANT — Reolink auth:** The Reolink BCS/FLV endpoint does **not**
> accept HTTP basic auth (`http://user:pass@ip/...`). That form returns
> ffmpeg "End of file" / exit 187. Credentials **must** be passed as
> **query parameters** (`&user=...&password=...`).
>
> **Shell escaping:** Wrap the whole `--camera` URL in **single quotes**.
> The password contains `!`, which bash treats as history expansion under
> double quotes. Single quotes also protect the `&` and `?` characters.

```bash
sudo pluginctl rm birdnet-test   # remove any prior pod first (see note below)

sudo pluginctl deploy -n birdnet-test \
  registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 -- \
  --camera 'http://CAMERA_IP:PORT/flv?port=1935&app=bcs&stream=channel0_sub.bcs&user=USER&password=PASS' \
  --duration 30 --min-confidence 0.60 --bandpass-fmax 8000

# Check logs:
sudo pluginctl logs birdnet-test

# Clean up:
sudo pluginctl rm birdnet-test
```

Confirmed-working example for the H00F hummingcam (Reolink RLC-811A at
`10.107.0.221:10000`, user `sage`):

```bash
sudo pluginctl deploy -n birdnet-test \
  registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 -- \
  --camera 'http://10.107.0.221:10000/flv?port=1935&app=bcs&stream=channel0_sub.bcs&user=sage&password=SageCam!' \
  --duration 30 --min-confidence 0.60 --bandpass-fmax 8000
```

> **"pod updates may not change fields..." error:** A `birdnet-test` pod
> already exists and pluginctl is trying to patch it in place (k8s only
> allows the image field to change on a running pod). Delete it first with
> `sudo pluginctl rm birdnet-test`, wait a few seconds, then redeploy. If
> it's stuck Terminating: `sudo kubectl delete pod birdnet-test --grace-period=0 --force`.

### Mobotix M16 Camera (H00F)

> **Note:** Unlike Reolink, the Mobotix M16 MxPEG stream uses HTTP **basic
> auth** (`http://user:pass@ip/...`) — this form is confirmed working for
> the M16. Still wrap the URL in single quotes to protect `!`, `&`, `?`.

```bash
sudo pluginctl deploy -n birdnet-m16-test \
  registry.sagecontinuum.org/beckman/birdnet-species:0.2.1 -- \
  --camera 'http://USER:PASS@CAMERA_IP/control/faststream.jpg?stream=MxPEG&needlength' \
  --duration 30 --min-confidence 0.60 --bandpass-fmax 4000

# Check logs:
sudo pluginctl logs birdnet-m16-test

# Clean up:
sudo pluginctl rm birdnet-m16-test
```

### What to look for in the logs

A successful run looks like:
```
Auto-detected BirdNET week: 23
Auto-detected node location: (41.7180, -87.9827)
BirdNET Species Classifier starting
  min_confidence=0.60  sensitivity=1.0  overlap=0.0  top_k=5
  source=camera (CAMERA_IP/...)
Loading BirdNET V2.4 acoustic model...
Acoustic model loaded (sample rate: 48000 Hz)
Loading geo model for species filtering (41.7180, -87.9827, week=23)...
Geo filter: 187 species expected at this location/time
Capturing 30 seconds from camera ...
Camera audio saved to /tmp/birdnet_.../camera_audio.flac (..., FLAC)
Classified camera_audio.flac: 2 detections in 3.50s
  Passer domesticus (House Sparrow): 0.8666 [54.0-57.0s]
  Haemorhous mexicanus (House Finch): 0.6200 [3.0-6.0s]
```

If you see `No detections above threshold 0.60`, that's normal —
it just means no confident bird vocalizations in that 30-second window.

## Scheduled Deployment (sesctl)

Once the one-shot test works, schedule it to run every 10 minutes.

### Step 1: Set up sesctl credentials

```bash
export SES_HOST=https://es.sagecontinuum.org
export SES_USER_TOKEN=<your-token-from-portal>
```

### Step 2: Confirm the version is built in ECR

With the ECR build fix in place, the version you tagged and built (see "Building
via ECR" above) is already in the catalog and registry. Confirm it exists:

```bash
# the app should be listed and public in the portal, at the version your job targets
# (job YAML points at registry.sagecontinuum.org/beckman/birdnet-species:0.2.1)
```

SES validates a job's image against the ECR app **catalog** — if the catalog has
no record for the exact version, `sesctl submit` fails with
`[registry.sagecontinuum.org/beckman/birdnet-species:<ver> does not exist in ECR]`.
The normal ECR build creates that record; only fall back to
`scripts/register-ecr-version.py` if you deliberately side-loaded (see the
historical fallback section above).

### Step 3: Create the job

Edit the job YAML in `jobs/` to set the correct camera URL + image tag, then
create it. Note the actual `sesctl` flags (the portal docs are wrong here):

```bash
# create takes -f / --file-path and RETURNS a numeric job id:
sesctl --server "$SES_HOST" --token "$SES_USER_TOKEN" create -f jobs/birdnet-reolink.yaml
# => {"job_id": "5657", "state": "Created"}
```

### Step 4: Submit (activate) the job — by numeric ID, not name

```bash
sesctl --server "$SES_HOST" --token "$SES_USER_TOKEN" stat        # list jobs + ids
sesctl --server "$SES_HOST" --token "$SES_USER_TOKEN" submit -j 5657   # activate by ID
```

> **sesctl gotchas:** `create` uses `-f/--file-path` (not `--from-file`).
> `submit` takes `-j <numeric-job-id>` (not the job *name*). `rm -s <id>`
> suspends; `rm <id>` removes.

### Step 5: Monitor

```bash
sesctl --server "$SES_HOST" --token "$SES_USER_TOKEN" stat   # check job status
```

### Step 6: Query results from Beehive

From any machine with sage-data-client:

```python
import sage_data_client

df = sage_data_client.query(
    start="-1h",
    filter={
        "name": "env.detection.audio.*",
        "vsn": "H00F",
    }
)
print(df)
```

Or with curl:

```bash
curl -s -X POST https://data.sagecontinuum.org/api/v1/query -d '
{
  "start": "-1h",
  "filter": {
    "vsn": "H00F",
    "name": "env.detection.audio.*"
  }
}'
```

### Step 7: Manage the job

```bash
sesctl --server "$SES_HOST" --token "$SES_USER_TOKEN" rm -s <job-id>   # Suspend (pause)
sesctl --server "$SES_HOST" --token "$SES_USER_TOKEN" submit -j <job-id>   # Resume
sesctl --server "$SES_HOST" --token "$SES_USER_TOKEN" rm <job-id>      # Remove completely
```

## Location & Week Resolution

The plugin resolves week-of-year automatically, and *attempts* to resolve
location automatically — but **on SES today you must pass `--lat`/`--lon`
explicitly** for fixed nodes (see the caveat below).

| Feature | Source (in priority order) | Override flag |
|---------|----------------------------|---------------|
| Week of year | Current date (BirdNET weeks 1–48) | `--week 25` or `--week -1` |
| Latitude/Longitude | (1) node manifest → (2) `WAGGLE_NODE_GPS_*` env → (3) live `sys.gps.*` (opt-in `--gps-subscribe`) | `--lat` / `--lon` |

> **IMPORTANT — explicit coords required on SES.** Auto-resolution sounds like
> "same YAML works on any node," but in practice:
> - SES does **not** mount the node manifest into plugin pods, so source (1)
>   is unavailable in scheduled jobs.
> - Fixed nodes have no GPS publisher, so source (3) yields nothing.
> - pywaggle (0.56) has no first-class location API; `sys.gps.*` is the only
>   live mechanism.
>
> So for a fixed node like H00F, **set `--lat`/`--lon` in the job YAML**
> (e.g. `--lat 41.7180 --lon -87.9827`). When geo-filtering is engaged the
> startup log prints `Geo filter: N species expected at this location/time`.
> If that line is absent, filtering is OFF and you will get the global
> species list (out-of-range birds/frogs in your data).
>
> **Negative longitudes:** the Western Hemisphere has negative longitude
> (Lemont, IL is -87.98). The plugin handles negative coordinates correctly
> as of **v0.1.4**; earlier versions silently skipped geo-filtering for any
> negative longitude.

## Audio Source Comparison

| Source | Bandwidth | Nyquist | --bandpass-fmax | Quality for BirdNET |
|--------|-----------|---------|-----------------|---------------------|
| USB mic (ETS) | 48 kHz | 24 kHz | 15000 (default) | Best |
| Reolink 811A (sub-stream) | 16 kHz | 8 kHz | 8000 | Good — covers most passerines |
| Mobotix M16 (MxPEG) | 8 kHz | 4 kHz | 4000 | Marginal — misses high-frequency calls |

## Troubleshooting

**"unrecognized arguments"** — The running image is stale. Rebuild via ECR
(bump the version tag, re-Register and Build), or for a local one-shot test:
```bash
cd ~/AI-projects/birdnet && git pull
sudo docker build -t birdnet-species:0.2.1 .
sudo docker save birdnet-species:0.2.1 | sudo k3s ctr images import -
```

**ffmpeg "End of file" / exit 187 (Reolink)** — Wrong auth method.
The Reolink BCS/FLV endpoint rejects HTTP basic auth (`user:pass@ip`).
Pass credentials as query parameters instead:
`...&user=USER&password=PASS`, and wrap the whole URL in single quotes.

**"please login first"** — Camera requires token/credential auth.
For Reolink, append `&user=USER&password=PASS` as query parameters.
For Mobotix M16, use inline basic auth (`http://user:pass@ip/...`).

**Zero detections** — Check the audio: capture a sample, pull it
back, and listen. If silent, the camera mic may be disabled.
For Reolink, enable audio via the web UI or the API:
```bash
curl -s "http://CAMERA_IP:PORT/api.cgi?cmd=SetEnc&user=USER&password=PASS" \
  -d '[{"cmd":"SetEnc","action":0,"param":{"Enc":{"channel":0,"audio":1}}}]'
```

**ffmpeg timeout** — Camera stream may be unreachable. Test
connectivity from the node:
```bash
curl -s --max-time 5 "http://CAMERA_IP:PORT/cgi-bin/api.cgi?cmd=Snap&channel=0&user=USER&password=PASS" -o /dev/null && echo "reachable" || echo "unreachable"
```
