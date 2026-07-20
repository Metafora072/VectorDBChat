# 复合向量查询研究地图：场景、Baseline、现有工作与候选机会

## 1. 当前阶段的目标

当前不要急着确定具体系统机制，也不要把方向直接定义为“通用复合查询优化”。

“复合查询”覆盖的范围非常大。如果目标是支持任意 SQL 谓词、任意 Boolean expression、任意索引与执行方式，系统会迅速演化成一个通用查询优化器，范围难以控制，也容易依赖大量启发式规则。

但目前同样不适合过早限制为某一个固定模板，例如只研究：

```text
tenant + ACL + time
```

更合理的推进方式是先做一轮开放式研究：

1. 从实际系统需求出发，统计现实中常见的复合向量查询；
2. 分析每类查询的数据分布、谓词性质和 SSD 执行瓶颈；
3. 整理基础执行方案以及现有论文、系统的覆盖情况；
4. 找出场景真实、现有方法存在明显缺口、设计空间充足的查询族；
5. 再从中选择一到两类查询，围绕其稳定结构设计专门系统。

当前关注的底层背景仍然是：

- 大规模向量数据；
- SSD 驻盘图 ANN；
- 内存中只能保存有限的压缩向量、拓扑或元数据；
- 查询成本主要来自随机 SSD I/O、距离计算和图遍历；
- 系统可能同时面对向量、图拓扑和属性更新。

本轮讨论先扩开思路，不采用过于严格的 KILL 标准。只要候选方向具备真实场景、自洽故事、充分动机、充足设计点和可量化收益，就值得保留并继续分析。

---

## 2. 首先需要回答的问题

### 2.1 现实中有哪些复合向量查询

不要只从现有论文支持的语法反推需求，应优先从真实应用出发调查，例如：

- 企业 RAG；
- Agent 长期记忆与工作空间；
- 商品与视觉搜索；
- 推荐系统；
- 代码搜索；
- 日志与可观测性平台；
- 多媒体搜索；
- 地理位置搜索；
- 文档、邮件与知识库搜索；
- 安全与权限控制搜索；
- 数据库中的向量检索算子。

对每个场景，需要提取其稳定出现的查询结构，而不是只列一个抽象 SQL 示例。

### 2.2 哪些查询足够典型

“典型”不应只凭直觉判断。建议按证据等级记录：

#### A 级：强典型

同时满足多项：

- 跨两个或更多实际领域出现；
- 有真实产品接口或系统文档；
- 有公开数据集、benchmark 或 workload；
- 有多篇论文专门讨论；
- 查询结构在应用中稳定出现。

#### B 级：场景成立

- 有明确应用动机；
- 有部分产品、论文或数据证据；
- 公开 workload 不够充分，或只集中在单一领域。

#### C 级：理论上可见

- 主要由论文构造；
- 缺少真实使用证据；
- 很难获得代表性数据或查询分布。

“典型程度”与“研究潜力”必须分开记录。某类查询可能非常常见，但已有工作已经处理得很好；另一类查询可能稍窄，但存在显著 SSD 系统问题。

### 2.3 现有方法在哪里失效

对每类查询都要回答：

- Post-filter 为什么慢；
- Pre-filter 在什么情况下退化；
- In-filter 是否破坏图连通性；
- 是否需要大量非法节点作为路由桥梁；
- 是否需要扩大候选集合才能返回足够的 top-k；
- 是否产生大量无效 full-vector SSD 读取；
- 是否需要专用图、专用分区或组合索引；
- 多谓词是否引起索引组合爆炸；
- 属性更新是否带来维护写放大；
- 全局选择率是否足以预测查询难度；
- 相同全局选择率下，局部数据分布是否导致完全不同的执行成本。

---

## 3. 第一轮需要覆盖的复合查询族

本轮先广泛统计，暂不提前排除。

### 3.1 多个离散标签合取

```text
VectorTopK(q)
WHERE tenant = 17
  AND language = Chinese
  AND document_type = paper
```

