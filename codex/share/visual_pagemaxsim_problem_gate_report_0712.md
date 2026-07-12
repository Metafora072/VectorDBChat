# Visual PageMaxSim P0–P2 Problem Gate Report

**日期**：2026-07-12

**执行者**：Codex

**上游 gate**：`gpt/share/visual_pagemaxsim_problem_gate_0712.md`

**最终裁决**：**KILL at P2；不进入 P3 SSD replay，不实现 PageMaxSim 系统**

## 1. 执行结论

本轮严格按 P0 → P1 → P2 的早停顺序执行，没有因为先验倾向跳过强表示、量化或 Col-Bandit baseline。

- **P0 通过**：官方 ColQwen2 每页实测中位 755 个 128D token。Light-style factor-9 semantic merging 后，每对象仍占 6 个 4 KiB 页（FP16）或 3 页（per-token int8）；32 个真实第一阶段候选对应中位 191/95 页，尚未塌缩成普遍单页对象。
- **P1 通过 problem oracle**：物理 page coupling 真实存在。以 factor-9 int8 为例，Col-Bandit `alpha=0.2` 只揭示 72.7% cells，但普通连续布局仍读 100% 的 95.1 页；预知 maxima 的 page oracle 可降至 80.9 页。raw int8 的 page oracle 更可从 792.6 页降至 181.8 页。page oracle 因而形成了表示层 baseline 之外的理论 Pareto 点，不能在 P1 Kill。
- **P2 明确 Kill**：centroid-radius 安全界无法兑现上述空间。18 个 `representation × layout × schedule` 配置中，feasible policy 读取 **99.92%–100%** 页面；raw int8 与 factor-9 int8 的全部配置均为 100%。与此同时 synopsis 额外占数据 bytes 的 7.0%–7.3%，active-batch greedy 调度还分别增加约 43.7/20.7/2.5 ms 的 bound/scheduler CPU（raw FP16/raw int8/factor-9 int8）。

因此，否定 PageMaxSim 的不是“已有工作有相似组件”，也不是人为百分比门槛，而是最小可行安全机制在真实 embedding 上几乎一页都跳不过。继续进入 P3 只会验证“读了全部页再多付 synopsis 与调度开销”，违反 gate。

## 2. 数据、模型与可复现边界

### 2.1 固定输入

| 项目 | 固定值 |
|---|---|
| Dataset | `vidore/docvqa_test_subsampled`，revision `49bf8f13e13c41dd8cdb0cae5314e31c1da1e0d6`，MIT |
| Encoder | `vidore/colqwen2-v1.0-hf`，revision `0d3e414967fde994dd99a0ccc29bcb34b5355712`，Apache-2.0 |
| 样本 | 64 个去重真实 DocVQA 页面，16 个对应真实问题 |
| 候选 | normalized mean-vector top-32；若正例不在 top-32，用正例替换最后一项 |
| Query tokens | 18–31，实测均值约 23.2 |
| Document tokens | 557–767，中位 755 |
| Seed | `20260712` |
| Page | 4096 B，object 起点与 direct-I/O page 对齐 |
| 机器 | 112 logical CPUs；无 GPU；ColQwen2 BF16 CPU batch=4 |

候选不是随机文档：它们由同一真实 corpus 上的单向量粗排产生，并保留真实 qrel 正例。离线编码耗时约 8 秒/page；这只属于数据准备，不计入 serving。

公开检查未发现 Light-ColPali/ColQwen2 的可下载权重或官方代码仓库，因此本轮按论文 Section 5.1 实现 training-free、cosine average-linkage hierarchical semantic clustering。报告将其称为 **Light-style post-hoc merging**，不冒充论文中约 72 A100-hour fine-tuned Light 模型。论文报告 factor 9 的 training-free relative effectiveness 约 97.5%，fine-tuned 最终配置在 11.8% footprint 保留 98.2% NDCG@5；它构成比本 pilot 更强的表示威胁，而不是 PageMaxSim 的有利假设。

### 2.2 数据盘纪律

所有模型、环境、HF/PIP cache、Parquet、embedding、对象文件、PDF 和结果共 **6.8 GiB**，只位于：

