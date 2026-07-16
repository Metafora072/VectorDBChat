# Dynamic Vamana W1：CP05 R03 Query-I/O Baseline 恢复门禁

**日期**：2026-07-17

**上游证据**：

* `codex/share/2026-07-17/dynamic_vamana_w1_cp05_r02_replay_query_io_baseline_stop_analysis_0717.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_cp05_replay_base_mode_stop_analysis_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_trajectory_preparation_results_0716.md`

**裁决**：

* R02 fail-closed stop：**有效**
* 接受 immutable replay-base lineage 与 frozen static-smoke evidence
* 授权修复共享 query-scope I/O baseline
* 授权使用全新 R03 identity 重新执行 `16→80 replay`
* replay 通过后，可自动执行正式 `CP00→CP01→CP05`
* CP10、CP20 继续 HOLD

---

# 1. R02 证据边界

终止 run：

```text
pilot3_sift10m_w1_cp05_trajectory_r02
```

停止阶段：

```text
replay_DGAI
```

停止时：

* DGAI replay mutable clone 已创建；
* CP00 的 L64/L128 各执行三次；
  -六次查询均 exit 0；
  -六份 `36×10` result IDs 完整；
  -无 sentinel；
  -所有 IDs 属于 CP00 active set；
  -无 OOM、OOM-kill、fatal 或查询错误；
  -尚未调用任何 16-record update API。

不存在：

* replay CP01 checkpoint；
  -replay CP05 checkpoint；
  -OdinANN replay clone；
  -SIFT10M DGAI/OdinANN clone；
  -SIFT10M update；
  -DiskANN CP05 stale control。

R02 永久保持 terminal，不续写、不重试、不复用其 run 或 attempt identity。

---

# 2. 根因裁决

R02 的 static-smoke 路径已经具备：

```text
same systemd scope
→ 4 KiB O_DIRECT primer
→ resource_probe baseline
→ query
```

因此 static smoke 的首个 resource sample 已有目标设备：

```text
259:10
```

但共享 cumulative runner 的：

```text
query_checkpoint()
```

仍直接启动：

```text
resource_probe
→ query
```

新建 cgroup 的 `io.stat` 只有在第一次目标设备 I/O 后才出现设备行。因此：

-查询确实读取了 NVMe；
-后续 samples 出现 `259:10`；
-首个 baseline sample 中没有该行；
-validator 无法从严格零点计算增量；
-query evidence 被正确拒绝。

这属于 query-scope 编排分叉，不属于索引、查询、设备或数据错误。

---

# 3. 不放宽 Evidence Validator

不得把 validator 改为：

```text
首个包含目标设备的 sample
→ 最后一个 sample
```

也不得把缺失设备行隐式解释为零。

原因是这会丢失严格的时间边界，无法证明被忽略的早期 samples 中没有目标设备 I/O。

保留现有硬门禁：

1. `samples[0]` 中恰有一个目标设备行；
   2.最后一个 sample 中恰有一个目标设备行；
2. final read bytes 大于 baseline read bytes；
3. final read I/O count 大于 baseline read I/O count；
4. query delta 只由 final-baseline 计算。

修复只能发生在 scope 启动顺序中。

---

# 4. 唯一 Query-Scope Launcher

新增：

```text
w1_run_query_scope.sh
```

以下三种路径必须共同调用它：

* immutable replay-base static smoke；
* sequential replay CP00/CP01/CP05 query；
* SIFT10M formal CP00/CP01/CP05 query。

禁止 static smoke 和 cumulative runner 各自维护一份 primer 编排。

固定顺序：

```text
validate exact query capability
→ validate index root and prime file
→ execute 4 KiB O_DIRECT primer
→ write primer report
→ exec resource_probe
→ exec query worker
```

`resource_probe` 必须在 primer 完成后才启动。

---

# 5. Primer Target 约束

Primer 文件固定为当前查询 index root 下的：

```text
index_disk.index
```

不得接收任意文件路径。

要求：

* canonical realpath 位于当前 exact index root 内；
  -文件名精确为 `index_disk.index`；
  -regular file；
  -不是 symlink；
* hard-link count 为 1；
  -位于项目 NVMe `259:10`；
  -大小至少为 4096 bytes；
  -当前 scope 用户拥有读取权限。

Primer 需要同时支持两类合法索引：

## 5.1 Immutable replay base

```text
owner = root:root
mode  = 0444
```

## 5.2 Mutable private clone

```text
owner = ubuntu:ubuntu
mode  = 0600
```

不得沿用 static-smoke helper 中“文件必须为 0444”的单一假设，否则 formal/replay 的 mutable clone 会再次被错误拒绝。

