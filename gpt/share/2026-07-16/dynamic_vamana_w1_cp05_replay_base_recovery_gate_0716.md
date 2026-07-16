# Dynamic Vamana W1：CP05 Replay Base 恢复与 R02 累计执行门禁

**日期**：2026-07-16

**上游证据**：

* `codex/share/2026-07-16/dynamic_vamana_w1_cp05_replay_base_mode_stop_analysis_0716.md`
* `codex/share/2026-07-15/dynamic_vamana_w1_formal_execution_preflight_0715.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_trajectory_preparation_results_0716.md`

**裁决**：

* 首次 CP05 cumulative attempt 的 fail-closed stop：**有效**
* 授权创建专用 immutable SIFT1M replay bases
* 授权使用全新 R02 identity 重新执行 sequential replay
* replay 全部通过后，可自动执行正式 `CP00→CP01→CP05`
* CP10、CP20 继续 HOLD

---

# 1. 首次 Attempt 的证据边界

终止 run：

```text
pilot3_sift10m_w1_cp05_trajectory
```

停止阶段：

```text
replay_DGAI
```

停止发生在：

```text
clone helper 检查 replay base mode
```

之前已经完成：

* trajectory/formal input preflight；
  -正式 80K 与 320K delta 派生；
  -replay 16 与 64 delta 派生；
  -replay GT 与 probes 派生；
  -所有 delta/input 冻结；
  -stop-time preservation。

没有发生：

* replay private clone 发布；
  -replay CP00 query；
  -replay update；
  -SIFT10M private clone；
  -SIFT10M query/update；
  -DiskANN CP05 stale control。

该 run 永久保持 `stopped_failed`，不得续写或复用。

---

# 2. 根因裁决

现有 SIFT1M replay sources：

```text
index/atlas1m/DGAI/sift1m
index/atlas1m/OdinANN/sift1m
```

属于历史共享可写工件，其 mode 包含：

```text
directory 0775
regular files 0664/0644
```

新的 clone helper 要求 base 满足 immutable policy，因而在复制前拒绝。

这属于 replay-base 生命周期不匹配：

```text
历史可写 index
→ 被当作 immutable base 使用
```

不是：

* DGAI/OdinANN 算法失败；
  -trace 或 GT 失败；
  -memory/NVMe 失败；
  -cumulative runner 状态机失败。

---

# 3. 禁止原地 chmod

不得修改：

```text
index/atlas1m/DGAI/sift1m
index/atlas1m/OdinANN/sift1m
```

包括：

-不得执行递归 chmod；
-不得更改 ownership；
-不得删除或替换 `BUILD_OK`；
-不得在原目录写入新 manifest；
-不得把原目录重新命名为 immutable base。

这些路径是共享历史工件。原地冻结会改变过去实验环境，并可能影响其他脚本。

---

# 4. Source Content Lineage

创建副本前，必须证明当前可写 source 仍等于此前接受的 r07 replay base。

接受的 lineage 来自：

```text
pilot3_w1_formal_path_replay_r07
```

对 DGAI 和 OdinANN 分别定位其已保存的：

```text
base_content_before.tsv
base_content_after*.tsv
clone_manifest.json
```

要求：

1. r07 attempt 存在成功 marker；
2. r07 base-before/base-after content manifest 完全一致；
   3.当前 source 重新生成的 content manifest 与 r07 `base_content_before.tsv` 逐字节一致；
3. source 路径精确为两个冻结 `atlas1m` 路径；
4. source 不包含 symlink、FIFO、socket 或 device；
   6.所有 regular file 的 hard-link count 为 1；
   7.复制前不存在指向 source subtree 的 `O_WRONLY/O_RDWR` 打开文件描述符；
5. source content manifest 在复制前后不变；
   9.source mode manifest 在复制前后不变。

如果 r07 lineage evidence 缺失或 manifest 不一致，立即停止。

不得将“当前 source 自身的首次 manifest”当作历史 identity 的替代品。

---

# 5. 专用 Immutable Replay Bases

新建：

```text
formal/pilot3_w1_cp05_replay_bases_v1/
├── DGAI/cp00/index/
└── OdinANN/cp00/index/
```

