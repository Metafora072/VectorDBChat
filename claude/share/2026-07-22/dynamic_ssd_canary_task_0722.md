# DynamicSSD-Maintenance Corrective Canary：Codex 任务规格

**日期：** 2026-07-22  
**前序：** Claude 源码审计 PASS（`dynamic_ssd_p0_code_audit_0722.md`），Gpt 修正三项后批准压缩版 canary  
**时间预算：** 2–4 小时（hard wall 4h）  
**工作目录：** `codex/work/2026-07-22/dynamic_ssd_maintenance_p0/`  
**结果报告：** `codex/share/2026-07-22/dynamic_ssd_maintenance_p0_results_0722.md`

---

## 0. 关键技术背景（源码审计已确认）

1. **O_DIRECT**：graph fd 使用 `O_DIRECT | O_LARGEFILE`（`linux_aligned_file_reader.cpp:646`），OS page cache 不参与 graph read。
2. **用户态 PageCache 是写缓冲**：`send_read()` 检查 cache 但 miss 时不回填；只有 `read_alloc` + `page_ref!=nullptr` 的写路径才回填。搜索时大部分读走真实 O_DIRECT。
3. **默认 insert 路径是 copy-on-write 重定位**：每个 insert 重定位 R 个邻居到新 sector（`direct_insert.cpp:211`）。编译宏 `IN_PLACE_RECORD_UPDATE` 为替代路径。
4. **alloc_loc() 三级分配**：回收页 → hint 页 → 文件末尾追加（`ssd_index.cpp:742-823`）。Hint 页提供一定局部性。
5. **lazy_delete 是纯内存操作**，没有磁盘 tombstone。`merge_deletes()` 是全量顺序重写。
6. **SECTOR_LEN = 4096**。SIFT1M（128d float32, R=64）约 5 nodes/sector，索引约 200K sectors ≈ 800MB。

---

## 1. 实验 A：Q2 Physical Layout Aging（主实验）

### 1.1 四种状态

在同一 SIFT1M 数据和 query 集上，构建四种索引状态：

| 状态 | 构建方式 |
|------|----------|
| S0 Static | 一次性静态构建 1M 向量 |
| S1 Insert | 静态构建 900K，动态插入 100K（+10%） |
| S2 Churn | 静态构建 1M，动态插入 100K 新向量，删除 100K 旧向量（保持 1M 活跃） |
| S3 Rebuild | 对 S1 的活跃向量集合做静态重建（same vectors, fresh layout） |

参数：R=64, Lbuild=96, Lsearch=96。**必须使用 DynamicSSDIndex 的真实 SSD 路径。**

### 1.2 搜索指标采集

对每种状态，用相同 query 集（前 1000 条）搜索，采集：

- Recall@10
- distance calculations（mean, p50, p95, p99）
- visited nodes（mean, p50, p95, p99）
- **distinct graph pages per query**（需 instrumentation：在 `send_read` 或搜索层记录每个 query 访问的 page ID 集合大小）
- **graph bytes read per query**
- **nodes per fetched page**（有效利用率）
- n_ios per query（已有 `QueryStats::n_ios`）
- latency p50/p95/p99

### 1.3 Instrumentation 需求

需要在搜索路径中添加 per-query page ID 追踪。建议方案：

- 在 `do_pipe_search` 或 `cached_beam_search` 中，收集每个 `send_read` 请求的 `(offset / SECTOR_LEN)` 到一个 per-query `std::unordered_set<uint64_t>`
- 搜索结束后记录 `set.size()` = distinct pages，`total_reads` = total page accesses
- 不修改更新路径，只在搜索路径添加统计

### 1.4 PASS 条件

```
PASS-L-PHYSICAL-AGING 当且仅当：
  S1/S2 vs S0：visited nodes 变化 < 5%
  S1/S2 vs S0：distinct pages/query 增加 > 10%（超过噪声）
  S3 vs S1：distinct pages/query 恢复到接近 S0 水平
```

如果 distinct pages 增加但 visited nodes 同步增加 → 不是 layout aging，是图质量问题。
如果 S3 relayout 不能恢复 → 不可归因于 physical layout。

---

## 2. 实验 B：Q1 Write Path A/B Trace（辅助）

### 2.1 对比

| 配置 | 说明 |
|------|------|
| COW（默认） | 不定义 `IN_PLACE_RECORD_UPDATE` |
| In-Place | 定义 `IN_PLACE_RECORD_UPDATE` |

在已建好的静态索引上，执行 1K 和 10K 次 insert，采集：

- 总 block writes（`iostat` 或 `strace` 统计 `pwrite/io_uring` 字节）
- distinct dirty pages
- 重复 page touches（同一 page 被多次写的次数）
- 时间分解：position-seeking / prune / RMW+flush

### 2.2 注意

- 如果 `IN_PLACE_RECORD_UPDATE` 路径无法编译或运行不稳定，记录原因即可，不强制修复
- 不需要多种子，单次运行足够
- 目标是量化 COW vs in-place 的写放大差异，不是证明 page coalescing 机会

---

## 3. 实验 C：Q3 Tombstone & Merge（辅助）

### 3.1 Tombstone 查询税

从同一静态索引开始，lazy_delete 不同比例的节点（0% / 5% / 10%，uniform random），然后搜索：

- visited deleted nodes per query
- distinct pages per query
- Recall@10
- latency

### 3.2 Merge 成本

对 10% tombstone 状态执行一次 `merge_deletes()`/`final_merge`，记录：

- 读取字节
- 写入字节
- wall time
- merge 前后 distinct pages/query 变化

### 3.3 注意

- 如果 `final_merge` 在 SIFT1M 上超过 30 分钟，降低数据量或减少 tombstone 比例
- 不实现 page-local compaction，只量化

---

## 4. 执行纪律

- **必须使用 DynamicSSDIndex 的真实 SSD 路径**
- 所有大文件写入 `/dev/nvme8n1` 对应数据目录
- RSS ≤ 24 GiB，新增数据 ≤ 10 GiB
- 保留现有 page cache、write coalescing 和正常 flush 语义
- 不得关闭 cache 或逐边 fsync 制造结果
- 不设计新算法
- 实验 A 是主实验，B/C 是辅助；A 必须先完成
- 如果 SSD 路径有 bug 无法完成某项，标记 `HOLD-SSD-BUG` 并详细记录

---

## 5. 输出

### 5.1 主报告

`codex/share/2026-07-22/dynamic_ssd_maintenance_p0_results_0722.md`

包含：
1. 环境、commit、hash
2. Instrumentation 说明（添加了什么计数器、在哪里）
3. 实验 A 数据表（四种状态的完整指标对比）
4. 实验 B 数据表（COW vs in-place）
5. 实验 C 数据表（tombstone + merge）
6. 限制和未完成项
7. **一个主裁决**

### 5.2 允许的裁决

```
PASS-L-PHYSICAL-AGING
PASS-D-PAGE-LOCAL-OPPORTUNITY
KILL-DYNAMIC-SSD-MAINTENANCE
HOLD-MEASUREMENT-CLOSURE
```

### 5.3 机器可读产物

```
codex/work/2026-07-22/dynamic_ssd_maintenance_p0/
  results/
    layout_aging.jsonl
    write_path.jsonl
    deletion_cost.jsonl
    summary.json
  logs/
  patches/
```
