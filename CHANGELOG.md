# Changelog

## 2026-03-23 — Real MQTT data + clean datasets + honest eval

**Added 10K real Meshtastic messages from MQTT, fixed test/train leakage, switched to JSONL datasets.**

### Test methodology fix

Previous eval had a critical blind spot: **70-75% of synthetic test messages were also in the training set** (template generator produced the same patterns in both). This inflated BPC numbers for DE, ES, FR, PT, ZH, AR, JA, KO.

Fixed by:
1. Created `build_datasets.py` — builds clean JSONL datasets from all sources with guaranteed zero train/test overlap
2. Test data now prefers **real MQTT messages** (where available) over synthetic templates
3. Added `eval_all.py` — unified evaluation on clean JSONL datasets with per-language breakdown

### Real MQTT data

Downloaded ~200K raw messages from [meshtastic.liamcottle.net](https://meshtastic.liamcottle.net) public API, yielding ~12K unique messages after deduplication:
- EN: 6,056 real messages (from 53K total with original corpus)
- RU: 4,239 real messages (from 52K total)
- PL: 974 (new language)
- NO: 201 (new language)
- DE: 120, ES: 203, FR: 44, PT: 68, SV: 56

### Honest numbers (no leakage)

| Language | Ratio | BPC | Test source | Roundtrip |
|----------|-------|-----|-------------|-----------|
| RU | 78% | 3.02 | real MQTT | 100% |
| EN | 73% | 2.19 | real MQTT | 99.8% |
| NO | 64% | 3.00 | real MQTT | 98% |
| PL | 50% | 4.19 | real MQTT | 94% |
| DE | 43% | 4.73 | real MQTT | 90% |
| ES | 44% | 4.61 | real MQTT | 94% |
| PT | 43% | 4.86 | real MQTT | 97% |
| FR | 41% | 4.88 | real MQTT | 91% |
| SV | 40% | 5.01 | real MQTT | 100% |
| AR | 82% | 2.29 | synthetic* | 100% |
| KO | 77% | 3.07 | synthetic* | 100% |
| JA | 76% | 3.49 | synthetic* | 100% |
| ZH | 73% | 3.76 | synthetic* | 100% |

\* Synthetic test results are inflated — model memorises template patterns.

### Repo cleanup

- Removed old JPG images (replaced by PNG)
- Removed one-off experiment scripts
- Removed train_all/test_all concatenation files
- Added .gitignore for MQTT raw data, local experiment logs
- 3 new languages: PL, NO, SV

---

## 2026-03-23 — Format optimization: passthrough + compact header

**BPC: 3.210 → 2.977 (−7.3%). Negative compression eliminated (19 → 0 cases).**

15 autoresearch experiments, 4 kept, 11 discarded.

### What changed

#### 1. Zero-overhead passthrough for short messages

**Problem:** Messages like "ok" (2 UTF-8 bytes) were being output as 6 bytes — the 3-byte header + arithmetic coder overhead made short messages *bigger* than the original.

**Fix:** After arithmetic coding, compare the compressed output with the raw UTF-8 bytes. If compressed ≥ raw, return the raw UTF-8 directly with no header. The decompressor auto-detects the format by the first byte: compressed data always starts with `0x00` (the high byte of the text length field), while raw UTF-8 text never starts with a null byte.

**Impact:** 19 messages that previously had negative compression now have zero overhead. Output is guaranteed ≤ input for all messages.

#### 2. Compact 2-byte header (was 3 bytes)

**Problem:** Every compressed message paid a 3-byte header tax: `[uint16 text_len] [flags]`. For a typical 10-byte compressed message, 30% is just header.

**Fix:** For messages with text_len < 128 (99%+ of Meshtastic messages), pack everything into 2 bytes: `[0x00] [has_escapes_bit7 | text_len_7bits]`. Messages with text_len ≥ 128 keep the old 3-byte header, disambiguated by the high bit of byte[1].

**Impact:** **−7.1% BPC** — the single biggest improvement ever. Saves 1 byte per compressed message, which is huge for short radio packets.

#### 3. Confidence denominator n+3 → n+1.5 for Latin/Cyrillic

**Problem:** The confidence penalty `min(count / (n+3), 1)` was too conservative for well-represented scripts — it distrusted high-order contexts that had plenty of training data.

**Fix:** Reduce the denominator from `n+3` to `n+1.5` for Latin/Cyrillic scripts (CJK/Hangul/Japanese keep `n+8`). This trusts long-context predictions more when training data is abundant.

**Impact:** −0.003 BPC. Small but consistent improvement across all Latin/Cyrillic languages.

### Discarded experiments

| Experiment | Result | Why discarded |
|-----------|--------|---------------|
| Remove EOF encoding | BPC −0.018 | Roundtrip failures (99.95%) — EOF needed for AC finalization |
| ESC_PROB 500→200 | BPC +0.002 | Slight regression |
| Order weight exponent 3→4 | BPC +0.013 | Over-emphasizes long contexts |
| SCRIPT_BOOST 5→3 | BPC ±0 | No measurable effect |
| CDF_SCALE 2^20→2^22 | BPC −0.0001 | Negligible, not worth complexity |
| Epsilon cap CDF_SCALE/4 | BPC ±0 | Cap was never being hit |
| ORDER 11→13 | BPC +0.004 | Overfitting (not enough data for long contexts) |
| ORDER 11→9 | BPC +0.006 | Loses useful long-context predictions |
| PPM-style exclusion | BPC +1.55 | Catastrophic — zeroed out too many probabilities |
| Soft PPM exclusion (50%) | BPC +0.095 | Still too aggressive for this interpolation model |
| Passthrough threshold ≥ vs > | BPC ±0 | No messages had exactly equal sizes |

### Files changed

- `src/compress.py` — passthrough logic, compact header, confidence tuning
- `tools/eval_all.py` — evaluation harness (was eval_short.py)
- `tools/gen_charts.py` — chart generator (matplotlib) for all README charts
- `docs/img/*.png` — regenerated all charts with current data
- `README.md` — updated results, wire format docs, added "How compression works" section
- `CHANGELOG.md` — this file

### Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| avg_bpc (RU+EN) | 3.210 | 2.977 | **−7.3%** |
| avg_ratio | 76.87% | 78.55% | +1.68pp |
| neg_count | 19 | 0 | **−100%** |
| roundtrip | 100% | 100% | ✓ |
| fits_233 | 100% | 100% | ✓ |

Per-language BPC (multilingual universal model):

| Language | Before | After | Change |
|----------|--------|-------|--------|
| ZH | 4.759 | 3.950 | −17% |
| JA | 3.906 | 3.225 | −17% |
| KO | 3.454 | 2.859 | −17% |
| RU | 3.271 | 3.041 | −7% |
| EN | 2.208 | 1.964 | −11% |

---

## 2026-03-22 — Multilingual CJK optimization

25 autoresearch experiments. 9 kept, 15 discarded, 1 no-op.

- ESC_PROB 20000→500: more CDF budget for model predictions
- SCRIPT_BOOST 30→5: less epsilon bias toward same-script chars
- CJK 3× training weight: compensate for sparse template-generated CJK data
- CJK-specific confidence denominator (n+8): prevent overfitting rare high-order CJK contexts
- CJK weight threshold 0.3→0.05: boost mixed CJK messages too
- Two-tier CJK codepoint encoding: top-500 common chars get cheaper ESC codes

ZH BPC: 4.841 → 4.759 (−1.7%). All other languages improved or stable.

---

## 2026-03-21 — Model tuning (initial autoresearch)

17 experiments. Key findings:

- Order=11 with cubic `(n+1)^3` interpolation weights is optimal
- Confidence penalty `min(t/(n+3), 1)` prevents overfitting sparse contexts
- Quartic/quintic weights, PPM exclusion, dynamic model update all failed

BPC: 3.272 → 3.212 (−1.8%).

---

## 2026-03-20 — Multilingual universal model

- 10-language universal model (RU, EN, ES, DE, FR, PT, ZH, AR, JA, KO)
- 452,532 training messages, 1,494 unique characters
- Web UI with client-side JavaScript compression
- Only 1-3% worse than per-language models → ship one universal model
