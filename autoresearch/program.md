# autoresearch — Russian Text Compression

Autonomous research to improve Russian text compression for Meshtastic radio mesh network devices. 233-byte payload limit per packet.

## Context

We compress short Russian messages (average ~35 chars / ~60 UTF-8 bytes) using a **character-level n-gram language model + arithmetic coding**. The model learns character transition probabilities from a corpus of 46K real Meshtastic messages, then uses arithmetic coding to encode text near the entropy limit.

Current baseline: **5-gram model → 3.276 bits/char on held-out test set** (76% compression ratio).
Theoretical min for Russian text: **~0.7-1.0 bits/char** (Shannon estimate for natural language).

**There is significant room for improvement** — the gap between 3.28 bpc and ~1.0 bpc is where research happens.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar21`).
2. **Read the in-scope files**: The relevant files are small. Read these for full context:
   - This `program.md` — context and instructions.
   - `prepare.py` — fixed evaluation harness. DO NOT MODIFY.
   - `compress.py` — the file you modify. Model, arithmetic coder, everything.
3. **Verify data exists**: Check that `data/train.txt` and `data/test.txt` exist. If not, run: `python3 -m autoresearch.prepare` from the project root.
4. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
5. **Confirm and go**.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs on CPU. Run from the project root (`meshtastic/`):

```bash
python3 -m autoresearch.prepare --eval > autoresearch/run.log 2>&1
```

This trains the model on train.txt and evaluates on 2000 test messages. Budget: **3 minutes** total.

**What you CAN do:**
- Modify `autoresearch/compress.py` — this is the ONLY file you edit. Everything is fair game:
  - Model: n-gram order, smoothing method, interpolation weights, context representation
  - Vocabulary: encoding, special symbols, unknown char handling
  - CDF computation: precision, normalization, caching strategy
  - Arithmetic coder: precision bits, renormalization strategy
  - Wire format: header, bitstream encoding, metadata
  - Entirely new approaches: PPM, CTW, BWT+MTF+AC, etc.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the fixed evaluation.
- Add external dependencies (only Python stdlib + pickle allowed).
- Break the roundtrip: compress→decompress must return the original text for ALL 2000 messages.
- Exceed the 3-minute time budget for train + full eval.

**The goal is simple: get the lowest avg_bpc** (average bits per character). Lower = better compression.

**Roundtrip is MANDATORY**: If roundtrip_pct < 100%, the experiment is a FAILURE regardless of bpc.

**Simplicity criterion**: All else being equal, simpler is better. A 0.01 bpc improvement that adds ugly complexity? Maybe worth it. A 0.001 bpc improvement from deleting code? Definitely keep. Equal bpc but simpler code? Keep.

**The first run**: Your very first run should always establish the baseline — run the script as-is.

## Output format

The evaluation script prints:

```
---
avg_bpc:            3.275767
avg_ratio:          76.40
roundtrip_pct:      100.00
fits_233_pct:       100.00
train_seconds:      3.2
eval_seconds:       36.8
total_seconds:      40.0
...
```

Extract the key metric:
```
grep "^avg_bpc:\|^roundtrip_pct:\|^total_seconds:" autoresearch/run.log
```

## Logging results

When an experiment is done, log it to `autoresearch/results.tsv` (tab-separated).

Header and 6 columns:

```
commit	avg_bpc	roundtrip	time_s	status	description
```

1. commit: short hash or "baseline"
2. avg_bpc achieved (e.g. 3.275767) — use 0.000000 for crashes
3. roundtrip % (must be 100.00 for keep)
4. total_seconds (train + eval)
5. status: `keep`, `discard`, or `crash`
6. short text description

Example:
```
commit	avg_bpc	roundtrip	time_s	status	description
baseline	3.275767	100.00	40.0	keep	baseline (5-gram, quadratic interpolation)
exp001	3.120000	100.00	55.1	keep	increase order to 7
exp002	2.950000	100.00	120.0	keep	PPM escape mechanism
exp003	0.000000	0.00	0.0	crash	CTW implementation (recursion too deep)
```

## The experiment loop

LOOP FOREVER:

1. Look at current `compress.py`
2. Modify `compress.py` with an experimental idea
3. Run the experiment: `python3 -m autoresearch.prepare --eval > autoresearch/run.log 2>&1`
4. Read results: `grep "^avg_bpc:\|^roundtrip_pct:\|^total_seconds:" autoresearch/run.log`
5. If grep output is empty → crash. Run `tail -n 50 autoresearch/run.log` for stack trace. Fix or skip.
6. Record results in results.tsv
7. If avg_bpc improved AND roundtrip=100% → keep the change
8. If worse or broken roundtrip → revert compress.py to previous version
9. Think of next idea and repeat

**Timeout**: If a run exceeds 5 minutes, kill it and treat as failure.

**NEVER STOP**: Do NOT pause to ask the user. Keep running experiments autonomously until manually interrupted. If you run out of ideas, think harder — re-read the code, try radical changes, combine near-misses.

## Research Ideas to Try

Here are promising directions, roughly ordered by expected impact:

### High Impact
- **Increase order** to 7 or 9 (more context = better prediction, but more memory + slower)
- **PPM (Prediction by Partial Matching)** — use escape mechanism instead of simple interpolation. This is THE classic technique for text compression
- **Better smoothing**: Kneser-Ney, Modified Kneser-Ney, Witten-Bell escape estimation
- **Exclusion mechanism** — when encoding at order-n, exclude symbols not seen at that order from lower-order predictions. This is a huge win for PPM

### Medium Impact
- **Context mixing** — weight multiple models (e.g. word-level + char-level)
- **Recency / adaptation** — give more weight to recent symbols (online model update during encoding)
- **Dynamic model update** — update counts while encoding (PPM does this naturally)
- **Higher CDF_SCALE** — increase from 2^16 to 2^20 for finer granularity (less quantization loss)
- **Variable-order** — use higher order when enough data, fall back otherwise

### Experimental
- **BWT + MTF + arithmetic coding** — Burrows-Wheeler transform approach
- **Dictionary pre-coding** — replace frequent words/phrases before AC
- **Context tree weighting (CTW)** — Bayesian optimal context mixing
- **Byte-level instead of char-level** — model UTF-8 bytes directly (smaller vocab = less CDF waste)

### Optimization (speed, not compression)
- **Binary search in CDF decode** instead of linear scan
- **Precompute vocab→index mapping** as dict instead of binary search
- **Bitwise operations** for encoder/decoder

## Technical Notes

- Russian Cyrillic char = 2 UTF-8 bytes. So 1 bpc = excellent (12.5% of raw UTF-8)
- Corpus has ~720 unique characters (Cyrillic + Latin + digits + punctuation + emoji)
- Messages are short (median 24 chars, mean 35 chars) — short context = hard problem
- Meshtastic packets: 233 bytes max
- Train: ~46,500 messages, Test: 2,000 messages (fixed split, seed=42)
- The CDF must sum to exactly CDF_SCALE. Every symbol must have freq >= 1 (for decodability)
- Encoder and decoder must use identical arithmetic — any divergence = roundtrip failure
- Unknown chars in test set are handled via extra-chars header in wire format
