# 并发查询与更新干扰 P0 报告

## 裁决

本轮裁决为 **Kill 跨系统 SSD 干扰候选**，不进入 P1 因果隔离，也不测试 scheduler、优先级或限速方案。DGAI 在 9 个 mixed workload 点中没有出现稳定 query p99 退化，平均变化范围为 −3.0%～+1.7%；OdinANN 在相同归一化负载结构下出现 +296.0%～+2402.4% 的 p99 放大。两个系统既没有同方向 service curve，也不需要同一种原因解释，直接触发 P0 Kill 条件。

OdinANN 的现象也不支持直接解释为 SSD(Solid State Drive，固态硬盘) queue interference。其 p50 只变化 −0.6%～+4.8%，query throughput、update throughput 与 recall 基本不变；p99 放大时 NVMe(Non-Volatile Memory Express，非易失性存储接口) read await 仍约为 0.05 ms，且没有随 update offered load 单调上升。当前证据只支持 OdinANN 存在架构特有的并发尾延迟现象，不支持启动跨系统 SSD-aware scheduling 研究方向。

## 系统与 Harness

DGAI 固定于提交 `a0179b876a4bd453336dc2893b46ae890f680555`，使用真实 SIFT-128、900K base、R=64、L=160、beam=4、decoupled topology/coordinate layout。构建关闭 `PROFILE_RMW`，启用 `DGAI_USE_TOPO_DISK`、`FIX_PQ_TABLE_ALIGNMENT` 与 `FIX_PENDING_INSERT_VISIBILITY`。OdinANN 使用官方 `thustorage/PipeANN` 提交 `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`，使用同一数据、规模、R 与 L；保留官方 query beam=32、insert beam=8 与 coupled record 路径。

现有 DGAI `vectordb_rmw_steady_mixed` 使用全局 `index_mu` 串行化 query/update，且 query 为 closed-loop，不能用于本门禁。本轮新增两系统共用的 measurement-only open-loop harness `codex/share/concurrent_query_update_p0_harness.cpp`。query 与 update 分别由独立 arrival scheduler 按绝对到达时间入队，响应时间从 offered arrival 计到 completion，包含排队时间。8 个 query workers 固定到 CPU 0–7，1 个 update worker 固定到 CPU 20，两个 scheduler 固定到 CPU 26–27；整个进程限制在 NUMA node 0 的 CPU 0–27。

Sanity 中发现 DGAI 第一次 insert 会把全局 PQ byte vector 扩容到 1.5 倍，并发 query 仍持有旧 `data()` 指针，稳定在 `aggregate_coords()` 中 SIGSEGV。正式 harness 在启动 workers 前执行与原 insert 路径相同的 1.5 倍预分配，避免运行时 reallocation；没有修改已有 PQ codes、I/O 路径或索引算法。修复后连续 3 次 debug 重复及 90 个正式点均无崩溃。失败 debug 样本保留但不进入统计。

## Offered-load 定义与实验协议

短 sweep 先定位 query-only backlog 拐点。QPS(Queries Per Second，每秒查询数) 作为 query offered load 单位。8 query workers 下，DGAI 在约 2.2K QPS、OdinANN 在约 4.75K QPS 开始持续排队。正式 query offered load 分别取 DGAI 400/1000/1800 QPS 和 OdinANN 900/2400/4000 QPS，约覆盖各自容量的轻载、中载和高但稳定负载。

Update-only sweep 显示 DGAI 单线程在约 20–28 updates/s 后出现持续 backlog，且仍受已知 `io_submit()` 非平稳状态影响；正式取 2/5/10 updates/s。OdinANN 通过后台 writeback 维持更高提交率，正式取 20/80/140 updates/s。两套系统的 update rate 按各自稳定 service range 归一化，不使用相同绝对数字制造不公平比较。

每套系统包括 3 个 query-only、3 个 update-only 和 9 个 query/update mixed 点。每点 warmup 3 秒、measurement 10 秒、3 次 clean-index 独立重复，共 90 个正式运行。DGAI 每个含更新的点先从 clean 900K source 覆盖恢复；OdinANN 每次由官方 `load(..., true)` 创建 shadow。更新次序在不同重复间轮换。所有 query/update offered requests 均完成，没有 drop 或 exception；harness 未设置人为 deadline，因此不伪造 timeout 指标。

