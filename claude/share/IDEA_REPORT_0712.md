# Research Idea Report

**Direction**: Vector database / ANNS system optimization for a storage systems researcher
**Generated**: 2026-07-12
**Ideas evaluated**: 10 generated → 6 survived first filtering → 3 recommended

## Landscape Summary

The ANNS/vector database space in 2026 is highly active but unevenly explored. Disk-resident single-vector graph search (DiskANN family) is saturated with 30+ systems. In-memory multi-vector retrieval (ColBERT/PLAID/WARP) is advancing rapidly but remains entirely in-memory. Vector-augmented SQL analytics has emerged as a real problem (Exqutor 2025, DiskJoin SIGMOD 2026) but physical design is untouched. Streaming index maintenance has Ada-IVF (IVF) and IVF-TQ but lacks graph-index coverage. Vector DB testing is an acknowledged open problem (2025 Roadmap paper) but is more software engineering than systems.

Critical finding: LEMUR (2025) reduces multi-vector search to single-vector via learned projection, enabling DiskANN integration. This partially closes Gap A but introduces a quality-latency tradeoff — native multi-vector disk retrieval could outperform reduced single-vector approaches. Constant-space multi-vector representations (ECIR 2025) fix document size on disk but don't address I/O-aware layout or MaxSim-specific scheduling.

## Recommended Ideas (ranked)

---

### Idea 1: SSD-Resident Late-Interaction Retrieval Engine (DiskColBERT)

**Hypothesis**: A purpose-built SSD-resident retrieval engine for multi-vector (ColBERT-style) representations can serve billion-document late-interaction queries with quality matching WARP/PLAID while requiring only O(100 MB) DRAM, by designing token-group-aware page layout, MaxSim-specific I/O scheduling, and hierarchical candidate filtering.

