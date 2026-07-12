# Idea Candidates

| # | Idea | Source | Novelty | Status |
|---|------|--------|---------|--------|
| 1 | DiskColBERT | Idea Discovery Pipeline | KILLED — ESPN + ColBERT-serve | KILLED |
| 2 | VAQ Physical Design | Idea Discovery Pipeline | KILLED — MINT + BoomHQ + traditional advisors | KILLED |
| 3 | Multi-Vector I/O Characterization | Idea Discovery Pipeline | KILLED — lost narrative target | KILLED |
| A | SetPageANN: Page-granular progressive multi-vector evaluation | Survey-derived | TBD — pending Codex audit | PRIOR-ART AUDIT |
| B | SnapCursor: Versioned ANN cursor | Survey-derived | TBD — pending Codex audit (likely KILL) | PRIOR-ART AUDIT |

## Active Candidate: A — SetPageANN

- **Hypothesis**: Even with existing candidate generation and token pruning, multi-vector refinement still reads unnecessary token pages. A progressive page evaluation engine with synopsis-based score bounds can safely skip pages, introducing a new scheduling unit: (object, token-page-group).
- **Key distinction from DiskColBERT**: Contribution is "read less data" not "put data on SSD." Requires proving that page-level skip space is significant AFTER PLAID/WARP pruning.
- **Claude's risks**: (1) Post-pruning tokens per doc may fit in <1 page; (2) IGP reduces candidates to hundreds, limiting absolute I/O savings; (3) ESPN partial reranking is already object-level progressive evaluation.
- **Next step**: Codex prior-art audit → oracle gate if PROVISIONAL

## Secondary Candidate: B — SnapCursor

- **Hypothesis**: Dynamic ANN indexes lack proper pagination semantics. Versioned cursor with compact state, bounded version retention, and cursor-aware GC enables consistent progressive retrieval.
- **Claude's concerns**: Demand risk high (search pagination rare in vector search, RAG re-searches cheaply, agent use case unproven). Existing systems (Milvus time travel, Weaviate cursor API) may suffice. LSM/segment snapshot is nearly free. A0 finding suggests topology mutation may not affect cursor quality.
- **Next step**: Codex prior-art audit → likely KILL unless demand is stronger than expected

## Frozen Candidates (C-F)

| # | Idea | Freeze Reason |
|---|------|---------------|
| C | SLO-ANN (progressive recall-SLO execution) | Filtered-ANN optimizer track crowded |
| D | BridgeIndex (embedding version lifecycle) | Conflicts with A0 topology robustness finding |
| E | MetricOverlay (shared backbone + metric overlays) | More graph algorithm than system |
| F | QuarantineANN (vector poisoning quarantine) | More security/ML than system |
