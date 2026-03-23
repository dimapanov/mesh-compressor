#!/usr/bin/env python3
"""Unpack training data from zip archive. Run once after cloning.

Usage:
    python3 unpack_data.py
"""

import zipfile
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def unpack():
    archive = DATA_DIR / "datasets.zip"
    if not archive.exists():
        print(f"ERROR: {archive} not found")
        return

    print(f"Unpacking {archive}...")
    with zipfile.ZipFile(archive) as z:
        z.extractall(DATA_DIR)
        print(f"  Extracted {len(z.namelist())} files")

    # Verify
    for name in ["datasets/train.jsonl", "datasets/test.jsonl"]:
        p = DATA_DIR / name
        if p.exists():
            lines = sum(1 for _ in open(p))
            size_mb = p.stat().st_size / 1024 / 1024
            print(f"  ✓ {name}: {lines:,} records ({size_mb:.1f} MB)")
        else:
            print(f"  ✗ {name}: MISSING")


if __name__ == "__main__":
    unpack()
