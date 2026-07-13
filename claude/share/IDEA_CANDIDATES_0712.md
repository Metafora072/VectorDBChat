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
| 8 | DGAI Selective Recoupling (Query Capsule) | Gpt gate | KILLED — capsule weaker than LRU/vector-hot; 99.54% invalidated at 1% update |
| 9 | DGAI Dynamic Layout Debt | Gpt gate | KILLED — no growing debt; fresh layout ≈ current layout (0.17% diff at 20% update) |
| — | *Next direction* | *TBD* | *Awaiting PZ/Gpt decision — recommend exit DGAI* |

## DGAI Selective Recoupling + Layout Debt Closure (2026-07-13)

Codex ran C0–C4 joint characterization on DGAI with SIFT-900K and GIST-900K:

**Track 1 — Selective Recoupling**:
- 10% space capsule oracle: SIFT -9.48%, GIST -8.16% pages/query
- Simple LRU baseline: SIFT -14.19%, GIST -21.87% — **beats capsule by wide margin**
- Vector-hot cache: SIFT -18.18%, GIST -18.01% — also beats capsule
- Skewed workload: LRU -69/87% vs capsule -7/4%
- After 1% real updates: 99.54% capsule pages invalidated
- **Conclusion**: Ordinary caching captures the available locality; cross-store co-location adds nothing

**Track 2 — Dynamic Layout Debt**:
- 20% uniform update: current 175.405 vs fresh-rebuilt 175.705 pages/query (+0.17%) — no debt
- Adjacency relayout: -14.97% at 0%, -8.26% at 20% — static opportunity that SHRINKS with updates
- Clustered update aligned region: fresh -1.13% — also no debt
- Recall drops 0.9970→0.9632 but C4 layout replay shows identical recall across all layouts → **graph quality degradation, not physical layout**

**Only new finding**: Update-induced graph/search-quality degradation. Needs new mechanism-level gate (delete/reinsert/neighbor repair). Not a storage/I/O problem.

## DecoupleVS Late-Stability Closure (2026-07-13)

- R0 passed (latency-aware search recovers ~16% at W=8)
- R1: phenomenon exists but weak difficulty correlation (Spearman 0.118–0.218)
- R2: fixed quota covers 8.3–8.7% vs oracle 8.6–9.0%; queue contention is binding constraint
- **Killed**: No per-query adaptive scheduler needed

## PageMaxSim Closure (2026-07-12)

- P1: oracle space exists (95.1→80.9 pages)
- P2 + Stage A: L2 residual certificate reads 100% pages; direction information loss
- **Killed**: Mechanism failure at geometric level
