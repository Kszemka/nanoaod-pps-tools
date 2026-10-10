#!/bin/bash -l
#SBATCH --job-name=pps-bigset
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --output=make-bigset-%j.out
#SBATCH --error=make-bigset-%j.err

# The artificial 1 TB set as a job of its own: make_bigset.sh writes ds_1.root .. ds_96.root
# next to $SCRATCH/bench/data/ds_x32.root. Runs alongside the Open Data download (both are
# small, non-exclusive jobs); test/archive/opendata_helios.sh queued the benchmark after both.
#
#   sbatch test/slurm_make_bigset.sbatch
#   sbatch --export=ALL,COPY_JOBS=16 test/slurm_make_bigset.sbatch
#
# Only `cp`, so no environment. A rerun skips the copies already at full size. 8 GB is enough:
# the page cache the copies fill is reclaimed within the job's memory limit.

set -euo pipefail

SCRATCH_BENCH="${SCRATCH}/bench"
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    REPO="${REPO:-${SCRATCH_BENCH}/nanoaod-pps-tools}"
else
    REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
fi
SOURCE="${SOURCE:-${SCRATCH_BENCH}/data/ds_x32.root}"
COPIES="${COPIES:-96}"
COPY_JOBS="${COPY_JOBS:-8}"

echo "=== $(hostname): $COPIES copies of $SOURCE, $COPY_JOBS at a time [$(date +%H:%M:%S)]"
start=$SECONDS
bash "$REPO/test/archive/make_bigset.sh" --source "$SOURCE" --copies "$COPIES" --jobs "$COPY_JOBS"
echo "=== done in $(((SECONDS - start) / 60)) min [$(date +%H:%M:%S)]"
