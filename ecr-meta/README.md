# BirdNET — Avian Diversity Monitoring on the Edge

Identifies bird, frog, and insect species from audio using BirdNET V2.4
(6,522 species). Records from a USB microphone, network camera, or audio file.

## Usage

```bash
# USB microphone — 15 seconds, with geo-filtering
python3 app.py --duration 15 --lat 41.88 --lon -87.62 --week 25

# Network camera (Mobotix M16)
python3 app.py --camera "http://admin:pass@IP/control/faststream.jpg?stream=MxPEG&needlength" --duration 15

# Audio file
python3 app.py --input recording.wav

# 6 recordings, 10s each, 5s gap
python3 app.py --num-recordings 6 --duration 10 --interval 5

# Continuous monitoring
python3 app.py --num-recordings 0 --duration 60 --interval 300
```

## Arguments

### Audio Input

| Argument | Default | Description |
|----------|---------|-------------|
| `--input`, `-i` | None | Path to audio file |
| `--camera` | None | Network camera audio URL (MxPEG, RTSP, etc.) |
| `--duration` | 15.0 | Recording duration in seconds |
| `--sample-rate` | 48000 | Audio sample rate in Hz |

### Model Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--min-confidence` | 0.25 | Minimum confidence threshold (0.01–0.99) |
| `--sensitivity` | 1.0 | Detection sensitivity (0.5–1.5) |
| `--overlap` | 0.0 | Window overlap in seconds (0.0–2.9) |
| `--top-k` | 5 | Max predictions per 3-second chunk |
| `--bandpass-fmin` | 0 | Low-frequency cutoff in Hz |
| `--bandpass-fmax` | 15000 | High-frequency cutoff in Hz |
| `--batch-size` | 1 | Parallel chunk processing |

### Location Filtering

| Argument | Default | Description |
|----------|---------|-------------|
| `--lat` | -1 | Latitude. -1 = auto-resolve (manifest / env; or live `sys.gps.*` with `--gps-subscribe`). |
| `--lon` | -1 | Longitude. -1 = auto-resolve (same sources as `--lat`). |
| `--gps-subscribe` | off | When auto-resolving, also try a live GPS fix via the node's `sys.gps.*` stream. NOTE: unreliable today (short subscribe vs slow GPS cadence) — pass `--lat`/`--lon` explicitly on fixed nodes. |
| `--week` | auto | Week of year, 1–48. 'auto' = current week. -1 for year-round. |
| `--sf-thresh` | 0.03 | Geo model species filter threshold |

### Runtime

| Argument | Default | Description |
|----------|---------|-------------|
| `--num-recordings` | 1 | Number of cycles (0 = loop forever) |
| `--interval` | 0.0 | Seconds between cycles |
| `--output`, `-o` | None | CSV output path |
| `--dry-run` | false | Test without publishing to Waggle |

## Output

Detections are routed to three soundscape-ecology topics (v0.3.0+):

- `env.detection.biophony.<scientific_name>` — living organisms (birds/frogs/insects) — the biological signal, and the default bucket
- `env.detection.anthrophony.<name>` — human-made (engine, siren, gun, power tools, dog, human…)
- `env.detection.geophony.<name>` — abiotic ambient (noise, environmental)
- `env.detection.audio.summary` — JSON summary/heartbeat per cycle, with per-category counts

Each record carries `meta.category`. Query all families with `env.detection.*`.
