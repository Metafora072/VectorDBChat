# Phase 1: Literature Survey — ANNS/Vector Database Unexplored Directions

Date: 2026-07-12

## Landscape Map (Avoiding 20+ Killed Directions)

After searching arXiv, Semantic Scholar, and Google Scholar across 9 focus areas, the following landscape emerges for directions **not** covered by our prior kills.

### Sub-Direction 1: Multi-Vector / Late-Interaction Retrieval Systems

| Paper | Venue | Method | Key Result | Relevance |
|-------|-------|--------|------------|-----------|
| WARP | SIGIR 2025 | Dynamic similarity imputation + implicit decompression for ColBERT/XTR | 3x speedup over PLAID, 2-4x less storage | In-memory engine; no disk-resident multi-vector system exists |
| MUVERA | 2024 | SimHash partitioning + AMS sketch → fixed-dim single-vector encoding | 0.72ms retrieval at 128D | Reduces multi-vector to single-vector; loses late interaction quality |
| DocPruner | 2025 preprint | Adaptive patch-level embedding pruning for visual document retrieval | Storage-efficient multi-vector | Compression-focused, not system architecture |
| ColBERTSaR | 2025 preprint | Sparse/inverted representation of ColBERT tokens | Reduced storage | Algorithm contribution |
| MM-Matryoshka | 2026 preprint | 2D multimodal Matryoshka training for budget-elastic retrieval | Flexible dimension/token budget | Training technique, not index system |

**Gap identified:** All multi-vector retrieval engines (WARP, PLAID, ColBERT-serve) are **in-memory**. There is **no disk-resident multi-vector retrieval system**. ColBERT documents have 100-300 token embeddings per document, making billion-document collections require TBs of storage. The MaxSim operation requires accessing all token embeddings of candidate documents. No system has designed SSD-aware data layouts, I/O scheduling, or caching strategies specifically for late-interaction retrieval.

### Sub-Direction 2: Hybrid Search (Vector + Structured Attributes)

| Paper | Venue | Method | Key Result | Relevance |
|-------|-------|--------|------------|-----------|
| FusedANN | 2025 preprint | Lagrangian relaxation → convex fused embedding space | 3x throughput over filtered ANNS | Novel formulation but in-memory |
| Curator | 2025 | Multi-tenant filtered search with shared/per-tenant index | Efficient low-selectivity | Focuses on tenant isolation |
| SIEVE | VLDB 2025 | Collection of specialized indexes for filtered search | Effective across selectivity range | In-memory approach |
| DEG | SIGMOD 2025 | Dynamic edge navigation graph for hybrid search | Efficient graph-based hybrid | In-memory graph |
| Exqutor | 2025 (Microsoft) | Query optimizer for vector-augmented analytical queries | 10000x improvement on TPC-H+vectors | **Query optimizer**, not index |

**Gap identified:** Exqutor is the most interesting — it addresses vector-augmented **analytical** queries (not just kNN), integrating vector search into SQL query optimization. However, it's already published. The broader gap is: **vector similarity as a first-class relational operator** — joins, group-by, aggregation over vector similarity scores. DiskJoin (SIGMOD 2026) addresses similarity join on SSD but only pairwise threshold join, not general analytical queries.

### Sub-Direction 3: Streaming / Temporal Vector Search

| Paper | Venue | Method | Key Result | Relevance |
|-------|-------|--------|------------|-----------|
| Ada-IVF | 2024 | Adaptive IVF partition maintenance for streaming | 2-5x higher update throughput | IVF-specific, not graph |
| IVF-TQ | 2025 preprint | Calibration-free codebook-free residual compression | No retraining needed for streaming | Quantization technique |
| VStream | VLDB 2025 | 4-tier streaming vector search | Comprehensive tiered system | Already in our kill list |

**Gap identified:** Streaming vector search for IVF has Ada-IVF and IVF-TQ, but the broader **index lifecycle management** problem — when to rebuild vs incrementally update, amortized cost models, quality degradation curves under sustained ingestion — lacks a systematic treatment for graph-based indexes.

### Sub-Direction 4: Vector Database Testing & Correctness

| Paper | Venue | Method | Key Result | Relevance |
|-------|-------|--------|------------|-----------|
| Roadmap for VDBMS Testing | 2025 preprint | Survey + roadmap for vector DB software testing | Identifies oracle problem, test generation challenges | **Research roadmap, not system** |
| Storage System Testing Survey | 2025 | Challenges of fuzzing storage systems | State-dependent bugs, brittle oracles | General storage, not vector-specific |

**Gap identified:** This is a genuinely under-explored area. The Roadmap paper explicitly identifies: (1) the **test oracle problem** for approximate search — how to determine if a result is "correct enough", (2) metamorphic relations for vector DB testing, (3) differential testing challenges with approximate results. **No system or tool exists** for systematic vector DB correctness testing. However, this is more of a software engineering contribution than a systems/architecture one.

### Sub-Direction 5: On-Device / Edge Vector Search

| Paper | Venue | Method | Key Result | Relevance |
|-------|-------|--------|------------|-----------|
| MicroNN (Apple) | SIGMOD 2025 | SQLite-based disk-resident IVF for edge devices | 7ms, 90% recall, 10MB memory on million-scale | Production system; covers edge IVF |

