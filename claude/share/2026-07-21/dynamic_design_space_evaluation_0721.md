# 动态 SSD Graph ANN：算法/系统设计区间评估

**Date:** 2026-07-21 17:15
**Author:** Claude

---

## 0. 先回答问题：系统论文 vs 算法论文

**都不必做"纯"的。** 这个领域 2024–2026 发表最多的形态是 **"一个核心算法 idea + 工程实现 + 端到端评估"**：

| 论文 | 核心贡献 | 系统/算法占比 |
|------|---------|-------------|
| Wolverine (VLDB 2025) | 单调路径修复算法 | 算法 70% / 系统 30% |
| Greator (VLDB 2026) | 拓扑感知局部更新 | 算法 60% / 系统 40% |
| SPFresh (SOSP 2023) | LIRE 增量再平衡协议 | 系统 60% / 算法 40% |
| OdinANN (FAST 2026) | Direct insert 策略 | 系统 70% / 算法 30% |
| NAVIS (PVLDB 2027) | Position-seeking 瓶颈消除 | 算法 50% / 系统 50% |
| Quake (OSDI 2025) | Cost-model 驱动自适应 IVF | 系统 50% / 算法 50% |

**这些论文都不需要 GPU。** 都是 CPU + SSD，与 PZ 环境完全匹配。

---

## 1. PipeANN 现有更新能力（源码确认）

PipeANN 已有 `v2/` 模块：

| 组件 | 状态 | 细节 |
|------|------|------|
| `DynamicSSDIndex` | ✅ 已实现 | insert / lazy_delete / final_merge / checkpoint |
| `direct_insert.cpp` | ✅ 已实现 | OdinANN 式 in-place 插入：position seeking → prune → RMW 写回 |
| `delete_merge.cpp` | ✅ 已实现 | Tombstone 删除 + 离线 merge（sector-by-sector 重写） |
| `page_cache.h` | ✅ 已实现 | 用户态 page cache，write-write 缓冲 |
| `lock_table.h` | ✅ 已实现 | 细粒度 page-level 锁 |
| `journal.h` | ⚠️ 骨架 | RocksDB WAL 全注释掉，只剩 cuckoo hash map，无持久性 |

**关键观察——PipeANN 的更新是"能用但粗糙"的：**

1. **插入时写放大严重**：插入一个节点要 RMW 所有邻居所在的 page（`direct_insert.cpp:80-130`），每个邻居 = 1 个 4KB page RMW，即使只改 4 bytes 的邻居 ID
2. **删除是全量 merge**：`delete_merge.cpp` 做 sector-by-sector 重写整个索引，没有增量 compaction
3. **无 page 重排 / 局部性维护**：`grep` 确认没有 reorder/relayout/defrag 相关代码
4. **无图质量监控**：没有 navigability/recall 退化检测

**这意味着：PipeANN 是一个很好的"有更新能力但没有更新优化"的 baseline。** 任何更新路径的优化都能直接在上面做，且有 clear before/after 对比。

---

## 2. 现有工作的精确覆盖边界

### NAVIS (PVLDB 2027，SNU) — 最新最强

**做了什么：**
- 识别出 position seeking（为新节点找邻居的搜索）占插入时间 85%，浪费向量读取占 44%
- 三个算法：(1) 向量与边表解耦存储，减少无效向量读取；(2) 收敛感知投机重排（CASR），PQ 距离引导的向量选择性加载；(3) 动态入口图增量维护
- 2.74x 插入吞吐，1.37x 并发搜索吞吐

**没做什么：**
- **只处理插入，不处理删除**（论文明确说"deletion is comparatively benign"，只是 sketch 了一个方案）
- **没有 page 局部性维护**——解耦存储 + out-of-place 写避开了问题但没解决
- **没有 compaction / 图质量退化分析**
- **没有写放大量化模型**

### Wolverine (VLDB 2025，NUS) — 删除修复

**做了什么：**
- 单调搜索路径修复：删除节点后添加 in-edges→out-edges 的新边，保证搜索单调性
- Wolverine++ 限制在 2-hop 内修复，11x 删除吞吐

**没做什么：**
- **纯内存工作**，不考虑 I/O
- **不处理 page 局部性**
- **不处理长期图质量退化**（只做局部修复）

