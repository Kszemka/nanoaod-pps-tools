#!/usr/bin/env python3
"""
Writes the first N entries of a file: the same branches and codec, fewer clusters.

Exists for one experiment: does the memory each ImplicitMT worker costs depend on how many
branches a file stores, or on branches x baskets, i.e. also on how long the file is? ds_x32 is
32 copies of examples/test.root merged into one 10.8 GB file (1111 clusters); its head keeps all
~2000 branches and ZSTD:5 but has 1/32 of the clusters. A list naming the head many times has
the events of the full set with short files.

    make_head.py --input ds_x32.root --output ds_x32_head.root [--entries 346825]

N is rounded up to the next cluster boundary. A partial tree cannot be fast-cloned, so the
entries are re-compressed with the source's settings and its mean cluster size (AutoFlush); the
output's codec, clusters and basket count are printed. Only the Events tree is written. Output
goes through a .partial name.
"""

import argparse
import os
import sys

import bench_common as bc

ROOT = bc.ROOT


def cluster_boundary(tree, entries):
    """The first cluster boundary at or after `entries`."""
    iterator = tree.GetClusterIterator(0)
    total = tree.GetEntries()
    start = iterator.Next()
    while start < entries and start < total:
        start = iterator.Next()
    return min(start, total)


def describe(name, layout):
    algorithm, level = layout["compression_algorithm"], layout["compression_level"]
    return (f"{name}: {layout['entries']} entries, {layout['clusters']} clusters, "
            f"{len(layout['branches'])} branches, {layout['baskets']} baskets, "
            f"codec {algorithm}:{level}, {layout['size_bytes'] / 1e9:.2f} GB")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--entries", type=int, default=346825,
                        help="entries to keep, rounded up to a cluster boundary "
                             "(default: one examples/test.root)")
    args = parser.parse_args()

    try:
        before = bc.tree_layout(args.input)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    source = ROOT.TFile.Open(args.input)
    tree = source.Get("Events")
    entries = cluster_boundary(tree, args.entries)

    partial = args.output + ".partial"
    target = ROOT.TFile(partial, "RECREATE", "", source.GetCompressionSettings())
    head = tree.CloneTree(0)
    # A partial copy is re-compressed, and without this the output is one cluster: one
    # ImplicitMT task per file instead of the source's granularity.
    head.SetAutoFlush(round(before["entries"] / max(before["clusters"], 1)))
    head.CopyEntries(tree, entries, "fast")
    target.cd()
    head.Write()
    target.Close()
    source.Close()

    after = bc.tree_layout(partial)
    print(describe(args.input, before))
    print(describe(args.output, after))
    same = (after["entries"] == entries and after["branches"] == before["branches"]
            and after["compression_algorithm"] == before["compression_algorithm"])
    if not same:
        os.remove(partial)
        print("ERROR: entries, branches or codec differ from the source", file=sys.stderr)
        return 1
    os.replace(partial, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
