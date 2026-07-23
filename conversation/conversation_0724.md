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

**Codex(00:31:40)：**
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

**PZ(00:33:02)**:
不需要测多次，时间太久了，测一次两次就行，另外是不是要避免把数据写系统盘上？

**Codex(00:34:42)：**
同意，已把冻结计划改为 **Recall 一次、性能两次**，不再做三次。Full 从 12 个 multi-L 进程降到 8 个：`PQ16/PQ32/PQ64/Exact × 2 repeats`，共 40 个 performance observations；每个进程仍一次加载并批量跑五个 L。两次原始结果都报告，mixed-precision GO 条件必须在两次中独立成立，不能靠均值或中位数挽救某次失败。若两次 p50 漂移超过 25%，直接标记 `PERFORMANCE-UNSTABLE` 并停止，不自动补第三次。

大文件也已明确禁止写系统盘。实测挂载关系为：

```text
/home/ubuntu/pz/VectorDB/data -> /dev/nvme8n1, 1.8TB, 当前约 727GB free
/home/ubuntu/pz             -> system LV, 当前约 139GB free
```

执行时固定：

```text
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
TMPDIR=$DATA_ROOT/tmp
```

下载、converted vectors、full graph/index、PQ artifacts、未压缩 per-query 数据和构图临时文件全部放 `DATA_ROOT`。系统盘上的仓库只保存计划、脚本、manifest、日志、压缩 CSV/JSON 和图。开始前必须用 `findmnt` 确认 `DATA_ROOT` 解析到 `/dev/nvme8n1`，并确认至少 30GB 可用，否则 hard stop。

缩减重复后，Cohere 路径预算调整为 3.5–7.5h，GIST fallback 为 2.5–5.5h，数据冻结后的 hard wall 从 10h 降为 8h。修订后的计划仍位于 [`EXPERIMENT_PLAN.md`](../codex/work/2026-07-24/pq_rp_highdim_a0/refine-logs/EXPERIMENT_PLAN.md)。当前仍未下载或运行实验，等待你或 Gpt 明确批准。

**PZ(01:16:03)：**
这些几百 G 的候选数据，后续应该用不到了吧？可以，执行吧。

**Codex(01:16:03)：**
已完成历史候选索引清理。删除范围严格限定为四棵已结束实验树中 basename
等于 `index` 的 232 个目录，以及
`dynamic_vamana_atlas/tmp` 旧临时目录；数据集、当前主索引、结果、日志、
manifest 和构建目录均未删除。

删除前对完整目标集合做了跨目录硬链接去重，索引目标占用为
746,728,136,704 字节。清理后以文件系统 `df` 的实际差值计，共释放
742,968,115,200 字节（691.943 GiB），挂载盘占用从约 1,012.9 GiB
下降到约 321.0 GiB，可用空间升至约 1.4 TiB，使用率为 19%。

清理后用 root 权限重新遍历，四棵历史树中残余 `index` 目录为 0，旧
`tmp` 已不存在；保留的 `datasets`、当前 `index`、`results` 和 `build`
分别约为 66G、68G、1.1G 和 17G。审计报告见
[`codex/share/2026-07-24/nvme_cleanup_0724.md`](../codex/share/2026-07-24/nvme_cleanup_0724.md)。
被删索引无法通过 Git 恢复，如后续需要只能依靠保留的数据、配置和脚本重建。

**Gpt(01:18:51)：**
我已审核修订后的 `PQ-RP-HIGHDIM-A0` 计划，批准按当前方案运行。

确认以下设置：

```text
Primary dataset:
Cohere-1M Wikipedia, 768D

Fallback:
GIST1M, 960D

Representations:
PQ16 / PQ32 / PQ64 / EXACT-NAV

L:
{50,100,200,400,800}

Search:
W=4, K=10, one thread, zero node cache

Execution:
Recall once
Performance exactly twice
No automatic third repeat

Hard wall:
8 hours after the selected dataset is locally frozen
```

大文件、converted vectors、graph/index、PQ artifacts、临时文件和未压缩结果必须全部写入：

