# DGAI Update-Induced Quality Attribution：G0 早停报告

**日期**：2026-07-13

**Gate**：`gpt/share/dgai_update_quality_attribution_gate_0713.md`

**裁决**：**G0 early stop，Exit DGAI**

**Result-to-claim**：`claim_supported=no`，`confidence=high`

## 1. 结论先行

上一轮 SIFT uniform same-vector refresh 的 Recall@10 从 0.9970 降至 0.9632，并不是可在 clean DGAI 上复现的稳定信号。最关键的严格直接复现匹配了旧运行的 seed=711、首批 refresh tags、qid 0--399、checkpoint、search 参数与 fresh strategy-23 索引：旧 dirty/instrumented 路径在 L=100 上由 0.99625 降至 0.96000；clean 路径却由 0.99625 变为 0.99700。L=200/400/800 同样持平或略升，逻辑 I/O 也没有恶化。独立 seed=17 得到相同阴性结论。

因此，本轮在 G0 触发 gate 的显式关闭条件：motivating observation 来自受未提交实现改动污染的旧执行路径，而不是可靠的 clean-implementation 现象。没有可信的质量退化可供 G1 primitive isolation、G2 topology/path attribution 或 G3 repair oracle 解释，继续运行这些阶段只会对一个不可复现的现象做事后归因。本轮不实现 repair，不形成 decoupling-specific repair-cost claim，正式退出 DGAI 主线。

## 2. Clean 环境与最小改动

- clean source：DGAI commit `a0179b876a4bd453336dc2893b46ae890f680555`；
- isolated worktree/build/raw root：`/home/ubuntu/pz/VectorDB/data/VectorDB/dgai_update_quality_attribution/`；
- 每个正式运行都从未更新的 `sift_strategy23_900k` 源索引复制 fresh index；
- 数据、索引、build 与 raw CSV 全部位于项目 NVMe；最终占用约 9.4 GiB；
- 系统盘 45%，项目 NVMe 15%。

clean commit 原样运行存在两项阻塞性 correctness/build 问题，因此只加入最小 guard：

1. PQ table 的 AVX-512 streaming load 假设地址对齐，first query 会 SIGSEGV；改用 unaligned-safe load。该改动不改变距离计算。
2. insert 的 PQ code 可能早于 topology/coordinate mapping 对查询可见，5% 后插入阶段可触发未映射节点访问和 SIGSEGV；search/rerank 在 mapping commit 前跳过该 pending point。旧正式 build 同样启用了这一 guard。

其余新增内容仅为 tag/vector/location 的只读 measurement helper 与 parseable G0 harness。可复核材料：

- `codex/share/dgai_update_quality_g0.cpp`；
- `codex/share/dgai_update_quality_measurement.cpp`；
- `codex/share/dgai_update_quality_clean_changes.md`。

## 3. G0 正确性审计

### 3.1 No-op、tag 与 ground truth

SIFT-900K no-op control 在 checkpoint 0/1 的 Recall@10 均保持 0.99（20-query sanity，L100/beam4）。全量 tag audit 得到 900,000 active internal nodes、900,000 unique tags、0 duplicate、0 missing。对前三个查询执行 900K 向量 exact scan 后，filtered official top-10 tag set 与 exact top-10 为 3/3 一致。

### 3.2 1% refresh 语义

seed=17 的 1% same-vector refresh 后：

- 900,000 active/unique tags，0 duplicate/missing；
- 采样 1,000 个 refreshed tags，old internal node 全部不可见，new internal/tag mapping 唯一；
- 从 decoupled coordinate store 读出的向量与原 base vector 的 max absolute error 全为 0；
- L100/200/400 Recall@10 由 0.996/0.998/1.000 保持为 0.996/0.998/1.000。

这排除了旧/新 internal ID 混用、tag 重复、same-vector 未正确写入和该子集 GT 口径错误。

### 3.3 独立持久化缺陷

重新打开 1% 更新后的文件集会在首次查询前崩溃。原因是进程内更新的 tag/location mapping 未被持久化为 reload 可重建的完整状态；loader 重新采用初始 identity mapping，与已修改文件不一致。这是 DGAI 的独立 correctness 缺陷，说明更新文件不能直接当作可靠持久快照；但它不影响本报告所有同一进程内、update completion 后立即执行的 checkpoint 查询，也不解释旧新两条同进程路径的反向结果。

## 4. 20% Search-Budget Sweep

操作比例沿用旧 harness 语义：checkpoint `p` 对应 refresh `900000*p/200` 个对象，因此 20% checkpoint 累计 refresh 90,000 个 tag。每个点使用 qid 0--399、k=10、beam=4、rerank=10，扫描 L=100/200/400/800。

### 4.1 seed=17

| checkpoint | L100 | L200 | L400 | L800 |
|---:|---:|---:|---:|---:|
| 0 | 0.99625 | 0.99825 | 0.99900 | 0.99900 |
| 1 | 0.99625 | 0.99825 | 0.99900 | 0.99900 |
| 5 | 0.99600 | 0.99825 | 0.99900 | 0.99900 |
| 10 | 0.99575 | 0.99875 | 0.99900 | 0.99900 |
| 20 | 0.99625 | 0.99850 | 0.99900 | 0.99900 |

