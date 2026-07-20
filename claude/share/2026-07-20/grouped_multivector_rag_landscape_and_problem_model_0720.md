# SSD-Resident Grouped Multi-Vector Retrieval: Landscape & Problem Model

**Date**: 2026-07-20
**Author**: Claude (landscape + problem model, per Gpt gate)
**Status**: Paper-only analysis, no implementation recommendation

---

## 1. Application Scenario and Workload Definition

### Target Workload

A corpus of N document pages (N = 10M–1B), each represented by a **group** of token/patch vectors produced by a late-interaction model (ColBERT, ColPali, ColQwen). A query is also a group of vectors. Retrieval returns the top-k pages ranked by a document-level aggregation score (MaxSim).

### Why This Workload Is Different from Single-Vector ANN

| Property | Single-vector ANN | Grouped multi-vector |
|---|---|---|
| Object representation | 1 vector per object | n vectors per object (n=32–1024+) |
| Score evaluation | 1 distance computation | m×n similarity matrix → aggregate |
| I/O per candidate | O(d) bytes | O(n×d) bytes |
| Partial read | meaningless (need full vector) | partial score is computable |
| Result unit | individual vector | document (group of vectors) |
| Page utilization | many objects per page | one object may span multiple pages |

### Scale Estimates

| Model | Vectors/page | Dim | Bytes/page (FP16) | Bytes/page (2-bit PQ) | 100M pages raw | 100M pages compressed |
|---|---|---|---|---|---|---|
| ColBERTv2 | ~128 | 128 | 32 KB | ~4 KB | 3.2 TB | 400 GB |
| ColPali | ~1024 | 128 | 262 KB | ~8 KB | 26.2 TB | 800 GB |
| ColQwen3-4B | ~1024 | 128 | 262 KB | ~8 KB | 26.2 TB | 800 GB |

Even with 32× compression, 100M-page corpora exceed typical server memory (64–256 GB). The multi-vector payload **must** reside on SSD for billion-scale deployment.

---

## 2. Exact Query Operator

### MaxSim

$$\text{Score}(Q, D) = \sum_{q_i \in Q} \max_{d_j \in D} \text{sim}(q_i, d_j)$$

Where:
- Q = {q₁, ..., q_m}: query token/patch vectors (m = 32 typical for text, ~100 for visual queries)
- D = {d₁, ..., d_n}: document token/patch vectors (n = 128 for ColBERT, ~1024 for ColPali)
- sim(·,·): cosine similarity or inner product
- Result: a scalar per (query, document) pair

### MaxSim Properties Relevant to SSD Execution

1. **Decomposable by query token**: Score = Σ_i S_i where S_i = max_j sim(q_i, d_j). Each query token's contribution is independent.

2. **Monotonically increasing with more document vectors read**: Reading more vectors from D can only increase S_i (new max can only be ≥ current max). Therefore, a partial read produces a **valid lower bound**.

3. **Not decomposable by document token**: You cannot score one document token in isolation — its value depends on which query token it maximizes for, which depends on all other document tokens already seen.

4. **Upper bound computable from metadata**: If per-page statistics are stored (e.g., max vector norms, centroid vectors), an upper bound on unread pages' contribution can be derived without reading the full vectors.

---

## 3. Storage / I/O Execution Path

### Current Two-Stage Pipeline (State of Practice)

```
Stage 1: Candidate generation (in-memory or disk ANN)
  - Single-vector proxy (MUVERA/LEMUR/DSE) or centroid interaction (PLAID/WARP)
  - Returns C candidates (C = 100–10,000)
  - I/O: graph traversal reads (if disk ANN)

Stage 2: Exact MaxSim reranking
  - For each candidate: read ALL n vectors from storage
  - Compute full m×n MaxSim score
  - Return top-k (k = 10–100)
  - I/O: C × n × d × sizeof(element) bytes, random access pattern
```

