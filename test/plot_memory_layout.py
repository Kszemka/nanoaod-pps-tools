#!/usr/bin/env python3
"""
Memory per thread against the layout of the input files.

Every ImplicitMT worker opens its own TTree on the file it is processing, and each TBranch of
that tree carries the index of all its baskets (bytes, first entry and file offset of each),
whether the analysis reads the branch or not. If that is what a thread costs, the slope of
peak RSS against threads follows

    MB per thread = a + b * branches + c * baskets per file

and not the branch count alone. Each --set contributes its strong sweep (r<N>_strong_*, median
per thread count) and a straight-line fit; the model is fitted by least squares over the sets
whose layout is known, and its residuals are printed, so a model that does not hold shows.

    plot_memory_layout.py --out DIR \
        --set "results/helios/slim-1.5tb:chain11:slim:results/real-1/results-helios-memtest/layout-slim11" \
        --set "results/helios/full-11m:chain:ds_x32:results/real-1/results-helios-memtest/layout-ds_x32" \
        --set "results/helios/full-1tb:chain:ds_x32 x96:results/real-1/results-helios-memtest/layout-ds_x32" \
        --set "results/real-1/results-helios-memtest:chain:ds_x32 head" \
        --set "results/real-1/results-helios-opendata-weak4:chain:Open Data 89 M" \
        --set "results/real-1/results-helios-opendata-weak16:chain:Open Data 356 M" \
        --set "results/real-1/results-helios-opendata-1tb:chain:Open Data 1 TB"

A set is DIR:TEST:LABEL[:LAYOUT]. LAYOUT is a directory with dataset.json (dataset_json.py),
or BRANCHES/BASKETS by hand; without it DIR/dataset.json is used. Writes 16_memory_layout.png
and summary_memory_layout.csv. Needs only matplotlib, like plot_results.py.
"""

import argparse
import csv
import json
import math
import os
import sys

from plot_optimum import solve3
from plot_results import core_rows, dedupe_labels, fit_linear, flag_disturbed, load_records, \
    median

COLOURS = ["#762a83", "#1b7837", "#e08214", "#d73027", "#4575b4", "#999999", "#000000",
           "#8c510a"]
FIELDS = ["label", "dir", "test", "branches", "baskets_per_file", "clusters_per_file",
          "rss_1_thread_mb", "mb_per_thread", "mb_per_thread_low", "mb_per_thread_high",
          "model_mb", "residual_mb"]
# On inputs of many files RSS is not linear in threads (full-1tb: 385 MB per thread up to 32,
# 124 MB above), so the slope is also given on either side of this thread count.
SPLIT_THREADS = 32


