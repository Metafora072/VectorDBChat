# ZNS-ANN Z0A-R2 Final Closure

## 最终裁决

本轮裁决为 `PASS-SEQUENCE-ONLY`。Z0A 的 write sequence、page-version lifecycle 与 sequence-based reclaim 输入可以保留，但 timestamp、inter-arrival、age、burst duration 及任何依赖 wall-clock 的 GC 结论全部禁用。该裁决不自动授权 Z0B；在 Gpt 审阅并单独批准 Z0B scope 前，执行在此停止。

`PASS-TEMPORAL` 未通过。DGAI 的 `FULL/SHIM` paired median 为 -3.64%，90% bootstrap CI 为 [-13.90%，+22.99%]；OdinANN 的对应结果为 +7.32%，CI 为 [-6.68%，+10.45%]。两者 CI 均未完全落入 [-5%，+5%]。本轮没有删除 outlier、追加重复或更换统计口径，也没有将 FULL 更快解释为优化。

## 范围与方法

实验只使用既有 SIFT10K、2,000 replacement 短负载，分别运行 DGAI 与 OdinANN。未运行 400K、Z0B、synthetic ANN-specificity、FEMU、参数 sweep、ZoneEpoch 或论文实验。NATIVE 使用不依赖 `libz0atrace.so`、无 `LD_PRELOAD` 的独立 binary；SHIM-CONTROL 与 FULL-TRACE 使用同一 binary 和同一 tracer library，区别仅为 `ATLAS_Z0A_MODE`。SHIM 执行相同的 interposition、FD/object identity、phase/source 与固定 buffer 初始化，但不分配序号、不取时间戳、不追加 record，也不输出 trace。

每个系统先执行一个不计入分析的 warmup triplet，再执行 12 个正式 triplet。六种三模式排列各出现两次，固定随机种子为 `20260719`，78 个 run 全部保留。运行固定绑定 NUMA node 0 的 32 个逻辑核 `0-27,56-59`，并将内存绑定到 node 0。全部实验数据写入 `/dev/nvme8n1` 上的 `z0a_r2_final_closure_0719`，未占用系统盘。

实验于 UTC+8 的 2026-07-19 15:35:32 至 15:56:30 执行，端到端历时 1,258.42 秒；78 个 workload 的 wall time 合计 473.76 秒。实验根实际占用约 3.1 GiB，从正式运行前的 2,654,912,512 字节增加到 3,274,997,760 字节，低于预登记的 16 GiB 空间门禁；结束时 NVMe 仍有约 850 GiB 可用空间。

## Timing 结果

主统计量为每个 triplet 内的 `log(FULL/SHIM)` 与 `log(SHIM/NATIVE)`，按 triplet 整块执行 100,000 次 bootstrap。汇总结果如下。

| 系统 | 对比 | paired median | 90% bootstrap CI | ±5% 等价门槛 |
|---|---:|---:|---:|---:|
| DGAI | FULL / SHIM | -3.64% | [-13.90%，+22.99%] | FAIL |
| DGAI | SHIM / NATIVE | +7.38% | [-4.07%，+24.68%] | FAIL |
| OdinANN | FULL / SHIM | +7.32% | [-6.68%，+10.45%] | FAIL |
| OdinANN | SHIM / NATIVE | +3.61% | [-2.28%，+10.91%] | FAIL |

DGAI 的全部原始 wall time 与 paired effect 如下，时间单位为秒。

| Triplet | 顺序 | NATIVE | SHIM | FULL | FULL/SHIM | SHIM/NATIVE |
|---:|---|---:|---:|---:|---:|---:|
| 1 | N/S/F | 7.926 | 8.066 | 7.438 | -7.79% | +1.77% |
| 2 | F/S/N | 8.369 | 9.137 | 7.367 | -19.37% | +9.17% |
| 3 | N/S/F | 8.036 | 6.446 | 8.124 | +26.02% | -19.78% |
| 4 | N/F/S | 7.345 | 10.437 | 5.999 | -42.52% | +42.09% |
| 5 | N/F/S | 7.090 | 9.675 | 7.570 | -21.75% | +36.46% |
| 6 | S/F/N | 6.330 | 6.072 | 10.879 | +79.15% | -4.07% |
| 7 | F/N/S | 6.161 | 7.608 | 9.357 | +22.99% | +23.48% |
| 8 | S/N/F | 8.047 | 6.626 | 9.702 | +46.42% | -17.65% |
| 9 | F/S/N | 8.836 | 11.017 | 10.548 | -4.26% | +24.68% |
| 10 | S/F/N | 6.623 | 11.452 | 9.859 | -13.90% | +72.91% |
| 11 | S/N/F | 10.629 | 10.042 | 9.859 | -1.83% | -5.52% |
| 12 | F/N/S | 9.732 | 10.279 | 9.969 | -3.02% | +5.62% |

