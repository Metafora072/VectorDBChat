# ZNS-ANN Z0A Trace / Model Preflight 实验报告

## 执行结论

Z0A 已在 2026-07-19 05:00:49 UTC+8 完成当前轮次。实验严格停留在 GPT 批准的 preflight 范围内，仅运行 DGAI 与 OdinANN 的 SIFT10K 短点、trace-off/on 重复、initial-live manifest 恢复、host-managed ZNS 模拟器手工 oracle 验证和空间闭合。未运行 400K、FEMU、synthetic trace、参数 sweep 或 Z0B。

本地严格判定为 `HOLD`，不提交 Z0B。26 个正式 run 均成功，13 个 trace-on run 均达到零丢失、零失败请求、零时间戳序列逆序、request-to-page 字节闭合、accepted M0 profiler 精确闭合和 active-set 精确通过。DGAI 的 trace-off/on 写结构完全相同，OdinANN 的 trace-off 自身存在约 `0.2%` 的内部并发波动，off/on 主要计数区间虽重叠，但不能据此证明统计等价。更关键的是，采用 8 次平衡顺序重复后，DGAI 的 trace-on/off 中位 wall-time 绝对差异为 `7.51%`，仍超过 `5%` 工程门槛。因此 Z0A 当前不能判 PASS，但也没有证据触发方向 KILL。

## 范围与工作负载

正式工作负载位于非系统盘 `/dev/nvme8n1`，设备号为 `259:10`。每个系统从现有 SIFT10K sanity index 的独立 clone 开始，顺序执行 2,000 次 replacement insert，删除 tag `0–1999` 并插入 tag `10000–11999`。预期最终 active set 为 tag `2000–11999`，共 10,000 个点。该短点为 DGAI 产生 19,333 个 application write requests，为 OdinANN 产生约 19,800 个 requests，均位于门禁要求的 $10^4$ 至 $10^5$ 区间。

