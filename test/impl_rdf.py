#!/usr/bin/env python3
"""
RDataFrame implementations of the three benchmarked operations.

Every function ends in an explicit reduction: RDataFrame is lazy, so without one it would build
a computation graph and read nothing at all, and the measurement would be meaningless.
"""

import bench_common as bc
import ROOT

from app.analyze_proton_events import (
    filter_detector_specific_events,
    filter_detector_type,
    filter_double_arm_events,
    filter_xi_ranged_events,
)
from app.apply_corrections import apply_diamond_efficiency_jit

CHAIN_FILTERS = {
    "pps": lambda df: df.Filter("nPPSLocalTrack > 0", "Events with PPS data"),
    "double_arm": filter_double_arm_events,
    "diamond": lambda df: filter_detector_type(df, "diamond"),
    "rp_id": lambda df: filter_detector_specific_events(df, bc.DEFAULT_RP_ID),
    "xi": lambda df: filter_xi_ranged_events(df, *bc.XI_RANGE),
}


# --- TEST 1: single filter -------------------------------------------------------------------

def filter_rdf(df, rp_id):
    return int(filter_detector_specific_events(df, rp_id).Count().GetValue())


# --- TEST 2: filter chain --------------------------------------------------------------------

def _apply_chain(df, chain_len):
    for name in bc.CHAIN_STEPS[:chain_len]:
        df = CHAIN_FILTERS[name](df)
    return df


def chain_rdf_lazy(df, chain_len):
    """Whole chain built, one Count() at the end -> a single event loop."""
    final = _apply_chain(df, chain_len).Count()
    return {"final": int(final.GetValue()), "intermediate": None, "event_loops": 1}


def chain_rdf_eager(df, chain_len):
    """
    Reproduces rdata_analysis(): the total event count, then one after every filter.

    Every Count().GetValue() is a full pass over the dataset, so reporting statistics as you go
    costs chain_len + 1 event loops instead of one.
    """
    counts = [int(df.Count().GetValue())]
    current = df
    for name in bc.CHAIN_STEPS[:chain_len]:
        current = CHAIN_FILTERS[name](current)
        counts.append(int(current.Count().GetValue()))
    return {"final": counts[-1], "intermediate": counts, "event_loops": chain_len + 1}


def chain_rdf_report(df, chain_len):
    """The same per-filter counts as the eager path, but collected in one event loop."""
    total = df.Count()
    report = _apply_chain(df, chain_len).Report()
    counts = [int(total.GetValue())] + [int(cut.GetPass()) for cut in report]
    return {"final": counts[-1], "intermediate": counts, "event_loops": 1}


# --- TEST 3: per-track efficiency ------------------------------------------------------------

def _efficiency_reduction(df):
    """Books both reductions before triggering, so they share one event loop."""
    df = df.Define("bench_eff_sum", "ROOT::VecOps::Sum(PPSLocalTrack_efficiency)")
    df = df.Define("bench_eff_hits", "ROOT::VecOps::Sum(PPSLocalTrack_efficiency > 0.f)")
    df = df.Define("bench_n_tracks", "(int)PPSLocalTrack_efficiency.size()")
    eff_sum = df.Sum("bench_eff_sum")
    eff_hits = df.Sum("bench_eff_hits")
    n_tracks = df.Sum("bench_n_tracks")
    return {
        "eff_sum": float(eff_sum.GetValue()),
        "eff_hits": int(eff_hits.GetValue()),
        "n_tracks": int(n_tracks.GetValue()),
    }


def efficiency_rdf_jit(df, rp_id, arm_key, correction_json, pot_type):
    """Graph building (which triggers the cling compile) is separate from the reduction so the
    caller can put the two in different measurement phases."""
    return apply_diamond_efficiency_jit(df, rp_id, arm_key, correction_json, pot_type=pot_type)


def efficiency_rdf_run(df):
    return _efficiency_reduction(df)