Recall@10 使用原始 10K×100 ground truth，在每条 query 完成时按当时 `visible_npts` 过滤并选择前 10 个有效 ID，避免把尚未插入的 suffix 当作漏召回。系统层同步记录 1 秒 `iostat`、`pidstat` 和 20 ms `/proc/<pid>/task/*/wchan`。`wchan` 只作为 futex、AIO 与睡眠驻留代理，不解释为精确内部 lock wait。

## DGAI Service Curves

表中 p99 为 3 次重复的均值，变化与 bootstrap 95% CI(Confidence Interval，置信区间) 均相对同一 query load、同一重复的 query-only baseline 配对计算。bootstrap 仅有 3 个独立重复，因此 CI 只用于判断方向，不作为高精度总体区间。

| Query QPS | Update QPS | Query-only p99 | Mixed p99 | p99 变化与 95% CI | p50 变化 | Query throughput | Update throughput | Recall 变化 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 400 | 2 | 12.26 ms | 12.19 ms | −0.6% [−2.2%, +1.9%] | +0.1% | −0.0% | 0.0% | 0.00000 |
| 400 | 5 | 12.26 ms | 11.98 ms | −2.3% [−2.7%, −1.9%] | −1.6% | 0.0% | 0.0% | 0.00000 |
| 400 | 10 | 12.26 ms | 11.93 ms | −2.6% [−8.0%, +1.2%] | −2.6% | 0.0% | 0.0% | 0.00000 |
| 1000 | 2 | 7.40 ms | 7.22 ms | −2.3% [−4.9%, +0.2%] | −0.6% | 0.0% | 0.0% | 0.00000 |
| 1000 | 5 | 7.40 ms | 7.53 ms | +1.7% [+1.1%, +2.5%] | +0.6% | 0.0% | 0.0% | 0.00000 |
| 1000 | 10 | 7.40 ms | 7.17 ms | −3.0% [−9.1%, +0.9%] | −0.7% | 0.0% | 0.0% | 0.00000 |
| 1800 | 2 | 4.25 ms | 4.22 ms | −0.6% [−1.8%, +0.2%] | +0.0% | 0.0% | 0.0% | −0.00000 |
| 1800 | 5 | 4.25 ms | 4.24 ms | −0.2% [−1.0%, +0.3%] | −0.1% | 0.0% | 0.0% | 0.00000 |
| 1800 | 10 | 4.25 ms | 4.26 ms | +0.3% [−0.5%, +0.8%] | −0.3% | 0.0% | 0.0% | −0.00000 |

DGAI 没有随 update rate 增长的 query tail degradation。唯一显著正变化是 1000/5 点的 +1.7%，但相邻 update rates 分别为 −2.3% 与 −3.0%，不构成服务曲线趋势。高载 1800 QPS 下，update rate 从 0 增至 10/s 时 read IOPS 约为 588.7K→592.3K、write IOPS 为 5→638、queue depth 为 46.9→47.7、read await 始终为 0.08 ms；query p99 仍只变化 +0.3%。这里的 IOPS(Input/Output Operations Per Second，每秒输入输出操作数) 取自 block-layer 设备统计。

## OdinANN Service Curves

| Query QPS | Update QPS | Query-only p99 | Mixed p99 | p99 变化与 95% CI | p50 变化 | Query throughput | Update throughput | Recall 变化 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 900 | 20 | 8.01 ms | 31.74 ms | +296.0% [+215.8%, +350.8%] | −0.6% | 0.0% | 0.0% | −0.00000 |
| 900 | 80 | 8.01 ms | 31.88 ms | +297.1% [+105.4%, +400.0%] | +3.0% | −0.0% | 0.0% | −0.00000 |
| 900 | 140 | 8.01 ms | 35.02 ms | +336.6% [+239.9%, +391.1%] | +4.8% | −0.0% | −0.0% | −0.00000 |
| 2400 | 20 | 4.71 ms | 52.15 ms | +1011.6% [+897.9%, +1208.6%] | +1.2% | 0.0% | 0.0% | 0.00000 |
| 2400 | 80 | 4.71 ms | 60.06 ms | +1177.1% [+1007.4%, +1298.0%] | +1.8% | 0.0% | 0.0% | −0.00002 |
| 2400 | 140 | 4.71 ms | 53.09 ms | +1031.7% [+560.6%, +1333.1%] | +2.9% | −0.0% | 0.0% | −0.00002 |
| 4000 | 20 | 2.95 ms | 59.48 ms | +1914.4% [+1883.0%, +1976.2%] | +1.5% | −0.0% | 0.0% | 0.00000 |
| 4000 | 80 | 2.95 ms | 47.80 ms | +1517.5% [+564.7%, +2132.6%] | +2.5% | −0.0% | 0.0% | −0.00001 |
| 4000 | 140 | 2.95 ms | 73.79 ms | +2402.4% [+1930.9%, +3332.0%] | +2.2% | 0.0% | 0.0% | −0.00000 |

