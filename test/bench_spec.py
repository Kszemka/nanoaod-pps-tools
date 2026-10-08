#!/usr/bin/env python3
"""
What the benchmarks compute, without ROOT: the chains, their columns and cuts, and the rule
that turns --input into a list of files.

bench_common re-exports all of it, so the benchmarks keep using bc.<name>. It lives apart for
the worker processes of bench_pool.py: an uproot worker that imported ROOT only to learn the
chain would carry ~0.3 GB it never uses, 192 times over, and charge it to uproot.
"""

import operator
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (REPO_ROOT, os.path.join(REPO_ROOT, "corrections-examples")):
    if path not in sys.path:
        sys.path.insert(0, path)

DEFAULT_RP_ID = 22
DEFAULT_ARM = "45"
DEFAULT_POT = "box"

# Filter chain for TEST 2, in order -- the notebook's rdata_analysis() chain, with its
# nPPSLocalTrack > 0 baseline as an explicit first step so --chain-len sweeps the whole thing.
CHAIN_STEPS = ["pps", "double_arm", "diamond", "rp_id", "xi"]
# The 1 TB campaign's chain: five cuts on further PPS columns and one on
# PPSLocalTrack_multiRPProtonIdx, which is there because rp_id reads PPSLocalTrack_decRPId a
# second time, then the five steps above -- eleven filters over ten distinct branches. The added
# steps come first, weakest cut first, because after the five steps above they pass every event
# that reaches them.
LONG_CHAIN_STEPS = ["theta_y", "multi_proton", "multi_rp_idx", "single_rp_idx", "time",
                    "time_unc"] + CHAIN_STEPS
CHAINS = {"base": CHAIN_STEPS, "long": LONG_CHAIN_STEPS}
CHAIN_COLUMNS = {
    "pps": "nPPSLocalTrack",
    "double_arm": "PPSLocalTrack_decRPId",
    "diamond": "PPSLocalTrack_rpType",
    "rp_id": "PPSLocalTrack_decRPId",
    "xi": "Proton_singleRP_xi",
    "multi_rp_idx": "PPSLocalTrack_multiRPProtonIdx",
    "single_rp_idx": "PPSLocalTrack_singleRPProtonIdx",
    "time": "PPSLocalTrack_time",
    "time_unc": "PPSLocalTrack_timeUnc",
    "theta_y": "Proton_singleRP_thetaY",
    "multi_proton": "nProton_singleRP",
}
MAX_CHAIN_LEN = len(CHAIN_STEPS)
EFFICIENCY_COLUMNS = ["PPSLocalTrack_x", "PPSLocalTrack_y", "PPSLocalTrack_decRPId"]
XI_RANGE = (0.05, 0.1)
# The detector-dependent parameters of the chain, per data-taking period. "2026" is the
# notebook's analysis on examples/test.root (run 396727) and the ds_xN copies of it: pots
# 23|123 and 3|103, diamond timing detectors, RP 22. In 2016 PPS ran with strip detectors only,
# in pots 2, 3, 102 and 103, so there the 2026 chain rejects every event at double_arm. The
# 2016 variant keeps the same five steps over the same columns with that year's pots and
# detector type. Its track cuts cannot be the 2026 ones either: every strip track belongs to a
# single-RP proton and none carries timing (time 0), so "single_rp_idx == -1" and "time != 0"
# drop every event. They keep the multi-RP cut and turn the other three around; on
# 2A2D52E2-CD96-BD4C-8D60-4BC274FA8ED5.root (2016) the chain then keeps 5.3% of the events.
#
# "run3" is the 2024-2026 data set: in its files (e.g. run 401844) the diamonds hold tracks in
# under 0.5% of events and multi-RP protons in 3%, so every cut that needs either drops almost
# all of it. The chain there selects on the pixels (rpType 4, RP 23), and its four track cuts
# are turned around: a track not used by a multi-RP proton, a track used by a single-RP one, a
# track without timing (pixel tracks carry time 0). On run 401844 it keeps 60% of the events.
#
# track_cuts: (operator, value) of the "any track with <column> <op> <value>" steps; the
# operator is written into the RDataFrame expression and looked up in TRACK_OPS for the arrays.
TRACK_OPS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le,
             ">": operator.gt, "<": operator.lt}
TRACK_CUTS = {"multi_rp_idx": (">=", 0), "single_rp_idx": ("==", -1),
              "time": ("!=", 0), "time_unc": ("!=", 0)}
PERIODS = {
    "2026": {"arms": ((23, 123), (3, 103)), "detector": "diamond", "rp_type": 5, "rp_id": 22,
             "track_cuts": TRACK_CUTS},
    "2016": {"arms": ((2, 3), (102, 103)), "detector": "strip", "rp_type": 3, "rp_id": 3,
             "track_cuts": {"multi_rp_idx": (">=", 0), "single_rp_idx": (">=", 0),
                            "time": ("==", 0), "time_unc": ("==", 0)}},
    "run3": {"arms": ((23, 123), (3, 103)), "detector": "pixel", "rp_type": 4, "rp_id": 23,
             "track_cuts": {"multi_rp_idx": ("==", -1), "single_rp_idx": (">=", 0),
                            "time": ("==", 0), "time_unc": ("==", 0)}},
}
DEFAULT_PERIOD = "2026"


def chain_steps(chain_len, chain="base"):
    """The first `chain_len` steps of the chain."""
    return CHAINS[chain][:chain_len]


def chain_columns(chain_len, chain="base"):
    """Distinct branches the first `chain_len` steps need, in first-use order."""
    columns = []
    for name in chain_steps(chain_len, chain):
        column = CHAIN_COLUMNS[name]
        if column not in columns:
            columns.append(column)
    return columns


def is_file_list(path):
    return path.endswith(".txt")


def input_files(path):
    """
    The .root files behind --input: the file itself, or the entries of a .txt list.

    Relative entries resolve against the list's own directory, so a list written next to the
    data stays valid wherever the data directory is mounted. Blank lines and # comments are
    skipped.
    """
    if not is_file_list(path):
        return [path]
    base = os.path.dirname(os.path.abspath(path))
    with open(path) as f:
        entries = [line.strip() for line in f]
    return [e if os.path.isabs(e) else os.path.join(base, e)
            for e in entries if e and not e.startswith("#")]
