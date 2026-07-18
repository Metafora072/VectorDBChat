# Round 2 Refinement

## Problem Anchor
(Verbatim — unchanged)

## Anchor Check
- Original bottleneck: page-rewrite patterns of graph ANN on append-only storage → GC feasibility
- Revised method still addresses it: YES
- Reviewer suggestions rejected as drift: NONE — all on-target

## Simplicity Check
- Dominant contribution: first page-lifecycle characterization for graph ANN, with GC feasibility boundary determination
- Removed: "hardest case" overclaim, unsupported B-tree comparison, vague "phase transition"
- Added: formal simulator specification, controlled trace transformation experiment
- Still the smallest adequate route: one question, one dataset, one simulator, one validation

## Changes Made

### 1. Formal Simulator Specification (CRITICAL)
- Reviewer said: Simulator state machine, GC trigger, placement, accounting all undefined.
- Action: Added complete simulator specification as a formal state machine.

### 2. Contribution Claim Narrowed (CRITICAL)
- Reviewer said: "Quasi-uniform → hardest case" is unproven causal jump.
- Action: 
  - Dropped "structurally the hardest case for ZNS GC" from all claims
  - Replaced with testable claim: "Graph ANN's low page-touch skewness suppresses hot/cold zone separation, producing higher GC WA than workloads with equivalent mean rewrite factor but skewed touch distributions"
  - Made this testable via controlled trace transformation: fix mean rewrite factor, vary Gini, measure WA
  - Gini/top-k now descriptive evidence, not causal mechanism

### 3. "Graph Density" → "Graph Scale" (CRITICAL)
- Reviewer said: n is scale, not density.
- Action: Replaced all instances of "graph density" with "graph scale (n)" or "rewrite intensity." The control variable is n (number of inserted replacements), which jointly varies graph scale, storage occupancy, and rewrite intensity.

### 4. "Phase Transition" → "Feasibility Boundary" (IMPORTANT)
- Reviewer said: "Phase transition" undefined; just picking arbitrary WA thresholds.
- Action: Replaced with formal definition:
  - Control variable: rewrite intensity (mean versions per page, derived from n)
  - Response variable: GC write amplification factor
  - Boundary identification: the rewrite intensity ρ* at which WA(ρ*, zone_size, OP) first exceeds a target T ∈ {2, 3, 5}
  - Stability criterion: boundary location varies <15% across Greedy and Cost-Benefit policies
  - If no stable boundary exists (WA grows smoothly), report the WA curve shape and functional fit instead

### 5. FEMU Validation Protocol (IMPORTANT)
- Reviewer said: Simulator vs FEMU with same GC is near-circular.
- Action: FEMU uses its own internal GC (the FTL-less ZNS block layer), which is independent of our simulator's GC implementation. Comparison items:
  1. Total host writes (should match exactly — same trace)
  2. Total zone resets (independent metric)
  3. Total bytes written to media (includes GC copies)
  4. Per-zone valid-page fraction at reset time (distribution)
  5. Final WA factor
  
  Validate on 3 representative points: low-WA (DGAI 50K), medium (DGAI 400K), high (OdinANN 400K). Report per-item delta.

### 6. Dropped B-tree Comparison (IMPORTANT)
- Reviewer said: No B-tree data, can't claim "unlike B-tree."
- Action: Removed all B-tree comparison claims. Gini comparison is now against synthetic baselines only (uniform, Zipfian). The paper does NOT claim graph ANN is harder than B-tree — it characterizes graph ANN's own feasibility boundary.

---

## Revised Proposal (v3)

# Research Proposal: ANN-on-ZNS Feasibility Frontier — Page-Lifecycle Characterization and GC Feasibility Boundary for Graph ANN on Append-Only Storage

## Problem Anchor
(Unchanged from v1)

## Technical Gap
(Unchanged, with B-tree comparison removed)

