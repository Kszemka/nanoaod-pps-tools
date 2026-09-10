#!/usr/bin/env python3

import ROOT
import sys
import os
import correctionlib

# Import analysis functions from analyze_proton_events
from app.analyze_proton_events import (
    PPSHistogramType,
    filter_single_arm_events,
    rdata_analysis,
    create_histograms_and_plots
)
import app.diamond_geometry as diamond_geometry


def apply_corrections_hybrid(df, correction_file):
    """
    Apply corrections using correctionlib Python API + RDataFrame C++.

    Standard HEP approach:
    1. Use correctionlib Python to compute corrections
    2. Store results in C++ global storage
    3. Use RDataFrame Define() to add corrected column

    Args:
        df: RDataFrame with PPS data
        correction_file: Path to correctionlib JSON file

    Returns:
        RDataFrame with corrected column added
    """

    print(f"=== Applying Corrections with correctionlib ===")
    print(f"Loading: {correction_file}")

    import json
    with open(correction_file, 'r') as f:
        json_data = json.load(f)

    metadata = json_data.get('metadata', {})

    if 'input_column' not in metadata or 'output_column' not in metadata:
        print("ERROR: JSON file must contain 'metadata' section with:")
        sys.exit(1)

    input_column = metadata['input_column']
    output_column = metadata['output_column']

    cset = correctionlib.CorrectionSet.from_file(correction_file)
    correction_name = list(cset.keys())[0]
    corr = cset[correction_name]

    # The correction's declared "inputs" tell us what args evaluate() needs
    # and in what order (e.g. ["x"], or ["track_idx"], or ["rdfentry_", "track_idx"]).
    # Names other than "track_idx"/"rdfentry_" are assumed to refer to the X value.
    correction_def = json_data['corrections'][0]
    input_names = [inp['name'] for inp in correction_def.get('inputs', [])]
    output_name = correction_def.get('output', {}).get('name', '')
    # A correction whose output is an "offset" must be added to x; otherwise
    # its result IS the corrected value.
    is_offset = output_name == 'correction_offset'

    print(f"✓ Loaded correction: {correction_name}")

    print("Extracting data from RDataFrame...")
    # IMPORTANT: also pull rdfentry_ — after any .Filter(), the surviving
    # events keep their ORIGINAL tree entry numbers (not a compact 0..N-1
    # sequence). AsNumpy() only returns values for surviving events, in
    # order, so we must remember each row's real entry number to correctly
    # map corrections back with Define("...", "get_corrections(rdfentry_)").
    data = df.AsNumpy(columns=["rdfentry_", input_column])
    entries = data["rdfentry_"]
    n_events = len(entries)
    all_corrections = []  # list of (entry_number, [corrected values...])

    for evt_idx in range(n_events):
        entry = int(entries[evt_idx])
        x_array = data[input_column][evt_idx]
        n_tracks = len(x_array)
        event_corrections = []

        for track_idx in range(n_tracks):
            x_val = float(x_array[track_idx])
            arg_values = {"track_idx": track_idx, "rdfentry_": entry}
            args = [arg_values.get(name, x_val) for name in input_names]

            try:
                result = corr.evaluate(*args)
                corrected = x_val + result if is_offset else result
                event_corrections.append(corrected)
            except Exception as e:
                event_corrections.append(x_val)

        all_corrections.append((entry, event_corrections))

        if (evt_idx + 1) % 5000 == 0:
            print(f"  Processed {evt_idx + 1}/{n_events} events...")


    curr_time = getattr(ROOT, "_my_time_uniq", 0) + 1
    ROOT._my_time_uniq = curr_time

    decl_str = f'''
    #include <vector>
    #include <unordered_map>
    std::unordered_map<ULong64_t, std::vector<double>> g_corrections_{curr_time};

    ROOT::RVec<float> get_corrections_{curr_time}(ULong64_t entry) {{
        auto it = g_corrections_{curr_time}.find(entry);
        if (it != g_corrections_{curr_time}.end()) {{
            ROOT::RVec<float> result(it->second.size());
            for (size_t i = 0; i < result.size(); ++i) {{
                result[i] = it->second[i];
            }}
            return result;
        }}
        return ROOT::RVec<float>();
    }}
    '''
    ROOT.gInterpreter.Declare(decl_str)

    # Use getattr/setattr dynamically instead of writing literal code
    root_map = getattr(ROOT, f"g_corrections_{curr_time}")
    for entry, corr_list in all_corrections:
        root_map[entry] = ROOT.std.vector['double'](corr_list)

    df_corrected = df.Define(output_column, f"get_corrections_{curr_time}(rdfentry_)")

    print("✓ Correction column added")
    print()
    return df_corrected, input_column, output_column


def _diamond_kernel_registry():
    """Declared-kernel cache, held on the ROOT module so it survives importlib.reload()."""
    if not hasattr(ROOT, "_diamond_eff_kernels"):
        ROOT._diamond_eff_kernels = {}
    return ROOT._diamond_eff_kernels


