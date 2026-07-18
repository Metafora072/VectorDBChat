# Disk-Resident ANN & Vector Search: Literature Landscape (2024-2026)

**Phase 1 Output — /idea-discovery pipeline**
**Date**: 2026-07-18
**Scope**: Disk-resident ANN and vector search, systems (FAST/VLDB/OSDI) + AI/algorithm (NeurIPS/ICML/ICLR)
**Exclusions**: Vamana internal optimization axes (repair, page layout, degree, beam, cache, query adaptation) — all closed

---

## 1. Landscape Table

| # | Paper | Venue | Year | Method | Key Result | Theme |
|---|-------|-------|------|--------|------------|-------|
| 1 | CXL-ANNS | ASPLOS | 2024 | CXL-attached memory pool for ANN, compute-memory disaggregation | Scales beyond single-node DRAM | HW-Arch |
| 2 | Cosmos | — | 2025 | Distributed vector search on disaggregated memory | Cross-node ANN with RDMA/CXL | HW-Arch |
| 3 | d-HNSW | — | 2025 | HNSW on disaggregated memory with remote page access | Preserves graph quality across memory tiers | HW-Arch |
| 4 | RetroInfer | VLDB | 2026 | KV cache as vector storage; wave index with tripartite attention approx | 4.5-10.5× speedup over FlashAttention, 1M context at 27 tok/s | LLM-Vec |
| 5 | QVCache | — | 2026 | Query-aware vector cache for RAG | Reduces redundant retrievals in RAG pipeline | LLM-Vec |
| 6 | QCFuse | — | 2026 | Compressed-view cache fusion for RAG serving | Fuses cached + fresh retrieval | LLM-Vec |
| 7 | TeleRAG | — | 2025 | RAG query routing and optimization | End-to-end RAG latency reduction | LLM-Vec |
| 8 | SymphonyQG | SIGMOD | 2025 | RaBitQ + graph with FastScan, avoids re-ranking | 1.5-4.5× QPS vs best baselines at 95% recall | Quant-Graph |
| 9 | QuIVer | arXiv | 2026 | BQ-native graph topology, training-free | 2.5-5.5× throughput vs DiskANN-Rust; works on cosine-native embeddings only | Quant-Graph |
| 10 | CS-PQ | arXiv | 2026 | Cache-friendly SIMD PQ for large-scale index construction | Accelerates construction phase | Quant-Graph |
| 11 | GateANN | arXiv | 2026 | Decouples graph traversal from vector retrieval for filtered search on SSD | Avoids fetching filter-failing nodes; I/O-efficient | Filtered |
| 12 | FusedANN | — | 2025 | Fused filter+ANN on SSD with predicate pushdown | End-to-end filtered disk search | Filtered |
| 13 | Filtered ANN Phase Trans. | arXiv | 2026 | Selectivity-estimation error → plan regret; phase transition model | GLS correlation metric for index selection | Filtered |
| 14 | Curator/SIEVE | — | 2025 | Partition subindexes for low-selectivity + analytical cost model | Workload-specialized index switching | Filtered |
| 15 | FreshDiskANN | — | 2024 | Delta buffer + StreamingMerge for streaming updates | Freshness guarantee via search delta | Dynamic |
| 16 | Quake | — | 2025 | Workload-aware vector database with online parameter adaptation | Adapts to distribution shift | Dynamic |
| 17 | IVF-TQ | — | 2025 | Streaming vector search with temporal quantization | Handles distribution drift in embeddings | Dynamic |
| 18 | P-HNSW | — | 2025 | Crash-consistent HNSW (in-memory, persistent) | Survives crash without index corruption | Consistency |
| 19 | Sparse Nav. Graphs | SODA | 2026 | Minimum edges for α-navigability; Set Cover equivalence | Tight bounds on edge count, O(log n) approx | Theory |
| 20 | Sort Before You Prune | — | 2025 | Sorted α-reachability + beam-search guarantee | Formal graph quality guarantee | Theory |
| 21 | Starling | SIGMOD | 2024 | I/O-efficient disk graph index, topology-guided co-placement | Multi-graph layout optimization | Disk-Sys |
| 22 | PageANN | — | 2025 | Page-node graph from vector graph; page-aligned execution | Page-native graph construction | Disk-Sys |
| 23 | OctopusANN | — | 2025 | Page-read complexity model: degree × path / (overlap × rpp) | Joint layout + page search | Disk-Sys |
| 24 | PipeANN | — | 2024 | Pipelined async I/O + computation for disk ANN | Hides I/O latency behind computation | Disk-Sys |
| 25 | VeloANN | — | 2025 | Fast disk-resident ANN with locality-aware layout | Improved SSD throughput | Disk-Sys |
| 26 | MicroNN | arXiv | 2025 | On-device disk-resident updatable vector database | Mobile/edge deployment | Disk-Sys |
| 27 | LSM-VEC | — | 2025 | LSM-tree based vector index | Log-structured vector updates | Learn-Idx |
| 28 | LeaFi | — | 2025 | Learned filter for ANN search | ML-based candidate filtering | Learn-Idx |
| 29 | RoarGraph | — | 2024 | Query-distribution-aware graph construction from query logs | Offline workload-specialized graph | Learn-Idx |
| 30 | ColPali | — | 2025 | Multi-modal document retrieval with vision-language models | End-to-end doc retrieval without OCR | Multi-Modal |
| 31 | MM-Matryoshka | — | 2025 | Multi-modal matryoshka representations, adaptive dimensionality | Variable-precision multi-modal embeddings | Multi-Modal |
| 32 | B+-tree on ZNS | ACM TACO | 2026 | Co-designed B+-tree for ZNS append-only zones | Index adaptation for ZNS semantics | ZNS |

