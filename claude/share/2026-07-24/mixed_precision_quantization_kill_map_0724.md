# MIXED-PRECISION-QUANTIZATION-KILL-MAP

**日期：** 2026-07-24  
**作者：** Claude  
**目的：** 在 mixed-precision 实现前，系统检查是否已有方法在相同或更低内存下解决 PQ32→PQ64 的前沿差距，或已覆盖候选机制的 novelty 空间。

**核心问题：**
> 在 GIST1M-960D、固定全精度图下，PQ64 L400 以 +32B/vector 代价严格 Pareto 优于 PQ32 L800（+1.99pp recall, −49% reads, 1.84× QPS, −46% p99）。能否在 ≤32B/vector 或相同平均预算下达到 PQ64 前沿？

---

## 1. OPQ（Optimized Product Quantization）

| 维度 | 内容 |
|---|---|
| 表示单位 | per-subspace（与 PQ 相同） |
| 精度分配 | uniform — 所有向量使用相同码长，通过学习旋转矩阵 R 最小化量化误差 |
| 图关系 | 固定图导航 — 不修改图拓扑，仅替换距离计算中的 PQ 码 |
| 内存预算 | 与 PQ 相同 bits/vector + 旋转矩阵 R（D×D float，query 端一次性开销） |
| 查询成本 | ADC，query 需额外一次 R 乘法（D×D），查表路径不变 |
| 存储场景 | in-memory / SSD graph 均可 |
| 结果指标 | 文献报告在 SIFT/GIST 上 OPQ 相对 PQ 降低 10-30% 量化误差；RPQ 论文实测 DiskANN-OPQ 相对 DiskANN-PQ 在同 recall 下 QPS 提升有限（远不如 RPQ）|
| 代码状态 | FAISS 原生支持 `OPQMatrix`；DiskANN 可通过对数据做 OPQ 旋转预处理后用标准 PQ 管线，需少量改造 |
| Novelty 威胁 | 低 — OPQ 是更优的 uniform 编码器，不涉及 per-vector 精度分配 |
| Kill 条件 | **若 OPQ32 在 GIST1M-960D 上达到 PQ64 前沿（同 recall 下 reads/QPS 可比），则 mixed-precision 动机被消灭。** 高维下旋转收益可能有限（960D 子空间已较细），需实验确认 |

**Kill 概率评估：** 中低。OPQ 在高维度场景下旋转优化空间有限——960D 分 32 个子空间时每子空间 30 维，旋转能做的对齐有限。但这是最廉价的 baseline 实验，必须先跑。

---

## 2. RPQ（Routing-Guided Learned Product Quantization）

| 维度 | 内容 |
|---|---|
| 表示单位 | per-subspace（与 PQ 相同，但 codebook 用神经网络 end-to-end 学习） |
| 精度分配 | uniform — 所有向量相同码长，差异在 codebook 质量 |
| 图关系 | **routing-aware training** — 用图采样提取邻域和路由特征，用 routing-aware loss 联合训练量化器 |
| 内存预算 | 与 PQ 相同 bits/vector；训练端额外开销（differentiable quantizer + feature extractor） |
| 查询成本 | ADC，查表路径不变 |
| 存储场景 | in-memory / SSD graph 均可，已与 DiskANN 集成 |
| 结果指标 | RPQ 论文（ICDE 2024）：DiskANN-RPQ 相对 DiskANN-PQ 在同 recall 下 QPS 提升 77%（BigANN），最高 320%（Deep）。**这意味着 RPQ32 可能接近或达到 PQ64 的路由质量** |
| 代码状态 | 论文开源（arXiv:2311.18724），已与 DiskANN 集成。需验证 960D 数据集兼容性和 frozen-graph harness 适配 |
| Novelty 威胁 | **高** — 若 RPQ32 达到 PQ64 前沿，说明问题根源是 codebook 质量而非 bit 数，mixed-precision 方向应 KILL |
| Kill 条件 | **若 RPQ32 在 GIST1M-960D 上 Recall-reads-QPS-p99 前沿达到或接近 PQ64，则直接 KILL mixed-precision。** |

**Kill 概率评估：** **中高。** RPQ 是当前最大威胁——它直接证明在相同 32B 下通过更好训练就能大幅改善路由质量。RPQ 论文的 BigANN/Deep 结果令人印象深刻，但 960D 高维下效果需验证。

---

## 3. RaBitQ / Extended-RaBitQ

