#!/usr/bin/env python3
"""Generate all charts for README. Run from project root: python3 autoresearch/gen_charts.py"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

OUT_DIR = "docs/img"
DPI = 180

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "--",
    }
)


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(
        f"{OUT_DIR}/{name}.png",
        dpi=DPI,
        bbox_inches="tight",
        facecolor="white",
        edgecolor="none",
    )
    fig.savefig(
        f"{OUT_DIR}/{name}.svg",
        bbox_inches="tight",
        facecolor="white",
        edgecolor="none",
    )
    plt.close(fig)
    print(f"  ✓ {name}.png/svg")


# ════════════════════════════════════════════════════════════
# 1. OPTIMIZATION TIMELINE
# ════════════════════════════════════════════════════════════
def fig_optimization_timeline():
    steps = [
        ("Baseline\norder=11, cubic", 3.220, "#5B8DEE"),
        ("Confidence\npenalty (n+3)", 3.212, "#5B8DEE"),
        ("ESC_PROB\n20K → 500", 3.211, "#5B8DEE"),
        ("SCRIPT_BOOST\n30 → 5", 3.210, "#F4A942"),
        ("CJK 3× weight\n+ conf n+8", 3.210, "#F4A942"),
        ("Passthrough\n(zero overhead)", 3.207, "#4CAF50"),
        ("Compact header\n3B → 2B", 2.980, "#4CAF50"),
        ("Conf n+1.5\n+ MQTT data", 2.970, "#4CAF50"),
    ]

    labels = [s[0] for s in steps]
    bpcs = [s[1] for s in steps]
    colors = [s[2] for s in steps]

    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.axvspan(-0.5, 2.5, alpha=0.06, color="#5B8DEE")
    ax.axvspan(2.5, 4.5, alpha=0.06, color="#F4A942")
    ax.axvspan(4.5, 7.5, alpha=0.06, color="#4CAF50")

    ax.text(
        1.0,
        3.24,
        "Model tuning",
        ha="center",
        fontsize=9,
        color="#5B8DEE",
        fontweight="bold",
        alpha=0.8,
    )
    ax.text(
        3.5,
        3.24,
        "Multilingual",
        ha="center",
        fontsize=9,
        color="#F4A942",
        fontweight="bold",
        alpha=0.8,
    )
    ax.text(
        6.0,
        3.24,
        "Format + data",
        ha="center",
        fontsize=9,
        color="#4CAF50",
        fontweight="bold",
        alpha=0.8,
    )

    ax.plot(range(len(bpcs)), bpcs, color="#333", lw=1.5, alpha=0.4, zorder=2)
    for i, (_, bpc, c) in enumerate(steps):
        ax.scatter(i, bpc, color=c, s=120, zorder=3, edgecolors="white", linewidth=1.5)

    for i, bpc in enumerate(bpcs):
        above = i != 6
        ax.annotate(
            f"{bpc:.3f}",
            (i, bpc),
            textcoords="offset points",
            xytext=(0, 8 if above else -12),
            ha="center",
            va="bottom" if above else "top",
            fontsize=9,
            fontweight="bold",
            color="#333",
        )

    ax.annotate(
        "",
        xy=(6, 2.980),
        xytext=(5, 3.207),
        arrowprops=dict(
            arrowstyle="->", color="#4CAF50", lw=2.5, connectionstyle="arc3,rad=-0.2"
        ),
    )
    ax.text(
        5.8,
        3.10,
        "−7.1%",
        fontsize=11,
        fontweight="bold",
        color="#4CAF50",
        ha="center",
        rotation=-50,
    )

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Bits per character (BPC)", fontsize=11)
    ax.set_title(
        "Compression optimization progress — RU+EN test set (lower = better)",
        fontsize=13,
        fontweight="bold",
        pad=15,
    )
    ax.set_ylim(2.90, 3.26)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.05))
    _save(fig, "optimization-progress")


# ════════════════════════════════════════════════════════════
# 2. COMPRESSION BY LANGUAGE — real vs synthetic test data
# ════════════════════════════════════════════════════════════
def fig_compression_by_language():
    # Honest eval_all numbers
    # Real MQTT test data
    real_langs = ["RU", "EN", "NO", "PL", "DE", "ES", "PT", "FR", "SV"]
    real_ratios = [78.4, 73.2, 64.4, 50.4, 42.5, 44.4, 42.7, 40.7, 39.9]
    # Synthetic test data
    synth_langs = ["AR", "KO", "JA", "ZH"]
    synth_ratios = [82.4, 76.6, 75.7, 73.5]

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(14, 5.5), gridspec_kw={"width_ratios": [9, 4]}
    )

    # Left: real data
    idx_r = np.argsort(real_ratios)[::-1]
    r_sorted = [real_langs[i] for i in idx_r]
    rr_sorted = [real_ratios[i] for i in idx_r]

    colors_r = [
        "#4CAF50" if r >= 60 else "#FFA726" if r >= 45 else "#EF5350" for r in rr_sorted
    ]
    bars = ax1.barh(
        range(len(r_sorted)),
        rr_sorted,
        color=colors_r,
        edgecolor="white",
        lw=0.8,
        height=0.65,
    )
    for i, (lang, r) in enumerate(zip(r_sorted, rr_sorted)):
        ax1.text(
            r + 0.8,
            i,
            f"{r:.0f}%",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="#333",
        )
    ax1.set_yticks(range(len(r_sorted)))
    ax1.set_yticklabels(r_sorted, fontsize=12, fontweight="bold")
    ax1.set_xlabel("Compression ratio (%)", fontsize=11)
    ax1.set_title("Real MQTT messages", fontsize=12, fontweight="bold")
    ax1.set_xlim(0, 95)
    ax1.invert_yaxis()
    ax1.spines["left"].set_visible(False)
    ax1.tick_params(axis="y", length=0)

    # Right: synthetic data
    idx_s = np.argsort(synth_ratios)[::-1]
    s_sorted = [synth_langs[i] for i in idx_s]
    sr_sorted = [synth_ratios[i] for i in idx_s]

    bars2 = ax2.barh(
        range(len(s_sorted)),
        sr_sorted,
        color="#90CAF9",
        edgecolor="white",
        lw=0.8,
        height=0.65,
    )
    for i, (lang, r) in enumerate(zip(s_sorted, sr_sorted)):
        ax2.text(
            r + 0.8,
            i,
            f"{r:.0f}%",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="#333",
        )
    ax2.set_yticks(range(len(s_sorted)))
    ax2.set_yticklabels(s_sorted, fontsize=12, fontweight="bold")
    ax2.set_xlabel("Compression ratio (%)", fontsize=11)
    ax2.set_title("Synthetic test data *", fontsize=12, fontweight="bold", color="#666")
    ax2.set_xlim(0, 95)
    ax2.invert_yaxis()
    ax2.spines["left"].set_visible(False)
    ax2.tick_params(axis="y", length=0)

    fig.suptitle(
        "Compression ratio by language (universal model)",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    _save(fig, "compression-by-language")


# ════════════════════════════════════════════════════════════
# 3. SHORT MESSAGE FIX
# ════════════════════════════════════════════════════════════
def fig_short_message_fix():
    msgs = ["ok", "да", "hi", "Лол", "Мм?", "Ое", "Ккк", "Впн", "нет", "тест", "привет"]
    utf8 = [2, 4, 2, 6, 5, 4, 6, 6, 6, 8, 12]
    comp_old = [6, 6, 7, 7, 7, 7, 7, 8, 6, 5, 5]
    comp_new = [2, 4, 2, 6, 5, 4, 6, 6, 5, 5, 5]

    x = np.arange(len(msgs))
    w = 0.25
    fig, ax = plt.subplots(figsize=(12, 5))

    ax.bar(
        x - w, utf8, w, label="UTF-8 (raw)", color="#90CAF9", edgecolor="white", lw=0.8
    )
    ax.bar(
        x,
        comp_old,
        w,
        label="Before (3B header, no pass)",
        color="#EF9A9A",
        edgecolor="white",
        lw=0.8,
    )
    ax.bar(
        x + w,
        comp_new,
        w,
        label="After (2B header + pass)",
        color="#81C784",
        edgecolor="white",
        lw=0.8,
    )

    for i in range(len(msgs)):
        if comp_old[i] > utf8[i]:
            ax.text(
                x[i],
                comp_old[i] + 0.15,
                f"+{comp_old[i] - utf8[i]}B",
                ha="center",
                va="bottom",
                fontsize=7.5,
                color="#C62828",
                fontweight="bold",
            )

    ax.set_xticks(x)
    ax.set_xticklabels([f'"{m}"' for m in msgs], fontsize=9, rotation=30, ha="right")
    ax.set_ylabel("Output size (bytes)", fontsize=11)
    ax.set_title(
        "Short message compression: negative compression eliminated",
        fontsize=13,
        fontweight="bold",
    )
    ax.legend(fontsize=9.5, loc="upper right")
    ax.set_ylim(0, 10)
    _save(fig, "short-message-fix")


# ════════════════════════════════════════════════════════════
# 4. COMPRESSION COMPARISON — n-gram+AC vs zlib vs Unishox2
# ════════════════════════════════════════════════════════════
def fig_compression_comparison():
    labels = [
        "Привет, как дела?",
        "Check channel 5",
        "Battery 40%,\npower save",
        "Проверка связи.\nКак слышно?",
        "Long EN\n(104 chars)",
        "Long RU\n(229 bytes)",
    ]
    utf8 = [30, 15, 39, 49, 104, 229]
    zlib = [41, 23, 47, 57, 96, 156]
    unishox = [20, 11, 26, 28, 65, 120]
    ngram = [6, 6, 11, 6, 52, 30]

    x = np.arange(len(labels))
    w = 0.20
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.bar(
        x - 1.5 * w, utf8, w, label="UTF-8", color="#BDBDBD", edgecolor="white", lw=0.8
    )
    ax.bar(
        x - 0.5 * w, zlib, w, label="zlib", color="#EF9A9A", edgecolor="white", lw=0.8
    )
    ax.bar(
        x + 0.5 * w,
        unishox,
        w,
        label="Unishox2",
        color="#FFE082",
        edgecolor="white",
        lw=0.8,
    )
    ax.bar(
        x + 1.5 * w,
        ngram,
        w,
        label="n-gram + AC",
        color="#81C784",
        edgecolor="white",
        lw=0.8,
    )

    for i in range(len(labels)):
        pct = (1 - ngram[i] / utf8[i]) * 100
        ax.text(
            x[i] + 1.5 * w,
            ngram[i] + 1,
            f"−{pct:.0f}%",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="#2E7D32",
        )
    for i in range(len(labels)):
        if zlib[i] > utf8[i]:
            ax.text(
                x[i] - 0.5 * w,
                zlib[i] + 1,
                f"+{(zlib[i] / utf8[i] - 1) * 100:.0f}%",
                ha="center",
                va="bottom",
                fontsize=7,
                color="#C62828",
                fontweight="bold",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5, ha="center")
    ax.set_ylabel("Compressed size (bytes)", fontsize=11)
    ax.set_title(
        "Compression comparison: n-gram+AC vs alternatives",
        fontsize=13,
        fontweight="bold",
    )
    ax.legend(fontsize=9.5, loc="upper left")
    ax.set_ylim(0, max(utf8) * 1.15)
    _save(fig, "compression-comparison")


# ════════════════════════════════════════════════════════════
# 5. COMPRESSION BY LENGTH
# ════════════════════════════════════════════════════════════
def fig_compression_by_length():
    buckets = ["1–10", "11–20", "21–50", "51–100", "101–200", "201+"]
    ratios = [26.7, 57.4, 73.7, 80.4, 81.8, 71.8]
    counts = [55, 214, 780, 617, 332, 2]

    fig, ax1 = plt.subplots(figsize=(10, 5.5))
    color_bars = "#5B8DEE"
    color_line = "#F4A942"

    ax1.bar(
        range(len(buckets)),
        ratios,
        color=color_bars,
        edgecolor="white",
        lw=0.8,
        width=0.6,
        alpha=0.85,
        zorder=2,
    )
    ax1.set_xticks(range(len(buckets)))
    ax1.set_xticklabels(buckets, fontsize=10)
    ax1.set_xlabel("Message size, UTF-8 bytes", fontsize=11)
    ax1.set_ylabel("Compression ratio (%)", fontsize=11, color=color_bars)
    ax1.tick_params(axis="y", labelcolor=color_bars)
    ax1.set_ylim(0, 100)

    for i, r in enumerate(ratios):
        ax1.text(
            i,
            r + 1.5,
            f"{r:.0f}%",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color=color_bars,
        )

    ax2 = ax1.twinx()
    ax2.plot(
        range(len(buckets)),
        counts,
        color=color_line,
        marker="o",
        lw=2,
        markersize=7,
        zorder=3,
    )
    ax2.set_ylabel("Message count", fontsize=11, color=color_line)
    ax2.tick_params(axis="y", labelcolor=color_line)
    ax2.set_ylim(0, max(counts) * 1.3)
    ax2.spines["top"].set_visible(False)

    for i, c in enumerate(counts):
        ax2.text(
            i, c + 25, str(c), ha="center", va="bottom", fontsize=8, color=color_line
        )

    ax1.set_title(
        "Compression ratio vs message length (RU+EN test set, n=2000)",
        fontsize=13,
        fontweight="bold",
    )
    _save(fig, "compression-by-length")


# ════════════════════════════════════════════════════════════
# 6. CAPACITY
# ════════════════════════════════════════════════════════════
def fig_capacity():
    scripts = ["Latin (EN)", "Cyrillic (RU)", "CJK (ZH)", "Arabic (AR)", "Hangul (KO)"]
    raw = [233, 116, 77, 116, 77]
    # capacity ≈ 233 * 8 / bpc  (from honest eval)
    # EN: 233*8/2.19≈850, RU: 233*8/3.02≈618, ZH: 233*8/3.76≈496
    # AR: 233*8/2.29≈813, KO: 233*8/3.07≈607
    comp = [850, 618, 496, 813, 607]

    x = np.arange(len(scripts))
    w = 0.35
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(
        x - w / 2,
        raw,
        w,
        label="Without compression",
        color="#EF9A9A",
        edgecolor="white",
        lw=0.8,
    )
    ax.bar(
        x + w / 2,
        comp,
        w,
        label="With compression",
        color="#81C784",
        edgecolor="white",
        lw=0.8,
    )

    for i in range(len(scripts)):
        mult = comp[i] / raw[i]
        ax.text(
            x[i] + w / 2,
            comp[i] + 15,
            f"×{mult:.1f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            color="#2E7D32",
        )
        ax.text(
            x[i] - w / 2,
            raw[i] + 15,
            str(raw[i]),
            ha="center",
            va="bottom",
            fontsize=9,
            color="#888",
        )
        ax.text(
            x[i] + w / 2,
            comp[i] - 40,
            str(comp[i]),
            ha="center",
            va="top",
            fontsize=9,
            color="white",
            fontweight="bold",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(scripts, fontsize=10, fontweight="bold")
    ax.set_ylabel("Characters per 233-byte packet", fontsize=11)
    ax.set_title(
        "Meshtastic packet capacity: with vs without compression",
        fontsize=13,
        fontweight="bold",
    )
    ax.legend(fontsize=10, loc="upper right")
    ax.set_ylim(0, max(comp) * 1.15)
    _save(fig, "capacity")


if __name__ == "__main__":
    print("Generating all charts...")
    fig_optimization_timeline()
    fig_compression_by_language()
    fig_short_message_fix()
    fig_compression_comparison()
    fig_compression_by_length()
    fig_capacity()
    print("All done!")
