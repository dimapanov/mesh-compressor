#!/usr/bin/env python3
"""
mqtt_collector.py — Collect real Meshtastic text messages from the public MQTT server.

Subscribes to mqtt.meshtastic.org, decrypts packets with the default key,
extracts text messages, detects language, and saves to data/mqtt/{lang}.jsonl.

Usage:
    python3 mqtt_collector.py                    # Run collector (Ctrl+C to stop)
    python3 mqtt_collector.py --stats            # Show collection stats
    python3 mqtt_collector.py --export           # Export to train/test files
    python3 mqtt_collector.py --export --min 100 # Export langs with ≥100 messages

Requirements:
    pip install paho-mqtt meshtastic cryptography
"""

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from meshtastic.protobuf import mesh_pb2, mqtt_pb2, portnums_pb2

# ── Config ──────────────────────────────────────────────────
BROKER = "mqtt.meshtastic.org"
PORT = 1883
USERNAME = "meshdev"
PASSWORD = "large4cats"
TOPIC = "msh/+/2/e/LongFast/#"  # All regions, default channel
DEFAULT_KEY = b"\x01" + b"\x00" * 15  # AQ== padded to 16 bytes

DATA_DIR = Path(__file__).parent / "data" / "mqtt"
DEDUP_WINDOW = 3600  # seconds — ignore duplicate texts within this window

# ── Language detection ──────────────────────────────────────
# Region code → likely languages (for fallback when script detection is ambiguous)
REGION_HINTS = {
    "US": "en",
    "EU_868": "multi_eu",
    "EU_433": "multi_eu",
    "CN": "zh",
    "JP": "ja",
    "KR": "ko",
    "RU": "ru",
    "IN": "hi",
    "TH": "th",
    "TW": "zh",
    "ANZ": "en",
    "UA_868": "uk",
    "MY_433": "ms",
    "MY_919": "ms",
    "SG_923": "en",
    "PH": "en",
    "NZ_865": "en",
}


def detect_script(text):
    """Detect dominant Unicode script in text."""
    scripts = Counter()
    for ch in text:
        if ch.isspace() or ch in ".,!?;:-()[]{}\"'/@#$%^&*+=~`|<>0123456789":
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("L"):  # Letter
            name = (
                unicodedata.name(ch, "").split()[0] if unicodedata.name(ch, "") else ""
            )
            if "CJK" in name or "IDEOGRAPH" in name:
                scripts["CJK"] += 1
            elif "HIRAGANA" in name or "KATAKANA" in name:
                scripts["JA"] += 1
            elif "HANGUL" in name:
                scripts["KO"] += 1
            elif "ARABIC" in name:
                scripts["AR"] += 1
            elif "DEVANAGARI" in name:
                scripts["HI"] += 1
            elif "THAI" in name:
                scripts["TH"] += 1
            elif "CYRILLIC" in name:
                scripts["CYRILLIC"] += 1
            elif "LATIN" in name:
                scripts["LATIN"] += 1
            else:
                # Try Unicode block
                cp = ord(ch)
                if 0x0400 <= cp <= 0x04FF:
                    scripts["CYRILLIC"] += 1
                elif 0x0600 <= cp <= 0x06FF:
                    scripts["AR"] += 1
                elif 0x0900 <= cp <= 0x097F:
                    scripts["HI"] += 1
                elif 0x0E00 <= cp <= 0x0E7F:
                    scripts["TH"] += 1
                elif 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
                    scripts["JA"] += 1
                elif 0xAC00 <= cp <= 0xD7AF:
                    scripts["KO"] += 1
                elif 0x4E00 <= cp <= 0x9FFF:
                    scripts["CJK"] += 1
                else:
                    scripts["LATIN"] += 1

    return scripts