def read_layout(results_dir, spec):
    if spec and "/" in spec and not os.path.isdir(spec):
        branches, baskets = spec.split("/")
        return {"branches_median": float(branches), "baskets_per_file": float(baskets)}
    path = os.path.join(spec or results_dir, "dataset.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def sweep(results_dir, test):
    records, _ = dedupe_labels(load_records(results_dir))
    flag_disturbed(records)
    by_threads = {}
    for r in core_rows(records, "strong"):
        if r.get("status") == "ok" and r.get("test") == test and r.get("threads") \
                and r.get("peak_rss_kb"):
            by_threads.setdefault(r["threads"], []).append(r["peak_rss_kb"] / 1024)
    return sorted((n, median(v)) for n, v in by_threads.items())


def slope(points):
    """MB per thread of a straight line through the points; None below 2 thread counts."""
    return fit_linear(*zip(*points))[1] if len(points) >= 2 else None


def parse_set(text):
    parts = text.split(":")
    if len(parts) < 3:
        raise ValueError(f"--set needs DIR:TEST:LABEL[:LAYOUT], not '{text}'")
    return {"dir": parts[0], "test": parts[1], "label": parts[2],
            "layout_spec": parts[3] if len(parts) > 3 else None}


def fit_model(rows):
    """a, b, c of MB/thread = a + b*branches + c*baskets, least squares; None if underdetermined."""
    known = [r for r in rows if r["branches"] is not None and r["baskets_per_file"] is not None]
    if len(known) < 3:
        return None
    xs = [(1.0, r["branches"], r["baskets_per_file"]) for r in known]
    ata = [[sum(x[i] * x[j] for x in xs) for j in range(3)] for i in range(3)]
    aty = [sum(x[i] * r["mb_per_thread"] for x, r in zip(xs, known)) for i in range(3)]
    return solve3(ata, aty)


def plot(rows, sweeps, model, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from itertools import cycle
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

    fig, (ax_rss, ax_cost) = plt.subplots(1, 2, figsize=(12, 4.6))
    for row, points, colour in zip(rows, sweeps, cycle(COLOURS)):
        xs, ys = zip(*points)
        ax_rss.plot(xs, [y / 1024 for y in ys], marker="o", color=colour, label=row["label"])
        intercept, slope = row["fit"]
        ends = [xs[0], xs[-1]]
        ax_rss.plot(ends, [(intercept + slope * n) / 1024 for n in ends], ls=":", color=colour)
        if row["baskets_per_file"]:
            ax_cost.scatter(row["baskets_per_file"], row["mb_per_thread"], s=60, color=colour,
                            zorder=3, label=f"{row['label']}: {row['branches']:.0f} branches")
            if row["model_mb"] is not None:
                ax_cost.scatter(row["baskets_per_file"], row["model_mb"], marker="x", s=60,
                                color=colour, zorder=3)
    ax_rss.set_xlabel("threads")
    ax_rss.set_ylabel("peak RSS [GB]")
    ax_rss.set_title("peak memory, with a straight line per input")
    ax_rss.grid(alpha=0.3)
    ax_rss.legend(fontsize=8)
    ax_cost.set_xscale("log")
    ax_cost.xaxis.set_major_locator(LogLocator(subs=(1, 2, 5)))
    ax_cost.xaxis.set_major_formatter(FuncFormatter(
        lambda x, _: f"{x / 1e6:g} M" if x >= 1e6 else f"{x / 1e3:g} k"))
    ax_cost.xaxis.set_minor_formatter(NullFormatter())
    ax_cost.set_xlabel("baskets per file")
    ax_cost.set_ylabel("memory per extra thread [MB]")
    title = "per-thread cost against file layout"
    if model:
        a, b, c = model
        title += (f"\nx: {a:.0f} MB + {b * 1024:.1f} kB/branch + {c * 1024 ** 2:.0f} B/basket")
    ax_cost.set_title(title, fontsize=10)
    ax_cost.grid(alpha=0.3, which="both")
    ax_cost.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", action="append", required=True, dest="sets",
                        help="DIR:TEST:LABEL[:LAYOUT]")
    parser.add_argument("--out", default=".", help="directory for the figure and the CSV")
    args = parser.parse_args()

    rows, sweeps = [], []
    for text in args.sets:
        spec = parse_set(text)
        points = sweep(spec["dir"], spec["test"])
        if len(points) < 2:
            print(f"ERROR: fewer than 2 thread counts of {spec['test']} in {spec['dir']}",
                  file=sys.stderr)
            return 1
        layout = read_layout(spec["dir"], spec["layout_spec"])
        fit = fit_linear(*zip(*points))
        rows.append({
            "label": spec["label"], "dir": spec["dir"], "test": spec["test"],
            "branches": layout.get("branches_median"),
            "baskets_per_file": layout.get("baskets_per_file"),
            "clusters_per_file": layout.get("clusters_per_file"),
            "rss_1_thread_mb": points[0][1], "mb_per_thread": fit[1], "fit": fit,
            "mb_per_thread_low": slope([p for p in points if p[0] <= SPLIT_THREADS]),
            "mb_per_thread_high": slope([p for p in points if p[0] >= SPLIT_THREADS]),
            "model_mb": None, "residual_mb": None,
        })
        sweeps.append(points)

    model = fit_model(rows)
    if model:
        a, b, c = model
        for row in rows:
            if row["branches"] is not None and row["baskets_per_file"] is not None:
                row["model_mb"] = a + b * row["branches"] + c * row["baskets_per_file"]
                row["residual_mb"] = row["mb_per_thread"] - row["model_mb"]

    low, high = f"<={SPLIT_THREADS}", f">={SPLIT_THREADS}"
    print(f"{'input':24s} {'branches':>8s} {'baskets/file':>12s} {'MB/thread':>9s} "
          f"{low:>6s} {high:>6s} {'model':>7s} {'resid':>7s}")
    for row in rows:
        def show(value, spec):
            return "-" if value is None else format(value, spec)
        print(f"{row['label'][:24]:24s} {show(row['branches'], '8.0f')} "
              f"{show(row['baskets_per_file'], '12.0f')} {row['mb_per_thread']:9.1f} "
              f"{show(row['mb_per_thread_low'], '6.1f')} {show(row['mb_per_thread_high'], '6.1f')} "
              f"{show(row['model_mb'], '7.1f')} {show(row['residual_mb'], '7.1f')}")
    print(f"  MB/thread: slope over all thread counts (the model's input); {low}, {high}: "
          "the same on either side")
    if model:
        a, b, c = model
        print(f"  MB/thread = {a:.1f} MB + {b * 1024:.2f} kB x branches + "
              f"{c * 1024 ** 2:.1f} B x baskets per file")
        if len(rows) == 3:
            print("  three inputs, three parameters: the fit is exact and tests nothing")
    else:
        print("  model not fitted: fewer than 3 inputs with a known layout")

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "summary_memory_layout.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v)
                             for k, v in row.items()})
    print(f"  {csv_path}")
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib not installed -- CSV written, plot skipped", file=sys.stderr)
        return 0
    png_path = os.path.join(args.out, "16_memory_layout.png")
    plot(rows, sweeps, model, png_path)
    print(f"  {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
