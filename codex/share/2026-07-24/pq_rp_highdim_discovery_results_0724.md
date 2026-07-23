# PQ-RP-HIGHDIM-DISCOVERY

GIST1M-960D full-1K characterization completed in 17m24.52s with zero
GPU use.

## Core result

| Comparison | Recall | Reads | Comparisons | QPS | p99 | Extra DRAM |
|---|---|---:|---:|---:|---:|---:|
| PQ16 L800 → PQ32 L400 | 80.78% → 88.75% | −49.29% | −46.23% | 1.883× | −45.10% | +16 B/vector |
| PQ32 L800 → PQ64 L400 | 94.83% → 96.82% | −49.29% | −46.27% | 1.839× | −45.60% | +32 B/vector |

Only Exact triggered a third full multi-`L` repeat. PQ16/PQ32/PQ64 use
the mean of two stable repeats; Exact uses the median of three and has a
stable pair at every `L`.

Exploratory verdict:

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
```

This is a GIST-specific idea-discovery signal. It does not establish
mixed-precision feasibility, node/query selectivity, high-dimensional
generality, or a paper-level performance claim.

The comparisons are threshold-matched no-lower-Recall Pareto
comparisons, not strict equal-Recall estimates. An independent
result-to-claim reviewer agreed with the discovery PASS at high
confidence within this narrow scope.

Artifacts:

- `pq_rp_highdim_discovery_curve_0724.csv`
- `pq_rp_highdim_discovery_decision_0724.json`
- `pq_rp_highdim_discovery_repeat_gate_0724.json`
- `pq_rp_highdim_discovery_frontier_0724.png`
- full scripts, summaries, compressed per-query data and logs under
  `codex/work/2026-07-24/pq_rp_highdim_discovery/`
