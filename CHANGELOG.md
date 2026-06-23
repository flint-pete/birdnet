# Changelog

All notable changes to the `birdnet-species` Sage plugin.

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
