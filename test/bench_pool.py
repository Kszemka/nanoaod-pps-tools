#!/usr/bin/env python3
"""
The filter chain on a whole node without ImplicitMT: uproot and the AsNumpy path, each in a pool
of --threads worker processes, one range of --chunk-events entries of a file per task.

This is how either is run on a large dataset in practice. Neither parallelises an event loop
by itself, and both hold the columns they read in memory, so in one process the 1.2 TB Run 3
set would need several times the node's RAM. Per task, a worker holds one chunk's columns at a
time: AsNumpy keeps ~1.5 kB per event over 4 jagged columns, so whole Run 3 files (up to
~1.35 M events) on 192 workers would need more than the node's 384 GB. --chunk-events 0 gives
one task per file.

  uproot-pool  every worker runs impl_uproot.chain_uproot on its range; no ROOT in the workers
  python-pool  every worker opens an RDataFrame on its range and runs impl_python.chain_python

    bench_pool.py --input core.txt --impl uproot-pool --threads 192 --chain long

Tasks go out largest first, so the last ones are short and the workers finish together. The
record is bench_chain's (test chain/chain11, the same checksums), with:
  setup      starting the workers and importing their libraries, up to a barrier, then the
             workers reading every file's entries from its metadata (to split the files)
  loop       every task through the chain
  chunk_events, tasks   the chunk size and the number of tasks
  cpu_loop   the parent's CPU plus every worker's CPU inside its tasks
  bytes_loop, io_rchar_loop, io_read_bytes_loop   summed over the workers
  peak_rss_tree_kb   the highest sum of the parent's and the workers' RSS in the trace

Top-level imports stay free of ROOT: under the spawn start method every worker imports this
file again, as __mp_main__.
"""

import os
import sys
import time

IMPLS = ("uproot-pool", "python-pool")
# Starting 192 interpreters and importing ROOT in each off Lustre takes tens of seconds; a
# worker that has not reached the barrier after this long is not coming.
STARTUP_TIMEOUT_S = 900


def _proc_io():
    try:
        with open("/proc/self/io") as f:
            fields = dict(line.split(":", 1) for line in f if ":" in line)
    except OSError:
        return {"rchar": 0, "read_bytes": 0}
    return {"rchar": int(fields["rchar"]), "read_bytes": int(fields["read_bytes"])}


def _init_worker(impl, barrier):
    """Imports the libraries a task needs, so that their cost falls in setup."""
    if impl == "uproot-pool":
        import impl_uproot  # noqa: F401
    else:
        import impl_python  # noqa: F401
    barrier.wait(STARTUP_TIMEOUT_S)


def _ready():
    return os.getpid()


def _entries(impl, path):
    """Entries of one file, from its metadata, with the worker's own library."""
    if impl == "uproot-pool":
        import uproot

        with uproot.open(path) as f:
            return int(f["Events"].num_entries)
    import ROOT

    f = ROOT.TFile.Open(path)
    try:
        return int(f.Get("Events").GetEntries())
    finally:
        f.Close()


def _range_frame(ROOT, path, start, stop):
    """
    An RDataFrame over entries [start, stop) of one file that does not step through the entries
    before start, as Range() would. Range() is the fallback where RDatasetSpec does not take
    the range.
    """
    experimental = ROOT.RDF.Experimental
    try:
        spec = experimental.RDatasetSpec()
        spec.AddSample(experimental.RSample("chunk", "Events", path))
        spec.WithGlobalRange(experimental.RDatasetSpec.REntryRange(start, stop))
        return ROOT.RDataFrame(spec)
    except (AttributeError, TypeError):
        return ROOT.RDataFrame("Events", path).Range(start, stop)


def _run_task(impl, path, start, stop, chain_len, rp_id, chain, period):
    """
    Entries [start, stop) of one file through the chain (stop None: the whole file):
    (per-step counts, bytes read, kernel I/O, CPU seconds).
    """
    io_before, cpu_before = _proc_io(), time.process_time()
    if impl == "uproot-pool":
        import impl_uproot

        bytes_before = impl_uproot.bytes_read()
        result = impl_uproot.chain_uproot(path, chain_len, rp_id, chain, period,
                                          entry_start=start, entry_stop=stop)
        read = impl_uproot.bytes_read() - bytes_before
    else:
        import ROOT
        import impl_python

        bytes_before = ROOT.TFile.GetFileBytesRead()
        df = (ROOT.RDataFrame("Events", path) if stop is None
              else _range_frame(ROOT, path, start, stop))
        result = impl_python.chain_python(df, chain_len, rp_id, chain, period)
        read = ROOT.TFile.GetFileBytesRead() - bytes_before
    io_after = _proc_io()
    return (result["intermediate"], int(read),
            {k: io_after[k] - io_before[k] for k in io_after},
            time.process_time() - cpu_before)


