# Experiment Plan — GC Feasibility Boundary for Graph ANN on Append-Only Storage

## Paper Claims

| # | Claim | Type | Evidence Block |
|---|-------|------|---------------|
| C1 | WA crosses T=3 at identifiable ρ* for observed workloads | Main anchor | B1 |
| C2 | Observed graph ANN has Gini 0.03-0.29 (descriptive) | Characterization | B2 |
| C3 | Lower Gini → higher WA in controlled setting | Supporting (controlled) | B3 |
| — | Simulator matches FEMU within 5% WA | Validation | B4 |

## B1: Feasibility Boundary Sweep (Main Result)

**Purpose**: Identify ρ* where WA crosses T=3 for each (zone_size, OP) configuration.

**Input**: 8 re-instrumented per-write traces (DGAI × {50K, 100K, 200K, 400K}, OdinANN × same)
**Simulator**: Greedy + Cost-Benefit policies
**Sweep**: zone_size ∈ {256MB, 512MB, 1GB, 2GB} × OP ∈ {0.07, 0.14, 0.21, 0.28}
**Total runs**: 8 × 4 × 4 × 2 = 256 runs
**Warm-up**: Discard first 10% of events from WA accounting
**Estimated time**: ~20 min total

**Output**:
- WA vs ρ curves for each (zone_size, OP, policy) — **Fig 1** (4 panels, one per zone_size)
- WA heatmap over (ρ, zone_size) at OP=0.14 — **Fig 2**
- ρ* table: boundary values for T ∈ {2, 3, 5} — **Table 2**
- Greedy vs Cost-Benefit gap — **Fig 3** (shows room for policy improvement)

**Success**: ρ* identifiable for ≥2 (zone_size, OP) combinations. If WA is monotone, report interpolated crossing. If not monotone, report all crossings.

**Decision gate**: If no crossing within observed range (all WA < 3 or all WA > 3), reframe as "feasible throughout" or "infeasible throughout" and report WA curve shape.

## B2: Workload Characterization (Descriptive)

**Purpose**: Characterize the page-touch distribution of observed graph ANN workloads.

**Input**: Same 8 traces
**Compute**: Gini, top-1%/10% concentration, page-lifetime CDF, rewrite inter-arrival histogram

**Output**:
- **Table 1**: Gini, top-1%, top-10%, mean ρ, max versions for all 8 traces
- **Fig 4**: Page version count histograms (4 panels: DGAI and OdinANN at 50K and 400K)
- **Fig 5**: Page-lifetime survival curves (CDF)

**Success**: Gini < 0.3 for all data points confirms low skewness.

**Decision gate**: If Gini > 0.5 for any trace, qualify C2 by system/scale.

## B3: Controlled Trace Transformation (Novelty Isolation)

**Purpose**: Show that skewness redistribution at fixed mean ρ changes WA.

**Input**: DGAI 400K trace (ρ = 1.99, Gini = 0.27) as base
**Fix**: total writes = 3,425,192; total pages = 1,721,291; mean ρ = 1.99
**Vary**: 
- Low-skew: actual graph ANN distribution (Gini ≈ 0.27)
- High-skew: Zipfian redistribution of version counts (target Gini ≈ 0.8)
- Continuous sweep: 5 Gini values from 0.1 to 0.9
**Temporal model**: version timestamps assigned uniformly at random within trace duration (same model for all)
**Simulator**: Greedy + Cost-Benefit, zone_size=512MB, OP=0.14
**Total runs**: 7 distributions × 2 policies = 14 runs

**Output**:
- **Fig 6**: WA vs Gini at fixed ρ = 1.99
- **Fig 7**: Victim valid-fraction distribution for low-skew vs high-skew (mechanism illustration)

**Success**: Low-skew WA ≥ 20% higher than high-skew WA.

**Decision gate**: If difference < 10%, drop C3 from paper.

**Confound note**: State explicitly that temporal locality and burstiness are held constant via the uniform temporal model, but real workloads may have correlated skew-temporality structure.

## B4: FEMU Validation (Simulator Credibility)

**Purpose**: Verify simulator WA predictions against independent ZNS emulation.

**Points**: 
- Below boundary: DGAI 50K (ρ ≈ 1.04)
- Near boundary: DGAI 400K (ρ ≈ 1.99) 
- Above boundary: OdinANN 400K (ρ ≈ 5.00)

**FEMU config**: ZNS mode, zone size matched to simulator, OP matched
**GC**: FEMU's internal GC or host-managed GC via libzbd
**Comparison metrics**:
- WA factor (primary, target: within 5%)
- Zone reset count (diagnostic)
- Victim valid-fraction distribution (diagnostic)

**Output**: **Table 3**: Simulator vs FEMU comparison

**Fallback**: If FEMU discrepancy > 10%, investigate cause, add calibration section, report honestly.

**Week 1 gate**: FEMU smoke test — if FEMU setup takes > 3 days, deprioritize to appendix and note as limitation.

## Run Order

```
WEEK 1:  Re-instrument M3 trace emission
         FEMU smoke test (install, configure, run trivial workload)
         
WEEK 2:  Re-collect 8 traces (DGAI + OdinANN × 4 scales)
         B2: Descriptive statistics (immediate, no sim needed)
         ├─ GATE: Gini < 0.3 for all? → proceed
         └─ GATE: Gini > 0.5 for any? → qualify C2
         Implement zone-packing simulator
         
WEEK 3:  B1: Full parameter sweep (256 runs, ~20 min)
         ├─ GATE: ρ* identifiable? → proceed with boundary
         └─ GATE: No crossing? → reframe as curve-shape paper
         B3: Controlled transformation (14 runs, ~1 min)
         ├─ GATE: WA difference > 20%? → C3 confirmed
         └─ GATE: WA difference < 10%? → drop C3
         
WEEK 4:  B4: FEMU validation (3 points)
         ├─ GATE: WA within 5%? → strong validation
         └─ GATE: WA off by > 10%? → add calibration section
         Begin paper writing
         
WEEK 5-6: Paper writing, visualization, revision
```

## Compute Budget

| Block | CPU-hours | Dependencies |
|-------|-----------|-------------|
| Re-collection (8 M3 runs) | ~10 | Re-instrumented M3 |
| B1 (256 sim runs) | < 1 | Traces + simulator |
| B2 (descriptive stats) | < 0.1 | Traces |
| B3 (14 sim runs) | < 0.1 | Simulator |
| B4 (3 FEMU points) | ~20-30 | FEMU + traces |
| **Total** | **~35** | **No GPU** |

## Paper Figure/Table Map

| # | Content | Block | Location |
|---|---------|-------|----------|
| Table 1 | Workload characterization (Gini, top-k%, ρ) | B2 | Section 3 |
| Table 2 | ρ* boundary values for T ∈ {2,3,5} | B1 | Section 4 |
| Table 3 | Simulator vs FEMU validation | B4 | Section 5 |
| Fig 1 | WA vs ρ curves (4 zone sizes) | B1 | Section 4 |
| Fig 2 | WA heatmap (ρ × zone_size) | B1 | Section 4 |
| Fig 3 | Greedy vs Cost-Benefit WA gap | B1 | Section 4 |
| Fig 4 | Page version count histograms | B2 | Section 3 |
| Fig 5 | Page-lifetime survival curves | B2 | Section 3 |
| Fig 6 | WA vs Gini at fixed ρ | B3 | Section 5 |
| Fig 7 | Victim valid-fraction (low vs high skew) | B3 | Section 5 |
