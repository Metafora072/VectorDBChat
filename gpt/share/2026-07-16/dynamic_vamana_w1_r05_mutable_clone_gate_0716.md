# Dynamic Vamana W1-C：R05 Mutable Private Clone Continuation 门禁

**日期**：2026-07-16

**上游证据**：

* `codex/share/2026-07-16/dynamic_vamana_w1_gt_recovery_results_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_r04_preflight_observer_stop_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_one_percent_canary_r04_results_0716.md`

**裁决**：**R04 STOP VALID；授权建立可写 private clone 并执行新的 R05 continuation**

---

# 1. R04 验收结论

R04 已通过：

* observer-safe process identity regressions；
* continuation preflight；
  -精确 clone capability tests；
* R02 GT/CP01 preservation；
* DGAI private clone 内容一致性检查；
* DGAI checkpoint-0 pre-update query gate。

DGAI pre-update median Recall@10：

```text
L=64  → 0.9513
L=128 → 0.9800
```

全部 result IDs 属于 checkpoint-0 active set。

R04 随后停止于：

```text
phase = DGAI_canary
exit_code = 255
```

marker 仅包含：

```text
clone_ready
index_loaded
```

不存在：

```text
ingest_begin
```

因此：

-没有执行 80,000 insert/delete；
-没有 merge；
-没有发布新的 DGAI 状态；
-OdinANN 未启动；
-DiskANN 未启动；
-R02 GT 与 CP01 preservation 为 pass。

R04 private clone 和结果必须永久保留，不续写、不删除。

---

# 2. 根因裁决

immutable checkpoint-0 base 使用：

```text
directories = 0555
regular files = 0444
```

clone helper 使用：

```bash
cp -a
```

将其权限原样复制到 private clone。

DGAI update driver 随后执行：

```cpp
reader->open(prefix + "_disk.index", true, false);
```

`enable_writes=true` 对应 `O_RDWR`，因此运行用户 `ubuntu` 无法重开 mode `0444` 的文件。

这属于 clone 生命周期语义错误：

```text
immutable base
→ content-identical private clone
→ 仍然保持 immutable permissions
```

正确生命周期应为：

```text
immutable base
→ content-identical private clone
→ capability-bound mutable permission normalization
→ query/update
```

---

# 3. 不使用文件级 write-set 启发式

本轮不维护如下列表：

```text
index_disk.index writable
index_disk.index.tags writable
其他文件 read-only
```

原因是：

* DGAI merge 可能替换多个持久化文件；
* OdinANN save 可能创建、截断、重命名或替换文件；
  -目录本身必须支持 create/rename/unlink；
  -人工 write-set 容易随 artifact 版本变化而失效；
  -后续失败会被误解为系统更新失败。

正式策略定义为：

> 每个由精确 capability 创建的 private clone 是一个完整的可变索引单元。其整个 index subtree 对运行 owner 可读写，对 group/other 不开放写权限。immutable base 始终保持只读。

该策略是确定性的，不依赖文件名或算法阶段猜测。

---

# 4. Mutable clone normalization 工具

新增：

```text
w1_prepare_mutable_clone.py
```

输入：

```text
--clone-root
--base-root
--owner ubuntu
--system DGAI|OdinANN
--output-manifest
```

工具只允许作用于 clone helper 当前正在创建的：

```text
$target.partial.$PID/index
```

不得直接接收任意已有目录。

## 4.1 文件类型门禁

使用 `lstat()` 遍历，不跟随 symlink。

clone subtree 只允许：

* directory；
* regular file。

发现以下任一类型立即停止：

* symbolic link；
* FIFO；
  -socket；
  -device；
  -指向 subtree 外的 hard-link 风险；
  -无法解析的文件。

不得使用会跟随 symlink 的递归 `chmod -R`。

## 4.2 Ownership 与 mode

对 private clone 执行确定性转换：

```text
owner  = ubuntu:ubuntu
dirs   = 0700
files  = 0600
```

同时清除：

* setuid；
  -setgid；
  -sticky；
  -group write；
  -other write；
  -不需要的 execute bits。

该权限仅作用于 private clone，不能作用于 base。

## 4.3 内容不变

权限转换前后分别生成：

```text
clone_content_before.tsv
clone_content_after.tsv
```

两者必须逐字节一致，并且均与：

```text
base_content_before.tsv
```

一致。

权限转换不能修改任何文件内容、大小或路径集合。