---

## 2. Thematic Synthesis

### Theme A: New Storage Hardware for ANN (CXL, Disaggregated Memory, ZNS)

CXL-ANNS, Cosmos, and d-HNSW represent a new wave exploiting CXL/RDMA-attached memory pools to scale ANN beyond single-node DRAM. These systems disaggregate compute from memory, enabling elastic scaling and sharing of large indices across nodes. The fundamental challenge is trading remote-access latency for capacity.

**Gap: ZNS SSD for ANN is completely unexplored.** B+-tree co-design for ZNS (ACM TACO 2026) shows that adapting index structures to ZNS append-only semantics is a real and publishable problem. Graph ANN's random-update-in-place pattern (edge insertion/deletion, neighbor repair) fundamentally conflicts with ZNS's sequential-write-only zones. A ZNS-native ANN index would require rethinking update propagation — potentially log-structured graph maintenance with zone-aligned compaction. This is a clean hardware-driven problem with no prior work.

### Theme B: Vector Search for LLM Serving (KV Cache, RAG, Semantic Cache)

RetroInfer (VLDB 2026, Microsoft) is the landmark paper: it reconceptualizes the KV cache as a vector storage problem and builds a specialized "wave index" with tripartite attention approximation. This achieves 4.5-10.5× speedup over FlashAttention for long-context inference. QVCache and QCFuse extend this to RAG-specific caching. Trinity disaggregates vector search from LLM prefill/decode.

**This is a fast-growing area with clear systems+AI crossover potential.** The wave index is ANN-inspired but not a standard ANN index — it exploits attention-specific sparsity structure. Open questions: (1) Can graph-based ANN techniques improve wave index quality? (2) How should the index adapt as the KV cache grows dynamically during generation? (3) Can disk-resident techniques enable even longer contexts by tiering KV to SSD?

### Theme C: Quantization-Graph Co-design

SymphonyQG (SIGMOD 2025) integrates RaBitQ into graph search with FastScan, achieving 1.5-4.5× QPS. QuIVer (2026) goes further: BQ defines the graph topology itself, not just distance computation. Both show that quantization and graph structure are deeply entangled — optimizing them independently leaves performance on the table.

**Gap: No work jointly optimizes quantization codebook + graph topology for the disk-resident setting.** On disk, the payoff is amplified because quantized codes can fit in memory while full vectors stay on SSD. If the quantized graph structure itself is optimized (as QuIVer shows for in-memory), the disk index could potentially avoid many SSD reads entirely.

### Theme D: Filtered ANN on SSD

GateANN, FusedANN, and the Phase Transition paper represent a surge of interest in predicate-aware ANN on disk. GateANN decouples traversal from retrieval to skip filter-failing nodes. The Phase Transition paper reveals that selectivity-estimation errors cause plan regret — the wrong query plan can be orders of magnitude slower. Curator/SIEVE use workload-specialized indexes with analytical cost models.

