# Dynamic Vamana W1-C：Checkpoint-1 GT 恢复与 R02 执行门禁

**日期**：2026-07-16
**上游停止报告**：`codex/share/2026-07-15/dynamic_vamana_w1_one_percent_canary_results_0715.md`
**裁决**：**FAIL-CLOSED STOP VALID；授权受限 GT 恢复与新的 R02 正式执行**

---

# 1. 当前停止结果验收

当前停止属于有效的 fail-closed 行为。

已经确认：

* fresh execution preflight 通过；
* 80K trace 与 trace validation 通过；
* checkpoint-1 active tags 与 active vectors 已完成；
* exact-GT 进程正常退出；
* validator 检测到结构错误后立即停止；
* DGAI、OdinANN、DiskANN 均未开始；
  -没有正式系统 clone；
  -没有 partial update 状态；
  -失败 GT、资源记录和 execution manifest 均已保留。

当前结果不能支持任何 1% churn 性能结论。

---

# 2. 根因裁决

失败来自 DiskANN `compute_groundtruth` 的 tagged 模式：

```cpp
if (!location_to_tag.empty())
    if (location_to_tag[location] == 0)
        continue;
```

该逻辑将 tag `0` 解释为无效位置。

但本实验的：

```text
active_cp01.tags.bin
```

是一个 dense location-to-tag 映射：

-每个 active-vector row 都有效；
-tag 唯一；
-tag `0` 合法；
-row 0 对应 tag 0；
-不存在需要由 tag 0 表示的空洞。

因此，该 sentinel 约定不适用于本实验。

query 7150 的 exact top-100 包含 tag 0，导致 tagged 模式只保留 99 个候选并写出未初始化尾项。

---

# 3. 恢复方案：Location GT 后置映射

本轮不修改 DiskANN 的距离计算、排序或分块 KNN 实现。

继续使用当前已经冻结的：

```text
compute_groundtruth
```

但运行时不传：

```text
--tags_file
```

先生成 location-ID truthset：

```text
gt_cp01_locations.tmp
```

其中 ID 表示：

```text
active_cp01.bin 中的 row index
```

随后使用：

```text
active_cp01.tags.bin
```

执行：

```text
external_tag = active_tags[location_id]
```

得到最终：

```text
gt_cp01
```

距离矩阵保持逐字节不变。

该方法只把原工具内部的最终 tag 映射移到一个独立、可审计的后处理步骤，不改变 nearest-neighbor 计算。

---

# 4. Truthset remap 工具

新增：

```text
w1_remap_truthset_locations_to_tags.py
```

输入：

```text
--location-truthset
--active-tags
--output
```

严格读取布局：

```text
int32 nquery
int32 K
uint32 IDs[nquery][K]
float distances[nquery][K]
```

要求：

1. `nquery = 10,000`；
2. `K = 100`；
   3.所有 location ID `< 8,000,000`；
   4.每行 location ID 无重复；
3. active-tag 数量恰好为 8,000,000；
4. active tags 全局唯一；
   7.tag 0 恰好出现一次；
   8.距离全部 finite；
   9.每行距离单调非降；
   10.只修改 ID block；
   11.distance block 的 SHA256 在 remap 前后完全相同；
   12.通过临时文件加原子 rename 写出。

任何检查失败时，不得产生最终 GT 文件。

---

# 5. 不完整 GT 必须 fail closed

GT wrapper 必须检查日志中是否存在：

```text
WARNING: found less than k GT entries
```

出现任何一行即判定失败。

location truthset 只能先写入临时目录。只有完成：

-工具返回码；
-log 检查；
-location truthset validator；
-tag remap；
-final truthset validator；

之后，才原子发布最终文件。

不得再接受“进程返回 0，但结果只有 99 项”的状态。

---

# 6. CP01 产物复用

允许复用当前已经生成的 CP01 数据，不重新物化 4.1 GB active vectors。

复用前必须生成新的只读审计：

```text
cp01_reuse_validation.json
```

重新验证：

* `replace_cp01_80k.bin`；
* `replace_cp01_80k.tsv`；
* `replace_cp01_manifest.json`；
* `trace_validation.json`；
* `active_cp01.tags.bin`；
* `active_cp01.bin`；
* `visibility_probes.bin`；
* `visibility_probes.json`。

要求其 size 和 SHA256 与第一次正式执行的 execution manifest 完全一致。

另外重新检查：

```text
active_cp01 cardinality = 8,000,000
tag 0 remains active
delete/insert sets correct
probe positions = 9
insert/delete probes = 18
```

对 tag 0 以及由固定 seed 选择的 1,024 个 row 执行：

```text
active_cp01[row] == full_10m[active_tag[row]]
```

任何不一致都禁止复用，并停止，不自动重新物化。

复用审计不能修改原 CP01 目录。

---

# 7. GT 回归测试

正式生成完整 GT 前必须通过以下测试。

## 7.1 Synthetic tag-0 test

构造小型数据集：

-包含合法 tag 0；

* query 的最近邻为 tag 0；
* K 至少为 2。

要求：

* location 模式返回完整 K；
  -remap 后包含 tag 0；
  -距离与独立 brute force 一致；
  -无 warning；
  -距离单调。

