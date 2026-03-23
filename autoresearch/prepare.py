#!/usr/bin/env python3
"""
autoresearch/prepare.py — FIXED. DO NOT MODIFY.

Corpus loading, train/test split, evaluation harness for compression research.
This file is the ground truth evaluator. The agent must NOT modify it.

Metrics:
  - avg_bpc: average bits per character on test set (lower = better) — PRIMARY
  - roundtrip_ok: % of messages that survive compress→decompress (must be 100%)
  - avg_ratio: average compression ratio vs UTF-8 (higher = better)
  - fits_233: % of compressed messages that fit in 233 bytes (Meshtastic payload)

Usage:
    python3 -m autoresearch.prepare          # one-time: create train/test split
    python3 -m autoresearch.prepare --eval   # evaluate current compress.py

When run as evaluator (--eval), it:
  1. Imports compress() and decompress() from compress.py
  2. Trains the model on train set (timed)
  3. Evaluates on test set (timed)
  4. Prints results in fixed format
"""

import argparse
import math
import os
import random
import sys
import time
from pathlib import Path

# ── Constants (DO NOT CHANGE) ──────────────────────────────
CORPUS_FILE = "corpus_ru.txt"
TRAIN_FILE = "train.txt"
TEST_FILE = "test.txt"
SPLIT_SEED = 42
TEST_SIZE = 2000
MESHTASTIC_MAX_PAYLOAD = 233
TIME_BUDGET_SECONDS = 180  # 3 minutes total for train + eval
SMAZ_BASELINE_BPC = 3.2758  # baseline 5-gram + AC bits_per_char on test set (first run)


def get_root():
    """Return autoresearch/ directory."""
    return Path(__file__).parent


def get_corpus_path():
    """Return path to full corpus (one level up from autoresearch/)."""
    return get_root().parent / CORPUS_FILE


def get_data_root():
    """Return data/ directory (one level up from autoresearch/)."""
    return Path(__file__).parent.parent / "data"


# ── Data Split ─────────────────────────────────────────────
def create_split():
    """One-time: split corpus into train.txt and test.txt."""
    corpus_path = get_corpus_path()
    if not corpus_path.exists():
        print(f"ERROR: Corpus not found at {corpus_path}")
        sys.exit(1)

    lines = [
        l.strip() for l in corpus_path.read_text("utf-8").splitlines() if l.strip()
    ]
    print(f"Loaded {len(lines)} messages from {corpus_path}")

    rng = random.Random(SPLIT_SEED)
    indices = list(range(len(lines)))
    rng.shuffle(indices)

    test_indices = set(indices[:TEST_SIZE])
    train_msgs = [lines[i] for i in range(len(lines)) if i not in test_indices]
    test_msgs = [lines[i] for i in indices[:TEST_SIZE]]

    root = get_data_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / TRAIN_FILE).write_text("\n".join(train_msgs) + "\n", encoding="utf-8")
    (root / TEST_FILE).write_text("\n".join(test_msgs) + "\n", encoding="utf-8")

    print(f"Train: {len(train_msgs)} messages → {root / TRAIN_FILE}")
    print(f"Test:  {len(test_msgs)} messages → {root / TEST_FILE}")

    # Stats
    train_chars = sum(len(m) for m in train_msgs)
    test_chars = sum(len(m) for m in test_msgs)
    test_bytes = sum(len(m.encode("utf-8")) for m in test_msgs)
    print(f"Train chars: {train_chars:,}")
    print(f"Test chars:  {test_chars:,}")
    print(f"Test UTF-8 bytes: {test_bytes:,}")

    # Compute charset
    charset = set()
    for m in train_msgs:
        charset.update(m)
    for m in test_msgs:
        charset.update(m)
    print(f"Unique chars: {len(charset)}")

    return train_msgs, test_msgs


def load_train():
    """Load training messages."""
    path = get_data_root() / TRAIN_FILE
    if not path.exists():
        print(f"ERROR: {path} not found. Run: python3 -m autoresearch.prepare")
        sys.exit(1)
    return [l.strip() for l in path.read_text("utf-8").splitlines() if l.strip()]


def load_test():
    """Load test messages."""
    path = get_data_root() / TEST_FILE
    if not path.exists():
        print(f"ERROR: {path} not found. Run: python3 -m autoresearch.prepare")
        sys.exit(1)
    return [l.strip() for l in path.read_text("utf-8").splitlines() if l.strip()]


