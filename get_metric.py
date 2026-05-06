#!/usr/bin/env python3
import sys, os, json, random, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/Users/dimapanov/meshtastic")
os.chdir("/Users/dimapanov/meshtastic")

SEED = 42
DATASETS_DIR = Path("/Users/dimapanov/meshtastic/data/datasets")
CJK_LANGS = {"zh", "ja", "ko"}
CJK_WEIGHT = 3


def load_jsonl(path):
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


from src.compress import train_model, compress, decompress, compress_text, decompress_text

rng = random.Random(SEED)
train_records = load_jsonl(DATASETS_DIR / "train.jsonl")
test_records = load_jsonl(DATASETS_DIR / "test.jsonl")

train_msgs = []
for rec in train_records:
    text = rec["text"]
    weight = CJK_WEIGHT if rec["lang"] in CJK_LANGS else 1
    for _ in range(weight):
        train_msgs.append(text)

rng.shuffle(train_msgs)

t0 = time.time()
model = train_model(train_msgs)
train_sec = time.time() - t0

test_by_lang = defaultdict(list)
for rec in test_records:
    test_by_lang[rec["lang"]].append(rec)

results = {}
all_rt_ok = True

for lang in sorted(test_by_lang.keys()):
    msgs = test_by_lang[lang]
    total_bits = 0       # binary path bits
    total_tc_bytes = 0   # text-channel path bytes (UTF-8 of compress_text output)
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
            tc = compress_text(text, model)
            dt = decompress_text(tc, model)
            utf8_len = len(text.encode("utf-8"))
            comp_len = len(c)

            total_bits += comp_len * 8
            total_tc_bytes += len(tc.encode("utf-8"))
            total_chars += len(text)
            total_utf8 += utf8_len
            total_comp += comp_len

            if d == text and dt == text:
                rt_ok += 1
            if comp_len > utf8_len:
                neg += 1
        except Exception as e:
            total_bits += len(text.encode("utf-8")) * 16
            total_tc_bytes += len(text.encode("utf-8")) * 2
            total_chars += len(text)
            total_utf8 += len(text.encode("utf-8"))
            total_comp += len(text.encode("utf-8")) * 2

    bpc = total_bits / total_chars if total_chars > 0 else 99
    tc_bpc = total_tc_bytes * 8 / total_chars if total_chars > 0 else 99
    ratio = (1 - total_comp / total_utf8) * 100 if total_utf8 > 0 else 0
    tc_ratio = (1 - total_tc_bytes / total_utf8) * 100 if total_utf8 > 0 else 0
    rt_pct = rt_ok / n * 100 if n > 0 else 0

    results[lang] = {"bpc": bpc, "tc_bpc": tc_bpc, "ratio": ratio, "tc_ratio": tc_ratio, "rt": rt_pct, "n": n}
    if rt_pct < 100:
        all_rt_ok = False

total_n = sum(r["n"] for r in results.values())
weighted_bpc = sum(r["bpc"] * r["n"] for r in results.values()) / total_n
weighted_tc_bpc = sum(r["tc_bpc"] * r["n"] for r in results.values()) / total_n

print(f"weighted_bpc(bin): {weighted_bpc:.6f}")
print(f"weighted_bpc(txt): {weighted_tc_bpc:.6f}")
print(f"roundtrip_pct:     {'100.00' if all_rt_ok else 'FAIL'}")
for lang, r in results.items():
    print(f"  {lang}: bin_bpc={r['bpc']:.4f} ({r['ratio']:5.2f}%)  txt_bpc={r['tc_bpc']:.4f} ({r['tc_ratio']:5.2f}%)  rt={r['rt']:.2f}% n={r['n']}")
print(f"train_sec: {train_sec:.2f}")
