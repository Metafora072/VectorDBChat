# Dynamic Vamana W1 R06 DiskANN Loader Stop 分析

## 结论

R06 于 `2026-07-16 17:18:11 UTC+8` 在 `diskann_stale_static_control` 阶段以退出码 `127` fail closed。直接原因是 DiskANN `search_disk_index` 启动时无法解析 `libtcmalloc.so.9.9.5`。该动态库实际存在且内容可读；为执行 DGAI 与 OdinANN 设置的运行时库路径只在 `w1_run_system_canary.sh` 内导出，没有传递到独立的 `w1_diskann_stale_control.sh` scope。因此，本次停止属于 DiskANN 正式编排缺少动态库环境，不支持算法错误、数据错误、OOM(Out of Memory，内存耗尽)或 NVMe 设备异常的解释。

R06 的 OdinANN `cp01-06` 已在停止前完整通过 identity-v2、80K update、online/fresh visibility、checkpoint-1 post-query 与 immutable-base audit。DiskANN 仅创建 stale-control 目录和 checkpoint-0 index manifest，并尝试第一条 `L=29, r1` 查询；二进制在加载阶段即失败，没有读取 NVMe、没有生成有效查询结果，也没有改变 immutable DiskANN base。R06 已正式写入 `stopped_failed`，不得续写、覆盖或复用该 run 名称。

## 失败证据

`execution_manifest.json` 的最终状态为 `stopped_failed`，`stopped_phase` 为 `diskann_stale_static_control`，`exit_code` 为 `127`。失败资源文件 `DiskANN/stale-cp00-06/L29_r1.resources.json` 记录的命令目标是 canonical DiskANN `search_disk_index`，wall time 为 `0.026126 s`，peak RSS 为 `0 B`，NVMe read/write 均为 `0 B`，`oom` 与 `oom_kill` 均为 `0`。对应日志给出的唯一直接错误为：

```text
search_disk_index: error while loading shared libraries: libtcmalloc.so.9.9.5: cannot open shared object file: No such file or directory
```

该信息说明动态链接器在进入程序主逻辑前失败。失败 binary 的 SHA256 为 `631fc53b4514fdac8325a7d789792ff6d19fb007e5442410898ec4a9505d4c3e`，与冻结 artifact manifest 中的 DiskANN binary identity 一致，不存在 binary 被替换的问题。

缺失库实际位于 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/build/gperftools-install/lib/libtcmalloc.so.9.9.5`，SHA256 为 `9035515aa26ebfaa2cf390291378e0ccba66175ba8291b92aa32e92f97a8b904`。不带环境运行 `ldd` 时该依赖显示为 `not found`；显式设置以下路径后，`ldd` 能精确解析到该文件：

```text
LD_LIBRARY_PATH=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/build/gperftools-install/lib
```

该对照验证了最小根因。`w1_run_system_canary.sh` 会在动态系统 scope 内导出 gperftools、OpenBLAS 与 jemalloc 路径，但 `w1_diskann_stale_control.sh` 没有等价设置；R06 launcher 创建 DiskANN scope 时也没有传入 `LD_LIBRARY_PATH`。因此，R06 首次真正到达 DiskANN stale control 后暴露了此前未覆盖的 formal-path loader 缺口。

## R06 有效证据边界

OdinANN identity-v2 gate 为 `pass`。query binary、driver、base/clone manifest、query、checkpoint-0 GT、active tags、单线程、`io_uring` 与设备 `259:10` 均精确匹配。Pre-update L29 Recall median 为 `0.95072`，L46 为 `0.97981`；Recall 仅作为观测，不参与 identity gate 裁决。

OdinANN 80K update 的 ingestion 为 `49.446224 s`，吞吐为 `1617.919 ops/s`；online visibility 为 `49.449186 s`，对应 `1617.822 ops/s`；fresh-process visibility 为 `147.467815 s`，对应 `542.491 ops/s`。Active set exact、18 个 fresh probe 与 18 个 online probe 均通过，六次 checkpoint-1 post-query 全部 exit 0 且结果 ID active。Update resource probe wall time 为 `150.808 s`，peak process-tree RSS 为 `2,148,999,168 B`，cgroup memory peak 为 `10,857,242,624 B`，无 OOM。Immutable OdinANN base 的 content 与 mode audit 均为 `pass`。

OdinANN private clone 的最终 formal tree apparent/allocated space 约为 `16,960,294,563/16,960,417,792 B`。R06 停止后，CP01 与 R02 GT preservation audit 为 `pass`，当前无遗留 root tmux、active `dv-w1-*` scope 或 worker。项目 NVMe 当前可用约 `1,340,080,599,040 B`。

以上证据支持将 R06 OdinANN 作为独立完成的 system-level canary 候选提交审议，但能否正式接受并参与 composed result，应由 Gpt 裁决。DiskANN R06 不包含任何有效性能或 Recall 样本。

## 建议的最小修复与回归

建议保留旧 R06 全部内容，不修改其 manifest、attempt 或停止报告。代码修复应为 DiskANN stale-control worker 显式建立冻结的 runtime library path，至少包含 artifact 对应的 gperftools install `lib`；不应依赖启动用户的交互式 shell 环境，也不应用系统级安装或修改 `/etc/ld.so.conf` 掩盖实验依赖。

启动新轮次前应新增 loader 回归。正向用例需要在与正式 DiskANN scope 相同的 `uid`、NUMA、环境清理和 binary identity 下证明全部 `DT_NEEDED` 依赖可解析，`libtcmalloc.so.9.9.5` 的 canonical realpath、size 与 SHA256 精确匹配。负向用例需要删除 `LD_LIBRARY_PATH` 后稳定复现退出码 `127` 与同一 loader 错误，并证明检查不运行查询、不创建 result、也不修改 immutable base。正式 worker 还应把实际 runtime library path 与 loader audit 写入 preflight evidence，而不是只依赖 shell 变量。

## 请求 Gpt 裁决

建议 Gpt 审议以下 continuation 边界。第一，是否接受 R06 OdinANN `cp01-06` 为独立有效证据，与已经接受的 R05 DGAI 对等冻结。第二，是否授权全新 R07 只执行 DiskANN stale-static control，不重跑 DGAI、OdinANN、CP01 或 R02 GT。第三，若 R07 通过，最终报告是否允许明确组合 R05 DGAI、R06 OdinANN、R07 DiskANN 与 R02 GT，并继续声明这些证据不是同一个无中断 attempt。

若授权，建议使用全新 `pilot3_sift10m_w1_r07` 与 `stale-cp00-07`。R07 不创建动态系统 clone，只读查询现有 immutable DiskANN checkpoint-0 base，并对 R02 checkpoint-1 GT 执行冻结的 L29/L53、每点 3 次 stale-static control。预计新增结果空间低于 `1 GiB`，保守 wall time 为 `5–20 分钟`；仍应持 global flock，验证 R06 stop、OdinANN frozen evidence、R02 GT/CP01 preservation、DiskANN base manifest、binary/library identity、项目盘设备与 free-space，并在任一失败时立即停止且不复用 R07。
