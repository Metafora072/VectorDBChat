# Research Proposal: Residual-Certified PageMaxSim

## Problem Anchor

- **Bottom-line problem**: 在强 token merging 与量化之后，visual late-interaction candidate object 仍跨多个 4 KiB pages；需要只读取部分 token pages，就求出外层 Col-Bandit 所需的 MaxSim cells，并产生表示压缩 baseline 达不到的 page/storage/CPU/fidelity Pareto。
- **Must-solve bottleneck**: P1 证明 page oracle 存在，但 P2 的 single centroid-radius 把每页 token set 包成一个大球，upper bound 在真实 128D ColQwen2 embedding 上过松，导致读取 99.92%–100% pages。
- **Non-goals**: 不发明新的 outer bandit；不直接实现 async SSD engine；不把 heuristic page order 冒充 exact；不以只在 raw unmerged representation 上成立的收益复活系统；不把 PageMaxSim 改名为通用 DiskColBERT。
- **Constraints**: 4 KiB direct-I/O alignment；真实 ViDoRe/ColQwen2 candidate sets；必须计入 codebook、per-page metadata、padding、bound CPU；优先复用当前 CPU pilot；P3 仍未获批准。
- **Success condition**: 在 held-out queries 上，新的 feasible bound 对 raw int8 和 Light-style f9 int8 都能严格恢复请求 cells，并形成 full scan、single-ball、strong representation 与 single-vector baseline 均无法达到的新 Pareto；否则继续 Kill。

## Technical Gap

当前 page synopsis 只保存 page mean `c_g` 和最远 token radius `r_g`。真实 page token set 往往是非球形、甚至多模态集合；一个 outlier 就会放大整页 radius。P2 中 page oracle 仅需 raw int8 的 21% 和 f9 int8 的 83%，而 single-ball policy 分别读取 100%/100%，说明 gap 位于集合外包络，不在 page order。

增加 scheduler、readahead 或 async I/O 不能修复错误的 upper bound。逐 token 保留 PQ/sketch 虽可收紧，但会把全量 compressed control plane 搬回 DRAM，破坏 storage problem。最小缺失机制应当是：用全 corpus 共享的少量 prototypes，将一个 page 表示为多个小 residual balls 的并集，而不是每页存多个 128D centroids。

## Method Thesis

- **One-sentence thesis**: 使用共享 global token codebook 与 per-page `(codeword ID, max residual norm)` 列表，把 page token set 安全地表示为多个小球的并集，从而以小 metadata 构造显著紧于 single centroid-radius 的 MaxSim page upper bound。
- **Why smallest adequate**: 只替换 P2 失败的 synopsis；outer Col-Bandit、candidate set、page cache、4 KiB object format 和 active-token batch interface 全部保持不变。
- **Why timely**: visual late-interaction 的 token vocabulary/centroid machinery 已被 PLAID/WARP 类系统验证可复用，但现有工作没有把它审计为 physical-page exact maximum 的安全 admission control。

## Contribution Focus

- **Dominant contribution**: residual-certified multi-ball page synopsis 与其 tightness/metadata trade-off。
- **Supporting contribution**: 一个读取 page 时同时收紧多个 active query-token cells 的简单 bound-gap scheduler；只有 synopsis 先通过时才保留。
- **Explicit non-contributions**: global k-means、Col-Bandit、PQ、async I/O、candidate pruning、token merging 均不声称 novelty。

## Proposed Method

### Complexity Budget

- **Frozen / reused**: official ColQwen2 embeddings、Light-style f9 representation、per-token int8、Col-Bandit `alpha=0.2`、真实 mean-vector top-32 candidates、现有 serializers。
- **New trainable components**: 0；global codebook 只做离线 k-means。
- **Intentionally excluded**: learned router、per-query neural predictor、hierarchical page tree、multiple parallel synopsis families、P3 engine。

### System Overview

```text
offline document tokens
  -> shared global codebook assignment
  -> group nearby codewords into physical pages
  -> per page store {(codeword id, max residual norm)}

query tokens
  -> compute q dot all global codewords once
  -> lookup each page's codeword/radius pairs
  -> U(q,g) = max_k_in_g [q dot mu_k + R(g,k)]
  -> read highest-value page for active query-token batch
  -> exact token scan updates lower bounds
  -> stop a cell when lower >= all unread upper bounds
```

### Core Mechanism