DGAI 最终包含 trace-off/on 各 8 次，执行顺序由前 3 组 off→on、后 4 组 on→off和最后 1 组 off→on 构成，整体达到 4 组 AB 与 4 组 BA。OdinANN 最终包含 trace-off/on 各 5 次，其中 3 组 AB 与 2 组 BA。正式结果根目录为 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/z0a_trace_model_preflight_0719`。当前整个 Z0A 工作树实际占用 592,934,461 B，其中 mutable clones 为 485,011,058 B，结果文件为 83,552,753 B，输入为 3,317,839 B。

供远程审阅的聚合证据已复制到 `zns_ann_z0a/evidence/`。其中 `z0a_run_summary.json` 包含 26 个正式 run 的 wall time、accepted counts、trace counts 与 closure 状态，`space_preflight_final.json` 包含磁盘和 RAM 分项预算，`simulator_tests.txt` 包含 10 个手工 case 的逐项结果。大体积 clone、raw trace 和 normalized binary 仍保留在项目 NVMe，不提交到 Chat 仓库。

## Trace 实现与闭合

统一 trace schema 覆盖 DGAI 的 `libaio`、OdinANN 的 `io_uring` 以及 POSIX write entrypoints。原始记录包含全局序号、线程序号、单调时间戳、系统、run identity、device、inode、run-scoped object incarnation、file role、phase、source entrypoint、offset、length、update identity 与 batch identity。规范化记录使用 `(run_hash, object_incarnation, aligned_page_offset)` 作为稳定 page key，并保留 request 与拆分 page 的双向映射。

最终 r08 tracer 使用 65,536 records 的固定容量 buffer，峰值为 10,223,616 B。异步引擎持有的长生命周期 FD 使用 thread-local identity cache，短生命周期 POSIX FD 每次以 `fstat()` 验证 device 与 inode。该设计修复了 r06 中 FD 复用造成的 57 B 账本偏差，同时避免在约 20,000 个异步写请求上重复执行 `readlink()` 和全局对象表加锁。r08 独立自测覆盖 DGAI `libaio`、OdinANN `io_uring`、POSIX 写和 FD 复用，结果为 3 requests、4 page events、11,144 B、2 objects、零丢失和零 identity error。

系统集成以 frozen M3 source 的独立 copy 为基线，没有修改或覆盖 M0–M3 artifact。可复现 source patches 位于 `zns_ann_z0a/trace/patches/`，两份 patch 均已对 M3 source 执行 `git apply --check`。正式二进制 SHA-256 如下。

| Artifact | SHA-256 |
|---|---|
| DGAI `z0a_canary` | `2cad57e8169e538c5e4a219cc39a1deb3a89efa2197e8596c7afc3a666694f1b` |
| OdinANN `z0a_canary` | `6835d711a1296508e4d39a311afcae2d6552db153b6537dbc222bf61581b4119` |
| r08 `libz0atrace.so` | `69e3ad21958704f621ee420c482ae035c3434f91c6f35f6a9c09354034393dd0` |

## 正式结果

### DGAI

| 模式 | Wall time 范围，秒 | 中位数，秒 | Application bytes | Requests | Page events | Dropped / inversions |
|---|---:|---:|---:|---:|---:|---:|
| trace-off，8 次 | `8.378–12.261` | `10.364` | `91,127,960` | `19,333` | `22,250` | `0 / 0` |
| trace-on，8 次 | `7.707–12.040` | `9.585` | `91,127,960` | `19,333` | `22,250` | `0 / 0` |

DGAI 的中位 wall-time 有符号差异为 `-7.51%`，绝对扰动为 `7.51%`，未通过 `5%` 门槛。负值不解释为 instrumentation 加速，而是说明当前测量仍受调度、缓存或 tracer 引起的执行行为改变影响。16 个 run 的写入数量完全一致，phase 结构均为 19,329 次 insert/neighbor-repair 与 5 次 publish/save。8 个 trace-on run 的 raw trace、accepted profiler、ledger、metadata 和 normalized pages 均精确闭合，active set 全部通过。

### OdinANN

| 模式 | Wall time 范围，秒 | 中位数，秒 | Bytes 区间 | Requests 区间 | Page events 区间 |
|---|---:|---:|---:|---:|---:|
| trace-off，5 次 | `3.795–4.166` | `4.032` | `98,939,928–99,161,112` | `19,738–19,829` | `24,168–24,222` |
| trace-on，5 次 | `3.362–4.320` | `3.949` | `98,890,776–99,197,976` | `19,732–19,837` | `24,156–24,231` |

OdinANN 的中位 wall-time 有符号差异为 `-2.07%`，绝对扰动为 `2.07%`，通过 `5%` 门槛。每个 trace-on run 均与其自身 accepted profiler 精确闭合，且 dropped events、failed requests、timestamp/sequence inversions 和 identity errors 均为 0。所有 run 都具有 load、insert/neighbor-repair 和 publish/save 三类 phase，固定部分分别为 10、可变 insert count 和 11。

OdinANN 即使将 `DynamicIndex` 与 two-hop sampler 随机种子固定，并在每次 insert 后执行 M3 barrier，trace-off 本身仍出现约 `0.2%` 的写数量波动。该变化来自系统内部并发执行，而不是 tracer 才出现的现象。off/on 三个主要计数区间均重叠，bytes、requests 与 page events 的中位数相对差异分别约为 `0.066%`、`0.056%` 和 `0.066%`。因此本报告将它标记为“跨分布观测兼容”，同时保留 `exactly_identical = false`，不把它表述成逐 run 完全相等。

## Initial-live image

DGAI manifest 包含 15 个对象、4,428 个 4 KiB logical pages、18,111,652 B logical bytes 和 18,132,992 B allocated bytes。OdinANN manifest 包含 5 个对象、1,752 个 logical pages、7,168,436 B logical bytes 和 7,176,192 B allocated bytes。

manifest 使用 `run_uuid:object_incarnation` 形成 run-scoped stable object identity，记录 device、inode、ctime、file role、aligned offset、page bytes、initial version 和 initial-live flag。当前正式 manifest 明确写有 `initial_packing = not_encoded`，因此只能证明 initial-live logical set 可恢复，尚不能证明一份正式 trace 已由 manifest 驱动完成真实 initial physical packing。simulator 手工 case 采用稳定输入顺序完成 packing，但正式 manifest 到 replay input 的转换仍是 Z0A 的一个 HOLD 缺口。

## Host-managed ZNS simulator

主 simulator 显式维护 zone size、zone capacity、4 KiB logical block、实际 zone 数量、max-open、max-active 和 host spare zone 数量，并维护 logical-to-physical map、zone write pointer、精确 live set、invalid bytes、open/active state、relocation destination 与 reset state。回收只在下一次 append 无法满足容量与 open/active 限制时机械触发。

实现仅包含 `GreedyValidFraction` 与 `OracleMinCopy`。后者严格限定为当前 eligible victims 中的一步最少 live-copy 选择，不使用未来信息，也不声称是全局 WA oracle。在等容量 FULL-only candidate 语义下，两者应选择相同 victim，这一性质被用作实现 sanity check。

10 个手算 case 全部通过，覆盖全部 new writes、同 page 连续重写、hot 集中、hot/cold 混合、relocation 二次空间压力、多文件同 offset、跨页 write、open/active limit、live-page migration 和 reset reuse。主 simulator 与独立 reference implementation 在每个 event 后的 zone state、mapping、victim、relocation、reset 和字节账均一致。关键可手算结果包括 all-new 的 HostWA `4/4`、hot/cold 的 `4/3`、secondary-pressure 的 `9/5` 和 reset-reuse 的 `6/4`。这里的 HostWA 只计算 host append 与 host relocation，不包含 SSD 固件内部写放大，不能表述为 DeviceWA。

每个 event 后均检查以下 conservation invariants：每个 logical key 至多一个 current live version、reset 前 victim live bytes 为 0、write pointer 单调且不超过 capacity、relocation 不改变 logical version、open/active limits 不被突破，以及 HostWA 等于 `(new logical bytes + relocated live bytes) / new logical bytes`。

## 空间、内存与清理闭合

启动前保守磁盘峰值预算为 17,405,354,966 B，1.5 倍门槛为 26,108,032,449 B，最终复核可用空间为 917,331,468,288 B。保守 RAM 峰值预算为 7,784,628,224 B，1.5 倍门槛为 11,676,942,336 B，最终复核 `MemAvailable` 为 256,877,223,936 B。磁盘与 RAM 均通过。

预算分项包含 base snapshot、mutable clone/shadow、trace binary、initial manifest、normalized events、simulator state、simulator output、temporary compression、failure residue 和 safety margin。所有大文件均位于项目 NVMe，未在系统盘执行正式实验。

`cleanup_z0a.sh` 默认 dry-run，只接受位于固定 Z0A root、设备号为 `259:10`、含 `.z0a-owned` marker、没有 wildcard、symlink 或 nested mount 的显式目录。正常与失败尝试均使用相同 marker。实际重试清理已验证该脚本可以逐目录删除失败 residue，且不能删除 root 或 M0–M3 artifact。

## 门禁矩阵与待审问题

| 门禁 | 本地结果 | 证据摘要 |
|---|---|---|
| 短点规模 | PASS | 两系统均约 19K requests |
| Trace schema | PASS | object、role、phase、update/batch、request-page mapping 齐全 |
| 零丢失与物理账本闭合 | PASS | 13/13 trace-on closure PASS |
| 低扰动 | HOLD | DGAI 绝对扰动 `7.51%` 未过；OdinANN `2.07%` 通过 |
| Trace-on 写结构 | DGAI PASS；OdinANN 待 GPT 解释 | DGAI 精确相等；OdinANN off/on 区间重叠但不逐 run 相等 |
| Active set | PASS | 26/26 精确通过 |
| Initial-live logical set | PASS | 两系统均恢复并带稳定 identity |
| Initial physical packing | HOLD | 正式 manifest 明示 `not_encoded`，尚未连接正式 replay |
| Simulator invariants | PASS | 10/10 手工 case，主实现等于独立 reference |
| 空间与清理 | PASS | 非系统盘、1.5 倍余量、fail-closed cleanup |

建议 GPT 将当前 Z0A 判为 `HOLD`。下一轮若获批，只补三项 closure，不扩大到 Z0B。一是继续降低 DGAI tracer 扰动或定义并执行独立 warmup 后的低噪声 timing control，使绝对中位差异不超过 `5%`。二是对 OdinANN 使用 GPT 接受的非确定性等价规则，或进一步收敛其并发调度。三是把正式 manifest 与 normalized trace 通过独立回读 validator 接入 simulator，显式生成 initial physical packing，并保留 HostWA 与 DeviceWA 的语义边界。无论裁决为何，本轮均在此停止，不自动进入 Z0B。
