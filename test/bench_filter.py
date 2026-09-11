#!/usr/bin/env python3
"""TEST 1 -- single filter (decRPId == rp_id): RDataFrame vs Python vs uproot."""

import bench_common as bc


def main():
    parser = bc.build_parser(__doc__, impls=["rdf", "python", "uproot"])
    args = parser.parse_args()

    bench = bc.Bench(args, "filter")
    bench.note_columns([bc.CHAIN_COLUMNS["double_arm"]])

    if args.impl == "rdf":
        import impl_rdf

        with bench.phase("warmup"):
            bc.warmup(args, lambda d: impl_rdf.trigger_filter(
                impl_rdf.build_filter(d, args.rp_id, args.filter_style)
            ))

    with bench.phase("setup"):
        bc.apply_tree_cache(args)
        bc.setup_root(bc.resolve_threads(args))
        n_events = bc.count_events(args)
        if args.impl != "uproot":
            df = bc.make_dataframe(args)

    if args.impl == "rdf":
        with bench.phase("jit"):
            handle = impl_rdf.build_filter(df, args.rp_id, args.filter_style)
        with bench.phase("loop"):
            passed = impl_rdf.trigger_filter(handle)
    elif args.impl == "uproot":
        import impl_uproot

        with bench.phase("loop"):
            passed = impl_uproot.filter_uproot(args.input, args.rp_id)
        bench.override_bytes("loop", impl_uproot.bytes_read())
    else:
        import impl_python

        with bench.phase("loop"):
            passed = impl_python.filter_python(df, args.rp_id, args.mode)

    bench.finish({"events_passed": passed}, n_events=n_events)


if __name__ == "__main__":
    main()