For normalized document token `x` assigned to shared codeword `mu_k`, write `x = mu_k + e`. For every physical page `g` and codeword `k` present on that page, store:

```text
R(g,k) = max_{x in page g, assign(x)=k} ||x - mu_k||_2
```

For normalized query token `q`:

```text
q dot x <= q dot mu_k + ||x - mu_k||_2
          <= q dot mu_k + R(g,k)

U(q,g) = max over k present in g [q dot mu_k + R(g,k)]
```

This remains deterministic and safe. `q dot mu_k` is computed once per query token and shared by all documents/pages. Per-page metadata is only codeword IDs, fp16 radii, counts and offsets; the 128D codeword table is global rather than repeated per page.

Physical layout sorts tokens by codeword ID before page packing. This reduces the number of `(g,k)` pairs and aligns the safe geometry with storage pages. The first experiment sweeps codebook sizes `{64, 256, 1024}` and records the actual distinct codewords/page instead of assuming one.

### Supporting Scheduler

For each document, keep the active query tokens requested by outer Col-Bandit. Choose the unread page that is currently the maximum-upper-bound page for the largest number of unresolved cells; break ties by aggregate bound gap. This is the current P2 scheduler, reused unchanged so any improvement can be attributed to the synopsis.

### Failure Modes and Diagnostics

- **Residual balls remain loose**: measure `U(q,g) - true_page_max(q,g)` and the number of false-threatening pages after the true-max page is read.
- **Metadata explosion**: report actual `(g,k)` pairs, global codebook bytes, aligned synopsis bytes and bytes/corpus token.
- **Only raw benefits**: require a non-dominated f9-int8 point; otherwise Kill under the original gate.
- **CPU dominates**: report query-codebook GEMM, bound lookup and scheduler CPU separately.
- **Static codebook does not generalize**: train codebook/layout on one document split and evaluate held-out queries/documents without retuning.

### Novelty and Elegance Argument

The mathematical ingredients—global centroids and residual norms—are known. The only defensible paper claim would be that a shared-codebook union-of-balls is the minimal page-safe control plane needed to turn MaxSim computation pruning into physical I/O pruning. If it does not yield a measured strong Pareto, it remains an engineering recombination and is Killed before architecture work.

## Route Comparison

### Route A: Exact residual-certified multi-ball synopsis — selected

It attacks the observed cause, preserves exact inner cells, and shares prototypes corpus-wide. It can be tested entirely offline on the existing trace.

### Route B: Budgeted approximate page routing — held in reserve

Rank pages by query-to-page centroid or predicted contribution, stop at a fixed/adaptive byte budget, and report top-k overlap. This may create a useful quality/I/O curve, but without a calibrated risk statement it overlaps token/centroid pruning and weakens the contribution. Do not combine it with Route A in the first gate. Only reconsider if PZ explicitly prefers an approximate IR contribution after Route A fails.

## Claim-Driven Validation Sketch

### Claim 1: Multi-ball bounds close the P1 oracle gap

- **Minimal experiment**: replay identical 16-query/top-32 ColQwen2 candidates under raw int8 and f9 int8; compare single-ball, multi-ball `{64,256,1024}`, page oracle and full scan.
- **Metrics**: exact cell audit, pages, bound slack, false-threatening pages, metadata bytes, bound CPU.
- **Decisive evidence**: at least one multi-ball point is non-dominated jointly in page reads, total storage, CPU and exact fidelity on both representations.

### Claim 2: The gain comes from synopsis geometry, not scheduler complexity

- **Minimal experiment**: sequential vs unchanged active-batch greedy under the best synopsis; delete the scheduler if sequential is on the same Pareto frontier.
- **Metrics**: pages, cells tightened/read, CPU.

## Experiment Handoff Inputs

- **Must-prove**: strict bound correctness; actual metadata; f9-int8 survival; held-out stability.
- **Critical baselines**: single centroid-radius, full contiguous, P1 page oracle, Light-style f9 full scan, f49, single-vector.
- **Highest-risk assumptions**: shared codewords materially reduce residual radii; per-page codeword lists remain small; f9 retains enough page space.

## Compute & Timeline Estimate

- GPU-hours: 0.
- New data: 0; reuse 6.8 GiB data-disk pilot.
- Local CPU: estimated under one hour for codebook sweeps and full replay.
- Decision: one additional synopsis gate only; no P3 or architecture work without a positive Pareto.
