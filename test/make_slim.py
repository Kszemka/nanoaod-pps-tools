#!/usr/bin/env python3
"""
Writes a copy of the benchmark input holding only the columns the benchmarks read.

Exists for one experiment (T6): the same events, codec and clustering as the full input, but the
6 columns the benchmarks read instead of ~2000 branches (plus whatever size branches Snapshot
writes for the jagged ones; the branch count is printed). Every ImplicitMT worker builds its own
TTree and readers over the whole schema, so if the strong-scaling ceiling comes from the file's
width rather than from the analysis, it moves when only the width changes.

  --input ds_x32.root --output ds_x32_slim.root    one file
  --input core.txt    --output core_slim.txt       a list: every file is slimmed into slim/
                                                   next to the output list, which is written
                                                   last, so its existence means "complete"

Each output keeps its source's file-level codec and mean cluster size. Written single-threaded
on purpose: a Snapshot under ImplicitMT merges per-thread buffers and does not keep the input's
cluster boundaries, and the cluster count is what ImplicitMT divides the work by. Outputs go
through a .partial name, so an interrupted run leaves nothing that looks finished, and files
already slimmed are skipped when it is restarted.
"""

import argparse
import os
import sys

import bench_common as bc

ROOT = bc.ROOT

# Compression algorithm values as stored in a TFile.
ALGORITHMS = {1: "kZLIB", 2: "kLZMA", 4: "kLZ4", 5: "kZSTD"}


def compression_algorithm(name):
    """
    The value RSnapshotOptions.fCompressionAlgorithm accepts. Up to ROOT 6.3x the field is a
    ROOT::ECompressionAlgorithm and wants ROOT::kZSTD; from 6.40 that enum is gone and the field
    is an int, which RCompressionSetting::EAlgorithm converts to.
    """
    return getattr(ROOT.ROOT, name, None) or getattr(ROOT.RCompressionSetting.EAlgorithm, name)


def slim_columns(which="all"):
    """
    all      what the three T6 benchmarks read (the 5-filter chain, filter, efficiency)
    chain11  exactly the 10 branches of the 11-filter chain, so that chain reads the whole file
             and the size of a set of these files is the volume it reads
    """
    if which == "chain11":
        return bc.chain_columns(len(bc.LONG_CHAIN_STEPS), "long")
    columns = bc.chain_columns(bc.MAX_CHAIN_LEN) + bc.EFFICIENCY_COLUMNS
    return sorted(set(columns))


def slim_file(source, output, autoflush, which="all"):
    layout = bc.tree_layout(source)
    options = ROOT.RDF.RSnapshotOptions()
    options.fMode = "RECREATE"
    algorithm = ALGORITHMS.get(layout["compression_algorithm"], "kZSTD")
    options.fCompressionAlgorithm = compression_algorithm(algorithm)
    options.fCompressionLevel = layout["compression_level"] or 5
    options.fAutoFlush = autoflush or round(layout["entries"] / max(layout["clusters"], 1))

    partial = output + ".partial"
    columns = ROOT.std.vector["std::string"](slim_columns(which))
    ROOT.RDataFrame("Events", source).Snapshot("Events", partial, columns, options)

    slim = bc.tree_layout(partial)
    print(f"{source}: {layout['entries']} entries, {layout['clusters']} clusters, "
          f"{len(layout['branches'])} branches, codec {algorithm}:{options.fCompressionLevel}")
    print(f"  -> {output}: {slim['entries']} entries, {slim['clusters']} clusters, "
          f"{len(slim['branches'])} branches")
    if slim["entries"] != layout["entries"]:
        os.remove(partial)
        raise RuntimeError(f"entry counts differ for {source}")
    os.replace(partial, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help=".root file or .txt list")
    parser.add_argument("--output", required=True, help=".root file or .txt list, matching --input")
    parser.add_argument("--autoflush", type=int, default=0,
                        help="entries per cluster; 0 keeps each source's mean cluster size")
    parser.add_argument("--columns", default="all", choices=["all", "chain11"],
                        help="all: T6's columns; chain11: the 10 branches of the 11-filter chain")
    args = parser.parse_args()

    if bc.is_file_list(args.input) != bc.is_file_list(args.output):
        print("ERROR: --input and --output must both be .root or both be .txt", file=sys.stderr)
        return 1

    try:
        if not bc.is_file_list(args.input):
            slim_file(args.input, args.output, args.autoflush, args.columns)
            return 0

        slim_dir = os.path.join(os.path.dirname(os.path.abspath(args.output)), "slim")
        os.makedirs(slim_dir, exist_ok=True)
        outputs = []
        for source in bc.input_files(args.input):
            output = os.path.join(slim_dir, os.path.basename(source))
            if not os.path.exists(output):
                slim_file(source, output, args.autoflush, args.columns)
            outputs.append(os.path.relpath(output, os.path.dirname(os.path.abspath(args.output))))
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    with open(args.output + ".partial", "w") as f:
        f.write("\n".join(outputs) + "\n")
    os.replace(args.output + ".partial", args.output)
    print(f"{len(outputs)} files -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
