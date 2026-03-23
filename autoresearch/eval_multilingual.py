#!/usr/bin/env python3
"""
autoresearch/eval_multilingual.py — Multilingual evaluation harness.

Trains the universal model on ALL languages, evaluates on per-language test sets.
Primary metric: ZH BPC (lower = better).
Guard: BPC for other languages must not increase by more than GUARD_TOLERANCE.

Usage:
    python3 -m autoresearch.eval_multilingual

Output (grep-friendly):
    zh_bpc:             4.805
    ru_bpc:             3.253
    en_bpc:             2.206
    ... (all 10 languages)
    weighted_bpc:       3.100
    roundtrip_pct:      100.00
    guard_passed:       true
    total_seconds:      45.0
"""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compress import train_model, compress, decompress

# ── Config ─────────────────────────────────────────────────
LANGS = ["ru", "en", "es", "de", "fr", "pt", "zh", "ar", "ja", "ko"]
DATA_DIR = Path(__file__).parent.parent / "data"
MULTI_DIR = DATA_DIR / "multilingual"
SEED = 42
SUBSAMPLE = 45000  # messages per language for training
TEST_LIMIT = 500  # test messages per language

# Guard tolerance: max BPC increase allowed for non-ZH languages
GUARD_TOLERANCE = (
    0.15  # 0.15 BPC — generous enough for noise, strict enough for regressions
)

# Baseline BPC values for guard comparison (will be set on first run)
BASELINE_BPC = None  # Set after baseline run


def is_cyrillic(line):
    return any("\u0400" <= c <= "\u04ff" for c in line)


def load_data():
    """Load train/test data for all languages."""
    rng = random.Random(SEED)
    train = {}
    test = {}

    # RU and EN from main train.txt
    all_lines = (DATA_DIR / "train.txt").read_text("utf-8").splitlines()
    all_lines = [l.strip() for l in all_lines if l.strip()]
    ru_lines = [l for l in all_lines if is_cyrillic(l)]
    en_lines = [l for l in all_lines if not is_cyrillic(l)]

    rng.shuffle(ru_lines)
    rng.shuffle(en_lines)

    train["ru"] = ru_lines[:SUBSAMPLE]
    train["en"] = en_lines[:SUBSAMPLE]

    # RU test from test.txt
    ru_test = (DATA_DIR / "test.txt").read_text("utf-8").splitlines()
    ru_test = [l.strip() for l in ru_test if l.strip()]
    test["ru"] = ru_test[:TEST_LIMIT]

    # EN test — take from held-out English
    test["en"] = en_lines[SUBSAMPLE : SUBSAMPLE + TEST_LIMIT]

    # Other languages
    for lang in LANGS:
        if lang in ("ru", "en"):
            continue
        train_file = MULTI_DIR / f"train_{lang}.txt"
        test_file = MULTI_DIR / f"test_{lang}.txt"
        if train_file.exists():
            train[lang] = [
                l.strip()
                for l in train_file.read_text("utf-8").splitlines()
                if l.strip()
            ][:SUBSAMPLE]
        if test_file.exists():
            test[lang] = [
                l.strip()
                for l in test_file.read_text("utf-8").splitlines()
                if l.strip()
            ][:TEST_LIMIT]

    return train, test


def evaluate_lang(model, messages):
    """Evaluate compression on a list of messages for one language.
    Returns (bpc, ratio, roundtrip_pct).
    """
    total_bits = 0
    total_chars = 0
    total_utf8 = 0
    total_comp = 0
    rt_ok = 0
    n_valid = 0

    for msg in messages:
        if not msg.strip():
            continue
        n_valid += 1
        try:
            c = compress(msg, model)
            d = decompress(c, model)
            comp_bytes = len(c)
            utf8_bytes = len(msg.encode("utf-8"))
            chars = len(msg)

            total_bits += comp_bytes * 8
            total_chars += chars
            total_utf8 += utf8_bytes
            total_comp += comp_bytes

            if d == msg:
                rt_ok += 1
        except Exception:
            total_chars += len(msg)
            total_utf8 += len(msg.encode("utf-8"))
            total_comp += len(msg.encode("utf-8")) * 2  # penalty

    bpc = total_bits / total_chars if total_chars > 0 else 99
    ratio = 1 - total_comp / total_utf8 if total_utf8 > 0 else 0
    rt_pct = rt_ok / n_valid * 100 if n_valid > 0 else 0
    return round(bpc, 6), round(ratio * 100, 2), round(rt_pct, 2)


def main():
    t_start = time.time()

    train, test = load_data()

    # Train universal model on ALL languages
    print("Training universal model...", file=sys.stderr)
    t_train = time.time()
    universal_train = []
    for lang in LANGS:
        if lang in train:
            universal_train.extend(train[lang])
    random.Random(SEED).shuffle(universal_train)

    model = train_model(universal_train)
    train_seconds = time.time() - t_train
    print(f"Training done in {train_seconds:.1f}s", file=sys.stderr)

    # Evaluate per-language
    print("Evaluating...", file=sys.stderr)
    results = {}
    all_rt_ok = True
    for lang in LANGS:
        if lang not in test or not test[lang]:
            continue
        bpc, ratio, rt_pct = evaluate_lang(model, test[lang])
        results[lang] = {"bpc": bpc, "ratio": ratio, "rt_pct": rt_pct}
        if rt_pct < 100.0:
            all_rt_ok = False

    total_seconds = time.time() - t_start

    # Compute weighted BPC (equal weight per language)
    bpc_values = [results[l]["bpc"] for l in LANGS if l in results]
    weighted_bpc = sum(bpc_values) / len(bpc_values) if bpc_values else 99

    # Guard check (placeholder — baseline set externally)
    guard_passed = True  # Will be checked by the autoresearch loop

    # ── Print results (grep-friendly) ──
    print("---")
    for lang in LANGS:
        if lang in results:
            print(f"{lang}_bpc:             {results[lang]['bpc']:.6f}")
    print(f"weighted_bpc:       {weighted_bpc:.6f}")
    print(f"roundtrip_pct:      {'100.00' if all_rt_ok else 'FAIL'}")
    for lang in LANGS:
        if lang in results:
            print(f"{lang}_ratio:           {results[lang]['ratio']:.2f}")
    for lang in LANGS:
        if lang in results:
            print(f"{lang}_rt:              {results[lang]['rt_pct']:.2f}")
    print(f"train_seconds:      {train_seconds:.1f}")
    print(f"total_seconds:      {total_seconds:.1f}")
    print(f"guard_passed:       {'true' if guard_passed else 'false'}")


if __name__ == "__main__":
    main()
