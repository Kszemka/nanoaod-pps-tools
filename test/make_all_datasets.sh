#!/usr/bin/env bash
#
# Generates every benchmark dataset. Split out from run_benchmark.sh because with the source
# file's compression this takes hours, and it only has to happen once -- run it as its own
# long SLURM job, not inside the measurement job.
#
# Usage: DATA_DIR=$SCRATCH/bench/data ./test/make_all_datasets.sh

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PY:-python3}"
DATA_DIR="${DATA_DIR:-$TEST_DIR/data}"
SOURCE="${SOURCE:-$(dirname "$TEST_DIR")/examples/test.root}"
# ZSTD rather than the source file's LZMA:9. Measured on the source: 70 s/copy against 156 s,
# at the cost of ~37% larger files. Set here rather than left to the caller so a forgotten
# environment variable cannot produce a size series with mixed algorithms -- decompression cost
# is part of the measured event loop, so mixing them within one plot would invalidate it.
COMPRESSION="${COMPRESSION:-5:5}"
# Snapshot is single-threaded, so on a 48-core node the default run leaves the node idle for
# hours. The files are independent, so JOBS>1 builds several at once and the whole thing takes
# about as long as its largest member instead of the sum. Concurrent writers to
# dataset_info.json are safe because make_dataset.py merges its entry under a lock.
#
# Left at 1 by default: this is compression-bound, and oversubscribing a login node is the
# kind of thing that gets an account suspended.
JOBS="${JOBS:-1}"
LOG_DIR="${LOG_DIR:-$DATA_DIR/logs}"

mkdir -p "$DATA_DIR"

# set -e plus background builds would otherwise leave half-written ROOT files behind: the
# script exits, the builds do not, and what they leave on disk passes every later `-f` test.
cleanup_builds() {
    local pids
    pids="$(jobs -rp)"
    if [[ -n "$pids" ]]; then
        echo "stopping unfinished builds: $pids" >&2
        # shellcheck disable=SC2086  -- word splitting is what turns the pid list into args
        kill $pids 2>/dev/null || true
    fi
}
trap cleanup_builds EXIT

# Blocks until fewer than JOBS builds are running. `wait -n` would be tidier but needs bash
# 4.3, and the Cyfronet nodes are not guaranteed to have it.
wait_for_slot() {
    while [[ "$(jobs -rp | wc -l)" -ge "$JOBS" ]]; do
        sleep 10
    done
}

gen() {
    local name="$1" copies="$2" autoflush="$3"
    shift 3
    local out="$DATA_DIR/${name}.root"
    if [[ -f "$out" ]]; then
        echo "== $name exists, describing only"
        if [[ -L "$out" ]]; then
            echo "   note: symlink to $(readlink "$out")"
        fi
        # --expect-settings so a reused file that was built with a different codec or a
        # different autoflush stops the run now, in seconds, rather than at the consistency
        # report after the generation has finished.
        "$PY" "$TEST_DIR/make_dataset.py" --out "$out" --copies "$copies" --describe-only \
            --autoflush "$autoflush" ${COMPRESSION:+--compression "$COMPRESSION"} \
            --expect-settings
        return
    fi
    echo "== $name: $copies copies, autoflush=$autoflush $*"
    local -a args=(--source "$SOURCE" --out "$out" --copies "$copies" --autoflush "$autoflush")
    [[ -n "$COMPRESSION" ]] && args+=(--compression "$COMPRESSION")
    if [[ "$JOBS" -le 1 ]]; then
        "$PY" "$TEST_DIR/make_dataset.py" "${args[@]}" "$@"
        return
    fi
    # Each build gets its own log, because interleaving six of them on one stream makes the
    # output useless exactly when something fails.
    mkdir -p "$LOG_DIR"
    wait_for_slot
    echo "   -> background, log in $LOG_DIR/${name}.log"
    "$PY" "$TEST_DIR/make_dataset.py" "${args[@]}" "$@" >"$LOG_DIR/${name}.log" 2>&1 &
}

# Fails the script if any background build failed, rather than leaving a half-built series to
# be discovered by run_benchmark.sh hours later.
wait_for_builds() {
    [[ "$JOBS" -le 1 ]] && return 0
    local pid failed=0
    for pid in $(jobs -rp); do
        wait "$pid" || failed=1
    done
    if [[ "$failed" -ne 0 ]]; then
        echo "ERROR: at least one dataset build failed; see $LOG_DIR/*.log" >&2
        exit 1
    fi
}

# The S dataset is the source file itself -- one "copy" would just re-encode identical content.
# Copied rather than symlinked so DATA_DIR stays self-contained on $SCRATCH.
echo "== ds_s: copy of $SOURCE"
if [[ ! -f "$DATA_DIR/ds_s.root" ]]; then
    cp "$SOURCE" "$DATA_DIR/ds_s.root"
fi
"$PY" "$TEST_DIR/make_dataset.py" --out "$DATA_DIR/ds_s.root" --copies 1 --describe-only

# ds_l is not a measurement dataset and no sweep points at it. It exists only because it is
# the one file that shows the read anomaly -- chain-len 1 reading 10.2 GB, growing to 20.4 GB
# at 4 threads -- and run_all.sh runs diag_io.py over it, which is read-only and takes seconds.
#
# Timing it instead of diagnosing it was the mistake it is here to avoid repeating: on Ares
# 36 runs cost 1.77 h, 11 of them hit the timeout and recorded nothing, and in those that
# finished setup outweighed the event loop (202 s against 84 s for efficiency/jit).
#
# Skip with WANT_DS_L=0 if you are not chasing the anomaly: it is 40 copies, ~11 GB and the
# single longest item in this script.
if [[ "${WANT_DS_L:-1}" != "0" ]]; then
    gen ds_l 40 15000
