#!/bin/bash -l
#SBATCH --job-name=pps-bench
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=180G
#SBATCH --time=06:00:00
#SBATCH --exclusive
#SBATCH --output=bench-ares-%j.out
#SBATCH --error=bench-ares-%j.err

# Ares: 2x Intel Xeon Platinum 8268, 48 cores/node, ~192 GB RAM.
#
# --exclusive is not optional: a shared node makes every scaling number a measurement of the
# neighbours' load. The extra allocation cost buys the only version of this plot worth showing.
#
# 6 h rather than the 8 h a whole-node booking invites: the campaign is 250 runs, and the
# per-run times measured on a dataset of this size put it at 1.5-2 h, the upper end being the
# size series once its large Python points are allowed to finish instead of being cut off.
# The rest is margin, kept deliberately finite because a shorter wall clock queues sooner and
# that matters with --exclusive. Raise it if THREADS_LIST, REPEATS or SCALE_SERIES grow.

set -euo pipefail

export MACHINE=ares
export SCRATCH_BENCH="${SCRATCH}/bench"
# Without this micromamba looks for environments under $HOME instead of the one on scratch.
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"

eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench

cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

export PY="$(command -v python)"
export DATA_DIR="${SCRATCH_BENCH}/data"
export RESULTS="${SCRATCH_BENCH}/results-ares"
export THREADS_LIST="1 2 4 8 16 32 48"
export REPEATS=3
# The default 300 s kills the Python arm of the size series: at the measured 10130 events/s
# the chain needs 550 s on ds_x16 and 1098 s on ds_x32, and ds_x8 lands at 276 s, only 8%
# under the limit. Those runs would be recorded as failures carrying no peak_rss_kb, which
# removes the points where the memory curves diverge most -- the whole reason the large
# datasets exist.
#
# cmd_scaling also scales the limit per dataset and takes whichever of the two is larger, so
# this raises the floor for every other run rather than fighting it.
export RUN_TIMEOUT=1800

# run_benchmark.sh appends to $RESULTS/raw.jsonl, so a directory left over from an earlier
# campaign quietly mixes its records in. plot_results.py separates them by schema_version, but
# only records of the current version have the phase split and the net RSS baseline, so the
# honest thing is to start a new directory and keep the old one as evidence.
if [[ -f "${RESULTS}/raw.jsonl" ]]; then
    previous="${RESULTS}-archived-$(date +%Y%m%d_%H%M%S)"
    echo "moving previous results to ${previous}"
    mv "${RESULTS}" "${previous}"
fi

# Datasets are built by their own job (see README): with LZMA they can outlast this one.
srun --cpu-bind=cores bash test/run_all.sh --skip-datasets

# Independent confirmation of the numbers the script collected itself. `seff` is not installed
# on Ares, so read the accounting database directly.
sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,AveCPU,NCPUS,ReqMem || true
