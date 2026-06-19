#!/usr/bin/env python3
"""Download test audio files from BirdNET official test data repo."""
import os
import shutil
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
AUDIO_DIR = os.path.join(SCRIPT_DIR, "audio")

FILES = {
    "soundscape.wav": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/soundscape/soundscape.wav",
    "s1_file01.wav": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/embeddings/embeddings-dataset/s1/file01.wav",
    "s1_file02.wav": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/embeddings/embeddings-dataset/s1/file02.wav",
    "s1_file03.wav": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/embeddings/embeddings-dataset/s1/file03.wav",
    "s2_file01.wav": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/embeddings/embeddings-dataset/s2/file01.wav",
    "s2_file02.wav": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/embeddings/embeddings-dataset/s2/file02.wav",
    "s2_file03.wav": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/embeddings/embeddings-dataset/s2/file03.wav",
    "search_sample.mp3": "https://raw.githubusercontent.com/birdnet-team/birdnet-test-data/main/embeddings/search_sample.mp3",
}

os.makedirs(AUDIO_DIR, exist_ok=True)

print("Downloading BirdNET test audio files...")
for name, url in FILES.items():
    dest = os.path.join(AUDIO_DIR, name)
    if os.path.exists(dest):
        print(f"  Already exists: {name}")
        continue
    print(f"  Downloading {name}...", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        size = os.path.getsize(dest)
        print(f"OK ({size:,} bytes)")
    except Exception as e:
        print(f"FAILED: {e}")

# Copy original plugin example audio
example_dir = os.path.join(REPO_DIR, "example")
if os.path.isdir(example_dir):
    print("\nCopying original plugin example audio...")
    for f in os.listdir(example_dir):
        if f.endswith((".wav", ".mp3")):
            src = os.path.join(example_dir, f)
            dst = os.path.join(AUDIO_DIR, f"original_{f.replace(' ', '_')}")
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"  Copied {f}")

print(f"\nTest audio files in {AUDIO_DIR}:")
total = 0
for f in sorted(os.listdir(AUDIO_DIR)):
    if f.endswith((".wav", ".mp3", ".flac", ".ogg")):
        size = os.path.getsize(os.path.join(AUDIO_DIR, f))
        print(f"  {f}: {size:,} bytes")
        total += 1
print(f"\nTotal: {total} audio files")