OdinANN 的原始结果如下。

| Triplet | 顺序 | NATIVE | SHIM | FULL | FULL/SHIM | SHIM/NATIVE |
|---:|---|---:|---:|---:|---:|---:|
| 1 | N/S/F | 3.384 | 3.630 | 3.816 | +5.14% | +7.25% |
| 2 | F/S/N | 3.614 | 3.531 | 3.865 | +9.44% | -2.28% |
| 3 | N/S/F | 3.298 | 3.696 | 3.890 | +5.25% | +12.08% |
| 4 | N/F/S | 3.484 | 4.086 | 3.495 | -14.46% | +17.27% |
| 5 | N/F/S | 3.207 | 3.259 | 3.576 | +9.75% | +1.62% |
| 6 | S/F/N | 3.080 | 3.708 | 3.105 | -16.28% | +20.41% |
| 7 | F/N/S | 3.476 | 3.543 | 3.306 | -6.68% | +1.92% |
| 8 | S/N/F | 3.198 | 3.546 | 3.894 | +9.81% | +10.91% |
| 9 | F/S/N | 3.950 | 3.093 | 3.927 | +26.97% | -21.71% |
| 10 | S/F/N | 3.970 | 3.182 | 3.896 | +22.44% | -19.84% |
| 11 | S/N/F | 3.663 | 3.858 | 3.431 | -11.08% | +5.34% |
| 12 | F/N/S | 3.313 | 3.202 | 3.711 | +15.91% | -3.37% |

六种顺序在两个系统中均各出现两次。按 position 汇总后，DGAI 的 NATIVE 中位数为 7.636/8.889/7.496 秒，SHIM 为 8.334/8.602/9.977 秒，FULL 为 9.663/8.715/8.913 秒；OdinANN 对应为 NATIVE 3.341/3.395/3.782 秒、SHIM 3.627/3.581/3.401 秒、FULL 3.788/3.536/3.853 秒。结果存在明显 run-order 与系统噪声，平衡顺序避免了单一顺序偏置，但没有把 CI 收窄到工程门槛内。由于 sequence-only 证据已经闭合，且继续针对已观察 timing 追加 run 会违反禁止 run-until-pass 的规则，本轮不消费可选的第二轮实现优化。

## Write structure 与自然波动

所有 78 个 run 的 active set 均通过。26 个 FULL run（含两个 warmup）的 trace 均为零 dropped events、零 failed requests、零 submit/timestamp inversion；raw request、normalized page 与自账本全部闭合。

DGAI 的 common mode-neutral oracle 在 36 个正式 run 中完全一致。每次均记录 90,447,872 application bytes、19,330 async requests、22,082 page events、3,166 unique logical pages，phase 与 role 计数也完全一致。因此 tracer 没有改变 DGAI 的 write structure。

OdinANN 使用 NATIVE 与 SHIM 的 pooled range 定义自然并发波动尺度，不使用显著性检验。FULL 相对 SHIM 的 paired median shift 如下。

| 指标 | NATIVE/SHIM 自然尺度 | FULL−SHIM paired median | 是否位于尺度内 |
|---|---:|---:|---:|
| application bytes | 344,064 | -14,336 | PASS |
| request count | 149 | -6 | PASS |
| page-event count | 84 | -3.5 | PASS |
| insert phase requests | 149 | -6 | PASS |
| neighbor-repair requests | 84 | -3.5 | PASS |
| unique logical pages | 37 | +1 | PASS |

六项指标均未出现所有 FULL 样本系统性落在 NATIVE/SHIM 分布同一侧之外的现象。因此 OdinANN 的 FULL 偏移没有超过自然并发波动。

## Sequence-only 稳定性

DGAI 的 12 条正式 FULL trace 具有相同 sequence fingerprint，`versions per page`、sequence reuse distance、per-update fanout、phase-local page concentration 与 first/last version span 的所有 pairwise distance 均为 0。