### Greator (VLDB 2026，NTU) — 拓扑感知更新

**做了什么：**
- 通过轻量图拓扑（不加载向量）快速定位受影响节点
- 细粒度块减少更新时的 I/O 浪费

**没做什么：**
- **不处理 page 局部性退化**
- **不处理 compaction**
- **在内存和 SSD 上都评估了，但 SSD 上的特定优化有限**

### LSM-VEC (arXiv 2025) — LSM 式更新

**做了什么：**
- 第一个把 LSM-tree 的 out-of-place 更新语义引入向量搜索
- 跨 level 的 HNSW 图，compaction 合并相邻 level

**没做什么：**
- **只有 HNSW 不支持 Vamana/DiskANN 式图**
- **跨 level 搜索开销大**（需要探测多个 level）
- **88.4% recall 在 50/50 工况下仍不理想**

### Navigability-Signal (IEEE Data Bulletin 2026) — 图质量监控

**做了什么：**
- 提出 probe-recall 信号检测图质量退化（Spearman ρ~0.95 与真实 recall）
- 证明 signal-triggered 修复 Pareto 优于固定周期修复

**没做什么：**
- **只是指标论文**，没有提出具体修复系统
- **没有在 SSD 上验证**
- **不处理 page 局部性**

---

## 3. 明确的算法/设计空白（按可行性排序）

### ⭐ 空白 A：SSD 图索引的 I/O 感知更新调度

**问题**：当前所有 SSD 图索引的更新是"逐个处理"的——收到一个 insert/delete 就立即执行。没有人做 **batch-aware scheduling**：把一批更新按 page 局部性排序/分组后一起执行，减少 page RMW 次数。

**为什么是算法贡献**：
- PipeANN 的 `direct_insert` 每插入一个节点要 RMW ~R 个 page（R=64→64 次 4KB RMW）
- 如果一批 insert 的邻居落在同一 page 上，只需 RMW 一次
- 最优调度是 NP-hard（类似 disk scheduling），但可以设计近似算法
- OdinANN 的 direct insert vs FreshDiskANN 的 batch merge 是两个极端，中间有巨大设计空间

**已验证 NAVIS 的 position seeking = 85% 开销**。但 NAVIS 解决的是"如何更快地找到邻居"，不是"如何更高效地写入这些邻居"。写入路径的优化（batch RMW、page-grouped flush）完全开放。

**设计区间**：
- Micro-batch：积累 B 个 insert，按目标 page 排序，共享 page RMW
- Workload-aware：根据 insert 到达率和 page locality 自适应调整 batch 大小
- 延迟-吞吐 trade-off：立即插入 vs 攒批写入的 Pareto 最优

### ⭐ 空白 B：Page 局部性退化的量化与增量修复

**问题**：SSD 图索引花大量时间做 build-time layout optimization（DiskANN 的 graph ordering，PipeANN 的 page search），但插入/删除后局部性持续退化，**没有人量化退化速率**，也没有增量修复方案。

**为什么是算法贡献**：
- 定义 page locality metric（例如：搜索时 unique page 数 / 总访问节点数）
- 建立 "更新量 → 局部性退化 → recall/IOPS 退化" 的定量模型
- 设计增量 page 重排算法：识别"最差"的 K 个 page，做局部 swap/migrate
- 确定触发阈值：何时局部修复，何时全量重建

**设计区间**：
- Metric：page entropy、page hit ratio、avg page fan-out
- 在线检测：piggyback 在搜索上的采样（类似 navigability-signal）
- 增量修复：page-level swap（最小 I/O 单位）vs sector-level migration
- 触发策略：固定阈值 vs 代价模型（修复 I/O cost vs 搜索 I/O 节省）

### ⭐ 空白 C：SSD 图索引的删除路径优化

**问题**：NAVIS 明确跳过了删除，Wolverine 只在内存做。SSD 上的删除有独特问题：
- Tombstone 积累导致搜索遇到大量无效节点 → 额外 page read
- Merge（如 PipeANN 的 `delete_merge`）是全量重写 → 写放大爆炸
- 没有"增量删除整理"——介于 tombstone 和全量 merge 之间的方案