def _declare_diamond_kernel(rp_id, arm_key, pot_type, eff_values):
    """
    Declares (once per distinct parameter set) a C++ kernel mapping a track's (x, y, decRPId) to
    its efficiency, and returns its name.

    Cling cannot redefine an already-Declare'd function in the same process, so the registry is
    keyed by everything baked into the source; re-calling with identical parameters reuses the
    existing kernel instead of raising "redefinition of ...".
    """
    key = (pot_type, arm_key, int(rp_id), tuple(eff_values))
    registry = _diamond_kernel_registry()
    if key in registry:
        return registry[key]

    uid = len(registry)
    region_func = f"diamondRegion_{uid}"
    kernel_func = f"diamondEff_{uid}"
    lut = ", ".join(f"{v!r}f" for v in eff_values)

    decl_str = diamond_geometry.get_cpp_source(arm_key, pot_type, region_func) + f"""
#include <array>

template <typename Tx, typename Ty, typename Trp>
ROOT::RVec<float> {kernel_func}(const ROOT::RVec<Tx>& x, const ROOT::RVec<Ty>& y,
                                const ROOT::RVec<Trp>& rp) {{
    constexpr std::array<float, {len(eff_values)}> kEfficiency = {{{lut}}};
    ROOT::RVec<float> out(x.size(), 0.f);
    for (std::size_t i = 0; i < x.size(); ++i) {{
        if (static_cast<int>(rp[i]) != {int(rp_id)}) continue;
        const int region = {region_func}(x[i], y[i]);
        if (region >= 0) out[i] = kEfficiency[region];
    }}
    return out;
}}
"""
    if not ROOT.gInterpreter.Declare(decl_str):
        raise RuntimeError(f"Failed to JIT-compile diamond efficiency kernel {kernel_func}")

    registry[key] = kernel_func
    return kernel_func


def apply_diamond_efficiency_jit(df, rp_id, arm_key, correction_json, pot_type="box"):
    """
    Adds a PPSLocalTrack_efficiency column, evaluated only for tracks in the given diamond RP
    (rp_id), using the pot-type region geometry (diamond_geometry) + a region_idx -> efficiency
    correctionlib JSON (built by build_diamond_efficiency_json).

    The correction is evaluated once per region at setup time and baked into the compiled kernel
    as a lookup table, so correctionlib stays the input format without sitting in the per-track
    hot path. The kernel is a pure function of the track columns, so unlike a Python-side pass it
    needs no rdfentry_ bookkeeping to survive an upstream .Filter(), and is safe under
    EnableImplicitMT.

    Args:
        df: RDataFrame (already filtered to events with a track in rp_id, e.g. via
            filter_detector_specific_events)
        rp_id: decRPId of the diamond RP (e.g. 22/122 for box, 16/116 for cyl)
        arm_key: "45" or "56", used to select the region ranges
        correction_json: path to the region_idx -> efficiency correctionlib JSON
        pot_type: "box" or "cyl", selects the region geometry

    Returns:
        RDataFrame with PPSLocalTrack_efficiency added (0.0 for tracks outside rp_id or outside
        all regions).
    """
    print(f"=== Applying Diamond {pot_type.capitalize()} Efficiency ===")

    cset = correctionlib.CorrectionSet.from_file(correction_json)
    corr = cset[list(cset.keys())[0]]

    print(f"Loaded correction: {corr.name}")

    n_regions = diamond_geometry.POT_CONFIG[pot_type]["n_regions"]
    eff_values = [float(corr.evaluate(region_idx)) for region_idx in range(n_regions)]

    kernel_func = _declare_diamond_kernel(rp_id, arm_key, pot_type, eff_values)
    df_with_efficiency = df.Define(
        "PPSLocalTrack_efficiency",
        f"{kernel_func}(PPSLocalTrack_x, PPSLocalTrack_y, PPSLocalTrack_decRPId)",
    )

    print("Efficiency column added")
    print()
    return df_with_efficiency


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 apply_corrections.py <root_file> <correction_json>")
        return

    file_path = sys.argv[1]
    correction_file = sys.argv[2]

    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return

    if not os.path.exists(correction_file):
        print(f"Error: {correction_file} not found")
        return


    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kWarning

    df_filtered = rdata_analysis(file_path, [filter_single_arm_events])

    df_corrected, input_column, output_column = apply_corrections_hybrid(df_filtered, correction_file)

    if 'x' in input_column.lower():
        histogram_type = PPSHistogramType.PPS_LOCAL_TRACK_X
    elif 'y' in input_column.lower():
        histogram_type = PPSHistogramType.PPS_LOCAL_TRACK_Y
    else:
        histogram_type = PPSHistogramType.PPS_LOCAL_TRACK_X  # default

    histogram_types = [histogram_type]

    print("\nOriginal data histograms:")
    create_histograms_and_plots(
        df_corrected,
        histogram_types,
        output_prefix="pps_original",
        corrections=False,
        save_root=False  # Don't save ROOT files
    )

    print("\nCorrected data histograms:")
    create_histograms_and_plots(
        df_corrected,
        histogram_types,
        output_prefix="pps_corrected",
        corrections=True,
        save_root=False  # Don't save ROOT files
    )


if __name__ == "__main__":
    main()