可能场景：

- 多租户 RAG；
- 文档搜索；
- 商品搜索；
- 推荐系统；
- 代码搜索中的 repository、branch、language；
- 日志搜索中的 service、environment、severity。

需要分析：

- 多个低成本 bitmap 谓词能否直接求交；
- 属性间相关性是否导致独立选择率估计失效；
- 合法节点在图中是否聚簇；
- 过滤后的子图是否断裂；
- 专用 filter-aware graph 是否会产生组合爆炸。

---

### 3.2 字段内 IN / OR 与字段间 AND

```text
VectorTopK(q)
WHERE tenant = 17
  AND type IN {paper, manual, report}
  AND language IN {Chinese, English}
```

这种查询在实际系统中很常见，但其单独创新价值可能有限。

需要确认：

- 字段内 OR 是否可以简单映射为 bitmap union；
- 字段间 AND 是否只是 bitmap intersection；
- 真正瓶颈是否仍然出现在 ANN 图遍历和 SSD full-vector 读取；
- 它是否更适合作为其他查询族中的基本组成部分。

---

### 3.3 类别属性 + 单个数值或时间范围

```text
VectorTopK(q)
WHERE category = shoes
  AND price BETWEEN 300 AND 800
```

或：

```text
VectorTopK(q)
WHERE tenant = 17
  AND timestamp >= T
```

典型场景：

- 商品类别与价格；
- 新闻类型与时间窗口；
- 文档租户与创建时间；
- 日志服务与时间；
- 代码仓库与 commit time；
- 图片类别与拍摄时间。

需要分析：

- 单范围查询已有工作是否充分；
- 类别与范围联合后，是否出现新的图连通性问题；
- 页级 category mask、min/max summary 能否减少 SSD 页读取；
- 滑动时间窗口是否引入摘要维护成本；
- 范围宽度变化是否导致最优执行策略切换。

---

### 3.4 多个类别属性 + 范围

```text
VectorTopK(q)
WHERE tenant = 17
  AND document_type IN {paper, manual}
  AND language = Chinese
  AND timestamp >= T
```

典型场景：

- 企业 RAG；
- Agent 工作空间；
- 文档、邮件与知识库搜索；
- 多租户内容检索；
- 推荐系统。

需要重点调查：

- 多谓词联合选择率；
- 属性间相关性；
- 查询局部选择率；
- 通用 Marker、bitmap 或 summary 的空间成本；
- SSD 图环境下，元数据应附着在拓扑、PQ 还是 full-vector 层；
- 现有多谓词 ANN 工作是否主要面向内存；
- 动态属性更新时，辅助索引和摘要维护是否昂贵。

---

### 3.5 Tenant + ACL membership + time/type

```text
VectorTopK(q)
WHERE tenant = current_tenant
  AND current_user IN ACL
  AND type IN {policy, manual}
  AND timestamp >= T
```

典型场景：

- 企业知识库；
- 私有 RAG；
- Agent 私有工作空间；
- 代码、邮件、文档权限搜索；
- 多用户协作系统。

这类查询不能简单视为多个普通标签 AND：

- tenant 通常是单值、低成本、容易 bitmap 化；
- ACL 是高基数集合成员判断；
- 每个对象的 ACL 可能不同；
- ACL 可能频繁变化；
- 最终权限判断不能出现错误授权；
- 近似摘要可以允许 false positive，但最终必须精确验证；
- ACL 精确验证可能需要额外内存访问或 SSD 读取。

需要调查：

- 公开论文是否真正模拟真实 ACL 分布；
- ACL 是否被简单退化成普通 label；
- 高基数 membership 与 SSD ANN 联合执行是否存在缺口；
- 动态权限变化是否造成 bitmap、summary 或 Marker 更新放大；
- 是否可以利用 tenant、ACL、type、time 的层次结构做专门设计。

---

### 3.6 多个数值范围联合

```text
VectorTopK(q)
WHERE price BETWEEN p1 AND p2
  AND timestamp BETWEEN t1 AND t2
```

