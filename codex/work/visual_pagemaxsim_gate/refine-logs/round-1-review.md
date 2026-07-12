# Round 1 Review

# 独立评审：Residual-Certified PageMaxSim

## 总体判断

这个方向确实针对 P2 的直接失败机制：它把每页一个大球替换为共享 codebook 支撑的多个小 residual balls，因此不是调度器、异步 I/O 或近似阈值意义上的漂移。不过，当前提案尚未证明 P2 的松弛主要来自“页内多模态”，而不是高维 Cauchy residual bound 本身的方向信息丢失；后者即使拆成多个球，也可能继续读取全部页面。

我支持再做一次严格限定的 CPU-only synopsis gate，但只把它视为低成本的机制证伪实验，不应称为 PageMaxSim 复活或批准 P3。当前版本需要先补齐浮点安全、真实 metadata 格式、held-out codebook protocol 和 f9-int8 生存判据。

## 评分

| 维度 | 分数 | 评语 |
|---|---:|---|
| Problem Fidelity | 9/10 | 直接替换 P2 失败的 synopsis，并保留 outer Col-Bandit、真实页面和强表示约束。 |
| Method Specificity | 6/10 | 数学主线清楚，但没有定义量化后评分对象、codeword/radius 精度、向上舍入、dot-product error、metadata 编码及严格 held-out 划分。 |
| Contribution Quality | 6/10 | “共享 centroid + residual radius + codeword-sorted pages”容易被视为 PLAID 式组件的物理页重组；只有 f9-int8 上形成强 Pareto 后才可能成为机制贡献。 |
| Frontier Leverage | 7/10 | 正确复用视觉 late interaction、token merging、量化与 centroid vocabulary，没有强塞 learned router；但与 PLAID/WARP 的机制边界仍是口头断言。 |
| Feasibility | 7/10 | 64/256/1024 codebook 的 CPU gate 可做，但 K=1024 的训练、全局表摊销和 f9 小样本过拟合需要约束。 |
| Validation Focus | 8/10 | 一次 synopsis gate、两项核心 claim，范围克制；应增加“松弛来源分解”，而不是增加数据集或系统实验。 |
| Venue Readiness | 5/10 | 当前仍是合理工程假说；尚无证据证明它越过 representation compression 和 PLAID/WARP prior art。 |

按指定权重计算：

```text
Overall = 0.15×9 + 0.25×6 + 0.25×6 + 0.15×7
        + 0.10×7 + 0.05×8 + 0.05×5
        = 6.75 ≈ 6.8/10
```

**Verdict：REVISE**

## 核心技术审查

### 1. 是否真正针对 single-ball looseness

部分成立，而且方向是对的。每页 single ball 会被跨模态 token 和 outlier 撑大；按全局 codeword 分组后，`max_k(q·μ_k + R_gk)` 严格不松于把所有分组并成一个粗球的同类构造，并提供了从“单球”到“近逐 token”的可控谱系。

但 P2 尚未把 looseness 分解为两项：

1. 页内多个语义/视觉模态被一个球混合；
2. `q·e ≤ ||e||` 丢失 residual direction。

multi-ball 主要解决第一项。若同一 codeword 内 residual norm 为 0.2，而竞争页面 MaxSim gap 只有 0.01–0.03，即使每页只有若干很纯的小组，Cauchy 界仍可能无法排除页面。K=1024 只有在逼近逐 token codebook 时才可能收紧，而这会把 metadata/control plane 推向 PLAID 式逐 token索引。

因此必须新增一个“松弛来源分解”，但不需要新增完整实验块：

- single-ball slack；
- multi-ball L2 slack；
- 每组真实最大值构成的 group oracle；
- page oracle；
- distinct codewords/page、组大小和 residual-radius 分布。

如果 multi-ball 与 group oracle 差距仍大，问题是 residual direction，而非页内多模态；不应继续调 K 或 scheduler。

可以考虑把欧氏球改为单位球面上的 angular cap。若 codeword 和 token 均归一化，并保存最大夹角，球面帽上界通常严格紧于 `q·μ+R`。这仍是相同的最小 synopsis 思路，不构成额外模块。不过应将 L2 union-of-balls 先作为可证伪 baseline，不能同时堆叠多种 synopsis 家族。

### 2. exact safety 尚未闭合

