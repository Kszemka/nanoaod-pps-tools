# NanoAOD PPS Analysis Tools

Python tools for analyzing CMS Precision Proton Spectrometer (PPS) data in NanoAOD format using ROOT RDataFrame.

## Overview

This toolkit provides efficient analysis of PPS detector data from CMS Run 3, including:
- **Event filtering** (single arm, double arm, specific detectors, xi ranges)
- **Histogram generation** for all PPS and proton reconstruction variables
- **2D correlation plots** (X vs Y track positions)
- **Statistical analysis** of proton tracks and reconstruction

## Requirements

- ROOT 6.34+ with PyROOT support
- Python 3.11+ (compatible with ROOT installation)
- NanoAOD ROOT files with PPS data

## Installation

```bash
# Ensure ROOT is properly configured
source /path/to/root/bin/thisroot.sh

# Or use system Python compatible with ROOT
/opt/homebrew/bin/python3  # macOS Homebrew example
```

## Scripts

### 1. `analyze_root.py` - Data Inspection Tool

Analyzes ROOT NanoAOD files to discover and display PPS variables.

**Features:**
- Automatically finds all PPS and proton-related variables (regex: `*PPS*` or `*proton*`)
- Displays variable types and data for first 5 events
- Supports PPSLocalTrack, Proton_multiRP, and Proton_singleRP collections
- Saves detailed analysis to text file

**Usage:**
```bash
python3 analyze_root.py <input_file.root>
```

**Example:**
```bash
python3 analyze_root.py ../test.root
```

**Output:**
- Console: Summary statistics and variable list
- File: `result_with_protons.txt` with detailed analysis

**Discovered Variables (25 total):**
- **HLT Triggers** (4): DiPFJetAve180_PPSMatch, PPSMaxTracksPerArm1, PPSMaxTracksPerRP4, PPSRandom
- **PPSLocalTrack** (9): x, y, decRPId, rpType, multiRPProtonIdx, singleRPProtonIdx, time, timeUnc, nPPSLocalTrack
- **Proton_multiRP** (8): arm, t, thetaX, thetaY, time, timeUnc, xi, nProton_multiRP
- **Proton_singleRP** (4): decRPId, thetaY, xi, nProton_singleRP

---

### 2. `analyze_proton_events.py` - RDataFrame Analysis Engine

High-performance analysis tool using ROOT RDataFrame for filtering events and generating histograms.

**Features:**
- **Fast columnar processing** with RDataFrame
- **Event filters**: single arm, double arm, detector-specific (RP 3, 23, 103, 123)
- **Flexible histogram generation** for any PPS variable
- **Automatic 2D histograms** when both X and Y are selected
- **Organized output** - all results saved to `../data/` directory

**Usage:**
```bash
python3 analyze_proton_events.py <input_file.root>
```

**Example:**
```bash
python3 analyze_proton_events.py ../test.root
```

**Output Structure:**
```
../data/
├── pps_single_arm.root          # ROOT file with histograms
├── pps_single_arm_track_x.png   # X position histogram
├── pps_single_arm_track_y.png   # Y position histogram
└── pps_single_arm_xy.png        # 2D correlation plot
```

---

## Available Filters

### Event Selection Functions

```python
from analyze_proton_events import *

# Single arm events (only left OR right, not both)
filter_single_arm_events(df)

# Double arm events (both left AND right)
filter_double_arm_events(df)

# Specific Roman Pot detector
filter_detector_specific_events(df, rp_id=23)  # RP IDs: 3, 23, 103, 123

# Detector type (pixel or diamond)
filter_detector_type(df, 'pixel')    # Silicon pixel detectors: RP 3, 23, 103, 123
filter_detector_type(df, 'diamond')  # Diamond timing detectors: RP 16, 22, 116, 122

# Proton xi range
filter_xi_ranged_events(df, xi_min=0.05, xi_max=0.2)
```

### Filter Combinations

Apply multiple filters sequentially:
```python
filters = [
    filter_double_arm_events,
    lambda df: filter_detector_type(df, 'pixel')
]
df_filtered = rdata_analysis("test.root", filters)
```

---

## Available Histogram Types

All 25 PPS variables are available as `PPSHistogramType` enum values:

