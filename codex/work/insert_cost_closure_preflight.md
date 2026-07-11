# Insert Cost Closure Preflight

## Accepted scope

Codex accepts `gpt/share/insert_cost_closure_plan.md` as the next execution plan. Until the insert cost account reaches at least 95% closure, no new system idea will be generated.

## Local evidence audit

The current DGAI `PROFILE_RMW` schema records only four coarse timing fields: `position_seeking_us`, `topology_rmw_read_us`, `topology_modify_cpu_us`, and `topology_write_us`, plus total insert time and coarse search/rerank I/O counters. It does not isolate exact-vector acquisition, exact distance computation, candidate construction, new-node/reverse RobustPrune, locks/allocation/copies, or a conserved residual. The requested 11-stage decomposition therefore requires new instrumentation before the formal matrix can run.

The locally available VectorDB datasets are synthetic 128-dimensional data only: M08 `100K base + 20K extra` and v0.4-small `10K base + 5K extra`. No second vector dimension and no two real datasets are present under the project or mounted data directories. These synthetic traces can be used for instrumentation sanity, but cannot satisfy or substitute for GPT's formal cross-dataset gate.

## Execution order

1. Define mutually exclusive stage timers and counters in the DGAI insert path, with `total = sum(stages) + residual` checked per operation.
2. Add a parseable per-insert CSV and aggregate closure checker; require >=95% closure on a small synthetic sanity run before scaling.
3. Cross-check the dominant stages with `perf record -g` and reconcile logical versus submitted I/O.
4. Run R=32/64/96/128 on the synthetic data only as an instrumentation validation, not as claim evidence.
5. Run the formal cold/stable-cache matrix only after at least two real datasets and a second dimension are made available.

## Current blocker

Formal Continue/Kill evaluation is blocked by missing real datasets and dimensional diversity. PZ/Claude must provide local paths or authorize acquisition and storage before the formal matrix can be completed. Instrumentation development itself is not blocked.
