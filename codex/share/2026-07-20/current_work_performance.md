# Dynamic Vamana 当前性能与资源审计

你问到 Recall 和 SSD，我按最近完成的 **Dynamic Vamana SIFT10M W1/CP20** 结果统计；最新的 T2 状态机实验本身没有 Recall 或真实 SSD 检索指标。

结论先说：

- SSD 没有达到设备上限。最高查询读带宽约 `1.163 GB/s`，最高更新总吞吐约 `0.912 GB/s`。
- 热查询和图更新路径都是精确 `4 KiB` 对齐，没有发现有害的非对齐 Direct I/O。
- CP20 Recall@10 为 `94.255%–97.634%`，可通过提高搜索参数再提升约 3 个百分点，但 QPS 会下降约 `28%–33%`。
- CP20 更新峰值内存为 DGAI `4.60 GiB`、OdinANN `2.53 GiB`；真正突出的内存问题是 DGAI 构建峰值 `132.2 GiB`。
- 当前 Dynamic Vamana Atlas 全部历史工件占 `725.6 GiB`，其中大量是重复 formal clone；磁盘清理空间很大。
- 工程优化仍有空间，但此前 queue coalescing 路线已经被 M3 证实为 `0` 可消除写入，不值得继续。

## 查询性能与 Recall

| 系统 | CP20 参数 | Recall@10 | QPS | SSD 读带宽 | 设备读 IOPS | 相对设备标称读上限 |
|---|---:|---:|---:|---:|---:|---:|
| DGAI | L=64 | 94.613% | 1,235.72 | 1.163 GB/s | 283.8K | 15.6% 带宽 / 20.3% IOPS |
| DGAI | L=128 | 97.634% | 827.91 | 0.964 GB/s | 235.4K | 12.9% / 16.8% |
| OdinANN | L=29 | 94.255% | 1,712.27 | 0.360 GB/s | 88.0K | 4.8% / 6.3% |
| OdinANN | L=46 | 97.431% | 1,226.82 | 0.331 GB/s | 80.8K | 4.4% / 5.8% |

