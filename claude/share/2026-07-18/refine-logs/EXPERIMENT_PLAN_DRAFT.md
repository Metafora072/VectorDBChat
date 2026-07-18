# Experiment Plan (Draft) — ANN-on-ZNS Feasibility Frontier

## Paper Claims to Validate

| # | Claim | Type | Block |
|---|-------|------|-------|
| C1 | GC WA exhibits regime transition at identifiable ρ* | Main anchor | B1 |
| C2 | Graph ANN page-touch has low skewness (Gini 0.03-0.29) | Descriptive | B2 |
| C3 | Low skewness → higher WA than skewed at same mean ρ | Causal (controlled) | B3 |

## Experiment Blocks

### B1: Feasibility Boundary Characterization (Main Result)

**Claim tested**: C1 — regime transition exists at identifiable ρ*
**Why**: This is the paper's raison d'être.

**Setup**:
- Input: 8 re-instrumented traces (2 systems × 4 scales)
- Simulator: formal state machine (Greedy, Cost-Benefit, Oracle)
- Sweep: zone_size ∈ {256MB, 512MB, 1GB, 2GB} × OP ∈ {0.07, 0.14, 0.21, 0.28}
- Total runs: 8 traces × 4 zone_sizes × 4 OP_ratios × 3 policies = 384 runs

**Metrics**:
- WA factor (primary)
- Zone reset count
- Victim valid-fraction distribution
- Greedy-Oracle WA gap (room for smart policy)

**Success criterion**:
- Clear ρ* identifiable for at least 2 zone_size × OP combinations
- ρ* stable (<15% variation) between Greedy and Cost-Benefit

**Failure interpretation**:
- If WA grows smoothly (no sharp boundary): report WA curve shape and functional fit. Still publishable as "no regime transition" finding.

**Visualizations**:
- Fig 1: WA vs ρ (mean ver/page) for each zone_size, OP=0.14, all 3 policies
- Fig 2: WA heatmap over (ρ, zone_size) for Greedy, OP=0.14
- Fig 3: Greedy-Oracle WA gap vs ρ (shows room for policy improvement)

**Estimated time**: 384 runs × ~5s each = ~30 min total

### B2: Workload Characterization (Descriptive)

**Claim tested**: C2 — low skewness characterization
**Why**: Provides structural understanding of graph ANN write patterns.

**Setup**:
- Compute from each of 8 traces:
  - Gini coefficient of page version count distribution
  - Top-1%, top-10% touch concentration
  - Page-lifetime survival curves (death_seq - birth_seq)
  - Rewrite inter-arrival time distribution

**Metrics**: Gini, top-k%, lifetime CDF shape, inter-arrival distribution shape

**Success criterion**: Gini < 0.3 for all graph ANN data points (confirms low skewness)

**Failure interpretation**: If Gini > 0.5 for some data points, the "low skewness" characterization doesn't hold universally → qualify the claim by system/scale.

**Visualizations**:
- Fig 4: Page version count distribution (histogram) for all 8 traces
- Fig 5: Page-lifetime survival curves (CDF) for DGAI vs OdinANN at 50K and 400K
- Table 1: Gini, top-1%, top-10%, mean ver/page for all 8 traces

**Estimated time**: < 5 min

### B3: Controlled Trace Transformation (Novelty Isolation)

**Claim tested**: C3 — skewness affects GC efficiency at same mean ρ
**Why**: This is the supporting causal claim. Isolates the effect of distribution shape.

**Setup**:
- Base trace: DGAI 400K (ρ = 1.99, Gini = 0.27)
- Fix: total writes (3,425,192), total pages (1,721,291), mean ver/page (1.99)
- Vary distribution shape:
  1. **Uniform**: every page gets exactly 2 versions (round to maintain total)
  2. **Graph-ANN-actual**: real distribution from trace
  3. **Zipfian(α=0.5)**: moderate skew, Gini ≈ 0.4
  4. **Zipfian(α=1.0)**: heavy skew, Gini ≈ 0.8
  5. **Bimodal(80/20)**: 80% pages get 1 version, 20% get ~6 versions
- Temporal model: version timestamps assigned uniformly at random within trace duration
- Simulator: Greedy + Cost-Benefit, zone_size=512MB, OP=0.14

**Metrics**: WA factor for each distribution shape

**Success criterion**: Uniform and Graph-ANN-actual produce WA at least 20% higher than Zipfian(α=1.0) at the same mean ρ

**Failure interpretation**: If difference < 10%, skewness effect is negligible at this mean ρ → claim doesn't hold

**Visualizations**:
- Fig 6: WA vs Gini coefficient at fixed ρ = 1.99
- Fig 7: Victim valid-fraction distribution for uniform vs Zipfian (explains the mechanism)

**Estimated time**: 5 distributions × 2 policies × ~5s = ~1 min

### B4: FEMU Validation (Simulator Credibility)

**Claim tested**: Simulator accuracy
**Why**: Strengthens venue readiness. Independent validation.

**Setup**:
- 3 representative traces: DGAI 50K (low WA), DGAI 400K (medium), OdinANN 400K (high)
- Replay each through FEMU ZNS mode
- Compare 5 metrics against simulator output (Greedy policy)

**Metrics**:
1. Total host write bytes (should match ±0.1%)
2. Total zone resets (independent)
3. Total media bytes written
4. Valid-fraction-at-reset distribution
5. WA factor

**Success criterion**: WA within 5% of simulator for all 3 traces

**Failure interpretation**: Discrepancy > 10% → investigate FEMU's internal GC behavior, calibrate simulator. Report calibration procedure honestly.

**Visualizations**:
- Table 2: Simulator vs FEMU comparison on 5 metrics × 3 traces

**Estimated time**: 3-5 days (FEMU setup + replay)

## Run Order and Decision Gates

```
Week 1-2: Re-instrument M3, re-collect 8 traces
  ↓
Week 2: B2 (descriptive stats) — immediate, no dependencies
  GATE: If Gini > 0.5 for any trace, re-examine C2 framing
  ↓
Week 2-3: B1 (full parameter sweep) — depends on traces
  GATE: If no identifiable ρ*, reframe as "smooth WA curve" paper
  ↓
Week 3: B3 (controlled transformation) — depends on B1 showing meaningful WA variation
  GATE: If skewness effect < 10%, drop C3 entirely
  ↓
Week 3-5: B4 (FEMU validation) — can run in parallel with B3
  GATE: If WA discrepancy > 10%, add calibration section
  ↓
Week 5-6: Paper writing
```

## Compute Budget

| Block | CPU-hours | Notes |
|-------|-----------|-------|
| B1 | < 1 | 384 simulation runs |
| B2 | < 0.1 | Histogram computation |
| B3 | < 0.1 | 10 simulation runs |
| B4 | ~20-30 | FEMU emulation |
| Re-collection | ~10 | 8 M3 runs |
| **Total** | **~35** | No GPU |
