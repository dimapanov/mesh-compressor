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
ESC = "\x04"  # Escape: next bytes encode a raw UTF-8 character

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
SCRIPT_BOOST = 5  # epsilon multiplier for same-script characters
ESC_PROB = 500  # base probability units for ESC symbol (out of CDF_SCALE=1M)


# ─── Unicode Block Ranges for Compact Codepoint Encoding ───
# Each block: (block_id, start, end, name)
# Ordered by frequency of use in multilingual text
_UNICODE_BLOCKS = [
    (0, 0x4E00, 0x9FFF),  # CJK Unified Ideographs (20992 chars)
    (1, 0xAC00, 0xD7AF),  # Hangul Syllables (11184 chars)
    (2, 0x0900, 0x097F),  # Devanagari (128 chars)
    (3, 0x0E00, 0x0E7F),  # Thai (128 chars)
    (4, 0x0980, 0x09FF),  # Bengali (128 chars)
    (5, 0x0600, 0x06FF),  # Arabic Extended (256 chars)
    (6, 0x0400, 0x04FF),  # Cyrillic (256 chars)
    (7, 0x0100, 0x024F),  # Latin Extended (336 chars)
    (8, 0x3040, 0x309F),  # Hiragana (96 chars)
    (9, 0x30A0, 0x30FF),  # Katakana (96 chars)
    (10, 0x0B80, 0x0BFF),  # Tamil (128 chars)
    (11, 0x10A0, 0x10FF),  # Georgian (96 chars)
    (12, 0x0590, 0x05FF),  # Hebrew (112 chars)
    (13, 0x0530, 0x058F),  # Armenian (96 chars)
    (14, 0x3400, 0x4DBF),  # CJK Extension A (6592 chars)
]
_NUM_BLOCKS = len(_UNICODE_BLOCKS)
_FALLBACK_BLOCK_ID = _NUM_BLOCKS  # for chars not in any block


# ─── Top CJK Characters by Frequency ──────────────────────
# Top ~500 most frequent CJK characters (from general Chinese text corpora).
# Used as sub-block for cheaper ESC encoding of common CJK chars.
# These characters cover ~80% of typical Chinese text.
_CJK_COMMON = (
    "的一是不了人在有我他这中大来上个国和也子时道"
    "到说里自后以会家小下天生能对去出都开就过学好"
    "年多没要起然作那还可为发事看用力心想所如面成"
    "而日么之她着知行已经当其得地无把现前全进从于"
    "种同话被手只最长但因老让很才与两点什头方又样"
    "将间呢机系高正电长问力意理它山公几已明体间但"
    "外分水果定实向情位次应特路真程变合活走几给少"
    "做回本部那每月打工此新本太三给海等法加门间带"
    "气口主第儿美又各关名常感直至场见更重今求满百"
    "放书听民觉吃认已字信使通女号先条别万元车及口"
    "目关四言该区需接找怎任光并世文管北再风清今西"
    "城受望解表觉决期候度白马空叫安完住阳越持请城"
    "算吗花落平广双色近象件记料东入设南品相离消钱"
    "确运夜早半华段院客村须选式园远准习共议论林集"
    "周青王计省市台父争引坐容必办团令格深便政团容"
    "呀笑身板连单杀块红故哪节究极环越孩细拿强石故"
    "响建拉照化音形刚首医局服办随备易差尔争居推兵"
    "速若影断食即算业联调队古切病静份木服球基脸热"
    "止福欢兴终师际备般斯际欢负观题武角坚费另丝黄"
    "类造待千严干考整杂买试护穿复底致微席黑官龙"
)
_CJK_COMMON_SET = set(_CJK_COMMON)
_CJK_COMMON_MAP = {ch: i for i, ch in enumerate(_CJK_COMMON)}
_CJK_COMMON_SIZE = len(_CJK_COMMON_MAP)
# Block IDs for two-tier CJK: common (0) vs full-block (original ID 0)
_CJK_COMMON_BLOCK_ID = _NUM_BLOCKS + 1  # new block ID for common CJK
_TOTAL_BLOCK_IDS = _NUM_BLOCKS + 2  # blocks + fallback + CJK-common


