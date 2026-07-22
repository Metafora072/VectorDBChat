# DynamicSSD-Maintenance Corrective Canary 结果

**日期：** 2026-07-22  
**主裁决：`KILL-DYNAMIC-SSD-MAINTENANCE`**

## 结论先行

Corrective canary 的三组测量均已闭合，但没有形成可继续为 ANN 算法项目的主信号。

- **Q2 Physical Layout Aging 未通过硬门槛。** S1/S2 的 visited nodes 相对 S0 分别只变动 −0.62%/−0.16%，满足“图工作量稳定”；但 distinct pages/query 不升反降 3.76%/6.12%，远离要求的 `>10%` 增长。fresh static S3 与 S0 相差 −0.42%，说明静态控制稳定，却没有 aging 可供 rebuild 恢复。
- **Q1 不能成为替代主轴。** 默认 COW 的确存在重复页触碰，但现有 `IN_PLACE_RECORD_UPDATE` 并未降低实际写入；10K inserts 时它写入 2.654 GB，是 COW 658 MB 的 4.03 倍。该结果更像具体写路径实现权衡，而非新的 ANN 优化目标。
- **Q3 没有 page-local opportunity 信号。** 5%/10% uniform tombstone 时，删除节点占导航 hops 的 6.06%/10.81%，仅为删除率的 1.21×/1.08×；distinct pages 反而下降 0.71%/0.60%。full merge 清除了删除 hops，但 distinct pages 增加 0.61%。

因此不满足 `PASS-L-PHYSICAL-AGING`，也没有证据支持 `PASS-D-PAGE-LOCAL-OPPORTUNITY`。按照 Gpt 的约束，不能仅凭 Q1 的 batching/in-place 差异建立项目，故整体 KILL。

## 1. 环境与可复现标识

| 项目 | 值 |
|---|---|
| PipeANN baseline | `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b` |
| Kernel | Linux 6.8.0, x86-64 |
| CPU | 2× Intel Xeon Gold 6348，112 logical CPUs |
| 数据盘 | Samsung 990 PRO 2TB，`/dev/nvme8n1`，ext4，实验结束可用 742 GB |
| I/O 路径 | graph fd `O_DIRECT`；CMake 在本机选择 Linux AIO fallback，而非 io_uring |
| 数据集 | SIFT1M，float32，1M×128；1000 queries |
| 参数 | R=64，Lbuild=96，Lsearch=96，PQ chunks=32，4 KiB sector，5 nodes/sector |
| 并发 | search 1 thread；build 32 threads；update 内部保留默认 BG I/O/flush |
| 峰值 RSS | 最大观测 3.44 GiB（S3 build），低于 24 GiB |
| 新增 NVMe 数据 | 9.8 GiB，低于 10 GiB |
| 默认 binary SHA-256 | `6fc719bf9856a6013313b016ded0d1cbc55fea28afd126129d0a6a0d971d0d12` |
| in-place binary SHA-256 | `22e91af91b7d096676df26d7bb6fd97fcc0e37097f78db339f66b26fa4772cec` |

关键数据哈希：

- `base_900k.bin`: `b547d390dcd7b1b1b1d36d692e0ed4a54a992239ac377617cd973e1067a42b2a`
- `delete_tags_100k.bin`: `e4f3171efe740ee2e5a876cadb5c65ab037cc504a4746a8db08dd149f67dbf2a`
- `churn_inserts_100k.bin`: `aa6ed35f717739132298b4ffa2804ebacfa8f0f003df00741ca966cd05e56ac4`
- `churn_gt_1000.bin`: `f8f04ab7d43fe2801bdd9684a0044389ceb3ee02425a974f6f8a8e556ee42d92`

## 2. Instrumentation

补丁只增加计量和 canary driver，不改变搜索/更新策略：

