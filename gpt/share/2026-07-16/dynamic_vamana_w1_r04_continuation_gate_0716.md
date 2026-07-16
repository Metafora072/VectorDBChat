# Dynamic Vamana W1-C：R04 Observer-Safe Continuation 门禁

**日期**：2026-07-16

**上游证据**：

* `codex/share/2026-07-16/dynamic_vamana_w1_gt_recovery_results_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_r02_dgai_preclone_stop_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_r03_preflight_observer_stop_0716.md`

**裁决**：**R03 STOP VALID；授权修复进程身份判定并执行新的 R04 continuation**

---

# 1. 当前有效状态

以下结果继续有效：

* CP01 数据已完成只读复用审计；
* R02 checkpoint-1 GT recovery 全部通过；
  -最终 GT SHA256 为：

```text
4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28
```

* R02 停止于 DGAI clone 前；
* R03 停止于 continuation preflight；
* R02/R03 均未创建任何 index clone；
  -未执行 pre-update query；
  -未执行 80K insert/delete；
  -未启动 OdinANN 或 DiskANN；
  -没有需要恢复或回滚的动态索引状态。

R03 的失败原因仅为 observer 命令行文本误匹配，不影响 CP01、GT、canonical binaries 或 immutable bases。

---

# 2. 不接受的修复

不得继续使用：

```text
ps -eo pid,args
→ 对整行文本做关键词或正则搜索
```

也不得仅修改为：

```text
任意 argv token 的 basename == w1_canary
```

第二种方式仍可能把以下合法 observer 误判：

```text
python3 observer.py w1_canary
rg w1_canary
echo w1_run_system_canary
```

进程身份必须来自可执行路径、脚本路径或 systemd cgroup，而不是普通参数内容。

---

# 3. Worker 身份分类器

新增独立工具：

```text
w1_process_identity.py
```

提供：

```text
scan
test-fixtures
```

两个模式。

## 3.1 Systemd scope 检查

首先检查所有 active scope：

```text
dv-w1-*.scope
```

通过 systemd unit 与对应：

```text
/sys/fs/cgroup/.../cgroup.procs
```

读取真实进程。

在 continuation preflight 时，除已经结束的 runtime canary 外，不允许存在任何 active `dv-w1-*` scope。

任一 active scope 均报告：

```text
unit
control_group
pid list
/proc/<pid>/exe
/proc/<pid>/cmdline
```

然后 fail closed。

不能通过进程命令行文本决定该 scope 是否相关。

## 3.2 直接二进制身份

对于 `/proc/<pid>/exe`，仅在 resolved realpath 精确等于以下冻结路径时认定为 W1 worker：

```text
canonical DGAI w1_canary
canonical DGAI search_disk_index
canonical OdinANN w1_canary
canonical OdinANN search_disk_index
frozen DiskANN search_disk_index
frozen compute_groundtruth
```

路径和 SHA256 来自 frozen artifact manifest。

仅 basename 相同但路径不同的进程不得被判为正式 worker。

## 3.3 Shell 脚本身份

对于 `/proc/<pid>/exe` 为受支持 shell 的进程：

```text
/usr/bin/bash
/usr/bin/dash
/usr/bin/zsh
```

只解析 shell 实际执行脚本的位置。

例如：

```text
bash /canonical/path/w1_run_system_canary.sh ...
```

只有 script token resolve 后精确等于批准脚本路径，才认定为 worker。

批准路径包括实际可能存活的：

```text
w1_run_system_canary.sh
w1_system_worker.sh
w1_diskann_stale_control.sh
run_w1_cp01_formal.sh
run_w1_gt_recovery_r02.sh
run_w1_r03_continuation.sh
run_w1_r04_continuation.sh
```

不得扫描脚本之后的普通参数。

对于：

```text
bash -c "..."
zsh -lc "..."
```

不得解析 command string 中的关键词来推断 worker 身份。

## 3.4 Python 脚本身份

对于 `/proc/<pid>/exe` 为 Python interpreter 的进程，只检查 Python 的实际 script argument。

