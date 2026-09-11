#!/usr/bin/env python3
"""
TEST 2 -- filter chain: eager vs lazy evaluation, and columnar selectivity.

--chain-len doubles as a sweep over how many branches the query touches, since each step of the
chain introduces exactly one new one. Comparing bytes_loop across chain lengths against
columns_zip_bytes shows how much of what RDataFrame reads the query actually asked for.
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

    if args.chain_order != "notebook" and args.chain_len != bc.MAX_CHAIN_LEN:
        parser.error(
            "--chain-order only makes sense at full length: a truncated chain in a different "
            "order applies a different set of filters, so the counts are not comparable"
        )

    bench = bc.Bench(args, "chain")
    bench.record["chain_len"] = args.chain_len
    bench.note_columns(bc.chain_columns(args.chain_len, args.chain_order))
    is_rdf = args.impl.startswith("rdf-")

    if is_rdf:
        import impl_rdf

        # Warmed up through the lazy path even for rdf-eager: it compiles the same predicate
        # strings, so cling's cost is paid here for all three and what remains in the eager
        # loop phase is its event loops rather than its compilation.
        with bench.phase("warmup"):
            bc.warmup(args, lambda d: impl_rdf.trigger_chain_lazy(
                impl_rdf.build_chain_lazy(
                    impl_rdf.build_chain_nodes(
                        d, args.chain_len, args.chain_order, args.filter_style, args.rp_id
                    )
                )
            ))

    with bench.phase("setup"):
        bc.apply_tree_cache(args)
        bc.setup_root(bc.resolve_threads(args))
        n_events = bc.count_events(args)
        if args.impl != "uproot":
            df = bc.make_dataframe(args)

    if args.impl == "rdf-eager":
        # No jit phase: rdf-eager declares each filter only after reading the previous count,
        # so its graph building is inseparable from its event loops. That interleaving is the
        # behaviour under study, not an artefact -- see impl_rdf.trigger_chain_eager.
        bench.record["graph_interleaved"] = True
        with bench.phase("loop"):
            result = impl_rdf.trigger_chain_eager(
                df, args.chain_len, args.chain_order, args.filter_style, args.rp_id
            )
    elif is_rdf:
        build, trigger = impl_rdf.CHAIN_BUILDERS[args.impl]
        with bench.phase("jit"):
            handles = build(
                impl_rdf.build_chain_nodes(
                    df, args.chain_len, args.chain_order, args.filter_style, args.rp_id
                )
            )
        with bench.phase("loop"):
            result = trigger(handles)
    elif args.impl == "uproot":
        import impl_uproot

        with bench.phase("loop"):
            result = impl_uproot.chain_uproot(
                args.input, args.chain_len, args.mode, args.rp_id, args.chain_order
            )
        bench.override_bytes("loop", impl_uproot.bytes_read())
    else:
        import impl_python

        with bench.phase("loop"):
            result = impl_python.chain_python(
                df, args.chain_len, args.mode, args.rp_id, args.chain_order
            )

    bench.record["event_loops"] = result["event_loops"]
    bench.finish(
        {"events_passed": result["final"], "intermediate": result["intermediate"]},
        n_events=n_events,
    )


if __name__ == "__main__":
    main()