这些目录属于可复用的只读 replay infrastructure，不属于某次动态 attempt。

## 5.1 创建顺序

每个系统执行：

```text
verify r07 lineage
→ source content/mode before
→ create .partial.<pid>
→ copy source content
→ verify source/copy content equality
→ verify inode independence
→ normalize immutable ownership/mode
→ owner write-denial audit
→ source content/mode after
→ atomic publish
```

## 5.2 文件约束

只允许：

* regular file；
  -directory。

不允许：

* symlink；
  -hard link；
  -FIFO；
  -socket；
  -device；
  -subtree escape。

## 5.3 Immutable policy

最终 policy：

```text
owner = root:root
directories = 0555
regular files = 0444
```

以 `ubuntu` 身份验证：

-所有 regular file `O_RDWR|O_NOFOLLOW` 均失败；
-所有 directory create/rename/unlink 均失败。

## 5.4 Content identity

以下三个 content manifest 必须逐字节一致：

```text
accepted r07 base content
current writable source content
new immutable replay-base content
```

权限转换前后 replay-base content SHA256 不得改变。

---

# 6. Replay Base Manifest

每个系统生成：

```text
immutable_replay_base_manifest.json
base_content.tsv
base_mode.tsv
source_content_before.tsv
source_content_after.tsv
source_mode_before.tsv
source_mode_after.tsv
write_denial_audit.json
IMMUTABLE_REPLAY_BASE_OK
```

manifest 至少记录：

```text
schema
system
accepted_r07_run
accepted_r07_attempt
accepted_r07_manifest_realpath
accepted_r07_manifest_sha256
source_realpath
immutable_base_realpath
content_manifest_sha256
mode_manifest_sha256
owner_uid/gid
directory_mode
file_mode
apparent_bytes
allocated_bytes
copy wall time
copy NVMe I/O
write-denial counts
```

若 final path 已存在，只允许做只读 identity verification；不得覆盖或重新创建。

---

# 7. Static Load Smoke

Immutable base 发布后，使用 cumulative replay 的冻结：

```text
query_36.bin
gt_cp00_36
active_cp00.tags.bin
```

和 canonical-v6 binaries 执行只读 load/query smoke。

## DGAI

```text
L = 64, 128
```

## OdinANN

```text
L = 29, 46
IO engine = io_uring
```

每个 L 执行一次，要求：

* exit code 0；
  -result shape `36×10`；
  -所有 IDs 属于 CP00 active set；
  -无 sentinel；
  -每行无重复；
  -metrics finite；
  -Recall 位于 `[0,1]`；
  -NVMe read bytes 大于 0；
  -无 OOM、fatal 或 I/O error；
  -查询前后 immutable-base content/mode 不变。

Recall 仅作观测，不设置经验区间。

---

# 8. 全新 R02 Identity

旧 run 不可复用。

新正式 run：

```text
pilot3_sift10m_w1_cp05_trajectory_r02
```

新 replay run：

```text
pilot3_w1_cp05_trajectory_replay_r02
```

Attempts：

```text
DGAI replay:
sequential-cp80-02

OdinANN replay:
sequential-cp80-02

DGAI formal:
trajectory-cp05-02

OdinANN formal:
trajectory-cp05-02

DiskANN:
stale-cp05-02
```

结果根：

```text
results/pilot3_sift10m_w1_cp05_trajectory_r02/
```

formal 根：

```text
formal/pilot3_sift10m_w1_cp05_trajectory_r02/
```

不得创建或续写旧 `*-01` attempt。

---

# 9. R02 Execution Deltas

首次失败 run 中派生的 deltas 保留为终止证据，不修改、不删除。

新建：

```text
datasets/sift10m/w1_trajectory/execution_deltas_r02/
```

重新从冻结 master trace 派生：

```text
cp00_to_cp01 = master[0:80K]
cp01_to_cp05 = master[80K:400K]
```

要求：

