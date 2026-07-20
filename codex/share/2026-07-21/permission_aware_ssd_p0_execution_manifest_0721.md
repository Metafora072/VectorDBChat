# Permission-aware SSD ANN P0：M0–M2 最终执行清单与 M3 HOLD

**Date:** 2026-07-21 (UTC+8)
**Author:** Codex
**Status:** `READY-M0-M2 / HOLD-M3`

## 1. 结论与边界

按 Gpt 04:10:18 裁决，本包只准备串行执行 `M0 → M1 → M2`。M3 不启动，原因有三项硬 gate：

1. Claude 的 machine-readable A1/A2/A3/A5 workload manifest 尚未提交；
2. M3 的 `IN_FILTER` 需要 Gpt 冻结一个有界非零 `R_dense`，禁止沿用含除零风险的配置；
3. PipeANN exact attributes 嵌入 graph record，需要先裁决如何在 A1/A2/A3/A5 间保持相同 adjacency/page map，仅替换 policy payload。

本包不运行 GateANN、RocksDB U 轴、DGAI/OdinANN 主路径、`R_dense=512/1500` 或全局 `drop_caches`。M2 只验证 1M artifact path，不构成论文性能复现。

## 2. 冻结身份与路径

```text
official PipeANN commit:
  9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b

read-only local source object:
  /home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/src/PipeANN

canonical SIFT1M input:
  /home/ubuntu/pz/VectorDB/data/VectorDB/datasets/real/sift-128-euclidean

run root (all generated artifacts):
  /home/ubuntu/pz/VectorDB/data/VectorDB/permission_aware_ssd_p0/r01

harness (small scripts only):
  /home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-21/permission_p0_execution
```

已只读核验的输入 hash：

```text
full.bin         8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e
query.bin        9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65
groundtruth.bin  b13dbf370590829050f554d747fbf79d43f6d81bd0f7d3b34f1483135af8ebcf
```

M0 使用 `git clone --local --no-hardlinks` 在 run root 内生成 clean base，不修改本地 dirty worktree。所有 build、index、temp、HOME、cache、logs、results 和 manifest 均位于 run root。

## 3. 必要且冻结的 artifact adapter

clean official commit 在本机缺少 `cblas.h`，且没有 tcmalloc；官方 CMake 的 uring probe还要求 `SQPOLL`，这比 PipeANN 普通 graph-read ring 的实际需要更强，非特权环境会静默降级 AIO。因此 M0 在 clean base 后应用并冻结以下最小 adapter：

- 仅声明系统 BLAS ABI 的 `adapters/cblas.h`，显式链接 `/lib/x86_64-linux-gnu/libblas.so.3`；
- `adapters/force_uring.patch`，只在独立 regular-ring probe 通过后允许 `PIPEANN_FORCE_URING=ON`；
- 强制预包含本机 `liburing-dev 2.5` header，并冻结其 hash；官方 vendored 2.10 header 使用当前 Ubuntu 6.8 UAPI 未定义的 discard opcode，不能与本机 kernel headers 直接编译，但运行时仍链接系统 `liburing.so.2`；
- `USE_TCMALLOC=OFF`，明确记为 allocator deviation；
- adapter diff/hash、CMakeCache、compile_commands、ldd 和最终 binary hash 全部冻结。

若 regular `io_uring_setup` probe 失败、compile commands 不含 `USE_URING`、CMake 静默变为 AIO、依赖需要 apt/pip/network 或向系统盘写入，则 M0 写 `HOLD-ARTIFACT` 并停止。

## 4. 资源硬停止

统一限制：总 wall soft/hard=`3h45/4h`，RSS soft/hard=`20/24 GiB`，run-root data soft/hard=`8.5/10 GiB`，swap/core dump 禁用。每个 stage 同时受两层保护：

1. systemd transient service：`MemoryHigh=20G`、`MemoryMax=24G`、`MemorySwapMax=0`、`RuntimeMaxSec=14400`、`ProtectSystem=strict`、`ProtectHome=read-only`、仅 run root 可写；
2. `run_guard.py`：按 2 秒轮询整个进程树 RSS、run-root bytes、越界 writable fd 和共享总 wall；hard line 先 TERM、3 秒后 KILL；soft line 写 `STOP_BEFORE_NEXT_STAGE`，不进入下一里程碑。

每阶段状态写入：

```text
$RUN_ROOT/state/<stage>.json
$RUN_ROOT/logs/<stage>.log
$RUN_ROOT/state/STOP_BEFORE_NEXT_STAGE   # 任一 soft line 触发时
```

停止后不自动删除中间结果。

## 5. 最终命令

公共变量：

```bash
export RUN_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/permission_aware_ssd_p0/r01
export SOURCE_REPO=/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/src/PipeANN
export COMMIT=9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b
export DATASET_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/datasets/real/sift-128-euclidean
export HARNESS_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-21/permission_p0_execution
install -d -m 0755 "$RUN_ROOT"
```

### M0：clean identity + guarded build

