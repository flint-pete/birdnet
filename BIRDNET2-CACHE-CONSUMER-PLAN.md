# Plan: birdnet2 — a v2 cache-consumer BirdNET

**Goal.** Build `sage-birdnet2`: a BirdNET plugin that CONSUMES audio clips from
the shared `/local-cache` (written by the new `hummingcam-audio-producer`
media-sampler3 instance), following the **exact same cache-consumer architecture**
as `sage-yolo2` and `sage-bioclip2`. One cheap producer (media-sampler3 audio),
one non-destructive reader (birdnet2) — the same producer/consumer split that
already works for the image side.

Status: PLAN — awaiting go-ahead. Last updated 2026-07-24.

---

## Why this is the right shape (the precedent)

The v2 plugin family already has TWO consumers of the shared cache, both built on
one shared read-side machinery:

| Plugin | Producer it reads | Media | Metadata source |
|---|---|---|---|
| sage-yolo2 | image-sampler2 / media-sampler3 (images) | JPEG | EXIF UserComment |
| sage-bioclip2 | sage-yolo2 (crops) | JPEG | EXIF UserComment |
| **sage-birdnet2 (this plan)** | **media-sampler3 (audio)** | **FLAC** | **`.json` sidecar** |

sage-bioclip2 is the closest precedent: it took yolo2's consumer pattern and
pointed it at a DIFFERENT producer's output. birdnet2 does the same — the only
genuinely new wrinkle is the **metadata source** (audio has no EXIF, so the
provenance lives in a `.json` sidecar next to the clip).

## The shared cache-consumer model (what we replicate)

Both existing consumers share five **byte-identical** modules (documented in
`sage-bioclip2/VENDORED.md`), plus a common app-loop shape:

- `consumer.py` — resolve cache root (fail-fast if absent), scan a per-stream dir,
  parse `<capture_ts_ns>-v2-<vsn>-<camera>.<ext>` filenames, order by capture_ts,
  read authoritative metadata.
- `selection.py` — frame selection: newest-unseen / `--select-every` stride /
  `--all-unseen` backlog; `parse_duration` (s/m/h).
- `seenstore.py` — restart-durable dedup memory of processed `unique_id`s, bounded,
  stored under `/local-cache/.state/`.
- `node_info.py` — pod self-identity from `WAGGLE_NODE_*` env (the pywaggle2
  nodeinfo shim we re-added in cut-over A).
- `save_match.py` — `Class:confidence` OR-rule parsing/matching (for optional
  save-on-match).
- **app-loop shape** — the "two independent clocks": a `--every` wake cadence
  (batch clock) and a `--select-every` sampling stride (capture-time clock), with
  `--all-unseen` backlog mode and `--max-frames` per-wake cap.

The consumer CLI contract (identical spelling across yolo2 & bioclip2, so birdnet2
inherits it):
```
--source cache --input /local-cache/<cache-name>/<stream>
--every <dur>            # wake cadence (0 = single-shot)
--select-every <dur>     # sampling stride (0 = newest unseen)
--all-unseen             # backlog mode
--max-frames <N>         # per-wake cap (0 = unlimited)
--consumer-id <id>       # seen-store segment (default: WAGGLE_JOB+TASK)
--seen-store <path>      # override
```

## What birdnet2 forks FROM

Two sources, combined:
1. **`~/AI-projects/birdnet` (birdnet-species v0.3.0)** — the BirdNET *science*:
   `record_from_camera` (ffmpeg), the analyzer invocation, eBird geo/season
   filtering, `publish_detections` (per-species + summary heartbeat), save_match.
   This is the domain logic we KEEP.
2. **`~/AI-projects/sage-yolo2`** — the *cache-consumer machinery* (the 5 vendored
   modules + the two-clock app loop). This is the input path we ADD.

birdnet2 = birdnet's analyzer/publish half + yolo2's consumer half, joined at a new
audio-frame reader.

## The v2 audio-frame contract birdnet2 reads

