# Round 3 Refinement

## Problem Anchor (REVISED — narrowed per reviewer drift warning)
- **Bottom-line problem**: What is the GC write amplification feasibility boundary for disk-resident graph ANN update workloads on ZNS (append-only) SSDs? Specifically: at what rewrite intensity does GC write amplification exceed practical thresholds, making ZNS an unsuitable storage medium for dynamic graph ANN indexes?
- **Must-solve bottleneck**: Graph ANN inserts trigger scattered, near-uniform page rewrites. On ZNS, each rewrite appends a new version. GC must reclaim old versions. Nobody has measured the resulting WA for graph ANN workloads.
- **Non-goals**: (1) Answering the full "does graph ANN work on ZNS" question (which includes read performance, query-update interference, tail latency). (2) Building a ZNS-ANN system. (3) Optimizing DiskANN.
- **Constraints**: M0-M3 data (re-instrumented with per-write trace), 5-6 weeks, EuroSys/FAST.
- **Success condition**: Quantitative WA boundary for observed DGAI and OdinANN workloads on SIFT-10M, with controlled evidence that page-touch skewness affects WA.

## Anchor Check
- Drift corrected: narrowed from "work on ZNS" to "write-side GC feasibility boundary"
- Title updated to match: "GC Feasibility Boundary for Graph ANN Update Workloads on Append-Only Storage"

## Changes Made

### 1. Problem Anchor Narrowed (accept drift correction)
Explicit non-goal: full system viability including reads. This paper answers the WRITE-SIDE question only. The paper's conclusion section can frame the remaining questions (read path, concurrency, tail latency) as future work.

### 2. Claims Scoped to Observed Traces
- All claims now qualified with "for the observed DGAI and OdinANN workloads on SIFT-10M"
- "Graph ANN" as a workload CLASS claim removed
- Generalization beyond observed data explicitly noted as limitation

### 3. Oracle Dropped to Optional Appendix
- Main paper uses only Greedy and Cost-Benefit (two well-understood, citable policies)
- Oracle moved to appendix as "offline reference bound" — no lower-bound claim

### 4. ρ* Operationalized
- ρ = mean versions per page (computed from trace)
- Available ρ values: {1.04, 1.24, 1.99, 5.00} from M3 data, plus {intermediate values from n=100K and n=200K data points}
- T = 3 (industry-standard threshold: ZNS deployment guides recommend WA < 3× for sustained workloads)
- Boundary identification: linear interpolation between adjacent ρ points where WA crosses T
- If WA does not cross T within observed range: report extrapolation slope and projected crossing point (or "no crossing in observed range")
- If WA is not monotone: report all crossings and note non-monotonicity

### 5. Claim 3 Narrowed to Observed Effect
- Changed from "skewness causes higher WA" to "in our controlled trace family, redistributing version counts to increase Gini while fixing total writes, total pages, mean versions/page, and temporal assignment model produces lower WA"
- Explicitly note confound: temporal locality and burstiness may covary with Gini in real workloads
- This is an OBSERVED EFFECT in a controlled setting, not a proven causal mechanism

### 6. Related Work Positioning Added
- SSD GC modeling: Desnoyers (2012) — general workload WA models; He et al. (FAST 2017) — workload-aware GC. Neither studies graph ANN.
- ZNS index co-design: B+-tree on ZNS (TACO 2026). Tree indexes only; no graph ANN.
- Graph ANN write characterization: Our M0-M3 (2026). Only existing syscall-level write attribution for graph ANN. No prior GC feasibility analysis.
- Log-structured ANN: LSM-VEC variants. Use log structure on conventional SSD, not ZNS.
- "First" claim scoped: "first GC feasibility analysis for graph ANN update workloads on append-only storage, using the only existing syscall-level page-write trace dataset for this workload class."
