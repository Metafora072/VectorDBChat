# Trajectory-Stable ANN — Phenomenon Micro Pilot

Date: 2026-07-22

Status: **positive signal for a full A0, not paper evidence**

## Question

Does ANN error cause additional loss when retrieval results update the next query, beyond the ordinary open-loop error observed by replaying a fixed exact-query trajectory?

## Setup

- Data: first 100,000 SIFT1M base vectors, 128 dimensions.
- Initial queries: first 80 SIFT1M queries.
- Index: HNSW, `M=16`, construction ef 120.
- Result size: `k=10`; horizon: 8.
- Exact reference: brute-force top-10 at every state.
- Feedback laws:
  - `centroid`: move the query toward the centroid of the top three results.
  - `rocchio`: an anchored positive-minus-negative update using the first and last three results.
- Controls:
  - local recall: ANN versus exact top-10 at the ANN trajectory's current query;
  - open-loop recall: ANN on the fixed exact-reference query trajectory;
  - terminal overlap: ANN closed-loop result versus the exact-reference trajectory's terminal result.

Raw output: `trajectory_micro_pilot_100k.json`.

## Results

| Feedback | ef | Local recall | Open-loop recall | Mean terminal overlap | P10 terminal overlap |
|---|---:|---:|---:|---:|---:|
| centroid | 12 | 95.30% | 94.84% | 81.50% | 20.00% |
| centroid | 20 | 97.73% | 97.25% | 89.38% | 40.00% |
| centroid | 40 | 99.48% | 99.39% | 97.63% | 100.00% |
| centroid | 80 | 99.97% | 99.91% | 99.50% | 100.00% |
| rocchio | 12 | 84.92% | 89.41% | 69.13% | 49.00% |
| rocchio | 20 | 91.08% | 94.13% | 76.25% | 50.00% |
| rocchio | 40 | 97.23% | 98.14% | 86.88% | 69.00% |
| rocchio | 80 | 99.38% | 99.59% | 95.50% | 80.00% |

## Interpretation

The pilot exhibits a closed-loop separation. At operating points where ordinary open-loop ANN recall is 94.8–98.1%, terminal overlap with the exact feedback trajectory is only 81.5–86.9%. The loss disappears as ANN recall approaches 100%, which is consistent with error propagation rather than an unrelated implementation defect.

The strongest signal is in the tail: for centroid feedback at ef 12, the tenth-percentile terminal overlap is only 20% despite 95.3% mean local recall. This supports studying trajectory divergence and horizon-aware budget allocation instead of relying only on mean per-step recall.

## Why this is not yet decisive

- Only one geometric dataset and one HNSW build were used.
- Both feedback laws are controlled vector-space operators rather than real interaction traces.
- The experiment did not yet compare equal-total-budget allocation policies.
- It did not separate margin sensitivity from future amplification.
- It reports overlap, not a downstream task outcome.

## Full A0 gate

Proceed only if a one-week A0 can show all of the following:

1. the open-loop versus closed-loop separation on at least two real embedding datasets and two feedback laws;
2. at matched total distance computations, amplification-weighted allocation reduces terminal divergence by at least 25% versus uniform and margin-only allocation;
3. the effect remains after matching mean local recall and cannot be explained by ordinary hard-query detection;
4. at least one standard relevance-feedback trace or task-grounded query update reproduces the phenomenon.

Otherwise: `KILL-TRAJECTORY-STABLE-ANN`.
