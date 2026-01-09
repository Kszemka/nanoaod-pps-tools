#!/usr/bin/env python3

import ROOT
import sys
import os
from enum import Enum


class PPSHistogramType(Enum):
    """
    Enum representing all PPS and proton variables found in ROOT file
    for histogram generation
    """
    # Trigger variables (HLT)
    HLT_DiPFJetAve180_PPSMatch_Xi0p3_QuadJet_Max2ProtPerRP = "HLT_DiPFJetAve180_PPSMatch_Xi0p3_QuadJet_Max2ProtPerRP"
    HLT_PPSMaxTracksPerArm1 = "HLT_PPSMaxTracksPerArm1"
    HLT_PPSMaxTracksPerRP4 = "HLT_PPSMaxTracksPerRP4"
    HLT_PPSRandom = "HLT_PPSRandom"

    # Track count
    N_PPS_LOCAL_TRACK = "nPPSLocalTrack"

    # PPSLocalTrack position variables
    PPS_LOCAL_TRACK_X = "PPSLocalTrack_x"
    PPS_LOCAL_TRACK_Y = "PPSLocalTrack_y"

    # PPSLocalTrack identification
    PPS_LOCAL_TRACK_DEC_RP_ID = "PPSLocalTrack_decRPId"
    PPS_LOCAL_TRACK_RP_TYPE = "PPSLocalTrack_rpType"

    # PPSLocalTrack associations
    PPS_LOCAL_TRACK_MULTI_RP_PROTON_IDX = "PPSLocalTrack_multiRPProtonIdx"
    PPS_LOCAL_TRACK_SINGLE_RP_PROTON_IDX = "PPSLocalTrack_singleRPProtonIdx"

    # PPSLocalTrack timing variables
    PPS_LOCAL_TRACK_TIME = "PPSLocalTrack_time"
    PPS_LOCAL_TRACK_TIME_UNC = "PPSLocalTrack_timeUnc"

    # Proton_multiRP variables
    N_PROTON_MULTI_RP = "nProton_multiRP"
    PROTON_MULTI_RP_ARM = "Proton_multiRP_arm"
    PROTON_MULTI_RP_T = "Proton_multiRP_t"
    PROTON_MULTI_RP_THETA_X = "Proton_multiRP_thetaX"
    PROTON_MULTI_RP_THETA_Y = "Proton_multiRP_thetaY"
    PROTON_MULTI_RP_TIME = "Proton_multiRP_time"
    PROTON_MULTI_RP_TIME_UNC = "Proton_multiRP_timeUnc"
    PROTON_MULTI_RP_XI = "Proton_multiRP_xi"

    # Proton_singleRP variables
    N_PROTON_SINGLE_RP = "nProton_singleRP"
    PROTON_SINGLE_RP_DEC_RP_ID = "Proton_singleRP_decRPId"
    PROTON_SINGLE_RP_THETA_Y = "Proton_singleRP_thetaY"
    PROTON_SINGLE_RP_XI = "Proton_singleRP_xi"


def filter_double_arm_events(df):
    """
    Select events with tracks in both arms:
    - Left arm: RP ID 23 or 123
    - Right arm: RP ID 3 or 103
    """
    df_filtered = df.Filter(
        "(ROOT::VecOps::Any(PPSLocalTrack_decRPId == 23 || PPSLocalTrack_decRPId == 123)) && "
        "(ROOT::VecOps::Any(PPSLocalTrack_decRPId == 3 || PPSLocalTrack_decRPId == 103))",
        "Events with tracks in both arms (23|123) and (3|103)"
    )
    return df_filtered


def filter_single_arm_events(df):
    """
    Select events with tracks in only one arm (left OR right, but not both)
    """
    df_filtered = df.Filter(
        "(ROOT::VecOps::Any(PPSLocalTrack_decRPId == 23 || PPSLocalTrack_decRPId == 123)) != "
        "(ROOT::VecOps::Any(PPSLocalTrack_decRPId == 3 || PPSLocalTrack_decRPId == 103))",
        "Events with tracks in only one arm"
    )
    return df_filtered


def filter_detector_specific_events(df, rp_id):
    """
    Select events with tracks in specific Roman Pot detector
    """
    filter_expr = f"ROOT::VecOps::Any(PPSLocalTrack_decRPId == {rp_id})"
    df_filtered = df.Filter(filter_expr, f"Events with tracks in RP {rp_id}")
    return df_filtered


