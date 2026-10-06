#!/bin/bash -l
#SBATCH --job-name=pps-realsyn
#SBATCH --account=plgccbmc15-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem=384000
#SBATCH --hint=nomultithread
#SBATCH --time=05:00:00
#SBATCH --exclusive
#SBATCH --output=bench-realsyn-%j.out
#SBATCH --error=bench-realsyn-%j.err

# Job 2 of the real-vs-artificial comparison, Helios only (192 cores; --mem=384000 because
# plgrid's MaxMemPerNode rejects --mem=0 there). Starts after slurm_fetch_opendata.sbatch has
# put the Open Data set in $OPENDATA_DIR and slurm_make_bigset.sbatch the copies in $SYNTH_DIR
# (test/opendata_helios.sh queues it with afterok on both).
#
#   real     the 5-filter chain, --period 2016, on ~1 TB of Run 2 Open Data, cold reads, one
#            repeat on 13 thread counts                     -> results-helios-opendata-1tb
#   control  the same chain on the artificial 1 TB (ds_1..ds_96.root), cold, 1/48/144/192
#            threads: the same node and the same Lustre as "real", so a difference between
#            control and the original full-1tb campaign shows how much the file system moved
#                                                           -> results-helios-control-1tb
#
# The two run one after the other, never together: they would share the Lustre bandwidth the
# cold reads measure. Compare afterwards with test/plot_real_vs_synthetic.py.
#
#   sbatch test/slurm_real_vs_synthetic.sbatch
#   sbatch --export=ALL,REAL_THREADS="1 16 96 192" test/slurm_real_vs_synthetic.sbatch
#   sbatch --export=ALL,CONTROL=0 test/slurm_real_vs_synthetic.sbatch   # real only, no ds_N needed

set -euo pipefail

export MACHINE="${MACHINE:-helios}"
export SCRATCH_BENCH="${SCRATCH}/bench"
export MAMBA_ROOT_PREFIX="${SCRATCH_BENCH}/micromamba"
OPENDATA_DIR="${OPENDATA_DIR:-${SCRATCH_BENCH}/data2}"
SYNTH_DIR="${SYNTH_DIR:-${SCRATCH_BENCH}/data}"
REAL_THREADS="${REAL_THREADS:-1 2 4 8 16 32 48 64 96 128 144 160 192}"
CONTROL_THREADS="${CONTROL_THREADS:-1 48 144 192}"
CONTROL="${CONTROL:-1}"

# Both inputs are checked before anything runs: a missing control set would otherwise only
# surface after the hours of the real sweep.
if [[ ! -f "$OPENDATA_DIR/READY" || ! -f "$OPENDATA_DIR/core.txt" ]]; then
    echo "ERROR: $OPENDATA_DIR/READY or core.txt missing: the download (Job 1) is not complete." >&2
    exit 1
fi
missing=0
for ((i = 1; i <= 96; i++)); do
    [[ -f "$SYNTH_DIR/ds_${i}.root" ]] || missing=$((missing + 1))
done
if [[ "$CONTROL" == 1 && "$missing" -ne 0 ]]; then
    echo "ERROR: $missing of ds_1..ds_96.root missing in $SYNTH_DIR (the control set)." >&2
    echo "       Make them first: bash test/make_bigset.sh --source $SYNTH_DIR/ds_x32.root" >&2
    echo "       or skip the control points: CONTROL=0" >&2
    exit 1
fi

# See slurm_benchmark.sbatch: the env's deactivate script trips over set -u.
set +u
eval "$("${SCRATCH_BENCH}/micromamba/bin/micromamba" shell hook -s bash)"
micromamba activate pps-bench
set -u
cd "${SCRATCH_BENCH}/nanoaod-pps-tools"

echo "=== allocation ==="
echo "node               : $(hostname) (${MACHINE})"
lscpu | grep -E 'Model name|^CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket|NUMA node\(s\)'
echo "SLURM_CPUS_PER_TASK: ${SLURM_CPUS_PER_TASK:-unset}"
echo "nproc              : $(nproc)"
expected_cpus="${SLURM_CPUS_PER_TASK:-192}"
if [[ "$(nproc)" -lt "$expected_cpus" ]]; then
    echo "ERROR: nproc=$(nproc) but the job asked for $expected_cpus CPUs." >&2
    exit 1
