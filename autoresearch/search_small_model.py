#!/usr/bin/env python3
"""
autoresearch/search_small_model.py — Find the smallest model with acceptable compression.

Systematically explores: order × threshold combinations.
For each variant, measures BPC on test set AND model size.

Goal: find the Pareto frontier of (model_size_MB, avg_bpc).
      Ideal: <4 MB model (fits in ESP32 flash) with best possible BPC.

Usage:
    python3 -m autoresearch.search_small_model
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from autoresearch.compress import (
    NGramModel,
    compress,
    decompress,
    BOS,
    EOF,
    ORDER,
)
from collections import Counter, defaultdict


def train_with_order(messages, order):
    """Train model with specific order."""
    model = NGramModel(order=order)
    model.train(messages)
    return model


def calc_model_size(model, threshold):
    """Calculate model size in compact binary format (bytes) and context count."""
    total_bytes = 0
    total_contexts = 0
    for n in range(model.order + 1):
        min_count = threshold if n >= 3 else 1
        for ctx, counts in model.counts[n].items():
            t = model.totals[n][ctx]
            if t >= min_count:
                total_bytes += 4 + 2 + len(counts) * 6
                total_contexts += 1
    return total_bytes, total_contexts


def calc_json_size(model, threshold):
    """Calculate JSON model size."""
    export = {"o": model.order, "v": model.vocab, "c": []}
    for n in range(model.order + 1):
        d = {}
        min_count = threshold if n >= 3 else 1
        for ctx, counts in model.counts[n].items():
            t = model.totals[n][ctx]
            if t >= min_count:
                d[ctx] = dict(counts)
        export["c"].append(d)
    return len(json.dumps(export, ensure_ascii=False, separators=(",", ":")))


def evaluate_bpc(model, test_msgs):
    """Calculate average bits per character on test set."""
    total_chars = 0
    total_bytes = 0
    ok = 0

    for msg in test_msgs:
        total_chars += len(msg)
        try:
            c = compress(msg, model)
            total_bytes += len(c)
            d = decompress(c, model)
            if d == msg:
                ok += 1
            model.clear_cache()
        except:
            total_bytes += len(msg.encode("utf-8"))
            model.clear_cache()

    bpc = (total_bytes * 8) / total_chars if total_chars else 999
    rt = ok / len(test_msgs) * 100
    return bpc, rt


def main():
    data_dir = Path(__file__).parent.parent / "data"
    train_msgs = [
        l.strip() for l in open(data_dir / "train.txt", encoding="utf-8") if l.strip()
    ]
    test_msgs = [
        l.strip() for l in open(data_dir / "test.txt", encoding="utf-8") if l.strip()
    ]

    # Use subset for speed
    test_sub = test_msgs[:200]

    print(f"Train: {len(train_msgs)}, Test: {len(test_sub)} (subset)")
    print()

    orders = [2, 3, 4, 5, 6, 7, 8, 9, 11]
    thresholds = [1, 2, 3, 5, 10, 20, 50, 100]

    results = []

    print(
        f"{'order':>5} {'thr':>4} {'BPC':>7} {'RT%':>6} {'bin_MB':>7} {'json_MB':>8} {'contexts':>10} {'ESP32':>6}"
    )
    print("=" * 68)

    for order in orders:
        t0 = time.time()
        model = train_with_order(train_msgs, order)
        train_s = time.time() - t0

        # Evaluate BPC once per order (threshold barely affects it)
        t0 = time.time()
        bpc, rt = evaluate_bpc(model, test_sub)
        eval_s = time.time() - t0

        for threshold in thresholds:
            bin_sz, n_ctx = calc_model_size(model, threshold)
            json_sz = calc_json_size(model, threshold)
            bin_mb = bin_sz / 1024 / 1024
            json_mb = json_sz / 1024 / 1024

            if bin_mb > 100:
                continue

            fits = "✅" if bin_mb <= 4 else ("⚠️ " if bin_mb <= 16 else "❌")

            print(
                f"{order:>5} {threshold:>4} {bpc:>7.3f} {rt:>5.1f}% {bin_mb:>6.1f}M {json_mb:>7.1f}M {n_ctx:>10,} {fits}"
            )

            results.append(
                {
                    "order": order,
                    "threshold": threshold,
                    "bpc": round(bpc, 4),
                    "rt": round(rt, 2),
                    "bin_mb": round(bin_mb, 2),
                    "json_mb": round(json_mb, 2),
                    "contexts": n_ctx,
                    "train_s": round(train_s, 1),
                }
            )

        print()

    # Pareto frontier
    print("=" * 68)
    print("PARETO FRONTIER — best BPC for each size point (ESP32-compatible)")
    print("=" * 68)

    esp32 = [r for r in results if r["bin_mb"] <= 4 and r["rt"] >= 100]
    esp32.sort(key=lambda r: r["bpc"])

    seen = set()
    print(
        f"{'order':>5} {'thr':>4} {'BPC':>7} {'bin_MB':>7} {'json_MB':>8} {'contexts':>10}"
    )
    print("-" * 50)
    for r in esp32:
        key = f"{r['order']}-{r['threshold']}"
        if key not in seen:
            seen.add(key)
            print(
                f"{r['order']:>5} {r['threshold']:>4} {r['bpc']:>7.3f} {r['bin_mb']:>6.1f}M {r['json_mb']:>7.1f}M {r['contexts']:>10,}"
            )

    if esp32:
        best = esp32[0]
        print()
        print(f"🏆 BEST ESP32: order={best['order']}, threshold={best['threshold']}")
        print(
            f"   BPC={best['bpc']}, binary={best['bin_mb']} MB, JSON={best['json_mb']} MB"
        )
        print(f"   {best['contexts']:,} contexts, train={best['train_s']}s")

    # ALL results — best BPC at any size
    all_sorted = sorted([r for r in results if r["rt"] >= 100], key=lambda r: r["bpc"])
    if all_sorted:
        best_any = all_sorted[0]
        print()
        print(
            f"🥇 BEST OVERALL: order={best_any['order']}, threshold={best_any['threshold']}"
        )
        print(
            f"   BPC={best_any['bpc']}, binary={best_any['bin_mb']} MB, JSON={best_any['json_mb']} MB"
        )

    # Save
    out = Path(__file__).parent / "search_results.tsv"
    with open(out, "w") as f:
        f.write("order\tthreshold\tbpc\trt_pct\tbin_mb\tjson_mb\tcontexts\ttrain_s\n")
        for r in results:
            f.write(
                f"{r['order']}\t{r['threshold']}\t{r['bpc']}\t{r['rt']}\t{r['bin_mb']}\t{r['json_mb']}\t{r['contexts']}\t{r['train_s']}\n"
            )
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