def detect_language(text, region=None):
    """Detect language from text content + region hint."""
    scripts = detect_script(text)
    if not scripts:
        return "unknown"

    dominant = scripts.most_common(1)[0][0]
    total = sum(scripts.values())

    # Unambiguous scripts
    if dominant == "CJK" and scripts["CJK"] / total > 0.3:
        return "zh"
    if (
        dominant == "JA"
        or (scripts.get("JA", 0) + scripts.get("CJK", 0)) / total > 0.3
        and scripts.get("JA", 0) > 0
    ):
        return "ja"
    if dominant == "KO" and scripts["KO"] / total > 0.3:
        return "ko"
    if dominant == "AR" and scripts["AR"] / total > 0.3:
        return "ar"
    if dominant == "HI" and scripts["HI"] / total > 0.3:
        return "hi"
    if dominant == "TH" and scripts["TH"] / total > 0.3:
        return "th"

    # Cyrillic → ru or uk
    if dominant == "CYRILLIC" and scripts["CYRILLIC"] / total > 0.3:
        if region and "UA" in region:
            return "uk"
        return "ru"

    # Latin — need region hint or heuristics
    if dominant == "LATIN":
        if region:
            hint = REGION_HINTS.get(region, "")
            if hint and hint != "multi_eu":
                return hint

        # Simple heuristics based on common words
        lower = text.lower()
        if any(
            w in lower
            for w in [" the ", " is ", " are ", " you ", " and ", " this ", " that "]
        ):
            return "en"
        if any(
            w in lower
            for w in [" der ", " die ", " das ", " und ", " ist ", " ein ", " ich "]
        ):
            return "de"
        if any(
            w in lower
            for w in [" est ", " les ", " des ", " une ", " dans ", " pour ", " que "]
        ):
            return "fr"
        if any(
            w in lower
            for w in [" los ", " las ", " una ", " que ", " por ", " con ", " para "]
        ):
            return "es"
        if any(
            w in lower for w in [" os ", " uma ", " com ", " para ", " que ", " não "]
        ):
            return "pt"
        if any(w in lower for w in [" bir ", " ve ", " bu ", " ile ", " için "]):
            return "tr"
        if any(w in lower for w in [" dan ", " yang ", " ini ", " untuk ", " dari "]):
            return "id"

        # Default Latin to en
        return "en"

    return "unknown"


# ── Message filtering ───────────────────────────────────────


def is_valid_message(text):
    """Filter out noise, system messages, and junk."""
    if not text or len(text.strip()) < 2:
        return False
    text = text.strip()

    # Too short or too long
    if len(text) < 2 or len(text) > 500:
        return False

    # System / bot messages
    if text.startswith(("seq ", "BAT:", "SNR:", "RSSI:", "pos:", "GPS:")):
        return False

    # Mostly non-printable or control chars
    printable = sum(1 for c in text if c.isprintable() or c.isspace())
    if printable / len(text) < 0.7:
        return False

    # Mostly digits / hex (telemetry, IDs)
    alpha = sum(1 for c in text if c.isalpha())
    if alpha < 2 and len(text) > 3:
        return False

    return True


# ── Crypto ──────────────────────────────────────────────────


def decrypt_packet(encrypted_bytes, packet_id, from_node, key=DEFAULT_KEY):
    """Decrypt a MeshPacket's encrypted payload."""
    nonce = struct.pack("<II", packet_id, from_node) + b"\x00" * 8
    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce))
    decryptor = cipher.decryptor()
    return decryptor.update(encrypted_bytes) + decryptor.finalize()


def parse_region(topic):
    """Extract region code from MQTT topic."""
    # msh/{REGION}/2/e/{CHANNEL}/{GATEWAY}
    parts = topic.split("/")
    if len(parts) >= 2:
        return parts[1]
    return "unknown"


# ── Storage ─────────────────────────────────────────────────


