# DENSE-OPQ-KERNEL-GATE-A0

## 目标

判断 GIST1M-960D 实验中观测到的约 `1.14 ms/query` OPQ rotation，究竟主要来自 OPQ 稠密变换本身，还是来自当前 DiskANN 查询路径的朴素实现。

当前代码审计已经确认：`FixedChunkPQTable::preprocess_query()` 使用逐查询 `std::vector<float>` 临时分配、普通双重循环和最终 `memcpy`；该热路径没有调用 MKL/BLAS，也没有显式 SIMD kernel。因此这轮只建立优化后的 dense-OPQ baseline，不设计 structured/Fast-OPQ。

## 冻结条件

复用现有 GIST1M-960D OPQ32 artifacts：

- 同一 100K training rows；
- 同一 OPQ rotation、centroid、codebook 和 codes；
- 同一 byte-identical graph；
- 同一 W=4、K=10、zero node cache、full-vector rerank；
- 不重新训练 OPQ，不重新构图，不修改 ADC、图搜索或 SSD I/O 路径；
- 单查询实验固定单 CPU 线程，`MKL_NUM_THREADS=1`、`OMP_NUM_THREADS=1`。

## 实现版本

### V0：DiskANN Native

保留当前 `preprocess_query()`，作为实测约 1.14 ms/query 的原始对照。

### V1：Loop + Reusable Scratch

只做实现级修正：

- 交换循环顺序，使 rotation matrix 内层连续访问；
- 使用 thread-local / query scratch 输出缓冲；
- 移除逐查询 heap allocation；
- 输出直接留在 PQ scratch，避免无意义的额外复制；
- `-O3 -march=native`，保留编译器 vectorization report。

### V2：MKL SGEMV

单查询调用单线程 `cblas_sgemv`，严格复用同一个 rotation matrix 和 centering 语义。不得启用隐式多线程。

### V3：Batch SGEMM，仅作吞吐上界

对 batch={8,32,128} 使用单线程或明确记录线程数的 SGEMM。该版本只说明批量查询场景的矩阵复用潜力，不与单查询尾延迟混为一谈。

## 正确性门禁

在固定查询集上比较 V0/V1/V2 的旋转输出：

- 报告 max absolute error、relative L2 error；
- 检查 NaN/Inf；
- 保持相同 OPQ artifacts；
- 端到端报告 Recall 和返回结果差异，不强求浮点累加顺序导致的 bit-identical；
- 若数值误差异常或需要修改图搜索语义，立即停止该版本。

## 测量矩阵

### Kernel microbenchmark

维度：

```text
D={128,768,960,1536}
```

其中 960D 使用实际 GIST rotation；其他维度可使用固定 seed 的正交矩阵，只用于复杂度和实现扩展性测量。

报告：

- mean / p50 / p95 rotation latency；
- cycles、instructions、IPC；
- GFLOP/s 和有效 matrix bandwidth；
- 临时分配次数与额外复制；
- batch SGEMM 的 queries/s。

### End-to-end frozen-graph search

只在实际 GIST1M-960D OPQ32 上运行：

```text
V0 / V1 / V2
× L={50,100,200,400,800}
× full 1K queries
× exactly two complete repeats
```

一次 index load 内批量运行所有 L。报告两次原始结果，不因单点漂移补第三次。

报告：

- Recall@10；
- reads/query、comparisons/query；
- QPS、p50、p99；
- rotation-only latency；
- rotation 占 p50 的比例；
- 假设 rotation 为零时的端到端理论上界，用于判断 structured transform 的最大可获收益。

## 裁决边界

这轮只回答 dense OPQ 实现是否已经足够快。

```text
若 V1/V2 将 960D rotation 大幅压低，且在 L>=200 时 rotation 只占很小比例，
同时“零 rotation”理论上界也无法带来有意义的端到端改善：
KILL-UNOPTIMIZED-OPQ-AS-RESEARCH-MOTIVATION
KILL/LOW-PRIORITY-STRUCTURED-FAST-OPQ

若经过单线程优化后，rotation 在目标高维、低/中 L 或高 QPS 场景仍是主要组成，
且零 rotation 上界显示仍有明显端到端空间：
PASS-DENSE-OPQ-BOTTLENECK
HOLD-STRUCTURED-FAST-OPQ-CANDIDATE
```

不得因为 kernel 自身快很多就自动 PASS；必须观察端到端收益上界。

## 时间与资源

预计：

- 实现与编译：20–40 分钟；
- kernel benchmark：10–15 分钟；
- GIST 端到端两次完整重复：15–25 分钟；
- 审计与报告：10–15 分钟。

```text
Expected wall time: 60–90 minutes
Hard wall: 120 minutes
GPU: 0
New NVMe: < 200 MB
```

超过 hard wall 时停止扩展测试，保留已完成的正确性和 kernel 结果，不自行加入 structured transform、Hadamard、Butterfly 或新量化器。