或：

```text
WHERE distance <= r
  AND rating >= x
  AND time BETWEEN t1 AND t2
```

可能场景：

- 商品搜索；
- 推荐系统；
- 日志搜索；
- 地理与时间联合搜索；
- 多媒体检索。

需要分析：

- 多维范围分区是否产生组合爆炸；
- 多个 min/max summary 是否足够；
- 属性间相关性是否导致大量假阳性页；
- 单属性 range-aware graph 是否能扩展；
- 多范围动态更新时如何维护布局与摘要；
- 实际 workload 中这类查询是否足够高频。

---

### 3.7 地理范围 + 类别 + 时间

```text
VectorTopK(q)
WHERE category = restaurant
  AND geo_distance(location, center) <= 5km
  AND open_time contains now
```

可能场景：

- 本地生活搜索；
- 地图与 POI；
- 图片和事件搜索；
- 推荐系统。

需要分析：

- 地理谓词是否需要独立空间索引；
- 空间索引与 ANN 图联合执行是否会扩展为通用多索引优化问题；
- 是否存在稳定、可专门利用的页面与布局结构；
- 该方向是否偏离当前 SSD 驻盘图主线。

---

### 3.8 商品类别 + 价格 + 库存 + 地区

```text
VectorTopK(q)
WHERE category = shoes
  AND price BETWEEN 300 AND 800
  AND stock > 0
  AND region = current_region
```

这类查询具有明显的动态属性：

- 库存频繁变化；
- 价格会更新；
- 地区可售状态变化；
- 类别较稳定。

需要分析：

- 静态与动态属性混合时，索引应该如何分层；
- 高频动态属性是否适合写入图节点摘要；
- 属性更新是否会导致大量随机小写；
- 是否可以只对稳定谓词做布局，对动态谓词采用增量层；
- 查询时如何联合稳定与动态元数据。

---

### 3.9 代码搜索复合查询

```text
VectorTopK(q)
WHERE repository = current_repo
  AND branch = current_branch
  AND language IN {C, C++}
  AND path NOT IN test/*
  AND commit_time <= checkpoint
```

典型场景：

- 代码 Agent；
- IDE 语义搜索；
- 历史版本检索；
- Repository-aware RAG。

需要分析：

- repository、branch、path 与向量空间通常高度相关；
- commit time 具有版本语义；
- 分支更新和代码提交频繁；
- 查询可能只需要当前 snapshot；
- 是否存在可利用的层次结构：repo → branch → path → commit；
- 这种层次化查询是否比通用多谓词更适合专门设计。

---

### 3.10 日志与可观测性查询

```text
VectorTopK(q)
WHERE service = payment
  AND environment = production
  AND severity >= warning
  AND timestamp BETWEEN t1 AND t2
```

特点：

- 时间范围几乎总是存在；
- 数据持续追加；
- 老数据逐渐冷却；
- service、environment 较稳定；
- severity 和时间具有一定相关性；
- 查询具有明显时间局部性。

需要分析：

- append-only 数据是否允许更高效的分段布局；
- 时间分段与图 ANN 如何联合；
- 热段、冷段是否使用不同索引；
- 多段检索与 top-k 合并是否成为主要瓶颈；
- 是否存在比通用 filtered ANN 更清晰的系统故事。

---

### 3.11 Dense + sparse + metadata

```text
TopK(
    α · dense_similarity
  + β · sparse_score
)
WHERE tenant = 17
  AND timestamp >= T
```

典型场景：

- RAG；
- 搜索引擎；
- 代码搜索；
- 企业知识库。

该查询同时涉及：

- Dense ANN；
- Sparse inverted index；
- Metadata filter；
- Top-k score fusion。

需要单独记录，但不要与 metadata-filtered ANN 混为一谈。

需要判断：

- 是否会把范围扩展到多路索引和通用 top-k 融合；
- 是否仍然能够锚定 SSD 存储路径；
- 是否存在稳定、非启发式的专门结构；
- 是否适合当前项目资源与时间。

