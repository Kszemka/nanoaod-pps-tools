#!/usr/bin/env bash
#
# Run 3 NanoAOD from CERN EOS (/eos/cms/store/...) into $OUT_DIR (default $SCRATCH/bench/data3)
# with rsync over SSH through lxplus. Interactive, on the login node inside tmux: lxplus asks
# for the second factor (OTP) on every new connection, so this cannot run as a batch job, and
# EOS does not serve file contents to Kerberos clients outside CERN. Afterwards
# slurm_fetch_eos.sbatch checks the sizes and builds the benchmark's lists.
#
#   1. list        SIZES ("<path under /eos> <bytes>" per line, from the selection on lxplus);
#                  copied from the lxplus home directory if it is not in OUT_DIR yet
#   2. download    CONNECTIONS SSH connections (one OTP each) x JOBS_PER_CONN rsync each, files
#                  round-robin; only files missing or of another size; up to ATTEMPTS rounds
#   3. check       every file has the size from SIZES
#
# With a valid Kerberos ticket (kinit, see the README) ssh asks for the OTP only; without one,
# for the CERN password as well. Neither is stored anywhere.
#
#   tmux new -s run3
#   CERN_USER=<login> bash test/fetch_eos.sh     # Ctrl-b d to detach, tmux attach -t run3
#
# Running it again resumes: rsync skips complete files.
# CMS data is not public: it stays on scratch, outside the repository.

set -euo pipefail

OUT_DIR="${OUT_DIR:-${SCRATCH:-$HOME}/bench/data3}"
SIZES="${SIZES:-run3_sizes.txt}"
LXPLUS_HOST="${LXPLUS_HOST:-lxplus.cern.ch}"
CONNECTIONS="${CONNECTIONS:-3}"
JOBS_PER_CONN="${JOBS_PER_CONN:-3}"
ATTEMPTS="${ATTEMPTS:-3}"
DELETE_TICKET="${DELETE_TICKET:-1}"
[[ -f "$HOME/.krb5/krb5.conf" ]] && export KRB5_CONFIG="${KRB5_CONFIG:-$HOME/.krb5/krb5.conf}"
[[ -f "$HOME/.krb5/cc_cern" ]] && export KRB5CCNAME="${KRB5CCNAME:-FILE:$HOME/.krb5/cc_cern}"

stamp() { date +%H:%M:%S; }
fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -t 0 ]] || fail "run it in a terminal (tmux): lxplus asks for a one-time code per connection."
for tool in ssh scp rsync xargs; do
    command -v "$tool" >/dev/null || fail "$tool missing."
done

ticket=""
if [[ -n "${KRB5CCNAME:-}" ]] && command -v klist >/dev/null && klist -s 2>/dev/null; then
    ticket="${KRB5CCNAME#FILE:}"
    case "$(stat -c %a "$ticket")" in
        600|400) ;;
        *) fail "$ticket is readable by others; chmod 600 it (or kinit again)." ;;
    esac
    kinit -R 2>/dev/null || true
    principal="$(klist | awk '/[Pp]rincipal:/ { print $NF; exit }')"
    CERN_USER="${CERN_USER:-${principal%@*}}"
    echo "  Kerberos ticket of $principal: ssh asks for the one-time code only"
else
    echo "  no Kerberos ticket: ssh asks for the CERN password and the one-time code"
fi
[[ -n "${CERN_USER:-}" ]] || fail "set CERN_USER=<your CERN login>."
remote="$CERN_USER@$LXPLUS_HOST"

mkdir -p "$OUT_DIR"
cd "$OUT_DIR"
sock_dir="$(mktemp -d /tmp/pps-eos.XXXXXX)"
close_all() {
    local s
    for s in "$sock_dir"/c*; do
        if [[ -S "$s" ]]; then
            ssh -S "$s" -O exit "$remote" 2>/dev/null || true
        fi
    done
    rm -rf "$sock_dir"
}
trap close_all EXIT
# open_all: a master connection per socket, asking for the code where one is not alive.
open_all() {
    local i s
    for ((i = 0; i < CONNECTIONS; i++)); do
        s="$sock_dir/c$i"
        ssh -S "$s" -O check "$remote" 2>/dev/null && continue
        rm -f "$s"
        echo "  connection $((i + 1)) of $CONNECTIONS to $remote [$(stamp)]"
        ssh -o GSSAPIAuthentication=yes -o GSSAPIDelegateCredentials=yes \
            -o ServerAliveInterval=60 -o ServerAliveCountMax=5 -S "$s" -M -fN "$remote"
    done
}
open_all

echo "=== 1. list [$(stamp)]"
if [[ ! -s "$SIZES" ]]; then
    scp -o ControlPath="$sock_dir/c0" "$remote:$(basename "$SIZES")" "$SIZES" \
        || fail "no $SIZES in $OUT_DIR nor in the lxplus home directory."
fi
awk 'NF != 2 || $1 !~ /^\/eos\/cms\/store\// || $2 !~ /^[0-9]+$/ { bad = 1 }
     END { exit bad }' "$SIZES" || fail "$SIZES: expected '/eos/cms/store/<path> <bytes>' lines."
echo "  $SIZES: $(wc -l <"$SIZES") files," \
    "$(awk '{ s += $2 } END { printf "%.1f", s / 1e9 }' "$SIZES") GB"

# pending: files (relative to /eos/cms/store/) absent here or of another size.
pending() {
    local path size rel
    while read -r path size; do
        rel="${path#/eos/cms/store/}"
        [[ "$(stat -c %s "$rel" 2>/dev/null)" == "$size" ]] || echo "$rel"
    done <"$SIZES"
}

echo "=== 2. download: $CONNECTIONS connections x $JOBS_PER_CONN rsync [$(stamp)]"
for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
    pending >pending.txt
    left="$(wc -l <pending.txt)"
    ((left == 0)) && break
    echo "  round $attempt: $left files [$(stamp)]"
    open_all
    pids=()
    for ((i = 0; i < CONNECTIONS; i++)); do
        # BatchMode: if this connection died, rsync fails instead of prompting in the background;
        # the next round reopens it. -W: whole files, the delta algorithm only costs CPU here.
        awk -v c="$CONNECTIONS" -v i="$i" 'NR % c == i' pending.txt \
            | xargs -r -P "$JOBS_PER_CONN" -I{} rsync -aRW --partial \
                -e "ssh -o BatchMode=yes -S $sock_dir/c$i" "$remote:/eos/cms/store/./{}" . &
        pids+=($!)
    done
    for pid in "${pids[@]}"; do
        wait "$pid" || true
    done
done

echo "=== 3. check [$(stamp)]"
pending >pending.txt
if [[ -s pending.txt ]]; then
    fail "$(wc -l <pending.txt) files missing after $ATTEMPTS rounds (pending.txt); run it again."
fi
rm -f pending.txt
echo "  all $(wc -l <"$SIZES") files have the size from $SIZES; next:"
echo "  sbatch test/slurm_fetch_eos.sbatch"
if [[ -n "$ticket" && "$DELETE_TICKET" == 1 ]]; then
    kdestroy
    echo "  Kerberos ticket destroyed"
fi
echo "done [$(stamp)]"
