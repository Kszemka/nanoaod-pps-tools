#!/usr/bin/env python3
"""
Converts a TTree dataset to RNTuple, the successor format ROOT is moving to.

Worth measuring because every result in this benchmark about *how much* RDataFrame reads is a
result about TTree's on-disk layout, not about RDataFrame. Baskets, clusters and TTreeCache are
TTree concepts; RNTuple replaces all three with pages, clusters and its own read coalescing. So
a query whose bytes-read curve looks the way it does because of basket granularity should look
different here, and one that looks that way because of what the query asks for should not.

The API moved between releases, which is why both spellings are tried: Ares has ROOT 6.32,
where RNTuple is in the Experimental namespace, and newer releases have promoted it.

Usage:
    python test/make_rntuple.py --input data/ds_x8.root --out data/ds_x8_rntuple.root
"""

import argparse
import json
import os
import sys

import ROOT

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_dataset  # noqa: E402  -- for merge_info's locking, shared with the TTree builder


def rntuple_importer():
    """RNTupleImporter under whichever namespace this ROOT release keeps it in."""
    for holder in (getattr(ROOT, "Experimental", None), ROOT):
        importer = getattr(holder, "RNTupleImporter", None)
        if importer is not None:
            return importer
    sys.exit(f"ROOT {ROOT.gROOT.GetVersion()} has no RNTupleImporter")


def from_rntuple(name, path):
    """RDataFrame over an RNTuple, under whichever namespace this release keeps it in."""
    for holder in (ROOT.RDF, getattr(ROOT.RDF, "Experimental", None)):
        factory = getattr(holder, "FromRNTuple", None)
        if factory is not None:
            return factory(name, path)
    sys.exit(f"ROOT {ROOT.gROOT.GetVersion()} cannot make an RDataFrame from an RNTuple")


def convert(source, out_path, tree="Events", name=None, max_entries=0):
    name = name or tree
    importer = rntuple_importer().Create(source, tree, out_path)
    importer.SetNTupleName(name)
    importer.SetIsQuiet(True)
    if max_entries:
        importer.SetMaxEntries(max_entries)
    importer.Import()
    return out_path


def describe(path, name="Events"):
    df = from_rntuple(name, path)
    return {
        "path": os.path.abspath(path),
        "format": "rntuple",
        "ntuple": name,
        "n_events": int(df.Count().GetValue()),
        "file_size_bytes": os.path.getsize(path),
        "n_fields": len(list(df.GetColumnNames())),
        "root_version": ROOT.gROOT.GetVersion(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="TTree .root file to convert")
    parser.add_argument("--out", required=True)
    parser.add_argument("--tree", default="Events")
    parser.add_argument("--name", default=None, help="RNTuple name (default: same as --tree)")
    parser.add_argument("--max-entries", type=int, default=0)
    parser.add_argument("--describe-only", action="store_true")
    args = parser.parse_args()

    if not args.describe_only:
        if not os.path.exists(args.input):
            sys.exit(f"Input not found: {args.input}")
        print(f"Converting {args.input} -> {args.out} (RNTuple)")
        convert(args.input, args.out, args.tree, args.name, args.max_entries)

    info = describe(args.out, args.name or args.tree)
    print(json.dumps(info, indent=2))

    source_size = os.path.getsize(args.input) if os.path.exists(args.input) else 0
    if source_size:
        print(f"\n-> size vs the TTree file: {info['file_size_bytes'] / source_size:.2f}x")

    info_path = os.path.join(os.path.dirname(os.path.abspath(args.out)), "dataset_info.json")
    make_dataset.merge_info(info_path, os.path.basename(args.out), info)
    print(f"-> dataset info written to {info_path}")


if __name__ == "__main__":
    main()