**Background→Problem→Motivation→Challenge chain**:
- **Background**: Late-interaction models (ColBERT) achieve superior retrieval quality over single-vector by preserving token-level interactions. PLAID/WARP have made in-memory retrieval efficient (sub-40ms). But storage scales linearly with tokens: 1B documents × 128 tokens × 128D × 2B (compressed) ≈ 32 TB.
- **Problem**: At billion scale, multi-vector indexes cannot fit in memory. LEMUR reduces to single-vector (loses quality). PLAID SHIRTTT does hierarchical sharding but assumes in-memory shards. No system designs SSD data layouts or I/O patterns for MaxSim retrieval.
- **Motivation**: MaxSim is fundamentally different from kNN — it requires accessing ALL tokens of a candidate document to compute the score (sum of max per-query-token similarities). This means the I/O pattern is not a dependent graph walk but rather: (1) identify candidate documents via centroid matching, (2) read all token embeddings of each candidate. Phase 1 is an inverted index lookup; Phase 2 is a bulk sequential read per candidate. This pattern is naturally SSD-friendly if tokens are co-located by document.
- **Challenge 1**: Centroid-based candidate identification (PLAID's approach) requires cluster centroids in memory. With 65K clusters × 128D × 4B = 32 MB — this fits.
- **Challenge 2**: Reading compressed token embeddings from SSD for each candidate. If a document has 128 tokens at 2B residual each, that's 256B + overhead ≈ 512B per document. A 4KB page can hold ~8 documents' tokens. With 1000 candidates, that's ~125 4KB reads — feasible at NVMe speeds.
- **Challenge 3**: The quality of centroid-based pruning determines how many candidates need full token reads. A better pruning layer reduces I/O.

**Deficiency in existing work**: WARP/PLAID assume in-memory token access. LEMUR trades quality for single-vector reduction. Constant-space approaches fix doc size but don't optimize I/O. No system exploits the fact that MaxSim's I/O pattern (bulk per-document read after inverted index filtering) is structurally different from graph-ANN's dependent reads and potentially MORE SSD-friendly.

**Minimum experiment**:
1. Profile PLAID/WARP on MS MARCO (8.8M passages) to measure: (a) candidate count after centroid filtering, (b) token access pattern per candidate, (c) total bytes touched per query.
2. Simulate SSD retrieval: place compressed token residuals on NVMe, co-located by document. Measure actual read latency for retrieving top-1000 candidates' tokens.
3. Compare: LEMUR+DiskANN (single-vector reduction) vs native SSD multi-vector retrieval in quality-latency Pareto.

**Expected outcome**: If native SSD multi-vector retrieval achieves <50ms at 90%+ of PLAID quality while using <200MB DRAM, the direction is viable. If LEMUR+DiskANN matches quality at lower latency, the direction is subsumed.

**Novelty**: 8/10 — No disk-resident multi-vector system exists. LEMUR reduces to single-vector (different approach). Constant-space doesn't address I/O. PLAID SHIRTTT is in-memory sharding. Closest: DiskANN (single-vector disk) + PLAID (in-memory multi-vector) = no intersection.
**Feasibility**: High — can prototype on single NVMe SSD with MS MARCO. No GPU needed for system evaluation.
**Risk**: MEDIUM — LEMUR's quality may be "good enough", eliminating motivation for native multi-vector disk retrieval.
**Contribution type**: New system
**Target venue**: SIGIR/VLDB/KDD (IR+systems crossover)

**Reviewer's likely objection**: "Why not just use LEMUR to reduce to single-vector and apply DiskANN?" — Must show quality gap is significant and native approach has better I/O efficiency for the specific MaxSim pattern.

**Why we should do this**: Multi-vector retrieval is the future of high-quality search (ECIR 2026 workshop launched). Storage is the bottleneck. PZ's SSD I/O expertise is exactly what's needed to design the first disk-resident engine. The MaxSim I/O pattern (inverted index → bulk document reads) is structurally different from graph-ANN dependent reads — existing disk-ANN techniques don't transfer, creating genuine design space.

---

### Idea 2: Physical Design Advisor for Vector-Augmented Analytical Queries

**Hypothesis**: Vector-augmented analytical queries (VAQs) require fundamentally different physical design (data layout, partitioning, materialized views) than pure relational or pure vector workloads, and a workload-aware physical design advisor can improve VAQ performance by 3-10x over naive co-location strategies.

**Background→Problem→Motivation→Challenge chain**:
- **Background**: Exqutor (Microsoft 2025) showed that vector similarity as a SQL operator creates new query optimization challenges. DiskJoin (SIGMOD 2026) addresses pairwise similarity join on SSD. pgvector/SQL Server 2025/DuckDB now support vector types natively.
- **Problem**: Query optimization is addressed (Exqutor), but physical design is not. When a query does `SELECT category, AVG(similarity(v, query)) FROM products GROUP BY category`, the optimal data layout depends on whether the workload is filter-first, vector-first, or mixed. No system provides guidance.
- **Motivation**: In traditional DBMSs, physical design advisors (index selection, partitioning, materialization) are mature. For vector-augmented workloads, the design space is new: should vectors be stored inline with tuples or in a separate column store? Should vector indexes partition by attribute ranges or by vector clusters? Should pre-computed similarity scores be materialized as views?
- **Challenge**: The interaction between relational operators and vector similarity creates a combinatorial design space. A group-by on category after vector filtering wants category-partitioned storage; a vector search after category filtering wants vector-clustered storage within each partition.

**Deficiency in existing work**: Exqutor only handles cardinality estimation / plan selection, not physical design. pgvector stores vectors as regular columns with no vector-specific physical optimization. DiskJoin optimizes one operation (pairwise join) not general VAQ workloads.

**Minimum experiment**:
1. Create a VAQ benchmark: extend TPC-H with embeddings (Exqutor's approach) plus new query templates involving vector group-by, vector join, filtered vector search, and vector-augmented aggregation.
2. Profile pgvector/DuckDB on these queries: identify which queries are bottlenecked by vector I/O vs relational I/O vs both.
3. Prototype 3 physical layouts: (a) inline vectors, (b) separate vector column store, (c) hybrid partitioned by attribute + clustered by vector within partition. Measure performance difference.

**Expected outcome**: If layout choice affects performance by >3x on realistic VAQ workloads, the physical design advisor problem is real and worth solving.

**Novelty**: 7/10 — Exqutor opened the problem but only did query optimization. Physical design for vectors is new. Closest: traditional physical design advisors + vector index tuning (HAKES) = not the same problem.
**Feasibility**: High — can use pgvector + DuckDB on single machine. TPC-H extension from Exqutor is available.
**Risk**: MEDIUM — If VAQ workloads turn out to be dominated by one pattern (always filter-first or always vector-first), the design space collapses.
**Contribution type**: New system + empirical finding
**Target venue**: VLDB/SIGMOD

**Reviewer's likely objection**: "Isn't this just database physical design with a new data type?" — Must show vector-specific challenges (approximate results, dimensionality-dependent I/O patterns, index-query interaction) create genuinely new design decisions.

---

### Idea 3: Multi-Vector Retrieval as a Storage System Problem — Characterization and Design Space Exploration

**Hypothesis**: The I/O and storage characteristics of multi-vector retrieval (ColBERT/MaxSim) are fundamentally different from single-vector ANN and deserve a systematic characterization that reveals non-obvious design principles for scalable multi-vector systems.

**Background→Problem→Motivation→Challenge chain**:
- **Background**: Multi-vector retrieval is gaining traction (ECIR 2026 workshop, WARP at SIGIR 2025, LEMUR, SSR). All work optimizes computation and compression. None characterizes the storage and I/O behavior.
- **Problem**: We don't know basic facts: How does multi-vector retrieval's I/O pattern differ from single-vector? What's the working set size? How does caching behavior differ? What's the bandwidth utilization? Is the bottleneck random reads, sequential reads, or CPU?
- **Motivation**: Without characterization, system designs are guesses. IISWC 2025 did this for Milvus+DiskANN and found only 24% SSD bandwidth utilization — a surprising result that motivated new work. The same treatment for multi-vector retrieval could reveal equally surprising insights.
- **Challenge**: Multi-vector systems are complex (centroid matching → candidate shortlisting → full token scoring → re-ranking), with different I/O patterns at each stage.

**Deficiency in existing work**: VIBE (2025) benchmarks ANN algorithms but doesn't characterize I/O. IISWC 2025 characterized single-vector DiskANN but not multi-vector. No paper profiles the storage/I/O behavior of PLAID, WARP, or ColBERT-serve.

**Minimum experiment**:
1. Instrument PLAID and WARP with I/O tracing (system calls, page cache hits, bandwidth utilization, latency breakdown).
2. Run on MS MARCO and BEIR at varying scales (1M, 10M, 100M if feasible).
3. Profile: working set, cache hit rates, read amplification, CPU vs I/O time breakdown, stage-by-stage latency.
4. Compare with single-vector DiskANN characterization (IISWC 2025 numbers as reference).

**Expected outcome**: Discover whether multi-vector retrieval is I/O-bound, compute-bound, or memory-bound at different scales. Identify which stages are bottlenecks. Produce design guidelines for future SSD-resident multi-vector systems.

**Novelty**: 6/10 — Characterization papers have lower novelty but high impact. IISWC 2025 did DiskANN; this would be the ColBERT equivalent.
**Feasibility**: Very high — requires no new system, just instrumentation and measurement.
**Risk**: LOW — characterization always produces results; the question is whether insights are surprising enough.
**Contribution type**: Empirical finding + design guidelines
**Target venue**: FAST/ATC/VLDB (characterization track)

**Why we should do this**: Even if Idea 1 or 2 is pursued, this characterization provides the foundation. If results show multi-vector retrieval is naturally SSD-friendly (our hypothesis from the MaxSim access pattern analysis), it strongly motivates Idea 1.

---

## Eliminated Ideas (for reference)

| Idea | Reason eliminated |
|------|-------------------|
| Graph index lifecycle manager (rebuild vs maintain policy) | Too close to killed directions (dynamic graph ANN update). Ada-IVF covers IVF. Risk of re-entering saturated space. |
| Vector DB correctness testing framework (metamorphic testing for ANNS) | More software engineering (ICSE/FSE) than systems (FAST/VLDB). PZ's storage expertise not the primary asset needed. |
| Edge/on-device multi-vector retrieval | MicroNN (Apple, SIGMOD 2025) covers edge IVF. Adding multi-vector is a narrow extension. |
| Streaming multi-vector index maintenance | PLAID SHIRTTT (SIGIR 2024) already addresses streaming ColBERT with hierarchical sharding. |
| Cross-modal vector join operator | Too algorithmic; FusedANN (2025) already proposes convex fusion. |
| Vector-aware buffer manager for DBMS | Too narrow; likely rejected as "just cache policy with a new cost model." |
| Pre-computed similarity materialized views | Too application-specific; hard to generalize. |

## Pilot Experiment Design (no GPU needed)

| Idea | Method | Time Est | Key Metric | Kill Threshold |
|------|--------|----------|------------|----------------|
| Idea 1 | Profile PLAID I/O + simulate SSD retrieval on MS MARCO | 2-3 days | Latency at 90% quality | If LEMUR+DiskANN achieves same quality at lower latency |
| Idea 2 | VAQ benchmark + 3 layout comparisons on pgvector | 3-4 days | Performance spread across layouts | If spread < 2x, design space is trivial |
| Idea 3 | Instrument PLAID/WARP + run at multiple scales | 3-5 days | I/O characterization data | If all stages are CPU-bound (no storage opportunity) |

## Suggested Execution Order

1. **Start with Idea 3 (characterization)** — lowest risk, produces useful data regardless, and directly informs whether Idea 1 is viable. If multi-vector retrieval turns out to be naturally I/O-friendly on SSD, Idea 1 is strongly motivated.
2. **If Idea 3 shows I/O opportunity → pursue Idea 1 (DiskColBERT)** — the flagship system contribution.
3. **Idea 2 (VAQ physical design) as independent parallel track** — can be explored with pgvector/DuckDB on the same machine.

## Next Steps

- [ ] Codex: verify LEMUR, constant-space MVR, SSR, and PLAID SHIRTTT coverage boundaries for Idea 1
- [ ] Codex: verify Exqutor, DiskJoin, and pgvector physical design coverage for Idea 2
- [ ] If novelty survives: design G0 characterization experiment for Idea 3
- [ ] PZ: decide which direction matches interest and available time
