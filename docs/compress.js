// compress.js — Client-side n-gram + arithmetic coding compressor.
// Direct port of src/compress.py (en+ru focused track).
//
// Implements:
//   - 1-byte header binary format (EOF-terminated AC stream)
//   - ESC + Unicode-block codepoint encoding for out-of-vocab chars
//   - Script-aware epsilon smoothing (Latin / Cyrillic / Common / Other)
//   - Text-channel API: compressText / decompressText (printable ASCII)

const BOS = '\x02';
const EOF = '\x03';
const ESC = '\x04';

const CDF_SCALE = 1 << 20;
const PRECISION = 32;
const FULL = 1n << BigInt(PRECISION);
const HALF = 1n << BigInt(PRECISION - 1);
const QUARTER = 1n << BigInt(PRECISION - 2);
const MASK = FULL - 1n;
const THREE_QUARTER = 3n * QUARTER;

const SCRIPT_BOOST = 8;
const ESC_PROB = 500;

// Same Unicode blocks as src/compress.py _UNICODE_BLOCKS.
const UNICODE_BLOCKS = [
  [0, 0x0400, 0x04FF],   // Cyrillic
  [1, 0x0100, 0x024F],   // Latin Extended
  [2, 0x2000, 0x206F],   // General Punctuation
  [3, 0x2190, 0x21FF],   // Arrows
  [4, 0x2600, 0x27BF],   // Misc Symbols + Dingbats
  [5, 0x1F300, 0x1F5FF], // Misc Symbols and Pictographs
  [6, 0x1F600, 0x1F64F], // Emoticons
  [7, 0x1F900, 0x1F9FF], // Supplemental Symbols and Pictographs
  [8, 0xFE00, 0xFE0F],   // Variation Selectors
  [9, 0x1FA70, 0x1FAFF], // Symbols and Pictographs Extended-A
];
const NUM_BLOCKS = UNICODE_BLOCKS.length;
const FALLBACK_BLOCK_ID = NUM_BLOCKS;
const TOTAL_BLOCK_IDS = NUM_BLOCKS + 1;

function charScript(ch) {
  const cp = ch.codePointAt(0);
  if (cp < 0x0041) return 'Common';
  if (cp <= 0x024F || (cp >= 0x1E00 && cp <= 0x1EFF)) return 'Latin';
  if (cp >= 0x0400 && cp <= 0x052F) return 'Cyrillic';
  if (cp > 0xFFFF) return 'Common';
  return 'Other';
}

class NGramModel {
  constructor(order, vocab, counts) {
    this.order = order;
    this.vocab = vocab;
    this.vocabIdx = new Map();
    for (let i = 0; i < vocab.length; i++) this.vocabIdx.set(vocab[i], i);
    this.vocabSet = new Set(vocab);
    this.counts = counts;
    this.totals = [];
    for (let n = 0; n <= order; n++) {
      const t = new Map();
      for (const [ctx, charCounts] of this.counts[n]) {
        let sum = 0;
        for (const c of charCounts.values()) sum += c;
        t.set(ctx, sum);
      }
      this.totals.push(t);
    }
    this.cdfCache = new Map();
    this._buildScriptIndex();
  }

  static fromJSON(data) {
    const order = data.o;
    const vocab = data.v.slice();
    // Make sure EOF/ESC are present (export should include them, but be safe).
    for (const sym of [EOF, ESC]) if (!vocab.includes(sym)) vocab.push(sym);
    vocab.sort();
    const counts = [];
    for (let n = 0; n <= order; n++) {
      const m = new Map();
      const obj = data.c[n] || {};
      for (const ctx in obj) {
        const charMap = new Map();
        const co = obj[ctx];
        for (const ch in co) charMap.set(ch, co[ch]);
        m.set(ctx, charMap);
      }
      counts.push(m);
    }
    return new NGramModel(order, vocab, counts);
  }

  _buildScriptIndex() {
    this.charScripts = new Map();
    for (const ch of this.vocab) this.charScripts.set(ch, charScript(ch));
  }