实数域推导正确，但当前序列化描述不足以保证实现中的 exact safety。至少要固定：

- 被认证的是原始 FP16 token、int8 反量化 token，还是反量化后重新归一化的 `x̂`；
- codeword 是 FP16 还是 FP32，是否重新归一化；
- radius 的存储精度；
- radius 是否朝 `+∞` outward rounding；
- FP32 dot product 的累计误差补偿；
- `U` 与 exact scan 是否基于同一个 `x̂`。

推荐定义：

```text
x̂ = serving 时真正参与 MaxSim 的反量化并归一化向量
μ̂ = 从磁盘 codebook 解码后、bound kernel 实际使用的向量
R(g,k) = upward_round(max ||x̂-μ̂||)
U(q,g) = upward_round(q·μ̂) + R(g,k) + εdot
```

若 radius 用 FP16，必须使用 `nextafter(...,+∞)`，不能普通 round-to-nearest。更稳妥的是先用 FP32 radius 完成 gate，再评估 outward-rounded FP16 是否仍安全。除了 exhaustive `atol` audit，还应报告最坏 certificate margin 和零 violation；`atol` 一致本身不是形式安全证明。

这是 **CRITICAL** 修改。

### 3. metadata、CPU 和 f9-int8 生存条件不够具体

必须给出实际 control-plane 格式，而不只是字段名称：

```text
global header
K × 128 codeword payload
per-document offset table
per-page header
n_pairs × (codeword_id, outward radius)
alignment/padding
query-side q·μ table
```

K=1024、FP16 codebook 本身约 256 KiB。对 64-document pilot，它相对 f9-int8 的约 768 KiB data payload 并不小；“全局共享”只有在大 corpus 中才自然摊薄。应同时报告：

- pilot 实际总 bytes；
- bytes/document 与 bytes/token；
- codebook 常驻 DRAM；
- 1M-document 外推；
- codebook 摊销 break-even corpus size；
- distinct `(page,codeword)` pairs，而非只报 pages。

CPU 也必须计入完整在线路径：

- query-codebook GEMM；
- metadata decode；
- bound materialization；
- priority/scheduler；
- 已读 token 的 exact MaxSim；
- 总 CPU，而非只报 bound kernel。

f9-int8 的 oracle 空间只有约 14–17 pages/query，约 56–70 KiB。报告中的 f9 Full-MaxSim 仅约 0.425 ms，而旧 greedy 已花 2.51 ms。因此新方法若仍复用 greedy，生存概率很低。应报告：

```text
extra CPU / pages saved  = 每省一页允许的 CPU 代价
```

并给出不同 page-touch cost 下的 crossover curve，不需要偷跑 P3 或设任意百分比阈值。

f9-int8 的最低生存条件应明确为：

- exact certificate 零违规；
- safe policy 严格少于 95.1 pages/query；
- 在 held-out 文档/查询上成立；
- 计入 codebook、page metadata、padding后仍有存储/I/O trade-off；
- 总 CPU 与省页数构成可解释的 crossover，而非明显被 f9 full scan 支配；
- 收益不能只由 raw representation 提供。

这是第二项 **CRITICAL** 修改。

### 4. held-out protocol 需要修正

“在一个 document split 上训练、held-out queries/documents 测试”目前不可直接从 64 documents/16 queries 推出。若 32 文档训练 codebook、32 文档测试，top-32 candidate set 会退化成整个测试库；若 codebook 使用全部 64 文档，则不能声称 document-held-out。

应预先选择一种诚实协议：

- 扩大仅用于 codebook/layout 训练的 document pool，保留原 64/16 trace 做完全 held-out replay；或
- 使用 document-level cross-fitting，并汇总 fold 内真实 coarse candidates；或
- 明确本轮只验证 query-held-out，不声称 codebook 跨文档泛化。

K=1024 对约 5.4K 个 f9 tokens 也容易接近记忆训练集。必须报告 codeword occupancy、空 codewords、singleton rate 和训练/测试 residual gap。

优先级：**IMPORTANT**。

## 与 PLAID、WARP、Col-Bandit 的边界

当前贡献边界方向正确，但不足以支持 novelty。建议用固定四列表，而不是“centroid machinery 已被验证”一句带过：

