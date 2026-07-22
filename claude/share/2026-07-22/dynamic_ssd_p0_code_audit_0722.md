# DynamicSSD-Maintenance P0 代码审计：跳过实验的理由

**日期：** 2026-07-22  
**裁决建议：** `KILL-DYNAMIC-SSD-MAINTENANCE`  
**方法：** 源码审计替代 characterization 实验，省 5–8 小时  
**审计基线：** PipeANN commit `9e7a193`

---

## 审计范围

| 模块 | 文件 | 行号 |
|------|------|------|
| 插入主路径 | `src/update/direct_insert.cpp` | 28-264 |
| 物理分配 | `src/ssd_index.cpp` | 742-823 |
| Page cache | `include/utils/page_cache.h` | 1-95 |
| Write-back 写入 | `include/aligned_file_reader.h` | 58-75 |
| 后台刷盘线程 | `src/update/direct_insert.cpp` | 267-301 |
| Lazy delete | `include/dynamic_index.h` | 523-531 |
| Full merge | `src/update/delete_merge.cpp` | 26-296 |
| In-place 替代路径 | `src/update/direct_insert.cpp` | 69-82 |

---

## Q1：插入写放大 — KILL-U，代码已回答

### 发现：默认 copy-on-write 重定位模型

PipeANN 默认的 `insert_in_place()` 并非"in-place"——每个被修改邻接表的邻居都被**整体复制到新 sector**：

```
insert 1 个新节点
  → greedy search 找到 R 个邻居
  → 对每个邻居：
      读取旧位置 → 追加新边 → memcpy 整个节点到新分配的 sector → 回收旧 sector
  → 写入新节点本身
  → bg_io_thread 逐任务刷盘
```

R=64 时，一次 insert 写 ~65 个 4KB sector ≈ **260KB/insert**。

### Page cache 不构成 coalescing 机会

- Write-back 模式：`wbc_write()` 写 cache，`bg_io_thread` 异步刷盘
- **没有跨 insert 的脏页合并**：每次 insert 是独立 task，bg_io_thread 按 task 逐个刷
- 唯一合并：同一 insert 内相邻 sector 拼接为单次 I/O（`direct_insert.cpp:129-141`）
- 没有 dirty flag、没有 LRU——仅 ref-counting，ref=0 即释放

### 替代路径已存在

编译宏 `IN_PLACE_RECORD_UPDATE`（`direct_insert.cpp:69-82`）直接在原位更新邻接表、不做重定位。写放大问题的解决方案已在代码中，只是非默认。

### 结论

写放大的主因是架构选择（copy-on-write vs in-place），不是 cache 效率。这是工程配置问题，不是需要实验发现的研究问题，不能支撑论文。Gpt 自己已将此轴排在最低优先级（"容易退化为通用 batching 优化"）。

---

## Q2：Physical Layout Aging — HOLD-L-SSD-TOO-SMALL

### 代码确认 fragmentation 不可避免

`alloc_loc()` 三级分配策略：

1. 回收页（`empty_pages` 队列，来自被重定位节点的旧位置）
2. Hint 页（搜索路径上有空位的页，提供一定局部性）
3. 文件末尾追加

每次 insert 的 R 个邻居被重定位到新位置（可能是回收页、hint 页或文件末尾），原始顺序布局被持续打散。动态更新后，相同逻辑搜索路径必然分散到更多物理 page。

### SIFT1M 太小，全部被缓存

```
节点大小：128d × 4B + R64 × 4B + overhead ≈ 768B
nnodes_per_sector = 4096 / 768 ≈ 5
总 sectors ≈ 200K × 4KB ≈ 800MB
```

机器可用内存远超 800MB。OS page cache + PipeANN 用户态 cache 会把整个索引缓存在内存中，"SSD page reads" 实际全部命中缓存，无法区分布局好坏。实验大概率命中 Gpt 自己设的 `HOLD-L-SSD-TOO-SMALL` gate。

### 升级条件

要验证 Q2，需要索引远超可用内存的数据集（SIFT100M/DEEP100M，索引 80–160GB），超出当前资源约束（10GB 数据上限、8h 时间墙、24GB RSS）。

### 补充

这是三个问题中唯一有潜在研究价值的方向。但即使在大数据集上成立，"relayout 恢复性能"在工程上等价于定期 offline rebuild，已是 DiskANN 标准做法。要发论文需要提出比 offline rebuild 更优的增量方案并证明其界。

---

## Q3：删除成本 — KILL-D，代码已回答

### Lazy delete 是纯内存操作

```
lazy_delete(tag)
  → deleted_nodes_set_.insert(tag)     // 内存 set
  → deleted_nodes_.push_back(tag)       // 内存 vector
  → mem_index_->lazy_delete(tag)        // 内存图标记
  // 没有任何磁盘写入，没有磁盘 tombstone
```

### 查询侧

在 `dynamic_index.h:457` 检查 `deleted_nodes_set_`（内存 set lookup）。搜索过程中删除节点**仍被遍历为中间跳板**（邻接表仍在图中），只是不返回结果。查询税 ≈ 删除比例 × 遍历概率 × page read。

### 没有局部 repair

PipeANN 不实现 Wolverine 式的 neighborhood repair。删除节点的邻居不会被重连。

### Merge 是全量顺序重写

`merge_deletes()`（`delete_merge.cpp:26-296`）：

```
Pass 1: 线性扫描所有 location → 给存活节点分配连续新 ID
Pass 2: 逐批读取 → 重映射邻接表 ID → 替换已删除邻居 → 顺序写入新文件
```

I/O 量 = 读全文件 + 写存活部分。SIFT1M ≈ 读写各 ~800MB。

### 成本结构

| 操作 | 成本 | 来源 |
|------|------|------|
| lazy_delete | ≈ 0 | 内存 set 插入 |
| 查询 tombstone 税 | 线性于删除比例 | 遍历删除节点但不返回 |
| 局部 repair | 不存在 | PipeANN 未实现 |
| full merge | O(N × node_size) | 全量重写 |

这是 LSM 系统中的已知模式（soft delete → scan penalty → full compaction），没有 ANN-specific 的未知。

---

## 总结

| 问题 | 代码能否回答 | 值得跑实验 | 理由 |
|------|:-:|:-:|------|
| Q1 写放大 | 完全 | 否 | copy-on-write 架构决定，in-place 替代已存在 |
| Q2 Layout Aging | 部分（现象必然存在） | 当前条件下否 | SIFT1M ≈ 800MB，全缓存；需 100M+ 数据集 |
| Q3 删除成本 | 完全 | 否 | 纯内存 soft-delete + 全量 merge，已知模式 |

**裁决建议：`KILL-DYNAMIC-SSD-MAINTENANCE`。**

1. Q1/Q3 从代码结构直接可得，不需要 characterization 实验。
2. Q2 在当前实验条件下无法验证。
3. 即使 Q2 成立，解决方案（定期 relayout）已是标准做法。
4. 三个轴都没有足够 novelty 支撑顶会论文。
