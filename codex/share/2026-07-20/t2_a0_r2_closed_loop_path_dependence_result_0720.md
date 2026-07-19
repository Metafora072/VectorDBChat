# T2-A0-R2 闭环路径依赖实验结果

## 最终裁决

本次唯一正式 attempt `t2_a0_r2_20260720_002` 的终局结果为 `KILL-NO-CLOSED-LOOP-SEPARATION`。协议闭包、因果证据链和结果封存均通过，因此该结果不是 `FAIL-PROTOCOL-CLOSURE`。实验确实观测到临时容量下降引起的持久状态与行为分歧，也为全部 200 个 closed-loop 配对实例重建了严格的 `action -> write -> future query-token use -> descendant durable version -> restored-capacity retrieval/action/outcome divergence` 证据链；但 open-loop query 和 write-disabled 两类必要控制复现了相当或更强的行为分歧，完整闭环没有形成独立的 behavioral separation。依据预注册门禁，本路线应在 A0-R2 终止。

本裁决只针对 deterministic endogenous path dependence。它不支持 phase transition、hysteresis、nonlinear scaling 或真实 LLM agent 系统上的泛化主张，也不应表述为完全不存在路径依赖。

## 实验与闭包

正式矩阵严格固定为 2 种 replacement policy、5 个 capacity triplet、20 个 immutable workload instance 和 4 类 causal/control model，共 800 个 paired cell。每条轨迹包含 48 步共同高容量前缀、36 步分叉区间和 96 步容量恢复后 evaluation。20 个工作负载覆盖 `cyclic`、`bursty`、`interleaved` 和 `reversal` 四类 dependency-graph operator，每类 5 个实例。全部计算使用冻结的 Python 标准库实现，LLM(Large Language Model，大语言模型)、API(Application Programming Interface，应用程序编程接口)、GPU(Graphics Processing Unit，图形处理器) 和外部 agent framework 的调用次数均为 0。

全量 validator 对 211,200 条 raw row 执行 streaming transition replay，并重新计算 pair metrics 和 classifier。19 项 validation check 全部为 `true`，包括 exact universe、prefix/fork replay、byte-identical fork、四类控制约束、完整 witness、source/config/workload/raw hash、资源门禁和最终分类。800/800 个 cell 的 `fork_bytes_sha256_a`、`fork_bytes_sha256_b` 与 `fork_hash` 完全相等；200/200 个 closed-loop cell 均存在 strict descendant witness。三路独立只读审计分别确认因果判据、统计判级和 provenance closure，没有发现会将本结果改判为协议失败的问题。

## 主要结果

预注册判据要求每个 policy/triplet cell 至少有 17/20 个 qualifying instance，并要求 family-stratified paired bootstrap 的 `B` 与 `D` 两个 margin 的 95% 置信区间下界均严格大于 0。`B` 表示 action/outcome behavioral divergence，`D` 是 query/action/live-memory/outcome 的 full composite divergence。正式结果如下。

| Policy | Capacity triplet | Qualifying | `B` margin 95% 置信区间 | `D` margin 95% 置信区间 | Supported |
|---|---:|---:|---:|---:|---:|
| LRU | `(12,10,12)` | 1/20 | `[-0.005469,-0.000781]` | `[0.196354,0.216406]` | No |
| LRU | `(12,8,12)` | 2/20 | `[-0.004948,≈0-]` | `[0.237109,0.247005]` | No |
| LRU | `(12,6,12)` | 2/20 | `[-0.004167,-0.000260]` | `[0.244141,0.248568]` | No |
| LRU | `(12,4,12)` | 2/20 | `[-0.005729,-0.000521]` | `[0.243750,0.248438]` | No |
| LRU | `(12,2,12)` | 3/20 | `[-0.005990,0.000260]` | `[0.243229,0.248698]` | No |
| LFU_RECENCY | `(12,10,12)` | 1/20 | `[-0.005469,-0.000781]` | `[0.182161,0.211979]` | No |
| LFU_RECENCY | `(12,8,12)` | 2/20 | `[-0.004948,≈0-]` | `[0.227734,0.244922]` | No |
| LFU_RECENCY | `(12,6,12)` | 2/20 | `[-0.003646,0]` | `[0.230469,0.246615]` | No |
| LFU_RECENCY | `(12,4,12)` | 2/20 | `[-0.005729,-0.000260]` | `[0.229818,0.246484]` | No |
| LFU_RECENCY | `(12,2,12)` | 3/20 | `[-0.005990,0.000260]` | `[0.238542,0.247005]` | No |

