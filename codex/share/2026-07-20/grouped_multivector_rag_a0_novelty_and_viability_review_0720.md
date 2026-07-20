# SSD-Resident Grouped Multi-Vector Retrieval：A0 新颖性与可行性对抗审查

> **Final disposition notice（2026-07-20 17:21:10 UTC+8）：** 本文保留了并发形成的 `HOLD-NEEDS-PROFILING` 审查草稿，但该标签已被随后写入对话的 Gpt 终局裁决覆盖。仓库 7 月 12 日的同题 exact PageMaxSim single/multi-ball 实测已经闭合，最终有效标签是 **`KILL-ALGORITHM-REPACKAGING`**。不得依据本文末尾的旧 HOLD 建议启动 profiling；该方向按 Gpt 要求归档，不再自动复活。

**日期：** 2026-07-20

**范围：** paper-only + 微型符号/玩具验证；未运行 GPU、未下载数据集、未建 ColPali/ColBERT 索引、未做 NVMe 实验、未调用外部 LLM/API。

**审查对象：** Claude 的 landscape/problem model 与 Gpt gate。文中的“页”如无特别说明均指 **SSD 物理页**，不是 PDF 的逻辑页面。

## 1. Prior-work audit：原论文/官方代码机制核验

| 工作 | 已核验机制（原论文/代码） | 与本方向的真实边界及对 Claude 的纠正 | 核验源 |
|---|---|---|---|
| PLAID (CIKM 2022) | 由查询 token 找相近 centroid，经倒排表产生候选；以文档的 bag-of-centroids 做 centroid interaction 和 centroid pruning；只对最终幸存文档 gather/decompress residual，并做完整 MaxSim。 | 与 Object 1 最接近的是“先用小摘要淘汰文档、再解压精确打分”，但剪枝单位是候选文档而不是候选内部物理页。Claude 对最终完整解压的描述正确；“假设索引在 RAM”在论文中没有被证明，不能当作已核验事实。 | [论文](https://arxiv.org/abs/2205.09707) |
| WARP (SIGIR 2025) | 面向 XTR；WARP_SELECT 用累计 cluster size 选择缺失相似度插补值；只解压被 centroid/token retrieval 命中的 token residual；以 implicit decompression 和两级 reduction 聚合分数。 | **Claude 有重大误述。** WARP 不只是“减少计算但不减少 I/O”，也不 gather 完整候选表示；它明确以不 gather complete document representations 为目标。其分数含缺失项插补，且论文承认该上界在 WARP 中不保证成立，因此不是原始 exact MaxSim。 | [论文](https://arxiv.org/abs/2501.17788)、[官方代码](https://github.com/jlscheerer/xtr-warp) |
| XTR (NeurIPS 2023) | 用新的训练目标让重要 document tokens 更早被 token retrieval 命中；候选只用已检索 token 打分，对缺失 query-token 相似度插补，不再访问全部 document token。 | Claude 对“避免 full-document read”的核心描述正确，但“token index 必须在内存”没有由原论文建立。XTR 是本方向最强算法替代之一，但改变训练目标和评分执行，不能给原始 MaxSim 的 exact top-k 保证。2026 replication 还报告其总体有效性优势未能在受控比较中复现。 | [原论文](https://arxiv.org/abs/2304.01982)、[官方代码](https://github.com/google-deepmind/xtr)、[复现论文](https://arxiv.org/abs/2605.00646) |
| MUVERA (NeurIPS 2024) | 以 data-oblivious 随机 Fixed Dimensional Encodings (FDE) 把 Chamfer/MaxSim 近似成单向量内积；用 MIPS 取候选，**随后以原始 Chamfer/MaxSim 精确重排候选**。 | Claude 的“转换为单向量，所以失去 MaxSim exactness”不完整：候选代理是近似的，最终重排仍精确。MUVERA 已直接压低 exact stage 的候选量，且 FDE 可接 DiskANN 等单向量索引，是 candidate-stage dominance 的强基线。 | [NeurIPS 论文](https://papers.neurips.cc/paper_files/paper/2024/file/b71cfefae46909178603b5bc6c11d3ae-Paper-Conference.pdf)、[官方实现](https://github.com/google/graph-mining/tree/main/sketching/point_cloud) |
| HEAVEN (Findings ACL 2026) | Stage 1 用 Visually-Summarized Pages 和 single-vector page refinement；Stage 2 先用约 30% key query tokens 对 `K=200` 页做 multi-vector rerank，再只对 `p2 K`（默认 `p2=0.25`，即约 50 页）用全部 query tokens 精排。 | **Claude 低估了级联强度。** 不是简单的“single-vector → 对所有候选做 full MaxSim”；完整 query-token MaxSim 只发生在再次缩小的集合上。论文报告相对 ColQwen2.5 平均保留 99.87% R@1、FLOPs 降 99.82%，虽其 FLOPs/延迟是全语料 GPU 流程且不是 SSD profiling。 | [ACL Anthology 论文](https://aclanthology.org/2026.findings-acl.54.pdf) |
| ColBERTSaR (SIGIR 2026 short) | 把 token embedding 映射为 anchor/centroid ID，省掉 residual，形成真正 sparse inverted index；用 query-anchor 分数作 query-specific weight，并以 top-n anchors 近似 MaxSim。 | 不只是“PQ 后仍读所有 surviving vectors”。它直接删除 residual payload，评分变为 residual-free 近似；论文报告比 one-bit PLAID 小 50–70%。这明显削弱“所有方法都仍读全 payload”的前提。 | [论文](https://arxiv.org/abs/2606.05568) |
| HPC-ColPali (KDIR 2025 / arXiv 2025) | 声称以 K-means 把每 patch 替换为 1-byte centroid ID，query-time attention pruning，再可选二进制/Hamming 检索。 | **定量证据不可采信为 gate 依据。** 原文写 `512-byte FP32 vector / 1 byte = 32×`，正确算术是 `512×`；其表格的 32× 口径没有解释。方法段还在“query attention”与“按 document patch attention 排序”之间自相矛盾。官方仓库只有少量提交，README 写明 benchmark results 待更新，且描述的 ColQwen2.5 文本 chunk/PQ pipeline 与论文 patch-level 叙述并不完全对应。Claude 将“32×、<2% nDCG loss”作为最强证据过于乐观。 | [论文](https://arxiv.org/abs/2506.21601)、[官方代码](https://github.com/DngBack/HPC-ColPali) |
| CRISP (arXiv 2025) | 将 clustering 纳入多向量模型的端到端训练，使 query/document representations 天生可聚类；C8x32 约 2.9× document compression 且均值略高于未剪枝模型，C4x8 为 11× document compression、NDCG@10 降 3.6%。 | 机制核验通过，但它是训练得到的新**文本**多向量模型，不是 ColPali SSD 执行器；可消除大量向量，却不能证明剩余 payload 的物理页可被 exact 地部分跳过。 | [论文](https://arxiv.org/abs/2505.11471) |
| ConstBERT (ECIR 2025) | 以 learned linear pooling 把可变长 document token embeddings 投影成固定 `C` 个向量（如 32），仍用 MaxSim；论文明确以固定磁盘记录改善 OS paging，并在等效效果处把索引缩小超过 50%。 | Claude 的基本描述正确，但遗漏了其明确的 on-disk/paging 动机。它已覆盖“固定对象尺寸 + 页面友好”的一部分 Object 3；不做 query-adaptive intra-object partial read。 | [论文](https://arxiv.org/abs/2504.01818)、[官方代码](https://github.com/pisa-engine/ConstBERT) |
| SAP / Structural Anchor Pruning (arXiv 2026) | query-agnostic、index-time pruning；用中间层 visual-to-visual attention 的 in-degree centrality 找 anchor patches，并由 Score Retention 诊断自动选结构窗口；>90% token reduction 时保留 >90% NDCG@5。 | Claude 的“90% patches pruned”大体正确，但“robust fidelity”不能写成近乎无损；最坏可有接近 10% 的相对质量损失。它直接减少永久索引和后续所有 I/O，是必须比较的强压缩基线。 | [论文](https://arxiv.org/abs/2601.20107) |
| TACHIOM (SIGIR 2026) | Token-Aware Clustering 按 token 频率/方差分配 centroid；HNSW 只搜 centroids，倒排列表进行 centroid-only document scoring；最终候选以 centroid + PQ residual 做 full MaxSim；物理布局把 document centroid IDs 和 PQ codes 连续存放，并重排 distance tables 改善 cache/SIMD。 | **Claude 有重大低估。** TACHIOM 不是“只加速 clustering”；它同时做 hierarchical candidate generation、PQ 精排和明确的 document/PQ layout。Object 3 若只提出 document-contiguous/cache-aware PQ layout，已被覆盖。它仍没有 sound intra-document page bound。 | [论文](https://arxiv.org/abs/2604.28142)、[官方代码](https://github.com/TusKANNy/tachiom) |
| LEMUR (ICML 2026) | 以一层 MLP 学习 corpus-specific MaxSim 代理，在 hidden space pooling 成单向量并用 ANNS 取 `k'`；最后对 `k'` 候选做 exact MaxSim。 | Claude 对“学习式单向量 reduction”的描述基本正确，但应明确其最终仍 exact rerank。它与 MUVERA 一样把问题压缩为“exact stage 还剩多少候选”，而不是证明 exact stage 必然很大。 | [论文](https://arxiv.org/abs/2601.21853) |
| MM-Matryoshka (arXiv 2026) | 以 2D Matryoshka 训练使表示可沿 prefix dimension 和 encoder layer 选择预算；选定中间层和维度后仍以 MaxSim 打分。 | Claude 基本正确。它降低每向量宽度和编码成本，不降低 token 数；论文效率协议明确**排除 disk I/O 和 first-stage retrieval**，故不能直接回答 SSD 瓶颈，但显著改变 payload 字节数。 | [论文/HTML](https://arxiv.org/html/2606.07654) |
| Visual RAG Toolkit (arXiv 2026) | 同一 Qdrant object 同时保存 full patches（约 700–1024）、tile/row pooled vectors（约 13–32）和 global vector；先 pooled MaxSim prefetch，再对 full named vector exact MaxSim，约 4× QPS。 | Claude 描述正确，但实验只有 3006 页、Qdrant 全内存、无 HNSW；它不能证明 SSD 行为。它却证明了 `prefetch-K` 能把 full stage 变小，是本方向必须打败的 candidate baseline。 | [论文](https://arxiv.org/abs/2602.12510)、[官方代码](https://github.com/Ara-Yeroyan/visual-rag-toolkit) |
| Block-Max WAND / BMW (SIGIR 2011) | 在每条 query-term posting list 的 docID block 上保存最大 impact，形成 piece-wise score upper bound；用 global max 选 pivot，再以 block max 判断能否 shallow-skip block，保证 safe top-k。 | Claude 说“BMW 是 inter-document、这里是 intra-document”在数据组织层面成立，但**粒度变化本身不构成新颖性**。两者的通用范式都是小元数据上界 + 动态阈值 + safe skip；新贡献必须来自 MaxSim 特有、显著紧致且存储高效的 support bound，而不是重新命名 BMW。 | [原论文](https://research.engineering.nyu.edu/~suel/papers/bmw.pdf) |
| **ESPN** (ISMM 2024；Claude 漏检) | 将完整多向量 reranking embedding table 放在 SSD；以 GPUDirect Storage、与 ANN 并行的软件预取和 early reranking 隐藏 I/O；报告 5–16× 内存下降、>90% prefetch hit、SSD retrieval 最高 6.4×，并发现只 rerank 64–128 而非 1000 个候选可减 8–16× 带宽、MRR@10 只降 0.3–0.7%。 | **这是最接近且不可遗漏的 storage prior work。** 它已建立“SSD-resident multi-vector reranking + 跨候选预取/调度 + 部分候选重排”的系统基线。它不在单个候选内部用 sound bound 跳 SSD 页，且依赖 GPU/GDS，但直接削弱 Object 2/3 的广泛新颖性和“无人研究 SSD”判断。 | [论文](https://arxiv.org/abs/2312.05417)、[官方代码](https://github.com/susavlsh10/ESPN-v1) |
| FLASH-MAXSIM (arXiv 2026；Claude 漏检) | 以 SRAM tiling + online max 融合 exact MaxSim，避免物化 query-token × document-token 张量；支持 ragged/INT8，A100/H100 相对 naive 最高 3.9×/4.7×，ColPali `B=1000` 的 corpus operand traffic 约 0.26 GB、kernel 约 1.70 ms。 | 这是 GPU HBM/SRAM I/O，不是 SSD；但它使“MaxSim compute 必然很贵”不成立，并给出精确 scorer 的 operand-read floor。反过来，若 payload 已在 GPU，Object 1 没有价值；若 payload 在 SSD，系统必须证明 SSD→host/GPU 才是剩余主瓶颈。 | [论文](https://arxiv.org/abs/2605.29517) |

**审计总评。** Claude 的检索边界没有闭合：遗漏直接的 SSD 多向量系统 ESPN，并低估 WARP、HEAVEN、TACHIOM 和 ColBERTSaR。与此同时，HPC-ColPali 的 headline compression 数字存在原文级算术/机制不一致，不能作为可靠 kill 或 support 证据。最接近 prior work 的排序是：**ESPN（存储执行） > PLAID/TACHIOM（候选剪枝与精排布局） > WARP/XTR（不 gather 全组） > BMW（安全上界范式）**。

## 2. 八个对抗性反例

以下 verdict 均针对“该反例对当前方向的影响”；`kills` 表示击穿当前对象的普遍性或充分性，不等价于最终标签必为 KILL。

### 2.1 (a) Useless bound — **Verdict: kills Object 1 的普遍有效性**

取 `d=3`、两个单位 query vectors `q1=e1, q2=e2`。每个 SSD 页都只含 `{+e3,-e3}`。每页 centroid 为 0、max residual norm 为 1，所以对任意未读页，centroid+radius 给每个 query token 的上界均为 1；但所有真实 dot product 都是 0，文档真实分数也是 0。四页玩具枚举得到：读 1/2/3 页时 `LB=0, UB=2`，只有读完第 4 页后 `UB=0`。因此只要还有一页未读，上界就完全不收缩。

该构造不是依赖负相似度的技巧；它表示“页内向量方向多样、centroid 接近 0、radius 接近 1”的正常高维坏情形。它证明 centroid+radius 的小元数据可以是 sound 的，却在淘汰显然无关候选时仍毫无用处。

### 2.2 (b) Metadata explosion — **Verdict: kills ‘任意查询下同时小且紧’的承诺**

一个页的最紧 query-dependent upper bound 是其向量集合凸包的 support function `h_P(q)=max_j q·d_j`。构造页内 `b` 个向量均为凸包 exposed vertices；对每个向量都存在一个查询方向使它成为唯一 MaxSim winner。若 metadata 要对任意查询方向给接近精确的上界，就必须保留这些 exposed directions，最坏需要与 `b` 个原向量同阶的信息；用 `K` 个方向网格保存投影上界时，`K` 必须随维度和目标误差快速增长。

4 KiB 页、`d=128`、FP16 payload 时一页只有 16 个向量。一个 FP16 centroid + FP16 radius 是 258 B，约 6.3% 额外空间，确实“小”；但当 centroid ball 过松而改为 16 个 exposed vectors 时，metadata 已等于 4096 B 全 payload。故元数据大小与紧致性之间存在真正下界，不可同时假定二者良好。

### 2.3 (c) Query-dependent layout conflict — **Verdict: weakens Object 3**

设每个对象有两组互不重合的重要方向 `A={a1…aB}` 与 `B={b1…bB}`，物理首读页只能放 `B` 个向量。A 类查询只在 A 组有 winner，B 类查询只在 B 组有 winner。把 A 放首读页使 A 查询一页完成、B 查询最差；反之亦然。均匀 query mixture 下不存在同时最优的静态 score-stratified layout，query distribution 漂移会直接反转布局收益。

这不否定按稳定 workload 学习布局，但使 Object 3 必须显式给定 query distribution、robustness/regret 目标和重布局成本。仅比较 contiguous/semantic/score-stratified 不是非启发式贡献。

### 2.4 (d) Candidate-stage dominance — **Verdict: weakens，并可在现代级联配置下局部 kill**

HEAVEN 对 `K=200` 做 key-token rerank，再只对约 50 页做 full-query refinement；Visual RAG Toolkit 常用 pooled prefetch；ESPN 已显示只 rerank 64–128 而不是 1000 个候选可保留 99.0–99.7% 的 MRR@10。若压缩 payload 为 8 KiB/object，256 个候选共 2 MiB，理想 7 GB/s 传输约 0.30 ms、512 个 4 KiB I/O 在 1M IOPS 下约 0.51 ms。此时增加 per-page metadata、调度和小随机读很可能比直接读完更贵。

所以 Claude 以 `C=1000–10000` 作为主工作点没有 primary-source 支撑；必须证明高 recall 的视觉任务在强候选器后仍需要如此大的 `C`。

### 2.5 (e) CPU dominance — **Verdict: weakens storage-specific claim**

压缩表示必须做 code lookup/dequant、MaxSim reduction 和候选 bookkeeping。WARP 的 PLAID profiling 显示 `k=1000` 时 decompression 约 150–200 ms，而 final scoring 本身近乎可忽略；TACHIOM 明确把瓶颈描述为 cache/memory-bandwidth 和 scattered distance-table access。相反，FLASH-MAXSIM 在 GPU 上把 ColPali `B=1000` exact kernel 压到约 1.7 ms。两边都说明瓶颈取决于表示与执行器，而不是由 `m×n×d` 算术单独决定。

Partial read 同时减少 I/O 和 compute，因而 CPU dominance 不完全否定优化价值；但若收益来自少做 dequant/MaxSim，它是算法/内存层贡献而不是不可替代的 SSD 贡献。

### 2.6 (f) Compression dominance — **Verdict: weakens；HPC 不能单独 kill，但其他证据仍强**

HPC-ColPali 的 32×/<2% headline 有内部错误，不能用来下结论。但更可信的独立证据仍然存在：Light-ColPali/ColQwen2 以 merging 在 11.8% memory 保留 98.2% effectiveness、在 2.8% memory 保留 94.6%；SAP 删除 >90% vectors 后保留 >90% NDCG@5；CRISP 在文本多向量上 11× document compression 仅降 3.6%；MM-Matryoshka 可把每向量宽度缩到前缀维度；ColBERTSaR 干脆删除 residual。

这些方法质量口径、模型和数据集不同，不能证明压缩总能消除 SSD 问题；但它们要求本方向在**压缩后的** payload 上证明剩余 SSD 占比，而不能以 raw FP16 ColPali 为主要系统场景。[Light-ColPali 原论文](https://arxiv.org/abs/2506.04997)

### 2.7 (g) Object-size skew — **Verdict: weakens平均收益并暴露 workload 定义歧义**

令 99% 对象占 1 个 SSD 页，1% 对象占 256 页，且因为 MaxSim 对更多 vectors 的极值机会更大，这 1% 长对象更常进入候选/top-k。即使短对象可节省 50% I/O，总字节仍由长对象控制；而长对象的每个未读页继续保持高 support bound，正落入 2.1 的坏例。按“每对象平均页数”报告会虚假显示高 pruning ratio。

Claude 同时使用“一个逻辑 document page 是检索对象”和“一个 document 跨多个 page”，没有始终区分逻辑页与 SSD 页。A0 必须按对象大小分位数和 bytes-weighted 指标，而不是只给对象数平均值。

### 2.8 (h) Update instability — **Verdict: weakens Object 3**

若 layout 根据 centroid、winner frequency 或 query workload 把向量重新分组，一次模型升级会使整库 embeddings、centroids、radii 和 page order 全部失效；单文档插入也可能令 cluster page 溢出并触发多页重写。跨文档 semantic packing 还把一个对象更新扩散到共享页，产生读改写和碎片。

文档连续布局可把更新限制在单对象，却牺牲语义聚簇与跨对象共享；预留空洞可减写放大，却降低 page utilization。更新不是本 A0 的新增研究范围，但 Object 3 若声称综合优化 updates，就必须把 rewrite amplification 纳入目标，否则只是静态 oracle layout。

## 3. Partial-document bound tightness 分析

### 3.1 正确的 sound bound

对已读向量集合 `R`，定义每个 query token 的当前最大值

`a_i(R) = max_{d in R} q_i · d`。

对未读 SSD 页 `p`，若保存 centroid `c_p` 与认证的最大残差半径 `r_p >= max_{d in p} ||d-c_p||`，则由 Cauchy–Schwarz：

`u_ip = q_i·c_p + ||q_i|| r_p >= max_{d in p} q_i·d`。

因此自然的全对象上界是：

`UB(R) = Σ_i max(a_i(R), max_{p unread} u_ip)`，

等价地：

`LB(R) + Σ_i max(0, max_{p unread} u_ip - a_i(R))`。

Claude 写成 `LB + Σ_i max_p ub_contrib`，没有扣除已读 maxima，通常会双计，因而更松；若相似度允许负值且没有 `max(0, ·)`，该加法形式甚至可能不 sound。量化 metadata 还必须向外舍入，否则 FP16/PQ rounding 会破坏 exact guarantee。

### 3.2 微型枚举结果

| toy | 页内容 | 读页数 | LB | UB | true score | 结论 |
|---|---|---:|---:|---:|---:|---|
| Loose | 4 页均为 `{+e3,-e3}`，`Q={e1,e2}` | 1 | 0 | 2 | 0 | 完全松 |
| Loose | 同上 | 2 | 0 | 2 | 0 | 不收缩 |
| Loose | 同上 | 3 | 0 | 2 | 0 | 仍不收缩 |
| Loose | 同上 | 4 | 0 | 0 | 0 | 直到读完才准确 |
| Tight | P1 两个 `(0.2,0.1,0)`；P2 两个 `(-0.4,0,0)`；P3 两个 `(0,-0.3,0)`；`Q={e1,e2}` | 1 | 0.3 | 0.3 | 0.3 | 读 1/3 即完成 |

结论不是“bound 必然无用”，而是存在明确的两相：当页内半径小、centroid 与 query 方向可分、且当前 `a_i` 已高于所有未读 support bounds 时，metadata 很小且上界很紧；当页内方向多样、centroid norm 小而半径接近 1 时，任一未读页都维持接近 trivial cosine bound 1。

### 3.3 元数据是否可能显著小于 payload

- 4 KiB、`d=128`、FP16 下每页约 16 vectors，centroid+radius 为约 258 B，即 6.3% 额外字节；**空间上可行**。
- 但空间小不等于信息足够。centroid ball 只编码各向同性半径；为紧致需要多球、方向盒、anchor projections 或凸包极点，metadata 很快增长到页面 payload 的同阶。
- 对已经极度压缩的 codes，258 B summary 仍占一个物理页约 6.3%，且还要另外读取/缓存 summary pages；若一个候选仅 1–2 个 SSD 页，metadata lookup 和额外随机 I/O 可能抹平节省。
- page 切得更小可缩半径但增加 metadata 与 IOPS；切得更大可减 metadata 但放松 bound。这才是 Object 1/3 应形式化的核心 trade-off。

### 3.4 对 Object 2 的形式化审查

固定查询下，`Σ_i max` 对已读 vector/page 集合具有 monotone diminishing returns（适当定义空集基线后可视为 submodular）。但这**不自动推出 adaptive submodularity**：后者需要给出随机状态、观测模型和条件期望边际收益，并验证随观测递减。Claude 未定义这些对象，因此“这是 adaptive submodularity 问题”和“greedy 有常数竞争比”目前只是猜想。

对于 exact top-k，最直接的安全调度其实是 branch-and-bound/threshold execution：维护每个候选 `[LB,UB]`，读取能最大降低决策不确定性且单位 I/O 成本低的页。该框架本身并不新；只有 MaxSim-specific tight support metadata 与 SSD cost model 的结合可能新。

**本节判定：** partial-document bound 在特定 clusterable 页上可以 nontrivial；但 A0 没有证明真实 ColPali/ColBERT 页具备该条件。它满足“存在性”，不满足 PASS 所需的“有用 metadata-size separation”。

## 4. 与主要替代路线的机制对比

| 基线 | 跳过的单位 | 是否保留原始 exact MaxSim top-k | 已解决的主要成本 | 与候选方向的关系 | 是否构成简单 repackaging 风险 |
|---|---|---|---|---|---|
| Block-Max WAND | posting list 中的 docID blocks / documents | 对其加法检索模型是 safe exact | postings scoring 与 traversal | 同为小上界 + threshold + safe skip；算子和物理组织不同 | **高**：仅把 block 换成 SSD page 不够新 |
| MUVERA | 通过 FDE/MIPS 跳绝大多数 documents | 候选生成近似；候选内最终 exact MaxSim | candidate count | 让 `C` 显著变小；可直接接单向量 disk ANN | **中高**：若 exact stage 已小，本方向失去意义 |
| WARP/XTR | 未被 token retrieval 命中的 document tokens，以及完整 document gather | 否；含缺失相似度插补/近似 ANN | gathering、decompression、scoring | 已实现 query-token selective payload access | **高**：Object 2 若不要求 exact，基本被覆盖 |
| PLAID | 低 centroid score documents，避免其 residual 解压 | 最终候选 exact | candidate filtering、decompression | 已有 coarse summary → progressive prune → exact survivors | **高**：Object 1 若只有 centroid proxy，是 PLAID 的页内化 |
| HEAVEN | 绝大多数 pages、约 70% query tokens、最终又缩小候选 | 级联候选近似；最后小集合全 query MaxSim | 全语料 multi-vector FLOPs | 直接挑战 `C=1000–10000` 假设 | **高**：candidate-stage dominance |
| Token pruning/merging（Light-ColPali、SAP、CRISP） | 永久删除/合并 document vectors | 改变表示与得分；通常非 exact 原模型 | index bytes + all later I/O/compute | 与 partial read 可叠加，但先将 payload 缩小 8–35×/更多 | **中**：若贡献只剩“少读压缩 vectors”，系统意义弱 |
| TACHIOM | centroid-only gather 跳 token scoring；候选后读 PQ residual | 候选近似；最终 compressed full MaxSim | clustering、candidate、cache/PQ refine | 已有 document-contiguous PQ layout 与 streaming two-pass refine | **高**：Object 3 的普通布局部分已覆盖 |
| ESPN | 通过预取隐藏 whole-document SSD reads；可只 rerank 64–128 candidates | 全 1000 rerank 可 exact；partial candidate rerank 有 0.3–0.7% 损失 | SSD residency、critical-path I/O、batch bandwidth | 最接近 storage 系统；没有 intra-document certified page skipping | **最高的系统 prior**，但仍留 exact intra-object 空隙 |

**不是简单等价于 BMW 的部分：** MaxSim 对 SSD 页不是页分数相加，而是每个 query token 在所有页上取最大值；正确 UB 必须维护每 token 当前最大值和未读页 support envelope。BMW 的 block impact 是给离散 query term 的预计算标量，而这里的 `q` 是连续向量，通用 tight support metadata 难得多。因此“数学边界构造”确实不同。

**仍像 repackaging 的部分：** 一旦有了页上界，跨候选 threshold scheduling、先读高潜力页、summary/payload separation、contiguous packing 都是既有 branch-and-bound、late materialization、ESPN/PLAID/TACHIOM 思路的自然组合。粒度不同只能建立 problem distinction，不能单独建立 contribution novelty。

## 5. 不可替代的 storage-level contribution

当前唯一可能不可被上述工作替代的贡献是：

> **一个保持原模型 exact MaxSim top-k 的 SSD physical-page execution primitive：以经过向外舍入认证的、query-continuous page support envelopes 维护每个候选的 `[LB,UB]`；在所有候选之间按 bound-reduction-per-I/O 调度实际页读；并将 summary/payload 布局共同优化为最小 bytes、IOPS 与 completion cost。**

其不可替代性来自三个条件必须同时成立：

1. **exactness：** 不采用 XTR/WARP 插补，不改变/prune 原表示，不依赖 approximate candidate recall 来声明正确；
2. **intra-object physical I/O：** 不只是 PLAID/MUVERA/HEAVEN/ESPN 的 document-level candidate pruning 或预取；
3. **可证明的 metadata/benefit separation：** support metadata 远小于 payload，并在真实候选上于读完大多数页前收紧。

但 Claude 的三个 Objects 尚未交付这一贡献：Object 1 只有通用 ball bound，且原 UB 公式过松/可能不 sound；Object 2 未定义 adaptive stochastic model；Object 3 与 TACHIOM 的连续 PQ layout、ESPN 的预取调度及一般 late materialization 高度重合。**所以不可替代贡献目前只是可检验的窄命题，不是已成立结果。**

## 6. 独立 reviewer pass：对初稿的反向审查与修订

第二遍按“支持方最强反驳 / kill 方最强反驳 / 证据口径”逐条检查，得到以下修订：

1. **初稿曾过度依赖 HPC-ColPali 的 compression dominance。** 复核原文后发现 `512/1=32` 的明确算术错误和 query/document attention 叙述冲突，因此删除以 HPC headline 作决定性证据，改用 Light-ColPali、SAP、CRISP、ColBERTSaR 和 MM-Matryoshka 的独立证据。
2. **初稿若未加入 ESPN，会错误夸大 storage novelty。** ESPN 已直接做 SSD-resident multi-vector embedding retrieval、预取、early rerank 和候选数/带宽权衡；已将其列为最近 prior，并把 Object 2/3 新颖性下调。
3. **不能因 ESPN 已接近 DRAM latency 就直接 KILL。** ESPN 依赖 GPU/GDS、按 whole document 取 payload，视觉页面更大，且没有 exact intra-document bound；因此仍给窄贡献留空间。
4. **玩具例只能证明 bound 既可紧也可松，不能推断真实分布。** 报告已把结论限定为 existential，不把 synthetic 成功写成 viability 证据。
5. **Claude 的 65 ms SSD、4 ms CPU 数字不是实测 closure。** 250 MiB raw payload 在 7 GB/s 理想带宽下约 36 ms；若按 4 KiB/1M IOPS 则约 64 ms，实际取决于连续布局、queue depth、并行度和 dequant。报告不采用其中任一作为真实瓶颈结论。
6. **为何不是 KILL-ALGORITHM-REPACKAGING：** BMW/PLAID/ESPN 覆盖框架，但没有找到“连续向量 query 的认证 support envelope + exact intra-object SSD page skipping”实现。直接 KILL 会把不同 exactness contract 混为一谈。
7. **为何不是 PASS：** 没有真实页上的 bound tightness、没有压缩后 SSD 占比、没有 metadata lookup 成本，也没有 ordinary NVMe+CPU 下相对 ESPN/TACHIOM/级联的优势证据；PASS 的核心门槛全部未满足。

### HOLD 的唯一后续 profiling gate（不是实现授权）

若未来另行授权，只需一个最小公开数据 gate：在 **ViDoRe v2 的一个公开子集（建议 `esg_reports_v2`）** 上，用一个公开 ColPali-family checkpoint 和其真实 query workload，先以公开的 pooled/single-vector stage 固定 `K=256` 候选；分别对 FP16 full vectors 与至少一个可信压缩/merging operating point 记录 `candidate generation / metadata / payload SSD read / dequant+MaxSim / query encoding` 的 p50/p95 时间和实际 bytes/IOPS。继续本方向必须同时满足：

- 压缩后的 exact payload read 占端到端 p95 **至少 25% 且至少 5 ms**；
- centroid+radius 或同等大小（metadata ≤ payload 的 10%）的 sound bound 在保持原始 exact top-k 时，于读取 50% payload 前淘汰至少 50% candidate payload bytes；
- 相对“document-contiguous + read-all compressed payload”基线，计入 metadata 和调度后 p95 至少改善 20%。

任一不满足，则分别转为 `KILL-NO-STORAGE-BOTTLENECK` 或 `KILL-ALGORITHM-REPACKAGING`。本报告不授权执行该 gate。

## 7. 最终标签

证据支持一个很窄、可能新颖的 exact intra-object SSD execution contract，但 Claude 没有证明真实 bound 紧致性，也没有在 ESPN、现代级联和可信压缩之后证明 SSD 仍是显著瓶颈。方向不应实施，只应停在 profiling 门前。

**HOLD-NEEDS-PROFILING（superseded draft；不得执行）**

## 8. Post-review final disposition

Gpt 已在 `conversation/conversation_0720.md` 接受仓库同题真实 negative closure，并作出最终裁决：

```text
KILL-ALGORITHM-REPACKAGING
```

本节优先于上文草稿标签。后续不得实现或 profiling 相同的 exact page-bound、centroid/multi-ball synopsis、adaptive reading 或 layout 组合。
