#!/bin/bash -l
#SBATCH --job-name=pps-smoke
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid-testing
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=0:40:00
#SBATCH --output=smoke-%j.out
#SBATCH --error=smoke-%j.err

# Correctness checks plus a one-pass smoke test of every measurement path.
#
# Batch rather than an interactive srun: an SSH drop kills a --pty session and takes the run
# with it, while a queued job keeps going and writes its output to smoke-<jobid>.out.
#
# 16 cores rather than a full exclusive node: nothing here is a timing measurement, so the
# only reason to want more than one is to prove the compiled kernel is thread-safe. The real
# scaling run (slurm_benchmark.sbatch) takes all 48 with --exclusive.

set -euo pipefail

export MACHINE=ares
export SCRATCH_BENCH="${SCRATCH}/bench"
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"

eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench

cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

export PY="$(command -v python)"
export RESULTS="${SCRATCH_BENCH}/results-smoke"

echo "node    : $(hostname)"
echo "cores   : $(nproc)"
echo "python  : ${PY}"
python -c "import ROOT; print('ROOT', ROOT.gROOT.GetVersion())"

# Full file, no --max-events: the thread-safety check needs ImplicitMT, which Range() disables.
python test/validate.py --threads "$(nproc)"
bash test/run_benchmark.sh quick
python test/plot_results.py --results "${RESULTS}" --csv-only

echo
echo "=== bench.csv ==="
cat "${RESULTS}/bench.csv"