---

### 3.12 Vector search + relational join

```sql
SELECT ...
FROM documents d
JOIN permissions p ON d.id = p.doc_id
WHERE p.user_id = ?
ORDER BY vector_distance(d.embedding, q)
LIMIT k;
```

这种查询真实存在，但会涉及：

- Join order；
- Cardinality estimation；
- ANN operator；
- Top-k pushdown；
- 通用数据库查询优化。

应当调查并明确其边界。除非发现非常清晰的 SSD ANN 专门问题，否则不建议作为当前主线。

---

## 4. 基础执行方案与 Baseline

对每类查询至少分析以下执行方案。

### 4.1 Post-filter

```text
普通 ANN 搜索
→ 获取更大的候选集合
→ 执行精确谓词验证
→ 返回 top-k
```

需要记录：

- 候选扩大倍数；
- full-vector SSD 读取量；
- 无效候选比例；
- 返回不足 k 的概率；
- 高选择率与低选择率下的退化情况。

### 4.2 Pre-filter + exact scan

```text
属性索引得到合法集合
→ 对合法向量做精确距离计算
→ 选出 top-k
```

适合候选集合非常小时。

需要记录：

- 候选数量；
- 精确向量读取量；
- 属性索引访问成本；
- 从低选择率到高选择率的拐点；
- SSD 顺序性或随机性。

### 4.3 Pre-filter + subset ANN

```text
属性索引得到合法集合
→ 在合法子集上执行 ANN
```

需要分析：

- 是否需要临时子图；
- 是否需要为常见过滤条件维护专用图；
- 查询组合增多后是否发生索引爆炸；
- 子图连通性与更新成本。

### 4.4 Strict in-filter

```text
图遍历时只扩展满足谓词的节点
```

需要分析：

- 图连通性损失；
- recall 下降；
- 合法节点是否形成孤岛；
- 属性—向量相关性对结果的影响。

### 4.5 Graph tunneling / bridge traversal

```text
非法节点可以承担路由作用
但尽量避免读取其完整向量或将其作为结果
```

需要分析：

- 非法桥接节点价值；
- 拓扑、PQ、full-vector 分层存储；
- 路由时需要哪些信息；
- 何时停止扩展非法节点；
- 是否依赖预算或启发式阈值。

### 4.6 Filter-aware graph

```text
构建阶段增加跨过滤集合的连接
```

需要分析：

- 支持哪些谓词；
- 是否需要提前知道过滤条件；
- 多谓词组合是否导致构建和空间爆炸；
- 动态属性更新时如何维护；
- 是否适合 SSD 布局。

### 4.7 Bitmap / inverted index + graph

需要分析：

- bitmap union/intersection 成本；
- bitmap 是否常驻内存；
- 高基数 membership 的表示；
- 候选集合与图遍历如何交互；
- 属性更新写放大。

### 4.8 Range partition / range-aware graph

需要分析：

- 单范围与多范围；
- 固定窗口与滑动窗口；
- 分区数量；
- 跨分区查询；
- 动态数据插入；
- 多属性组合空间。

### 4.9 Page-level metadata summary

例如每个 SSD 图页维护：

```text
category mask
tenant summary
min/max timestamp
Bloom filter
ACL sketch
```

需要分析：

- 摘要大小；
- false-positive rate；
- 对 SSD 页读取的实际减少；
- 属性相关性；
- 动态维护成本；
- 摘要应附着于图页、向量页还是独立页；
- 页面布局与邻居聚集方式。

### 4.10 分阶段或不同精度谓词执行

例如：

```text
cheap approximate check
→ graph traversal
→ expensive exact verification
```

需要分析：

- 哪些谓词允许近似预检查；
- false positive 与 false negative 语义；
- ACL 等安全谓词如何保证最终正确；
- 多阶段验证是否减少 SSD I/O；
- 是否出现额外随机读取。

---

## 5. 现有论文与系统调研范围

需要尽可能覆盖以下类别和代表工作。

