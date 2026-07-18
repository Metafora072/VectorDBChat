# Research Proposal: GC Feasibility Boundary for Graph ANN Update Workloads on Append-Only Storage

## Problem Anchor
- **Bottom-line problem**: What is the GC write amplification feasibility boundary for disk-resident graph ANN update workloads on ZNS (append-only) SSDs? At what rewrite intensity does GC WA exceed practical thresholds?
- **Must-solve bottleneck**: Graph ANN inserts trigger scattered, near-uniform page rewrites. On ZNS, each rewrite appends a new version + eventual GC. Nobody has measured the resulting WA for graph ANN.
- **Non-goals**: Full "does graph ANN work on ZNS" answer (reads, query-update interference, tail latency); building a ZNS-ANN system; optimizing DiskANN.
- **Constraints**: Re-instrumented M0-M3 data, 5-6 weeks, EuroSys 2027 or FAST 2027 short paper.
- **Success condition**: Quantitative WA boundary for observed DGAI and OdinANN workloads on SIFT-10M, with controlled evidence that page-touch skewness affects WA.

## Method Thesis
We characterize a GC write amplification boundary for graph ANN update workloads on append-only storage by replaying syscall-level per-write page traces through a zone-packing simulator with Greedy and Cost-Benefit GC policies, validated against FEMU ZNS emulation. We show that the observed graph ANN workloads have low page-touch skewness (Gini 0.03-0.29), and that within a controlled trace family, lower skewness produces higher GC WA at the same mean rewrite intensity.

## Contribution Focus
- **Dominant**: First GC feasibility analysis for graph ANN update workloads on append-only storage, using the only existing syscall-level page-write trace dataset for this workload class. Establishes the WA threshold-crossing boundary as a function of rewrite intensity, zone geometry, and over-provisioning.
- **Supporting**: Controlled trace transformation showing that page-touch skewness redistribution at fixed mean rewrite factor changes WA in the observed direction (lower skewness → higher WA).
- **Non-contributions**: No ZNS-ANN system, no new graph algorithm, no unconditional workload-class generalization, no read-side analysis.

## Related Work Positioning

| Prior Work | Workload | Page Lifecycle? | GC Feasibility Boundary? |
|------------|----------|-----------------|--------------------------|
| Desnoyers (2012) | General SSD workloads | No | Analytical WA model |
| He et al. (FAST 2017) | Workload-aware SSD GC | Implicit | No formal boundary |
| B+-tree on ZNS (TACO 2026) | B-tree index | No | Write pattern characterization |
| LSM-VEC variants | Log-structured ANN | No | N/A (conventional SSD) |
| DiskANN/PipeANN/OdinANN | Graph ANN on conv. SSD | No | No |
| Our M0-M3 (2026) | Graph ANN (DGAI, OdinANN) | YES (syscall-level) | **THIS PAPER** |

**"First" scope**: First GC feasibility analysis for graph ANN workloads on append-only storage, enabled by the only existing syscall-level page-write dataset for this workload class.

## Key Empirical Grounding (M0-M3 Data)

| System | n | Mean ver/page (ρ) | Gini | Single-ver pages | Multi-ver pages |
|--------|---|--------------------|------|------------------|-----------------|
| DGAI | 50K | 1.04 | 0.035 | 96.4% | 3.6% |
| OdinANN | 50K | 1.24 | 0.161 | 79.4% | 20.6% |
| DGAI | 400K | 1.99 | 0.268 | 38.4% | 61.6% |
| OdinANN | 400K | 5.00 | 0.290 | 7.3% | 92.7% |

## Method

### Step 1: Re-Instrument M3 for Per-Write Trace
Add monotonic sequence counter to existing write interception layer. Each pwrite64/io_uring write emits `(seq_no, page_id, replacement_batch_id)`. Re-collect 8 data points (2 systems × 4 scales). Estimated: 2 days.

### Step 2: Zone-Packing Simulator
Serial trace replay simulator. Two GC policies:

**Greedy**: victim = zone with lowest valid_count/capacity
**Cost-Benefit**: victim = zone maximizing `(1 - u) × age / (2u)` where u = valid_count/capacity, age = current_seq - zone's last_write_seq

GC triggers when free zones fall below a reserve watermark (2 zones). Full pseudocode and parameter table to be specified during implementation.

### Step 3: Boundary Identification
- Control variable: ρ = mean versions per page (available at ρ ∈ {1.04, 1.24, 1.99, 5.00} plus intermediate values from n=100K, 200K)
- Response: WA factor
- Threshold: T = 3 (industry convention for sustainable ZNS WA)
- Boundary: ρ* = linear interpolation where WA crosses T
- Sweep: zone_size ∈ {256MB, 512MB, 1GB, 2GB} × OP ∈ {0.07, 0.14, 0.21, 0.28}

### Step 4: Workload Characterization (Descriptive)
For each trace: Gini coefficient, top-1%/10% concentration, page-lifetime survival curves, rewrite inter-arrival distribution. These are DESCRIPTIVE statistics of the observed workloads, not workload-class generalizations.

### Step 5: Controlled Trace Transformation
Fix total writes, pages, mean ρ. Vary Gini via matched pair (low-skew ≈ graph ANN actual, high-skew = Zipfian redistribution). Use same temporal assignment model for both. Run both through simulator. Report WA difference. Explicitly note confound limitations.

### Step 6: FEMU Validation (3 representative points)
Points: below boundary (DGAI 50K), near boundary (DGAI 400K), above boundary (OdinANN 400K). Primary metric: WA (target: within 5%). Diagnostics: zone resets, victim valid-fraction distribution.

## Claims

**C1 (Threshold-Crossing Boundary)**: For the observed DGAI and OdinANN update workloads on SIFT-10M, GC WA crosses the T=3 threshold at an identifiable rewrite intensity ρ* that depends on zone geometry and OP. [Qualified to observed workloads.]

**C2 (Low Skewness)**: The observed graph ANN page-touch distributions have Gini coefficients in the range 0.03-0.29, indicating near-uniform page aging. [Descriptive, scoped to observations.]

**C3 (Skewness Effect)**: Within a controlled trace family with fixed total writes, pages, and mean ρ, redistributing version counts to increase Gini produces lower WA. [Scoped to controlled setting, confound-acknowledged.]

## Limitations (Stated Upfront)
1. Only two systems (DGAI, OdinANN) and one dataset (SIFT-10M). Generalization to other graph ANN systems, datasets, and dimensionalities requires additional experiments.
2. Write-side only. Read performance, query latency, and mixed read-write interference on ZNS are separate questions.
3. Simulation-based (validated against FEMU emulation). Real ZNS hardware may exhibit additional effects (zone reset latency, write buffer behavior).
4. Controlled transformation confound: temporal locality and burstiness may covary with Gini in real workloads.

## Timeline
- Week 1: Re-instrument M3, FEMU smoke test
- Week 2: Re-collect traces, implement simulator, run B2 (descriptive stats)
- Week 3: B1 (full sweep), B3 (controlled transformation)
- Week 4: B4 (FEMU validation, 3 points)
- Week 5-6: Paper writing, visualization

## Compute
- ~35 CPU-hours total (simulation + FEMU + re-collection)
- No GPU needed
