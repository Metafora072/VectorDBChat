# VectorDB / ANNS Idea Discovery R2 — Phase 0 Literature & Kill Map

Date: 2026-07-22

## Scope and decision rule

This map covers the 2024–2026 frontier by mechanism rather than by candidate name. A missing title match is not evidence of novelty. A direction is considered crowded when a nearest work already optimizes the same state, action, and objective, even if it uses a different index or application vocabulary.

The project constraints are: CPU and commodity NVMe experiments, no GPU training, pre-generated embeddings allowed, algorithmic or systems contribution, and no security, access-control, crash-recovery, or enterprise-lifecycle packaging.

## Local historical KILL map

| Family | Local evidence | Decision consequence |
|---|---|---|
| Graph aging under churn | IP-DiskANN and PipeANN showed essentially no recall or comparison degradation; equal-edge and shadow-replay controls removed the apparent effect. | Do not propose another edge repair score, maintenance trigger, or graph aging scheduler without a new phenomenon. |
| Dynamic SSD physical aging | Real `O_DIRECT` PipeANN canary: distinct pages fell by 3.76%/6.12% after insert/churn; static rebuild did not restore a missing effect. | Physical-layout aging, tombstone locality, and page coalescing are killed for this code path. |
| Workload self-healing graph | No causal degradation; nearby Quake/GATE/CleANN/hardness-repair mechanisms are crowded. | Query-aware relinking or entry-point tuning is not a candidate. |
| Low-DRAM / SSD placement | AiSAQ, LM-DiskANN, PipeANN, DiskANN, PiPNN and prior pilots cover the useful mechanism space. | Do not move an in-memory algorithm to SSD or rename a cache/layout heuristic. |
| Filtered / permission layout | Curator, HoneyBee, GateANN, SIEVE, UNIFY, dynamic range filtering and multi-attribute range indexes cover the direct formulations. | Excluded both for crowding and user preference. |
| Multi-vector page pruning | Bounds were not tight enough; MUVERA, PLAID, WARP, GEM and multi-vector graph work already cover algorithmic reductions and pruning. | A new page summary or token threshold is not enough. |
| ZNS / transaction / recovery | ANN-specific signal did not close; mechanisms reduced to generic reclaim, WAL, or transactional packaging. | Explicitly out of scope. |
| Closed-loop agent cache | T2 A0-R2 found no closed-loop separation from open-loop or write-disabled controls. | Any trajectory proposal must concern ANN answer error propagation, not memory admission or cache feedback. |
| Embedding topology reuse | Gaussian perturbations were invalid evidence and RobustPrune could not be inferred from edge watermarks; seeded NN-descent alone was incremental. | Do not equate migration scheduling with graph warm-start. |

## 2024–2026 frontier coverage

### Dynamic graph ANN: insert, delete, repair, concurrency

- CleANN (2025) combines clean dynamic beam search, robust insertion, deletion consolidation, and serializable concurrent search/insert/delete: <https://arxiv.org/abs/2507.19802>.
- Dynamic updates via random walks (ICLR 2026) gives a deletion framework preserving hitting-time statistics: <https://arxiv.org/abs/2512.18060>.
- OdinANN (FAST 2026) uses direct on-disk insertion to stabilize billion-scale serving performance: <https://www.usenix.org/conference/fast26/presentation/guo>.
- Dynamic Exploration Graph (2025) maintains connectivity and balance under insertion/deletion: <https://visual-computing.com/publications/dynamic-exploration-graph-a-novel-approach-for-efficient-nearest-neighbor-search-in-evolving-multimedia-datasets>.

**Boundary:** an insertion rule, local repair policy, tombstone cleanup rule, or concurrency scheme has to beat a very mature mechanism set. This family is KILL unless a different objective is introduced.

### Streaming ANN and continuous vector streams

- The Big ANN / NeurIPS practical vector-search benchmark explicitly includes streaming evaluation: <https://big-ann-benchmarks.com/>.
- Slipstream (2026) reuses candidates from the previous insertion and adapts to stream continuity: <https://arxiv.org/abs/2606.02992>.
- CleANN covers fully dynamic online updates rather than append-only streaming: <https://arxiv.org/abs/2507.19802>.
- The dynamic-dataset investigation (2024) evaluates update rate, batch size, and index maintenance cost: <https://arxiv.org/abs/2404.19284>.

