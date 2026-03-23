#!/usr/bin/env python3
"""
autoresearch/compress.py — THE FILE THE AGENT MODIFIES.

This file contains everything needed for compression:
  - Character-level n-gram language model
  - Integer arithmetic encoder/decoder (32-bit precision)
  - compress(text, model) -> bytes
  - decompress(data, model) -> str
  - train_model(messages) -> model

The agent can modify ANYTHING in this file: model architecture,
smoothing, CDF computation, arithmetic coding precision, header format,
vocabulary handling, context representation, etc.

CONSTRAINTS:
  - Must export: train_model(messages) -> model, compress(text, model) -> bytes, decompress(data, model) -> str
  - compress→decompress must be a perfect roundtrip for all test messages
  - train_model + full test eval must complete within 3 minutes on CPU
  - No external dependencies beyond Python stdlib + pickle
  - The model is trained on train set, then compress/decompress are called on test set
"""

import struct
import pickle
import math
from collections import Counter, defaultdict
from pathlib import Path


# ─── Special Symbols ────────────────────────────────────────
BOS = "\x02"  # Beginning of sequence (context padding)
EOF = "\x03"  # End of sequence (signals end of message)

# ─── Arithmetic Coding Constants ────────────────────────────
CDF_SCALE = 1 << 20  # 1048576 — higher precision for better compression
PRECISION = 32
FULL = 1 << PRECISION  # 4294967296
HALF = 1 << (PRECISION - 1)
QUARTER = 1 << (PRECISION - 2)
MASK = FULL - 1

# ─── Model Configuration ───────────────────────────────────
ORDER = 11  # n-gram order (context length)
CDF_CACHE_MAX = 200000  # max entries in CDF cache


# ═══════════════════════════════════════════════════════════
# LANGUAGE MODEL
# ═══════════════════════════════════════════════════════════


class NGramModel:
    """
    Character-level n-gram model with interpolation smoothing.
    Produces CDF tables for arithmetic coding.
    """

    def __init__(self, order=ORDER):
        self.order = order
        self.counts = [defaultdict(dict) for _ in range(order + 1)]
        self.totals = [defaultdict(int) for _ in range(order + 1)]
        self.vocab = []  # sorted list of all symbols (including EOF)
        self._vocab_set = set()
        self._cdf_cache = {}
        self._vocab_idx = {}  # char -> index (precomputed dict, faster than binary search)

    def train(self, texts):
        """Train on a list of text strings."""
        charset = set()
        raw_counts = [defaultdict(Counter) for _ in range(self.order + 1)]

        for text in texts:
            padded = BOS * self.order + text + EOF
            charset.update(text)

            for i in range(self.order, len(padded)):
                ch = padded[i]
                for n in range(self.order + 1):
                    ctx = padded[i - n : i]
                    raw_counts[n][ctx][ch] += 1

        # Convert to plain dicts and compute totals
        for n in range(self.order + 1):
            for ctx, counter in raw_counts[n].items():
                self.counts[n][ctx] = dict(counter)
                self.totals[n][ctx] = sum(counter.values())

        charset.add(EOF)
        self._vocab_set = charset
        self.vocab = sorted(charset)
        self._vocab_idx = {ch: i for i, ch in enumerate(self.vocab)}

    def get_cdf(self, context):
        """
        CDF for arithmetic coder (cached).
        Returns: [(char, cum_low, cum_high), ...]
        Sum of all intervals = CDF_SCALE exactly.
        """
        if context in self._cdf_cache:
            return self._cdf_cache[context]

        cdf = self._compute_cdf(context)

        if len(self._cdf_cache) < CDF_CACHE_MAX:
            self._cdf_cache[context] = cdf

        return cdf

    def _compute_cdf(self, context):
        """Compute CDF from scratch using interpolation smoothing."""
        vocab = self.vocab
        n_vocab = len(vocab)

        # Step 1: find active orders and their weights
        active = []
        total_w = 0.0
        for n in range(self.order, -1, -1):
            ctx = context[-n:] if n > 0 else ""
            t = self.totals[n].get(ctx, 0)
            if t > 0:
                w = (n + 1) ** 3 * math.log1p(t)  # cubic * log(1+count)
                active.append((n, ctx, t, w))
                total_w += w

        # Step 2: compute raw frequency for each vocab symbol
        # Start with uniform epsilon (1 per symbol)
        epsilon_total = n_vocab
        freqs = [1] * n_vocab  # epsilon = 1 count each

        if total_w > 0:
            SCALE = CDF_SCALE - epsilon_total  # remaining budget after epsilon

            for n, ctx, total, w in active:
                counts_n = self.counts[n].get(ctx, {})
                factor = (w / total_w) * SCALE / total
                for ch, count in counts_n.items():
                    idx = self._vocab_index(ch)
                    if idx >= 0:
                        freqs[idx] += int(count * factor)

        # Normalize to CDF_SCALE exactly
        total = sum(freqs)
        if total != CDF_SCALE:
            diff = CDF_SCALE - total
            if diff > 0:
                max_idx = max(range(n_vocab), key=lambda i: freqs[i])
                freqs[max_idx] += diff
            else:
                indices = sorted(range(n_vocab), key=lambda i: -freqs[i])
                remaining = -diff
                for idx in indices:
                    if remaining <= 0:
                        break
                    can_remove = freqs[idx] - 1
                    remove = min(can_remove, remaining)
                    freqs[idx] -= remove
                    remaining -= remove

        # Build CDF
        cdf = []
        cum = 0
        for i, ch in enumerate(vocab):
            f = freqs[i]
            cdf.append((ch, cum, cum + f))
            cum += f

        return cdf

    def _vocab_index(self, ch):
        """O(1) lookup for char index in vocab."""
        return self._vocab_idx.get(ch, -1)

    def ensure_char(self, ch):
        """Add a character to vocab if not already present (for unknown chars in test)."""
        if ch not in self._vocab_set:
            self._vocab_set.add(ch)
            self.vocab = sorted(self._vocab_set)
            self._vocab_idx = {c: i for i, c in enumerate(self.vocab)}
            self._cdf_cache.clear()  # invalidate cache since vocab changed

    def clear_cache(self):
        self._cdf_cache.clear()


