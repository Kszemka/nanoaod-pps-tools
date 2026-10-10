#!/usr/bin/env python3
"""
Before a campaign on a mixed real dataset: does the 11-filter chain mean the same thing in
every part of it, and which files does it leave no event of?

Every readable file of an inventory_files.py CSV that has all of the chain's columns, one file
per task in a pool of --jobs processes:
  types   the C++ type of each of the chain's 10 columns. A TChain over files that store a
          column with different types breaks, or reads garbage, as soon as that column is read;
          the inventory's schema hash only compares branch names.
  chain   events left after each of the 11 filters (Report(), one event loop per file), summed
          per (era, processing version), with the number of files nothing is left of. A period
          whose pots or detector type differ from the cuts in bench_spec.PERIODS shows up here
          as a step that drops every event.
and, from the CSV itself, the fraction of events with PPS tracks and with a track in the
default RP, per era. --per-file writes every file's counts, for make_filelists.py
--chain-counts.

Exit codes: 0 fine, 3 a file the chain cannot read, 2 a column with two types, 4 the chain
leaves no event of the whole set.

    check_chain11.py --inventory local.csv [--period 2026] [--jobs 16] [--per-file chain11_files.csv]
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import bench_common as bc
import impl_rdf

ROOT = bc.ROOT


def _check_file(path, rp_id, period):
    """(column types, events left after each filter), or (None, error) when the file fails."""
    try:
        df = ROOT.RDataFrame("Events", path)
        columns = bc.chain_columns(len(bc.LONG_CHAIN_STEPS), "long")
        types = {c: str(df.GetColumnType(c)) for c in columns}
        nodes = impl_rdf.build_chain_nodes(df, len(bc.LONG_CHAIN_STEPS), rp_id, "long", period)
        report = impl_rdf.build_chain_report(nodes)
        return types, impl_rdf.trigger_chain_report(report)["intermediate"]
    except Exception as exc:  # noqa: BLE001 -- one bad file must not stop the other 2000
        return None, str(exc).splitlines()[0] if str(exc) else type(exc).__name__


def _check_task(task):
    path, rp_id, period = task
    return path, _check_file(path, rp_id, period)


def main():
    import multiprocessing

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--period", default=bc.DEFAULT_PERIOD, choices=sorted(bc.PERIODS))
    parser.add_argument("--jobs", type=int, default=os.cpu_count())
    parser.add_argument("--per-file", help="CSV with every file's counts (and 'passed')")
    args = parser.parse_args()
    rp_id = bc.PERIODS[args.period]["rp_id"]
    steps = ["all"] + bc.LONG_CHAIN_STEPS
    # First line of the output: slurm_final.sbatch reruns a saved gate whose cuts differ.
    print(f"chain_cuts: {bc.chain_cuts(args.period, rp_id)}", flush=True)

    with open(args.inventory) as f:
        rows = [r for r in csv.DictReader(f)
                if not r.get("error") and not r.get("missing_columns") and r.get("entries")]
    if not rows:
        print("ERROR: no readable file with every benchmark column", file=sys.stderr)
        return 1

    by_era = defaultdict(lambda: [0, 0.0, 0.0])
    for r in rows:
        n = int(r["entries"])
        acc = by_era[r.get("era")]
        acc[0] += n
        acc[1] += float(r["pps_fraction"] or 0) * n
        acc[2] += float(r["rp_fraction"] or 0) * n
    print(f"{'era':10} {'events':>12} {'with PPS':>9} {'RP ' + str(rp_id):>9}")
    for era, (n, pps, rp) in sorted(by_era.items()):
        print(f"{era:10} {n:>12} {pps / n:>9.4f} {rp / n:>9.4f}")

    # Largest first, so the last tasks are short and the workers finish together.
    rows.sort(key=lambda r: -int(r["size_bytes"]))
    results = {}
    context = multiprocessing.get_context("spawn")
    # Every file JITs its own filters and Cling never frees them: replace workers every few files.
    # Not ProcessPoolExecutor(max_tasks_per_child=...): on Python 3.11 it hangs at the first
    # replacement.
    tasks = [(r["path"], rp_id, args.period) for r in rows]
    with context.Pool(max(1, args.jobs), maxtasksperchild=25) as pool:
        for done, (path, result) in enumerate(pool.imap_unordered(_check_task, tasks), 1):
            results[path] = result
            print(f"[{done}/{len(rows)}] {path}", file=sys.stderr, flush=True)

    groups = defaultdict(lambda: {"files": 0, "none_left": 0, "counts": [0] * len(steps)})
    types = defaultdict(lambda: defaultdict(set))
    errors = []
    for r in rows:
        file_types, counts = results[r["path"]]
        if file_types is None:
            errors.append((r["path"], counts))
            continue
        key = f"{r.get('era')}/{r.get('version')}"
        g = groups[key]
        g["files"] += 1
        g["none_left"] += counts[-1] == 0
        g["counts"] = [a + b for a, b in zip(g["counts"], counts)]
        for column, t in file_types.items():
            types[column][t].add(key)

    if args.per_file:
        with open(args.per_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["path", "era", "version", "error"] + steps + ["passed"])
            for r in sorted(rows, key=lambda r: r["path"]):
                file_types, counts = results[r["path"]]
                if file_types is None:
                    writer.writerow([r["path"], r.get("era"), r.get("version"), counts]
                                    + [""] * (len(steps) + 1))
                else:
                    writer.writerow([r["path"], r.get("era"), r.get("version"), ""]
                                    + counts + [counts[-1]])

    print(f"\nchain11 ({args.period} cuts), events left after each filter, summed over every "
          f"file of an era/version; 'none left': files the chain leaves no event of:")
    print("  " + f"{'files':>6} {'none left':>9} " + " ".join(f"{s:>13}" for s in steps))
    for key, g in sorted(groups.items()):
        print(f"  {key}")
        print("  " + f"{g['files']:>6} {g['none_left']:>9} "
              + " ".join(f"{c:>13}" for c in g["counts"]))
    total = [sum(g["counts"][i] for g in groups.values()) for i in range(len(steps))]
    print(f"  all: {sum(g['files'] for g in groups.values())} files, "
          f"{sum(g['none_left'] for g in groups.values())} with none left, "
          f"{total[0]} events, {total[-1]} left after the chain")

    status = 0
    if errors:
        status = 3
        print(f"\n{len(errors)} files could not be read through the chain:")
        for path, error in errors[:20]:
            print(f"  {path}: {error}")

    print("\ncolumn types:")
    for column in bc.chain_columns(len(bc.LONG_CHAIN_STEPS), "long"):
        seen = types[column]
        if len(seen) == 1:
            print(f"  {column:34} {next(iter(seen))}")
        else:
            status = status or 2
            print(f"  {column:34} DIFFERS: " +
                  "; ".join(f"{t} in {', '.join(sorted(keys))}" for t, keys in sorted(seen.items())))
    if status == 2:
        print("WARNING: a column with two types cannot be read through one TChain.")
    if total[-1] == 0:
        status = status or 4
        print(f"\nERROR: the chain leaves no event of the whole set: the {args.period} cuts do not "
              "fit these files, and a campaign would time only the filters up to the first empty "
              "one.")
    return status


if __name__ == "__main__":
    sys.exit(main())
