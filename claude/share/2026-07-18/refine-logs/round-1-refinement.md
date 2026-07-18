# Round 1 Refinement

## Problem Anchor
(Verbatim from round 0)
- **Bottom-line problem**: No one knows whether disk-resident graph ANN (DiskANN-family) can operate on ZNS SSDs, which forbid in-place page overwrites and require sequential-zone-append semantics.
- **Must-solve bottleneck**: Graph ANN inserts trigger cascading neighbor-repair writes that touch many scattered pages. On ZNS, every "overwrite" becomes an append + eventual GC. Nobody has measured the resulting GC pressure for graph ANN.
- **Non-goals**: Building a ZNS-ANN system; optimizing DiskANN's write path; comparing ZNS vs conventional SSD.
- **Constraints**: M0-M3 data, no GPU needed, 4-6 weeks, EuroSys/FAST target.
- **Success condition**: Quantitative GC phase transition characterization.

## Anchor Check
- Original bottleneck: page-rewrite patterns of graph ANN on append-only storage → GC feasibility
- Revised method still addresses it: YES — all changes sharpen the methodology without changing the question
- Reviewer suggestions rejected as drift: NONE — all suggestions are on-target

## Simplicity Check
- Dominant contribution after revision: first page-lifecycle characterization for graph ANN revealing structurally distinctive rewrite distribution + GC phase transition
- Components removed: OPTIMAL (LP/DP) → replaced with known-good Greedy-Future algorithm
- Claim 3 (R is dominant factor) merged into main phase transition claim
- Reviewer suggestions rejected as unnecessary complexity: NONE

## Changes Made

### 1. Temporal Data Resolution (CRITICAL)
- Reviewer said: M3 aggregate histograms don't have per-write temporal ordering needed for zone simulation.
- Action: Two-pronged approach:
  (a) **Primary**: Re-instrument the M3 pipeline to emit a per-write page-ID trace with monotonic sequence numbers. This is a small modification to the existing write interception layer — emit (seq_no, page_id, operation_id) for each pwrite64 call. Re-run for all 4 (system, n) points. Estimated: 1 day instrumentation + 1 day re-collection.
  (b) **Sensitivity**: Also run statistical simulation matching observed distributions for comparison, to validate that the exact ordering doesn't significantly affect WA conclusions.
- Impact: Transforms the simulation from synthetic to trace-driven. Much stronger paper.

### 2. Structural Insight Claim (IMPORTANT)
- Reviewer said: "WA goes up with density" is not surprising. Need to show something structurally unique about graph ANN page lifetimes.
- Action: Add Claim 2 (structural characterization):
  - Graph ANN page lifetimes follow a heavy-tailed distribution driven by graph locality — "hub" pages hosting vertices with high in-degree are rewritten far more frequently.
  - Quantify via: (1) Gini coefficient of page-touch distribution, (2) top-1%/top-10% touch fraction (already available from M2), (3) compare against synthetic baselines (uniform random, Zipfian, sequential).
  - From M2 data: DGAI 400K top-1% pages = 2.8% of touches, top-10% = 20.5%. OdinANN 400K top-1% = 2.7%, top-10% = 20.3%. These are remarkably uniform — NOT heavy-tailed! This itself is a finding: graph ANN repair writes are quasi-uniform across pages, unlike B-tree hot-paths.
  - Implication: quasi-uniform page lifetimes are actually the WORST case for ZNS GC, because there are no "cold" pages that can safely stay in zones long-term. Every zone ages at similar rates.
- Impact: Transforms the paper from "we computed WA" to "we discovered that graph ANN has quasi-uniform page aging, which is structurally the hardest case for ZNS GC."

