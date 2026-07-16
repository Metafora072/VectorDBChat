# Dynamic Vamana W1：1% Canary 验收与累计 Churn Trajectory 准备门禁

**日期**：2026-07-16

**上游结果**：

* `codex/share/2026-07-16/dynamic_vamana_w1_r05_dgai_partial_results_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_r06_odinann_partial_results_0716.md`
* `codex/share/2026-07-16/dynamic_vamana_w1_composed_one_percent_canary_r07_results_0716.md`

**裁决**：

* W1 checkpoint-1 1% replace-new canary：**PASS**
* 接受 R05 DGAI、R06 OdinANN 和 R07 DiskANN stale-static control；
* 当前只授权准备 checkpoint-5、checkpoint-10、checkpoint-20 的数据、trace 与 exact GT；
* 暂不授权新的动态系统 clone、update、query 或 stale-control 执行。

---

# 1. 1% Canary 正式验收

## 1.1 DGAI

来源：

```text
pilot3_sift10m_w1_r05 / DGAI / cp01-05
```

有效结果：

```text
ingestion time              = 79.852742 s
replacement throughput      = 1001.844 replacements/s
restart-visible time        = 103.025837 s
restart-visible throughput  = 776.504 replacements/s
```

Correctness：

* active set exact；
* fresh probes 18/18；
* checkpoint-1 post-query 完整；
* immutable base content/mode 未改变；
  -无 OOM、fatal 或 I/O error。

## 1.2 OdinANN

来源：

```text
pilot3_sift10m_w1_r06 / OdinANN / cp01-06
```

有效结果：

```text
ingestion time              = 49.446224 s
replacement throughput      = 1617.919 replacements/s
online-visible time         = 49.449186 s
online-visible throughput   = 1617.822 replacements/s
fresh-visible time          = 147.467815 s
fresh-visible throughput    = 542.491 replacements/s
```

Correctness：

* active set exact；
* online probes 18/18；
* fresh probes 18/18；
  -checkpoint-1 post-query 完整；
* canonical io_uring identity；
  -immutable base content/mode 未改变；
  -无 OOM、fatal 或 I/O error。

## 1.3 DiskANN

来源：

```text
pilot3_sift10m_w1_r07 / DiskANN / stale-cp00-07
```

它是 stale-static negative control，不执行更新。

```text
L=29 → Recall@10 = 0.9360
L=53 → Recall@10 = 0.9628
```

相比 checkpoint-0：

```text
L=29: 0.9516 → 0.9360，下降 0.0156
L=53: 0.9800 → 0.9628，下降 0.0172
```

该结果证明 checkpoint-1 GT 能够捕捉 stale index 退化。

---

# 2. 结果报告术语修正

保留原始 R07 报告，不覆盖或修改原始证据。