### I/O Cost Analysis for Stage 2

| Scenario | Candidates C | Vectors/doc n | Bytes/doc | Total read | Random 4K reads | NVMe time (1M IOPS) |
|---|---|---|---|---|---|---|
| ColBERT, compressed | 1,000 | 128 | 4 KB | 4 MB | 1,000 | 1 ms |
| ColBERT, raw | 1,000 | 128 | 32 KB | 32 MB | 8,000 | 8 ms |
| ColPali, compressed | 1,000 | 1024 | 8 KB | 8 MB | 2,000 | 2 ms |
| ColPali, raw | 1,000 | 1024 | 262 KB | 262 MB | 65,000 | 65 ms |
| ColPali, compressed | 10,000 | 1024 | 8 KB | 80 MB | 20,000 | 20 ms |
| ColPali, raw | 10,000 | 1024 | 262 KB | 2.6 GB | 650,000 | 650 ms |

### CPU Cost for MaxSim Scoring

| Scenario | C | m×n per doc | Total FLOPs | Time (AVX-512, 8 cores) |
|---|---|---|---|---|
| ColBERT (m=32, n=128, d=128) | 1,000 | 524K | 524M | <1 ms |
| ColPali (m=100, n=1024, d=128) | 1,000 | 13.1M | 13.1B | ~4 ms |
| ColPali (m=100, n=1024, d=128) | 10,000 | 13.1M | 131B | ~40 ms |

### Bottleneck Analysis

| Scenario | SSD I/O | CPU compute | Bottleneck |
|---|---|---|---|
| ColBERT compressed, C=1000 | 1 ms | <1 ms | **neither** (trivial) |
| ColPali raw, C=1000 | 65 ms | 4 ms | **SSD** |
| ColPali raw, C=10000 | 650 ms | 40 ms | **SSD** (16×) |
| ColPali compressed, C=1000 | 2 ms | ~10 ms (decompress+score) | **CPU** |
| ColPali compressed, C=10000 | 20 ms | ~100 ms | **CPU** |

**Key insight**: For uncompressed/lightly compressed ColPali-scale models at high candidate counts, **SSD I/O dominates**. Heavy compression shifts the bottleneck to CPU (decompression + scoring). The SSD problem is most acute in the regime where quality-sensitive applications avoid aggressive compression.

---

## 4. Prior Work Boundary (15 systems)

### 4.1 Late-Interaction Retrieval Engines (in-memory)

| System | Year/Venue | Mechanism | Addresses SSD? |
|---|---|---|---|
| **ColBERT/v2** | SIGIR'20 / NAACL'22 | Per-token embeddings + MaxSim; centroid-residual compression | No — in-memory |
| **PLAID** | CIKM'22 | Centroid interaction → candidate pruning → decompress survivors | No — in-memory; centroid interaction avoids full decompression but assumes index in RAM |
| **WARP** | SIGIR'25 | Dynamic similarity imputation + implicit decompression; 41× over XTR | No — in-memory; reduces computation not I/O |
| **XTR** | NeurIPS'23 | Token-level retrieval → score from retrieved tokens only (no full doc read) | Partially — avoids full-doc read, but token index itself must be in memory |
| **TACHIOM** | arXiv 04/2026 | Token-aware clustering + hierarchical indexing; 247× faster clustering | No — in-memory; faster clustering, not I/O optimization |

### 4.2 Multi-Vector → Single-Vector Reduction

| System | Year/Venue | Mechanism | Addresses SSD? |
|---|---|---|---|
| **MUVERA** | NeurIPS'24 | Fixed Dimensional Encoding (FDE); data-oblivious projection | Indirectly — converts to single-vector, so existing disk ANN applies. **But loses MaxSim exactness** |
| **LEMUR** | arXiv 01/2026 | Learned neural reduction to single vector | Same as MUVERA — loses exact MaxSim |
| **ConstBERT** | ECIR'25 | Fixed number of vectors per document (learned pooling) | Partially — fixed-size reduces I/O variance; still needs all vectors read |