## Method Thesis
- **One-sentence thesis**: We characterize a GC feasibility boundary for disk-resident graph ANN on append-only storage by replaying syscall-level page-write traces through a formally specified zone-packing simulator, showing that graph ANN's low page-touch skewness suppresses hot/cold zone separation and quantifying the rewrite intensity at which GC write amplification exceeds practical thresholds.
- **Why smallest adequate intervention**: One question, one re-instrumented dataset, one simulator (validated against FEMU), three claims.

## Contribution Focus
- **Dominant**: First page-lifecycle characterization for disk-resident graph ANN workloads on append-only storage, establishing the GC feasibility boundary as a function of graph scale, degree budget, and zone geometry.
- **Supporting**: Controlled trace transformation showing that page-touch skewness (not just mean rewrite factor) significantly affects GC WA.
- **Non-contributions**: No ZNS-ANN system, no new graph algorithm, no unconditional "hardest case" claim, no B-tree comparison.

## Proposed Method

### Simulator Specification (Formal State Machine)

**State variables**:
- `zones[]`: array of zones, each with capacity Z = zone_size / 4096 page slots
- `zones[i].pages[]`: array of (logical_page_id, write_seq) tuples in append order
- `zones[i].valid_count`: number of pages whose logical_page_id has no later version
- `active_zone_idx`: index of zone currently receiving appends
- `page_location[page_id]`: maps logical page to (zone_idx, slot_idx) of its latest version
- `total_user_writes`: counter
- `total_gc_copies`: counter
- `total_zone_resets`: counter

**Initialization**: 
- Allocate `N_total = ceil(trace_unique_pages × (1 + OP) / Z)` zones
- `active_zone_idx = 0`
- All zones empty

**Per-event processing** (for each trace event `(seq, page_id)`):
1. If `page_id` has a previous location `(z_old, s_old)`:
   - Mark `zones[z_old].pages[s_old]` as invalid
   - Decrement `zones[z_old].valid_count`
2. Append `(page_id, seq)` to `zones[active_zone_idx]`
3. Update `page_location[page_id] = (active_zone_idx, current_slot)`
4. Increment `zones[active_zone_idx].valid_count`
5. Increment `total_user_writes`
6. If `zones[active_zone_idx]` is full:
   - `active_zone_idx = next_free_zone()`
   - If no free zone available: trigger GC

**GC trigger**: When no free zone is available (all N_total zones have at least one page).

**GC procedure**:
1. Select victim zone `v` by policy:
   - **Greedy**: `v = argmin_i(zones[i].valid_count / Z)` (lowest valid fraction)
   - **Cost-Benefit**: `v = argmax_i((1 - u_i) × age_i / (2 × u_i))` where `u_i = valid_count/Z`, `age_i = current_seq - zones[i].last_append_seq`
   - **Oracle (offline)**: `v = argmax_i(next_invalidation_seq[i] - current_seq)` — zone whose next page invalidation is farthest in the future. Requires full trace lookahead. This is an offline LOWER BOUND on WA, not a deployable policy.
2. For each valid page `(page_id, _)` in `zones[v]`:
   - Append to `zones[active_zone_idx]`
   - Update `page_location[page_id]`
   - Increment `total_gc_copies`
   - If active zone fills, switch to next free zone
3. Reset `zones[v]` (clear all slots, valid_count = 0)
4. Increment `total_zone_resets`

**Output metrics**:
- `WA = (total_user_writes + total_gc_copies) / total_user_writes`
- `zone_reset_count = total_zone_resets`
- `victim_valid_fraction_distribution`: histogram of `valid_count/Z` at each GC event

**Warm-up**: Discard first 10% of trace events from WA accounting (pages fill zones before GC begins).
**End effects**: Stop WA accounting when trace ends; do not force-GC remaining zones.

### Structural Distribution Analysis (Descriptive, Not Causal)

For each (system, n) data point, compute descriptive statistics of the page-touch distribution:
1. **Gini coefficient** of page version counts
2. **Top-1%, top-10% touch concentration**
3. **Page-lifetime distribution**: histogram of `death_seq - birth_seq` for each page
4. **Rewrite inter-arrival distribution**: histogram of `seq_i+1 - seq_i` for consecutive writes to the same page

