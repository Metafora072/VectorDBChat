# SSD-Resident Grouped Multi-Vector Retrieval：A0 Novelty and Viability Review

**Date**: 2026-07-20

**Reviewer**: Codex（独立 novelty / viability 审计）

**Mode**: primary-paper/code review + tiny symbolic/toy validation

**Final label**: **`KILL-ALGORITHM-REPACKAGING`**

## 1. Reviewer conclusion

Claude 提出的 workload 是真实且定义清楚的：对象由多组 token/patch vectors 构成，最终按 document-level MaxSim 返回 top-k，物理载荷可能跨越多个 SSD page。问题不在于 workload 是否存在，而在于本轮三个候选对象没有留下满足 A0 novelty gate 的独立机制：

1. page-level bound 修正后是 MaxSim 上的 branch-and-bound / block-max certificate；
2. cross-candidate adaptive reading 与 Col-Bandit、TA/NRA、WAND/BMW 的 top-k 不确定性调度骨架高度重叠；
3. group-aware layout 尚未给出超越 summary/payload separation、document-contiguous packing 和 query-distribution-aware partitioning 的新目标或可证明性质。

更决定性的是，这不是一个尚待 profiling 的新对象。仓库在 2026-07-12 已对相同的 exact Visual PageMaxSim 路线完成真实 ColQwen2/DocVQA pilot：single-ball feasible policy 读取 **99.92%–100%** 页面；residual multi-ball 在 raw/factor-9、K=64/256、两种 schedule 下均读取 **100%** 页面。当前候选没有提出比已关闭机制更紧、仍严格安全且显著更小的新 synopsis。

因此不能使用 `HOLD-NEEDS-PROFILING`：HOLD 要求“novelty object appears distinct”，而当前 Object 1 是已关闭分支的直接复活，Objects 2–3 是相邻算法与普通物理设计的组合。这里也不裁成 `KILL-NO-STORAGE-BOTTLENECK`，因为未压缩、高候选数、多页对象下 SSD 可能成为瓶颈；被否定的是当前研究机制与 novelty，不是所有 grouped multi-vector SSD workload。

## 2. Claude 的三个 formal objects

| Object | Claude 的候选 | 审计后的准确边界 | A0 结论 |
|---|---|---|---|
| 1 | per-page centroid + residual radius 的 partial MaxSim LB/UB | 修正后是 intra-object page 粒度的 safe branch-and-bound；与 BMW 的 block upper bound 同构，并已在本仓库真实 pilot 中失败 | 已关闭机制复活 |
| 2 | 跨候选选择下一个 `(candidate,page)` | 与 Col-Bandit 的 ambiguous-candidate reveal、TA/NRA 的 partial-object top-k certificate、WAND/BMW thresholding 重叠；“adaptive submodularity”未证明 | 算法重包装 |
| 3 | score-completion-cost-aware layout | summary/payload late materialization、document-contiguous packing、semantic/query-aware partitioning 的组合；无稳定 oracle gap 或新近似保证 | 目标未闭合 |

## 3. Query operator and corrected certificate

令 document `D` 的物理页集合为 `P(D)`，已读页为 `R`。对 query token `q_i`：

\[
l_i(R)=\max_{p\in R}\max_{x\in p} q_i^\top x.
\]

若页摘要 `M_p` 给出安全支持函数上界

\[
U_{ip}\ge \max_{x\in p} q_i^\top x,
\]

则正确 document bounds 是：

\[
LB_D(R)=\sum_i l_i(R),
\qquad
UB_D(R)=\sum_i\max\left\{l_i(R),\max_{p\notin R}U_{ip}\right\}.
\]

Claude 草稿的

\[
LB_D+\sum_i\max_{p\notin R}U_{ip}
\]

不是一般正确的 completion bound。单 query token、已读最大值 `-0.8`、未读安全上界 `-0.7`、真实最大值 `-0.7` 时，草稿得到 `-1.5`，低于真值；即使上界非负，直接相加也通常过松。未读空集、未读全体以及 negative cosine 的初始化语义都必须显式定义；未读前 `l_i` 不能无条件取 0。

对于单位 query、inner-product scoring，页内 centroid `c_p` 与半径

\[
r_p\ge\max_{x\in p}\lVert x-c_p\rVert_2
\]

给出

\[
U_{ip}=\min(1,q_i^\top c_p+r_p).
\]