### 4.3 Compression / Pruning (reduce payload size)

| System | Year/Venue | Mechanism | Addresses SSD? |
|---|---|---|---|
| **HPC-ColPali** | arXiv 06/2025 | K-means quantization (32×) + attention-guided pruning (60% patches) | Indirectly — smaller payload means less I/O. But still reads ALL surviving vectors |
| **SAP** | arXiv 01/2026 | Training-free structural anchor pruning; 90% patches pruned | Same — reduces payload, doesn't change I/O pattern |
| **CRISP** | arXiv 05/2025 | End-to-end learnable clustered representations | Same |
| **ColBERTSaR** | SIGIR'26 | Sparsified ColBERT via PQ; 50-70% smaller than PLAID | Same — smaller index, same "read all" pattern |
| **MM-Matryoshka** | arXiv 06/2026 | 2D elastic (dimension + layer) budget selection | Same — flexible compression, same read pattern |

### 4.4 Cascading / Hybrid

| System | Year/Venue | Mechanism | Addresses SSD? |
|---|---|---|---|
| **HEAVEN** | ACL'26 Findings | Single-vector (DSE) stage 1 → multi-vector (ColQwen2.5) stage 2 | Partially — reduces C, but stage 2 still reads all vectors of each candidate |
| **Visual RAG Toolkit** | SIGIR'26 Demo | Tile-level pooling → multi-stage search | Same — cheaper stage 1, full MaxSim stage 2 |

### 4.5 Disk-Resident ANN (single-vector)

