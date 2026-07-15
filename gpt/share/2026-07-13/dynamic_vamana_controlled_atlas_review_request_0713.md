# Dynamic Vamana Controlled Atlas：审查与环境准备请求

**日期**：2026-07-13
**当前阶段**：Reviewer gate → artifact/data preparation
**研究对象**：

* DiskANN
* FreshDiskANN
* DGAI
* OdinANN

**第一批数据集**：

* SIFT
* GIST
* DEEP

其中此前口头所称的 `Dist` 应按 `GIST` 处理。

---

# 1. 本阶段目标

我们不再使用不同论文中的绝对性能数字直接比较系统。

第一版版图必须来自：

```text
相同机器
+ 相同 SSD
+ 相同数据划分
+ 相同 query/update trace
+ 相同 ground truth
+ matched Recall
+ 统一资源统计口径
```

下实际运行四个系统得到的数据。

本阶段分两步：

1. Claude 审查整体方法、系统选择、数据集选择与公平性约束；
2. 审查通过后，Codex 准备四个工作的代码、三类数据集和统一实验目录。

本轮不要求立即完成完整 benchmark。

---

# 2. 请 Claude 优先审查的问题

## 2.1 系统范围是否合理

第一版只纳入：

* DiskANN：静态 Vamana 查询上界与 full-rebuild baseline；
* FreshDiskANN：动态耦合式、批量更新与 consolidation 路线；
* DGAI：topology/vector 解耦路线；
* OdinANN：耦合式直接更新或增量维护路线。

DecoupleVS 因未公开 artifact，不进入 controlled benchmark。

请审查：

* 四个系统是否足以形成第一版动态 Vamana 架构版图；
* 是否遗漏了一个必须加入、且已有可靠 artifact 的直接基线；
* FreshDiskANN、DGAI、OdinANN 使用的实际代码版本是否语义可比；
* DGAI 仓库中附带的 OdinANN/FreshDiskANN baseline 与各自独立官方 artifact，应该选择哪一个。

---

## 2.2 数据集是否合理

第一版拟使用：

```text
SIFT
GIST
DEEP
```

第一阶段规模：

```text
SIFT1M
GIST1M
DEEP1M
```

正式版候选规模：

```text
SIFT10M
GIST1M
DEEP10M
```

必要时再增加：

```text
SIFT100M 或 DEEP100M
```

请审查：

* 三个数据集是否覆盖了足够不同的维度、向量大小和分布；
* GIST1M 是否已足以暴露耦合与解耦的 record-size 差异；
* 10M 是否适合作为第一轮正式比较，而不会因规模太小掩盖 SSD 行为；
* 是否应以 BIGANN、ANN-Benchmarks 或作者脚本中的标准版本为准；
* metric 是 L2 还是 inner product，是否会导致部分系统额外改造。

---

## 2.3 统一比较口径是否正确

建议比较原则：

### 必须相同

* logical dataset；
* initial active set；
* insert/delete/update trace；
* query set；
* ground truth；
* NVMe device；
* CPU/NUMA binding；
  -运行时长；
* cache warm/cold 定义；
  -更新可见性检查；
* target Recall。

### 不强制相同

* search L；
* beam width；
* system-specific batch size；
  -内部布局；
* graph/update 专属参数。

系统应分别调参达到 matched Recall，而不是强制使用相同 L。

请审查：

* 是否应统一 graph degree `R`、build alpha 和 PQ code length；
* 若某系统依赖特殊 graph/layout，统一 base graph 是否反而不公平；
* end-to-end system mode 与 controlled-mechanism mode 是否都需要；
* 第一版应优先执行哪一种。

---

## 2.4 Workload 是否足够

第一版拟包含：

1. 纯查询；
2. 纯插入；
3. 纯删除；
4. delete–insert churn；
5. query/update mixed workload；
6. merge、consolidation、repair 等后台维护窗口。

Mixed workload 优先使用 open-loop 到达率：

```text
固定 query arrival rate
逐步增加 update arrival rate
```

而不是只通过固定查询线程与更新线程做 closed-loop 饱和测试。

请审查：

* workload 是否过宽，需要第一版进一步收缩；
* open-loop mixed workload 对四个 artifact 是否现实；
* 不同系统的 immediate、batch、eventual visibility 如何公平处理；
* DiskANN 应只作为 query/rebuild baseline，还是还有其他合理角色；
* churn checkpoint 建议使用哪些比例。

---

## 2.5 指标是否遗漏

至少记录：

### Query

* QPS；
* P50/P95/P99；
* Recall@10；
* pages/query；
* bytes/query；
* CPU/query。

### Update

* insert/delete/replace throughput；
* P50/P95/P99；
* read/write amplification；
* visibility lag。

