#!/bin/bash -l
#SBATCH --job-name=pps-bench
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --mem=0
#SBATCH --hint=nomultithread
#SBATCH --time=08:00:00
#SBATCH --exclusive
#SBATCH --output=bench-ares-%j.out
#SBATCH --error=bench-ares-%j.err

# Ares: 48 cores/node, ~192 GB RAM. The CPU model is printed by the lscpu dump below rather
# than asserted here, because the two places in this repo that name it disagree.
#
# --exclusive is not optional: a shared node makes every scaling number a measurement of the
# neighbours' load. The extra allocation cost buys the only version of this plot worth showing.
#
# --mem=0 (the whole node) rather than 180G: the cgroup limit applies to page cache too, and
# the inputs are ~21 GB (synthetic) to ~60 GB (real). Capping it below the node's RAM puts the
# cgroup's reclaim policy inside the memory and bytes-read measurements.
#
# --hint=nomultithread so that 48 means 48 physical cores. With SMT counted in, the 32- and
# 48-thread points would be two threads sharing a core, and the flattening they show would be
# a property of the allocation rather than of the code.
#
# The synthetic campaign is ~1.5 h (406 runs plus validate.py and writing the slim copies on the
# first job; `DRY_RUN=1 test/run_benchmark.sh` lists them). The real one has 424 runs and a
# ~4x larger core input, so T1, T2 and T6 take roughly 3x longer: budget ~3-4 h. The margin
# covers a slow Lustre day; a job that runs out of wall clock has to queue again.
#
#   sbatch test/slurm_benchmark.sbatch                              # ds_x1..ds_x32
#   sbatch --export=ALL,DATASET=real test/slurm_benchmark.sbatch    # lists in $SCRATCH/bench/real

set -euo pipefail

export MACHINE=ares
export SCRATCH_BENCH="${SCRATCH}/bench"
# Without this micromamba looks for environments under $HOME instead of the one on scratch.
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"

# `set -u` off across the activation only. The job inherits the submitting shell's environment,
# so activate first deactivates whatever was already loaded, and the env's own
# deactivate-root.sh reads CONDA_BACKUP_ROOTSYS unconditionally -- unset on a fresh job, which
# under -u kills the script before the first benchmark.
set +u
eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench
set -u

cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

# Everything below this job measures parallel scaling, so the one thing that must be true
# before it starts is that the process can actually reach 48 cores. Printed in full because
# the CPU model and the SMT setting both belong in the thesis and neither is worth guessing.
echo "=== allocation ==="
lscpu | grep -E 'Model name|^CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket|NUMA node\(s\)'
echo "SLURM_CPUS_ON_NODE : ${SLURM_CPUS_ON_NODE:-unset}"
echo "SLURM_CPUS_PER_TASK: ${SLURM_CPUS_PER_TASK:-unset}"
echo "nproc              : $(nproc)"
taskset -cp $$ || true

# A benchmark that quietly runs 48 ROOT threads on 4 cores still exits 0 and still produces a
# plot; it just produces a wrong one. Hard stop instead.
expected_cpus="${SLURM_CPUS_PER_TASK:-48}"
if [[ "$(nproc)" -lt "$expected_cpus" ]]; then
    echo "ERROR: nproc=$(nproc) but the job asked for $expected_cpus CPUs." >&2
    echo "Refusing to run: every scaling number would be a measurement of the allocation." >&2
    exit 1
fi
echo

export PY="$(command -v python)"
export DATASET="${DATASET:-synthetic}"
if [[ "$DATASET" == real ]]; then
    export DATA_DIR="${SCRATCH_BENCH}/real"
    export RESULTS="${SCRATCH_BENCH}/results-ares-real"
else
    export DATA_DIR="${SCRATCH_BENCH}/data"
    export RESULTS="${SCRATCH_BENCH}/results-ares"
fi
export THREADS_LIST="1 2 4 8 12 16 24 32 48"
export RUN_TIMEOUT=2400

# run_benchmark.sh appends to $RESULTS/raw.jsonl, so a directory left over from an earlier
# campaign would quietly mix its records in. Start a new directory and keep the old one.
if [[ -f "${RESULTS}/raw.jsonl" ]]; then
    previous="${RESULTS}-archived-$(date +%Y%m%d_%H%M%S)"
    echo "moving previous results to ${previous}"
    mv "${RESULTS}" "${previous}"
fi

# No srun. Since Slurm 22.05 a job step does not inherit --cpus-per-task from the batch
# allocation, so `srun` here could hand the whole campaign a single CPU -- which fails
# silently, as a flat speedup curve. The batch script already runs inside a cgroup covering
# the full allocation, and this is one process on one node, so the step bought nothing.
bash test/run_all.sh

# Independent confirmation of the numbers the script collected itself. `seff` is not installed
# on Ares, so read the accounting database directly.
sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,AveCPU,NCPUS,ReqMem || true