def filter_xi_ranged_events(df, xi_min, xi_max):
    """
    Select events with proton fractional momentum loss in specified range
    Assumes PPSLocalTrack_xi variable exists
    """
    filter_expr = f"ROOT::VecOps::Any(PPSLocalTrack_xi >= {xi_min} && PPSLocalTrack_xi <= {xi_max})"
    df_filtered = df.Filter(filter_expr, f"Events with xi in [{xi_min}, {xi_max}]")
    return df_filtered


def filter_detector_type(df, detector_type):
    """
    Select events with tracks in specific detector type

    Args:
        df: RDataFrame
        detector_type: 'pixel' for silicon pixel detectors (RP 3, 23, 103, 123)
                      'diamond' for diamond timing detectors (RP 16, 22, 116, 122)

    Returns:
        Filtered RDataFrame
    """
    detector_map = {
        'pixel': [3, 23, 103, 123],
        'diamond': [16, 22, 116, 122]
    }

    if detector_type.lower() not in detector_map:
        raise ValueError(f"Unknown detector type '{detector_type}'. Use 'pixel' or 'diamond'.")

    rp_ids = detector_map[detector_type.lower()]

    conditions = " || ".join([f"PPSLocalTrack_decRPId == {rp_id}" for rp_id in rp_ids])
    filter_expr = f"ROOT::VecOps::Any({conditions})"

    df_filtered = df.Filter(filter_expr, f"Events with {detector_type} detector tracks")
    return df_filtered


def rdata_analysis(file_path, filter_funcs=None):
    """
    Simple RDataFrame analysis of PPS data - filtering, statistics, parallel processing

    Args:
        file_path: Path to ROOT file
        filter_funcs: List of filter functions to apply (optional)
                     Each function should take df and return filtered df
    """

    print("=== RDataFrame PPS Analysis ===")
    print(f"Analyzing file: {file_path}")
    print()

    df = ROOT.RDataFrame("Events", file_path)

    print(f"Total events in file: {df.Count().GetValue()}")

    # Filter events with at least one PPS track
    df_with_pps = df.Filter("nPPSLocalTrack > 0")
    events_with_pps = df_with_pps.Count().GetValue()

    print(f"Events with PPS data: {events_with_pps}")
    print()

    # Apply custom filters if provided
    if filter_funcs:
        print("=== Applying Custom Filters ===")
        df_filtered = df_with_pps

        for i, filter_func in enumerate(filter_funcs):
            print(f"Applying filter {i + 1}: {filter_func.__name__}")
            df_filtered = filter_func(df_filtered)
            count = df_filtered.Count().GetValue()
            print(f"  Events after filter: {count}")

        print()
        print("=== Filter Results ===")
        print(f"Events after all filters: {df_filtered.Count().GetValue()}")
        print()
    else:
        # No filters applied - use all PPS events
        df_filtered = df_with_pps

    return df_filtered

