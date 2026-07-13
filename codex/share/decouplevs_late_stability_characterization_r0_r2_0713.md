# DecoupleVS Late-Stability Residual Characterization

## 摘要与裁决

本轮按照 `gpt/share/decouplevs_residual_characterization_gate_0713.md` 的 R0→R1→R2 顺序，构建并评估了 `DecoupleSearch-R`。该实现是对 DecoupleVS 第 3.4 节 latency-aware search 的部分复现，不是官方 DecoupleVS artifact，也不包含压缩、缓存、更新与垃圾回收路径。

实验确认了现象层面的 residual。高召回配置需要较大的 rerank batch，导致 fixed-B stability trigger 几乎消失，并留下约 0.52–1.17 ms 的 exposed vector-fetch tail。以 `L=100, B=80` 为例，`W=4/8/16` 的触发率分别只有 0.40%/0.50%/0.40%。真正的 earliest-safe position 平均位于 traversal 的 79.9%/81.2%/83.5%，明显早于 fixed-B 的近 100%。

但实验不支持进入 `Continuous Dual-Frontier Search` 设计。query difficulty 与 stability/tail 的关系较弱，per-query 最优 `B` 在四个 difficulty 分位上没有稳定迁移。更重要的是，R2 的 earliest-safe oracle 在 `W=8/16` 仅改善平均延迟 9.46%/5.31%，而不使用最终候选信息、只采用固定 workload-level vector quota 已经能改善 8.30%/3.76%。oracle 相对简单固定调参只剩约 1–1.5 个百分点的平均延迟空间，未形成 fixed tuning 无法达到的新 latency–I/O–recall Pareto 点。

因此，本轮裁决为：**保留 late-stability 与 exposed-tail characterization finding，关闭 query-adaptive continuous dual-frontier 设计动机。** 第二数据集不再运行，因为第一个数据集已经不满足进入设计所需的 difficulty relationship 与新 Pareto 条件。若未来转向描述性的并发调优工作，才需要使用第二数据集和官方 DecoupleVS artifact 验证外部有效性。

## 实验范围与有效口径

### 实现范围

`DecoupleSearch-R` 从同一个 Vamana 索引导出独立 graph 与 vector files。Graph traversal 只读取邻接记录，PQ(Product Quantization，乘积量化) code 常驻内存，vector file 仅在 rerank 或 prefetch 时读取。Graph 与 vector 均通过 PipeANN 的 Linux `io_uring` backend 和 `O_DIRECT` 访问。

实现包含 `naive`、`fixed`、`oracle_final`、`oracle_safe` 与 `oracle_bw` 五种模式。`fixed` 在 `K+B` candidate pool 填满后，使用连续 `B` 次展开无 top-`K+B` 替换作为稳定条件，并只使用 traversal 未占用的队列槽发起 vector prefetch。`oracle_final` 知道最终 rerank 集合，在候选首次进入 frontier 后发起读取；`oracle_safe` 知道最终集合不会再变化的最早 logical beam round，但仍采用 graph-first spare-width 规则；`oracle_bw` 不知道最终集合，也不提前稳定触发，只在 fixed-B 触发后改变 graph/vector 队列配额。

为了使 oracle replay 与 baseline 具有同一个逻辑搜索，最终实现采用确定性的 PipeANN-style logical beam round。每轮先固定最多 `W` 个待展开候选，底层 I/O 保持异步，但只有本轮 graph pages 就绪后才按固定顺序展开。最终 R2 中 `oracle_final` 与 `oracle_safe` 的 offline final set 和 replay final set 匹配率均为 100%。采用异步完成顺序直接驱动 frontier 的早期数据批次匹配率只有 79%–96%，已明确排除，不用于任何结论。

### 非目标

本轮未实现 Elias–Fano graph compression、XOR-delta/Huffman vector compression、LRU cache、adaptive benefit termination、segment GC、batch update、page layout 或完整 dual-frontier scheduler。结果不能表述为官方 DecoupleVS 绝对性能复现，也不能外推到其 compression、cache 与 update 路径。

## 环境与数据

实验主机运行 Linux `6.8.0`，PipeANN 基线提交为 `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`。构建显式启用 `PIPEANN_FORCE_URING=ON`，关闭 `USE_TCMALLOC`。索引、导出 layout、构建目录与原始结果全部位于挂载在 `/home/ubuntu/pz/VectorDB/data` 的 Samsung SSD 990 PRO 2TB 项目 NVMe 上；系统盘未用于保存大规模实验产物。

主数据集为 SIFT-900K，向量维数为 128，Vamana degree 为 64。Graph record 为 260 B，每个 4 KiB page 容纳 15 个节点；vector record 为 512 B，每页容纳 8 个向量。查询使用 `K=10`，每个正式配置运行 1,000 个查询并丢弃前 5 个查询，保留 995 个样本。R0 matched comparison 使用三个重复，且交替 naive/fixed 运行顺序。

