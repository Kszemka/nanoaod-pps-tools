#!/usr/bin/env python3
"""
TEST 4 -- does row selectivity ever reduce I/O?

TESTING.md explains the flat bytes-read curve of TEST 2 by arguing that a filter saves
predicate evaluations but not reads, because the surviving events are scattered across every
basket of the branches read later on. That is a claim about where the survivors sit in entry
order, and it predicts something specific: a selection that is *contiguous* in entry order
should read less.

Both implementations here keep a comparable fraction of events and end in the same reduction
over the same branch (Proton_singleRP_xi). The only difference is the selection:

  scattered  - Any(PPSLocalTrack_decRPId == rp_id), survivors spread over the whole file
  contiguous - rdfentry_ < N, survivors forming a prefix

The result to report is bytes_loop and read_amplification for the two, side by side.
"""

import bench_common as bc


def main():
    parser = bc.build_parser(__doc__, impls=["scattered", "contiguous"])
    parser.add_argument(
        "--keep-fraction",
        type=float,
        default=0.173,
        help="fraction of entries the contiguous selection keeps. The default matches the "
             "scattered selection's measured pass rate (59946 of 346825 events, 17.3%%), so "
             "the two read the same amount of surviving data and differ only in where it sits",
    )
    args = parser.parse_args()

    import impl_rdf

    bench = bc.Bench(args, "selectivity")
    bench.record["keep_fraction"] = args.keep_fraction
    # The contiguous selection needs no data column to decide with, so its denominator is the
    # reduction branch alone. Charging it for decRPId as well would understate its amplification.
    selection_columns = ["PPSLocalTrack_decRPId"] if args.impl == "scattered" else []
    bench.note_columns(selection_columns + [bc.CHAIN_COLUMNS["xi"]])

    with bench.phase("warmup"):
        bc.warmup(args, lambda d: impl_rdf.trigger_selective_read(
            impl_rdf.build_selective_read(d, args.impl, 1, args.rp_id, args.keep_fraction)
        ))

    with bench.phase("setup"):
        bc.apply_tree_cache(args)
        bc.setup_root(bc.resolve_threads(args))
        n_events = bc.count_events(args)
        df = bc.make_dataframe(args)

    with bench.phase("jit"):
        handles = impl_rdf.build_selective_read(
            df, args.impl, n_events, args.rp_id, args.keep_fraction
        )

    with bench.phase("loop"):
        result = impl_rdf.trigger_selective_read(handles)

    bench.finish(result, n_events=n_events)


if __name__ == "__main__":
    main()