### 5.1 Filtered graph ANN

- Filtered-DiskANN；
- ACORN；
- 其他 filter-aware graph 或 predicate subgraph 工作。

### 5.2 Range-filtered ANN

- UNIFY；
- SeRF；
- Window Search；
- 其他 range-aware graph、range partition 或 window ANN 工作。

### 5.3 SSD filtered ANN

- GateANN；
- PipeANN-Filter；
- 其他面向驻盘图和 SSD I/O 的工作。

### 5.4 Multi-predicate 与 general attribute filtering

- EMA；
- 支持 categorical + numerical 的工作；
- 支持 AND、OR、range 和 membership 的工作。

### 5.5 Query planning 与 workload characterization

- Learning-based filtered query planning；
- Global/local selectivity；
- Attribute-vector correlation；
- Filtered ANN benchmark；
- 查询难度建模。

### 5.6 工业系统

至少调查：

- Milvus；
- Qdrant；
- Weaviate；
- Pinecone；
- Vespa；
- pgvector；
- Elasticsearch / OpenSearch；
- 其他公开说明 filtered vector search 执行方式的系统。

---

## 6. 现有工作能力矩阵

建议整理以下字段：

| 字段 | 说明 |
|---|---|
| 工作或系统 | 论文、开源项目或产品 |
| 基础索引 | HNSW、Vamana、IVF、分段图等 |
| 数据驻留位置 | DRAM、SSD、混合 |
| 类别谓词 | equality、IN、多标签 |
| 范围谓词 | 单范围、多范围、时间窗口 |
| Membership | ACL、高基数集合成员 |
| 多谓词 | categorical + numerical 等 |
| Boolean 形式 | AND、OR、有限表达式、任意表达式 |
| 向量更新 | 插入、删除、修改 |
| 属性更新 | 是否支持，维护代价 |
| 执行方式 | pre/post/in-filter、tunneling、专用图 |
| 辅助索引 | bitmap、inverted list、Marker、summary |
| 内存开销 | 拓扑、标签、辅助结构 |
| SSD 空间开销 | 图、向量、额外索引 |
| 构建成本 | 时间、峰值内存 |
| 更新成本 | 延迟、写放大、后台维护 |
| 适用区间 | 选择率、相关性、查询类型 |
| 报告收益 | QPS、延迟、I/O、recall |
| 数据集 | 真实或合成 |
| 是否开源 | 复现难度 |
| 主要局限 | 对应潜在机会 |

特别注意：

- “支持多谓词”本身不能直接作为创新点；
- “支持动态更新”本身也不一定足够；
- 需要区分向量更新、属性更新、辅助摘要更新和统计漂移；
- 查询开始前选择执行计划与查询中途调整属于不同问题；
- 内存图上的收益不一定能直接迁移到 SSD；
- 专用图的构建成本和维护成本必须纳入评价。

---

## 7. 现实查询需求地图

建议每个查询族记录以下内容：

| 字段 | 说明 |
|---|---|
| 查询族 | 规范名称 |
| 表达式 | Vector Top-k + metadata predicates |
| 原子谓词 | equality、IN、range、membership 等 |
| 组合形式 | AND、字段内 OR、多个范围等 |
| 真实场景 | RAG、商品、代码、日志等 |
| 场景证据 | 产品接口、论文、数据集、benchmark |
| 典型程度 | A、B、C |
| 研究潜力 | 高、中、低 |
| 全局选择率 | 典型范围 |
| 局部选择率 | 查询邻域内的合法比例 |
| 向量—属性相关性 | 聚簇、随机、反相关等 |
| 谓词间相关性 | 独立、正相关、负相关 |
| 属性基数 | 低、中、高 |
| 更新特征 | 静态、低频、高频、append-only |
| 判断成本 | bitmap、集合验证、额外 I/O |
| 正确性语义 | 是否允许 false positive/negative |
| SSD 难点 | 无效读、图断连、页放大等 |
| 现有最佳方法 | 相关 baseline |
| 未解决问题 | 候选机会 |