| 维度 | 内容 |
|---|---|
| 表示单位 | per-vector — 对每个向量做随机旋转后逐维量化 |
| 精度分配 | uniform — 原版 1 bit/dim（SIGMOD 2024），Extended-RaBitQ 支持 B bits/dim（SIGMOD 2025） |
| 图关系 | 固定图导航 — 替换距离计算；SymphonyQG 进一步将 RaBitQ 码与邻居列表共置 |
| 内存预算 | 1-bit RaBitQ: 960 bits = 120 bytes/vector + 约 8B 元数据（norm、scale）≈ 128 B/vector。**远超 PQ64 的 64B！** 2-bit: ~248 B/vector。4-bit Extended-RaBitQ: ~488 B/vector |
| 查询成本 | bitwise popcount + 少量 float 运算；SymphonyQG 的 FastScan 路径极快 |
| 存储场景 | in-memory 为主（SymphonyQG）；SSD 场景下码长太大反而不利 |
| 结果指标 | SymphonyQG（RaBitQ + 图共置）：1.5-4.5× QPS 提升；但在 960D 下 1-bit RaBitQ 的 128B/vector > PQ64 的 64B/vector |
| 代码状态 | 开源（VectorDB-NTU/RaBitQ-Library）；SymphonyQG 开源。需验证 DiskANN SSD 管线适配 |
| Novelty 威胁 | **低（在本问题框架下）** — RaBitQ 在高维下的每向量内存大于 PQ64，不能在 ≤64B 预算内替代 |
| Kill 条件 | **不适用于当前问题。** RaBitQ 的优势在低维或 in-memory 场景；960D 下反而更贵。除非 Extended-RaBitQ 的 sub-1-bit 配置能在 ≤32B/vector 达到高 recall，但这在 960D 下不可能（1 bit/dim 已是 120B） |

**Kill 概率评估：** 极低。RaBitQ 在 960D 下的内存消耗远超 PQ64，不构成竞争。但在低维场景（128D SIFT）下 RaBitQ 可能是强 baseline（128 bits = 16 bytes/vector < PQ32），这限制了 mixed-precision 论文的适用范围声称。

---

## 4. LeanVec / LVQ（Locally-adaptive Vector Quantization）

| 维度 | 内容 |
|---|---|
| 表示单位 | LVQ: per-vector scalar quantization with per-vector adaptive scaling；LeanVec: 先降维再量化 |
| 精度分配 | LVQ: uniform 精度但 per-vector scale/bias（局部自适应）；LeanVec: uniform |
| 图关系 | 固定图导航 — Intel SVS 中与图索引集成 |
| 内存预算 | LVQ-8: 8 bits/dim → 960D = 960 bytes（太大）；LVQ-4: 4 bits/dim → 480 bytes（仍太大）。LeanVec: 降维至 d' 后用 LVQ，内存取决于 d' |
| 查询成本 | LVQ: SIMD scalar quantized distance（非查表，直接计算）；利用 Intel AVX-512 |
| 存储场景 | in-memory（Intel SVS）；SSD 未适配 |
| 结果指标 | LeanVec 比 SVS-LVQ 快 2.4×，比 HNSWlib 快 13.7×（NeurIPS'23 BigANN 竞赛表现） |
| 代码状态 | Intel SVS 开源但 **仅支持 Intel 平台**，与 DiskANN SSD 管线不兼容 |
| Novelty 威胁 | 低 — LVQ 在高维下内存过大；LeanVec 的降维-量化组合是不同范式，不直接竞争 PQ 导航码 |
| Kill 条件 | **不适用。** LVQ 在 960D 下 per-dim scalar 量化导致内存远超 PQ64。LeanVec 的降维路径与 PQ 不可比。且都局限于 Intel in-memory |

**Kill 概率评估：** 极低。架构和内存预算完全不适用于本问题。

---

## 5. TurboQuant

| 维度 | 内容 |
|---|---|
| 表示单位 | per-vector — data-oblivious，随机旋转后用预计算 Lloyd-Max codebook 逐维量化 |
| 精度分配 | uniform bits/dim，可配置（理论上支持 per-vector 不同精度） |
| 图关系 | 无 — TurboQuant 是纯量化方法，不涉及图索引 |
| 内存预算 | B bits/dim × D dims。960D 下：2-bit = 240B, 4-bit = 480B, 1-bit ≈ 120B。与 RaBitQ 类似量级 |
| 查询成本 | 无 codebook 训练，零索引时间；距离计算需解码（比 PQ ADC 慢） |
| 存储场景 | 主要用于 LLM KV-cache 压缩（Gemma 4 等）；ANNS 应用未见 |
| 结果指标 | 理论上 near-Shannon-optimal distortion rate；但在 ANNS 距离估计场景未见 benchmark |
| 代码状态 | ICLR 2026，有第三方复现（dengls24/TurboQuant-Reproduction）。无 graph ANNS 集成 |
| Novelty 威胁 | 极低 — TurboQuant 与 RaBitQ 是同类方法（random rotation + scalar quantization），在 960D 下内存预算同样远超 PQ |
| Kill 条件 | **不适用。** TurboQuant 在 ANNS 图导航场景无已知集成，内存预算在高维下不竞争 |

