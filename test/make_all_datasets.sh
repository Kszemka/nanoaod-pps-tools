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
COMPRESSION="${COMPRESSION:-}"

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

gen ds_m 8 10000
gen ds_l 40 15000
gen ds_xl 100 15000

# Size series for the memory- and time-vs-size plots. One autoflush for the whole series, so
# clustering does not vary along the x axis and turn into a hidden second variable -- which is
# why x1 is regenerated here instead of reusing the ds_s copy above.
for copies in 1 2 4 8 16 32 64; do
    gen "ds_x${copies}" "$copies" 10000
done

# Same size, different clustering: the control experiment for the thread-scaling plateau.
gen ds_xl_coarse 100 250000

echo
echo "Datasets in $DATA_DIR:"
du -sh "$DATA_DIR"/*.root
