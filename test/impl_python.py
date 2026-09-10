#!/usr/bin/env python3
"""
Pure-Python implementations of the same three operations, reading through AsNumpy().

Two modes throughout:
  vector - NumPy on flattened jagged arrays (how you would sensibly write it)
  loop   - plain Python for-loops (the naive version)

Both materialise every column they touch in full before doing any work; that is the structural
difference from the RDataFrame path, and it is what the memory and bytes-read plots measure.

Geometry constants come from diamond_geometry.POT_CONFIG rather than being re-typed here, so
this stays a different *implementation* of the same definition rather than a second definition.
"""

import math

import numpy as np

import bench_common as bc
import correctionlib
import app.diamond_geometry as diamond_geometry


def _flatten(jagged):
    """Jagged object-array of per-event arrays -> (flat values, event index per value)."""
    counts = np.fromiter((len(a) for a in jagged), dtype=np.int64, count=len(jagged))
    if counts.sum() == 0:
        return np.empty(0), np.empty(0, dtype=np.int64), counts
    flat = np.concatenate([np.asarray(a) for a in jagged if len(a)])
    event_id = np.repeat(np.arange(len(jagged), dtype=np.int64), counts)
    return flat, event_id, counts


# --- TEST 1: single filter -------------------------------------------------------------------

def filter_python(df, rp_id, mode):
    column = bc.CHAIN_COLUMNS["double_arm"]
    data = df.AsNumpy([column])[column]

    if mode == "loop":
        return sum(1 for event in data if rp_id in event)

    flat, event_id, _ = _flatten(data)
    if flat.size == 0:
        return 0
    matching_events = np.unique(event_id[flat == rp_id])
    return int(matching_events.size)


# --- TEST 2: filter chain --------------------------------------------------------------------

def _any_in(jagged, values):
    return np.fromiter(
        (bool(np.isin(np.asarray(event), values).any()) for event in jagged),
        dtype=bool,
        count=len(jagged),
    )


def _step_mask(name, data, rp_id):
    """Boolean per-event mask for one chain step, evaluated over all events."""
    column = data[bc.CHAIN_COLUMNS[name]]
    if name == "pps":
        return np.asarray(column) > 0
    if name == "double_arm":
        return _any_in(column, bc.ARM_LEFT_RPS) & _any_in(column, bc.ARM_RIGHT_RPS)
    if name == "diamond":
        return _any_in(column, [bc.DIAMOND_RP_TYPE])
    if name == "rp_id":
        return _any_in(column, [rp_id])
    lo, hi = bc.XI_RANGE
    return np.fromiter(
        (bool(((np.asarray(e) >= lo) & (np.asarray(e) <= hi)).any()) for e in column),
        dtype=bool,
        count=len(column),
    )


def _step_passes(name, event, rp_id):
    """Same predicate as _step_mask, for a single event, without NumPy."""
    if name == "pps":
        return int(event) > 0
    if name == "double_arm":
        left = any(int(v) in bc.ARM_LEFT_RPS for v in event)
        right = any(int(v) in bc.ARM_RIGHT_RPS for v in event)
        return left and right
    if name == "diamond":
        return any(int(v) == bc.DIAMOND_RP_TYPE for v in event)
    if name == "rp_id":
        return any(int(v) == rp_id for v in event)
    lo, hi = bc.XI_RANGE
    return any(lo <= float(v) <= hi for v in event)


def chain_python(df, chain_len, mode, rp_id=bc.DEFAULT_RP_ID):
    # Every column the chain needs is pulled up front -- unlike RDataFrame, there is no way to
    # read the later columns only for the events that survived the earlier filters. All of the
    # filtering happens here too, including the nPPSLocalTrack > 0 step: leaving it to
    # RDataFrame would mean measuring RDataFrame doing part of Python's work.
    columns = bc.chain_columns(chain_len)
    data = df.AsNumpy(columns)
    n_events = len(data[columns[0]])
    counts = [n_events]

    if mode == "loop":
        surviving = list(range(n_events))
        for name in bc.CHAIN_STEPS[:chain_len]:
            column = data[bc.CHAIN_COLUMNS[name]]
            surviving = [i for i in surviving if _step_passes(name, column[i], rp_id)]
            counts.append(len(surviving))
        return {"final": counts[-1], "intermediate": counts, "event_loops": 1}

    combined = None
    for name in bc.CHAIN_STEPS[:chain_len]:
        mask = _step_mask(name, data, rp_id)
        combined = mask if combined is None else (combined & mask)
        counts.append(int(np.count_nonzero(combined)))
    return {"final": counts[-1], "intermediate": counts, "event_loops": 1}


