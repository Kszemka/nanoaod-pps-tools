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
    "label", "status", "schema_version", "machine", "storage", "cache", "test", "impl", "mode", "threads",
    "chain_len", "tag", "input", "input_bytes", "n_events",
    "n_tracks", "wall_setup", "wall_warmup", "wall_jit", "wall_loop", "wall_fixed",
    "bytes_setup", "bytes_warmup", "bytes_jit", "bytes_loop", "bytes_total",
    "peak_rss_kb", "rss_baseline_kb",
    "peak_rss_net_kb", "time_maxrss_kb", "cpu_percent", "elapsed_s", "cpu_loop",
    "cores_busy_loop", "events_per_s", "tracks_per_s", "event_loops", "exit_code", "timeout_s",
    "pinned_core", "cpus_allowed", "os_threads", "root_version", "uproot_version", "node",
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

    Last rather than first: the run that completed wrote the later records. Repeated warm-ups
    are not counted as superseded: every job of a RESUME=1 campaign runs its own.
    """
    last_index = {}
    for index, record in enumerate(records):
        last_index[record.get("label")] = index
    keep = [r for i, r in enumerate(records) if last_index[r.get("label")] == i]
    superseded = [r for i, r in enumerate(records) if last_index[r.get("label")] != i
                  and not str(r.get("label", "")).startswith("warmup_")]
    return keep, len(superseded)


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


def plot_rows(ax, rows, field, label, **kwargs):
    """plot_series for scalability_rows output: whiskers from field_lo / field_hi."""
    points = [(r["threads"], r[field], r[f"{field}_lo"], r[f"{field}_hi"]) for r in rows]
    plot_series(ax, points, label, lw=2, **kwargs)


def cores_busy(record):
    """
    Average number of cores the event loop kept busy.

    Measured directly as cpu_loop / wall_loop when the record has it. Older records only have
    GNU time's whole-process CPU%, and for those the non-loop part of the run is assumed to
    have used one core -- true of setup, warmup and JIT, which are all single-threaded.
    """
    if record.get("cores_busy_loop") is not None:
        return record["cores_busy_loop"]
    cpu, elapsed, loop = record.get("cpu_percent"), record.get("elapsed_s"), record.get("wall_loop")
    if not (cpu and elapsed and loop):
        return None
    return (cpu / 100 * elapsed - (elapsed - loop)) / loop


def fit_linear(xs, ys):
    """Least-squares intercept and slope."""
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sxx
    return mean_y - slope * mean_x, slope


def _normalised(value):
    # Float sums are reduced in a thread-dependent order under ImplicitMT, so they agree to
    # rounding rather than bit for bit.
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, dict):
        return {k: _normalised(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalised(v) for v in value]
    return value


def check_results_agree(records):
    """
    Every run over the same events must produce the same answer, whatever the thread count
    and whichever of the core input and its slim copy it read. Returns {test: number of
    distinct results}.
    """
    distinct = defaultdict(set)
    for r in records:
        distinct[r.get("test")].add(json.dumps(_normalised(r.get("checksums")), sort_keys=True))
    return {test: len(values) for test, values in distinct.items()}


# The integer every implementation of a test reports. Per-step counts and float sums are left
# out: only some implementations report the former, and the latter differ in float32/float64
# accumulation between RDataFrame and numpy.
IMPL_ANSWER = {"filter": "events_passed", "chain": "events_passed", "efficiency": "eff_hits"}


def check_impls_agree(records):
    """
    T5 on the impl input: {test: {implementation: answer}} for every test where they differ.

    validate.py checks agreement on examples/test.root; this repeats it on the data the
    comparison was actually measured on, at no extra cost.
    """
    answers = defaultdict(dict)
    for r in records:
        field = IMPL_ANSWER.get(r.get("test"))
        value = (r.get("checksums") or {}).get(field)
        if value is not None:
            answers[r["test"]][f"{r.get('impl')}/{r.get('mode')}"] = value
    return {test: values for test, values in answers.items() if len(set(values.values())) > 1}


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
    The core campaign: strong scaling, weak scaling, query structure, implementations, and
    the file-width experiment.

    Ordered by what the reader needs first rather than by how the runs happened: the two
    scaling laws lead, memory follows them because it is the cost that the speedup curve
    cannot show, the two single-threaded experiments come next, and the figures that explain
    the shape of the scaling curves close.
    """
    for r in ok:
        busy = cores_busy(r)
        if busy is not None:
            r["cores_busy"] = busy

    strong_all = core_rows(ok, "strong")
    slim_all = core_rows(ok, "slim")
    # t0 (ImplicitMT off) is a baseline, not a point on a log thread axis.
    strong = [r for r in strong_all if r.get("threads")]
    slim = [r for r in slim_all if r.get("threads")]
    weak = core_rows(ok, "weak")
    weak_slim = core_rows(ok, "weakslim")
    qstruct = core_rows(ok, "qstruct")
    impls = core_rows(ok, "impl")
    sized = core_rows(ok, "size")
    # The 1 TB campaign has no T5 of its own: its implementation comparison is the largest
    # point of the size series, which is the same set of variants on one core.
    impls_from_size = not impls and bool(sized)
    if impls_from_size:
        largest = max(r.get("input_bytes") or 0 for r in sized)
        impls = [r for r in sized if (r.get("input_bytes") or 0) == largest]
    # uproot with its own thread pool is a separate point, not a repeat of the pinned one.
    for r in impls:
        if r.get("tag") == "own-threads":
            r["impl"] = f"{r['impl']} (own threads)"

    distinct = check_results_agree(strong_all + slim_all)
    for test, count in sorted(distinct.items()):
        status = "identical" if count == 1 else f"WARNING: {count} different results"
        print(f"  {test}: results across thread counts and full/slim input {status}")
    if impls:
        disagree = check_impls_agree(impls)
        for test, values in sorted(disagree.items()):
            print(f"  WARNING: T5 {test} implementations disagree: {values}")
        if not disagree:
            print("  T5: every implementation gives the same answer")

    # What each extra ImplicitMT worker costs. On the full schema every worker builds its own
    # ~2000-branch tree; on the slim copy the same slopes should be close to zero.
    for name, rows_set in (("full schema", strong), ("slim", slim)):
        for test in CORE_TEST_LABEL:
            cost = per_thread_cost(rows_set, test)
            if cost:
                print(f"  per extra thread [{name}] {test}: "
                      f"{cost.get('rss_mb', float('nan')):+.1f} MB RSS, "
                      f"{cost.get('bytes_mb', float('nan')):+.2f} MB read, "
                      f"{cost.get('cpu_s', float('nan')):+.3f} CPU-s in the loop")

    # T5's RDataFrame runs are the same configuration as T1's t0 runs. A gap between the two is
    # a property of when T5 ran, not of the implementation.
    rdf_impl = {"filter": "rdf", "chain": "rdf-lazy", "efficiency": "jit"}
    for test, impl in ({} if impls_from_size else rdf_impl).items():
        t5 = [r["wall_loop"] for r in impls if r.get("test") == test and r.get("impl") == impl]
        t0 = serial_loop([r for r in strong_all if r.get("impl") == impl], test)
        if t5 and t0:
            print(f"  T5 {test}/{impl}: loop {median(t5):.2f} s (n={len(t5)}) against "
                  f"T1 t0 {t0:.2f} s ({(median(t5) / t0 - 1) * 100:+.0f}%)")

    ticks = sorted({r["threads"] for r in strong + weak + weak_slim + slim}) or [1]

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
        ax.set_ylabel(r"speedup $S(n) = T(1)\,/\,T(n)$")

    # (1) Strong scaling: the same events, more threads. Amdahl applies here and only
    # here. It is drawn not because it fits but because it cannot -- monotonic in n for any
    # serial fraction, it has no way to express a curve that turns back down. USL adds the
    # coherency term that does, and its maximum is the number of practical interest.
    rows = {test: scalability_rows(strong, test) for test in CORE_TEST_LABEL}
    if any(rows.values()):
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        for test, pretty in CORE_TEST_LABEL.items():
            if rows[test]:
                plot_rows(ax, rows[test], "speedup", pretty, color=CORE_TEST_COLOUR[test])
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
        ax.set_title("Strong scaling: fixed problem size, more threads")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "01_speedup_amdahl.png")

        # (2) The same data as a fraction of the threads paid for. A speedup of 5 is a
        # different statement at 8 threads than at 48, and only this axis says which.
        fig, ax = plt.subplots(figsize=(8, 4.8))
        for test, pretty in CORE_TEST_LABEL.items():
            if rows[test]:
                percent = [{**r, **{k: r[k] * 100 for k in
                                    ("efficiency", "efficiency_lo", "efficiency_hi")}}
                           for r in rows[test]]
                plot_rows(ax, percent, "efficiency", pretty, color=CORE_TEST_COLOUR[test])
        ax.axhline(100, color="#bbbbbb", lw=1)
        thread_axis(ax)
        ax.set_ylabel("parallel efficiency [%]")
        ax.set_ylim(0, 105)
        ax.set_title("Parallel efficiency: speedup per thread")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3, which="both")
        save(fig, "02_parallel_efficiency.png")

    # (3) Weak scaling: N threads against N units of work (ds_xN or weak_N.txt), so work per
    # thread is constant. Ideal is a
    # flat wall-time line, and the question is the opposite of T1's -- not "is the same job
    # faster" but "does a job that grows with the machine still finish in the same time".
    #
    # Gustafson's law is not drawn: with the serial fraction taken from the T1 fit it predicts
    # ~24x at 32 threads against a measured 3-5x, because what grows here is not a serial
    # region but a cost paid once per worker thread. The straight-line fit t = w + c*N reads
    # that cost off directly.
    #
    # T2S (dashed) is the same series on slim copies. A unit of work on the full files is
    # 0.24-0.52 s of loop per thread, less than the ~1 s of CPU a worker spends building its
    # tree, so the solid curves are mostly that setup and the dashed ones are the work.
    if weak:
        fig, (ax_t, ax_s) = plt.subplots(1, 2, figsize=(12, 4.8))
        for test, pretty in CORE_TEST_LABEL.items():
            colour = CORE_TEST_COLOUR[test]
            for rows_set, style, suffix in ((weak, "-", ""), (weak_slim, "--", ", control file")):
                sub = [r for r in rows_set if r.get("test") == test]
                xs, ys = curve(sub, "threads", "wall_loop")
                if len(xs) < 2:
                    continue
                intercept, slope = fit_linear(xs, ys)
                label = f"{pretty}{suffix}: {slope * 1000:.0f} ms per extra thread"
                for _, points in series(sub, ("test",), "threads", "wall_loop").items():
                    plot_series(ax_t, points, label, lw=2, ls=style, color=colour)
                if not suffix:
                    ax_t.plot(xs, [intercept + slope * n for n in xs], ls=":", lw=1,
                              color=colour)
                print(f"  weak{suffix} {test}: loop = {intercept:.3f} s + "
                      f"{slope * 1000:.1f} ms x threads")
                ax_s.plot(xs, [n * ys[0] / y for n, y in zip(xs, ys)], marker="o", lw=2,
                          ls=style, color=colour, label=pretty + suffix)
        weak_ticks = sorted({r["threads"] for r in weak + weak_slim if r.get("threads")}) or ticks
        ax_s.plot(weak_ticks, weak_ticks, lw=1, color="#bbbbbb", label="ideal ($S = n$)")
        for ax in (ax_t, ax_s):
            ax.set_xscale("log", base=2)
            ax.set_xticks(weak_ticks)
            ax.set_xticklabels([str(t) for t in weak_ticks])
            ax.minorticks_off()
            ax.set_xlabel("threads (N threads on N units of work)")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3, which="both")
        ax_t.set_ylabel("event-loop wall time [s]")
        ax_t.set_title("Constant work per thread: flat is ideal")
        speedup_axis(ax_s, weak_ticks)
        ax_s.set_ylabel("scaled speedup")
        ax_s.set_title("Scaled speedup" + (" (dashed: control files)" if weak_slim else ""))
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
        ax.set_title("Memory against thread count (fixed problem size)")
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
        ax.set_title("Memory along the weak-scaling series")
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
        ax_time.set_title("...and what it costs")
        save(fig, "07_query_structure.png")

    # (8) Implementations, and where their time goes. Same file, same codec, same events for
    # every bar -- the comparison a reader is most likely to challenge is the one that must
    # not straddle two datasets.
    #
    # Events/s rather than tracks/s: only the efficiency test reports a track count, and a
    # figure keyed on it silently dropped the filter and chain rows.
    # Only single-core runs: uproot with its own thread pool is a different resource budget and
    # does not belong on a per-core comparison. Python is represented by its faster, loop mode:
    # the vector mode still loops over per-event objects to flatten them and only adds copies.
    # correctionlib is part of the RDataFrame solution, not a competing implementation.
    one_core = [r for r in impls if r.get("tag") != "own-threads"
                and r.get("impl") != "correctionlib"
                and not (r.get("impl") == "python" and r.get("mode") == "vector")]
    impl_tests = [t for t in CORE_TEST_LABEL if any(r.get("test") == t for r in one_core)]
    if impl_tests:
        def impl_name(key):
            impl, _ = key
            if impl in ("rdf", "rdf-lazy", "jit"):
                return "RDataFrame"
            return impl

        per_test = {}
        for test in impl_tests:
            sub = [r for r in one_core if r.get("test") == test]
            values = aggregate(sub, ("impl", "mode"), "events_per_s")
            per_test[test] = (sub, values, sorted(values, key=lambda k: values[k][0]))
        heights = [max(len(per_test[t][2]), 1) for t in impl_tests]
        fig, axes = plt.subplots(len(impl_tests), 2, figsize=(13, 1.4 + 0.5 * sum(heights)),
                                 gridspec_kw={"height_ratios": heights}, squeeze=False)
        # The warmup pass is where cling compiles the kernel, so together with graph building it
        # is RDataFrame's compilation cost -- the one-off price uproot and NumPy do not pay.
        for r in one_core:
            r["wall_compile"] = (r.get("wall_warmup") or 0.0) + (r.get("wall_jit") or 0.0)
        phase_names = ("wall_setup", "wall_compile", "wall_loop")
        phase_labels = ("setup", "JIT compilation", "event loop")
        phase_colours = ("#4575b4", "#1a9850", "#d73027")
        for row, test in enumerate(impl_tests):
            sub, values, keys = per_test[test]
            ax_tp, ax_ph = axes[row]
            names = [impl_name(k) for k in keys]
            rates = [values[k][0] for k in keys]
            ax_tp.barh(names, rates, color=CORE_TEST_COLOUR[test])
            ax_tp.set_xscale("log")
            ax_tp.set_xlim(right=max(rates) * 1.5)
            ax_tp.xaxis.set_minor_formatter(plt.NullFormatter())
            ax_tp.set_ylabel(CORE_TEST_LABEL[test])
            ax_tp.grid(alpha=0.3, axis="x")

            phases = {name: aggregate(sub, ("impl", "mode"), name) for name in phase_names}
            lefts = [0.0] * len(keys)
            for name, label, colour in zip(phase_names, phase_labels, phase_colours):
                widths = [phases[name].get(k, (0.0,))[0] or 0.0 for k in keys]
                ax_ph.barh(names, widths, left=lefts, color=colour,
                           label=label if row == 0 else None)
                lefts = [a + b for a, b in zip(lefts, widths)]
            # Linear, because on a log axis stacked segments are not proportional to time: the
            # ~1 s setup took as much width as a 20 s loop. The scale follows the compiled
            # implementations; the interpreted ones run off it and are labelled with their total.
            compiled = [t for n, t in zip(names, lefts) if not n.startswith("python")]
            right = max(compiled or lefts) * 1.6
            ax_ph.set_xlim(0, right)
            for index, total in enumerate(lefts):
                label = f"{total:.1f} s" if total <= right else f"{total:.0f} s \u2192"
                ax_ph.text(min(total, right * 0.985), index, f"  {label}" if total <= right
                           else label, va="center", fontsize=7,
                           ha="left" if total <= right else "right",
                           color="black" if total <= right else "white")
            ax_ph.grid(alpha=0.3, axis="x")
        impl_input = impls[0].get("input", "one input")
        axes[0][0].set_title(f"Event-loop throughput on {impl_input}, one core")
        axes[0][1].set_title("Wall time per query")
        axes[-1][1].legend(*axes[0][1].get_legend_handles_labels(), fontsize=8,
                           loc="upper center", bbox_to_anchor=(0.5, -0.45), ncol=3)
        axes[-1][0].set_xlabel("events / s")
        axes[-1][1].set_xlabel("wall time [s]")
        save(fig, "08_implementations.png")

    # (9) Two baselines for the same speedup. ImplicitMT(1) is the right reference for how well
    # the parallel machinery scales; ImplicitMT off is the right one for what a user gains by
    # turning it on, and it is the faster of the two.
    serial = {test: serial_loop(strong_all, test) for test in CORE_TEST_LABEL}
    if strong and any(serial.values()):
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        for test, pretty in CORE_TEST_LABEL.items():
            colour = CORE_TEST_COLOUR[test]
            vs_mt1 = scalability_rows(strong, test)
            if vs_mt1:
                plot_rows(ax, vs_mt1, "speedup", f"{pretty} vs ImplicitMT(1)", color=colour)
            if serial[test] and vs_mt1:
                vs_off = scalability_rows(strong, test, baseline=serial[test])
                plot_rows(ax, vs_off, "speedup", f"{pretty} vs ImplicitMT off",
                          color=colour, ls="--", alpha=0.7)
                best = max(vs_off, key=lambda r: r["speedup"])
                print(f"  {test}: ImplicitMT(1) loop {vs_mt1[0]['seconds']:.2f} s, "
                      f"off {serial[test]:.2f} s; best speedup vs off "
                      f"{best['speedup']:.2f}x at {best['threads']} threads")
        ax.plot(ticks, ticks, lw=1, color="#bbbbbb", label="ideal ($S = n$)")
        thread_axis(ax)
        speedup_axis(ax, ticks)
        ax.set_ylabel("speedup")
        ax.set_title("Speedup against both serial baselines")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3, which="both")
        save(fig, "09_speedup_baselines.png")

    # (10) How many cores the event loop actually kept busy. The answer to "why does ImplicitMT
    # look single-threaded": whole-process CPU% averages the loop with ~5 s of serial setup.
    busy_sets = [(strong, "-", "")] + ([(slim, "--", ", control file")] if slim else [])
    if any(r.get("cores_busy") is not None for r in strong):
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        for test, pretty in CORE_TEST_LABEL.items():
            for rows_set, style, suffix in busy_sets:
                sub = [r for r in rows_set if r.get("test") == test]
                for _, points in series(sub, ("test",), "threads", "cores_busy").items():
                    plot_series(ax, points, pretty + suffix, lw=2, ls=style,
                                color=CORE_TEST_COLOUR[test])
        ax.plot(ticks, ticks, lw=1, color="#bbbbbb", label="all threads busy")
        thread_axis(ax)
        speedup_axis(ax, ticks)
        ax.set_ylabel("cores busy during the event loop")
        if any(r.get("cores_busy_loop") is None for r in strong + slim):
            ax.text(0.02, 0.97, "estimated from whole-process CPU% (no cpu_loop in records)",
                    transform=ax.transAxes, va="top", fontsize=8, style="italic")
        ax.set_title("Event-loop CPU utilisation")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3, which="both")
        save(fig, "10_cores_busy.png")

    # (11) T6: the file-width experiment. The two files hold the same events with the same
    # codec and cluster size and differ only in branch count, so whatever changes between the
    # solid and dashed curves is the cost of the schema every worker thread sets up.
    if slim:
        fig, (ax_t, ax_s, ax_m) = plt.subplots(1, 3, figsize=(16, 4.8))
        for test, pretty in CORE_TEST_LABEL.items():
            colour = CORE_TEST_COLOUR[test]
            for rows_set, rows_all, style, name in ((strong, strong_all, "-", "full schema"),
                                                   (slim, slim_all, "--", "control file")):
                sub = [r for r in rows_set if r.get("test") == test]
                if not sub:
                    continue
                label = f"{pretty}, {name}"
                for _, points in series(sub, ("test",), "threads", "wall_loop").items():
                    plot_series(ax_t, points, label, lw=2, ls=style, color=colour)
                speedups = scalability_rows(sub, test, baseline=serial_loop(rows_all, test))
                plot_rows(ax_s, speedups, "speedup", label, ls=style, color=colour)
                for _, points in series(sub, ("test",), "threads", "peak_rss_kb").items():
                    plot_series(ax_m, [(x, m / 1024, lo / 1024, hi / 1024)
                                       for x, m, lo, hi in points],
                                label, lw=2, ls=style, color=colour)
                xs, rss = curve(sub, "threads", "peak_rss_kb")
                best = max(speedups, key=lambda r: r["speedup"])
                per_thread = fit_linear(xs, rss)[1] / 1024 if len(xs) > 1 else float("nan")
                print(f"  {test} [{name}]: best {best['speedup']:.2f}x at {best['threads']} "
                      f"threads (vs ImplicitMT off), {per_thread:.0f} MB RSS per thread")
        ax_s.plot(ticks, ticks, lw=1, color="#bbbbbb", label="ideal ($S = n$)")
        for ax in (ax_t, ax_s, ax_m):
            thread_axis(ax)
            ax.grid(alpha=0.3, which="both")
        speedup_axis(ax_s, ticks)
        ax_s.set_ylabel("speedup vs ImplicitMT off, same file")
        ax_t.set_ylabel("event-loop wall time [s]")
        ax_m.set_ylabel("peak RSS [MB]")
        ax_t.set_title("Event-loop time")
        ax_s.set_title("Speedup")
        ax_m.set_title("Peak memory")
        ax_m.legend(fontsize=7)
        save(fig, "11_file_width.png")

    # (13) T5 against input size, from the size and sizepy series of the 1 TB campaign.
    if sized:
        plot_input_size(sized, plt, save)


