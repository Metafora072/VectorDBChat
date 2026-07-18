# IDEA_REPORT.md — Phase 2: Idea Generation

**Direction**: Disk-resident ANN and vector search (systems + AI venues)
**Date**: 2026-07-18
**Phase**: 2 (idea-creator) — 10 ideas generated, spanning G1-G7
**Status**: Pre-filtering; novelty check pending

---

## Gap Coverage Index

| Idea | Gap(s) | Venue Type |
|------|--------|------------|
| I1 | G1 (ZNS) | Systems (FAST) |
| I2 | G1 (ZNS) | Systems (FAST/OSDI) |
| I3 | G2 (I/O theory) | Theory (SODA/NeurIPS) |
| I4 | G3 (KV cache SSD) | Systems+AI (VLDB/OSDI) |
| I5 | G4 (Quant-topology disk) | Systems (SIGMOD/VLDB) |
| I6 | G5 (Crash consistency) | Systems (FAST/EuroSys) |
| I7 | G6 (Freshness theory) | Theory (NeurIPS/ICML) |
| I8 | G6 (Freshness) + G1 | Systems+Theory (VLDB) |
| I9 | G7 (Dynamic filtered) | Systems (VLDB/SIGMOD) |
| I10 | Cross-cutting (diagnostic) | Systems (VLDB) |

---

## Idea Candidates

### I1: ZoneANN — Log-Structured Graph ANN on ZNS SSD

1. **Title**: ZoneANN: Log-Structured Graph ANN for Zoned Namespace SSDs
2. **Summary**: Redesign the graph ANN update path for ZNS append-only zone semantics using log-structured graph maintenance with zone-aligned compaction.
3. **Core hypothesis**: ZNS's higher sustained write bandwidth (no FTL garbage collection) compensates for the log-structured overhead of converting in-place graph updates to appends, achieving ≥1.5× write throughput vs DiskANN on conventional SSD at matched recall. Falsifiable: if ZNS compaction overhead exceeds FTL GC savings, write throughput will be worse.
4. **Target venue**: FAST 2027
5. **Minimum viable experiment**: Implement atop DiskANN codebase (available in `/home/ubuntu/pz/VectorDB/repos/DiskANN`). Use SIFT10M with streaming insert workload from M0-M3 traces. Emulate ZNS via `libzbd` on a Samsung PM1731a or use `nullblk` ZNS emulation. Compare: (a) DiskANN on ext4/conventional SSD, (b) ZoneANN on ZNS, (c) DiskANN on f2fs/ZNS as naive baseline. Metrics: write throughput (ops/s), write amplification, recall@10, QPS.
6. **Contribution type**: System design
7. **Risk**: MEDIUM — ZNS compaction scheduling for graph ANN is non-trivial; may require co-designed zone allocation policy.
8. **Estimated effort**: 3-4 months
9. **Differentiation**: B+-tree on ZNS (ACM TACO 2026) adapts tree indexes; NO prior work exists for graph ANN on ZNS. LSM-VEC uses LSM structure for vector indexes but not on ZNS and not graph-based. Our M0-M3 write attribution data (fanout × page-mapping × temporal-rewrite decomposition) directly informs which writes can be deferred/batched for zone alignment.

---

### I2: ZNS ANN Feasibility Diagnostic — In-Place vs Append Write Classification

1. **Title**: How Much of Graph ANN I/O is In-Place? A ZNS Feasibility Study
2. **Summary**: Classify all graph ANN write operations as in-place-overwrite vs new-allocation using M0-M3 infrastructure to determine whether ZNS requires fundamental redesign or only a thin translation layer.
3. **Core hypothesis**: >70% of DiskANN/OdinANN writes during dynamic operations are in-place overwrites of existing pages, meaning a naive FTL-emulation layer on ZNS would not suffice and a fundamental log-structured redesign is necessary. Falsifiable: if <30% are overwrites, a simple indirection layer works.
4. **Target venue**: FAST 2027 (paired with I1, or standalone short paper)
5. **Minimum viable experiment**: Extend M0-M3 write profiling scripts to classify each `pwrite64` by whether the target offset has been previously written (overwrite) or is a fresh allocation (append). Run on DGAI and OdinANN with SIFT1M/SIFT10M streaming insert. Generate write classification histogram and temporal pattern analysis. Data already partially available in M0-M3 supersession audit (22.5M page versions, 0 supersession found — this needs reinterpretation for ZNS context).
6. **Contribution type**: Diagnostic / empirical finding
7. **Risk**: LOW — purely empirical, but the finding directly determines G1 tractability.
8. **Estimated effort**: 2-3 weeks
9. **Differentiation**: No prior work characterizes graph ANN write patterns for append-only storage. Our M0-M3 supersession audit (22.5M page versions) is the only existing dataset of this kind. The write supersession result of 0 actually suggests DiskANN pre-allocates and never overwrites — which would be favorable for ZNS.

