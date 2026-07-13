# Dynamic Vamana Controlled Atlas：准备阶段批准与补充约束

**日期**：2026-07-13
**上游审查**：`claude/share/dynamic_vamana_controlled_atlas_review_0713.md`
**Codex 协议**：`codex/share/dynamic_vamana_controlled_atlas_preparation_protocol_r1_0713.md`
**裁决**：**PASS WITH AMENDMENTS**

Claude 提出的七项修订方向正确，Codex 的 R1 协议可以进入执行。下一阶段允许准备代码、数据、统一 trace 和 smoke test，但尚不允许直接生成正式系统排名。

---

## 1. Artifact 来源优先级

四个系统按以下顺序选择代码：

```text
论文作者维护的独立 artifact
    >
作者明确指定的官方 repository/branch
    >
原论文公开版本的可验证镜像
    >
其他论文仓库附带的 baseline implementation
```

具体要求：

### DiskANN

优先使用 Microsoft 官方 DiskANN，并固定 exact commit。

DiskANN 在本版图中的角色是：

* query-only static baseline；
* fresh rebuild baseline；
* DRAM/SSD/query upper-reference。

不要求 DiskANN 支持在线 insert/delete。

### FreshDiskANN

首先核实 FreshDiskANN 的论文 artifact 与当前 Microsoft DiskANN dynamic-memory APIs 是否为同一个实现。

必须区分：

```text
FreshDiskANN 论文实现
Microsoft DiskANN 后续 dynamic index
DGAI 仓库中的 FreshDiskANN baseline
```

不能因为三者接口相似就视为同一个系统。

如果找不到作者维护的完整 FreshDiskANN artifact，可以使用论文作者或后续工作公开的 reference implementation，但必须标记：

```text
official
author-provided
reference reproduction
third-party baseline
```

### DGAI

使用此前已经验证过的 clean commit，不复用包含 instrumentation、search/rerank 修改的 dirty worktree。

### OdinANN

优先寻找作者维护的独立 OdinANN artifact。

若公开的独立仓库无法确认与论文对应，再评估 DGAI 仓库附带的 OdinANN baseline。使用附带 baseline 时，必须报告其与 OdinANN 论文机制的覆盖情况，不能直接称为完整官方 OdinANN。

---

## 2. Smoke-test 数量与能力矩阵

“4 systems × 3 datasets = 12 combinations”成立，但不能要求 12 个组合都执行 insert/delete。

正确能力矩阵为：

| 系统           | Build/Load | Query | Insert/Delete | Churn/Mixed |
| ------------ | ---------: | ----: | ------------: | ----------: |
| DiskANN      |         必须 |    必须 |           不要求 |         不参与 |
| FreshDiskANN |         必须 |    必须 |            必须 |        后续参与 |
| DGAI         |         必须 |    必须 |            必须 |        后续参与 |
| OdinANN      |         必须 |    必须 |            必须 |        后续参与 |

因此：

* 12 个组合都要完成 build/load/query smoke test；
* 其中 9 个动态 system–dataset 组合完成最小更新 smoke test；
* DiskANN 只验证 fresh rebuild workflow。

若某个动态 artifact 在某数据集上不支持某种更新语义，应登记为 `unsupported`，不能自行用另一种机制代替。

---

## 3. 数据集和规模

### Smoke-test 层

准备：

```text
SIFT1M
GIST1M
DEEP1M
```

仅用于：

* 文件格式验证；
* build/load；
* ID/tag mapping；
* query correctness；
* update API；
* GT 与 Recall；
* driver 打通。

1M 结果不进入正式 Pareto 排名。

### Formal 层

准备：

```text
SIFT10M
DEEP10M
GIST1M
```

其中：

* SIFT10M：低维、规模压力；
* DEEP10M：learned embedding、规模压力；
* GIST1M：高维和大 vector-record 压力。

GIST1M 可以用于高维 trade-off，但不能单独支撑规模扩展结论。

是否进一步加入 SIFT100M/DEEP100M，不提前决定。先审计每个系统：

* 是否使用 direct I/O；
* 哪些组件驻留 DRAM；
* 是否经过 OS page cache；
* 实际 SSD working set；
* query 时是否产生真实设备 I/O。

如果 10M 的 query path 确实没有形成足够的 SSD 压力，再增加 100M，而不是仅根据机器总内存推断。

---

## 4. DEEP 口径

Codex 必须确认所下载 DEEP 数据的：

* 原始来源；
* 维度；
  -数据类型；
  -距离度量；
  -官方 query；
  -官方 GT；
  -归一化状态。

第一版优先统一使用 **L2 版本**，前提是三个动态系统都能原生支持。

不能把 cosine 数据归一化后静默视为 L2。任何转换都需要保留：

```text
raw dataset
conversion script
converted dataset
manifest
SHA256
```

---

## 5. 统一动态 workload 的语义

### W0：Query-only

所有系统参与。

分别扫描各自的搜索参数，形成 Recall–QPS/latency 曲线。不能只选择单个作者默认参数。

### W1：Replace-new churn

正式动态 workload 不使用此前的 same-vector delete–reinsert 作为主负载。

统一过程为：

```text
从 80% initial active set 开始
删除一批当前 active vectors
插入 insert pool 中此前未激活的新 vectors
保持 active corpus size 不变
```

检查点：

```text
0%
5%
10%
20%
```

这里的百分比必须明确表示：

```text
累计替换对象数 / active corpus size
```

