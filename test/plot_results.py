#!/usr/bin/env python3
"""
Turns results/raw.jsonl into a flat CSV and the plots of the benchmark campaign.

Repeats are aggregated, never overwritten: every curve goes through a median, and the spread
across repeats is kept for the error bars. Runs that failed or hit the timeout stay in the CSV
with status "failed".

Needs only matplotlib, not ROOT, so it runs on a laptop over a results directory copied off the
cluster.
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
    "chain_len", "tag", "input", "n_events",
    "n_tracks", "wall_setup", "wall_warmup", "wall_jit", "wall_loop", "wall_fixed",
    "bytes_setup", "bytes_warmup", "bytes_jit", "bytes_loop", "bytes_total",
    "peak_rss_kb", "rss_baseline_kb",
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


# Experiments are identified by label prefix rather than by test/impl/threads: T1 and T2 share
# test, impl and thread count, and selecting on the columns would median them together.
CORE_TEST_LABEL = {
    "filter": "single filter",
    "chain": "5-filter chain",
    "efficiency": "efficiency column",
}
CORE_TEST_COLOUR = {"filter": "#4575b4", "chain": "#1b7837", "efficiency": "#d73027"}


def core_rows(records, experiment):
    """Records from one experiment, matched on the r<N>_<experiment>_ label prefix."""
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


def plot(records, results_dir):
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

    plot_core(ok, results_dir, plt, save, outputs)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    parser.add_argument("--csv-only", action="store_true")
    args = parser.parse_args()

    records = load_records(args.results)
    if not records:
        print(f"No records in {args.results}/raw.jsonl", file=sys.stderr)
        return 1

    records, superseded = dedupe_labels(records)
    if superseded:
        print(f"WARNING: ignoring {superseded} superseded records (duplicate labels from a "
              f"restarted job; the earlier attempts ran on a cold page cache)")

    print(f"{len(records)} records -> {write_csv(records, args.results)}")
    failed = [r for r in records if r.get("status") != "ok"]
    if failed:
        print(f"NOTE: {len(failed)} runs failed or timed out: "
              f"{', '.join(sorted(r['label'] for r in failed)[:10])}")

    if not args.csv_only:
        for path in plot(records, args.results):
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
