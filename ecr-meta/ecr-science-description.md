# Science

By observing the trends in the diversity variations of certain species, researchers can track the current ecosystem conditions.
Birds are ideal to monitor the ecosystem's health since of the diversity of environments they can occupy is vast.
Relative to other species, birds are prominently chosen since they can be sensitive to similar factors affecting such species.
These facts make birds study one of the most effective baselines for the determination of the ecosystem health.
Furthermore, there are plenty of avian research efforts, which have also turned some avian species into model organisms, 
enabling the development of novel quantitative methods that can then be applied beyond ornithology.
As a consequence, birds could be rendered as sentinel species, umbrella species, model organisms, and flagship species.

Following this line, *Avian diversity monitoring on the edge* is an autonomous avian diversity monitoring system, which uses sounds taken from microphones located in natural areas.

This project will allow the determination of avian biodiversity autonomously through the use of machine learning on edge devices by placing microphones in specific forest locations. Consequently it will be possible to get exposure to many different organisms occupying such areas without needing to detect them during demanding and expensive human fieldwork [1].

In the figure at the right (Credits to S. Kahl et al.) we can see an illustration of the utility of this network.
In  such a figure we can see the migratory species occurrence correlation (r) between weekly cumulative BirdNET detections (in blue) and human point count observations (eBird checklist frequency, in red). As can be see in the plot, the detections of the Network closely resemble human observational performance. In [1], the authors achieved a high correlation for migratory species that vocalize frequently (i.e., multiple hundreds of detections per week). This is indicative of the importance of this kind of automated detection systems.

# AI@Edge

This plugin uses **BirdNET V2.4**, a deep neural network designed for bird sound recognition of 6,522 species worldwide (birds, frogs, and insects). The model uses an EfficientNetB0-like architecture with dual mel-spectrograms (0–3 kHz and 500 Hz–15 kHz) analyzing 3-second audio chunks at 48 kHz. It includes a built-in eBird geo model for location-aware species filtering — when provided with latitude, longitude, and week of year, the model restricts predictions to species expected at that location and time.

Audio can be captured from three sources: a USB microphone connected directly to the node, a network-attached camera (Mobotix MxPEG, RTSP, or any ffmpeg-compatible source), or local audio files for batch processing.

# Using the code

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

# Arguments

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
| `--bandpass-fmax` | 15000 | High-frequency cutoff in Hz. Match to audio source. |
| `--batch-size` | 1 | Chunks to process in parallel |

### Location Filtering (eBird)

| Argument | Default | Description |
|----------|---------|-------------|
| `--lat` | -1 | Latitude for species range filtering. -1 to disable. |
| `--lon` | -1 | Longitude for species range filtering. -1 to disable. |
| `--week` | auto | Week of year (1–48) for seasonal filtering. 'auto' = current week. -1 for year-round. |
| `--sf-thresh` | 0.03 | Species filter threshold for geo model |

### Runtime

| Argument | Default | Description |
|----------|---------|-------------|
| `--num-recordings` | 1 | Number of recording cycles. 0 = loop forever. |
| `--interval` | 0.0 | Seconds between recording cycles |
| `--output`, `-o` | None | Path to save CSV results |
| `--dry-run` | false | Run without publishing to Waggle |

# Ontology

Detections are published to Waggle as:

- **`env.detection.audio.<scientific_name>`** — confidence (0–1) per species per detection window
- **`env.detection.audio.summary`** — JSON summary per cycle with unique species and top confidences

# Inference from Sage

```python
import sage_data_client

df = sage_data_client.query(
    start="-1h",
    filter={
        "name": "env.detection.audio.*",
    }
)
print(df)
```

# References

[1] Stefan Kahl, Connor M. Wood, Maximilian Eibl and Holger Klinck. BirdNET: A deep learning solution for avian diversity monitoring. Ecological Informatics Volume 61, March 2021.

# Credits

- Image credit:
  * Creator: Becky Matsubara 
  * Copyright: © 2017, Becky Matsubara

- Original [BirdNET](https://github.com/birdnet-team/birdnet) network by Stefan Kahl, Shyam Madhusudhana, and Holger Klinck
- Original [Sage plugin](https://github.com/dariodematties/BirdNET_Lite_Plugin) by Dario Dematties

# Changes with BirdNET V2.4

This plugin was rewritten from the original BirdNET Lite Plugin (v0.2.5) to use BirdNET V2.4.

## Model Changes

| | BirdNET Lite (old) | BirdNET V2.4 (new) |
|---|---|---|
| Species coverage | ~6,000 birds only | 6,522 (birds + frogs + insects) |
| Architecture | Custom CNN, 27M params, manual TFLite | EfficientNetB0-like, 77 MB TFLite FP32 |
| Model storage | 55 MB file committed to git | Auto-downloaded by library, baked into Docker at build time |
| Installation | Manual model file + tflite_runtime | `pip install birdnet` |
| Geo-filtering | Manual metadata file + `--custom_list` | Built-in eBird geo model (`--lat`/`--lon`/`--week`) |
| Bandpass filter | Not available | `--bandpass-fmin`/`--bandpass-fmax` |
| Batch processing | Not available | `--batch-size` for parallel inference |

## Audio Source Changes

| | Old | New |
|---|---|---|
| USB microphone | `arecord -D hw:0,0` (hard-coded device) | pywaggle `Microphone` class (default audio device) |
| Network camera | Not supported | `--camera URL` (Mobotix MxPEG, RTSP, any ffmpeg source) |
| Audio file | `--i path` | `--input path` |

## Command-Line Argument Changes

| Old (analyze.py) | New (app.py) | Notes |
|---|---|---|
| `--i` | `--input`, `-i` | Renamed |
| `--o` | `--output`, `-o` | Renamed |
| `--num_rec` | `--num-recordings` | Same behavior. 0 = loop forever (new). |
| `--sound_int` | `--duration` | Recording duration per cycle |
| `--silence_int` | `--interval` | Gap between recording cycles |
| `--min_conf` | `--min-confidence` | Same behavior |
| `--sensitivity` | `--sensitivity` | Unchanged |
| `--overlap` | `--overlap` | Unchanged |
| `--lat` | `--lat` | Unchanged |
| `--lon` | `--lon` | Unchanged |
| `--week` | `--week` | Unchanged |
| `--custom_list` | *(removed)* | Replaced by geo model: `--lat`/`--lon`/`--week` + `--sf-thresh` |
| `--filetype` | *(removed)* | Auto-detected |
| `--keep` | *(removed)* | Temp files always cleaned up |
| — | `--camera` | **New:** network camera audio capture |
| — | `--dry-run` | **New:** test without Waggle |
| — | `--sample-rate` | **New:** configurable sample rate |
| — | `--top-k` | **New:** max predictions per chunk |
| — | `--sf-thresh` | **New:** geo model species filter threshold |
| — | `--bandpass-fmin` | **New:** low-frequency filter cutoff |
| — | `--bandpass-fmax` | **New:** high-frequency filter cutoff |
| — | `--batch-size` | **New:** parallel chunk processing |
| — | `--num-recordings 0` | **New:** loop forever mode |

## Infrastructure Changes

- **Docker base image:** `nvcr.io/nvidia/l4t-tensorflow:r32.4.4` → `python:3.12-slim` (no GPU needed — CPU TFLite inference)
- **Waggle topics:** `env.detection.avian.*` → `env.detection.audio.*` (broader scope: birds + frogs + insects)
- **Test suite:** 9 North American bird audio tests with species validation and 5% confidence tolerance
- **Test audio:** committed to git — no runtime downloads, fully self-contained
