# Dynamic Vamana Pilot Atlas：时间与 NVMe 容量预算

**状态：** 只读预算，尚未下载 SIFT10M、构建 F0 索引或启动任何正式负载。  
**适用范围：** Claude 提议的 SIFT10M Pilot Atlas，以及其后完整 W0/W1 的容量上界。  
**不适用范围：** W2 mixed workload；它尚未获得授权。

## 口径与当前余量

容量均为十进制 GB，并按 `du --block-size=1` 的已分配空间峰值估算，而非目录表观大小。复制、reflink 失效和重建期间旧/新索引共存均按最坏情况计入。各系统严格串行，动态工作目录在成功写入 manifest 和校验结果后才可清理；不会自动删除既有 1M preparation artifacts。

2026-07-13 18:39 UTC 的只读检查显示：系统盘 `/` 仅余 156 GB，实验 NVMe `/home/ubuntu/pz/VectorDB/data` 余约 1.4 TB。因此所有原始数据、索引、临时文件、日志和结果均必须落在该 NVMe；脚本的 `TMPDIR`、build directory 和结果根目录也必须显式指向它，不能依赖系统盘默认 `/tmp`。

下表中“时间”是墙钟预算，不是 CPU 时间；“额外峰值”是相对当前 NVMe 已用 352 GB 的新增空间。实际运行时每个阶段必须用 `resource_probe.py` 记录 RSS、目录已分配字节和设备吞吐，并以记录值更新后续阶段预算。

## 估算依据

现有 1M preparation 的静态 build 实测为：DiskANN 3:25--51:00、Fresh-Ref 5:58--19:20、DGAI 7:26--18:34、OdinANN 0:57--10:15，范围由 SIFT/DEEP/GIST 的维度与索引参数造成。将 active set 从 0.8M 扩至 8M 后，时间不假设严格线性，采用 10 倍实测量级再乘 1.3--2.0 的安全系数。

空间的基准来自 1M 资源 smoke：SIFT 的动态工作目录峰值为 Fresh-Ref 1.52 GB、DGAI 1.42 GB、OdinANN 1.71 GB；按 10 倍 active set 估算为 15.2 GB、14.2 GB、17.1 GB。静态索引按相同口径扩展。该预算是排期保护值，不是性能结论。

## Pilot Atlas：SIFT10M

### F0 readiness

| 系统 | 8M active 静态索引估算 | 单系统 build/load 预算 | F0 交付物 |
| --- | ---: | ---: | --- |
| DiskANN | 8.0 GB | 45--75 分钟 | index、环境 manifest、build/load/query/resource 记录 |
| Fresh-Ref | 7.8 GB | 70--120 分钟 | 同上 |
| DGAI | 14.2 GB | 90--150 分钟 | 同上，含 merge/reload 可见性口径 |
| OdinANN | 8.5 GB | 15--30 分钟 | 同上 |
| 四系统串行合计 | 38.4 GB | 3.7--6.3 小时 | 加上数据取得、GT、校验、冷启动 query 和异常重跑后，预留 12--24 小时 |

F0 的 12--24 小时包含以下不可省略的工程时间：取得并 hash SIFT10M、生成 canonical full/cp00/cp20、计算或验证 exact GT、固定 NUMA/CPU/dedicated cgroup、四套 build/load、一次 query smoke 与资源快照。原始 SIFT 的取得路径尚未冻结：若只能保留标准 BIGANN 的完整 `bigann_base.bvecs`，其原始文件约 128 GB；若来源支持对前 10M 的直接或范围读取，实际会显著更小。预算仍按 128 GB 保留，避免将源数据容量误当作零。

### slim W0

| 实验 | 运行量 | 时间预算 | 相对 F0 的新增峰值 |
| --- | --- | ---: | ---: |
| Recall--QPS sweep | 4 systems × 2 个 `Tq`（1、16）× 4 个 search settings × 1 repeat = 32 点；可合并为 8 次 cold-lifecycle sweep | 2--6 小时 | 不超过 5 GB（TSV、per-run manifest、短期日志与 query trace） |

W0 不需要同时复制四个索引。每次只挂载一个 F0 已完成索引，先写原始结果再生成汇总 TSV；失败点保留独立失败记录，不覆盖已完成点。

### slim W1

