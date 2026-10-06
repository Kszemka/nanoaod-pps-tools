#!/usr/bin/env python3
"""
Writes <results dir>/dataset.json: codec, branches, clusters and baskets of a benchmark input.

The plotting scripts need no ROOT and so cannot read the files themselves. Clusters and baskets
are per file, the median over up to --sample distinct files spread across the input: every
ImplicitMT worker opens one file at a time, so it is one file's layout that it pays for.

    dataset_json.py --out RESULTS --input core.txt [--inventory local.csv]
    dataset_json.py --out RESULTS --input ds_1.root

--inventory (inventory_files.py output) adds the event and schema counts and the branch range
over every file of the input, not only the sampled ones.
"""

import argparse
import csv
import json
import os
import sys

import bench_common as bc

CODECS = {1: "ZLIB", 2: "LZMA", 4: "LZ4", 5: "ZSTD"}


def median(values):
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def codec_name(algorithm, level):
    return f"{CODECS.get(int(algorithm), algorithm)}:{level}"


def describe(input_path, inventory=None, sample=5):
    files = list(dict.fromkeys(bc.input_files(input_path)))
    step = max(len(files) // sample, 1)
    layouts = [bc.tree_layout(path) for path in files[::step][:sample]]
    branches = sorted({len(layout["branches"]) for layout in layouts})
    info = {
        "files": len(bc.input_files(input_path)),
        "distinct_files": len(files),
        "branches": str(branches[0]) if len(branches) == 1 else f"{branches[0]}-{branches[-1]}",
        "branches_median": median([len(layout["branches"]) for layout in layouts]),
        "clusters_per_file": median([layout["clusters"] for layout in layouts]),
        "baskets_per_file": median([layout["baskets"] for layout in layouts]),
        "codec": " ".join(sorted({codec_name(layout["compression_algorithm"],
                                             layout["compression_level"]) for layout in layouts})),
        "sampled": len(layouts),
    }
    if inventory:
        names = {os.path.basename(path) for path in files}
        with open(inventory) as f:
            rows = [r for r in csv.DictReader(f) if r["name"] in names]
        counts = sorted({int(r["n_branches"]) for r in rows})
        info["events"] = sum(int(r["entries"]) for r in rows)
        info["schemas"] = len({r["schema"] for r in rows})
        info["branches"] = str(counts[0]) if len(counts) == 1 else f"{counts[0]}-{counts[-1]}"
        info["codec"] = " ".join(sorted({codec_name(*r["compression"].split(":")) for r in rows}))
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="results directory")
    parser.add_argument("--input", required=True, help=".root file or .txt list")
    parser.add_argument("--inventory", help="inventory CSV covering the input's files")
    parser.add_argument("--sample", type=int, default=5)
    args = parser.parse_args()
    try:
        info = describe(args.input, args.inventory, args.sample)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "dataset.json"), "w") as f:
        json.dump(info, f, indent=1)
    print("dataset.json:", info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