### 3. Concrete GC Algorithms (IMPORTANT)
- Reviewer said: "OPTIMAL (LP/DP)" is hand-wavy.
- Action: Replace with three concrete policies from the SSD GC literature:
  1. **Greedy**: pick zone with lowest live fraction → reset → copy live pages to new zone
  2. **Cost-Benefit (Rosenblum & Ousterhout, LFS 1992)**: weight live fraction by zone age — prefer old zones with low live fraction
  3. **Greedy-Future (offline upper bound)**: among all zones, pick the one whose next page invalidation is farthest in the future → known to be near-optimal for uniform page sizes
  
  Drop the vague LP. Greedy vs Cost-Benefit vs Greedy-Future gives a tight bound on achievable WA.
- Impact: Methodologically sound, citable, reproducible.

### 4. FEMU Validation (IMPORTANT)
- Reviewer said: Pure simulation is weak for FAST/EuroSys venue.
- Action: Add FEMU ZNS emulation validation:
  1. Replay the per-write page-ID trace through FEMU's ZNS mode
  2. Measure actual zone reset count and bytes written
  3. Compare against our simulator's predictions
  4. Confirm simulator accuracy within 5% of FEMU
  
  Estimated additional effort: 3-5 days (FEMU setup + trace replay tool).
- Impact: Significantly strengthens venue readiness. Moves from "simulation study" to "trace-driven analysis validated against ZNS emulation."

### 5. Revised Claim Structure (IMPORTANT)
- Reviewer said: Claim 3 (R is dominant) is tautological.
- Action: Restructure to 3 claims:
  1. **Phase transition exists**: GC WA crosses practical thresholds at identifiable (n, zone_size, OP) boundaries.
  2. **Structural uniqueness**: Graph ANN page-touch distribution is quasi-uniform (not heavy-tailed), making it structurally harder for ZNS GC than B-tree or LSM workloads.
  3. **Distribution shape determines feasibility**: Two workloads with identical mean rewrite factor but different tail shapes produce significantly different GC WA. Graph ANN's quasi-uniform shape is the critical factor, not just the mean.
- Impact: Each claim is non-obvious and testable.

### 6. GC Trigger Specification (MINOR)
- Reviewer said: GC trigger condition not specified.
- Action: GC triggers when active zone count reaches `floor(total_zones × (1 - OP_ratio))`. Victim selection per the chosen policy (Greedy / Cost-Benefit / Greedy-Future). Live pages in victim zone are copied to the current active zone before zone reset.

---

## Revised Proposal

# Research Proposal: ANN-on-ZNS Feasibility Frontier — Page-Lifecycle Phase Transition in Graph ANN on Append-Only Storage

## Problem Anchor
(Unchanged from round 0)

## Technical Gap
(Unchanged, with one addition)

**Additional gap**: The SSD GC literature extensively studies GC write amplification for general workloads (Desnoyers 2012, He et al. FAST 2017), but no work characterizes GC behavior for graph ANN specifically. Graph ANN's scattered, repair-driven page updates represent a workload class not studied in the GC modeling literature.

## Method Thesis
- **One-sentence thesis**: We characterize a GC phase transition in disk-resident graph ANN on append-only storage by replaying syscall-level page-write traces through a zone-packing simulator with established GC policies, discovering that graph ANN's quasi-uniform page-touch distribution makes it structurally the hardest case for ZNS GC, establishing a feasibility frontier as a function of graph density and zone geometry.
- **Why this is the smallest adequate intervention**: One question, one (re-instrumented) dataset, one simulator, one validation (FEMU).
- **Why timely**: ZNS entering production; B+-tree-on-ZNS published (TACO 2026); graph ANN is the natural next index class to study.

## Contribution Focus
- **Dominant contribution**: First page-lifecycle characterization for graph ANN, revealing quasi-uniform page-touch distribution and the resulting GC phase transition on append-only storage.
- **Supporting contribution**: Trace-driven zone-packing simulator validated against FEMU ZNS emulation.
- **Explicit non-contributions**: No ZNS-ANN system. No new graph algorithm. No end-to-end performance comparison.

## Proposed Method

