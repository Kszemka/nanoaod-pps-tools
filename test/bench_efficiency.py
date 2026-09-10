#!/usr/bin/env python3
"""
TEST 3 -- attach a per-track efficiency to every record.

Three measurement points:
  jit           - correctionlib evaluated once per region at setup, values baked into a
                  JIT-compiled C++ kernel; one Define(), no Python in the loop
  correctionlib - corr.evaluate() called per track through the Python API
  python        - no correctionlib and no JSON in the loop, geometry evaluated directly

The rp_id filter and the correction JSON build belong to setup: the filter's own cost is
already measured by TEST 1, so timing it again here would make the two tests overlap.
"""

import bench_common as bc


def main():
    parser = bc.build_parser(__doc__, impls=["jit", "correctionlib", "python"])
    args = parser.parse_args()

    bench = bc.Bench(args, "efficiency")

    with bench.phase("setup"):
        from app.analyze_proton_events import filter_detector_specific_events

        correction_json = bc.build_efficiency_json(args.arm, args.pot_type)
        if args.impl == "jit":
            import impl_rdf

            bc.warmup(
                args,
                lambda d: impl_rdf.efficiency_rdf_run(
                    impl_rdf.efficiency_rdf_jit(
                        filter_detector_specific_events(d, args.rp_id),
                        args.rp_id,
                        args.arm,
                        correction_json,
                        args.pot_type,
                    )
                ),
            )
        bc.setup_root(bc.resolve_threads(args))
        df = bc.make_dataframe(args)
        df = filter_detector_specific_events(df, args.rp_id)
        n_events = int(df.Count().GetValue())
        if args.impl == "jit":
            df = impl_rdf.efficiency_rdf_jit(
                df, args.rp_id, args.arm, correction_json, args.pot_type
            )

    with bench.phase("loop"):
        if args.impl == "jit":
            result = impl_rdf.efficiency_rdf_run(df)
        elif args.impl == "correctionlib":
            import impl_python

            result = impl_python.efficiency_correctionlib(
                df, args.rp_id, args.arm, args.pot_type, correction_json
            )
        else:
            import impl_python

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
