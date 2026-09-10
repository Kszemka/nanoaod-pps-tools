#!/usr/bin/env python3
"""
Turns results/raw.jsonl into a flat CSV and the plots.

Plot order follows how much the result can be trusted, not how interesting it looks. The
deterministic quantities -- memory against dataset size, bytes read, number of event loops --
come first; the thread-scaling curve is last and carries its caveats printed on the figure,
because on a warm cache with a fixed JIT cost it is the most fragile thing measured here.
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

CSV_FIELDS = [
    "label", "status", "machine", "test", "impl", "mode", "threads", "chain_len",
    "input", "n_events", "n_tracks", "wall_setup", "wall_loop", "bytes_setup",
    "bytes_loop", "bytes_total", "peak_rss_kb", "time_maxrss_kb", "cpu_percent",
    "elapsed_s", "events_per_s", "tracks_per_s", "event_loops", "root_version",
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
    """Median across repeats. The first repeat is not special-cased: each run is a fresh
    process, so none of them get to reuse a warm JIT cache."""
    buckets = defaultdict(list)
    for record in records:
        if record.get("status") != "ok" or record.get(value_field) is None:
            continue
        key = tuple(record.get(field) for field in key_fields)
        buckets[key].append(record[value_field])
    return {key: median(values) for key, values in buckets.items()}


def max_useful_threads(results_dir):
    """Thread counts beyond ~clusters/4 measure scheduling noise, not scaling."""
    info_path = os.path.join(results_dir, "dataset_info.json")
    if not os.path.exists(info_path):
        return 999
    with open(info_path) as f:
        info = json.load(f)
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
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for test in ("efficiency", "chain"):
            for impl in ("jit", "rdf-lazy", "python"):
                points = sorted(
                    (r["n_events"], r["peak_rss_kb"] / 1024)
                    for r in scale
                    if r["test"] == test and r["impl"] == impl and r.get("n_events")
                )
                if points:
                    ax.plot(*zip(*points), marker="o", label=f"{test}/{impl}")
        ax.set_xlabel("events")
        ax.set_ylabel("peak RSS [MB]")
        ax.set_xscale("log")
        ax.set_title("Memory vs dataset size: streaming O(1) against materialised O(N)")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        save(fig, "01_rss_vs_size.png")

        # (2) Wall time vs dataset size.
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for test in ("efficiency", "chain"):
            for impl in ("jit", "rdf-lazy", "python"):
                points = sorted(
                    (r["n_events"], r["wall_loop"])
                    for r in scale
                    if r["test"] == test and r["impl"] == impl and r.get("n_events")
                )
                if points:
                    ax.plot(*zip(*points), marker="o", label=f"{test}/{impl}")
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
        labels = [f"{k[1]}/{k[2]}" for k in values]
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.barh(labels, list(values.values()))
        ax.set_xscale("log")
        ax.set_xlabel("tracks / s (single thread)")
        ax.set_title("Throughput -- compared as a ratio, since inputs differ in size")
        ax.grid(alpha=0.3, axis="x")
        save(fig, "03_throughput.png")

    chain = [r for r in ok if r.get("test") == "chain" and r.get("chain_len")]

    # (4) Event loops, and what they cost.
    if chain:
        fig, (ax_loops, ax_time) = plt.subplots(1, 2, figsize=(11, 4))
        by_impl = defaultdict(dict)
        for record in chain:
            by_impl[record["impl"]][record["chain_len"]] = record
        for impl, per_len in sorted(by_impl.items()):
            lengths = sorted(per_len)
            ax_loops.plot(
                lengths, [per_len[n]["event_loops"] for n in lengths], marker="o", label=impl
            )
            ax_time.plot(
                lengths, [per_len[n]["wall_loop"] for n in lengths], marker="o", label=impl
            )
        ax_loops.set_xlabel("filters in chain")
        ax_loops.set_ylabel("event loops over the dataset")
        ax_loops.set_title("Counted, not measured")
        ax_time.set_xlabel("filters in chain")
        ax_time.set_ylabel("wall time [s]")
        ax_time.set_yscale("log")
        ax_time.set_title("...and what it costs")
        for ax in (ax_loops, ax_time):
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)
        save(fig, "04_event_loops.png")

        # (5) Bytes read vs chain length.
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for impl, per_len in sorted(by_impl.items()):
            lengths = sorted(per_len)
            ax.plot(
                lengths,
                [per_len[n]["bytes_loop"] / 1e6 for n in lengths],
                marker="o",
                label=impl,
            )
        ax.set_xlabel("filters in chain (one new branch each)")
        ax.set_ylabel("bytes read during the loop [MB]")
        ax.set_title("Columnar selectivity: only the branches the query names are read")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        # Both implementations read the same bytes: ROOT reads whole baskets, and events
        # surviving an earlier filter are scattered across all of them, so short-circuiting
        # saves predicate evaluations but not I/O. The result here is the ratio to file size.
        info_path = os.path.join(results_dir, "dataset_info.json")
        if os.path.exists(info_path):
            with open(info_path) as f:
                entry = next(iter(json.load(f).values()), {})
            total_mb = entry.get("file_size_bytes", 0) / 1e6
            if total_mb:
                ax.text(
                    0.02, 0.95,
                    f"whole file: {total_mb:.0f} MB, {entry.get('n_branches', '?')} branches",
                    transform=ax.transAxes, fontsize=8, va="top",
                )
        save(fig, "05_bytes_read.png")

    # (6) TEST 3 implementations.
    efficiency = [r for r in ok if r.get("test") == "efficiency" and not r.get("threads")]
    if efficiency:
        values = aggregate(efficiency, ("impl", "mode"), "tracks_per_s")
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.barh([f"{k[0]}/{k[1]}" for k in values], list(values.values()))
        ax.set_xscale("log")
        ax.set_xlabel("tracks / s")
        ax.set_title("TEST 3: attaching efficiency to every track")
        ax.grid(alpha=0.3, axis="x")
        save(fig, "06_efficiency_impls.png")

    # (7) Thread scaling -- reported last, with its caveats on the figure.
    threaded = [r for r in ok if r.get("threads")]
    if threaded:
        limit = max_useful_threads(results_dir)
        fig, ax = plt.subplots(figsize=(7.5, 5))
        by_group = defaultdict(dict)
        for record in threaded:
            by_group[(record["machine"], record["test"], record["impl"])][record["threads"]] = record["wall_loop"]
        for (machine, test, impl), per_threads in sorted(by_group.items()):
            counts = sorted(per_threads)
            baseline = per_threads.get(min(counts))
            if not baseline:
                continue
            ax.plot(
                counts,
                [baseline / per_threads[n] for n in counts],
                marker="o",
                label=f"{machine}/{test}/{impl}",
            )
        ideal = sorted({r["threads"] for r in threaded})
        ax.plot(ideal, ideal, "k--", alpha=0.4, label="ideal")
        if limit < max(ideal):
            ax.axvline(limit, color="red", ls=":", label=f"TTree cluster limit (~{limit})")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log", base=2)
        ax.set_xlabel("threads")
        ax.set_ylabel("speedup vs 1 thread")
        ax.set_title("Thread scaling (supporting result)")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3, which="both")
        fig.text(
            0.01, 0.01,
            "Caveats: warm page cache; RDataFrame parallelises over TTree clusters, not events; "
            "cling JIT and result merging are serial.",
            fontsize=7, style="italic",
        )
        save(fig, "07_thread_scaling.png")

    # (8) RSS over time, from the sampler.
    samples = [f for f in os.listdir(results_dir) if f.startswith("rss_") and f.endswith(".csv")]
    if samples:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for name in sorted(samples)[:12]:
            times, values = [], []
            with open(os.path.join(results_dir, name)) as f:
                for row in csv.DictReader(f):
                    try:
                        times.append(float(row["t_s"]))
                        values.append(float(row["rss_kb"]) / 1024)
                    except (ValueError, KeyError):
                        continue
            if times:
                ax.plot(times, values, label=name[4:-4], lw=1)
        ax.set_xlabel("time [s]")
        ax.set_ylabel("RSS [MB]")
        ax.set_title("Memory profile over time")
        ax.legend(fontsize=6)
        ax.grid(alpha=0.3)
        save(fig, "08_rss_over_time.png")

    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--max-threads", action="store_true", help="print the cluster-implied thread cap and exit")
    args = parser.parse_args()

    if args.max_threads:
        print(max_useful_threads(args.results))
        return 0

    records = load_records(args.results)
    if not records:
        print(f"No records in {args.results}/raw.jsonl", file=sys.stderr)
        return 1

    print(f"{len(records)} records -> {write_csv(records, args.results)}")
    failed = [r for r in records if r.get("status") != "ok"]
    if failed:
        print(f"WARNING: {len(failed)} runs failed or timed out: "
              f"{', '.join(sorted(r['label'] for r in failed)[:10])}")

    if not args.csv_only:
        for path in plot_all(records, args.results):
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
