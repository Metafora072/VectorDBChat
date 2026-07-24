# Result-to-Claim Review: DENSE-OPQ-KERNEL-GATE-A0

## Verdict

```text
claim_supported = partial
confidence = medium
```

## Supported

- The original `~1.14 ms/query` OPQ rotation is strongly shown to be an unoptimized DiskANN native implementation artifact.
- Rotation-only 960D:
  - V0 native: `1143.66 us/query` mean, `1130.82 us` p50.
  - V1 loop/scratch: `123.15 us/query` mean, `122.80 us` p50, about `9.3x` faster.
  - V2 system-BLAS SGEMV-compatible: `327.17 us/query` mean, `325.56 us` p50.
- Recall is identical across V0/V1/V2 in the frozen-graph search matrix.
- At larger search budgets, optimized dense rotation is unlikely to dominate:
  - V2 L400: rotation share `7.3%`, zero-rotation upper bound `1.08x`.
  - V2 L800: rotation share `3.6%`, zero-rotation upper bound `1.04x`.

## Not Supported

- Do not claim dense OPQ rotation remains a major end-to-end bottleneck across the full search regime.
- Do not use the original `1.14 ms/query` as an optimized OPQ baseline.
- Do not claim structured/Fast-OPQ is broadly necessary on this setup.
- Do not claim BLAS SGEMV is the best optimized path on this host; V1 is faster than V2 in rotation-only microbench.
- Do not over-trust precise in-search rotation attribution because sampled search-process rotation time is much larger than standalone rotation timing.

## Suggested Claim

On GIST1M-960D OPQ32 under fixed graph/codes/query semantics, the previously observed `~1.14 ms/query` OPQ rotation is mostly an unoptimized DiskANN native implementation artifact: a simple loop/scratch optimization reduces rotation-only time to `~123 us/query`. After optimization, dense OPQ rotation remains a measurable but regime-dependent cost, with possible moderate impact at `L=100-200` and small impact at `L>=400`. These results justify holding, not prioritizing, structured/Fast-OPQ work until cleaner in-search attribution and stronger BLAS/hardware validation show a persistent bottleneck.

## Next Experiments

- Fix rotation instrumentation and compare standalone rotation, in-search sampled timing, and a direct pre-rotated-query or zero-rotation ablation if semantically allowed.
- Repeat V1/V2 with stronger system isolation or more repeats.
- Test Intel oneMKL or another high-performance BLAS backend.
- Collect per-implementation perf counters rather than aggregate perf only.
- If structured/Fast-OPQ remains under consideration, compare against optimized V1, not V0.