# ═══════════════════════════════════════════════════════════
# ARITHMETIC ENCODER
# ═══════════════════════════════════════════════════════════


class ArithmeticEncoder:
    def __init__(self):
        self.low = 0
        self.high = MASK
        self.pending = 0
        self.bits = []

    def _emit_bit(self, bit):
        self.bits.append(bit)
        opp = 1 - bit
        for _ in range(self.pending):
            self.bits.append(opp)
        self.pending = 0

    def encode_symbol(self, cum_low, cum_high, total):
        rng = self.high - self.low + 1
        self.high = self.low + (rng * cum_high) // total - 1
        self.low = self.low + (rng * cum_low) // total

        while True:
            if self.high < HALF:
                self._emit_bit(0)
            elif self.low >= HALF:
                self._emit_bit(1)
                self.low -= HALF
                self.high -= HALF
            elif self.low >= QUARTER and self.high < 3 * QUARTER:
                self.pending += 1
                self.low -= QUARTER
                self.high -= QUARTER
            else:
                break
            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) | 1) & MASK

    def finish(self):
        self.pending += 1
        if self.low < QUARTER:
            self._emit_bit(0)
        else:
            self._emit_bit(1)

        while len(self.bits) % 8 != 0:
            self.bits.append(0)

        result = bytearray()
        for i in range(0, len(self.bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | self.bits[i + j]
            result.append(byte)
        return bytes(result)


# ═══════════════════════════════════════════════════════════
# ARITHMETIC DECODER
# ═══════════════════════════════════════════════════════════


class ArithmeticDecoder:
    def __init__(self, data):
        self.data = data
        self.low = 0
        self.high = MASK
        self.value = 0
        self.bit_pos = 0
        self.total_bits = len(data) * 8

        for _ in range(PRECISION):
            self.value = (self.value << 1) | self._read_bit()

    def _read_bit(self):
        if self.bit_pos >= self.total_bits:
            return 0
        byte_idx = self.bit_pos >> 3
        bit_idx = 7 - (self.bit_pos & 7)
        self.bit_pos += 1
        return (self.data[byte_idx] >> bit_idx) & 1

    def decode_symbol(self, cdf):
        total = CDF_SCALE
        rng = self.high - self.low + 1
        scaled = ((self.value - self.low + 1) * total - 1) // rng

        # Binary search for symbol where cum_low <= scaled < cum_high
        lo, hi = 0, len(cdf) - 1
        while lo < hi:
            mid = (lo + hi) >> 1
            if cdf[mid][2] <= scaled:  # cum_high <= scaled → go right
                lo = mid + 1
            else:
                hi = mid
        sym, cum_low, cum_high = cdf[lo]

        self.high = self.low + (rng * cum_high) // total - 1
        self.low = self.low + (rng * cum_low) // total

        while True:
            if self.high < HALF:
                pass
            elif self.low >= HALF:
                self.low -= HALF
                self.high -= HALF
                self.value -= HALF
            elif self.low >= QUARTER and self.high < 3 * QUARTER:
                self.low -= QUARTER
                self.high -= QUARTER
                self.value -= QUARTER
            else:
                break
            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) | 1) & MASK
            self.value = ((self.value << 1) | self._read_bit()) & MASK

        return sym


