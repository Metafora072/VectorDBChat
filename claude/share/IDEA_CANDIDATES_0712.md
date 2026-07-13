# Idea Candidates

| # | Idea | Source | Status |
|---|------|--------|--------|
| 1 | DiskColBERT | Idea Discovery | KILLED — ESPN + ColBERT-serve |
| 2 | VAQ Physical Design | Idea Discovery | KILLED — MINT + BoomHQ + traditional advisors |
| 3 | Multi-Vector I/O Characterization | Idea Discovery | KILLED — lost narrative target |
| A | SetPageANN / PageMaxSim | Survey-derived | KILLED — exact synopsis mechanism fails (P2 + Stage A) |
| B | SnapCursor | Survey-derived | KILLED — demand unproven, MVCC baseline sufficient |
| **NEW** | **Decoupled ANN Architecture Characterization + Optimization** | **PZ direction** | **ACTIVE — characterization pilot R1** |

## Active Direction: Decoupled ANN Architecture on Modern NVMe

- **Core question**: Does the decoupled architecture (DGAI-style: separate topology/coordinate storage) incur significant I/O amplification on modern high-bandwidth NVMe SSDs compared to coupled architecture (DiskANN/OdinANN)?
- **Methodology change**: Problem-driven, not prior-art-driven. Characterize first, then build story from data. No exhaustive Kill gate before pilot.
- **Key measurements**: Reranking I/O share, coupled vs decoupled I/O count/bytes, per-I/O software overhead, SSD utilization
- **Decision logic**: Coordinate I/O >30% or per-I/O overhead >30% → direction viable. CPU dominant or <20% architecture difference → pivot.
- **Scope**: `claude/share/decoupled_ann_characterization_scope_0713.md`
- **Next step**: Codex executes R1 characterization on DGAI + OdinANN SIFT-900K

## PageMaxSim Closure

PageMaxSim (visual multi-vector page-level progressive evaluation) closed at Stage A:
- P0 passed (multi-page objects exist after token merging)
- P1 passed (page oracle shows 20% space: f9-int8 95.1→80.9 pages)
- P2 failed (single centroid-radius: 100% pages read)
- Stage A failed (multi-ball certificate: still 100% pages read, ~3 false-threatening pages per cell)
- Root cause: L2 residual direction information loss makes safe bounds too loose at page granularity
- This is a mechanism failure, not a prior-art kill
