# DGAI Selective Recoupling / Layout Debt Characterization Tracker

- Gate: `gpt/share/dgai_recoupling_layout_debt_opportunity_gate_0713.md`
- Source commit: `a0179b876a4bd453336dc2893b46ae890f680555` + preserved local instrumentation
- Raw-data root: `/home/ubuntu/pz/VectorDB/data/VectorDB/dgai_recoupling_layout_debt`
- System-disk policy: no build tree, index copy, or raw trace outside the raw-data root

| Stage | State | Evidence |
|---|---|---|
| C0 unified instrumentation | complete | SIFT 10,000-query and GIST 1,000-query formal traces; counter/sequence consistency true |
| C1 selective-recoupling oracle | complete | held-out 1/5/10% Pareto curves on SIFT and GIST; train/eval IDs disjoint |
| C2 strong baselines | complete | B0--B5; LRU/vector-hot dominate capsule oracle at 10% |
| C3 layout-debt progression | complete (mixed streams) | uniform and clustered delete+reinsert streams through 20%; active records remain 900k |
| C4 fresh/simple maintenance | complete | M0--M4 same-graph replay; fresh never improves current; adjacency gain shrinks with updates |
| SIFT-900K characterization | complete | uniform + clustered, aligned + separate regions; capsule lifecycle and update cost included |
| second dataset (GIST-900K) | complete for C0--C2; C3--C4 early-stopped | cross-dataset capsule result confirms strong-baseline failure |
| result-to-claim | complete | `claim_supported=no`, confidence high, recommendation kill |
| joint-gate report | complete | `codex/share/dgai_recoupling_layout_debt_characterization_r1_0713.md` |

## Current invariants

- DecoupleVS is related work only, not an executable baseline.
- Base DGAI remains the sole source of truth; C1 models derived, revocable capsules.
- Capsule selection uses training traces only; all reported opportunity metrics use held-out queries.
- Fresh-layout comparison preserves the same logical graph and recall.
- Stop after characterization and return evidence to GPT/PZ; do not implement a controller or full system.

## Early-stop boundary

- Directly executed uniform mixed and clustered mixed update streams; both contain real delete+reinsert operations and cover aligned/separate query regions.
- Insert-only/delete-only full checkpoint streams and GIST C3/C4 were not executed after both core claims were falsified. They are recorded as limitations, not reported as completed experiments.
- Final route: kill selective recoupling and dynamic layout debt; any graph-quality follow-up requires a new gate.
