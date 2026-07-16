# Dynamic Vamana W1：CP05 累计 Trajectory 执行门禁

**日期**：2026-07-16

**上游证据**：

* `codex/share/2026-07-16/dynamic_vamana_w1_composed_one_percent_canary_r07_audited_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_trajectory_preparation_results_0716.md`

**裁决**：

* Trajectory preparation：**PASS**
* 授权验证累计状态机并执行正式 `CP00 → CP01 → CP05`
* 暂不授权 CP10、CP20
* 暂不授权 mixed workload、DiskANN rebuild、Recall refinement、W2、DEEP 或 GIST

---

# 1. 本阶段研究问题

本阶段需要回答：

> 当同一个动态索引连续经历 1% 和 5% 累计 replacement 时，更新成本、可见性成本、设备 I/O、持久化空间和固定查询策略质量如何变化？

正式路径必须让同一个 private clone 依次经历：

```text
checkpoint-0
→ 应用 master[0:80K]
→ checkpoint-1
→ 应用 master[80K:400K]
→ checkpoint-5
```

禁止采用以下替代方式：

```text
从 CP00 独立 clone
→ 一次性应用完整 CP05 400K prefix
```

该方式只能测量独立批量更新，无法验证 repeated merge/save 和累计维护状态。

也禁止在已经位于 CP01 的 clone 上重新应用完整 400K prefix，否则前 80K replacement 会被重复执行。

---

# 2. 增量 Trace

从冻结 master trace 确定性派生：

```text
delta_cp00_to_cp01.bin = master[0:80,000]
delta_cp01_to_cp05.bin = master[80,000:400,000]
```

对应 replacement 数：

| Stage     | Incremental replacements | Primitive mutations | Cumulative replacements |
| --------- | -----------------------: | ------------------: | ----------------------: |
| CP00→CP01 |                   80,000 |             160,000 |                  80,000 |
| CP01→CP05 |                  320,000 |             640,000 |                 400,000 |

新增目录：

```text
datasets/sift10m/w1_trajectory/execution_deltas/
```

每个 delta 输出：

```text
delta_*.bin
delta_*.tsv
delta_manifest.json
delta_visibility_probes.bin
delta_visibility_probes.json
```

要求：

1. 两个 delta 顺序连接后逐条等于 CP05 400K prefix；
2. 第一段逐条等于历史 CP01 trace；
3. 两段 delete sets 不相交；
4. 两段 insert sets 不相交；
5. 不产生新的随机采样；
6. `insert_source_row == insert_tag`；
7. 文件只读、inode 独立、SHA256 冻结。

---

# 3. Probe 语义

每个 stage 同时执行两组 probe。

## 3.1 Stage-local probes

在当前 delta 的局部位置：

```text
floor(j × (Ndelta - 1) / 8), j=0...8
```

生成 9 个 delete 和 9 个 insert probe。

它们验证本轮增量确实生效。

## 3.2 Checkpoint-global probes

继续使用已冻结的：

```text
CP01 visibility probes
CP05 visibility probes
```

它们验证整个累计状态，而不只验证最新增量。

每个 checkpoint 完成后：

* DGAI fresh probes：local 18/18、global 18/18；
* OdinANN online probes：local 18/18、global 18/18；
* OdinANN fresh probes：local 18/18、global 18/18。

任何 probe 失败立即停止。

---

# 4. 共用累计状态机

新增唯一共用 runner：

```text
w1_run_cumulative_trajectory.sh
```

DGAI 与 OdinANN 使用同一控制流程：

```text
clone CP00 once
→ CP00 query
→ apply CP01 delta
→ publish
→ checkpoint-1 correctness
→ CP01 query
→ reopen persisted CP01 state
→ apply CP05 delta
→ publish
→ checkpoint-5 correctness
→ CP05 query
→ freeze final CP05 clone
```

系统间只允许以下语义差异：

## DGAI

```text
online visibility = unsupported
publish 后 fresh-process visibility required
```

## OdinANN

```text
update 后 live online visibility required
save 后 fresh-process visibility required
IO engine = io_uring
```

不得为两个系统维护两份重复的累计 orchestrator。

