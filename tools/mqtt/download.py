#!/usr/bin/env python3
"""
mqtt_download.py — Download historical Meshtastic text messages from meshtastic.liamcottle.net API.

Usage:
    python3 mqtt_download.py                    # Download all available messages
    python3 mqtt_download.py --stats            # Show download stats
    python3 mqtt_download.py --export           # Export to train/test files
    python3 mqtt_download.py --export --min 200 # Export langs with ≥200 unique messages
"""

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

API_BASE = "https://meshtastic.liamcottle.net/api/v1/text-messages"
BATCH_SIZE = 500  # max count per request
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "mqtt"
RAW_FILE = DATA_DIR / "_raw_messages.jsonl"


# ── Language detection (same as mqtt_collector.py) ──────────


def detect_language(text):
    """Simple script-based + keyword language detection."""
    scripts = Counter()
    for ch in text:
        if not ch.isalpha():
            continue
        cp = ord(ch)
        if 0x0400 <= cp <= 0x04FF:
            scripts["CYRILLIC"] += 1
        elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            scripts["CJK"] += 1
        elif 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
            scripts["JA"] += 1
        elif 0xAC00 <= cp <= 0xD7AF:
            scripts["KO"] += 1
        elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
            scripts["AR"] += 1
        elif 0x0900 <= cp <= 0x097F:
            scripts["HI"] += 1
        elif 0x0E00 <= cp <= 0x0E7F:
            scripts["TH"] += 1
        elif cp < 0x0250:  # Basic Latin + Latin Extended
            scripts["LATIN"] += 1

    if not scripts:
        return "unknown"

    total = sum(scripts.values())
    dominant, count = scripts.most_common(1)[0]

    if dominant == "CJK" and count / total > 0.3:
        return "zh"
    if dominant == "JA" or (
        scripts.get("JA", 0) > 0
        and (scripts.get("JA", 0) + scripts.get("CJK", 0)) / total > 0.3
    ):
        return "ja"
    if dominant == "KO" and count / total > 0.3:
        return "ko"
    if dominant == "AR" and count / total > 0.3:
        return "ar"
    if dominant == "HI" and count / total > 0.3:
        return "hi"
    if dominant == "TH" and count / total > 0.3:
        return "th"
    if dominant == "CYRILLIC" and count / total > 0.3:
        return "ru"

    if dominant == "LATIN":
        lower = text.lower()
        if re.search(
            r"\b(the|is|are|you|and|this|that|have|for|not|with|but)\b", lower
        ):
            return "en"
        if re.search(r"\b(der|die|das|und|ist|ein|ich|nicht|auch|noch)\b", lower):
            return "de"
        if re.search(r"\b(est|les|des|une|dans|pour|pas|qui|sur|avec)\b", lower):
            return "fr"
        if re.search(r"\b(los|las|una|que|por|con|para|del|más|como)\b", lower):
            return "es"
        if re.search(r"\b(os|uma|com|para|não|mais|por|como|dos|das)\b", lower):
            return "pt"
        if re.search(r"\b(bir|ve|bu|ile|için|olan|var|gibi|ben|sen)\b", lower):
            return "tr"
        if re.search(r"\b(en|ett|och|det|att|som|med|har|kan|inte)\b", lower):
            return "sv"
        if re.search(r"\b(en|og|det|er|at|til|med|som|har|kan)\b", lower):
            return "no"
        if re.search(r"\b(i|nie|się|na|to|jest|co|tak|ale|jak)\b", lower):
            return "pl"
        if re.search(r"\b(dan|yang|ini|untuk|dari|ada|akan|tidak|bisa)\b", lower):
            return "id"
        if re.search(r"\b(en|het|van|een|dat|met|niet|ook|zijn|maar)\b", lower):
            return "nl"
        return "en"  # default Latin

    return "unknown"


def is_valid_message(text):
    """Filter noise, bot messages, telemetry."""
    if not text or len(text.strip()) < 2 or len(text) > 500:
        return False
    text = text.strip()

    # Bot / system patterns
    if re.match(
        r"^(Pong to|seq |BAT:|SNR:|RSSI:|pos:|GPS:|Ping$|CQ CQ|test$)", text, re.I
    ):
        return False
    # Weather bot responses
    if re.match(r"^За окном:|^Погода$|^Weather:", text):
        return False
    # Mostly numbers / hex
    alpha = sum(1 for c in text if c.isalpha())
    if alpha < 2 and len(text) > 3:
        return False
    # Non-printable junk
    printable = sum(1 for c in text if c.isprintable() or c.isspace())
    if printable / len(text) < 0.7:
        return False
    return True


# ── Download ────────────────────────────────────────────────