def _encode_codepoint(encoder, cp):
    """Encode a Unicode codepoint using block-aware variable-length encoding.

    Two-tier CJK: common CJK chars (top ~500) get a cheaper sub-block encoding.
    block_id is uniform over _TOTAL_BLOCK_IDS choices.
    """
    # Check if it's a common CJK character first (cheapest path)
    ch = chr(cp)
    if ch in _CJK_COMMON_SET:
        encoder.encode_symbol(
            _CJK_COMMON_BLOCK_ID, _CJK_COMMON_BLOCK_ID + 1, _TOTAL_BLOCK_IDS
        )
        idx = _CJK_COMMON_MAP[ch]
        encoder.encode_symbol(idx, idx + 1, _CJK_COMMON_SIZE)
        return

    for block_id, start, end in _UNICODE_BLOCKS:
        if start <= cp <= end:
            # Encode block ID
            encoder.encode_symbol(block_id, block_id + 1, _TOTAL_BLOCK_IDS)
            # Encode offset within block
            block_size = end - start + 1
            offset = cp - start
            encoder.encode_symbol(offset, offset + 1, block_size)
            return

    # Fallback: encode full codepoint
    encoder.encode_symbol(_FALLBACK_BLOCK_ID, _FALLBACK_BLOCK_ID + 1, _TOTAL_BLOCK_IDS)
    encoder.encode_symbol(cp & 0x7F, (cp & 0x7F) + 1, 128)
    encoder.encode_symbol((cp >> 7) & 0x7F, ((cp >> 7) & 0x7F) + 1, 128)
    encoder.encode_symbol((cp >> 14) & 0x7F, ((cp >> 14) & 0x7F) + 1, 128)


def _decode_codepoint(decoder):
    """Decode a Unicode codepoint using block-aware encoding with two-tier CJK."""
    block_cdf = [(i, i, i + 1) for i in range(_TOTAL_BLOCK_IDS)]
    block_id = decoder.decode_symbol(block_cdf, total=_TOTAL_BLOCK_IDS)

    if block_id == _CJK_COMMON_BLOCK_ID:
        # Common CJK sub-block
        idx_cdf = [(i, i, i + 1) for i in range(_CJK_COMMON_SIZE)]
        idx = decoder.decode_symbol(idx_cdf, total=_CJK_COMMON_SIZE)
        return ord(_CJK_COMMON[idx])
    elif block_id < _NUM_BLOCKS:
        _, start, end = _UNICODE_BLOCKS[block_id]
        block_size = end - start + 1
        offset_cdf = [(i, i, i + 1) for i in range(block_size)]
        offset = decoder.decode_symbol(offset_cdf, total=block_size)
        return start + offset
    else:
        # Fallback: full 21-bit codepoint
        cp7_cdf = [(i, i, i + 1) for i in range(128)]
        b0 = decoder.decode_symbol(cp7_cdf, total=128)
        b1 = decoder.decode_symbol(cp7_cdf, total=128)
        b2 = decoder.decode_symbol(cp7_cdf, total=128)
        return b0 | (b1 << 7) | (b2 << 14)


def _char_script(ch):
    """Classify a character into its Unicode script by codepoint ranges."""
    cp = ord(ch)
    # Common (digits, punctuation, space, symbols, control, emoji)
    if cp < 0x0041:
        return "Common"
    # Basic Latin
    if cp <= 0x024F:
        return "Latin"
    # Latin Extended Additional & beyond
    if 0x1E00 <= cp <= 0x1EFF:
        return "Latin"
    # Cyrillic
    if 0x0400 <= cp <= 0x04FF or 0x0500 <= cp <= 0x052F:
        return "Cyrillic"
    # Arabic
    if (
        0x0600 <= cp <= 0x06FF
        or 0x0750 <= cp <= 0x077F
        or 0xFB50 <= cp <= 0xFDFF
        or 0xFE70 <= cp <= 0xFEFF
    ):
        return "Arabic"
    # Devanagari
    if 0x0900 <= cp <= 0x097F:
        return "Devanagari"
    # Thai
    if 0x0E00 <= cp <= 0x0E7F:
        return "Thai"
    # Georgian
    if 0x10A0 <= cp <= 0x10FF:
        return "Georgian"
    # Hangul (Korean)
    if 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
        return "Hangul"
    # CJK (Chinese/Japanese Kanji)
    if (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0xF900 <= cp <= 0xFAFF
    ):
        return "CJK"
    # Hiragana
    if 0x3040 <= cp <= 0x309F:
        return "Hiragana"
    # Katakana
    if 0x30A0 <= cp <= 0x30FF:
        return "Katakana"
    # CJK Symbols/Punctuation (shared between ZH/JA/KO)
    if 0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF:
        return "CJK_Punct"
    # Greek
    if 0x0370 <= cp <= 0x03FF:
        return "Greek"
    # Hebrew
    if 0x0590 <= cp <= 0x05FF:
        return "Hebrew"
    # Armenian
    if 0x0530 <= cp <= 0x058F:
        return "Armenian"
    # Bengali
    if 0x0980 <= cp <= 0x09FF:
        return "Bengali"
    # Tamil
    if 0x0B80 <= cp <= 0x0BFF:
        return "Tamil"
    # Emoji and misc symbols
    if cp > 0xFFFF:
        return "Common"
    return "Other"


