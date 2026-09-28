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
import re
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


def dedupe_labels(records):
    """
    Keeps the last record per label when a results directory holds more than one campaign.

    A label names one configuration within one run of the harness, so a repeated label means
    the directory was appended to -- typically a job that died partway and was resubmitted.
    The abandoned attempts are the early ones and they ran against a cold page cache: in the
    thread sweep the discarded r1_*_t1 runs came in at 5.5 s against 4.1 s for the same label
    in the run that finished. Taking the median across all of them raises the single-thread
    baseline and inflates every speedup computed from it.

    Last rather than first: the run that completed wrote the later records.
    """
    last_index = {}
    for index, record in enumerate(records):
        last_index[record.get("label")] = index
    keep = [r for i, r in enumerate(records) if last_index[r.get("label")] == i]
    return keep, len(records) - len(keep)


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


# The four cmd_core experiments, identified by label prefix rather than by test/impl/threads.
# Selecting on the columns instead is what let the RNTuple and cluster-control runs merge into
# the thread-scaling curves: they carry the same test, impl and thread count as the real sweep.
CORE_EXPERIMENTS = ("strong", "weak", "qstruct", "impl")
CORE_TEST_LABEL = {
    "filter": "single filter",
    "chain": "5-filter chain",
    "efficiency": "efficiency column",
}
CORE_TEST_COLOUR = {"filter": "#4575b4", "chain": "#1b7837", "efficiency": "#d73027"}


def core_rows(records, experiment):
    """Records from one cmd_core experiment, matched on the r<N>_<experiment>_ label prefix."""
    pattern = re.compile(rf"r\d+_{experiment}_")
    return [r for r in records if pattern.match(str(r.get("label", "")))]


def curve(records, x_field, value_field):
    """Median of value_field per x, as sorted ([x], [y]). Empty when nothing qualifies."""
    buckets = defaultdict(list)
    for r in records:
        if r.get(x_field) is not None and r.get(value_field) is not None:
            buckets[r[x_field]].append(r[value_field])
    xs = sorted(buckets)
    return xs, [median(buckets[x]) for x in xs]


def measured_serial_fraction(records):
    """
    Serial fraction read off the phase timings at the lowest thread count, not fitted.

    Setup and cling JIT do not parallelise, so they are the serial region the fitted s should
    correspond to. Two numbers that disagree mean the degradation has a cause outside the
    code's own serial part, which is exactly what USL's coherency term is for.
    """
    threaded = [r for r in records if r.get("threads") and r.get("wall_loop") is not None]
    if not threaded:
        return None
    lowest = min(r["threads"] for r in threaded)
    at_one = [r for r in threaded if r["threads"] == lowest]
    fixed = median([(r.get("wall_setup") or 0) + (r.get("wall_jit") or 0) for r in at_one])
    loop = median([r["wall_loop"] for r in at_one])
    total = fixed + loop
    return fixed / total if total else None


