#!/usr/bin/env python3
"""
Sweep progressive threshold configurations for model size vs quality tradeoff.
Tests different threshold schedules: higher thresholds for higher orders.
"""

import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from autoresearch.compress import NGramModel, compress, decompress

DATA = Path(__file__).parent.parent / "data"
MULTI = DATA / "multilingual"
ORDER = 9


def load_all_train():
    msgs = DATA.joinpath("train.txt").read_text("utf-8").splitlines()
    for lang in ["es", "de", "fr", "pt", "zh", "ar", "ja", "ko"]:
        msgs.extend(MULTI.joinpath(f"train_{lang}.txt").read_text("utf-8").splitlines())
    return msgs


def load_test_per_lang():
    tests = {}
    # RU
    tests["ru"] = DATA.joinpath("test.txt").read_text("utf-8").splitlines()[:250]
    # EN
    all_lines = DATA.joinpath("train.txt").read_text("utf-8").splitlines()
    en = [l for l in all_lines if not any("\u0400" <= c <= "\u04ff" for c in l)]
    tests["en"] = en[-250:]
    # Others
    for lang in ["es", "de", "fr", "pt", "zh", "ar", "ja", "ko"]:
        tests[lang] = (
            MULTI.joinpath(f"test_{lang}.txt").read_text("utf-8").splitlines()[:250]
        )
    return tests


def calc_model_size(model, thresholds):
    """Calculate binary model size with per-order thresholds."""
    total_bytes = 0
    total_contexts = 0
    for n in range(model.order + 1):
        thr = thresholds.get(n, thresholds.get("default", 1))
        for ctx, counts in model.counts[n].items():
            t = model.totals[n][ctx]
            if t >= thr:
                total_bytes += 4 + 2 + len(counts) * 6
                total_contexts += 1
    return total_bytes, total_contexts


def eval_compression(model, messages):
    """Quick BPC evaluation on a set of messages."""
    total_bits = 0
    total_chars = 0
    rt_ok = 0
    n = 0
    for msg in messages:
        if not msg.strip():
            continue
        n += 1
        try:
            c = compress(msg, model)
            d = decompress(c, model)
            total_bits += len(c) * 8
            total_chars += len(msg)
            if d == msg:
                rt_ok += 1
        except Exception:
            total_chars += len(msg)
            total_bits += len(msg.encode("utf-8")) * 8 * 2
    bpc = total_bits / total_chars if total_chars > 0 else 99
    rt = rt_ok / n * 100 if n > 0 else 0
    return bpc, rt


def export_model_size_json(model, thresholds):
    """Calculate what the JSON export size would be."""
    export = {"o": model.order, "v": model.vocab, "c": []}
    for n in range(model.order + 1):
        thr = thresholds.get(n, thresholds.get("default", 1))
        d = {}
        for ctx, counts in model.counts[n].items():
            t = model.totals[n][ctx]
            if t >= thr:
                d[ctx] = dict(counts)
        export["c"].append(d)
    raw = json.dumps(export, ensure_ascii=False, separators=(",", ":"))
    return len(raw.encode("utf-8"))


def main():
    print("=" * 90)
    print("PROGRESSIVE THRESHOLD SWEEP")
    print("=" * 90)

    # Train model
    print("Training model (order=9, all languages)...")
    t0 = time.time()
    msgs = load_all_train()
    model = NGramModel(order=ORDER)
    model.train(msgs)
    print(f"  Trained in {time.time() - t0:.1f}s, vocab={len(model.vocab)}")

    tests = load_test_per_lang()
    langs = ["ru", "en", "es", "de", "fr", "pt", "zh", "ar", "ja", "ko"]

    # Define threshold configurations to test
    configs = {
        "uniform-50": {n: (50 if n >= 3 else 1) for n in range(ORDER + 1)},
        "uniform-100": {n: (100 if n >= 3 else 1) for n in range(ORDER + 1)},
        "uniform-200": {n: (200 if n >= 3 else 1) for n in range(ORDER + 1)},
        "uniform-500": {n: (500 if n >= 3 else 1) for n in range(ORDER + 1)},
        "prog-A": {
            0: 1,
            1: 1,
            2: 1,
            3: 50,
            4: 80,
            5: 120,
            6: 200,
            7: 300,
            8: 500,
            9: 800,
        },
        "prog-B": {
            0: 1,
            1: 1,
            2: 1,
            3: 30,
            4: 50,
            5: 100,
            6: 150,
            7: 250,
            8: 400,
            9: 600,
        },
        "prog-C": {
            0: 1,
            1: 1,
            2: 1,
            3: 50,
            4: 100,
            5: 200,
            6: 400,
            7: 600,
            8: 1000,
            9: 1500,
        },
        "prog-D": {
            0: 1,
            1: 1,
            2: 1,
            3: 100,
            4: 150,
            5: 250,
            6: 400,
            7: 600,
            8: 1000,
            9: 1500,
        },
        "cut-order7-100": {n: (100 if n >= 3 else 1) for n in range(8)},
        "cut-order7-prog": {0: 1, 1: 1, 2: 1, 3: 50, 4: 80, 5: 120, 6: 200, 7: 300},
        "cut-order6-100": {n: (100 if n >= 3 else 1) for n in range(7)},
    }

    print()
    print(f"{'Config':<22} {'Bin MB':>7} {'JSON MB':>8} {'Contexts':>9}", end="")
    for lang in langs:
        print(f" {lang:>5}", end="")
    print(f" {'avg':>6} {'RT':>5}")
    print("-" * 130)

    for name, thresholds in configs.items():
        bin_size, n_ctx = calc_model_size(model, thresholds)
        json_size = export_model_size_json(model, thresholds)

        # Evaluate on all languages
        bpcs = []
        all_rt = True
        for lang in langs:
            model._cdf_cache.clear()
            bpc, rt = eval_compression(model, tests[lang])
            bpcs.append(bpc)
            if rt < 100:
                all_rt = False

        avg_bpc = sum(bpcs) / len(bpcs)

        print(
            f"{name:<22} {bin_size / 1024 / 1024:>7.2f} {json_size / 1024 / 1024:>8.1f} {n_ctx:>9}",
            end="",
        )
        for bpc in bpcs:
            print(f" {bpc:>5.2f}", end="")
        print(f" {avg_bpc:>6.3f} {'✅' if all_rt else '❌':>5}")

    print()
    print("BPC = bits per character (lower is better)")
    print("Bin MB = estimated C++ binary size")
    print("JSON MB = exported JSON size for web UI")


if __name__ == "__main__":
    main()
