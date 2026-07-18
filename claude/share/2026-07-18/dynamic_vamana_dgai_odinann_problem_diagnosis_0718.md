> 该文件属于中间分析，其中相关机制解释已被M2/M3运行时证据推翻。

# DGAI vs OdinANN：实验指标驱动的问题诊断

基于五点轨迹（CP00→CP01→CP05→CP10→CP20）和 M0–M3 写归因实验的完整数据。

---

## DGAI 的问题

### P1. 无 Online Visibility：publish 前更新不可查询

五点轨迹中 DGAI 的 online visibility 始终标记为 unsupported。数据是 ingested 了，但在 merge/publish/reload 完成之前，任何查询请求都看不到新数据。

量化影响（CP20, 800K replacements）：
- Ingest: 768.2s → 数据进入系统
- Publish: 93.8s → 数据变为可查询
- **Visibility latency = 863.8s（E2E）**

对于需要亚秒级数据新鲜度的应用（如推荐系统、欺诈检测），这种架构从根本上不适用。OdinANN 的 online visibility 为 0.005s。

### P2. Publish 是固定成本瓶颈

M1 scale matrix 揭示 DGAI publish 写入量精确为 **6,005,336,152 bytes**，与 N（50K/100K/200K/400K）完全无关。这意味着：

| N | Ingest write | Publish write | Publish 占 E2E 比例 | E2E write/repl |
|---:|---:|---:|---:|---:|
| 50K | 1.325 GB | 6.005 GB | 81.9% | 149.3 KB |
| 100K | 2.466 GB | 6.005 GB | 70.6% | 91.5 KB |
| 200K | 6.080 GB | 6.005 GB | 49.7% | 61.4 KB |
| 400K | 15.113 GB | 6.005 GB | 28.4% | 52.8 KB |

小 batch 更新时，固定 publish 成本被分摊到少量 replacement 上，导致 per-replacement 成本极高。CP01 的 80K 更新实际 E2E 为 97.0 KB/repl，其中大部分是 publish。

**系统问题**：merge/rebuild 架构无法增量化——即使只改了 1 条记录，publish 仍需重写 ~6 GB。

### P3. QPS 稳定但 Recall 在温和退化

DGAI 的 merge/rebuild 每次都重建干净的图结构，所以 QPS 基本不随 churn 变化（L64: 1261→1236, -2.0%）。但 Recall 仍然在温和下降（L128: 0.9801→0.9763, -0.39%）。这意味着 merge 并没有完全恢复图质量——可能是因为 merge 只在当前 active set 上重建局部拓扑，而不是全局重建。

---

## OdinANN 的问题

### P4. Neighbor-Repair 写放大随规模增长

M1/M2 的核心数据：

| N | Neighbor-only bytes/repl | Temporal rewrite factor | Unique pages/repl |
|---:|---:|---:|---:|
| 50K | 128.6 KB | 1.244 | 31.4 |
| 100K | 150.5 KB | (M1 interpolation) | — |
| 200K | 167.7 KB | (M1 interpolation) | — |
| 400K | 176.7 KB | 4.999 | 43.1 |

每次 insert 固定调度 96 条邻居的潜在修复。随着 batch 变大，更多页面被重复触及（temporal rewrite 从 1.2 升到 5.0），导致实际物理写入量远超"新增修改"。而且这种重复是**广泛分布**的（92.71% 的 unique pages 被多次触及），不是少数热点，意味着：
- 简单的写缓存（只缓存热点页）不会有效
- Queue coalescing 也不行（M3 已 Kill，page lock 阻止了同页并发）

**系统问题**：in-place 修复的写入成本与 batch size 不是线性关系，而是因 temporal overlap 超线性增长。

### P5. 高 R 值是写放大的主要结构性来源

M2 乘法分解：OdinANN/DGAI 的 neighbor-repair page touch ratio：
- 50K: **3.000** × 1.596 × 1.199 = 5.741
- 400K: **3.000** × 0.668 × 2.512 = 5.036

