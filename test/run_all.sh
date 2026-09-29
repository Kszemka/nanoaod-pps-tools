#!/usr/bin/env bash
#
# Correctness checks, then the benchmark campaign, stopping at the first failure.
#
#   1. validate.py       -- nothing below is meaningful if the implementations disagree
#   2. run_benchmark.sh  -- T1/T2/T4/T5/T6 on the dataset DATASET selects, then the plots
#
# Usage:
#   DATA_DIR=/path/to/data ./test/run_all.sh
#   DATASET=real DATA_DIR=/path/to/lists ./test/run_all.sh
#
# VALIDATE_THREADS sets the thread count of the 1-vs-N check on the compiled kernel.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$TEST_DIR")"
cd "$REPO_ROOT"

if [[ -z "${PY:-}" && -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PY="$REPO_ROOT/.venv/bin/python"
fi
PY="${PY:-python3}"
RESULTS="${RESULTS:-$TEST_DIR/results}"
DATA_DIR="${DATA_DIR:-$TEST_DIR/data}"
VALIDATE_THREADS="${VALIDATE_THREADS:-8}"
export PY RESULTS DATA_DIR

mkdir -p "$RESULTS"
LOG="$RESULTS/run_all_$(date +%Y%m%d_%H%M%S).log"

echo "python : $PY" | tee -a "$LOG"
echo "machine: ${MACHINE:-local}" | tee -a "$LOG"
echo "data   : $DATA_DIR (${DATASET:-synthetic})" | tee -a "$LOG"
echo "results: $RESULTS" | tee -a "$LOG"

# uproot and awkward carry the columnar baseline. Without them the Python side of the comparison
# is only the AsNumpy path, whose cost is dominated by PyROOT materialising one object per event.
if ! "$PY" -c "import ROOT, correctionlib, numpy, uproot, awkward" 2>/dev/null; then
    echo "ERROR: '$PY' is missing one of ROOT, correctionlib, numpy, uproot, awkward." | tee -a "$LOG" >&2
    exit 1
fi

# validate.py runs on it, and every benchmark compiles its kernel on it during warmup.
SOURCE_ROOT="$REPO_ROOT/examples/test.root"
if [[ -f "$SOURCE_ROOT" ]] && head -c 40 "$SOURCE_ROOT" | grep -q 'git-lfs'; then
    echo "ERROR: $SOURCE_ROOT is a Git LFS pointer, not the actual file." | tee -a "$LOG" >&2
    echo "       Run: git lfs install && git lfs pull" | tee -a "$LOG" >&2
    exit 1
fi

echo | tee -a "$LOG"
echo "=== correctness  [$(date +%H:%M:%S)]" | tee -a "$LOG"
"$PY" "$TEST_DIR/validate.py" --threads "$VALIDATE_THREADS" 2>&1 | tee -a "$LOG"

echo | tee -a "$LOG"
echo "=== measurements  [$(date +%H:%M:%S)]" | tee -a "$LOG"
bash "$TEST_DIR/run_benchmark.sh" 2>&1 | tee -a "$LOG"

echo | tee -a "$LOG"
echo "done. results in $RESULTS, log in $LOG" | tee -a "$LOG"