| System | Relevance |
|---|---|
| **DiskANN/Vamana** | Graph traversal on SSD for single-vector ANN; doesn't handle grouped multi-vector scoring |
| **DGAI (PZ's work)** | Dynamic graph ANN with disk I/O optimization; single-vector only |
| **SPANN** | Inverted index partitioning for disk ANN; single-vector |

### 4.6 Analogous Techniques from Text Retrieval

| Technique | Analogy to Multi-Vector | Gap |
|---|---|---|
| **Block-Max WAND** | Per-block score upper bounds for posting lists → skip documents | Operates at document level (skip entire documents from a term's posting list). Multi-vector bounds operate at **intra-document** level (skip parts of a document). Different granularity. |
| **Document-at-a-time (DAAT)** | Process one document completely before moving to next | Multi-vector is inherently DAAT; the question is whether you can process a document **partially** |
| **Late materialization (columnar DBs)** | Read only needed columns | Analogous to reading only needed "columns" of a document's vectors. But multi-vector scoring isn't column-selective — every vector could contribute to any query token |
| **WAND** | Weak-AND with per-term upper bounds | Multi-vector version would be per-page upper bounds. Not formalized for MaxSim |

### Summary: What's Missing

**No existing system combines ALL of:**
1. Partial-document MaxSim scoring with page-level bounds (skip unread pages)
2. SSD-aware page layout optimized for multi-vector access patterns
3. Adaptive reading strategy (read pages in order of expected score contribution)

XTR comes closest by avoiding full-doc reads, but its token-level index is in-memory and the scoring mechanism is different (uses only retrieved tokens, not exact MaxSim). MUVERA/LEMUR avoid the problem by converting to single-vector but sacrifice MaxSim exactness.

The block-max WAND analogy is the closest conceptual match, but it operates at a different level (inter-document vs intra-document) and hasn't been formalized for the multi-vector MaxSim case on SSD.

---

## 5. Bottleneck Evidence

### Evidence FOR an SSD bottleneck

1. **Scale arithmetic**: ColPali at 100M pages = 26 TB raw, 800 GB compressed. Neither fits in memory. Reranking MUST read from SSD.

2. **PLAID profiling** (Santhanam et al. 2022): "Gathering vectors from the index is expensive because it consumes significant memory bandwidth: each vector is encoded with a 4-bit centroid ID and 32-byte residuals, with tens of vectors per passage." If memory bandwidth is already a bottleneck, SSD bandwidth is worse by ~10-50×.

3. **ColPali I/O dominance**: At C=1000 uncompressed candidates, SSD random reads (65 ms) exceed CPU scoring (4 ms) by 16×. This gap grows with C.

4. **Industry signals**: The ECIR 2026 "LIR: Workshop on Late Interaction and Multi-Vector Retrieval" and rapid publication rate (15+ papers in 2025-2026) indicate the community recognizes scalability as an open problem.

### Evidence AGAINST an SSD bottleneck

1. **Compression may eliminate it**: HPC-ColPali achieves 32× compression with <2% NDCG loss. At 8 KB/doc, 1000 candidates = 8 MB — trivial on NVMe. The bottleneck shifts to CPU decompression.

2. **Cascading reduces C**: HEAVEN/Visual RAG Toolkit use single-vector stage 1 to reduce C to ~100. At C=100 even uncompressed ColPali needs only 26 MB — fast on NVMe.

3. **XTR avoids full-doc reads entirely**: By scoring from retrieved tokens only, the full-document I/O never happens (at some quality cost).

4. **Future hardware**: CXL-attached memory, persistent memory, and faster NVMe (PCIe 5/6) may make the bottleneck irrelevant.

### Net Assessment

The SSD bottleneck is **real but conditional**: it exists in the regime of (large corpus) × (high candidate count OR high recall requirement) × (no/light compression). Aggressive compression or aggressive candidate pruning can eliminate it. The research question is whether there's a **third approach** — partial-document reading with score bounds — that avoids the quality loss of compression and the recall loss of aggressive candidate pruning.

---

## 6. Three Candidate Formal/System Objects

### Object 1: Page-Level MaxSim Score Bounds (strongest formal object)

**Definition**: Given a document D stored across pages P₁, ..., P_k, and per-page metadata M(P_j), define:

```
LB(Q, D, R) = Σ_i max_{j ∈ read_pages(R)} sim(q_i, d_j)
UB(Q, D, R) = LB(Q, D, R) + Σ_i max_{P ∈ unread_pages(R)} ub_contrib(q_i, M(P))
```

Where `ub_contrib(q_i, M(P))` bounds the maximum possible similarity between q_i and any vector on page P, computed from metadata M(P) alone.

**Required properties**:
- Soundness: LB ≤ true Score ≤ UB
- Usefulness: UB < top-k threshold before all pages read (for a meaningful fraction of candidates)
- Metadata efficiency: |M(P)| ≪ |P| (metadata much smaller than full vectors)

**Metadata candidates**:
- Per-page centroid vector c_P and max residual norm r_P: ub_contrib(q_i, M(P)) = sim(q_i, c_P) + ||q_i|| × r_P
- Per-page min/max per dimension: hyperrectangle bound
- Per-page sketch (random projection summary)

**Formal question**: For what metadata size M, what fraction of candidates can be pruned after reading fraction f of their pages? Is there a phase transition in pruning effectiveness as f increases?

**Novelty claim**: Block-max WAND operates on term-level posting lists and skips entire documents. This operates WITHIN a document and skips pages of vectors. The scoring function (MaxSim with max-then-sum structure) creates different bound properties than term-level tf-idf/BM25 scoring. No prior work formalizes page-level MaxSim bounds for SSD-resident grouped vectors.

### Object 2: Cost-Optimal Adaptive Page Reading Order

**Definition**: Given C candidates, each with k pages and per-page metadata, and a current top-k threshold θ, determine the optimal order to read pages across ALL candidates to minimize total I/O while correctly identifying the top-k documents.

**Formal framework**: This is an instance of the **adaptive submodularity** problem:
- State: (pages read per candidate, current scores, current threshold θ)
- Action: choose next page to read (from any candidate)
- Objective: minimize total pages read subject to correct top-k identification
- The score function is monotone submodular per candidate (each new page can only increase score)

**Key insight**: Cross-candidate scheduling matters. If candidate A's UB drops below θ after reading 2/8 pages, those 6 saved reads can be "spent" on candidate B instead.

**Formal question**: What is the competitive ratio of greedy page selection (read the page with highest expected utility) vs optimal offline strategy? Is there a constant-factor approximation?

**Novelty claim**: Traditional top-k algorithms (threshold algorithm, NRA) assume you read one attribute at a time for all candidates. Here, you choose which candidate's which page to read next, with the additional constraint that pages have SSD-specific costs (seek + transfer). The combination of MaxSim scoring + SSD page reads + adaptive scheduling is new.

### Object 3: Score-Completion-Cost-Aware Page Layout

**Definition**: Given a corpus of N documents, each with n vectors, and a page size B, find a packing of vectors into pages that minimizes expected score-completion cost under the adaptive reading strategy from Object 2.

**Formal framework**: Joint optimization of:
- Document vectors → page assignment
- Page reading order for typical queries
- Expected I/O cost (weighted by query distribution)

**Layout options to compare**:
1. **Document-contiguous**: All vectors of a document on consecutive pages. Sequential reads, but no cross-document sharing and no early termination benefit.
2. **Semantic-clustered**: Vectors from different documents with similar embeddings share pages. Reduces redundancy but breaks document locality.
3. **Score-stratified**: Within each document, separate high-importance vectors (likely MaxSim winners) from low-importance ones. Read high-importance pages first for tighter bounds. Requires offline analysis of vector importance distributions.
4. **Summary-payload separation**: Compact metadata/summary vectors on separate pages from full-precision vectors. Enables bound computation before full reads.

**Formal question**: Is there a layout that achieves O(k·log(C/k)) expected page reads for top-k identification (matching information-theoretic lower bound for comparison-based selection), or is the problem inherently harder due to MaxSim's structure?

**Novelty claim**: Existing disk ANN layout optimization (e.g., Vamana's sector-based packing) optimizes for graph traversal I/O where each read reveals independent objects. Multi-vector layout must optimize for grouped reads where partial reads enable pruning — a fundamentally different objective.

---

## 7. Strongest Reviewer Objections

### Objection 1: "Compression Already Solves This" (most dangerous)

HPC-ColPali achieves 32× compression. At 8 KB/doc, SSD I/O for 1000 candidates is 8 MB = ~1 ms on NVMe. Where's the bottleneck?

**Counter**: (a) Compression has quality cost; quality-sensitive applications (legal, medical) avoid it. (b) Future models produce more vectors (higher resolution → more patches). ColQwen3-4B at higher resolution could produce 4096+ patches. (c) Partial-document bounds are ORTHOGONAL to compression — they reduce the number of candidate reads, not the size of each read. Apply both for multiplicative gains. (d) 32× compression reduces B_abs per doc, but if C is large (10K for high recall), total I/O is still 80 MB compressed → non-trivial.

### Objection 2: "This Is Just Block-Max WAND for Vectors"

The page-level bound with early termination is structurally identical to block-max WAND.

**Counter**: (a) BMW operates on per-term posting lists; this operates on per-document vector groups. The data structures and access patterns are fundamentally different. BMW skips over documents within a posting list; this skips over pages within a document. (b) MaxSim (max-then-sum) has different mathematical properties than BM25 (sum of per-term scores). The bound tightness analysis is different. (c) BMW doesn't involve SSD page layout optimization — it operates on pre-sorted posting lists. The layout problem is new.

### Objection 3: "Cascading Eliminates the Reranking Problem"

HEAVEN + Visual RAG Toolkit already use single-vector stage 1 to reduce C. If C=100, even uncompressed ColPali is 26 MB — fast.

**Counter**: (a) Single-vector stage 1 introduces recall loss. The whole point of multi-vector is fine-grained matching that single-vector misses. Low C means low recall in the exact-scoring stage. (b) The question of "how low can C go without hurting recall" is itself a function of the reranking strategy. If partial-document reading makes reranking cheaper, you can afford higher C, which means higher recall. (c) For visual document retrieval, single-vector representations are particularly lossy — they can't distinguish documents that differ in spatial layout.

### Objection 4: "The Bounds Will Be Useless in Practice"

If document vectors are high-dimensional and diverse, per-page upper bounds stay loose until almost all pages are read.

**Counter**: This is the key empirical question. But structural properties of real documents suggest bounds can be useful: (a) ColPali patches from the same spatial region are highly correlated → one page's centroid is informative about the rest. (b) Many query tokens match "easy" patterns (common words, background patches) that can be resolved with a single page read. (c) The important case is eliminating non-top-k candidates early — even a loose bound can separate obvious non-matches from top candidates.

### Objection 5: "CPU Dominates, Not SSD"

MaxSim scoring is compute-intensive. With decompression, CPU may dominate.

**Counter**: (a) Uncompressed ColPali: I/O 65 ms vs CPU 4 ms → SSD dominates by 16×. (b) Even with compressed vectors, partial-document reading avoids BOTH I/O AND CPU for pruned pages. (c) SIMD/AVX-512 makes MaxSim very fast; SSD random reads don't benefit from instruction-level parallelism the same way.

---

## 8. Preliminary Scores

| Criterion | Score | Rationale |
|---|---|---|
| **Significance** | 7/10 | Multi-vector retrieval is a major trend (15+ papers in 2025-2026). SSD residency is the next frontier as corpora scale beyond memory. But significance depends on proving the bottleneck exists at production scale. |
| **Novelty** | 7/10 | Page-level MaxSim bounds with adaptive reading is genuinely new — no prior work formalizes this for SSD-resident grouped vectors. Risk: reviewer may see it as "obvious extension of block-max WAND." Need strong separation argument. |
| **System specificity** | 8/10 | Directly tied to SSD page granularity, random read costs, and storage layout. Cannot be solved by algorithm alone — requires storage-aware design. Strong systems contribution. |
| **Hardware fit** | 9/10 | PZ's multi-NVMe server is ideal. No GPU required. SQLite/direct I/O skills transfer from DGAI. ColPali embedding generation can use cached/precomputed embeddings. |
| **Feasibility** | 7/10 | A0 (toy model) is straightforward. Full experiment needs a ColPali index at scale — can use precomputed embeddings from ViDoRe or similar. Main risk: the bound may be too loose to yield meaningful I/O savings on real data. |

---

## 9. Key Open Questions for Codex Review

1. Does XTR's "score from retrieved tokens only" approach ALREADY solve the I/O problem? If XTR achieves exact-MaxSim-equivalent quality without reading full documents, the SSD problem vanishes.

2. Is MUVERA's FDE approximation tight enough that exact MaxSim reranking is never needed? If so, the multi-vector SSD problem reduces to single-vector disk ANN.

3. What is the actual storage breakdown in a production ColPali deployment? How much is vectors vs metadata vs index?

4. Has anyone published I/O profiling of multi-vector retrieval at billion scale? (Preliminary answer: no — most evaluations are in-memory with <10M documents.)

5. Can per-page centroid + norm metadata (O(d + 1) per page) give tight enough bounds, or does useful bounding require O(n × d) metadata (defeating the purpose)?

---

## Appendix: Non-recommendations

Per gate instructions, this report makes no implementation recommendations. The three formal objects are presented for Codex's independent adversarial review. The strongest threat to the direction is the compression-dominance counterexample (Objection 1): if 32× compression with negligible quality loss makes the SSD problem trivial, the direction should be KILLED.