# --- TEST 3: per-track efficiency ------------------------------------------------------------

EFFICIENCY_COLUMNS = ["PPSLocalTrack_x", "PPSLocalTrack_y", "PPSLocalTrack_decRPId"]


def _region_edges(arm_key, pot_type):
    n_regions = diamond_geometry.POT_CONFIG[pot_type]["n_regions"]
    u_left = -n_regions * diamond_geometry.DIAMOND_SIZE_X / 2
    return np.array(
        [u_left + i * diamond_geometry.DIAMOND_SIZE_X for i in range(n_regions + 1)]
    )


def _rotation(arm_key, pot_type):
    center = diamond_geometry.POT_CONFIG[pot_type]["centers"][arm_key]
    theta = math.radians(diamond_geometry.POT_CONFIG[pot_type]["angles_deg"][arm_key])
    return center, math.cos(theta), math.sin(theta)


def _lut(arm_key, pot_type, correction_json):
    cset = correctionlib.CorrectionSet.from_file(correction_json)
    corr = cset[list(cset.keys())[0]]
    n_regions = diamond_geometry.POT_CONFIG[pot_type]["n_regions"]
    return np.array([corr.evaluate(i) for i in range(n_regions)], dtype=np.float64)


def efficiency_python(df, rp_id, arm_key, pot_type, correction_json, mode):
    """No correctionlib in the hot path: the region -> efficiency values are read once, then
    the geometry is evaluated directly, as if the whole thing had been written by hand."""
    lut = _lut(arm_key, pot_type, correction_json)
    data = df.AsNumpy(EFFICIENCY_COLUMNS)
    xs, ys, rps = (data[c] for c in EFFICIENCY_COLUMNS)

    if mode == "loop":
        eff_sum = 0.0
        eff_hits = 0
        n_tracks = 0
        for i in range(len(xs)):
            x_event, y_event, rp_event = xs[i], ys[i], rps[i]
            for t in range(len(x_event)):
                n_tracks += 1
                if int(rp_event[t]) != rp_id:
                    continue
                region = diamond_geometry.assign_region(
                    float(x_event[t]), float(y_event[t]), arm_key, pot_type
                )
                if region < 0:
                    continue
                value = np.float32(lut[region])
                eff_sum += float(value)
                eff_hits += 1
        return {"eff_sum": eff_sum, "eff_hits": eff_hits, "n_tracks": n_tracks}

    flat_x, _, counts = _flatten(xs)
    flat_y, _, _ = _flatten(ys)
    flat_rp, _, _ = _flatten(rps)
    n_tracks = int(counts.sum())
    if n_tracks == 0:
        return {"eff_sum": 0.0, "eff_hits": 0, "n_tracks": 0}

    (center_x, center_y), cos_theta, sin_theta = _rotation(arm_key, pot_type)
    dx = flat_x.astype(np.float64) - center_x
    dy = flat_y.astype(np.float64) - center_y
    u = dx * cos_theta + dy * sin_theta
    v = -dx * sin_theta + dy * cos_theta

    edges = _region_edges(arm_key, pot_type)
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
        & (region < len(edges) - 1)
    )

    values = np.zeros(n_tracks, dtype=np.float32)
    values[valid] = lut[region[valid]].astype(np.float32)
    return {
        "eff_sum": float(values.astype(np.float64).sum()),
        "eff_hits": int(np.count_nonzero(valid)),
        "n_tracks": n_tracks,
    }


def efficiency_correctionlib(df, rp_id, arm_key, pot_type, correction_json):
    """correctionlib evaluated per track through its Python API -- its real per-call cost."""
    cset = correctionlib.CorrectionSet.from_file(correction_json)
    corr = cset[list(cset.keys())[0]]
    data = df.AsNumpy(EFFICIENCY_COLUMNS)
    xs, ys, rps = (data[c] for c in EFFICIENCY_COLUMNS)

    eff_sum = 0.0
    eff_hits = 0
    n_tracks = 0
    for i in range(len(xs)):
        x_event, y_event, rp_event = xs[i], ys[i], rps[i]
        for t in range(len(x_event)):
            n_tracks += 1
            if int(rp_event[t]) != rp_id:
                continue
            region = diamond_geometry.assign_region(
                float(x_event[t]), float(y_event[t]), arm_key, pot_type
            )
            if region < 0:
                continue
            eff_sum += float(np.float32(corr.evaluate(region)))
            eff_hits += 1
    return {"eff_sum": eff_sum, "eff_hits": eff_hits, "n_tracks": n_tracks}
