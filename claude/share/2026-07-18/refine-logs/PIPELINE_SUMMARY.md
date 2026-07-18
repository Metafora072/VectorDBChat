# Pipeline Summary

**Problem**: GC feasibility boundary for graph ANN update workloads on ZNS (append-only) SSDs
**Final Method Thesis**: Replay syscall-level per-write page traces through a zone-packing simulator with Greedy and Cost-Benefit GC policies, validated against FEMU. Show low page-touch skewness in observed workloads and quantify the WA threshold-crossing boundary.
**Final Verdict**: REVISE (converged — remaining issues are implementation-level)
**Date**: 2026-07-18

## Final Deliverables
- Proposal: `refine-logs/FINAL_PROPOSAL.md`
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Experiment tracker: `refine-logs/EXPERIMENT_TRACKER.md`
- Refinement report: `refine-logs/REFINEMENT_REPORT.md`

## Contribution Snapshot
- Dominant: First GC feasibility analysis for graph ANN update workloads on append-only storage (scoped to observed DGAI/OdinANN on SIFT-10M)
- Supporting: Controlled trace transformation showing skewness redistribution affects WA
- Explicitly rejected: "Hardest case" overclaim, B-tree comparison, workload-class generalization, read-side analysis

## Must-Prove Claims
- C1: WA crosses T=3 at identifiable ρ* (threshold-crossing boundary)
- C2: Observed Gini 0.03-0.29 (descriptive, low skewness)
- C3: Lower Gini → higher WA in controlled setting (with confound caveat)

## First Runs to Launch
1. Re-instrument M3 trace emission (2 days)
2. FEMU smoke test (1 day, parallel with #1)
3. Re-collect 8 traces: DGAI × {50K, 100K, 200K, 400K} + OdinANN × same
4. B2: Descriptive statistics (immediate once traces available)
5. Implement simulator + B1: Full sweep (week 2-3)

## Main Risks
- **Risk**: Temporal trace re-instrumentation may require more than expected code changes
  **Mitigation**: M3 already intercepts pwrite64; adding seq counter is minimal
- **Risk**: No clear ρ* crossing (WA monotonically below or above T=3)
  **Mitigation**: Report curve shape + functional fit; still publishable
- **Risk**: FEMU setup takes too long
  **Mitigation**: Week-1 smoke test gate; fallback to simulation-only with stated limitation

## Next Action
- Proceed to trace re-instrumentation and simulator implementation
- Use `/run-experiment` when ready to execute B1-B4