  ensureChar(ch) {
    if (!this.vocabSet.has(ch)) {
      this.vocabSet.add(ch);
      this.vocab.push(ch);
      this.vocab.sort();
      this.vocabIdx.clear();
      for (let i = 0; i < this.vocab.length; i++) this.vocabIdx.set(this.vocab[i], i);
      this.cdfCache.clear();
      this._buildScriptIndex();
    }
  }

  getCDF(context, hasEscapes) {
    const key = (hasEscapes ? '1|' : '0|') + context;
    let cdf = this.cdfCache.get(key);
    if (cdf) return cdf;
    cdf = this._computeCDF(context, hasEscapes);
    if (this.cdfCache.size < 50000) this.cdfCache.set(key, cdf);
    return cdf;
  }

  _computeCDF(context, hasEscapes) {
    const vocab = this.vocab;
    const nVocab = vocab.length;

    // Active orders + weights
    const active = [];
    let totalW = 0;
    let maxMatchOrder = -1;
    for (let n = this.order; n >= 0; n--) {
      const ctx = n > 0 ? context.slice(-n) : '';
      const t = this.totals[n].get(ctx);
      if (t !== undefined && t > 0) {
        const confidence = t / (t + 1.5);
        const w = (n + 1) ** 3 * Math.log1p(t) * confidence;
        active.push([n, ctx, t, w]);
        totalW += w;
        if (n > maxMatchOrder) maxMatchOrder = n;
      }
    }
    const scriptBoost = maxMatchOrder <= 2 ? SCRIPT_BOOST * 4 : SCRIPT_BOOST;

    // Detect ctx script (last non-BOS char with non-Common script)
    let ctxScript = null;
    for (let i = context.length - 1; i >= 0; i--) {
      const ch = context[i];
      if (ch !== BOS) {
        const s = this.charScripts.get(ch) || charScript(ch);
        if (s && s !== 'Common') { ctxScript = s; break; }
        if (!ctxScript) ctxScript = s;
      }
    }

    // Compatible scripts set
    let compat = null;
    if (ctxScript && ctxScript !== 'Common') compat = new Set([ctxScript, 'Common']);

    // Epsilon
    const freqs = new Array(nVocab);
    let epsilonTotal = 0;
    for (let i = 0; i < nVocab; i++) {
      const ch = vocab[i];
      const sc = this.charScripts.get(ch) || 'Other';
      let eps;
      if (ch === ESC) {
        eps = hasEscapes ? ESC_PROB : 0;
      } else if (compat && compat.has(sc)) {
        eps = scriptBoost;
      } else if (sc === 'Common') {
        eps = Math.max(1, Math.floor(scriptBoost / 3));
      } else {
        eps = 1;
      }
      freqs[i] = eps;
      epsilonTotal += eps;
    }

    if (epsilonTotal > CDF_SCALE / 2) {
      const factor = (CDF_SCALE / 2) / epsilonTotal;
      epsilonTotal = 0;
      for (let i = 0; i < nVocab; i++) {
        freqs[i] = Math.max(1, Math.floor(freqs[i] * factor));
        epsilonTotal += freqs[i];
      }
    }

    if (totalW > 0) {
      const SCALE = CDF_SCALE - epsilonTotal;
      for (const [n, ctx, total, w] of active) {
        const countsN = this.counts[n].get(ctx);
        if (!countsN) continue;
        const factor = (w / totalW) * SCALE / total;
        for (const [ch, count] of countsN) {
          const idx = this.vocabIdx.get(ch);
          if (idx !== undefined) freqs[idx] += Math.floor(count * factor);
        }
      }
    }

    // Normalize to CDF_SCALE exactly
    let total = 0;
    for (let i = 0; i < nVocab; i++) total += freqs[i];
    if (total !== CDF_SCALE) {
      let diff = CDF_SCALE - total;
      if (diff > 0) {
        let mi = 0;
        for (let i = 1; i < nVocab; i++) if (freqs[i] > freqs[mi]) mi = i;
        freqs[mi] += diff;
      } else {
        const idxs = Array.from({length: nVocab}, (_, i) => i);
        idxs.sort((a, b) => freqs[b] - freqs[a]);
        let remaining = -diff;
        for (const idx of idxs) {
          if (remaining <= 0) break;
          const can = freqs[idx] - 1;
          const rm = Math.min(can, remaining);
          freqs[idx] -= rm;
          remaining -= rm;
        }
      }
    }

    const cdf = new Array(nVocab);
    let cum = 0;
    for (let i = 0; i < nVocab; i++) {
      const f = freqs[i];
      cdf[i] = [vocab[i], cum, cum + f];
      cum += f;
    }
    return cdf;
  }

