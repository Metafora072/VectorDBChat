# Dynamic Vamana W1 CP05 cumulative R03 replay canary permission stop

## 结论

R03 于 `2026-07-17 01:29:44 UTC+8` 激活，并于 `01:30:10 UTC+8` 在 `replay_DGAI` 以 `exit=1` fail closed。停止发生在 DGAI replay CP00 query gate 通过之后、任何 16-record update API 调用之前。直接原因不是 query I/O primer 或 evidence validator，而是 CP01 inaccessible-input canary 以 `ubuntu` 运行，却试图在 owner 为 controller、mode 0755 的 attempt 根目录创建 JSON，因 `EACCES` 未产生门禁文件。

R03 identity 已 terminal，不允许续写、重试或复用 `sequential-cp80-03`。OdinANN replay、SIFT10M DGAI/OdinANN formal、DiskANN CP05 均未启动；CP10/CP20 继续 HOLD。

## 已通过证据

- R03 preflight、R01/R02 terminal audit、R02→R03 inputs byte identity 与 inode disjointness均通过。
- immutable replay bases 与 frozen static-smoke 全量只读重算通过。
- shared query launcher 的 DGAI L64、OdinANN L29 正向 fixture 通过；无-primer 负向 fixture 被严格 parser拒绝。
- DGAI replay CP00 `L64/L128 × 3` 六点 query gate 为 PASS：每点 baseline 均为 `4,096 B / 1 I/O`，query read delta 为 `29,188,096–39,292,928 B` 和 `7,126–9,593 I/O`，primer 明确排除在 final-minus-baseline 之外。
- 六次查询均 exit 0、`36×10` 结果完整且全部 active、无 OOM；Recall 诊断值为 L64 `0.9833` 左右、L128 `0.9917`。
- stop-time preservation schema 为 `dynamic-vamana-w1-cp05-cumulative-r03-preservation-v1`，`status=pass`、`checked_count=85`、0 mismatch；immutable bases、formal bases 与 DiskANN lineage 均保持不变。

## 失败位置与根因

失败单元为：

```text
dv-w1-cum-r03-replay-dgai-cp01-input-canary.service
```

服务以 `ubuntu` 身份执行，日志中的唯一错误为：

```text
PermissionError: [Errno 13] Permission denied:
.../replay/DGAI/sequential-cp80-03/cp01_inaccessible_canary.json
```

共享 runner 已将 `queries/`、`stages/`、`checkpoints/` 创建为 `ubuntu:ubuntu`，但 canary output 被派生到 attempt 根目录。该根目录由 controller/clone orchestration 创建，停止时为 controller owner、mode 0755，`ubuntu` 不能在其中新建文件。因此 systemd canary 正确返回 exit 1，runner随后因 marker 缺失停止。没有 `STAGE_WORKER_OK`、`stage_evidence.json`、CP01/CP05 checkpoint evidence 或 completion marker，证明 update worker 尚未进入。

## 建议恢复边界

新的 recovery identity 应把 canary JSON 与 log 固定放入已授权的 `stages/<checkpoint>/` 目录，或在启动 canary 前显式创建一个 exact `ubuntu:ubuntu`、0700 的 canary evidence 子目录；不能放宽 inaccessible-path 检查，也不能把 canary 失败当作可忽略事件。启动前需要新增真实 uid=ubuntu 的正向 fixture，证明：allowed delta 可读、全部 denied inputs 返回 EACCES/EPERM、evidence 能原子落盘、canary scope 已回收、且没有调用 update API。R03 clone 与 inputs 是否只读复用、还是重新派生为 R04，应由 Gpt 裁决。

## 时间与空间

- 正式激活到停止：约 `25.97 s`。
- R03 result allocated：`7,458,816 B`。
- DGAI replay clone allocated：`1,415,319,552 B`。
- R03 formal deltas allocated：`15,630,336 B`。
- 停止后项目 NVMe `259:10` 可用：`1,322,250,809,344 B`。
- 停止后 MemAvailable：约 `258.1 GB`。

全部大文件仍位于项目 NVMe；系统盘未承载实验数据。