---

### I3: External Memory Lower Bounds for Navigable Graph ANN

1. **Title**: I/O Complexity of α-Navigable Graph Search in the External Memory Model
2. **Summary**: Establish the first formal I/O complexity lower bounds for approximate nearest neighbor search via navigable graphs, extending Sparse Navigable Graphs' edge-count bounds to page-read bounds.
3. **Core hypothesis**: For any α-navigable graph on n points in d-dimensional space with page capacity B, worst-case greedy search requires Ω(log n / log B) page reads, and this is tight up to constant factors. If true, current systems (DiskANN achieves O(log n) hops ≈ O(log n) page reads with B≈1 effective) are near-optimal. Falsifiable: a constructive algorithm with o(log n / log B) page reads would refute the lower bound.
4. **Target venue**: SODA 2027 or NeurIPS 2026
5. **Minimum viable experiment**: Pure theory paper. Start from SNG (SODA 2026) Set Cover equivalence for edge count. Model: Aggarwal-Vitter external memory (memory M, page size B). Define α-navigable graph in this model. Attempt reduction from Set Cover to prove page-read lower bound. Verify against known page costs of DiskANN (empirical: ~50-80 page reads for SIFT1M at 95% recall).
6. **Contribution type**: Theoretical result
7. **Risk**: HIGH — I/O lower bounds require careful modeling; the lower bound may be trivially loose or the reduction may not go through.
8. **Estimated effort**: 3-6 months (pure theory)
9. **Differentiation**: SNG (SODA 2026) gives edge-count bounds and Set Cover equivalence. Sort Before You Prune gives navigability guarantees. Neither addresses I/O complexity. External memory lower bounds exist for sorting (Aggarwal-Vitter), subgraph enumeration (ICDT 2024), but NOT for ANN. This would be the first.

---

### I4: GraphKV — Disk-Resident ANN Index for KV Cache Retrieval in Ultra-Long-Context LLM

1. **Title**: GraphKV: Graph-ANN-Based KV Cache Retrieval from SSD for Million-Token Inference
2. **Summary**: Build a disk-resident graph ANN index over KV cache entries using attention-aware distance to selectively retrieve the most relevant tokens from SSD, enabling 2M+ context on a single GPU + NVMe.
3. **Core hypothesis**: Sparse attention retrieval via disk-resident ANN achieves equivalent generation quality (perplexity within 1% of full attention) at 5-10× lower I/O than page-granularity KV swapping (Tutti, KVSwap), because ANN retrieves the ≤1% of tokens that dominate attention weight, while swap loads entire pages including irrelevant tokens. Falsifiable: if attention sparsity is insufficient (>10% of tokens needed per step), ANN overhead exceeds bulk-swap savings.
4. **Target venue**: VLDB 2027 or OSDI 2027
5. **Minimum viable experiment**: Prototype on Llama-3.1-8B with 128K context. Build HNSW/Vamana index over K vectors for each layer (offline, during prefill). At decode time, query the graph index with current Q vector to retrieve top-64 KV entries from SSD. Compare: (a) Full attention (baseline), (b) RetroInfer wave-index (DRAM-only, cannot scale past DRAM), (c) Tutti (SSD page swap), (d) GraphKV (SSD ANN retrieval). Metrics: perplexity, TTFT, TPOT, SSD read IOPS, memory footprint.
6. **Contribution type**: System design + new method
7. **Risk**: MEDIUM — Per-step ANN query latency on SSD (~100μs per page read × ~50 hops) may bottleneck token generation speed. Need async prefetch pipeline.
8. **Estimated effort**: 3-4 months
9. **Differentiation**: RetroInfer (VLDB 2026) = DRAM-only wave index; cannot scale past DRAM. Tutti (2026) = GPU-centric SSD page swap without ANN intelligence. KVSwap = simple eviction policy. GraphKV is the first to use disk-resident ANN for selective KV retrieval. Our deep DiskANN expertise (async I/O, page layout, PQ reranking) directly applies to the SSD retrieval path.

---

### I5: DiskQG — Quantization-Aware Graph Topology for Disk-Resident ANN