## 7.2 CP00 regression

使用相同 location-GT 加 remap 流程重新生成 checkpoint-0 GT。

要求新结果与现有冻结：

```text
gt_cp00
```

逐字节完全一致。

若不一致，停止并报告全部差异，不能继续 CP01。

## 7.3 Query 7150 targeted audit

先只对 query 7150 生成 top-100：

* location GT 必须有完整 100 项；
  -remap 后必须包含合法 tag 0；
  -tag 0 的距离必须与独立 brute force 一致；
  -100 个 ID 与距离必须和独立 exact result 一致；
  -不得出现尾部 `distance=0` 伪项。

---

# 8. 新 GT 与新 attempt 路径

原失败证据保持不变：

```text
groundtruth/sift10m/w1/
results/pilot3_sift10m_w1/
```

不得覆盖、删除或重新标记为成功。

新的恢复路径：

```text
groundtruth/sift10m/w1_r02/
results/pilot3_sift10m_w1_r02/
formal/pilot3_sift10m_w1_r02/
```

系统 attempt：

```text
DGAI/cp01-02
OdinANN/cp01-02
DiskANN/stale-cp00-02
```

新的 execution manifest 必须记录：

```text
recovery_parent = pilot3_sift10m_w1
parent_stop_stage = gt_validation
cp01_reused = true
cp01_reuse_manifest_sha256
failed_gt_preserved = true
```

---

# 9. Full CP01 GT 验证

完整 10K GT 生成后，验证：

* shape 为 `10000 × 100`；
  -所有 ID 均属于 `active_cp01.tags.bin`；
  -不存在 deleted tag；
  -每行 ID 无重复；
  -所有距离 finite；
  -每行距离单调非降；
  -日志中不存在 less-than-K warning。

独立 brute-force audit 至少覆盖：

```text
0
17
7150
9999
```

以及由固定 seed 选择的另外 32 个 query。

query 7150 必须作为显式回归项保留在 validator 输出中。

同时比较失败 GT：

-除 query 7150 外，其余 9,999 行必须逐字节一致；
-query 7150 的旧 99 个有效 `(tag,distance)` 必须全部存在于新 top-100；
-新结果必须补回 tag 0；
-不得通过手工编辑失败 GT 生成新文件。

---

# 10. Recovery preflight

新增 recovery 模式，例如：

```text
run_w1_cp01_formal.sh recovery
```

它必须在同一 global flock 内验证：

-原 execution manifest 状态为 `stopped_failed`；
-停止阶段为 `gt_validation`；
-旧运行不存在 DGAI/OdinANN/DiskANN attempt；
-不存在遗留 W1 进程、scope 或 tmux；

* CP01 reuse validation 通过；
  -旧失败 GT 目录未改变；
  -新 R02 GT/result/formal 目录不存在；
* DGAI/OdinANN canonical binary hash 未改变；
  -OdinANN 仍为 io_uring；
  -三个 checkpoint-0 base manifest 未改变；
  -free space 仍通过门禁。

recovery 模式不得重新执行 CP01 materialization。

---

# 11. 正式恢复执行

完成 GT synthetic、CP00 regression、query-7150 audit 和 full GT validation 后，可以自动继续，不再等待中间人工审批。

顺序：

```text
acquire global flock
→ recovery preflight
→ CP01 reuse audit
→ location-ID CP01 GT
→ location GT validation
→ tag remap
→ final CP01 GT validation
→ DGAI cp01-02
→ DGAI final validation
→ OdinANN cp01-02
→ OdinANN final validation
→ DiskANN stale-cp00-02
→ recovery final report
→ stop
```

DGAI/OdinANN 的：

* pre-update Recall gate；
  -固定 L；
  -三次 post-update query；
  -active-tag audit；
  -live/fresh probes；
  -phase I/O；
  -base integrity；

全部沿用上一轮已批准门禁，不得修改。

---

# 12. 失败规则

任一 recovery 阶段失败：

-立即停止；
-保留全部新 attempt；
-不执行后续系统；
-不自动重试；
-不修改 CP01；
-不回填或手工修正 GT；
-不删除原失败证据。

---

# 13. 输出

GT 修复与审计报告：

```text
codex/share/2026-07-16/dynamic_vamana_w1_gt_recovery_results_0716.md
```

正式 R02 完成后报告：

```text
codex/share/2026-07-16/dynamic_vamana_w1_one_percent_canary_r02_results_0716.md
```

若 recovery 在 GT 阶段再次失败，只提交前一个报告并停止。

---

# 14. 完成后停止

R02 完成后不自动执行：

* 5% replacement；
  -10% replacement；
  -20% replacement；
  -DiskANN rebuild；
  -checkpoint-1 matched-Recall refinement；
  -mixed query/update；
  -DEEP/GIST；
  -W2。

---

# 15. 最终裁决

当前 CP01 数据可以在严格 hash 和 row-mapping 审计后复用。

本轮不修改 DiskANN exact-KNN 核心，也不使用 tagged GT 模式。使用：

```text
location-ID exact GT
→ dense active-tag remap
```

消除合法 tag 0 与哨兵值之间的歧义。

通过全部 GT 回归门禁后，授权在新的 R02 目录中继续正式 1% canary。
