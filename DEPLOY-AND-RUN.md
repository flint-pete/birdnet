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
   (e.g. `registry.sagecontinuum.org/beckman/birdnet-species:0.1.0`).

   > **Namespace note:** the ECR namespace is `beckman`, not `flint-pete`.
   > Use `registry.sagecontinuum.org/beckman/birdnet-species:0.1.0`.

## Quick Test (pluginctl, one-shot)

SSH into the target node and run the plugin once to verify it works
before scheduling. No sesctl token needed.

### USB Microphone (W-series nodes with ETS mic)

```bash
sudo pluginctl deploy -n birdnet-test \
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.0 -- \
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
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.0 -- \
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
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.0 -- \
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
  registry.sagecontinuum.org/beckman/birdnet-species:0.1.0 -- \
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

### Step 2: Create the job

Edit the job YAML in `jobs/` to set the correct camera URL, then:

```bash
# Reolink hummingbird cam:
sesctl create --from-file jobs/birdnet-reolink.yaml

# Or Mobotix M16:
sesctl create --from-file jobs/birdnet-m16.yaml
```

### Step 3: Submit (activate) the job

```bash
sesctl stat                    # List your jobs
sesctl sub birdnet-reolink     # Start scheduling
```

### Step 4: Monitor

```bash
sesctl stat birdnet-reolink    # Check job status
```

### Step 5: Query results from Beehive

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

### Step 6: Manage the job

```bash
sesctl sus birdnet-reolink     # Suspend (pause)
sesctl sub birdnet-reolink     # Resume
sesctl rm birdnet-reolink      # Remove completely
```

## Auto-Detection Features

The plugin auto-detects these at runtime — no need to set them
in the job YAML:

| Feature | Source | Override flag |
|---------|--------|---------------|
| Latitude/Longitude | Node manifest (`/etc/waggle/node-manifest-v2.json`) | `--lat` / `--lon` |
| Week of year | Current date (BirdNET weeks 1-48) | `--week 25` or `--week -1` |

This means the same job YAML works on any node without changes.
Only the `--camera` URL is node-specific.

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
sudo docker build -t birdnet-species:0.1.0 .
sudo docker save birdnet-species:0.1.0 | sudo k3s ctr images import -
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