The `hummingcam-audio-producer` writes, per clip, into
`/local-cache/hummingcam-audio/hummingcam_mic/`:
- **Clip:** `<capture_ts_ns>-v2-H00F-hummingcam_mic.flac` (FLAC, 16 kHz, mono, 15 s)
- **Sidecar:** `<same>.flac.json` — the authoritative metadata:
  ```json
  {
    "media_type": "audio", "source_type": "camera_mic",
    "schema_version": "sage-media-1",
    "capture_timestamp_ns": 1784815547927905619,
    "object_name": "<...>.flac", "unique_id": "<sha256>",
    "vsn": "H00F", "camera": "hummingcam_mic", "source": "hummingcam_mic",
    "lat": null, "lon": null, "node_id": null,
    "plugin": "media-sampler3:dev", "job": "sage", "task": "media-sampler3"
  }
  ```
- One logical frame = clip + sidecar; the producer writes the sidecar so a reader
  that sees a clip always finds its metadata. Ordering key = `capture_ts_ns`
  (filename prefix), NOT mtime — same as the image consumers.

## The ONE real adaptation: sidecar metadata reader

The image consumers read metadata from **EXIF UserComment**. Audio has no EXIF, so
birdnet2's `consumer.py` needs a **sidecar variant**: `read_frame_metadata()` opens
`<clip>.flac.json` instead of the JPEG EXIF, returning the same field set
(capture_ts, unique_id, vsn, camera, lat/lon, acquisition_path). Everything else in
`consumer.py` (root resolve, fail-fast, filename parse, ordering, fail-soft on a
missing/corrupt sidecar → filename-derived fallback) is unchanged.

The filename parser already generalizes: it splits on the first `-v2-`, so
`.flac` works exactly like `.jpg` — no change needed there. Only the metadata
read swaps EXIF → sidecar. Keep the vendored modules byte-identical where possible
and isolate the audio-metadata read behind a small `media_type`-aware branch (so a
future re-vendor from yolo2 stays mechanical); document any divergence in
`VENDORED.md`.

---

## Staged build plan (mirrors how yolo2/bioclip2 were staged)

**Stage 0 — scaffold the fork.**
Create `~/AI-projects/sage-birdnet2` from the birdnet repo (KEEP: analyzer,
publish, geo-filter, save_match, Dockerfile base, tests). Vendor the 5 consumer
modules from sage-yolo2 (byte-identical) + a `VENDORED.md` with the sync
obligation. `sage.yaml`: name `sage-birdnet2`, namespace `beckman`, version `2.0.0`
(matching the yolo2/bioclip2 v2 line), keywords audio/birdnet/consumer.

**Stage 1 — cache read + fail-fast (TDD).**
Wire `--source cache --input <dir>`: resolve root, fail-fast if absent, scan the
per-stream dir, list committed `.flac` frames ordered by capture_ts. Reuse
yolo2's `test_consumer*` adapted for `.flac`. Success: point `--input` at the live
`hummingcam-audio/hummingcam_mic/` and list the ring.

**Stage 2 — sidecar metadata reader.**
Add the `.flac.json` sidecar read to `consumer.read_frame_metadata` (fail-soft).
Success: a clip's `unique_id`/`capture_ts`/`vsn` come from the sidecar and match
the producer's values; a clip with a missing sidecar still yields filename-derived
identity.