**Gap identified:** MicroNN covers IVF-based edge vector search. **No graph-based edge vector search** system exists, but the problem may not be compelling enough (IVF suffices at edge scale).

### Sub-Direction 6: Vector Similarity Join

| Paper | Venue | Method | Key Result | Relevance |
|-------|-------|--------|------------|-----------|
| DiskJoin | SIGMOD 2026 | SSD-based similarity join using graph+IVF indexes | First disk-based billion-scale join | **Very recent, PZ's expertise area** |
| Work Sharing for Threshold Join | 2025 preprint | GPU offloading for approximate threshold join | Efficient shared computation | GPU-focused |

**Gap identified:** DiskJoin just came out (SIGMOD 2026), covering threshold-based similarity join. **Range-constrained or top-k similarity join** on SSD may still have space, but DiskJoin's approach is quite general. The gap is narrow.

### Sub-Direction 7: Vector-Augmented Analytical Queries

| Paper | Venue | Method | Key Result | Relevance |
|-------|-------|--------|------------|-----------|
| Exqutor | 2025 (Microsoft) | Cardinality estimation for vector+SQL queries | 10000x on TPC-H+vectors | Query optimizer for pgvector/DuckDB |
| Tribase | SIGMOD 2025 | Triangle inequality for lossless pruning | Reliable vector query engine | Compression-focused |
| PostgreSQL-V | CIDR 2026 | pgvector characterization and optimization | System-level insights | Characterization |

**Gap identified:** Exqutor shows that vector-augmented analytical query optimization is a real problem. But the **physical design** side — how to co-locate vector data with relational data for mixed analytical+vector queries, how to design buffer management for interleaved vector and relational scans, how to partition data for vector-augmented group-by — is not systematically addressed.

## Structural Gaps and Open Problems

### Gap A: Disk-Resident Multi-Vector Retrieval (ColBERT on SSD)
- **Problem:** ColBERT/late-interaction models store 100-300 token embeddings per document. At billion scale, this is 10-100x more storage than single-vector. All engines (WARP, PLAID) are in-memory.
- **Thinking chain:** ColBERT quality > single-vector → but storage 100x → must go to SSD → MaxSim needs all tokens → dependent reads → graph ANN doesn't apply directly → new index structure needed
- **PZ fit:** Excellent — disk I/O optimization, page layout, caching for token-level access patterns
- **Risk:** Compression approaches (MUVERA, ColBERTSaR, DocPruner) may reduce storage enough to stay in memory

### Gap B: Vector Index Lifecycle Management Under Continuous Ingestion
- **Problem:** Production vector DBs face sustained ingestion. Graph indexes degrade but lack systematic models for when to rebuild vs maintain. Ada-IVF addresses IVF only.
- **Thinking chain:** Streaming data → index quality degrades → when to rebuild? → need degradation model → need cost model for rebuild vs incremental → need system that manages lifecycle
- **PZ fit:** Good — storage lifecycle, amortized I/O cost modeling
- **Risk:** May overlap with our killed "dynamic update" directions; must differentiate by focusing on lifecycle policy, not update mechanism

### Gap C: Vector Database Correctness Testing Infrastructure
- **Problem:** No systematic testing framework exists for vector DBs. Approximate results make oracle definition hard. The 2025 Roadmap paper identifies this as completely open.
- **Thinking chain:** Approximate search → no exact oracle → metamorphic relations? → but what MRs hold for ANNS? → need to discover and validate MRs → build testing framework
- **PZ fit:** Medium — more software engineering than storage systems
- **Risk:** May not be a "systems" paper; better for ICSE/FSE/ISSTA

### Gap D: Physical Design for Vector-Augmented Analytical Workloads
- **Problem:** As vector search becomes a SQL operator (Exqutor), the physical design — data layout, buffer management, partitioning for mixed vector+relational queries — is unexplored.
- **Thinking chain:** Vector = new data type in DBMS → query optimizer (Exqutor) done → but physical design not done → how to co-locate vectors with tuples → how to buffer manage interleaved access → how to partition for vector group-by
- **PZ fit:** Excellent — physical design is core storage systems
- **Risk:** Exqutor + PostgreSQL-V may be close enough; narrow problem scope

### Gap E: Multi-Vector Retrieval Quality-Cost Tradeoff System
- **Problem:** Multi-vector retrieval (ColBERT) offers better quality but 100x more computation. No system provides elastic quality-cost tradeoffs at serving time — e.g., use fewer tokens per document based on query difficulty.
- **Thinking chain:** ColBERT quality > dense → but cost 100x → can we adaptively reduce tokens? → per-query difficulty → per-document importance → need runtime system
- **PZ fit:** Medium-high — runtime resource management, caching
- **Risk:** MM-Matryoshka and DocPruner address this at the model/compression level

## Recommended Directions for Phase 2

**Priority 1: Gap A — Disk-Resident Multi-Vector Retrieval**
Strongest system problem, excellent PZ fit, clear deficiency in existing work (all in-memory), real scale need.

**Priority 2: Gap D — Physical Design for Vector-Augmented Analytics**
Strong system problem at the DB-vector integration boundary, Exqutor opened the door but physical design is untouched.

**Priority 3: Gap B — Vector Index Lifecycle Management**
Real production problem, but risk of overlap with killed directions.