  clearCache() { this.cdfCache.clear(); }
}

// ═══ Arithmetic Encoder ═══

class ArithmeticEncoder {
  constructor() {
    this.low = 0n;
    this.high = MASK;
    this.pending = 0;
    this.bits = [];
  }
  _emitBit(bit) {
    this.bits.push(bit);
    const opp = 1 - bit;
    for (let i = 0; i < this.pending; i++) this.bits.push(opp);
    this.pending = 0;
  }
  encodeSymbol(cumLow, cumHigh, total) {
    const cl = BigInt(cumLow), ch = BigInt(cumHigh), tot = BigInt(total);
    const rng = this.high - this.low + 1n;
    this.high = this.low + (rng * ch) / tot - 1n;
    this.low  = this.low + (rng * cl) / tot;
    while (true) {
      if (this.high < HALF) this._emitBit(0);
      else if (this.low >= HALF) { this._emitBit(1); this.low -= HALF; this.high -= HALF; }
      else if (this.low >= QUARTER && this.high < THREE_QUARTER) {
        this.pending++; this.low -= QUARTER; this.high -= QUARTER;
      } else break;
      this.low = (this.low << 1n) & MASK;
      this.high = ((this.high << 1n) | 1n) & MASK;
    }
  }
  finishBits() {
    this.pending++;
    if (this.low < QUARTER) this._emitBit(0); else this._emitBit(1);
    return this.bits;
  }
  finish() {
    const bits = this.finishBits().slice();
    while (bits.length % 8 !== 0) bits.push(0);
    const out = new Uint8Array(bits.length / 8);
    for (let i = 0; i < bits.length; i += 8) {
      let b = 0;
      for (let j = 0; j < 8; j++) b = (b << 1) | bits[i + j];
      out[i / 8] = b;
    }
    return out;
  }
}

// ═══ Arithmetic Decoder ═══

class ArithmeticDecoder {
  constructor(data) {
    this.data = data;
    this.low = 0n;
    this.high = MASK;
    this.value = 0n;
    this.bitPos = 0;
    this.totalBits = data.length * 8;
    for (let i = 0; i < PRECISION; i++) {
      this.value = (this.value << 1n) | BigInt(this._readBit());
    }
  }
  _readBit() {
    if (this.bitPos >= this.totalBits) return 0;
    const bi = this.bitPos >> 3;
    const bit = 7 - (this.bitPos & 7);
    this.bitPos++;
    return (this.data[bi] >> bit) & 1;
  }
  decodeSymbol(cdf, total = CDF_SCALE) {
    const tot = BigInt(total);
    const rng = this.high - this.low + 1n;
    const scaled = Number(((this.value - this.low + 1n) * tot - 1n) / rng);
    let lo = 0, hi = cdf.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cdf[mid][2] <= scaled) lo = mid + 1; else hi = mid;
    }
    const [sym, cumLow, cumHigh] = cdf[lo];
    this.high = this.low + (rng * BigInt(cumHigh)) / tot - 1n;
    this.low  = this.low + (rng * BigInt(cumLow))  / tot;
    while (true) {
      if (this.high < HALF) {/* nothing */}
      else if (this.low >= HALF) { this.low -= HALF; this.high -= HALF; this.value -= HALF; }
      else if (this.low >= QUARTER && this.high < THREE_QUARTER) {
        this.low -= QUARTER; this.high -= QUARTER; this.value -= QUARTER;
      } else break;
      this.low = (this.low << 1n) & MASK;
      this.high = ((this.high << 1n) | 1n) & MASK;
      this.value = ((this.value << 1n) | BigInt(this._readBit())) & MASK;
    }
    return sym;
  }
}

