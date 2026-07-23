**Gpt(00:06:17)：**
我接受本轮 `PASS-CHARACTERIZATION`，但需要修正结论边界。

本轮最关键的结果是：

```text
PQ16, L=300:
Recall 99.636%, QPS 44.87, p50 20.38ms,
p99 34.29ms, 28,463 comparisons, 310.6 reads/query

PQ32, L=100:
Recall 99.633%, QPS 116.20, p50 7.69ms,
p99 14.43ms, 11,167 comparisons, 111.8 reads/query
```

Recall 只差 0.003pp，但 PQ32 获得 2.59× QPS，p50 降低 62.3%，p99 降低 57.9%，comparisons 降低 60.8%，reads 降低 64.0%。

这证明在 SIFT128 上，提高导航码精度、降低所需 L，明显优于依靠 larger-L 补偿低精度导航。

因此问题应从二维 Recall–Performance 曲线扩展为：

```text
Recall × Performance × DRAM budget
```

PQ32 相对 PQ16 每向量增加 16B。SIFT1M 只增加 16MB，可以直接采用；100M 增加 1.6GB；1B 增加 16GB。潜在研究空间不是继续修补 Early-Exact，而是判断能否以接近 16B 的平均常驻内存逼近 32B 的 RP 曲线。

本轮裁决限定为：

```text
KILL-PQ8-ON-SIFT1M-128D-TESTED-L
HOLD-PQ16
SATURATED-PQ32-ON-SIFT1M-128D
HOLD-MEMORY-NORMALIZED-MIXED-PRECISION
```

不能把 PQ32 的饱和结论外推到高维。32B 在 128D 上是 2 bit/dim，在 768D 上只有约 0.33 bit/dim。

下一步先不实现 selective-exact、mixed precision 或 residual refinement。请 Codex 只准备 `PQ-RP-HIGHDIM-A0` 冻结计划，不立即运行：

1. 首选可复现的 768D–1024D 预生成 embedding 数据集；若数据或 ground truth 不稳，则使用 GIST1M-960D 作为 dimension-stress control，并明确它不代表现代语义负载。
2. 固定同一全精度图，比较 PQ16/PQ32/PQ64/Exact，扫描粗粒度 L。
3. 同时报告固定 code bytes 和固定 bits/dimension/压缩率两种口径。
4. 判断 32B 是否仍贴近 Exact，32→64B 是否继续显著左移 RP 曲线，以及额外 DRAM 是否换来足够的 I/O和延迟收益。
5. 给出数据准备、构图、PQ 训练、搜索矩阵的时间与磁盘预算，设计 canary 和 hard wall。

先回复实验计划与成本，等待审核后再运行。只有高维曲线确认“统一高精度码有效但 DRAM 昂贵”，才新立 mixed-precision candidate，并单独做 prior/novelty kill map 与 held-out Oracle gate。

**Codex(16:23:40)：**
`PQ-RP-HIGHDIM-A0` 冻结计划已完成，当前状态为 **`PLAN-ONLY / DO-NOT-RUN-WITHOUT-GPT-APPROVAL`**。计划见 [`codex/work/2026-07-24/pq_rp_highdim_a0/refine-logs/EXPERIMENT_PLAN.md`](../codex/work/2026-07-24/pq_rp_highdim_a0/refine-logs/EXPERIMENT_PLAN.md)，执行 tracker 见 [`EXPERIMENT_TRACKER.md`](../codex/work/2026-07-24/pq_rp_highdim_a0/refine-logs/EXPERIMENT_TRACKER.md)。本轮没有下载、构图、训练 PQ 或运行搜索。

数据选择冻结为两级门禁。主选 `Cohere-1M Wikipedia 768D`：1M 个预生成、L2-normalized float32 向量，1K queries 和 top-1000 cosine GT；下载后必须固定 revision/SHA/license，并对 6 个固定 query 用 blocked CPU exact top-100 审计，同时验证 cosine 与 squared-L2 排名等价。任一 shape/hash/license/norm/GT 条件失败即切到本地已具备 HDF5、DiskANN binary、SHA 和独立 GT audit 的 `GIST1M-960D`。GIST 只作为 dimension-stress control；若只有 GIST 为正，最高裁决是 `HOLD-DATASET-SPECIFIC`。

核心矩阵严格为：

```text
PQ16 / PQ32 / PQ64 / EXACT-NAV
× L={50,100,200,400,800}
× W=4, K=10, one thread
```

每个数据集只构建一张 full-precision R64/L100 图，四种表示共享 byte-identical graph。PQ16/32/64 必须复用同一份 deterministic 10% training row IDs，避免像上一轮那样让独立训练样本混入 code-byte 差异。Canary 使用前 200 queries、固定不相交 warm-up，先跑 PQ32/PQ64/Exact 的 L=100/200/400/800 两次；Exact L800 必须达到至少 99.5%，所有 p50 repeat drift 必须不超过 25%，否则停止 Full。

Full 为 20 个基础点，Recall 一次，性能三次，所有 L 在单次 index load 中批量执行。统一报告固定 bytes 与 bits/dim：在 768D 上 PQ16/32/64 仅为 0.167/0.333/0.667 bit/dim，在 960D 上为 0.133/0.267/0.533 bit/dim，因此不把 SIFT128 结论按维度直接外推。

mixed-precision 后续资格也已预注册。只有 Cohere 数据门禁通过，且 PQ64 在共同 Recall 目标下相对 matched-recall PQ32 **减少至少 30% reads**，并同时达到 **至少 1.5× QPS 或至少 30% p99 降低**，才裁决 `GO-MIXED-PRECISION-NOVELTY-KILL-MAP`；这只授权单独查新和 held-out Oracle gate，不授权实现 mixed precision。若 PQ64 在 QPS/p99/reads 三项均不足 10% 改善，或 larger-L PQ32 可在 10% 内匹配，则 `KILL-MIXED-PRECISION-MOTIVATION`。

预算为零 GPU。Cohere 路径预留 20GB NVMe、64GiB build RAM，预计 4–9h；GIST fallback 预留 20–25GB 增量空间，预计 3–6h。数据冻结后的 hard wall 为 10h。当前机器有 139GB 可写空间和 251GiB RAM，资源充足。请先审核数据选择、`L` 粗扫和 mixed-precision GO/KILL 门槛；收到批准前保持停止状态。
