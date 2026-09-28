#!/usr/bin/env python3
"""
TEST 2 -- filter chain: eager vs lazy vs Report() evaluation, and RDataFrame vs Python.

--chain-len sweeps how many filters the query applies. rdf-eager reads a count after every
filter (chain_len + 1 event loops); rdf-lazy and rdf-report need one.
"""

import bench_common as bc


def main():
    parser = bc.build_parser(
        __doc__, impls=["rdf-lazy", "rdf-eager", "rdf-report", "python", "uproot"]
    )
    parser.add_argument(
        "--chain-len",
        type=int,
        default=bc.MAX_CHAIN_LEN,
        choices=range(1, bc.MAX_CHAIN_LEN + 1),
    )
    args = parser.parse_args()

    bench = bc.Bench(args, "chain")
    bench.record["chain_len"] = args.chain_len
    is_rdf = args.impl.startswith("rdf-")
    if not is_rdf:
        bench.record["mode"] = "shortcircuit"

    if is_rdf:
        import impl_rdf

        # Warmed up through the lazy path even for rdf-eager: it compiles the same predicate
        # strings, so cling's cost is paid here for all three and what remains in the eager
        # loop phase is its event loops rather than its compilation.
        with bench.phase("warmup"):
            bc.warmup(args, lambda d: impl_rdf.trigger_chain_lazy(
                impl_rdf.build_chain_lazy(
                    impl_rdf.build_chain_nodes(d, args.chain_len, args.rp_id)
                )
            ))

    with bench.phase("setup"):
        bc.setup_root(args.threads)
        n_events = bc.count_events(args)
        if args.impl != "uproot":
            df = bc.make_dataframe(args)

    if args.impl == "rdf-eager":
        # No jit phase: rdf-eager declares each filter only after reading the previous count,
        # so its graph building is inseparable from its event loops. That interleaving is the
        # behaviour under study, not an artefact -- see impl_rdf.trigger_chain_eager.
        bench.record["graph_interleaved"] = True
        with bench.phase("loop"):
            result = impl_rdf.trigger_chain_eager(df, args.chain_len, args.rp_id)
    elif is_rdf:
        build, trigger = impl_rdf.CHAIN_BUILDERS[args.impl]
        with bench.phase("jit"):
            handles = build(impl_rdf.build_chain_nodes(df, args.chain_len, args.rp_id))
        with bench.phase("loop"):
            result = trigger(handles)
    elif args.impl == "uproot":
        import impl_uproot

        with bench.phase("loop"):
            result = impl_uproot.chain_uproot(args.input, args.chain_len, args.rp_id)
        bench.override_bytes("loop", impl_uproot.bytes_read())
    else:
        import impl_python

        with bench.phase("loop"):
            result = impl_python.chain_python(df, args.chain_len, args.rp_id)

    bench.record["event_loops"] = result["event_loops"]
    bench.finish(
        {"events_passed": result["final"], "intermediate": result["intermediate"]},
        n_events=n_events,
    )


if __name__ == "__main__":
    main()