SIZE_IMPL_LABEL = {"rdf": "RDataFrame", "rdf-lazy": "RDataFrame", "jit": "RDataFrame",
                   "uproot": "uproot", "python": "Python (AsNumpy)"}
SIZE_IMPL_COLOUR = {"RDataFrame": "#1b7837", "uproot": "#762a83", "Python (AsNumpy)": "#e08214"}


def plot_input_size(records, plt, save):
    """
    Peak memory and total time against input size, per implementation, on one core.

    Total rather than loop time, because the loop alone hides the cost RDataFrame pays and the
    others do not: setup plus cling JIT, once per process. Failed runs have no record here, so a
    line that stops short is where that implementation ran out of memory or time.
    """
    fig, axes = plt.subplots(2, len(CORE_TEST_LABEL), figsize=(15, 8), squeeze=False)
    for column, (test, pretty) in enumerate(CORE_TEST_LABEL.items()):
        by_impl = defaultdict(list)
        for r in records:
            if r.get("test") != test or not r.get("input_bytes"):
                continue
            rss_kb = r.get("time_maxrss_kb") or r.get("peak_rss_kb")
            r["input_gb"] = r["input_bytes"] / 1e9
            r["rss_gb"] = rss_kb * 1024 / 1e9 if rss_kb else None
            r["wall_total"] = (r.get("wall_fixed") or 0.0) + (r.get("wall_loop") or 0.0)
            by_impl[SIZE_IMPL_LABEL.get(r.get("impl"), r.get("impl"))].append(r)

        totals = {}
        for name, rows in sorted(by_impl.items()):
            xs_m, rss = curve(rows, "input_gb", "rss_gb")
            xs_t, total = curve(rows, "input_gb", "wall_total")
            colour = SIZE_IMPL_COLOUR.get(name)
            axes[0][column].plot(xs_m, rss, marker="o", lw=2, color=colour, label=name)
            axes[1][column].plot(xs_t, total, marker="o", lw=2, color=colour, label=name)
            totals[name] = dict(zip(xs_t, total))
            if len(xs_m) > 1 and len(xs_t) > 1:
                print(f"  size {test} [{name}]: {fit_linear(xs_m, rss)[1]:.3f} GB of RSS and "
                      f"{fit_linear(xs_t, total)[1]:.2f} s per GB of input, "
                      f"measured up to {max(xs_t):.0f} GB")

        rdf, up = totals.get("RDataFrame", {}), totals.get("uproot", {})
        common = sorted(set(rdf) & set(up))
        if common:
            faster = [gb for gb in common if rdf[gb] < up[gb]]
            print(f"  size {test}: RDataFrame faster than uproot in total from {faster[0]:.0f} GB"
                  if faster else
                  f"  size {test}: uproot faster than RDataFrame in total up to {common[-1]:.0f} GB")

        axes[0][column].set_title(pretty)
        axes[1][column].set_xlabel("input size on disk [GB]")
        for ax in (axes[0][column], axes[1][column]):
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
            ax.grid(alpha=0.3)
    axes[0][0].set_ylabel("peak RSS [GB]")
    axes[1][0].set_ylabel("total time: setup + JIT + event loop [s]")
    axes[0][0].legend(fontsize=8)
    fig.suptitle("Memory and time against input size, one core")
    save(fig, "13_input_size.png")


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
        if not tail.isdigit() or int(tail) == 0:
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


