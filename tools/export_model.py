#!/usr/bin/env python3
"""
Export trained n-gram model to JSON for client-side use.

Usage:
    python export_model.py [--threshold 5] [--output docs/model.json]

The threshold controls pruning: contexts with total count < threshold
(for order >= 3) are removed. Lower threshold = bigger model, better
compression. Higher = smaller, slightly worse.

Threshold vs size vs quality (on 100 test messages):
    >=2:  BPC=3.157, ~5.0MB gzipped
    >=3:  BPC=3.167, ~3.7MB gzipped
    >=5:  BPC=3.217, ~2.6MB gzipped  (default)
    >=10: BPC=3.293, ~2.2MB gzipped
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.compress import train_model, ORDER


def main():
    parser = argparse.ArgumentParser(description="Export model to JSON")
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        help="Min total count for contexts at order >= 3 (default: 5)",
    )
    parser.add_argument(
        "--output",
        default="docs/model.json",
        help="Output path (default: docs/model.json)",
    )
    parser.add_argument(
        "--max-order",
        type=int,
        default=None,
        help="Max n-gram order to export (default: full model order)",
    )
    args = parser.parse_args()

    import json
    train_path = Path(__file__).parent.parent / "data" / "datasets" / "train.jsonl"
    print(f"Loading training data from {train_path}...")
    msgs = []
    with open(train_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                msgs.append(rec["text"])
    print(f"  {len(msgs)} messages")

    print("Training model...")
    model = train_model(msgs)
    print(f"  vocab={len(model.vocab)}, order={model.order}")

    # Export with pruning
    max_order = args.max_order if args.max_order is not None else model.order
    max_order = min(max_order, model.order)
    export = {"o": max_order, "v": model.vocab, "c": []}
    total_contexts = 0
    for n in range(max_order + 1):
        d = {}
        min_count = args.threshold if n >= 3 else 1
        for ctx, counts in model.counts[n].items():
            t = model.totals[n][ctx]
            if t >= min_count:
                d[ctx] = dict(counts)
        export["c"].append(d)
        total_contexts += len(d)

    print(f"  {total_contexts} contexts after pruning (threshold >= {args.threshold})")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = output.stat().st_size / 1024 / 1024
    print(f"  Wrote {output} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
