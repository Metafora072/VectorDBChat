# Phase 3: Deep Novelty Check Results

**Date**: 2026-07-18
**Method**: Multi-source web search (10+ queries) + Codex GPT-5.4 cross-verification + devil's advocate
**Corrections**: 2 critical landscape corrections discovered

---

## Critical Landscape Corrections

### Correction 1: I/O Lower Bounds for ANN Already Exist
**Goswami, Jacob, Pagh (PODS 2020)** proved Ω(k) block-read lower bounds for kNN:
- High-dimensional Hamming space, polynomial space indexing
- For ℓ∞: holds for c-approximate with c ∈ (1,3)
- Optimal ⌈k/B⌉ upper bound for 3-approximate

**Impact**: G2 ("no I/O lower bounds for ANN") was incorrect. Block-Probe Navigability idea is **REDUCED** — remaining novelty is only navigable-graph-specific bounds in Euclidean metric.

### Correction 2: KV Cache Retrieval Space Is Extremely Crowded
Since our Phase 1 survey, discovered:
- **RetrievalAttention (NeurIPS 2025)**: ANNS indexes in CPU memory for KV, attention-aware
- **KVDrive (2026)**: Multi-tier GPU+DRAM+**SSD** with hierarchical centroid index — already retrieves from SSD!
- **ParisKV (ICML 2026)**: Drift-robust retrieval, collision-based, supports CPU-offloaded KV
- **CTkvr (2025)**: Centroid-then-token two-stage retrieval
- **CentroidKV (2026)**: KV cache clustering

**Impact**: GraphKV is **KILLED** — KVDrive already implements selective KV retrieval from SSD with indexing. GraphKV would be "replace KVDrive's centroid index with graph index" — insufficient novelty.

---

## Revised Novelty Verdicts

| # | Idea | Pre-Check | Post-Check | Codex Verdict | Key Evidence |
|---|------|-----------|------------|---------------|--------------|
| 1 | ZoneEpoch-ANN | PASS | **CONFIRMED** | CONFIRMED | Zero ZNS+ANN prior work; navigability cert for zone reclamation is novel |
| 2 | ANN-on-ZNS Feasibility | PASS | **CONFIRMED** | (not reviewed) | Zero prior work; unique M3 dataset |
| 3 | FreshCert | PASS | **REDUCED** | REDUCED | INSQ safe-region paradigm exists; but nobody applies to stale graph + delta |
| 4 | Ambiguity-Monotone | CONDITIONAL | **REDUCED** | REDUCED | SymphonyQG + δ-EMG + SkipDisk overlap; need formal proof of new criterion |
| 5 | GraphKV | PASS | **KILLED** | KILLED | KVDrive (2026) already does SSD KV retrieval with index |
| 6 | Block-Probe Navigability | PASS | **REDUCED** | REDUCED | PODS 2020 has I/O kNN lower bounds; only graph-specific bounds remain |
| 7 | PageTxn-ANN | PASS | **CONFIRMED** | (not reviewed) | Zero crash-consistent disk-resident ANN |
| 8 | Selectivity Is Not Enough | PASS | **CONFIRMED** | (not reviewed) | Novel diagnostic beyond selectivity |
| 9 | AttentionLoop-SSD | PASS | **VIABLE** | (not reviewed) | Novel diagnostic; depends on existing SSD KV systems |
| 10 | Summary-Bit/Probe LB | PASS | **REDUCED** | (not reviewed) | PODS 2020 Ω(k) bounds weaken "first lower bound" claim |

---

## Final Ranking After Phase 3

### Tier A — CONFIRMED NOVEL (recommend Phase 4 review)

**A1: ZoneEpoch-ANN (G1, FAST)**
- Novelty: **10/10** — zero prior ZNS + ANN work
- Strongest objection: DiskANN is read-heavy; ZNS benefits are write-focused. May be seen as engineering.
- Counter: Navigability certificates for zone reclamation are a genuine algorithmic contribution. M0-M3 write data shows 96 repairs/insert × 4KB page writes — writes ARE significant for dynamic ANN.
- Differentiation: B+-tree on ZNS (TACO 2026) = tree index only; LSM-VEC = conventional SSD; ZoneEpoch-ANN = first graph ANN on ZNS with navigability-aware reclamation.

