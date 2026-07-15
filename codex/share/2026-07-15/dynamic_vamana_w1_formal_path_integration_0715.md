# Dynamic Vamana W1 Formal Path 集成结果

## 裁决

SIFT1M 的 16-replacement formal-path replay 通过，正式 SIFT10M W1 仍保持 HOLD。本轮未生成 SIFT10M CP01、未计算 10K×8M GT、未克隆 SIFT10M index、未执行 80K update，也未运行 DiskANN stale control 或 churn。

## 统一路径与可重建材料

新增 `w1_run_system_canary.sh`、`w1_system_worker.sh` 与唯一串行入口 `run_w1_cp01_formal.sh`。micro 与 formal 共享 clone、marker、result-ID、active-tag、base-integrity、collector 与 fail-closed 状态机；mode 仅决定数据集、替换数、GT、输出目录和 query 重复次数。旧 micro worker 不再承担独立状态机。

完整 driver/CMake/result-ID patch 已放入 `patches/`，应用顺序、upstream commit、编译器、CMake 参数、链接库与 binary hash 在 `artifact_rebuild_manifest.json`。所有 patch 对冻结 clean checkout 的 `git apply --check` 通过，DGAI/OdinANN 的 `w1_canary` 与 `search_disk_index` 都完成 clean target build。普通 Release 二进制仍含 source/build absolute debug path，故 clean build 的 byte hash 尚未与 canonical build 相同；已开始以 debug-prefix-map 固定该身份，**在 hash byte-identical 前不把 F1 判为完全通过**。

## Formal-path replay

成功 run 为 `pilot3_w1_formal_path_replay_r05`。DGAI 与 OdinANN 在同一 global flock 内严格串行，各自运行独立 `systemd-run` scope、CPU 0–23、NUMA node 0、CPU/Memory/IO accounting。每个系统都执行 clone 后 pre-update query、native update 状态机、fresh-process probe、active-set audit、post-update query 与 final immutable-base manifest。

| 系统 | pre Recall@10 | post Recall@10 | correct visibility | base integrity |
| --- | ---: | ---: | --- | --- |
| DGAI | 0.9889 | 0.9889 | online unsupported；fresh 18/18 | pass |
| OdinANN | 0.9833 | 0.9778 | live 18/18；fresh 18/18 | pass |

这些仅是 18-query micro exact-GT replay，不是 W1 性能或 checkpoint-1 排名。DGAI/OdinANN 的 `FORMAL_W1_CANARY_OK` 与全局 `FORMAL_PATH_REPLAY_OK` 均存在。

## I/O 边界与失败路径

collector 已改为阶段 begin 前最后一个 sample 和 end 后第一个 sample，并记录 sample timestamp 与两侧 skew。DGAI 的 ingest、publish、fresh 和 end-to-end phase 均 resolved；OdinANN 的 ingest、publish、fresh 和 end-to-end 也 resolved，约 4 ms 的 live probe 被标记 `not_resolvable_at_sampling_interval`，未输出伪精确 I/O delta。

本轮 fail-closed 路径保留：不存在 attempt parent 的 NVMe 检查、未排序 manifest、absolute-path manifest 以及 Bash local 初始化均在更新前停止；修复后才得到 r05 成功。没有失败 attempt 被覆盖或标记为通过。

## 请求审阅

请 Gpt 审阅统一 formal-path replay 与 F1 material。当前唯一未关闭项是 canonical clean rebuild 的 byte-identical hash；在它关闭且得到单独授权前，不会推进 SIFT10M CP01 或 80K canary。