// ═══ Codepoint encoding (ESC follow-up) ═══

function encodeCodepoint(encoder, cp) {
  for (const [bid, start, end] of UNICODE_BLOCKS) {
    if (cp >= start && cp <= end) {
      encoder.encodeSymbol(bid, bid + 1, TOTAL_BLOCK_IDS);
      const size = end - start + 1;
      const off = cp - start;
      encoder.encodeSymbol(off, off + 1, size);
      return;
    }
  }
  encoder.encodeSymbol(FALLBACK_BLOCK_ID, FALLBACK_BLOCK_ID + 1, TOTAL_BLOCK_IDS);
  encoder.encodeSymbol(cp & 0x7F, (cp & 0x7F) + 1, 128);
  encoder.encodeSymbol((cp >> 7) & 0x7F, ((cp >> 7) & 0x7F) + 1, 128);
  encoder.encodeSymbol((cp >> 14) & 0x7F, ((cp >> 14) & 0x7F) + 1, 128);
}

function decodeCodepoint(decoder) {
  const blockCdf = [];
  for (let i = 0; i < TOTAL_BLOCK_IDS; i++) blockCdf.push([i, i, i + 1]);
  const bid = decoder.decodeSymbol(blockCdf, TOTAL_BLOCK_IDS);
  if (bid < NUM_BLOCKS) {
    const [, start, end] = UNICODE_BLOCKS[bid];
    const size = end - start + 1;
    const offCdf = [];
    for (let i = 0; i < size; i++) offCdf.push([i, i, i + 1]);
    const off = decoder.decodeSymbol(offCdf, size);
    return start + off;
  }
  const cdf128 = [];
  for (let i = 0; i < 128; i++) cdf128.push([i, i, i + 1]);
  const b0 = decoder.decodeSymbol(cdf128, 128);
  const b1 = decoder.decodeSymbol(cdf128, 128);
  const b2 = decoder.decodeSymbol(cdf128, 128);
  return b0 | (b1 << 7) | (b2 << 14);
}

// ═══ Compress / Decompress (binary, 1-byte header) ═══

function compressAcBits(text, model) {
  let hasExtras = false;
  for (const ch of text) if (!model.vocabSet.has(ch)) { hasExtras = true; break; }
  const flags = hasExtras ? 1 : 0;

  const enc = new ArithmeticEncoder();
  let context = BOS.repeat(model.order);

  for (const ch of text) {
    const cdf = model.getCDF(context, hasExtras);
    if (model.vocabSet.has(ch)) {
      for (const [s, lo, hi] of cdf) if (s === ch) { enc.encodeSymbol(lo, hi, CDF_SCALE); break; }
    } else {
      for (const [s, lo, hi] of cdf) if (s === ESC) { enc.encodeSymbol(lo, hi, CDF_SCALE); break; }
      encodeCodepoint(enc, ch.codePointAt(0));
    }
    context = (context + ch).slice(-model.order);
  }
  const cdf = model.getCDF(context, hasExtras);
  for (const [s, lo, hi] of cdf) if (s === EOF) { enc.encodeSymbol(lo, hi, CDF_SCALE); break; }

  return [flags, enc.finishBits()];
}

function bitsToBytes(bits) {
  const len = Math.ceil(bits.length / 8);
  const out = new Uint8Array(len);
  for (let i = 0; i < bits.length; i++) {
    if (bits[i]) out[i >> 3] |= 1 << (7 - (i & 7));
  }
  return out;
}

function bitsToMinBytes(bits) {
  const out = bitsToBytes(bits);
  let end = out.length;
  while (end > 0 && out[end - 1] === 0) end--;
  return out.slice(0, end);
}

function utf8(text) { return new TextEncoder().encode(text); }

function compress(text, model) {
  if (!text) return new Uint8Array(0);
  const [flags, bits] = compressAcBits(text, model);
  const acBytes = bitsToBytes(bits);
  const out = new Uint8Array(1 + acBytes.length);
  out[0] = flags & 1;
  out.set(acBytes, 1);
  const u = utf8(text);
  if (out.length > u.length && u[0] >= 0x02) return u;
  return out;
}

