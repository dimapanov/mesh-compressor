"""
FastAPI сервер для n-gram + Arithmetic Coding тестера.

Загружает обучающие данные и тренирует модель при старте,
затем предоставляет API для кодирования/декодирования + веб-интерфейс.
"""

import sys
import time
import pickle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.compress import train_model, compress, decompress

# Base91 для текстового транспорта через Meshtastic TEXT_MESSAGE_APP
from src.base91 import encode as b91_encode, decode as b91_decode

# Meshtastic max payload size (bytes)
MESHTASTIC_MAX_PAYLOAD = 233

app = FastAPI(title="n-gram + AC Tester")

# ─── Load or train model on startup ───────────────────────────
TRAIN_PATH = Path(__file__).parent / "data" / "train.txt"
CACHE_PATH = Path(__file__).parent / "model.pkl"

if CACHE_PATH.exists():
    print(f"Loading cached model from {CACHE_PATH}...")
    t0 = time.time()
    with open(CACHE_PATH, "rb") as f:
        model = pickle.load(f)
    print(f"  Loaded in {time.time() - t0:.1f}s, vocab={len(model.vocab)} chars")
else:
    print("Loading training data...")
    t0 = time.time()
    with open(TRAIN_PATH, "r", encoding="utf-8") as f:
        messages = [line.strip() for line in f if line.strip()]
    print(f"  Loaded {len(messages)} lines in {time.time() - t0:.1f}s")

    print("Training model (this takes ~3-5 seconds)...")
    t0 = time.time()
    model = train_model(messages)
    print(f"  Trained in {time.time() - t0:.1f}s, vocab={len(model.vocab)} chars")

    print(f"Saving model cache to {CACHE_PATH}...")
    t0 = time.time()
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(model, f)
    print(
        f"  Saved in {time.time() - t0:.1f}s ({CACHE_PATH.stat().st_size / 1024 / 1024:.1f} MB)"
    )


class EncodeRequest(BaseModel):
    text: str


class DecodeRequest(BaseModel):
    hex: str


@app.post("/api/encode")
def api_encode(req: EncodeRequest):
    text = req.text
    if not text:
        return {
            "original_chars": 0,
            "original_utf8_bytes": 0,
            "compressed_bytes": 0,
            "compressed_hex": "",
            "compression_pct": 0,
            "bits_per_char": 0,
            "fits_in_payload": True,
            "meshtastic_max": MESHTASTIC_MAX_PAYLOAD,
        }

    utf8_bytes = text.encode("utf-8")
    orig_len = len(utf8_bytes)

    # n-gram + AC
    try:
        t0 = time.time()
        compressed = compress(text, model)
        encode_time = time.time() - t0
        comp_len = len(compressed)
        ratio = (1 - comp_len / orig_len) * 100
        bpc = (comp_len * 8) / len(text)

        # Verify roundtrip
        decoded = decompress(compressed, model)
        roundtrip_ok = decoded == text
    except Exception as e:
        return {"error": str(e)}

    # Base91 encoding for text transport (Meshtastic TEXT_MESSAGE_APP)
    b91 = "~" + b91_encode(compressed)  # ~ prefix marks compressed message
    b91_len = len(b91)
    b91_ratio = (1 - b91_len / orig_len) * 100

    return {
        "original_chars": len(text),
        "original_utf8_bytes": orig_len,
        # n-gram + AC
        "compressed_bytes": comp_len,
        "compressed_hex": compressed.hex(),
        "compression_pct": round(ratio, 1),
        "bits_per_char": round(bpc, 2),
        "fits_in_payload": comp_len <= MESHTASTIC_MAX_PAYLOAD,
        "meshtastic_max": MESHTASTIC_MAX_PAYLOAD,
        "encode_time_ms": round(encode_time * 1000, 1),
        "roundtrip_ok": roundtrip_ok,
        # Base91 text transport
        "base91": b91,
        "base91_len": b91_len,
        "base91_ratio": round(b91_ratio, 1),
        "fits_base91": b91_len <= MESHTASTIC_MAX_PAYLOAD,
        # Capacity estimates
        "max_chars_ngram": int(MESHTASTIC_MAX_PAYLOAD / (comp_len / len(text)))
        if comp_len > 0
        else 0,
        "max_chars_raw": MESHTASTIC_MAX_PAYLOAD // 2,
        "max_chars_b91": int(MESHTASTIC_MAX_PAYLOAD / (b91_len / len(text)))
        if b91_len > 0
        else 0,
    }


@app.post("/api/decode")
def api_decode(req: DecodeRequest):
    try:
        data = bytes.fromhex(req.hex)
        t0 = time.time()
        decoded = decompress(data, model)
        decode_time = time.time() - t0
        return {
            "decoded_text": decoded,
            "decode_time_ms": round(decode_time * 1000, 1),
            "error": None,
        }
    except Exception as e:
        return {"decoded_text": "", "error": str(e)}


class B91DecodeRequest(BaseModel):
    text: str


@app.post("/api/decode_b91")
def api_decode_b91(req: B91DecodeRequest):
    """Decode a ~base91 encoded compressed message back to text."""
    try:
        text = req.text.strip()
        if not text.startswith("~"):
            return {"decoded_text": "", "error": "Message must start with ~ prefix"}
        b91_str = text[1:]  # strip ~ prefix
        compressed = b91_decode(b91_str)
        t0 = time.time()
        decoded = decompress(compressed, model)
        decode_time = time.time() - t0
        return {
            "decoded_text": decoded,
            "decode_time_ms": round(decode_time * 1000, 1),
            "error": None,
        }
    except Exception as e:
        return {"decoded_text": "", "error": str(e)}


@app.get("/", response_class=HTMLResponse)
def index():
    html_path = Path(__file__).parent / "docs" / "index.html"
    return html_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8766)
