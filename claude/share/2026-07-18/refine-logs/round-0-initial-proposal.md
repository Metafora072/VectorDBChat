# Research Proposal: ANN-on-ZNS Feasibility Frontier — Page-Lifecycle Phase Transition in Graph ANN on Append-Only Storage

## Problem Anchor
- **Bottom-line problem**: No one knows whether disk-resident graph ANN (DiskANN-family) can operate on ZNS SSDs, which forbid in-place page overwrites and require sequential-zone-append semantics. The fundamental question is whether the page-rewrite patterns of dynamic graph ANN are compatible with append-only storage, or whether write amplification from garbage collection makes ZNS-ANN infeasible beyond a critical graph density.
- **Must-solve bottleneck**: Graph ANN inserts trigger cascading neighbor-repair writes that touch many scattered pages. On conventional SSDs, this is handled by in-place overwrites via the FTL. On ZNS SSDs (no FTL), every "overwrite" becomes an append of a new page version + eventual garbage collection of the old version. The ratio of live-to-dead data in zones determines GC write amplification — but nobody has measured this for graph ANN workloads.
- **Non-goals**: (1) Building a complete ZNS-ANN system (that's the follow-up ZoneEpoch-ANN paper). (2) Optimizing DiskANN's write path. (3) Comparing ZNS vs conventional SSD performance.
- **Constraints**: Use existing M0-M3 write attribution data (22.5M page versions across DGAI and OdinANN, SIFT-10M, 4 scale points). No ZNS hardware needed — this is an analytical/simulation study. Target: EuroSys 2027 or FAST 2027 short paper. Timeline: 4-6 weeks.
- **Success condition**: Produce a quantitative characterization of the GC phase transition — the critical (graph-density, update-rate, zone-size) triple beyond which ZNS-ANN write amplification exceeds a practical threshold (e.g., 3× over conventional SSD). The result is publishable whether the transition is favorable (ZNS-ANN is tractable for most practical regimes) or unfavorable (ZNS-ANN requires fundamentally different index semantics).

## Technical Gap

Current disk-resident graph ANN systems (DiskANN, PipeANN, OdinANN, VeloANN, GateANN) all assume conventional SSDs with FTL-mediated in-place overwrites. ZNS SSDs eliminate the FTL, offering higher sustained write bandwidth and lower tail latency — but require the host to manage data placement within sequential-write zones.

B+-tree on ZNS (ACM TACO 2026) demonstrates that tree-structured indexes can be adapted to ZNS by exploiting their naturally sequential write patterns. However, graph ANN has fundamentally different write characteristics:
- Each insert triggers R reverse-edge repair attempts (R=32 for DGAI, R=96 for OdinANN), each potentially updating a different page
- The resulting page-touch pattern is scatter-heavy, not sequential
- Pages accumulate multiple versions over time as different inserts repair different edges on the same page

**Why naive solutions fail**:
- "Just append every modified page" works at low density but creates massive garbage at high density (our M3 data shows temporal rewrite factor grows from 1.04× to 5.0×)
- "Use a log-structured layer" adds an indirection that defeats ZNS's latency advantages
- "Pre-allocate and never overwrite" only works if pages are rarely rewritten — but M2 data shows 92.7% of pages are rewritten at scale (OdinANN 400K)

**What's missing**: A quantitative model of when the page-rewrite dynamics of graph ANN cross from ZNS-tractable to ZNS-infeasible. Our M0-M3 infrastructure provides the first dataset capable of answering this question.

## Method Thesis
- **One-sentence thesis**: We characterize a GC phase transition in disk-resident graph ANN on append-only storage by computing offline-optimal and worst-case zone-packing boundaries from syscall-level page-version lifecycle data, establishing the feasibility frontier for ZNS-ANN as a function of graph density, degree budget, and zone geometry.
- **Why this is the smallest adequate intervention**: The question "is ZNS-ANN feasible?" must be answered before investing 3-4 months in building ZoneEpoch-ANN. A simulation study using real page-version traces is the minimum viable approach.
- **Why this route is timely**: ZNS SSDs are entering production (Samsung, Western Digital). B+-tree-on-ZNS is published (TACO 2026). The natural next question is whether more complex index structures (graph ANN) can also benefit — but nobody has the write-pattern data to answer it. We do (M0-M3).

## Contribution Focus
- **Dominant contribution**: First quantitative characterization of page-lifecycle dynamics in disk-resident graph ANN, revealing a GC phase transition that determines ZNS feasibility.
- **Optional supporting contribution**: A zone-packing simulation framework that computes optimal and greedy GC write amplification under configurable zone sizes and over-provisioning ratios.
- **Explicit non-contributions**: We do NOT build a ZNS-ANN system. We do NOT propose a new graph construction algorithm. We do NOT compare ZNS vs conventional SSD end-to-end performance.

## Proposed Method

### Complexity Budget
- **Frozen / reused**: M0-M3 write attribution infrastructure (already validated, 22.5M page versions collected)
- **New components**: (1) Page-version lifecycle extraction pipeline, (2) Zone-packing simulator, (3) GC write amplification analyzer
- **Tempting additions intentionally not used**: Real ZNS hardware experiments (simulation is sufficient for feasibility), adaptive zone allocation policies (that's ZoneEpoch-ANN's job)

### System Overview

```
M3 page-version traces (raw)
    ↓
[1] Page-Version Lifecycle Extractor
    - For each page: birth time, death time (first overwrite or end-of-trace), version count
    - Output: page_lifecycle_table(page_id, birth_t, death_t, version_count, system, n)
    ↓
[2] Zone-Packing Simulator
    - Input: page_lifecycle_table + zone_size_bytes + over_provisioning_ratio
    - Simulate: pages are appended to zones in arrival order
    - Track: per-zone live/dead ratio at each zone-reset decision point
    - Two policies: (a) GREEDY — reset zone with lowest live ratio, (b) OPTIMAL — offline optimal via LP/DP
    ↓
[3] GC Write Amplification Analyzer
    - Compute: WA = total_bytes_written / net_new_data_bytes for each (system, n, zone_size, OP_ratio)
    - Identify: phase transition boundary where WA exceeds threshold
    ↓
[4] Diagnostic Visualizations
    - Phase transition heatmaps: WA as function of (n, zone_size)
    - Page-lifetime distributions: survival curves per (system, n)
    - Temporal rewrite factor evolution curves
```

### Core Mechanism

**Input**: M3 page-version trace files containing (page_id, write_timestamp, system, batch_id) tuples for all 22.5M page versions across 4 (system, scale) points.

**Processing**:
1. **Lifecycle extraction**: For each unique page, compute:
   - `birth_time`: timestamp of first write
   - `death_time`: timestamp when a newer version of the same page appears (or end-of-trace)
   - `lifespan`: death_time - birth_time
   - `version_count`: total versions of this page in the trace
   
2. **Zone simulation**: Given zone_size Z (in pages) and over-provisioning ratio OP:
   - Maintain a pool of zones, each with capacity Z pages
   - Append pages in trace order to the current active zone
   - When active zone fills, start a new zone
   - When total allocated zones exceed (1 + OP) × minimum required, trigger GC:
     - GREEDY: pick zone with lowest live-page fraction, copy live pages to active zone, reset
     - OPTIMAL: solve offline for minimum total bytes written (linear program over zone-reset ordering)
   - Track cumulative write amplification

3. **Phase transition identification**: Sweep (zone_size, OP_ratio) parameter space for each (system, n) point. Identify the boundary where WA crosses practical thresholds (2×, 3×, 5×).

**Output**: Phase transition diagrams + page lifetime statistics + GC write amplification tables.

**Why this is the main novelty**: No prior work has analyzed page-rewrite dynamics of graph ANN workloads. The M0-M3 data is unique — it captures every 4KB page write at the syscall level for two different DiskANN implementations across 4 scale points. The phase transition characterization directly answers whether ZNS-ANN is worth building.

### Modern Primitive Usage
- No LLM/VLM/RL primitives needed. This is a pure empirical/analytical systems study.
- The "modern" aspect is the ZNS storage hardware trend — we are ahead of it analytically.

### Training Plan
- Not applicable (no ML training). This is an analytical/simulation study.

### Failure Modes and Diagnostics
- **Failure mode 1**: Phase transition is trivially favorable (WA < 2× everywhere) → paper becomes "ZNS works for ANN, just use it." **Mitigation**: Even a favorable result is valuable as the first quantitative evidence. Extend to larger scales via extrapolation models.
- **Failure mode 2**: Phase transition is trivially unfavorable (WA > 10× everywhere) → paper becomes "ZNS doesn't work for ANN." **Mitigation**: Identify which write-pattern components dominate and whether index-level changes (smaller R, batched repair, lazy maintenance) could shift the boundary. This becomes the motivation for ZoneEpoch-ANN.
- **Failure mode 3**: Simulation doesn't match real ZNS behavior. **Mitigation**: Validate simulation against ZNS emulation (FEMU) on a small-scale workload.

### Novelty and Elegance Argument

**Closest work**:
- B+-tree on ZNS (TACO 2026): analyzes tree-index page patterns for ZNS, but B-tree has very different (mostly sequential) write patterns
- DiskANN write analysis: our own M0-M3 is the only work characterizing DiskANN page writes at syscall level
- FTL GC modeling (FAST/USENIX tradition): extensive work on GC for general workloads, but none applied to graph ANN specifically

**Exact difference**: We provide the first page-lifecycle characterization for graph ANN workloads and use it to determine ZNS feasibility — a question nobody has asked because nobody had the data.

**Why focused**: One question (is ZNS-ANN feasible?), one dataset (M0-M3), one methodology (zone-packing simulation), one deliverable (phase transition characterization).

## Claim-Driven Validation Sketch

### Claim 1: Page-rewrite dynamics exhibit a phase transition with graph density
- **Minimal experiment**: Plot temporal_rewrite_factor, rewritten_page_fraction, and page-lifetime survival curves across all 4 (system, n) points. Show the transition from mostly-new-pages (50K) to mostly-rewrites (400K).
- **Baselines**: Compare against synthetic workloads (uniform random page rewrites, Zipfian hot pages) to show graph ANN has a distinctive rewrite pattern.
- **Metric**: Temporal rewrite factor, page-lifetime distribution shape, rewritten page fraction.
- **Expected evidence**: Clear non-linear growth in rewrite intensity between n=100K and n=400K, with OdinANN (R=96) showing steeper transition than DGAI (R=32).

### Claim 2: GC write amplification crosses practical thresholds at identifiable boundaries
- **Minimal experiment**: Run zone-packing simulation across (zone_size ∈ {256MB, 512MB, 1GB, 2GB}, OP ∈ {0.05, 0.10, 0.15, 0.20, 0.28}) for all 4 data points. Compute WA for GREEDY and OPTIMAL policies.
- **Baselines**: Compare GREEDY vs OPTIMAL to bound the gap that a smart zone allocation policy (ZoneEpoch-ANN) could close.
- **Metric**: GC write amplification factor.
- **Expected evidence**: DGAI 50K stays below 2× WA for all zone sizes; OdinANN 400K exceeds 5× WA for small zones with low OP; the OPTIMAL-GREEDY gap indicates room for intelligent reclamation policies.

### Claim 3: Degree budget R is the dominant factor in ZNS tractability
- **Minimal experiment**: Fix zone geometry, vary system (R=32 DGAI vs R=96 OdinANN) and show WA scales super-linearly with R due to repair fan-out.
- **Baselines**: Linear extrapolation from R to predicted WA.
- **Metric**: WA as function of R.
- **Expected evidence**: R=96 has >3× the WA of R=32, not just 3× (which would be linear), because higher R means more page collisions and shorter page lifetimes.

## Experiment Handoff Inputs
- **Must-prove claims**: Phase transition exists; GC WA crosses practical thresholds; R is dominant factor.
- **Must-run ablations**: Zone size sensitivity, OP ratio sensitivity, GREEDY vs OPTIMAL gap.
- **Critical datasets**: M3 page-version traces for DGAI and OdinANN at n ∈ {50K, 100K, 200K, 400K}.
- **Highest-risk assumptions**: (1) M3 traces from SIFT-10M are representative of real workloads. (2) Zone-packing simulation accurately models ZNS GC behavior. (3) The 400K scale is sufficient to capture the asymptotic trend.

## Compute & Timeline Estimate
- **Estimated compute**: < 10 CPU-hours total (simulation only, no GPU needed)
- **Data / annotation cost**: Zero — M0-M3 data already collected
- **Timeline**: 
  - Week 1-2: Page-version lifecycle extraction + zone-packing simulator implementation
  - Week 3: Parameter sweep + GC write amplification analysis
  - Week 4: FEMU validation (optional)
  - Week 5-6: Paper writing + visualization
