#!/usr/bin/env python3
"""Classify all audio files in tests/audio/ and generate manifest.json."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import BirdNETClassifier

classifier = BirdNETClassifier(min_confidence=0.25, top_k=3)
audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")

manifest = {}
for f in sorted(os.listdir(audio_dir)):
    if not f.endswith(('.wav', '.mp3', '.flac', '.ogg')):
        continue
    path = os.path.join(audio_dir, f)
    print(f"\n{'='*60}")
    print(f"FILE: {f}")

    try:
        dets = classifier.classify_file(path)
        species_best = {}
        for d in dets:
            key = d['scientific_name']
            if key not in species_best or d['confidence'] > species_best[key]['confidence']:
                species_best[key] = d

        top = sorted(species_best.values(), key=lambda x: x['confidence'], reverse=True)
        manifest[f] = {
            'total_detections': len(dets),
            'unique_species': len(top),
            'top_species': [
                {'scientific_name': d['scientific_name'], 'common_name': d['common_name'],
                 'confidence': round(d['confidence'], 4)}
                for d in top[:5]
            ]
        }
        for d in top[:5]:
            print(f"  {d['scientific_name']} ({d['common_name']}): {d['confidence']:.4f}")
        if not top:
            print(f"  (no detections)")
    except Exception as e:
        print(f"  ERROR: {e}")
        manifest[f] = {'error': str(e)}

out = os.path.join(audio_dir, 'manifest.json')
with open(out, 'w') as mf:
    json.dump(manifest, mf, indent=2)
print(f"\nManifest saved to {out}")
print(f"Total files: {len(manifest)}")
print(f"Files with detections: {sum(1 for v in manifest.values() if v.get('unique_species', 0) > 0)}")