---

# 5. Mode 与 ownership manifest

新增：

```text
w1_mode_manifest.py
```

每行至少记录：

```text
relative_path
type
uid
gid
mode_octal
inode
link_count
```

clone helper 输出：

```text
base_mode_before.tsv
base_mode_after_clone.tsv
clone_mode_before.tsv
clone_mode_after.tsv
mutable_clone_audit.json
```

要求：

```text
base_mode_before == base_mode_after_clone
```

以及：

```text
clone_mode_before == base_mode_before
```

转换后：

```text
all clone dirs  = 0700
all clone files = 0600
all clone uid/gid = ubuntu:ubuntu
```

最终 attempt 完成后再次生成：

```text
base_mode_after_attempt.tsv
```

并要求与 `base_mode_before.tsv` 完全一致。

当前仅有 content manifest 不足以证明 immutable base 的 mode 未被改变；R05 必须同时验证内容和权限。

---

# 6. Live writable audit

权限转换完成后，以实际运行用户 `ubuntu` 执行：

```text
w1_writable_clone_audit.py
```

## 6.1 Clone regular files

对每个 regular file：

```text
os.open(path, O_RDWR | O_CLOEXEC | O_NOFOLLOW)
```

只打开并关闭，不写入内容。

所有文件必须成功。

## 6.2 Clone directories

对每个 directory 执行：

```text
create temporary file
→ rename
→ unlink
```

要求全部成功，且测试结束后不存在临时文件。

这验证 DGAI merge/OdinANN save 所需的目录 create/rename 权限。

## 6.3 Immutable base

以 `ubuntu` 身份对 base 执行相反验证：

* regular file 的 `O_RDWR` 必须失败；
  -directory 中 create 必须失败；
  -base 所有 regular file 不得具有 write bit；
  -base 所有 directory 不得具有 write bit。

若 base 中任一对象可写，立即停止。

## 6.4 文件系统属性

如果 clone 文件存在 ACL、xattr 或 filesystem immutable flag，导致上述 live audit 失败，则停止。

不得仅依据 mode bits 推断可写性。

---

# 7. Clone helper 原子顺序

`w1_clone_base.sh` 的顺序固定为：

```text
exact capability validation
→ device/target validation
→ create partial directory
→ cp/reflink clone
→ base content manifest
→ clone content identity
→ base/clone mode manifest
→ mutable permission normalization
→ content identity recheck
→ live writable audit
→ immutable base write-denial audit
→ write clone_manifest
→ atomic rename partial → final target
→ final target content/mode recheck
```

只有全部通过后才发布 final attempt。

任何失败：

-删除当前 `.partial.$PID`；
-不创建 final target；
-不修改 base；
-不继续 pre-update query；
-保留审计日志。

---

# 8. Clone manifest

升级为：

```text
dynamic-vamana-w1-clone-v3
```

至少记录：

```text
system
base_realpath
target_realpath
clone_mode
base_content_manifest_sha256
clone_content_manifest_sha256
base_mode_manifest_sha256
clone_mode_before_sha256
clone_mode_after_sha256
mutable_policy = owner_private_tree_v1
owner_uid
owner_gid
directory_mode = 0700
file_mode = 0600
regular_file_open_tests
directory_create_rename_tests
base_write_denial_tests
normalization_started_ns
normalization_completed_ns
```

另外记录：

```text
apparent bytes
allocated bytes
free-space before
free-space after
```

不得再根据 clone 尚未完成时的瞬时 free-space 推断 reflink 是否成功。

---

# 9. R05 启动前回归

## 9.1 Synthetic permission tree

构造：

```text
source/
  dirs 0555
  files 0444
```

运行 clone normalization 后要求：

* source 仍为 0555/0444；
  -clone 为 0700/0600；
  -content SHA256 一致；
  -clone O_RDWR 全部成功；
  -source O_RDWR 全部失败；
  -directory create/rename 只在 clone 成功。

## 9.2 Capability negative cases

以下情况必须在 mkdir/chmod/chown 前失败：

-错误 run；
-错误 attempt；
-cross-system capability；
-缺少 capability；
-target 已存在；
-symlink escape；
-错误 NVMe；
-试图把 base 作为 clone target；
-试图把 R04 clone 作为 target；
-试图直接 normalize 任意已存在目录。

## 9.3 Atomic failure injection

至少注入：

* copy 后失败；
  -normalization 中途失败；
  -live audit 失败。