**为什么是算法贡献**：
- Wolverine 的单调路径修复搬到 SSD 上需要 I/O-aware 改造
- 核心算法挑战：修复边需要读邻居的邻居信息，每一步 = page read。如何 plan 修复操作使 page reuse 最大化？
- Lazy vs eager repair 的 cost model

**设计区间**：
- I/O-aware path repair：把 Wolverine 的 2-hop 修复按 page 分组
- Page-level tombstone compaction：只重写 tombstone 超过阈值的 page（而非全量 merge）
- Background vs foreground repair：搜索线程 piggyback 顺带修复 vs 专用后台线程

### 空白 D：统一代价模型

**问题**：给定一个 update 流（insert rate、delete rate、query rate），系统应该做什么？目前没有代价模型回答：
- 何时积累到一定量再 batch write？
- 何时触发局部 page 重排？
- 何时触发 page-level compaction？
- 何时不得不全量 rebuild？

**这是系统贡献多于算法贡献**，但代价模型本身有算法设计。类似 Quake (OSDI 2025) 对 IVF 做的 cost-model-guided maintenance，但面向图索引 + SSD。

---

## 4. 具体方向建议

### 推荐组合：空白 A + B + C → 一篇论文

**标题方向**："I/O-Efficient Maintenance for Dynamic SSD-Resident Graph Indexes"

| 贡献 | 类型 | 对标 |
|------|------|------|
| Batch-aware update scheduling | 算法 | 对标 NAVIS（只优化了读，没优化写） |
| Page locality degradation metric + 增量修复 | 算法+实验 | 对标 Navigability-Signal（只有指标，没有修复） |
| I/O-aware delete repair | 算法 | 对标 Wolverine（内存→SSD 搬迁） |
| 在 PipeANN 上的端到端实现 | 系统 | PipeANN 有更新但无优化 → clear baseline |

**为什么可行**：
1. **不需要 GPU**：纯 CPU + SSD
2. **基础设施就绪**：PipeANN `v2/` 已有 insert/delete/merge，在上面改进而非从零搭建
3. **算法为主**：核心贡献是三个算法，不是系统架构。系统只是评估载体
4. **实验清晰**：before/after 在同一系统上，控制变量干净
5. **Baseline 充足**：OdinANN（direct insert）、FreshDiskANN（batch merge）、NAVIS（优化 position seeking）、Wolverine（内存删除修复）

**为什么有 novelty**：
- NAVIS 优化了更新的**读路径**（position seeking），但写路径完全没碰
- Wolverine 做了删除修复但**不考虑 I/O cost**
- 没有人把 page locality maintenance 做成**在线增量**的
- 没有人在 SSD 图索引上做 **batch-aware update scheduling**

### 备选：空白 B 单独 → 一篇短论文或 workshop

如果精力有限，单独做 page locality degradation quantification + incremental repair 也可以作为 VLDB/SIGMOD 短论文或 workshop 论文。这个贡献足够 self-contained。

---

## 5. 风险评估

| 风险 | 严重度 | 应对 |
|------|--------|------|
| NAVIS 后续工作覆盖写路径优化 | 中 | NAVIS 团队是 SNU，目前论文完全没讨论写优化。但 PVLDB 2027 = camera-ready 还没出，有时间差 |
| Greator 团队扩展到 SSD page locality | 中 | Greator 目前无 page 局部性代码，但方向自然 |
| 效果不明显 | 低 | PipeANN 的 RMW 写放大是结构性的（每 insert ~R 次 4KB RMW），batch 优化应该有 clear gain |
| 工程量 | 中 | PipeANN `v2/` 已有框架，不是从零开始。估计 2-3 月实现+评估 |

---

## 6. 与 PZ 定位的匹配

| 维度 | 评分 |
|------|------|
| FAST/VLDB 契合度 | ★★★★★（SSD + 图索引 + 更新 = 存储系统核心话题） |
| 无 GPU 可行性 | ★★★★★ |
| PipeANN 基础设施利用 | ★★★★★（直接在 v2/ 上改进） |
| 学术 novelty | ★★★★（写路径优化 + page 局部性增量维护 = 明确 gap） |
| 实验可行性（1M–100M） | ★★★★（1M 做开发调试，100M 做最终评估，硬件足够） |
| 与 ACL 方向独立性 | ★★★★★（不绑定任何特定应用场景） |
