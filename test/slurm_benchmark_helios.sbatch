#!/bin/bash -l
#SBATCH --job-name=pps-bench-helios
#SBATCH --account=<GRANT>-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --time=08:00:00
#SBATCH --exclusive
#SBATCH --output=bench-helios-%j.out
#SBATCH --error=bench-helios-%j.err

# VERIFY BEFORE SUBMITTING: cores per node, CPU partition names, memory per node and the NUMA
# (NPS) configuration in the current Cyfronet Helios documentation, then fix --cpus-per-task,
# --partition and THREADS_LIST below. The values here are placeholders.
#
# Helios has many more cores per node than Ares and a different NUMA topology, so the point at
# which the curve flattens is expected to differ -- that difference is the reason for running
# on both machines, not the raw speed.

set -euo pipefail

export MACHINE=helios
export SCRATCH_BENCH="${SCRATCH}/bench"
# Without this micromamba looks for environments under $HOME instead of the one on scratch.
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"

eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench

cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

export PY="$(command -v python)"
export DATA_DIR="${SCRATCH_BENCH}/data"
export RESULTS="${SCRATCH_BENCH}/results-helios"
export THREADS_LIST="1 2 4 8 16 32 48 96 192"
export REPEATS=3

# On a many-domain EPYC the allocation policy matters; run both and report the difference
# rather than silently picking one.
if command -v numactl >/dev/null 2>&1; then
    srun --cpu-bind=cores numactl --interleave=all bash test/run_all.sh --skip-datasets
else
    srun --cpu-bind=cores bash test/run_all.sh --skip-datasets
fi

# Independent confirmation of the numbers the script collected itself. `seff` is not installed
# on Ares, so read the accounting database directly.
sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,AveCPU,NCPUS,ReqMem || true
