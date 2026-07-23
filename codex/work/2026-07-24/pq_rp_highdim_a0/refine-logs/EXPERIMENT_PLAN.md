# PQ-RP-HIGHDIM-A0 Frozen Experiment Plan

**Problem**: Characterize whether uniform PQ code precision remains the dominant Recall–Performance lever at 768D–960D, and whether its benefit is large enough to motivate a later memory-normalized mixed-precision candidate.
**Method Thesis**: None; this is a characterization A0 and must not introduce selective exact, mixed precision, residual refinement, OPQ/RPQ/LVQ/RaBitQ, or a new search policy.
**Date**: 2026-07-24
**State**: `PLAN-ONLY / DO-NOT-RUN-WITHOUT-GPT-APPROVAL`

## Claim Map

| Claim | Why it matters | Minimum convincing evidence | Linked blocks |
|---|---|---|---|
| C1: fixed-byte PQ32 no longer necessarily saturates at high dimension | SIFT128 PQ32 has 2 bit/dim, but PQ32 has only 0.333 bit/dim at 768D and 0.267 bit/dim at 960D | One stable high-dimensional dataset; same full-precision graph; same-L PQ32-to-Exact gap and full RP curves | B1–B3 |
| C2: PQ64 may buy enough lower-L search efficiency to justify its DRAM increment | A later mixed-precision question exists only if uniform higher precision is effective but materially expensive | At a preregistered common-recall target, PQ64 reduces reads by ≥30% and also delivers either ≥1.5× QPS or ≥30% lower p99; the 1B-scale increment is explicitly 32 GB | B3–B4 |
| Anti-claim: an apparent gain is only graph, metric, GT, training-sample, loading, or L-selection drift | Without these controls the 3-D story is not identifiable | Byte-identical graph; one shared deterministic PQ training sample; metric-equivalence audit; coarse L frozen before full; two performance repeats that must agree | B0–B3 |

This A0 cannot support a mixed-precision algorithm claim. It can only return `GO-NOVELTY-KILL-MAP`, `HOLD-DATASET-SPECIFIC`, or `KILL-MIXED-PRECISION-MOTIVATION`.

## Dataset Gate

### Primary: Cohere-1M Wikipedia 768D

