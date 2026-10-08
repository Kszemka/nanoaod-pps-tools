#!/usr/bin/env bash
#
# Submits the real-vs-artificial comparison on Helios. Two small jobs run side by side:
#   download  slurm_fetch_opendata.sbatch: ~1 TB of Open Data into $SCRATCH/bench/data2
#   copies    slurm_make_bigset.sbatch: ds_1..ds_96.root next to ds_x32.root, only if some are
#             missing (and not with --no-control)
# and the benchmark (slurm_real_vs_synthetic.sbatch) starts only once both have exited 0
# (afterok). If either fails, the benchmark is dropped from the queue instead of waiting forever.
# Takes seconds; run it on the login node from the repository on scratch.
#
#   bash test/opendata_helios.sh                  # everything
#   bash test/opendata_helios.sh --fetch-only     # the download (and the copies) alone
#   bash test/opendata_helios.sh --bench-only     # data already there (needs READY)
#   bash test/opendata_helios.sh --fetch-jobs 16 --streams 2 --max-gb 1040 --out-dir DIR
#   bash test/opendata_helios.sh --no-control     # benchmark without the ds_1..ds_96 points
#   bash test/opendata_helios.sh --dry-run        # print the sbatch commands only

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

MODE=both
OUT_DIR="${OUT_DIR:-${SCRATCH:-}/bench/data2}"
SYNTH_DIR="${SYNTH_DIR:-${SCRATCH:-}/bench/data}"
FETCH_JOBS="${FETCH_JOBS:-10}"
XRD_STREAMS="${XRD_STREAMS:-1}"
MAX_GB="${MAX_GB:-1040}"
DRY_RUN=""
CONTROL=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fetch-only) MODE=fetch; shift ;;
        --bench-only) MODE=bench; shift ;;
        --fetch-jobs) FETCH_JOBS="$2"; shift 2 ;;
        --streams) XRD_STREAMS="$2"; shift 2 ;;
        --max-gb) MAX_GB="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --no-control) CONTROL=0; shift ;;
        -h|--help) sed -n '2,/^$/p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "ERROR: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

if [[ -z "${SCRATCH:-}" && "$OUT_DIR" == /bench/data2 ]]; then
    echo "ERROR: \$SCRATCH is not set; give --out-dir." >&2
    exit 1
fi
if ! command -v sbatch >/dev/null && [[ -z "$DRY_RUN" ]]; then
    echo "ERROR: no sbatch here; run this on the Helios login node (or use --dry-run)." >&2
    exit 1
fi

# submit <sbatch arguments...>: prints the job id (or, with --dry-run, the command).
submit() {
    if [[ -n "$DRY_RUN" ]]; then
        echo "sbatch --parsable $*" >&2
        echo "<id>"
    else
        sbatch --parsable "$@"
    fi
}

after=()
fetch_id=""
if [[ "$MODE" != bench ]]; then
    fetch_id="$(submit \
        --export=ALL,OUT_DIR="$OUT_DIR",MAX_GB="$MAX_GB",FETCH_JOBS="$FETCH_JOBS",XRD_STREAMS="$XRD_STREAMS" \
        test/slurm_fetch_opendata.sbatch)"
    echo "download  : $fetch_id  -> fetch-opendata-${fetch_id}.out"
    after+=("$fetch_id")
fi

copy_id=""
if [[ "$CONTROL" == 1 ]]; then
    missing=0
    for ((i = 1; i <= 96; i++)); do
        [[ -f "$SYNTH_DIR/ds_${i}.root" ]] || missing=$((missing + 1))
    done
    if [[ "$missing" -ne 0 ]]; then
        if [[ ! -f "$SYNTH_DIR/ds_x32.root" && -z "$DRY_RUN" ]]; then
            echo "ERROR: $SYNTH_DIR/ds_x32.root is missing; nothing to copy (or use --no-control)." >&2
            exit 1
        fi
        copy_id="$(submit --export=ALL,SOURCE="$SYNTH_DIR/ds_x32.root" test/slurm_make_bigset.sbatch)"
        echo "copies    : $copy_id  -> make-bigset-${copy_id}.out ($missing of 96 to write)"
        after+=("$copy_id")
    fi
fi

if [[ "$MODE" != fetch ]]; then
    if [[ -z "$fetch_id" && ! -f "$OUT_DIR/READY" && -z "$DRY_RUN" ]]; then
        echo "ERROR: $OUT_DIR/READY is missing: the download has not finished." >&2
        exit 1
    fi
    dependency=()
    if [[ ${#after[@]} -gt 0 ]]; then
        dependency=(--dependency="afterok$(printf ':%s' "${after[@]}")" --kill-on-invalid-dep=yes)
    fi
    bench_id="$(submit ${dependency[@]+"${dependency[@]}"} \
        --export=ALL,OPENDATA_DIR="$OUT_DIR",SYNTH_DIR="$SYNTH_DIR",CONTROL="$CONTROL" \
        test/slurm_real_vs_synthetic.sbatch)"
    echo "benchmark : $bench_id  -> bench-realsyn-${bench_id}.out" \
        "${after[*]:+(starts after ${after[*]} succeed)}"
fi

echo
echo "follow:  squeue -u \$USER"
[[ -n "$fetch_id" ]] && echo "         tail -f fetch-opendata-${fetch_id}.out"
[[ -n "$copy_id" ]] && echo "         tail -f make-bigset-${copy_id}.out"
echo "results: \$SCRATCH/bench/results-helios-opendata-1tb, \$SCRATCH/bench/results-helios-control-1tb"
