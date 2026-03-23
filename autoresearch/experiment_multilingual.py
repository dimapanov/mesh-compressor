#!/usr/bin/env python3
"""
Multilingual compression experiment:
  - Per-language models (one per language, ~5K messages each)
  - Universal model (5K messages per language, all mixed)
  - Cross-language evaluation matrix

Usage: python3 autoresearch/experiment_multilingual.py
"""

import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from autoresearch.compress import NGramModel, compress, decompress

# ── Config ─────────────────────────────────────────────────
ORDER = 9
THRESHOLD = 50  # for model size estimation
SUBSAMPLE = 45000  # messages per language for training
TEST_LIMIT = 500  # test messages per language
LANGS = ["ru", "en", "es", "de", "fr", "pt", "zh", "ar", "ja", "ko"]
DATA_DIR = Path(__file__).parent.parent / "data"
MULTI_DIR = DATA_DIR / "multilingual"
SEED = 42


# ── Data Loading ───────────────────────────────────────────
def is_cyrillic(line):
    return any("\u0400" <= c <= "\u04ff" for c in line)


def load_data():
    """Load train/test data for all languages."""
    rng = random.Random(SEED)
    train = {}
    test = {}

    # RU and EN from main train.txt
    all_lines = (DATA_DIR / "train.txt").read_text("utf-8").splitlines()
    ru_lines = [l for l in all_lines if is_cyrillic(l)]
    en_lines = [l for l in all_lines if not is_cyrillic(l)]

    rng.shuffle(ru_lines)
    rng.shuffle(en_lines)

    train["ru"] = ru_lines[:SUBSAMPLE]
    train["en"] = en_lines[:SUBSAMPLE]

    # RU test from test.txt
    ru_test = (DATA_DIR / "test.txt").read_text("utf-8").splitlines()
    test["ru"] = ru_test[:TEST_LIMIT]

    # EN test — take from held-out English
    test["en"] = en_lines[SUBSAMPLE : SUBSAMPLE + TEST_LIMIT]

    # Other languages
    for lang in LANGS:
        if lang in ("ru", "en"):
            continue
        train_file = MULTI_DIR / f"train_{lang}.txt"
        test_file = MULTI_DIR / f"test_{lang}.txt"
        train[lang] = train_file.read_text("utf-8").splitlines()[:SUBSAMPLE]
        test[lang] = test_file.read_text("utf-8").splitlines()[:TEST_LIMIT]

    return train, test


# ── Model Size ─────────────────────────────────────────────
def calc_model_size_mb(model, threshold=THRESHOLD):
    total_bytes = 0
    for n in range(model.order + 1):
        min_count = threshold if n >= 3 else 1
        for ctx, counts in model.counts[n].items():
            t = model.totals[n][ctx]
            if t >= min_count:
                total_bytes += 4 + 2 + len(counts) * 6
    return total_bytes / 1024 / 1024


# ── Evaluation ─────────────────────────────────────────────
def evaluate(model, messages):
    """Evaluate compression on a list of messages. Returns (bpc, ratio, rt_pct)."""
    total_bits = 0
    total_chars = 0
    total_utf8 = 0
    total_comp = 0
    rt_ok = 0

    for msg in messages:
        if not msg.strip():
            continue
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

    n = len([m for m in messages if m.strip()])
    bpc = total_bits / total_chars if total_chars > 0 else 99
    ratio = 1 - total_comp / total_utf8 if total_utf8 > 0 else 0
    rt_pct = rt_ok / n * 100 if n > 0 else 0
    return round(bpc, 3), round(ratio * 100, 1), round(rt_pct, 1)


