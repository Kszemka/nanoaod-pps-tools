#!/usr/bin/env python3
"""
Where the strong-scaling optimum lies against input size, across campaigns.

Each --results directory contributes its T1 sweep (r<N>_strong_*). For every benchmark the
event-loop time under ImplicitMT(n) is fitted with

    T(n) = c + a/n + b*n

a/n is the work that divides among the threads, so a grows with the number of events; b*n is
what every extra thread costs on top (its own reader and tree, its share of the task
scheduling), which does not. The minimum is at n* = sqrt(a/b): the optimum grows as the square
root of the work, which is why ds_x32 peaks at 8-16 threads and 1 TB is still rising at 48.

Writes 14_optimum_vs_size.png (fitted n* and the measured best thread count against events,
with a sqrt(N) guide and each machine's core count) and prints the fit for the text.

Near the optimum T(n) is flat, so the fastest point alone is decided by noise. The plateau is
the range of thread counts whose median loop time is within 5% of the minimum -- about the
run-to-run spread on Helios -- and is drawn as a whisker on the fastest point. A fitted n*
beyond the sweep is not a measurement; it is drawn at the last point with an arrow.

    plot_optimum.py --results results-ares results-ares-big results-helios-x32 ... [--out DIR]

Needs only matplotlib, like plot_results.py.
"""

import argparse
import math
import os
import sys

from plot_results import CORE_TEST_COLOUR, CORE_TEST_LABEL, core_rows, dedupe_labels, \
    load_records, median

MACHINE_MARKER = {"ares": "o", "helios": "s"}
PLATEAU = 1.05


