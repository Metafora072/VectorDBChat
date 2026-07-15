# Dynamic Vamana W1 1% Replace-New Canary 执行结果

## 执行结论

本次正式 W1 1% canary 在 checkpoint-1 exact GT(Ground Truth，精确真值集)验证阶段按门禁停止，未进入 DGAI、OdinANN 或 DiskANN 阶段。fresh execution preflight、CP01 trace、trace validation 和 active-vector materialization 均通过；`compute_groundtruth` 进程以 0 退出并写出形状为 `10000×100` 的 GT，但独立 validator 发现 query `7150` 的最后一个距离由正常的 `75212.0` 降为 `0.0`，违反距离单调性。控制器随即退出，未创建任何正式系统 clone，也未执行 80K insert/delete。

本结果属于有效的 fail-closed 停止，不支持任何 1% churn 性能或正确性结论。GPT 明确规定正式失败不得自动重试，因此当前保留全部产物并等待新的执行裁决；没有修复后重跑，也没有启动 5%/10%/20%、W2 或其他数据集。

## 自动门禁与启动状态

canonical v6 使用固定环境完成两次 clean build，DGAI 与 OdinANN 的 `w1_canary`、`search_disk_index` 四个目标均 byte-identical。DGAI 的 `ingest_begin` 已位于 `get_atlas_trace()` 之后；OdinANN 两轮 CMake 均通过宿主 io_uring runtime check，compile definition 包含 `USE_URING`，`ldd` 包含 `liburing` 且不含 `libaio`。

SIFT1M r08 在 update 前停止，原因是基于 r07 单次测量设置的 replay 专用区间过窄。该失败证据未覆盖。修正仅作用于 SIFT1M sanity gate，GPT 指定的 SIFT10M formal Recall 区间保持不变。随后 r09 完整通过两个系统各 3 次 pre-query、16-op update、post-query、active-set exact audit、live/fresh probe、immutable-base integrity、phase I/O 与 OOM 检查。

正式会话 `dv-w1-formal-0715` 在项目 NVMe `259:10` 上取得 global flock。`execution_preflight.json` 重新验证了 canonical binaries、DGAI/OdinANN/DiskANN 三个 checkpoint-0 base manifest、全部输入、compute-GT binary、OdinANN io_uring identity、systemd/NUMA/cgroup runtime 和约 1.398 TB 初始可用空间。检查时 CP01、checkpoint-1 GT、正式 attempt 和 stale-control 结果均不存在。

## GT 失败根因

失败由 `compute_groundtruth.cpp` 对合法 tag `0` 的哨兵歧义触发，而不是内存不足、磁盘不足或 GT 计算未完成。CP01 active-tag 文件包含 8,000,000 个 tag，tag `0` 仍为合法 active tag，位于 active-vector row `0`。`processUnfilteredParts()` 在启用 tags 时执行以下判断：

```cpp
if (location_to_tag[closest_points_part[i * k + j] + start_id] == 0)
    continue;
```

该代码把 tag `0` 解释为待过滤的无效哨兵。query `7150` 的 exact top-100 包含该 active tag，因此结果只收集到 99 项。后续写出逻辑没有初始化第 100 项，最终文件的该行尾部为 `id=0, distance=0.0`。GT 日志明确输出 `WARNING: found less than k GT entries for query 7150`。

结构审计结果为 `missing=0`、`finite=true`、`monotonic=false`。全文件仅有 1 个距离逆序，位置为 query `7150` 的索引 `98→99`；尾部距离为 `74929.0, 75110.0, 75212.0, 0.0`，对应 ID 为 `6163146, 1616043, 4513470, 0`。validator 对 query `0/17/9999` 的独立 brute-force audit 未先行报错，随后在全局结构门禁处停止。

## 时间、内存、I/O 与空间

| 阶段 | Wall time | Peak process-tree RSS | cgroup memory peak | OOM | NVMe read | NVMe write | Peak allocated space |
|---|---:|---:|---:|---:|---:|---:|---:|
| CP01 preparation | 4.902 s | 5,178,290,176 B | 4,298,792,960 B | 0 | 0 B | 0 B | 4,131,135,488 B |
| Exact GT + validation | 46.003 s | 20,604,805,120 B | 20,680,892,416 B | 0 | 3,059,712 B | 8,036,352 B | 8,007,680 B |

CP01 preparation 的设备读取为 0，是因为正式 preflight 对输入执行 SHA256 后相关数据仍在 page cache；该值按实记录，不用于动态系统 I/O 比较。exact GT 正常遍历全部 10,000 个 query batch 并写出完整 8,000,008 B truthset，整个正式控制器从 `14:27:20 UTC` 启动到约 `14:28:15 UTC` 停止。项目盘当前仍有约 1.394 TB 可用空间；相对启动时减少约 4.14 GB，主要由 `active_cp01.bin` 构成。

## 正确保留的证据

执行根目录为 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1/`。其中 `preflight/execution_preflight.json` 为 fresh preflight，`execution_manifest.json` 已标记 `stopped_failed`，`preparation/cp01_preparation_resources.json` 与 `preparation/gt_cp01_resources.json` 保存资源证据，`formal_controller.log` 保存完整停止链路。CP01 数据位于 `datasets/sift10m/w1_cp01/`，失败 GT 与日志位于 `groundtruth/sift10m/w1/`。

失败时不存在 `formal/pilot3_sift10m_w1/`，也不存在 `results/pilot3_sift10m_w1/DGAI`、`OdinANN` 或 `DiskANN`。因此没有部分更新 clone、没有系统间顺序污染，也没有可被误认为正式 canary 结果的成功标记。

## 后续裁决请求

如需继续，必须由 GPT 明确授权新的 attempt，而不能覆盖当前证据。建议的最小修订是让 dense active-tag GT 路径区分合法 tag `0` 与缺失哨兵，重新构建并冻结 compute-GT binary，再在新 GT 和 formal attempt 目录中执行；同时需明确 CP01 materialization 是否允许按冻结 hash 复用，以及 fresh preflight 对已存在失败目录的处理规则。在获得该裁决前，当前 W1 保持停止。