只允许 mode：

```text
0444
0600
```

其他 mode fail closed。

---

# 6. Primer 实现

执行：

```text
4 KiB O_DIRECT read
```

只读，不写文件。

Primer 前后记录：

```text
realpath
device major:minor
inode
size
uid
gid
mode
link count
mtime_ns
bytes requested
return code
```

要求上述文件身份在 primer 前后完全一致。

`atime` 不作为不变条件，因为读取可能受文件系统 relatime/noatime 策略影响。

输出：

```text
<query-stem>.io_primer.json
```

至少包含：

```text
schema = dynamic-vamana-w1-query-io-primer-v1
status = pass
bytes_read = 4096
direct_io = true
resource_probe_started_after_primer = true
```

Primer 失败时，不启动 resource probe 或 query。

---

# 7. Resource Evidence 语义

Primer 会使 query scope 的 target-device counter 在 probe 启动前非零。

因此 resource JSON 中：

```text
baseline target read bytes >= 4096
baseline target read I/Os >= 1
```

正式 query I/O 仍定义为：

```text
query_read_bytes =
final_read_bytes - baseline_read_bytes
```

```text
query_read_ios =
final_read_ios - baseline_read_ios
```

Primer 的 4096 bytes 不计入：

* mean query I/O；
  -query device bytes；
  -query bytes/request；
  -update I/O；
  -end-to-end update accounting。

报告中将 primer 标记为：

```text
accounting infrastructure
```

不得将其算作查询工作量。

---

# 8. Query-Scope 集成回归

R03 正式 manifest 激活前，使用新的共享 launcher 执行集成回归。

## 8.1 DGAI 正向回归

使用：

```text
immutable DGAI replay base
canonical-v6 DGAI query binary
query_36.bin
gt_cp00_36
L = 64
Tq = 1
```

要求：

* primer report pass；
* `samples[0]` 恰有一个 `259:10` 行；
  -final sample 恰有一个 `259:10` 行；
  -baseline read bytes 至少 4096；
  -query read-byte delta > 0；
  -query read-I/O delta > 0；
  -result shape `36×10`；
  -所有 IDs active；
  -无 OOM/fatal；
  -base content/mode 不变。

## 8.2 OdinANN 正向回归

使用相同 launcher：

```text
immutable OdinANN replay base
canonical-v6 OdinANN-uring query binary
L = 29
```

要求与 DGAI 相同，并重新确认：

```text
io_engine = uring
```

## 8.3 缺失 Primer 负向回归

在独立 scratch scope 中：

-不执行 primer；
-让 resource probe 在任何目标设备 I/O 前采集至少两个 samples；
-确认 `samples[0]` 没有 `259:10` 行；
-确认严格 evidence parser拒绝该证据。

负向测试不能修改生产 validator。

## 8.4 Primer 计量边界回归

验证：

```text
final - baseline
```

不包含 primer 4096 bytes。

保存：

```text
results/pilot3_sift10m_w1_cp05_trajectory_r03/preflight/
query_scope_primer_tests.json
```

---

# 9. 可复用工件

## 9.1 Immutable replay bases

允许复用：

```text
formal/pilot3_w1_cp05_replay_bases_v1/
```

但 R03 preflight 必须重新只读验证：

* accepted r07 lineage；
  -content manifest；
  -mode manifest；
  -root:root；
  -directory 0555；
  -file 0444；
  -write/create/rename/unlink denial；
  -source content/mode preservation。

不得重新复制或修改 replay bases。

## 9.2 Static smoke

允许复用 frozen static-smoke evidence：

```text
SHA256 =
5c9f2189a5c37c29d052c3593bc5cdd4f635b050cb6bbbf60a857b49b7be09c3
```

它继续证明：

-两个 immutable bases 可加载；
-DGAI AIO identity；
-OdinANN io_uring identity；
-四个静态 query point 完整；
-真实 NVMe read；
-无 OOM。

R03 必须只读重算其全部文件 identity。

新的 query-scope integration fixture用于验证共享 launcher，不能用旧 static smoke替代。

---

# 10. R03 Fresh Identity

正式 run：

```text
pilot3_sift10m_w1_cp05_trajectory_r03
```

Replay run：

```text
pilot3_w1_cp05_trajectory_replay_r03
```

Attempts：

```text
DGAI replay:
sequential-cp80-03

OdinANN replay:
sequential-cp80-03

DGAI formal:
trajectory-cp05-03

OdinANN formal:
trajectory-cp05-03

DiskANN:
stale-cp05-03
```

结果根：