```text
/home/ubuntu/pz/VectorDB/data/pagemaxsim_gate
```

系统盘实验前后均为 46%；项目 NVMe 为 14%，剩余约 1.5 TiB。没有在系统盘运行或缓存实验。

代码与精确命令见 `codex/work/visual_pagemaxsim_gate/README.md`。原始表位于数据盘：

```text
results/p0_p1/p0_object_footprints.csv
results/p0_p1/p0_representation_summary.csv
results/p0_p1/p1_oracles.csv
results/p2/p2_detail.csv
results/p2/p2_summary.csv
```

## 3. 真实序列化格式

每个对象独立 page-aligned；第 0 页含 64 B object header，后续页各含 16 B page header。token row 不允许跨页。FP16 row 为 256 B；int8 row 为 `128 B codes + 2 B fp16 scale`。所有表中 page 数来自实际写出的 `.bin` 文件 `st_size / 4096`，不是 token 数乘 bit width。

| Representation | 中位 token | 中位 logical B | continuation header B | quant metadata B | alignment/padding B | 实际 B | 页 |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw FP16 | 755 | 194,144 | 800 | 0 | 14,752 | 208,896 | 51 |
| raw int8 | 755 | 98,598 | 384 | 1,510 | 3,802 | 102,400 | 25 |
| Light-style f9 FP16 | 84 | 21,648 | 80 | 0 | 2,928 | 24,576 | 6 |
| Light-style f9 int8 | 84 | 11,016 | 32 | 168 | 1,272 | 12,288 | 3 |
| Light-style f49 FP16 | 16 | 4,176 | 16 | 0 | 4,016 | 8,192 | 2 |
| single FP16 | 1 | 320 | 0 | 0 | 3,776 | 4,096 | 1 |

int8 使用逐 token 对称量化，并在评分前反量化、重新归一化。raw int8 相对 raw FP16 的 top-5 set overlap 为 98.75%，说明量化是实质强 baseline，而非只用于压 footprint 的失真点。

## 4. P0：Representation 与 Page Footprint

| Representation | 对象 pages P50/P95 | 候选 pages P50/P95 | Top-5 overlap vs raw | 真实候选内 MRR | MaxSim CPU ms/query | page break-even µs |
|---|---:|---:|---:|---:|---:|---:|
| raw FP16 | 51/51 | 1,613/1,618 | 1.000 | 0.906 | 0.992 | 0.615 |
| raw int8 | 25/25 | 792/795 | 0.988 | 0.906 | 0.982 | 1.240 |
| Light-style f9 FP16 | 6/6 | 191/191 | 0.688 | 0.854 | 0.425 | 2.226 |
| Light-style f9 int8 | 3/3 | 95/95 | 0.688 | 0.854 | 0.425 | 4.470 |
| Light-style f49 FP16 | 2/2 | 62/63 | 0.513 | 0.830 | 0.210 | 3.391 |
| single FP16 | 1/1 | 32/32 | 0.338 | 0.644 | 0.105 | 3.278 |

`page break-even` 是 `CPU MaxSim time / candidate pages`，不假设任意 SSD latency，也没有偷跑 P3。例如 factor-9 int8 只要每个 page touch 的端到端代价超过约 4.47 µs，page path 就与本轮 NumPy MaxSim CPU 同量级。这个量只说明 I/O 不可在 P0 忽略，不是端到端性能声称。

本 pilot 的 top-5 overlap 不是论文 NDCG，且小样本 post-hoc merging 未经过 Light fine-tuning，不能用于否定 Light 的公开质量结果。P0 的有效结论只依赖真实 footprint：factor-9 即使再叠加 int8，仍有中位 3 页，故按 gate 进入 P1。

## 5. P1：Interaction 与 Physical Page Coupling

### 5.1 三种 interaction policy

