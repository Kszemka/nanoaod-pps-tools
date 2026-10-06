#!/usr/bin/env python3
"""
uproot + awkward implementations: the honest columnar baseline.

Why this exists. The `python` implementation reads through `RDataFrame.AsNumpy()`, which for a
jagged branch hands back a NumPy array *of RVec objects* -- one Python object per event. Any
"vectorised" operation on that has to loop in Python underneath, and the measurements say so:
on examples/test.root the plain-loop mode came out faster than the vectorised one (2.86 s
against 4.20 s for TEST 1, 3.42 s against 4.05 s for TEST 3), and the TEST 2 chain jumped from
1.61 s at chain-len 1, where the only column is a flat integer, to 25.6 s at chain-len 2, where
the first jagged branch appears.

So the `python` path measures the cost of PyROOT's materialisation, not the cost of columnar
analysis in Python. awkward gives the real thing -- a flat values buffer plus offsets -- and
`ak.any(..., axis=1)` runs in compiled code. Without this baseline the comparison is against a
strawman, and the conclusion "RDataFrame is orders of magnitude faster than NumPy" would be
partly an artefact of how the NumPy side was forced to read its input.

Kept deliberately close to impl_python.py in structure so the two are readable side by side.
"""

import math

import numpy as np

import bench_common as bc
import app.diamond_geometry as diamond_geometry

try:
    import awkward as ak
    import uproot
    from uproot.source.futures import TrivialExecutor
except ImportError as exc:  # pragma: no cover - the cluster env has both
    raise SystemExit(
        "impl_uproot needs uproot and awkward: micromamba install -c conda-forge uproot awkward"
    ) from exc

# uproot decompresses baskets on a thread pool sized to the machine by default: on Ares the
# "single-threaded" uproot runs were measured at 434-501% CPU against 99% for every other
# implementation. The executors are pinned to the calling thread so ImplicitMT stays the only
# source of parallelism in the campaign.
_SERIAL = TrivialExecutor()

# Bytes read, accumulated across _read calls. The benchmark's own byte counter is
# TFile::GetFileBytesRead, which only sees I/O that went through ROOT and therefore reports a
# flat zero for this implementation -- making it look as though awkward read nothing at all.
# uproot's source keeps its own tally, so the comparison stays meaningful.
_bytes_read = 0


def bytes_read():
    return _bytes_read


def _read(path, columns, tree="Events"):
    """Columns from one file or a .txt list of them, concatenated in list order."""
    global _bytes_read
    parts = []
    for file_path in bc.input_files(path):
        with uproot.open(file_path) as handle:
            parts.append(handle[tree].arrays(
                columns,
                library="ak",
                decompression_executor=_SERIAL,
                interpretation_executor=_SERIAL,
            ))
            source = getattr(handle.file, "source", None)
            _bytes_read += int(getattr(source, "num_requested_bytes", 0) or 0)
    return parts[0] if len(parts) == 1 else ak.concatenate(parts)


# --- TEST 1: single filter -------------------------------------------------------------------

def filter_uproot(path, rp_id):
    column = bc.CHAIN_COLUMNS["double_arm"]
    data = _read(path, [column])
    return int(ak.sum(ak.any(data[column] == rp_id, axis=1)))


# --- TEST 2: filter chain --------------------------------------------------------------------

def _step_mask(name, data, rp_id, period=bc.DEFAULT_PERIOD):
    """Boolean per-event mask for one chain step, evaluated in compiled code."""
    column = data[bc.CHAIN_COLUMNS[name]]
    if name == "pps":
        return ak.to_numpy(column) > 0
    if name == "double_arm":
        (l1, l2), (r1, r2) = bc.PERIODS[period]["arms"]
        left = ak.any((column == l1) | (column == l2), axis=1)
        right = ak.any((column == r1) | (column == r2), axis=1)
        return ak.to_numpy(left & right)
    if name == "diamond":
        return ak.to_numpy(ak.any(column == bc.PERIODS[period]["rp_type"], axis=1))
    if name == "rp_id":
        return ak.to_numpy(ak.any(column == rp_id, axis=1))
    if name == "xi":
        lo, hi = bc.XI_RANGE
        return ak.to_numpy(ak.any((column >= lo) & (column <= hi), axis=1))
    if name == "multi_rp_idx":
        return ak.to_numpy(ak.any(column >= 0, axis=1))
    if name == "single_rp_idx":
        return ak.to_numpy(ak.any(column == -1, axis=1))
    if name == "multi_proton":
        return ak.to_numpy(column) > 1
    # time, time_unc, theta_y
    return ak.to_numpy(ak.any(column != 0, axis=1))