def plot_core(ok, results_dir, plt, save, outputs):
    """
    The core campaign: strong scaling, weak scaling, query structure, implementations.

    Ordered by what the reader needs first rather than by how the runs happened: the two
    scaling laws lead, memory follows them because it is the cost that the speedup curve
    cannot show, and the two single-threaded experiments come last.
    """
    strong = core_rows(ok, "strong")
    weak = core_rows(ok, "weak")
    qstruct = core_rows(ok, "qstruct")
    impls = core_rows(ok, "impl")

    ticks = sorted({r["threads"] for r in strong + weak if r.get("threads")}) or [1]

    def thread_axis(ax):
        ax.set_xscale("log", base=2)
        ax.set_xticks(ticks)
        ax.set_xticklabels([str(t) for t in ticks])
        ax.minorticks_off()
        ax.set_xlabel("threads")

    # Speedup goes on a log axis to match the thread axis, so ideal scaling is the diagonal.
    # On a linear y the ideal line curves away exponentially and takes the whole figure with
    # it: the measured curves, which are the subject, end up squashed against the bottom.
    def speedup_axis(ax, marks):
        ax.set_yscale("log", base=2)
        ax.set_yticks(marks)
        ax.set_yticklabels([str(t) for t in marks])
        ax.set_ylabel("speedup vs 1 thread")

    fitted_s = None

    # (1) Strong scaling: the same 11.1 M events, more threads. Amdahl applies here and only
    # here. It is drawn not because it fits but because it cannot -- monotonic in n for any
    # serial fraction, it has no way to express a curve that turns back down. USL adds the
    # coherency term that does, and its maximum is the number of practical interest.
    rows = {test: scalability_rows(strong, test) for test in CORE_TEST_LABEL}
    if any(rows.values()):
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        for test, pretty in CORE_TEST_LABEL.items():
            if not rows[test]:
                continue
            threads = [r["threads"] for r in rows[test]]
            ax.plot(threads, [r["speedup"] for r in rows[test]], marker="o", lw=2,
                    color=CORE_TEST_COLOUR[test], label=pretty)
        ax.plot(ticks, ticks, ls="-", lw=1, color="#bbbbbb", label="ideal ($S = n$)")

        if rows["chain"]:
            measured = [(r["threads"], r["speedup"]) for r in rows["chain"]]
            grid = [t for t in range(1, max(ticks) + 1)]
            fitted_s = fit_amdahl(measured)
            sigma, kappa = fit_usl(measured)
            ax.plot(grid, [1 / (fitted_s + (1 - fitted_s) / n) for n in grid], ls="--", lw=1.6,
                    color="#888888", label=f"Amdahl, $s$={fitted_s:.3f}")
            ax.plot(grid, [n / (1 + sigma * (n - 1) + kappa * n * (n - 1)) for n in grid],
                    ls=":", lw=1.8, color="#333333",
                    label=fr"USL, $\sigma$={sigma:.3f}, $\kappa$={kappa:.4f}")
            print(f"  Amdahl serial fraction s = {fitted_s:.4f} (ceiling {1 / fitted_s:.2f}x)")
            print(f"  USL sigma = {sigma:.4f}, kappa = {kappa:.5f}")
            if kappa > 0:
                peak = ((1 - sigma) / kappa) ** 0.5
                ax.axvline(peak, color="#333333", ls=":", lw=1, alpha=0.5)
                print(f"  USL predicted optimum = {peak:.1f} threads")

            observed = measured_serial_fraction(strong)
            if observed is not None:
                ax.text(0.02, 0.97,
                        f"fitted $s$ = {fitted_s:.3f}\n"
                        f"measured setup+JIT share at 1 thread = {observed:.3f}",
                        transform=ax.transAxes, va="top", fontsize=8)
                print(f"  measured serial share (setup+JIT) = {observed:.4f}")

        thread_axis(ax)
        speedup_axis(ax, ticks)
        ax.set_title("T1 strong scaling: fixed problem size, more threads")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "01_speedup_amdahl.png")

        # (2) The same data as a fraction of the threads paid for. A speedup of 5 is a
        # different statement at 8 threads than at 48, and only this axis says which.
        fig, ax = plt.subplots(figsize=(8, 4.8))
        for test, pretty in CORE_TEST_LABEL.items():
            if not rows[test]:
                continue
            ax.plot([r["threads"] for r in rows[test]],
                    [r["efficiency"] * 100 for r in rows[test]],
                    marker="o", lw=2, color=CORE_TEST_COLOUR[test], label=pretty)
        ax.axhline(100, color="#bbbbbb", lw=1)
        thread_axis(ax)
        ax.set_ylabel("parallel efficiency [%]")
        ax.set_ylim(0, 105)
        ax.set_title("T1 parallel efficiency: speedup per thread paid for")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "02_parallel_efficiency.png")

    # (3) Weak scaling: N threads against ds_xN, so work per thread is constant. Ideal is a
    # flat wall-time line, and the question is the opposite of T1's -- not "is the same job
    # faster" but "does a job that grows with the machine still finish in the same time".
    if weak:
        fig, (ax_t, ax_s) = plt.subplots(1, 2, figsize=(12, 4.8))
        for test, pretty in CORE_TEST_LABEL.items():
            xs, ys = curve([r for r in weak if r.get("test") == test], "threads", "wall_loop")
            if len(xs) < 2:
                continue
            colour = CORE_TEST_COLOUR[test]
            ax_t.plot(xs, ys, marker="o", lw=2, color=colour, label=pretty)
            ax_t.axhline(ys[0], color=colour, ls=":", lw=1, alpha=0.5)
            ax_s.plot(xs, [n * ys[0] / y for n, y in zip(xs, ys)], marker="o", lw=2,
                      color=colour, label=pretty)
        weak_ticks = sorted({r["threads"] for r in weak if r.get("threads")}) or ticks
        ax_s.plot(weak_ticks, weak_ticks, lw=1, color="#bbbbbb", label="ideal ($S = n$)")
        if fitted_s is not None:
            ax_s.plot(weak_ticks, [n - fitted_s * (n - 1) for n in weak_ticks], ls="--", lw=1.6,
                      color="#888888", label=f"Gustafson, $s$={fitted_s:.3f}")
        for ax in (ax_t, ax_s):
            ax.set_xscale("log", base=2)
            ax.set_xticks(weak_ticks)
            ax.set_xticklabels([str(t) for t in weak_ticks])
            ax.minorticks_off()
            ax.set_xlabel("threads (N threads on ds_xN)")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3, which="both")
        ax_t.set_ylabel("event-loop wall time [s]")
        ax_t.set_title("Constant work per thread: flat is ideal")
        speedup_axis(ax_s, weak_ticks)
        ax_s.set_ylabel("scaled speedup")
        ax_s.set_title("T2 weak scaling against Gustafson's law")
        save(fig, "03_weak_scaling.png")

    # (4) What the speedup curve cannot show. Every worker gets its own TTreeCache and its own
    # decompression buffers, which is why node memory rather than core count is what ends up
    # limiting the usable thread count.
    if strong:
        fig, ax = plt.subplots(figsize=(8, 4.8))
        for test, pretty in CORE_TEST_LABEL.items():
            sub = [r for r in strong if r.get("test") == test]
            for key, points in sorted(series(sub, ("test",), "threads", "peak_rss_kb").items()):
                plot_series(ax, [(x, m / 1024, lo / 1024, hi / 1024) for x, m, lo, hi in points],
                            pretty, color=CORE_TEST_COLOUR[test])
        thread_axis(ax)
        ax.set_ylabel("peak RSS [MB]")
        ax.set_title("T3 memory against thread count (fixed problem size)")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "04_rss_vs_threads.png")

    # (5) Memory along the weak-scaling series. Work per thread is constant here, so anything
    # steeper than linear in the thread count is the cost of coordination rather than of data.
    if weak:
        fig, ax = plt.subplots(figsize=(8, 4.8))
        for test, pretty in CORE_TEST_LABEL.items():
            xs, ys = curve([r for r in weak if r.get("test") == test], "n_events", "peak_rss_kb")
            if len(xs) < 2:
                continue
            ax.plot(xs, [y / 1024 for y in ys], marker="o", lw=2,
                    color=CORE_TEST_COLOUR[test], label=pretty)
        ax.set_xscale("log")
        ax.set_xlabel("events (growing with the thread count)")
        ax.set_ylabel("peak RSS [MB]")
        ax.set_title("T3 memory along the weak-scaling series")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "05_rss_vs_size.png")

    # (6) RSS over time, restricted to the strong sweep so the curves differ in one variable.
    outputs.extend(plot_rss_profile(results_dir, plt, name="06_rss_over_time.png",
                                    prefix="r1_strong_"))

    # (7) Query structure. Single-threaded on purpose: the number of event loops is a property
    # of how the query was written, not of the machine it ran on.
    if qstruct:
        fig, (ax_loops, ax_time) = plt.subplots(1, 2, figsize=(11.5, 4.6))
        for key, points in sorted(series(qstruct, ("impl",), "chain_len", "event_loops").items()):
            ax_loops.plot([p[0] for p in points], [p[1] for p in points], marker="o",
                          label=key[0])
        for key, points in sorted(series(qstruct, ("impl",), "chain_len", "wall_loop").items()):
            plot_series(ax_time, points, key[0])
        for ax in (ax_loops, ax_time):
            ax.set_xlabel("filters in chain")
            ax.set_xticks(sorted({r["chain_len"] for r in qstruct if r.get("chain_len")}))
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)
        ax_loops.set_ylabel("event loops over the dataset")
        ax_loops.set_title("Counted, not measured")
        ax_time.set_ylabel("event-loop wall time [s]")
        ax_time.set_title("T4 ...and what it costs")
        save(fig, "07_query_structure.png")

    # (8) Implementations, and where their time goes. Same file, same codec, same events for
    # every bar -- the comparison a reader is most likely to challenge is the one that must
    # not straddle two datasets.
    if impls:
        values = aggregate(impls, ("test", "impl", "mode"), "tracks_per_s")
        keys = sorted(values, key=lambda k: values[k][0])
        fig, (ax_tp, ax_ph) = plt.subplots(1, 2, figsize=(13, 5))
        ax_tp.barh([f"{k[0]}/{k[1]}/{k[2]}" for k in keys], [values[k][0] for k in keys])
        ax_tp.set_xscale("log")
        ax_tp.set_xlabel("tracks / s (single thread)")
        ax_tp.set_title("T5 throughput on one dataset")
        ax_tp.grid(alpha=0.3, axis="x")

        phases = {name: aggregate(impls, ("test", "impl", "mode"), name)
                  for name in ("wall_setup", "wall_warmup", "wall_jit", "wall_loop")}
        bottoms = [0.0] * len(keys)
        names = [f"{k[0]}/{k[1]}/{k[2]}" for k in keys]
        for name in ("wall_setup", "wall_warmup", "wall_jit", "wall_loop"):
            heights = [phases[name].get(k, (0.0,))[0] or 0.0 for k in keys]
            ax_ph.barh(names, heights, left=bottoms, label=name[5:])
            bottoms = [b + h for b, h in zip(bottoms, heights)]
        ax_ph.set_xscale("log")
        ax_ph.set_xlabel("wall time [s]")
        ax_ph.set_title("Fixed cost against the event loop")
        ax_ph.legend(fontsize=8)
        ax_ph.grid(alpha=0.3, axis="x")
        save(fig, "08_implementations.png")


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

    # A results directory holds one campaign or the other, never a useful mix: the figures
    # below select by test and thread count, which the core campaign's four experiments share.
    # Drawing both sets would median a strong-scaling point together with a weak-scaling one.
    if any(core_rows(ok, experiment) for experiment in CORE_EXPERIMENTS):
        plot_core(ok, results_dir, plt, save, outputs)
        return outputs

    scale = [r for r in ok if str(r.get("label", "")).startswith("scale_")]

    # One curve per approach, not per (test, impl) pair. Plotting the chain and the efficiency
    # test together put six lines on one axis, of which three were the same three approaches
    # measured on a different query -- the comparison the figure is about got lost in them.
    IMPL_NAME = {
        "rdf-lazy": "RDataFrame",
        "uproot": "uproot + awkward",
        "python": "Python + numpy",
    }
    scale_chain = [r for r in scale if r.get("test") == "chain" and r.get("impl") in IMPL_NAME]

    # (1) Peak RSS vs dataset size -- the headline result.
    if scale_chain:
        fig, (ax_gross, ax_net) = plt.subplots(1, 2, figsize=(11, 4.5))
        for ax, field, title in (
            (ax_gross, "peak_rss_kb", "peak RSS"),
            # The interpreter, PyROOT and numpy account for ~470 MB before any data is read, so
            # on the smaller datasets the gross peak is mostly a constant and hides the very
            # difference the plot is about.
            (ax_net, "peak_rss_net_kb", "peak RSS minus baseline"),
        ):
            for key, points in sorted(series(scale_chain, ("impl",), "n_events", field).items()):
                plot_series(ax, [(x, m / 1024, lo / 1024, hi / 1024) for x, m, lo, hi in points],
                            IMPL_NAME[key[0]])
            ax.set_xlabel("events")
            ax.set_ylabel(f"{title} [MB]")
            ax.set_xscale("log")
            ax.legend(fontsize=9)
            ax.grid(alpha=0.3)
        fig.suptitle("Memory vs dataset size, single thread: "
                     "streaming O(1) against materialised O(N)")
        save(fig, "01_rss_vs_size.png")

        # (2) Wall time vs dataset size.
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for key, points in sorted(series(scale_chain, ("impl",), "n_events", "wall_loop").items()):
            plot_series(ax, points, IMPL_NAME[key[0]])
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("events")
        ax.set_ylabel("event-loop wall time [s]")
        ax.set_title("Time vs dataset size (3-filter chain, single thread)")
        ax.legend(fontsize=9)
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

    # The chain-length sweep is single-threaded and untagged by construction. Selecting on
    # test and chain_len alone also swept in the thread sweep and the layout, order and style
    # variants, all of which carry chain_len=5: the rdf-lazy point at length 5 was a median
    # over 24 records, 21 of them multi-threaded, which is why it read more bytes than
    # rdf-report at the same length while matching it exactly at every shorter length.
    chain = [r for r in ok if r.get("test") == "chain" and r.get("chain_len")
             and not r.get("threads") and not r.get("tag")
             and "order-" not in str(r.get("label", "")) and "style-" not in str(r.get("label", ""))]

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
        thread_counts = sorted({r["threads"] for r in threaded})

        # A log2 axis only labels powers of two, so 48 -- the core count of the node and the
        # whole point of the sweep -- was drawn but left unlabelled between 2^5 and 2^6.
        def label_thread_axis(ax):
            ax.set_xscale("log", base=2)
            ax.set_xticks(thread_counts)
            ax.set_xticklabels([str(t) for t in thread_counts])
            ax.minorticks_off()

        fig, ax = plt.subplots(figsize=(8, 5))
        # Seconds rather than speedup. A ratio hides how much work each curve actually
        # represents -- filter and chain differ by 2.7x at one thread -- and it also hides that
        # every curve turns back up after its minimum, which is the result this plot is for.
        groups = series(threaded, ("test", "impl"), "threads", "wall_loop")
        for key, points in sorted(groups.items()):
            plot_series(ax, points, f"{key[0]}/{key[1]}")
        thread_max = max(thread_counts)
        if limit < thread_max:
            ax.axvline(limit, color="red", ls=":",
                       label=f"TTree cluster limit (~{limit}, {sweep_input})")
        label_thread_axis(ax)
        ax.set_xlabel("threads")
        ax.set_ylabel("event-loop wall time [s]")
        ax.set_title(f"Thread scaling ({sweep_input})")
        ax.legend(fontsize=8)
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
        label_thread_axis(ax)
        ax.set_xlabel("threads")
        ax.set_ylabel("bytes read during the loop [MB]")
        ax.set_title("Does reading more threads mean reading more bytes?")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "07b_bytes_vs_threads.png")

        # (7c) Memory against thread count. Every worker gets its own TTreeCache and its own
        # decompression buffers, so this is the cost of parallelism that the speedup curve
        # cannot show: on ds_x32 the slope is a flat ~240 MB per thread, which makes node
        # memory -- not core count -- the thing that limits how many threads are usable.
        fig, ax = plt.subplots(figsize=(7.5, 4.5))
        for key, points in sorted(series(threaded, ("test", "impl"), "threads", "peak_rss_kb").items()):
            plot_series(ax, [(x, m / 1024, lo / 1024, hi / 1024) for x, m, lo, hi in points],
                        f"{key[0]}/{key[1]}")
        label_thread_axis(ax)
        ax.set_xlabel("threads")
        ax.set_ylabel("peak RSS [MB]")
        ax.set_title(f"Memory vs thread count ({sweep_input})")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "07c_rss_vs_threads.png")

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
    #
    # Was every trace in the directory, alphabetically, capped at twelve: a dozen unrelated runs
    # on one axis, labelled with raw filenames. One family at a time across thread counts turns
    # it into a controlled comparison -- same query, same data, one variable.
    for path in plot_rss_profile(results_dir, plt):
        outputs.append(path)

    return outputs