These are DESCRIPTIVE. They characterize the workload but do not directly determine WA. The controlled trace transformation (Claim 3) provides the causal test.

### Controlled Trace Transformation (Claim 3 Validation)

To isolate the effect of page-touch skewness on WA:
1. Take the real graph ANN trace (e.g., DGAI 400K)
2. Fix: total writes, total pages, mean versions per page
3. Vary: page-touch distribution shape by redistributing version counts:
   - **Uniform**: every page gets exactly `mean_ver` versions
   - **Graph-ANN-actual**: the real distribution (Gini ≈ 0.27)
   - **Zipfian(α=1.0)**: heavy-tailed, Gini ≈ 0.82
   - **Bimodal(90/10)**: 90% pages get 1 version, 10% get all extra versions
4. For each synthetic trace, assign version timestamps using the same temporal model (uniform random within the trace duration)
5. Run zone simulator with Greedy + Cost-Benefit policies
6. Compare WA across distributions

**Expected result**: Zipfian and Bimodal traces produce LOWER WA than Uniform and Graph-ANN traces at the same mean rewrite factor, because concentrated rewrites create zones that are either mostly-valid (stable) or mostly-invalid (cheap to reclaim). Graph ANN's near-uniform distribution suppresses this separation.

### Claims (Revised)

**Claim 1 (Feasibility Boundary)**: GC write amplification for graph ANN workloads exhibits a regime transition at an identifiable rewrite intensity ρ*: below ρ*, WA remains below a practical threshold T (e.g., 3×) for standard OP ratios; above ρ*, WA exceeds T and grows rapidly. The boundary ρ* depends on zone geometry and is stable across GC policies.

*Control variable*: rewrite intensity ρ = mean versions per page (varied via graph scale n)
*Response variable*: WA factor
*Boundary*: ρ* such that WA(ρ*, zone_size, OP) = T
*Stability*: ρ* varies <15% between Greedy and Cost-Benefit

**Claim 2 (Workload Characterization)**: Graph ANN page-touch distributions have low skewness (Gini 0.03-0.29) compared to synthetic benchmarks (Zipfian Gini 0.82), indicating that graph ANN repair writes spread near-uniformly across the page space rather than concentrating on hot pages.

*This is a descriptive finding, not a causal mechanism claim.*

**Claim 3 (Skewness Affects GC Efficiency)**: At identical mean rewrite factor, workloads with lower page-touch skewness (like graph ANN) produce higher GC WA than workloads with higher skewness (like Zipfian), because skewed distributions enable hot/cold zone separation. Validated by controlled trace transformation.

*This replaces the overclaimed "hardest case" with a testable comparative statement.*

### FEMU Validation Protocol

**Purpose**: Verify simulator correctness, NOT validate structural claims.

**Procedure**:
1. Select 3 representative traces: low-WA (DGAI 50K, ρ≈1.04), medium (DGAI 400K, ρ≈1.99), high (OdinANN 400K, ρ≈5.0)
2. Convert each page-write trace to a ZNS-compatible block I/O trace (zoned random write workload using `libzbd` or `fio` with `--zonemode=zbd`)
3. Replay through FEMU's ZNS mode
4. Compare 5 independent metrics:
   - Total host write bytes (should match ±0.1%)
   - Total zone resets
   - Total bytes written to media
   - Valid-page fraction at each zone reset (distribution)
   - Final WA factor
5. Report per-metric delta. Simulator accuracy target: WA within 5% of FEMU.

**Note**: FEMU uses a different implementation of page placement and GC than our simulator. Discrepancies reveal modeling assumptions that need calibration.

## Compute & Timeline Estimate
- Re-instrumentation + re-collection: 2 days
- Simulator implementation (including formal spec): 4-5 days
- Parameter sweep + structural analysis: 2-3 days
- Controlled trace transformation: 1-2 days
- FEMU validation (3 points): 3-5 days
- Paper writing + visualization: 7-10 days
- **Total**: 5-6 weeks
- **Compute**: < 30 CPU-hours (simulation + FEMU)
