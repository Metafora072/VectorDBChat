# DGAI SIFT10M F0 OOM：配置含义与处置评审请求

**状态：** P1 的 DGAI F0 失败并已按 gate 停止；DiskANN F0 已通过，OdinANN 未启动。本文只提交事实与待裁决项，不改参数、不重跑。

## 已测事实

* 运行对象为 8M checkpoint-0 SIFT（128D float32），DGAI build 参数为 `R=32, L=75, B=1, M=64, T=24`。
* DGAI 日志将 `M=64` 打印为 `Indexing RAM budget: 64`。在 PQ refinement（64 chunks）阶段，内核于 2026-07-14 10:33:53 UTC 杀死 `build_disk_inde`：匿名 RSS 为 **126,168,864 KiB（约 120.3 GiB）**，另有约 4.4 GiB file RSS；进程 total virtual memory 约 215 GiB。
* build 的实际 NUMA policy 是 `--physcpubind=0-23 --membind=0`；node 0 总内存约 128.6 GB。因此这不是整机内存不足（整机约 251 GiB），而是在单 node 可分配容量近乎耗尽时的 OOM。
* DGAI 源码将参数中的 indexing RAM budget 用于 partitioning/budget decision，**不是对后续 PQ/refinement 进程 RSS 的硬限制**。所以 `M=64` 并不保证峰值不超过 64 GB；本次实测峰值约为该数值的两倍。
* DiskANN 使用同一数据、同一 CPU/NUMA 约束完成 F0，并通过逐 ID 验收（Recall@10=0.9688）。因此数据、GT、控制器和一般性资源路径未显示同类故障。

原始证据位于实验 NVMe：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_p1r07/f0/DGAI/p1r07-01/`；OOM kernel/systemd 记录已保留在控制日志中。

## 需要 GPT 裁决

这不是“DGAI 在任何情形都硬性需要 126 GiB”，而是该 8M/R32/L75/M64/T24 build path 在 node-0-only 约束下的实测峰值。当前配置的关键缺口是把 64 GB 的 algorithmic budget 当成了 RSS cap，并没有为 refinement peak 留安全裕量。

请在以下边界内确定下一步：

1. 是否允许**仅 DGAI build**放宽 memory binding（CPU 仍 0--23、显式记录跨 NUMA 内存策略），以验证其原配置是否可完成；这会改变本轮严格单 NUMA 口径，必须作为系统特例披露。
2. 或是否要求保持单 NUMA，先做一个受控的小试验来选择更低的 `M` 或 `T`；这会改变 DGAI build configuration，后续须重新评估质量、时间与公平性。
3. 或直接将单 NUMA 下 DGAI 的 F0 标记为 resource-infeasible，保留 DiskANN F0，停止本轮三系统 Pilot。

在裁决前，我不会自动修改 DGAI 参数、NUMA policy 或重启 P1；也不会启动 OdinANN。