1. **Title**: DiskQG: Joint Quantization-Topology Optimization for Disk-Resident Graph ANN
2. **Summary**: Extend SymphonyQG/QuIVer's quantization-graph co-design from in-memory to disk-resident ANN, where the graph topology is optimized for quantized-distance navigation while the SSD layout groups quantization-similar nodes.
3. **Core hypothesis**: A disk graph whose edge selection is co-optimized with RaBitQ/BQ codes achieves 30%+ fewer SSD page reads than DiskANN's post-hoc PQ + graph combination, because quantization-aware edges avoid "false shortcut" hops that look good in PQ distance but require expensive SSD reads for full-precision verification. Falsifiable: if PQ distance errors are already well-calibrated by existing graph pruning (RobustPrune), the co-design adds no benefit.
4. **Target venue**: SIGMOD 2027 or VLDB 2027
5. **Minimum viable experiment**: Modify DiskANN construction: during RobustPrune, use RaBitQ distance (in memory) to select edges instead of exact distance; store RaBitQ codes alongside PQ codes in memory. At search time, navigate using RaBitQ distance, load SSD pages only for final reranking. Compare vs DiskANN+PQ, DiskANN+OPQ, SymphonyQG (in-memory, unfair but shows quality ceiling). Datasets: SIFT1M, DEEP1M, SPACEV1M. Metrics: recall@10 vs SSD page reads, QPS, construction time.
6. **Contribution type**: New method
7. **Risk**: MEDIUM — QuIVer shows BQ works only for cosine-native embeddings; RaBitQ (SymphonyQG) is more general but untested for graph topology definition.
8. **Estimated effort**: 2-3 months
9. **Differentiation**: SymphonyQG (SIGMOD 2025) = in-memory, uses RaBitQ for distance during search but conventional graph construction. QuIVer (2026) = in-memory, BQ defines topology, cosine-only. Neither is disk-resident. DiskQG: disk-resident, RaBitQ-aware construction, general distance metrics.

---

### I6: CrashANN — Crash-Consistent Dynamic Disk-Resident Graph ANN