### Track Variables
- `N_PPS_LOCAL_TRACK` - Number of tracks per event
- `PPS_LOCAL_TRACK_X` - X position [mm]
- `PPS_LOCAL_TRACK_Y` - Y position [mm]
- `PPS_LOCAL_TRACK_DEC_RP_ID` - Decimal Roman Pot ID
- `PPS_LOCAL_TRACK_RP_TYPE` - RP detector type
- `PPS_LOCAL_TRACK_TIME` - Time [ns]
- `PPS_LOCAL_TRACK_TIME_UNC` - Time uncertainty [ns]
- `PPS_LOCAL_TRACK_MULTI_RP_PROTON_IDX` - Multi-RP proton index
- `PPS_LOCAL_TRACK_SINGLE_RP_PROTON_IDX` - Single-RP proton index

### Multi-RP Proton Variables
- `N_PROTON_MULTI_RP` - Number of multi-RP reconstructed protons
- `PROTON_MULTI_RP_ARM` - Arm (0=sector45, 1=sector56)
- `PROTON_MULTI_RP_T` - Mandelstam t [GeV²]
- `PROTON_MULTI_RP_THETA_X` - θ_x angle [rad]
- `PROTON_MULTI_RP_THETA_Y` - θ_y angle [rad]
- `PROTON_MULTI_RP_TIME` - Time [ns]
- `PROTON_MULTI_RP_TIME_UNC` - Time uncertainty [ns]
- `PROTON_MULTI_RP_XI` - Fractional momentum loss ξ

### Single-RP Proton Variables
- `N_PROTON_SINGLE_RP` - Number of single-RP protons
- `PROTON_SINGLE_RP_DEC_RP_ID` - Decimal RP ID
- `PROTON_SINGLE_RP_THETA_Y` - θ_y angle [rad]
- `PROTON_SINGLE_RP_XI` - Fractional momentum loss ξ

### HLT Triggers
- `HLT_PPSMaxTracksPerArm1` - PPS trigger: max tracks per arm = 1
- `HLT_PPSMaxTracksPerRP4` - PPS trigger: max tracks per RP = 4
- `HLT_PPSRandom` - PPS random trigger
- `HLT_DiPFJetAve180_PPSMatch_Xi0p3_QuadJet_Max2ProtPerRP` - Combined jet+PPS trigger

---

## Customization Examples

### Example 1: Custom Filter + Specific Histograms

Edit the `main()` function in `analyze_proton_events.py`:

```python
def main():
    # ... setup code ...
    
    # Custom analysis: double arm events only
    filters = [filter_double_arm_events]
    df_filtered = rdata_analysis(file_path, filters)
    
    # Generate only proton xi histograms
    histogram_types = [
        PPSHistogramType.PROTON_MULTI_RP_XI,
        PPSHistogramType.PROTON_SINGLE_RP_XI,
    ]
    
    create_histograms_and_plots(
        df_filtered, 
        histogram_types, 
        output_prefix="pps_double_arm_xi"
    )
```

### Example 2: All Variables Analysis

```python
def main():
    # ... setup code ...
    
    # No filters - all PPS events
    df_filtered = rdata_analysis(file_path)
    
    # Generate ALL 25 histograms
    all_types = list(PPSHistogramType)
    
    create_histograms_and_plots(
        df_filtered, 
        all_types, 
        output_prefix="pps_complete_analysis"
    )
```

### Example 3: Specific Roman Pot Analysis

```python
def main():
    # ... setup code ...
    
    # Only events with RP 23 (sector 45, far station)
    filters = [lambda df: filter_detector_specific_events(df, 23)]
    df_filtered = rdata_analysis(file_path, filters)
    
    # Track position histograms + 2D plot
    histogram_types = [
        PPSHistogramType.PPS_LOCAL_TRACK_X,
        PPSHistogramType.PPS_LOCAL_TRACK_Y,
        PPSHistogramType.PPS_LOCAL_TRACK_DEC_RP_ID,
    ]
    
    create_histograms_and_plots(
        df_filtered, 
        histogram_types, 
        output_prefix="pps_rp23_analysis"
    )
```

### Example 4: Detector Type Filter (Pixel vs Diamond)