```text
results/pilot3_sift10m_w1_cp05_trajectory_r03/
```

Formal 根：

```text
formal/pilot3_sift10m_w1_cp05_trajectory_r03/
```

不得创建或续写任何 `*-02` attempt。

---

# 11. R03 Inputs

R02 inputs 保留为终止证据。

R03 重新派生：

```text
datasets/sift10m/w1_trajectory/execution_deltas_r03/
```

以及：

```text
results/pilot3_sift10m_w1_cp05_trajectory_r03/replay/inputs/
```

要求：

* R03 formal deltas 与 R02 deltas byte-identical；
  -R03 replay inputs 与 R02 replay inputs byte-identical；
  -inode 完全独立；
  -只读；
  -无 symlink/hardlink；
  -80K delta 等于 master `[0:80K]`；
  -320K delta 等于 master `[80K:400K]`；
  -两段连接等于 CP05 prefix。

重新派生只用于 attempt 隔离，不改变 trace、seed 或 GT。

---

# 12. R03 Preflight

在同一 global flock 内验证：

-首次 attempt 停于 replay-base mode；
-R02 停于 replay DGAI CP00 query gate；
-R02 没有调用任何 update API；
-R02 没有 CP01/CP05 replay evidence；
-R02 没有 OdinANN replay/formal/DiskANN attempt；
-R02 preservation 为 pass；
-immutable replay bases 完整；
-frozen static smoke 完整；
-query-scope primer integration tests通过；
-R03 inputs 与 R02 byte-identical且 inode-disjoint；
-canonical binaries 未改变；
-DGAI io_engine 为 `aio`；
-OdinANN io_engine 为 `uring`；
-trajectory、CP00/CP01/CP05 GT 未改变；
-SIFT10M formal bases 未改变；
-DiskANN runtime lineage 未改变；
-无 active W1 process/scope；
-R03 targets 全部不存在；
-free-space 门禁通过。

---

# 13. R03 Replay

执行：

```text
DGAI 16→80
→ OdinANN 16→80
```

每个系统：

```text
clone immutable CP00 replay base once
→ CP00 query
→ worker 1 applies 16 replacements
→ publish/reload
→ CP16 query and correctness
→ worker 2 reloads persisted CP16
→ applies only 64 replacements
→ publish/reload
→ CP80 query and correctness
→ freeze final replay clone
```

所有 CP00、CP16、CP80 query scopes必须使用新的共享 primer launcher。

Replay 任一系统失败，不启动 SIFT10M。

---

# 14. 正式 CP05 累计执行

Replay 全部通过后，自动执行：

```text
DGAI CP00→CP01→CP05
→ OdinANN CP00→CP01→CP05
→ DiskANN CP05 stale control
```

动态系统继续满足：

-一个 private clone；
-两个独立 update workers；
-第一阶段只应用 80K；
-第二阶段只应用 320K；
-CP01 persisted reload；
-stage-local 与 checkpoint-global probes；
-active-set exact；
-固定 L/Tq/repeats；
-Recall 只观测；
-每次 query使用共享 primer launcher；
-CP05 clone最终冻结为 0555/0444。

---

# 15. Query Evidence 新增字段

每个 query point额外记录：

```text
primer_report_sha256
baseline_target_read_bytes
baseline_target_read_ios
final_target_read_bytes
final_target_read_ios
query_target_read_bytes_delta
query_target_read_ios_delta
primer_excluded_from_delta = true
```

最终 summary 只能使用 query delta。

---

# 16. 失败规则

R03 任一阶段失败：

-立即停止；
-保留全部证据；
-不自动重试；
-不复用 R03 identity；
-不放宽 validator；
-不删除 primer report；
-不启动后续系统；
-不进入 CP10/CP20。

---

# 17. 输出

成功报告：

```text
codex/share/2026-07-17/
dynamic_vamana_w1_cp05_cumulative_trajectory_r03_results_0717.md
```

失败报告：

```text
codex/share/2026-07-17/
dynamic_vamana_w1_cp05_cumulative_r03_stop_analysis_0717.md
```

---

# 18. 最终裁决

R02 查询结果正确，但缺少严格的 cgroup I/O baseline，不能作为通过的 replay checkpoint。

授权将 4 KiB O_DIRECT primer 下沉到唯一共享 query-scope launcher，并保持 validator 完全不变。

在全新 R03 identity 下重新执行：

```text
query-scope integration fixture
→ DGAI/OdinANN 16→80 replay
→ DGAI/OdinANN CP00→CP01→CP05
→ DiskANN CP05 stale control
```

CP10 与 CP20 继续 HOLD。