def per_thread_cost(records, test):
    """
    Slopes against the thread count of the medians of peak RSS [MB], bytes read in the loop
    [MB] and CPU spent in the loop [s], over the ImplicitMT runs of one test.

    CPU is what the threads burned, not wall time: a cost that every worker pays in parallel
    still shows up here, which is what separates "each thread does extra work" from "threads
    wait for each other". None when there are fewer than two thread counts.
    """
    buckets = defaultdict(list)
    for r in records:
        if r.get("test") != test or not r.get("threads") or r.get("wall_loop") is None:
            continue
        cpu = r.get("cpu_loop")
        if cpu is None and r.get("cores_busy") is not None:
            cpu = r["cores_busy"] * r["wall_loop"]
        buckets[r["threads"]].append((r.get("peak_rss_kb"), r.get("bytes_loop"), cpu))
    if len(buckets) < 2:
        return None
    xs = sorted(buckets)
    out = {}
    for index, (name, scale) in enumerate((("rss_mb", 1024), ("bytes_mb", 1e6), ("cpu_s", 1))):
        points = [(x, median([v[index] for v in buckets[x] if v[index] is not None]))
                  for x in xs]
        points = [(x, y / scale) for x, y in points if y is not None]
        if len(points) > 1:
            out[name] = fit_linear([p[0] for p in points], [p[1] for p in points])[1]
    return out


