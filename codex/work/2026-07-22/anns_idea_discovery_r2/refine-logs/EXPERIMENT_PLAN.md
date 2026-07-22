# Trajectory-Stable ANN — RETHINK Mechanism Pre-Gate

Status: **HOLD-RETHINK; not a full A0**
Compute: CPU + commodity NVMe, no training or GPU

## Purpose

The exact-reference trajectory problem remains plausible, but the frontier-certificate mechanism has been killed. This plan tests the only thin-layer observable left on standard HNSW/Vamana: whether **realized feedback-summary changes across fixed search blocks** predict residual local state error and enable a stopping rule materially better than ordinary result stability or hard-query control.

Passing this pre-gate does not establish novelty. Failing it kills Route A as `KILL-DYNAMIC-EF`.

## Observable and formal scope

At geometric effort checkpoints `b_0 < ... < b_L`, let `C_l` be the current top-k result and define

`z_l = ||F(s_t, C_l) - F(s_t, C_{l-1})||`.

Use only affine/additive feedback (centroid and Rocchio). `z_l` is a realized, computable displacement after paying for block `l`; it is not an unseen-object certificate and is not assumed monotone. A minimal policy uses the last one to three `z_l` values, remaining budget, and a mandatory future-step reserve to decide whether to buy the next block.

## Claims and gates

| ID | Claim tested | Evidence | Hard failure |
|---|---|---|---|
| P1 | High local recall can coexist with causal exact-reference trajectory loss. | Four-path decomposition on two datasets and a label-grounded feedback cell. | <15-point terminal loss or open-loop controls explain it. |
| P2 | Realized result-summary changes predict residual exact-local summary error beyond existing stopping signals. | Held-out trajectories; matched local recall, top-k Jaccard stability, margin, visited nodes, and DARTH-style hardness. | No significant incremental prediction or only one dataset. |
| P3 | A result-change stopping rule improves terminal fidelity at equal total cost. | Uniform, patience/top-k stability, margin, hardness, result-change, and oracle policies. | <25% over strongest baseline, or gain disappears at equal wall-clock. |

## Causal decomposition

For each trajectory step distinguish:

1. `Exact(q_t*)`: exact reference trajectory;
2. `ANN(q_t)` versus `Exact(q_t)`: direct ANN error at the same approximate-path query;
3. `Exact(q_t)` versus `Exact(q_t*)`: pure query-state drift;
4. `ANN(q_t)` versus `Exact(q_t*)`: end-to-end error.

Primary outputs are one-step feedback-state error, residual local summary error after each checkpoint, cumulative exact-result regret, terminal exact-reference overlap, downstream label discovery, distance-equivalent work, and CPU wall-clock. Resample whole trajectories for 95% bootstrap confidence intervals.

## Data and feedback

- SIFT100K/1M as a regression and geometric dataset.
- GloVe-200, Deep1M, or another locally available pre-generated semantic embedding corpus.
- At least one label-grounded Rocchio cell where positive/negative feedback uses corpus labels; rank-picked positives alone are insufficient.
- `k in {10,50}`, horizon `H in {8,16}`; at least 200 trajectories per main cell in the pre-gate.

## ANN and baselines

- HNSW with resumable or replayable geometric effort checkpoints.
- A second CPU ANN family for a positive follow-up; do not delay the first Kill gate for invasive integration.
- Exact local/reference results from cached brute force on the selected subsets.

Baselines:

1. fixed uniform effort;
2. patience based on unchanged top-k/Jaccard across blocks;
3. current boundary margin;
4. DARTH-style single-query hardness;
5. result-change history `z_l`;
6. offline oracle over the same checkpoint ladder.

All policies receive the same minimum future-step reserve. Charge checkpoint control, result hashing/Jaccard, feedback summary updates, vector distances, and SSD reads.

## Three-day run order

| Day | Work | Decision |
|---|---|---|
| 1 | Extend the pilot with four-path decomposition and geometric result snapshots; reproduce the prior SIFT table. | Stop on regression failure. |
| 2 | Fit no trained model: evaluate conditional bins, matched pairs, and a fixed trailing-change rule on development trajectories; lock thresholds. | Kill if `z_l` adds no information beyond patience/margin/hardness. |
| 3 | Test locked policies on the second dataset and label-grounded cell with full wall-clock accounting. | Continue only for >=25% terminal-divergence reduction over the strongest baseline. |

## Resource budget

- 16–32 CPU cores, 64–128 GB RAM.
- 12–36 aggregate CPU-hours, up to 72 with repetitions.
- Less than 100 GB additional NVMe.
- GPU-hours: 0.

## Positive-result follow-up

Only after all three gates pass:

- reproduce with Vamana/DiskANN and an NVMe-backed index;
- scale to 1–10M vectors and at least 1,000 trajectories;
- audit whether the gain is just an early-exit patience variant;
- conduct a fresh novelty review of “feedback-summary convergence stopping” before claiming a paper mechanism;
- then design the full experiment matrix.

Route B—an index exposing admissible unseen-region bounds—is a separate idea requiring separate novelty and bound-tightness checks. It is not part of this plan.