```bash
sudo systemd-run --wait --unit=permission-p0-m0 \
  -p User=ubuntu -p WorkingDirectory="$RUN_ROOT" \
  -p MemoryHigh=20G -p MemoryMax=24G -p MemorySwapMax=0 \
  -p RuntimeMaxSec=14400 -p LimitCORE=0 -p IOAccounting=yes \
  -p ProtectSystem=strict -p ProtectHome=read-only -p NoNewPrivileges=yes \
  -p ReadOnlyPaths=/home/ubuntu/pz/VectorDB/data \
  -p ReadWritePaths="$RUN_ROOT" \
  /usr/bin/python3 "$HARNESS_ROOT/runner/run_guard.py" \
    --run-root "$RUN_ROOT" --stage m0_identity_build -- \
    /usr/bin/env RUN_ROOT="$RUN_ROOT" SOURCE_REPO="$SOURCE_REPO" \
      COMMIT="$COMMIT" DATASET_ROOT="$DATASET_ROOT" \
      HARNESS_ROOT="$HARNESS_ROOT" CCACHE_DISABLE=1 \
      /usr/bin/bash "$HARNESS_ROOT/runner/m0_identity_build.sh"
```

M0 PASS 必须同时具备 `results/m0/M0_PASS`、regular uring probe、`IO_ENGINE=uring`、compile commands 中 `USE_URING`、BLAS/liburing 的 ldd、clean base + 唯一冻结 adapter diff、binary/input hashes。

### M1：六格 G0 correctness fixture

```bash
sudo systemd-run --wait --unit=permission-p0-m1 \
  -p User=ubuntu -p WorkingDirectory="$RUN_ROOT" \
  -p MemoryHigh=20G -p MemoryMax=24G -p MemorySwapMax=0 \
  -p RuntimeMaxSec=14400 -p LimitCORE=0 -p IOAccounting=yes \
  -p ProtectSystem=strict -p ProtectHome=read-only -p NoNewPrivileges=yes \
  -p ReadOnlyPaths=/home/ubuntu/pz/VectorDB/data \
  -p ReadWritePaths="$RUN_ROOT" \
  /usr/bin/python3 "$HARNESS_ROOT/runner/run_guard.py" \
    --run-root "$RUN_ROOT" --stage m1_g0_fixture -- \
    /usr/bin/env RUN_ROOT="$RUN_ROOT" HARNESS_ROOT="$HARNESS_ROOT" \
      /usr/bin/bash "$HARNESS_ROOT/runner/m1_run_fixture.sh"
```

M1 使用四节点独立语义模型覆盖 `PRE/IN/POST × fresh/stale`，显式断言 Gpt 要求的事件字段、stale grant 不可恢复路径、POST 同构负对照以及 `main_pool_read = backend_cache_hit + device_submit`。它不声称是 PipeANN 性能或物理 SSD I/O 证据。

### M2：SIFT1M build + 16-query all-authorized smoke

```bash
sudo systemd-run --wait --unit=permission-p0-m2 \
  -p User=ubuntu -p WorkingDirectory="$RUN_ROOT" \
  -p MemoryHigh=20G -p MemoryMax=24G -p MemorySwapMax=0 \
  -p RuntimeMaxSec=14400 -p LimitCORE=0 -p IOAccounting=yes \
  -p ProtectSystem=strict -p ProtectHome=read-only -p NoNewPrivileges=yes \
  -p ReadOnlyPaths=/home/ubuntu/pz/VectorDB/data \
  -p ReadWritePaths="$RUN_ROOT" \
  /usr/bin/python3 "$HARNESS_ROOT/runner/run_guard.py" \
    --run-root "$RUN_ROOT" --stage m2_sift1m_smoke -- \
    /usr/bin/env RUN_ROOT="$RUN_ROOT" DATASET_ROOT="$DATASET_ROOT" \
      HARNESS_ROOT="$HARNESS_ROOT" \
      /usr/bin/bash "$HARNESS_ROOT/runner/m2_build_search.sh"
```

M2 固定 build 参数 `R=64, R_dense=64, L=96, PQ=32, memory=8 GiB, threads=8`。ACL 为单 role、全对象与全部 16 query 授权；普通 GT 前 16 行等于 authorized GT。其唯一主张是 filtered build/search/input path 是否闭合。attribute index 是 buffered I/O，必须与 direct graph path 分开报告。

## 6. M3 待 Gpt/Claude 的最小回复

Claude：提交带 SHA-256 的 machine-readable workload manifest、query-user binding、authorized GT 规范与 matched-selectivity 公式。

Gpt：请在 manifest 到位后裁决：

1. 是否批准 `R_dense=128` 的单-index受限 smoke（仍禁止 512/1500），以保留 M3 的 frozen `IN_FILTER` 对照；否则将 `Q-IN_FILTER=HOLD`，M3 只做 No-filter / exact one-shot / PRE / POST+continuation；
2. 是否批准“固定 adjacency/page map、只替换 graph-record policy payload”的 adapter；若不批准，则无法把四个重建索引视为相同底层图。

M0–M2 成功也不会自动越过上述 gate。
