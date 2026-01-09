#!/usr/bin/env python3

import ROOT
import sys
import os
import correctionlib

# Import analysis functions from analyze_proton_events
from analyze_proton_events import (
    PPSHistogramType,
    filter_single_arm_events,
    rdata_analysis,
    create_histograms_and_plots
)


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

    print(f"✓ Loaded correction: {correction_name}")

    print("Extracting data from RDataFrame...")
    data = df.AsNumpy(columns=[input_column])
    n_events = len(data[input_column])
    all_corrections = []

    for evt_idx in range(n_events):
        x_array = data[input_column][evt_idx]
        n_tracks = len(x_array)
        event_corrections = []

        for track_idx in range(n_tracks):
            x_val = float(x_array[track_idx])

            try:
                corrected = corr.evaluate(x_val)
                event_corrections.append(corrected)
            except Exception as e:
                event_corrections.append(x_val)

        all_corrections.append(event_corrections)

        if (evt_idx + 1) % 5000 == 0:
            print(f"  Processed {evt_idx + 1}/{n_events} events...")


    ROOT.gInterpreter.Declare('''
    #include <vector>
    std::vector<std::vector<double>> g_corrections;
    
    ROOT::RVec<float> get_corrections(unsigned long long entry) {
        if (entry < g_corrections.size()) {
            ROOT::RVec<float> result(g_corrections[entry].size());
            for (size_t i = 0; i < result.size(); ++i) {
                result[i] = g_corrections[entry][i];
            }
            return result;
        }
        return ROOT::RVec<float>();
    }
    ''')

    ROOT.g_corrections.clear()
    for corr_list in all_corrections:
        ROOT.g_corrections.push_back(ROOT.std.vector['double'](corr_list))

    df_corrected = df.Define(output_column, "get_corrections(rdfentry_)")

    print("✓ Correction column added")
    print()
    return df_corrected, input_column, output_column


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
