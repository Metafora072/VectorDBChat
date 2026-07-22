# ARIS Idea Creator — Candidate Funnel

Date: 2026-07-22

Eleven mechanisms were generated from an explicit background → phenomenon → formal problem → objective-gap chain. The table records the result after the first mechanism-level filter; later novelty review is stricter.

| Rank | Candidate | New objective / property | First-pass verdict | Reason |
|---:|---|---|---|---|
| 1 | Trajectory-Stable ANN | Cumulative and terminal divergence from an exact feedback trajectory under a total search budget | PASS to novelty review | Per-query recall does not express endogenous query-state drift. |
| 2 | Spectral-Fidelity kNN Graph | Laplacian/diffusion fidelity of an approximate kNN graph under distance-computation budget | Conditional PASS to novelty review | Edge recall can ignore globally important missing edges. |
| 3 | Query-Coverage Budgeted Backfill | Query-weighted top-k critical-risk coverage during embedding migration | HOLD | Must beat FastFill, not merely replace uncertainty with another priority score. |
| 4 | Globally Budgeted Batch ANN | Batch-level utility under one shared comparison/I/O budget | HOLD/KILL | Likely reducible to adaptive ef/search scheduling. |
| 5 | Query-Tube Certified ANN | Candidate coverage for all queries on a curve/tube | KILL | Continuous/moving kNN and safe-region work already occupies the mechanism. |
| 6 | Conformal Candidate-Superset ANN | Calibrated probability that a returned superset contains true top-k | KILL | ConANN directly covers the formulation. |
| 7 | Distributionally Robust Workload Graph | Worst-window/CVaR recall under future query mixtures | KILL | GATE, CleANN, RoarGraph, LIRA, Quake and hardness repair make this another workload-aware graph. |
| 8 | Query-Weighted Multi-Metric ANN | ANN for arbitrary online mixtures of several distances | KILL | Weighted-space and multi-metric ANN have direct theory/index precedents. |
| 9 | Progressive-Coordinate ANN | Allocate dimension reads by top-k decision risk | KILL | ADSampling, RaBitQ, MRQ and adaptive distance computation are mature. |
| 10 | Late-Interaction Token-Budget ANN | Allocate probes across MaxSim query tokens | KILL | PLAID, XTR, WARP, MUVERA, GEM and the local multi-vector negative result crowd it. |
| 11 | Large-k ANN | Collector/rerank optimization for very large k | KILL | BBC (2026) directly addresses large-k ANN. |

## Open-generation discipline

Rejected candidates were not retained by adding an LSM, cache, RL controller, GNN, bandit, new edge score, new beam width, or SSD port. A candidate advanced only when the optimization target itself differed from independent top-k recall/latency.