fi

# Size series for the memory- and time-vs-size plots. One autoflush for the whole series, so
# clustering does not vary along the x axis and turn into a hidden second variable -- which is
# why x1 is regenerated here instead of reusing the ds_s copy above.
#
# ds_x8 is also the main dataset for the thread, chain and layout sweeps, so the series is not
# an extra cost: those sweeps reuse a file the size plots need anyway.
#
# Stops at 32: measured 5.4 min per copy on an Ares node, so an x64 point alone would cost
# ~5.8 h for one more marker on a log-log fit that already spans 1.5 decades.
SERIES="${SERIES:-1 2 4 8 16 32}"
for copies in $SERIES; do
    gen "ds_x${copies}" "$copies" 10000
done

# Control for the thread-scaling plateau: the same 8 copies as ds_x8, an order of magnitude
# fewer TTree clusters. RDataFrame parallelises over clusters, so if the plateau moves with
# this file, it is a property of the data layout rather than of the code.
#
# It has to be 8 copies, matching ds_x8 exactly. A coarse twin of a different size would let
# volume masquerade as clustering, which is the one thing this control is for -- run_benchmark.sh
# refuses to run the comparison if the two differ in event count.
gen ds_x8_coarse 8 250000

# --- read amplification: what in the file layout causes it -----------------------------------
#
# On the source NanoAOD the full chain reads 1.04x the compressed size of the branches it names.
# On a Snapshot-built copy the same query reached ~560x. Both files hold the same events, so the
# difference is layout, and these two variants separate the candidate causes.
#
# slim: only the branches the chain actually touches, instead of all ~2000. If amplification
# drops, the cause is that the baskets of unrelated branches are interleaved with the wanted
# ones, so a read of one drags in the others.
#
# The other candidate cause, basket granularity, needs no file of its own: ds_x8_coarse above
# has the same content with a 25x larger autoflush and therefore much larger baskets, so
# cmd_layout uses it as the large-basket arm.
gen ds_x8_slim 8 10000 --slim

# Everything above may still be running under JOBS>1, and what follows reads those files: the
# RNTuple conversion needs a complete ds_x8, and the consistency check needs every description
# written.
wait_for_builds

# RNTuple copy of the main dataset. Baskets, clusters and TTreeCache are TTree concepts, so
# every bytes-read result in this benchmark is partly a result about the format; RNTuple is the
# control that says how much. Converted from ds_x8 rather than generated from the source, so
# the two hold exactly the same events.
if [[ -f "$DATA_DIR/ds_x8.root" && ! -f "$DATA_DIR/ds_x8_rntuple.root" ]]; then
    echo "== ds_x8_rntuple: converting ds_x8"
    "$PY" "$TEST_DIR/make_rntuple.py" --input "$DATA_DIR/ds_x8.root" \
        --out "$DATA_DIR/ds_x8_rntuple.root" || \
        echo "   RNTuple conversion failed -- the format comparison will be skipped" >&2
fi

echo
echo "Datasets in $DATA_DIR:"
du -sh "$DATA_DIR"/*.root

# The size series is only a valid plot if every point differs in size alone. Files generated
# before this script fixed the codec inherited the source's LZMA:9, and a series that mixes
# LZMA and ZSTD points measures the codec along the x axis as well, because decompression
# happens inside the measured event loop. Same for autoflush, which sets the clustering.
#
# Checked here rather than trusted, because the failure is invisible in the plot: the points
# still line up, just on the wrong slope.
echo
"$PY" - "$DATA_DIR/dataset_info.json" <<'PYEOF'
import json, re, sys

try:
    info = json.load(open(sys.argv[1]))
except (OSError, ValueError) as exc:
    print(f"cannot check series consistency: {exc}")
    raise SystemExit(0)

series = {}
for name, entry in info.items():
    match = re.fullmatch(r"ds_x(\d+)\.root", name)
    if match:
        series[int(match.group(1))] = entry

if len(series) < 2:
    print("series consistency: fewer than two ds_xN files described, nothing to compare")
    raise SystemExit(0)

def key(entry):
    return (entry.get("compression_algorithm"), entry.get("compression_level"),
            entry.get("auto_flush"))

print(f"{'file':14} {'events':>10} {'clusters':>9} {'GB':>6}  {'compression':>12} {'autoflush':>10}")
for copies in sorted(series):
    e = series[copies]
    algorithm, level, autoflush = key(e)
    print(f"ds_x{copies:<10} {e.get('n_events', 0):>10} {e.get('n_clusters', 0):>9} "
          f"{(e.get('file_size_bytes') or 0) / 1e9:6.2f}  {str(algorithm) + ':' + str(level):>12} "
          f"{str(autoflush):>10}")

groups = {}
for copies, entry in series.items():
    groups.setdefault(key(entry), []).append(copies)
if len(groups) > 1:
    print()
    print("ERROR: the size series mixes settings, so its plots would not be comparable:")
    for (algorithm, level, autoflush), members in sorted(groups.items(), key=lambda kv: min(kv[1])):
        members = ", ".join(f"ds_x{n}" for n in sorted(members))
        print(f"  compression {algorithm}:{level}, autoflush {autoflush}  ->  {members}")
    print("Delete the odd ones out and re-run this script to regenerate them.")
    raise SystemExit(1)
print()
print("series consistency: all ds_xN share compression and autoflush")
PYEOF
