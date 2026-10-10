#!/usr/bin/env bash
#
# Makes N plain copies of one file, ds_1.root ... ds_N.root, next to it (or in --out-dir).
# That is all it does: the lists the 1 TB campaign reads them through are written by
# run_benchmark.sh itself (DATASET=big), into lists/ in the same directory.
#
# The point of the copies is that each one is a separate inode. A single file named 96 times in
# a list would be read once from the file system and 95 times out of the page cache, so the
# campaign would measure the cache rather than the storage. With copies, run_benchmark.sh can
# drop their pages before every run (COLD=1) and each run reads every byte from Lustre, exactly
# as it would with 96 genuinely different files. The contents are identical, so the physics
# results stay checkable: the event count is N x the source's and the checksums must all agree.
#
# Not hadd: merging 1 TB into one file would take hours and produce a file whose cluster
# boundaries no longer match the source's. `cp` keeps both the clustering and the codec.
#
#   ./test/archive/make_bigset.sh --source $SCRATCH/bench/data/ds_x32.root [--copies 96] [--jobs 8]
#
# Copies go through a .partial name and are skipped if they already exist at the right size, so
# an interrupted run can simply be repeated.

set -euo pipefail

SOURCE=""
OUT_DIR=""
# 96 = 2 x 48: the weak-scaling series takes 2N copies at N threads, so its last point is the
# whole set, the same 1 TB as T1. Must match BIG_COPIES in run_benchmark.sh.
COPIES=96
# 8 parallel `cp` saturates a Lustre stripe set without turning the login node into a bad
# neighbour. More streams do not make the copy faster; they only make it lumpier.
JOBS=8

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source) SOURCE="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --copies) COPIES="$2"; shift 2 ;;
        --jobs) JOBS="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "ERROR: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

if [[ -z "$SOURCE" ]]; then
    echo "ERROR: --source is required." >&2
    exit 1
fi
if [[ ! -f "$SOURCE" ]]; then
    echo "ERROR: missing $SOURCE" >&2
    exit 1
fi
if [[ "$COPIES" -lt 1 ]]; then
    echo "ERROR: --copies must be at least 1" >&2
    exit 1
fi
OUT_DIR="${OUT_DIR:-$(dirname "$SOURCE")}"
mkdir -p "$OUT_DIR"

size="$(wc -c <"$SOURCE")"
target_of() { printf '%s/ds_%d.root' "$OUT_DIR" "$1"; }

# Only the copies not yet there at the source's size need space, so repeating the script on a
# complete set does not fail the check.
missing=0
for ((index = 1; index <= COPIES; index++)); do
    target="$(target_of "$index")"
    if [[ ! -f "$target" || "$(wc -c <"$target")" -ne "$size" ]]; then
        missing=$((missing + 1))
    fi
done
need_kb=$(($(du -sk "$SOURCE" | cut -f1) * missing))
free_kb="$(df -Pk "$OUT_DIR" | awk 'NR == 2 {print $4}')"
echo "=== $COPIES copies of $(basename "$SOURCE") in $OUT_DIR, $missing still to write:" \
    "$((need_kb / 1048576)) GB needed, $((free_kb / 1048576)) GB free"
# df knows the file system, not the grant. On Ares the binding limit is usually the quota, which
# only `hpc-fs` reports.
echo "    (df only; check the grant's quota with hpc-fs before a 1 TB copy)"
if [[ "$need_kb" -ge "$free_kb" ]]; then
    echo "ERROR: not enough free space." >&2
    exit 1
fi

# copy_one <target>
#
# A copy that already exists at the source's size is left alone: on a 1 TB set a restart that
# began again from ds_1 would cost another half hour. The .partial name is what makes that
# safe -- an interrupted `cp` never leaves a short file under the final name.
copy_one() {
    local target="$1"
    if [[ -f "$target" && "$(wc -c <"$target")" -eq "$size" ]]; then
        return 0
    fi
    cp "$SOURCE" "${target}.partial"
    mv "${target}.partial" "$target"
    echo "  $(basename "$target")"
}

# $JOBS copies at a time, in batches. `wait -n` would keep the pipe fuller but needs bash 4.3,
# and the copies are all the same size anyway, so a batch barrier costs nothing here.
running=0
for ((index = 1; index <= COPIES; index++)); do
    copy_one "$(target_of "$index")" &
    running=$((running + 1))
    if [[ "$running" -ge "$JOBS" ]]; then
        wait
        running=0
    fi
done
wait

# A bare `wait` does not report a failed `cp` (a full quota, say), so count what is there.
for ((index = 1; index <= COPIES; index++)); do
    target="$(target_of "$index")"
    if [[ ! -f "$target" || "$(wc -c <"$target")" -ne "$size" ]]; then
        echo "ERROR: $(basename "$target") is missing or incomplete; run the script again." >&2
        exit 1
    fi
done
echo "done: ds_1.root ... ds_${COPIES}.root in $OUT_DIR"