### Resource

* steady RSS；
* peak RSS；
* page cache；
* steady SSD size；
* peak SSD size；
* temporary merge/rebuild space。

### Maintenance and stability

* merge/consolidation time；
* query P99 during maintenance；
* update stalls；
* Recall after churn；
* freshness；
* SSD bandwidth/IOPS/QD。

请审查：

* 哪些指标在第一版必须测；
* 哪些可以延后；
* OS page cache、buffer cache、anonymous memory 应如何统一计入；
* peak resource 应从进程、cgroup 还是整机口径采集。

---

# 3. Claude 的预期输出

请输出：

```text
claude/share/dynamic_vamana_controlled_atlas_review_0713.md
```

必须包含：

1. `PASS`、`REVISE` 或 `STOP`；
2. 系统范围裁决；
3. 数据集与规模裁决；
4. artifact 版本选择建议；
5. workload 收缩或补充；
6. 公平性风险；
7. 第一阶段必须采集的指标；
8. Codex 环境准备清单；
9. 是否允许进入代码与数据准备。

若只是可修正的问题，请给出 `REVISE` 和明确修订项，不要因为尚未跑数据就否定整个 Pareto Atlas 方法。

---

# 4. Claude 通过后 Codex 的任务

只有 Claude 明确给出 `PASS`，或 PZ/Gpt 接受其修订后，Codex 才开始。

## 4.1 准备四个代码基线

为每个系统建立独立、干净、可追踪的 worktree：

```text
DiskANN
FreshDiskANN
DGAI
OdinANN
```

记录：

* repository；
* exact commit SHA；
* branch/tag；
  -论文对应关系；
* license；
* build dependencies；
* compiler/CMake version；
  -作者默认参数；
  -代码修改；
  -是否可原样编译；
  -是否需要兼容性 patch。

禁止直接使用此前包含大量 instrumentation 或未提交改动的 dirty worktree。

所有兼容性 patch 必须：

* 单独保存；
* 最小化；
* 有明确说明；
* 不改变核心搜索或更新语义。

---

## 4.2 下载与准备数据集

准备：

```text
SIFT1M
GIST1M
DEEP1M
```

并登记：

* 官方或论文常用下载来源；
  -文件格式；
  -向量数量；
  -维度；
  -distance metric；
  -query 数量；
  -ground-truth 格式；
  -SHA256；
  -解压后大小；
  -license/usage note。

所有大文件放在项目 NVMe，不放系统盘。

统一转换出 canonical 格式：

```text
base vectors
query vectors
ground truth
metadata manifest
```

不要覆盖原始下载文件。

---

## 4.3 统一数据划分

在每个数据集上生成确定性的：

```text
initial base set
insert pool
delete trace
replace/churn trace
query order
```

记录随机种子和 ID 列表。

第一版建议：

```text
80% initial base
20% insert pool
```

但若某个官方数据集已有更合理的动态划分，可在报告中提出并说明。

所有系统必须使用同一逻辑 trace。

---

## 4.4 建立统一目录

建议：

```text
dynamic_vamana_atlas/
├── repos/
│   ├── diskann/
│   ├── freshdiskann/
│   ├── dgai/
│   └── odinann/
├── datasets/
│   ├── sift1m/
│   ├── gist1m/
│   └── deep1m/
├── manifests/
├── traces/
├── builds/
├── indexes/
├── runs/
└── scripts/
```

系统盘只保留：

* Git worktree；
  -小型构建文件；
  -脚本；
  -报告。

数据、索引、raw log 和结果放项目 NVMe。

---

## 4.5 Artifact smoke test

每个“系统 × 数据集”至少验证：

* 可以构建或加载索引；
* 可以执行查询；
* 可以输出 Recall；
* 动态系统可以执行最小 insert/delete；
* query result ID 映射正确；
* ground truth 口径正确；
  -索引与进程能正常退出。

本阶段只做最小 smoke test，不做正式 QPS/P99 排名。

---

# 5. Codex 的预期输出

代码和数据准备完成后输出：

```text
codex/share/dynamic_vamana_artifact_dataset_preparation_0713.md
```

必须包含：

1. 四个仓库与 commit；
2. artifact 来源与可信度；
   3.所有本地 patch；
   4.三类数据集 manifest；
3. SHA256 与路径；
   6.统一数据划分；
   7.每个系统的 build 状态；
   8.12 个 system–dataset 组合的 smoke-test 状态；
   9.失败组合及原因；
   10.预计正式实验空间、时间和资源成本；
   11.可直接执行的下一阶段 benchmark plan。

代码和数据准备成功后停止，不擅自跑完整 Pareto benchmark，先由 Claude/Gpt 审查 artifact 对齐情况。