### Complexity Budget
- **Frozen / reused**: M0-M3 write attribution infrastructure, FEMU ZNS emulator
- **New**: (1) Per-write page-ID trace instrumentation (minor M3 extension), (2) Zone-packing simulator with Greedy/Cost-Benefit/Greedy-Future policies, (3) Structural distribution analysis
- **Tempting additions not used**: Real ZNS hardware, adaptive zone allocation, log-structured indirection layer

### System Overview

```
M3 pipeline (re-instrumented)
    ↓ per-write page-ID trace: (seq_no, page_id, op_id, system, n)
    ↓
[1] Page-Version Lifecycle Extractor
    - birth_time (seq of first write), death_time (seq of next version), lifespan, version_count
    - page_touch_order (global write sequence for zone filling)
    ↓
[2] Structural Distribution Analyzer
    - Gini coefficient of page-touch distribution
    - Top-k% touch concentration
    - Compare against uniform, Zipfian, sequential baselines
    - Page-lifetime survival curves
    ↓
[3] Zone-Packing Simulator
    - Replay page writes in trace order into zones of configurable size
    - GC policies: Greedy, Cost-Benefit, Greedy-Future (offline)
    - Sweep: zone_size ∈ {256MB, 512MB, 1GB, 2GB}, OP ∈ {0.07, 0.14, 0.21, 0.28}
    - Output: WA factor for each (system, n, zone_size, OP, policy) tuple
    ↓
[4] FEMU Validation
    - Replay same trace through FEMU ZNS emulation
    - Compare simulated vs emulated WA
    ↓
[5] Phase Transition Analysis
    - Identify (n, zone_size) boundaries where WA crosses 2×, 3×, 5× thresholds
    - Phase transition heatmaps
    - Structural explanation: why quasi-uniform distribution creates these boundaries
```

### Core Mechanism

**Input**: Re-instrumented M3 per-write traces for DGAI and OdinANN at n ∈ {50K, 100K, 200K, 400K} on SIFT-10M.

**Re-instrumentation** (1 day): Modify the existing write interception layer to emit `(monotonic_seq, page_id, replacement_batch_id)` for each pwrite64/io_uring write. The page_id is `(st_dev, st_ino, aligned_4k_offset)` already tracked by M3. Add a monotonic sequence counter. Re-collect all 8 data points (2 systems × 4 scales).

**Processing**:
1. **Lifecycle extraction**: For each page_id, compute birth (first seq), death (seq of next version write to same page_id, or trace end), lifespan = death - birth, version_count.

2. **Structural analysis**: 
   - Compute Gini coefficient of the page-touch-count distribution
   - Compute concentration: fraction of total writes from top-1%, top-10% hottest pages
   - Generate comparison baselines: (a) uniform random — each write picks a uniformly random page from the page pool, (b) Zipfian(α=1.0) — standard hot-page model, (c) sequential — pages are written once in order (best case for ZNS)
   - Compute the same Gini/concentration metrics for baselines and graph ANN

3. **Zone simulation**: 
   - Zone model: each zone holds `zone_size / 4096` pages. Pages are appended in trace order.
   - GC trigger: when number of open zones reaches `floor(total_zones / (1 + OP))`, pick a victim zone.
   - Victim selection:
     - **Greedy**: zone with lowest (live_pages / total_capacity)
     - **Cost-Benefit**: maximize `(1 - utilization) × age / (2 × utilization)` (Rosenblum-Ousterhout)
     - **Greedy-Future** (offline): zone whose next page invalidation is farthest in the future (requires full trace lookahead)
   - Copy live pages from victim to current active zone, reset victim, continue.
   - Track: total pages written (data + GC copies) / total new data pages = WA factor.

4. **FEMU validation**: Convert the page-write trace to a block I/O trace, replay through FEMU's ZNS mode (zoned block device), measure actual zone resets and bytes written. Compare with simulator output.

5. **Phase transition identification**: For each (system, policy), produce a heatmap of WA over (n, zone_size) space. Identify the contour where WA = 2× (tractable), 3× (marginal), 5× (infeasible). Overlay the structural distribution metrics to explain why the boundary falls where it does.

