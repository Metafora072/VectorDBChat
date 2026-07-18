# ZNS Z0: Trace/Model Validity Gate

**Date**: 2026-07-19
**Status**: Proposed — awaiting Gpt approval
**Scope**: Minimum viable validation of whether ANN page-write traces produce structurally different GC behavior than non-ANN workloads with matched statistics.

---

## Objective

Answer one question: **Does graph ANN produce ZNS GC behavior that cannot be predicted from mean rewrite intensity (ρ) alone?**

If yes → ANN-specific structure exists → Z1 can explore design levers.
If no → ρ determines WA regardless of workload source → no ANN-specific contribution → KILL entire ZNS-ANN direction.

## Gpt's Criticisms Accepted

1. **Novelty inflation**: Pipeline scores were systematically high. "No paper with this exact title" ≠ mechanism gap.
2. **ρ/Gini insufficiency**: Same ρ and Gini can yield different WA due to temporal locality, burstiness, reuse distance.
3. **WA=3 arbitrary**: The threshold has no principled basis. Z0 should report WA curves, not thresholds.
4. **B3 confounding**: Redistributing version counts while assigning random timestamps destroys temporal structure. Not a valid isolation.
5. **Scope**: Two systems × one dataset × write-only trace × host-GC simulation is not automatically a FAST/EuroSys paper.

## Z0 Deliverables

### D1: Temporal per-write trace extraction

Re-instrument M3 to emit a per-write `(sequence_number, page_id, write_size)` trace.
- Scope: DGAI 400K only (highest ρ among DGAI points, most interesting for GC)
- Output: One trace file, ~3.4M events
- Effort: ~1 day (small M3 code change + single run)

### D2: Minimal zone-packing simulator

Single-policy (Greedy), single configuration:
- Zone size: 512MB (midpoint of planned range)
- OP: 0.14 (industry standard)
- Page size: 4KB
- Output: WA, zone resets, victim valid-page fraction distribution

No sweep, no Cost-Benefit, no FEMU. Just one honest data point.

### D3: Matched-statistics synthetic baselines

Generate 3 synthetic traces with identical (total_writes, total_pages, mean_ρ) as the real DGAI-400K trace:
1. **Uniform**: Each page gets exactly ⌊ρ⌋ or ⌈ρ⌉ versions, timestamps uniformly distributed
2. **Zipfian**: Page version counts follow Zipf(s=1.0), timestamps uniformly distributed
3. **Temporal-clustered**: Uniform version counts but writes to each page arrive in bursts (models locality)

Run all 3 through the same simulator as D2.

### D4: Comparison table

| Trace | mean ρ | Gini | WA | Zone resets | Conclusion |
|-------|--------|------|----|-----------|-|
| DGAI 400K (real) | 1.99 | 0.27 | ? | ? | — |
| Uniform synthetic | 1.99 | ~0 | ? | ? | — |
| Zipfian synthetic | 1.99 | ~0.8 | ? | ? | — |
| Temporal-clustered | 1.99 | ~0 | ? | ? | — |

**Pass criterion**: Real ANN trace WA differs from ALL three synthetics by >15% relative, showing ANN-specific temporal/spatial structure matters beyond ρ and Gini.

**Kill criterion**: Real ANN trace WA is within 15% of Uniform synthetic → ρ alone predicts WA → no ANN-specific contribution.

**Ambiguous**: Real close to one synthetic but not others → report and discuss whether the matched dimension (temporal, skewness) constitutes a novel characterization.

## What Z0 Does NOT Include

- No 8-point trace collection
- No OdinANN traces (only DGAI 400K)
- No FEMU validation
- No parameter sweeps
- No Cost-Benefit policy
- No paper writing
- No claims about feasibility boundaries or thresholds

## Resource Estimate

- Re-instrumentation: 1 day
- Single DGAI 400K trace collection: ~30 min wall, ~30 GB disk
- Simulator implementation: 1 day
- Synthetic trace generation + simulation: <1 hour
- Analysis: 0.5 day
- **Total: ~3 days, <1 CPU-hour simulation, ~30 GB temporary disk**

## Decision Tree After Z0

```text
Z0 result
├─ ANN WA ≠ all synthetics (>15%): Z0 PASS
│   → Write Z0 report
│   → Propose Z1 scope: what ANN-specific design lever to explore
│   → Gpt decides whether Z1 is worth pursuing
├─ ANN WA ≈ Uniform synthetic (<15%): Z0 KILL
│   → ρ alone predicts GC, no ANN-specific contribution
│   → Close entire ZNS-ANN direction
│   → Move to Ambiguity-Monotone or PageTxn paper gate
└─ Ambiguous: Z0 HOLD
    → Report which synthetic matches and why
    → Gpt decides whether the matched dimension is novel
```
