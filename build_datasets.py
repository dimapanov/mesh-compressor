#!/usr/bin/env python3
"""
build_datasets.py — Build clean JSONL train/test datasets from all sources.

Guarantees:
- Zero overlap between train and test
- Test set prefers real MQTT data over synthetic
- Languages without real data: synthetic test only, clearly marked
"""

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SEED = 42
TEST_PER_LANG = 500
DATA_DIR = Path(__file__).parent / "data"
MULTI_DIR = DATA_DIR / "multilingual"
MQTT_DIR = DATA_DIR / "mqtt_export"
OUT_DIR = DATA_DIR / "datasets"


def load_lines(path):
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text("utf-8").splitlines() if l.strip()]


def detect_lang(text):
    cyrillic = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    return "ru" if cyrillic > len(text) * 0.2 else "en"


def main():
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Collect per-language, per-source
    real = defaultdict(list)  # lang → [text, ...]  (from MQTT or original Meshtastic)
    synth = defaultdict(list)  # lang → [text, ...]  (from template generator)

    # Original RU+EN
    for line in load_lines(DATA_DIR / "train.txt") + load_lines(DATA_DIR / "test.txt"):
        real[detect_lang(line)].append(line)

    # MQTT
    for f in sorted(MQTT_DIR.glob("train_*.txt")) + sorted(MQTT_DIR.glob("test_*.txt")):
        lang = f.stem.split("_", 1)[1]
        real[lang].extend(load_lines(f))

    # Synthetic
    for f in sorted(MULTI_DIR.glob("train_*.txt")) + sorted(
        MULTI_DIR.glob("test_*.txt")
    ):
        lang = f.stem.split("_", 1)[1]
        if lang in ("all",):
            continue
        synth[lang].extend(load_lines(f))

    # Deduplicate within each pool, and remove from synth anything that's in real (globally)
    all_real_texts = set()
    for lang in real:
        real[lang] = list(dict.fromkeys(real[lang]))
        all_real_texts.update(real[lang])
    for lang in synth:
        synth[lang] = list(
            dict.fromkeys(m for m in synth[lang] if m not in all_real_texts)
        )

    all_langs = sorted(set(list(real.keys()) + list(synth.keys())))

    # Split
    train_records = []
    test_records = []
    global_test_set = set()  # for global dedup

    print(
        f"{'Lang':>4} {'Real':>6} {'Synth':>6} {'Test':>5} {'Test src':>10} {'Train':>6}"
    )
    print("-" * 50)

    for lang in all_langs:
        r = real.get(lang, [])
        s = synth.get(lang, [])
        rng.shuffle(r)
        rng.shuffle(s)

        total = len(r) + len(s)
        if total == 0:
            continue

        # Test: prefer real, fall back to synthetic
        test_size = min(TEST_PER_LANG, max(50, total // 10))

        if len(r) >= 20:
            # Use real data for test
            n_test = min(test_size, len(r))
            test_msgs = [(m, "real") for m in r[:n_test]]
            train_from_real = r[n_test:]
            train_from_synth = s
        else:
            # Not enough real → use synthetic for test
            n_test = min(test_size, len(s))
            test_msgs = [(m, "synthetic") for m in s[:n_test]]
            train_from_real = r
            train_from_synth = s[n_test:]

        # Add to global sets
        for m, src in test_msgs:
            global_test_set.add(m)
            test_records.append({"text": m, "lang": lang, "source": src})

        for m in train_from_real:
            if m not in global_test_set:
                train_records.append({"text": m, "lang": lang, "source": "real"})
        for m in train_from_synth:
            if m not in global_test_set:
                train_records.append({"text": m, "lang": lang, "source": "synthetic"})

        n_real_test = sum(1 for _, src in test_msgs if src == "real")
        n_synth_test = sum(1 for _, src in test_msgs if src == "synthetic")
        n_train = len(train_from_real) + len(train_from_synth)
        test_src = (
            "real"
            if n_real_test == len(test_msgs)
            else ("synth" if n_synth_test == len(test_msgs) else "mixed")
        )
        print(
            f"{lang:>4} {len(r):>6} {len(s):>6} {len(test_msgs):>5} {test_src:>10} {n_train:>6}"
        )

    # Final pass: remove any train record whose text is in test
    train_records = [r for r in train_records if r["text"] not in global_test_set]

    # Final dedup check
    train_texts = set(r["text"] for r in train_records)
    test_texts = set(r["text"] for r in test_records)
    overlap = train_texts & test_texts
    assert len(overlap) == 0, f"BUG: {len(overlap)} overlap!"

    # Shuffle and write
    rng.shuffle(train_records)

    with open(OUT_DIR / "train.jsonl", "w", encoding="utf-8") as f:
        for rec in train_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(OUT_DIR / "test.jsonl", "w", encoding="utf-8") as f:
        for rec in test_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Stats
    print(f"\n{'=' * 50}")
    print(f"Train: {len(train_records):,} messages")
    print(f"Test:  {len(test_records):,} messages")
    print(f"Overlap: {len(overlap)}")

    test_by_source = Counter(r["source"] for r in test_records)
    print(f"Test sources: {dict(test_by_source)}")


if __name__ == "__main__":
    main()