def chain_uproot(path, chain_len, rp_id=bc.DEFAULT_RP_ID, chain="base", period=bc.DEFAULT_PERIOD):
    data = _read(path, bc.chain_columns(chain_len, chain))
    n_events = len(data)
    counts = [n_events]

    # What RDataFrame does: later steps only ever look at events that got past the earlier ones.
    surviving = np.arange(n_events)
    for name in bc.chain_steps(chain_len, chain):
        surviving = surviving[_step_mask(name, data[surviving], rp_id, period)]
        counts.append(len(surviving))
    return {"final": counts[-1], "intermediate": counts, "event_loops": 1}


# --- TEST 3: per-track efficiency ------------------------------------------------------------

def efficiency_uproot(path, rp_id, arm_key, pot_type, correction_json):
    """
    Same geometry and the same lookup table as impl_python's vector mode, on awkward arrays.

    The event selection is applied here rather than upstream: the RDataFrame paths get a
    dataframe that has already been filtered on rp_id, so to measure the same work this has to
    do that filtering itself.
    """
    import correctionlib

    cset = correctionlib.CorrectionSet.from_file(correction_json)
    corr = cset[list(cset.keys())[0]]
    n_regions = diamond_geometry.POT_CONFIG[pot_type]["n_regions"]
    lut = np.array([corr.evaluate(i) for i in range(n_regions)], dtype=np.float64)

    data = _read(path, bc.EFFICIENCY_COLUMNS)
    rps = data["PPSLocalTrack_decRPId"]
    data = data[ak.any(rps == rp_id, axis=1)]

    flat_x = ak.to_numpy(ak.flatten(data["PPSLocalTrack_x"])).astype(np.float64)
    flat_y = ak.to_numpy(ak.flatten(data["PPSLocalTrack_y"])).astype(np.float64)
    flat_rp = ak.to_numpy(ak.flatten(data["PPSLocalTrack_decRPId"]))
    n_tracks = int(flat_x.size)
    if n_tracks == 0:
        return {"eff_sum": 0.0, "eff_hits": 0, "n_tracks": 0}

    config = diamond_geometry.POT_CONFIG[pot_type]
    center_x, center_y = config["centers"][arm_key]
    theta = math.radians(config["angles_deg"][arm_key])
    cos_theta, sin_theta = math.cos(theta), math.sin(theta)

    dx, dy = flat_x - center_x, flat_y - center_y
    u = dx * cos_theta + dy * sin_theta
    v = -dx * sin_theta + dy * cos_theta

    size_x = diamond_geometry.DIAMOND_SIZE_X
    edges = np.array([-n_regions * size_x / 2 + i * size_x for i in range(n_regions + 1)])
    half_y = diamond_geometry.DIAMOND_SIZE_Y / 2

    # searchsorted(side="left") - 1 reproduces assign_region's inclusive-on-both-ends bins:
    # a u landing exactly on an internal edge falls into the lower region, as in the loop.
    region = np.searchsorted(edges, u, side="left") - 1
    region = np.where(u == edges[0], 0, region)
    valid = (
        (flat_rp == rp_id)
        & (v >= -half_y)
        & (v <= half_y)
        & (region >= 0)
        & (region < n_regions)
    )

    values = np.zeros(n_tracks, dtype=np.float32)
    values[valid] = lut[region[valid]].astype(np.float32)
    return {
        "eff_sum": float(values.astype(np.float64).sum()),
        "eff_hits": int(np.count_nonzero(valid)),
        "n_tracks": n_tracks,
    }