**This is a well-populated space but with remaining gaps in dynamic filtered indices (filter predicates change over time) and formal selectivity-I/O tradeoff theory.**

### Theme E: Dynamic/Streaming ANN

FreshDiskANN, Quake, IVF-TQ address streaming updates and distribution shift. The key insight across all: buffering + periodic merge is the dominant architecture (analogous to LSM-trees). No system provides formal guarantees on recall degradation during the buffer phase.

**Our M0-M3 infrastructure and deep understanding of Vamana write patterns gives us a unique asset here, but the direction was closed for Vamana-specific variants.** The broader question — formal freshness-recall tradeoff for any graph ANN under streaming updates — remains open.

### Theme F: Crash Consistency for ANN

P-HNSW provides crash consistency for in-memory HNSW. **No crash-consistent disk-resident dynamic ANN exists.** Given that disk-resident ANN (DiskANN, Starling) targets production deployments where crash recovery is mandatory, this is a real systems gap. The challenge: graph ANN updates involve multiple dependent writes (vector, adjacency list, neighbor updates) that must be atomic.

### Theme G: Theoretical Foundations

Sparse Navigable Graphs (SODA 2026) and Sort Before You Prune provide the first formal foundations for graph ANN. **No I/O complexity lower bounds for ANN exist.** External memory lower bounds are well-established for problems like sorting (Ω(n/B log_{M/B} n/B)), set intersection, and subgraph enumeration — but not for approximate nearest neighbor search. A formal I/O complexity model for ANN would be a foundational contribution.

---

## 3. Structural Gaps (Ranked by Research Potential)

| Rank | Gap | Prior Work Boundary | Venue Fit | Our Advantage |
|------|-----|---------------------|-----------|---------------|
| **G1** | ZNS SSD + ANN: append-only zone semantics vs random-update graph | B+-tree on ZNS (TACO 2026), LSM-VEC; NO ANN on ZNS | FAST/VLDB/OSDI | Deep DiskANN internals, M0-M3 write profiling |
| **G2** | I/O complexity lower bounds for ANN | Sparse Nav Graphs (SODA 2026) for edge count; NO I/O model | NeurIPS/SODA/STOC | Can build on SNG's Set Cover equivalence |
| **G3** | KV cache vector index on SSD for ultra-long context | RetroInfer (VLDB 2026) DRAM-only wave index | VLDB/OSDI + NeurIPS | Disk-resident index expertise |
| **G4** | Quantization-graph co-design for disk-resident ANN | SymphonyQG (in-mem), QuIVer (in-mem BQ topology) | SIGMOD/VLDB + ICML | DiskANN+PQ integration knowledge |
| **G5** | Crash-consistent dynamic disk-resident ANN | P-HNSW (in-mem only) | FAST/OSDI/EuroSys | DiskANN update path expertise |
| **G6** | Formal freshness-recall tradeoff for streaming graph ANN | FreshDiskANN (heuristic delta), Quake (parameter tuning) | NeurIPS/ICML theory | M0-M3 write attribution data |
| **G7** | Dynamic filtered ANN on SSD (filters change over time) | GateANN, FusedANN (static filters) | VLDB/SIGMOD | Existing filtered search infrastructure |

---

## 4. Key Observations

1. **RetroInfer changes the game**: KV-cache-as-vector-search is now a VLDB paper. This validates vector DB techniques as first-class contributions to LLM serving — a new venue bridge between systems and AI.

2. **Quantization-topology coupling is the hot frontier**: SymphonyQG → QuIVer shows rapid progression. QuIVer's finding that BQ-native topology works only on cosine-native embeddings suggests embedding-aware index design is an open direction.

3. **ZNS is the cleanest hardware gap**: Every other hardware direction (CXL, disaggregated memory) already has 2-3 papers. ZNS has zero ANN work despite being a major storage trend with real deployment (Samsung, WD).

4. **Theory is wide open**: Beyond SNG's edge-count bounds, there are no formal I/O complexity results for ANN. The external memory model is well-studied for other problems but entirely unexplored for ANN.

5. **Our unique assets**: M0-M3 write attribution infrastructure, deep Vamana/DiskANN implementation knowledge (DGAI, OdinANN), and the exhaustive closure of Vamana-internal directions means we know exactly what doesn't work — a valuable filter.
