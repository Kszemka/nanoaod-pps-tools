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

mkdir -p "$DATA_DIR"

gen() {
    local name="$1" copies="$2" autoflush="$3"
    local out="$DATA_DIR/${name}.root"
    if [[ -f "$out" ]]; then
        echo "== $name exists, describing only"
        "$PY" "$TEST_DIR/make_dataset.py" --out "$out" --copies "$copies" --describe-only
        return
    fi
    echo "== $name: $copies copies, autoflush=$autoflush"
    local -a args=(--source "$SOURCE" --out "$out" --copies "$copies" --autoflush "$autoflush")
    [[ -n "$COMPRESSION" ]] && args+=(--compression "$COMPRESSION")
    "$PY" "$TEST_DIR/make_dataset.py" "${args[@]}"
}

# The S dataset is the source file itself -- one "copy" would just re-encode identical content.
# Copied rather than symlinked so DATA_DIR stays self-contained on $SCRATCH.
echo "== ds_s: copy of $SOURCE"
if [[ ! -f "$DATA_DIR/ds_s.root" ]]; then
    cp "$SOURCE" "$DATA_DIR/ds_s.root"
fi
"$PY" "$TEST_DIR/make_dataset.py" --out "$DATA_DIR/ds_s.root" --copies 1 --describe-only

gen ds_l 40 15000

# Size series for the memory- and time-vs-size plots. One autoflush for the whole series, so
# clustering does not vary along the x axis and turn into a hidden second variable -- which is
# why x1 is regenerated here instead of reusing the ds_s copy above.
#
# Stops at 32: measured 5.4 min per copy on an Ares node, so an x64 point alone would cost
# ~5.8 h for one more marker on a log-log fit that already spans 1.5 decades.
SERIES="${SERIES:-1 2 4 8 16 32}"
for copies in $SERIES; do
    gen "ds_x${copies}" "$copies" 10000
done

# Control for the thread-scaling plateau: same size and contents as ds_l, far fewer TTree
# clusters. RDataFrame parallelises over clusters, so if the plateau moves with this file, it
# is a property of the data layout rather than of the code.
gen ds_l_coarse 40 250000

echo
echo "Datasets in $DATA_DIR:"
du -sh "$DATA_DIR"/*.root