---

## 8. 不要只按查询语法分类

相同语法形式可能具有完全不同的系统性质。

例如：

```text
tenant = 17
```

和：

```text
current_user IN ACL
```

都可以表示为过滤条件，但它们不同：

| 特征 | Tenant | ACL membership |
|---|---|---|
| 属性形式 | 单值 | 高基数集合 |
| 判断成本 | 低 | 中到高 |
| Bitmap 表示 | 容易 | 可能昂贵 |
| 更新频率 | 较低 | 可能较高 |
| 允许近似判断 | 可作为剪枝 | 只能允许 false positive，最终必须精确验证 |
| 数据局部性 | 可能与向量聚簇 | 可能高度离散 |
| 安全语义 | 普通过滤 | 不能错误授权 |

调研中还要记录：

- 谓词判断便宜还是昂贵；
- 是否适合 bitmap；
- 是否能做页级摘要；
- 是否允许 false positive；
- 是否允许 false negative；
- 是否高基数；
- 是否具有层次结构；
- 属性是否与向量空间相关；
- 合法节点是否形成孤岛；
- 是否需要额外 SSD 读取验证；
- 更新是否会造成随机小写和维护放大。

这些性质可能比 SQL 表达式本身更能决定设计方向。

---

## 9. 候选设计空间

本轮不要只围绕“自适应 planner”讨论，可以开放考虑以下方向。

### 9.1 针对某类典型查询设计专用索引或布局

例如：

- Tenant + ACL + time；
- Category + range；
- Append-only log + time range；
- Repository + branch + commit。

重点是利用查询族的稳定结构，而不是支持任意表达式。

### 9.2 多谓词 page-level summary

研究：

- 多个类别 mask；
- 范围 min/max；
- ACL Bloom/sketch；
- 摘要压缩；
- 页剪枝；
- 页面内节点重排；
- 动态维护。

### 9.3 不同谓词承担不同角色

区分：

- 结果合法性谓词；
- 图路由辅助谓词；
- 页读取剪枝谓词；
- 最终精确验证谓词。

例如非法节点可能不能成为结果，但可以作为图路由桥梁。

### 9.4 高基数 ACL 与低基数标签联合执行

研究：

- Tenant 先过滤；
- ACL 近似预检查；
- 精确授权验证；
- 时间和类型页摘要；
- 动态权限 delta；
- 安全语义。

### 9.5 滑动时间窗口

研究：

- 时间分段；
- 热冷索引；
- 过期段淘汰；
- 时间摘要；
- 查询窗口变化；
- 图与时间布局的协同。

### 9.6 多范围组合

研究：

- 多维 summary；
- 分区组合爆炸；
- 属性相关性；
- false-positive 页；
- 多维 range-aware traversal。

### 9.7 属性与向量相关性

研究：

- 相同全局选择率但不同局部分布；
- 合法节点聚簇与反相关；
- 查询局部图结构；
- 无效桥接节点；
- 图路由预算。

### 9.8 专用图的组合爆炸与维护问题

研究：

- 常见查询模板；
- 共享基础图；
- 轻量 overlay；
- 动态属性变化；
- 局部重构；
- 多租户索引共享。

### 9.9 拓扑、PQ 与 full vector 分离后的谓词附着位置

研究：

- 谓词放在内存拓扑；
- 谓词放在 PQ entry；
- 谓词放在 SSD 图页；
- 谓词独立存储；
- 不同层的空间和 I/O 权衡。

### 9.10 多 NVMe 执行

研究：

- 按谓词候选密度调度；
- 按页有效率调度；
- 按查询阶段调度；
- 多盘并行 graph traversal；
- 元数据索引与向量数据分盘；
- 负载平衡。

### 9.11 动态属性维护

研究：

- Bitmap delta；
- Summary delta；
- Marker 更新；
- 批量合并；
- 版本一致性；
- 查询期间的旧摘要安全性；
- 写放大。

### 9.12 复合查询的稳定层次结构