function decompress(data, model) {
  if (!data || !data.length) return '';
  const flags = data[0];
  if (flags > 0x01) return new TextDecoder().decode(data);
  const hasEscapes = (flags & 1) === 1;
  if (data.length === 1) return '';
  const ac = data.subarray(1);
  const dec = new ArithmeticDecoder(ac);
  let context = BOS.repeat(model.order);
  let result = '';
  for (let i = 0; i < 4096; i++) {
    const cdf = model.getCDF(context, hasEscapes);
    const ch = dec.decodeSymbol(cdf);
    if (ch === EOF) break;
    let outCh;
    if (ch === ESC && hasEscapes) {
      const cp = decodeCodepoint(dec);
      outCh = String.fromCodePoint(cp);
    } else {
      outCh = ch;
    }
    result += outCh;
    context = (context + outCh).slice(-model.order);
  }
  return result;
}

// ═══ Text-channel API (printable ASCII via base91) ═══

const TC_EMPTY = '!';
const TC_COMPRESSED_NOESC = '"';
const TC_COMPRESSED_ESC = '#';
const TC_MARKERS = new Set([TC_EMPTY, TC_COMPRESSED_NOESC, TC_COMPRESSED_ESC]);

function compressText(text, model) {
  if (!text) return TC_EMPTY;
  const [flags, bits] = compressAcBits(text, model);
  const payload = bitsToMinBytes(bits);
  const marker = (flags & 1) ? TC_COMPRESSED_ESC : TC_COMPRESSED_NOESC;
  const compressedText = marker + b91encode(payload);
  if (compressedText.length >= text.length && !TC_MARKERS.has(text[0])) return text;
  return compressedText;
}

function decompressText(s, model) {
  if (!s) return '';
  const head = s[0];
  if (head === TC_EMPTY) return '';
  let flags;
  if (head === TC_COMPRESSED_NOESC) flags = 0;
  else if (head === TC_COMPRESSED_ESC) flags = 1;
  else return s; // passthrough
  const payload = b91decode(s.slice(1));
  const buf = new Uint8Array(1 + payload.length);
  buf[0] = flags;
  buf.set(payload, 1);
  return decompress(buf, model);
}

// ═══ Base91 ═══

const B91_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&()*+,./:;<=>?@[]^_`{|}~"';
const B91_DECODE = new Map();
for (let i = 0; i < B91_ALPHABET.length; i++) B91_DECODE.set(B91_ALPHABET[i], i);

function b91encode(data) {
  if (!data.length) return '';
  const result = [];
  let n = 0, nbits = 0;
  for (const byte of data) {
    n |= byte << nbits;
    nbits += 8;
    if (nbits > 13) {
      let val = n & 8191;
      if (val > 88) { n >>= 13; nbits -= 13; }
      else { val = n & 16383; n >>= 14; nbits -= 14; }
      result.push(B91_ALPHABET[val % 91]);
      result.push(B91_ALPHABET[Math.floor(val / 91)]);
    }
  }
  if (nbits) {
    result.push(B91_ALPHABET[n % 91]);
    if (n >= 91 || nbits > 7) result.push(B91_ALPHABET[Math.floor(n / 91)]);
  }
  return result.join('');
}

function b91decode(text) {
  if (!text) return new Uint8Array(0);
  const result = [];
  let n = 0, nbits = 0, v = -1;
  for (const char of text) {
    const c = B91_DECODE.get(char);
    if (c === undefined) throw new Error(`Invalid Base91 char: ${char}`);
    if (v === -1) { v = c; }
    else {
      v += c * 91;
      const b = (v & 8191) > 88 ? 13 : 14;
      n |= v << nbits;
      nbits += b;
      v = -1;
      while (nbits >= 8) { result.push(n & 0xFF); n >>= 8; nbits -= 8; }
    }
  }
  if (v !== -1) {
    n |= v << nbits;
    nbits += 7;
    while (nbits >= 8) { result.push(n & 0xFF); n >>= 8; nbits -= 8; }
  }
  return new Uint8Array(result);
}