**A2: ANN-on-ZNS Feasibility Frontier (G1 diagnostic, EuroSys)**
- Novelty: **9/10** — no prior page-lifetime analysis for graph ANN on append-only storage
- Risk: LOW — 4-6 weeks, purely empirical, publishable either way
- Should run BEFORE ZoneEpoch-ANN to determine tractability

**A3: PageTxn-ANN (G5, FAST)**
- Novelty: **8/10** — P-HNSW is pmem/in-memory only; zero disk-resident crash-consistent ANN
- Strongest objection: WAL is standard technique; novelty may be "applying known technique to new domain"
- Counter: Graph ANN's multi-page update pattern (vector + own adj + N neighbor adj lists) creates a unique atomicity challenge not present in B-trees or LSM.
- Differentiation: P-HNSW = persistent memory (byte-addressable, HNSW); PageTxn-ANN = SSD (page-granularity, Vamana, async I/O + publish epoch).

### Tier B — REDUCED BUT VIABLE (conditional on repositioning)

**B1: FreshCert (G6, NeurIPS)**
- Novelty: **6/10** — safe-region paradigm exists (INSQ etc.); but nobody applies to streaming ANN with stale graph + quantized delta envelope
- Repositioning needed: Frame as "extending safe-region to streaming ANN" rather than "first per-query freshness certificate"
- Strongest objection: kth-distance margin only excludes delta points; doesn't prove base graph didn't miss closer old points
- Counter: For α-navigable graphs, the base graph's recall guarantee (from construction) can be formally composed with the delta exclusion certificate
- Risk: MEDIUM — needs careful formal treatment; could be NeurIPS if done right

**B2: Selectivity Is Not Enough (G7, VLDB)**
- Novelty: **7/10** — nobody has shown that matched-selectivity workloads can produce opposite optimal plans due to label fragmentation + churn
- Strongest objection: May be seen as "just another benchmark/diagnostic paper"
- Counter: Provides a constructive result — an example where selectivity-only planners provably fail — with implications for GateANN, SIEVE, Curator design
- Risk: MEDIUM — clean execution, good venue fit (VLDB experiment track)

**B3: Ambiguity-Monotone Graph (G4, SIGMOD)**
- Novelty: **5/10** — SymphonyQG, δ-EMG, SkipDisk overlap; the specific "uncertainty interval monotonicity" criterion is new but needs formal proof of achievability + strict I/O improvement
- Risk: MEDIUM-HIGH — may be seen as combining existing pieces

### Tier C — KILLED or DEFERRED

**C1: GraphKV (G3)** — KILLED. KVDrive already does SSD KV retrieval with index.
**C2: Block-Probe Navigability (G2)** — DEFERRED. PODS 2020 has I/O kNN lower bounds; remaining novelty is narrow (navigable-graph-specific). Very high risk.
**C3: Summary-Bit/Probe LB (G2+G4)** — DEFERRED. Same issue as C2; also, PODS 2020 Ω(k) bound already covers this space.
**C4: AttentionLoop-SSD (G3)** — DEFERRED. Novel diagnostic but depends on having a working SSD KV system; could be a follow-up to other groups' KVDrive/RetroInfer work.

---

## Recommended Phase 4 Ideas

Send to `/research-review` for external critical review:
1. **ZoneEpoch-ANN** (Tier A1) — strongest novelty, highest risk
2. **ANN-on-ZNS Feasibility** (Tier A2) — de-risks A1, standalone publishable
3. **PageTxn-ANN** (Tier A3) — confirmed gap, clean systems contribution
4. **FreshCert** (Tier B1) — needs repositioning but novel angle
5. **Selectivity Is Not Enough** (Tier B2) — clean diagnostic, good venue fit