1. **Title**: CrashANN: Crash Recovery for Dynamic Disk-Resident Graph ANN
2. **Summary**: Design and implement a WAL-based crash recovery protocol for disk-resident graph ANN that guarantees atomicity of multi-page updates (vector insert + adjacency list modifications across multiple neighbor pages).
3. **Core hypothesis**: Crash consistency can be achieved with <20% throughput overhead by exploiting the observation that graph ANN updates are write-heavy but writes are to a small working set (the inserting vector's neighborhood), enabling group commit + sequential WAL with bounded recovery time. Falsifiable: if the neighbor update fan-out (M0-M3 shows ~96 per insert) makes WAL too large, overhead will exceed 20%.
4. **Target venue**: FAST 2027 or EuroSys 2027
5. **Minimum viable experiment**: Implement WAL-based recovery atop DiskANN/OdinANN. Each insert operation: (1) log intent (new vector, candidate neighbor list); (2) write vector page; (3) update adjacency lists; (4) commit. On crash: replay uncommitted intents. Test with fault injection (kill -9 during insert stream). Compare: (a) DiskANN no-crash baseline, (b) CrashANN with WAL, (c) CrashANN with group commit. Metrics: throughput, recovery time, space overhead, recall after crash+recovery.
6. **Contribution type**: System design
7. **Risk**: LOW — WAL-based crash recovery is well-understood; the challenge is adapting it to graph ANN's multi-page update pattern. But novelty concern: reviewers may view it as "standard WAL, just applied to ANN."
8. **Estimated effort**: 2-3 months
9. **Differentiation**: P-HNSW (2025) uses persistent memory (pmem), not SSD, and targets in-memory HNSW. No disk-resident crash-consistent graph ANN exists. Our OdinANN FAST 2026 experience gives us the multi-page update pattern knowledge needed (M0-M3 shows 96 neighbor repairs per insert, each touching different pages).

---

### I7: Recall Degradation Certificates for Streaming Graph ANN

1. **Title**: Freshness-Recall Phase Transition in Streaming α-Navigable Graphs
2. **Summary**: Prove formal bounds on recall degradation as a function of un-integrated updates in streaming graph ANN, establishing a phase transition threshold for when deferred maintenance becomes catastrophic.
3. **Core hypothesis**: For a random insertion stream into an α-navigable graph, there exists a critical freshness ratio ρ* = Θ(α/√n) such that: recall@k ≥ 1 - O(1-ρ)² for ρ > ρ* (graceful degradation), but recall@k drops to O(k/n) for ρ < ρ* (catastrophic). This would give the optimal trigger for FreshDiskANN's StreamingMerge. Falsifiable: if recall degrades linearly (no phase transition), the threshold doesn't exist.
4. **Target venue**: NeurIPS 2026 or ICML 2027
5. **Minimum viable experiment**: (a) Theory: formalize the model — α-navigable graph G₀ on n points; streaming insertions arrive; each insertion is integrated with probability ρ (random Bernoulli model). Prove recall bound as function of ρ. (b) Empirical validation: use DiskANN/DGAI with SIFT1M, vary integration fraction ρ from 0.1 to 1.0, measure recall@10 curve. Check for phase transition signature.
6. **Contribution type**: Theoretical result + empirical validation
7. **Risk**: HIGH — formal recall bounds on partially-updated graphs are very hard. Random insertion model may not capture adversarial workloads.
8. **Estimated effort**: 3-6 months
9. **Differentiation**: FreshDiskANN provides no formal guarantee on delta size vs recall. Wolverine/CleANN have empirical repair scheduling but no theory. This would be the first formal freshness-recall tradeoff. Different from KILLED "amortized maintenance" direction because we bound recall degradation (query quality metric), not repair cost (update metric).

---

### I8: Write-Deferred Graph ANN with Provable Freshness Bounds

1. **Title**: Lazy-First Graph ANN: Trading Write I/O for Bounded Recall Loss
2. **Summary**: Design a practical write-deferral policy for streaming graph ANN that provably bounds recall degradation as a function of deferred writes, enabling optimal I/O scheduling on both conventional and ZNS SSDs.
3. **Core hypothesis**: By deferring neighbor repairs and batching them at zone boundaries (ZNS) or I/O-idle periods, total write I/O can be reduced by 40-60% with recall@10 degradation bounded by <3%, because M0-M3 data shows ~50% of neighbor repairs are accepted by RobustPrune (the other 50% are wasted reads that discover no improvement). Falsifiable: if graph quality is fragile to any deferral, recall drops >10% even with small batches.
4. **Target venue**: VLDB 2027
5. **Minimum viable experiment**: Modify OdinANN to defer neighbor repairs into a pending queue, flush every K inserts. Measure recall@10 vs K on SIFT1M/SIFT10M. Compare: (a) eager repair (current OdinANN), (b) defer-K with K=10,50,100,500, (c) defer until zone full (ZNS simulation). Use M0-M3 accept/reject statistics to predict optimal K.
6. **Contribution type**: System design + empirical finding
7. **Risk**: MEDIUM — the idea is simple and clean, but must be differentiated from FreshDiskANN's delta buffer approach. Key difference: we defer repairs within the main index (not a separate delta), guided by formal bounds from I7.
8. **Estimated effort**: 2-3 months
9. **Differentiation**: FreshDiskANN uses a separate delta buffer with StreamingMerge — structurally different from deferring repairs within the main graph. Wolverine has cleaning scheduling but no formal bounds. Our M0-M3 repair accept/reject data provides unique ground truth for predicting repair value. IMPORTANT: distinct from KILLED "amortized maintenance" because we don't claim amortized cost improvement; we claim recall-bounded write reduction.

---

### I9: FilterShift — Dynamic Predicate-Aware ANN on SSD

1. **Title**: FilterShift: Incrementally Maintaining Filtered Graph ANN Under Predicate Evolution
2. **Summary**: Design an SSD-resident filtered ANN index that incrementally adapts its graph structure when filter predicates change (ACL updates, TTL expiration, category reclassification), avoiding full index rebuild.
3. **Core hypothesis**: Incremental filter-graph maintenance (re-link only affected subgraph neighborhoods when a predicate changes) is 5-10× cheaper in I/O than rebuilding the filtered index, with <3% recall degradation vs rebuild-from-scratch. Falsifiable: if predicate changes affect >30% of graph edges, incremental update is no cheaper than rebuild.
4. **Target venue**: VLDB 2027 or SIGMOD 2027
5. **Minimum viable experiment**: Extend DiskANN with per-node filter labels (categorical metadata). Simulate predicate evolution: random label flips affecting 1-10% of nodes per epoch. Compare: (a) rebuild filtered index each epoch, (b) FilterShift incremental re-linking (identify affected nodes, repair their neighborhoods under new filter constraints), (c) no adaptation baseline. Datasets: SIFT1M with synthetic labels, or Microsoft SPACEV with real categorical metadata. Metrics: recall@10 under filter, rebuild I/O cost, incremental update I/O cost.
6. **Contribution type**: System design
7. **Risk**: LOW-MEDIUM — clean problem definition, but must differentiate from general dynamic ANN (FreshDiskANN handles inserts/deletes, not predicate changes). The specific challenge is maintaining filter-aware navigability.
8. **Estimated effort**: 2-3 months
9. **Differentiation**: GateANN (2026) = static filters, I/O optimization for filter-failing nodes. FusedANN = static fused filter+ANN. Filtered ANN Phase Transition = query planning with static index. None handle dynamic predicates. FreshDiskANN handles vector insertions but not predicate changes. Quake adapts to workload distribution shift but not filter evolution.

---

### I10: DiskANN I/O Attribution Benchmark — Where Do Real Workloads Spend I/O?

1. **Title**: Anatomy of Disk-Resident ANN I/O: A Write and Read Attribution Study
2. **Summary**: Build the first complete I/O attribution benchmark for disk-resident graph ANN, decomposing both read and write I/O by purpose (navigation, reranking, repair, compaction, filter-check) across diverse workloads.
3. **Core hypothesis**: >40% of total I/O in production-representative graph ANN workloads is spent on operations that current optimizations (page layout, async I/O, PQ reranking) do not target — specifically, neighbor repair read probes that result in no graph change and redundant re-reads of hot pages across concurrent queries. Falsifiable: if existing optimizations already target the dominant I/O sources, no untapped opportunity exists.
4. **Target venue**: VLDB 2027 (experiment & analysis track)
5. **Minimum viable experiment**: Extend M0-M3 infrastructure to capture both reads and writes. Add per-operation tags: {navigation_read, rerank_read, repair_read, repair_write, compaction_write, filter_check_read}. Run on SIFT10M, DEEP10M, SPACEV10M with mixed query+insert workloads. Generate I/O attribution breakdown charts. Compare across DiskANN, OdinANN (DGAI), Starling configurations. Data: reuse M0-M3 scripts and dynamic_vamana_atlas traces.
6. **Contribution type**: Diagnostic / empirical finding
7. **Risk**: LOW — purely empirical, but findings directly guide future optimization and validate/invalidate assumptions of other papers (PageANN, OctopusANN, PipeANN, VeloANN all optimize different I/O aspects without knowing actual I/O breakdown).
8. **Estimated effort**: 4-6 weeks
9. **Differentiation**: BAMG (2025) and OctopusANN model I/O analytically but don't measure actual I/O breakdown. "Disk-Resident Graph ANN Search: An Experimental Evaluation" (2026) benchmarks performance but not I/O attribution. Our M0-M3 write attribution is the only existing per-operation I/O profiling infrastructure for graph ANN. Extending it to reads creates the first complete picture.

---

## Pre-Filtering Assessment

| Idea | Novelty (est.) | Feasibility | Impact | Proceed? |
|------|---------------|-------------|--------|----------|
| I1 ZoneANN | HIGH (zero prior) | MEDIUM | HIGH | YES — deep novelty check needed |
| I2 ZNS Diagnostic | HIGH (zero prior) | HIGH | MEDIUM | YES — quick win, pairs with I1 |
| I3 I/O Lower Bounds | HIGH (first theory) | LOW (hard proof) | HIGH | YES — high risk/high reward |
| I4 GraphKV | HIGH (new intersection) | MEDIUM | VERY HIGH | YES — hot topic, strong motivation |
| I5 DiskQG | MEDIUM-HIGH | MEDIUM | MEDIUM-HIGH | YES — builds on strong recent work |
| I6 CrashANN | MEDIUM (standard technique) | HIGH | MEDIUM | CONDITIONAL — novelty concern |
| I7 Freshness Theory | HIGH (first formal) | LOW (hard proof) | HIGH | YES — pairs with I8 |
| I8 Write-Deferred | MEDIUM | HIGH | MEDIUM-HIGH | CONDITIONAL — differentiation from FreshDiskANN |
| I9 FilterShift | MEDIUM-HIGH | MEDIUM-HIGH | MEDIUM-HIGH | YES — clean problem |
| I10 I/O Attribution | MEDIUM | VERY HIGH | MEDIUM | YES — enables other work |

**Top candidates for Phase 3 (novelty check)**: I1, I4, I5, I7, I9
**Secondary**: I2, I3, I8, I10
**Conditional**: I6 (novelty concern), I8 (differentiation needed)
