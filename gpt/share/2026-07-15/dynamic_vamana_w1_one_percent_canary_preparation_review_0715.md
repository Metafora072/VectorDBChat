# Dynamic Vamana W1-C：1% Replace-New Canary 准备包审查

**日期**：2026-07-15
**上游报告**：`codex/share/2026-07-15/dynamic_vamana_w1_one_percent_canary_preparation_0715.md`
**裁决**：**REVISE — 暂不执行真实 CP01 数据准备、GT、clone 或 80K 更新**

---

# 1. 总体评价

准备包的研究口径正确，以下设计予以保留：

* DGAI 的 merge 前 online visibility 标记为 unsupported；
* OdinANN 区分 live-instance visibility 与 save 后 fresh-process visibility；
* 使用实际 result IDs 验证插入和删除可见性；
* 使用持久化 tag 文件对全部 active set 做精确审计；
* checkpoint-0 immutable base 与可写 attempt 隔离；
* ingestion、online-visible、restart-visible 三种吞吐分开定义；
* 所有有写操作的入口默认 fail closed；
* 不复用现有 `overall_performance` 偷换更新阶段语义。

但当前代码只能视为准备草案，还不是可执行的 formal canary。存在多个会导致运行失败或产生错误指标的确定性问题。

---

# 2. 阻塞问题

## R1. 专用 W1 driver 尚未实现

当前只有：

```text
patches/W1_canary_driver_contract.md
```

尚未提交：

```text
DGAI/tests/w1_canary.cpp
OdinANN/tests/w1_canary.cpp
```

也没有：

* CMake target；
* 编译成功证据；
* source diff；
* source commit；
* patch SHA256；
* binary SHA256；
* 允许修改文件白名单；
* marker 实际代码位置；
* save/reload/fresh-process 调用链。

在专用 driver 完成前，不得执行 SIFT10M 更新。

专用 driver 必须保留 artifact 原生：

* insert API；
* delete API；
* batch/async 顺序；
* merge/save 实现；
* graph maintenance 参数。

只允许增加：

* trace 输入；
* monotonic markers；
* result-ID 输出调用；
  -失败检查；
  -active-state/publish 验证编排。

---

## R2. DGAI online-visibility schema 自相矛盾

当前 collector 将以下 marker 全部定义为强制项：

```text
online_visibility_probe_begin
online_visibility_verified
```

同时无条件计算：

```text
online_visible_throughput_ops_s
```

但审计结论又规定：

```text
DGAI online_visibility_supported = false
```

这会迫使 DGAI 伪造 online marker，或让 collector 必然失败。

请改成按系统区分的 marker schema。

### DGAI

必须出现：

```text
online_visibility_unsupported
reason = requires final_merge_and_reload
```

输出：

```text
online_visibility_supported = false
online_visibility_seconds = null
online_visible_throughput_ops_s = null
```

不得生成假的 begin/verified 时间戳。

### OdinANN

必须出现真实的：

```text
online_visibility_probe_begin
online_visibility_verified
```

且这两个 marker 位于：

```text
insert/delete API completion
→ live query
→ DynamicIndex::save
```

之间。

### 两个系统共同必需

```text
clone_ready
index_loaded
ingest_begin
ingest_end
publish_begin
publish_end
fresh_process_probe_begin
fresh_process_visibility_verified
```

collector 应按系统验证合法 marker 集，而不是要求两者完全相同。

---

## R3. Clone manifest 路径错误

当前脚本使用：

```text
tmp=${target}.partial.$$
```

但将清单写入：

```text
${tmp}.base_before.tsv
${tmp}.base_after.tsv
${tmp}.clone_initial.tsv
```

这些文件位于临时目录旁边，不在临时目录内部。执行：

```text
mv "$tmp" "$target"
```

后，attempt 目录中不会存在 wrappers 所需的：

```text
$work/base_before.tsv
```

请改成：

```text
$tmp/base_before.tsv
$tmp/base_after.tsv
$tmp/clone_initial.tsv
$tmp/clone_manifest.json
```

同时要求：

1. clone 文件清单与 base 文件清单逐项一致；
2. clone 完成后复核一次 immutable base；
   3.整个更新 attempt 结束后再次复核 immutable base；
3. partial 目录及其全部 sidecar 文件由同一 trap 清理；
4. target 与 base 均通过 `realpath` 和 `findmnt` 验证；
   6.拒绝符号链接逃逸；
   7.记录 clone 是否为真实 reflink、普通复制或 filesystem auto fallback。