# Related script groups — scripts that commonly co-occur
_SCRIPT_COMPAT = {
    "CJK": {"CJK", "CJK_Punct", "Hiragana", "Katakana", "Common"},
    "Hiragana": {"CJK", "CJK_Punct", "Hiragana", "Katakana", "Common"},
    "Katakana": {"CJK", "CJK_Punct", "Hiragana", "Katakana", "Common"},
    "CJK_Punct": {"CJK", "CJK_Punct", "Hiragana", "Katakana", "Common"},
    "Hangul": {"Hangul", "CJK_Punct", "Common"},
}


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
        self._char_scripts = {}  # char -> script name
        self._script_indices = defaultdict(list)  # script -> [vocab indices]

    def train(self, texts):
        """Train on a list of text strings.

        CJK/Hangul/Japanese texts get multiplied counts to compensate for
        the lower diversity of CJK training data (template-generated).
        """
        charset = set()
        raw_counts = [defaultdict(Counter) for _ in range(self.order + 1)]

        for text in texts:
            padded = BOS * self.order + text + EOF
            charset.update(text)

            # Detect if text is primarily CJK/Hangul — boost count weight
            cjk_chars = sum(
                1
                for c in text
                if 0x4E00 <= ord(c) <= 0x9FFF
                or 0x3040 <= ord(c) <= 0x30FF  # Hiragana/Katakana
                or 0xAC00 <= ord(c) <= 0xD7AF
            )  # Hangul
            weight = 3 if cjk_chars > len(text) * 0.05 else 1

            for i in range(self.order, len(padded)):
                ch = padded[i]
                for n in range(self.order + 1):
                    ctx = padded[i - n : i]
                    raw_counts[n][ctx][ch] += weight

        # Convert to plain dicts and compute totals
        for n in range(self.order + 1):
            for ctx, counter in raw_counts[n].items():
                self.counts[n][ctx] = dict(counter)
                self.totals[n][ctx] = sum(counter.values())

        charset.add(EOF)
        charset.add(ESC)  # Escape symbol for inline unknown chars
        self._vocab_set = charset
        self.vocab = sorted(charset)
        self._vocab_idx = {ch: i for i, ch in enumerate(self.vocab)}
        self._build_script_index()

    def _build_script_index(self):
        """Build script classification for all vocab characters."""
        self._char_scripts = {}
        self._script_indices = defaultdict(list)
        for i, ch in enumerate(self.vocab):
            script = _char_script(ch)
            self._char_scripts[ch] = script
            self._script_indices[script].append(i)

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
        """Compute CDF from scratch using interpolation smoothing.

        Uses script-aware epsilon: characters from the same Unicode script
        as the context get higher base probability, ensuring that out-of-domain
        text compresses at least as well as a naive per-script encoder.
        """
        vocab = self.vocab
        n_vocab = len(vocab)

        # Step 1: find active orders and their weights
        active = []
        total_w = 0.0

        # Detect script early for confidence adjustment
        ctx_script_early = None
        for ch in reversed(context):
            if ch != BOS:
                ctx_script_early = self._char_scripts.get(ch)
                if ctx_script_early and ctx_script_early != "Common":
                    break

        # CJK/Hangul scripts have much sparser training data —
        # require more counts before trusting high-order contexts
        is_sparse_script = ctx_script_early in ("CJK", "Hiragana", "Katakana", "Hangul")
        confidence_denom = (
            (lambda n: n + 8.0) if is_sparse_script else (lambda n: n + 3.0)
        )

        for n in range(self.order, -1, -1):
            ctx = context[-n:] if n > 0 else ""
            t = self.totals[n].get(ctx, 0)
            if t > 0:
                # Confidence: penalize low-count contexts (more aggressive for sparse scripts)
                confidence = min(t / confidence_denom(n), 1.0)
                w = (n + 1) ** 3 * math.log1p(t) * confidence
                active.append((n, ctx, t, w))
                total_w += w

        # Step 2: compute script-aware epsilon
        # Detect active script from context (last non-BOS characters)
        ctx_script = None
        for ch in reversed(context):
            if ch != BOS:
                ctx_script = self._char_scripts.get(ch)
                if ctx_script and ctx_script != "Common":
                    break

        # Get compatible scripts
        if ctx_script and ctx_script in _SCRIPT_COMPAT:
            compat_scripts = _SCRIPT_COMPAT[ctx_script]
        elif ctx_script and ctx_script != "Common":
            compat_scripts = {ctx_script, "Common"}
        else:
            compat_scripts = None  # no script boost — use uniform

        # Build epsilon array
        freqs = [0] * n_vocab
        epsilon_total = 0
        for i, ch in enumerate(vocab):
            ch_script = self._char_scripts.get(ch, "Other")
            if ch == ESC:
                # ESC gets a fixed probability for inline unknown char encoding
                eps = ESC_PROB
            elif compat_scripts and ch_script in compat_scripts:
                eps = SCRIPT_BOOST
            elif ch_script == "Common":
                eps = SCRIPT_BOOST // 3
            else:
                eps = 1
            freqs[i] = eps
            epsilon_total += eps

        # Cap epsilon_total to at most CDF_SCALE // 2 to leave room for model
        if epsilon_total > CDF_SCALE // 2:
            scale_factor = (CDF_SCALE // 2) / epsilon_total
            epsilon_total = 0
            for i in range(n_vocab):
                freqs[i] = max(1, int(freqs[i] * scale_factor))
                epsilon_total += freqs[i]

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
            # Rebuild script index (indices shift when vocab is re-sorted)
            self._build_script_index()

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

    def decode_symbol(self, cdf, total=CDF_SCALE):
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

    Format v2: [2 bytes: text length as uint16 BE]
               [1 byte: flags (bit 0 = has inline escapes)]
               [AC bitstream]

    Unknown characters are encoded inline in the AC stream:
    ESC symbol + UTF-8 bytes (each byte encoded at uniform 1/256 probability).
    This avoids the expensive per-char header listing.
    """
    if not text:
        return b"\x00\x00"

    # Find chars not in training vocab
    extra_chars = set(ch for ch in text if ch not in model._vocab_set)
    has_extras = len(extra_chars) > 0

    # For backward compatibility: if no extras, use flag=0
    # If extras exist, use flag=1 (inline escape mode)
    flags = 1 if has_extras else 0

    encoder = ArithmeticEncoder()
    context = BOS * model.order

    for ch in text:
        if ch in model._vocab_set:
            # Normal character — encode using model CDF
            cdf = model.get_cdf(context)
            found = False
            for sym, cum_low, cum_high in cdf:
                if sym == ch:
                    encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
                    found = True
                    break
            if not found:
                raise ValueError(
                    f"Character '{ch}' (U+{ord(ch):04X}) in vocab but not in CDF"
                )
        else:
            # Unknown character — encode as ESC + block-aware codepoint
            cdf = model.get_cdf(context)
            for sym, cum_low, cum_high in cdf:
                if sym == ESC:
                    encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
                    break

            # Encode codepoint using block-aware variable-length encoding
            _encode_codepoint(encoder, ord(ch))

        context = (context + ch)[-model.order :]

    # Encode EOF
    cdf = model.get_cdf(context)
    for sym, cum_low, cum_high in cdf:
        if sym == EOF:
            encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
            break

    ac_bytes = encoder.finish()

    # Build header: [uint16 text_len] [uint8 flags]
    header = struct.pack(">HB", len(text), flags)

    return header + ac_bytes


def decompress(data, model):
    """
    Decompress bytes back to text using the trained model.

    Supports two formats:
    - v1 (flags >= 2 or old format): [2B len] [1B n_extra] [extra chars] [AC stream]
    - v2 (flags 0 or 1): [2B len] [1B flags] [AC stream with inline escapes]
    """
    if len(data) < 3:
        raise ValueError("Data too short")

    text_len = struct.unpack(">H", data[:2])[0]
    if text_len == 0:
        return ""

    flags_or_nextra = data[2]

    # Detect format: v2 uses flags 0 or 1, v1 has n_extra >= 0
    # If flags_or_nextra <= 1, it's v2 format (flags)
    # If flags_or_nextra > 1, it's v1 format (n_extra chars listed in header)
    # Edge case: v1 with 0 or 1 extra chars is indistinguishable from v2
    # Solution: v2 with flags=0 means "no extras, no escape" = same behavior as v1 with 0 extras
    # v2 with flags=1 means "has inline escapes"
    # v1 with n_extra=1 means "one extra char listed in header"
    # We detect by checking if the next byte looks like a UTF-8 char length (1-4)

    if flags_or_nextra > 1:
        # v1 format: old-style header with extra chars listed
        return _decompress_v1(data, model, text_len, flags_or_nextra)
    elif flags_or_nextra == 1:
        # v2 format: inline escape mode
        return _decompress_v2(data, model, text_len, has_escapes=True)
    else:
        # flags=0: no extras, same for both v1 and v2
        return _decompress_v2(data, model, text_len, has_escapes=False)


def _decompress_v1(data, model, text_len, n_extra):
    """Decompress v1 format with extra chars in header."""
    offset = 3
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


def _decompress_v2(data, model, text_len, has_escapes):
    """Decompress v2 format with inline escape encoding."""
    ac_data = data[3:]
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
        elif ch == ESC and has_escapes:
            # Decode inline codepoint using block-aware encoding
            cp = _decode_codepoint(decoder)
            ch = chr(cp)

        result.append(ch)
        context = (context + ch)[-model.order :]

    return "".join(result)
