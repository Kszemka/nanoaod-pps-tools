#!/usr/bin/env python3
"""
TEST 3 -- attach a per-track efficiency to every record.

Four measurement points:
  jit           - correctionlib evaluated once per region at setup, values baked into a
                  JIT-compiled C++ kernel; one Define(), no Python in the loop
  correctionlib - corr.evaluate() called per track through the Python API
  python        - no correctionlib and no JSON in the loop, geometry evaluated directly
  uproot        - the same geometry on awkward arrays read outside ROOT

The rp_id filter and the correction JSON build belong to setup: the filter's own cost is
already measured by TEST 1, so timing it again here would make the two tests overlap.
"""

import bench_common as bc


def main():
    parser = bc.build_parser(__doc__, impls=["jit", "correctionlib", "python", "uproot"])
    args = parser.parse_args()

    bench = bc.Bench(args, "efficiency")
    bench.note_columns(["PPSLocalTrack_x", "PPSLocalTrack_y", "PPSLocalTrack_decRPId"])

    with bench.phase("setup"):
        from app.analyze_proton_events import filter_detector_specific_events

        correction_json = bc.build_efficiency_json(args.arm, args.pot_type)
        bc.apply_tree_cache(args)

    if args.impl == "jit":
        import impl_rdf

        with bench.phase("warmup"):
            bc.warmup(args, lambda d: impl_rdf.trigger_efficiency(
                impl_rdf.build_efficiency(
                    impl_rdf.efficiency_rdf_jit(
                        filter_detector_specific_events(d, args.rp_id),
                        args.rp_id,
                        args.arm,
                        correction_json,
                        args.pot_type,
                    )
                )
            ))

    # Second half of setup: EnableImplicitMT has to come after the warmup, because Range() --
    # which is how the warmup limits itself to one entry -- is unsupported under implicit MT.
    with bench.phase("setup"):
        bc.setup_root(bc.resolve_threads(args))
        n_events = bc.count_events(args)
        if args.impl != "uproot":
            df = filter_detector_specific_events(bc.make_dataframe(args), args.rp_id)

    if args.impl == "jit":
        with bench.phase("jit"):
            handles = impl_rdf.build_efficiency(
                impl_rdf.efficiency_rdf_jit(
                    df, args.rp_id, args.arm, correction_json, args.pot_type
                )
            )
        with bench.phase("loop"):
            result = impl_rdf.trigger_efficiency(handles)
    elif args.impl == "correctionlib":
        import impl_python

        with bench.phase("loop"):
            result = impl_python.efficiency_correctionlib(
                df, args.rp_id, args.arm, args.pot_type, correction_json
            )
    elif args.impl == "uproot":
        import impl_uproot

        with bench.phase("loop"):
            result = impl_uproot.efficiency_uproot(
                args.input, args.rp_id, args.arm, args.pot_type, correction_json
            )
        bench.override_bytes("loop", impl_uproot.bytes_read())
    else:
        import impl_python

        with bench.phase("loop"):
            result = impl_python.efficiency_python(
                df, args.rp_id, args.arm, args.pot_type, correction_json, args.mode
            )

    bench.finish(
        {"eff_sum": result["eff_sum"], "eff_hits": result["eff_hits"]},
        n_events=n_events,
        n_tracks=result["n_tracks"],
    )


if __name__ == "__main__":
    main()