**Boundary:** append-only ingestion, candidate reuse between arrivals, and stream-aware insertion are crowded. A possible gap is high-dimensional *moving-vector* or kinetic ANN, where existing object coordinates drift rather than points merely arriving/departing; older continuous-NN computational-geometry work is a serious boundary, not a novelty-free zone.

### Adaptive beam, early termination, hard-query detection

- Distance-Adaptive Beam Search (NeurIPS 2025) gives a provably accurate distance-based stopping rule: <https://proceedings.neurips.cc/paper_files/paper/2025/hash/904fe070f484231aa26dbdb37816cd40-Abstract-Conference.html>.
- DARTH (SIGMOD 2026) targets declarative recall, adaptive termination, and hard queries: <https://arxiv.org/abs/2505.19001>.
- GATE uses query-aware entry points: <https://arxiv.org/abs/2505.10948>.
- Dynamic hardness detection/repair (2025) diagnoses reachability and neighborhood defects under OOD workloads: <https://arxiv.org/abs/2510.22316>.
- PAG (2026) uses projection-based statistical tests to avoid exact distance computations and supports online insertion: <https://arxiv.org/abs/2603.06660>.

**Boundary:** changing beam width, entry point, termination threshold, or hard-query score is KILL. A surviving proposal must optimize a sequence-level or downstream objective not reducible to independent per-query recall/latency.

### Workload-aware and query-aware graph construction/maintenance

- Quake (OSDI 2025) adapts partitions and maintenance to workload drift: <https://www.usenix.org/conference/osdi25/presentation/wang-yingqi>.
- GATE provides query-aware entry routing: <https://arxiv.org/abs/2505.10948>.
- CleANN includes workload-aware linking and consolidation mechanisms: <https://arxiv.org/abs/2507.19802>.
- Dynamic hard-query repair targets workload-induced search failures: <https://arxiv.org/abs/2510.22316>.

**Boundary:** graph rewiring from query logs is crowded and has already failed a causal local A0. KILL.

### Filtered, dynamic filtered, and multi-predicate ANN

- UNIFY (PVLDB 2025) unifies filtered graph search: <https://www.vldb.org/pvldb/vol18/p1118-yao.pdf>.
- Dynamic range-filtered ANN (PVLDB 2025) supports updates: <https://www.vldb.org/pvldb/vol18/p3256-deng.pdf>.
- SIEVE (PVLDB 2025) builds a collection of predicate-form-specific indexes: <https://doi.org/10.14778/3749646.3749725>.
- Curator (2026) and GateANN (2026) cover tenant-aware and arbitrary-predicate filtered search: <https://arxiv.org/abs/2601.01291>, <https://arxiv.org/abs/2603.21466>.
- KHI (2026) handles multi-attribute numeric ranges: <https://arxiv.org/abs/2602.15488>.
- RNSG (2026) develops range-aware graph structure: <https://arxiv.org/abs/2603.12913>.

**Boundary:** direct filtered/multi-predicate work is both crowded and outside the requested flavor. KILL.

### Embedding-model migration and cross-version compatibility

- FastFill (ICLR 2023) already performs policy-based partial backfilling, uses uncertainty to order gallery refresh, and explicitly optimizes the backfilling curve: <https://arxiv.org/abs/2303.04766>.
- Metric-Compatible Training / online backfilling (WACV 2025) uses distance-rank merge, reverse query transformation, and calibrated old/new distances: <https://openaccess.thecvf.com/content/WACV2025/html/Seo_Metric_Compatible_Training_for_Online_Backfilling_in_Large-Scale_Retrieval_WACV_2025_paper.html>.
- Drift-Adapter (EMNLP 2025) maps new queries into the legacy space and reports 95–99% of full re-embedding retrieval quality: <https://aclanthology.org/2025.emnlp-main.805/>.
- Embedding-Converter (ACL 2025) learns cross-model transformations: <https://aclanthology.org/2025.acl-long.1237/>.
- Cross-modal backward-compatible training (2024) extends compatibility to vision-language models: <https://arxiv.org/abs/2405.14715>.
- Query Drift Compensation (2026) maps continually updated query representations back to a fixed corpus space: <https://proceedings.mlr.press/v330/goswami26a.html>.

