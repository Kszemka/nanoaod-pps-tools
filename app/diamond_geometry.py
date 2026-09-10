#!/usr/bin/env python3
"""
Diamond box/cyl region geometry: N equal-width sub-regions per arm and pot type, defined as a
hardcoded, rotated center +/- (sensor_dimension / 2) box (matching the tilted band seen in the
reference efficiency plots).

POT_CONFIG's angles are the real alignment values from diamond_alignment_coords_2025.json
(box/cylAngle = 28.5deg for both pot types and both arms, set at base run 391699 and never
changed in the later runs). The centers are still empirical, fit to this sample's observed
PPSLocalTrack_x/y per RP: both pot types sit on the hit band's centroid (with a perpendicular
correction so the band is centered on the hits rather than on the raw x/y centroid), plus a
small x nudge to the left read off the all-pot maps. That file's absolute
boxX/boxY/cylX/cylY (plus its per-run cumulative shift) can't be used instead --
PPSLocalTrack_x/y here are not alignment-corrected. Note the consequence: the hit band in this
sample spans only ~9.5mm (box) / ~10.4mm (cyl) along u, less than the nominal
n_regions * 4.5mm sensor width, so the trailing cyl region stays essentially empty. Once
alignment is applied upstream, the box should be centered around y=0 (beam line); replace the
centers then.

The intended long-term design (once real alignment is available) is exactly
center +/- (sensor_dimension / 2), with `center` hardcoded per run from the real alignment
coords file (see diamond_alignment_coords_2025.json: an absolute
boxX/boxY/cylX/cylY/boxAngle/cylAngle for a base run 391699, then a "shift" per later run where
something changed). Those centers aren't wired in here, and neither reading of the shift table
reproduces this sample (run 396727, so the entries up to 395984 apply): summing the increments
puts the pots at x = 48-69mm, 5-7x past the data, while treating the last entry as already
cumulative still overshoots the observed cloud by +3.3 to +6.9mm to the right. Until the real
per-run RPAlignmentCorrections matrices are available, POT_CONFIG's centers stay empirical.

Both pot types share the same per-channel diamond sensor dimensions (DIAMOND_SIZE_X/Y): "box"
pots (RP22/122) have a row of 3 channels, "cyl" pots (RP16/116) have a row of 4, matching
efficiency.json's "box"/"cyl" array lengths. The per-crystal size (4.5x4.5mm) is the real
hardware spec (CERN-TOTEM-NOTE-2012-002: single diamond pad is 4.5x4.5mm^2), not a data fit --
it's bigger than the empirically-fit hit spread in this sample, giving each region some margin
so outlier/edge hits aren't clipped.
"""

import math

DIAMOND_SIZE_X = 4.5  # mm, real single diamond crystal width (CERN-TOTEM-NOTE-2012-002 spec)
DIAMOND_SIZE_Y = 4.5  # mm, real single diamond crystal height (same spec, square crystal)

# box centers sit on the hit band's centroid (shifted along the perpendicular v so the band is
# centered on the hits, not on the raw x/y centroid) minus 0.4mm in x; cyl centers take the x
# nudge but keep that centroid's y -- moving along the 28.5deg axis would lift the band off the
# densest hits. The x nudges are by eye against the all-pot maps; the alignment file's shift
# table pushes the pots the other way (see module docstring).
# angles are the alignment file's box/cylAngle, not a fit (see module docstring).
POT_CONFIG = {
    "box": {
        "n_regions": 3,
        "centers": {"45": (8.683, 3.794), "56": (8.329, 3.672)},
        "angles_deg": {"45": 28.5, "56": 28.5},
    },
    "cyl": {
        "n_regions": 4,
        "centers": {"45": (10.067, 4.151), "56": (9.657, 3.963)},
        "angles_deg": {"45": 28.5, "56": 28.5},
    },
}


def _to_local(x, y, arm_key, pot_type="box"):
    """Rotates a global (x, y) point into the box's local (u, v) frame."""
    center_x, center_y = POT_CONFIG[pot_type]["centers"][arm_key]
    theta = math.radians(POT_CONFIG[pot_type]["angles_deg"][arm_key])
    dx, dy = x - center_x, y - center_y
    u = dx * math.cos(theta) + dy * math.sin(theta)
    v = -dx * math.sin(theta) + dy * math.cos(theta)
    return u, v


