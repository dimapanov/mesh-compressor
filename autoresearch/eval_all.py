#!/usr/bin/env python3
"""
autoresearch/eval_all.py — Unified evaluation on clean JSONL datasets.

Trains universal model on data/datasets/train.jsonl,
evaluates per-language on data/datasets/test.jsonl.

Usage:
    python3 -m autoresearch.eval_all 2>/dev/null | grep -E "^[a-z_]+:"
"""

import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compress import train_model, compress, decompress

SEED = 42
DATASETS_DIR = Path(__file__).parent.parent / "data" / "datasets"
CJK_LANGS = {"zh", "ja", "ko"}
CJK_WEIGHT = 3


def load_jsonl(path):
    # Auto-unpack if needed
    if not path.exists():
        zip_path = path.parent.parent / "datasets.zip"
        if zip_path.exists():
            import zipfile

            print(f"Unpacking {zip_path}...", file=sys.stderr)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(path.parent.parent)
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def main():
    rng = random.Random(SEED)

    # Load datasets
    train_records = load_jsonl(DATASETS_DIR / "train.jsonl")
    test_records = load_jsonl(DATASETS_DIR / "test.jsonl")

    # Prepare training messages (with CJK upweighting)
    train_msgs = []
    for rec in train_records:
        text = rec["text"]
        weight = CJK_WEIGHT if rec["lang"] in CJK_LANGS else 1
        for _ in range(weight):
            train_msgs.append(text)

    rng.shuffle(train_msgs)

    # Train
    t0 = time.time()
    model = train_model(train_msgs)
    train_sec = time.time() - t0

    # Group test by language
    test_by_lang = defaultdict(list)
    for rec in test_records:
        test_by_lang[rec["lang"]].append(rec)

    # Evaluate per language
    results = {}
    all_rt_ok = True

    for lang in sorted(test_by_lang.keys()):
        msgs = test_by_lang[lang]
        total_bits = 0
        total_chars = 0
        total_utf8 = 0
        total_comp = 0
        rt_ok = 0
        neg = 0
        n = 0

        for rec in msgs:
            text = rec["text"]
            if not text:
                continue
            n += 1
            try:
                c = compress(text, model)
                d = decompress(c, model)
                utf8_len = len(text.encode("utf-8"))
                comp_len = len(c)

                total_bits += comp_len * 8
                total_chars += len(text)
                total_utf8 += utf8_len
                total_comp += comp_len

                if d == text:
                    rt_ok += 1
                if comp_len > utf8_len:
                    neg += 1
            except Exception:
                total_bits += len(text.encode("utf-8")) * 16
                total_chars += len(text)
                total_utf8 += len(text.encode("utf-8"))
                total_comp += len(text.encode("utf-8")) * 2

        bpc = total_bits / total_chars if total_chars > 0 else 99
        ratio = (1 - total_comp / total_utf8) * 100 if total_utf8 > 0 else 0
        rt_pct = rt_ok / n * 100 if n > 0 else 0
        source = msgs[0].get("source", "?")

        results[lang] = {
            "bpc": bpc,
            "ratio": ratio,
            "rt": rt_pct,
            "n": n,
            "neg": neg,
            "source": source,
        }
        if rt_pct < 100:
            all_rt_ok = False

    # Print results
    total_sec = time.time() - t0
    weighted_bpc = sum(r["bpc"] * r["n"] for r in results.values()) / sum(
        r["n"] for r in results.values()
    )
    total_neg = sum(r["neg"] for r in results.values())

    for lang in sorted(results.keys()):
        r = results[lang]
        print(f"{lang}_bpc:             {r['bpc']:.6f}")
    for lang in sorted(results.keys()):
        r = results[lang]
        print(f"{lang}_ratio:           {r['ratio']:.2f}")
    for lang in sorted(results.keys()):
        r = results[lang]
        print(f"{lang}_rt:              {r['rt']:.2f}")
    for lang in sorted(results.keys()):
        r = results[lang]
        print(f"{lang}_n:               {r['n']}")
    for lang in sorted(results.keys()):
        r = results[lang]
        print(f"{lang}_source:          {r['source']}")

    print(f"weighted_bpc:       {weighted_bpc:.6f}")
    print(f"neg_count:          {total_neg}")
    print(f"roundtrip_pct:      {'100.00' if all_rt_ok else 'FAIL'}")
    print(f"train_messages:     {len(train_msgs)}")
    print(f"test_messages:      {sum(r['n'] for r in results.values())}")
    print(f"train_seconds:      {train_sec:.1f}")
    print(f"total_seconds:      {total_sec:.1f}")


if __name__ == "__main__":
    main()