所有结果采用 cold per-query page map 与 `O_DIRECT`。报告中的 p95/p99 是 995 个 query-level latency 样本的经验分位数，未将其表述为跨主机置信区间。

## R0 正确性检查

R0 的目标是确认 phase separation 在同 recall 下能够减少 traversal 关键路径中的 vector reads，并相对 naive decoupling 恢复性能。

| `W` | Fixed recall | Naive recall | Fixed mean | Naive mean | Mean change | Fixed vector pages | Naive vector pages | 结论 |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 4 | 0.90774 | 0.90824 | 4.353 ms | 4.325 ms | +0.6% | 89.6 | 111.3 | 打平，末尾读取抵消 I/O 减少 |
| 8 | 0.90764 | 0.90804 | 3.356 ms | 3.998 ms | -16.1% | 89.6 | 122.1 | 通过 |
| 16 | 0.90794 | 0.90814 | 3.209 ms | 3.619 ms | -11.3% | 89.6 | 145.0 | 通过 |

每个表项为三个 matched repeats 的均值。`W=8/16` 重现了 gate 要求的定性关系。Fixed 模式把 vector pages 固定在最终 rerank 集合约 89.6 页，而 naive 模式随 beam width 增加到 122.1 和 145.0 页，平均延迟分别降低约 16% 和 11%。`W=4` 是一个明确边界，队列宽度不足以同时隐藏 graph 与 vector latency，fixed 模式约 1.17 ms 的 exposed tail 抵消了减少的 vector I/O。

R0 因而判定通过，但只支持定性正确性，不支持官方系统绝对性能复现。

## R1 Late-Stability Characterization

### Recall 与 B 的权衡

下表给出 `L=100, W=4` 的代表性扫描。

| `B` | Recall | Mean | p95 | p99 | Trigger rate | Mean stability position | Mean exposed tail | Mean vector pages |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.85015 | 3.143 ms | 3.961 ms | 4.130 ms | 100.0% | 0.381 | 0.004 ms | 20.1 |
| 20 | 0.89256 | 3.084 ms | 3.315 ms | 3.478 ms | 99.5% | 0.587 | 0.066 ms | 29.9 |
| 40 | 0.91417 | 3.566 ms | 3.769 ms | 3.854 ms | 53.6% | 0.906 | 0.573 ms | 49.9 |
| 80 | 0.91819 | 4.175 ms | 4.342 ms | 4.430 ms | 0.4% | 1.000 | 1.165 ms | 89.7 |

Recall 从 0.850 提高到 0.918 时，fixed-B trigger 从每个查询都发生退化为几乎从不发生，exposed tail 从约 4 µs 增至 1.165 ms。这支持高质量点存在 late-stability 与 exposed-tail residual。

该 residual 不是简单增加 `L` 就能消除。较大的 `L` 增加稳定触发机会，但同时增加 graph I/O 与 traversal latency。增加 `W` 可以缩短 exposed tail，例如 `B=80` 在 `W=8/16` 的 mean tail 分别约为 0.654/0.521 ms，但 fixed-B trigger 仍只有约 0.5%/0.4%。

### Query difficulty 关系

Difficulty 使用 baseline 的 graph I/O、discovered candidates、heap replacements 与 total latency 的 rank average 定义，不使用人工标签。Spearman 相关系数如下。

| 关系 | Spearman ρ |
|---|---:|
| Difficulty 与 `B=40` stability position | 0.218 |
| Difficulty 与 `B=40` exposed tail | 0.211 |
| Difficulty 与 `B=80` exposed tail | 0.118 |

这些相关性方向为正但强度较弱，不能支持可预测的 per-query adaptive trigger。使用一个宽松的 offline selector，在每个查询上选择满足 recall 不低于该查询 `B=80` 结果的最快 `B`，995 个查询的选择为 `B=10/20/40/80` 各 355/440/158/42 个。四个 difficulty quartile 中，`B=10/20` 均占主导，没有出现困难查询系统性转向更小或更大 `B` 的单调模式。

R1 因此支持 residual 存在，但不支持 residual 与 difficulty 之间存在足够强的可利用关系。

## R2 三个互斥上界

### Oracle 定义与正确性

Oracle A 只改变候选知识，在最终候选第一次进入 frontier 时用一个 vector slot 预取。Oracle B 只改变稳定时机，在离线 earliest-safe round 后使用 graph-first spare-width prefetch。Oracle C 不使用最终候选或 earliest-safe 信息，保留 fixed-B trigger，只扫描固定 vector quota 并用 per-query offline selector 给出配额上界。

所有 Oracle A/B 配置的 final-set match rate 均为 100%，recall delta、graph I/O delta 与 vector I/O delta 均为 0。因而延迟变化来自调度时机和队列竞争，而不是质量或 I/O 数量变化。

### 结果

