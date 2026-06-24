# Changelog

All notable changes to the `birdnet-species` Sage plugin.

## 0.2.1 — 2026-06-24

### Changed
- **Saved audio clips are now FLAC instead of WAV.** Captured/recorded audio is
  written as lossless FLAC (ffmpeg `-acodec flac`; mic path saves `.flac`). This:
  - **Makes clips inline in the Sage portal.** The query-browser
    (`sage-gui` `QueryBrowser.tsx`) renders an inline `<audio>` player ONLY for
    `.flac` uploads — it does not recognize `.wav` or `.mp3`. 0.2.0 saved `.wav`,
    so clips showed as a download link with no player. They now play inline,
    matching the `audio-sampler` plugin.
  - **Cuts storage ~50-70%** (a 30 s 48 kHz mono clip drops from ~2.88 MB to
    ~1-1.4 MB) with **zero quality loss** — FLAC is lossless and BirdNET reads it
    natively via librosa/soundfile.
  - **Improves archival fidelity** — FLAC is a recognized long-term archival
    audio format.
- No behavior change to detection, publishing, heartbeat, or `--save-match`
  semantics; only the on-disk/uploaded container changed (WAV → FLAC).

## 0.2.0 — 2026-06-24

### Added
- **`--save-match`: species-aware audio-clip saving, decoupled from publishing.**
  The recorded clip is now uploaded only when a detection matches a user-supplied
  OR-list of `Name:confidence` rules (e.g. `"Northern Cardinal:0.5,Barn Owl:0.4"`).
  A clip is saved when ANY detection matches ANY rule. Name matching is
  case-insensitive and EXACT against the common OR scientific name (no substring).
  The wildcard `"*:0.5"` saves any clip with a detection ≥0.5. Implemented via the
  shared `save_match.py` helper (29 unit tests, identical copy to bioclip/yolo).
  This is the first time birdnet uploads audio at all — previously it published
  only topics + CSV.

### Fixed
- **Heartbeat never fired on quiet cycles.** `publish_detections()` always emits
  the `env.detection.audio.summary` heartbeat internally, but the CALL was gated
  behind `if detections:` in the run cycle — so cycles with zero detections
  published NOTHING, making a live job indistinguishable from a dead one. The call
  is now unconditional; every cycle emits the summary heartbeat (and
  `plugin.duration.*`), even with zero detections.

### Changed
- Publish (topics + heartbeat, always) and save (audio clip, selective) are now
  strictly separate code paths. `--min-confidence` remains the publish/detection
  floor; `--save-match` is the only thing that uploads audio. Omitting
  `--save-match` saves no audio (topics + heartbeat still publish).

## 0.1.6 — 2026-06-23

### Fixed
- **Startup crash-loop in 0.1.5** (`NameError: name 'birdnet' is not defined`).
  When model loading was refactored from `__init__` into the new `load()` method
  (0.1.5), the `import birdnet` statement was left behind in `__init__`, so
  `load()` called `birdnet.load(...)` with the name unbound in its scope. The
  plugin raised on every startup and the scheduler crash-looped it (zero output).
  Fix: moved `import birdnet` into `load()` where it is used. (0.1.5 is a
  known-bad published version — do not deploy it; it never ran successfully.)
  Lesson: when extracting code into a new method, method-local imports must move
  with the code that uses them; a Pyright "not defined" warning on the lazy
  import flagged this and should not have been dismissed.

## 0.1.5 — 2026-06-23

### Added
- **Standard `plugin.duration.*` performance telemetry** (matching
  `avian-diversity-monitoring` / TAFT-node convention). Each cycle now publishes
  nanosecond phase timings via pywaggle's `plugin.timeit`:
  `plugin.duration.loadmodel` (acoustic + geo model load, once),
  `plugin.duration.input` (audio capture/record + decode, per cycle),
  `plugin.duration.inference` (classification, per cycle). These make cold-start
  cost and per-cycle latency observable from the data plane and double as a
  liveness signal on quiet cycles. Model load was refactored into a `load()`
  method so it can be timed inside the Plugin context.

## 0.1.4 — 2026-06-23

### Fixed
- **Geo-filtering never engaged in the Western Hemisphere.** The gate was
  `if lat > -1 and lon > -1`. Every longitude in the Americas is negative
  (Lemont, IL is -87.98), so `lon > -1` was always False and the eBird species
  filter was never built — the plugin silently ran against the full global
  6,522-species list. Symptom: out-of-range species (tinamous, pardalotes,
  European tits, Pacific Chorus Frog) appearing in Illinois data. The `-1`
  "unset" sentinel collided with real negative coordinates. Now gated by an
  explicit sentinel + geographic-range check:
  `coords_set = not (lat == -1 and lon == -1)` and
  `coords_valid = -90 <= lat <= 90 and -180 <= lon <= 180`. Same fix applied to
  the `location=` startup log. Verified live: pod now logs
  `Geo filter: 124 species expected at this location/time`.

## 0.1.3 — 2026-06-22

### Fixed
- **Publish crash dropped every real detection.** `publish_detections()` passed
  float `meta` values (`start_time_s`/`end_time_s`); pywaggle requires
  `meta` to be `dict[str, str]` and raised
  `TypeError: Meta must be a dictionary of strings to strings.` at the
  per-species publish. The summary publish (no meta) survived, so the heartbeat
  looked healthy while detections never reached Beehive. All meta values are now
  stringified.

### Changed
- **Honest live-GPS path.** Removed a reference to a non-existent
  `waggle.data.gps` module. Live location now comes from subscribing to the
  node's `sys.gps.*` measurement stream, **opt-in** via a new `--gps-subscribe`
  flag (default off, so fixed nodes don't waste a broker round-trip). pywaggle
  0.56 has no first-class location API; this is the only live mechanism.

## 0.1.2 — 2026-06-22

### Changed
- Dynamic location resolution (manifest → env → optional live GPS) and detection
  threshold lowered to **0.35** for low-bandwidth camera audio (16 kHz
  sub-stream caps real-bird confidence near ~0.40). Verified House Sparrow
  passes at 0.35.

## 0.1.1 — 2026-06-21

### Added
- Heartbeat/liveness summary record (`env.detection.audio.summary`) published
  every cycle, including quiet cycles (`total_detections: 0`).

## 0.1.0

- Initial BirdNET V2.4 rewrite of the original BirdNET Lite plugin. See the
  "Changes with BirdNET V2.4" section of `ecr-meta/ecr-science-description.md`
  for the full old→new mapping.

---

### Note on historical data

Detections published before a given version reflect that version's behavior
(e.g. records before 0.1.4 may contain out-of-range species; records before
0.1.3 may be missing per-species detections entirely). Every record carries the
exact image version in its `meta.plugin` tag
(`registry.sagecontinuum.org/<ns>/birdnet-species:<ver>`), so the archive can be
partitioned or filtered by version when analyzing data that spans a behavior
change. Historical records are intentionally retained, not deleted.