```text
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724
TMPDIR=$DATA_ROOT/tmp
```

执行前必须确认 `findmnt -T "$DATA_ROOT"` 解析到 `/dev/nvme8n1`，且可用空间不少于 30GB。失败则 hard stop。

补充两项结果表述纪律：

1. 本轮同时改变了数据集、维度、分布和 metric。即使 Cohere-768 与 SIFT128 的曲线不同，也只能表述为 workload-specific evidence，禁止把差异单独归因于维度。
2. `GO-MIXED-PRECISION-NOVELTY-KILL-MAP` 只表示“统一 PQ64 有效但 DRAM 昂贵”，不表示额外精度具有可选择性。通过后仍需单独验证高精度收益是否集中在少量节点、查询或 frontier 决策上。

按冻结顺序执行：

```text
M0 dataset/metric audit
→ M1 one shared graph + shared PQ training sample
→ M2 Canary
→ M3 full matrix
→ M4 preregistered decision
```

Cohere 任一 revision/hash/license/shape/norm/GT 审计失败，直接切换 GIST，不得自行修复或重新归一化。Canary 任一 gate 失败则停止 Full。

本轮禁止加入：

```text
OPQ / RPQ / RaBitQ / LVQ / LeanVec
mixed precision
selective exact
residual refinement
新的 L/W 点
```

完成后在对话中只回报：

* 实际选择的数据集及 M0 审计结果；
* PQ16/32/64/Exact 的核心 RP-memory 曲线；
* matched-recall PQ32↔PQ64 对比；
  -两次性能重复的稳定性；
  -最终 GO/HOLD/KILL 裁决；
  -实际时间、内存和 NVMe 占用。

可以开始运行。

**Codex(02:37:55)：**
`PQ-RP-HIGHDIM-A0` 已按冻结门禁推进到 M2，并因 Canary 稳定性失败停止；
没有运行 Full，也没有添加第三次重复。

M0 首选 Cohere 镜像失败：全量 base 的最大 `|norm-1|=16.4741764`，远超
`1e-4` 门限。未做归一化或修复，按预注册切换到 GIST1M-960D。GIST 的
HDF5/base/query/GT 四个 SHA 均匹配，shape 为
`1M×960 / 1K×960 / 1K×100`，GT 距离单调违规为 0，6 个固定 query 的
独立 exact top-100 集合均 100/100 一致。

M1 构建了一张 R64/L100 full-precision 图，大小 8,192,004,096B，SHA 为
`52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`。
PQ16/32/64 使用同一 100,000 行训练样本，三者 graph realpath 完全一致；
code resident 分别为 16/32/64MB。共享样本重构 L2² median 为
0.7959/0.6540/0.5120。

Canary 中 Exact L800 Recall@10 为 99.85%，返回 IDs 和 Recall 在两次间
完全一致。诊断性的 95.5% common-recall 对比为 PQ32 L800（95.8%）对
PQ64 L400（97.25%）：两次分别得到 2.093×/1.875× QPS、49.29% reads
降低、61.65%/39.04% p99 降低。但 PQ32 L200 p50 漂移 65.1%，Exact
L200 漂移 28.1%，均违反 25% 稳定性门禁。因此这些强数值不能升级为
GO；GIST 本来也只能支持最高 `HOLD-DATASET-SPECIFIC`。

最终状态为：

```text
STOP-CANARY
NO GO/HOLD/KILL PAPER DECISION
NO FULL MATRIX
NO THIRD REPEAT
```

总计使用 0 GPU；M1 53m34.67s，M2 2m16.34s，峰值 RSS 约 12.41GiB。
本轮 NVMe 实际增量为 11.423GiB，当前约 333G used、1.4T available。
完整结果、原始曲线与 claim 边界见
[`EXPERIMENT_RESULTS.md`](../codex/work/2026-07-24/pq_rp_highdim_a0/EXPERIMENT_RESULTS.md)
和 [`findings.md`](../codex/work/2026-07-24/pq_rp_highdim_a0/findings.md)。
