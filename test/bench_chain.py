#!/usr/bin/env python3
"""
TEST 2 -- filter chain: eager vs lazy evaluation, and columnar selectivity.

--chain-len doubles as a sweep over how many branches the query touches, since each step of the
chain introduces exactly one new one. Comparing bytes_loop across chain lengths shows that
RDataFrame reads a later column only for the events that reached it, while the Python path has
to materialise all of them up front.
"""

import bench_common as bc


def main():
    parser = bc.build_parser(
        __doc__, impls=["rdf-lazy", "rdf-eager", "rdf-report", "python"]
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
    bench.record["columns"] = bc.chain_columns(args.chain_len)

    with bench.phase("setup"):
        if args.impl != "python":
            import impl_rdf

            bc.warmup(args, lambda d: impl_rdf.chain_rdf_lazy(d, args.chain_len))
        bc.setup_root(bc.resolve_threads(args))
        df = bc.make_dataframe(args)
        n_events = int(df.Count().GetValue())

    with bench.phase("loop"):
        if args.impl == "python":
            import impl_python

            result = impl_python.chain_python(df, args.chain_len, args.mode, args.rp_id)
        else:
            import impl_rdf

            runner = {
                "rdf-lazy": impl_rdf.chain_rdf_lazy,
                "rdf-eager": impl_rdf.chain_rdf_eager,
                "rdf-report": impl_rdf.chain_rdf_report,
            }[args.impl]
            result = runner(df, args.chain_len)

    bench.record["event_loops"] = result["event_loops"]
    bench.finish(
        {"events_passed": result["final"], "intermediate": result["intermediate"]},
        n_events=n_events,
    )


if __name__ == "__main__":
    main()