**Kill 概率评估：** 极低。这是 LLM 压缩方法，不是 ANNS 导航码方案。

---

## 6. QuIVer

| 维度 | 内容 |
|---|---|
| 表示单位 | per-vector — 2-bit Sign-Magnitude BQ（每维 2 bits） |
| 精度分配 | uniform 2-bit；图构建和导航全部在 BQ 空间完成，仅 final rerank 用 float32 |
| 图关系 | **quantized graph construction** — Vamana edge selection、diversity pruning 全在 BQ metric 下完成 |
| 内存预算 | 2 bits/dim × 960 = 1920 bits = 240 bytes/vector（远超 PQ64） |
| 查询成本 | bitwise ops（极快热路径）；final rerank 需 float32 random access |
| 存储场景 | in-memory，hot memory 4.7× less than full-precision（但在 960D 下仍然 240B/vector） |
| 结果指标 | 2.5-5.5× throughput over DiskANN Rust 和 HNSW（matched recall）；但主要在 128D-768D 上 benchmark |
| 代码状态 | arXiv 2026-05，开源。图构建假设与 frozen-graph harness 不兼容（QuIVer 自己构图） |
| Novelty 威胁 | **中** — QuIVer 证明图导航可以在极低精度下完成（概念相关），但它改变了图拓扑，不是"同一图不同精度码"的问题 |
| Kill 条件 | **不适用于当前 frozen-graph 设定。** QuIVer 需要用 BQ 距离构图，无法 drop-in 替换现有全精度图的导航码。且 960D 下 240B/vector 远超 PQ64 |

**Kill 概率评估：** 极低（在 frozen-graph 框架下）。QuIVer 的 novelty 威胁在于证明了"低精度可以导航"的概念，但它是通过改图而非改码实现的。

---

## 7. ANNS-AMP（Adaptive Mixed-Precision）

| 维度 | 内容 |
|---|---|
| 表示单位 | per-cluster — 按 PQ cluster 分配不同计算精度 |
| 精度分配 | **runtime adaptive** — 轻量级 predictor 根据 cluster 特征（scale, radius, query distance）动态选择计算精度 |
| 图关系 | 无图 — 针对 IVF/cluster-based 方法，不涉及图遍历 |
| 内存预算 | 数据存储不变（码不变），只改变距离计算的硬件精度 |
| 查询成本 | 87-94% 距离计算在低精度完成；需要专用硬件加速器 |
| 存储场景 | **硬件加速器（ASIC）** — 不适用于通用 CPU/SSD |
| 结果指标 | 163× speedup vs CPU, 10.6× vs GPU, 2× vs ASIC baseline；energy 降低 1100× vs CPU |
| 代码状态 | arXiv 2026-06，专用硬件设计，无通用 CPU 实现 |
| Novelty 威胁 | **中** — ANNS-AMP 的"per-cluster runtime precision"概念与我们的"per-node precision"有重叠，但它是硬件精度（FP16/INT8/INT4）而非码长分配 |
| Kill 条件 | **不直接适用。** ANNS-AMP 解决的是硬件计算精度问题（距离计算用多少位浮点），不是导航码长度分配问题。且依赖专用硬件，IVF-based 而非 graph-based |

**Kill 概率评估：** 极低（在当前 CPU+SSD graph 框架下）。但论文中的 novelty 重叠需要在写作时明确区分——"adaptive precision"一词有两层含义。

---

## 8. ScaNN（Anisotropic Quantization Loss）

