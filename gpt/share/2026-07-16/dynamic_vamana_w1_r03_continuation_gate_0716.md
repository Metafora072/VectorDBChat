# Dynamic Vamana W1-C：R03 系统阶段 Continuation 门禁

**日期**：2026-07-16
**上游报告**：

* `codex/share/2026-07-16/dynamic_vamana_w1_gt_recovery_results_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_r02_dgai_preclone_stop_0716.md`

**裁决**：**GT RECOVERY PASS；授权新的 R03 系统阶段 continuation**

---

# 1. R02 验收结论

R02 的 GT recovery 正式通过。

已验证：

* CP01 trace 重验证通过；
* 8,000,000 行 active-vector/tag 语义重建通过；
  -合法 tag 0 保持 active；
* synthetic tag-0 回归通过；
* CP00 GT 与冻结 truthset 逐字节一致；
  -query 7150 top-100 独立审计通过；
  -完整 CP01 GT 的结构与 36-query audit 通过；
  -除 query 7150 外，旧失败 GT 的 9,999 行逐字节一致；
  -query 7150 的旧 99 个有效 pair 全部保留；
  -合法 tag 0 已恢复；
  -没有 less-than-K warning；
  -final GT 已原子发布。

冻结 R02 GT：

```text
path:
groundtruth/sift10m/w1_r02/gt_cp01

SHA256:
4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28
```

该 GT 可以直接复用于 continuation，不重新计算。

---

# 2. R02 pre-clone stop 的性质

R02 停止于：

```text
phase = DGAI_canary
exit_code = 2
```

停止点位于 clone helper 的路径 allowlist 检查。

停止时：

-不存在 `DGAI/cp01-02`；
-没有 index clone；
-没有 pre-update query；
-没有 insert/delete；
-没有 DGAI merge；
-没有 OdinANN attempt；
-没有 DiskANN stale control；
-没有任何部分更新状态。

因此不需要回滚索引，也不需要重新执行 CP01 或 GT preparation。

R02 目录作为失败证据永久保留，不在其中续写。

---

# 3. Clone allowlist 修复

## 3.1 禁止宽泛通配符

不得把 helper 修改成：

```text
pilot3_sift10m_w1_r*/*
```

或：

```text
formal/pilot3_sift10m_w1*
```

此类规则会让未来未经审议的 run 自动获得 clone 权限。

## 3.2 精确 target capability

为 `w1_clone_base.sh` 增加环境变量：

```text
W1_ALLOWED_CLONE_TARGET
```

规则：

```bash
allowed=$(realpath -m "$W1_ALLOWED_CLONE_TARGET")
[[ "$target" == "$allowed" ]] || fail
```

在 continuation 中，每个 systemd scope 只收到一个精确值：

```text
DGAI:
formal/pilot3_sift10m_w1_r03/DGAI/cp01-03

OdinANN:
formal/pilot3_sift10m_w1_r03/OdinANN/cp01-03
```

要求：

-环境变量非空；
-target 必须逐字节等于其 canonical realpath；
-target 的 system component 与传入 system 一致；
-target 的 basename 必须为 `cp01-03`；
-target 尚不存在；
-target 位于项目 NVMe；
-不接受 symlink escape；
-一个 scope 的 DGAI capability 不能用于 OdinANN；
-helper 完成后不把 capability 写入持久化脚本。

原有 micro replay 和原始 formal 规则可以保留，但 R03 必须走精确 capability 分支。

## 3.3 Preflight-only target test

新增只读检查模式：

```text
W1_CLONE_PREFLIGHT_ONLY=1
```

该模式执行：

* authorization；
  -system；
  -base marker；
  -base/target realpath；
  -exact target capability；
  -device；
  -target nonexistence；

随后在任何 `mkdir`、manifest、reflink 或 copy 前退出 0。

R03 正式启动前，分别对 DGAI 和 OdinANN 的精确 target 执行一次该检查。

---

# 4. 新 R03 目录

使用全新路径：

```text
results/pilot3_sift10m_w1_r03/
formal/pilot3_sift10m_w1_r03/
```

system attempts：

```text
DGAI/cp01-03
OdinANN/cp01-03
DiskANN/stale-cp00-03
```

正式结果报告：

```text
codex/share/2026-07-16/dynamic_vamana_w1_one_percent_canary_r03_results_0716.md
```

不得使用或创建：

```text
cp01-02
stale-cp00-02
```

R02 的空父目录保持原状。

---

# 5. R03 continuation preflight

在同一 global flock 中，执行只读 continuation preflight。

## 5.1 父运行状态

要求：

```text
R01 status = stopped_failed
R01 stopped_phase = gt_validation

R02 status = stopped_failed
R02 stopped_phase = DGAI_canary
R02 exit_code = 2
```

并验证 R02 中：

-没有 DGAI attempt；
-没有 OdinANN attempt；
-没有 DiskANN attempt；
-没有 success marker；
-只允许已经报告的空 system 父目录与 GT recovery/preflight 证据。

