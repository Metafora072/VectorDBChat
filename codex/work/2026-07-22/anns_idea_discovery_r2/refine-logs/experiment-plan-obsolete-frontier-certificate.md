# OBSOLETE — TraceGuard Frontier-Certificate Experiment Plan

> Superseded after Round 2 found that a discovered true top-k point cannot be missing from the current heap in standard exact-distance graph search. Do not execute this plan. It is retained only as an audit trail.

Status: **A0 only until all Kill gates pass**
Compute constraint: CPU + commodity NVMe, no GPU training

## 1. Claims and required evidence

| ID | Intended claim | Minimum evidence | Kill condition |
|---|---|---|---|
| C1 | Independent recall hides causal feedback-trajectory loss. | Exact-reference, direct-error, pure-state-drift, and end-to-end paths on two datasets; high-recall operating points. | Terminal loss <15 points, disappears after controls, or occurs only on one toy law. |
| C2 | Discovered frontier alternatives often cover feedback-critical exact misses. | Complete-set event `Omega_t^m`, not per-object recall, for `m=1,2`; coverage vs effort and query strata. | Coverage <90% where intervention matters. |
| C3 | Feedback push-forward radius contains risk information beyond single-query hardness. | Matched-pair and multivariate tests controlling local recall, exact margin, visited nodes, and DARTH-style hardness. | No significant incremental predictive value or effect is explained by margin. |
| C4 | Result-sensitive stopping improves the trajectory at equal total cost. | Uniform, margin, hardness, myopic state-risk, TraceGuard, and oracle at equal distance-equivalent work and wall-clock. | <25% improvement over strongest baseline, overhead reverses the result, or online retains <50% of oracle gain. |

## 2. Causal metric decomposition

For every step, compute these four paths with deterministic tie handling:

1. **Exact reference:** exact search at the exact-reference query, `Exact(q_t*)`.
2. **Direct ANN error:** approximate versus exact result at the same approximate-path query, `ANN(q_t)` versus `Exact(q_t)`.
3. **Pure state drift:** exact result at approximate-path versus exact-reference queries, `Exact(q_t)` versus `Exact(q_t*)`.
4. **End to end:** `ANN(q_t)` versus `Exact(q_t*)`.

Primary metrics:

- one-step state error `||F(s_t, ANN(q_t)) - F(s_t, Exact(q_t))||`;
- trajectory state divergence `||s_t-s_t*||`;
- cumulative retrieval regret `sum_t [1-overlap@k(Exact(q_t), Exact(q_t*))]`;
- terminal exact-reference overlap and task success;
- complete frontier coverage `1[Omega_t^m]`;
- distance computations, controller vector operations, CPU time, and page reads.

Report means, medians, P10/P90, 95% bootstrap confidence intervals over initial-query trajectories, and paired randomization tests for controller comparisons. Trajectories, not individual steps, are the resampling unit.

## 3. Data and feedback laws

### A0 datasets

- **SIFT100K/1M, 128D:** preserve the existing pilot as a regression test; use a larger 1M confirmation subset if memory permits.
- **GloVe-200 or Deep1M:** a semantically/geometrically different pre-generated embedding corpus.
- **One label-grounded cell:** use available class/category labels to define positive/negative Rocchio feedback from retrieved items. If no suitable local labeled corpus is already cached, use a public pre-generated text embedding set and cache only embeddings/labels, not a model.

### Feedback laws

- centroid/query-by-example: move toward the mean of the top positive items;
- standard Rocchio: anchored query plus positive centroid minus negative centroid;
- label-grounded Rocchio: positives/negatives determined by corpus labels rather than a hand-chosen rank rule.

Keep horizon `H in {8,16}` and `k in {10,50}`. The formal theorem covers only affine/additive set feedback. Other agent updates are out of scope.

## 4. ANN families and effort checkpoints

- **HNSW** via the existing CPU implementation, with resumable/geometric checkpoints.
- **Vamana/DiskANN-family CPU search** if the existing PipeANN build exposes visited/frontier state without invasive index changes. Otherwise use a second HNSW graph configuration only for A0 and require Vamana for the full paper.
- Exact reference: chunked CPU brute force for A0 subsets, with reproducible ground-truth caches.