OdinANN 的 query p99 放大在 3 次重复中均存在，但不是随 update offered load 单调增长。例如 2400 QPS 下，20/80/140 updates/s 的 mixed p99 为 52.15/60.06/53.09 ms；4000 QPS 下为 59.48/47.80/73.79 ms。与此同时 p50、query throughput、update throughput 和 recall 几乎不变，表明这是间歇性 tail stall，而不是整体 service capacity 按 update load 平滑下降。

高载 4000 QPS 下，update rate 从 0 增至 140/s 时 read IOPS 为 693.3K→713.3K、write IOPS 为 2→393、queue depth 为 33.9→35.7，read await 始终约 0.05 ms。进程 CPU 使用从约 660% 升至 744%，其中 system CPU 从约 256% 升至 280%；futex `wchan` sample fraction 从 0.797 降至 0.755，主要反映更多线程处于运行态，不能证明锁竞争。设备延迟没有与 p99 的 20 倍以上放大同步变化，因此 P0 不把该信号归因为 SSD。

## 初步原因边界

两系统 query-only 高载都已使 NVMe `%util` 接近 100%，但该指标对多队列 NVMe 只表示采样期持续有 outstanding I/O，不等于达到吞吐容量。DGAI 在 read IOPS 约 590K、queue depth 约 47 的条件下加入更新仍无 query p99 损失；OdinANN 在相近或更低设备延迟下出现只影响 p99 的间歇性 stall。这个反差否定了同一 SSD queue/介质干扰对两套结果的共同解释。

P0 不能区分 OdinANN 的 tail stall 究竟来自 coupled-record locks、mapping transition、后台 writeback completion、内存同步还是其他实现细节。继续做 CPU-only shadow 或 I/O-only replay只会诊断单系统现象，而 gate 明确要求跨系统同方向退化后才能进入 P1。因此本轮不扩展因果实验，也不把 OdinANN tail 包装成新方向。

## 有效性边界

本轮只使用 SIFT-128、900K base、单块 Samsung 990 PRO NVMe、8 query workers 和 1 update worker。负载覆盖三个 query 强度和三个 update 强度，但不支持对更多线程数、第二数据集或其他 SSD 外推。DGAI 的 PQ 预分配是必要并发安全准备；若不预分配，测到的是全局 vector reallocation use-after-reallocation，而非存储干扰。OdinANN 的后台 writeback 使 application insert completion 不等于介质持久化 completion，但设备 write IOPS 已独立记录，不影响跨系统门禁判断。

3 次独立重复足以区分 DGAI 的近零变化与 OdinANN 的数倍 tail 放大，但不足以精确估计重尾分布总体 CI。由于 P0 Kill 条件已经由架构方向不一致直接满足，增加重复、第二数据集或更细 block trace 不会恢复跨系统叙事，故按 Kill-first 原则停止。

## 最终边界

P0 支持两个观察。第一，DGAI 在稳定 update load 范围内没有并发 query tail degradation。第二，OdinANN 有稳定但非单调、只集中于 p99 的并发 tail stall，且初步设备指标不随其同比恶化。P0 不支持动态驻盘图索引普遍存在 update-induced SSD interference，也不支持设计通用 SSD-aware scheduler。

因此候选 A 按跨系统问题 **Kill**。不进入 P1、P2，不请求 Claude novelty review，不保留 scheduler 工程分支。若未来单独处理 OdinANN tail，应以实现诊断重新立项，并首先检查 coupled-record 同步与后台 writeback，而不是沿用本轮跨系统存储叙事。

机器可读汇总位于 NVMe 的 `VectorDB/data/VectorDB/p0_interference/analysis.json` 与 `service_curves.csv`，SHA-256 分别为 `58eb78e826787fccf4e71647c7c70e94f53011859bbcdd36d149cc3cdf4f6ed6` 和 `2c54634ae8489425660cc636cb7b35c1265a6efb5329966c82d53278410b94cf`。原始实验目录占用约 21 GiB，系统盘实验前后均为 128 GiB 已用、155 GiB 可用。