---

# 5. 每个 Stage 使用新进程

CP01 和 CP05 update stage 必须由两个独立 worker process 执行。

CP05 worker 必须：

1. 从 CP01 已发布的 index realpath 加载；
2. 验证 CP01 persisted active tags；
3. 只读取 320K delta；
4. 不读取或应用完整 400K prefix；
5. 使用同一个 private clone realpath；
6. 完成后发布 CP05。

这验证：

* repeated load；
* repeated merge/save；
* persisted state 可作为下一轮 update 输入；
  -前一轮 active-set 状态没有只存在于内存中。

---

# 6. Sequential-state 基础设施回放

正式 SIFT10M 前，使用与正式完全相同的 runner 做一次 1M structural replay。

累计 record 数固定为：

```text
stage 1 cumulative = 16
stage 2 cumulative = 80
stage 2 delta      = 64
```

选择原因是：

-复用已验证的 16-op replay 基础；
-保持 CP01→CP05 的 5× cumulative ratio；
-仅验证重复状态转换，不解释性能。

两个系统均须验证：

-同一个 clone；
-两次独立 update worker；
-两次 publish；
-两次 fresh reload；
-两级 active set exact；
-stage-local/global probes；
-base content/mode 不变；
-无 OOM、fatal、I/O error；
-最终 clone 可冻结。

回放失败时不得启动 SIFT10M。

---

# 7. 正式目录

结果根：

```text
results/pilot3_sift10m_w1_cp05_trajectory/
```

索引根：

```text
formal/pilot3_sift10m_w1_cp05_trajectory/
```

Attempts：

```text
DGAI/trajectory-cp05-01
OdinANN/trajectory-cp05-01
DiskANN/stale-cp05-01
```

每个动态 attempt 只有一次 initial clone，不得在 CP01→CP05 之间创建第二个 clone。

---

# 8. 查询策略

## 8.1 DGAI

```text
L = 64, 128
Tq = 1
每个 checkpoint、每个 L 三次
```

## 8.2 OdinANN

```text
L = 29, 46
Tq = 1
每个 checkpoint、每个 L 三次
```

Checkpoint GT：

| 状态   | Ground truth         |
| ---- | -------------------- |
| CP00 | 冻结 CP00 GT           |
| CP01 | R02 `gt_cp01`        |
| CP05 | trajectory `gt_cp05` |

使用 `identity-v2`：

* binary/index/query/GT/active-tag identity；
  -完整 result shape；
  -所有 IDs active；
  -无 sentinel；
  -每行 top-10 无重复；
  -finite metrics；
  -NVMe reads > 0；
  -无 OOM、fatal、I/O error。

Recall 只作为观测，不设置经验 acceptance interval。

---

# 9. CP01 Replay 的解释

新累计 run 中的 CP01 是状态机必需阶段。

它不得覆盖或替代已经接受的：

```text
R05 DGAI CP01
R06 OdinANN CP01
```

报告需要并列展示：

```text
accepted CP01 result
trajectory CP01 replay
```

比较：

* Recall；
  -QPS；
  -P99；
  -mean I/O；
  -replacement throughput；
  -device bytes/replacement；
  -space growth；
  -visibility time。

这些差异仅作 reproducibility 观测，不设置事后性能阈值。

Correctness 和 artifact identity仍是硬门禁。

---

# 10. Update 与 I/O Accounting

每个 stage 独立记录：

```text
trace load
ingest
online probe
publish
fresh probe
post-query
```

Ingestion 区间继续定义为：

```text
首个原生 insert/delete API
→ 最后一个原生 insert/delete API 完成
```

不包含：

* trace parsing；
  -vector loading；
  -index load；
  -publish；
  -query；
  -probe；
  -clone。

每个 stage 报告：

* incremental replacements；
  -replacements/s；
  -primitive mutations/s；
  -ingest read/write bytes；
  -publish read/write bytes；
  -end-to-end read/write bytes；
  -bytes per incremental replacement；
  -apparent persistent delta；
  -allocated persistent delta；
  -peak RSS；
  -cgroup memory peak；
  -visibility time 与 throughput。

另外报告 CP00→CP05 的 cumulative totals。

