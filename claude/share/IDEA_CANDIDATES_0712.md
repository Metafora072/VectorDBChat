# Idea Candidates

| # | Idea | Pilot Signal | Novelty | Status |
|---|------|-------------|---------|--------|
| 1 | DiskColBERT: SSD-Resident Late-Interaction Retrieval Engine | NEEDS PILOT (trace-based) | 8/10 — no disk multi-vector system exists | RECOMMENDED |
| 2 | Physical Design Advisor for Vector-Augmented Analytical Queries | NEEDS PILOT (pgvector benchmark) | 7/10 — Exqutor did optimizer, not physical design | BACKUP |
| 3 | Multi-Vector Retrieval I/O Characterization | LOW RISK | 6/10 — characterization, no system | FOUNDATION |

## Active Idea: #1 — DiskColBERT

- **Hypothesis**: A purpose-built SSD-resident engine for ColBERT/MaxSim retrieval can serve billion-document queries with quality matching WARP/PLAID while using O(100 MB) DRAM. The MaxSim I/O pattern (inverted index filtering → bulk per-document token reads) is structurally different from graph-ANN dependent reads and potentially MORE SSD-friendly.
- **Key evidence**: (1) No disk-resident multi-vector system exists. (2) LEMUR reduces to single-vector (quality loss). (3) MaxSim access pattern is inverted-index + sequential per-doc reads, unlike graph-ANN dependent reads. (4) Compressed tokens ~512B/doc → 8 docs per 4KB page → good SSD utilization.
- **Strongest threat**: LEMUR+DiskANN may achieve "good enough" quality after single-vector reduction.
- **Next step**: Codex prior-art verification → characterization pilot (Idea 3) → system design

## Backup Idea: #2 — VAQ Physical Design

- **Hypothesis**: Vector-augmented analytical queries require fundamentally different physical design than pure relational or pure vector workloads.
- **Key evidence**: Exqutor (2025) proved VAQ optimization matters (10000x improvement) but only addressed query planning, not physical design.
- **Next step**: Codex verify Exqutor/DiskJoin/pgvector coverage → pgvector benchmark with 3 layouts
