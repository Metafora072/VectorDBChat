# 路径二扩展：ANNS/向量数据库全域方向扫描

日期：2026-07-12

## 前提变更

PZ 将目标从"驻盘图 ANN 的 FAST/VLDB 论文"扩展为"ANNS/向量数据库相关的任何系统或算法+系统贡献"，目标会议包括 AI 会议（NeurIPS/ICML/ICLR/KDD/WWW/MLSys 等）。这大幅扩展了可探索的设计空间。

## 优先方向

### E1：RAG 系统的向量索引层

**核心问题：** 检索增强生成（RAG）是 2024–2026 最主要的向量搜索使用场景，但当前向量索引被当作黑盒 API 调用。真实 RAG pipeline 有独特的系统需求：

- **Freshness SLA**：知识库持续更新，索引必须在 SLA 内反映变更。这不是简单的 dynamic insert——涉及 chunk 重分割、embedding 重算、旧向量失效。
- **多粒度索引**：paragraph-level、sentence-level、passage-level chunk 策略需要不同粒度的索引，或可能需要 hierarchical retrieval。
- **上下文相关检索**：对话历史影响 retrieval query，静态 kNN 不是最优目标。
- **端到端质量度量**：RAG 的质量不只是 recall@k，还包括 downstream generation quality。这可能改变 index 的优化目标。
- **Token 成本意识**：检索到的 chunk 被送入 LLM context，有 token 成本。最优检索不是"最多相关文档"而是"最小 token 下达到 generation quality threshold"。

**PZ 适配度：高。** 索引更新、多层存储、freshness/consistency 与 PZ 的存储系统背景直接相关。

**初步 prior art 识别（需 Codex 验证）：**
- RAPTOR (2024)：hierarchical chunk clustering + multi-level retrieval
- Self-RAG (2024)：learned retrieval decision
- CRUD-RAG (2024)：更新场景下的 RAG
- Milvus/Qdrant/Weaviate 的 RAG 集成（工程实践）

**为什么 AI 会议适合：** RAG 是 NeurIPS/ICML/KDD/WWW 的热门主题，系统化的索引设计在这些会议的 systems track 非常受欢迎。

---

### E2：向量搜索的学习化组件

**核心问题：** 当前 ANN 系统的关键决策（beam width、entry point、neighbor pruning、termination）使用启发式规则。ML 可以学习这些决策：

- **Learned beam width**：根据 query difficulty 动态决定搜索宽度，避免 easy query 浪费计算和 hard query 质量不足
- **Learned entry point selection**：替代随机或 medoid entry，学习 query-specific entry
- **Learned pruning/routing**：在 graph traversal 中学习哪些 neighbor 值得扩展
- **Learned termination**：学习何时停止搜索（当前固定 beam exhaustion 或 iteration limit）
- **Learned index structure selection**：根据 data/query 特性自动选择 IVF/HNSW/Vamana/DiskANN 配置

**PZ 适配度：中高。** 更偏算法，但如果聚焦在 disk-based system 上的 learned decision（例如 learned I/O scheduling），系统味道增强。

**初步 prior art 识别：**
- RoarGraph (VLDB 2025)：heterogeneous graph for out-of-distribution queries
- NHQ (VLDB 2023)：learned quantization-aware graph
- LIDER (PVLDB 2024)：learned index routing
- Quake (OSDI 2025)：online workload-aware index adaptation

**AI 会议适合度：** 非常高。Learned index 是 NeurIPS/ICML 的经典主题。

---

### E3：面向 LLM 推理的近似搜索

**核心问题：** LLM serving 产生了新的 ANN 使用场景，约束与传统向量搜索不同：

- **KV cache 检索**：长上下文 LLM 的 attention 可以用 ANN 近似（检索与 query token 最相关的 key-value pairs）。约束：sub-millisecond latency、per-token 频率、在 GPU 上运行。
- **Speculative decoding**：draft model 的 candidate token 检索可以用 embedding space ANN 加速。
- **Embedding cache / model routing**：多模型部署下，根据 query 选择最合适的模型或缓存命中的 embedding。
- **Prompt cache / semantic dedup**：相似 prompt 的 KV cache 复用，本质是 ANN-based cache lookup。

**PZ 适配度：中。** 偏 GPU/ML 系统，但 cache 管理和存储分层与 PZ 背景有交叉。

**初步 prior art：**
- Quest (2024)：KV cache 的 attention selection
- H2O (2023)：Heavy-Hitter Oracle for attention
- InfLLM/MInference (2024)：long-context attention 优化
- CacheGen (2024)：KV cache compression and storage

**AI 会议适合度：** 极高。LLM serving 是当前最热的系统主题。

---

### E4：ANN 在数据管理系统中的深度集成（原方向 A 扩展）

**核心问题：** 同方向 A，但扩展到不限于 disk-resident graph——包括 in-memory vector index 与 OLAP/OLTP 系统的整合。

**PZ 适配度：高。** 存储引擎级工作。

**目标会议：** VLDB/SIGMOD/CIDR。

---

### E5：向量搜索 Benchmark / Characterization（原方向 C）

**核心问题：** 2023–2026 大量新系统缺乏统一的跨系统 characterization。

**PZ 适配度：中高。** 已有实验基础设施可复用。

**目标会议：** FAST/ATC/VLDB（测量论文）。

---

## 优先排序

**E1 > E2 > E3 > E4 > E5**

E1 (RAG 索引层) 最值得优先验证：它处在 AI 研究的最热交叉点，系统需求真实且 PZ 的存储/索引背景直接适用，且当前 RAG 系统论文多关注 pipeline 设计和 prompt engineering，对索引层的系统化研究相对稀缺。关键风险是 RAG 赛道太热，可能已有大量未发表的工作。

E2 (learned components) 是算法+系统混合方向，AI 会议接受度高，但需要 ML 实验能力。

E3 (LLM serving) 极热但竞争也极激烈，且偏 GPU 系统。

**所有方向都必须经过 Codex prior-art 扫描后才能判断。**
