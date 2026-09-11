#!/usr/bin/env python3
"""TEST 1 -- single filter (decRPId == rp_id): RDataFrame vs Python."""

import bench_common as bc


def main():
    parser = bc.build_parser(__doc__, impls=["rdf", "python"])
    args = parser.parse_args()

    bench = bc.Bench(args, "filter")

    with bench.phase("setup"):
        if args.impl == "rdf":
            import impl_rdf

            bc.warmup(args, lambda d: impl_rdf.filter_rdf(d, args.rp_id))
        bc.setup_root(bc.resolve_threads(args))
        df = bc.make_dataframe(args)
        n_events = bc.count_events(args)

    with bench.phase("loop"):
        if args.impl == "rdf":
            import impl_rdf

            passed = impl_rdf.filter_rdf(df, args.rp_id)
        else:
            import impl_python

            passed = impl_python.filter_python(df, args.rp_id, args.mode)

    bench.finish({"events_passed": passed}, n_events=n_events)


if __name__ == "__main__":
    main()
