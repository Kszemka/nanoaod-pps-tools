#!/usr/bin/env python3
"""
The 5-filter chain's strong scaling on the artificial 1 TB set against ~1 TB of real Run 2
Open Data, on the same machine.

    plot_real_vs_synthetic.py --synthetic results/helios/full-1tb \
        --control results/real-1/results-helios-control-1tb \
        --real results/real-1/results-helios-opendata-1tb [--out DIR]

--synthetic is the original campaign on ds_1..ds_96.root, --control a few of its points
measured again in the job that measured --real, so that a gap between --control and
--synthetic is the file system having changed, not the data. --control is optional.

Writes 15_real_vs_synthetic.png (loop time, speedup against one thread and peak RSS against
the thread count) and summary_real_vs_synthetic.csv, and prints the same table. Codec and
branch count come from dataset.json in a results directory when slurm_real_vs_synthetic.sbatch
wrote one there; the synthetic set falls back to the control's, which reads the same files.

Needs only matplotlib, like plot_results.py.
"""

import argparse
import csv
import json
import os
import sys

from plot_optimum import fit_optimum
from plot_results import core_rows, dedupe_labels, fit_linear, flag_disturbed, load_records, \
    median

TEST = "chain"
# Fewer than plot_results.LABELLED_THREADS: three panels side by side leave less room per tick.
LABELLED = {1, 2, 4, 8, 16, 32, 64, 128, 192}
STYLE = {
    "synthetic": {"label": "artificial (96 x ds_x32)", "color": "#1b7837", "marker": "o",
                  "ls": "-"},
    "control": {"label": "artificial, re-measured", "color": "black", "marker": "s",
                "ls": "none", "mfc": "none", "ms": 9},
    "real": {"label": "Run 2 Open Data", "color": "#d73027", "marker": "^", "ls": "-"},
}
FIELDS = ["set", "events", "input_gb", "codec", "branches", "read_gb_t1", "read_pct_t1",
          "events_per_s_t1", "loop_s_t1", "loop_min_s", "threads_at_min", "max_speedup",
          "n_star", "b_ms", "mb_per_thread", "events_passed"]


def sweep(results_dir):
    """Per thread count: median loop time, median peak RSS and the runs themselves."""
    records, _ = dedupe_labels(load_records(results_dir))
    flag_disturbed(records)
    ok = [r for r in records if r.get("status") == "ok"]
    runs = [r for r in core_rows(ok, "strong")
            if r.get("test") == TEST and r.get("threads") and r.get("wall_loop") is not None]
    by_threads = {}
    for r in runs:
        by_threads.setdefault(r["threads"], []).append(r)
    points = []
    for n in sorted(by_threads):
        group = by_threads[n]
        points.append({
            "threads": n,
            "loop": median([r["wall_loop"] for r in group]),
            "loop_lo": min(r["wall_loop"] for r in group),
            "loop_hi": max(r["wall_loop"] for r in group),
            "rss_gb": median([r["peak_rss_kb"] / 1024 ** 2 for r in group
                              if r.get("peak_rss_kb")] or [0]) or None,
            "runs": group,
        })
    return points


def dataset_info(results_dir):
    path = os.path.join(results_dir, "dataset.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def summarise(name, points, info):
    first = points[0]
    one = first["runs"] if first["threads"] == 1 else []
    best = min(points, key=lambda p: p["loop"])
    events = median([r["n_events"] for p in points for r in p["runs"] if r.get("n_events")])
    input_bytes = median([r["input_bytes"] for p in points for r in p["runs"]
                          if r.get("input_bytes")])
    read = median([r["bytes_loop"] for r in one if r.get("bytes_loop") is not None])
    passed = sorted({(r.get("checksums") or {}).get("events_passed")
                     for p in points for r in p["runs"]} - {None})
    fit = fit_optimum([(p["threads"], p["loop"]) for p in points]) if len(points) >= 4 else None
    rss = [(p["threads"], p["rss_gb"] * 1024) for p in points if p["rss_gb"]]
    slope = fit_linear(*zip(*rss))[1] if len({n for n, _ in rss}) >= 2 else None
    return {
        "set": name,
        "events": events,
        "input_gb": input_bytes / 1e9 if input_bytes else None,
        "codec": info.get("codec", ""),
        "branches": info.get("branches", ""),
        "read_gb_t1": read / 1e9 if read is not None else None,
        "read_pct_t1": 100 * read / input_bytes if read is not None and input_bytes else None,
        "events_per_s_t1": median([r["events_per_s"] for r in one if r.get("events_per_s")]),
        "loop_s_t1": first["loop"] if one else None,
        "loop_min_s": best["loop"],
        "threads_at_min": best["threads"],
        "max_speedup": first["loop"] / best["loop"] if one else None,
        "n_star": (fit[1] / fit[2]) ** 0.5 if fit and fit[1] > 0 and fit[2] > 0 else None,
        "b_ms": fit[2] * 1000 if fit else None,
        "mb_per_thread": slope,
        # More than one value would mean the thread count changed the answer.
        "events_passed": " ".join(str(v) for v in passed),
    }


def fmt(value, spec):
    return "-" if value is None or value == "" else format(value, spec)


def print_table(rows):
    columns = [("set", "set", "10s"), ("events", "events", ".3g"), ("GB", "input_gb", ".0f"),
               ("codec", "codec", "s"), ("branches", "branches", "s"),
               ("read GB", "read_gb_t1", ".1f"), ("read %", "read_pct_t1", ".1f"),
               ("ev/s t1", "events_per_s_t1", ".3g"), ("T(1) s", "loop_s_t1", ".0f"),
               ("Tmin s", "loop_min_s", ".1f"), ("at n", "threads_at_min", "d"),
               ("max S", "max_speedup", ".1f"), ("n*", "n_star", ".0f"), ("b ms", "b_ms", ".1f"),
               ("MB/thr", "mb_per_thread", ".0f"), ("passed", "events_passed", "s")]
    print("  ".join(f"{head:>9s}" for head, _, _ in columns))
    for row in rows:
        print("  ".join(f"{fmt(row[key], spec):>9s}" for _, key, spec in columns))
    print("  T = event-loop time; S = T(1)/T(n); n*, b from T(n) = c + a/n + b*n "
          "(plot_optimum.py); MB/thr = slope of a straight line through peak RSS")


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v)
                             for k, v in row.items()})