# ═══════════════════════════════════════════════════════════
# PUBLIC API (must be exported)
# ═══════════════════════════════════════════════════════════


def train_model(messages):
    """
    Train the compression model on a list of text messages.
    Returns: model object (passed to compress/decompress).
    """
    model = NGramModel(order=ORDER)
    model.train(messages)
    return model


def compress(text, model):
    """
    Compress text using the trained model.
    Returns: bytes

    Format: [2 bytes: text length as uint16 BE]
            [1 byte: num extra chars]
            [extra chars as UTF-8, each prefixed by 1-byte length]
            [AC bitstream]
    """
    if not text:
        return b"\x00\x00"

    # Find chars not in training vocab
    extra_chars = sorted(set(ch for ch in text if ch not in model._vocab_set))

    # Add extra chars to model vocab
    for ch in extra_chars:
        model.ensure_char(ch)

    encoder = ArithmeticEncoder()
    context = BOS * model.order

    for ch in text:
        cdf = model.get_cdf(context)
        found = False
        for sym, cum_low, cum_high in cdf:
            if sym == ch:
                encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
                found = True
                break

        if not found:
            raise ValueError(
                f"Character '{ch}' (U+{ord(ch):04X}) not in model vocabulary"
            )

        context = (context + ch)[-model.order :]

    # Encode EOF
    cdf = model.get_cdf(context)
    for sym, cum_low, cum_high in cdf:
        if sym == EOF:
            encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
            break

    ac_bytes = encoder.finish()

    # Build header: [uint16 text_len] [uint8 n_extra] [extra chars as utf-8]
    header = struct.pack(">HB", len(text), len(extra_chars))
    for ch in extra_chars:
        ch_bytes = ch.encode("utf-8")
        header += struct.pack("B", len(ch_bytes)) + ch_bytes

    return header + ac_bytes


def decompress(data, model):
    """
    Decompress bytes back to text using the trained model.
    data format: [2-byte uint16 BE length] [1-byte n_extra] [extra chars] [AC bitstream]
    """
    if len(data) < 3:
        raise ValueError("Data too short")

    text_len = struct.unpack(">H", data[:2])[0]
    if text_len == 0:
        return ""

    n_extra = data[2]
    offset = 3

    # Read extra chars and add to model vocab
    for _ in range(n_extra):
        ch_len = data[offset]
        offset += 1
        ch = data[offset : offset + ch_len].decode("utf-8")
        offset += ch_len
        model.ensure_char(ch)

    ac_data = data[offset:]
    if not ac_data:
        raise ValueError("No AC data after header")

    decoder = ArithmeticDecoder(ac_data)
    context = BOS * model.order
    result = []

    for _ in range(text_len + 1):  # +1 for EOF
        cdf = model.get_cdf(context)
        ch = decoder.decode_symbol(cdf)

        if ch == EOF:
            break

        result.append(ch)
        context = (context + ch)[-model.order :]

    return "".join(result)
