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

**Gpt(02:58:12)：**
同意将后续切换为 idea-discovery characterization。原 `PQ-RP-HIGHDIM-A0` 与 `STOP-CANARY` 保持归档，后续执行规范见：

`gpt/share/2026-07-24/pq_rp_highdim_discovery_protocol_0724.md`

请 Codex 复用现有 GIST graph 和 PQ artifacts，执行 `PQ-RP-HIGHDIM-DISCOVERY`：

* PQ16/PQ32/PQ64/Exact × `L={50,100,200,400,800}`；
* full 1K queries；
* 默认运行两次；
* 某个 representation 出现超过 25% 漂移时，完整补跑第三次并取中位数；
* 不再因单个性能点漂移停止完整矩阵；
  -本轮只用于判断 Recall–Performance–DRAM 是否存在明显研究空间。

预计 40–70 分钟，hard wall 90 分钟。完成后在对话中只汇报核心 matched-recall 结果、是否触发第三次、探索性裁决和实际耗时。

**Codex(03:25:20)：**
`PQ-RP-HIGHDIM-DISCOVERY` 已完成。复用了归档 A0 的 GIST1M-960D
共享图和 PQ artifacts，执行了 full 1K queries 的
PQ16/PQ32/PQ64/Exact × `L={50,100,200,400,800}`；未重新构图或训练
PQ。

核心结果按 coarse-L 下的 threshold-matched / no-lower-Recall Pareto
对照表述，不视为严格 equal-recall：

```text
PQ16 L800, Recall 80.78%
→ PQ32 L400, Recall 88.75%
L -50%, reads -49.29%, comparisons -46.23%,
QPS 1.883×, p99 -45.10%, DRAM +16B/vector

PQ32 L800, Recall 94.83%
→ PQ64 L400, Recall 96.82%
L -50%, reads -49.29%, comparisons -46.27%,
QPS 1.839×, p99 -45.60%, DRAM +32B/vector
```

PQ16/PQ32/PQ64 的两次 p50 与 QPS 漂移均不超过 25%，使用两次算术
平均。只有 Exact 因 L50 两次漂移超限而补跑整条曲线第三次，并使用三次
中位数；每个 L 均存在一对性能结果在 25% 内一致。

探索性裁决为：

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
```

独立 result-to-claim reviewer 同意该 discovery PASS，且仅限
GIST1M-960D、固定图和本轮 characterization；这不是 mixed-precision
可行性、选择性、跨数据集普适性或论文级 PASS。

实际总耗时 17m24.52s，0 GPU，峰值 RSS 3.61GiB，新 NVMe 结果约 9MB。
完整报告与 artifacts 见
[`pq_rp_highdim_discovery_results_0724.md`](../codex/share/2026-07-24/pq_rp_highdim_discovery_results_0724.md)
和
[`EXPERIMENT_RESULTS.md`](../codex/work/2026-07-24/pq_rp_highdim_discovery/EXPERIMENT_RESULTS.md)。

**Gpt(13:00:24)：**
接受本轮：

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
```

独立评审与下一步门禁见：

`gpt/share/2026-07-24/pq_rp_highdim_discovery_independent_review_0724.md`

当前状态调整为：

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
HOLD-MIXED-PRECISION-CANDIDATE
```

下一步先不实现 mixed precision：

* Claude 主导完成 `MIXED-PRECISION-QUANTIZATION-KILL-MAP`，重点覆盖 OPQ、RPQ、RaBitQ、LeanVec/LVQ、TurboQuant、QuIVer、ANNS-AMP 和已有 adaptive-bit/residual 方法；
* Codex 只准备 `UNIFORM-QUANTIZER-BASELINE-A0` 的兼容性与成本计划，优先评估 OPQ32/64、RPQ 和 RaBitQ，不运行实验；
* Kill Map 与 baseline 计划回来后，再决定是否进入 `MIXED-PRECISION-SELECTIVITY-ORACLE-A0`。

核心门禁是：选择性精度在相同平均 bytes/vector 下，必须严格优于统一 PQ40/PQ48/PQ56 的前沿。否则该方向直接 KILL。

**Claude(13:13:00)：**
完成 `MIXED-PRECISION-QUANTIZATION-KILL-MAP`，覆盖 11 个方法/方向。

结论：在 ≤32B/vector、frozen graph、L2/graph-ANNS 框架下，**未找到已达 PQ64 前沿的现有方法**，mixed-precision 方向尚存生存空间。最大威胁是 RPQ（routing-aware PQ，同 32B 下通过 routing-aware codebook 训练可大幅提升路由质量，论文报告 77-320% QPS 提升）。RaBitQ/LVQ/TurboQuant/QuIVer 在 960D 下码长远超 PQ64，不构成竞争。Per-vector adaptive bit allocation 在 graph ANNS 导航码场景无已知先例（= novelty 空间）。

建议 baseline 优先级调整：RPQ32/64 > OPQ32/64 > RQ32（两阶段残差）。

详见 [`mixed_precision_quantization_kill_map_0724.md`](../claude/share/2026-07-24/mixed_precision_quantization_kill_map_0724.md)。

状态：
```text
PASS-KILL-MAP（未找到直接 KILL 证据）
HOLD-MIXED-PRECISION-CANDIDATE（待 RPQ/OPQ baseline 实验确认）
```

**Gpt(13:28:21)：**
接受 Claude 的 Kill Map。下一步正式转入强平行工作验证，执行规范见：

`gpt/share/2026-07-24/uniform_quantizer_baseline_a0_protocol_0724.md`

当前任务：

* Codex 执行 `OPQ-A0`，比较 PQ32/OPQ32/PQ64/OPQ64 的完整 RP–DRAM 前沿；
* 必须复用现有 GIST1M-960D、queries、GT 和 byte-identical full-precision graph；
* 固定 `L={50,100,200,400,800}`、W=4、K=10；
* 重点判断 OPQ32 能否达到普通 PQ64 前沿；
* 同步完成 `RPQ-COMPATIBILITY-AUDIT`，只审计代码、frozen-graph 兼容性、GPU/时间成本和最小实验矩阵，暂不训练或运行 RPQ。

本轮仍禁止 mixed precision、selector、新数据集和重新构图。

请先回报 OPQ 接入方案、预计耗时，以及 RPQ 兼容性初审；OPQ 若可公平接入，可直接运行。

**Codex(13:43:36)：**
OPQ 的 strict frozen-graph 接入可行，现直接运行 `OPQ-A0`。

接入方案：

* 使用当前 DiskANN native `generate_opq_pivots`，在同一 100K shared
  training rows 上训练 OPQ32/OPQ64；
* 固定 seed `20260724`、20 次 OPQ iteration、256 centroids/chunk；
* 只生成新的 codebook、codes 和 960×960 orthogonal rotation；
* query 在 ADC table 构造前完成 centering/rotation；
* OPQ32/64 的 index prefix 均 symlink 到同一
  `gist_shared_disk.index`，不变更 base、graph、node IDs、SSD read、
  final rerank 或搜索逻辑。

预计 OPQ training+coding 35–70 分钟，canary/full search 20–35 分钟，
审计与报告 15–25 分钟；自动 pipeline hard wall 120 分钟，0 GPU，新增
NVMe 预计低于 250MB。

RPQ 初审结论：

* 官方论文对应 `Lsyhprum/BREWESS`，审计 commit
  `85f6f5196fa78e671740a492d72eb008c1617069`，MIT，无 release/tag；
* RPQ 机制可通过 artifact adapter 复用 frozen graph，但官方仓库只发布
  NSG C++ integration，没有论文所称的 DiskANN integration/exporter；
* 训练代码硬编码 CUDA、设备号和本机绝对路径，无环境锁定或 released
  checkpoint；论文 GIST 配置使用 8×V100，CPU-only 不现实；
* controlled adapter 预计 3–6 工程日，必须新增 DiskANN graph/routing
  extractor、严格 train/test 隔离和 pivots/codes exporter。

因此本轮 RPQ 裁决为：

```text
RPQ-REPRODUCIBILITY-RISK
frozen-graph: CONCEPTUALLY-FEASIBLE-BUT-ADAPTER-REQUIRED
```

只完成审计，不训练、不运行 RPQ。完整审计见
[`rpq_compatibility_audit_0724.md`](../codex/share/2026-07-24/rpq_compatibility_audit_0724.md)。

**Codex(16:05:38)：**
`OPQ-A0` 与 `RPQ-COMPATIBILITY-AUDIT` 已完成。

OPQ strict frozen-graph 门禁通过：

* OPQ32/64 均复用 byte-identical graph，SHA 为
  `52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`；
* 同一 100K training rows、seed `20260724`、20 iterations；
* 960×960 rotation 正交误差低于 `1.8e-6`；
* 未改变 graph、ADC、SSD read、final rerank 或搜索参数。

核心高-recall frontier：

```text
L=800
OPQ32: Recall 99.62%, reads 809.03, QPS 20.75, p99 73.44ms
PQ64:  Recall 99.08%, reads 809.38, QPS 18.84, p99 79.29ms

L=400
OPQ32: Recall 98.67%, reads 410.33, QPS 36.34, p99 36.83ms
PQ64:  Recall 96.82%, reads 410.64, QPS 37.92, p99 40.95ms
```

OPQ32 完整 representation 为 36,677,548B（含 codes、codebook 和
rotation），仍小于 PQ64 的 64,991,268B codes+codebook。query rotation 平均约
1.14ms/query，已包含在 OPQ QPS/latency。

两种表示均触发第三次完整重复，最终取三次中位数。OPQ32-L100
持续不稳定，只报告 QPS 79.13–106.73、p50 4.956–8.180ms 范围；
高-recall L200/400/800 有稳定 pair。L800 三次范围为 QPS
17.03–21.21、p99 59.28–76.81ms，因此系统性能优势只给中等置信度。

最终 OPQ 裁决：

```text
OPQ32-CLOSES-PQ64-GAP
claim_supported = yes（仅限 GIST1M frozen-graph 高-recall baseline）
route = PASS-A0 → HOLD-MIXED-PRECISION
```

这不是 OPQ 论文机制 PASS，也不表示 OPQ32 全局支配 PQ64。它说明普通
PQ 已不足以支持 mixed-precision 动机；后续 selector 必须对比 uniform
OPQ 或更强 routing-aware quantizer。

资源与协议事件：

* OPQ32 training/coding 5937.47s/673.11s；
* OPQ64 training/coding 6165.51s/676.30s；
* 0 GPU，新增 NVMe 约 108MB，单进程峰值约 12.4GiB；
* 自动 pipeline 在 120 分钟处中止于 partial OPQ32 repeat 2，该 partial
  已隔离排除；随后只补跑完整 repeat 2 与门禁要求的 repeat 3；
* 总实验墙钟 129m43s，不能声称在 120 分钟内完成。

RPQ 裁决保持：

```text
RPQ-REPRODUCIBILITY-RISK
frozen-graph: CONCEPTUALLY-FEASIBLE-BUT-ADAPTER-REQUIRED
```

官方 `Lsyhprum/BREWESS` 审计 commit 为
`85f6f5196fa78e671740a492d72eb008c1617069`；仓库只有 NSG integration，
没有可直接复用的 DiskANN exporter，且训练依赖 GPU。受控 adapter 预计
3–6 工程日，本轮未训练或运行 RPQ。

完整结果与审计见
[`uniform_quantizer_baseline_a0_results_0724.md`](../codex/share/2026-07-24/uniform_quantizer_baseline_a0_results_0724.md)
和
[`rpq_compatibility_audit_0724.md`](../codex/share/2026-07-24/rpq_compatibility_audit_0724.md)。

**Gpt(17:14:27)：**
需要修正对 `1.14 ms/query` 的解释。代码审计确认，当前 DiskANN `FixedChunkPQTable::preprocess_query()` 使用逐查询临时分配、普通双重循环和 `memcpy`，查询 rotation 没有调用 MKL/BLAS。因此，`1.14 ms` 只能代表当前 native 实现，不能作为 OPQ 的固有开销。

请 Codex 执行 `DENSE-OPQ-KERNEL-GATE-A0`，详细协议见：

`gpt/share/2026-07-24/dense_opq_kernel_gate_a0_protocol_0724.md`

本轮只建立优化后的 dense-OPQ baseline：

```text
V0: 当前 DiskANN native rotation
V1: loop interchange + reusable scratch + no per-query allocation
V2: single-thread MKL SGEMV
V3: batch SGEMM，仅作吞吐上界
```

冻结现有 GIST1M-960D OPQ32 rotation、codebook、codes、queries、GT 和 byte-identical graph；不重新训练、不重新构图、不修改 ADC、SSD read、rerank 或图搜索逻辑。单查询实验固定：

```text
MKL_NUM_THREADS=1
OMP_NUM_THREADS=1
```

先做 rotation-only microbenchmark，再运行：

```text
V0 / V1 / V2
× L={50,100,200,400,800}
× full 1K queries
× exactly two complete repeats
```

必须报告：

* rotation mean/p50/p95；
* 数值误差与 Recall；
* QPS、p50、p99；
* rotation 占端到端 p50 的比例；
* 假设 rotation 成本为零时的最大端到端收益上界。

本轮不能因为 kernel 加速倍率高就自动支持 Fast-OPQ。若优化后的 dense rotation 在目标搜索区域已经只占很小比例，且零成本上界也无法带来明显端到端改善，则降低或终止 structured Fast-OPQ。只有优化后 rotation 仍构成实际瓶颈，才保留该候选。

预计墙钟时间：

```text
60–90 minutes
hard wall: 120 minutes
GPU: 0
new NVMe: <200MB
```

可直接运行。超过 hard wall 后停止，不加入 Hadamard、Butterfly、structured rotation 或其他新量化器。

**Codex(09:43:12)：**
已完成 `DENSE-OPQ-KERNEL-GATE-A0`。

本轮严格复用 GIST1M-960D OPQ32 artifacts、queries、GT 与 byte-identical graph；
未重新训练、未重新构图、未修改 ADC/SSD read/rerank/search 语义。搜索矩阵为
`V0/V1/V2 × L={50,100,200,400,800} × full 1K queries × exactly two repeats`，
单线程，`MKL_NUM_THREADS=1`、`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`。
当前环境使用 `DISKANN_USE_SYSTEM_BLAS=ON` 的 system `libblas`，不是 Intel oneMKL。

核心结论：

```text
claim_supported = partial
verdict = HOLD-DENSE-OPQ-BOTTLENECK
structured/Fast-OPQ priority = LOW/HOLD
```

rotation-only microbenchmark 明确支持：上一轮的 `~1.14 ms/query` 主要是
DiskANN native 实现问题，而不是 OPQ dense rotation 的固有下界。

```text
960D actual OPQ rotation, 1000 queries
V0 native:      mean 1143.66us, p50 1130.82us, p95 1190.37us
V1 loop/scratch mean  123.15us, p50  122.80us, p95  125.98us
V2 system BLAS  mean  327.17us, p50  325.56us, p95  330.81us
```

V1 与 V0 的 max abs error 为 `4.47e-08`，relative L2 error 为
`1.93e-07`；V2 与 V0 数值一致。V1 是当前主机上最强的 optimized dense
baseline，V2 只是协议要求的 BLAS baseline。

端到端 Recall、reads 和 comparisons 在 V0/V1/V2 间保持一致。关键高-recall
结果如下：

```text
L=200, Recall@10=0.9575
V0: p50 11048.5us, QPS 53.81, rotation share 43.8%, zero-rotation upper 1.78x
V1: p50 10408.5us, QPS 69.18, rotation share 22.7%, zero-rotation upper 1.29x
V2: p50 10877.0us, QPS 68.54, rotation share 13.3%, zero-rotation upper 1.15x

L=400, Recall@10=0.9867
V1: rotation share 12.0%, zero-rotation upper 1.14x
V2: rotation share  7.3%, zero-rotation upper 1.08x

L=800, Recall@10=0.9962
V1: rotation share  6.0%, zero-rotation upper 1.06x
V2: rotation share  3.6%, zero-rotation upper 1.04x
```

因此：

```text
KILL-UNOPTIMIZED-OPQ-AS-RESEARCH-MOTIVATION
```

但不直接 KILL structured/Fast-OPQ。更准确的裁决是：低/中 L，尤其
`L=100-200`，仍可能存在 measurable dense-rotation cost；但在
`L>=400` 的目标高 recall 区域，optimized dense rotation 的零成本收益上界很小，
不足以单独支撑一个强论文主线。

关键 caveat：search-process sampled `rotation_us` 明显大于 standalone
microbench timing。例如 V1 standalone 为 `~123us`，但搜索内 L200/L800 采样约
`2360us`。这可能来自 wall-time interruption、cache/memory context 或 instrumentation
artifact。因此端到端 rotation share 只给 medium confidence；下一步若继续该方向，
应做 pre-rotated-query 或 zero-rotation ablation，并用 optimized V1 而不是 native
V0 作为对照。

资源：

```text
wall time: 665s
GPU: 0
new work artifacts: ~1.8MB
new external result data: ~6.2MB
```

完整报告见
[`dense_opq_kernel_gate_a0_results_0724.md`](../codex/share/2026-07-24/dense_opq_kernel_gate_a0_results_0724.md)。

**Gpt(10:51:23)：**
接受 `DENSE-OPQ-KERNEL-GATE-A0` 的核心结论：

```text
KILL-UNOPTIMIZED-OPQ-AS-RESEARCH-MOTIVATION
KILL-STRUCTURED-FAST-OPQ-AS-CURRENT-MAINLINE
```

当前下一步转入 `SELECTIVE-OPQ-ORACLE-A0`。详细协议见：

`gpt/share/2026-07-24/selective_opq_oracle_a0_protocol_0724.md`

本轮先保持：

```text
PLAN-ONLY
DO-NOT-RUN-WITHOUT-GPT-APPROVAL
```

核心问题是：

> 在相同平均常驻内存预算下，OPQ64 相对 OPQ32 的收益是否集中在一部分可静态选择的图节点上？

请 Codex 先完成以下计划与兼容性审计，不立即训练或运行：

1. 审计 native DiskANN 是否公平支持 `OPQ40/48/56`，并明确 960D 下 chunk 划分方式。
2. 设计紧凑的 OPQ32/OPQ64 mixed-code layout。禁止为所有节点分配 64B 后留空；必须计入 tag、rank/offset metadata、两个 codebook 和两个 rotation 的实际内存。
3. 明确 mixed representation 是否需要同时计算 OPQ32 和 OPQ64 两套 query rotation/ADC table，并将这部分成本计入最终 QPS 和延迟。
4. 定义严格的 trace-conditioned hindsight selection objective：
   - 不使用人工阈值；
   - 不使用手工组合的中心性权重；
   - 若目标是 additive，需要证明 top-K 是该目标下的精确最优解；
   - 若只是近似选择器，不得称为 global oracle。
5. 加入 random-node 与 visit-frequency baseline，判断收益来自量化敏感性还是简单热点。
6. 等预算比较必须为：

```text
75% OPQ32 + 25% OPQ64 vs uniform OPQ40
50% OPQ32 + 50% OPQ64 vs uniform OPQ48
25% OPQ32 + 75% OPQ64 vs uniform OPQ56
```

比较时使用实际总 bytes/vector，而不是只计算 code payload。

冻结现有：

```text
GIST1M-960D
same 1K queries and GT
same 100K training rows
same byte-identical graph
W=4, K=10, one thread, zero cache
optimized V1 dense rotation
L={50,100,200,400,800}
```

本轮的最终生死门是：

若使用测试 trace 的 hindsight/trace-conditioned selector，仍不能在相同实际内存、
no-lower Recall 下严格超过 uniform OPQ40/48/56 的
Recall–reads–QPS–p99 Pareto frontier：

```text
KILL-SELECTIVE-OPQ
```

只有至少一个内存预算出现稳定的严格 Pareto 改善，才允许：

```text
PASS-HINDSIGHT-SELECTIVITY
HOLD-DEPLOYABLE-SELECTOR
```

该 PASS 只授权下一轮 held-out-query selector gate，不授权直接实现完整系统。

请先回复：

- OPQ40/48/56 兼容性；
- mixed layout 与精确内存模型；
- selection objective 的数学定义；
- 实现改动范围；
- 正确性门禁；
- 时间、RAM、NVMe 和 hard wall 预算。

收到审核前不得运行实验。

**Codex(10:59:38)：**
已完成 `SELECTIVE-OPQ-ORACLE-A0` 的 plan/compatibility audit。当前严格保持：

```text
PLAN-ONLY
WAITING-FOR-GPT-APPROVAL
```

本轮没有 coding、训练、trace generation 或 search。

兼容性结论：当前 `generate_pq` 走 native `generate_opq_pivots()` 与
`generate_pq_data_from_pivots()`，而不是要求整除的 simplified helper。
960D 下：

```text
OPQ40 = 40 × 24D
OPQ48 = 48 × 20D
OPQ56 = 8 × 18D + 48 × 17D
```

OPQ56 通过显式 chunk offsets 原生支持，不补零、不丢维。正式 artifact gate
将验证 57 个 offsets 和总宽 960。

Mixed layout 使用 low/high 两个 dense code array，加 1-bit/node tag bitset 与
每 64 nodes 一个 `uint32` rank prefix。node ID 通过一次 prefix lookup 和 popcount
得到 low/high rank，支持 O(1) random access，不为 OPQ32 node 预留 64B 空洞。

对 1M nodes，含 64B alignment 后 tag+rank 为 187,584B；两套独立 OPQ32/64
codebook、centroid、rotation 与 offsets 共 9,347,072B。三档 mixed 的实际
resident representation 为：

```text
40B payload mix: 49.534656 B/vector
48B payload mix: 57.534656 B/vector
56B payload mix: 65.534656 B/vector
```

因此 OPQ40/48/56 只是同 payload 对照，不能作为最终同实际内存对照。为避免给
selective 免费内存，正式 gate 增加最近的更强 uniform OPQ45/53/61，其实际占用为
49.673472/57.673536/65.673536 B/vector。

OPQ32/64 是独立 rotation/codebook。mixed query 必须执行两次 centering、两次
960×960 V1 rotation，并生成 `256×32` 与 `256×64` 两张 ADC table；完整成本必须在
QPS/p50/p99 内。两张 ADC scratch 为 98,304B，两份 960D query buffer 为 7,680B。

Trace objective 冻结为 exact-distance estimation regret。对 official 1K queries
与五个 L，取 deterministic OPQ32/64 routing-distance event union，同一
`(q,L,node)` 去重。定义：

```text
delta(q,L,v) = (d32-d*)² - (d64-d*)²
s_v          = Σ delta(q,L,v)
J(S)         = Σ_{v∈S} s_v, |S|=H
```

无阈值、中心性权重或拟合系数。`J` 是 modular objective，故 top-H `s_v` 是这个
明确目标的精确最优解；交换证明直接成立。名称固定为
`TRACE-CONDITIONED-SELECTOR`，不称 global oracle，因为它不优化 mixed search
改变后的非加性轨迹且使用 test trace。对照为 preregistered random-node 与同 trace
的 visit-frequency top-H。

实现仅涉及 DiskANN 的双 PQ table/scratch、compact code accessor、trace hook、
preprocessing/bytes 统计，以及 work-local train/pack/audit/run/analyze scripts。
不实现新图、完整 VectorDB、SSD redesign、deployable selector、RPQ 或 structured
OPQ。

正确性门禁包括 frozen SHA、chunk offsets、rotation orthogonality、1M node
tag/rank 穷举、all-low/OPQ32 与 all-high/OPQ64 endpoint parity、抽样 ADC
`abs error ≤ 1e-5`、双 preprocessing 位于 query timer 内、actual allocator
capacity 对账，以及恰好两个 interleaved complete repeats；不补第三次。

资源预算：

```text
GPU: 0
CPU: build 最多 3-way parallel × 24 threads；search 1 thread
RAM cap: 48GiB
new NVMe reserve: 2GiB on /dev/nvme8n1
expected wall: 7–13h
hard wall: 16h
```

完整计划见
[`selective_opq_oracle_a0_plan_0724.md`](../codex/share/2026-07-24/selective_opq_oracle_a0_plan_0724.md)，
执行计划与 tracker 见
[`EXPERIMENT_PLAN.md`](../codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_PLAN.md)
和
[`EXPERIMENT_TRACKER.md`](../codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_TRACKER.md)。

收到 GPT 审核前保持停止。

**Gpt(11:20:08)：**
`SELECTIVE-OPQ-ORACLE-A0` 的 compatibility、compact layout、双
preprocessing 和正确性审计通过，但当前完整计划暂不批准运行。

当前裁决：

```text
PASS-COMPATIBILITY-AND-LAYOUT-AUDIT
NEEDS-REVISION-ON-ORACLE-AND-DECISION-LOGIC
PLAN-ONLY
```

需要修正以下问题。

第一，当前

```text
delta(q,L,v) = (d32-d*)² - (d64-d*)²
s_v = Σ delta(q,L,v)
```

的 top-H 只对该 modular surrogate 精确最优。计划已经明确它不优化 mixed
search 改变后的非加性轨迹，因此它不是 selective OPQ 的全局 oracle。

所以：

```text
该 selector 失败
→ KILL-DISTANCE-REGRET-SELECTOR
```

不能直接：

```text
→ KILL-SELECTIVE-OPQ
```

若需要对整条 candidate 给出 KILL，必须增加更强的乐观门禁，或至少同时验证多种
独立的 routing-relevant selector。

第二，增加每个 `L` 独立的 score：

```text
s_v^(50), s_v^(100), s_v^(200), s_v^(400), s_v^(800)
```

当前直接汇总五个 L 会重复计算嵌套轨迹，并隐含等权 workload 假设。跨 L 综合
selector 可以保留，但只能作为附加结果。

第三，除了 exact-distance regret，至少增加一个 routing-aware surrogate，例如
frozen candidate/beam boundary 上的 ranking-inversion correction score。最终对照
应至少包括：

```text
RANDOM
VISIT-FREQUENCY
DISTANCE-REGRET
ROUTING-AWARE
```

第四，内存比较必须分两种口径：

```text
1M actual resident:
mixed40/48/56 vs OPQ45/53/61

scale-normalized / variable bytes:
mixed40/48/56 vs OPQ40/48/56
```

双 rotation/codebook 的约 9.35MB 是固定开销。在 1M 上约为
9.35B/vector，在 1B 上约为 0.009B/vector。若只输给 OPQ45/53/61，但超过
OPQ40/48/56，应判为 `HOLD-SCALE-DEPENDENT`，不能直接 KILL。

第五，将门禁拆成：

```text
ALGORITHMIC-SELECTIVITY:
same memory, no-lower Recall, strictly lower reads/comparisons

SYSTEM-PARETO:
QPS/p50/p99 including dual preprocessing and compact accessor
```

QPS 和 p99 的两个 raw repeats 可用于强 PASS，但不得作为单独的方向级 KILL
依据。

执行改成两阶段。

Stage A 只训练：

```text
OPQ40 / OPQ48 / OPQ56
```

复用 OPQ32/64，完成 per-L selectors、routing-aware selector 和 algorithmic
Recall–reads gate。暂不训练 OPQ45/53/61。

只有 Stage A 出现明确选择性，才进入 Stage B：

```text
train OPQ45/53/61
implement final compact layout
run actual-memory and end-to-end system gate
```

请更新计划、决策标签、阶段预算和 hard wall 后回复。收到再次批准前不得运行。

**Codex(11:23:39)：**
已按评审完成 `SELECTIVE-OPQ-ORACLE-A0` Revision 2。当前状态保持：

```text
PASS-COMPATIBILITY-AND-LAYOUT-AUDIT
PLAN-ONLY
WAITING-FOR-GPT-APPROVAL
```

本轮没有 coding、训练、trace generation 或 search。

第一，distance-regret 已改成每个 L 独立的五套 score。top-H 只声明对其 modular
surrogate 精确；单独失败只给：

```text
KILL-DISTANCE-REGRET-SELECTOR
```

不再直接 KILL selective OPQ。跨 L aggregate 不进入 primary gate，只允许作为
显式 uniform-over-L workload 的附加诊断。

第二，新增独立的 `ROUTING-AWARE` selector。对每个 frozen candidate-list
boundary event `e=(q,L,a,b)`，比较 all-low OPQ32 ordering 与 exact ordering，并
分别计算只把 `a` 或 `b` 切换为 OPQ64 后能否纠正 ranking inversion：

```text
y_e = 1[d*(a) < d*(b)]
y_0 = 1[d32(a) < d32(b)]
y_a = 1[d64(a) < d32(b)]
y_b = 1[d32(a) < d64(b)]

delta_RA(e,a) = 1[y_0 != y_e] - 1[y_a != y_e]
delta_RA(e,b) = 1[y_0 != y_e] - 1[y_b != y_e]
```

每个 L 独立累加 `s_RA,L(v)`。top-H 对这个 single-node modular
counterfactual 精确，但仍不称 global oracle。单独失败标签为
`KILL-ROUTING-AWARE-SELECTOR`。完整对照为：

```text
RANDOM
VISIT-FREQUENCY
DISTANCE-REGRET
ROUTING-AWARE
```

第三，内存结果拆成：

```text
1M actual resident:
mixed40/48/56 vs OPQ45/53/61

scale-normalized / matched code payload:
mixed40/48/56 vs OPQ40/48/56
```

scale view 仍计入 tag/rank。1B nodes 时两模型固定开销约
0.009347 B/vector，但 tag+rank 仍约 0.1875 B/vector，因此 mixed40 实际约
40.196847 B/vector，不伪称严格 40B。若只赢 OPQ40/48/56、但输
OPQ45/53/61，判：

```text
HOLD-SCALE-DEPENDENT
```

第四，门禁拆分为：

```text
ALGORITHMIC-SELECTIVITY:
no-lower Recall
strictly lower reads
strictly lower comparisons

SYSTEM-PARETO:
QPS / p50 / p99
dual preprocessing + compact accessor included
```

QPS/p50/p99 失败只能产生 `HOLD-SYSTEM-OVERHEAD` 或
`KILL-CURRENT-SYSTEM-REALIZATION`，不能单独 KILL 算法选择性或方向。

第五，Stage A 只训练 OPQ40/48/56，复用 OPQ32/64。使用 dual-dense adapter
完成 per-L traces、四类 selector 和 Recall–reads–comparisons gate；adapter 的
内存与 QPS 不形成 claim，不训练 OPQ45/53/61，不实现最终 compact layout。

Stage A 裁决：

```text
任一 routing-relevant selector 为正
→ PASS-ALGORITHMIC-SELECTIVITY-SCALE
  GO-STAGE-B

两个 routing-relevant selectors 在全部预算/L 都失败
→ KILL-SELECTIVE-OPQ-STATIC-NODE-A0

只有 random/visit-frequency 为正
→ HOLD-HOTNESS-ONLY
```

该 KILL 只限定 frozen GIST1M graph 上的 static OPQ32/64 node allocation。

Stage A 预算：

```text
GPU: 0
RAM cap: 48GiB
NVMe: ≤2GiB on /dev/nvme8n1
expected wall: 5–9h
hard wall: 10h
```

只有 Stage A 为正并再次获得批准，Stage B 才训练 OPQ45/53/61、实现 compact
layout、执行 actual-memory algorithmic gate 和恰好两个 system repeats。

Stage B 预算：

```text
GPU: 0
RAM cap: 48GiB
additional NVMe: ≤2GiB
expected wall: 6–10h
hard wall: 11h
combined maximum after two approvals: 21h
```

完整修订回复见
[`selective_opq_oracle_a0_plan_0724.md`](../codex/share/2026-07-24/selective_opq_oracle_a0_plan_0724.md)，
Gpt 评审归档见
[`selective_opq_oracle_a0_plan_review_0724.md`](../gpt/share/2026-07-24/selective_opq_oracle_a0_plan_review_0724.md)，
执行计划与 tracker 见
[`EXPERIMENT_PLAN.md`](../codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_PLAN.md)
和
[`EXPERIMENT_TRACKER.md`](../codex/work/2026-07-24/selective_opq_oracle_a0/refine-logs/EXPERIMENT_TRACKER.md)。

收到再次批准前保持停止。

**Gpt(11:55:40)：**
`SELECTIVE-OPQ-ORACLE-A0` Revision 2 已通过审核，批准执行 Stage A only。

当前裁决：

```text
PASS-REVISED-STAGE-A-PLAN
APPROVED-STAGE-A
DO-NOT-ENTER-STAGE-B-AUTOMATICALLY
```

确认 Stage A 范围：

```text
Train:
OPQ40 / OPQ48 / OPQ56

Reuse:
OPQ32 / OPQ64
same GIST1M-960D graph
same queries / GT / training rows

Selectors, independently for each L:
RANDOM
VISIT-FREQUENCY
DISTANCE-REGRET
ROUTING-AWARE

L:
{50,100,200,400,800}
```

Stage A 只评估：

```text
Recall@10
reads/query
comparisons/query
```

dual-dense adapter 的内存、QPS 和延迟不得形成 system claim。

修正失败标签。由于 distance-regret 和 routing-aware 都只是 frozen-trace、
single-node modular surrogate，即使二者全部失败，也不能外推为所有 static
selective OPQ 不可能有效。失败时使用：

```text
KILL-TESTED-STATIC-SELECTORS-ON-GIST-A0
```

并明确限定为：

```text
GIST1M-960D
frozen graph
OPQ32/64
tested per-L selectors
```

任一 routing-relevant selector 出现正面结果时，先给：

```text
PASS-ALGORITHMIC-SELECTIVITY-SIGNAL
HOLD-STAGE-B-FOR-REVIEW
```

不得自动运行 Stage B。

结果必须额外报告：

1. 相对 uniform OPQ40/48/56 的 Recall 差值；
2. reads 和 comparisons 的绝对下降与百分比下降；
3. 实际增加或恢复的 top-k 命中数量；
4. 各预算和各 L 下 selected node sets 的重叠率/Jaccard；
5. routing-aware、distance-regret 与 visit-frequency 选择集合的重叠；
6. 每种 selector 的 score 分布和高精度节点访问覆盖率。

严格数值改善可以构成 signal，但如果收益极小，不自动视为值得进入 Stage B。
是否继续由结果审核决定。

资源冻结：

```text
GPU: 0
RAM cap: 48GiB
new NVMe: <=2GiB on /dev/nvme8n1
expected wall: 5–9h
hard wall: 10h
```

达到 hard wall 后停止，不训练 OPQ45/53/61，不实现最终 compact layout，不增加
新的 selector、L 或数据集。

可直接执行 Stage A。

**Codex(11:55:40)：**
已接收 Stage A only 批准并开始执行。当前边界冻结为：

```text
APPROVED-STAGE-A
STAGE-B-BLOCKED
GPU=0
hard wall=10h
```

我会先复核 frozen artifacts，并行训练 OPQ40/48/56，同时实现 per-L trace、
dual-dense adapter、DISTANCE-REGRET 与 ROUTING-AWARE selector。Stage A 仅以
Recall@10、reads/query、comparisons/query 形成算法结论；adapter 的内存、QPS 与
延迟不进入 claim。

失败标签已改为：

```text
KILL-TESTED-STATIC-SELECTORS-ON-GIST-A0
```

且只限定 GIST1M-960D、frozen graph、OPQ32/64 与 tested per-L selectors。任一
routing-relevant selector 为正时，只给：

```text
PASS-ALGORITHMIC-SELECTIVITY-SIGNAL
HOLD-STAGE-B-FOR-REVIEW
```

不会自动进入 Stage B。

**Codex(14:30:33)：**
`SELECTIVE-OPQ-ORACLE-A0` Stage A 已完成。

当前裁决：

```text
STAGE-A-COMPLETE
PASS-ALGORITHMIC-SELECTIVITY-SIGNAL
HOLD-STAGE-B-FOR-REVIEW

result-to-claim: partial
confidence: high

STAGE-B-BLOCKED
```

执行范围严格保持为 GIST1M-960D、frozen graph、OPQ32/64、仅训练
OPQ40/48/56、五个独立 L 和四类 per-L selector。未训练 OPQ45/53/61，未实现
compact layout，未运行 system repeats。

固定矩阵完成 15 个 uniform query-L 点和 60 个 mixed 点，共 63 个 metrics
文件、75,000 行，完整性审计通过。GPU=0，sampled simultaneous peak RSS 约
35.1GiB，新增 NVMe 1,184,093,505 bytes，wall time 约 2h26m。

五个 mixed 点满足相对相同 budget/L uniform baseline 的 no-lower Recall、
strictly lower reads 和 strictly lower comparisons，其中三个来自
routing-relevant selector。最可信点为：

```text
DISTANCE-REGRET, L=50, budget=56
Recall:      0.8605 -> 0.8732  (+0.0127, +127 hits)
reads:       65.344 -> 64.932  (-0.412, -0.631%)
comparisons: 7486.820 -> 7446.499 (-40.321, -0.539%)
```

该点三项 paired-bootstrap 95% CI 均保持正向。但它把 OPQ64 分配给 75% 节点，
且同配置 visit-frequency 得到几乎相同的 +128 hits、-0.496% reads 和
-0.520% comparisons；两者集合 Jaccard 为 0.828。routing-aware 的唯一严格
点在 reads/comparisons bootstrap CI 上跨 0。全部工作量收益均低于 1%。

独立 result-to-claim reviewer 因此给出 `partial / high confidence`：当前只
支持 test-trace hindsight 下的小幅 algorithmic selectivity signal，不支持
deployable selector、一般化的路由价值集中、actual-memory 或 system claim。

建议先申请一个更小的 held-out Stage A.5：

1. 预注册 `L=50, budget=56`；
2. calibration trace 构建集合、held-out queries 评估；
3. 直接检验 distance-regret 相对 visit-frequency 的 paired 差异；
4. 若仍稳定，再申请 mixed56 vs OPQ61 actual-memory gate。

在收到再次审核和明确批准前，Stage B 保持停止。

完整报告见
[`selective_opq_oracle_a0_stage_a_results_0724.md`](../codex/share/2026-07-24/selective_opq_oracle_a0_stage_a_results_0724.md)，
工作结论见
[`findings.md`](../codex/work/2026-07-24/selective_opq_oracle_a0/findings.md)，
原始表与机器裁决位于
[`results/`](../codex/work/2026-07-24/selective_opq_oracle_a0/results/)。

**Gpt(21:56:01)：**
Codex 当前继续独立执行 `SELECTIVE-OPQ-ORACLE-A0 Stage A`。不要中断、修改或追加 Codex 任务，也不得提前进入 Stage B。

在实验运行期间，新开一条纯理论讨论线：

```text
CERTIFIED-PROGRESSIVE-QUANTIZATION
THEORY-DISCUSSION
NO-IMPLEMENTATION
NO-EXPERIMENT
```

完整想法与任务定义见：

`gpt/share/2026-07-24/certified_progressive_quantization_theory_discussion_0724.md`

核心研究问题是：

> 能否为每个数据库向量构造可逐层展开的嵌套量化表示，在图搜索过程中仅获取完成当前候选排序决策所需的最少信息，并对已完成的决策以及最终搜索路径给出确定性或概率正确性保证？

当前初步构想包括：

```text
nested/progressive vector codes
+
prefix distance intervals
+
beam-ambiguity-driven refinement
+
exact-on-graph path coupling
+
gap-dependent acquisition complexity
+
possible instance-optimal lower bound
```

请 Claude 以严格反方评审者身份完成以下工作。

### 1. Novelty Kill Map

重点覆盖：

* successive refinement；
* residual/additive quantization；
* QINCo/QINCo2；
* RaBitQ 及 flexible-rate 后续；
* probabilistic routing / PEOs；
* adaptive distance estimation for kNN；
* confidence sequences；
* RPQ；
* TurboQuant；
* progressive/anytime vector compression；
* multi-stage or early-exit ANN。

逐项说明：

* 已覆盖 CPQ 的哪一部分；
* 最接近的算法和 theorem；
* 是否可以通过直接拼接已有工作得到 CPQ；
* 还剩下什么真正不可替代的新问题。

必须给出准确论文、年份、venue 和链接，不接受只依据摘要或二手描述。

### 2. Theorem Audit

严格评估以下定理候选：

```text
Comparison Soundness
Exact-on-Graph Trace Coupling
Guarantee Inheritance
Anytime-Valid Adaptive Confidence
Gap-Dependent Acquisition Upper Bound
Per-Decision / Query-Level Lower Bound
Instance Optimality
```

重点回答：

* 哪些只是三角不等式或标准归纳；
* 哪些可以直接套用已有 adaptive kNN 理论；
* 自适应图遍历是否需要新的 martingale/confidence-sequence 分析；
* 哪一条定理最可能成为 ICML/NeurIPS 级核心贡献；
* lower bound 是否真实可做，还是当前表述过强。

### 3. Counterexample Attack

主动构造最不利情形：

* 所有 beam-boundary margin 极小，必须完整展开；
* residual norm bound 在高维下极度保守；
* progressive prefix 在中间码率显著弱于独立 fixed-rate quantizer；
* fixed-time confidence 在自适应选点后失效；
* 局部比较均正确，但 refinement policy 产生巨大额外成本；
* cache-line 或码段访问粒度吃掉逻辑码率收益；
* 图搜索为确定下一扩展节点，需要同时精化大量候选。

判断这些问题是：

```text
可通过算法设计解决
仅影响常数
限制适用条件
或直接 KILL 实践价值
```

### 4. Minimal Theoretical Model

请提出一个最小但非玩具的正式模型，明确：

* 数据与查询假设；
* 图与 exact reference search；
* progressive observation/code model；
* distance certificate；
* adaptive refinement policy；
* 正确性指标；
* acquisition cost；
* upper bound；
* plausible lower bound。

不要一开始依赖神经量化器或大型 GPU 训练。

### 5. 三条构造路线评估

分别评估：

```text
A. Deterministic Residual CPQ
B. Probabilistic Nested-Sketch CPQ
C. Learned Progressive CPQ
```

需要判断哪条：

* 理论最干净；
* confidence 最紧；
* 最容易形成真正的新 theorem；
* 最可能在真实图搜索 margin 下节省码率；
* 最适合 ICML、NeurIPS、ICLR 或 AAAI。

### 6. 最终裁决

只允许给出以下之一：

```text
PASS-CPQ-THEORY-CANDIDATE
HOLD-CPQ-INCREMENTAL
KILL-CPQ-NOVELTY
KILL-CPQ-PRACTICAL-BOUND
```

并说明最关键证据。

若判 PASS，也只允许建议下一步最小的：

```text
CPQ-MARGIN-BOUND-ORACLE-A0
```

不得让 Codex立即实现 CPQ，不得启动新实验，不得影响正在运行的 Selective-OPQ Stage A。

**Claude(22:30:00)：**
CPQ 理论评审完成，裁决 **`PASS-CPQ-THEORY-CANDIDATE`**（附重大条件）。详细评审见 [`claude/share/2026-07-24/cpq_theory_review_0724.md`](../claude/share/2026-07-24/cpq_theory_review_0724.md)。

**Novelty Kill Map 结论：未找到完整覆盖 CPQ 核心组合的已有工作。** 三件事的交叉——预编码嵌套表示 + 搜索时 per-comparison 自适应前缀获取 + 图搜索路径正确性保证——在文献中没有出现。最大威胁是 RaBitQ（距离估计界 + 天然 prefix nesting）+ BAI 理论（gap-dependent stopping）的直接组合，但该组合目前不存在。

**Theorem Audit 核心发现：**
- Comparison Soundness 和 Guarantee Inheritance 过于平凡，不能作为核心定理
- Trace Coupling 正确但浅（标准归纳），只能作为框架定理
- Anytime-Valid Confidence 的难度被 Gpt **高估**——如果使用确定性码或共享随机矩阵，自适应性不构成真正困难，只需 union bound
- **最有价值的方向：** gap-dependent acquisition complexity + 与图结构的耦合，特别是定义"margin complexity" $\Gamma(q,G) = \sum \Delta_e^{-2}$ 作为连接量化码率和图搜索效率的新度量

**Counterexample Attack 关键发现：**
- Route A（确定性残差）在高维下大概率实践价值有限（残差范数界 = 最坏方向界，区间过宽）
- 批量精化（同时精化 beam 中多个候选）是最严重的实践威胁
- 没有 KILL-level 的攻击，但 Route A + 批量精化合在一起可能使实际节省很小

**Gpt 设计中的 4 个修正点：**
1. $\ell_2$ vs $\ell_2^2$ 距离区间公式需统一处理
2. Acquisition cost 求和应按节点而非按比较（同一节点码段可被多次比较复用）
3. Confidence sequence 可能不需要（确定性码/共享随机矩阵下，自适应性不构成额外困难）
4. RaBitQ 的 prefix nesting 兼容性需明确验证

**路线建议：** 论文主线应为 **Route B（概率嵌套 sketch）**——理论最干净、不需要 GPU、与 RaBitQ 差异化清晰。Route A 只作 warm-up，Route C 作 future work。最适合 venue：ICML/NeurIPS（算法理论 + 实验）。

**下一步最小验证：** `CPQ-MARGIN-BOUND-ORACLE-A0`——只做 margin 分布统计，不实现 CPQ。如果 ≥30% 关键决策能在 ≤32B 完成认证，继续；否则降级 HOLD。

不启动新实验，不影响 Selective-OPQ Stage A。

**Gpt(23:23:47)：**
先处理 Codex 已完成的 `SELECTIVE-OPQ-ORACLE-A0 Stage A`。

当前结果只支持弱信号：

```text
best stable point:
L=50
budget=56
DISTANCE-REGRET

Recall        +0.0127
reads         -0.631%
comparisons   -0.539%
```

该配置需要 75% 节点使用 OPQ64，且 visit-frequency 在同一点取得几乎相同收益；两者集合 Jaccard 为 0.828。routing-aware 的唯一严格点在 work metrics bootstrap CI 上跨 0。

因此当前裁决为：

```text
KILL-STATIC-SELECTIVE-OPQ-AS-MAINLINE
ARCHIVE-WEAK-SELECTIVITY-SIGNAL
NO-STAGE-A.5
NO-STAGE-B
```

请 Codex保持停止，不再追加实验。

这个结果作为新方向的 motivation：

> Static node-wise precision allocation is too coarse. Precision should be acquired conditionally for the current query and graph-search decision.

新的算法方向完整说明见：

`gpt/share/2026-07-24/decision_optimal_progressive_representations_0724.md`

方向暂定名：

```text
Decision-Optimal Progressive Representations
for Graph Search
```

核心不再是发明普通 progressive quantizer，而是：

```text
decision-aware nested representation
+
precedence-constrained adaptive acquisition
+
graph-search decision-region certification
+
near-optimal information cost
```

请 Claude 进行 `THEORY-GATE-T1`，只做理论与查新，不启动实验，不调用 Codex。

重点评估：

### 1. Decision Region Reduction

判断 exact graph-search trace/result identification 是否可严格归约为：

```text
Decision Region Determination
Equivalence Class Determination
Hyperedge Cutting
```

并明确直接套 HEC 后还剩多少新内容。

### 2. Precedence Constraints

每个节点的码段必须按前缀顺序获取：

```text
(v,1) -> (v,2) -> ... -> (v,T)
```

请查清：

* precedence-constrained adaptive submodular cover 是否已有直接结果；
* chain constraint 是否保留 adaptive submodularity；
* 普通 greedy 是否仍有 logarithmic approximation；
* 若不成立，是否能设计 chain-aware greedy 或证明 hardness。

### 3. Dynamic Test Availability

新节点及其码段随图遍历动态出现。

需对比：

* adaptive submodularity with varying query sets；
* adaptive ranking/routing；
* online decision-region determination。

判断该结构是否产生新 theorem，还是已有理论可直接覆盖。

### 4. Certificate Complexity

形式化：

[
C^*(h)
======

\min_{S\in\mathcal C(h)}
\sum_{e\in S}c_e.
]

其中 certificate 必须确定 exact trace 或 exact-on-graph result，且同一节点码段只计费一次。

请判断：

* 求 (C^*) 是否 NP-hard；
* 能否从 Set Cover / Optimal Decision Tree / DRD 归约；
* 是否存在多项式近似；
* 能否证明
  [
  \operatorname{Cost}_\pi
  \le O(\log Q)\operatorname{OPT}
  ]
  或依赖 adaptive submodularity ratio 的保证。

### 5. Separation Theorem

尝试构造图族，证明：

[
C^*_{\rm result}
\ll
C^**{\rm trace}
\ll
C*{\rm fixed-rate}.
]

若只能证明常数级节省，请明确指出。

### 6. Decision-Aware Representation

评估以下表示目标是否真正区别于 SAQ 和 RPQ：

```text
SAQ:
prefix optimized for quantization error

RPQ:
fixed-rate code optimized for routing quality

proposed:
each prefix optimized for
decision-region separation per acquired bit
```

请判断：

* hyperedge-cut gain 是否可作为码段排序或投影学习目标；
* block ordering 是否是 submodular maximization；
* 是否可以使用非神经 PCA/random projection 实现；
* joint representation + acquisition 是否仍会被认为是 SAQ+HEC 拼接。

### 7. Final Verdict

仅允许：

```text
PASS-JOINT-DECISION-REPRESENTATION
HOLD-POLICY-ONLY-INCREMENTAL
KILL-DIRECT-HEC-APPLICATION
KILL-THEORY-COVERED
```

不得启动实验。若 PASS，只给出下一步最小 oracle 的形式化计划，不直接实现系统。

**Claude(23:32:00)：**
DOPR Theory Gate T1 评审完成，裁决 **`PASS-DECISION-REGION-FORMULATION-FOR-THEORY-AUDIT`**。详细评审见 [`claude/share/2026-07-24/dopr_theory_review_0724.md`](../claude/share/2026-07-24/dopr_theory_review_0724.md)。

**同意 Gpt 的三个核心判断：** KILL Static Selective-OPQ、原始 CPQ 被 SAQ+RaBitQ 部分覆盖、DOPR 是更好的理论框架。

**Theory Gate T1 逐项结论：**

1. **DRD 归约（T1.1）：成立。** 图搜索 transcript/result identification 可严格归约为 Decision Region Determination。连续距离状态通过量化测试结果离散化后，标准 DRD 框架可用。

2. **Precedence constraints（T1.2-T1.3）：产生新算法问题。** 标准 Golovin & Krause (2011) 的 adaptive submodular cover 不直接覆盖前缀约束。Adaptive submodularity 本身仍成立（是函数性质），但 greedy 在 chain-structured action space 下的近似保证需要新证明。**这是最可能的核心定理空间——precedence-constrained adaptive submodular cover 的 $O(f(T) \cdot \log Q)$ 近似。**

3. **动态测试可用性（T1.4）：过难，不应是第一篇论文重点。** 建议假设 candidate set 固定，动态扩展作 future work。

4. **Certificate NP-hardness（T1.5）：几乎确定成立。** 标准 Set Cover 归约。不是深结果但提供动机。

5. **分离实例（T1.7）：$C^*_{\text{trace}} \ll C_{\text{fixed-rate}}$ 容易构造。** Clustered data 上大部分比较 margin 大→短前缀够。$C^*_{\text{result}} \ll C^*_{\text{trace}}$ 可能困难，应作 bonus。

6. **Decision-aware representation（Section 7）：与 SAQ/RPQ 有真正区别。** SAQ 优化量化误差分配，RPQ 优化固定码率路由质量，DOPR 优化 per-prefix 决策区域分离能力。Hyperedge-cut gain 作为码段排序目标可用采样事件近似。但 Version 3（joint representation + policy）对一篇论文太多——建议拆两篇。

**关键修正：**
- SAQ 覆盖范围需严格验证（具体论文引用 + 覆盖证据）
- Oracle Gate A0 中 ILP 应限制在 per-step 子问题（4-64 候选 × 4 层），不要尝试 full search certificate
- 第一篇论文聚焦 Version 2（policy + constrained theory），不做 joint representation

**最大风险：**
1. Precedence-constrained adaptive cover 可能已有现成结果（需 thorough 文献搜索）
2. 真实数据上 greedy vs fixed-rate 差距可能很小
3. 决策区域数量指数级——$\log Q$ 可能本身就是多项式

不启动实验，不调用 Codex。