def serial_loop(records, test):
    """Median loop time with ImplicitMT off (threads == 0), or None if there are no such runs."""
    loops = [r["wall_loop"] for r in records
             if r.get("test") == test and r.get("threads") == 0 and r.get("wall_loop")]
    return median(loops) if loops else None


def scalability_rows(records, test, baseline=None):
    """
    Speedup and efficiency per thread count for one benchmark, with min-max whiskers.

    baseline=None measures speedup against the lowest thread count, i.e. ImplicitMT(1). Passing
    serial_loop() instead measures it against ImplicitMT off, which is the faster of the two:
    ImplicitMT(1) still goes through the task-based path. The whiskers take the loop time's
    spread across repeats at each thread count; the baseline's own spread is not propagated.
    """
    runs = defaultdict(list)
    for r in records:
        if r.get("status") == "ok" and r.get("test") == test and r.get("threads"):
            runs[r["threads"]].append(r)
    if not runs:
        return []
    if baseline is None:
        baseline = median([x["wall_loop"] for x in runs[min(runs)]])
    rows = []
    for threads in sorted(runs):
        loops = [x["wall_loop"] for x in runs[threads]]
        seconds = median(loops)
        rows.append({
            "threads": threads,
            "seconds": seconds,
            "speedup": baseline / seconds,
            "speedup_lo": baseline / max(loops),
            "speedup_hi": baseline / min(loops),
            "efficiency": baseline / seconds / threads,
            "efficiency_lo": baseline / max(loops) / threads,
            "efficiency_hi": baseline / min(loops) / threads,
        })
    return rows


