// compress.js — Client-side n-gram + arithmetic coding compressor
// Direct port of autoresearch/compress.py

const BOS = '\x02';
const EOF = '\x03';
const CDF_SCALE = 1 << 20; // 1048576
const PRECISION = 32;
const FULL = BigInt(1) << BigInt(PRECISION); // 4294967296n
const HALF = BigInt(1) << BigInt(PRECISION - 1);
const QUARTER = BigInt(1) << BigInt(PRECISION - 2);
const MASK = FULL - 1n;
const THREE_QUARTER = 3n * QUARTER;

class NGramModel {
  constructor(order, vocab, counts) {
    this.order = order;
    this.vocab = vocab; // sorted array of chars
    this.vocabIdx = new Map();
    for (let i = 0; i < vocab.length; i++) this.vocabIdx.set(vocab[i], i);
    this.vocabSet = new Set(vocab);
    // counts[n] = Map<context, Map<char, count>>
    // totals[n] = Map<context, total>
    this.counts = counts; // array of Maps
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
  }

  static fromJSON(data) {
    const order = data.o;
    const vocab = data.v;
    const counts = [];
    for (let n = 0; n <= order; n++) {
      const m = new Map();
      const obj = data.c[n];
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

  ensureChar(ch) {
    if (!this.vocabSet.has(ch)) {
      this.vocabSet.add(ch);
      this.vocab.push(ch);
      this.vocab.sort();
      this.vocabIdx.clear();
      for (let i = 0; i < this.vocab.length; i++) this.vocabIdx.set(this.vocab[i], i);
      this.cdfCache.clear();
    }
  }

  getCDF(context) {
    let cdf = this.cdfCache.get(context);
    if (cdf) return cdf;
    cdf = this._computeCDF(context);
    if (this.cdfCache.size < 50000) this.cdfCache.set(context, cdf);
    return cdf;
  }

  _computeCDF(context) {
    const vocab = this.vocab;
    const nVocab = vocab.length;

    // Find active orders and weights
    const active = [];
    let totalW = 0;
    for (let n = this.order; n >= 0; n--) {
      const ctx = n > 0 ? context.slice(-n) : '';
      const t = this.totals[n].get(ctx);
      if (t !== undefined && t > 0) {
        const w = (n + 1) * (n + 1) * (n + 1) * Math.log1p(t);
        active.push([n, ctx, t, w]);
        totalW += w;
      }
    }

    // Start with uniform epsilon
    const freqs = new Array(nVocab).fill(1);
    const epsilonTotal = nVocab;

    if (totalW > 0) {
      const SCALE = CDF_SCALE - epsilonTotal;
      for (const [n, ctx, total, w] of active) {
        const countsN = this.counts[n].get(ctx);
        if (!countsN) continue;
        const factor = (w / totalW) * SCALE / total;
        for (const [ch, count] of countsN) {
          const idx = this.vocabIdx.get(ch);
          if (idx !== undefined) {
            freqs[idx] += Math.floor(count * factor);
          }
        }
      }
    }

    // Normalize to CDF_SCALE exactly
    let total = 0;
    for (let i = 0; i < nVocab; i++) total += freqs[i];
    if (total !== CDF_SCALE) {
      let diff = CDF_SCALE - total;
      if (diff > 0) {
        let maxIdx = 0;
        for (let i = 1; i < nVocab; i++) if (freqs[i] > freqs[maxIdx]) maxIdx = i;
        freqs[maxIdx] += diff;
      } else {
        // Sort indices by freq descending
        const indices = Array.from({length: nVocab}, (_, i) => i);
        indices.sort((a, b) => freqs[b] - freqs[a]);
        let remaining = -diff;
        for (const idx of indices) {
          if (remaining <= 0) break;
          const canRemove = freqs[idx] - 1;
          const remove = Math.min(canRemove, remaining);
          freqs[idx] -= remove;
          remaining -= remove;
        }
      }
    }

    // Build CDF: [[char, cumLow, cumHigh], ...]
    const cdf = [];
    let cum = 0;
    for (let i = 0; i < nVocab; i++) {
      const f = freqs[i];
      cdf.push([vocab[i], cum, cum + f]);
      cum += f;
    }
    return cdf;
  }

  clearCache() {
    this.cdfCache.clear();
  }
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
    const cumLowB = BigInt(cumLow);
    const cumHighB = BigInt(cumHigh);
    const totalB = BigInt(total);
    const rng = this.high - this.low + 1n;
    this.high = this.low + (rng * cumHighB) / totalB - 1n;
    this.low = this.low + (rng * cumLowB) / totalB;

    while (true) {
      if (this.high < HALF) {
        this._emitBit(0);
      } else if (this.low >= HALF) {
        this._emitBit(1);
        this.low -= HALF;
        this.high -= HALF;
      } else if (this.low >= QUARTER && this.high < THREE_QUARTER) {
        this.pending++;
        this.low -= QUARTER;
        this.high -= QUARTER;
      } else {
        break;
      }
      this.low = (this.low << 1n) & MASK;
      this.high = ((this.high << 1n) | 1n) & MASK;
    }
  }

  finish() {
    this.pending++;
    if (this.low < QUARTER) this._emitBit(0);
    else this._emitBit(1);

    while (this.bits.length % 8 !== 0) this.bits.push(0);

    const result = new Uint8Array(this.bits.length / 8);
    for (let i = 0; i < this.bits.length; i += 8) {
      let byte = 0;
      for (let j = 0; j < 8; j++) byte = (byte << 1) | this.bits[i + j];
      result[i / 8] = byte;
    }
    return result;
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
    const byteIdx = this.bitPos >> 3;
    const bitIdx = 7 - (this.bitPos & 7);
    this.bitPos++;
    return (this.data[byteIdx] >> bitIdx) & 1;
  }

  decodeSymbol(cdf) {
    const totalB = BigInt(CDF_SCALE);
    const rng = this.high - this.low + 1n;
    const scaled = Number(((this.value - this.low + 1n) * totalB - 1n) / rng);

    // Binary search
    let lo = 0, hi = cdf.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (cdf[mid][2] <= scaled) lo = mid + 1;
      else hi = mid;
    }
    const [sym, cumLow, cumHigh] = cdf[lo];

    const cumLowB = BigInt(cumLow);
    const cumHighB = BigInt(cumHigh);
    this.high = this.low + (rng * cumHighB) / totalB - 1n;
    this.low = this.low + (rng * cumLowB) / totalB;

    while (true) {
      if (this.high < HALF) {
        // nothing
      } else if (this.low >= HALF) {
        this.low -= HALF;
        this.high -= HALF;
        this.value -= HALF;
      } else if (this.low >= QUARTER && this.high < THREE_QUARTER) {
        this.low -= QUARTER;
        this.high -= QUARTER;
        this.value -= QUARTER;
      } else {
        break;
      }
      this.low = (this.low << 1n) & MASK;
      this.high = ((this.high << 1n) | 1n) & MASK;
      this.value = ((this.value << 1n) | BigInt(this._readBit())) & MASK;
    }

    return sym;
  }
}