L100 在中间点最大仅变化 -0.0005，并在 20% 回到初值；普通 L200 已完全覆盖该抖动。L100 mean logical I/O 从 62.6675 降至 61.5875，L800 从 371.8275 降至 369.4175。

### 4.2 seed=711：旧 positive case 严格直接复现

旧 trace 首批 refresh tags 为 `858547, 590351, 544834, 243196, 580277, 86554, 820409, 876942, 341223, 305245`。根据 harness 的 `std::mt19937_64 + std::shuffle` 精确反推出 seed=711；clean run 的首批 tags 与其逐项一致。

| checkpoint | L100 | L200 | L400 | L800 |
|---:|---:|---:|---:|---:|
| 0 | 0.99625 | 0.99825 | 0.99900 | 0.99900 |
| 1 | 0.99625 | 0.99825 | 0.99900 | 0.99900 |
| 5 | 0.99675 | 0.99825 | 0.99900 | 0.99900 |
| 10 | 0.99700 | 0.99850 | 0.99900 | 0.99900 |
| 20 | 0.99700 | 0.99850 | 0.99900 | 0.99900 |

checkpoint 20 的 tag audit 仍为 900,000 active/unique、0 duplicate/missing。mean logical I/O 的 0%→20% 变化为：L100 64.065→62.2225、L200 111.51→110.7275、L400 203.375→201.8275、L800 372.0425→369.53。

旧 dirty run 的全 1,000 queries 是 0.9970→0.9632；为排除 query subset 差异，重新聚合旧 trace 的同一 qid 0--399 后是 0.99625→0.96000。clean seed=711 在完全相同子集上是 0.99625→0.99700。因此差异既不是 seed，也不是 query subset，更不是用较大 L 隐藏；它来自旧 dirty/instrumented 与 clean 执行路径之间的实现差异。

## 5. 旧观测为何不能继续作为证据

旧运行所在主 worktree 与 clean commit 同基线，但包含约 930 行未提交改动，除 measurement 字段外还重写了 search/rerank 控制流，包括 frontier loop、selected-buffer handling、conditional PQ2/map fallback 等。旧初始索引 recall 正常，并不能证明这些改动在经历动态更新后仍语义等价。

当前证据足以判定“旧 trace 受非 clean implementation 污染”，但未做逐行 patch bisection，因此不会把伪下降武断归因于某一个具体修改。若未来只为历史取证，可在 clean worktree 上逐项启用旧 patch；该工作不改变当前 research gate 的裁决。

## 6. G1--G3 早停登记

- G1 insert-only/delete-only/replace-new/clustered：未运行。G0 的 motivating observation 已被严格 direct-match 反证。
- G2 graph snapshot、node/path/region attribution：未运行。没有 clean quality loss 可归因。
- G3 fresh rebuild、local-repair oracle、IP-DiskANN/TALS-style baselines：未实现。为不可复现现象开发 repair 会违反 gate。
- GIST 与第三 seed：未运行。它们只是在 positive observation 存活后验证普适性的门禁；本报告不声称“所有 refresh 永不退化”。

这一早停严格遵循 gate 第 12/13 节：若 G0 证明 observation 来自 harness、ground truth 或实现问题，应立即停止，不为了保留 DGAI 而强行推进 G1--G3。

## 7. Result-to-claim

独立 reviewer 的结构化裁决：

- `claim_supported=no`；
- 数据支持 clean SIFT 两个 seeds 到 20% 不发生 recall/逻辑 I/O 退化，并足以否定旧观测的可靠复现性；
- 数据不支持 universal no-degradation，也不支持 repair necessity 或 decoupled repair Pareto；
- GIST、第三 seed 只在改写为普遍性负结论时才是缺失证据；
- 当前路线应为 `G0 early stop -> Exit DGAI`；
- confidence `high`。

## 8. Raw evidence

所有以下路径均位于：

`/home/ubuntu/pz/VectorDB/data/VectorDB/dgai_update_quality_attribution/`

- no-op：`runs/sift_g0_noop_sanity/`；
- seed17 1% correctness：`runs/sift_g0_refresh1_seed17/`；
- persistence failure：`runs/sift_g0_refresh1_seed17_reload/`；
- seed17 20%：`runs/sift_g0_refresh20_seed17_fixed/`；
- seed711 direct match：`runs/sift_g0_refresh20_seed711_fixed/`；
- isolated source/build：`worktree/DGAI/`、`build/DGAI/`。

旧 positive raw trace：

`/home/ubuntu/pz/VectorDB/data/VectorDB/dgai_recoupling_layout_debt/runs/sift_strategy23_c3_uniform_mixed_r1/query_trace.jsonl`

## 9. 最终裁决

**Exit DGAI。** 当前已提出的 DGAI query scheduling、selective recoupling、dynamic layout debt 和 update-quality repair 动机均已关闭。update-quality 分支的关闭原因不是 repair oracle 不够强，而是更前置：clean implementation 中没有复现需要 repair 的质量退化。除非未来先获得一个 clean、可持久化、跨 seed 的正观测，否则不重启 G1--G3，也不再为 DGAI 枚举次级 I/O/storage residual。
