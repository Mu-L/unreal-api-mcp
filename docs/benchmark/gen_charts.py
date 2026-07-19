#!/usr/bin/env python3
"""Render the accuracy benchmark charts (light + dark) from results JSON files.

Usage: python gen_charts.py  (expects results-api.json and results-source.json here)
Outputs: ../images/benchmark-accuracy-{light,dark}.png
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "images"

CONFIG_LABELS = {"mcp": "MCP + targeted Read", "skilled": "Skilled (Grep+Read)", "naive": "Naive (full Reads)"}
CONFIG_ORDER = ["mcp", "skilled", "naive"]

THEMES = {
    "light": {
        "surface": "#fcfcfb", "text": "#0b0b0b", "text2": "#52514e",
        "grid": "#e4e3df",
        "status": {"correct": "#0ca30c", "partial": "#fab219", "wrong": "#d03b3b"},
        "series": ["#2a78d6", "#008300", "#e87ba4"],
    },
    "dark": {
        "surface": "#1a1a19", "text": "#ffffff", "text2": "#c3c2b7",
        "grid": "#33322f",
        "status": {"correct": "#0ca30c", "partial": "#fab219", "wrong": "#d03b3b"},
        "series": ["#3987e5", "#008300", "#d55181"],
    },
}


def verdict_counts(results: dict) -> dict:
    counts = {c: {"correct": 0, "partial": 0, "wrong": 0} for c in CONFIG_ORDER}
    for cfgs in results.values():
        for c, d in cfgs.items():
            v = d["verdict"]["verdict"]
            counts[c][v if v in ("correct", "partial") else "wrong"] += 1
    return counts


def style_axes(ax, t):
    ax.set_facecolor(t["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"])
    ax.tick_params(colors=t["text2"], labelsize=11, length=0)
    ax.xaxis.grid(True, color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def accuracy_figure(api, source, theme_name, t):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2), dpi=200)
    fig.patch.set_facecolor(t["surface"])
    panels = [(f"Unreal API lookup ({len(api)} questions)", verdict_counts(api)),
              (f"Big-file engine source ({len(source)} questions)", verdict_counts(source))]
    for ax, (title, counts) in zip(axes, panels):
        style_axes(ax, t)
        y = list(range(len(CONFIG_ORDER)))[::-1]
        left = [0.0] * len(CONFIG_ORDER)
        for verdict in ("correct", "partial", "wrong"):
            vals = [counts[c][verdict] for c in CONFIG_ORDER]
            ax.barh(y, vals, left=left, height=0.55, color=t["status"][verdict],
                    edgecolor=t["surface"], linewidth=2, label=verdict.capitalize())
            for yi, (l, v) in enumerate(zip(left, vals)):
                if v > 0:
                    ax.text(l + v / 2, y[yi], str(v), ha="center", va="center",
                            fontsize=11, fontweight="bold", color="#ffffff")
            left = [l + v for l, v in zip(left, vals)]
        ax.set_yticks(y)
        ax.set_yticklabels([CONFIG_LABELS[c] for c in CONFIG_ORDER], color=t["text"], fontsize=11)
        ax.set_title(title, color=t["text"], fontsize=12, pad=10)
        ax.set_xlim(0, max(left) * 1.05)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, -0.06), labelcolor=t["text2"], fontsize=10)
    fig.suptitle("Answer quality by agent config (judged against verified ground truth)",
                 color=t["text"], fontsize=13, y=1.04)
    fig.tight_layout()
    out = OUT / f"benchmark-accuracy-{theme_name}.png"
    fig.savefig(out, bbox_inches="tight", facecolor=t["surface"])
    plt.close(fig)
    return out


def main():
    api = json.loads((HERE / "results-api.json").read_text())
    source = json.loads((HERE / "results-source.json").read_text())
    OUT.mkdir(exist_ok=True)
    for name, t in THEMES.items():
        print(accuracy_figure(api, source, name, t))


if __name__ == "__main__":
    main()