1. **Deterministic interaction oracle**：预知 exhaustive matrix/top-k；在每个 cell 的合法支持 `[-1,1]` 下枚举分割阈值。top-k 文档优先揭示最高 cell 以抬升 lower bound，非 top-k 文档优先揭示最低 cell 以压低 upper bound。这给出该确定性 certificate model 下的最少 reveals。
2. **Col-Bandit deployed**：按论文 Algorithm 1/Eq. 7–8 实现 `alpha=0.2, B=4, M=5, delta=0.01`，共享固定 query-token permutation，survivors 完整重算。
3. **Col-Bandit certificate corner**：相同算法，`alpha=1.0`。

P1 的 page oracle 对每个 revealed cell 预知真正 maximizing document token，并读取 maxima 所在页的 union。普通布局 baseline 一旦揭示某个 document 的一个 cell，就必须扫描该 document 的全部 token pages；由于 Col-Bandit 第一轮触达全部 32 documents，ordinary layout 始终读 100% 候选页。

### 5.2 Col-Bandit `alpha=0.2` 的主要结果

| Representation | Full cells | Revealed cells | Cell coverage | Full/ordinary pages | Page oracle pages | Page oracle/full | Outer overlap |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw FP16 | 742.0 | 582.4 | 79.4% | 1,613.4 | 197.1 | 12.2% | 98.75% |
| raw int8 | 742.0 | 582.1 | 79.4% | 792.6 | 181.8 | 22.9% | 98.75% |
| Light-style f9 FP16 | 742.0 | 537.9 | 73.0% | 191.1 | 118.2 | 61.9% | 92.50% |
| Light-style f9 int8 | 742.0 | 535.9 | 72.7% | 95.1 | 80.9 | 85.1% | 93.75% |
| Light-style f49 FP16 | 742.0 | 477.6 | 64.1% | 62.3 | 49.0 | 78.7% | 98.75% |

结果分离了三件事：

- Col-Bandit 的 computation saving 没有自动变成 I/O saving；普通 layout 页面数完全不变。
- raw 表示存在巨大的 maxima locality oracle，但强表示/量化先回收了多数空间：从 raw FP16 的 87.8% oracle saving 降到 factor-9 int8 的 14.9%。
- 即便只剩 14.9%，factor-9 int8 page-oracle 点仍在其 68.75% representation fidelity 上把 95.1 页降到 80.9 页，没有被 f49 的 62.3 页/51.25% fidelity 或 single-vector 的 32 页/33.75% fidelity完全支配。P1 因而只能 Continue，不能把“收益变小”当作人为 Kill。

## 6. P2：Feasible Centroid-Radius Safe Bound

### 6.1 实现

每个真实物理 token page 存：

```text
centroid c_g: fp16[128]
radius r_g:   fp16
token count, document/page IDs, byte offset
record size: 288 B (actual packed/aligned)
```

对单位 query token 使用安全界：

```text
U(q,g) = q · c_g + max_x_in_g ||x - c_g||_2
```

已读页给出 lower bound；当 lower bound 不小于所有未读页 upper bound 时，该 cell 精确结束。每次 page read 同时更新当前 document 的全部 active query tokens。比较：

- layouts：spatial/document contiguous、centroid-grouped、representative-first；
- schedules：simple sequential、`active query-token batch` greedy；
- representations：raw FP16、raw int8、Light-style f9 int8；
- oracle：同一 Col-Bandit reveal set 的 maxima-page union。

所有 inner cell 最终均与 exhaustive MaxSim `atol=2e-6` 一致；因此 P2 失败不是 ranking error 换来的假象。

### 6.2 结果

下表对每种表示取 page oracle 最好的 layout，并列 feasible policy 的最好页面数。不同 schedule 的页面结果几乎相同。

| Representation | Full pages | 最佳 page oracle | 最佳 feasible pages | Feasible/full | Synopsis/data | Greedy bound CPU | Inner exact | Outer overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| raw FP16 | 1,613.4 | 187.9 | 1,612.2 | 99.92% | 7.05% | 43.7–43.8 ms | 100% | 98.75% |
| raw int8 | 792.6 | 167.2 | 792.6 | 100% | 7.04% | 20.6–20.7 ms | 100% | 98.75% |
| Light-style f9 int8 | 95.1 | 78.5 | 95.1 | 100% | 7.33% | 2.51 ms | 100% | 93.75% |