def plot(sets, rows, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax_t, ax_s, ax_m) = plt.subplots(1, 3, figsize=(15, 4.6))
    ticks = sorted({p["threads"] for points in sets.values() for p in points})
    for name, points in sets.items():
        style = dict(STYLE[name])
        label = style.pop("label")
        xs = [p["threads"] for p in points]
        ax_t.errorbar(xs, [p["loop"] for p in points],
                      yerr=[[p["loop"] - p["loop_lo"] for p in points],
                            [p["loop_hi"] - p["loop"] for p in points]],
                      capsize=3, label=label, **style)
        if points[0]["threads"] == 1:
            ax_s.plot(xs, [points[0]["loop"] / p["loop"] for p in points], label=label, **style)
        rss = [(p["threads"], p["rss_gb"]) for p in points if p["rss_gb"]]
        if rss:
            ax_m.plot(*zip(*rss), label=label, **style)
            row = next(r for r in rows if r["set"] == name)
            if row["mb_per_thread"] is not None and name != "control":
                intercept, slope = fit_linear(*zip(*rss))
                ends = [rss[0][0], rss[-1][0]]
                ax_m.plot(ends, [intercept + slope * n for n in ends], ls=":",
                          color=style["color"], label=f"{slope * 1024:.0f} MB per thread")
    ax_s.plot(ticks, ticks, ls="--", color="grey", lw=0.8, label="ideal")
    labelled = [t for t in ticks if t in LABELLED]
    for ax in (ax_t, ax_s):
        ax.set_xscale("log", base=2)
        ax.set_xticks(labelled)
        ax.set_xticklabels([str(t) for t in labelled])
        ax.minorticks_off()
    # Linear here: the fit is a straight line in n.
    ax_m.set_xlim(0, ticks[-1] * 1.04)
    for ax in (ax_t, ax_s, ax_m):
        ax.set_xlabel("threads")
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=8)
    ax_t.set_yscale("log")
    ax_t.set_ylabel("event-loop time [s]")
    ax_s.set_ylabel("speedup against 1 thread")
    ax_m.set_ylabel("peak RSS [GB]")
    ax_t.set_title("event loop")
    ax_s.set_title("strong scaling")
    ax_m.set_title("memory")
    fig.suptitle("5-filter chain, ~1 TB: artificial set against real Run 2 data")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--synthetic", required=True, help="results of the artificial 1 TB set")
    parser.add_argument("--control", help="the same set re-measured next to --real")
    parser.add_argument("--real", required=True, help="results of the Open Data set")
    parser.add_argument("--out", default=".", help="directory for the figure and the CSV")
    args = parser.parse_args()

    dirs = {"synthetic": args.synthetic, "control": args.control, "real": args.real}
    sets, rows = {}, []
    for name, results_dir in dirs.items():
        if not results_dir:
            continue
        points = sweep(results_dir)
        if not points:
            print(f"ERROR: no {TEST} strong sweep (r<N>_strong_*) in {results_dir}",
                  file=sys.stderr)
            return 1
        info = dataset_info(results_dir)
        if not info and name == "synthetic" and args.control:
            info = dataset_info(args.control)
        sets[name] = points
        rows.append(summarise(name, points, info))

    print_table(rows)
    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "summary_real_vs_synthetic.csv")
    write_csv(rows, csv_path)
    print(f"  {csv_path}")
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib not installed -- CSV written, plot skipped", file=sys.stderr)
        return 0
    png_path = os.path.join(args.out, "15_real_vs_synthetic.png")
    plot(sets, rows, png_path)
    print(f"  {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