这只在以下条件下安全：`sim` 是 inner product 而不是对未归一化 centroid 再算 cosine；summary 相对真正 serving/quantized vectors 构建；量化、dot product、norm 和落盘舍入误差向外包络。`sum_i max_p` 也不能换成 `max_p sum_i`，因为不同 query tokens 的 winner 可以位于不同页。

若当前全局第 k 大 candidate lower bound 为 `theta`，仅当 `UB_D < theta` 才能安全删除候选。若输出还要求 exact winner scores，而不只是 top-k IDs，winner 的未完成 cells 仍需额外 certificate 或完整评分。

## 4. Primary-source boundary audit

以下只用原论文、正式出版页或官方代码界定机制；未把二手博客作为证据。

| Work | Primary source | Mechanism-level overlap and boundary |
|---|---|---|
| ColBERT | [SIGIR 2020 paper](https://arxiv.org/abs/2004.12832) | 定义 token-level late interaction / MaxSim；不是 SSD page skipping |
| ColBERTv2 | [NAACL 2022 paper](https://aclanthology.org/2022.naacl-main.272/) | residual compression 直接削弱 full payload I/O；仍保留 late interaction |
| PLAID | [CIKM 2022 paper](https://arxiv.org/abs/2205.09707) | centroid interaction、candidate pruning、survivor payload materialization；已覆盖 summary-first/coarse-to-fine 执行骨架 |
| XTR | [NeurIPS 2023 paper](https://arxiv.org/abs/2304.01982) | 从检索到的 document tokens 评分，避免 exhaustive token gathering；改变/近似 scorer，不是 exact full MaxSim certificate |
| DESSERT | [NeurIPS 2023 paper](https://papers.nips.cc/paper_files/paper/2023/file/d6cc45de2e2dea14b96c1eba88fd8ef7-Paper-Conference.pdf) | 直接定义 vector-set search，覆盖 `sigma=max, A=sum`，用 per-set sketches/filtering 避免完整 pairwise scoring并给概率保证；是 set-search 算法最近邻 |
| ESPN | [ISMM 2024 paper](https://arxiv.org/abs/2312.05417) | multi-vector table 驻 SSD、GDS async I/O、ANN-guided prefetch、early/partial reranking；直接覆盖 disk residency 与 progressive materialization 边界 |
| MUVERA | [NeurIPS 2024 paper](https://arxiv.org/abs/2405.19504) | 用 fixed-dimensional encoding 近似多向量相似度并减少 candidate，随后可用 original Chamfer/MaxSim exact rerank；candidate stage 不保持 exact recall，但强烈压缩 exact 工作集 |
| ColPali | [ICLR 2025 paper](https://arxiv.org/abs/2407.01449) | visual-page patch embeddings + late interaction；提供目标 workload，不提供 SSD page certificate |
| WARP | [SIGIR 2025 paper](https://arxiv.org/abs/2501.17788) | dynamic similarity imputation、implicit decompression 与两阶段 reduction；覆盖 query-time computation/representation reduction |
| Light-ColPali/ColQwen2 | [ACL Findings 2025 paper](https://arxiv.org/abs/2506.04997) | token merging；11.8% footprint 保留 98.2% effectiveness，2.8% footprint 保留 94.6%，是比 raw payload 更可靠的 compression baseline |
| HPC-ColPali | [2025 preprint](https://arxiv.org/abs/2506.21601) | 声称 1-byte centroid ID、patch pruning 与 30–50% latency reduction；仅是 preprint，且其 byte/bit 与压缩倍数叙述不能承担硬性成本结论 |
| HEAVEN | [ACL Findings 2026 paper](https://aclanthology.org/2026.findings-acl.54/) | single-vector VS-Page candidate stage + multi-vector reranking + query-token filtering；四个 benchmark 平均保留 99.87% Recall@1 performance，并减少 99.82% per-query computation |
| Col-Bandit | [2026 preprint](https://arxiv.org/abs/2602.02827) | 在部分观察的 `(document,query-token)` MaxSim entries 上维护 uncertainty bounds 并自适应 reveal；直接覆盖 Object 2 核心，但为 statistical/tunable 而非 page-exact |
| Flash-MaxSim | [2026 preprint](https://arxiv.org/abs/2605.29517) | exact fused tile scoring 与 on-chip I/O 优化；不处理 NVMe，但证明 CPU/GPU scorer baseline 仍在快速移动 |
| Block-Max WAND | [WSDM 2011 paper](https://research.engineering.nyu.edu/~suel/papers/bmw.pdf) | per-block maximum、动态 top-k threshold 和 safe early termination；Object 1 的 certificate/skip 骨架与其同构 |
| VecFlow-Chamfer | [official code](https://github.com/Supercomputing-System-AI-Lab/VecFlow) | grouped MaxSim/Chamfer 的 anchor candidate generation 与 tiered full-precision materialization；不是 SSD exact-page system，但削弱“grouped scoring 没有 tiered system execution”的叙事 |

### Audit of Claude's boundary claims

- “无一同时组合 exact partial-document MaxSim + SSD layout + adaptive reading”作为字面组合可能成立，但不能自动推出 novelty；DESSERT/PLAID/ESPN/Col-Bandit/BMW 已分别占据 set scoring、summary/payload staging、SSD residency、partial-score scheduling 和 safe block pruning，剩余差别主要是把相同骨架放到 intra-document 4 KiB page。
- Claude 将 WARP 写成“只减少计算、不减少 I/O”不准确。WARP 只解码 query-token 所选 centroid clusters 中的 residual payload，并对 missing interactions 做 dynamic imputation；与 XTR 一样，它通过改变/近似 execution 避免 full-document gathering。
- XTR/WARP 不保持标准 exhaustive MaxSim，因此不能单独 Kill exact 路线；MUVERA 的 FDE candidate stage 也近似，但其 survivor rerank 可回到 original score。MUVERA、HEAVEN、Light 系列不能证明 exact 路线在所有质量点无用，它们是强 dominance baselines。
- Claude 将 PLAID 简单分类为“index 假设全驻内存”过强；官方 ColBERT residual storage 支持 mmap。PLAID 没有给出 NVMe page certificate，但 memory mapping 已跨过纯 DRAM/纯 SSD 的二分法。
- HPC-ColPali 不能承担“32× 已消除 SSD 问题”的硬证据：其 preprint 的 1-byte/K=512/32×叙述彼此存在算术冲突，官方代码也未闭合论文声称的 centroid-ID MaxSim serving path。本报告只把它列为未经充分验证的 compression threat，不用它定案。
- Claude 漏掉了最直接的历史证据：本仓库已经实现并关闭 exact Visual PageMaxSim single-ball 与 residual multi-ball admission。
- “adaptive submodularity”没有成立。固定 payload 下，单文档已读页 MaxSim value 是 monotone submodular；但“是否已认证 top-k”的 stopping utility具有跨页互补性，不能由前者直接推出 adaptive-submodular 或 greedy constant-factor guarantee。
- “`O(k log(C/k))` expected page reads matching comparison-selection lower bound”无依据。没有先验可区分 metadata 时，exact top-k 至少需要给各竞争 candidate 排除证据；adversary 还可把决定性 winner 放在每个对象最后一页，使 worst case 为 `sum_D P_D`。

## 5. Tiny symbolic/toy validation

复现脚本：

`codex/share/2026-07-20/grouped_multivector_rag_a0/toy_bound_validation.py`

脚本只用 Python 标准库，无 GPU、无下载、无 NVMe 运行。固定 seed `20260720` 的结果：

| Check | Result |
|---|---:|
| corrected centroid-radius bound | 2,000 signed random trials, 0 violation |
| explicit draft-formula counterexample | draft UB `-1.5`, true `-0.7` |
| deliberately clustered, margin-separated construction | certify top-1 after 9/64 pages = 14.06% |
| diverse-page construction | certify top-1 after 62/64 pages = 96.88% |
| d=128, 4 KiB page, all-FP16 centroid+radius | 258 B/page = 6.30%, before header/alignment |
| d=128, 4 KiB page, FP32 centroid+radius | 516 B/page = 12.60%, before header/alignment |

该 toy 只证明两个存在性结果：正确 bound 可以 sound；在低半径、大 margin、winner 共页的人工数据上可以提前停止。它同时表明 diverse geometry 会使单球接近 full read。它不是 workload evidence，不能覆盖真实 pilot。

### Existing real pilot is decisive

仓库已有两份同题实测：

- `codex/share/2026-07-12/visual_pagemaxsim_problem_gate_report_0712.md`
- `codex/share/2026-07-12/visual_pagemaxsim_multiball_stage_a_report_0712.md`

真实 ColQwen2 / ViDoRe DocVQA、64 pages、16 queries、top-32 candidates 的结论：

| Mechanism | Best relevant result |
|---|---:|
| single centroid-radius, raw FP16 | 99.92% pages read; synopsis/data 7.05% |
| single centroid-radius, raw int8 | 100% pages read; synopsis/data 7.04% |
| single centroid-radius, factor-9 int8 | 100% pages read; synopsis/data 7.33% |
| residual multi-ball, raw/factor-9, K=64/256 | all 128 query-config rows read 100% pages |
| residual multi-ball f9 K64/K256 | 2.943/2.950 false-threat pages per active cell |

这比 A0 toy 更接近 Claude 当前候选，且已经覆盖 representation、layout、schedule、single/multi-ball 与 exact safety。没有新 synopsis 时，不能把同一对象重新标成“待 profiling”。

## 6. Eight required adversarial counterexamples

### 6.1 Useless bound

每页包含方向分散的 unit vectors，使 centroid 为 0、radius 为 1。对任意单位 query token，所有未读页都有 `U_ip=1`；不同 query tokens 的真实 winners 分散在不同页。直到几乎所有页面已读，document UB 都不下降。真实 pilot 的 residual p50 约 `0.85–0.88`、false threats/cell 约 `2.94`，给出了同类现实几何。

### 6.2 Metadata explosion

单球 FP16 summary 已约占 4 KiB 页的 6.3%（历史真实 packed 值约 7%）；axis-aligned FP16 min/max 约 12.5%；`h` 个 FP16 balls 约按 `6.3% × h` 增长。任意 query direction 的紧支持函数在最坏情况下需要表示页 convex hull 的全部 exposed vertices，复杂度退化到 `Theta(n d)`，与 payload 同阶。

### 6.3 Query-dependent layout conflict

容量为 2 的页面、三类查询分别希望 winner pairs `{a,b}`、`{a,c}`、`{b,c}` 共页。无复制 partition 至少让一类 query 跨页；正交方向 `e1/e2` 也会要求相反首读顺序。若不给 query distribution 或复制预算，不存在统一的 score-stratified layout optimum。

### 6.4 Candidate-stage dominance

HEAVEN 已把 stage-2 candidate budget 设为 100/200/400，并报告极高 Recall@1 retention 与 99.82% computation reduction；PLAID、MUVERA、XTR、WARP也在 full refinement 前减少 documents/tokens。若 exact stage 只有几十至几百个压缩对象，page scheduler 的绝对收益可能低于 candidate stage 与 metadata traversal。

### 6.5 CPU dominance

Claude 的 `C=1000,m=100,n=1024,d=128` 至少约 26.2 GFLOP（FMA 计 2 FLOP）；4 ms 等价于持续 6.55 TFLOP/s，不能无测量地归给“8-core AVX-512”。压缩后的 decode、summary dot products、scheduler 和 MaxSim 可能主导；Flash-MaxSim 还说明 scorer baseline 会随 fused kernels 改变。

### 6.6 Compression dominance

Light-ColPali/ColQwen2 在 11.8% footprint 保留 98.2% effectiveness；更激进点在 2.8% footprint 保留 94.6%。1024×128 FP16 raw 约 256 KiB/object，确有 64 个 4 KiB pages；8 KiB representation 只有 2 页，1–4 KiB representation 则不存在 intra-object skipping 空间。partial page reading 与 compression 在抽象上可叠加，但新机制必须在强 compression baseline 后仍有多页可省。

### 6.7 Object-size skew

若单个未读页产生 false threat 的概率为 `p`，P-page 大对象至少一个 false threat 的概率为 `1-(1-p)^P`，随对象长度趋近 1；MaxSim extreme value 还会使 candidate gaps 变小。p99 latency 因少数巨对象而退化，平均页数无法证明系统收益。

### 6.8 Update instability

insert 会扩大 radius、令历史 bounds 变松；delete 若要收紧 radius 或删除 extremal support point，需要页内重扫或额外 heap；semantic regrouping 会把 append/update 变为跨页重写。允许 stale outward bounds 虽保持 sound，却会持续丧失 pruning。Claude 当前 layout object 没有 update cost 或 stability constraint。

## 7. Cost-model audit

Claude 的“raw ColPali C=1000：SSD 65 ms、CPU 4 ms，SSD 慢 16×”不能作为瓶颈证据：

- `65,000 × 4 KiB / 1M IOPS = 65 ms` 使用设备峰值 IOPS 算术，却未指定 queue depth、并发、cache 和 completion batching；
- document-contiguous layout 更接近 1,000 个约 256 KiB extents，受随机 extent latency与带宽共同约束，不等同 65,000 个独立 4 KiB reads；
- adaptive serial page reads又可能达不到峰值 IOPS；
- 4 ms CPU 数字没有实现或 profile 支持，并与上述 FLOP 数不一致；
- 压缩、decompression、candidate generation 与 metadata scoring 没有进入同一端到端 critical path。

所以 A0 不能声称“SSD 已证明比 CPU 慢 16×”。但已有真实 PageMaxSim pilot 的 kill 不依赖 SSD 延迟：feasible bound 与 full scan 读相同页面且额外增加 metadata/CPU，在任何正 page cost 下都被 full scan严格支配。

## 8. Is there a nonreplaceable storage contribution?

抽象上唯一可能不可替代的 storage object 是：

> 在 ordinary NVMe page 粒度下，用远小于 payload 的严格安全 synopsis，把 partial MaxSim 的 interaction-level redundancy 转换成显著 page-I/O saving，同时在 strong compression/cascade 后仍保持端到端 Pareto 改善。

当前候选没有交付这个对象：single-ball 与 residual multi-ball 已真实失败；更强 arbitrary-direction synopsis 面临 metadata explosion；adaptive order 不能修复所有 unread pages 均为 false threats；layout 只能改变 winner locality，不能自动收紧支持上界。因此剩余内容是既有 late-interaction、block-max certificate、adaptive top-k 与普通 physical layout 的组合，而不是已经成立的 nonreplaceable storage mechanism。

## 9. Independent reviewer pass

本轮三个相互独立的只读子审计分别覆盖 prior art、数学/反例和 systems cost model；Codex 主审另外执行 toy validation并核对 7 月 12 日真实报告。

| Reviewer perspective | Verdict | Main reason |
|---|---|---|
| primary-source audit | FAIL（若只审 Claude 报告） | WARP/Col-Bandit/PLAID mmap/MUVERA exact-rerank/HPC code consistency 均被 Claude 漏写或误写 |
| mathematical/bound audit | KILL | draft UB错误；修正后同构 B&B/BMW；真实 single/multi-ball 读满页面 |
| systems/cost audit | KILL | SSD/CPU算术未闭合；ESPN/PLAID/VecFlow 已覆盖 tiered execution；强 representation 压缩页数 |
| Codex main review | KILL | 同题 exact PageMaxSim 已有真实 negative closure；当前没有新 exact synopsis |

只看 Claude 文档本身，primary-source reviewer 会给 `FAIL-LITERATURE-OR-MODEL-CLOSURE`。主审没有停在 FAIL，是因为修正后的 operator、primary boundary 与 7 月 12 日同题真实证据已经足以闭合裁决：在闭合模型上，当前三个对象仍是已关闭机制与相邻算法的重包装，所以最终使用更实质的 `KILL-ALGORITHM-REPACKAGING`。

## 10. Scores and final gate mapping

| Criterion | Score | Reason |
|---|---:|---|
| Significance | 6/10 | workload真实，但可用场景被 candidate reduction/compression 收窄 |
| Novelty | 3/10 | 三对象分别落入已关闭 PageMaxSim、Col-Bandit/TA/BMW、普通 layout |
| System specificity | 5/10 | page coupling 是系统属性，但当前机制没有产生新的 SSD Pareto 点 |
| Hardware fit | 7/10 | 普通 NVMe+CPU 可研究，但不补足 novelty |
| Feasibility of proposed exact bound | 2/10 | 真实 single/multi-ball 已读 99.92%–100% 页面 |

Gate mapping：

- `PASS-GROUPED-MULTIVECTOR-A0`: 不满足 novelty >= 6、system specificity >= 7、useful bound 与 SSD gap 条件；
- `HOLD-NEEDS-PROFILING`: 不适用；已有同题 profile，且 novelty object 不 distinct；
- `KILL-NO-STORAGE-BOTTLENECK`: 证据不足以否定所有 SSD bottleneck regime；
- `FAIL-LITERATURE-OR-MODEL-CLOSURE`: 不适用；primary boundary、operator 与本地实测均可闭合；
- **`KILL-ALGORITHM-REPACKAGING`: 命中。**

```text
KILL-ALGORITHM-REPACKAGING
```

按 gate 停止：不实现、不下载数据、不运行 NVMe/GPU、不制定 profiling gate，也不扩大到 multi-NVMe、动态更新、过滤或 Agent 场景。
