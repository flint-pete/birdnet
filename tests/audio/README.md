# Test Audio Files

Audio test data is NOT committed to git (too large). To set up:

```bash
# Run from repo root
python3 tests/download_test_audio.py
```

This downloads ~55 MB of audio from the BirdNET official test data repo
and copies the original plugin's example files. Then run:

```bash
# Generate the manifest (species labels for each file)
python3 tests/generate_manifest.py

# Run the full test suite
./tests/run-tests.sh
```

## Sources

- `soundscape.wav` — BirdNET official multi-species soundscape
  (Black-capped Chickadee, Dark-eyed Junco, House Finch, American Goldfinch)
- `s1_*.wav` — Red-backed Shrike (99%+ confidence)
- `s2_*.wav` — Eurasian Wryneck (99%+ confidence)
- `search_sample.mp3` — Blue Jay (99.7%)
- `original_*.wav/mp3` — Original plugin's Xeno-Canto samples
  (MacGillivray's Warbler, Spotted Towhee, Nuttall's Woodpecker, etc.)