# ── Evaluation ─────────────────────────────────────────────
def evaluate(compress_fn, decompress_fn, train_fn, test_msgs):
    """
    Full evaluation pipeline:
    1. Call train_fn(train_messages) to get a trained model/state
    2. For each test message: compress, check roundtrip, measure size
    3. Return metrics dict

    compress_fn: (text: str, model) -> bytes
    decompress_fn: (data: bytes, model) -> str
    train_fn: (messages: list[str]) -> model (any object passed to compress/decompress)
    """
    # ── Phase 1: Train ──
    train_msgs = load_train()

    t_train_start = time.time()
    model = train_fn(train_msgs)
    train_seconds = time.time() - t_train_start

    # ── Phase 2: Evaluate on test set ──
    t_eval_start = time.time()

    total_chars = 0
    total_utf8_bytes = 0
    total_compressed_bytes = 0
    roundtrip_ok = 0
    roundtrip_fail = 0
    fits_233 = 0
    errors = 0
    error_messages = []

    for i, msg in enumerate(test_msgs):
        utf8 = msg.encode("utf-8")
        total_chars += len(msg)
        total_utf8_bytes += len(utf8)

        try:
            compressed = compress_fn(msg, model)
            comp_len = len(compressed)
            total_compressed_bytes += comp_len

            if comp_len <= MESHTASTIC_MAX_PAYLOAD:
                fits_233 += 1

            # Roundtrip check
            try:
                decompressed = decompress_fn(compressed, model)
                if decompressed == msg:
                    roundtrip_ok += 1
                else:
                    roundtrip_fail += 1
                    if len(error_messages) < 5:
                        error_messages.append(
                            f"  MISMATCH [{i}]: '{msg[:50]}...' -> '{decompressed[:50]}...'"
                        )
            except Exception as e:
                roundtrip_fail += 1
                if len(error_messages) < 5:
                    error_messages.append(f"  DECOMPRESS ERROR [{i}]: {e}")

        except Exception as e:
            errors += 1
            total_compressed_bytes += len(utf8)  # count as uncompressed
            if len(error_messages) < 5:
                error_messages.append(f"  COMPRESS ERROR [{i}]: {e}")

    eval_seconds = time.time() - t_eval_start
    total_seconds = train_seconds + eval_seconds

    # ── Compute metrics ──
    n_test = len(test_msgs)
    avg_bpc = (total_compressed_bytes * 8) / total_chars if total_chars > 0 else 999
    avg_ratio = (
        (1 - total_compressed_bytes / total_utf8_bytes) * 100
        if total_utf8_bytes > 0
        else 0
    )
    roundtrip_pct = roundtrip_ok / n_test * 100 if n_test > 0 else 0
    fits_pct = fits_233 / n_test * 100 if n_test > 0 else 0

    return {
        "avg_bpc": avg_bpc,
        "avg_ratio": avg_ratio,
        "roundtrip_pct": roundtrip_pct,
        "fits_233_pct": fits_pct,
        "train_seconds": train_seconds,
        "eval_seconds": eval_seconds,
        "total_seconds": total_seconds,
        "total_chars": total_chars,
        "total_utf8_bytes": total_utf8_bytes,
        "total_compressed_bytes": total_compressed_bytes,
        "n_test": n_test,
        "roundtrip_ok": roundtrip_ok,
        "roundtrip_fail": roundtrip_fail,
        "errors": errors,
        "fits_233": fits_233,
        "error_messages": error_messages,
    }


def print_results(results):
    """Print results in fixed, grep-friendly format."""
    print("---")
    print(f"avg_bpc:            {results['avg_bpc']:.6f}")
    print(f"avg_ratio:          {results['avg_ratio']:.2f}")
    print(f"roundtrip_pct:      {results['roundtrip_pct']:.2f}")
    print(f"fits_233_pct:       {results['fits_233_pct']:.2f}")
    print(f"train_seconds:      {results['train_seconds']:.1f}")
    print(f"eval_seconds:       {results['eval_seconds']:.1f}")
    print(f"total_seconds:      {results['total_seconds']:.1f}")
    print(f"total_chars:        {results['total_chars']}")
    print(f"total_utf8_bytes:   {results['total_utf8_bytes']}")
    print(f"total_compressed:   {results['total_compressed_bytes']}")
    print(f"n_test:             {results['n_test']}")
    print(f"roundtrip_ok:       {results['roundtrip_ok']}")
    print(f"roundtrip_fail:     {results['roundtrip_fail']}")
    print(f"errors:             {results['errors']}")
    print(f"fits_233:           {results['fits_233']}")
    print(f"baseline_bpc:       {SMAZ_BASELINE_BPC}")
    improvement = (SMAZ_BASELINE_BPC - results["avg_bpc"]) / SMAZ_BASELINE_BPC * 100
    print(f"improvement_pct:    {improvement:.2f}")

    if results["error_messages"]:
        print("\nFirst errors:")
        for em in results["error_messages"]:
            print(em)


# ── Main ───────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="autoresearch: prepare data & evaluate"
    )
    parser.add_argument(
        "--eval", action="store_true", help="Evaluate current compress.py"
    )
    args = parser.parse_args()

    if args.eval:
        # Import from compress.py
        sys.path.insert(0, str(get_root()))
        try:
            from compress import compress, decompress, train_model
        except ImportError as e:
            print(f"ERROR: Cannot import from compress.py: {e}")
            sys.exit(1)

        test_msgs = load_test()
        print(f"Evaluating on {len(test_msgs)} test messages...")
        results = evaluate(compress, decompress, train_model, test_msgs)
        print_results(results)

        # Check time budget
        if results["total_seconds"] > TIME_BUDGET_SECONDS:
            print(
                f"\nWARNING: Exceeded time budget ({results['total_seconds']:.0f}s > {TIME_BUDGET_SECONDS}s)"
            )

        # Check roundtrip
        if results["roundtrip_pct"] < 100.0:
            print(f"\nFAILURE: Roundtrip not 100% ({results['roundtrip_pct']:.2f}%)")
    else:
        create_split()


if __name__ == "__main__":
    main()