| 系统 | 已有机制 | 不解决什么 | 本工作的唯一候选增量 |
|---|---|---|---|
| Col-Bandit | 外层 `(document, query-token)` cell 选择与淘汰 | 一个 cell 需要读取哪些物理页 | exact inner page maximum |
| PLAID | centroid IDs、residual compression、centroid interaction/candidate pruning | 面向 4 KiB per-document pages 的 exact maximum certificate | per-page outward-safe residual envelope |
| WARP | late-interaction 索引和高效检索执行 | 需要核实其 page organization、pruning safety 与 exactness | 只有其未覆盖 exact page admission 时才有空间 |
| 本方案 | codeword-sorted page + residual certificate | 不发明 outer bandit、codebook 或 residual codec | 强压缩表示下用小 control plane 精确跳页 |

尤其要核实 PLAID/WARP 是否已有等价 residual upper bound 或 centroid-partition skipping。若有，则该提案最多是视觉文档上的物理页实例化；若没有，贡献也必须表述为“exact physical-page admission control”，不能声称 centroid/residual indexing novelty。

优先级：**IMPORTANT**。

## Simplification Opportunities

1. 删除 supporting scheduler contribution。使用固定 best-upper-bound 或现有 active-batch scheduler作为执行器，不把它写成贡献；P2 已证明 scheduler 不是主要变量。
2. 只保留一个 synopsis family：codeword-sorted residual certificate。K 是精度/metadata knob，不再并列 learned router、hierarchy或 approximate route。
3. 分阶段扫 K：先 64/256 做几何证伪；只有 f9 residual slack 明显下降时才运行 1024，避免用近逐 token metadata“赢得”结果。

## Modernization Opportunities

无需添加 learned router、VLM finetuning 或 RL scheduler。当前“复用现有 late-interaction codebook、零新增训练组件”的选择是合理的。更有价值的现代化是：

- 若 PLAID/ColBERT 兼容，直接复用已有部署 codebook，而非为 gate 单独训练；
- 将欧氏 residual ball 升级为 normalized embedding 的 angular-cap certificate，但保持单一 synopsis 贡献。

## Drift Warning

**NONE。**

提案仍在解决“强压缩 visual multi-vector object 内 exact MaxSim 的部分物理页读取”，没有漂移到通用 ANN、近似路由或异步 SSD engine。

## 是否值得额外 CPU-only synopsis gate

**值得，但仅值得一次，并应采用两级早停。**

第一阶段是几何/安全 micro-gate：

- train-only codebook、held-out replay；
- K=64/256；
- raw-int8 与 f9-int8；
- outward-safe certificate；
- slack、false-threatening pages、distinct pairs、exact violation；
- single-ball → multi-ball → group oracle → page oracle 分解。

若 f9-int8 仍读 100% 页面，或 multi-ball 与 group oracle 的差距仍占主要部分，立即 Kill，不跑 K=1024。

第二阶段仅在第一阶段有信号时执行：

- K=1024；
- actual serialized metadata；
- complete online CPU accounting；
- total page/storage/CPU crossover；
- sequential/best-upper-bound 对比，不优化 scheduler。

通过该 CPU-only gate只意味着“可请求 P3”，不意味着 PageMaxSim 已成立。当前不应进行 SSD replay、architecture review 或系统实现。

## 按优先级的修改清单

1. **CRITICAL**：定义 int8 服务向量、codeword/radius 精度、outward rounding 和 dot-product error，闭合位级安全。
2. **CRITICAL**：把 f9-int8 生存条件写成 actual bytes、total CPU、pages 和 crossover 的联合判据。
3. **CRITICAL**：增加 single-ball / multi-ball / group oracle / page oracle 的松弛来源分解。
4. **IMPORTANT**：修正 document-held-out codebook 协议，避免 64-document trace 上的数据泄漏或 top-32 退化。
5. **IMPORTANT**：逐项核实 PLAID/WARP 的 residual pruning、物理布局和 exactness，写成 closest-mechanism table。
6. **IMPORTANT**：删除 scheduler 的 supporting contribution，把论文主张收缩为 exact page-safe synopsis。
7. **MINOR**：先 K=64/256，只有出现 f9 信号才运行 K=1024。
8. **MINOR**：将“under one hour”改为按 K、token 数、k-means迭代和 replay 数量分解的 CPU 预算。
