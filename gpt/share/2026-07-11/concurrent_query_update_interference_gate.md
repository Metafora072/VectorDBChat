# 动态驻盘图索引：并发查询/更新 SSD 干扰门禁

## 当前状态

正式冻结当前 insert-path 优化平面，包括：

* topology write；
* deferred write；
* append-only adjacency；
* coordinate acquisition；
* PQ/heap/visited；
* maintenance debt；
* query/update locality transfer；
* write-set constrained relayout。

这些方向保留为已完成的阴性证据，不再继续拆解或变形。

下一候选问题是：

> 当动态驻盘图索引在同一 SSD 上并发执行查询和更新时，更新产生的读取、写回及突发提交是否会系统性破坏查询的吞吐和尾延迟；这种干扰是否跨越不同索引架构，并且无法由普通静态 I/O 隔离充分解决？

当前只批准问题验证，不批准 SSD scheduler、优先级队列或任何正式系统设计。

---

## 核心研究边界

需要区分四类原因：

1. SSD 队列和介质层干扰；
2. CPU、内存带宽或 PQ 计算竞争；
3. 图锁、位置映射锁或应用内部同步；
4. 应用缓存污染或后台线程调度。

只有第一类在至少两个不同架构中占主要解释力，并且普通隔离手段不能恢复主要损失，才可能形成存储系统问题。

---

## P0：跨系统现象复现

第一阶段只使用：

* DGAI；
* OdinANN；
* SIFT-128；
* 900K base；
* 固定索引参数；
* 数据与结果全部放在 NVMe。

暂不加入第二数据集，也不修改索引算法。

### 工作负载

分别测量：

```text
query-only
update-only
query + update concurrently
```

查询使用 open-loop offered load，至少覆盖：

* query-only 饱和点以下的轻载；
* 中载；
* 接近饱和但仍稳定的高载。

更新率从低到高扫描，直到达到 update-only 的稳定吞吐范围。不能只用一个固定 query/update 比例。

查询和更新线程固定 CPU affinity，避免线程漂移；每个点自适应重复，直到主要指标置信区间收敛。

### 指标

应用层：

* query throughput；
* p50/p95/p99 query latency；
* update throughput；
* update latency；
* recall；
* timeout/失败率。

设备与系统层：

* read/write IOPS；
* read/write bandwidth；
* outstanding queue depth；
* block-layer read/write latency；
* request size 分布；
* submit/completion burst；
* CPU utilization；
* context switches；
* lock wait；
* page/cache hit 信息；
* 各线程运行时间。

### P0 通过条件

只有以下现象在 DGAI 和 OdinANN 中同时成立，才进入因果隔离：

* 并发运行产生稳定、超出运行噪声的 query throughput 或 p99 degradation；
* 退化随 update offered load 呈可重复趋势；
* 不是 recall 或参数变化导致；
* 两个系统不要求数值完全相同，但应存在同方向的服务曲线。

若只在一个系统成立，或退化只出现在系统已经完全饱和的无意义负载点，立即 Kill 跨系统叙事。

---

## P1：因果隔离

P0 通过后，使用以下对照拆分原因。

### CPU-only shadow update

执行与更新近似相同的：

* PQ 计算；
* candidate/prune；
* metadata 操作；

但不提交真实 SSD I/O。

用于判断 CPU 和锁竞争可以解释多少退化。

### I/O-only replay

根据真实更新 trace 重放相同的：

* read/write request size；
* arrival time；
* queue depth；
* burst pattern；

但不执行图锁和算法计算。

用于判断设备干扰是否足以复现查询退化。

### 同设备与分离设备对照

若有第二块独立物理 SSD：

* query 与 update 共用设备；
* query 与 update 分离设备。

若没有第二设备，使用 query-only/update-only service curve 建立无干扰上界，并明确这只是分析上界，不能伪装成物理隔离实验。

### 因果门禁

只有 SSD/device queueing 能解释混合负载性能损失的主要部分，才继续。

如果 CPU-only shadow 或锁竞争已经复现大部分退化，则这是索引内部并发问题，不进入 SSD-aware 系统方向。

---

## P2：普通方案排除

在提出新机制前，必须测试最强简单基线：

* 固定 update rate cap；
* 固定 update concurrency；
* 限制 update queue depth；
* query-first 静态优先级；
* Linux `ioprio`；
* cgroup I/O bandwidth/IOPS 控制；
* query/update 使用独立 submission queue；
* 简单时间片隔离。

同时报告 query 和 update 的 Pareto frontier，不能只保护 query 而隐藏 update throughput 损失。

### Kill 条件

出现任一情况即停止：

1. 两个系统无法稳定复现干扰；
2. 主要原因是 CPU、锁或缓存；
3. 只在设备完全饱和后发生；
4. 静态限速、优先级或 queue-depth 控制已恢复大部分可恢复性能；
5. 查询改善完全来自牺牲同等或更大的更新吞吐；
6. 不同系统需要完全不同的原因解释；
7. 最终方案只能是普通 I/O priority queue、rate limiting 或 cgroup 参数调节；
8. 现象只在单一线程数或单一 query/update 比例下存在。

“恢复大部分性能”需要相对于无干扰上界计算，不允许只报告相对于最差 baseline 的提升。

---

## 可能的系统假设边界

只有 P0–P2 全部通过后，才允许讨论以下类型的系统假设：

> 动态 ANN 更新由多个具有依赖关系的 I/O 阶段构成，静态优先级无法在保护查询尾延迟的同时保持更新进度，因此需要理解 graph-operation phase 和未来 I/O burst 的联合 admission/scheduling。

这只是可能的机制形态，不是当前获批设计。

系统贡献必须明显区别于：

* 普通读优先；
* deadline scheduler；
* cgroup 限速；
* 固定 queue depth；
* 批量写回；
* 前后台线程隔离。

---

## 实验推进顺序

```text
P0：两系统、单数据集复现
    ↓
P1：CPU / lock / SSD 因果隔离
    ↓
P2：普通隔离方案排除
    ↓
第二数据集验证
    ↓
Gpt + Claude novelty / systems review
    ↓
决定是否形成正式 Idea
```

在 P0 失败时，不进入 P1；在 P1 失败时，不测试 scheduler；在 P2 被简单方案解决时，不继续包装论文。

---

## Codex 产物

第一阶段只发布：

```text
codex/share/concurrent_query_update_interference_p0.md
```

内容包括：

* 两个系统的 harness 与版本；
* query/update offered-load 定义；
* 单独与并发 service curves；
* p99、throughput 与 recall；
* CPU、lock 和 block-layer 初步指标；
* 置信区间；
* Continue / Reframe / Kill。

P0 前不得设计新 I/O scheduler，也不得把 NAVIS 的 27.89% 数字直接当作本机问题已成立。