1. 在 `pipe_search_common` 每个 query 内收集请求的 graph sector ID 集合，输出 distinct pages、total page accesses 与已有 `n_ios`；graph bytes 定义为 `page_accesses × 4096`。
2. `nodes/page` 定义为实际 expanded graph nodes / distinct requested graph pages。
3. 搜索时通过只读 deleted-tag 集合统计 expanded deleted nodes。更新与搜索不并发，避免计量集合的数据竞争。
4. 在 direct insert 路径统计读/写 page touches、distinct pages，以及 position search、prune、RMW+flush/enqueue 临界路径时间。
5. 用 `/proc/self/io` 的 `read_bytes`/`write_bytes` 统计该进程实际提交到 block layer 的字节；insert 后保留 2 秒让默认后台 I/O 排空。没有关闭 PageCache、没有添加逐边 fsync。

sanity 10-query run 验证了 `distinct_pages <= page_accesses` 且计数非零。完整源码修改保存在 `patches/pipeann_dynamic_ssd_canary.patch`。

## 3. 实验 A：Physical Layout Aging

S2 从 S0 的同一静态图开始，随机删除 100K 原向量并插入其加 `N(0, 0.01)` 扰动的替代向量，维持 1M active objects；使用对应 active-set exact GT。S1 active set 与原始 SIFT1M 相同。S3 由 S1 的同一 active set重新独立静态构建，参数与 S1 一致且无 attribute。

| State | Recall@10 | cmps mean / p95 / p99 | visited mean / p95 / p99 | distinct pages mean / p95 / p99 | accesses | KiB/query | nodes/page | latency p50 / p95 / p99 (µs) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| S0 static | 0.8156 | 4036.2 / 5045 / 5325 | 108.746 / 114 / 116 | 111.262 / 117 / 119 | 111.588 | 446.4 | 0.9775 | 1500 / 1648 / 1722 |
| S1 +100K insert | 0.8152 | 3966.6 / 4993 / 5369 | 108.077 / 113 / 116 | 107.076 / 115 / 118 | 111.750 | 447.0 | 1.0110 | 1150 / 1392 / 1568 |
| S2 100K churn | 0.9945* | 3928.9 / 4916 / 5172 | 108.569 / 114 / 116 | 104.451 / 113 / 116 | 112.073 | 448.3 | 1.0423 | 1021 / 1133 / 1198 |
| S3 fresh rebuild | 0.8157 | 4038.4 / 5034 / 5335 | 108.728 / 114 / 117 | 110.794 / 116 / 119 | 111.092 | 444.4 | 0.9815 | 1268 / 1446 / 1517 |

`*` S2 使用 perturbed-replacement active set 的独立 GT，Recall 数值不能与 S0/S1 横向解释；layout gate 只比较同参数下的 traversal/page 指标。

门槛核对：

| Gate | S1 vs S0 | S2 vs S0 | 结果 |
|---|---:|---:|---|
| `|Δ visited| < 5%` | −0.62% | −0.16% | PASS |
| `Δ distinct pages > 10%` | −3.76% | −6.12% | **FAIL** |
| S3 pages 接近 S0 | −0.42% | — | PASS control |

值得注意的是 total page accesses 几乎不变（S1 +0.15%，S2 +0.43%），但 distinct pages 减少、nodes/page 增加。这说明更新后同一页被重复请求的概率略升；它不是“相同 traversal 被摊到更多物理页”的 aging 信号。

## 4. 实验 B：COW vs In-Place 写路径

每个配置从同一个 fresh 900K static index 开始。`actual writes` 是进程 block-I/O bytes；dirty/repeat 是逻辑 4 KiB page touches。时间分解为累计 CPU/critical-path 计时，不与 wall time相加。