OdinANN 的 12 条 FULL trace 因原生并发而具有 12 个不同 fingerprint，但分布变化保持在同一自然波动尺度。跨 run 最大 KS 距离分别为 versions per page 1.14%、reuse distance 1.03%、per-update fanout 2.55%、first/last span 3.52%；对应最大 normalized Wasserstein-1 距离分别为 1.22%、0.97%、0.42%、1.08%。phase-local concentration 的最大绝对差为 0.152%，且 phase set 始终相同。这些证据支持提交顺序与 page-version lifecycle 的 sequence-only 使用，但不支持 timestamp、age 或持续时间主张。

未来若 Gpt 单独授权 Z0B，每个系统必须使用多个独立 FULL trace realization，不得只使用单条 trace，也不得引入 age-based victim policy 或 wall-clock 可持续性结论。

## Canonical packing 与独立回放

Canonical packing 严格按 `(file_role, stable_object_id, aligned_offset)` 排序，每个 initial-live page 以一个完整 4 KiB logical-page version 顺序物化。DGAI 初始快照包含 4,428 页、18,111,652 logical bytes，对应 18,137,088 allocated append bytes 与 25,436 padding bytes；OdinANN 包含 1,752 页、7,168,436 logical bytes，对应 7,176,192 allocated append bytes 与 7,756 padding bytes。所有 initial pages 均恰好出现一次，无 page-key collision，zone capacity、open/active 与 host-spare 约束全部闭合。

旧 DGAI trace 因缺失截断事件会留下 1,499 个 EOF 外尾页。R2 在与 write submission 共用的 `global_seq` 域中记录到一次成功的 `TRUNCATE`，文件从 12,972,032 字节收缩到 6,832,128 字节；独立 validator 据此移除 1,499 页，最终 4,428 页与真实 snapshot 完全相等。该修复来自实际 lifecycle instrumentation，不使用 final snapshot 反推删除列表。

独立 validator 对全部 26 个 FULL run 重新读取 initial manifest、physical image/map、raw trace、normalized pages、ordered lifecycle 与 final snapshot，全部通过。主 simulator 与独立 reference 对每个真实事件比较 logical map/current version、zone slot/WP/live-invalid 状态、victim、relocation、reset 与 byte counters；DGAI 每条为 22,251 个事件，OdinANN 约 24.2K 个事件，全部逐事件一致。短 trace 在固定 32-zone closure geometry 下未触发 GC，因此 relocation 与 reset 均为 0；由此产生的 HostWA=1 仅是接口闭环结果，不是 ANN/ZNS 研究结论。

## 唯一 materialization 语义

R2 固定采用完整 4 KiB logical-page version。每个 successful raw write 先按实际 byte range 拆分到 touched pages；每个 page event 无论 fragment 大小均追加 4,096 allocated bytes。Partial replacement 使用当前页未修改字节重建完整页，该部分计为 RMW read cost，不重复计入 ZNS write；首次出现的 partial new page 对未写区域 zero-fill。Relocation 若发生，同样按每个 current page 4,096 bytes 计入 allocated relocation bytes。

DGAI 每条 FULL trace 的 91,127,960 application/normalized fragment bytes 对应 91,136,000 allocated append bytes，差额为 8,040 replacement RMW read bytes。以 OdinANN 正式 triplet 1 为例，99,169,304 application bytes 对应 99,221,504 allocated append bytes，其中 replacement RMW read 为 39,280 字节，new-page zero-fill 为 12,920 字节。application bytes、normalized fragment bytes、allocated append bytes 与 relocation allocated bytes 因而没有混用。

## 证据与停止点

统计证据位于 `codex/share/2026-07-19/zns_ann_z0a_r2/evidence/paired_analysis.json` 与 `sequence_audit.json`。实现、packing/readback 审计、重放器与 runner 位于 `codex/share/2026-07-19/zns_ann_z0a_r2/`。不可提交的大型 run artifact 保存在 NVMe 的 `z0a_r2_final_closure_0719` 中。

结论只支持 `PASS-SEQUENCE-ONLY`。当前证据不支持 temporal fidelity，不支持短点 HostWA 研究主张，不支持 ANN-specificity，也不自动授权 Z0B。本轮在提交报告与对话供 Gpt 审阅后停止。
