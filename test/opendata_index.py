#!/usr/bin/env python3
"""
Lists the files of CMS NanoAOD datasets on the CERN Open Data portal: one CSV row per file.

The portal's search API returns, for every dataset record, its full file index -- xrootd URI,
size and adler32 checksum of each file -- so nothing has to be collected by hand. The rows are
ordered by --era (in the order given), then dataset and file name, which is the order
make_filelists.py --era-order fills a transfer budget in.

Open Data is public: no account, certificate or proxy is involved at any step.

    python test/opendata_index.py --era Run2016H Run2016G --output index.csv --urls scan.txt
    python test/opendata_index.py --recid 30563 30530 --output index.csv

scan.txt (one URI per line) is the input for inventory_files.py, which opens each file remotely
to check its schema and PPS content before anything is downloaded.
"""

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request

API = "https://opendata.cern.ch/api/records/"
PAGE_SIZE = 50
FIELDS = ["uri", "name", "size_bytes", "adler32", "recid", "era", "primary_dataset", "version"]


def get_json(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def search(title_match):
    """Every CMS NanoAOD dataset record whose title contains title_match."""
    records, page = [], 1
    while True:
        query = urllib.parse.urlencode({
            "type": "Dataset", "experiment": "CMS", "file_type": "nanoaod",
            "size": PAGE_SIZE, "page": page, "sort": "mostrecent",
        })
        hits = get_json(f"{API}?{query}")["hits"]
        records += [h["metadata"] for h in hits["hits"]]
        if page * PAGE_SIZE >= hits["total"] or not hits["hits"]:
            break
        page += 1
    return [r for r in records if title_match in r.get("title", "")]


def by_recid(recids):
    return [get_json(f"{API}{recid}")["metadata"] for recid in recids]


def files_of(record):
    """
    Rows for one record. The title is /<PD>/<era>-<version>/NANOAOD, e.g.
    /SingleMuon/Run2016H-UL2016_MiniAODv2_NanoAODv9-v1/NANOAOD.
    """
    _, pd, processed, _ = record["title"].split("/")
    era, version = processed.split("-", 1)
    rows = []
    for index in record.get("_file_indices", []):
        for f in index["files"]:
            if not f["filename"].endswith(".root"):
                continue
            rows.append({
                "uri": f["uri"], "name": f["filename"], "size_bytes": f["size"],
                "adler32": f["checksum"].split(":", 1)[1] if f.get("checksum") else "",
                "recid": record["recid"], "era": era, "primary_dataset": pd, "version": version,
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--era", nargs="+", default=["Run2016H", "Run2016G"],
                        help="eras to keep, in order of preference")
    parser.add_argument("--title-match", default="UL2016_MiniAODv2_NanoAODv9",
                        help="substring of the dataset title (processing version)")
    parser.add_argument("--recid", nargs="+", help="these records only, instead of a search")
    parser.add_argument("--output", required=True, help="CSV to write")
    parser.add_argument("--urls", help="also write the URIs here, one per line")
    args = parser.parse_args()

    records = by_recid(args.recid) if args.recid else search(args.title_match)
    rows = [row for record in records for row in files_of(record)]
    if not args.recid:
        rows = [r for r in rows if r["era"] in args.era]
    rank = {era: i for i, era in enumerate(args.era)}
    rows.sort(key=lambda r: (rank.get(r["era"], len(rank)), r["primary_dataset"], r["name"]))
    if not rows:
        print("ERROR: no files matched", file=sys.stderr)
        return 1

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    if args.urls:
        with open(args.urls, "w") as f:
            f.writelines(r["uri"] + "\n" for r in rows)

    print(f"{len(records)} records, {len(rows)} files -> {args.output}")
    print(f"{'era':10} {'primary dataset':20} {'files':>5} {'GB':>8}")
    totals = {}
    for r in rows:
        t = totals.setdefault((r["era"], r["primary_dataset"]), [0, 0])
        t[0] += 1
        t[1] += r["size_bytes"]
    for (era, pd), (n, size) in totals.items():
        print(f"{era:10} {pd:20} {n:>5} {size / 1e9:>8.1f}")
    print(f"{'total':31} {len(rows):>5} {sum(r['size_bytes'] for r in rows) / 1e9:>8.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
