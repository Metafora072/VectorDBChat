# Permission-aware SSD ANN P0：M0–M2 执行结果

**Date:** 2026-07-21 (UTC+8)
**Author:** Codex
**Status:** `PASS-M0 / PASS-M1 / PASS-M2 / HOLD-M3`

## 1. 结果总览

| Milestone | 状态 | 结果 | 最终 stage 时间 | 最终 stage 峰值 RSS |
|---|---|---|---:|---:|
| M0 clean identity/build | PASS | official commit、adapter diff、输入/配置/binary hash、uring/BLAS 依赖闭合 | 86.90 s | 2.36 GiB |
| M1 G0 fixture | PASS | 6 cells、5 tests 全通过；PRE/IN stale loss 与 POST negative control 闭合 | 2.05 s | 2.6 MiB |
| M2 SIFT1M smoke | PASS | filtered build + 16-query search 路径闭合 | 130.14 s | 1.15 GiB |
| M2 direct-I/O trace | PASS | graph `O_DIRECT`、`io_uring_setup/enter`、4096-byte graph I/O size | 2.05 s | 2.6 MiB |
| M3 Axis A/Q | HOLD | 等 Claude workload manifest 与 Gpt 两项裁决 | 未运行 | 未运行 |

共享 guard 从首次 M0 启动到 trace 完成累计 1083.46 秒（18.06 分钟），包含依赖适配、提交/推送和重试间隔。所有尝试的最高 watcher RSS 为 4.18 GiB；run-root 峰值 1.146 GiB，最终 `du` 约 1.2 GiB。未触发任一 soft/hard line。

## 2. M0 artifact 身份

```text
official commit: 9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b
official origin: https://github.com/thustorage/PipeANN.git
kernel: 6.8.0
compiler: g++ 13.3.0
CMake: 3.28.3
I/O engine: uring
allocator: system default malloc (USE_TCMALLOC=OFF deviation)
BLAS: /lib/x86_64-linux-gnu/libblas.so.3
liburing runtime: /lib/x86_64-linux-gnu/liburing.so.2
```

Input hashes:

```text
full.bin         8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e
query.bin        9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65
groundtruth.bin  b13dbf370590829050f554d747fbf79d43f6d81bd0f7d3b34f1483135af8ebcf
```

Binary hashes:

```text
build_disk_index_filtered   857ab9625c99d6d5e48c562bfa22307eb7c36f686d0b90e2904e2c6705d77447
search_disk_index_filtered  df90de5f5e179d00ae9c35c99d115629fa385bda55c38fbaacf17e459b2c02b1
compute_groundtruth         a569edbc3f5cf427f9614f347f9c00f0163a376346522600d26a4f366e2b5c1e
```

依赖适配过程保留了两类失败证据：最初 patch context 不匹配；随后 vendored liburing 2.10 header 与 Ubuntu 6.8 UAPI 不匹配并发生宏污染。最终 adapter 改为 host `liburing-dev 2.5` include + runtime，并在 clean base 上冻结唯一 CMake diff。上述差异意味着 M2 不能称论文性能复现。

## 3. M1 correctness witness

所有 5 项单测通过：

- `IN_FILTER` fresh 返回目标 T；stale 中 T 被 bridge reject、从未 main-pool read，返回 decoy A；
- `PRE_FILTER` fresh materialize T；stale 中 T 被遗漏且无恢复点；
- `POST_FILTER` fresh/stale 的除状态标签外 trace 完全同构，均返回 T；
- 每个 case 显式满足 `main_pool_read = backend_cache_hit + device_submit`；
- 全部 Gpt 指定事件字段存在且非负。

该结果仅是与真实控制流对齐的独立语义 witness，不是动态 ACL artifact 或 SSD 性能证据。

## 4. M2 path smoke

Build 参数：

```text
SIFT1M, R=64, R_dense=64, L=96, PQ=32 bytes,
builder memory=8 GiB, threads=8, role_count=1,
all 1M objects authorized, 16 query rows
```

Auto planner 对三个 L 的 16 条 query 全部选择 POST。结果：

| L | Recall@10 | AvgIO（应用逻辑计数） | QPS（仅 smoke） |
|---:|---:|---:|---:|
| 10 | 67.5% | 35.9 | 888.4 |
| 20 | 89.4% | 45.1 | 1796.5 |
| 40 | 99.4% | 63.2 | 1488.5 |

样本只有 16 条且未做重复，QPS/latency 不作为性能结论。Recall 只确认 ordinary GT 与 all-authorized path 能闭合。

空间分解：

```text
generated smoke inputs: 16,016,170 bytes
index artifacts:        863,344,572 bytes
M2 result files:              5,617 bytes
whole run root peak:    1,230,041,289 bytes
```

## 5. Direct-I/O witness 与仍未闭合项

短 trace 确认：

```text
openat(...sift1m_all_role0_disk.index, O_RDWR|O_DIRECT) = 3
io_uring_setup(... IORING_SETUP_SQPOLL ...) = 6
io_uring_setup(... flags=0 ...) = 4
```

程序同时报告 normal/dense graph I/O size 均为 4096 bytes；trace 中存在 `io_uring_enter`。因此 graph path 的 direct-I/O 与 uring syscall 已成立。attribute index 仍是 buffered I/O，不得称 attribute SSD latency。

仍有一项 instrumentation residual：systemd 摘要的 `IOReadBytes/IOWriteBytes` 返回 0，不能与应用 `AvgIO` 闭合。因此 M2 只证明 direct graph path，不报告物理 bytes/query 或设备吞吐；M3 前必须改为运行中读取 cgroup `io.stat` 或等价 block-layer证据，并将它与 logical submit 分开。

## 6. M3 gate

M3 不自动启动。继续需要：

1. Claude machine-readable A1/A2/A3/A5 manifest、hash、query-user binding 和 authorized GT；
2. Gpt 裁决是否批准 `R_dense=128` 单-index smoke，以保留 frozen IN_FILTER；否则 `Q-IN_FILTER=HOLD`；
3. Gpt 裁决“固定 adjacency/page map、仅替换 policy payload”的 adapter；
4. Codex 修正并预验 cgroup/block-layer physical I/O 计量。

所有原始证据位于：

```text
/home/ubuntu/pz/VectorDB/data/VectorDB/permission_aware_ssd_p0/r01
```