---

# 11. Checkpoint Evidence Boundary

CP01 完成后生成只读证据：

```text
cp01_state_content_manifest.tsv
cp01_state_mode_manifest.tsv
cp01_active_audit.json
cp01_query_summary.tsv
cp01_checkpoint_evidence.json
```

随后索引仍可由 CP05 worker修改。

因此 CP01 manifest 表示当时状态的加密摘要，不声称保留了可直接恢复的 CP01 index snapshot。

CP05 完成后：

1. 停止所有 update/query process；
   2.生成 final content/mode manifest；
   3.验证 active set 等于 prepared CP05；
   4.将整个 private index tree 转换为 immutable policy：

```text
directories = 0555
regular files = 0444
```

5.验证 owner 写入和目录创建均失败；
6.写入：

```text
IMMUTABLE_TRAJECTORY_CP05_OK
```

未来 CP10 必须从该冻结 CP05 base 创建新的 mutable clone，不能直接解冻或续写本轮 attempt。

---

# 12. Base 与输入保护

全过程必须反复验证：

* CP00 immutable base content/mode 不变；
* master trace 不变；
* CP01/CP05 trace 不变；
* CP01/CP05 active artifacts 不变；
* CP01/CP05 GT 不变；
  -full corpus/query 不变。

动态系统只能写各自 capability-bound private clone 和结果目录。

---

# 13. DiskANN CP05 Stale Control

动态系统全部通过后，执行：

```text
checkpoint-0 immutable DiskANN index
vs.
checkpoint-5 exact GT
```

固定参数：

```text
L = 29, 53
Tq = 1
每点三次
```

继续使用 R07 冻结的：

* binary；
  -runtime manifest；
  -loader environment；
  -CPU 0–23；
  -NUMA node 0；
  -systemd resource accounting。

报告 CP00、CP01、CP05 的 stale Recall trajectory。

DiskANN 仍是 stale-static negative control，不参与 update throughput 排名。

---

# 14. 执行顺序

唯一正式顺序：

```text
acquire global flock
→ trajectory/input preflight
→ derive and freeze execution deltas
→ sequential-state 1M replay
→ DGAI cumulative CP00→CP01→CP05
→ DGAI complete validation and CP05 freeze
→ OdinANN cumulative CP00→CP01→CP05
→ OdinANN complete validation and CP05 freeze
→ DiskANN CP05 stale control
→ final preservation audit
→ report
→ stop
```

任一阶段失败：

-立即停止；
-不启动后续系统；
-保留当前 attempt；
-不自动重试；
-不更换参数；
-不续写失败 clone；
-不进入 CP10/CP20。

已经完整通过的 system attempt可以作为独立候选证据，但须由下一轮审议决定是否接受。

---

# 15. 输出

报告：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_cp05_cumulative_trajectory_results_0716.md
```

机器目录：

```text
results/pilot3_sift10m_w1_cp05_trajectory/
├── execution_manifest.json
├── preflight/
├── replay/
├── DGAI/trajectory-cp05-01/
├── OdinANN/trajectory-cp05-01/
├── DiskANN/stale-cp05-01/
├── summary.tsv
└── trajectory_summary.json
```

报告必须明确区分：

* incremental stage cost；
  -cumulative checkpoint state；
  -accepted CP01；
  -trajectory CP01 replay；
  -CP05 result；
  -DiskANN stale trajectory。

---

# 16. 当前禁止执行

本轮不授权：

* CP10 update；
  -CP20 update；
  -直接应用完整 CP05 prefix 到 CP01 clone；
  -为每个 checkpoint 从 CP00 创建独立动态 clone；
  -DiskANN CP05 rebuild；
  -checkpoint-specific L refinement；
  -mixed query/update；
  -W2；
  -DEEP/GIST。

---

# 17. 最终裁决

Trajectory preparation 正式通过。

下一轮先验证动态索引的第二次累计维护：

```text
CP00 → CP01 → CP05
```

只有 CP05 累计状态、重复 merge/save、correctness、query stability、I/O 和 space growth 全部通过后，才审议从冻结 CP05 base继续 CP10 与 CP20。
