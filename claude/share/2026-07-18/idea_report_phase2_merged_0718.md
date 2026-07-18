# IDEA_REPORT.md — Phase 2 Merged (Claude + Codex GPT-5.4)

**Direction**: Disk-resident ANN and vector search (systems + AI venues)
**Date**: 2026-07-18
**Phase**: 2 merged — 10 finalist ideas from 21 total (10 Claude + 11 Codex), spanning G1-G7
**Codex session**: 019f75a9-4c07-7412-8fb1-88e4138a10a9

---

## Gap Coverage Index

| # | Idea | Gap(s) | Venue | Source | Quick Novelty |
|---|------|--------|-------|--------|---------------|
| 1 | ZoneEpoch-ANN | G1 | FAST | Codex | PASS (zero prior) |
| 2 | ANN-on-ZNS Feasibility Frontier | G1 | EuroSys | Codex | PASS (zero prior) |
| 3 | Block-Probe Navigability | G2 | SODA | Codex | PASS (no I/O lower bounds exist) |
| 4 | Summary-Bit/Probe Lower Bound | G2+G4 | ICML | Codex | PASS (novel formulation) |
| 5 | FreshCert | G6 | NeurIPS | Codex | PASS (no per-query certificate exists) |
| 6 | Ambiguity-Monotone Graph | G4 | SIGMOD | Codex | CONDITIONAL (check vs δ-EMG) |
| 7 | GraphKV | G3 | VLDB/OSDI | Claude | PASS (no disk-ANN for KV cache) |
| 8 | PageTxn-ANN | G5 | FAST | Codex | PASS (no disk crash-consistent ANN) |
| 9 | Selectivity Is Not Enough | G7 | VLDB | Codex | PASS (novel diagnostic) |
| 10 | AttentionLoop-SSD | G3 | ICLR | Codex | PASS (novel diagnostic) |

---

## Top 5 Recommended Ideas (for Phase 3 deep novelty check)

### Rank 1: FreshCert — Per-Query Freshness Certificates Without Graph Repair

**Gap**: G6 (Freshness-recall tradeoff)
**Venue**: NeurIPS 2026 / ICML 2027
**Contribution**: New method + theoretical result

**Summary**: Given a stale graph index with un-integrated updates in a delta buffer, provide a per-query certificate that proves "this query's top-k result from the stale graph is still valid" without touching the graph. Uses the kth-distance margin from the stale search result and quantized-distance envelope over pending updates.

**Core hypothesis**: Under natural streaming updates, a significant fraction (>50%) of queries can be certified as "still correct" without any graph repair, because the kth-distance margin exceeds the minimum distance to any pending update. Distribution drift causes certificate coverage to drop automatically, providing a natural merge trigger.

**Why this is strong**:
- Novel concept with no direct prior work (verified: FreshDiskANN guarantees system freshness, not per-query correctness)
- Clean theoretical formulation with practical system implications
- Answers both ways: if certificates work → skip expensive repairs; if they don't → proves streaming ANN needs eager updates
- Leverages M0-M3 data for ground-truth validation
- Targets NeurIPS/ICML (AI theory venue)

**Key differentiation**: FreshDiskANN = system-level freshness via delta buffer; Quake = parameter adaptation; IVF-TQ = temporal quantization. None provide per-query provable freshness/recall.

**Risk**: MEDIUM — certificate computation overhead may negate repair savings; adversarial streams may break coverage.

**Effort**: 2-3 months

---

### Rank 2: GraphKV — Disk-Resident ANN for KV Cache Retrieval in Ultra-Long-Context LLM

**Gap**: G3 (KV cache vector index on SSD)
**Venue**: VLDB 2027 / OSDI 2027
**Contribution**: System design

**Summary**: Build a disk-resident graph ANN index over KV cache entries using attention-aware distance. Unlike Tutti (GPU page swap) and KVSwap (simple eviction), use graph-ANN search to selectively retrieve the ~1% most attention-relevant tokens from SSD per decoding step.

**Core hypothesis**: ANN-based selective KV retrieval from SSD achieves equivalent generation quality (perplexity within 1%) at 5-10× lower I/O than page-granularity swap, because sparse attention means <1% of tokens dominate attention weight.

**Why this is strong**:
- Massive industry interest (Nvidia ICMSP/CMX, RetroInfer VLDB 2026)
- Clear gap: RetroInfer = DRAM only; Tutti = page swap without ANN intelligence; nobody combines disk-ANN + KV cache
- Our DiskANN expertise (async I/O, PQ reranking, page layout) directly applies
- Enables 2M+ context on commodity hardware
- Complemented by Codex's AttentionLoop-SSD diagnostic (Rank 10)

**Key differentiation**: RetroInfer (VLDB 2026) = DRAM wave index. Tutti (2026) = GPU io_uring page swap. KVSwap = simple eviction. GraphKV = first disk-resident ANN for selective KV retrieval.

**Risk**: MEDIUM — per-step SSD ANN query latency (~5ms) may bottleneck token generation. Need async prefetch.

**Effort**: 3-4 months

---

### Rank 3: ZoneEpoch-ANN — ZNS-Native Graph ANN with Navigability-Constrained Zone Reclamation

**Gap**: G1 (ZNS SSD + ANN)
**Venue**: FAST 2027
**Contribution**: System design

**Summary**: Separate the stable navigation core from append-style adjacency versions, using navigability certificates to decide zone resets instead of naively converting random updates to appends.

**Core hypothesis**: Navigability-constrained zone reclamation reduces GC write amplification vs naive append-log by 3-5×, while ZNS's higher sustained bandwidth (no FTL GC) gives ≥1.5× write throughput vs DiskANN on conventional SSD.

