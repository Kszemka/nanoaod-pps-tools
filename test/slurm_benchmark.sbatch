#!/bin/bash -l
#SBATCH --job-name=pps-bench
#SBATCH --account=<GRANT>-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=180G
#SBATCH --time=08:00:00
#SBATCH --exclusive
#SBATCH --output=bench-ares-%j.out
#SBATCH --error=bench-ares-%j.err

# Ares: 2x Intel Xeon Platinum 8268, 48 cores/node, ~192 GB RAM.
#
# --exclusive is not optional: a shared node makes every scaling number a measurement of the
# neighbours' load. The extra allocation cost buys the only version of this plot worth showing.

set -euo pipefail

export MACHINE=ares
export SCRATCH_BENCH="${SCRATCH}/bench"

eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench

cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

export PY="$(command -v python)"
export DATA_DIR="${SCRATCH_BENCH}/data"
export RESULTS="${SCRATCH_BENCH}/results-ares"
export THREADS_LIST="1 2 4 8 16 32 48"
export REPEATS=3

# Datasets are built by their own job (see README): with LZMA they can outlast this one.
srun --cpu-bind=cores bash test/run_all.sh --skip-datasets

# Independent confirmation of the numbers the script collected itself.
seff "${SLURM_JOB_ID}" || true