| 维度 | 内容 |
|---|---|
| 表示单位 | per-subspace（与 PQ 相同） |
| 精度分配 | uniform 码长，但 loss function 各向异性（更重惩罚平行于原始向量方向的误差） |
| 图关系 | 无图 — IVF-based；SOAR 扩展处理搜索阶段 spilling |
| 内存预算 | 与 PQ 相同 bits/vector |
| 查询成本 | ADC，与 PQ 相同 |
| 存储场景 | in-memory（Google ScaNN 库） |
| 结果指标 | ICML 2020 报告 2× 优于其他 ANN 库；2024 SOAR 进一步改善。但报告主要在 MIPS 上 |
| 代码状态 | Google 开源（ScaNN 库），但与 DiskANN SSD 管线不兼容，IVF-based |
| Novelty 威胁 | 低 — anisotropic loss 是 MIPS 优化，不直接适用于 L2 图导航 |
| Kill 条件 | **不直接适用。** ScaNN 优化的是 MIPS 排序质量，不是 L2 图路由。且 IVF-based，无法 drop-in |

**Kill 概率评估：** 极低。但 anisotropic loss 的思想（对路由重要方向降低误差）与 RPQ 有概念关联，值得关注。

---

## 9. SymphonyQG（RaBitQ + Graph Co-location）

| 维度 | 内容 |
|---|---|
| 表示单位 | per-vector（RaBitQ 1-bit） |
| 精度分配 | uniform 1-bit；但将 RaBitQ 码与邻居列表物理共置以利用 cache locality |
| 图关系 | 固定图导航 + 码共置 — 不改图拓扑，但改存储布局 |
| 内存预算 | 1-bit: D/8 bytes + metadata。960D: ~128 B/vector（> PQ64） |
| 查询成本 | FastScan + popcount（16-20× distance kernel speedup） |
| 存储场景 | in-memory |
| 结果指标 | 1.5-4.5× QPS 提升，2× end-to-end QPS over exact-distance graph traversal |
| 代码状态 | SIGMOD 2025 开源。In-memory only |
| Novelty 威胁 | 低 — 960D 下 128B/vector > PQ64，不在预算内竞争 |
| Kill 条件 | **不适用。** 960D 下 RaBitQ 码比 PQ64 更大 |

**Kill 概率评估：** 极低（在 960D/SSD 框架下）。但在低维场景下是强竞争者。

---

## 10. Residual / Multi-stage PQ（RQ, AQ, IVFPQR）

| 维度 | 内容 |
|---|---|
| 表示单位 | per-vector（多阶段残差编码） |
| 精度分配 | uniform 每阶段码长，总精度通过阶段数控制 |
| 图关系 | 通常无图 — IVF-based；与图索引结合需定制 |
| 内存预算 | M stages × K bits/stage。两阶段 PQ16+PQ16 = 32B/vector（与 PQ32 相同） |
| 查询成本 | 多阶段 ADC 累加；查表次数翻倍 |
| 存储场景 | in-memory（FAISS）；SSD 未见集成 |
| 结果指标 | 文献报告 RQ/AQ 在相同 bits 下 distortion 低于 PQ/OPQ（尤其高维），但查询延迟更高 |
| 代码状态 | FAISS 原生支持 ResidualQuantizer、AdditiveQuantizer。与 DiskANN graph 管线集成需大量工程 |
| Novelty 威胁 | **中高** — 若两阶段 RQ（32B total）在距离估计质量上接近 PQ64，则 mixed-precision 动机被削弱 |
| Kill 条件 | **若 RQ32 (e.g. PQ16 + residual PQ16) 在 GIST1M-960D 上 recall-reads-QPS 前沿接近 PQ64，则 KILL。** 关键瓶颈：多阶段查表延迟可能抵消距离质量改善 |

**Kill 概率评估：** 中。理论上 RQ 的距离估计更准（残差编码捕捉 PQ 遗漏的信息），但实测查询速度可能下降。且与 DiskANN graph 的 ADC 路径集成是工程挑战。

---

## 11. Per-vector Adaptive Bit Allocation（已有工作）

| 维度 | 内容 |
|---|---|
| 表示单位 | per-vector — 不同向量分配不同码长 |
| 精度分配 | **static adaptive** — 基于向量特征（如重构误差、访问频率）分配 |
| 图关系 | 通常不涉及图 |
| 内存预算 | 可变码长，平均预算可控 |
| 查询成本 | 可变长度码的 ADC 需要条件分支或填充对齐 |
| 存储场景 | 理论研究为主；TurboQuant 提到 hot/cold 不同精度的概念（6-bit/2-bit），但在 LLM KV-cache 场景 |
| 结果指标 | 无 graph ANNS 场景的可比较 benchmark |
| 代码状态 | **无已知开源实现用于 graph ANNS 导航码。** 这是我们候选方向的空白 |
| Novelty 威胁 | **这正是我们候选方向的核心** — 当前无已知工作在 graph ANNS 中实现 per-node 可变码长导航 |
| Kill 条件 | 若已有工作在 graph ANNS 中实现了 per-node 可变码长且证明无效，则 KILL。**当前未找到此证据** |