新增审计版报告：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_composed_one_percent_canary_r07_audited_0716.md
```

## 2.1 Throughput 单位

当前报告中的：

```text
ops/s
```

实际分母为：

```text
80,000 replacement records
```

每条 replacement 包含：

```text
1 delete + 1 insert
```

因此必须改称：

```text
replacements/s
```

可以附加报告：

```text
primitive mutations/s = 2 × replacements/s
```

但不能只写含义不明确的 `ops/s`。

## 2.2 Persistent growth

明确区分：

```text
apparent persistent growth
allocated persistent growth
```

当前单一 `persistent growth` 不足以说明文件系统实际分配空间。

DGAI 的 `0 B` 只能解释为正式测量口径下的 apparent size delta 为零，不能解释为更新没有产生设备写入。

## 2.3 Tail latency

动态系统报告的是：

```text
P99
```

当前 DiskANN binary报告的是：

```text
P99.9
```

两者不得放在同一 P99 列中进行直接比较。

## 2.4 跨系统解释边界

DGAI 和 OdinANN：

-构建参数不同；
-图度数与 layout 不同；
-I/O engine 不同；
-update 与 publish 语义不同；
-visibility 语义不同。

因此：

```text
OdinANN 比 DGAI 快 1.615×
```

只能作为本次完整系统配置的描述，不能写成某个单独设计机制带来 `1.615×` 收益。

后续 trajectory 的主要判断应采用：

```text
同一系统随 churn 增长的归一化变化
```

包括：

* throughput slope；
  -device bytes/replacement slope；
  -space growth slope；
  -query Recall/QPS/P99 slope；
  -visibility cost slope。

跨系统绝对值作为次要描述。

---

# 3. Trajectory 定义

累计 churn checkpoint 固定为：

| Checkpoint | 累计 replacement 数 | 占 8M active set |
| ---------- | ---------------: | --------------: |
| CP01       |           80,000 |              1% |
| CP05       |          400,000 |              5% |
| CP10       |          800,000 |             10% |
| CP20       |        1,600,000 |             20% |

这些 checkpoint 来自原始实验协议，不根据 CP01 结果临时选择。

每个 replacement 定义为：

```text
delete one original-active tag
insert one insert-pool tag
```

因此 primitive mutation 数为 replacement 数的两倍。

---

# 4. 单一 Master Trace

新增目录：

```text
datasets/sift10m/w1_trajectory/
```

生成一个最大长度为：

```text
1,600,000 replacement records
```

的 master trace。

所有 checkpoint 必须是该 trace 的前缀：

```text
CP01 = master[0:80,000]
CP05 = master[0:400,000]
CP10 = master[0:800,000]
CP20 = master[0:1,600,000]
```

禁止分别独立随机采样 CP05、CP10 和 CP20。

---

# 5. 保留现有 CP01 前缀

现有：

```text
replace_cp01_80k.bin
replace_cp01_80k.tsv
```

已经是冻结实验输入。

master trace 的前 80,000 条 record 必须与现有 CP01：

* record 顺序一致；
  -delete tag 一致；
  -insert tag 一致；
  -record payload 逐字节一致。

由于 binary header 中的总 count 不同，比较时应解析 header 后比较 record payload，不能直接要求整个 master 文件以 CP01 文件字节开头。

输出：

```text
cp01_prefix_validation.json
```

记录：

-旧 CP01 SHA256；
-master trace SHA256；
-record size；
-prefix record count；
-payload comparison result。

---

# 6. Deterministic Extension

在冻结 CP01 后，只从尚未使用的 tag 中生成剩余 1,520,000 条 replacement。

Delete pool：

```text
[0, 8,000,000)
```

Insert pool：

```text
[8,000,000, 10,000,000)
```

要求：

-所有 delete tag 唯一；
-所有 insert tag 唯一；
-delete 与 insert domain 不重叠；
-不再次使用 CP01 已用 tag；
-只删除 checkpoint-0 original-active tag；
-不删除 trajectory 中新插入的 tag。

使用版本固定、可复现的确定性 PRNG，并为 delete/insert 使用 domain-separated stream。

manifest 记录：

* seed；
* PRNG 名称与版本；
  -Python/NumPy 版本；
  -generator script SHA256；
  -existing CP01 input hashes；
  -master output hashes。

不得使用系统时间、线程调度或 unordered-container iteration 影响输出。

---

# 7. Checkpoint Artifact

对 CP05、CP10、CP20 分别生成：

```text
replace_cpXX.bin
replace_cpXX.tsv
active_cpXX.tags.bin
active_cpXX.bin
visibility_probes.bin
visibility_probes.json
checkpoint_manifest.json
```

## 7.1 Active set

每个 checkpoint：

```text
active =
checkpoint-0 active tags
- prefix delete tags
+ prefix insert tags
```

要求：

```text
active cardinality = 8,000,000
```

并满足：

```text
CP20 inserted set ⊃ CP10 inserted set ⊃ CP05 inserted set ⊃ CP01 inserted set

