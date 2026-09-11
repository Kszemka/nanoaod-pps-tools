#!/usr/bin/env bash
#
# Runs the whole benchmark pipeline in order, stopping at the first failure.
#
#   1. correctness      (validate.py -- nothing below is meaningful if this fails)
#   2. smoke test       (every path starts and produces a record)
#   3. datasets         (skipped if they already exist)
#   4. measurements     (thread sweep, size sweep, layout, cache probe)
#   5. I/O diagnostics  (why the bytes-read numbers are what they are)
#   6. plots + CSV
#
# Usage:
#   ./test/run_all.sh                  # everything
#   ./test/run_all.sh --skip-datasets  # datasets already built by a separate job
#   ./test/run_all.sh --from 4         # resume at a step
#
# On a cluster, prefer building the datasets in their own long job: with the source file's
# LZMA compression that step alone can outlast the measurement job's time limit.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$TEST_DIR")"
cd "$REPO_ROOT"

if [[ -z "${PY:-}" && -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PY="$REPO_ROOT/.venv/bin/python"
fi
PY="${PY:-python3}"
export PY

RESULTS="${RESULTS:-$TEST_DIR/results}"
DATA_DIR="${DATA_DIR:-$TEST_DIR/data}"
export RESULTS DATA_DIR

FROM_STEP=1
SKIP_DATASETS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-datasets) SKIP_DATASETS=1; shift ;;
        --from) FROM_STEP="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$RESULTS" "$DATA_DIR"
LOG="$RESULTS/run_all_$(date +%Y%m%d_%H%M%S).log"

step() {
    local number="$1" name="$2"
    if [[ "$number" -lt "$FROM_STEP" ]]; then
        echo "--- step $number ($name): skipped (--from $FROM_STEP)" | tee -a "$LOG"
        return 1
    fi
    echo | tee -a "$LOG"
    echo "=== step $number: $name  [$(date +%H:%M:%S)]" | tee -a "$LOG"
    return 0
}

echo "python : $PY" | tee -a "$LOG"
echo "machine: ${MACHINE:-local}" | tee -a "$LOG"
echo "data   : $DATA_DIR" | tee -a "$LOG"
echo "results: $RESULTS" | tee -a "$LOG"

if ! "$PY" -c "import ROOT, correctionlib, numpy" 2>/dev/null; then
    echo "ERROR: '$PY' is missing ROOT, correctionlib or numpy." | tee -a "$LOG" >&2
    exit 1
fi
# uproot and awkward carry the columnar baseline. Without them the Python side of the
# comparison is only the AsNumpy path, whose cost is dominated by PyROOT materialising one
# object per event -- so the headline RDataFrame-vs-Python ratio would be measuring the wrong
# thing. Missing is a hard error rather than a skipped implementation.
if ! "$PY" -c "import uproot, awkward" 2>/dev/null; then
    echo "ERROR: '$PY' is missing uproot or awkward." | tee -a "$LOG" >&2
    echo "       micromamba install -c conda-forge uproot awkward" | tee -a "$LOG" >&2
    exit 1
fi

SOURCE_ROOT="$REPO_ROOT/examples/test.root"
if [[ -f "$SOURCE_ROOT" ]] && head -c 40 "$SOURCE_ROOT" | grep -q 'git-lfs'; then
    echo "ERROR: $SOURCE_ROOT is a Git LFS pointer, not the actual file." | tee -a "$LOG" >&2
    echo "       Run: git lfs install && git lfs pull" | tee -a "$LOG" >&2
    exit 1
fi

if step 1 "correctness"; then
    "$PY" "$TEST_DIR/validate.py" 2>&1 | tee -a "$LOG"
fi

if step 2 "smoke test"; then
    bash "$TEST_DIR/run_benchmark.sh" quick 2>&1 | tee -a "$LOG"
fi

if step 3 "datasets"; then
    if [[ "$SKIP_DATASETS" -eq 1 ]]; then
        echo "  --skip-datasets given" | tee -a "$LOG"
    else
        bash "$TEST_DIR/make_all_datasets.sh" 2>&1 | tee -a "$LOG"
    fi
fi

if step 4 "measurements"; then
    bash "$TEST_DIR/run_benchmark.sh" full 2>&1 | tee -a "$LOG"
fi

if step 5 "I/O diagnostics"; then
    # Runs on whatever datasets exist. TFile::GetFileBytesRead says how much was read but not
    # why; this sweeps the TTreeCache size, which is what distinguishes a cache too small to
    # hold a cluster from plain basket granularity.
    for name in ds_x1 ds_x8 ds_x8_slim ds_x8_coarse ds_l; do
        dataset="$DATA_DIR/${name}.root"
        [[ -f "$dataset" ]] || continue
        "$PY" "$TEST_DIR/diag_io.py" --input "$dataset" \
            --out "$RESULTS/diag_io.jsonl" 2>&1 | tee -a "$LOG"
    done
fi

if step 6 "plots"; then
    "$PY" "$TEST_DIR/plot_results.py" --results "$RESULTS" 2>&1 | tee -a "$LOG"
fi

echo | tee -a "$LOG"
echo "done. results in $RESULTS, log in $LOG" | tee -a "$LOG"