def read_rss_trace(path):
    times, rss = [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                times.append(float(row["t_s"]))
                rss.append(float(row["rss_kb"]) / 1024)
            except (ValueError, KeyError):
                continue
    return times, rss


def plot_rss_profile(results_dir, plt, name="12_rss_over_time.png", prefix=None):
    """
    Memory over time for one benchmark family, one curve per thread count.

    Picks the family with the most thread variants, and among ties the one with the most
    samples -- traces are taken every 0.1 s, so a run of a few seconds leaves under a dozen
    points and a sparse family would draw a misleadingly angular profile.

    prefix restricts the choice to one experiment. Without it the core campaign's weak sweep
    can win the tie-break, and its curves differ in dataset as well as in thread count.
    """
    families = defaultdict(dict)
    for name_csv in os.listdir(results_dir):
        if not (name_csv.startswith("rss_") and name_csv.endswith(".csv") and "_t" in name_csv):
            continue
        if prefix and not name_csv.startswith(f"rss_{prefix}"):
            continue
        base, _, tail = name_csv[4:-4].rpartition("_t")
        if not tail.isdigit():
            continue
        families[base][int(tail)] = os.path.join(results_dir, name_csv)
    if not families:
        return []

    def family_weight(item):
        base, members = item
        return (len(members), sum(len(read_rss_trace(p)[0]) for p in members.values()))

    base, members = max(families.items(), key=family_weight)
    traces = []
    for threads in sorted(members):
        times, rss = read_rss_trace(members[threads])
        # A flat trace is the wrapper-pid bug -- the sampler followed `timeout`, not the
        # benchmark -- and a near-empty one cannot show a profile either way.
        if len(times) < 3 or max(rss) - min(rss) < 1:
            continue
        traces.append((threads, times, rss))
    if len(traces) < 2:
        return []

    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    colours = plt.get_cmap("viridis")
    # The sampler is a Python thread and the event loop holds the GIL in C++, so it is starved
    # exactly where the profile matters: a 48-thread run leaves ~10 samples, one of them after
    # the loop. Solid means consecutive samples, dashed means interpolation across a gap, so
    # the figure cannot be read as a measured ramp where nothing was measured.
    gap = 1.0
    for index, (threads, times, rss) in enumerate(traces):
        colour = colours(index / max(len(traces) - 1, 1))
        label = f"{threads} thread" + ("" if threads == 1 else "s")
        for point in range(len(times) - 1):
            ax.plot(times[point:point + 2], rss[point:point + 2], lw=1.8, color=colour,
                    ls="--" if times[point + 1] - times[point] > gap else "-",
                    label=label if point == 0 else None)
        ax.plot(times, rss, "o", color=colour, markersize=3.5)
    ax.set_xlabel("time since process start [s]")
    ax.set_ylabel("resident memory [MB]")
    ax.set_title(f"Memory profile over the run, by thread count ({base})")
    ax.legend(title="ImplicitMT", fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax.text(0.99, 0.02,
            "dots: samples   solid: consecutive   dashed: interpolated across an unsampled gap",
            transform=ax.transAxes, ha="right", fontsize=7, style="italic", color="#555555")
    fig.tight_layout()
    path = os.path.join(results_dir, name)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return [path]


IMPL_LABEL = {
    "rdf-lazy": "RDataFrame (C++ JIT)",
    "uproot": "uproot + awkward",
    "python": "Python + numpy",
}
IMPL_STYLE = {
    "rdf-lazy": dict(color="#1b7837", marker="o"),
    "uproot": dict(color="#4575b4", marker="s"),
    "python": dict(color="#d73027", marker="^"),
}


def fit_amdahl(points):
    """Serial fraction s minimising relative error of S(n) = 1 / (s + (1 - s) / n)."""
    best = (float("inf"), 0.0)
    for step in range(1, 2000):
        s = step / 2000
        error = sum((1 / (s + (1 - s) / n) / measured - 1) ** 2 for n, measured in points)
        best = min(best, (error, s))
    return best[1]


def fit_usl(points):
    """
    Contention and coherency of S(n) = n / (1 + sigma(n-1) + kappa*n(n-1)).

    Amdahl's law is this with kappa = 0, and it cannot bend back down: it is monotonic in n for
    any serial fraction. The measured curves do bend down, so what the fit establishes is not
    goodness of match but that kappa is distinguishable from zero.
    """
    best = (float("inf"), 0.0, 0.0)
    for sigma_step in range(0, 400):
        sigma = sigma_step / 1000
        for kappa_step in range(0, 400):
            kappa = kappa_step / 20000
            error = sum((n / (1 + sigma * (n - 1) + kappa * n * (n - 1)) / measured - 1) ** 2
                        for n, measured in points)
            if error < best[0]:
                best = (error, sigma, kappa)
    return best[1], best[2]


def scalability_rows(records, test, dataset=None):
    """
    (threads, seconds, throughput, speedup, efficiency, cpu) for one benchmark.

    dataset=None means "whatever these records ran on", which is what the core campaign wants:
    its strong-scaling records are one dataset by construction, and its weak-scaling records
    are deliberately several.
    """
    runs = defaultdict(list)
    for r in records:
        if (r.get("status") == "ok" and r.get("test") == test
                and r.get("threads") and (dataset is None or r.get("input") == dataset)):
            runs[r["threads"]].append(r)
    if not runs:
        return []
    baseline = median([x["wall_loop"] for x in runs[min(runs)]])
    rows = []
    for threads in sorted(runs):
        seconds = median([x["wall_loop"] for x in runs[threads]])
        events = median([x["n_events"] for x in runs[threads]])
        rows.append({
            "threads": threads,
            "seconds": seconds,
            "throughput": events / seconds,
            "speedup": baseline / seconds,
            "efficiency": baseline / seconds / threads,
            "cpu": median([x["cpu_percent"] for x in runs[threads] if x.get("cpu_percent")] or [0]),
        })
    return rows


def plot_thesis(records, out_dir):
    """
    One figure per thesis subsection, each carrying a single claim.

    The campaign figures show every variant that was measured, which is right for deciding what
    happened and wrong for a thesis: a reader given six curves has to be told which two matter.
    These four are the ones the text actually argues from.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = [r for r in records if r.get("status") == "ok"]
    os.makedirs(out_dir, exist_ok=True)
    outputs = []

    def save(fig, name):
        path = os.path.join(out_dir, name)
        fig.tight_layout()
        fig.savefig(path, dpi=200)
        plt.close(fig)
        outputs.append(path)

    scale = [r for r in ok if str(r.get("label", "")).startswith("scale_chain")
             and r.get("impl") in IMPL_LABEL]

    # (1) Memory. Linear y on purpose: the argument is that one line stays flat while the
    # others climb off the top of the axis, and a log axis would flatter the losers.
    if scale:
        fig, ax = plt.subplots(figsize=(7, 4.6))
        for impl in ("python", "uproot", "rdf-lazy"):
            points = sorted((r["n_events"], r["peak_rss_kb"] / 1024) for r in scale
                            if r["impl"] == impl)
            if not points:
                continue
            ax.plot([p[0] / 1e6 for p in points], [p[1] / 1024 for p in points],
                    label=IMPL_LABEL[impl], lw=2, markersize=6, **IMPL_STYLE[impl])
        ax.set_xlabel("dataset size [million events]")
        ax.set_ylabel("peak resident memory [GB]")
        ax.set_title("Peak memory vs dataset size (single thread)")
        ax.legend()
        ax.grid(alpha=0.3)
        save(fig, "bench_memory.png")

        # (2) Time. Log-log here, because the spread is 1055 s against 8.5 s and a linear axis
        # would collapse both fast implementations onto the x axis.
        fig, ax = plt.subplots(figsize=(7, 4.6))
        for impl in ("python", "uproot", "rdf-lazy"):
            points = sorted((r["n_events"], r["wall_loop"]) for r in scale if r["impl"] == impl)
            if not points:
                continue
            ax.plot([p[0] / 1e6 for p in points], [p[1] for p in points],
                    label=IMPL_LABEL[impl], lw=2, markersize=6, **IMPL_STYLE[impl])
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("dataset size [million events]")
        ax.set_ylabel("processing time [s]")
        ax.set_title("Processing time vs dataset size (single thread, 3-filter chain)")
        ax.legend()
        ax.grid(alpha=0.3, which="both")
        save(fig, "bench_time.png")

    # (3) Query structure: same data, same answer, four ways of asking. Horizontal bars because
    # the labels are sentences, and sorted so the reader sees the cost ordering immediately.
    #
    # The last two variants were measured in lazy mode, not through Report(), so they are
    # described by what they share with it -- a single event loop -- rather than by the call.
    variants = [
        ("chain_rdf-eager_l5", "Count() after every filter\n(6 event loops)", "#d73027"),
        ("chain_rdf-report_l5", "Report()\n(1 event loop)", "#1b7837"),
        ("chain_order-selective-first", "1 event loop + most\nselective filter first", "#1b7837"),
        ("chain_style-callable", "1 event loop + predicate as\ncompiled C++ function", "#1b7837"),
    ]
    by_variant = defaultdict(list)
    for r in ok:
        label = str(r.get("label", ""))
        if "_" in label and r.get("input") == "ds_x8.root":
            by_variant[label.split("_", 1)[1]].append(r)
    rows = [(text, median([x["wall_loop"] for x in by_variant[key]]), colour)
            for key, text, colour in variants if by_variant.get(key)]
    if rows:
        fig, ax = plt.subplots(figsize=(7.5, 4.2))
        ax.barh([r[0] for r in rows], [r[1] for r in rows],
                color=[r[2] for r in rows], alpha=0.85)
        for index, row in enumerate(rows):
            ax.text(row[1] + 0.12, index, f"{row[1]:.2f} s", va="center", fontsize=9)
        ax.set_xlabel("processing time [s]")
        ax.set_title("Processing time by query formulation (2.77 M events, single thread)")
        ax.set_xlim(0, max(r[1] for r in rows) * 1.2)
        ax.grid(alpha=0.3, axis="x")
        ax.invert_yaxis()
        save(fig, "bench_query_structure.png")

    # (4) Threads: time and memory on one axis pair. Separately, the time curve looks like a
    # plateau and the memory curve looks unremarkable; together they say that the extra threads
    # stop buying speed at the point where they are still buying memory at full price.
    threaded = [r for r in ok if r.get("threads") and r.get("test") == "chain"
                and r.get("input") == "ds_x32.root"]
    if threaded:
        times = sorted((t, median([x["wall_loop"] for x in threaded if x["threads"] == t]))
                       for t in {r["threads"] for r in threaded})
        memory = sorted((t, median([x["peak_rss_kb"] for x in threaded if x["threads"] == t]) / 1024 ** 2)
                        for t in {r["threads"] for r in threaded})
        fig, ax = plt.subplots(figsize=(7.4, 4.6))
        ax.plot([p[0] for p in times], [p[1] for p in times],
                color="#1b7837", marker="o", lw=2, label="processing time")
        ax.set_xscale("log", base=2)
        ax.set_xticks([p[0] for p in times])
        ax.set_xticklabels([str(p[0]) for p in times])
        ax.minorticks_off()
        ax.set_xlabel("threads")
        ax.set_ylabel("processing time [s]", color="#1b7837")
        ax.tick_params(axis="y", labelcolor="#1b7837")
        ax.set_ylim(0, max(p[1] for p in times) * 1.15)

        ax_mem = ax.twinx()
        ax_mem.plot([p[0] for p in memory], [p[1] for p in memory],
                    color="#d73027", marker="s", ls="--", lw=2, label="peak memory")
        ax_mem.set_ylabel("peak resident memory [GB]", color="#d73027")
        ax_mem.tick_params(axis="y", labelcolor="#d73027")
        ax_mem.set_ylim(0, max(p[1] for p in memory) * 1.15)

        # Only RDataFrame appears here: ImplicitMT is a ROOT mechanism, and the numpy and uproot
        # paths are single-threaded by construction, so for them there is a point, not a curve.
        ax.set_title("RDataFrame: processing time and memory vs thread count (11.1 M events)")
        handles = ax.get_lines()[:1] + ax_mem.get_lines()[:1]
        ax.legend(handles, [h.get_label() for h in handles], loc="upper center")
        ax.grid(alpha=0.3)
        save(fig, "bench_threads.png")

    # (5) The three implementations on one thread axis. The efficiency benchmark is the only one
    # measured for all three on the largest dataset and swept across thread counts, so it is the
    # only place this comparison can be drawn without pairing runs of different queries.
    #
    # The two baselines are horizontal because they have no thread control: the GIL serialises
    # the numpy path, and the harness pins the maths libraries to one thread so they cannot
    # parallelise behind its back. A flat line is the honest shape, not a missing measurement.
    sweep = [r for r in ok if r.get("test") == "efficiency" and r.get("threads")
             and r.get("input") == "ds_x32.root"]
    baselines = {r["impl"]: r["wall_loop"] for r in ok
                 if str(r.get("label", "")).startswith("scale_eff")
                 and r.get("input") == "ds_x32.root" and r["impl"] in ("uproot", "python")}
    if sweep and baselines:
        points = sorted((t, median([x["wall_loop"] for x in sweep if x["threads"] == t]))
                        for t in {r["threads"] for r in sweep})
        threads = [p[0] for p in points]
        fig, ax = plt.subplots(figsize=(7.6, 4.8))
        for impl, style in (("python", dict(color="#d73027", ls="--")),
                            ("uproot", dict(color="#4575b4", ls="-."))):
            if impl not in baselines:
                continue
            ax.axhline(baselines[impl], lw=2, **style,
                       label=f"{IMPL_LABEL[impl]} (single-threaded)")
        ax.plot(threads, [p[1] for p in points], color="#1b7837", marker="o", lw=2,
                markersize=6, label="RDataFrame (C++ JIT), ImplicitMT")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(threads)
        ax.set_xticklabels([str(t) for t in threads])
        ax.minorticks_off()
        ax.set_xlabel("threads")
        ax.set_ylabel("processing time [s]")
        ax.set_title("Efficiency assignment on 11.1 M events, by implementation and thread count")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3, which="both")
        save(fig, "bench_threads_compare.png")

    # (6) Throughput: events per second normalises away dataset size, so it is the only view on
    # which the three implementations can be compared across the whole series at once.
    if scale:
        fig, ax = plt.subplots(figsize=(7, 4.6))
        for impl in ("python", "uproot", "rdf-lazy"):
            points = sorted((r["n_events"], r["n_events"] / r["wall_loop"]) for r in scale
                            if r["impl"] == impl)
            if points:
                ax.plot([p[0] / 1e6 for p in points], [p[1] / 1e6 for p in points],
                        label=IMPL_LABEL[impl], lw=2, markersize=6, **IMPL_STYLE[impl])
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("dataset size [million events]")
        ax.set_ylabel("throughput [million events / s]")
        ax.set_title("Throughput vs dataset size (single thread, 3-filter chain)")
        ax.legend()
        ax.grid(alpha=0.3, which="both")
        save(fig, "bench_throughput.png")

    # (7) Speedup against the two analytical models, and parallel efficiency beside it.
    #
    # Amdahl is drawn not because it fits but because it cannot: monotonic in n for any serial
    # fraction, it has no way to express a curve that turns back down. USL adds a coherency term
    # and therefore has a maximum, which is the quantity of practical interest here.
    tests = [("filter", "single filter"), ("chain", "5-filter chain"),
             ("efficiency", "efficiency column")]
    series_rows = {name: scalability_rows(ok, name, "ds_x32.root") for name, _ in tests}
    if any(series_rows.values()):
        fig, (ax_s, ax_e) = plt.subplots(1, 2, figsize=(12, 4.8))
        colours = {"filter": "#4575b4", "chain": "#1b7837", "efficiency": "#d73027"}
        for name, pretty in tests:
            rows = series_rows.get(name)
            if not rows:
                continue
            threads = [r["threads"] for r in rows]
            ax_s.plot(threads, [r["speedup"] for r in rows], marker="o", lw=2,
                      color=colours[name], label=pretty)
            ax_e.plot(threads, [r["efficiency"] * 100 for r in rows], marker="o", lw=2,
                      color=colours[name], label=pretty)
            if name == "chain":
                measured = [(r["threads"], r["speedup"]) for r in rows]
                grid = [1, 2, 4, 8, 12, 16, 24, 32, 40, 48]
                s = fit_amdahl(measured)
                sigma, kappa = fit_usl(measured)
                ax_s.plot(grid, [1 / (s + (1 - s) / n) for n in grid], ls="--", lw=1.6,
                          color="#888888", label=f"Amdahl, $s$={s:.3f}")
                ax_s.plot(grid, [n / (1 + sigma * (n - 1) + kappa * n * (n - 1)) for n in grid],
                          ls=":", lw=1.8, color="#333333",
                          label=fr"USL, $\sigma$={sigma:.3f}, $\kappa$={kappa:.4f}")
                print(f"  Amdahl serial fraction s = {s:.4f} (ceiling {1 / s:.2f}x)")
                print(f"  USL sigma = {sigma:.4f}, kappa = {kappa:.5f}")
                if kappa > 0:
                    peak = ((1 - sigma) / kappa) ** 0.5
                    ax_s.axvline(peak, color="#333333", ls=":", lw=1, alpha=0.5)
                    print(f"  USL predicted optimum = {peak:.1f} threads")
                print(f"  Amdahl predicts S(48) = {1 / (s + (1 - s) / 48):.2f}, "
                      f"measured {dict(measured).get(48, float('nan')):.2f}")
        for ax in (ax_s, ax_e):
            ax.set_xscale("log", base=2)
            ax.set_xticks([1, 2, 4, 8, 16, 32, 48])
            ax.set_xticklabels(["1", "2", "4", "8", "16", "32", "48"])
            ax.minorticks_off()
            ax.set_xlabel("threads")
            ax.grid(alpha=0.3)
            ax.legend(fontsize=8)
        ax_s.set_ylabel("speedup vs 1 thread")
        ax_s.set_title("Measured speedup against analytical models")
        ax_e.set_ylabel("parallel efficiency [%]")
        ax_e.set_title("Parallel efficiency")
        ax_e.set_ylim(0, 105)
        save(fig, "bench_scalability.png")

        print("\n  metrics per benchmark (ds_x32):")
        for name, _ in tests:
            for row in series_rows.get(name, []):
                print(f"    {name:11s} t={row['threads']:<3} {row['seconds']:6.2f}s "
                      f"{row['throughput'] / 1e6:5.2f} Mevt/s  S={row['speedup']:5.2f} "
                      f"E={row['efficiency'] * 100:5.1f}%  CPU={row['cpu']:4.0f}%")

    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--thesis", metavar="OUT_DIR", default=None,
                        help="write one figure per thesis subsection instead of the full set")
    parser.add_argument("--also-results", action="append", default=[], metavar="DIR",
                        help="merge a second results directory (the thread sweep lives in its own)")
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

    records, superseded = dedupe_labels(records)
    if superseded:
        print(f"WARNING: ignoring {superseded} superseded records (duplicate labels from a "
              f"restarted job; the earlier attempts ran on a cold page cache)")

    if args.thesis:
        for extra in args.also_results:
            extra_records, _ = current_schema_records(load_records(extra))
            extra_records, _ = dedupe_labels(extra_records)
            records += extra_records
        for path in plot_thesis(records, args.thesis):
            print(f"  {path}")
        return 0

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
