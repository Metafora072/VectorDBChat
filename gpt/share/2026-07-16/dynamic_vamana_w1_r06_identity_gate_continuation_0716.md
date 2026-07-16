# Dynamic Vamana W1-C：R06 Identity-Gated Continuation 门禁

**日期**：2026-07-16

**上游证据**：

* `codex/share/2026-07-16/dynamic_vamana_w1_one_percent_canary_r05_results_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_r05_odin_preupdate_stop_analysis_0716.md`

**裁决**：

* **接受 R05 DGAI 为有效的独立 1% canary 结果**
* **接受 OdinANN pre-update fail-closed**
* **废止绝对 Recall 区间作为 clone 正确性门禁**
* **授权在新的 R06 中仅继续 OdinANN 与 DiskANN stale control**

---

# 1. R05 结果边界

## 1.1 DGAI

R05 DGAI 已完成：

```text
mutable private clone
→ checkpoint-0 pre-update query
→ 80,000 deletes + 80,000 inserts
→ merge/publish
→ fresh-process visibility
→ active-set exact audit
→ checkpoint-1 post-update query
→ immutable-base content/mode audit
```

后续 OdinANN pre-update gate 失败不会使已经完成且独立验证的 DGAI attempt 失效。

因此：

```text
R05 DGAI cp01-05 = accepted system-level canary
```

不在 R06 中重复执行 DGAI。

重复 DGAI：

-不会修复 OdinANN 门限来源问题；
-会产生第二份非必要更新样本；
-增加约 14 GB clone 与更新成本；
-模糊哪一个 DGAI attempt 是正式结果。

## 1.2 OdinANN

R05 OdinANN 已完成：

* mutable clone；
  -content exact audit；
  -permission/live-writable audit；
  -base write-denial audit；
  -六次 checkpoint-0 query；
  -result-ID active audit；
  -NVMe read 与 resource audit。

但不存在：

```text
markers.jsonl
ingest_begin
insert/delete
online probe
save
post-update query
```

因此 OdinANN 索引仍处于 checkpoint-0 状态，R05 Odin attempt只作为停止证据保留。

---

# 2. 废止绝对 Recall clone gate

原 pre-update gate 使用：

```text
DGAI/OdinANN 0.95 policy:
[0.950, 0.955]

DGAI/OdinANN 0.98 policy:
[0.980, 0.985]
```

该规则存在两个问题。

## 2.1 Provenance 不一致

历史 P2B 使用的 OdinANN query binary 与 R05 canonical-v6 query binary 并非 byte-identical。

因此历史 Recall 分布不能直接作为新 binary 的严格 acceptance interval。

## 2.2 Recall 是随机执行观测，不是 clone 身份

R05 canonical-v6 OdinANN：

```text
L=46:
0.97983
0.97993
0.97994
```

三次均正常完成，且：

-输出完整；
-所有 ID active；
-无 fatal；
-无 OOM；
-无 I/O error；
-真实读取 NVMe；
-clone 与 base 内容相同。

`0.97993` 与 `0.98000` 的差异不能证明 artifact 错误。

继续建立新的 Recall interval 会引入新的经验阈值，不能从系统语义或实验身份中推出。

---

# 3. Pre-update gate v2

新增：

```text
w1_preupdate_identity_gate.py
```

或为现有工具增加显式版本：

```text
--gate-policy identity-v2
```

不得静默改变旧结果的解释。

输出 schema：

```text
dynamic-vamana-w1-preupdate-identity-v2
```

## 3.1 硬门禁：Artifact identity

必须精确匹配：

* query binary SHA256；
  -driver SHA256；
  -index base manifest SHA256；
  -clone initial content manifest SHA256；
  -query SHA256；
  -checkpoint-0 GT SHA256；
  -checkpoint-0 active-tag SHA256；
  -requested L；
  -thread count；
  -I/O engine；
  -device major:minor。

要求：

```text
clone initial content manifest == immutable base content manifest
```

## 3.2 硬门禁：执行正确性

每个 L 仍运行三次。

每次必须满足：