**Boundary:** Seed A is not novel as stated. Partial re-embedding scheduling, mixed-version comparison, and uncertainty-prioritized backfill all exist. The only defensible residual is a formally different objective with a theorem (for example, top-k ranking-risk coverage under a hard budget) and an A0 showing that it materially beats FastFill's uncertainty ordering. Until then: HOLD leaning KILL.

### Multi-vector / late-interaction ANN

- MUVERA (NeurIPS 2024) reduces Chamfer/MaxSim-style multi-vector retrieval to single-vector MIPS: <https://papers.nips.cc/paper_files/paper/2024/hash/b71cfefae46909178603b5bc6c11d3ae-Abstract-Conference.html>.
- Alpha-reachable graphs study graph structure for multi-vector nearest-neighbor search: <https://openreview.net/forum?id=v8jSxLHEE9>.
- Existing PLAID/WARP/GEM-style systems already prune token interactions and candidates; Qdrant has product support for late interaction: <https://qdrant.tech/articles/late-interaction-models/>.

**Boundary:** token pruning, page bounds, or a direct MaxSim index is crowded. KILL absent a new aggregate-query objective or proof.

### Adaptive queries, query sequences, and closed-loop retrieval

- On Adaptive Distance Estimation (NeurIPS 2020) guarantees correctness for adaptively selected queries: <https://proceedings.neurips.cc/paper/2020/hash/803ef56843860e4a48fc4cdb3065e8ce-Abstract.html>.
- Efficient Adversarially Robust ANN (2026) handles a powerful adaptive adversary controlling a query sequence: <https://arxiv.org/abs/2601.00272>.
- QVCache (2026) exploits semantic query repetition with a query-aware vector cache: <https://arxiv.org/abs/2602.02057>.
- Relevance-feedback search makes the next query depend on returned results; current vector-engine support demonstrates the loop but does not analyze ANN-induced trajectory divergence: <https://qdrant.tech/documentation/search/search-relevance/>.

**Observed gap:** prior adaptive-query theory asks whether each answer is correct despite adaptively chosen queries. Cache/reuse work asks how to reduce cost. Neither objective measures how an approximate answer changes the *future query state* and amplifies downstream error. Seed B remains a plausible PASS candidate, subject to a non-toy A0 and a theorem stronger than a direct Lipschitz recursion.

### Diverse, fair, robust, and adversarial ANN

- Approximate diverse k-NN (2025) integrates progressive search, diversification, and verification: <https://arxiv.org/abs/2510.27243>.
- LotusFilter (CVPR 2025) learns a cutoff for fast diverse nearest-neighbor postprocessing: <https://openaccess.thecvf.com/content/CVPR2025/html/Matsui_LotusFilter_Fast_Diverse_Nearest_Neighbor_Search_via_a_Learned_Cutoff_CVPR_2025_paper.html>.
- Multi-attribute group-fair k-NN (2026) gives LSH candidate generation plus flow/ILP postprocessing: <https://arxiv.org/abs/2602.17858>.
- Efficient adversarially robust ANN (2026) uses fairness, privacy, and LSH mechanisms for adaptive adversaries: <https://arxiv.org/abs/2601.00272>.
- RetrievalGuard provides certified robust 1-NN retrieval under perturbations: <https://proceedings.mlr.press/v162/wu22o.html>.

**Boundary:** generic diversity, group fairness, perturbation robustness, and adversarial-query correctness are directly occupied. They are not reserve candidates for this round.

## Phase 0 verdict

1. **Seed A — Budgeted Embedding Migration:** `HOLD/KILL`. The premise is real, but FastFill directly occupies policy-based partial backfilling and WACV 2025 occupies mixed-version rank merge. Only a theorem-backed top-k risk objective plus decisive head-to-head A0 can rescue it.
2. **Seed B — Trajectory-Stable ANN:** `PROVISIONAL PASS TO NOVELTY CHECK`. Mechanism-level searches find adaptive correctness, cache/reuse, and relevance feedback, but not cumulative ANN-induced trajectory divergence or horizon-aware search-budget allocation.
3. **Open generation:** look for a new point-query generalization such as path/tube ANN or moving-vector ANN, but treat continuous-NN and uncertainty-search literature as strong boundaries. Do not force a third candidate.