| `W` | Fixed mean/p95/p99 | Oracle A mean/p99 change | Oracle B mean/p99 change | Best fixed quota mean/p99 change | Per-query quota oracle mean/p99 change |
|---:|---:|---:|---:|---:|---:|
| 4 | 4.175/4.342/4.430 ms | +12.0%/+82.4% | +4.2%/+121.3% | `Q=2`: -8.7%/-6.1% | -9.0%/-9.0% |
| 8 | 3.276/3.439/3.547 ms | -3.1%/-4.7% | -9.5%/-9.7% | `Q=8`: -8.3%/-7.7% | -8.6%/-7.9% |
| 16 | 3.213/3.442/3.552 ms | -4.1%/-4.4% | -5.3%/-5.4% | `Q=1`: -3.8%/-1.7% | -4.4%/-4.4% |

Oracle A 在 `W=4` 将 vector reads 提前后严重竞争 graph slots，虽然 mean tail 减少约 52%，但 traversal 被拖慢，p99 反而增加 82%。在 `W=8/16`，Oracle A 只获得约 3%–4% 改善。这说明完美候选识别本身不足以形成强上界，队列竞争是直接约束。

Oracle B 证明 fixed-B stability 确实比真正稳定点晚约 16%–20% 的 traversal，但 graph-first spare-width 规则限制了可利用窗口。`W=8/16` 的 mean 改善为 9.5%/5.3%，`W=4` 则因队列不足出现明显 tail amplification。该结果不支持只替换 stability signal 就能获得大幅稳定收益。

Oracle C 是最关键的鉴别结果。`W=4` 使用固定 `Q=2` 已达到 8.7% mean 改善，而 per-query quota oracle 为 9.0%；`W=8` 的固定 `Q=8` 为 8.3%，per-query oracle 为 8.6%；`W=16` 的固定 `Q=1` 为 3.8%，per-query oracle 为 4.4%。因此几乎全部可回收空间都能由 workload-level fixed quota 覆盖，不需要 per-query continuous scheduler。

## Result-to-Claim 审核

独立 reviewer 对预期 claim 给出 `claim_supported=partial`、`confidence=high`。Partial 仅指现象层面得到支持，即高召回下 fixed-B late stability 失效并暴露 vector tail；方法层面的核心 claim 未得到支持。Reviewer 明确认为现有结果不支持 difficulty-dependent residual、不支持 fixed parameters 无法覆盖 residual，也不支持 continuous dual-frontier scheduling 形成新 Pareto。

审核后的安全 claim 为：

> 在该 PipeANN/io_uring 部分复现中，高召回搜索会使 fixed-B late-stability 失效并暴露向量尾部，但该尾部主要可通过简单的 workload-level 向量并发配额缓解，尚无证据表明需要按查询自适应的 continuous dual-frontier scheduler。

## 有效性威胁

第一，实验只有 SIFT-900K。该限制意味着现象不能推广到不同维度、分布或设备，但由于当前数据已经否定进入设计所需的核心机制关系，未继续第二数据集符合 gate 的早停逻辑。

第二，`DecoupleSearch-R` 是部分复现。缺少官方 artifact 和 compression、cache、adaptive benefit termination、update path，不能将本结论外推为完整 DecoupleVS 的系统结论。

第三，延迟受主机状态和 NVMe 调度影响。R0 使用三个交替顺序的 matched repeats，R1/R2 使用逐 query 样本与 p95/p99，但没有跨机器重复。结论主要依赖 recall、I/O 数量、trigger/stability position 与 oracle 相对关系，而不是单一绝对延迟。

第四，确定性 logical beam rounds 是 oracle 正确性所需的控制变量。它保持异步 `io_uring` I/O，但可能与官方 DecoupleVS 的具体 frontier 更新细节不同。

## 最终停止条件

本轮在 R2 后停止，不实现 cache、compression、page layout、update mechanism 或 complete dual-frontier system，也不运行 GIST 第二数据集。停止原因不是 residual 不存在，而是 residual 缺少强 difficulty relationship，且 oracle 上界几乎被简单固定配额覆盖。

后续只有两种合法路径。若保留描述性工作，应将题目收窄为 decoupled graph search 的 high-recall tail characterization 与 workload-level queue tuning，并在第二数据集、不同 NVMe 和官方 DecoupleVS artifact 上验证。若目标仍是独立系统贡献，应转向新的、由数据固定的 residual，不能把本轮结果包装为 continuous dual-frontier design motivation。

## 复现材料

可复现源文件和脚本位于 `codex/work/decouplevs_gate/`。正式使用的数据目录为：

| 内容 | 路径 |
|---|---|
| Graph/vector layout | `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/layout/` |
| Deterministic PipeANN worktree | `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/src/PipeANN/` |
| Build | `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/build/PipeANN-uring/` |
| R0 final results | `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/results/r0_batched/` 与 `r0_batched_widths/` |
| R1 final results | `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/results/r1_batched/` |
| R2 final results | `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/results/r2_batched/` |
| Final analysis | `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/results/analysis_batched/` |

`results/r2/`、`results/r2_exclusive/`、`results/analysis/` 与早期非 batched 目录只保留审计用途，不能用于最终结论。
