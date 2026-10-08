#!/usr/bin/env python3
"""
Peak memory against thread count on two input sets, in one figure.

The full NanoAOD files and the slim files differ in the number of branches stored, not in the
analysis: the chain on the full files reads a few percent of them, the chain on the slim files
reads all of them. If every worker thread pays for the branches stored in the file, the full
files cost far more memory per thread although far less of them is read. Each set contributes
its strong sweep (r<N>_strong_*), median per thread count with min/max whiskers, a straight-line
fit whose slope is the average memory per additional thread, and the share of the input the
event loop read. On the full files the growth is steeper below 32 threads than above, so the
slope there is an average, not a constant.

    plot_memory_compare.py --full results/helios/full-1tb --slim results/helios/slim-1.5tb \
        [--out bench_rss_slim_vs_full.png]

Needs only matplotlib, like plot_results.py.
"""

import argparse
import os
import sys

from plot_results import CORE_TEST_COLOUR, core_rows, dedupe_labels, fit_linear, flag_disturbed, \
    load_records, median, series


def strong_records(results_dir, test):
    records, _ = dedupe_labels(load_records(results_dir))
    flag_disturbed(records)
    return [r for r in core_rows(records, "strong")
            if r.get("status") == "ok" and r.get("test") == test and r.get("threads")]


def share_read(records):
    """Median fraction of the input the event loop read."""
    shares = [r["bytes_loop"] / r["input_bytes"] for r in records
              if r.get("bytes_loop") and r.get("input_bytes")]
    return median(shares)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", required=True, help="results directory of the full files")
    parser.add_argument("--slim", required=True, help="results directory of the slim files")
    parser.add_argument("--full-test", default="chain")
    parser.add_argument("--slim-test", default="chain11")
    parser.add_argument("--full-label", default="full files (about 2000 branches), 5-filter chain")
    parser.add_argument("--slim-label", default="slim files (10 branches), 10-branch chain")
    parser.add_argument("--out", default="bench_rss_slim_vs_full.png")
    args = parser.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.8))
    top = 0
    for results_dir, test, label in ((args.full, args.full_test, args.full_label),
                                     (args.slim, args.slim_test, args.slim_label)):
        records = strong_records(results_dir, test)
        if not records:
            print(f"ERROR: no strong-scaling records for {test} in {results_dir}", file=sys.stderr)
            return 1
        points = next(iter(series(records, ("test",), "threads", "peak_rss_kb").values()))
        gb = [(x, m / 1e6, lo / 1e6, hi / 1e6) for x, m, lo, hi in points]
        xs = [p[0] for p in gb]
        intercept, slope = fit_linear(xs, [p[1] for p in gb])
        share = share_read(records)
        colour = CORE_TEST_COLOUR[test]
        ax.errorbar(xs, [p[1] for p in gb],
                    yerr=[[p[1] - p[2] for p in gb], [p[3] - p[1] for p in gb]],
                    marker="o", capsize=3, lw=2, color=colour,
                    label=f"{label}: {slope * 1000:.3g} MB per thread on average, "
                          f"reads {share * 100:.0f}% of the input")
        ax.plot([0, max(xs)], [intercept, intercept + slope * max(xs)], ls=":", color=colour)
        top = max(top, max(p[3] for p in gb))
        print(f"{test} in {results_dir}: {gb[0][1]:.2f} GB at {xs[0]} threads, "
              f"{gb[-1][1]:.2f} GB at {xs[-1]}, fit {intercept:.2f} GB + {slope * 1000:.1f} MB "
              f"per thread, loop reads {share * 100:.1f}% of the input")

    ax.set_xlim(0, 196)
    ax.set_xticks(range(0, 193, 32))
    ax.set_ylim(0, top * 1.08)
    ax.set_xlabel("threads")
    ax.set_ylabel("peak resident memory [GB]")
    ax.set_title("Memory against thread count (fixed problem size)")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"  {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