| Path | Inserts | actual writes | KiB/insert | distinct dirty pages | repeat touches | position / prune / RMW (s) | wall (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| COW | 1K | 55.7 MB | 54.4 | 12,596 | 1,007 | 1.504 / 0.029 / 0.700 | 4.239 |
| In-place | 1K | 265.6 MB | 259.4 | 39,711 | 25,135 | 1.714 / 0.031 / 0.910 | 4.666 |
| COW | 10K | 658.5 MB | 64.3 | 108,376 | 52,385 | 17.067 / 0.304 / 7.856 | 27.295 |
| In-place | 10K | 2.654 GB | 259.2 | 152,910 | 495,103 | 14.272 / 0.302 / 8.379 | 25.063 |

In-place 的实际写入为 COW 的 4.77×（1K）和 4.03×（10K）。10K 时 in-place wall time稍低 8.2%，来自 position search 更短，而非较少写入。该替代宏会对大量邻居 sector 做直接 RMW；默认 COW 的 hint allocation 与写缓冲反而合并了更多物理写。结果否定“已有 in-place 宏即可消除写放大”，但也没有给出可升级为 ANN 算法贡献的独立机制。

## 5. 实验 C：Tombstone 与 full merge

删除 tag 由 seed `20260722` uniform without replacement 生成。Recall GT 在前 100 true neighbors 中跳过 deleted tags，再取 active top-10。

| Tombstone | Recall@10 | visited | deleted visited | deleted hop fraction | distinct pages | nodes/page | latency p50 / p95 / p99 (µs) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0% | 0.8156 | 108.809 | 0 | 0 | 111.560 | 0.9755 | 1247 / 1646 / 1744 |
| 5% | 0.8055 | 108.505 | 6.576 | 6.06% | 110.773 | 0.9797 | 1451 / 1594 / 1696 |
| 10% | 0.8139 | 108.570 | 11.741 | 10.81% | 110.887 | 0.9793 | 1518 / 1689 / 1760 |

deleted-hop enrichment 相对 uniform 删除率仅 1.21×/1.08×，且 pages/query 相对 0% 为 −0.71%/−0.60%。p50 latency 上升 16.3%/21.7%，但没有伴随 page I/O 或 traversal 增长；它包含 deleted-set membership 与单次运行噪声，不能归因为 page-local I/O 税。

10% full merge：

| wall | process reads | process writes | pages pre → post | Recall pre → post | p50 latency pre → post |
|---:|---:|---:|---:|---:|---:|
| 11.303 s | 1.642 GB | 769.8 MB | 111.581 → 112.259 (+0.61%) | 0.8139 → 0.8144 | 1299 → 997 µs |

merge 是高效的全量顺序重写并清除了 deleted hops，但没有改善 distinct pages。它量化了维护成本，却没有揭示局部 compaction 可以利用的页面聚集结构。

## 6. 限制与裁决边界

- corrective canary 按规格只做单 seed、单 search-L；它足以执行 `>10% pages` 的 kill gate，不用于声称所有规模和 workload 下永不老化。
- 本机 CMake 的 io_uring probe 未通过，实际异步后端为 Linux AIO；graph fd 仍为真实 NVMe `O_DIRECT`，因此不是内存 fallback。结论限定于 PipeANN 的 direct-I/O SSD 路径，而非 io_uring 的队列开销。
- S0/S2 起点复用了已验证的 1M static artifact，其 normal record 含未使用的 16-byte attribute 区；S1/S3 为 attr-free build。两者均为 5 nodes/sector，page-ID gate 不依赖 record 内字节差异。S3 另行 fresh build 消除了“复用 S0 充当 rebuild”的歧义。
- `/proc/self/io` 是进程级实际 block bytes，不是独占设备级 iostat；后台 flush 等待已包含，但没有对 SSD firmware 写放大做推断。
- 5%/10% p50 latency 的变化没有重复种子，且与 page counters 方向相反，因此报告为观察值，不作为 PASS-D 证据。

## 7. 最终裁决

**`KILL-DYNAMIC-SSD-MAINTENANCE`**

停止 Physical Layout Aging、page-local tombstone compaction 和以现有 COW/in-place 写路径为中心的独立项目。不进入多种子扩展，不实现 scheduler、relayout 或新 compaction。若未来重新开启，必须由更强的新证据触发，例如更大规模或长期非均匀 churn 下，在 visited 稳定时可复现 `>10%` 的 distinct-page 增长；本轮结果本身不支持继续。