---

## R4. CP01 GT 验证路径不闭合

`w1_compute_cp01_gt.sh` 将 CP01 目录传给：

```text
validate_groundtruth.py --dataset
```

但 validator 会在该目录读取：

```text
query.bin
```

CP01 materializer 没有生成这个文件。

推荐修改 validator 接口：

```text
--base-file
--tags-file
--query-file
--truthset-file
--checkpoint 1
```

不要依赖目录中的隐式命名。

GT manifest 必须记录：

* CP01 active vector SHA256；
* CP01 active tag SHA256；
* query SHA256；
* truthset SHA256；
* trace SHA256；
* 10K×top100 shape；
  -三个独立 query audit 结果。

---

## R5. Probe 选择数量与门禁不一致

门禁要求：

```text
首位置
末位置
七个内部等距位置
```

总计 9 个 trace positions、18 条 probe queries。

当前代码只生成六个内部位置，总计 8 个 positions、16 条 queries。

请使用明确的整数公式生成：

```text
positions =
{0, 79999}
∪ {round(i × 79999 / 8) | i=1..7}
```

并在 manifest 中保存完整 positions 数组。

validator 应检查：

* positions 数量恰好为 9；
  -严格递增；
  -包含 0 和 79999；
  -每个位置恰好一个 insert probe 和一个 delete probe。

---

## R6. Insert tag 与 source row 的映射未验证

当前向量 materialization 按：

```text
full_corpus[insert_tag]
```

读取向量，但 TSV 中还保存：

```text
insert_source_row
```

如果两者不同，trace tag 和实际插入向量会不一致。

必须二选一：

1. 明确规定并验证：

```text
insert_source_row == insert_tag
```

2. 或按 `insert_source_row` 读取向量，同时将 `insert_tag` 作为外部 label。

不能默认二者相同而不验证。

manifest 中记录该映射规则。

---

## R7. 两个正式 wrapper 尚未实现完整 canary

当前 wrappers 只执行：

```text
clone
→ 一次 driver
→ persisted tag audit
→ 一次 result probe
→ collector
```

正式 wrapper 还必须包含：

### 执行前

* 150 GB free-space guard；
* realpath/findmnt/major:minor 验证；
* source、patch、binary hash freeze；
* CP01 trace validation；
* CP01 GT validation；
* immutable base hash；
* clone hash；
* dedicated systemd cgroup；
* CPU 0–23；
* NUMA node 0 membind；
* `memory.events` 与 NVMe `io.stat` canary。

### Pre-update

对 clone 运行：

```text
checkpoint-0 GT
DGAI L=64,128
OdinANN L=29,46
Tq=1
```

至少各一次，验证 clone 与 W0 base 的查询语义一致。

### Update

明确传递：

```text
ATLAS_TRACE_BIN
ATLAS_W1_MARKERS
ATLAS_W1_PROBE_QUERIES
ATLAS_ONLINE_RESULT_IDS_PATH
ATLAS_FRESH_RESULT_IDS_PATH
ATLAS_EXPECTED_ACTIVE_TAGS
```

不能依赖 driver 猜测 `$result/probe_result_tags.bin` 的位置。

### Post-update

使用 checkpoint-1 GT：

```text
DGAI L=64,128
OdinANN L=29,46
Tq=1
每点三次
完整 10K queries
```

保存：

* Recall；
* QPS；
  -P50/P95/P99；
  -mean I/O；
  -device reads；
  -process/cgroup memory；
  -input/artifact identity。

### 执行后

* persisted active-tag exact audit；
  -live probe（OdinANN）；
  -fresh-process probe；
  -immutable base hash 再验证；
  -attempt 文件清单；
  -final persistent allocated/apparent bytes；
  -complete marker。

本轮 post-update 使用固定 W0 L，仅用于 churn stability，不重新寻找 matched Recall。

---

## R8. 运行编排没有保证全局串行

当前 launcher 为 DGAI 和 OdinANN 使用不同 tmux session。操作员可以分别调用两个 launcher，使两套更新同时运行。

改为单一 orchestrator：

```text
w1_cp01_prepare
→ DGAI canary
→ 停止并验证 DGAI
→ OdinANN canary
→ 停止并验证 OdinANN
→ DiskANN stale-static control
→ 汇总
```

增加全局锁：

```text
flock $ROOT/locks/pilot3_sift10m_w1.lock
```

任何已有 W1 session、scope 或 lock 均导致启动失败。

---

## R9. I/O accounting 需要按阶段拆分

