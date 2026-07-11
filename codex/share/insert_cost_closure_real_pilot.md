# Insert Cost Closure Real-Data Pilot

## 1. 语义修复隔离与基线可比性

原先的 profiling 构建不只增加 timer：它还在 `pq_table.h` 中把 AVX-512 streaming load 换成了 unaligned load，并在 `rerank_search.cpp` 中过滤尚未提交 topology/coordinate mapping 的当前插入点。两项现已分别由 `FIX_PQ_TABLE_ALIGNMENT` 与 `FIX_PENDING_INSERT_VISIBILITY` 控制；`PROFILE_RMW` 只负责计时和记录，`USE_TOPO_DISK` 也可在 profiling 关闭时独立启用。

原始 streaming-load 语义在本机 profiling 开/关下都于 `populate_chunk_distances_nt()` 同一位置 SIGSEGV，说明成功运行不是 instrumentation 本身的效果，而是 profiling 曾隐式携带 alignment 修复。启用 alignment-safe load 后，profiling 开/关均可完成相同 workload。pending-insert filter 在 pilot 中保持关闭，R64 synthetic 与两套真实数据均能完成，因此本轮没有携带该 `rerank_search.cpp` 语义修复。

相同 20-insert workload 下，profiling 开/关生成的 coordinate 文件完全相同；topology 文件不逐字节相同，但两次 uninstrumented 重复之间同样不相同，表明该路径本身存在页面/邻接写入次序的非字节确定性，不能把 topology byte equality 当作 profiling 语义判据。成功状态、输入序列、参数和单线程条件保持一致。

## 2. Instrumentation overhead

在同一 clean R64 source index 上，对每组 trial 复制独立索引，执行 250 inserts × 12 配对重复。ops-only profiling 的 paired median overhead 为 −0.32%，bootstrap 95% CI 为 [−3.81%, 1.61%]，未检测到可分辨开销。完整 page-event logging 在先导 100 inserts × 9 重复中产生约 18.0% median overhead，95% CI 为 [4.66%, 30.09%]，因此 real pilot 强制 `PROFILE_RMW_EVENTS=0`；逐 insert ops CSV 保留。

## 3. Pilot 协议

- 数据：真实 SIFT-128 与 GIST-960。
- 规模：100K base，使用原始 1M 数据中的连续 suffix 做 insert；此步只验证路径与成本稳定性，900K base 留给 full matrix。
- 图参数：R=64、L=160、beam=4、strategy=19、单线程。
- 稳定缓存：同一进程先 warm up 500 inserts，再按 100-row checkpoint 检查 dominant-stage share；要求连续 3 个 checkpoint dominant 相同、share drift ≤1pp、bootstrap CI 半宽 ≤2pp。
- 冷缓存：每个 cluster 使用全新源索引副本和新进程，只取前 100 inserts；按 cluster bootstrap 自适应增加独立冷启动，直到 CI 半宽 ≤2pp。

## 4. 阶段占比与缓存影响

| Dataset/cache | Samples | Dominant stage | Share (95% CI) | New candidate | Reverse candidate | Submission/writeback |
|---|---:|---|---:|---:|---:|---:|
| SIFT cold | 15 clusters / 1,500 | coordinate acquisition/rerank | 54.41% [52.72, 55.67] | 33.45% | 4.43% | 6.48% |
| SIFT stable | warmup 500 + 500 | coordinate acquisition/rerank | 37.78% [37.06, 38.52] | 23.11% | 19.87% | 13.60% |
| GIST cold | 45 clusters / 4,500 | coordinate acquisition/rerank | 65.06% [62.93, 66.88] | 24.43% | 3.31% | 3.94% |
| GIST stable | warmup 500 + 800 | coordinate acquisition/rerank | 50.24% [49.15, 51.38] | 19.63% | 10.21% | 9.83% |

冷缓存使 dominant share 相对稳定缓存分别提高 16.62pp（SIFT）和 14.83pp（GIST）。两个维度下主瓶颈一致，且稳定缓存占比仍分别超过 30% 与 50%。exact-distance compute 本身很小（SIFT 0.27%，GIST 0.65%）；当前证据指向 coordinate page acquisition/rerank 路径，而不是 exact arithmetic。

SIFT 共审计 4,400 行、GIST 7,400 行，全部满足 `Σ(stage)+residual=total`；最低 closure 分别为 99.10% 与 99.12%，仍高于 95% 门禁。

## 5. 存储纠正

执行中发现部分相对路径误落到 `repos/DGAI/data`，累计 57,565,228,412 bytes。该树已原样迁移到 NVMe 的 `VectorDB/data/VectorDB/recovered_system_disk_20260711/`，迁移前后均为 1,404 个文件、字节数完全一致，系统盘源目录已清空。系统盘可用空间由 59 GiB 恢复至 113 GiB。实验脚本现已增加路径硬门禁，输出不在 `VectorDB/data` 下会直接退出。

## 6. 是否继续完整矩阵

建议 **继续 R32/64/96/128 完整矩阵**。理由仅限 pilot 门禁：两套真实数据路径有效、计时开销不可分辨、阶段占比已按 CI 自适应稳定，且 coordinate acquisition/rerank 在两个维度和两种缓存状态下均为同一 dominant stage。该结论只授权扩展 R，不构成新 Idea 或跨系统结论；完整矩阵需要验证该份额是否随 R 保持，以及 acquisition 内部的 page wait、lock/copy 与 rerank bookkeeping 各自占比。

机器可读汇总位于主项目 `reports/insert_cost_closure_real_pilot.json`，原始数据位于 NVMe 的 `VectorDB/data/VectorDB/recovered_system_disk_20260711/`。
