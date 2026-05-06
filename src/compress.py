#!/usr/bin/env python3
"""
src/compress.py — THE FILE THE AGENT MODIFIES.

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

from src import base91


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
SCRIPT_BOOST = 8  # epsilon multiplier for same-script characters
ESC_PROB = 500  # base probability units for ESC symbol (out of CDF_SCALE=1M)


# ─── Unicode Block Ranges for Compact Codepoint Encoding ───
# Each block: (block_id, start, end, name)
# Ordered by frequency of use in multilingual text
_UNICODE_BLOCKS = [
    (0, 0x0400, 0x04FF),  # Cyrillic (256 chars)
    (1, 0x0100, 0x024F),  # Latin Extended (336 chars)
    (2, 0x2000, 0x206F),  # General Punctuation
    (3, 0x2190, 0x21FF),  # Arrows
    (4, 0x2600, 0x27BF),  # Misc Symbols + Dingbats
    (5, 0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs (emoji)
    (6, 0x1F600, 0x1F64F),  # Emoticons
    (7, 0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
    (8, 0xFE00, 0xFE0F),  # Variation Selectors
    (9, 0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
]
_NUM_BLOCKS = len(_UNICODE_BLOCKS)
_FALLBACK_BLOCK_ID = _NUM_BLOCKS  # for chars not in any block


# ─── (CJK common-char table removed — en/ru only) ────────
_CJK_COMMON = ""
_DEAD_CJK = """
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
"""
_TOTAL_BLOCK_IDS = _NUM_BLOCKS + 1  # blocks + fallback


def _encode_codepoint(encoder, cp):
    """Encode a Unicode codepoint using block-aware variable-length encoding."""
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
    """Decode a Unicode codepoint using block-aware encoding."""
    block_cdf = [(i, i, i + 1) for i in range(_TOTAL_BLOCK_IDS)]
    block_id = decoder.decode_symbol(block_cdf, total=_TOTAL_BLOCK_IDS)

    if block_id < _NUM_BLOCKS:
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
    """Classify a character: Latin / Cyrillic / Common / Other (en+ru only)."""
    cp = ord(ch)
    if cp < 0x0041:
        return "Common"
    if cp <= 0x024F or 0x1E00 <= cp <= 0x1EFF:
        return "Latin"
    if 0x0400 <= cp <= 0x052F:
        return "Cyrillic"
    if cp > 0xFFFF:
        return "Common"  # emoji / supplementary
    return "Other"


_SCRIPT_COMPAT = {}


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

    def get_cdf(self, context, has_escapes=True):
        """
        CDF for arithmetic coder (cached).
        Returns: [(char, cum_low, cum_high), ...]
        Sum of all intervals = CDF_SCALE exactly.

        When has_escapes=False, the ESC symbol is given zero probability mass,
        so the ESC_PROB budget is redistributed to real characters. Both encoder
        and decoder must agree on this flag (it's stored in the 1-byte header).
        """
        cache_key = (context, has_escapes)
        if cache_key in self._cdf_cache:
            return self._cdf_cache[cache_key]

        cdf = self._compute_cdf(context, has_escapes)

        if len(self._cdf_cache) < CDF_CACHE_MAX:
            self._cdf_cache[cache_key] = cdf

        return cdf

    def _compute_cdf(self, context, has_escapes=True):
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

        max_match_order = -1
        for n in range(self.order, -1, -1):
            ctx = context[-n:] if n > 0 else ""
            t = self.totals[n].get(ctx, 0)
            if t > 0:
                confidence = t / (t + 1.5)
                w = (n + 1) ** 3 * math.log1p(t) * confidence
                active.append((n, ctx, t, w))
                total_w += w
                if n > max_match_order:
                    max_match_order = n

        # When only short-context matches are available, model is uncertain;
        # boost the script-prior so mass goes to plausible characters.
        if max_match_order <= 2:
            script_boost = SCRIPT_BOOST * 4
        else:
            script_boost = SCRIPT_BOOST

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
                # ESC gets a fixed probability for inline unknown char encoding.
                # When the message has no escapes (signalled in the header), we
                # know ESC will never be encoded, so we don't waste mass on it.
                eps = ESC_PROB if has_escapes else 0
            elif compat_scripts and ch_script in compat_scripts:
                eps = script_boost
            elif ch_script == "Common":
                eps = max(1, script_boost // 3)
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

    def finish_bits(self):
        """Same as finish() but returns the raw bit list (no byte padding)."""
        self.pending += 1
        if self.low < QUARTER:
            self._emit_bit(0)
        else:
            self._emit_bit(1)
        return list(self.bits)


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


def _compress_ac_bits(text, model):
    """Same as _compress_ac, but returns (flags, bits) without byte padding.

    `bits` is a list of 0/1 ints. Caller is responsible for serialization.
    """
    extra_chars = set(ch for ch in text if ch not in model._vocab_set)
    has_extras = len(extra_chars) > 0
    flags = 1 if has_extras else 0

    encoder = ArithmeticEncoder()
    context = BOS * model.order

    for ch in text:
        cdf = model.get_cdf(context, has_escapes=has_extras)
        if ch in model._vocab_set:
            for sym, cum_low, cum_high in cdf:
                if sym == ch:
                    encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
                    break
        else:
            for sym, cum_low, cum_high in cdf:
                if sym == ESC:
                    encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
                    break
            _encode_codepoint(encoder, ord(ch))
        context = (context + ch)[-model.order :]

    cdf = model.get_cdf(context, has_escapes=has_extras)
    for sym, cum_low, cum_high in cdf:
        if sym == EOF:
            encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
            break

    return flags, encoder.finish_bits()


def _compress_ac(text, model):
    """
    Internal: compress text using arithmetic coding.
    Returns: bytes (3-byte header + AC bitstream)
    """
    extra_chars = set(ch for ch in text if ch not in model._vocab_set)
    has_extras = len(extra_chars) > 0
    flags = 1 if has_extras else 0

    encoder = ArithmeticEncoder()
    context = BOS * model.order

    for ch in text:
        if ch in model._vocab_set:
            cdf = model.get_cdf(context, has_escapes=has_extras)
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
            cdf = model.get_cdf(context, has_escapes=has_extras)
            for sym, cum_low, cum_high in cdf:
                if sym == ESC:
                    encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
                    break
            _encode_codepoint(encoder, ord(ch))

        context = (context + ch)[-model.order :]

    cdf = model.get_cdf(context, has_escapes=has_extras)
    for sym, cum_low, cum_high in cdf:
        if sym == EOF:
            encoder.encode_symbol(cum_low, cum_high, CDF_SCALE)
            break

    ac_bytes = encoder.finish()

    # 1-byte header. Length is implicit: decoder loops until EOF symbol.
    #   data[0] == 0x00 → compressed, no escapes
    #   data[0] == 0x01 → compressed, with escapes
    #   data[0] >= 0x02 → passthrough (raw UTF-8)
    return bytes([flags & 0x01]) + ac_bytes


def compress(text, model):
    """
    Compress text using the trained model.
    Returns: bytes

    Format (binary):
      data[0] == 0x00 → compressed, no escapes
      data[0] == 0x01 → compressed, with escapes
      data[0] >= 0x02 → passthrough (raw UTF-8; real UTF-8 never starts <0x02)
    """
    if not text:
        return b""

    utf8_bytes = text.encode("utf-8")
    ac_result = _compress_ac(text, model)

    if len(ac_result) > len(utf8_bytes) and utf8_bytes[0] >= 0x02:
        return utf8_bytes
    return ac_result


def decompress(data, model):
    """
    Decompress bytes back to text using the trained model.

    Supports formats:
    - Passthrough: data[0] != 0x00 → raw UTF-8, just decode directly
    - Empty:       data == b'\\x00\\x00' → empty string
    - Compressed:  data[0] == 0x00 → standard format with header
      - v1 (flags >= 2): old-style header with extra chars listed
      - v2 (flags 0 or 1): inline escape mode
    """
    if not data:
        return ""

    # Format discrimination via first byte:
    #   0x00 → compressed, no escapes
    #   0x01 → compressed, with escapes
    #   else → passthrough (raw UTF-8; valid UTF-8 text never starts with 0x00/0x01)
    flags = data[0]
    if flags > 0x01:
        return data.decode("utf-8")

    has_escapes = bool(flags & 1)
    ac_data = data[1:]
    if not ac_data:
        return ""

    decoder = ArithmeticDecoder(ac_data)
    context = BOS * model.order
    result = []

    # Hard upper bound to prevent runaway in case of corrupted input.
    # Meshtastic packets are <256 chars so 4096 is generous.
    for _ in range(4096):
        cdf = model.get_cdf(context, has_escapes=has_escapes)
        ch = decoder.decode_symbol(cdf)
        if ch == EOF:
            break
        elif ch == ESC and has_escapes:
            cp = _decode_codepoint(decoder)
            ch = chr(cp)
        result.append(ch)
        context = (context + ch)[-model.order :]

    return "".join(result)


# ═══════════════════════════════════════════════════════════
# TEXT-CHANNEL API (Meshtastic text channels send printable ASCII)
# ═══════════════════════════════════════════════════════════
#
# Wire format on text channels (e.g. LoRa text payload, base91-only):
#   First base91 character signals the format:
#     '!'        → empty message
#     '"'        → compressed, no escapes      (base91 of AC bitstream)
#     '#'        → compressed, with escapes    (base91 of AC bitstream)
#     anything else → passthrough (rest of string is the raw text verbatim)
#
# `!`, `"`, `#` are the first three printable ASCII characters and
# extremely rare as the first character of organic short messages
# in en/ru. The passthrough path therefore stays zero-overhead for
# the vast majority of messages.
_TC_EMPTY = "!"
_TC_COMPRESSED_NOESC = '"'
_TC_COMPRESSED_ESC = "#"
_TC_MARKERS = {_TC_EMPTY, _TC_COMPRESSED_NOESC, _TC_COMPRESSED_ESC}


def _bits_to_min_bytes(bits):
    """Pack MSB-first bit stream into bytes, dropping any trailing all-zero byte
    that consists purely of finalisation padding. Decoder doesn't need those —
    AC decoder's _read_bit returns 0 past the end."""
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for j in range(8):
            v = (v << 1) | (bits[i + j] if i + j < len(bits) else 0)
        out.append(v)
    # Strip trailing zero bytes (they're just padding noise).
    while len(out) > 0 and out[-1] == 0:
        out.pop()
    return bytes(out)


def compress_text(text, model):
    """Compress to a text-channel-safe printable-ASCII string.

    Pipeline: AC bit stream → minimal bytes (drop trailing zero pad-bytes) →
    base91 → 1-char format/escape marker prefix. Falls back to raw passthrough
    if that's shorter than the encoded form.
    """
    if not text:
        return _TC_EMPTY

    flags, bits = _compress_ac_bits(text, model)
    payload = _bits_to_min_bytes(bits)
    marker = _TC_COMPRESSED_ESC if flags & 1 else _TC_COMPRESSED_NOESC
    compressed_text = marker + base91.encode(payload)

    if len(compressed_text) >= len(text) and text[0] not in _TC_MARKERS:
        return text
    return compressed_text


def decompress_text(s, model):
    """Inverse of compress_text."""
    if not s:
        return ""
    head = s[0]
    if head == _TC_EMPTY:
        return ""
    if head == _TC_COMPRESSED_NOESC:
        flags = 0
    elif head == _TC_COMPRESSED_ESC:
        flags = 1
    else:
        return s  # passthrough

    payload = base91.decode(s[1:])
    return decompress(bytes([flags]) + payload, model)


# ═══════════════════════════════════════════════════════════
# MODEL SERIALIZATION (compact, zlib-compressed pickle)
# ═══════════════════════════════════════════════════════════

import zlib as _zlib


def prune_model(model, threshold=2):
    """Drop low-count contexts at order >= 3 to shrink the model.

    threshold=1 is a no-op. Higher thresholds trade bpc for size:
      thr=2  → ~74% smaller, +0.06 bpc
      thr=3  → ~84% smaller, +0.11 bpc
      thr=5  → ~90% smaller, +0.19 bpc

    Returns the same model object (mutated).
    """
    if threshold <= 1:
        return model
    for n in range(3, model.order + 1):
        for ctx in list(model.totals[n].keys()):
            if model.totals[n][ctx] < threshold:
                del model.counts[n][ctx]
                del model.totals[n][ctx]
    model._cdf_cache = {}
    return model


def save_model(model, path, threshold=1, compress_level=9):
    """Pickle + zlib + optional pruning. Format:
        4 bytes magic 'NGM1' | zlib(pickle(model_dict))
    """
    import pickle as _pickle
    if threshold > 1:
        prune_model(model, threshold)
    payload = _pickle.dumps(model, protocol=_pickle.HIGHEST_PROTOCOL)
    blob = b"NGM1" + _zlib.compress(payload, compress_level)
    with open(path, "wb") as f:
        f.write(blob)
    return len(blob)


def load_model(path):
    import pickle as _pickle
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:4] != b"NGM1":
        # Legacy uncompressed pickle.
        return _pickle.loads(blob)
    return _pickle.loads(_zlib.decompress(blob[4:]))