10/10 个 cell 均未达到 17/20 门槛，LRU 与 LFU_RECENCY 各自支持的 triplet 数均为 0/5，共同 supported triplet 数为 0。200 个 policy/triplet/instance 组合中只有 20 个 behavioral margin 严格为正，111 个为零，69 个为负；其均值为 `-0.00268`。按任务族检查时，`bursty` 在全部 cell 中均无 qualifying instance，因此 family coverage 门禁也未通过。

## 控制组解释

四类模型的 200 个实例均值进一步说明了 kill 原因。

| Model | `Q` mean | `A` mean | `M` mean | `Y` mean | `B` mean |
|---|---:|---:|---:|---:|---:|
| closed-loop | 0.943 | 0.944 | 1.000 | 0.942 | 0.943 |
| open-loop query | 0.000 | 0.947 | 1.000 | 0.943 | 0.945 |
| write-disabled | 0.942 | 0.942 | 0.000 | 0.941 | 0.941 |
| transparent retrieval | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

Open-loop query 固定未来 query，因而 `Q=0`，但仍保留 durable-update 通道，其 `B` 均值与 closed-loop 相当且略高。Write-disabled 移除 durable write，因而 `M=0`，但 action-to-query feedback 仍产生相当的 action/outcome persistence。Transparent retrieval 的所有语义差异均为 0，说明 capacity bookkeeping 或 resize marker 本身没有泄漏为伪差异。

Closed-loop 的 `D` margin 在全部 cell 中为正，是因为它同时保留 `Q` 与 `M` 两个差异分量；这只能证明完整闭环中存在更丰富的复合状态差异，不能替代行为指标 `B` 的对照分离。预注册门禁明确要求 `B` 和 `D` 同时胜过最强控制，因此正的 `D` 不能将结果改判为 PASS。

允许保留的最强结论是：在该确定性状态机中，临时容量下降能够形成真实的 action-to-write-to-future-query 因果链，并在容量恢复后留下持久分歧；然而该行为持久性不依赖完整闭环，open-loop durable-update 通道或无 durable write 的 action-to-query 通道均能复现，因此没有证据支持完整闭环产生独特或更强的 endogenous path dependence。

## 资源与证据封存

实验于 2026-07-20 01:45:56 UTC+8 完成。正式运行耗时 397.20 秒，全量复验耗时 396.79 秒，attempt 累计墙钟 798.92 秒，约 13 分 19 秒，低于 7,200 秒硬上限。最高 RSS(Resident Set Size，常驻内存集) 为 69,931,008 B，约 66.7 MiB，低于 1 GiB。最终目录实际分配 141,561,856 B，约 135.0 MiB，低于 256 MiB。所有产物位于 `/home/ubuntu/pz/VectorDB/data` 对应的独立 NVMe(Non-Volatile Memory Express，非易失性存储器快速协议) 卷 `/dev/nvme8n1`，未占用系统盘执行正式实验。

关键 SHA-256 如下。

| Artifact | SHA-256 |
|---|---|
| Authorizing gate | `9609d439fa202653fd50b37cbf19a9be44c4e8c8bbb61bc7b70199affd8d9682` |
| Frozen source | `435441698069f24b34255851f64e4e97f11ec46b9245b010496179328a6ff87b` |
| Config | `9b9f7dda414fa79fb31a1e4f349491370ee6f8a24381525142b7a8cb574ef969` |
| Formal raw | `76e16e68b430d882ac4f0776b3f8ff02f251336c6bd0c157945347f4313c987f` |
| Formal pairs | `4225b9ccd575e1ca16e17b23ad668d92376a6493bd48ad68a53b4f9a43b1547a` |
| Formal validation | `8ec23295d03f67e9f57ffbed611f6f5169910fa22942be6fd19fbf2c9d368498` |
| Postrun manifest | `4adaeca1bd2a1496ad5240dc7fcdaae36b0e0b886ecd3ea1fab5382511f4c668` |

原始封存目录为 `/home/ubuntu/pz/VectorDB/data/agent_infra/t2_a0_r2/t2_a0_r2_20260720_002`。Frozen `inspect` 已重新核对 postrun manifest 中的全部文件、哈希和三处 outcome seal，未发现缺失、篡改或分类不一致。

## 停止条件与后续路由

本轮已满足 GPT gate 的 A0-R2 终止条件。T1 保持永久停止，T2 不进入 A1，不安装 agent framework，不调用 LLM/API，也不追加容量点、工作负载或自动重跑。后续仅将本报告提交 Gpt 审阅；除非获得新的显式裁决，否则不启动下一项实验或 idea-discovery round。