def make_tasks(files, entries, chunk_events):
    """
    (path, start, stop) per task, largest first; one task per file, with stop None, when
    chunk_events is 0.
    """
    if chunk_events <= 0:
        return [(path, 0, None) for path in sorted(files, key=os.path.getsize, reverse=True)]
    tasks = [(path, start, min(start + chunk_events, n))
             for path, n in zip(files, entries) for start in range(0, n, chunk_events)]
    return sorted(tasks, key=lambda t: t[2] - t[1], reverse=True)


def trace_peak_kb(path):
    """Highest rss_kb in an RSS trace, or None without one."""
    if not path or not os.path.exists(path):
        return None
    peak = None
    with open(path) as f:
        next(f, None)
        for line in f:
            try:
                rss = int(line.split(",")[1])
            except (IndexError, ValueError):
                continue
            peak = rss if peak is None else max(peak, rss)
    return peak


def main():
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor, as_completed

    import bench_common as bc

    parser = bc.build_parser(__doc__, impls=list(IMPLS))
    parser.add_argument("--chain", default="base", choices=sorted(bc.CHAINS))
    parser.add_argument("--chain-len", type=int, default=None,
                        help="number of filters; default: the whole chain")
    parser.add_argument("--chunk-events", type=int, default=250000,
                        help="entries per task; 0: one task per file")
    args = parser.parse_args()
    steps = bc.CHAINS[args.chain]
    if args.chain_len is None:
        args.chain_len = len(steps)
    if not 1 <= args.chain_len <= len(steps):
        parser.error(f"--chain-len must be 1..{len(steps)} for --chain {args.chain}")
    if args.threads < 1:
        parser.error("--threads is the number of worker processes and must be at least 1")

    bench = bc.Bench(args, "chain" if args.chain == "base" else "chain11")
    bench.record.update(chain=args.chain, chain_len=args.chain_len, mode="shortcircuit",
                        workers=args.threads, event_loops=1, chunk_events=args.chunk_events)
    files = bc.input_files(args.input)
    context = multiprocessing.get_context("spawn")

    with bench.phase("setup"):
        barrier = context.Barrier(args.threads + 1)
        pool = ProcessPoolExecutor(max_workers=args.threads, mp_context=context,
                                   initializer=_init_worker, initargs=(args.impl, barrier))
        # With spawn the executor starts a worker per submitted task until it has them all;
        # the barrier then holds until every one of them has imported its libraries.
        ready = [pool.submit(_ready) for _ in range(args.threads)]
        barrier.wait(STARTUP_TIMEOUT_S)
        pids = {future.result() for future in ready}
        # Splitting files into ranges needs their entries: the pool reads them from the files
        # itself, in parallel, as it would with nothing but the file list.
        entries = list(pool.map(_entries, [args.impl] * len(files), files,
                                chunksize=max(1, len(files) // (4 * args.threads))))
        n_events = sum(entries)
        tasks = make_tasks(files, entries, args.chunk_events)
    bench.record["worker_pids"] = len(pids)
    bench.record["tasks"] = len(tasks)

    counts, read, io, cpu_workers = None, 0, {"rchar": 0, "read_bytes": 0}, 0.0
    with bench.phase("loop"):
        futures = [pool.submit(_run_task, args.impl, path, start, stop, args.chain_len,
                               args.rp_id, args.chain, args.period)
                   for path, start, stop in tasks]
        for future in as_completed(futures):
            intermediate, file_read, file_io, file_cpu = future.result()
            counts = intermediate if counts is None else [a + b for a, b in
                                                          zip(counts, intermediate)]
            read += file_read
            cpu_workers += file_cpu
            for key in io:
                io[key] += file_io[key]
    pool.shutdown(wait=True)

    bench.override_bytes("loop", read)
    bench.record["cpu_loop_parent"] = bench.record["cpu_loop"]
    bench.record["cpu_loop_workers"] = cpu_workers
    bench.record["cpu_loop"] += cpu_workers
    bench.record["io_rchar_loop"] = io["rchar"]
    bench.record["io_read_bytes_loop"] = io["read_bytes"]
    bench.record["peak_rss_tree_kb"] = trace_peak_kb(os.environ.get("RSS_TRACE"))
    bench.finish({"events_passed": counts[-1], "intermediate": counts}, n_events=n_events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
