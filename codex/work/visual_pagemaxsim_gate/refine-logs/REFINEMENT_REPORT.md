# Refinement Report

**Problem**: PageMaxSim P2失败是否只是single-ball设计过弱

**Date**: 2026-07-12

**Rounds**: 4

**Final Score**: 9.0 / 10

**Final Verdict**: READY to execute Stage A CPU-only gate

## Output Files

- Final proposal: `FINAL_PROPOSAL.md`
- Review summary: `REVIEW_SUMMARY.md`
- Reviews/refinements: `round-*-review.md`, `round-*-refinement.md`
- Score history: `score-history.md`

## Final Thesis

- P2只证伪single centroid-radius，不足以证明所有exact synopsis失败。
- 最小新机制是shared-codebook union-of-residual-balls，不是更复杂scheduler。
- Stage A先在K=64/256分解multi-modal与residual-direction slack。
- f9-int8不能安全跳页就立即Kill；raw-only不允许存活。
- 完整persistent/DRAM/query-state/CPU成本必须形成非支配点。

## Remaining Weaknesses

- 方法是否有效完全未知，Stage A很可能仍因residual-direction looseness失败。
- PLAID/WARP等价机制需在任何正结果后、请求P3前核实。
- 64/16 replay只适合作为机制gate，不是论文级evaluation。
