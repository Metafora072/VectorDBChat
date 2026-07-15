# Insert cost closure instrumentation status

## 修改路径

- `repos/DGAI/include/rmw_profile.h`：增加 11 个互斥阶段、守恒字段及候选/写入计数器。
- `repos/DGAI/src/rmw_profile.cpp`：扩展逐 insert CSV，并在 `finish_insert` 计算 `stage_sum_us`、`stage_residual_us` 与 `closure_ratio`。
- `repos/DGAI/src/update/direct_to_topo_insert.cpp`：在真实 insert 路径布置阶段计时；修复旧 `position_seeking_us` 跨越 PQ/search/prune 的混计，并实际赋值 `topology_modify_cpu_us`。
- `repos/DGAI/src/search/rerank_search.cpp`：过滤 PQ 已可见但 topology/coordinate mapping 尚未提交的当前插入点，避免把未提交节点送入 graph expansion/exact rerank。
- `scripts/analyze_insert_cost_closure.py`：逐行检查 `Σ(stage) + residual = total`，失败即退出，并输出各 R 汇总。

## 计时阶段定义

一次 insert 被拆为 position seeking、topology acquisition、coordinate acquisition/rerank、exact distance、new-node candidate construction、new-node RobustPrune、reverse-link candidate construction、reverse RobustPrune、topology modification、submission/writeback、lock/allocation/copy/other，共 11 个互斥 wall-time 阶段。搜索内部按实测 search wall time守恒拆分；reverse-link candidate、prune 和 buffer mutation分别在调用边界计时。

## Closure 结果

在全新构建的 synthetic 128d、100K base 上，对 R=32/64/96/128 各执行 50 条单线程 insert，共 200 条。四档逐行守恒全部通过；各 R 的最小 closure 为 99.93%、99.93%、99.96%、99.96%，中位数为 99.97%–99.98%。`topology_modify_cpu_us` 在 200/200 条中非零，确认旧值为“未赋值”，不是实际成本为零。结果位于主项目 `experiment/results/insert_cost_closure/synthetic_sanity/`。

## 剩余 residual

四档最大 residual 分别为 13/18/29/31 μs，最差占比 0.07%，没有大块 unknown。该尾差来自阶段边界的时钟调用、计数/日志整理及 `finish_insert` 前后的薄层控制流；它已作为每行显式 residual 保存，没有被塞入任一研究阶段。

## perf 主热点

R64 的独立新索引上执行 50 insert，`perf record -F 999 -g --call-graph dwarf` 得到 6,364 个 samples、0 lost。可归因的 insert CPU 主热点是 `compute_pq_dists` 9.79%，其中 8.60% 位于 `delta_prune_neighbors_pq` 调用链；这与 timer 将 reverse RobustPrune/候选构造识别为主要 CPU 成本一致。整进程采样中 libgomp 启动/后台线程占比很高，因此该 perf 仅用于交叉验证调用栈，不作为阶段 wall-time 占比估计。

## 逻辑/物理 I/O 可区分性

当前可以区分 logical topology/coordinate update bytes、unique touched pages、cache hits/misses，以及提交到 host I/O 接口的 read/write pages 与 bytes；因此算法逻辑量和 host-submitted page I/O 可分开。它不能把 host submission 等同于最终介质 I/O，尚无 block-layer trace 来证明 device-completed bytes，正式实验若需要“设备物理 I/O”结论必须补 `blktrace`/eBPF 或等价块层观测。

## 正式实验所需数据与空间

正式门禁仍缺至少两套真实数据集，且要覆盖至少两个向量维度；每套需 base、连续 insert 流和 query/ground-truth（用于确认工作负载没有退化），并提供可复现的本地 manifest。还需冷缓存与稳定缓存、R=32/64/96/128 的独立索引副本。当前 synthetic 产物占 2.9 GiB；建议在原始真实数据之外预留至少 20 GiB 可写空间用于两套小/中型真实数据的四档索引、冷/热副本、CSV 与 perf。`/home/ubuntu/pz` 当前约 39 GiB 可用；NVMe 有约 1.7 TiB 空闲但当前只读，未经授权不能作为正式输出盘。

本结果只证明计时工具已达到 sanity 门禁，不支持选择 Idea，也不触发 Continue/Kill 研究裁决。正式矩阵在 PZ 提供真实数据路径或授权获取后再启动。
