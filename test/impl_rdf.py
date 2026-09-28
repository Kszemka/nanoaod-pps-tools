#!/usr/bin/env python3
"""
RDataFrame implementations of the three benchmarked operations.

Every implementation is split into `build` and `trigger`. RDataFrame is lazy, so a build on its
own reads nothing -- but it is not free either: `Filter("string")` hands the expression to cling
to compile, which is a fixed cost independent of the dataset. Keeping the two apart is what
lets the caller charge compilation to a `jit` phase and the event loop to a `loop` phase.

The one exception is `rdf-eager`, and deliberately so: its whole point is that it interleaves
counting with filtering, so it has no separable build step.
"""

import bench_common as bc

from app.analyze_proton_events import (
    filter_detector_specific_events,
    filter_detector_type,
    filter_double_arm_events,
    filter_xi_ranged_events,
)
from app.apply_corrections import apply_diamond_efficiency_jit


def chain_filters(rp_id=bc.DEFAULT_RP_ID):
    return {
        "pps": lambda df: df.Filter("nPPSLocalTrack > 0", "Events with PPS data"),
        "double_arm": filter_double_arm_events,
        "diamond": lambda df: filter_detector_type(df, "diamond"),
        "rp_id": lambda df: filter_detector_specific_events(df, rp_id),
        "xi": lambda df: filter_xi_ranged_events(df, *bc.XI_RANGE),
    }


# --- TEST 1: single filter -------------------------------------------------------------------

def build_filter(df, rp_id):
    return filter_detector_specific_events(df, rp_id).Count()


def trigger_filter(handle):
    return int(handle.GetValue())


# --- TEST 2: filter chain --------------------------------------------------------------------

def build_chain_nodes(df, chain_len, rp_id=bc.DEFAULT_RP_ID):
    """
    Every node of the chain, including the unfiltered root: `nodes[i]` has `i` filters applied.

    Returned in full rather than just the tail because the report path needs the root for its
    total, and building the nodes is exactly the cost we want outside the loop phase.
    """
    filters = chain_filters(rp_id)
    nodes = [df]
    for name in bc.chain_steps(chain_len):
        nodes.append(filters[name](nodes[-1]))
    return nodes


def build_chain_lazy(nodes):
    """Whole chain, one Count() at the end -> a single event loop."""
    return {"final": nodes[-1].Count()}


def trigger_chain_lazy(handles):
    return {
        "final": int(handles["final"].GetValue()),
        "intermediate": None,
        "event_loops": 1,
    }


def trigger_chain_eager(root, chain_len, rp_id):
    """
    Reproduces rdata_analysis(): the total event count, then one after every filter.

    Each GetValue() is a full pass over the dataset, so reporting statistics as you go costs
    chain_len + 1 event loops instead of one. Declaring the next filter only after reading the
    previous count is what keeps them from collapsing into a single loop -- RDataFrame would
    otherwise satisfy every booked action in one pass, which is the behaviour this path is
    supposed to lack.
    """
    filters = chain_filters(rp_id)
    counts = [int(root.Count().GetValue())]
    current = root
    for name in bc.chain_steps(chain_len):
        current = filters[name](current)
        counts.append(int(current.Count().GetValue()))
    return {"final": counts[-1], "intermediate": counts, "event_loops": len(counts)}


def build_chain_report(nodes):
    """The same per-filter counts as the eager path, but collected in one event loop."""
    return {"total": nodes[0].Count(), "report": nodes[-1].Report()}


def trigger_chain_report(handles):
    total = int(handles["total"].GetValue())
    counts = [total] + [int(cut.GetPass()) for cut in handles["report"]]
    return {"final": counts[-1], "intermediate": counts, "event_loops": 1}


CHAIN_BUILDERS = {
    "rdf-lazy": (build_chain_lazy, trigger_chain_lazy),
    "rdf-report": (build_chain_report, trigger_chain_report),
}


# --- TEST 3: per-track efficiency ------------------------------------------------------------

def build_efficiency(df):
    """Books all three reductions before triggering, so they share one event loop."""
    df = df.Define("bench_eff_sum", "ROOT::VecOps::Sum(PPSLocalTrack_efficiency)")
    df = df.Define("bench_eff_hits", "ROOT::VecOps::Sum(PPSLocalTrack_efficiency > 0.f)")
    df = df.Define("bench_n_tracks", "(int)PPSLocalTrack_efficiency.size()")
    return {
        "eff_sum": df.Sum("bench_eff_sum"),
        "eff_hits": df.Sum("bench_eff_hits"),
        "n_tracks": df.Sum("bench_n_tracks"),
    }


def trigger_efficiency(handles):
    return {
        "eff_sum": float(handles["eff_sum"].GetValue()),
        "eff_hits": int(handles["eff_hits"].GetValue()),
        "n_tracks": int(handles["n_tracks"].GetValue()),
    }


def efficiency_rdf_jit(df, rp_id, arm_key, correction_json, pot_type):
    """Adds the efficiency column. The cling compile happens here, not in the reduction."""
    return apply_diamond_efficiency_jit(df, rp_id, arm_key, correction_json, pot_type=pot_type)
