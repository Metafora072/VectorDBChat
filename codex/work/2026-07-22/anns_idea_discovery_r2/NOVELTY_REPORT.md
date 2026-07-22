# ARIS Novelty Check — Finalists

Date: 2026-07-22

## N1. Trajectory-Stable ANN

### Claim checked

Given an endogenous query sequence whose next state depends on the current retrieved top-k, allocate a total ANN budget to control cumulative or terminal divergence from the exact-retrieval counterfactual trajectory.

### Closest mechanisms and boundary

| Work | Overlap | Remaining boundary |
|---|---|---|
| [Nearest Neighbor Search for Relevance Feedback, CVPR 2003](https://vision.ece.ucsb.edu/sites/vision.ece.ucsb.edu/files/publications/03CVPRJelena.pdf) | Repeated NN search in feedback loops; consecutive-neighborhood reuse | No exact-versus-approximate trajectory objective or ANN error certificate. |
| [Speeding Up Active Relevance Feedback with Approximate kNN, 2008](https://digitalcommons.njit.edu/fac_pubs/13040/) | Most damaging early prior: approximate kNN inside the loop; speedup traded for additional feedback rounds | No total-budget allocation, cumulative trajectory regret, or margin-based stability guarantee. |
| [SALSAS, Pattern Recognition 2011](https://www.sciencedirect.com/science/article/abs/pii/S0031320310005753) | LSH/approximate kNN in iterative active retrieval | Fixed scalable learner rather than exact-reference trajectory control. |
| [Generative Multi-hop Retrieval, 2022](https://arxiv.org/abs/2204.13596) | Iterative retrieval error propagation | Representation/generation error, not isolated ANN effort. |
| [Early Exit for Dense Retrieval, CIKM 2024](https://doi.org/10.1145/3627673.3679903) | Query-dependent IVF depth | Independent-query objective. |
| [Adaptive Search via Sketching, ICML 2025](https://proceedings.mlr.press/v267/feng25c.html) | Correctness for answer-dependent adaptive queries | Protects randomized search correctness; future state is not the loss. |
| [Distance-Adaptive Beam Search, NeurIPS 2025](https://proceedings.neurips.cc/paper_files/paper/2025/hash/904fe070f484231aa26dbdb37816cd40-Abstract-Conference.html) | Certified query-specific graph-search termination | Per-query only. |
| [DARTH, SIGMOD 2026](https://arxiv.org/abs/2505.19001) | Declarative recall and hard-query-aware effort | Strongest algorithmic threat; the candidate dies if it is just a higher-level ef controller. |
| [Multiple-Query Optimization for ANNS, ICLR 2026 submission](https://openreview.net/forum?id=rZyQVls8TD) | Reuses results/entry points along correlated queries | Query batch is exogenous; objective is computation reuse. |
| [QVCache, 2026](https://arxiv.org/abs/2602.02057) | Temporal-semantic query locality | Cache hit/latency objective, not endogenous trajectory fidelity. |

### Novelty audit

- Exact-reference trajectory divergence: medium-high novelty.
- The fact that approximation affects a feedback loop: **not novel**.
- A Lipschitz/Grönwall recursion: low novelty and invalid globally for discontinuous hard top-k.
- Future-amplification-weighted budget allocation: only medium-low novelty until it beats DARTH/DABS-style single-query control.
- Margin-conditioned trajectory certificate from an ANN frontier: plausible novel core.

For a query whose k/(k+1) distance gap is `Delta`, a perturbation of radius below `Delta/2` preserves the exact top-k set because each point distance is 1-Lipschitz. A credible theory must combine these stable regions with feedback-summary error; it cannot simply assume the hard top-k map is globally Lipschitz.

### Verdict

**HOLD, novelty confidence about 6/10.** A positive SIFT micro-pilot justifies a full A0, but not a paper claim. To become PASS, an online amplification estimator must outperform uniform, margin-only, and DARTH/DABS-style effort at matched total work, and the causal closed-loop effect must survive open-loop controls on task-grounded feedback traces.

## N2. Query-Coverage Budgeted Backfill

### Claim checked

Select objects to re-encode under a migration budget by covering query-weighted objects whose cross-version uncertainty intersects the top-k boundary.

### Closest mechanisms and boundary

| Work | Overlap | Remaining boundary |
|---|---|---|
| [FastFill, ICLR 2023](https://arxiv.org/abs/2303.04766) | Directly performs policy-based partial backfilling, orders items by learned uncertainty, and optimizes the backfill curve | Only an explicit query-boundary coverage objective and a nontrivial guarantee remain. |
| [Metric-Compatible Online Backfilling, WACV 2025](https://openaccess.thecvf.com/content/WACV2025/html/Seo_Metric_Compatible_Training_for_Online_Backfilling_in_Large-Scale_Retrieval_WACV_2025_paper.html) | Mixed old/new distance-rank merge and progressive online backfill | Does not appear to optimize a query-object coverage set function. |
| [Lambda-Orthogonality, NeurIPS 2025](https://nips.cc/virtual/2025/poster/119181) | Compatible transformation plus explicit partial-backfill ordering | Further reduces room for a new ordering heuristic. |
| [Backward-Compatible Training, CVPR 2020](https://arxiv.org/abs/2003.11942) | Cross-version direct comparison | Avoids or reduces backfill rather than budget scheduling. |
| [Forward-Compatible Training, CVPR 2022](https://arxiv.org/abs/2112.02805) | Prepares representations for future updates | Requires compatible training. |
| [Universal Backward-Compatible Representation Learning, 2022](https://arxiv.org/abs/2203.01583) | Multi-version compatibility | Representation learning, not query-risk allocation. |
| [Drift-Adapter, EMNLP 2025](https://aclanthology.org/2025.emnlp-main.805/) | Maps new queries to the old corpus space and defers recomputation | Makes migration less necessary; strong practical baseline. |
| [Embedding-Converter, ACL 2025](https://aclanthology.org/2025.acl-long.1237/) | Converts embeddings across models | Transformation rather than selective exact refresh. |
| [Query Drift Compensation, 2026](https://proceedings.mlr.press/v330/goswami26a.html) | New queries against a fixed old corpus after continual retriever updates | No partial object schedule. |

### Theory audit

A surrogate

`F(S) = sum_q w_q g_q(sum_{i in S} r_qi)`

is monotone submodular when each `g_q` is nondecreasing and concave, so greedy has the standard `1-1/e` guarantee. That fact alone is not enough for novelty: the paper must prove that the computable risk `r_qi` controls actual mixed-version top-k error without already knowing every new embedding. Exact recall restoration is generally not submodular and must not be mislabeled.

### Verdict

**KILL as the broad Seed A; HOLD only for the narrow risk-coverage formulation.** Novelty confidence is 3–4/10. It must reproduce and beat FastFill by a material margin on public paired-model features; otherwise it is only a different priority score.

## N3. Spectral-Fidelity kNN Graph

### Claim checked

Use ANN uncertainty and current effective resistance to spend distance computations on missing kNN edges that matter most to the exact graph's spectrum.

### Closest mechanisms and boundary

| Work | Overlap | Consequence |
|---|---|---|
| [Stars, NeurIPS 2022](https://proceedings.neurips.cc/paper_files/paper/2022/hash/86ab3ff2c1387c895766f5c5fc2b610c-Abstract-Conference.html) | Two-hop graph construction with downstream connectivity/clustering guarantees | Occupies two-hop witness plus learning-aware similarity graph construction. |
| [Fast Approximation of Similarity Graphs, NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/d5c56ec4f69c9a473089b16000d3f8cd-Abstract-Conference.html) | Directly constructs sparse graphs preserving cluster structure/eigengap from points | Reviewer can ask why exact kNN is the right spectral target. |
| [Spectral Sparsification of Metrics and Kernels, SODA 2021](https://epubs.siam.org/doi/10.1137/1.9781611976465.87) | Metric/kernel oracle to spectral approximation | Threatens the distance-oracle spectral-construction framing. |
| [Structure-Aware Spectral Sparsification, NeurIPS 2025](https://papers.neurips.cc/paper_files/paper/2025/hash/45fb0a1934329ade4316f74bac75860f-Abstract-Conference.html) | Cluster-aware spectral preservation, sometimes by uniform sampling | Resistance-aware gains may be unnecessary in the intended downstream task. |
| [Refining a kNN Graph for Spectral Clustering, 2021](https://www.sciencedirect.com/science/article/abs/pii/S003132032100056X) | Progressive neighbors, local statistics, reciprocal/mutual pruning | Highly similar refinement vocabulary. |
| [Randomized Near-Neighbor Graphs, 2020](https://arxiv.org/abs/1711.04712) | Sparse random neighbors improve global connectivity and clustering | The motivating bridge-edge phenomenon is not new. |
| [CkNN, 2019](https://www.aimsciences.org/article/doi/10.3934/fods.2019001) | Neighborhood graph with topology and spectral convergence | Exact kNN need not be the best reference graph. |
| [Incremental Graph Construction for Robust Spectral Clustering, 2026](https://arxiv.org/abs/2603.03056) | Construction that guarantees connectivity for text embeddings | Occupies the disconnection motivation. |
| [TOPOGRAPH, AAAI 2026](https://ojs.aaai.org/index.php/AAAI/article/view/38478) | Topology-preserving graph reduction | Prevents a broad topology-preservation claim. |
| [Maximizing Spanning Trees / logdet edge addition, 2018](https://arxiv.org/abs/1804.02785) and [effective-resistance sparsification](https://epubs.siam.org/doi/10.1137/080734029) | Existing resistance marginal and submodular edge-selection theory | Does not transfer automatically to a search action that discovers/replaces multiple unknown edges. |

### Fatal theory mismatch

The logdet set function is submodular over a known candidate-edge set. An ANN refinement action discovers unknown edges, removes false edges, and replaces degree-limited neighbors; this action is not necessarily monotone or submodular. Effective resistance in the wrong/disconnected graph may not rank the exact graph's missing bridge edges, and a two-hop pool cannot discover a bridge between disconnected components.

### Verdict

**KILL AS-IS, novelty 4/10.** A possible new problem, `Active Spectral Certification of an Uncertain kNN Graph`, would begin with a high-coverage candidate superset and query exact distances until every consistent kNN graph has small spectral diameter. That narrower problem is HOLD and must be rechecked from scratch; it is not a surviving mechanism from the original proposal.

## Final novelty ranking

1. **Trajectory-Stable ANN — HOLD; run a strict causal A0.**
2. **Query-Coverage Backfill — KILL broad / HOLD narrow.**
3. **Spectral-Fidelity kNN Graph — KILL AS-IS.**

No candidate is promoted to paper-ready PASS by novelty alone.