**Stage 3 — wire the two-clock loop + analyzer.**
Replace birdnet's `--camera`/`--input FILE` primary path with the consumer loop:
each selected `.flac` frame → BirdNET analyze → `publish_detections`
(frame-anchored: observation time = clip capture_ts, NOT wall-clock) → seen-store
mark. Keep `--every` / `--select-every` / `--all-unseen` / `--max-frames`
semantics identical to the other consumers. Keep `--input FILE` and `--camera` as
secondary/dev modes (don't delete — useful for offline testing).

**Stage 4 — geo/season + gain.**
Node identity via `node_info.py` (WAGGLE_NODE_* → real vsn/lat/lon from the
nodeinfo shim) so eBird seasonal filtering works on H00F (the old birdnet logged
"no node manifest → geo-filtering disabled"). Carry the known **faint-mic** issue:
the Reolink mic has no gain control and BirdNET does NOT normalize input, so add a
fixed-gain option (measured via `volumedetect`, default off) — see the sage-waggle
refs `reolink-audio-capture` / `audio-plugin-debugging-birdnet`.

**Stage 5 — build, side-load, on-node validate.**
Native aarch64 `podman build` + `k3s ctr images import` (ECR is broken on Thor —
Infra #2/#3). Run via `sudo pluginctl run` against the LIVE
`hummingcam-audio/hummingcam_mic/` ring. Success: birdnet2 reads real ms3 clips,
publishes `env.detection.*` / summary to Beehive frame-anchored to clip capture
times, seen-store advances, pod stable. Add it to the reboot-recovery runbook as
component 5.

**Stage 6 — finalize.**
CHANGELOG, README, HANDOFF (what's verified vs CI-owned), VENDORED.md sync note,
tests green (`make test`). Update RESUME-HERE for the audio track.

---

## Proposed run shape (Stage 5, matches the family)
```bash
sudo pluginctl run --name sage-birdnet2-consumer --selector zone=core \
  --resource limit.memory=16Gi,request.memory=4Gi \
  -v /media/plugin-data/local-cache:/local-cache \
  -e WAGGLE_JOB_NAME=hummingcam -e WAGGLE_TASK_NAME=sage-birdnet2 \
  localhost/sage-birdnet2:2.0.0 -- \
  --source cache --input /local-cache/hummingcam-audio/hummingcam_mic \
  --every 5m --all-unseen --max-frames 0 \
  --min-confidence 0.6 --bandpass-fmax 8000
```

## Decisions for Pete (each with a lean)

1. **Repo layout — new repo vs branch of birdnet.**
   *Lean: NEW repo `sage-birdnet2`* (public, `flint-pete/sage-birdnet2`), matching
   how sage-yolo2/sage-bioclip2 are their own v2 repos. The v1 `birdnet` stays as
   the camera-capture ancestor. Keeps the v2 family consistent.

2. **Vendor-vs-share the consumer modules.**
   *Lean: vendor byte-identical from sage-yolo2* (as bioclip2 does) + `VENDORED.md`
   sync obligation. A shared package would be cleaner long-term but there's no
   packaging path across these repos yet; vendoring is the established family
   convention.

3. **Where the sidecar-reader adaptation lives.**
   *Lean: a `media_type`-aware branch inside the vendored `consumer.py`* (EXIF for
   image, sidecar for audio), kept minimal and documented, so re-vendoring stays
   mechanical. Alternative (a separate `audio_consumer.py`) diverges more from the
   family. Note this is the one place birdnet2's consumer.py won't be byte-identical.

4. **Confidence + gain defaults.**
   *Lean: `--min-confidence 0.6`, `--bandpass-fmax 8000` (16 kHz sub-stream), gain
   OFF by default* (measure first with volumedetect, enable if clips are too faint).
   The faint-mic caveat is real but is a tuning follow-up, not a blocker.

5. **Scope of this first cut.**
   *Lean: consumer path only* (read cache → analyze → publish), keeping
   `--input FILE`/`--camera` as dev fallbacks. Defer any `--from-cache` uploader
   and any save-clip-on-match to a follow-up, mirroring how yolo2/bioclip2 shipped
   the consumer first.

## Out of scope (explicit)
- The audio PRODUCER — already live (`hummingcam-audio-producer`).
- Registry publish / persistent SES deploy — CI-owned, same as the rest of the stack.
- Retraining/replacing the BirdNET model — birdnet2 reuses the existing analyzer.

## Key references
- `sage-bioclip2/VENDORED.md` — the vendoring pattern + sync obligation (the template).
- `sage-yolo2/V2-Design.md` §8 — the two-clock consumer runtime & parameter set.
- `~/AI-projects/birdnet/` — the BirdNET science to keep (analyzer, publish, geo).
- sage-waggle refs: `reolink-audio-capture`, `audio-plugin-debugging-birdnet`
  (mic quirks, faint-audio gain, geo-filter gap), `frame-anchored-batch-consumers-and-watchers`.
