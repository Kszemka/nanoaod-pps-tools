#!/usr/bin/env python3
"""
Strong scaling of one chain on several ~1 TB sets, on the same machine: one figure for the sets
of full-width files, one table for all of them.

    plot_real_vs_synthetic.py --out results/comparison \
        --set "results/full-chain11/run2-1tb:chain11:Run 2 Open Data" \
        --set "results/run3/chain11:chain11:Run 3" \
        --set "results/synthetic-slim:chain11:artificial, slim files" \
        --figure "Run 2 Open Data" --figure "Run 3" --best-of "Run 2 Open Data"

The artificial full files (96 copies of one ds_x32) are left out: their 5 million baskets per
file make the memory per thread a property of the copies rather than of production files, and
they serve instead as the memory control against the slim set (plot_memory_control.py).

--set DIR:TEST:LABEL is a results directory, the test field of its strong sweep (chain11 for
the 11-filter chain, chain for the 5-filter one) and the name the set goes by; a directory
without raw.jsonl or without that sweep is skipped with a warning, so sets still being measured
can stay on the command line. --figure LABEL puts a set in the figure (every set without any
--figure). The figure's sets are full-width files of which the chain reads a few percent; the
slim set, which the chain reads whole, belongs in the table as the reference.

--best-of LABEL takes a set's loop time at each thread count as the fastest of its repeats
instead of their median, for a set whose repeats were slowed down from outside by different
amounts (e.g. Run 2 measured while a download was writing to the same Lustre). The min-max band
stays, the table marks the set, and sets_summary.csv says which statistic each row uses
(loop_stat). Thread counts run once are the same either way.

Writes into --out:
  full_files_chain11.png  loop time, speedup against one thread and peak RSS against the thread
                          count, each with the min-max of the repeats
  sets_summary.csv        every column below, plus the events passing the chain
  sets_summary.tex        the table for the thesis, one column per set
and prints the table. Per set: events; size on disk; codec, branches and baskets per file
(dataset.json, when the job wrote one); bytes read in the event loop at one thread, in GB and as
a share of the set; the fastest point (S_max and its thread count); the 5% plateau, the fewest
threads within 5% of the fastest loop; E at 96 threads; MB per thread (slope of peak RSS); and
GB/s read at the fastest point.

Needs only matplotlib, like plot_results.py.
"""

import argparse
import csv
import json
import os
import sys

from plot_results import core_rows, dedupe_labels, fit_linear, flag_disturbed, load_records, \
    median

# Fewer than plot_results.LABELLED_THREADS: three panels side by side leave less room per tick.
LABELLED = {1, 2, 4, 8, 16, 32, 64, 128, 192}
STYLES = [
    {"color": "#1b7837", "marker": "o"},
    {"color": "#d73027", "marker": "^"},
    {"color": "#4575b4", "marker": "s"},
    {"color": "#762a83", "marker": "D"},
    {"color": "black", "marker": "v"},
]
PLATEAU = 0.05
EFFICIENCY_AT = 96
FIELDS = ["set", "test", "events", "input_tb", "codec", "branches", "baskets_per_file",
          "read_gb", "read_pct", "loop_s_t1", "loop_min_s", "threads_at_min", "max_speedup",
          "plateau_threads", "efficiency_96", "mb_per_thread", "gb_per_s_at_min",
          "events_passed", "loop_stat"]
BEST_MARK = "*"


def parse_set(text):
    parts = text.split(":", 2)
    if len(parts) != 3 or not all(parts):
        raise argparse.ArgumentTypeError(f"--set takes DIR:TEST:LABEL, not '{text}'")
    return parts


def sweep(results_dir, test, best=False):
    """Per thread count: median (best: fastest) loop time, median peak RSS and the runs."""
    records, _ = dedupe_labels(load_records(results_dir))
    flag_disturbed(records)
    ok = [r for r in records if r.get("status") == "ok"]
    runs = [r for r in core_rows(ok, "strong")
            if r.get("test") == test and r.get("threads") and r.get("wall_loop") is not None]
    by_threads = {}
    for r in runs:
        by_threads.setdefault(r["threads"], []).append(r)
    points = []
    for n in sorted(by_threads):
        group = by_threads[n]
        rss = [r["peak_rss_kb"] / 1024 ** 2 for r in group if r.get("peak_rss_kb")]
        points.append({
            "threads": n,
            "loop": (min if best else median)([r["wall_loop"] for r in group]),
            "loop_lo": min(r["wall_loop"] for r in group),
            "loop_hi": max(r["wall_loop"] for r in group),
            "rss_gb": median(rss) if rss else None,
            # The peak is a high-water mark and moves with how the tasks happened to be
            # scheduled; the spread across repeats is what a step between neighbours is
            # compared against.
            "rss_lo": min(rss) if rss else None,
            "rss_hi": max(rss) if rss else None,
            "runs": group,
        })
    return points


