# BirdNET-species — Future Enhancements

Deferred work items, captured so they aren't lost. Each entry: what, why,
where in the code, and a sketch of the fix. Not yet scheduled.

---

## 1. Scope `--save-match` to biophony only (skip human-made / abiotic classes)

**What:** Right now `--save-match "*:0.5"` archives a FLAC clip for *any* class
at or above the threshold — including the non-biological BirdNET classes
(Engine, Siren, Noise, Environmental, Human*, Dog, Power tools, Fireworks, Gun).
On a roadside/ranch node that means we burn storage saving clips of passing
vehicles, generators, and ambient noise.

**Why:** The science target is biological sound (biophony). Anthropogenic and
geophysical detections are still published as topics (see the
biophony/anthrophony/geophony routing added in 0.3.0), but we rarely want to
*keep the audio* for them. Clip storage should follow the biology.

**Where:** `app.py` — the save decision (`save_match.py` rules evaluated in the
run cycle) and `sound_category()` (already added in 0.3.0).

**Sketch:** Before evaluating save-match rules for a detection, skip it when
`sound_category(det["scientific_name"]) != "biophony"` — OR add a
`--save-categories biophony[,anthrophony,geophony]` arg (default `biophony`) so
an operator can opt back into saving non-bio clips when the deployment wants the
full soundscape. Keep the wildcard rule semantics; just gate on category first.
Add a test in `tests/test_save_match.py` covering "an Engine detection at 0.9
does NOT save when categories=biophony".

---

## 2. Make live-GPS self-location actually work (pywaggle2)

**What:** `--gps-subscribe` is supposed to let the plugin self-locate from the
node's live `sys.gps.*` stream (so no hardcoded `--lat/--lon`, and mobile nodes
work). Verified 2026-07-11 on W06C (job 5680) that it does NOT work yet: the app
opens a ~3 s `plugin.subscribe` on `sys.gps.lat/lon`, but GPS-equipped nodes
publish position only every ~2 min, so the short window almost always misses it
→ "No node location available → geo-filtering disabled". We currently work
around it by passing explicit coords on fixed nodes (e.g. W06C).

**Why:** True self-location is the goal — portable jobs, correct geo-filtering
on mobile deployments, no per-node coordinate edits.

**Where:** `app.py` — `_coords_from_live_gps()` and `read_node_location()`.

**Sketch:** With pywaggle2, read the LAST cached `sys.gps.*` value (data-API /
pywaggle2 accessor) instead of a short live subscribe — a fix is available
instantly regardless of publish cadence. When it lands, the explicit `--lat/--lon`
in `jobs/birdnet-w06c-gps.yaml` can be dropped in favor of `--gps-subscribe`.
See also the platform note in `~/AI-projects/sage-design-planning/Infra-problems-to-fix.md` about
runtime GPS/VSN injection.