* exit code 为 0；
  -完整生成 metrics JSON；
  -完整生成 `10000 × 10` result-ID 文件；
  -所有 metrics finite；
  -Recall 位于数学定义域 `[0,1]`；
  -每个 query 返回 10 个有效 ID；
  -每行不存在 sentinel ID；
  -每行不存在重复 ID；
  -所有 ID 属于 checkpoint-0 active set；
  -无 fatal/assertion/EBADF/negative CQE/I/O error；
  -无 OOM 或 OOM-kill；
  -NVMe read bytes 大于 0；
  -log 中实际 L 与请求 L 一致；
  -binary、query、GT 和 index identity 在三次运行间不变。

以上任一失败仍立即停止。

## 3.3 Recall 只作为观测

保存每次：

```text
exact Recall@10
QPS
mean latency
P50/P95/P99
mean I/O
NVMe reads
result-ID hash
```

计算：

```text
median
min
max
per-query top-10 exact-match rate
result-slot overlap
```

但不得依据 Recall 是否落入某个经验区间决定 clone 是否有效。

可以报告：

```text
observed_policy_recall
```

不得再报告：

```text
recall_interval_pass
```

## 3.4 质量顺序仅做诊断

记录：

```text
median Recall(L=46) vs median Recall(L=29)
```

但不设置人为差值阈值。

若高 L 的 Recall 明显低于低 L，报告异常并停止在静态审计阶段；不得自动调整 L。这里的异常必须结合原始 result IDs 和执行错误分析，不通过固定 epsilon 判定。

---

# 4. 冻结 R05 DGAI 证据

R06 启动前，先对 R05 DGAI 做只读冻结审计。

输出：

```text
results/pilot3_sift10m_w1_r06/preflight/
  r05_dgai_freeze.json
  r05_dgai_evidence_manifest.tsv
```

必须验证：

* `FORMAL_W1_CANARY_OK` 存在；
  -marker 顺序完整；
  -`ingest_begin/end` 完整；
  -`publish_begin/end` 完整；
  -fresh-process visibility verified；
  -DGAI online visibility 明确为 unsupported；
  -active-tag exact audit 通过；
  -fresh probes 18/18；
  -pre-update 6 个 query point valid；
  -post-update 6 个 query point valid；
  -checkpoint-1 GT identity 正确；
  -base content/mode 最终不变；
  -no OOM/fatal/I/O error；
  -canary collector 输出完整；
  -clone manifest v3 完整；
  -result tree 中所有正式证据文件生成 size/SHA256 manifest。

同时生成：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_r05_dgai_partial_results_0716.md
```

该报告必须给出 DGAI 的实际：

* ingestion time 与 throughput；
  -restart-visible time 与 throughput；
  -ingest/publish/end-to-end device I/O；
  -index persistent growth；
  -payload-normalized writes；
  -peak memory；
  -pre/post Recall、QPS、P99 和 mean I/O；
  -三次原始 query values。

在该冻结审计通过前，不启动 R06 OdinANN。

---

# 5. R06 目录

使用全新路径：

```text
results/pilot3_sift10m_w1_r06/
formal/pilot3_sift10m_w1_r06/
```

attempt：

```text
OdinANN/cp01-06
DiskANN/stale-cp00-06
```

R06 不创建 DGAI clone。

正式报告：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_one_percent_canary_r06_results_0716.md
```

R05 所有 DGAI/OdinANN 目录保持不变。

---

# 6. R06 continuation preflight

在同一个 global flock 内验证：

## 6.1 历史状态

* R01 停于 GT validation；
* R02 GT recovery 通过，随后停于 pre-clone；
* R03 停于 observer identity；
* R04 停于 immutable clone permission；
* R05 DGAI system attempt完整成功；
* R05 OdinANN 停于 pre-update gate；
  -R05 OdinANN 不存在 `ingest_begin`；
  -R05 DiskANN 未启动；
  -R05 CP01/GT preservation 为 pass。

## 6.2 R05 DGAI

要求第 4 节冻结审计通过。

R06 execution manifest 记录：

```text
DGAI_source_run = pilot3_sift10m_w1_r05
DGAI_source_attempt = cp01-05
DGAI_reexecuted = false
```

## 6.3 Frozen inputs

重新验证：

