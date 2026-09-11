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


# --- predicate compilation styles ------------------------------------------------------------
#
# `jit` is what app/analyze_proton_events.py does: the whole predicate is a string, so cling
# compiles the RVec expression at graph-build time. `callable` moves the bodies into functions
# declared once, leaving a one-line call for cling to compile.
#
# This is the realistic mitigation, not a synthetic one -- it is what a user would do after
# noticing that the fixed cost dominates a short run. What it isolates is how much of that cost
# is the predicate body rather than RDataFrame's own bookkeeping.

_CALLABLE_SOURCE = f"""
namespace bench {{

inline bool pps(int n) {{ return n > 0; }}

inline bool doubleArm(const ROOT::RVec<int>& rp) {{
    bool left = false, right = false;
    for (auto id : rp) {{
        if (id == {bc.ARM_LEFT_RPS[0]} || id == {bc.ARM_LEFT_RPS[1]}) left = true;
        if (id == {bc.ARM_RIGHT_RPS[0]} || id == {bc.ARM_RIGHT_RPS[1]}) right = true;
    }}
    return left && right;
}}

inline bool diamond(const ROOT::RVec<int>& rpType) {{
    for (auto t : rpType) if (t == {bc.DIAMOND_RP_TYPE}) return true;
    return false;
}}

inline bool rpId(const ROOT::RVec<int>& rp, int wanted) {{
    for (auto id : rp) if (id == wanted) return true;
    return false;
}}

inline bool xiRange(const ROOT::RVec<float>& xi, float lo, float hi) {{
    for (auto v : xi) if (v >= lo && v <= hi) return true;
    return false;
}}

}}  // namespace bench
"""

_callable_declared = False


def _declare_callables():
    """Declares the predicate bodies once; cling rejects a redefinition in the same process."""
    global _callable_declared
    if not _callable_declared:
        ROOT.gInterpreter.Declare(_CALLABLE_SOURCE)
        _callable_declared = True


def _callable_filters(rp_id):
    lo, hi = bc.XI_RANGE
    return {
        "pps": lambda df: df.Filter("bench::pps(nPPSLocalTrack)", "Events with PPS data"),
        "double_arm": lambda df: df.Filter(
            "bench::doubleArm(PPSLocalTrack_decRPId)", "Events with tracks in both arms"
        ),
        "diamond": lambda df: df.Filter(
            "bench::diamond(PPSLocalTrack_rpType)", "Events with diamond detector tracks"
        ),
        "rp_id": lambda df: df.Filter(
            f"bench::rpId(PPSLocalTrack_decRPId, {rp_id})", f"Events with tracks in RP {rp_id}"
        ),
        "xi": lambda df: df.Filter(
            f"bench::xiRange(Proton_singleRP_xi, {lo}f, {hi}f)",
            f"Events with xi in [{lo}, {hi}]",
        ),
    }


def chain_filters(style="jit", rp_id=bc.DEFAULT_RP_ID):
    if style == "callable":
        _declare_callables()
        return _callable_filters(rp_id)
    return CHAIN_FILTERS


# --- TEST 1: single filter -------------------------------------------------------------------

def build_filter(df, rp_id, style="jit"):
    if style == "callable":
        _declare_callables()
        node = df.Filter(f"bench::rpId(PPSLocalTrack_decRPId, {rp_id})", f"RP {rp_id}")
    else:
        node = filter_detector_specific_events(df, rp_id)
    return node.Count()


def trigger_filter(handle):
    return int(handle.GetValue())


# --- TEST 2: filter chain --------------------------------------------------------------------

def build_chain_nodes(df, chain_len, order="notebook", style="jit", rp_id=bc.DEFAULT_RP_ID):
    """
    Every node of the chain, including the unfiltered root: `nodes[i]` has `i` filters applied.

    Returned in full rather than just the tail because the report path needs the root for its
    total, and building the nodes is exactly the cost we want outside the loop phase.
    """
    filters = chain_filters(style, rp_id)
    nodes = [df]
    for name in bc.chain_steps(chain_len, order):
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


def trigger_chain_eager(root, chain_len, order, style, rp_id):
    """
    Reproduces rdata_analysis(): the total event count, then one after every filter.

    Each GetValue() is a full pass over the dataset, so reporting statistics as you go costs
    chain_len + 1 event loops instead of one. Declaring the next filter only after reading the
    previous count is what keeps them from collapsing into a single loop -- RDataFrame would
    otherwise satisfy every booked action in one pass, which is the behaviour this path is
    supposed to lack.

    Unlike the lazy and report paths this one cannot have its graph building hoisted into a
    separate phase, and that is the point rather than a limitation. It also has a measurable
    I/O consequence: with the branches declared one loop at a time the TTreeCache never gets to
    learn them all at once, which is where the extra bytes read come from.
    """
    filters = chain_filters(style, rp_id)
    counts = [int(root.Count().GetValue())]
    current = root
    for name in bc.chain_steps(chain_len, order):
        current = filters[name](current)
        counts.append(int(current.Count().GetValue()))
    # One loop per count: the unfiltered total plus one after each filter.
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


# --- TEST 4: scattered vs contiguous selection -----------------------------------------------
#
# TESTING.md explains the flat bytes-read curve by arguing that filtering saves CPU but not
# I/O, because the events surviving a cut are spread across every basket of the branches read
# later, so each basket has to be decompressed anyway. That is a hypothesis about *where the
# survivors sit*, not about filtering as such, and it is testable.
#
# Both queries below keep a similar fraction of events and end in the same reduction over the
# same branch. They differ only in whether the survivors are contiguous in entry order. If the
# explanation is right, the contiguous one reads substantially fewer bytes; if both read the
# whole column, the explanation is wrong.

def build_selective_read(df, selection, n_events, rp_id=bc.DEFAULT_RP_ID, keep_fraction=0.25):
    column = bc.CHAIN_COLUMNS["xi"]
    if selection == "contiguous":
        # rdfentry_ is the global entry number and is valid under ImplicitMT, so this is a
        # genuine prefix of the file rather than a per-thread slice.
        node = df.Filter(f"rdfentry_ < {int(n_events * keep_fraction)}", "contiguous prefix")
    else:
        node = df.Filter(
            f"ROOT::VecOps::Any(PPSLocalTrack_decRPId == {rp_id})", "scattered selection"
        )
    node = node.Define("bench_xi_sum", f"ROOT::VecOps::Sum({column})")
    return {"passed": node.Count(), "xi_sum": node.Sum("bench_xi_sum")}


def trigger_selective_read(handles):
    return {
        "events_passed": int(handles["passed"].GetValue()),
        "xi_sum": float(handles["xi_sum"].GetValue()),
    }
