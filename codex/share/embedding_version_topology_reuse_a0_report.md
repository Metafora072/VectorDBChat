# 跨 Embedding 版本拓扑复用：A0 Finding Gate 报告

日期：2026-07-12

## 最终裁决

**KILL。** A0 在 100K topology reuse window 阶段触发停止条件，没有进入 seeded refinement、1M scaling 或 architecture review。

两个独立的真实模型版本迁移都显示：embedding 空间的 exact kNN 邻居可以发生明显变化，但旧 Vamana topology 在新坐标上的 ANN 搜索质量仍与 fresh-new Vamana 基本相同。因此当前证据不支持“模型升级后旧图明显失效、需要 warm-start repair”这一前提。

- MiniLM-L6 v1→v2：exact kNN@10 overlap 为 73.81%，但 old topology 与 fresh 的 Recall@10 差异在全部搜索预算上均小于 0.28 个百分点，paired 95% CI 均包含 0。
- E5-small v1→v2：exact kNN@10 overlap 已降至 56.35%，@64 仅 47.23%，但 old topology 与 fresh 的 Recall@10 差异仍在全部搜索预算上小于 0.46 个百分点，paired 95% CI 均包含 0。
- 两组 old topology 都远好于与数据空间无关的 random topology，说明旧图确实保留结构信息；但它们又都已接近 fresh，属于“无需修复”，不是门禁要求的中间 reuse window。

预注册条件要求至少两组真实 transition 同时满足“旧图明显失效但仍优于普通初始化”。前两组均不满足；即使第三组 BGE 通过，也最多只有一组，因此逻辑上已不可能通过 A0。脚本在 BGE-old 编码开始后的第 5/782 batch 被主动停止，遵守“不得为了完成流程越过前一阶段 Kill”。

## 实验边界

本轮只回答：真实模型升级后，旧 topology 是否普遍处于“需要修复但值得复用”的中间状态。

没有执行：

- seeded NN-Descent 或 continuous refinement；
- drift detector、局部 re-prune 或 new-candidate discovery；
- DGAI serving 修改；
- 1M scaling；
- synthetic noise/rotation sensitivity。

所以本报告不能判断某个 repair 算法是否有效；它判断的是当前问题前提没有通过最低 finding gate。

## 数据与模型 inventory

### 数据