仅当 resolved script path 精确属于批准的 W1 worker/collector 路径时，才判定为 worker。

JSON、正则、policy 文本和其他普通参数中的 worker 名称全部忽略。

## 3.5 Ancestor 与当前控制器

继续排除 preflight 自身及其完整 ancestor chain。

当前 R04 controller 的 PID、PPID chain、tmux session 与 global-lock inode 必须写入 preflight JSON。

不得通过宽泛的“忽略所有 root/bash/python”绕过真实 worker 检测。

---

# 4. 进程身份回归测试

启动 R04 前必须运行以下测试，并保存：

```text
results/pilot3_sift10m_w1_r04/preflight/process_identity_tests.json
```

## 4.1 Observer 负例

以下进程均不得被识别为 worker：

```text
rg 'w1_canary|w1_run_system_canary'
zsh -lc 'ps ... | rg w1_canary'
python3 observer.py w1_canary
python3 -c 'sleep(...)' w1_run_system_canary
echo w1_diskann_stale_control
```

还应覆盖 Codex sandbox/bwrap 命令行中包含这些文本的 fixture。

## 4.2 Path 负例

下列进程不得仅因 basename 相同而被识别：

```text
/tmp/w1_canary
/tmp/w1_run_system_canary.sh
```

前提是其 resolved path 不等于 frozen canonical path。

## 4.3 Canonical 正例 fixture

使用固定 `/proc` fixture 验证：

* canonical `w1_canary` executable path 会被拒绝；
* canonical `search_disk_index` executable path 会被拒绝；
* shell interpreter 加 canonical worker script path 会被拒绝；
* Python interpreter 加 canonical worker script path会被拒绝。

fixture 必须保存：

```text
pid
exe
argv
cgroup
expected classification
actual classification
```

## 4.4 Scope 正例

创建受控测试 scope：

```text
dv-w1-stale-fixture.scope
```

其中运行无害 `sleep`。

要求 scope scanner 将其判为 stale W1 scope并拒绝。

随后显式停止 scope，确认下一次 scan 通过。

## 4.5 Ancestor 测试

确认当前 preflight/controller ancestor 不被当作 stale sibling，但同路径的非祖先 fixture 仍会被拒绝。

所有测试必须通过后才能进入正式 preflight。

---

# 5. R04 目录与 attempt

使用全新路径：

```text
results/pilot3_sift10m_w1_r04/
formal/pilot3_sift10m_w1_r04/
```

attempt：

```text
DGAI/cp01-04
OdinANN/cp01-04
DiskANN/stale-cp00-04
```

正式报告：

```text
codex/share/2026-07-16/dynamic_vamana_w1_one_percent_canary_r04_results_0716.md
```

不得创建或续写：

```text
cp01-02
cp01-03
stale-cp00-02
stale-cp00-03
```

---

# 6. Clone capability 泛化

当前 helper 对 R03 路径存在静态绑定。R04 不再增加新的宽泛路径 pattern。

为 continuation scope 使用以下完整 capability：

```text
W1_ALLOWED_CLONE_TARGET
W1_ALLOWED_CLONE_SYSTEM
W1_ALLOWED_CLONE_RUN
W1_ALLOWED_CLONE_ATTEMPT
```

R04 的值分别为：

```text
run = pilot3_sift10m_w1_r04
attempt = cp01-04
```

helper 必须验证：

```text
target ==
$ATLAS_ROOT/formal/
$W1_ALLOWED_CLONE_RUN/
$W1_ALLOWED_CLONE_SYSTEM/
$W1_ALLOWED_CLONE_ATTEMPT
```

并同时要求：

```text
target == realpath -m(W1_ALLOWED_CLONE_TARGET)
system == W1_ALLOWED_CLONE_SYSTEM
basename(target) == W1_ALLOWED_CLONE_ATTEMPT
```

每个 systemd scope 只获得自身的 capability。

不得接受：

-其他 run；
-其他 attempt；
-cross-system target；
-缺少任一 capability；
-symlink escape；
-target 已存在；
-不在项目 NVMe 上的路径。