def solve3(m, v):
    """Gaussian elimination with partial pivoting for a 3x3 system; None if singular."""
    a = [row[:] + [rhs] for row, rhs in zip(m, v)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-300:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(col + 1, 3):
            f = a[r][col] / a[col][col]
            for k in range(col, 4):
                a[r][k] -= f * a[col][k]
    x = [0.0, 0.0, 0.0]
    for r in (2, 1, 0):
        x[r] = (a[r][3] - sum(a[r][k] * x[k] for k in range(r + 1, 3))) / a[r][r]
    return x


def fit_optimum(points):
    """
    c, a, b of T(n) = c + a/n + b*n, least squares on relative error.

    Relative rather than absolute: T spans two orders of magnitude across a sweep, and an
    absolute fit would be decided by the one- and two-thread points alone. A negative b means
    no growth term is measurable within the sweep (single runs on a shared file system); b is
    then fixed at 0 and the optimum lies beyond the last point.
    """
    rows = [(1 / t, 1 / (n * t), n / t) for n, t in points]
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    aty = [sum(r[i] for r in rows) for i in range(3)]
    sol = solve3(ata, aty)
    if sol is None:
        return None
    c, a, b = sol
    if b < 0:
        s11 = sum(r[0] * r[0] for r in rows)
        s12 = sum(r[0] * r[1] for r in rows)
        s22 = sum(r[1] * r[1] for r in rows)
        y1, y2 = aty[0], aty[1]
        det = s11 * s22 - s12 * s12
        if abs(det) < 1e-300:
            return None
        c, a, b = (y1 * s22 - y2 * s12) / det, (s11 * y2 - s12 * y1) / det, 0.0
    return c, a, b


def campaign(results_dir):
    """One entry per benchmark of a directory's T1 sweep."""
    records, _ = dedupe_labels(load_records(results_dir))
    ok = [r for r in records if r.get("status") == "ok"]
    strong = [r for r in core_rows(ok, "strong") if r.get("threads")]
    entries = []
    for test in CORE_TEST_LABEL:
        runs = [r for r in strong if r.get("test") == test and r.get("wall_loop") is not None]
        if not runs:
            continue
        by_threads = {}
        for r in runs:
            by_threads.setdefault(r["threads"], []).append(r["wall_loop"])
        points = sorted((n, median(v)) for n, v in by_threads.items())
        if len(points) < 4:
            continue
        fit = fit_optimum(points)
        if fit is None:
            continue
        c, a, b = fit
        best_n, best_t = min(points, key=lambda p: p[1])
        flat = [n for n, t in points if t <= PLATEAU * best_t]
        machines = sorted({r.get("machine") for r in runs if r.get("machine")})
        entries.append({
            "dir": os.path.basename(os.path.normpath(results_dir)),
            "machine": machines[0] if len(machines) == 1 else "/".join(machines),
            "cores": max((r.get("cpus_allowed") or 0) for r in runs) or points[-1][0],
            "input": sorted({r.get("input") for r in runs if r.get("input")}),
            "events": median([r["n_events"] for r in runs if r.get("n_events")]),
            "test": test,
            "c": c, "a": a, "b": b,
            "n_star": math.sqrt(a / b) if b > 0 and a > 0 else None,
            "best_n": best_n,
            "plateau": (min(flat), max(flat)),
            "max_n": points[-1][0],
        })
    return entries


def print_table(entries):
    print(f"{'campaign':26s} {'machine':7s} {'events':>9s} {'test':10s} {'a [s]':>8s} "
          f"{'b [ms]':>7s} {'n*':>11s} {'best':>5s} {'plateau':>8s} {'max':>4s}")
    for e in entries:
        if e["n_star"] is None:
            n_star = f">{e['max_n']}"
        elif e["n_star"] > e["max_n"]:
            n_star = f">{e['max_n']} (fit)"
        else:
            n_star = f"{e['n_star']:.0f}"
        best = f"{e['best_n']}" + ("+" if e["best_n"] == e["max_n"] else "")
        plateau = "{}-{}".format(*e["plateau"])
        print(f"{e['dir']:26s} {e['machine']:7s} {e['events'] / 1e6:8.1f}M {e['test']:10s} "
              f"{e['a']:8.1f} {e['b'] * 1000:7.1f} {n_star:>11s} {best:>5s} {plateau:>8s} "
              f"{e['max_n']:>4d}")
    print("  best = thread count of the shortest loop; '+' = the sweep's last point, so the "
          f"optimum lies beyond it; plateau = median loop time within {PLATEAU:.2f} x the "
          "shortest")


def plot(entries, out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import ScalarFormatter

    tests = [t for t in CORE_TEST_LABEL if any(e["test"] == t for e in entries)]
    fig, axes = plt.subplots(1, len(tests), figsize=(5 * len(tests), 4.4), sharey=True,
                             squeeze=False)
    events = [e["events"] for e in entries]
    x_lo, x_hi = min(events) / 2, max(events) * 2
    cores = sorted({(e["machine"], e["cores"]) for e in entries}, key=lambda m: m[1])

    for ax, test in zip(axes[0], tests):
        colour = CORE_TEST_COLOUR[test]
        rows = sorted((e for e in entries if e["test"] == test), key=lambda e: e["events"])
        for machine in sorted({e["machine"] for e in rows}):
            mine = [e for e in rows if e["machine"] == machine]
            marker = MACHINE_MARKER.get(machine, "D")
            fitted = [e for e in mine if e["n_star"]]
            ax.plot([e["events"] for e in fitted],
                    [min(e["n_star"], e["max_n"]) for e in fitted], marker=marker,
                    ls="-", color=colour, mfc="none", ms=8, label=f"{machine}: fitted $n^*$")
            ax.errorbar([e["events"] for e in mine], [e["best_n"] for e in mine],
                        yerr=[[e["best_n"] - e["plateau"][0] for e in mine],
                              [e["plateau"][1] - e["best_n"] for e in mine]],
                        marker=marker, ls="none", color=colour, ms=6, capsize=3,
                        label=f"{machine}: fastest measured, {PLATEAU - 1:.0%} plateau")
            # A sweep whose fastest point is its last only bounds the optimum from below, and
            # so does a fit whose n* lies beyond it.
            for e in mine:
                if e["best_n"] == e["max_n"]:
                    ax.annotate("", xy=(e["events"], e["best_n"] * 1.6),
                                xytext=(e["events"], e["best_n"]),
                                arrowprops={"arrowstyle": "->", "color": colour})
                if e["n_star"] and e["n_star"] > e["max_n"]:
                    ax.annotate("", xy=(e["events"] * 1.15, e["max_n"] * 1.6),
                                xytext=(e["events"] * 1.15, e["max_n"]),
                                arrowprops={"arrowstyle": "->", "color": colour, "ls": ":"})
        anchor = next((e for e in rows if e["n_star"]), None)
        if anchor:
            xs = [x_lo, x_hi]
            ax.plot(xs, [anchor["n_star"] * math.sqrt(x / anchor["events"]) for x in xs],
                    ls=":", color="grey", label=r"$\propto\sqrt{N}$")
        for machine, n in cores:
            ax.axhline(n, ls="--", lw=0.8, color="black", alpha=0.5)
            ax.text(x_lo * 1.1, n * 1.05, f"{machine}: {n} cores", fontsize=8, alpha=0.7)
        ax.set_xscale("log")
        ax.set_yscale("log", base=2)
        ax.yaxis.set_major_formatter(ScalarFormatter())
        ax.set_xlim(x_lo, x_hi)
        ax.set_xlabel("events in the input")
        ax.set_title(CORE_TEST_LABEL[test])
        ax.grid(alpha=0.3, which="both")
    axes[0][0].set_ylabel("optimal thread count")
    axes[0][0].legend(fontsize=8, loc="lower right")
    fig.suptitle(r"Strong-scaling optimum against input size: $T(n) = c + a/n + b\,n$, "
                 r"$n^* = \sqrt{a/b}$")
    fig.tight_layout()
    path = os.path.join(out_dir, "14_optimum_vs_size.png")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", nargs="+", required=True,
                        help="results directories, each with a raw.jsonl holding a T1 sweep")
    parser.add_argument("--out", default=".", help="directory for 14_optimum_vs_size.png")
    args = parser.parse_args()

    entries = []
    for results_dir in args.results:
        found = campaign(results_dir)
        if not found:
            print(f"WARNING: no T1 sweep in {results_dir}", file=sys.stderr)
        entries.extend(found)
    if not entries:
        return 1
    entries.sort(key=lambda e: (e["machine"], e["events"], list(CORE_TEST_LABEL).index(e["test"])))
    print_table(entries)
    os.makedirs(args.out, exist_ok=True)
    print(f"  {plot(entries, args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
