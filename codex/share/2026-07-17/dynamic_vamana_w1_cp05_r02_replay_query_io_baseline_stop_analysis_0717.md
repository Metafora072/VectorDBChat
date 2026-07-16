# Dynamic Vamana W1 CP05 R02 Replay Query I/O Baseline 停止分析

## 停止结论

`pilot3_sift10m_w1_cp05_trajectory_r02` 已于 `2026-07-17 00:15:39 UTC+8` 激活 execution manifest，并于 `00:16:03 UTC+8` 在 `replay_DGAI` 以 `exit_code=1` fail closed。直接错误为 `expected exactly one cgroup io row for device 259:10`。该 R02 identity 已成为正式 terminal attempt，不得重试、续写或复用。

停止发生在 DGAI 1M replay 的 CP00 query gate。DGAI `L64/L128` 各三次查询均返回码 0，六次 `36×10` result IDs 完整、无 sentinel、全部属于 CP00 active set，Recall 诊断值分别稳定为 `0.9833/0.9917`，无 `oom`、`oom_kill` 或 `oom_group_kill`。但是通用 `query_checkpoint()` 路径没有使用 static smoke 新增的同 scope I/O baseline primer，资源探针的首样本均无 `259:10` 行，`resource_read_delta()` 因而在汇总第一点时拒绝证据。

## 影响范围

启动前的 immutable replay-base live verification、DGAI/OdinANN 四点 static smoke、R02 formal/replay input 重新派生、旧新 byte identity、inode disjointness 和 R02 preflight 均为 `pass`。Static smoke 汇总 SHA256 为 `5c9f2189a5c37c29d052c3593bc5cdd4f635b050cb6bbbf60a857b49b7be09c3`；DGAI `L64/L128` device-read delta 为 `190,394,368/199,434,240 B`，OdinANN `L29/L46` 为 `35,639,296/38,027,264 B`。

正式 R02 只创建了 DGAI replay mutable clone `pilot3_w1_cp05_trajectory_replay_r02/DGAI/sequential-cp80-02`，allocated size 为 `1,415,319,552 B`。它只执行 CP00 查询，没有启动 16-record CP01 update worker，也没有创建 CP01/CP05 checkpoint。OdinANN replay clone、SIFT10M formal clone/update 和 DiskANN CP05 stale control 均未创建或执行。R02 result tree allocated size为 `7,204,864 B`，其中包含 frozen inputs、preflight、自测、六次 CP00 raw query 和 terminal manifest。

Stop-time preservation 为 `pass`、`mismatches=[]`。R02 formal/replay inputs、trajectory/GT、canonical binaries、immutable replay bases、static smoke 和历史 terminal attempt 等受保护工件未发生漂移。root tmux 与 transient scopes 已自然退出，失败通知由 MailSender 以 HTTP 202 接受。项目 NVMe 当前可用 `1,323,735,105,536 B`，没有在系统盘生成大工件。

## 根因与建议修复

Static smoke 的 primer 只集成在顶层 `run_static_smoke()`，没有下沉到共享 cumulative runner 的 `query_checkpoint()`。因此，顶层四点 smoke 可以建立 baseline 并通过，而 replay/formal 的 CP00、CP01、CP05 query scopes 仍从空 `io.stat` 开始。实际查询随后产生 device rows，但 `w1_cumulative_evidence.py` 明确要求 `samples[0]` 与末样本各恰有一个目标设备行，后续样本不能补写缺失的零点。

建议 GPT 为全新 R03 attempt 授权最小修复。共享 `query_checkpoint()` 中的每个 query scope 应在 `resource_probe.py` 启动前执行同一 `4 KiB O_DIRECT` primer，随后仍由 probe baseline 之后的正 read-byte/read-I/O delta 门禁查询。启动前应增加同一 runner 的正向集成 fixture，精确断言 `samples[0]` 与末样本各有一个 `259:10` 行且净增量为正，并增加移除 primer 后首样本稳定缺行的负向 fixture。

是否复用已冻结的 immutable replay bases 与四点 static smoke、是否要求 R03 重新派生 formal/replay inputs，以及 R03 的 run/attempt identities，应由 GPT 明确裁决。R02 的 DGAI replay clone和六次 CP00 查询只能作为失败定位证据，不能作为通过的 replay checkpoint。CP10 与 CP20 继续 HOLD。