def latex_escape(text):
    return str(text).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%")


def scalability_table(records, test):
    """
    The thesis's scalability table (tab:scalability) for one benchmark of the strong sweep.

    Same definitions as the hand-written original, so a new campaign drops in unchanged: time is
    the event-loop wall time under ImplicitMT(n), speedup and efficiency are against
    ImplicitMT(1), and throughput is events over that loop time. There are two CPU columns.
    CPU loop is the event loop's own CPU time over its wall time, the same window as the time
    column. CPU process is GNU time's whole-process figure, which also counts the
    single-threaded setup and JIT: on 1 TB that is ~48 s against a ~43 s loop at 48 threads,
    so it reads less than half of what the loop actually used. Returns None when the sweep
    has no records for this test.
    """
    rows = scalability_rows(records, test)
    if not rows:
        return None
    ok = [r for r in records if r.get("status") == "ok" and r.get("test") == test]
    n_events = median([r["n_events"] for r in ok if r.get("n_events")])
    cpu = {key[0]: value[0] for key, value in aggregate(ok, ("threads",), "cpu_percent").items()}
    loop_cpu = defaultdict(list)
    for r in ok:
        busy = cores_busy(r)
        if busy is not None and r.get("threads"):
            loop_cpu[r["threads"]].append(100 * busy)
    best = max(rows, key=lambda row: row["speedup"])
    inputs = sorted({r.get("input") for r in ok if r.get("input")})
    machines = sorted({r.get("machine") for r in ok if r.get("machine")})
    repeats = max(aggregate(ok, ("threads",), "wall_loop").values(), key=lambda v: v[3])[3]
    cold = any(r.get("cache") == "cold" for r in ok)

    def bold(row, text):
        return rf"\textbf{{{text}}}" if row is best else text

    body = []
    for row in rows:
        seconds, threads = row["seconds"], row["threads"]
        throughput = n_events / seconds / 1e6 if n_events else None
        cpu_text = f"{cpu[threads]:.0f}\\%" if cpu.get(threads) is not None else "--"
        loop_text = (f"{median(loop_cpu[threads]):.0f}\\%" if loop_cpu.get(threads) else "--")
        body.append(" & ".join([
            f"{threads:>2}",
            bold(row, f"{seconds:.2f}"),
            bold(row, f"{throughput:.2f}") if throughput is not None else "--",
            bold(row, f"{row['speedup']:.2f}"),
            f"{row['efficiency'] * 100:.0f}\\%",
            loop_text,
            cpu_text,
        ]) + r" \\")

    source = ", ".join(latex_escape(name) for name in inputs) or "the core input"
    where = (f"measured on {latex_escape(machines[0].capitalize())}" if len(machines) == 1
             else "measured")
    if not n_events:
        events = "the core input"
    elif n_events >= 1e9:
        events = f"${n_events / 1e9:.2f}$ billion events"
    else:
        events = f"${n_events / 1e6:.1f}$ million events"
    median_note = f"median of {repeats} repeats, " if repeats > 1 else "single run, "
    cache_note = "inputs evicted from the page cache before every run, " if cold else ""
    caption = (
        f"Parallel scalability metrics for the {CORE_TEST_LABEL[test].replace('5-', 'five-')} "
        f"on {events} (\\texttt{{{source}}}), {where} "
        f"({median_note}{cache_note}speedup against \\texttt{{ImplicitMT}} with one thread). "
        f"Nominal CPU utilisation for $n$ threads is $100n\\%$. CPU loop covers the same "
        f"event-loop window as the time column; CPU process is the whole-process figure, which "
        f"also includes the single-threaded setup and JIT. The speedup maximum at "
        f"{best['threads']} threads coincides with a parallel efficiency of only "
        f"${best['efficiency'] * 100:.0f}\\%$."
    )
    return "\n".join([
        r"\begin{table}[htbp]",
        r"\centering",
        rf"\caption{{{caption}}}",
        rf"\label{{tab:scalability-{test}}}",
        r"\begin{tabular}{rrrrrrr}",
        r"\toprule",
        r"Threads & Time [s] & Throughput [$10^6$ ev/s] & Speedup $S$ & Efficiency $E$ & CPU loop & CPU process \\",
        r"\midrule",
        *body,
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
    ])


def write_scalability_tables(records, results_dir):
    """table_scalability_<test>.tex for every benchmark of the strong sweep that has records."""
    strong = core_rows(records, "strong")
    paths = []
    for test in CORE_TEST_LABEL:
        table = scalability_table(strong, test)
        if table is None:
            continue
        path = os.path.join(results_dir, f"table_scalability_{test}.tex")
        with open(path, "w") as f:
            f.write(table)
        paths.append(path)
    return paths


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

    for path in write_scalability_tables(records, args.results):
        print(f"  {path}")
    if not args.csv_only:
        for path in plot(records, args.results):
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