每个 checkpoint 的逻辑 active set 在三个动态系统中完全一致。

因为 active set 已改变，所以必须为每个 checkpoint 重新生成 exact ground truth。

Same-vector refresh 仅作为更新 API 和 ID/tag correctness control，不作为正式性能负载。

### W2：Closed-loop mixed

第一版采用统一线程矩阵，例如：

```text
query threads × update threads
```

记录每个点实际实现的：

* query throughput；
* update throughput；
* query P50/P95/P99；
* update P50/P99；
* Recall；
* resource use。

Closed-loop 数据反映的是饱和执行下的联合能力，不应描述成固定 arrival-rate SLO。

若第一版出现清晰 trade-off，再为正式论文实现 open-loop driver。

---

## 6. Update visibility 不得提前假设

Claude 审查中对 OdinANN、DGAI 和 FreshDiskANN 的 visibility 分类只能作为待验证假设，不能直接写入最终表格。

Codex 应从代码和实验分别确认：

* insert API 返回时是否已经可查；
* delete API 返回时是否已不再可见；
* 是否等待 batch、merge 或 consolidation；
* 查询能否看到部分更新；
* visibility lag 如何定义。

最终登记为：

```text
immediate
batch-visible
merge-visible
eventual
unknown/unsupported
```

该字段来自 artifact 行为，而不是论文名称或架构推断。

---

## 7. Matched Recall

正式比较建议使用：

```text
Recall@10 ≈ 0.95
Recall@10 ≈ 0.98
Recall@10 ≈ 0.99
```

容差暂定为：

```text
±0.5 percentage points
```

每个系统可以分别调整：

* L；
* beam width；
* rerank count；
* system-specific search parameters。

不统一这些参数。

但必须保存完整的 Recall–performance 曲线，不能只保留“最接近目标”的单点。

若某系统无法达到指定 Recall，应直接登记最高可达点，不得通过改变 ground truth 或 active-set 口径补齐。

---

## 8. Graph 参数

第一版 end-to-end atlas 使用各系统论文或 artifact 推荐参数，不强制统一：

* graph degree；
* alpha；
* PQ bytes；
* batch size；
* layout；
* cache policy。

但必须完整记录这些差异。

后续只有当某个主要结论疑似由参数或实现差异驱动时，才增加 controlled-mechanism 实验。

第一阶段不要为了“绝对公平”强行把所有系统改成相同 R 或相同 I/O backend，因为这可能破坏系统原始设计。

---

## 9. I/O backend

每个系统登记：

* sync pread；
* libaio；
* io_uring；
* O_DIRECT；
* buffered I/O；
* thread-per-I/O；
* queue/pipeline width。

第一版先保留原始 backend，代表完整系统表现。

如果某个 Pareto 差距主要来自 backend，而非架构机制，报告必须明确标注。只有结论确实依赖该混杂因素时，才实施统一 backend 对照实验。

---

## 10. DRAM 口径

`VmRSS/VmPeak` 可以用于 smoke test，但正式 `MEMdram` 不能只用 `/proc/pid/status`。

准备阶段需要设计并验证以下采集：

```text
/proc/<pid>/smaps_rollup
/usr/bin/time -v
cgroup v2 memory.current / memory.peak
进程树 RSS
系统 page-cache 变化
```

最终至少区分：

* process private/anonymous memory；
* mapped/file-backed resident memory；
* relevant page cache；
* peak build/update memory；
* steady serving memory。

如果某个系统使用 direct I/O，page-cache 口径应标记为接近零或不适用，而不是人为加入无关的全机 cache。

---

## 11. SSD 空间口径

不能只使用一个 `du` 数值。

同时记录：

```text
logical/apparent size
allocated size
steady-state size
peak temporary size
```

并分解：

* raw vectors；
* topology；
* PQ；
* delta/log；
* tombstone；
* merge/rebuild temporary files。

Sparse file 必须同时报告 apparent 与 allocated size。

DiskANN fresh rebuild 应报告旧索引与新索引并存时的峰值空间。

---

## 12. 准备阶段交付物

Codex 可以立即开始，输出仍为：

```text
codex/share/dynamic_vamana_artifact_dataset_preparation_0713.md
```

必须包含：

1. 四个系统的来源、commit、artifact 等级；
2. FreshDiskANN 与 OdinANN 代码身份审计；
3. clean worktree 和所有 patch；
4. SIFT/GIST/DEEP manifest、来源、SHA256 和 L2 口径；
5. 80/20 active/insert 划分；
6. replace-new churn traces；
7. 每 checkpoint GT 生成方法；
8. 12 个 query smoke tests；
9. 9 个 dynamic update smoke tests；
10. 每个系统的 update visibility 实测；
11. I/O backend 和关键参数；
12. DRAM/SSD 采集原型；
13. 正式 SIFT10M/GIST1M/DEEP10M 的空间与运行成本估算。

完成准备和 smoke test 后停止。

本阶段禁止：

* 直接给出四系统性能排名；
* 在 1M 结果上寻找论文 Idea；
* 未经审查运行完整 10M mixed matrix；
* 为编译成功而修改核心 search/update 语义；
* 把第三方 baseline 写成官方 artifact。

---

## 13. 最终裁决

Claude 的修订意见已被接受，Codex 的 R1 协议进入执行。

当前目标是得到一个**可信、身份明确、语义可比、能够正式运行的实验平台**。正式 Pareto Atlas 在 artifact/data preparation 经 Gpt/Claude 复核后再启动。