CP20 deleted set  ⊃ CP10 deleted set  ⊃ CP05 deleted set  ⊃ CP01 deleted set
```

Active tag 文件顺序必须明确冻结。

`active_cpXX.bin` 的第 i 行必须严格对应：

```text
active_cpXX.tags.bin[i]
```

中的 tag。

## 7.2 Visibility probes

每个 checkpoint 选择 9 个 trace position：

```text
floor(j × (N - 1) / 8), j = 0...8
```

每个 position 同时生成 delete probe 和 insert probe，共 18 个语义检查。

该选择由 checkpoint 大小决定，不增加经验阈值。

---

# 8. Exact Ground Truth

目录：

```text
groundtruth/sift10m/w1_trajectory/
├── cp05/
├── cp10/
└── cp20/
```

每个 checkpoint 使用已验证的流程：

```text
active vectors
→ location-ID exact top-100
→ validate location truthset
→ active-tag remap
→ validate final tag truthset
```

不得使用 DiskANN tagged-GT 模式。

## 8.1 必须验证

每个 GT：

* shape `10000 × 100`；
  -所有 location ID 在 active-vector row 范围内；
  -所有最终 tag 属于对应 active set；
  -不存在 deleted tag；
  -每行 100 个 ID 唯一；
  -距离 finite；
  -每行距离单调非降；
  -distance block 在 remap 前后逐字节一致；
  -log 中不存在 less-than-K warning；
  -output 通过原子 rename 发布。

## 8.2 Independent audit

每个 checkpoint 独立 brute-force 审计：

```text
query 0
query 17
query 7150
query 9999
```

以及由固定 seed 选出的另外 32 个 query。

共 36 个 query。

记录：

-完整 top-100 ID；
-距离；
-与正式 GT 的逐项比较；
-tag 0 在该 checkpoint 的 active/deleted 状态。

不得假定 tag 0 永远 active，也不得重新把 tag 0 当成 sentinel。

---

# 9. Cross-checkpoint Invariants

新增：

```text
trajectory_validation.json
```

必须验证：

1. checkpoint record 是 master trace prefix；
2. CP01 与历史 trace 完全一致；
3. CP05、CP10、CP20 active cardinality 均为 8M；
4. delete/insert sets 严格嵌套；
5. active set 差分与 trace prefix 完全一致；
6. active-vector row/tag mapping 正确；
7. probe specification 与 checkpoint prefix 一致；
8. GT tag 仅来自对应 active set；
   9.三个 checkpoint 不共享可写文件；
   10.所有 output hashes 已冻结。

---

# 10. 资源记录

CP05、CP10、CP20 的：

* trace generation；
  -active-vector materialization；
  -exact GT computation；

分别在独立 cgroup 中记录：

* wall time；
  -peak process-tree RSS；
  -cgroup memory peak；
  -memory.events；
  -NVMe read/write；
  -apparent/allocated output bytes。

这些属于 preparation，不与动态系统更新成本比较。

---

# 11. 唯一 Preparation Orchestrator

新增唯一入口：

```text
run_w1_trajectory_preparation.sh
```

顺序：

```text
acquire global flock
→ verify CP01 frozen input
→ generate deterministic master trace
→ validate CP01 prefix
→ derive CP05 artifacts
→ validate CP05
→ compute/validate CP05 GT
→ derive CP10 artifacts
→ validate CP10
→ compute/validate CP10 GT
→ derive CP20 artifacts
→ validate CP20
→ compute/validate CP20 GT
→ cross-checkpoint validation
→ preparation report
→ stop
```

任一阶段失败：

-立即停止；
-保留失败 attempt；
-不执行后续 checkpoint；
-不自动重试；
-不更改 seed；
-不覆盖已有目录；
-不启动任何索引更新。

---

# 12. 输出目录

机器证据：

```text
results/pilot3_sift10m_w1_trajectory_prep/
```

报告：

```text
codex/share/2026-07-16/
dynamic_vamana_w1_trajectory_preparation_results_0716.md
```

报告至少包含：

* master trace identity；
* CP01 prefix proof；
  -CP05/10/20 counts；
  -active-set hashes；
  -active-vector hashes；
  -probe definitions；
  -GT hashes；
  -36-query audit；
  -cross-checkpoint invariants；
  -resource consumption；
  -free-space remaining。

---

# 13. 当前禁止执行

本轮不授权：

-创建 DGAI/OdinANN trajectory clone；
-运行 CP05/CP10/CP20 update；
-运行任何 checkpoint query；
-运行 DiskANN stale control；
-重跑 CP01；
-更改 W0 L；
-Recall refinement；
-mixed query/update；
-DiskANN rebuild；
-W2；
-DEEP/GIST。

---

# 14. 下一轮计划边界

Preparation 通过后，再单独审议累计 trajectory 执行。

后续执行应以：

```text
CP00 → CP01 → CP05 → CP10 → CP20
```

的单一 cumulative clone 为候选方案，并在每个 checkpoint形成不可变 evidence boundary。

本轮不提前启动该阶段。

---

# 15. 最终裁决

W1 1% composed canary 正式通过。

当前数据已经建立了：

-动态系统在 1% churn 下维持固定策略 Recall；
-stale static index 出现明确退化；
-DGAI 与 OdinANN 在 ingestion、visibility、device writes 和 persistent layout 之间存在系统级权衡。

单点数据不足以判断这些成本随 churn 的增长规律。

授权只准备 CP05、CP10、CP20 的嵌套 trace、active sets 和 exact GT，为下一轮累计 trajectory 提供冻结输入。