* R02 GT SHA256 `4703d2...2c28`；
* CP01 八个文件 identity；
  -tag 0 active；
  -fixed 1,025-row audit；
  -OdinANN canonical-v6 binaries；
  -OdinANN io_uring identity；
  -OdinANN checkpoint-0 base content/mode；
  -DiskANN binary/base；
  -query、CP00 GT、full corpus；
  -process-identity scan；
  -无 active `dv-w1-*` scope；
  -free space ≥150 GB；
  -R06 targets 不存在。

---

# 7. OdinANN R06 执行

## 7.1 New mutable clone

创建：

```text
formal/pilot3_sift10m_w1_r06/OdinANN/cp01-06
```

重新执行：

* exact capability；
  -content identity；
  -mode identity；
  -0700/0600 normalization；
  -live writable audit；
  -base write-denial audit；
  -atomic publish。

不得复用 R05 OdinANN clone。

## 7.2 Pre-update identity gate

运行：

```text
L=29,46
Tq=1
每点三次
```

使用 `identity-v2`。

Recall 作为观测记录，不以 `[0.950,0.955]` 或 `[0.980,0.985]` 判定。

同时在报告中引用 R05 canonical-v6 观测：

```text
L=29:
0.9510 / 0.9508 / 0.9496

L=46:
0.9798 / 0.9799 / 0.9799
```

R06 新三次结果不得覆盖或替换 R05 数据。

## 7.3 Update 与 correctness

身份门禁通过后执行：

```text
80,000 deletes
80,000 inserts
```

保持：

-原生 async insert/delete；
-live online visibility probe；
-save/publish；
-fresh-process probe；
-active-tag exact audit；
-checkpoint-1 post-query；
-phase I/O；
-base content/mode final audit。

参数与 canonical binary 均不变。

---

# 8. DiskANN stale control

OdinANN 完整通过后执行：

```text
L=29,53
Tq=1
每点三次
```

使用 checkpoint-0 immutable index 与 checkpoint-1 GT。

继续标记：

```text
stale-static negative control
```

不得参与动态 update-throughput 排名。

---

# 9. 组合报告

R06 最终报告由以下独立有效证据组成：

```text
DGAI    → R05 cp01-05
OdinANN → R06 cp01-06
DiskANN → R06 stale-cp00-06
GT      → R02 w1_r02
CP01    → frozen shared CP01
```

报告标题明确写为：

```text
Composed W1 1% Canary Result
```

不能描述为三个系统在单一无中断 controller attempt 中完成。

允许比较：

-同一冻结 trace 下的 update throughput；
-visibility semantics；
-device writes；
-space growth；
-fixed-policy pre/post query stability。

但必须注明 DGAI 和 OdinANN 来自两个严格隔离的串行 continuation attempt，因此该比较仍属于 pilot-level evidence。

---

# 10. Pre-update gate 历史解释

报告中明确区分：

```text
P2B Recall target
```

和：

```text
W1 pre-update infrastructure validation
```

P2B 的 L 选择继续冻结：

```text
DGAI 64/128
OdinANN 29/46
```

废止绝对 Recall clone gate不代表重新选择 L，也不代表把 `0.97993` 宣称为新的 0.98 matched point。

它只表示：

> clone 的正确性由 artifact identity 和执行不变量证明，不能由跨 binary 的狭窄 Recall 区间证明。

checkpoint-1 查询仍称为：

```text
fixed-W0-policy churn stability
```

不得称为 matched-Recall frontier。

---

# 11. 失败规则

R06 任一阶段失败：

-立即停止；
-不启动后续阶段；
-保留全部证据；
-不复用 R06 名称；
-不修改 L；
-不增加正式重复次数；
-不调整 Recall；
-不重新运行 DGAI；
-不进入更高 churn。

---

# 12. 完成后停止

R06 完成后停止，不自动运行：

* 5%/10%/20% replacement；
  -DiskANN rebuild；
  -checkpoint-1 Recall refinement；
  -mixed query/update；
  -W2；
  -DEEP/GIST。

---

# 13. 最终裁决

R05 DGAI 是有效的完整系统结果，应保留并冻结。

R05 OdinANN 的 `0.97993 < 0.98000` 暴露的是门禁定义错误，而不是索引错误。禁止通过新的经验 interval 修补旧 interval。

授权使用基于 exact identity 与执行不变量的 pre-update gate v2，在新的 R06 中仅继续 OdinANN 与 DiskANN，并与 R05 DGAI 组成最终 W1 1% canary 证据。
