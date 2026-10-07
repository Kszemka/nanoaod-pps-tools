#!/usr/bin/env python3
"""
Builds the benchmark's file lists from an inventory_files.py CSV.

Eligible files: readable, every benchmark column present, PPS in at least --min-pps of the
events, optionally one run and one processing version, and then one schema -- the one with the
most events, unless --schema names another. Mixing schemas in a TChain works only as long as
no branch that differs is read, which is not a property worth resting a benchmark on.

Two uses:

  1. Before the transfer, on the lxplus inventory: --transfer-list writes the selected paths
     relative to --strip-prefix, ready for `rsync -R --files-from`. On a remote inventory of
     CERN Open Data, with --max-gb and --era-order, it writes the URLs fetch_opendata.sh takes.
     Open Data files differ in schema (HLT menus change between runs), so --any-schema keeps
     them all; the benchmark columns are checked in every file regardless.
  2. After it, on the Ares inventory: writes into --out-dir
       core.txt       T1 (and T6 via make_slim.py): up to --core-events or --core-gb
       weak_<N>.txt   T2: subsets of core.txt with ~N x (core events / max N) events each
       impl.txt       T4 and T5: ~--impl-events, so the Python paths stay within ~20 min
       sets.json      events, clusters and GB of every list, and the weak series' deviation
                      from its target -- real files come in uneven sizes
     --interleave orders the files so that every prefix has the whole set's era/PD mix, and
     --nested makes weak_N and impl prefixes of core.txt, each one inside the next: with both,
     a weak point differs from its neighbours in size alone, not in which data it holds.

Paths inside --out-dir are written relative to it, so the lists move with the data.
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict


def load(path):
    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("error") or not row.get("entries"):
                continue
            for field in ("entries", "clusters", "size_bytes"):
                row[field] = int(row[field])
            row["pps_fraction"] = float(row["pps_fraction"]) if row.get("pps_fraction") else None
            rows.append(row)
    return rows


def eligible(rows, args):
    out = []
    for row in rows:
        if row.get("missing_columns"):
            continue
        if row["pps_fraction"] is None or row["pps_fraction"] < args.min_pps:
            continue
        if args.run and str(row.get("run")) != str(args.run):
            continue
        if args.version and row.get("version") != args.version:
            continue
        out.append(row)
    if not out:
        return [], None
    events_by_schema = defaultdict(int)
    for row in out:
        events_by_schema[row["schema"]] += row["entries"]
    if args.any_schema:
        return sorted(out, key=lambda r: r["path"]), " ".join(sorted(events_by_schema))
    schema = args.schema or max(events_by_schema, key=events_by_schema.get)
    return sorted((r for r in out if r["schema"] == schema), key=lambda r: r["path"]), schema


def print_schemas(files):
    groups = defaultdict(lambda: [0, 0, 0, 0])
    for row in files:
        g = groups[row["schema"]]
        g[0] += 1
        g[1] += row["entries"]
        g[2] += row["size_bytes"]
        g[3] = row.get("n_branches", "")
    print(f"  {'schema':12} {'branches':>8} {'files':>5} {'events':>12} {'GB':>8}")
    for schema, (n, events, size, branches) in sorted(groups.items(), key=lambda kv: -kv[1][1]):
        print(f"  {schema:12} {branches:>8} {n:>5} {events:>12} {size / 1e9:>8.1f}")


def within_budget(files, max_gb, era_order):
    """
    Files in --era-order (eras not named come last), each file within an era in path order,
    taken while the running total stays within max_gb.
    """
    rank = {era: i for i, era in enumerate(era_order or [])}
    ordered = sorted(files, key=lambda r: (rank.get(r.get("era"), len(rank)), r["path"]))
    if not max_gb:
        return ordered
    chosen, size = [], 0
    for row in ordered:
        if size + row["size_bytes"] > max_gb * 1e9:
            break
        chosen.append(row)
        size += row["size_bytes"]
    return chosen


def closest_subset(files, target, tolerance=0.02):
    """
    Greedy subset whose event count is as close to target as uneven file sizes allow.

    Largest files first, each taken if it keeps the total within tolerance above the target;
    when even the smallest file overshoots, that file alone.
    """
    chosen, total = [], 0
    for row in sorted(files, key=lambda r: -r["entries"]):
        if total + row["entries"] <= target * (1 + tolerance):
            chosen.append(row)
            total += row["entries"]
    if not chosen:
        chosen = [min(files, key=lambda r: r["entries"])]
    return sorted(chosen, key=lambda r: r["path"])


def interleave(files):
    """
    Files of every (era, primary dataset) spread evenly through the list, by events.

    Each file sits at the middle of its share of its group's events, as a fraction of the
    group, and the list is sorted on that. Every prefix then holds each group in its overall
    proportion, so a weak-scaling point at 4 threads reads the same mix of 2023 and 2024,
    Muon0 and Muon1, as the one at 96.
    """
    groups = defaultdict(list)
    for row in sorted(files, key=lambda r: r["path"]):
        groups[(row.get("era"), row.get("primary_dataset"))].append(row)
    keyed = []
    for key, rows in groups.items():
        total, before = sum(r["entries"] for r in rows) or 1, 0
        for row in rows:
            keyed.append(((before + row["entries"] / 2) / total, str(key), row))
            before += row["entries"]
    return [row for _, _, row in sorted(keyed, key=lambda k: (k[0], k[1]))]


def closest_prefix(files, target):
    """The prefix of files whose event count is closest to target, at least one file."""
    best, best_gap, total = 1, None, 0
    for count, row in enumerate(files, 1):
        total += row["entries"]
        gap = abs(total - target)
        if best_gap is None or gap < best_gap:
            best, best_gap = count, gap
        if total > target:
            break
    return files[:best]


def describe(files):
    return {
        "files": len(files),
        "events": sum(r["entries"] for r in files),
        "clusters": sum(r["clusters"] for r in files),
        "gb": round(sum(r["size_bytes"] for r in files) / 1e9, 2),
    }


def write_list(path, files, out_dir):
    with open(path, "w") as f:
        for row in files:
            p = os.path.abspath(row["path"])
            if p.startswith(os.path.abspath(out_dir) + os.sep):
                p = os.path.relpath(p, out_dir)
            f.write(p + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--run", help="keep one run only, e.g. 369998")
    parser.add_argument("--version", help="keep one processing version, e.g. PromptReco-v21141959")
    parser.add_argument("--schema", help="schema hash to use instead of the largest one")
    parser.add_argument("--any-schema", action="store_true",
                        help="keep every schema; safe as long as the benchmark columns are in all")
    parser.add_argument("--min-pps", type=float, default=0.01,
                        help="minimum fraction of events with nPPSLocalTrack > 0")
    parser.add_argument("--transfer-list", help="write the selected paths here and stop")
    parser.add_argument("--strip-prefix", default="",
                        help="with --transfer-list: removed from the front of every path")
    parser.add_argument("--max-gb", type=float,
                        help="with --transfer-list: stop adding files at this total size")
    parser.add_argument("--era-order", nargs="+",
                        help="with --transfer-list: eras to fill --max-gb from, in this order")
    parser.add_argument("--out-dir", help="where the lists go (default: next to the inventory)")
    parser.add_argument("--core-events", type=float, default=45e6)
    parser.add_argument("--core-gb", type=float, default=60.0,
                        help="page-cache budget: 192 GB node, ~12 GB RSS at 48 threads")
    parser.add_argument("--impl-events", type=float, default=11.1e6)
    parser.add_argument("--weak-series", default="1 2 4 8 16 32 48")
    parser.add_argument("--interleave", action="store_true",
                        help="order core.txt so that every prefix has the same era/PD mix")
    parser.add_argument("--nested", action="store_true",
                        help="weak_N.txt and impl.txt as prefixes of core.txt, each containing "
                             "the smaller ones, instead of greedy subsets")
    args = parser.parse_args()

    files, schema = eligible(load(args.inventory), args)
    if not files:
        print("ERROR: no eligible files (check --run, --version, --min-pps)", file=sys.stderr)
        return 1
    if args.interleave:
        files = interleave(files)
    summary = describe(files)
    print(f"eligible: {summary['files']} files, {summary['events']} events, "
          f"{summary['gb']} GB, schema {schema}")
    if args.any_schema:
        print_schemas(files)

    if args.transfer_list:
        selected = within_budget(files, args.max_gb, args.era_order)
        prefix = args.strip_prefix.rstrip("/") + "/" if args.strip_prefix else ""
        with open(args.transfer_list, "w") as f:
            for row in selected:
                path = row["path"]
                f.write((path[len(prefix):] if prefix and path.startswith(prefix) else path) + "\n")
        chosen = describe(selected)
        print(f"{chosen['files']} paths, {chosen['events']} events, {chosen['gb']} GB "
              f"-> {args.transfer_list}")
        if args.any_schema:
            print_schemas(selected)
        return 0

    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.inventory))
    os.makedirs(out_dir, exist_ok=True)

    core, events, size = [], 0, 0
    for row in files:
        if events >= args.core_events or size + row["size_bytes"] > args.core_gb * 1e9:
            break
        core.append(row)
        events += row["entries"]
        size += row["size_bytes"]
    if not core:
        print(f"ERROR: the first eligible file alone exceeds --core-gb {args.core_gb}",
              file=sys.stderr)
        return 1

    series = [int(n) for n in args.weak_series.split()]
    unit = events / max(series)
    subset_of = closest_prefix if args.nested else closest_subset
    sets = {"schema": schema, "core": describe(core), "weak": {}, "impl": None,
            "order": "interleaved" if args.interleave else "path",
            "subsets": "prefixes" if args.nested else "closest"}
    write_list(os.path.join(out_dir, "core.txt"), core, out_dir)

    for n in series:
        subset = subset_of(core, n * unit)
        info = describe(subset)
        info["target_events"] = round(n * unit)
        info["deviation"] = round(info["events"] / (n * unit) - 1, 4)
        info["clusters_per_thread"] = round(info["clusters"] / n, 1)
        sets["weak"][n] = info
        write_list(os.path.join(out_dir, f"weak_{n}.txt"), subset, out_dir)

    impl = subset_of(core, min(args.impl_events, events))
    sets["impl"] = describe(impl)
    write_list(os.path.join(out_dir, "impl.txt"), impl, out_dir)

    with open(os.path.join(out_dir, "sets.json"), "w") as f:
        json.dump(sets, f, indent=2)

    print(f"{'list':>10} {'files':>5} {'events':>12} {'clusters':>8} {'GB':>7}  notes")
    c = sets["core"]
    print(f"{'core':>10} {c['files']:>5} {c['events']:>12} {c['clusters']:>8} {c['gb']:>7}")
    for n, w in sets["weak"].items():
        print(f"{'weak_' + str(n):>10} {w['files']:>5} {w['events']:>12} {w['clusters']:>8} "
              f"{w['gb']:>7}  {w['deviation']:+.1%} vs target, "
              f"{w['clusters_per_thread']} clusters/thread")
    i = sets["impl"]
    print(f"{'impl':>10} {i['files']:>5} {i['events']:>12} {i['clusters']:>8} {i['gb']:>7}")
    print(f"lists and sets.json -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