fi
echo "=== Open Data set ==="
cat "$OPENDATA_DIR/READY"
echo

export PY="$(command -v python)"
export STORAGE=lustre COLD=1 TESTS=strongchain REPEATS_STRONG=1

# fresh_results <dir>: a directory left over from an earlier job would mix its records in.
fresh_results() {
    if [[ -f "$1/raw.jsonl" ]]; then
        mv "$1" "$1-archived-$(date +%Y%m%d_%H%M%S)"
    fi
    mkdir -p "$1"
}

# dataset_json <results dir> <inventory csv | root file>: codec and branch count for
# plot_real_vs_synthetic.py, which needs no ROOT and so cannot read them itself.
dataset_json() {
    "$PY" - "$@" <<'EOF'
import csv, json, os, sys
sys.path.insert(0, "test")
out, source = sys.argv[1], sys.argv[2]
names = {1: "ZLIB", 2: "LZMA", 4: "LZ4", 5: "ZSTD"}
if source.endswith(".csv"):
    with open(os.path.join(os.path.dirname(source), "core.txt")) as f:
        core = {os.path.basename(line.strip()) for line in f if line.strip()}
    rows = [r for r in csv.DictReader(open(source)) if r["name"] in core]
    codecs = sorted({r["compression"] for r in rows})
    branches = sorted({int(r["n_branches"]) for r in rows})
    info = {"files": len(rows), "schemas": len({r["schema"] for r in rows}),
            "branches": f"{branches[0]}-{branches[-1]}" if len(branches) > 1 else str(branches[0])}
else:
    import bench_common as bc
    layout = bc.tree_layout(source)
    codecs = [f"{layout['compression_algorithm']}:{layout['compression_level']}"]
    info = {"branches": str(len(layout["branches"]))}
info["codec"] = " ".join(names.get(int(c.split(":")[0]), c.split(":")[0]) + ":" + c.split(":")[1]
                         for c in codecs)
with open(os.path.join(out, "dataset.json"), "w") as f:
    json.dump(info, f, indent=1)
print("dataset.json:", info)
EOF
}

echo "=== real: Open Data, chain --period 2016 [$(date +%H:%M:%S)] ==="
REAL_RESULTS="${SCRATCH_BENCH}/results-helios-opendata-1tb"
fresh_results "$REAL_RESULTS"
dataset_json "$REAL_RESULTS" "$OPENDATA_DIR/local.csv"
# The 1-thread run on LZMA files can take well over the default 40 min.
DATASET=real DATA_DIR="$OPENDATA_DIR" CHAIN_ARGS="--period 2016" THREADS_LIST="$REAL_THREADS" \
    RESULTS="$REAL_RESULTS" RUN_TIMEOUT=14400 bash test/run_all.sh

if [[ "$CONTROL" == 1 ]]; then
    echo "=== control: artificial 1 TB, chain [$(date +%H:%M:%S)] ==="
    CONTROL_RESULTS="${SCRATCH_BENCH}/results-helios-control-1tb"
    fresh_results "$CONTROL_RESULTS"
    dataset_json "$CONTROL_RESULTS" "$SYNTH_DIR/ds_1.root"
    # run_benchmark.sh, not run_all.sh: validate.py has already run in this job.
    DATASET=big DATA_DIR="$SYNTH_DIR" THREADS_LIST="$CONTROL_THREADS" RESULTS="$CONTROL_RESULTS" \
        RUN_TIMEOUT=2400 bash test/run_benchmark.sh
else
    echo "=== control skipped (CONTROL=0) ==="
fi

echo "done [$(date +%H:%M:%S)]. Copy both results directories to results/helios/ and run"
echo "  python test/plot_real_vs_synthetic.py --synthetic results/helios/full-1tb \\"
echo "      --control results/helios/control-1tb --real results/helios/opendata-1tb"
sacct -j "${SLURM_JOB_ID}" --format=JobID,JobName,State,Elapsed,MaxRSS,NCPUS,ReqMem || true