def dataset_info(results_dir):
    path = os.path.join(results_dir, "dataset.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def summarise(name, test, points, info, fastest_of_repeats=False):
    first = points[0]
    one = first["runs"] if first["threads"] == 1 else []
    best = min(points, key=lambda p: p["loop"])
    runs = [r for p in points for r in p["runs"]]
    events = median([r["n_events"] for r in runs if r.get("n_events")])
    input_bytes = median([r["input_bytes"] for r in runs if r.get("input_bytes")])
    # One thread reads each basket once; more threads re-read a few at task boundaries.
    read = median([r["bytes_loop"] for r in (one or best["runs"])
                   if r.get("bytes_loop") is not None])
    read_best = median([r["bytes_loop"] for r in best["runs"] if r.get("bytes_loop") is not None])
    passed = sorted({(r.get("checksums") or {}).get("events_passed") for r in runs} - {None})
    plateau = min(p["threads"] for p in points if p["loop"] <= (1 + PLATEAU) * best["loop"])
    at_e = next((p for p in points if p["threads"] == EFFICIENCY_AT), None)
    rss = [(p["threads"], p["rss_gb"] * 1024) for p in points if p["rss_gb"]]
    return {
        "set": name,
        "test": test,
        "events": events,
        "input_tb": input_bytes / 1e12 if input_bytes else None,
        "codec": info.get("codec", ""),
        "branches": info.get("branches_median", info.get("branches", "")),
        "baskets_per_file": info.get("baskets_per_file"),
        "read_gb": read / 1e9 if read is not None else None,
        "read_pct": 100 * read / input_bytes if read is not None and input_bytes else None,
        "loop_s_t1": first["loop"] if one else None,
        "loop_min_s": best["loop"],
        "threads_at_min": best["threads"],
        "max_speedup": first["loop"] / best["loop"] if one else None,
        "plateau_threads": plateau,
        "efficiency_96": first["loop"] / at_e["loop"] / EFFICIENCY_AT if one and at_e else None,
        "mb_per_thread": mb_slope(rss),
        "gb_per_s_at_min": read_best / best["loop"] / 1e9 if read_best is not None else None,
        # More than one value would mean the thread count changed the answer.
        "events_passed": " ".join(str(v) for v in passed),
        "loop_stat": "best" if fastest_of_repeats else "median",
    }


def mb_slope(points):
    """Slope of a straight line through (threads, MB); None below 2 thread counts."""
    return fit_linear(*zip(*points))[1] if len({n for n, _ in points}) >= 2 else None


def fmt(value, spec):
    return "-" if value is None or value == "" else format(value, spec)


TABLE = [
    # (console head, LaTeX row, key, format)
    ("events", r"Events [$10^9$]", "events", ".3g"),
    ("TB", "Size on disk [TB]", "input_tb", ".2f"),
    ("codec", "Codec", "codec", "s"),
    ("branches", "Branches per file", "branches", ""),
    ("baskets", "Baskets per file", "baskets_per_file", ","),
    ("read GB", "Read in the loop [GB]", "read_gb", ".1f"),
    ("read %", r"Read in the loop [\%]", "read_pct", ".1f"),
    ("T(1) s", "Loop, 1 thread [s]", "loop_s_t1", ".0f"),
    ("Tmin s", "Fastest loop [s]", "loop_min_s", ".1f"),
    ("at n", "at threads", "threads_at_min", "d"),
    ("max S", r"Maximum speedup $S$", "max_speedup", ".1f"),
    ("5% at", r"Within 5\% of fastest, from", "plateau_threads", "d"),
    ("E(96)", r"Efficiency $E$ at 96 threads", "efficiency_96", ".2f"),
    ("MB/thr", "Peak RSS per thread [MB]", "mb_per_thread", ".0f"),
    ("GB/s", "Read rate at fastest [GB/s]", "gb_per_s_at_min", ".2f"),
]


def cell(row, key, spec):
    value = row[key]
    if key == "events" and value:
        value = value / 1e9
    return fmt(value, spec)


def set_name(row):
    return row["set"] + (BEST_MARK if row["loop_stat"] == "best" else "")


def print_table(rows):
    print(f"{'':>9s}  " + "  ".join(f"{set_name(row)[:22]:>22s}" for row in rows))
    for head, _, key, spec in TABLE:
        print(f"{head:>9s}  " + "  ".join(f"{cell(row, key, spec):>22s}" for row in rows))
    print("  T = event-loop time; S = T(1)/T(n); E = S/n; read at 1 thread; "
          "MB/thr = slope of a straight line through peak RSS")
    if any(row["loop_stat"] == "best" for row in rows):
        print(f"  {BEST_MARK} T = fastest of the repeats at each thread count, not their median")


def write_csv(rows, path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v)
                             for k, v in row.items()})


def latex_escape(text):
    return str(text).replace("\\", r"\textbackslash{}").replace("&", r"\&") \
        .replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")


