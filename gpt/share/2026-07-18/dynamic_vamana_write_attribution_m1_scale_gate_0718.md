# Dynamic Vamana Write Attribution M1：Matched-Size Scale Gate

## 1. 裁决与目标

正式接受 M0 双系统 100K composed closure：

- DGAI：R03 / V4 profiler / 100K PASS；
- OdinANN：R04 / V5 profiler / 100K PASS；
- 两者均从同一 R12 frozen CP10 source、同一 master prefix `[800000:900000]` 创建独立 fresh clone；
- active-set、visibility、query smoke、changed-file coverage、ledger closure、source preservation 与 OOM 门禁均通过。

M1 只回答固定写入成本与每 replacement 边际写入成本，不设计新系统，不开始 novelty 宣称。

## 2. 口径修正

不得把 OdinANN 的 application physical total `32.417 GB` 与 DGAI 的 `9.015 GB` 直接解释为持续更新写放大差距。

OdinANN total 包含一次性的 load/shadow-copy：

- load：`8.480 GB`；
- insert-neighbor-repair：`15.457 GB`；
- publish-save：`8.480 GB`。

因此后续必须分别报告：

1. cold-start/load bytes；
2. recurring update-window bytes，排除 load；
3. insert-neighbor-repair bytes；
4. publish-save bytes；
5. logical neighbor-repair、target-only、shared-page bytes。

100K anchor 的描述性结果为：

- recurring update-window：OdinANN 约为 DGAI 的 `2.66×`；
- insert-neighbor-repair：OdinANN 约为 DGAI 的 `5.14×`；
- publish-save：根据 machine ledger 单独计算并报告。

这些比值仍是单点观察，M1 用 matched-size 数据判断其是否稳定。

## 3. 实验矩阵

使用 accepted 100K anchor，并新增：

| System | New sizes |
|---|---|
| DGAI | 50K、200K、400K |
| OdinANN | 50K、200K、400K |

每个点都必须：

- 从各自同一个 R12 frozen CP10 source 创建独立 fresh private clone；
- 不从前一个规模的结果继续；
- 使用嵌套 master prefix：
  - 50K：`[800000:850000]`
  - 100K：`[800000:900000]`
  - 200K：`[800000:1000000]`
  - 400K：`[800000:1200000]`
- 使用已完成 changed-file coverage 的 profiler；
- DGAI 新点可使用 V5；100K R03/V4 anchor继续有效，因为 closure 已证明该 workload 不触发新增 sendfile hook；
- 单点只运行一次。application-requested bytes 是主要归因指标，wall time 与 device bytes 只作描述性和 sanity evidence。

## 4. 每个点必须记录

### 按 phase

- load；
- insert-neighbor-repair；
- delete；
- metadata；
- visibility；
- publish-save；
- other。

### 按 physical component

- graph-vector-combined；
- vector/PQ；
- tags/metadata；
- shadow files；
- unknown。

### 按 logical role

- target-only；
- target + neighbor shared page；
- neighbor-repair-only。

### 统计量

- application physical bytes；
- async bytes；
- POSIX/copy bytes；
- device write bytes；
- write request count；
- unique 4 KiB pages；
- page-touch count；
- page rewrite factor；
- bytes/replacement；
- pages/replacement；
- ingest、publish、E2E wall time；
- active-set、online/fresh visibility、query smoke与source preservation。

## 5. 分解方式

对每个系统、phase和component给出四个真实数据点：

```text
N = 50K, 100K, 200K, 400K
```

进行描述性拟合：

```text
bytes(N) = intercept + slope × N
```

必须报告：

- intercept；
- slope；
- 每个点的实际值；
- 每个点的预测值；
- 绝对残差与相对残差；
- `bytes/replacement` 随 N 的变化。

不得仅报告 R²，也不得设定任意阈值后宣称线性成立。若残差呈系统性变化，应直接判定简单固定+边际模型不足。

## 6. 核心归因问题

最终报告必须回答：

1. OdinANN 相对 DGAI 的 recurring update-window 差距主要来自 insert 还是 publish？
2. insert 差距主要来自更多 unique pages，还是相同页面的更高 rewrite factor？
3. neighbor-repair-only 的边际 bytes/replacement 是否稳定？
4. load/shadow-copy 是否基本为固定成本？
5. publish-save 是否随 N 变化，还是主要由全索引重写决定？
6. 100K 单点观察到的 insert `5.14×` 差距，在 50K–400K 是否持续存在？

只能回答数据能够支持的问题。不能将差异直接归因于 online visibility，因为两系统的布局、I/O engine和更新算法仍同时不同。

## 7. 正确性与停止条件

每个点必须通过：

- replacement count/range exact；
- active-set exact；
- online/fresh visibility符合各系统语义；
- query smoke；
- changed-file coverage；
- physical ledger/bucket/entry闭合；
- phase/component分类完整；
- frozen source不变；
-无OOM/fatal。

普通目录、owner、unit命名和日志问题可自行最小修复。

出现写入口遗漏、重复计数、changed-file coverage失败、索引结果变化或共享source风险时立即停止。

## 8. 输出与停止点

输出：

```text
codex/share/2026-07-18/
dynamic_vamana_write_attribution_m1_scale_0718.md
```

同时生成 machine-readable scale summary，绑定 M0 closure、全部 run identity、profiler identity 与 input prefix。

完成双系统 50K/100K/200K/400K matched-size 分解后停止。

不得自动开始：

- 新系统实现；
- write buffering原型；
-邻居修复优化；
-novelty结论；
-额外churn checkpoint。
