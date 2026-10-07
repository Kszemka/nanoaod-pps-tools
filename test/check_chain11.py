#!/usr/bin/env python3
"""
Before a campaign on a mixed real dataset: does the 11-filter chain mean the same thing in
every part of it?

One file per (era, processing version) of an inventory_files.py CSV:
  types   the C++ type of each of the chain's 10 columns. A TChain over files that store a
          column with different types breaks, or reads garbage, as soon as that column is read;
          the inventory's schema hash only compares branch names.
  chain   events left after each of the 11 filters (Report(), one event loop). A period whose
          pots or detector type differ from the cuts in bench_spec.PERIODS shows up here as a
          step that drops every event.
and, from the CSV itself, the fraction of events with PPS tracks and with a track in the
default RP, per era.

    check_chain11.py --inventory local.csv [--period 2023]
"""

import argparse
import csv
import sys
from collections import defaultdict

import bench_common as bc
import impl_rdf

ROOT = bc.ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--period", default=bc.DEFAULT_PERIOD, choices=sorted(bc.PERIODS))
    args = parser.parse_args()
    rp_id = bc.PERIODS[args.period]["rp_id"]

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

    first = {}
    for r in sorted(rows, key=lambda r: r["path"]):
        first.setdefault((r.get("era"), r.get("version")), r["path"])

    columns = bc.chain_columns(len(bc.LONG_CHAIN_STEPS), "long")
    types = {}
    print(f"\nchain11 ({args.period} cuts), events left after each filter, one file per era/version:")
    print("  " + " ".join(f"{s:>13}" for s in ["all"] + bc.LONG_CHAIN_STEPS))
    for (era, version), path in sorted(first.items()):
        df = ROOT.RDataFrame("Events", path)
        types[(era, version)] = {c: str(df.GetColumnType(c)) for c in columns}
        nodes = impl_rdf.build_chain_nodes(df, len(bc.LONG_CHAIN_STEPS), rp_id, "long",
                                           args.period)
        counts = impl_rdf.trigger_chain_report(impl_rdf.build_chain_report(nodes))["intermediate"]
        print(f"  {era}/{version}")
        print("  " + " ".join(f"{c:>13}" for c in counts))

    print("\ncolumn types:")
    status = 0
    for column in columns:
        seen = defaultdict(list)
        for key, t in types.items():
            seen[t[column]].append("/".join(str(k) for k in key))
        if len(seen) == 1:
            print(f"  {column:34} {next(iter(seen))}")
        else:
            status = 2
            print(f"  {column:34} DIFFERS: " +
                  "; ".join(f"{t} in {', '.join(keys)}" for t, keys in sorted(seen.items())))
    if status:
        print("WARNING: a column with two types cannot be read through one TChain.")
    return status


if __name__ == "__main__":
    sys.exit(main())