def write_tex(rows, path):
    lines = [r"\begin{tabular}{l" + "r" * len(rows) + "}", r"\toprule",
             " & ".join([""] + [latex_escape(row["set"])
                                + (f"$^{BEST_MARK}$" if row["loop_stat"] == "best" else "")
                                for row in rows]) + r" \\",
             r"\midrule"]
    for _, title, key, spec in TABLE:
        cells = [latex_escape(cell(row, key, spec)).replace(",", "\\,") for row in rows]
        lines.append(" & ".join([title] + cells) + r" \\")
    lines.append(r"\bottomrule")
    if any(row["loop_stat"] == "best" for row in rows):
        lines.append(rf"\multicolumn{{{len(rows) + 1}}}{{l}}{{\footnotesize ${BEST_MARK}$ loop "
                     r"times: fastest of the repeats at each thread count, not their median.} \\")
    lines.append(r"\end{tabular}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def plot(sets, tests, path, best=()):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax_t, ax_s, ax_m) = plt.subplots(1, 3, figsize=(15, 4.6))
    ticks = sorted({p["threads"] for points in sets.values() for p in points})
    for (name, points), base in zip(sets.items(), STYLES * len(sets)):
        style = dict(base, ls="-")
        xs = [p["threads"] for p in points]
        timed = name + (" (fastest of repeats)" if name in best else "")
        ax_t.errorbar(xs, [p["loop"] for p in points],
                      yerr=[[p["loop"] - p["loop_lo"] for p in points],
                            [p["loop_hi"] - p["loop"] for p in points]],
                      capsize=3, label=timed, **style)
        if points[0]["threads"] == 1:
            ax_s.plot(xs, [points[0]["loop"] / p["loop"] for p in points], label=timed, **style)
        with_rss = [p for p in points if p["rss_gb"]]
        if with_rss:
            ax_m.errorbar([p["threads"] for p in with_rss], [p["rss_gb"] for p in with_rss],
                          yerr=[[p["rss_gb"] - p["rss_lo"] for p in with_rss],
                                [p["rss_hi"] - p["rss_gb"] for p in with_rss]],
                          capsize=3, label=name, **style)
    ax_s.plot(ticks, ticks, ls="--", color="grey", lw=0.8, label="ideal")
    labelled = [t for t in ticks if t in LABELLED]
    for ax in (ax_t, ax_s):
        ax.set_xscale("log", base=2)
        ax.set_xticks(labelled)
        ax.set_xticklabels([str(t) for t in labelled])
        ax.minorticks_off()
    ax_m.set_xlim(0, ticks[-1] * 1.04)
    for ax in (ax_t, ax_s, ax_m):
        ax.set_xlabel("threads")
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=8)
    ax_t.set_yscale("log")
    ax_s.set_yscale("log", base=2)
    ax_s.set_yticks(labelled)
    ax_s.set_yticklabels([str(t) for t in labelled])
    ax_t.set_ylabel("event-loop time [s]")
    ax_s.set_ylabel("speedup against 1 thread")
    ax_m.set_ylabel("peak RSS [GB]")
    ax_t.set_title("event loop")
    ax_s.set_title("strong scaling")
    ax_m.set_title("memory")
    chain = {"chain11": "11-filter chain (10 branches)", "chain": "5-filter chain (4 branches)"}
    fig.suptitle(" / ".join(chain.get(t, t) for t in sorted(set(tests)))
                 + ", ~1 TB of full-width files each")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="sets", type=parse_set, action="append", required=True,
                        metavar="DIR:TEST:LABEL", help="a results directory (repeatable)")
    parser.add_argument("--figure", action="append", default=[], metavar="LABEL",
                        help="a set to draw (repeatable; default: every set)")
    parser.add_argument("--best-of", action="append", default=[], metavar="LABEL",
                        help="a set timed by the fastest of its repeats (repeatable)")
    parser.add_argument("--out", default=".", help="directory for the figure and the tables")
    args = parser.parse_args()

    labels = [label for _, _, label in args.sets]
    for option, given in (("--figure", args.figure), ("--best-of", args.best_of)):
        unknown = [label for label in given if label not in labels]
        if unknown:
            print(f"ERROR: {option} {', '.join(unknown)} is not the label of any --set",
                  file=sys.stderr)
            return 1

    sets, tests, rows = {}, {}, []
    for results_dir, test, label in args.sets:
        best = label in args.best_of
        points = sweep(results_dir, test, best) if os.path.isdir(results_dir) else []
        if not points:
            print(f"WARNING: skipping '{label}': no {test} strong sweep (r<N>_strong_*) in "
                  f"{results_dir}", file=sys.stderr)
            continue
        sets[label], tests[label] = points, test
        rows.append(summarise(label, test, points, dataset_info(results_dir), best))
    if not rows:
        print("ERROR: no set with a strong sweep", file=sys.stderr)
        return 1

    print_table(rows)
    os.makedirs(args.out, exist_ok=True)
    for name, writer in (("sets_summary.csv", write_csv), ("sets_summary.tex", write_tex)):
        path = os.path.join(args.out, name)
        writer(rows, path)
        print(f"  {path}")

    drawn = {label: sets[label] for label in (args.figure or labels) if label in sets}
    if not drawn:
        print("no set of --figure has results yet -- figure skipped", file=sys.stderr)
        return 0
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib not installed -- tables written, figure skipped", file=sys.stderr)
        return 0
    png_path = os.path.join(args.out, "full_files_chain11.png")
    plot(drawn, [tests[label] for label in drawn], png_path, set(args.best_of))
    print(f"  {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