def create_histograms_and_plots(df_with_pps, histogram_types=None, output_prefix="pps_analysis"):
    """
    Create histograms and plots for PPS analysis

    Args:
        df_with_pps: Filtered RDataFrame with PPS data
        histogram_types: List of PPSHistogramType enums specifying which histograms to create
                        If None, creates common histograms (nTracks, X, Y, XY)
        output_prefix: Prefix for output files (default: "pps_analysis")

    Returns:
        Dictionary of created histograms
    """

    print("=== Creating Histograms ===")

    # Create data directory if it doesn't exist
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created directory: {data_dir}")

    if histogram_types is None:
        # Generate ALL histograms for all 25 PPS and Proton variables
        histogram_types = list(PPSHistogramType)

    histograms = {}

    for hist_type in histogram_types:
        var_name = hist_type.value
        print(f"Creating histogram for: {var_name}")

        if hist_type == PPSHistogramType.N_PPS_LOCAL_TRACK:
            h = df_with_pps.Histo1D(
                ("h_ntracks", "Number of PPS tracks per event;Number of tracks;Events",
                 20, 0, 20), var_name)
            histograms['ntracks'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_X:
            h = df_with_pps.Histo1D(
                ("h_track_x", "PPS track X position;X [mm];Tracks",
                 100, -20, 20), var_name)
            histograms['track_x'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_Y:
            h = df_with_pps.Histo1D(
                ("h_track_y", "PPS track Y position;Y [mm];Tracks",
                 100, -20, 20), var_name)
            histograms['track_y'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_DEC_RP_ID:
            h = df_with_pps.Histo1D(
                ("h_dec_rp_id", "PPS Roman Pot ID;RP ID;Tracks",
                 130, 0, 130), var_name)
            histograms['dec_rp_id'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_RP_TYPE:
            h = df_with_pps.Histo1D(
                ("h_rp_type", "PPS Roman Pot Type;RP Type;Tracks",
                 10, 0, 10), var_name)
            histograms['rp_type'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_TIME:
            h = df_with_pps.Histo1D(
                ("h_track_time", "PPS track time;Time [ns];Tracks",
                 100, -10, 10), var_name)
            histograms['track_time'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_TIME_UNC:
            h = df_with_pps.Histo1D(
                ("h_track_time_unc", "PPS track time uncertainty;Time uncertainty [ns];Tracks",
                 100, 0, 1), var_name)
            histograms['track_time_unc'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_MULTI_RP_PROTON_IDX:
            h = df_with_pps.Histo1D(
                ("h_multi_rp_idx", "Multi-RP proton index;Index;Tracks",
                 20, -5, 15), var_name)
            histograms['multi_rp_idx'] = h

        elif hist_type == PPSHistogramType.PPS_LOCAL_TRACK_SINGLE_RP_PROTON_IDX:
            h = df_with_pps.Histo1D(
                ("h_single_rp_idx", "Single-RP proton index;Index;Tracks",
                 20, -5, 15), var_name)
            histograms['single_rp_idx'] = h

        elif hist_type == PPSHistogramType.HLT_PPSMaxTracksPerArm1:
            h = df_with_pps.Histo1D(
                ("h_hlt_max_tracks_arm1", "HLT PPS Max Tracks Per Arm1;Pass;Events",
                 2, 0, 2), var_name)
            histograms['hlt_max_tracks_arm1'] = h

        elif hist_type == PPSHistogramType.HLT_PPSMaxTracksPerRP4:
            h = df_with_pps.Histo1D(
                ("h_hlt_max_tracks_rp4", "HLT PPS Max Tracks Per RP4;Pass;Events",
                 2, 0, 2), var_name)
            histograms['hlt_max_tracks_rp4'] = h

        elif hist_type == PPSHistogramType.HLT_PPSRandom:
            h = df_with_pps.Histo1D(
                ("h_hlt_pps_random", "HLT PPS Random;Pass;Events",
                 2, 0, 2), var_name)
            histograms['hlt_pps_random'] = h

        # Proton_multiRP histograms
        elif hist_type == PPSHistogramType.N_PROTON_MULTI_RP:
            h = df_with_pps.Histo1D(
                ("h_n_proton_multi_rp", "Number of multi-RP protons per event;Number of protons;Events",
                 10, 0, 10), var_name)
            histograms['n_proton_multi_rp'] = h

        elif hist_type == PPSHistogramType.PROTON_MULTI_RP_ARM:
            h = df_with_pps.Histo1D(
                ("h_proton_multi_rp_arm", "Multi-RP proton arm;Arm (0=sector45, 1=sector56);Protons",
                 2, 0, 2), var_name)
            histograms['proton_multi_rp_arm'] = h

        elif hist_type == PPSHistogramType.PROTON_MULTI_RP_T:
            h = df_with_pps.Histo1D(
                ("h_proton_multi_rp_t", "Multi-RP proton Mandelstam t;t [GeV^{2}];Protons",
                 100, -2, 0), var_name)
            histograms['proton_multi_rp_t'] = h

        elif hist_type == PPSHistogramType.PROTON_MULTI_RP_THETA_X:
            h = df_with_pps.Histo1D(
                ("h_proton_multi_rp_theta_x", "Multi-RP proton #theta_{x};#theta_{x} [rad];Protons",
                 100, -0.001, 0.001), var_name)
            histograms['proton_multi_rp_theta_x'] = h

        elif hist_type == PPSHistogramType.PROTON_MULTI_RP_THETA_Y:
            h = df_with_pps.Histo1D(
                ("h_proton_multi_rp_theta_y", "Multi-RP proton #theta_{y};#theta_{y} [rad];Protons",
                 100, -0.001, 0.001), var_name)
            histograms['proton_multi_rp_theta_y'] = h

        elif hist_type == PPSHistogramType.PROTON_MULTI_RP_TIME:
            h = df_with_pps.Histo1D(
                ("h_proton_multi_rp_time", "Multi-RP proton time;Time [ns];Protons",
                 100, -10, 10), var_name)
            histograms['proton_multi_rp_time'] = h

        elif hist_type == PPSHistogramType.PROTON_MULTI_RP_TIME_UNC:
            h = df_with_pps.Histo1D(
                ("h_proton_multi_rp_time_unc", "Multi-RP proton time uncertainty;Time uncertainty [ns];Protons",
                 100, 0, 0.1), var_name)
            histograms['proton_multi_rp_time_unc'] = h

        elif hist_type == PPSHistogramType.PROTON_MULTI_RP_XI:
            h = df_with_pps.Histo1D(
                ("h_proton_multi_rp_xi", "Multi-RP proton #xi;#xi;Protons",
                 100, 0, 0.3), var_name)
            histograms['proton_multi_rp_xi'] = h

        # Proton_singleRP histograms
        elif hist_type == PPSHistogramType.N_PROTON_SINGLE_RP:
            h = df_with_pps.Histo1D(
                ("h_n_proton_single_rp", "Number of single-RP protons per event;Number of protons;Events",
                 20, 0, 20), var_name)
            histograms['n_proton_single_rp'] = h

        elif hist_type == PPSHistogramType.PROTON_SINGLE_RP_DEC_RP_ID:
            h = df_with_pps.Histo1D(
                ("h_proton_single_rp_dec_rp_id", "Single-RP proton Roman Pot ID;RP ID;Protons",
                 130, 0, 130), var_name)
            histograms['proton_single_rp_dec_rp_id'] = h

        elif hist_type == PPSHistogramType.PROTON_SINGLE_RP_THETA_Y:
            h = df_with_pps.Histo1D(
                ("h_proton_single_rp_theta_y", "Single-RP proton #theta_{y};#theta_{y} [rad];Protons",
                 100, -0.001, 0.001), var_name)
            histograms['proton_single_rp_theta_y'] = h

        elif hist_type == PPSHistogramType.PROTON_SINGLE_RP_XI:
            h = df_with_pps.Histo1D(
                ("h_proton_single_rp_xi", "Single-RP proton #xi;#xi;Protons",
                 100, 0, 0.3), var_name)
            histograms['proton_single_rp_xi'] = h

    # Create 2D histogram X vs Y if both are requested
    if (PPSHistogramType.PPS_LOCAL_TRACK_X in histogram_types and
        PPSHistogramType.PPS_LOCAL_TRACK_Y in histogram_types):
        print("Creating 2D histogram: X vs Y")
        h_xy = df_with_pps.Histo2D(
            ("h_xy", "PPS track positions;X [mm];Y [mm]",
             60, -20, 20, 60, -20, 20),
            "PPSLocalTrack_x", "PPSLocalTrack_y")
        histograms['xy'] = h_xy

    print(f"Created {len(histograms)} histogram(s)")
    print()

    # Save histograms to ROOT file in data directory
    output_root = os.path.join(data_dir, f"{output_prefix}.root")
    print(f"Saving histograms to: {output_root}")
    output_file = ROOT.TFile(output_root, "RECREATE")

    for name, hist in histograms.items():
        hist.Write()

    output_file.Close()
    print(f"Histograms saved!")
    print()

    print("=== Creating Plots ===")
    ROOT.gROOT.SetBatch(True)

    for name, hist in histograms.items():
        canvas_name = f"c_{name}"
        output_png = os.path.join(data_dir, f"{output_prefix}_{name}.png")

        c = ROOT.TCanvas(canvas_name, name, 800, 600)

        if 'xy' in name or name == 'xy':
            hist.Draw("COLZ")
        else:
            hist.Draw()

        c.SaveAs(output_png)
        print(f"Saved: {output_png}")

    print()
    print("=== Histogram Creation Complete ===")

    return histograms


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 rdata_test.py <path_to_file.root>")
        return

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist!")
        return

    try:
        # Setup ROOT
        ROOT.gROOT.SetBatch(True)
        ROOT.gErrorIgnoreLevel = ROOT.kWarning

        print("ROOT loaded successfully")
        print(f"ROOT version: {ROOT.gROOT.GetVersion()}")
        print()

        # Apply single arm filter
        filters = [filter_single_arm_events]

        # Run analysis
        df_filtered = rdata_analysis(file_path, filters)

        # Generate only X and Y histograms (which will create 2D histogram automatically)
        histogram_types = [
            PPSHistogramType.PPS_LOCAL_TRACK_X,
            PPSHistogramType.PPS_LOCAL_TRACK_Y,
        ]
        print(f"Generating histograms for single arm events...")
        print()

        create_histograms_and_plots(df_filtered, histogram_types, output_prefix="pps_single_arm")


    except Exception as e:
        print(f"Error during analysis: {e}")


if __name__ == "__main__":
    main()