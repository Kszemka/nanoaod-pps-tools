#!/usr/bin/env python3
"""
Merges a second campaign into a copy of a first one, so plot_results.py sees a single sweep.

plot_results.py reads one directory and keeps the last record per label. Two campaigns that
each start at r1 would therefore overwrite each other's repeats, so the repeats of --add are
shifted up by --shift: with --shift 1, its r1..r3 become r2..r4 and --base keeps r1. The rss_
traces are renamed the same way. Warm-ups of --add are dropped; they are never plotted and
--base already has its own.

    merge_results.py --base results/helios/full-1tb-job1 \
        --add results/helios/full-1tb-job2 --shift 1 \
        --out results/helios/full-1tb

Neither input is modified. --out must not exist yet.
"""

import argparse
import json
import os
import re
import shutil
import sys

REPEAT = re.compile(r"^r(\d+)_(.+)$")


def shift_label(label, by):
    """r1_strong_chain_rdf-lazy_t64 -> r2_strong_chain_rdf-lazy_t64 for by=1; None if not r<N>_."""
    match = REPEAT.match(label)
    if not match:
        return None
    return f"r{int(match.group(1)) + by}_{match.group(2)}"


def read_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="campaign kept as it is")
    parser.add_argument("--add", required=True, help="campaign whose repeats are shifted")
    parser.add_argument("--shift", type=int, required=True, help="added to --add's repeat numbers")
    parser.add_argument("--out", required=True, help="new directory for the merged campaign")
    args = parser.parse_args()

    if os.path.exists(args.out):
        print(f"ERROR: {args.out} already exists", file=sys.stderr)
        return 1
    base = read_jsonl(os.path.join(args.base, "raw.jsonl"))
    added = []
    renames = {}
    for record in read_jsonl(os.path.join(args.add, "raw.jsonl")):
        label = shift_label(record.get("label", ""), args.shift)
        if label is None:
            continue
        renames[record["label"]] = label
        added.append({**record, "label": label})

    clash = {r["label"] for r in base} & {r["label"] for r in added}
    if clash:
        print(f"ERROR: {len(clash)} labels exist in both, e.g. {sorted(clash)[0]}; "
              f"raise --shift", file=sys.stderr)
        return 1

    os.makedirs(args.out)
    with open(os.path.join(args.out, "raw.jsonl"), "w") as f:
        for record in base + added:
            f.write(json.dumps(record) + "\n")

    traces = 0
    for name in os.listdir(args.base):
        if name.startswith("rss_") and name.endswith(".csv"):
            shutil.copy2(os.path.join(args.base, name), os.path.join(args.out, name))
            traces += 1
    for name in os.listdir(args.add):
        old = name[4:-4] if name.startswith("rss_") and name.endswith(".csv") else None
        if old in renames:
            shutil.copy2(os.path.join(args.add, name),
                         os.path.join(args.out, f"rss_{renames[old]}.csv"))
            traces += 1

    print(f"{len(base)} records from {args.base} + {len(added)} from {args.add} "
          f"(repeats +{args.shift}) -> {args.out}/raw.jsonl, {traces} rss traces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
