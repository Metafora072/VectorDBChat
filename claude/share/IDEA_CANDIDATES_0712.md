# Idea Candidates

| # | Idea | Source | Status |
|---|------|--------|--------|
| 1 | DiskColBERT | Idea Discovery | KILLED — ESPN + ColBERT-serve |
| 2 | VAQ Physical Design | Idea Discovery | KILLED — MINT + BoomHQ + traditional advisors |
| 3 | Multi-Vector I/O Characterization | Idea Discovery | KILLED — lost narrative target |
| A | SetPageANN / PageMaxSim | Survey-derived | KILLED — exact synopsis mechanism fails (P2 + Stage A) |
| B | SnapCursor | Survey-derived | KILLED — demand unproven, MVCC baseline sufficient |
| 6 | Decoupled ANN: DGAI-vs-OdinANN R1 | PZ direction | SUPERSEDED — DecoupleVS already answers this |
| 7 | DecoupleVS Late-Stability Dual-Frontier | PZ direction | KILLED — residual not query-dependent, fixed tuning covers oracle |
| — | *Next direction* | *TBD* | *Awaiting PZ/Gpt decision* |

## DecoupleVS Late-Stability Closure (2026-07-13)

Codex built `DecoupleSearch-R` (partial reproduction of DecoupleVS §3.4 on PipeANN/io_uring) and ran R0→R1→R2:

- **R0 passed**: Latency-aware search recovers ~16% mean latency at W=8 vs naive decoupling
- **R1 confirmed phenomenon**: High-recall (B=80) causes trigger rate to drop to 0.4%, exposed tail ~1.17ms. But difficulty-tail Spearman only 0.118–0.218; per-query optimal B does not shift monotonically with difficulty quartile
- **R2 killed design motivation**:
  - Oracle A (perfect candidate knowledge): W=4 p99 **worsens 82%** due to queue contention; W=8/16 only 3–4% improvement
  - Oracle B (earliest-safe stability): W=8/16 only 9.5%/5.3% mean improvement
  - Oracle C (bandwidth allocation): Fixed workload-level quota already achieves 8.3–8.7% improvement; per-query oracle adds only 0.3–0.6% more
- **Root cause**: Queue contention is the binding constraint, not stability signal precision. Simple fixed tuning nearly fully covers the recoverable space.
- **Safe claim**: "High recall causes fixed-B late-stability to fail, exposing vector tail, but workload-level queue tuning suffices — no per-query adaptive scheduler needed."

## PageMaxSim Closure (2026-07-12)

PageMaxSim (visual multi-vector page-level progressive evaluation) closed at Stage A:
- P0 passed (multi-page objects exist after token merging)
- P1 passed (page oracle shows 20% space: f9-int8 95.1→80.9 pages)
- P2 failed (single centroid-radius: 100% pages read)
- Stage A failed (multi-ball certificate: still 100% pages read, ~3 false-threatening pages per cell)
- Root cause: L2 residual direction information loss makes safe bounds too loose at page granularity
- This is a mechanism failure, not a prior-art kill
