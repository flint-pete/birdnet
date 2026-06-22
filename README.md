[![CC BY-NC-SA 4.0][cc-by-nc-sa-shield]][cc-by-nc-sa]

# BirdNET — Avian Diversity Monitoring on the Edge

A Sage/Waggle plugin for autonomous bird species identification using audio.
Records sound from a USB microphone or network camera, runs [BirdNET V2.4](https://github.com/birdnet-team/birdnet)
inference (6,522 species — birds, frogs, insects), and publishes per-species
detections with confidence scores.

## Audio Sources

The plugin supports three audio input modes:

1. **USB microphone** (default) — records directly from the node's audio
   input via pywaggle. Full 48 kHz bandwidth. Used on Wild Sage nodes
   (W-series) with connected microphones.

2. **Network camera** (`--camera URL`) — captures audio from a network
   camera's built-in or attached microphone via ffmpeg. Supports Mobotix
   MxPEG, RTSP, and any ffmpeg-compatible source.

3. **Audio file** (`--input FILE`) — reads from a local WAV/MP3/FLAC file
   for testing and batch processing.

## Quick Start

```bash
# Record 15 seconds from USB mic, classify, print results
python3 app.py --duration 15 --dry-run

# Classify an audio file
python3 app.py --input recording.wav --dry-run

# Capture from a Mobotix M16 camera
python3 app.py --camera "http://admin:pass@CAMERA_IP/control/faststream.jpg?stream=MxPEG&needlength" \
               --duration 15 --dry-run

# With eBird geo-filtering (Chicago, late June)
python3 app.py --duration 15 --lat 41.88 --lon -87.62 --week 25 --dry-run

# 6 recordings of 10 seconds each, 5-second gap between them
python3 app.py --num-recordings 6 --duration 10 --interval 5 --dry-run

# Continuous monitoring, 60-second recordings every 5 minutes
python3 app.py --num-recordings 0 --duration 60 --interval 300
```

## Arguments

### Audio Input

| Argument | Default | Description |
|----------|---------|-------------|
| `--input`, `-i` | None | Path to audio file. If not set, records from mic or camera. |
| `--camera` | None | URL for network camera audio (Mobotix MxPEG, RTSP, etc.) |
| `--duration` | 15.0 | Recording duration in seconds (mic or camera mode) |
| `--sample-rate` | 48000 | Audio sample rate in Hz |

### Model Parameters

| Argument | Default | Description |
|----------|---------|-------------|
| `--min-confidence` | 0.25 | Minimum confidence threshold (0.01–0.99) |
| `--sensitivity` | 1.0 | Detection sensitivity (0.5–1.5). Higher = more detections. |
| `--overlap` | 0.0 | Overlap in seconds between 3-second windows (0.0–2.9) |
| `--top-k` | 5 | Max predictions per 3-second chunk |
| `--bandpass-fmin` | 0 | Low-frequency cutoff in Hz |
| `--bandpass-fmax` | 15000 | High-frequency cutoff in Hz. Match to audio source (e.g. 4000 for 8 kHz camera mic). |
| `--batch-size` | 1 | Chunks to process in parallel. Increase for long recordings. |

### Location Filtering (eBird)

| Argument | Default | Description |
|----------|---------|-------------|
| `--lat` | -1 | Latitude for species range filtering. -1 = auto-resolve dynamically (see below). |
| `--lon` | -1 | Longitude for species range filtering. -1 = auto-resolve dynamically (see below). |
| `--week` | auto | Week of year (1–48) for seasonal filtering. 'auto' = current week. -1 for year-round. |
| `--sf-thresh` | 0.03 | Species filter threshold for geo model |

**Dynamic location resolution (v0.1.2+).** When `--lat`/`--lon` are left at
-1, the plugin resolves the node's GPS at runtime by trying these sources,
using the first that succeeds:

1. **Node manifest file** — the platform-maintained `node-manifest-v2.json`
   (probed at `/etc/waggle/`, `/run/waggle/`, `/host/etc/waggle/`, or the path
   in `$WAGGLE_NODE_MANIFEST`). Reads `gps_lat` / `gps_lon`.
2. **Waggle env vars** — `WAGGLE_NODE_GPS_LAT` / `WAGGLE_NODE_GPS_LON` if set.
3. **Live `sys.gps.*` stream** (opt-in via `--gps-subscribe`) — subscribes to
   the node's `sys.gps.lat` / `sys.gps.lon` measurements. Only useful on
   GPS-equipped/mobile nodes that run a GPS device plugin; off by default
   because fixed nodes have no GPS publisher and the subscribe just adds a few
   seconds of startup.

> **Note on pywaggle:** as of pywaggle 0.56 there is **no** dedicated
> location/GPS accessor (no `waggle.data.gps`, no `Plugin.get_location()`).
> The only live-GPS mechanism is the data plane (`sys.gps.*` measurements,
> hence `--gps-subscribe`). A proper fix belongs upstream: a pywaggle location
> API plus WES injecting node GPS into the plugin environment.

This keeps job files portable (no hardcoded coordinates). If none of the
sources are reachable inside the pod, geo-filtering is disabled and the log
says `No node location available …`; pass `--lat`/`--lon` explicitly to force
it. Explicit `--lat`/`--lon` always override auto-resolution.

**On Sage today (confirmed on H00F):** SES does **not** mount the node manifest
into plugin pods and fixed nodes have no `sys.gps.*` publisher, so
auto-resolution finds nothing — pass `--lat`/`--lon` explicitly (see the
hummingcam job for the pattern).



### Runtime

| Argument | Default | Description |
|----------|---------|-------------|
| `--num-recordings` | 1 | Number of recording cycles. 0 = loop forever. |
| `--interval` | 0.0 | Seconds between recording cycles |
| `--output`, `-o` | None | Path to save CSV results |
| `--dry-run` | false | Run without publishing to Waggle |

## Ontology

Detections are published to Waggle as:

- **`env.detection.audio.<scientific_name>`** — confidence (0–1) per species per detection window, with metadata: `common_name`, `start_time_s`, `end_time_s`
- **`env.detection.audio.summary`** — JSON summary published **every cycle** (heartbeat): `total_detections`, `unique_species`, and top species with confidences. On a quiet cycle this is still published with `total_detections: 0` and an empty `species` list, so the data API carries proof the job ran even when no birds are detected.

## Querying Results

```python
import sage_data_client

df = sage_data_client.query(
    start="-1h",
    filter={
        "name": "env.detection.audio.*",
        "vsn": "W01B",
    }
)
print(df)
```

## Build and Test

```bash
# Build Docker image
make build

# Run full test suite (build + 9 NA bird audio tests)
make test

# Run tests natively (requires venv)
make test-native
```

All test audio is committed to the repo — no downloads needed.

## Changes with BirdNET V2.4

This plugin was rewritten from the original [BirdNET Lite Plugin](https://github.com/dariodematties/BirdNET_Lite_Plugin) (v0.2.5). Key changes:

### Model

| | BirdNET Lite (old) | BirdNET V2.4 (new) |
|---|---|---|
| Species | ~6,000 birds | 6,522 (birds + frogs + insects) |
| Architecture | Custom CNN, 27M params | EfficientNetB0-like, 77 MB TFLite |
| Model in git | Yes (55 MB committed) | No — auto-downloaded by library, baked into Docker |
| Installation | Manual TFLite model loading | `pip install birdnet` (model auto-downloads) |
| Geo-filtering | Manual metadata file conversion | Built-in eBird geo model (`--lat`/`--lon`/`--week`) |
| Bandpass filter | Not available | `--bandpass-fmin`/`--bandpass-fmax` for frequency-limited sources |
| Batch processing | Not available | `--batch-size` for parallel chunk inference |

### Audio Sources

| | Old | New |
|---|---|---|
| USB microphone | `arecord -D hw:0,0` (hard-coded) | pywaggle `Microphone` class (default audio device) |
| Network camera | Not supported | `--camera URL` (Mobotix MxPEG, RTSP, any ffmpeg source) |
| Audio file | `--i path` | `--input path` |

### Command-Line Arguments

| Old (analyze.py) | New (app.py) | Notes |
|---|---|---|
| `--i` | `--input`, `-i` | Renamed for clarity |
| `--o` | `--output`, `-o` | Renamed for clarity |
| `--num_rec` | `--num-recordings` | Same behavior: run N cycles then exit. 0 = loop forever (new). |
| `--sound_int` | `--duration` | Recording duration per cycle |
| `--silence_int` | `--interval` | Gap between recording cycles |
| `--min_conf` | `--min-confidence` | Same behavior |
| `--sensitivity` | `--sensitivity` | Unchanged |
| `--overlap` | `--overlap` | Unchanged |
| `--lat` | `--lat` | Unchanged |
| `--lon` | `--lon` | Unchanged |
| `--week` | `--week` | Unchanged |
| `--custom_list` | (removed) | Replaced by geo model: `--lat`/`--lon`/`--week` + `--sf-thresh` |
| `--filetype` | (removed) | Auto-detected |
| `--keep` | (removed) | Temp files always cleaned up |
| — | `--camera` | **New:** network camera audio capture |
| — | `--dry-run` | **New:** test without Waggle |
| — | `--sample-rate` | **New:** configurable sample rate |
| — | `--top-k` | **New:** max predictions per chunk |
| — | `--sf-thresh` | **New:** geo model species filter threshold |
| — | `--bandpass-fmin` | **New:** low-frequency filter cutoff |
| — | `--bandpass-fmax` | **New:** high-frequency filter cutoff |
| — | `--batch-size` | **New:** parallel chunk processing |
| — | `--num-recordings 0` | **New:** loop forever mode |

### Infrastructure

- **Docker base image:** `nvcr.io/nvidia/l4t-tensorflow:r32.4.4` → `python:3.12-slim` (no GPU needed)
- **Test suite:** 9 North American bird audio tests with PASS/FAIL validation and 5% confidence tolerance
- **Test audio:** committed to git (no runtime downloads)
- **Image size:** ~3 GB (TensorFlow overhead, CPU-only inference)

## References

[1] Stefan Kahl, Connor M. Wood, Maximilian Eibl and Holger Klinck. BirdNET: A deep learning solution for avian diversity monitoring. Ecological Informatics Volume 61, March 2021.

## Credits

- Original [BirdNET](https://github.com/birdnet-team/birdnet) by Stefan Kahl, Shyam Madhusudhana, and Holger Klinck (Cornell Lab of Ornithology)
- Original [Sage plugin](https://github.com/dariodematties/BirdNET_Lite_Plugin) by Dario Dematties
- Image credit: Becky Matsubara, © 2017

[cc-by-nc-sa]: http://creativecommons.org/licenses/by-nc-sa/4.0/
[cc-by-nc-sa-shield]: https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg
