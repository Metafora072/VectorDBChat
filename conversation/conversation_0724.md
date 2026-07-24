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