Effort ladder: low floor followed by geometric expansion checkpoints, selected before looking at terminal outcomes. Record discovered unresolved candidates at each checkpoint. Cap `|U|=32` initially and sweep 16/32/64 only after the main mechanism passes.

## 5. Baselines

1. Fixed uniform effort per step.
2. Equal total budget with current exact/discovered boundary margin.
3. DARTH-style or strongest implementable per-query hardness score.
4. Myopic branch radius without horizon amplification.
5. TraceGuard conditional branch radius with the simple online shadow price.
6. Offline oracle allocation over the same effort ladder.

Orthogonal cache, query reuse, and entry-point reuse are not main baselines because they optimize reusable work, not trajectory fidelity. They may appear only as a final compatibility check.

## 6. Ablations

- remove the feedback push-forward and allocate using frontier size only;
- replace discovered alternatives with random visited points;
- use single-miss `m=1` versus multi-miss `m=2`;
- ignore controller vector-operation cost;
- remove the horizon amplification weight;
- oracle exact alternatives versus discovered frontier alternatives;
- stratify by contractive versus expansive feedback coefficients;
- matched current-query hardness with high versus low branch radius.

## 7. One-week A0 run order

| Day | Milestone | Output and decision |
|---|---|---|
| 1 | Refactor the pilot to emit all four causal paths, frontier snapshots, distance counts, and deterministic trace files. | Unit tests on tiny exact-search cases; reproduce prior SIFT100K table. |
| 2 | Measure `Omega_t^m` and radius tightness across HNSW effort checkpoints. | **Gate 1:** Kill immediately if complete coverage is <90% in the high-recall intervention band. |
| 3 | Add GloVe/Deep and label-grounded feedback; run phenomenon matrix. | **Gate 2:** Kill toy-only behavior or <15-point terminal separation. |
| 4 | Implement uniform, margin, hardness, and oracle effort allocation; create matched-query analysis. | **Gate 3:** Kill if branch radius adds no predictive information. |
| 5 | Implement the minimal online shadow-price stopping rule and account for its full CPU overhead. | **Gate 4:** require >=25% terminal-divergence reduction at equal wall-clock. |
| 6 | Repeat seeds/configurations; bootstrap confidence intervals; inspect tails and failure strata. | Check online/oracle fraction and stability. |
| 7 | Freeze A0 report and issue PASS/HOLD/KILL without adding rescue components. | Promote only if all gates pass. |

## 8. Full-paper experiments after a positive A0

- Scale to SIFT1M/Deep1M plus a 1–10M text embedding corpus.
- Use HNSW and Vamana/DiskANN, including an NVMe-backed configuration.
- Test at least 1,000 independent trajectories, three index seeds/configurations, `k={10,50}`, and horizons 8–32.
- Compare quality–latency and quality–distance Pareto frontiers, not one chosen budget.
- Evaluate frontier coverage calibration across datasets and identify the regime where the conditional bound is invalid.
- Add one public relevance-feedback/session trace or a benchmark with grounded positive/negative labels.
- Report controller overhead, memory, page reads, and sensitivity to frontier cap/checkpoint spacing.
- Include a negative regime (contractive feedback or very large margins) where uniform search should be sufficient.

## 9. Resource budget

### A0

- 16–32 CPU cores, 64–128 GB RAM.
- 12–36 aggregate CPU-hours for the core matrix; allow up to 72 CPU-hours with repetitions.
- Less than 100 GB additional NVMe for embeddings, exact neighbors, indices, and traces.
- GPU-hours: 0.

### Full study

- 1–2 weeks on the same class of host.
- 100–300 GB NVMe; 100–300 aggregate CPU-hours depending on exact-reference caching.
- No representation training; all embeddings are pre-generated.

## 10. Venue routing

- **AAAI/IJCAI:** best initial fit if the result emphasizes sequential decision quality, clean formalization, and broad CPU experiments.
- **NeurIPS/ICML:** plausible only if the result-sensitive signal has a clear statistical/theoretical separation from single-query hardness and survives strong task-grounded evaluation.
- If the main contribution becomes an index interface or I/O optimization, reroute to a systems/database venue rather than forcing the current claim.