def fetch_batch(last_id=None, order="asc", count=BATCH_SIZE):
    """Fetch a batch of messages from the API."""
    url = f"{API_BASE}?count={count}&order={order}"
    if last_id is not None:
        url += f"&last_id={last_id}"

    req = Request(url, headers={"User-Agent": "MeshtasticCompressor/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("text_messages", [])
    except (URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  Error fetching: {e}")
        return None


def download_all():
    """Download all available text messages."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Resume from where we left off
    last_id = None
    if RAW_FILE.exists():
        # Find the last downloaded ID
        with open(RAW_FILE, "rb") as f:
            # Read last non-empty line
            f.seek(0, 2)
            size = f.tell()
            if size > 0:
                f.seek(max(0, size - 2048))
                lines = f.read().decode("utf-8", errors="ignore").strip().split("\n")
                for line in reversed(lines):
                    if line.strip():
                        try:
                            rec = json.loads(line)
                            last_id = int(rec["id"])
                            break
                        except:
                            pass
        if last_id:
            print(f"Resuming from id={last_id}")

    total = 0
    retries = 0

    with open(RAW_FILE, "a", encoding="utf-8") as f:
        while True:
            msgs = fetch_batch(last_id=last_id, order="asc", count=BATCH_SIZE)
            if msgs is None:
                retries += 1
                if retries > 5:
                    print("Too many errors, stopping")
                    break
                time.sleep(5)
                continue

            retries = 0
            if not msgs:
                print(f"\nDone! No more messages. Total downloaded: {total}")
                break

            for m in msgs:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

            total += len(msgs)
            last_id = int(msgs[-1]["id"])
            first_date = msgs[0].get("created_at", "?")[:19]
            last_date = msgs[-1].get("created_at", "?")[:19]

            print(
                f"  Batch: {len(msgs)} msgs (id {msgs[0]['id']}..{msgs[-1]['id']}) "
                f"{first_date}..{last_date}  total: {total}",
                flush=True,
            )

            # Polite rate limiting
            time.sleep(0.5)

    print(f"\nRaw data saved to {RAW_FILE}")


# ── Process & Export ────────────────────────────────────────


def process_and_export(min_messages=200):
    """Process raw messages, detect languages, deduplicate, export train/test."""
    import random

    random.seed(42)

    if not RAW_FILE.exists():
        print(f"No raw data. Run: python3 mqtt_download.py")
        return

    print(f"Processing {RAW_FILE}...")

    # Read and deduplicate by packet_id
    seen_packets = set()
    seen_texts = set()
    lang_messages = {}  # lang -> [text, ...]

    total = 0
    dupes = 0
    filtered = 0

    with open(RAW_FILE, encoding="utf-8") as f:
        for line in f:
            total += 1
            try:
                rec = json.loads(line)
                text = rec["text"].strip()
                packet_id = rec.get("packet_id", "")

                # Dedup by packet_id (same message from multiple gateways)
                if packet_id and packet_id in seen_packets:
                    dupes += 1
                    continue
                if packet_id:
                    seen_packets.add(packet_id)

                # Dedup by exact text
                text_hash = hashlib.md5(text.encode()).hexdigest()
                if text_hash in seen_texts:
                    dupes += 1
                    continue
                seen_texts.add(text_hash)

                # Filter noise
                if not is_valid_message(text):
                    filtered += 1
                    continue

                # Detect language
                lang = detect_language(text)
                if lang == "unknown":
                    filtered += 1
                    continue

                if lang not in lang_messages:
                    lang_messages[lang] = []
                lang_messages[lang].append(text)

            except (json.JSONDecodeError, KeyError):
                continue

    print(f"\nProcessed: {total} raw, {dupes} dupes, {filtered} filtered")
    print(f"\nLanguages found:")
    for lang, msgs in sorted(lang_messages.items(), key=lambda x: -len(x[1])):
        print(f"  {lang:>5}: {len(msgs):>6} unique messages")

    # Export
    out_dir = Path(__file__).parent.parent.parent / "data" / "mqtt_export"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nExporting to {out_dir}/ (min {min_messages} per lang):")

    for lang, msgs in sorted(lang_messages.items(), key=lambda x: -len(x[1])):
        if len(msgs) < min_messages:
            print(f"  {lang:>5}: {len(msgs):>6} (skipped, < {min_messages})")
            continue

        random.shuffle(msgs)
        split = max(10, int(len(msgs) * 0.9))
        train = msgs[:split]
        test = msgs[split:]

        (out_dir / f"train_{lang}.txt").write_text(
            "\n".join(train) + "\n", encoding="utf-8"
        )
        (out_dir / f"test_{lang}.txt").write_text(
            "\n".join(test) + "\n", encoding="utf-8"
        )
        print(f"  {lang:>5}: {len(msgs):>6} → train={len(train)}, test={len(test)}")

    print("\nDone!")


def show_stats():
    """Show raw download stats."""
    if not RAW_FILE.exists():
        print("No data. Run: python3 mqtt_download.py")
        return

    total = 0
    first_date = last_date = first_id = last_id = None
    with open(RAW_FILE) as f:
        for line in f:
            total += 1
            try:
                rec = json.loads(line)
                if first_id is None:
                    first_id = rec["id"]
                    first_date = rec.get("created_at", "?")[:19]
                last_id = rec["id"]
                last_date = rec.get("created_at", "?")[:19]
            except:
                pass

    size_mb = RAW_FILE.stat().st_size / 1024 / 1024
    print(f"\nRaw data: {RAW_FILE}")
    print(f"  Records:    {total:,}")
    print(f"  Size:       {size_mb:.1f} MB")
    print(f"  ID range:   {first_id} .. {last_id}")
    print(f"  Date range: {first_date} .. {last_date}")
    print()


# ── Main ────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Download Meshtastic text messages")
    parser.add_argument("--stats", action="store_true", help="Show download stats")
    parser.add_argument(
        "--export", action="store_true", help="Process & export to train/test"
    )
    parser.add_argument(
        "--min", type=int, default=200, help="Min unique messages per lang for export"
    )
    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.export:
        process_and_export(args.min)
    else:
        download_all()


if __name__ == "__main__":
    main()