要求：

* final target 不存在；
  -base content/mode 不变；
  -partial tree 被清理；
  -后续 query/update 未启动。

测试结果保存：

```text
results/pilot3_sift10m_w1_r05/preflight/mutable_clone_tests.json
```

---

# 10. R05 目录

使用全新目录：

```text
results/pilot3_sift10m_w1_r05/
formal/pilot3_sift10m_w1_r05/
```

attempt：

```text
DGAI/cp01-05
OdinANN/cp01-05
DiskANN/stale-cp00-05
```

报告：

```text
codex/share/2026-07-16/dynamic_vamana_w1_one_percent_canary_r05_results_0716.md
```

不得续写：

```text
cp01-04
stale-cp00-04
```

---

# 11. R05 continuation preflight

在同一 global flock 内重新验证：

## 11.1 历史状态

* R01 停于 GT validation；
* R02 停于 DGAI pre-clone；
* R03 停于 observer process check；
* R04 停于 DGAI update open；
* R04 execution manifest 为 `stopped_failed`；
* R04 marker 不包含 `ingest_begin`；
  -R04 不存在 active-set、publish 或 post-update success marker；
  -OdinANN/DiskANN 未启动。

## 11.2 R04 clone 审计

只读验证 R04 private clone：

* content 仍等于 checkpoint-0 base；
  -没有任何更新产生的新文件；
  -base content/mode 未改变；
  -R04 attempt 保持只读证据状态。

不删除 R04 clone。

## 11.3 复用输入

重新验证：

* R02 GT SHA256 `4703d2...2c28`；
* CP01 八个文件 identity；
  -fixed 1,025-row audit；
  -tag 0 active；
  -canonical binaries；
  -OdinANN io_uring；
  -三套 immutable base；
  -NVMe 与 free space；
  -process identity scan；
  -无 active `dv-w1-*` scope；
  -R05 targets 不存在。

---

# 12. R05 正式顺序

```text
acquire global flock
→ process identity tests
→ continuation preflight
→ mutable-clone regressions
→ exact clone-capability tests
→ DGAI cp01-05 mutable clone
→ DGAI pre-update gate
→ DGAI 80K update
→ DGAI correctness/post-query/final validation
→ OdinANN cp01-05 mutable clone
→ OdinANN pre-update gate
→ OdinANN 80K update
→ OdinANN correctness/post-query/final validation
→ DiskANN stale-cp00-05
→ base content+mode final audit
→ CP01/GT preservation audit
→ final report
→ stop
```

不重新生成 CP01 或 GT。

---

# 13. 系统参数不变

## DGAI

```text
L = 64, 128
Tq = 1
pre-update 每点 3 次
post-update 每点 3 次
80,000 replacements
online visibility unsupported
fresh visibility required
```

## OdinANN

```text
L = 29, 46
Tq = 1
pre-update 每点 3 次
post-update 每点 3 次
80,000 replacements
live visibility required
fresh visibility required
IO engine = io_uring
```

## DiskANN stale control

```text
L = 29, 53
Tq = 1
每点 3 次
stale-static negative control
```

binary、算法参数、update API、trace 和 GT 均不得修改。

---

# 14. Accounting

Clone 和 permission normalization 属于 preparation，不计入：

```text
ingestion throughput
online-visible throughput
restart-visible throughput
update write amplification
```

但必须单独报告：

```text
clone wall time
clone apparent/allocated bytes
clone device read/write
normalization wall time
normalization metadata I/O
```

正式 update accounting 仍从原 `ingest_begin`/publish marker 计算。

---

# 15. 失败规则

R05 任一阶段失败：

-立即停止；
-不启动后续系统；
-保留全部 attempt；
-不自动重试；
-不复用 R05；
-不修改参数；
-不续写失败 clone；
-不删除 R01–R04 证据。

---

# 16. 完成后停止

R05 完成后不自动启动：

* 5%/10%/20% replacement；
  -DiskANN rebuild；
  -checkpoint-1 matched-Recall refinement；
  -mixed query/update；
  -W2；
  -DEEP/GIST。

---

# 17. 最终裁决

R04 停止发生在任何 update API 之前，属于 immutable permission 被错误传播到 private clone。

授权将**整个精确 capability-bound private clone**转换为 owner-only mutable tree，而不是维护文件级 write-set。

通过 permission/content/base-isolation 门禁后，在新 R05 目录继续正式 1% canary。