进一步观察：

- raw FP16 的绝对最佳只少读平均 1.25 页/1,613 页；这不是可回收的系统空间。
- centroid grouping 确实把 raw int8 oracle 从 spatial 的 181.8 页降至 167.2 页，但 safe policy 仍读 792.6 页，说明瓶颈是 radius looseness，不是 page order。
- factor-9 int8 每 query 平均 32 active documents、535.9 active cells。一次读页能改善约 9.6–11.5 cells，但不足以证明任何 cell 已达到未读页上界，最终仍读完 95.1 页。
- synopsis 总文件已实际 4 KiB 对齐；不是只按 `page_count × vector bytes` 估算。其 7% storage overhead 在完全没有 page saving 时纯属负收益。
- sequential schedule 的 bound CPU 较低（raw FP16/int8/f9 int8 约 0.30/0.21/0.14 ms），但因为读全页，它就是 full scan 加 synopsis。greedy schedule 又将 CPU 放大到 43.7/20.7/2.5 ms，仍不减少页面。

## 7. Pareto 与 Kill 原因

P1 的 oracle 证明问题空间不是虚构的：特别是 raw 表示，maxima 分布允许少读很多页；strong representation 后仍残留一个很窄的理论点。但 P2 表明 centroid-radius synopsis 的 upper bounds 在 128D ColQwen2 geometry 中过松，所有简单 layout 和 active-batch schedule 都收敛到 full scan。

因此 P2 同时命中 gate 的自然 Kill 条件：

1. **safe bounds 太松，必须读取几乎全部页面**；
2. **metadata 增加约 7%，却没有 I/O 回报**；
3. **收益无法在 strong Light-style + int8 representation 上兑现**；
4. **greedy scheduler 只是增加 CPU，不产生新 joint Pareto 点**；
5. 继续组合 async direct I/O 最终只会成为 `Col-Bandit + page summaries + full object read`。

最终裁决：

```text
PageMaxSim = KILL at P2
P3 SSD replay = NOT AUTHORIZED / NOT RUN
architecture review = NOT REQUESTED
system implementation = NOT STARTED
```

这不证明任何更复杂的 learned/non-spherical bound 永远无效；它证明当前候选没有取得进入该机制研究所需的最小 feasibility evidence。若未来要复活，必须先提出无需真实 page reads 即可离线验证、且严格安全并显著紧于 centroid-radius 的 synopsis；不能用同一结果改成 heuristic threshold 或 async I/O 叙事。

## 8. 局限与不应过度外推之处

- pilot 只有 64 documents/16 queries，足以做 paired page-bound feasibility，但不是论文级 retrieval quality evaluation。
- ColQwen2 与 DocVQA 属于 gate 允许的 ViDoRe 类 workload；未再追加 REAL-MM-RAG，因为 P2 已在 raw 和两个强 footprint 上共同触发早停。
- Light 的 fine-tuned checkpoint 不公开；post-hoc factor-9 的小样本 top-5 overlap 不能替代论文 NDCG。更强 Light 质量会增强表示压缩 baseline 的竞争力，但不同 fine-tuned embedding geometry 是否令 radius 变紧尚未直接测量。
- 未测 cold/warm cache 与 concurrency 1/8/32，因为这些属于 P3 真实 SSD replay；P2 Kill 后继续测量违反上游 gate。
- CPU MaxSim 是 NumPy reference，不是 NUMKONG fused kernel；因此只使用 device-independent break-even，不做端到端 latency claim。

## 9. 复现代码

- `codex/work/visual_pagemaxsim_gate/prepare_embeddings.py`
- `codex/work/visual_pagemaxsim_gate/analyze_p0_p1.py`
- `codex/work/visual_pagemaxsim_gate/analyze_p2.py`
- `codex/work/visual_pagemaxsim_gate/README.md`

代码固定了 dataset/model revisions、seed、serialization format、Col-Bandit parameters、candidate construction 和所有输出路径。P0/P1/P2 JSON/CSV 及实际 `.bin` 文件保留在项目 NVMe，可逐项审计。
