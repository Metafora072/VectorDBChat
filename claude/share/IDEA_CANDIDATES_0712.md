# Idea Candidates

| # | Idea | Pilot Signal | Novelty | Status |
|---|------|-------------|---------|--------|
| 1 | DiskColBERT: SSD-Resident Late-Interaction Retrieval Engine | — | KILLED — ESPN + ColBERT-serve 覆盖 | KILLED |
| 2 | Physical Design Advisor for Vector-Augmented Analytical Queries | NEEDS PILOT (pgvector benchmark) | 7/10 — Exqutor did optimizer, not physical design | ACTIVE — pending Codex audit |
| 3 | Multi-Vector Retrieval I/O Characterization | — | KILLED — 失去叙事目标 | KILLED |

## Active Idea: #2 — VAQ Physical Design

- **Hypothesis**: Vector-augmented analytical queries (VAQs) require fundamentally different physical design than pure relational or pure vector workloads. Workload-aware layout/partitioning/materialization can improve VAQ performance by 3-10x over naive co-location.
- **Key evidence**: (1) Exqutor (2025) proved VAQ query optimization matters (10000x) but only did query planner. (2) DiskJoin (SIGMOD 2026) covers pairwise join only. (3) pgvector stores vectors as regular columns with no vector-specific physical optimization. (4) Traditional physical design advisors don't account for vector similarity as an operator.
- **Strongest threat**: VAQ workloads dominated by a single access pattern → design space trivial.
- **Next step**: Codex prior-art audit of Exqutor/DiskJoin/pgvector/PostgreSQL-V/traditional physical design advisors → pgvector benchmark with 3 layouts

## Killed Ideas

### Idea 1: DiskColBERT
- **Kill reason**: ESPN (ISMM 2024) covers GPU+SSD multi-vector reranking. ColBERT-serve (ECIR 2025) covers mmap-based disk serving. Core novelty claim "no disk-resident multi-vector system" invalidated. Capacity and I/O pattern calculations had factual errors (8× underestimate on doc size, random inter-document access mischaracterized as sequential).
- **Remaining space**: CPU-only purpose-built I/O (too narrow for a paper).

### Idea 3: Multi-Vector I/O Characterization
- **Kill reason**: Without a viable system direction (Idea 1 killed), characterization loses narrative purpose. ESPN characterizes GPU path, ColBERT-serve characterizes mmap path. CPU-NVMe profiling is technically uncharted but insufficient as standalone contribution.
