# Refinement Report

**Problem**: GC feasibility boundary for graph ANN update workloads on ZNS SSDs
**Date**: 2026-07-18
**Rounds**: 3 / 5 (converged at stable score)
**Final Score**: 6.4/10
**Final Verdict**: REVISE (remaining issues are implementation-level, not directional)

## Problem Anchor
What is the GC write amplification feasibility boundary for disk-resident graph ANN update workloads on ZNS SSDs?

## Output Files
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Final proposal: `refine-logs/FINAL_PROPOSAL.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Experiment tracker: `refine-logs/EXPERIMENT_TRACKER.md`

## Score Evolution

| Round | PF | MS | CQ | FL | Feas | VF | VR | Overall | Verdict |
|-------|----|----|----|----|------|----|-----|---------|---------|
| 1 (self) | 9 | 6 | 7 | 7 | 9 | 6 | 5 | 7.0 | REVISE |
| 2 (Codex) | 9 | 6 | 5 | 7 | 7 | 6 | 5 | 6.4 | REVISE |
| 3 (Codex) | 6.5 | 6.5 | 6.5 | 6 | 6.5 | 6.5 | 6 | 6.4 | REVISE |

## Method Evolution Highlights
1. **Most important narrowing**: "Does graph ANN work on ZNS?" → "Write-side GC feasibility boundary"
2. **Most important correction**: "Quasi-uniform = hardest case" overclaim → controlled skewness effect
3. **Most important addition**: FEMU validation + controlled trace transformation experiment

## Pushback / Drift Log
| Round | Reviewer Said | Author Response | Outcome |
|-------|---------------|-----------------|---------|
| 2 | "Quasi-uniform → hardest case" unproven | Dropped. Replaced with controlled transformation | Accepted |
| 2 | B-tree comparison unsupported | Dropped entirely | Accepted |
| 3 | Problem anchor drift | Narrowed anchor to write-side only | Accepted |
| 3 | Oracle is unproven lower bound | Dropped to appendix | Accepted |

## Remaining Weaknesses
1. Pseudocode completeness — resolves during implementation
2. Only 2 systems, 1 dataset — stated as limitation; extending is future work
3. FEMU timeline uncertainty — mitigated by week-1 smoke test gate
4. Controlled transformation confound — acknowledged explicitly