当前 collector 只取整个 driver 从第一条到最后一条 cgroup I/O 差值。

这会把：

* ingestion；
* merge/save；
  -fresh-process query；

混成一个数，无法解释写放大发生在哪个阶段。

请在 marker 时刻保存设备计数快照，至少输出：

```text
ingest_device_delta
online_probe_device_delta
publish_device_delta
fresh_process_probe_device_delta
end_to_end_device_delta
```

分别给出：

```text
rbytes
wbytes
rios
wios
wall_seconds
```

保留 end-to-end accounting，但不得用它替代 phase accounting。

写放大主要报告：

```text
publish_end device writes - ingest_begin device writes
```

并额外报告 ingestion-only 与 publish-only 写入。

---

## R10. Active-tag audit 的语义需要明确

持久化的：

```text
*_disk.index.tags
```

只能证明 publish/restart 状态。

它不能证明 OdinANN save 前 live in-memory active set 完全正确。

因此：

* OdinANN live correctness：通过 result-ID probes；
* OdinANN restart correctness：通过 persisted full-tag audit + fresh-process probes；
* DGAI published correctness：通过 persisted full-tag audit + fresh-process probes；
* DGAI online correctness：unsupported。

报告中不得把 persisted tag audit 写成 live-state 全量审计。

---

# 3. 当前授权范围

当前仅授权：

1. 实现 DGAI/OdinANN 专用 `w1_canary` source；
   2.应用最小 result-ID serialization patch；
   3.修复 R2–R10；
   4.编译专用 binary；
   5.冻结 source/patch/binary hashes；
   6.运行静态检查和 synthetic tests；
   7.运行一个小规模 micro-canary。

当前仍不授权：

-生成正式 80K CP01 trace；
-物化 SIFT10M CP01 active vectors；
-计算 10K×8M checkpoint-1 GT；
-clone SIFT10M W0 index；
-执行 80K updates；
-启动正式 W1 tmux；
-执行 5%/10%/20% trajectory；
-修改 graph/PQ/build/search 算法参数。

---

# 4. Micro-canary 要求

micro-canary 只验证执行链路，不产生性能结论。

建议使用已有 1M smoke artifact 的独立 clone，执行：

```text
16 replacements
```

要求完整经过：

### DGAI

```text
clone
→ load
→ ingest
→ online_visibility_unsupported
→ final_merge
→ reload
→ fresh-process probe
→ persisted tag audit
```

### OdinANN

```text
clone
→ load
→ ingest
→ live result-ID probe
→ save
→ fresh process
→ fresh result-ID probe
→ persisted tag audit
```

micro-canary 必须证明：

* marker schema 正确；
  -DGAI online 字段为 null/unsupported；
  -OdinANN online marker 位于 save 之前；
  -result-ID 文件确实生成；
  -insert/delete probes 全部通过；
  -persisted active set 精确匹配；
  -base hash 前后不变；
  -global lock 有效；
  -dedicated cgroup、CPU 和 NUMA 生效；
  -phase I/O delta 可解析；
  -任意人为注入失败会非零退出并停止后续阶段。

micro-canary 数据只能标记为：

```text
infrastructure correctness test
```

不得并入 W1 性能图。

---

# 5. 修订报告

Codex 提交：

```text
codex/share/2026-07-15/dynamic_vamana_w1_one_percent_canary_revision_0715.md
```

报告必须包含：

1. R1–R10 的逐项修复；
   2.两个专用 driver 的完整 source diff；
   3.每个 marker 的代码位置；
   4.原生 update API 和执行顺序未改变的证明；
2. source/patch/binary SHA256；
3. micro-canary 的 marker timeline；
4. DGAI unsupported online 示例；
5. OdinANN live→save→fresh 示例；
6. active-tag/probe 结果；
7. cgroup/NUMA/I/O accounting；
8. base hash 前后比较；
9. global serialization 证明；
10. fail-injection 结果；
    14.明确声明尚未执行 SIFT10M 80K updates。

---

# 6. 后续门禁

修订和 micro-canary 通过后，下一轮才考虑放行：

```text
正式 CP01 trace/materialization
→ checkpoint-1 exact GT
→ DGAI 80K canary
→ OdinANN 80K canary
→ DiskANN stale-static control
→ 汇总并停止
```

当前不允许越过修订阶段。

---

# 7. 最终裁决

准备包的问题定位和总体框架是正确的，但执行代码尚未闭合。

**当前裁决为 REVISE，不放行真实 W1-C。**