某些场景具有天然层次：

```text
tenant → repository → branch → path → commit
```

或：

```text
tenant → ACL → document type → time
```

可以研究这种层次是否允许比通用 Boolean planner 更稳定、更有原理的执行结构。

---

## 10. 评价指标

不能只看最终 QPS。

### 10.1 查询结果

- Recall@k；
- 返回不足 k 的比例；
- 过滤正确性；
- ACL 等安全谓词的精确性。

### 10.2 查询性能

- QPS；
- p50、p95、p99 latency；
- 单查询 CPU 时间。

### 10.3 SSD 行为

- SSD reads/query；
- SSD bytes/query；
- full-vector reads/query；
- 平均请求大小；
- IOPS；
- 随机读放大；
- 多盘并行度。

### 10.4 图行为

- Visited nodes；
- Expanded nodes；
- Invalid bridge nodes；
- Valid candidate yield；
- Local selectivity；
- 候选队列增长；
- 路由失败或图断连情况。

### 10.5 谓词执行

- Predicate checks/query；
- 各原子谓词执行次数；
- Bitmap/inverted index 访问；
- 近似检查 false-positive rate；
- 精确验证次数。

### 10.6 索引与维护

- 构建时间；
- 峰值内存；
- DRAM 常驻空间；
- SSD 额外空间；
- 向量插入/删除代价；
- 属性更新延迟；
- 维护写放大；
- 后台合并成本。

### 10.7 稳定性

需要改变：

- 全局选择率；
- 查询局部选择率；
- 向量—属性相关性；
- 谓词间相关性；
- 谓词数量；
- 查询范围宽度；
- 更新比例；
- 热点分布。

---

## 11. Claude 与 Codex 的讨论任务

Claude 和 Codex 分别独立完成第一轮分析，再互相评议。

每一方至少给出：

1. 复合查询分类草案；
2. 各查询族的真实场景；
3. 典型程度证据；
4. 查询的数据与系统性质；
5. 基础 baseline 及其退化点；
6. 相关论文和工业系统；
7. 现有工作的覆盖边界；
8. 最有潜力的 3～5 类查询；
9. 每类查询可能产生的系统瓶颈；
10. 可探索的设计点；
11. 最适合先做的 profiling 或 A0 实验；
12. 对另一方结论的补充、质疑或反驳。

讨论原则：

- 不要过早 KILL；
- 不要只因为已有工作支持某种语法就判断问题已解决；
- 不要把“支持多谓词”直接当作创新；
- 不要只罗列论文名称；
- 必须分析 SSD 环境中的具体数据路径；
- 必须区分查询支持、索引代价、更新代价和性能稳定性；
- 优先寻找具有稳定结构、可做专门优化的典型查询；
- 允许提出较开放的系统构想，后续再逐步收敛。

---

## 12. 希望形成的最终产物

### 表一：现实复合查询需求地图

目标是回答：

> 现实中哪些查询最值得研究？

### 表二：现有工作能力与缺口矩阵

目标是回答：

> 每类查询已经被解决到什么程度，还剩下什么问题？

### 候选方向排序

对每个候选给出：

- 场景强度；
- 现有工作覆盖程度；
- SSD 特有问题；
- 设计空间；
- 实现难度；
- 数据与 benchmark 可获得性；
- 潜在效果；
- 风险。

最终希望得到以下形式的判断：

```text
查询族 A：
场景非常典型，但已有工作处理充分，不作为主线。

查询族 B：
场景典型，现有方法主要面向内存，SSD 驻盘问题明显，保留。

查询族 C：
单谓词已有优化，但多谓词导致页面剪枝和维护成本问题，重点关注。

查询族 D：
故事成立，但缺少真实 workload 和数据证据，暂时降级。
```

只有完成这张研究地图后，再决定是否锚定：

- 多类别 + 时间范围；
- Tenant + ACL + time；
- 多范围联合；
- 日志 append-only + time；
- 代码仓库层次查询；
- 或其他更有潜力的复合查询族。