**Kill 概率评估：** N/A — 这是候选方向本身，而非竞争方法。当前空白说明有 novelty 空间，但也说明可能有工程难度原因导致无人尝试。

---

## 综合 Kill 判定

### 威胁层级排序

| 层级 | 方法 | Kill 概率 | 需要实验确认 |
|---|---|---|---|
| **Tier-1 危险** | RPQ（routing-aware PQ） | 中高 | **是 — 必须跑 RPQ32 vs PQ64 on GIST1M-960D** |
| **Tier-2 危险** | OPQ | 中低 | **是 — 最廉价 baseline，优先跑** |
| **Tier-2 危险** | Residual/Multi-stage PQ | 中 | 是 — 但 DiskANN 集成工程量大 |
| Tier-3 参考 | RaBitQ/SymphonyQG | 极低（960D） | 否 — 内存预算不竞争 |
| Tier-3 参考 | LVQ/LeanVec | 极低 | 否 — 架构不兼容 |
| Tier-3 参考 | TurboQuant | 极低 | 否 — 非 ANNS 方法 |
| Tier-3 参考 | QuIVer | 极低 | 否 — 需改图，非 frozen-graph |
| Tier-3 参考 | ANNS-AMP | 极低 | 否 — 硬件精度，非码长 |
| Tier-3 参考 | ScaNN | 极低 | 否 — MIPS/IVF，非 L2/graph |

### Kill Map 结论

1. **当前未找到在 ≤32B/vector、frozen graph、L2/graph-ANNS 场景下已达到 PQ64 前沿的已有方法。** Mixed-precision 方向尚存生存空间。

2. **RPQ 是最大生存威胁。** RPQ32 在同 32B 下通过 routing-aware codebook 可能达到接近 PQ64 的路由质量。若确认，mixed-precision 动机应直接 KILL（问题根源是 codebook 质量而非 bit 数）。RPQ 论文报告 77-320% QPS 提升（BigANN/Deep/SIFT），但 960D 数据未测。**这是 UNIFORM-QUANTIZER-BASELINE-A0 的最高优先级实验。**

3. **OPQ 是最廉价 baseline。** 实现简单（数据预旋转），但 960D 下旋转优化空间可能有限。必须先跑以排除。

4. **Residual PQ 理论上可以在 32B 达到更低 distortion，但查询延迟和工程集成是瓶颈。** 优先级低于 RPQ 和 OPQ。

5. **RaBitQ/LVQ/TurboQuant/QuIVer 在 960D 高维场景下不构成竞争**——per-dim scalar 量化导致码长远超 PQ。这些方法的优势在低维或 in-memory 场景。

6. **ANNS-AMP 的"adaptive precision"是硬件计算精度（FP16/INT8），非码长分配。** 概念有重叠但机制不同，需在论文写作时明确区分。

7. **Per-vector adaptive bit allocation 在 graph ANNS 导航码场景下无已知先例。** 这是 novelty 空间所在，但也意味着可能有隐含工程难度。

### 建议下一步

```text
UNIFORM-QUANTIZER-BASELINE-A0 优先级调整：
  第一层（必须）：RPQ32 / RPQ64 on GIST1M-960D（frozen graph，替换导航码）
  第二层（必须）：OPQ32 / OPQ64 on GIST1M-960D
  第三层（有条件）：若 RPQ32 和 OPQ32 均未达 PQ64 前沿，考虑 RQ32（两阶段残差 PQ）

Kill Map 状态：
  PASS-KILL-MAP — 未找到直接 KILL 证据，但 RPQ/OPQ baseline 实验是硬门禁。
```

---

## 附录：GPT 提出的 6 类区分

| 类别 | 相关方法 | 对候选的威胁 |
|---|---|---|
| 1. 改善量化表示本身 | OPQ, ScaNN anisotropic loss | 中（OPQ） |
| 2. 针对图路由训练量化器 | RPQ | **高** |
| 3. 改变图拓扑 | QuIVer | 低（不适用于 frozen-graph） |
| 4. 查询期动态提高精度 | ANNS-AMP | 低（硬件方案） |
| 5. 节点静态分配不同码长 | **无已知先例** | 候选方向本身 |
| 6. CPU/SSD 系统设计 | SymphonyQG 码共置, LeanVec 降维 | 低 |

候选方向属于类别 5，当前无已知先例。最大威胁来自类别 2（RPQ 可能使类别 5 不必要）。