- Source: [`YoKONCy/Cohere-1M-wikipedia-768d`](https://huggingface.co/datasets/YoKONCy/Cohere-1M-wikipedia-768d), a reproducible mirror of 1M pre-generated English Wikipedia embeddings.
- Expected files: 1,000,000×768 float32 normalized base vectors; 1,000×768 float32 queries; 1,000×1,000 int32 cosine ground truth.
- Metric: cosine ranking, implemented as squared L2 only after verifying unit normalization, since `||q-x||²=2-2<q,x>` for unit vectors.
- Motivation: a modern semantic embedding workload with pre-generated vectors and GT; no GPU inference or training.
- Limitation: it is a recent mirror associated with one 2026 benchmark paper, not yet a broadly established benchmark. All hashes, provenance, license, and independent GT audits must be frozen locally.

### Mandatory M0 preflight

1. Pin repository revision and SHA256 for every downloaded file; record license and byte size.
2. Verify exact shapes, float32/int32 types, finiteness, ID range, uniqueness, and monotonic GT distances.
3. Verify base/query norms: max `|norm-1| ≤ 1e-4`; otherwise do not silently normalize or change metric.
4. For fixed query IDs `{0,17,101,257,509,997}`, recompute exact top-100 with blocked CPU BLAS and require tie-safe top-100 set agreement with supplied GT.
5. Verify cosine and squared-L2 top-100 sets are identical for the same audited queries.
6. Convert to DiskANN headers without changing row order; hash source and converted files.

Any shape/hash/license failure, non-unit metric ambiguity, or audited top-100 mismatch immediately triggers `FALLBACK-GIST`; it is not repaired post hoc.

### Fallback: GIST1M-960D dimension-stress control

- Official [ANN-Benchmarks GIST](https://github.com/erikbern/ann-benchmarks#data-sets): 1,000,000 train, 1,000 test, top-100 GT, Euclidean.
- Already local and audited:
  - HDF5: 3,844,648,288 bytes, SHA256 recorded in `dataset_manifest.env`;
  - full DiskANN binary: 3,840,000,008 bytes;
  - query: 3,840,008 bytes; GT: 400,008 bytes;
  - independent GT validation manifests already exist.
- GIST is a dimension-stress control, not a modern semantic workload. A positive result on GIST alone can produce at most `HOLD-DATASET-SPECIFIC`, never `GO-MIXED-PRECISION`.

Only one dataset proceeds to the full matrix: Cohere if M0 passes, otherwise GIST. Running both requires a new approval.

## Representation and Memory Normalization

Core representations are exactly `PQ16`, `PQ32`, `PQ64`, and `EXACT-NAV`.

| Dataset | Representation | code bits/dim | raw-float compression | resident at 1M | at 100M | at 1B |
|---|---|---:|---:|---:|---:|---:|
| Cohere-768 | PQ16 | 0.1667 | 192× | 16 MB | 1.6 GB | 16 GB |
| Cohere-768 | PQ32 | 0.3333 | 96× | 32 MB | 3.2 GB | 32 GB |
| Cohere-768 | PQ64 | 0.6667 | 48× | 64 MB | 6.4 GB | 64 GB |
| Cohere-768 | Exact | 32 | 1× | 3.072 GB | 307.2 GB | 3.072 TB |
| GIST-960 | PQ16 | 0.1333 | 240× | 16 MB | 1.6 GB | 16 GB |
| GIST-960 | PQ32 | 0.2667 | 120× | 32 MB | 3.2 GB | 32 GB |
| GIST-960 | PQ64 | 0.5333 | 60× | 64 MB | 6.4 GB | 64 GB |
| GIST-960 | Exact | 32 | 1× | 3.840 GB | 384.0 GB | 3.840 TB |

Both fixed code bytes and bits/dimension/compression ratio must appear in every table. This matrix does **not** match SIFT128 at fixed bits/dim: SIFT PQ16/PQ32 correspond to 1/2 bit/dim. Therefore cross-dataset statements must not attribute differences to dimension alone.

## Frozen Search Controls

- Build one full-precision Vamana/DiskANN graph per selected dataset: `R=64`, build `L=100`, one fixed entry point and default pruning alpha recorded in the manifest.
- All four representations symlink the same graph/SSD index; verify realpath, size, and SHA256.
- Train ordinary PQ with 256 centroids/subspace. PQ16/32/64 must reuse the **same deterministic 10% training row IDs** and record the row-ID hash. If the current generator cannot accept shared samples, add only a deterministic data-preparation hook before execution; do not train three independent samples.
- `K=10`, `W=4`, one search thread, zero node cache, identical synchronous I/O, entry point, final rerank, query order, warm-up source, and warm-up count.
- Coarse scan: `L={50,100,200,400,800}`.
- No midpoint is allowed before full results. At most one midpoint may be proposed later, and only if the 95%–99.5% common-recall crossing is demonstrably bracketed by two coarse points.
- `EXACT-NAV` uses the full float matrix in DRAM and the PQ16 prefix for shared DiskANN plumbing; report both the auxiliary 16 MB code and full-vector resident bytes.

## Storage Placement

- `DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724` is on the dedicated `/dev/nvme8n1` ext4 mount. All downloads, converted vectors, full graph/index files, PQ artifacts, uncompressed per-query outputs, and temporary build files must live below this root.
- Set `TMPDIR=$DATA_ROOT/tmp`; do not let conversion, sorting, graph building, or PQ training spill to `/tmp`, the repository, or `/home/ubuntu/pz`, which are on the system logical volume.
- `WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0` remains on the system disk, but may contain only small scripts, plans, manifests, logs, compressed CSV/JSON summaries, and figures.
- Execution preflight must verify `findmnt -T "$DATA_ROOT"` resolves to `/dev/nvme8n1` and that at least 30 GB is free. A failed mount check is a hard stop.

## Paper Storyline

- Main A0 must establish the 3-D `Recall × Performance × DRAM` frontier and the matched-recall PQ32↔PQ64 comparison.
- Appendix/supporting evidence may contain query-level residual distributions and the GIST fallback audit.
- Intentionally cut: mixed per-vector precision, selective exact, residual refinement, code allocation, OPQ/RPQ/LVQ/RaBitQ, learned policies, additional L/W grids, multiple graph degrees, and multiple datasets without approval.

## Experiment Blocks

### B0: Data and Metric Preflight

- Claim tested: the selected high-dimensional workload and GT are stable.
- Compared systems: supplied GT vs blocked exact CPU computation; cosine vs L2 ranking for normalized Cohere.
- Metrics: top-100 overlap, tie-safe agreement, norms, hashes, row counts.
- Success criterion: all M0 checks pass; otherwise deterministic fallback to GIST.
- Failure interpretation: data path is unsuitable; no ANN conclusion.
- Priority: MUST-RUN after approval.

### B1: Shared Graph and PQ Artifact Audit

- Claim tested: representation is the only changing navigation factor.
- Setup: one full graph, one shared deterministic PQ sample, PQ16/32/64, Exact full matrix.
- Metrics: SHA256/realpaths, graph parameters, PQ quantization residual median/P90/P99, resident bytes, peak build RSS/time.
- Success criterion: byte-identical graph and common sample IDs; all artifacts finite and correctly sized.
- Failure interpretation: stop before search.
- Priority: MUST-RUN.

### B2: Canary

- Queries: first 200 official queries; official query IDs 900–999 are the fixed 100-query warm-up and are disjoint from Canary measurements.
- Systems: PQ32, PQ64, Exact; `L={100,200,400,800}`; two performance repeats.
- Metrics: Recall@10, QPS, p50/p95/p99, CPU/I/O time, comparisons, hops, 4-KiB reads, touched bytes, peak RSS, returned IDs.
- Gate:
  1. 800 rows/process and complete counters;
  2. deterministic returned IDs across repeats;
  3. Recall non-decreasing up to tie tolerance 0.01pp;
  4. Exact `L=800` Recall@10 ≥99.5%; otherwise investigate graph/GT and do not run full;
  5. repeat p50 drift ≤25% for every system/L; if it fails, stop as `PERFORMANCE-UNSTABLE` and do not automatically add a third run;
  6. PQ64 must not be worse than PQ32 by >0.1pp at every L; otherwise audit training artifacts.
- Failure interpretation: `STOP-CANARY`; no full matrix.
- Priority: MUST-RUN.

### B3: Full Recall–Performance–Memory Matrix

- Queries: all official queries (1,000 for either frozen dataset).
- Systems: PQ16/PQ32/PQ64/Exact × five L values = 20 base points.
- Execution: all L values in one loaded process per representation; Recall is taken once from repeat 1, and performance is measured in exactly two warm-up-controlled repetitions. Both raw repeats are reported; no selective rerun or automatic third repeat is allowed.
- Primary metrics: Recall@10, QPS, p50/p95/p99.
- Secondary metrics: CPU_us, IO_us, comparisons, hops, 4-KiB reads, NVMe bytes, navigation DRAM bytes, combined touched bytes, peak RSS, PQ resident bytes; query scratch only if allocation-derived.
- Figures: Recall–QPS/p50/p95/p99/comparisons/reads/bytes, plus a memory-frontier plot at matched recall.
- Priority: MUST-RUN.

### B4: Preregistered Decision Analysis

Define the common-recall target `R*` before examining performance:

1. Let `R*` be the highest 0.5pp grid point in `[95%,99.5%]` reachable by both PQ32 and PQ64 without extrapolation.
2. Linearly interpolate only between adjacent measured L points for reporting; the decision is confirmed using the nearest measured point on the conservative side.

Decisions:

- `SATURATED-PQ32-HIGHDIM` if its same-L gap to Exact is ≤0.25pp at all points where Exact Recall lies in `[95%,99.5%]`, and PQ64 improves neither QPS by ≥1.5× nor p99/reads by ≥30% at `R*`.
- `GO-MIXED-PRECISION-NOVELTY-KILL-MAP` only if Cohere M0 passes and PQ64 vs matched-recall PQ32 reduces reads by ≥30% **and** also achieves either ≥1.5× QPS or ≥30% lower p99, while PQ64 costs the explicit extra 32B/vector (32 GB at 1B).
- `KILL-MIXED-PRECISION-MOTIVATION` if PQ64 yields <10% improvement in QPS, p99, and reads at `R*`, or larger-L PQ32 matches it within those bounds.
- `HOLD-DATASET-SPECIFIC` for any positive result obtained only on GIST, or for improvements between the KILL and GO thresholds.

No mixed-precision implementation follows automatically. A GO only authorizes a separate prior/novelty Kill Map and held-out Oracle gate.

Every GO threshold must hold independently in both performance repeats. Central tables may report the two-run median and full range, but a mean/median may not rescue a failed repeat.

## Run Order and Milestones

| Milestone | Goal | Runs | Decision gate | Cost after approval | Risk |
|---|---|---|---|---:|---|
| M0 | freeze dataset/GT | six exact audits | Cohere pass or GIST fallback | 0.5–1 h | source/GT instability |
| M1 | graph and PQ artifacts | one graph + three PQ codes | byte-identical graph, shared sample | 1.5–3 h | PQ training dominates |
| M2 | Canary | 3 systems × 4 L × 2 repeats | all six Canary gates | 0.25–0.6 h | graph oracle too weak |
| M3 | Full matrix | 4 systems × 5 L × 2 repeats | 40 complete performance observations | 1–2.75 h | high-L exact CPU/I/O |
| M4 | analysis/report | deterministic aggregation | B4 decision only | 0.5–1 h | interpolation overclaim |

Hard wall: **8 wall-clock hours after data are locally frozen**. Stop rather than reduce query count, remove Exact, change L after seeing results, add a third repeat, or run mixed precision.

## Compute and Data Budget

- GPU-hours: **0**.
- CPU: up to 24 build threads; one search thread for measurement; machine has 112 logical CPUs.
- RAM: cap graph/PQ preparation at 64 GiB; Exact needs about 3.1 GiB (Cohere) or 3.84 GiB (GIST) plus index/search overhead; machine has 251 GiB.
- Dedicated data NVMe (`/dev/nvme8n1`, mounted at `/home/ubuntu/pz/VectorDB/data`):
  - Cohere: ~3.08 GB source, ~3.08 GB converted base, ~4.1 GB expected disk index, <0.2 GB PQ/GT/results, 5–8 GB temporary; reserve **20 GB**.
  - GIST fallback: source and converted data already local; fresh full-1M index expected 8.2 GB because a 960D node spans two 4-KiB sectors, plus PQ/results/temp; reserve **20–25 GB incremental**.
  - The data mount currently has ~727 GB free. The system volume has ~139 GB free but is explicitly excluded from bulk artifacts.
- Time:
  - Cohere path: expected **3.5–7.5 h**, hard wall 8 h after freeze; download time reported separately.
  - GIST fallback: expected **2.5–5.5 h**. Prior local 800K GIST build took ~3,059 s end-to-end, including ~2,854 s quantized-data generation, providing the calibration.
- Raw artifacts: base vectors, indexes, temporary files, and uncompressed results stay on the data NVMe and outside Git; manifests, compressed per-query CSVs, summaries, logs, commands, and figures enter the dated work directory.

## Risks and Mitigations

- Recent Cohere mirror is not established: pin hashes/revision/license and independently audit GT; otherwise use GIST with a weaker verdict.
- Cosine/L2 mismatch: require unit norms and exact ranking equivalence before conversion.
- Independent PQ samples confound code bytes: mandate one deterministic shared sample-ID list.
- Graph ceiling hides PQ effects: Canary Exact `L=800 ≥99.5%` or stop.
- Fixed bytes are not fixed bits/dim: report both; do not make dimension-only causal claims.
- 1K queries give weaker tail estimates than SIFT 10K: retain raw per-query data, report repeat ranges, and avoid subpopulation claims.
- Existing GIST index is 900K/800K-derived and does not match the full 1M GT: build or locate a verified full-1M graph; never silently reuse it.
- System-disk spill: pin `DATA_ROOT` and `TMPDIR`, record `findmnt`/`df` output, and stop if the resolved device is not `/dev/nvme8n1`.

## Final Checklist

- [x] Primary and fallback datasets are explicit
- [x] Fixed-byte and bits/dim views are both frozen
- [x] Stronger-code and larger-L baselines receive equal tuning
- [x] Canary, hard wall, resource budget, and stop gates are explicit
- [x] No mixed-precision algorithm is implemented or implied
- [ ] Gpt approves plan
- [ ] Dataset M0 begins
