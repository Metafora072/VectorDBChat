# Findings: DENSE-OPQ-KERNEL-GATE-A0

## Status

```text
HOLD-DENSE-OPQ-BOTTLENECK
LOW/HOLD-STRUCTURED-FAST-OPQ
```

## Main Finding

The `~1.14 ms/query` OPQ rotation from the prior OPQ-A0 is not a defensible research motivation by itself. A direct implementation-level fix reduces 960D rotation-only time from `1143.66 us` to `123.15 us` without changing Recall.

## Boundary

The optimized dense rotation is still measurable in search-process timing at low and medium L. The clearest remaining window is `L=100-200`; at `L>=400`, the zero-rotation p50 upper bound is small for V2 (`1.08x` at L400, `1.04x` at L800).

## Caveat

Search-process sampled `rotation_us` is much larger than standalone microbench timing for every implementation. This makes precise bottleneck attribution medium-confidence only. Future work should validate with a pre-rotated-query or zero-rotation ablation before turning Fast-OPQ into a paper mechanism.

## Constraint For Future Attempts

Any structured/Fast-OPQ proposal must compare against optimized V1 dense rotation, not against DiskANN native V0.
