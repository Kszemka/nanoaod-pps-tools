#!/usr/bin/env python3
"""
Turns results/raw.jsonl into a flat CSV and the plots.

Plot order follows how much the result can be trusted, not how interesting it looks. The
deterministic quantities -- memory against dataset size, bytes read, number of event loops --
come first; the thread-scaling curve is last and carries its caveats printed on the figure,
because on a warm cache with a fixed JIT cost it is the most fragile thing measured here.

Two rules run through all of it:

  Repeats are aggregated, never overwritten. Every curve goes through `aggregate()`, which
  takes the median and can report the spread. An earlier version indexed records by key in a
  dict, so with REPEATS=3 the plot silently showed whichever repeat happened to be written
  last, and no figure said how much the three differed.

  Runs that hit the timeout are drawn, not dropped. A Python path that cannot finish in 300 s
  is a result about the implementation; filtering it out turns the plot into a survivorship
  bias in favour of whatever was fast enough to complete.
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

CSV_FIELDS = [
    "label", "status", "schema_version", "machine", "test", "impl", "mode", "threads",
    "chain_len", "chain_order", "filter_style", "tree_cache", "format", "tag", "input",
    "n_events",
    "n_tracks", "wall_setup", "wall_warmup", "wall_jit", "wall_loop", "wall_fixed",
    "bytes_setup", "bytes_warmup", "bytes_jit", "bytes_loop", "bytes_total",
    "columns_zip_bytes", "read_amplification", "peak_rss_kb", "rss_baseline_kb",
    "peak_rss_net_kb", "time_maxrss_kb", "cpu_percent", "elapsed_s", "events_per_s",
    "tracks_per_s", "event_loops", "exit_code", "timeout_s", "root_version",
]


def load_records(results_dir):
    path = os.path.join(results_dir, "raw.jsonl")
    if not os.path.exists(path):
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_dataset_info(results_dir):
    info_path = os.path.join(results_dir, "dataset_info.json")
    if not os.path.exists(info_path):
        return {}
    with open(info_path) as f:
        return json.load(f)


def current_schema_records(records):
    """
    Drops records written by an older harness.

    Results get merged across machines and across campaigns, and some fields changed meaning
    rather than just being added -- n_events in TEST 3, and the split of time between setup and
    loop. Averaging those together would produce numbers belonging to neither version.
    """
    import bench_common as bc

    keep, stale = [], []
    for record in records:
        if record.get("status") != "ok":
            keep.append(record)
        elif record.get("schema_version") == bc.SCHEMA_VERSION:
            keep.append(record)
        else:
            stale.append(record)
    return keep, stale


def write_csv(records, results_dir):
    out_path = os.path.join(results_dir, "bench.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS + ["checksums"], extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["checksums"] = json.dumps(record.get("checksums"))
            writer.writerow(row)
    return out_path


def median(values):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def aggregate(records, key_fields, value_field):
    """
    Median across repeats, with the range kept alongside it.

    Returns key -> (median, min, max, n). The spread is not decoration: it is the only thing
    that distinguishes a real difference between two implementations from run-to-run noise on
    a shared machine, and it is what the error bars on the figures are drawn from.
    """
    buckets = defaultdict(list)
    for record in records:
        if record.get("status") != "ok" or record.get(value_field) is None:
            continue
        key = tuple(record.get(field) for field in key_fields)
        buckets[key].append(record[value_field])
    return {
        key: (median(values), min(values), max(values), len(values))
        for key, values in buckets.items()
    }


def series(records, group_fields, x_field, value_field):
    """Aggregated curves: group key -> sorted [(x, median, min, max)]."""
    values = aggregate(records, tuple(group_fields) + (x_field,), value_field)
    out = defaultdict(list)
    for key, (mid, low, high, _) in values.items():
        out[key[:-1]].append((key[-1], mid, low, high))
    return {key: sorted(points) for key, points in out.items() if all(p[0] is not None for p in points)}


def plot_series(ax, points, label, **kwargs):
    """Draws a curve with min/max whiskers, so the reader sees the spread across repeats."""
    xs = [p[0] for p in points]
    mids = [p[1] for p in points]
    lows = [p[1] - p[2] for p in points]
    highs = [p[3] - p[1] for p in points]
    ax.errorbar(xs, mids, yerr=[lows, highs], marker="o", capsize=3, label=label, **kwargs)


def censored_points(records, test=None, impl=None):
    """
    Timed-out runs, as lower bounds on time.

    The failure record carries the timeout it hit, so the run can be drawn at that value with
    an upward arrow: "at least this long, we stopped watching". That is what the measurement
    established, and it is more informative than an absent marker.
    """
    out = []
    for record in records:
        if record.get("status") == "ok" or not record.get("timeout_s"):
            continue
        label = str(record.get("label", ""))
        if test and test not in label:
            continue
        if impl and impl not in label:
            continue
        out.append((label, float(record["timeout_s"])))
    return out


def max_useful_threads(results_dir, for_input=None):
    """
    Thread counts beyond ~clusters/4 measure scheduling noise, not scaling.

    Scoped to one dataset when asked. Taking the maximum over every dataset in
    dataset_info.json means the cap printed next to a sweep can come from a completely
    different file: with ds_s at 39 clusters and ds_x32 at 1100, the cap for a sweep actually
    running on ds_s would be reported as 275.
    """
    info = load_dataset_info(results_dir)
    if not info:
        return 999
    if for_input:
        entry = info.get(os.path.basename(for_input))
        if not entry:
            return 999
        return max(entry.get("n_clusters", 0) // 4, 1)
    clusters = [entry.get("n_clusters", 0) for entry in info.values()]
    return max(max(clusters) // 4, 1) if clusters else 999


def plot_all(records, results_dir):
    try:
        import matplotlib
    except ImportError:
        print("matplotlib not installed -- CSV written, plots skipped "
              "(conda install -c conda-forge matplotlib)", file=sys.stderr)
        return []

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = [r for r in records if r.get("status") == "ok"]
    failed = [r for r in records if r.get("status") != "ok"]
    info = load_dataset_info(results_dir)
    outputs = []

    def save(fig, name):
        path = os.path.join(results_dir, name)
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
        outputs.append(path)

    scale = [r for r in ok if str(r.get("label", "")).startswith("scale_")]

    # (1) Peak RSS vs dataset size -- the headline result.
    if scale:
        fig, (ax_gross, ax_net) = plt.subplots(1, 2, figsize=(11, 4.5))
        for ax, field, title in (
            (ax_gross, "peak_rss_kb", "peak RSS"),
            # The interpreter, PyROOT and numpy account for ~470 MB before any data is read, so
            # on the smaller datasets the gross peak is mostly a constant and hides the very
            # difference the plot is about.
            (ax_net, "peak_rss_net_kb", "peak RSS minus baseline"),
        ):
            for key, points in sorted(series(scale, ("test", "impl"), "n_events", field).items()):
                plot_series(ax, [(x, m / 1024, lo / 1024, hi / 1024) for x, m, lo, hi in points],
                            f"{key[0]}/{key[1]}")
            ax.set_xlabel("events")
            ax.set_ylabel(f"{title} [MB]")
            ax.set_xscale("log")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)
        fig.suptitle("Memory vs dataset size: streaming O(1) against materialised O(N)")
        save(fig, "01_rss_vs_size.png")

        # (2) Wall time vs dataset size.
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for key, points in sorted(series(scale, ("test", "impl"), "n_events", "wall_loop").items()):
            plot_series(ax, points, f"{key[0]}/{key[1]}")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("events")
        ax.set_ylabel("event-loop wall time [s]")
        ax.set_title("Time vs dataset size")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "02_time_vs_size.png")

    # (3) Throughput at one thread.
    single = [r for r in ok if not r.get("threads") and r.get("tracks_per_s")]
    if single:
        values = aggregate(single, ("test", "impl", "mode"), "tracks_per_s")
        keys = sorted(values, key=lambda k: values[k][0])
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        mids = [values[k][0] for k in keys]
        errs = [[values[k][0] - values[k][1] for k in keys], [values[k][2] - values[k][0] for k in keys]]
        ax.barh([f"{k[1]}/{k[2]}" for k in keys], mids, xerr=errs, capsize=3)
        ax.set_xscale("log")
        ax.set_xlabel("tracks / s (single thread)")
        ax.set_title("Throughput -- compared as a ratio, since inputs differ in size")
        ax.grid(alpha=0.3, axis="x")
        save(fig, "03_throughput.png")

    chain = [r for r in ok if r.get("test") == "chain" and r.get("chain_len")]

    # (4) Event loops, and what they cost.
    if chain:
        fig, (ax_loops, ax_time) = plt.subplots(1, 2, figsize=(11, 4.5))
        for key, points in sorted(series(chain, ("impl",), "chain_len", "event_loops").items()):
            ax_loops.plot([p[0] for p in points], [p[1] for p in points], marker="o", label=key[0])
        for key, points in sorted(series(chain, ("impl",), "chain_len", "wall_loop").items()):
            plot_series(ax_time, points, key[0])
        for label, limit in censored_points(failed, test="chain"):
            ax_time.annotate("", xy=(0.5, limit), xytext=(0.5, limit * 0.7),
                             arrowprops=dict(arrowstyle="->", color="red", alpha=0.6))
        ax_loops.set_xlabel("filters in chain")
        ax_loops.set_ylabel("event loops over the dataset")
        ax_loops.set_title("Counted, not measured")
        ax_time.set_xlabel("filters in chain")
        ax_time.set_ylabel("event-loop wall time [s]")
        ax_time.set_yscale("log")
        ax_time.set_title("...and what it costs")
        for ax in (ax_loops, ax_time):
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)
        save(fig, "04_event_loops.png")

        # (5) Bytes read vs chain length, against what the query actually asked for.
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        for key, points in sorted(series(chain, ("impl",), "chain_len", "bytes_loop").items()):
            plot_series(ax, [(x, m / 1e6, lo / 1e6, hi / 1e6) for x, m, lo, hi in points], key[0])
        # The reference line is the compressed size of the named branches. Without it the curve
        # only says "this many bytes", and the interesting question -- whether that is the
        # branches or the whole file -- cannot be read off the plot.
        expected = series(chain, ("impl",), "chain_len", "columns_zip_bytes")
        for key, points in sorted(expected.items()):
            ax.plot([p[0] for p in points], [p[1] / 1e6 for p in points], "k--", alpha=0.5,
                    label="branches named by the query")
            break
        ax.set_xlabel("filters in chain (one new branch each)")
        ax.set_ylabel("bytes read during the loop [MB]")
        ax.set_title("Columnar selectivity: what was read against what was asked for")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        # Annotated from the dataset the chain runs on, not from whichever entry
        # dataset_info.json happens to list first.
        inputs = {r.get("input") for r in chain}
        entry = next((info[name] for name in inputs if name in info), {})
        if entry:
            ax.text(0.02, 0.95,
                    f"{', '.join(sorted(i for i in inputs if i))}: "
                    f"{entry.get('file_size_bytes', 0) / 1e6:.0f} MB, "
                    f"{entry.get('n_branches', '?')} branches",
                    transform=ax.transAxes, fontsize=8, va="top")
        save(fig, "05_bytes_read.png")

    # (6) TEST 3 implementations.
    efficiency = [r for r in ok if r.get("test") == "efficiency" and not r.get("threads")]
    if efficiency:
        values = aggregate(efficiency, ("impl", "mode"), "tracks_per_s")
        keys = sorted(values, key=lambda k: values[k][0])
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        mids = [values[k][0] for k in keys]
        errs = [[values[k][0] - values[k][1] for k in keys], [values[k][2] - values[k][0] for k in keys]]
        ax.barh([f"{k[0]}/{k[1]}" for k in keys], mids, xerr=errs, capsize=3)
        ax.set_xscale("log")
        ax.set_xlabel("tracks / s")
        ax.set_title("TEST 3: attaching efficiency to every track")
        ax.grid(alpha=0.3, axis="x")
        save(fig, "06_efficiency_impls.png")

    # (7) Thread scaling -- reported last, with its caveats on the figure.
    threaded = [r for r in ok if r.get("threads")]
    if threaded:
        sweep_input = next((r.get("input") for r in threaded), None)
        limit = max_useful_threads(results_dir, sweep_input)
        fig, ax = plt.subplots(figsize=(8, 5))
        groups = series(threaded, ("machine", "test", "impl"), "threads", "wall_loop")
        for key, points in sorted(groups.items()):
            baseline = points[0][1]
            if not baseline:
                continue
            # Speedup, with the whiskers carried over from the underlying times: a ratio of two
            # noisy numbers is noisier than either, and hiding that makes a 10% wobble look
            # like a real difference between machines.
            ax.errorbar(
                [p[0] for p in points],
                [baseline / p[1] for p in points],
                yerr=[
                    [baseline / p[1] - baseline / p[3] for p in points],
                    [baseline / p[2] - baseline / p[1] for p in points],
                ],
                marker="o", capsize=3, label="/".join(str(k) for k in key),
            )
        ideal = sorted({r["threads"] for r in threaded})
        ax.plot(ideal, ideal, "k--", alpha=0.4, label="ideal")
        if limit < max(ideal):
            ax.axvline(limit, color="red", ls=":",
                       label=f"TTree cluster limit (~{limit}, {sweep_input})")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log", base=2)
        ax.set_xlabel("threads")
        ax.set_ylabel("speedup vs 1 thread")
        ax.set_title("Thread scaling (supporting result)")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3, which="both")
        fig.text(0.01, 0.01,
                 "Caveats: warm page cache; RDataFrame parallelises over TTree clusters, not "
                 "events; cling JIT and result merging are serial.",
                 fontsize=7, style="italic")
        save(fig, "07_thread_scaling.png")

        # (7b) Bytes read against thread count. On ds_l this grew from 10.2 GB at one thread to
        # 20.4 GB at four, which is the strongest clue about where the read amplification comes
        # from: the file layout cannot change between those runs, but the number of TTreeCaches
        # does. Flat here means the amplification is not per-thread read-ahead.
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        for key, points in sorted(series(threaded, ("test", "impl"), "threads", "bytes_loop").items()):
            plot_series(ax, [(x, m / 1e6, lo / 1e6, hi / 1e6) for x, m, lo, hi in points],
                        f"{key[0]}/{key[1]}")
        ax.set_xscale("log", base=2)
        ax.set_xlabel("threads")
        ax.set_ylabel("bytes read during the loop [MB]")
        ax.set_title("Does reading more threads mean reading more bytes?")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "07b_bytes_vs_threads.png")

    # (8) Where the time goes: the fixed cost against the event loop.
    phases = [r for r in ok if r.get("wall_loop") is not None]
    if phases:
        values = {}
        for name in ("wall_setup", "wall_warmup", "wall_jit", "wall_loop"):
            values[name] = aggregate(phases, ("test", "impl", "chain_len"), name)
        keys = sorted(values["wall_loop"], key=lambda k: -values["wall_loop"][k][0])[:14]
        fig, ax = plt.subplots(figsize=(8.5, 5))
        bottoms = [0.0] * len(keys)
        for name, colour in (("wall_setup", None), ("wall_warmup", None),
                             ("wall_jit", None), ("wall_loop", None)):
            heights = [values[name].get(k, (0.0,))[0] or 0.0 for k in keys]
            ax.barh([f"{k[0]}/{k[1]}" + (f"/l{k[2]}" if k[2] else "") for k in keys],
                    heights, left=bottoms, label=name[5:], color=colour)
            bottoms = [b + h for b, h in zip(bottoms, heights)]
        ax.set_xlabel("wall time [s]")
        ax.set_title("Fixed cost against the event loop: which phase dominates")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, axis="x")
        save(fig, "08_phase_breakdown.png")

    # (9) Cluster-count control: same data, different TTree layout.
    clusters = [r for r in ok if str(r.get("label", "")).startswith("clusters_")]
    if clusters:
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        for key, points in sorted(series(clusters, ("tag",), "threads", "wall_loop").items()):
            baseline = points[0][1]
            ax.plot([p[0] for p in points], [baseline / p[1] for p in points],
                    marker="o", label=f"{key[0]} clustering")
        ax.set_xscale("log", base=2)
        ax.set_xlabel("threads")
        ax.set_ylabel("speedup vs fewest threads")
        ax.set_title("Same data, different cluster count: does the plateau follow the layout?")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "09_cluster_control.png")

    # (10) Read amplification by file layout.
    layout = [r for r in ok if str(r.get("label", "")).startswith("layout_")]
    if layout:
        values = aggregate(layout, ("tag",), "read_amplification")
        keys = sorted(values, key=lambda k: values[k][0])
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        ax.barh([str(k[0]) for k in keys], [values[k][0] for k in keys])
        ax.axvline(1.0, color="green", ls="--", alpha=0.6, label="reads only what it asked for")
        ax.set_xscale("log")
        ax.set_xlabel("bytes read / compressed size of the branches named")
        ax.set_title("Read amplification by file layout")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, axis="x")
        save(fig, "10_read_amplification.png")

    # (11) Scattered against contiguous selection.
    selectivity = [r for r in ok if r.get("test") == "selectivity"]
    if selectivity:
        values = aggregate(selectivity, ("impl",), "bytes_loop")
        keys = sorted(values)
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.barh([str(k[0]) for k in keys], [values[k][0] / 1e6 for k in keys])
        ax.set_xlabel("bytes read during the loop [MB]")
        ax.set_title("Does a selection contiguous in entry order read less?")
        ax.grid(alpha=0.3, axis="x")
        save(fig, "11_selectivity.png")

    # (12) RSS over time, from the in-process sampler.
    samples = [f for f in os.listdir(results_dir) if f.startswith("rss_") and f.endswith(".csv")]
    if samples:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        drawn = 0
        for name in sorted(samples):
            times, rss = [], []
            with open(os.path.join(results_dir, name)) as f:
                for row in csv.DictReader(f):
                    try:
                        times.append(float(row["t_s"]))
                        rss.append(float(row["rss_kb"]) / 1024)
                    except (ValueError, KeyError):
                        continue
            # A trace that never moves is the wrapper-pid bug, not a flat memory profile.
            # Skipping them keeps the figure about the runs that actually have a profile.
            if len(times) < 3 or max(rss) - min(rss) < 1:
                continue
            ax.plot(times, rss, label=name[4:-4], lw=1)
            drawn += 1
            if drawn >= 12:
                break
        if drawn:
            ax.set_xlabel("time [s]")
            ax.set_ylabel("RSS [MB]")
            ax.set_title("Memory profile over time")
            ax.legend(fontsize=6)
            ax.grid(alpha=0.3)
            save(fig, "12_rss_over_time.png")
        else:
            plt.close(fig)

    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--max-threads", action="store_true",
                        help="print the cluster-implied thread cap and exit")
    parser.add_argument("--for-input", default=None,
                        help="scope --max-threads to one dataset instead of taking the maximum "
                             "over every dataset described")
    parser.add_argument("--describes", default=None,
                        help="exit 0 if dataset_info.json describes this file, 1 otherwise")
    parser.add_argument("--same-size", nargs=2, default=None, metavar=("A", "B"),
                        help="exit 0 if the two datasets hold the same number of events")
    args = parser.parse_args()

    if args.describes:
        info = load_dataset_info(args.results)
        return 0 if os.path.basename(args.describes) in info else 1

    if args.same_size:
        info = load_dataset_info(args.results)
        counts = []
        for path in args.same_size:
            entry = info.get(os.path.basename(path))
            if not entry:
                print(f"{path} is not described in dataset_info.json", file=sys.stderr)
                return 1
            counts.append(entry.get("n_events"))
        if counts[0] != counts[1]:
            print(f"event counts differ: {counts[0]} vs {counts[1]}", file=sys.stderr)
            return 1
        return 0

    if args.max_threads:
        print(max_useful_threads(args.results, args.for_input))
        return 0

    records = load_records(args.results)
    if not records:
        print(f"No records in {args.results}/raw.jsonl", file=sys.stderr)
        return 1

    records, stale = current_schema_records(records)
    if stale:
        print(f"WARNING: ignoring {len(stale)} records from an older schema "
              f"(fields changed meaning; they cannot be averaged with the current ones)")

    print(f"{len(records)} records -> {write_csv(records, args.results)}")
    failed = [r for r in records if r.get("status") != "ok"]
    if failed:
        print(f"NOTE: {len(failed)} runs failed or timed out; they are drawn as lower bounds: "
              f"{', '.join(sorted(r['label'] for r in failed)[:10])}")

    if not args.csv_only:
        for path in plot_all(records, args.results):
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