-新 80K delta 与历史 CP01 语义逐条一致；
-新 320K delta 与 master 对应 slice 逐条一致；
-两个新 delta 与首次 attempt 对应 delta byte-identical；
-两段连接后等于 CP05 400K prefix；
-新旧文件 inode 不共享；
-所有文件只读；
-输入 master、CP01 和 CP05 artifacts 未改变。

Replay inputs 同样在新 R02 result tree 中重新派生，并与首次 attempt 的逻辑内容一致。

---

# 10. Runner Identity 更新

共享 cumulative runner 的状态机和统计口径不变，只更新被允许的 run/attempt identity。

禁止添加宽泛规则：

```text
pilot3_*_cp05_trajectory*
```

只允许精确：

```text
pilot3_w1_cp05_trajectory_replay_r02
sequential-cp80-02

pilot3_sift10m_w1_cp05_trajectory_r02
trajectory-cp05-02
```

Replay base 必须精确解析为新 immutable paths，不能再指向 `index/atlas1m/...`。

---

# 11. R02 Preflight

在同一 global flock 内验证：

-旧 attempt 为 `stopped_failed`；
-旧停止阶段为 `replay_DGAI`；
-旧 attempt 中没有 replay/formal clone 或 checkpoint evidence；
-旧 formal/replay deltas preservation 通过；
-两个 immutable replay bases 的 lineage/content/mode/write-denial 全部通过；
-static load smoke 通过；
-R02 deltas 与 master slices 精确；
-trajectory preparation artifacts 未改变；
-CP00/CP01/CP05 GT 未改变；
-canonical-v6 binaries 未改变；
-OdinANN 仍为 io_uring；
-SIFT10M formal CP00 bases 未改变；
-DiskANN runtime lineage 未改变；
-无 active W1 scope/process；
-free space 足够；
-所有 R02 target 不存在。

---

# 12. R02 执行顺序

唯一顺序：

```text
acquire global flock
→ validate terminal attempt
→ validate/create immutable replay bases
→ static load smoke
→ derive/freeze R02 execution deltas
→ DGAI 16→80 sequential replay
→ OdinANN 16→80 sequential replay
→ DGAI CP00→CP01→CP05
→ freeze DGAI CP05
→ OdinANN CP00→CP01→CP05
→ freeze OdinANN CP05
→ DiskANN CP05 stale control
→ preservation audit
→ final report
→ stop
```

Replay 任一系统失败时，不得启动 SIFT10M formal execution。

---

# 13. 正式累计语义保持不变

正式系统仍须：

```text
clone CP00 exactly once
→ apply 80K delta
→ publish and verify CP01
→ new worker reloads persisted CP01
→ apply only 320K delta
→ publish and verify CP05
```

禁止：

-在 CP01 state 上重放完整 400K prefix；
-为 CP05 重新从 CP00 clone；
-在一个 worker 内连续完成两个 stage；
-跳过 CP01 persisted reload；
-改变固定 L 或 query repeat；
-使用 Recall threshold 替代 identity/correctness gate。

---

# 14. 输出

成功报告：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_cp05_cumulative_trajectory_r02_results_0716.md
```

若仍在 replay/base 阶段失败：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_cp05_cumulative_r02_stop_analysis_0716.md
```

报告必须包含：

* immutable replay-base lineage；
  -copy/mode/write-denial evidence；
  -static load smoke；
  -sequential replay；
  -DGAI/OdinANN CP01 与 CP05 incremental costs；
  -CP05 final frozen-base identity；
  -DiskANN CP05 stale trajectory；
  -accepted CP01 与 trajectory CP01 replay 的并列结果。

---

# 15. 当前禁止执行

仍不授权：

* CP10；
  -CP20；
  -mixed query/update；
  -DiskANN rebuild；
  -checkpoint-specific L refinement；
  -W2；
  -DEEP；
  -GIST。

---

# 16. 最终裁决

首次 cumulative attempt 的停止有效，且没有产生动态索引状态。

授权创建与 accepted r07 content lineage 精确一致的独立 immutable SIFT1M replay bases，并在全新 R02 identity 下重新执行：

```text
16→80 replay
→ CP00→CP01→CP05 formal trajectory
```

原始 writable replay sources 保持完全不变。