## 5.2 GT identity

重新验证：

```text
gt_cp01 SHA256 =
4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28
```

同时检查：

* shape `10000×100`；
  -finite；
  -逐行距离单调；
  -ID 属于 CP01 active set；
  -无 deleted tag；
  -query 7150 包含 tag 0；
  -GT recovery validation/report hash 与 R02 一致。

不重新运行 KNN 或 remap。

## 5.3 CP01 preservation

重新验证当前 CP01：

-八个文件的 size/SHA256/mtime 与 R02 reuse manifest 相同；
-trace validation 仍通过；
-8M active tags cardinality；
-tag 0 active；
-原 CP01 目录内容未改变。

本次不要求再次流式读取全部 8M vectors；复用 R02 已完成的完整语义重建证据，并对固定 1,025 row 重新抽样即可。

## 5.4 Frozen artifacts

重新验证：

* DGAI canonical v6 driver/query hash；
* OdinANN canonical v6 driver/query hash；
  -OdinANN `USE_URING`、`liburing`、无 `libaio`；
  -DGAI/OdinANN/DiskANN 三套 CP00 base manifest；
  -query、CP00 GT、full corpus SHA256；
  -NVMe major:minor；
  -可用空间不少于 150 GB；
  -无遗留 W1 tmux、scope、进程或 global lock owner。

## 5.5 新目标

要求以下均不存在：

```text
results/pilot3_sift10m_w1_r03
formal/pilot3_sift10m_w1_r03
```

完成 preflight 后创建新的 R03 execution manifest，记录：

```text
continuation_parent_r01 = pilot3_sift10m_w1
continuation_parent_r02 = pilot3_sift10m_w1_r02
r02_gt_reused = true
r02_gt_sha256 = 4703...
cp01_reused = true
clone_allowlist_mode = exact_target_capability
```

---

# 6. 执行前最小测试

clone allowlist 修改不涉及索引算法，无需再次运行 GT recovery 或完整 micro update replay。

但必须执行：

1. DGAI R03 target 的 preflight-only 检查返回 0；
2. OdinANN R03 target 的 preflight-only 检查返回 0；
3. DGAI capability 用于 OdinANN target 必须失败；
4. OdinANN capability 用于 DGAI target 必须失败；
5. `cp01-02`、`cp01-04` 和任意其他路径必须失败；
6. symlink escape 必须失败；
   7.没有 capability 时 R03 target 必须失败；
   8.所有失败都发生在创建目录之前。

将测试结果保存为：

```text
results/pilot3_sift10m_w1_r03/preflight/clone_target_tests.json
```

---

# 7. R03 正式顺序

GT 已恢复完成，本轮从系统阶段开始：

```text
acquire global flock
→ continuation preflight
→ exact clone-target tests
→ DGAI cp01-03
→ DGAI final validation
→ OdinANN cp01-03
→ OdinANN final validation
→ DiskANN stale-cp00-03
→ R03 final report
→ stop
```

不得再次运行：

* CP01 materialization；
  -location GT；
  -tag remap；
  -CP00 GT regression；
  -full CP01 GT computation。

---

# 8. DGAI 与 OdinANN 门禁

继续沿用上一轮已经批准的全部正式参数和验证：

* DGAI L=64、128；
* OdinANN L=29、46；
* Tq=1；
  -pre-update 每点三次；
  -post-update 每点三次；
  -完整 10K queries；
  -pre-update Recall gate；
  -80,000 replacements；
  -active-tag exact audit；
  -result-ID visibility probes；
  -immutable base integrity；
  -phase I/O；
  -serving memory；
  -index growth；
  -OOM/fatal/error 检查。

DGAI：

```text
online visibility = unsupported
fresh-process visibility required
```

OdinANN：

```text
live visibility required
fresh-process visibility required
```

参数、binary 和 update API 均不得修改。

---

# 9. DiskANN stale control

沿用：

```text
L = 29, 53
Tq = 1
每点三次
```

必须标记为：

```text
stale-static negative control
```

不得参与 update-throughput 排名。

---

# 10. 失败规则

R03 任一阶段失败：

-立即停止；
-不启动后续系统；
-保留全部 attempt；
-不自动重试；
-不改参数；
-不续写失败 clone；
-不返回 R02 或 R01 目录补写；
-不删除 GT recovery 和 pre-clone stop 证据。

---

# 11. 完成后停止

R03 完成后不自动执行：

* 5% replacement；
  -10% replacement；
  -20% replacement；
  -DiskANN rebuild；
  -checkpoint-1 matched-Recall refinement；
  -mixed query/update；
  -W2；
  -DEEP/GIST。

---

# 12. 最终裁决

R02 GT recovery 通过，pre-clone 停止不涉及任何索引状态变化。

授权修复 clone helper 的**精确 target capability**，并在新 R03 目录中从 DGAI 系统阶段继续。

R03 不重新生成 CP01 或 GT。