| 数据 | 来源 | 原始规模 | 固定样本 | Query | ID 复现哈希 |
|---|---|---:|---:|---:|---|
| Quora Retrieval | [`mteb/quora`](https://huggingface.co/datasets/mteb/quora) | 522,931 | 100,000 | 2,000/15,000 | corpus `0692a61f…12d2`；query `13256fc6…6109` |
| NQ top-50 subset | [`mteb/nq_top_50_only`](https://huggingface.co/datasets/mteb/nq_top_50_only) | 154,171 | 100,000 | 2,000/3,452 | corpus `95486962…454`；query `c7e61b4f…5530` |

抽样固定为 seed `20260712` 下 `BLAKE2b(seed:item_id)` 最小的 100K corpus IDs；query 使用 seed+1 的同一规则。old/new 两侧读取完全相同的 JSONL 和 ID 顺序。完整哈希与来源规模在 NVMe 的 `datasets/formal_100k/*/manifest.json`。

### 尝试过的 transitions

| Transition | Corpus | 模型 revision | 维度 | 状态 |
|---|---|---|---:|---|
| MiniLM-L6 v1→v2 | Quora | old `d8ccfb53…`; new `1110a243…` | 384→384 | 完成 100K A0-1 |
| E5-small→E5-small-v2 | NQ | old `e272f304…`; new `ffb93f3b…` | 384→384 | 完成 100K A0-1 |
| BGE-small-en→v1.5 | NQ | old 已下载 `2275a7bd…`; new 未下载 | 384→384 | old 编码 5/782 batch 时因 A0 已不可能通过而停止；无 partial fbin |

MiniLM 不加 prefix；E5 对 corpus/query 分别使用官方 `passage: ` / `query: `；BGE 计划对 query 使用官方 retrieval instruction。所有完成的 embeddings 均为 float32、L2-normalized，模型原生最大长度未修改。

## 实现与 sanity

执行器位于 `codex/work/a0_topology_reuse/`：

- `a0_pipeline.py`：确定性数据抽样、模型编码、FAISS exact kNN、DiskANN truthset、graph parser、可达性/edge retention、paired recall CI 与搜索日志解析。
- `run_sanity.sh`：2K MiniLM 端到端 sanity。
- `run_a0_1_100k.sh`：预注册的三 transition 100K A0-1；在命中 Kill 后人工中断第三组。

sanity 验证了关键语义：用官方 DiskANN `build_memory_index` 得到 old/new/random Vamana；用 `create_disk_layout(new_coordinates, old_graph)` 构造真正的 old-topology + new-coordinates hybrid index；三种 index 共用由新坐标训练的 PQ，避免错误地用旧 PQ 距离导航。

2K MiniLM sanity 的 old/fresh 在 L=80 时 Recall@10 均为 97.3%，random topology 为 47.6%，说明 hybrid 不是误读旧向量或错误 ground truth。

## Exact topology overlap

### MiniLM v1→v2，Quora 100K

| 指标 | Mean | 95% CI | P05 | P50 | P95 |
|---|---:|---:|---:|---:|---:|
| exact kNN overlap@10 | 73.81% | [73.72%, 73.90%] | 50.0% | 80.0% | 90.0% |
| exact kNN overlap@32 | 73.89% | [73.82%, 73.96%] | 53.1% | 75.0% | 90.6% |
| exact kNN overlap@64 | 73.65% | [73.59%, 73.71%] | 54.7% | 75.0% | 87.5% |

旧 Vamana edge 落入新空间 exact-kNN@64 的节点级平均比例为 59.27%；fresh-new 为 70.43%；random 为 0.065%。三图从各自入口均 100% 有向可达。

### E5-small v1→v2，NQ 100K

| 指标 | Mean | 95% CI | P05 | P50 | P95 |
|---|---:|---:|---:|---:|---:|
| exact kNN overlap@10 | 56.35% | [56.21%, 56.50%] | 10.0% | 60.0% | 90.0% |
| exact kNN overlap@32 | 51.96% | [51.83%, 52.09%] | 15.6% | 53.1% | 84.4% |
| exact kNN overlap@64 | 47.23% | [47.12%, 47.34%] | 17.2% | 48.4% | 75.0% |

旧 Vamana edge retention@64 为 38.87%；fresh-new 为 69.90%；random 为 0.064%。从入口的有向可达率分别为 old 99.904%、fresh 99.945%、random 100%；极少不可达点未被隐去。

## Old topology/no-repair 与 fresh graph

共同配置：官方 DiskANN Vamana，`R=32, Lbuild=64`，56 build threads；新坐标 PQ 32 bytes/vector；2K new-model queries；Recall@10 exact ground truth；search `beamwidth=2`，L 扫描 10/20/40/80/120/160。性能运行三次，recall CI 使用 query-level paired difference，不把重复运行当作独立样本。

### MiniLM Recall–I/O

| L | Fresh recall | Old recall | Random recall | Old−Fresh 95% CI | Fresh I/O | Old I/O |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 71.91% | 71.82% | 0.52% | [-0.72, +0.55] pp | 18.56 | 19.38 |
| 20 | 88.34% | 88.07% | 0.85% | [-0.76, +0.21] pp | 27.87 | 28.80 |
| 40 | 95.61% | 95.55% | 1.58% | [-0.35, +0.25] pp | 47.10 | 48.00 |
| 80 | 98.45% | 98.38% | 3.02% | [-0.27, +0.13] pp | 86.22 | 87.09 |
| 120 | 99.13% | 99.05% | 4.50% | [-0.21, +0.05] pp | 125.83 | 126.63 |
| 160 | 99.40% | 99.35% | 5.69% | [-0.18, +0.08] pp | 165.47 | 166.28 |

### E5 Recall–I/O

| L | Fresh recall | Old recall | Random recall | Old−Fresh 95% CI | Fresh I/O | Old I/O |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 61.29% | 61.02% | 0.52% | [-1.34, +0.79] pp | 20.69 | 21.64 |
| 20 | 80.09% | 79.63% | 0.87% | [-1.30, +0.39] pp | 30.65 | 31.47 |
| 40 | 89.59% | 89.70% | 1.57% | [-0.45, +0.68] pp | 49.87 | 50.77 |
| 80 | 93.92% | 93.89% | 2.97% | [-0.44, +0.37] pp | 88.75 | 89.59 |
| 120 | 95.63% | 95.34% | 4.33% | [-0.58, +0.01] pp | 127.88 | 128.76 |
| 160 | 96.39% | 96.20% | 5.76% | [-0.46, +0.08] pp | 167.39 | 168.27 |

两组 old topology 的平均 I/O 仅比 fresh 多约 0.8–1.0 reads/query；没有为了达到相同 recall 而出现数量级或稳定显著的 search-cost 退化。三次 latency 均值中 old 通常较慢，但幅度不稳定，MiniLM L=160 甚至反向；在 recall 与 I/O 几乎相同的情况下，这不足以证明 topology repair 的必要性。

## 成本账与 strong baseline

| Transition | Old encode | New encode | Old exact kNN | New exact kNN | Fresh-new Vamana build | Old Vamana build | Peak build DRAM |
|---|---:|---:|---:|---:|---:|---:|---:|
| MiniLM | 46.4 s | 47.6 s | 405.8 s | 327.1 s | 2.43 s | 2.50 s | 180 MiB |
| E5 | 703.0 s | 712.3 s | 330.6 s | 335.2 s | 2.23 s | 2.52 s | 180 MiB |

Strong fresh baseline 是同一官方 DiskANN 版本、相同 R/L/线程/坐标精度构建的 fresh-new Vamana，不是削弱的近似 baseline。PQ carrier 为相同新坐标生成，耗时 MiniLM 153.5 s、E5 148.9 s，peak RSS 约 622–624 MiB；该公共 search artifact 不影响 fresh/old topology 的相对 recall。

seeded refinement 总成本账为 **N/A**：A0-1 已 Kill，按计划不允许启动 A0-2。1M 一致性同样为 **N/A**。

## Kill 原因

命中两个预注册停止条件：

1. **旧图无需修复。** 两组 transition 的 old topology 在完整 Recall–I/O 曲线上都已接近 fresh；即便 E5 exact kNN@64 只保留 47.23%，Vamana 导航仍没有明显退化。
2. **已不可能有至少两组 reuse window。** 三组预注册 transition 中前两组均失败，剩余一组无论结果如何都无法满足“至少两组独立真实 transition”的继续条件。

这也暴露出一个重要事实：**exact kNN overlap 或 edge retention 不能直接预测 Vamana search topology 是否失效。** RobustPrune 图包含的长程导航边和多路径冗余，使 exact local-neighbor churn 不必转化为 ANN recall 下降。

因此不应继续把“跨 embedding 版本 warm-start graph repair”作为当前系统方向，也不应设计 drift detector 来定位一个尚未表现为服务质量问题的变化。若未来有真实 production checkpoint 明确显示 old graph 的 Recall–I/O 曲线显著退化，应作为新证据重新开题，而不是从本轮模型对强行外推。

## 复现与存储

```bash
cd /home/ubuntu/pz/VectorDB/chat
./codex/work/a0_topology_reuse/run_sanity.sh
./codex/work/a0_topology_reuse/run_a0_1_100k.sh
```

第二条命令原计划含三组 transition。当前脚本已把停止逻辑固化：若 `old−fresh` 的 paired 95% CI 未在至少两个搜索预算上严格低于 0，则该 transition 不算 reuse window；当剩余 transition 数已不足以累计两个 window 时，以 exit code 20 停止。因此复现本报告时会在 E5 结果后自动结束。

原始 embeddings、exact neighbors、Vamana/PQ indexes、搜索结果和日志位于：

`/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse/`

总占用约 6.0 GiB，全部位于项目 NVMe。实验前后系统盘均为 46%；没有使用系统盘保存模型、raw data、索引、临时文件或 core dump。
