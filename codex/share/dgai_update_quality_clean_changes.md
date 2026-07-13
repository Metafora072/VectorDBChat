# DGAI G0 Clean Changes

Base commit: `a0179b876a4bd453336dc2893b46ae890f680555`.

The experiment used only the following source changes. The canonical harness and measurement helper are stored beside this file.

## Build compatibility

- Make jemalloc optional because the local environment does not provide its development symlink.
- Add a minimal `mkl_cblas.h` compatibility include.
- Build with `REORDER_COMPUTE_PQ`, `USE_TOPO_DISK`, `USE_DOUBLE_PQ`, `COLLECT_INFO_2`, `FIX_PQ_TABLE_ALIGNMENT` and `FIX_PENDING_INSERT_VISIBILITY`.
- Link `/usr/lib/x86_64-linux-gnu/blas/libblas.so.3` explicitly.

## PQ alignment guard

In `include/pq_table.h`, `FIX_PQ_TABLE_ALIGNMENT` replaces `_mm512_stream_load_si512` with `_mm512_loadu_ps`. The original streaming load faults when the table address is not 64-byte aligned. Both paths load the same 16 floats and leave distance arithmetic unchanged.

## Pending insert visibility guard

In `src/search/rerank_search.cpp`, a PQ ID whose topology mapping is still `kInvalidID` is marked visited, unlocked and skipped under `FIX_PENDING_INSERT_VISIBILITY`. Before full-vector reranking, candidates whose coordinate mapping is still invalid are removed. This prevents a newly appended PQ code from being searched before topology/coordinate mapping commit.

The prior dirty formal build also enabled both named guards. These guards are therefore prerequisites for a stable direct match, not an explanation for the old dirty-only recall decline.

## Measurement-only access

`include/ssd_index.h` declares three read-only helpers implemented in `codex/share/dgai_update_quality_measurement.cpp`:

- copy a node's topology/coordinate locations;
- copy a stored vector;
- copy a node's neighbor list.

`tests/CMakeLists.txt` adds the `dgai_update_quality_g0` target whose source is `codex/share/dgai_update_quality_g0.cpp`. No production repair, scheduler, graph mutation policy or pruning algorithm was added.
