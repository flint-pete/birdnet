#!/usr/bin/env python3
"""
Download North American bird audio from Wikimedia Commons for testing.
Uses the Wikimedia API to find audio files, then downloads them.
Run from repo root: python3 tests/download_na_birds.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(SCRIPT_DIR, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# Known Wikimedia Commons audio files for North American birds
# Format: (filename_on_commons, local_name, scientific_name, common_name)
# These are CC-licensed recordings from Xeno-Canto uploaded to Wikimedia
KNOWN_FILES = [
    ("Cardinalis cardinalis - Northern Cardinal XC175226.mp3",
     "northern_cardinal.mp3", "Cardinalis cardinalis", "Northern Cardinal"),
    ("Corvus brachyrhynchos - American Crow XC110263.mp3",
     "american_crow.mp3", "Corvus brachyrhynchos", "American Crow"),
    ("Picoides pubescens - Downy Woodpecker XC115431.mp3",
     "downy_woodpecker.mp3", "Dryobates pubescens", "Downy Woodpecker"),
    ("Sitta carolinensis - White-breasted Nuthatch XC121069.ogg",
     "white_breasted_nuthatch.ogg", "Sitta carolinensis", "White-breasted Nuthatch"),
    ("Carolina Wren (Thryothorus ludovicianus) - New Jersey 2023-02-23.mp3",
     "carolina_wren.mp3", "Thryothorus ludovicianus", "Carolina Wren"),
]

# Additional species we'll search for
SEARCH_SPECIES = [
    ("Turdus migratorius", "American Robin", "american_robin"),
    ("Zenaida macroura", "Mourning Dove", "mourning_dove"),
    ("Mimus polyglottos", "Northern Mockingbird", "northern_mockingbird"),
    ("Melospiza melodia", "Song Sparrow", "song_sparrow"),
    ("Agelaius phoeniceus", "Red-winged Blackbird", "red_winged_blackbird"),
    ("Strix varia", "Barred Owl", "barred_owl"),
    ("Buteo jamaicensis", "Red-tailed Hawk", "red_tailed_hawk"),
    ("Setophaga petechia", "Yellow Warbler", "yellow_warbler"),
    ("Vireo olivaceus", "Red-eyed Vireo", "red_eyed_vireo"),
    ("Sialia sialis", "Eastern Bluebird", "eastern_bluebird"),
    ("Icterus galbula", "Baltimore Oriole", "baltimore_oriole"),
    ("Hylocichla mustelina", "Wood Thrush", "wood_thrush"),
    ("Gavia immer", "Common Loon", "common_loon"),
    ("Megaceryle alcyon", "Belted Kingfisher", "belted_kingfisher"),
    ("Haliaeetus leucocephalus", "Bald Eagle", "bald_eagle"),
]

API_BASE = "https://commons.wikimedia.org/w/api.php"


def get_file_url(title: str) -> str | None:
    """Get direct download URL for a Wikimedia Commons file."""
    params = urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    })
    url = f"{API_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "BirdNET-test-suite/1.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        ii = page.get("imageinfo", [{}])
        if ii:
            return ii[0].get("url")
    return None


def search_audio(query: str) -> str | None:
    """Search Wikimedia Commons for an audio file matching query."""
    params = urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srnamespace": "6",
        "srlimit": "5",
        "format": "json",
    })
    url = f"{API_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "BirdNET-test-suite/1.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    results = data.get("query", {}).get("search", [])
    for r in results:
        title = r["title"]
        # Only audio files
        if title.lower().endswith((".mp3", ".ogg", ".wav", ".flac")):
            return title
    return None


def download_file(url: str, dest: str) -> bool:
    """Download a file from URL to dest path."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BirdNET-test-suite/1.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        with open(dest, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        print(f"    Download failed: {e}")
        return False


def main():
    downloaded = []

    # Phase 1: Download known files
    print("Phase 1: Downloading known audio files...")
    for commons_name, local_name, sci_name, common_name in KNOWN_FILES:
        dest = os.path.join(AUDIO_DIR, local_name)
        if os.path.exists(dest):
            print(f"  Already exists: {local_name}")
            downloaded.append((local_name, sci_name, common_name))
            continue

        title = f"File:{commons_name}"
        print(f"  {common_name} ({sci_name})...", end=" ", flush=True)
        try:
            file_url = get_file_url(title)
            if file_url and download_file(file_url, dest):
                size = os.path.getsize(dest)
                print(f"OK ({size:,} bytes)")
                downloaded.append((local_name, sci_name, common_name))
            else:
                print("URL not found")
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(1)

    # Phase 2: Search for additional species
    print("\nPhase 2: Searching for additional species...")
    for sci_name, common_name, file_prefix in SEARCH_SPECIES:
        # Check if we already have this species
        ext_candidates = [".mp3", ".ogg", ".wav", ".flac"]
        already_have = any(
            os.path.exists(os.path.join(AUDIO_DIR, f"{file_prefix}{ext}"))
            for ext in ext_candidates
        )
        if already_have:
            print(f"  Already exists: {common_name}")
            continue

        print(f"  Searching: {common_name} ({sci_name})...", end=" ", flush=True)
        try:
            # Search with scientific name first
            title = search_audio(f"{sci_name} call song")
            if not title:
                title = search_audio(f"{common_name} bird call")
            if title:
                file_url = get_file_url(title)
                if file_url:
                    ext = os.path.splitext(title)[-1].lower()
                    if not ext:
                        ext = ".mp3"
                    local_name = f"{file_prefix}{ext}"
                    dest = os.path.join(AUDIO_DIR, local_name)
                    if download_file(file_url, dest):
                        size = os.path.getsize(dest)
                        print(f"OK ({size:,} bytes) <- {title}")
                        downloaded.append((local_name, sci_name, common_name))
                    else:
                        print("download failed")
                else:
                    print("no URL")
            else:
                print("not found")
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)  # Be polite to Wikimedia

    # Summary
    print(f"\n{'='*60}")
    print(f"Downloaded {len(downloaded)} North American bird audio files:")
    for local_name, sci_name, common_name in sorted(downloaded):
        size = os.path.getsize(os.path.join(AUDIO_DIR, local_name))
        print(f"  {local_name:40s} {common_name:25s} {size:>10,} bytes")

    # Write a labels file
    labels_path = os.path.join(AUDIO_DIR, "na_bird_labels.json")
    labels = {
        local_name: {"scientific_name": sci, "common_name": common}
        for local_name, sci, common in downloaded
    }
    with open(labels_path, "w") as f:
        json.dump(labels, f, indent=2)
    print(f"\nLabels saved to {labels_path}")


if __name__ == "__main__":
    main()