**Why this is strong**:
- Absolute zero prior work in ZNS + ANN (confirmed by multiple searches)
- Our M0-M3 write attribution directly informs zone reclamation design
- B+-tree on ZNS (ACM TACO 2026) validates that ZNS index co-design is publishable
- Paired with diagnostic (Rank 4) for risk mitigation

**Key differentiation**: ZNS B+-tree (TACO 2026) = tree index; LSM-VEC = log-structured vector index on conventional SSD. No graph ANN on ZNS exists.

**Risk**: HIGH — ZNS zone management + graph navigability is uncharted territory.

**Effort**: 3-4 months

---

### Rank 4: ANN-on-ZNS Feasibility Frontier — GC Phase Transition from M3 Page Versions

**Gap**: G1 (ZNS diagnostic)
**Venue**: EuroSys 2027 / FAST 2027 short paper
**Contribution**: Diagnostic / empirical finding

**Summary**: Using M3's 22.5M page version lifecycle data, compute the optimal and worst-case GC boundaries for graph ANN page versions under different zone sizes and over-provisioning ratios, to determine if ZNS-ANN is fundamentally tractable.

**Core hypothesis**: Broad, completion-after-rewrite page versions from M3 will create a GC phase transition: below a critical update-rate × zone-reset-period threshold, GC is manageable; above it, write amplification explodes. If even the offline optimal layout has high amplification, ZNS-ANN requires changing index semantics.

**Why this is strong**:
- LOW risk, quick execution (4-6 weeks)
- Unique dataset (M3 page versions — no one else has this)
- Answers "should we even try ZNS-ANN?" before investing 3-4 months in ZoneEpoch-ANN
- Publishable either way: YES = proceed with confidence; NO = fundamental impossibility result

**Key differentiation**: No prior work characterizes graph ANN page lifetimes for append-only storage.

**Risk**: LOW

**Effort**: 4-6 weeks

---

### Rank 5: Ambiguity-Monotone Graph — Quantization-Uncertainty-Shrinking Disk Topology

**Gap**: G4 (Quantization-topology co-design for disk)
**Venue**: SIGMOD 2027
**Contribution**: New method

**Summary**: Construct graph edges such that quantized distance intervals shrink monotonically along search paths, triggering SSD full-precision reads only when the quantized interval overlaps the current top-k boundary.

**Core hypothesis**: Uncertainty-monotone topology reduces exact-vector SSD reads by ≥30% vs standard DiskANN+PQ on at least 2 of {SIFT, DEEP, GIST}, because it avoids "false shortcut" hops where quantized distance looks good but exact distance doesn't help.

**Why this is strong**:
- Extends both δ-EMG's monotonicity concept and QuIVer's quantization-topology coupling
- Directly addresses the disk-specific problem: "when to read SSD" rather than "which edge to follow"
- Clean experimental setup (modify DiskANN's pruning, no new infrastructure needed)
- Not equivalent to page-cost-aware navigability (KILLED) because it optimizes quantization decision, not page layout

**Key differentiation**: SymphonyQG (SIGMOD 2025) = in-memory, accelerates distance with RaBitQ. QuIVer = in-memory BQ topology. δ-EMG = monotonic geometric constraints without quantization awareness. This idea: disk-resident, quantization-uncertainty-driven construction targeting SSD read reduction.

**Risk**: MEDIUM — need to verify that uncertainty monotonicity doesn't destroy navigability.

**Effort**: 8-12 weeks

---

## Secondary Ideas (Rank 6-10)

### Rank 6: Block-Probe Navigability (G2, SODA)
First I/O complexity lower bounds for navigable graph ANN. Use SAT/ILP on small instances to find counterexamples, then formalize proofs. HIGH risk, HIGH reward.

### Rank 7: Summary-Bit/Probe Lower Bound (G2+G4, ICML)
Information-theoretic lower bound on SSD reads given b-bit memory summaries. Proves which quantization quality is "enough" to avoid SSD. HIGH risk.

### Rank 8: PageTxn-ANN (G5, FAST)
Multi-page transactional crash recovery for disk graph ANN using redo logging. Kill-point fault injection on DGAI/OdinANN. LOW-MEDIUM risk.

### Rank 9: Selectivity Is Not Enough (G7, VLDB)
Proves that identical selectivity distributions can produce opposite optimal query plans when label-space fragmentation and churn differ. MEDIUM risk.

### Rank 10: AttentionLoop-SSD (G3, ICLR)
Diagnostic: do SSD KV retrieval errors compound through autoregressive generation? Closed-loop vs fixed-trace comparison. HIGH risk but novel diagnostic.

---

## Eliminated During Merge

| Idea | Reason |
|------|--------|
| Claude I8 (Write-Deferred) | Too close to KILLED "amortized maintenance" / FreshDiskANN delta |
| Claude I10 (I/O Attribution) | Valuable but insufficient novelty as standalone paper |
| Codex #6 (Deadline-Wave) | Subsumed by GraphKV; too speculative without GraphKV baseline |
| Codex #10 (Maintenance-Bandwidth LB) | Overlaps with FreshCert; harder with lower practical payoff |
| Claude I6 (CrashANN) | Merged into Codex PageTxn-ANN (better formulated) |

---

## Recommended Execution Order

1. **Start immediately**: I4 (ANN-on-ZNS Feasibility, 4-6 weeks) — answers whether G1 is tractable
2. **Parallel with I4**: I5 (FreshCert, 2-3 months) — clean theory + experiment, NeurIPS target
3. **If I4 positive**: I3 (ZoneEpoch-ANN, 3-4 months) — full ZNS system
4. **If I4 negative**: I7 (GraphKV, 3-4 months) — pivot to hot LLM serving direction
5. **Background theory**: I6 (Block-Probe Navigability) — long-term theory project