实验盘 `/dev/nvme8n1` 是 PCIe 4.0×4 Samsung 990 PRO 2TB，目前链路以完整的 `16 GT/s ×4` 运行。厂商标称上限为顺序读 `7,450 MB/s`、顺序写 `6,900 MB/s`、随机读 `1.4M IOPS`、随机写 `1.55M IOPS`。[Samsung 官方规格](https://semiconductor.samsung.com/news-events/news/samsung-electronics-unveils-high-performance-990-pro-ssd-optimized-for-gaming-and-creative-applications/)

这些百分比只是描述性对照，因为 ANN 是低队列深度、逐跳依赖的小随机读，不能直接与高队列深度的厂商峰值等价比较。但可以明确判断：当前吞吐远未触及设备的带宽或标称随机 IOPS 上限，瓶颈更可能在图遍历依赖、CPU 距离计算、每查询 I/O 串行性和有效队列深度。

## 更新性能

| 系统 | CP20 E2E 更新吞吐 | SSD 读带宽 | SSD 写带宽 | 合计吞吐 | 峰值 RSS |
|---|---:|---:|---:|---:|---:|
| DGAI | 926.15 repl/s | 0.494 GB/s | 0.044 GB/s | 0.539 GB/s | 4.60 GiB |
| OdinANN | 1,109.03 repl/s | 0.685 GB/s | 0.227 GB/s | 0.912 GB/s | 2.53 GiB |

OdinANN 的更新总吞吐更高，但写带宽和每次 replacement 的写量也明显更高。CP20 每次 replacement 的写入量为：

| 系统 | 写入量/replacement |
|---|---:|
| DGAI | 48.0 KB |
| OdinANN | 204.6 KB |

OdinANN 约为 DGAI 的 `4.26×`，但两者的 `R`、记录布局、I/O engine 和可见性语义不同，不能把差异简单归因于单一机制。完整数据见 `codex/share/2026-07-17/dynamic_vamana_w1_final_five_point_review_0717.md`。

## I/O 对齐情况

| 路径 | 请求形态 | 对齐结论 |
|---|---|---|
| 查询读取 | 设备计数显示平均请求精确为 `4096 B` | 已对齐 |
| DGAI 图更新 | libaio 提交 `4 KiB` 页 | 已对齐 |
| OdinANN 图更新 | io_uring 提交 `4 KiB` 页 | 已对齐 |
| M1 全部 8 个正式点 | `requested_bytes = page_touches × 4096` | 100% 闭合 |
| Publish/PQ/tags | 包含 8-byte 文件头和尾部写入，走 buffered POSIX I/O | 应用请求不全是 4 KiB，但不属于有害的非对齐 Direct I/O |
| 块层实际请求 | 文件系统可能合并相邻 `4 KiB` 请求 | 正常现象 |

因此，当前没有通过修正 alignment 获得显著收益的空间。真正的问题是大量小随机页访问及 neighbor repair 写入，而不是 offset/length 没对齐。相关闭包见 `codex/share/2026-07-18/dynamic_vamana_neighbor_repair_m2_0718.md`。

## 内存与索引空间

| 系统 | CP20 更新峰值 RSS | 历史构建峰值 RSS | 最终索引文件 | Formal clone 实际基线 |
|---|---:|---:|---:|---:|
| DGAI | 4.60 GiB | 132.2 GiB | 14.13 GB | 14.13 GB |
| OdinANN | 2.53 GiB | 10.7 GiB | 8.48 GB | 16.96 GB，包含 shadow-copy 路径 |

当前没有 Dynamic Vamana 实验进程运行，因此当前额外实验 RSS 为 0。整机约有 `239.1 GiB` 可用内存。

内存优化判断：

- DGAI 构建的 `132.2 GiB` 是最值得优化的内存点，远高于运行期的 `4.60 GiB`。
- OdinANN 构建仅 `10.7 GiB`，继续优化的紧迫性较低。
- 查询/更新运行期内存已经不构成当前机器上的容量瓶颈。
- 降低 PQ/cache 驻留可以省内存，但需要重新测量 Recall、QPS 和 SSD I/O，不能视为无损优化。

## 当前 SSD 占用与可清理空间

| Atlas 子目录 | 当前占用 |
|---|---:|
| `formal/` | 474.3 GiB |
| `z0b_sequence_endpoint_reclaim_0719/` | 87.9 GiB |
| `index/` | 67.1 GiB |
| `datasets/` | 65.6 GiB |
| `build/` | 16.3 GiB |
| `tmp/` | 5.8 GiB |
| 其他结果、源码和原始文件 | 8.6 GiB |
| **Dynamic Vamana Atlas 合计** | **725.6 GiB** |

整个 `/dev/nvme8n1` 当前使用约 `980 GiB`，剩余约 `759.7 GiB`。最新 T2 实验只额外占 `135 MiB`，不是磁盘占用主体。

空间节省建议：

| 动作 | 潜在节省 | 风险 |
|---|---:|---|
| 清理已终止 attempt 的临时目录 | 约 5.8 GiB | 低，但需先核对 manifest |
| 删除可重建的旧 build | 最多约 16.3 GiB | 中，需要保留源码、编译参数和 binary hash |
| 去除 superseded formal private clones | 可能超过 300 GiB | 高，必须先建立 accepted/superseded 清单 |
| 压缩冷的 JSON/log/profile | 数 GiB | 低 |
| 删除 canonical datasets/index | 约 132.7 GiB | 不建议，会影响复现和后续查询 |

## 还有多少优化空间

| 方向 | 空间判断 | 建议 |
|---|---|---|
| SSD 利用率 | 有明显工程空间 | 先做同盘 fio 校准、`iostat` queue-depth/util 和 CPU profile，再判断是 IOPS、延迟链还是计算受限 |
| Recall | 有约 3 个百分点的参数空间 | 提高 L，但需接受 28%–33% QPS 损失 |
| 非对齐 I/O | 基本没有 | 热路径已是严格 4 KiB |
| Queue coalescing | 没有 | M3 测得 pre-submit supersedable bytes 精确为 0 |
| Neighbor repair 写量 | 有工程空间，但研究新颖性低 | 减 R、改变布局或 repair scope 都会改变图质量/语义，且已有大量 prior work |
| 构建内存 | DGAI 有较大空间 | 优先分析其 132.2 GiB 的分配组成 |
| 历史工件磁盘 | 很大 | 建议先生成只读清理清单，预计可安全回收数百 GiB |

总的判断是：**设备没有跑满，Recall 仍可用吞吐换取提升，DGAI 构建内存和历史实验磁盘占用有显著优化空间；但此前研究主线中的 queue coalescing 已经没有空间。**