保留 `W1_CLONE_PREFLIGHT_ONLY=1`，且所有检查在任何目录创建前完成。

---

# 7. R04 continuation preflight

在同一个 global flock 内重新验证：

## 7.1 R01/R02/R03 状态

* R01 在 GT validation fail closed；
* R02 在 DGAI pre-clone fail closed；
* R03 在 observer process check fail closed；
* R03 result/formal tree 不存在；
* R03 controller log SHA256 为：

```text
e32beff751641dc83af4acefe2214186a4941eb57a46c1bb20eed4eabc91b944
```

-三轮均无 dynamic attempt 或 success marker。

## 7.2 GT 与 CP01

重新验证：

```text
R02 GT SHA256 = 4703d2...
```

并检查：

* GT shape；
  -distance finite/monotonic；
  -query 7150 包含 tag 0；
* CP01 八个文件 identity；
  -tag 0 active；
  -fixed 1,025-row mapping audit；
* CP01 与 GT mtime/content 未被 R03 修改。

不重新运行 GT KNN、remap 或 8M full semantic rebuild。

## 7.3 Artifacts 与环境

重新验证：

* canonical v6 DGAI/OdinANN binaries；
  -OdinANN io_uring identity；
* DiskANN binary；
  -三套 immutable base manifest；
  -full corpus/query/CP00 GT；
  -NVMe major:minor；
  -free space ≥150 GB；
  -global lock；
  -无 active `dv-w1-*` scope；
  -新的 process identity scan 通过；
  -R04 result/formal target 不存在。

---

# 8. Observer 规则

R04 可以被只读观察，但 observer 不得：

-持有 global lock；
-进入 `dv-w1-*` scope；
-打开可写 attempt/index 文件；
-修改 CP01、GT 或 result tree；
-向运行进程发送信号。

推荐 observer 只读取：

```text
tmux session existence
systemd unit state
controller log
execution manifest
result directory marker
device free space
```

observer 的命令行可以包含 worker 名称；新的身份分类器不应因此误判。

---

# 9. R04 执行顺序

```text
acquire global flock
→ process-identity regression tests
→ R04 continuation preflight
→ exact clone-capability tests
→ DGAI cp01-04
→ DGAI complete validation
→ OdinANN cp01-04
→ OdinANN complete validation
→ DiskANN stale-cp00-04
→ final preservation audit
→ R04 report
→ stop
```

不重新执行 CP01 preparation 或 GT recovery。

---

# 10. 系统参数与门禁保持不变

## DGAI

```text
L = 64, 128
Tq = 1
pre-update: 每点三次
post-update: 每点三次
80,000 replacements
online visibility = unsupported
fresh visibility required
```

## OdinANN

```text
L = 29, 46
Tq = 1
pre-update: 每点三次
post-update: 每点三次
80,000 replacements
live visibility required
fresh visibility required
IO engine = io_uring
```

## DiskANN stale control

```text
L = 29, 53
Tq = 1
每点三次
stale-static negative control
```

所有原有 Recall、active set、probe、I/O、memory、OOM、base-integrity 与 binary-identity 门禁继续生效。

---

# 11. 失败规则

R04 任一阶段失败：

-立即停止；
-不执行后续系统；
-保留全部证据；
-不自动重试；
-不复用 R04 名称；
-不续写失败 clone；
-不修改参数；
-不回到 R01/R02/R03 目录补写。

---

# 12. 完成后停止

R04 完成后不自动启动：

* 5%/10%/20% replacement；
  -DiskANN rebuild；
  -checkpoint-1 matched-Recall refinement；
  -mixed query/update workload；
  -W2；
  -DEEP/GIST。

---

# 13. 最终裁决

R03 observer-interference stop 有效，未产生索引状态。

授权以 canonical executable/script path 与 systemd cgroup 为依据修复进程身份检查，并使用新的 R04 目录继续正式系统阶段。

R04 不重新生成 CP01 或 GT。
