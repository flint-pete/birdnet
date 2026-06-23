# Deploy and Run Guide

## Prerequisites

1. **Sage portal account** — get your access token from
   [portal.sagecontinuum.org/account/access](https://portal.sagecontinuum.org/account/access)

2. **sesctl installed** — should already be on Sage nodes. Verify:
   ```bash
   which sesctl
   ```

3. **ECR image built** — check the ECR portal at
   [portal.sagecontinuum.org/apps](https://portal.sagecontinuum.org/apps)
   and find `birdnet-species`. Copy the registry tag from the "Tags" tab
   (e.g. `registry.sagecontinuum.org/beckman/birdnet-species:0.1.1`).

   > **Namespace note:** the ECR namespace is `beckman`, not `flint-pete`.
   > Use `registry.sagecontinuum.org/beckman/birdnet-species:0.1.1`.

## Quick Test (pluginctl, one-shot)

SSH into the target node and run the plugin once to verify it works
before scheduling. No sesctl token needed.

### USB Microphone (W-series nodes with ETS mic)

```bash
sudo pluginctl deploy -n birdnet-test \
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 -- \
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
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 -- \
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
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 -- \
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
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.1 -- \
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
Camera audio saved to /tmp/birdnet_.../camera_audio.wav (...)
Classified camera_audio.wav: 2 detections in 3.50s
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

### Step 2: Register the version in the ECR catalog (the "import" step)

**This is the step most people miss.** SES validates a job's image against the
ECR app *catalog* (`ecr.sagecontinuum.org`) — **not** the Docker registry and
**not** the image you sideloaded into k3s. If the catalog has no record for your
exact version, `sesctl submit` fails with:

```
[registry.sagecontinuum.org/<ns>/birdnet-species:<ver> does not exist in ECR]
```

Normally the ECR **portal** "Create App / add version" UI registers that catalog
record (and builds the image) for you. But for Thor/arm64 NVIDIA-base plugins the
portal *build* crashes under QEMU, and we serve the actual image by **sideloading**
it into the node's k3s containerd instead (SES pods use
`imagePullPolicy=IfNotPresent`, so a locally-present image is used as-is). All we
then need from ECR is the catalog *metadata* record. Register it directly via the
API with the helper script — it clones a known-good prior version's metadata,
bumps the version + git source, and POSTs to `/api/submit`:

```bash
python3 scripts/register-ecr-version.py \
  --namespace beckman \
  --name birdnet-species \
  --from-version 0.1.3 \
  --version 0.1.4 \
  --git-url https://github.com/flint-pete/birdnet.git \
  --token "$SAGE_TOKEN"
```

It prints `registered: beckman/birdnet-species:0.1.4` and lists the catalog
versions. (Auth uses the `Authorization: Sage <token>` header; the token is your
portal access token, which has write scope.)

### Step 2b: Build + sideload the image onto the node

The catalog record is metadata only — the image must actually be pullable. On
Thor we build locally and sideload into k3s (no registry push needed):

```bash
cd ~/AI-projects/birdnet && git pull
sudo docker build -t registry.sagecontinuum.org/beckman/birdnet-species:0.1.4 .
sudo docker save registry.sagecontinuum.org/beckman/birdnet-species:0.1.4 \
  | sudo k3s ctr images import -
# verify:
sudo k3s ctr images ls | grep birdnet-species:0.1.4
```

> **Why this works:** SES pods use `imagePullPolicy=IfNotPresent`. Because the
> tag is already present in containerd, the kubelet uses it directly and never
> contacts the registry. Tag the image with the **full registry path** so it
> matches the job YAML's `image:` field exactly.

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

**"unrecognized arguments"** — The k3s image is stale. Rebuild and
reimport:
```bash
cd ~/AI-projects/birdnet && git pull
sudo docker build -t birdnet-species:0.1.1 .
sudo docker save birdnet-species:0.1.1 | sudo k3s ctr images import -
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
