# P01 + P07 A0 实验结果

**日期：** 2026-07-22  
**执行者：** Claude（Codex 子智能体未返回直接结果，Claude 自行执行）

---

## P01: PQ Codebook Staleness — HOLD-NEEDS-STRONGER-SHIFT

### 实验设计
- SIFT1M 拆分：700K build / 300K insert（自然顺序）
- 测量 PQ 重构误差 BUILD vs INSERT，两种 PQ：128-chunk 和 32-chunk

### 结果

**128-chunk PQ（DiskANN 搜索用，1 dim/chunk）：**
- 误差比率 2.15×，但绝对值 ~0.01 L2²（占 1-NN 距离 0.0000%）
- PQ recall@10 = 1.0000（BUILD 和 INSERT 均无差异）
- **结论：比率存在但影响为零**

**32-chunk PQ（4 dims/chunk）：**
- 误差比率仅 1.011×（几乎无差异）
- PQ recall@10：BUILD NNs 0.8247 vs INSERT NNs 0.7991（差 2.56pp）
- 2.56pp 差异可能来自图位置差异而非 PQ 过时

### 根因
SIFT1M 自然序 700K/300K 拆分的分布偏移极小（centroid shift / spread = 0.09）。同分布数据上 PQ codebook 不会过时。

### 裁决：HOLD-NEEDS-STRONGER-SHIFT
需要真正的分布偏移场景测试（synthetic shift 或跨域数据集）。

---

## P07: Page Bonus — KILL-NO-PROBLEM

### 实验设计
- SIFT1M full 1M 构建 DiskANN disk index（R=64, 5 nodes/sector）
- 解析 disk layout 的 sector→node 映射 + 图邻接表
- 图分析：co-resident 节点对是否为图邻居
- 搜索分析：1000 queries 的贪心搜索模拟，统计 bonus 节点效用

### 结果

**图分析（200K sectors, 2M co-resident pairs）：**

| 关系 | 占比 |
|------|------|
| 1-hop 图邻居 | **0.32%** |
| 2-hop 图邻居 | 3.97% |
| 无关 | 95.71% |

**搜索分析（1000 queries）：**

| 指标 | 值 |
|------|-----|
| 平均 visited nodes/query | 372 |
| 平均 sectors read/query | 370 |
| 平均 bonus nodes/query | 1,475 |
| Bonus 在 GT-100 中 | **0.03%** |
| Bonus 在后续 beam 中 | **0.31%** |
| 潜在 I/O 节省 | **1.29%** |

### 根因
DiskANN graph-order layout（BFS from medoid）将 BFS 序相邻的节点放在同一 sector。但 BFS 的同一层包含来自数据空间各区域的节点——它们共享"离 medoid 的图距离"，不共享空间近邻性。因此 co-resident 节点对查询无用。

### 裁决：KILL-NO-PROBLEM
- 0.32% 的 1-hop 共驻率仅比随机放置高 12×，绝对值极低
- 0.03% 的 GT-100 命中率意味着 bonus 节点几乎无搜索价值
- 1.29% 的 I/O 节省远低于 10% 的 PASS 阈值

---

## 综合

| 候选 | A0 裁决 | 下一步 |
|------|---------|--------|
| P01 PQ Staleness | HOLD-NEEDS-STRONGER-SHIFT | 需在真正分布偏移场景重测 |
| P07 Page Bonus | **KILL-NO-PROBLEM** | 终止 |
