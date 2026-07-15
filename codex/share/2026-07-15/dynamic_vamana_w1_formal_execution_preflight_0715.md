# Dynamic Vamana W1 正式执行预检结果

## 裁决

F7–F12 已关闭，只读 formal preflight 和修订后的 SIFT1M 16-replacement formal-path replay 均通过。成功回放为 `pilot3_w1_formal_path_replay_r07`，使用两次 clean build 可逐字节复现的 canonical binaries，其中 OdinANN 明确为 `IO_ENGINE=uring`。正式 SIFT10M CP01、8M checkpoint-1 物化、10K×8M exact GT、SIFT10M index clone、80K updates 与 DiskANN stale control 均未执行，正式 W1 继续保持 HOLD。

## Formal 与 micro artifact map

micro 与 formal 继续共用 `w1_run_system_canary.sh` 和 `w1_system_worker.sh`。唯一入口 `run_w1_cp01_formal.sh` 现在只接受 `preflight`、`micro` 或另行授权的 `formal`，并在进入任一系统前取得同一 global flock、验证 canonical binary SHA256 和解析显式 artifact map。

| 字段 | micro | formal |
| --- | --- | --- |
| trace | `trace.bin` | `replace_cp01_80k.bin` |
| expected active tags | `active.tags.bin` | `active_cp01.tags.bin` |
| probe queries | `probes.bin` | `visibility_probes.bin` |
| probe specification | `probes.json` | `visibility_probes.json` |
| active vectors | micro preparation 内部产物 | `active_cp01.bin` |
| full corpus | `datasets/sift1m/full_1m.bin` | `datasets/sift10m/full_10m.bin` |
| operation count | 16 | 80,000 |
| attempt | `replay-01` | `cp01-01` |

shared runner 不再依据 `mode` 或 `dataset-dir` 拼接 corpus 文件名，而是要求显式 `--full-corpus`。每个 attempt 都在更新前写入 `attempt_artifacts.json`，记录 corpus、trace、active tags 和 probes 的 realpath、大小与 SHA256。

## SIFT10M base 与 clone 约束

formal base 已修正为通过 P1R08 F0 的两个 8M index。DGAI base 为 `formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index`，其确定性目录 manifest SHA256 为 `980ce1c3ed6eb5bef4a595c74dab641b5cd5da5a606786c753d3d00cd5ddcaa5`。OdinANN base 为 `formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index`，manifest SHA256 为 `50d5aacb142bf352c0fb63920cc85573fdced5dccf9d7c5dd16586442b3a0a4e`。preflight 重新读取全部 index 内容并与冻结值精确匹配。

`w1_clone_base.sh` 只接受 `formal/pilot3_w1_formal_path_replay_*/*/*` 与 `formal/pilot3_sift10m_w1/*/*`，不接受宽泛的 `formal/*`。原有 `|| true` 已移除，formal base realpath 不符合对应 P1R08 F0 路径时会直接终止。

## OdinANN io_uring identity

OdinANN patch 顺序固定为 system `liburing`/CBLAS compatibility、非特权 basic-ring compatibility、禁止 AIO fallback、result-ID、W1 driver 和 CMake target。CMake 两次均输出 `Using system liburing for asynchronous I/O`，`compile_commands.json` 均包含 `-DUSE_URING`，两个 canonical binaries 的 `ldd` 均包含 `liburing.so.2` 且不包含 `libaio`。r07 的 OdinANN update 与 query binary 来自同一个 canonical build tree，并实际完成 io_uring 查询和更新状态机；配置或运行时无法建立 io_uring 时会 fail closed，不会改用 AIO。

原始项目的 uring 探测同时要求 `IORING_SETUP_SQPOLL`，普通 `ubuntu` 进程会因权限不足返回 `EPERM`。compatibility patch 将可用性测试和 query ring 改为无特权的 basic io_uring，仍使用 `USE_URING`、`liburing` 与 io_uring submission/completion path，不引入 AIO fallback。

## Canonical rebuild identity

两次构建均从冻结 upstream commit 的独立 clean source 展开，应用相同 patch 顺序，并固定 `SOURCE_DATE_EPOCH=1721001600`、compiler/linker、dependency realpath、locale、时区、`-ffile-prefix-map`、`-fdebug-prefix-map` 与 `-fmacro-prefix-map`。项目 CMake 会把 build-tree `third_party/liburing` 写入 RUNPATH，该路径使 linker build-id 随 run 目录变化；canonical v4 使用 `CMAKE_SKIP_RPATH=ON`，运行时依赖仍由冻结 system library 和 runner 的 `LD_LIBRARY_PATH` 提供。

