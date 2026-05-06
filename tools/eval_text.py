#!/usr/bin/env python3
"""
tools/eval_text.py — Evaluate text-channel (base91) path.

Trains on data/datasets/train.jsonl (en+ru only),
evaluates compress_text/decompress_text on data/datasets/test.jsonl.

Prints:
    txt_bpc: X.XXXXXX           # overall, weighted by char count
    txt_bpc_en: X.XXXXXX
    txt_bpc_ru: X.XXXXXX
    roundtrip_pct: 100.00       # or FAIL
    train_seconds: N.N
    total_seconds: N.N
"""

import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.compress import train_model, compress_text, decompress_text

SEED = 42
DATASETS_DIR = Path(__file__).parent.parent / "data" / "datasets"
LANGS = {"en", "ru"}


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    rng = random.Random(SEED)
    train_records = load_jsonl(DATASETS_DIR / "train.jsonl")
    test_records = load_jsonl(DATASETS_DIR / "test.jsonl")

    train_msgs = [r["text"] for r in train_records if r["lang"] in LANGS]
    rng.shuffle(train_msgs)

    t0 = time.time()
    model = train_model(train_msgs)
    train_sec = time.time() - t0

    by_lang = defaultdict(list)
    for r in test_records:
        if r["lang"] in LANGS:
            by_lang[r["lang"]].append(r["text"])

    all_rt_ok = True
    per_lang = {}
    total_bits = 0
    total_chars = 0
    for lang, msgs in by_lang.items():
        bits = 0
        chars = 0
        rt_ok = 0
        n = 0
        for text in msgs:
            if not text:
                continue
            n += 1
            try:
                c = compress_text(text, model)
                d = decompress_text(c, model)
                bits += len(c.encode("utf-8")) * 8
                chars += len(text)
                if d == text:
                    rt_ok += 1
            except Exception:
                bits += len(text.encode("utf-8")) * 16
                chars += len(text)
        bpc = bits / chars if chars else 99
        per_lang[lang] = (bpc, rt_ok, n)
        total_bits += bits
        total_chars += chars
        if rt_ok != n:
            all_rt_ok = False

    overall = total_bits / total_chars if total_chars else 99
    total_sec = time.time() - t0

    print(f"txt_bpc:            {overall:.6f}")
    for lang in sorted(per_lang):
        bpc, rt, n = per_lang[lang]
        print(f"txt_bpc_{lang}:         {bpc:.6f}")
    print(f"roundtrip_pct:      {'100.00' if all_rt_ok else 'FAIL'}")
    print(f"train_seconds:      {train_sec:.1f}")
    print(f"total_seconds:      {total_sec:.1f}")


if __name__ == "__main__":
    main()