# ── Main Experiment ────────────────────────────────────────
def main():
    print("=" * 80)
    print("MULTILINGUAL COMPRESSION EXPERIMENT")
    print(f"Order={ORDER}, Subsample={SUBSAMPLE}/lang, Test={TEST_LIMIT}/lang")
    print("=" * 80)

    train, test = load_data()

    for lang in LANGS:
        print(f"  {lang}: {len(train[lang])} train, {len(test[lang])} test")
    print()

    # ── Train per-language models ──────────────────────────
    print("Training per-language models...")
    per_lang_models = {}
    per_lang_sizes = {}
    for lang in LANGS:
        t0 = time.time()
        model = NGramModel(order=ORDER)
        model.train(train[lang])
        per_lang_models[lang] = model
        per_lang_sizes[lang] = calc_model_size_mb(model)
        dt = time.time() - t0
        print(
            f"  model_{lang}: {dt:.1f}s, {per_lang_sizes[lang]:.2f} MB, vocab={len(model.vocab)}"
        )
    print()

    # ── Train universal model ──────────────────────────────
    print("Training universal model (all languages mixed)...")
    t0 = time.time()
    universal_train = []
    for lang in LANGS:
        universal_train.extend(train[lang])
    random.Random(SEED).shuffle(universal_train)

    universal_model = NGramModel(order=ORDER)
    universal_model.train(universal_train)
    universal_size = calc_model_size_mb(universal_model)
    dt = time.time() - t0
    print(
        f"  universal: {dt:.1f}s, {universal_size:.2f} MB, vocab={len(universal_model.vocab)}"
    )
    print()

    # ── Evaluate: per-language models ──────────────────────
    print("=" * 80)
    print("PER-LANGUAGE MODELS — BPC (bits per character)")
    print("=" * 80)

    header = f"{'model':<10}" + "".join(f"{l:>8}" for l in LANGS) + f"{'size_MB':>10}"
    print(header)
    print("-" * len(header))

    per_lang_bpc = {}  # (train_lang, test_lang) -> bpc
    for train_lang in LANGS:
        model = per_lang_models[train_lang]
        row = f"{'m_' + train_lang:<10}"
        for test_lang in LANGS:
            bpc, ratio, rt = evaluate(model, test[test_lang])
            per_lang_bpc[(train_lang, test_lang)] = bpc
            row += f"{bpc:>8.3f}"
        row += f"{per_lang_sizes[train_lang]:>10.2f}"
        print(row)

    print()

    # ── Evaluate: universal model ──────────────────────────
    print("=" * 80)
    print("UNIVERSAL MODEL — BPC (bits per character)")
    print("=" * 80)

    header = f"{'model':<10}" + "".join(f"{l:>8}" for l in LANGS) + f"{'size_MB':>10}"
    print(header)
    print("-" * len(header))

    universal_bpc = {}
    row = f"{'univ':<10}"
    for test_lang in LANGS:
        bpc, ratio, rt = evaluate(universal_model, test[test_lang])
        universal_bpc[test_lang] = bpc
        row += f"{bpc:>8.3f}"
    row += f"{universal_size:>10.2f}"
    print(row)

    print()

    # ── Summary ────────────────────────────────────────────
    print("=" * 80)
    print("SUMMARY: Universal vs Per-Language (own-language model)")
    print("=" * 80)

    header = f"{'lang':<8}{'per-lang':>10}{'universal':>10}{'winner':>10}{'diff':>10}{'per_MB':>10}{'uni_MB':>10}"
    print(header)
    print("-" * len(header))

    results = []
    for lang in LANGS:
        pl_bpc = per_lang_bpc[(lang, lang)]
        un_bpc = universal_bpc[lang]
        diff = un_bpc - pl_bpc
        winner = "per-lang" if pl_bpc < un_bpc else "universal"
        print(
            f"{lang:<8}{pl_bpc:>10.3f}{un_bpc:>10.3f}{winner:>10}{diff:>+10.3f}"
            f"{per_lang_sizes[lang]:>10.2f}{universal_size:>10.2f}"
        )
        results.append(
            {
                "lang": lang,
                "per_lang_bpc": pl_bpc,
                "universal_bpc": un_bpc,
                "winner": winner,
                "diff": diff,
                "per_lang_mb": per_lang_sizes[lang],
                "universal_mb": universal_size,
            }
        )

    print()
    total_per = sum(per_lang_sizes[l] for l in LANGS)
    print(
        f"Total per-language models: {total_per:.1f} MB (but each device only needs 1)"
    )
    print(f"Universal model: {universal_size:.2f} MB")
    print()

    # ── Compression ratios ─────────────────────────────────
    print("=" * 80)
    print("COMPRESSION RATIOS (% saved vs UTF-8) — own-language model vs universal")
    print("=" * 80)

    header = f"{'lang':<8}{'per-lang':>10}{'universal':>10}"
    print(header)
    print("-" * len(header))

    for lang in LANGS:
        _, pl_ratio, _ = evaluate(per_lang_models[lang], test[lang])
        _, un_ratio, _ = evaluate(universal_model, test[lang])
        print(f"{lang:<8}{pl_ratio:>+10.1f}%{un_ratio:>+10.1f}%")

    print()

    # ── Save TSV ───────────────────────────────────────────
    tsv_path = Path(__file__).parent / "multilingual_results.tsv"
    with open(tsv_path, "w") as f:
        f.write(
            "lang\tper_lang_bpc\tuniversal_bpc\twinner\tdiff\tper_lang_mb\tuniversal_mb\n"
        )
        for r in results:
            f.write(
                f"{r['lang']}\t{r['per_lang_bpc']}\t{r['universal_bpc']}\t"
                f"{r['winner']}\t{r['diff']:.3f}\t{r['per_lang_mb']:.2f}\t{r['universal_mb']:.2f}\n"
            )
    print(f"Results saved to {tsv_path}")


if __name__ == "__main__":
    main()
