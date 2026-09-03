#!/usr/bin/env python3
"""
Build a correctionlib JSON file from a plain-text data table.
Usage
-----
1. Edit the CONFIG block below: pick CORRECTION_TYPE, INPUT_COLUMN, and point
   INPUT_TXT_FILE at your data table.
2. The script writes OUTPUT_JSON_FILE and immediately re-evaluates it with
   correctionlib to print a sanity check. main() returns the written path.
3. In pps_analysis.ipynb, import this module and call main() to get the path,
   then call apply_corrections_hybrid(df_single_arm, path) as usual.

Supported CORRECTION_TYPE values
---------------------------------
- "per_track_direct": INPUT_TXT_FILE holds one offset per line, applied by
  track index (line 0 -> track_idx 0, line 1 -> track_idx 1, ...). Mirrors
  per_track_direct_values.json.
- "range_formula": INPUT_TXT_FILE holds one bin per line as
  "edge_low edge_high offset", e.g. `0 2 1` (adds 1 to x for x in [0, 2)).
  Bins must be contiguous and sorted. Mirrors x_track_range_correction.json.
"""

import json

import correctionlib
import correctionlib.schemav2 as schema

# ============================== CONFIG ==============================
CORRECTION_TYPE = "per_track_direct"
INPUT_COLUMN = "PPSLocalTrack_x"
INPUT_TXT_FILE = "corrections-examples/example_track_offsets.txt"
OUTPUT_JSON_FILE = "corrections-examples/generated_per_track_direct.json"
CORRECTION_NAME = ""  # leave empty to auto-derive from INPUT_COLUMN
DESCRIPTION = ""
DEFAULT_VALUE = 0
# ======================================================================


def read_offsets_txt(path):
    """Reads one numeric offset per line, in track_idx order (0, 1, 2, ...)."""
    values = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            token = line.strip()
            if not token:
                continue
            try:
                values.append(float(token))
            except ValueError:
                raise ValueError(
                    f"{path}:{line_no}: expected a number, got {token!r}"
                )
    if not values:
        raise ValueError(f"{path} contains no offset values")
    return values


def read_range_formula_txt(path):
    """Reads bins as 'edge_low edge_high offset' lines, e.g. '0 2 1'."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            token = line.strip()
            if not token:
                continue
            parts = token.split()
            if len(parts) != 3:
                raise ValueError(
                    f"{path}:{line_no}: expected 'edge_low edge_high offset', got {token!r}"
                )
            edge_low, edge_high, offset = parts
            rows.append((float(edge_low), float(edge_high), float(offset)))

    if not rows:
        raise ValueError(f"{path} contains no bin rows")

    rows.sort(key=lambda row: row[0])
    for (low, high, _), (next_low, _, _) in zip(rows, rows[1:]):
        # correctionlib binning requires each bin's edges to line up with the next
        if high != next_low:
            raise ValueError(
                f"Bins are not contiguous: bin ending at {high} is followed by "
                f"bin starting at {next_low}"
            )
    return rows


def build_per_track_direct(values, name, description, default):
    content = [
        schema.CategoryItem(key=track_idx, value=value)
        for track_idx, value in enumerate(values)
    ]
    data = schema.Category(
        nodetype="category", input="track_idx", content=content, default=default
    )
    return schema.Correction(
        name=name,
        version=1,
        description=description,
        inputs=[
            schema.Variable(
                name="track_idx", type="int", description="Track index in event array"
            )
        ],
        output=schema.Variable(
            name="correction_offset", type="real", description="Correction offset to add"
        ),
        data=data,
    )


def build_range_formula(rows, name, description, default):
    edges = [rows[0][0]] + [high for _, high, _ in rows]
    content = [offset for _, _, offset in rows]
    data = schema.Binning(
        nodetype="binning", input="x", edges=edges, content=content, flow=default
    )
    return schema.Correction(
        name=name,
        version=1,
        description=description,
        inputs=[schema.Variable(name="x", type="real", description="Raw input value")],
        output=schema.Variable(
            name="correction_offset", type="real", description="Correction offset to add"
        ),
        data=data,
    )


def write_correction_set(correction, input_column, output_column, out_path):
    correction_set = schema.CorrectionSet(schema_version=2, corrections=[correction])
    payload = correction_set.model_dump(exclude_none=True)
    payload.pop("$schema", None)
    payload["metadata"] = {"input_column": input_column, "output_column": output_column}

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {out_path}")


def verify(out_path, sample_inputs):
    cset = correctionlib.CorrectionSet.from_file(out_path)
    corr = cset[list(cset.keys())[0]]
    print("Sanity check (re-evaluated from the written JSON):")
    for value in sample_inputs:
        print(f"  evaluate({value!r}) = {corr.evaluate(value)}")


def main():
    correction_name = CORRECTION_NAME or f"{INPUT_COLUMN}_correction"
    output_column = f"{INPUT_COLUMN}_corrected"

    if CORRECTION_TYPE == "per_track_direct":
        values = read_offsets_txt(INPUT_TXT_FILE)
        correction = build_per_track_direct(values, correction_name, DESCRIPTION, DEFAULT_VALUE)
        write_correction_set(correction, INPUT_COLUMN, output_column, OUTPUT_JSON_FILE)
        verify(OUTPUT_JSON_FILE, list(range(len(values))) + [len(values) + 5])
    elif CORRECTION_TYPE == "range_formula":
        rows = read_range_formula_txt(INPUT_TXT_FILE)
        # DEFAULT_VALUE is used as the "flow" (out-of-range) behavior here: pass
        # "clamp"/"error"/"wrap" or a fixed fallback number, e.g. 0.
        correction = build_range_formula(rows, correction_name, DESCRIPTION, DEFAULT_VALUE)
        write_correction_set(correction, INPUT_COLUMN, output_column, OUTPUT_JSON_FILE)
        sample_values = [row[0] for row in rows] + [rows[-1][1] + 100]
        verify(OUTPUT_JSON_FILE, sample_values)
    else:
        raise ValueError(f"Unknown CORRECTION_TYPE: {CORRECTION_TYPE!r}")

    return OUTPUT_JSON_FILE


if __name__ == "__main__":
    main()