// ═══ Compress / Decompress ═══

function compress(text, model) {
  if (!text) return new Uint8Array([0, 0]);

  // Find extra chars
  const extraChars = [...new Set([...text].filter(ch => !model.vocabSet.has(ch)))].sort();
  for (const ch of extraChars) model.ensureChar(ch);

  const encoder = new ArithmeticEncoder();
  let context = BOS.repeat(model.order);

  for (const ch of text) {
    const cdf = model.getCDF(context);
    let found = false;
    for (const [sym, cumLow, cumHigh] of cdf) {
      if (sym === ch) {
        encoder.encodeSymbol(cumLow, cumHigh, CDF_SCALE);
        found = true;
        break;
      }
    }
    if (!found) throw new Error(`Char '${ch}' not in vocab`);
    context = (context + ch).slice(-model.order);
  }

  // Encode EOF
  const cdf = model.getCDF(context);
  for (const [sym, cumLow, cumHigh] of cdf) {
    if (sym === EOF) {
      encoder.encodeSymbol(cumLow, cumHigh, CDF_SCALE);
      break;
    }
  }

  const acBytes = encoder.finish();

  // Build header: [uint16 textLen BE] [uint8 nExtra] [extra chars utf8]
  const textLen = [...text].length;
  const header = [textLen >> 8, textLen & 0xFF, extraChars.length];
  for (const ch of extraChars) {
    const encoded = new TextEncoder().encode(ch);
    header.push(encoded.length);
    for (const b of encoded) header.push(b);
  }

  const result = new Uint8Array(header.length + acBytes.length);
  result.set(header);
  result.set(acBytes, header.length);
  return result;
}

function decompress(data, model) {
  if (data.length < 3) throw new Error('Data too short');

  const textLen = (data[0] << 8) | data[1];
  if (textLen === 0) return '';

  const nExtra = data[2];
  let offset = 3;

  for (let i = 0; i < nExtra; i++) {
    const chLen = data[offset]; offset++;
    const chBytes = data.slice(offset, offset + chLen);
    const ch = new TextDecoder().decode(chBytes);
    offset += chLen;
    model.ensureChar(ch);
  }

  const acData = data.slice(offset);
  if (!acData.length) throw new Error('No AC data');

  const decoder = new ArithmeticDecoder(acData);
  let context = BOS.repeat(model.order);
  const result = [];

  for (let i = 0; i < textLen + 1; i++) {
    const cdf = model.getCDF(context);
    const ch = decoder.decodeSymbol(cdf);
    if (ch === EOF) break;
    result.push(ch);
    context = (context + ch).slice(-model.order);
  }

  return result.join('');
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