| 实验 | 运行量 | 单次工作目录/重建空间 | 时间预算 |
| --- | --- | ---: | ---: |
| Fresh-Ref direct-to-20% | canonical replace-new trace，1 repeat，随后 query | 15.2 GB | 2--8 小时 |
| DGAI direct-to-20% | canonical replace-new trace，1 repeat，含 merge/reload/publish | 14.2 GB | 6--24 小时 |
| OdinANN direct-to-20% | canonical replace-new trace，1 repeat，随后 query | 17.1 GB | 2--8 小时 |
| DiskANN checkpoint-20 rebuild | 旧索引、新索引和 build 临时文件可共存 | 25 GB | 1--3 小时 |
| checkpoint-20 query | 3 动态系统 × 2 个 `Tq` × 4 settings = 24 点，可合并为 6 次 sweep | 不额外复制索引 | 2--6 小时 |

直接跑到 20% 的 update 时间没有 10M 轨迹实测支撑，尤其 DGAI 的 merge/reload 不能由 100-operation smoke 外推为精确值。因此每条 W1 trajectory 脚本必须有 36 小时 watchdog 与每 5% 的进度/已分配空间记录；超时、可见性校验失败或容量越界必须停止并标为失败，而非静默重跑。

### Pilot 的总量

| 组成 | 额外峰值空间预算 |
| --- | ---: |
| 最坏原始 SIFT 源文件保留 | 128 GB |
| canonical full、cp00、cp20、GT 与 hash manifest | 22 GB |
| F0 四套静态索引 | 38.4 GB |
| 最大单个动态工作目录 | 17.1 GB |
| DiskANN rebuild、转换、临时文件、日志和 25% 防护余量 | 44.5 GB |
| **Pilot Atlas 上界** | **250 GB** |

Pilot 的顺序为 F0 → slim W0 → 三条 W1 trajectory 与 DiskANN rebuild 串行 → checkpoint-20 query；不并发索引构建或 churn。该顺序下建议预留 **2--3 个自然日、额外不超过 250 GB**。以当前 NVMe 余量计，完成 Pilot 后仍应有约 1.15 TB 空闲，不会触碰系统盘。

## 如 Pilot 显示 gap：完整 W0/W1 的扩展上界

完整矩阵仅在 Pilot 结果显示值得扩展时考虑；它不是当前启动授权。其空间估算如下，三套数据集的静态基线可以保留，但动态工作目录仍必须串行。

| 数据集 | 四系统静态索引 | 最大动态工作目录 | full + 5/10/20% checkpoint 数据与 GT | 主要时间构成 |
| --- | ---: | ---: | ---: | --- |
| SIFT10M | 38.4 GB | 17.1 GB | 约 22 GB，另按最坏情况保留 128 GB 源文件 | F0 12--24 小时；W0 及 W1 见下 |
| DEEP10M | 32.5 GB | 13.8 GB | 约 16.1 GB；base 已在 NVMe | build/load 6--10 小时 |
| GIST1M | 24.5 GB | 13.2 GB | 约 16.1 GB | build/load 2--4 小时 |

| 完整实验阶段 | 运行量 | 增量时间预算 |
| --- | --- | ---: |
| W0 | 4 systems × 3 datasets × 4 `Tq` × 4 settings × 3 repeats = 576 点，可合并为 144 cold sweeps | 10--22 小时 |
| W1 checkpoint query | 3 dynamic systems × 3 datasets × 3 checkpoints × 4 `Tq` × 4 settings × 3 repeats = 1,296 点，可合并为 324 sweeps | 22--48 小时 |
| W1 trajectories 与 DiskANN rebuild | 27 条 20% churn trajectories，加上 DiskANN checkpoint-20 rebuild | 34--96 小时 |
| **完整 W0/W1** | 不含 W2 | **4--8 天；保守上界 10 天** |

全量阶段按已完成数据集清理其可再生的动态工作目录和临时源副本后，额外容量保护值为 **500 GB**。这不是三套数据集每一份中间结果永久累加的需求；若不按清理协议执行，则不得启动下一个数据集。当前 NVMe 余量足以满足该上界，但仍应在空闲量低于 500 GB、任一阶段已分配字节超过该阶段预算 25%，或系统盘出现实验写入时立即停止。

## 执行前后的硬性检查

1. F0 脚本必须显式设置数据、索引、结果、临时目录到 `/home/ubuntu/pz/VectorDB/data`，并在启动时拒绝系统盘路径。
2. 每个系统一个幂等目录和完成标记；仅当 manifest、hash、退出码和资源记录齐全时标记完成。中断后只能重跑未完成系统，不能覆盖成功目录。
3. `tmux:f0-build`、`tmux:f0-query`、`tmux:w0-sweep`、`tmux:w1-churn`、`tmux:w1-checkpoint-query` 只能按依赖顺序启动；索引 build 与 churn 不得并发争用同一 NVMe。
4. F0 完成后必须以实测 build 时间、实际已分配空间和 source 下载大小更新此表，并重新提交是否进入 slim W0/W1 的 ETA；在此之前不启动正式负载。