| 系统与目标 | run1 SHA256 | run2 SHA256 | byte-identical |
| --- | --- | --- | --- |
| DGAI `w1_canary` | `6ba762d385492a867d7c1f2c9383a6f662fd00d107b66038e5eb8538c701adc9` | 同左 | 是 |
| DGAI `search_disk_index` | `778a02b929adfd138ca90caa05c5876d7d683290743d061b5d6777710d01ed5e` | 同左 | 是 |
| OdinANN-uring `w1_canary` | `647ddb05495bc767881f5354fb09684cdedf7f4718cd6ccdb0743e5ae6443eb8` | 同左 | 是 |
| OdinANN-uring `search_disk_index` | `36c17a96266998aee3505619a8b8c7260898b7565faaa4d5cf0237ad91c5082c` | 同左 | 是 |

构建证据位于 `build/w1-canonical-v4/`，共享冻结身份位于 `artifact_rebuild_manifest.json`。orchestrator 和 shared runner 都会在 clone 或 update 前重新计算 binary SHA256；OdinANN 还会重验 CMake log、compile definition 与 `ldd`。

## Read-only formal preflight

`run_w1_cp01_formal.sh preflight` 已通过，机器可读结果为 `results/pilot3_sift10m_w1/preflight/formal_preflight.json`。该 JSON 包含全部 resolved realpaths、文件大小、SHA256、正式 artifact map、F0 base manifest、canonical binaries、实验设备 `259:10`、free space、通知配置以及 systemd/NUMA/cgroup runtime canary。

执行时项目 NVMe 可用空间为 `1,410,794,983,424` bytes，超过 150 GB 门禁。`datasets/sift10m/w1_cp01` 与 `formal/pilot3_sift10m_w1` 均不存在，说明 preflight 没有生成 CP01、没有 clone index。预检约耗时 31 秒，结果目录占用约 12 KiB，主要时间用于只读重算两个 F0 base 和正式输入的 SHA256。

## Canonical SIFT1M replay

成功 run `pilot3_w1_formal_path_replay_r07` 使用 formal 相同的 artifact-map resolution、binary verification、global lock、shared runner、systemd scope、CPU 0–23、NUMA node 0 和 NVMe `259:10` accounting。DGAI 与 OdinANN 严格串行，均完成 clone、pre-update query、16 replacements、visibility、active-tag exact audit、post-update query 和 final immutable-base manifest。

| 系统 | pre Recall@10 | post Recall@10 | visibility | active/base integrity |
| --- | --- | --- | --- | --- |
| DGAI | L64 `0.9889`，L128 `1.0000` | L64 `0.9889`，L128 `1.0000` | online unsupported；fresh 18/18 | 800K exact；pass |
| OdinANN-uring | L29 `0.9833`，L46 `0.9944` | L29 `0.9778`，L46 `1.0000` | live 18/18；fresh 18/18 | 800K exact；pass |

这些数值来自 18-query micro exact GT，仅证明路径与身份集成正确，不是正式 W1 性能结论。两个 `FORMAL_W1_CANARY_OK` 和全局 `FORMAL_PATH_REPLAY_OK` 均存在，return code 与 cgroup OOM 均为 0，结束后没有遗留 `w1_canary` 或 query 进程。

phase I/O sampler 已移除每个 25 ms 周期内昂贵的 `smaps_rollup` 与目录遍历，并使用固定 deadline；cgroup memory peak 仍由内核计数器记录。r07 的 DGAI 实测采样周期中位数为 25.005 ms、最大值为 25.888 ms，OdinANN 分别为 24.992 ms 和 26.081 ms。ingest、publish、fresh 与 end-to-end 的 begin 前最后一个和 end 后第一个 sample 均完成 bracket 并报告两侧 skew。OdinANN 约 4 ms 的 online probe 继续标记为 `not_resolvable_at_sampling_interval`，没有输出伪精确 I/O delta。

## 时间、空间与失败审计

canonical v4 双重 clean build 从首个 CMake log 到成功标记约 204 秒，占项目 NVMe 约 1.6 GiB。r07 从首个 micro input 到全局成功标记约 36.3 秒，当前占用约 2.9 GiB formal clone、394 MiB input 和 456 KiB result，共约 3.3 GiB。实验根仍位于 `/dev/nvme8n1`，当前总占用约 431 GiB、可用约 1.3 TiB；本轮没有在系统盘写实验 artifact。

失败证据均保留且未覆盖。`w1-canonical-v1` 因手写 patch hunk 元数据错误停止，约占 411 MiB；v2 因 sandbox seccomp 阻止 io_uring runtime probe 停止，约占 411 MiB；v3 的四个 target 均构建成功，但 build-tree RUNPATH 导致 binary build-id 不一致，约占 1.4 GiB；r06 在 DGAI 完成后因 sampler 标称 25 ms、实际中位约 43 ms且一次间隔 153 ms而被 collector 拒绝，未启动 OdinANN，formal clone 约占 1.4 GiB。上述失败 artifact 合计约 3.6 GiB，目前未擅自删除。

## 审阅请求与停止边界

请 Gpt 审阅 F7–F12、formal preflight 和 canonical OdinANN-uring r07 replay。当前实现已经具备 formal artifact preparation 的串行结构，但本轮没有获得执行正式 CP01、exact GT、80K updates 或 DiskANN stale control 的授权，因此保持停止，不会自行进入 SIFT10M W1。