class MessageStore:
    """Append-only JSONL storage with deduplication."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.seen = {}  # text_hash → timestamp (for dedup)
        self.counts = Counter()
        self._load_counts()

    def _load_counts(self):
        for f in self.data_dir.glob("*.jsonl"):
            lang = f.stem
            with open(f) as fh:
                self.counts[lang] = sum(1 for _ in fh)

    def add(self, text, lang, region, from_node, timestamp):
        """Add a message. Returns True if stored, False if duplicate."""
        text = text.strip()
        h = hashlib.md5(text.encode()).hexdigest()

        now = time.time()
        if h in self.seen and (now - self.seen[h]) < DEDUP_WINDOW:
            return False
        self.seen[h] = now

        # Prune old dedup entries
        if len(self.seen) > 100000:
            cutoff = now - DEDUP_WINDOW
            self.seen = {k: v for k, v in self.seen.items() if v > cutoff}

        filepath = self.data_dir / f"{lang}.jsonl"
        record = {
            "text": text,
            "lang": lang,
            "region": region,
            "from": f"!{from_node:08x}",
            "ts": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
        }
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self.counts[lang] += 1
        return True


# ── MQTT callbacks ──────────────────────────────────────────


class MeshtasticCollector:
    def __init__(self):
        self.store = MessageStore(DATA_DIR)
        self.stats = {
            "connected": False,
            "packets_total": 0,
            "packets_encrypted": 0,
            "decrypt_ok": 0,
            "decrypt_fail": 0,
            "text_messages": 0,
            "stored": 0,
            "filtered": 0,
            "duplicates": 0,
            "start_time": time.time(),
        }

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        print(f"[{self._ts()}] Connected to {BROKER} (rc={reason_code})")
        client.subscribe(TOPIC)
        # Also subscribe to other common channels
        client.subscribe("msh/+/2/e/MediumSlow/#")
        client.subscribe("msh/+/2/e/ShortFast/#")
        print(
            f"[{self._ts()}] Subscribed to LongFast + MediumSlow + ShortFast, all regions"
        )
        self.stats["connected"] = True

    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        print(f"[{self._ts()}] Disconnected (rc={reason_code}), reconnecting...")
        self.stats["connected"] = False

    def on_message(self, client, userdata, msg):
        self.stats["packets_total"] += 1
        try:
            self._process_message(msg)
        except Exception as e:
            pass  # Silent — noisy packets are common

    def _process_message(self, msg):
        # Parse ServiceEnvelope
        envelope = mqtt_pb2.ServiceEnvelope()
        envelope.ParseFromString(msg.payload)

        packet = envelope.packet
        if not packet.encrypted:
            return

        self.stats["packets_encrypted"] += 1
        region = parse_region(msg.topic)

        # Decrypt
        try:
            decrypted = decrypt_packet(
                bytes(packet.encrypted),
                packet.id,
                getattr(packet, "from"),
            )
        except Exception:
            self.stats["decrypt_fail"] += 1
            return

        # Parse Data
        try:
            data = mesh_pb2.Data()
            data.ParseFromString(decrypted)
        except Exception:
            self.stats["decrypt_fail"] += 1
            return

        self.stats["decrypt_ok"] += 1

        # Only text messages
        if data.portnum != portnums_pb2.TEXT_MESSAGE_APP:
            return

        self.stats["text_messages"] += 1

        # Decode text
        try:
            text = data.payload.decode("utf-8")
        except UnicodeDecodeError:
            return

        # Filter
        if not is_valid_message(text):
            self.stats["filtered"] += 1
            return

        # Detect language
        lang = detect_language(text, region)

        # Store
        ts = packet.rx_time if packet.rx_time else int(time.time())
        stored = self.store.add(text, lang, region, getattr(packet, "from"), ts)

        if stored:
            self.stats["stored"] += 1
            total = sum(self.store.counts.values())
            # Print every message with running stats
            preview = text[:60].replace("\n", " ")
            counts_str = " ".join(
                f"{k}:{v}" for k, v in sorted(self.store.counts.items())
            )
            print(
                f'[{self._ts()}] [{region}] [{lang}] "{preview}"  | total: {total} | {counts_str}'
            )
        else:
            self.stats["duplicates"] += 1

    def _ts(self):
        return datetime.now().strftime("%H:%M:%S")

    def print_stats(self):
        s = self.stats
        elapsed = time.time() - s["start_time"]
        h, m = divmod(int(elapsed), 3600)
        m, sec = divmod(m, 60)

        print(f"\n{'=' * 60}")
        print(f"Collection stats ({h}h {m}m {sec}s)")
        print(f"{'=' * 60}")
        print(f"Packets received:    {s['packets_total']}")
        print(f"Encrypted:           {s['packets_encrypted']}")
        print(f"Decrypted OK:        {s['decrypt_ok']}")
        print(f"Decrypt failed:      {s['decrypt_fail']}")
        print(f"Text messages:       {s['text_messages']}")
        print(f"Filtered (noise):    {s['filtered']}")
        print(f"Duplicates:          {s['duplicates']}")
        print(f"Stored:              {s['stored']}")
        print(f"\nPer language:")
        for lang, count in sorted(self.store.counts.items(), key=lambda x: -x[1]):
            print(f"  {lang:>8}: {count:>6}")
        print(f"{'=' * 60}\n")


# ── Export to train/test ────────────────────────────────────


def export_datasets(min_messages=50):
    """Export collected MQTT messages to train/test split files."""
    import random

    random.seed(42)

    data_dir = DATA_DIR
    out_dir = Path(__file__).parent / "data" / "multilingual"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting from {data_dir} to {out_dir}")
    print(f"Minimum messages per language: {min_messages}\n")

    for f in sorted(data_dir.glob("*.jsonl")):
        lang = f.stem
        if lang == "unknown":
            continue

        messages = []
        with open(f) as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    text = rec["text"].strip()
                    if text and len(text) >= 2:
                        messages.append(text)
                except (json.JSONDecodeError, KeyError):
                    continue

        # Deduplicate
        messages = list(dict.fromkeys(messages))

        if len(messages) < min_messages:
            print(f"  {lang}: {len(messages)} messages (skipped, < {min_messages})")
            continue

        random.shuffle(messages)

        # 90/10 train/test split
        split = max(1, int(len(messages) * 0.9))
        train = messages[:split]
        test = messages[split:]

        train_file = out_dir / f"train_{lang}.txt"
        test_file = out_dir / f"test_{lang}.txt"

        train_file.write_text("\n".join(train) + "\n", encoding="utf-8")
        test_file.write_text("\n".join(test) + "\n", encoding="utf-8")

        print(f"  {lang}: {len(messages)} unique → train={len(train)} test={len(test)}")

    print("\nDone!")


def show_stats():
    """Show current collection statistics."""
    data_dir = DATA_DIR
    if not data_dir.exists():
        print("No data collected yet. Run: python3 mqtt_collector.py")
        return

    total = 0
    print(f"\n{'Language':<10} {'Messages':>10} {'Unique':>10} {'File':>20}")
    print("-" * 55)

    for f in sorted(data_dir.glob("*.jsonl")):
        lang = f.stem
        count = 0
        unique = set()
        with open(f) as fh:
            for line in fh:
                count += 1
                try:
                    rec = json.loads(line)
                    unique.add(rec["text"])
                except:
                    pass
        total += count
        print(f"{lang:<10} {count:>10} {len(unique):>10} {f.name:>20}")

    print("-" * 55)
    print(f"{'TOTAL':<10} {total:>10}")
    print()


# ── Main ────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Collect Meshtastic text messages from MQTT"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show collection statistics"
    )
    parser.add_argument(
        "--export", action="store_true", help="Export to train/test files"
    )
    parser.add_argument(
        "--min",
        type=int,
        default=50,
        help="Min messages per lang for export (default: 50)",
    )
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if args.export:
        export_datasets(args.min)
        return

    # Run collector
    collector = MeshtasticCollector()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(USERNAME, PASSWORD)
    client.on_connect = collector.on_connect
    client.on_disconnect = collector.on_disconnect
    client.on_message = collector.on_message

    print(f"Connecting to {BROKER}:{PORT}...")
    print(f"Data will be saved to {DATA_DIR}/")
    print(f"Press Ctrl+C to stop\n")

    client.connect(BROKER, PORT, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n\nStopping...")
        collector.print_stats()
        client.disconnect()


if __name__ == "__main__":
    main()