```python
def main():
    # ... setup code ...
    
    # Analyze only pixel detector events
    filters = [lambda df: filter_detector_type(df, 'pixel')]
    df_filtered = rdata_analysis(file_path, filters)
    
    # Generate position and RP ID histograms
    histogram_types = [
        PPSHistogramType.PPS_LOCAL_TRACK_X,
        PPSHistogramType.PPS_LOCAL_TRACK_Y,
        PPSHistogramType.PPS_LOCAL_TRACK_DEC_RP_ID,
    ]
    
    create_histograms_and_plots(
        df_filtered, 
        histogram_types, 
        output_prefix="pps_pixel_detectors"
    )
```

### Example 5: Xi Range Selection

```python
def main():
    # ... setup code ...
    
    # Select events with protons in specific xi range
    filters = [
        filter_double_arm_events,
        lambda df: filter_xi_ranged_events(df, 0.05, 0.2)
    ]
    df_filtered = rdata_analysis(file_path, filters)
    
    # Generate xi histograms
    histogram_types = [
        PPSHistogramType.PROTON_MULTI_RP_XI,
        PPSHistogramType.PROTON_SINGLE_RP_XI,
    ]
    
    create_histograms_and_plots(
        df_filtered, 
        histogram_types, 
        output_prefix="pps_xi_range_0.05_0.2"
    )
```

---

## Detector Type Mapping

The `filter_detector_type()` function provides convenient string-based detector selection:

### Pixel Detectors (Silicon tracking)
Use `filter_detector_type(df, 'pixel')` to select:
- **RP 3** - Sector 45, near horizontal
- **RP 23** - Sector 45, far horizontal
- **RP 103** - Sector 56, near horizontal
- **RP 123** - Sector 56, far horizontal

### Diamond Detectors (Timing)
Use `filter_detector_type(df, 'diamond')` to select:
- **RP 16** - Sector 45, near timing
- **RP 22** - Sector 45, far timing
- **RP 116** - Sector 56, near timing
- **RP 122** - Sector 56, far timing

**Usage Example:**
```python
# Analyze only pixel detector tracks
df_pixel = filter_detector_type(df, 'pixel')

# Analyze only diamond timing detector tracks
df_diamond = filter_detector_type(df, 'diamond')
```

---

## Roman Pot Detector IDs

### Sector 45 (Positive side, arm 0)
- **RP 3** - Near horizontal pot
- **RP 23** - Far horizontal pot
- **RP 16, 22** - Timing detectors

### Sector 56 (Negative side, arm 1)
- **RP 103** - Near horizontal pot
- **RP 123** - Far horizontal pot
- **RP 116, 122** - Timing detectors

---

## Performance Notes

- **RDataFrame** enables lazy evaluation and multi-threading
- Processing ~350k events with PPS data: **< 1 minute**
- Histogram generation: **parallel execution** for multiple histograms
- Output files automatically saved to `../data/` directory

---

## Example Analysis Results

### Test File Statistics (test.root)
```
Total events:              346,825
Events with PPS data:      311,565 (89.8%)
Single arm events:          34,828 (11.2% of PPS events)
Double arm events:         276,737 (88.8% of PPS events)
```

### Typical Output
```
data/
├── pps_single_arm.root (3 histograms)
├── pps_single_arm_track_x.png
├── pps_single_arm_track_y.png
└── pps_single_arm_xy.png (2D correlation)
```

---

## Troubleshooting

### Issue: `ImportError: libcppyy.so` or Python version mismatch

**Solution:** Use Python version compatible with your ROOT installation:
```bash
# Check ROOT's Python version
root-config --python-version

# Use matching system Python (not venv)
/opt/homebrew/bin/python3 analyze_proton_events.py test.root
```

### Issue: Variables not found

**Solution:** Run inspection first:
```bash
python3 analyze_root.py test.root
```
Check output to verify variable names match enum values.

### Issue: Empty histograms

**Solution:** Check event counts after filtering. Some filters may be too restrictive:
```python
# Add diagnostic output
print(f"Events after filter: {df_filtered.Count().GetValue()}")
```

---

## Related Documentation

- [ROOT RDataFrame Documentation](https://root.cern/doc/master/classROOT_1_1RDataFrame.html)
- [CMS NanoAOD Format](https://cms-nanoaod-integration.web.cern.ch/)
- [PPS Detector TWiki](https://twiki.cern.ch/twiki/bin/view/CMS/TaggedProtonsRun3)

---

## Author
Kszemka

Project: CMS PPS Run 3 NanoAOD Validation  
Purpose: Efficiency analysis of unified data processing model