def _to_global(u, v, arm_key, pot_type="box"):
    """Rotates a local (u, v) point back into global (x, y)."""
    center_x, center_y = POT_CONFIG[pot_type]["centers"][arm_key]
    theta = math.radians(POT_CONFIG[pot_type]["angles_deg"][arm_key])
    x = center_x + u * math.cos(theta) - v * math.sin(theta)
    y = center_y + u * math.sin(theta) + v * math.cos(theta)
    return x, y


def build_region_polygons(arm_key, pot_type="box"):
    """Returns the pot type's rotated box sub-region rectangles as [(x, y), ...] (4 corners each)."""
    n_regions = POT_CONFIG[pot_type]["n_regions"]
    x_left = -n_regions * DIAMOND_SIZE_X / 2
    v_min, v_max = -DIAMOND_SIZE_Y / 2, DIAMOND_SIZE_Y / 2
    polygons = []
    for i in range(n_regions):
        u_low = x_left + i * DIAMOND_SIZE_X
        u_high = u_low + DIAMOND_SIZE_X
        corners_local = [(u_low, v_min), (u_high, v_min), (u_high, v_max), (u_low, v_max)]
        polygons.append([_to_global(u, v, arm_key, pot_type) for u, v in corners_local])
    return polygons


def assign_region(x, y, arm_key, pot_type="box"):
    """Returns the index (0..n_regions-1) of the sub-region containing (x, y), or -1 if outside."""
    n_regions = POT_CONFIG[pot_type]["n_regions"]
    u, v = _to_local(x, y, arm_key, pot_type)
    if not (-DIAMOND_SIZE_Y / 2 <= v <= DIAMOND_SIZE_Y / 2):
        return -1
    x_left = -n_regions * DIAMOND_SIZE_X / 2
    for i in range(n_regions):
        u_low = x_left + i * DIAMOND_SIZE_X
        u_high = u_low + DIAMOND_SIZE_X
        if u_low <= u <= u_high:
            return i
    return -1


def get_plot_range(arm_key, margin=6.0, pot_type="box"):
    """Returns (x_min, x_max, y_min, y_max) bounding the box +/- margin, for consistent zoomed plots."""
    corners = [corner for polygon in build_region_polygons(arm_key, pot_type) for corner in polygon]
    xs = [x for x, _ in corners]
    ys = [y for _, y in corners]
    return min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin


def get_cpp_source(arm_key, pot_type="box", func_name="assignRegion"):
    """
    Returns C++ source for `int func_name(double x, double y)`, a line-by-line transcription of
    assign_region() with POT_CONFIG's constants baked in as literals.

    Generated rather than hand-written so POT_CONFIG stays the single source of truth for the
    geometry -- a hand-maintained C++ copy would silently drift from the Python one.
    """
    n_regions = POT_CONFIG[pot_type]["n_regions"]
    center_x, center_y = POT_CONFIG[pot_type]["centers"][arm_key]
    theta = math.radians(POT_CONFIG[pot_type]["angles_deg"][arm_key])
    x_left = -n_regions * DIAMOND_SIZE_X / 2

    return f"""
int {func_name}(double x, double y) {{
    constexpr double kCenterX = {center_x!r};
    constexpr double kCenterY = {center_y!r};
    constexpr double kCosTheta = {math.cos(theta)!r};
    constexpr double kSinTheta = {math.sin(theta)!r};
    constexpr double kHalfSizeY = {DIAMOND_SIZE_Y / 2!r};
    constexpr double kSizeX = {DIAMOND_SIZE_X!r};
    constexpr double kULeft = {x_left!r};
    constexpr int kNRegions = {n_regions};

    const double dx = x - kCenterX;
    const double dy = y - kCenterY;
    const double u = dx * kCosTheta + dy * kSinTheta;
    const double v = -dx * kSinTheta + dy * kCosTheta;

    if (!(-kHalfSizeY <= v && v <= kHalfSizeY)) return -1;

    for (int i = 0; i < kNRegions; ++i) {{
        const double uLow = kULeft + i * kSizeX;
        const double uHigh = uLow + kSizeX;
        if (uLow <= u && u <= uHigh) return i;
    }}
    return -1;
}}
"""