### Failure Modes and Diagnostics
1. **Phase transition is trivially favorable**: Paper becomes "graph ANN works on ZNS." Still valuable as first evidence + structural characterization. Extend to larger scales by modeling.
2. **Phase transition is trivially unfavorable**: Paper becomes "graph ANN requires fundamentally different index semantics for ZNS." Structural analysis explains why. Motivates ZoneEpoch-ANN.
3. **Quasi-uniform distribution hypothesis is wrong** (pages ARE heavy-tailed): Then graph ANN is actually EASIER for ZNS than expected (cold pages act as stable anchors). The structural finding is still novel either way.
4. **FEMU validation diverges from simulator**: Investigate cause (write coalescing, zone reset overhead, device cache). Calibrate simulator. Report gap honestly.

### Novelty and Elegance Argument
**Closest work**:
- B+-tree on ZNS (TACO 2026): tree indexes have naturally sequential writes; graph ANN has scattered writes. Fundamentally different workload class.
- SSD GC modeling (Desnoyers 2012, He et al. FAST 2017): general workload GC models. No graph-ANN-specific characterization.
- DiskANN/PipeANN/OdinANN: assume conventional SSD. No ZNS analysis.

**What's new**: (1) First page-lifecycle dataset for graph ANN. (2) Discovery that graph ANN has quasi-uniform page aging (neither hot-cold like B-tree nor sequential like LSM). (3) GC phase transition characterization specific to this workload class. (4) Validated against FEMU ZNS emulation.

**Why focused**: One workload class (graph ANN), one question (ZNS feasibility), one methodology (trace-driven simulation + emulation validation), one structural insight (quasi-uniform aging). No system building, no new algorithms.

## Claim-Driven Validation Sketch

### Claim 1: GC write amplification exhibits a phase transition with graph density
- **Experiment**: Sweep (n, zone_size, OP) parameter space for both systems. Plot WA heatmaps.
- **Baselines**: Same zone simulator with synthetic traces (uniform, Zipfian, sequential) at matched write volumes.
- **Metric**: WA factor. Phase transition boundary location.
- **Expected**: DGAI stays below 2× WA for most configurations up to 400K. OdinANN crosses 5× WA for small zones at 400K. Transition is sharper than for synthetic baselines.

### Claim 2: Graph ANN page-touch distribution is quasi-uniform, making it structurally the hardest case for ZNS GC
- **Experiment**: Compute Gini coefficient and top-k% concentration for all (system, n) points. Compare against B-tree-like (top-heavy), Zipfian, and uniform distributions.
- **Metric**: Gini coefficient. Top-1%/10% touch fraction.
- **Expected**: Graph ANN Gini ≈ 0.1-0.2 (near-uniform), vs B-tree Gini ≈ 0.5-0.7 (concentrated at upper levels). Near-uniform is worst case because all zones age at similar rates → no "safe" cold zones to keep.

### Claim 3: Page-lifetime distribution shape, not just mean rewrite factor, determines GC feasibility
- **Experiment**: Construct two synthetic traces with identical mean rewrite factor but different shapes (one uniform, one heavy-tailed). Run through zone simulator. Show different WA.
- **Metric**: WA factor at identical mean rewrite factors.
- **Expected**: Heavy-tailed distribution has 20-40% lower WA than uniform at the same mean rewrite factor, because cold pages in heavy-tailed distributions create naturally stable zones.

## Compute & Timeline Estimate
- **Re-instrumentation + re-collection**: 2 days
- **Simulator implementation**: 3-4 days
- **Parameter sweep + analysis**: 2-3 days
- **FEMU validation**: 3-5 days
- **Paper writing + visualization**: 7-10 days
- **Total**: 4-5 weeks
- **Compute**: < 20 CPU-hours (simulation + FEMU)
- **No GPU needed**