第一个因子 3.000 直接来自 R=96/32。这是 **index 构建时的参数选择**，不是运行时算法的结果。但 R=96 也意味着更密的图、潜在更好的 Recall（OdinANN 用 L=29 就能匹配 DGAI L=64 的 Recall），所以 R 不是可以随意降低的——它是 Recall-Write 的 trade-off 参数。

**系统问题**：当前实现没有 write-aware 的 R 选择机制，也没有 adaptive degree 策略。R 在构建时固定，更新时被动承受其写入代价。

### P6. Publish 同样有大量固定成本

OdinANN publish 精确为 **8,480,136,500 bytes**（含 shadow copy），与 N 无关。其中包含一次 sendfile 复制整个 shadow tags 文件（32 MB）。Publish ratio 恒定 1.412×（vs DGAI）。

虽然 OdinANN 有 online visibility，但 **fresh-process visibility**（重启后可查询）仍需完整 publish/save。两种 visibility 的语义差距是：
- Online: 进程内 page cache，0.005s，非 crash durable
- Fresh-process: 磁盘持久化，CP20 需 254.2s

### P7. QPS 波动来源不明

五点轨迹中 OdinANN L29 QPS：1609→1629→1667→**1268**→1712

CP10 的 24% 下降在 CP20 完全恢复。M0–M3 没有定位根因。可能的因素包括：缓存状态、内存分配碎片、index 局部结构变化、NVMe 内部 GC。这种不可预测的 QPS 波动对 SLA 敏感的生产系统是一个可靠性问题。

---

## 两系统共享的结构性问题

### P8. 4 KiB 页粒度 RMW 的浪费

两系统都使用 4 KiB 页作为 I/O 单元。但记录大小分别只有 644 B（DGAI, 6/page）和 900 B（OdinANN, 4/page）。每次修改一条记录都需要读-改-写整个 4 KiB 页。

如果 R=32（644 B records），修改一个邻居意味着写 4096 B 中只有 644 B 是有效修改，空间效率仅 15.7%。

### P9. Target + Shared 精确 4096 bytes/replacement

M1 证明两系统的 target+shared-page 写入都精确为 4096 bytes/replacement——即插入点自身总是恰好一页。这部分没有系统间差异，也没有优化空间。差异全部来自 neighbor-repair。

### P10. 没有中间态：要么完全离线（DGAI），要么完全在线但高写入（OdinANN）

当前两系统代表了 visibility-write 光谱的两个极端：
- DGAI: 0 online visibility, 48 KB/repl write
- OdinANN: 即时 online visibility, 205 KB/repl write

没有系统探索中间态——比如：部分可见（只有 target 立即可查询，neighbor repair 延迟执行）、分层持久化（热数据立即写、冷数据批量写）、或者可调 freshness-write trade-off。

---

## 小结：哪些问题可能构成研究贡献

| 问题 | 严重性 | 是否已被文献覆盖 | 研究潜力 |
|---|---|---|---|
| P1 DGAI 无 online visibility | 高 | FreshDiskANN 尝试过增量方案 | 需 novelty check |
| P2 固定 publish 成本 | 中 | 可能被 lazy/incremental merge 覆盖 | 需 novelty check |
| P4 neighbor-repair temporal rewrite | 高 | 不确定是否有文献直接量化 | 有潜力 |
| P5 R 作为 Recall-Write trade-off | 中 | 图度数与性能的关系有文献 | 增量贡献 |
| P8 页粒度 RMW 浪费 | 中 | block-aware 布局有文献 | 需 novelty check |
| P10 visibility-write 没有中间态 | 高 | 这是系统设计空间的 gap | 最有潜力 |

Gpt 已经发出 novelty gate，Codex 即将对照 FreshDiskANN、IP-DiskANN、SVFusion 等文献判断这些问题是否已被占据。P10（visibility-write 中间态的缺失）和 P4（neighbor-repair 的 temporal rewrite 广泛性）是我认为最有可能通过 novelty check 的方向。
