# Dynamic Vamana P2-A-R1：重复性门禁修订

**日期**：2026-07-15
**上游报告**：`codex/share/dynamic_vamana_p2a_r1_canary_gate_failure_0715.md`
**裁决**：**允许受限重复性测量；不再要求单次 Recall bit-level 相等**

---

# 1. 对当前 DGAI 差异的裁决

当前 DGAI 两次结果为：

```text
原 P1 F0：Recall@10 = 0.9216
P2-A-R1：Recall@10 = 0.9210
绝对差值：0.0006
```

P2-A-R1 点同时满足：

* 完整 10,000 queries；
* 原始 checkpoint-0 exact GT；
* Tq=8；
* beamwidth=16；
* L=40；
  -相同 immutable index；
  -进程正常退出；
  -无 fatal marker；
  -无 cgroup OOM；
  -实际读取约 9.78 GB；
  -QPS 与平均 I/O 和原 F0 处于相同量级。

因此该差异不足以证明配置错误或搜索语义改变。

原 P1 F0 只有一次测量，不能作为要求所有后续运行完全相等的绝对真值。

---

# 2. Artifact 冻结

重复性测试使用当前已经修正并记录的：

* DiskANN query binary；
* DGAI query binary；
* OdinANN query binary；
  -三个 immutable checkpoint-0 indexes；
  -完整 10K query；
  -原始 checkpoint-0 GT。

每个 point 必须记录：

```text
query binary SHA256
index file SHA256
query SHA256
GT SHA256
compatibility patch SHA256
source commit
```

测试过程中不得再次修改或重新编译 artifact。

DGAI 的只读兼容性补丁仅允许改变文件打开权限，不允许改变搜索、距离计算、候选队列、PQ 或图遍历代码。

OdinANN 使用已经批准的：

```text
query path → O_RDONLY
update path → O_RDWR
negative CQE/open/submit error → fail closed
```

---

# 3. F0 重复性实验

## 3.1 固定配置

统一使用：

```text
queries = 10,000
GT = 原始 checkpoint-0 exact GT
K = 10
L = 40
Tq = 8
CPU = 0-23
NUMA policy = membind node 0
beamwidth = 各系统原 F0 值
```

每次运行：

1. 使用新进程；
   2.创建新 dedicated cgroup；
   3.执行 page-cache drop；
   4.不复用前一次进程内状态；
   5.写入新的 repeat 目录；
   6.保留全部 raw log 与 point.json。

---

## 3.2 重复次数

运行：

```text
DiskANN：3 次
DGAI：10 次
OdinANN：10 次
```

DiskANN 已经精确复现一次，三次用于确认完整流程稳定。

DGAI 需要十次以估计实际多线程运行方差。

OdinANN 修复后尚未完成有效 canary，需要十次同时验证：

* EBADF 已消失；
  -错误处理生效；
  -Recall 稳定；
  -修复没有改变成功查询语义。

不得挑选最好一次作为结果。

---

# 4. 统计判据

对每个系统计算：

```text
mean Recall
median Recall
sample standard deviation
minimum
maximum
95% confidence interval of the mean
95% prediction interval for one future run
```

95% prediction interval计算为：

```text
mean ± t(0.975, n-1) × s × sqrt(1 + 1/n)
```

## 4.1 有效性条件

所有重复均必须：

* `valid=true`；
  -返回码为 0；
  -无 I/O error、EBADF、fatal 或 assertion；
  -无 cgroup OOM；
  -实验 NVMe read bytes 大于 0；
  -输入与 artifact hash 完全一致；
  -Recall 有限且位于 `[0,1]`。

任意一次 invalid 均停止该系统，不通过简单补跑替换失败样本。

## 4.2 重复性条件

要求：

```text
95% CI half-width ≤ 0.001
```

理由是正式 matched-Recall 的容差为 ±0.005；重复噪声应不超过该容差的五分之一，避免噪声主导系统匹配。

## 4.3 与旧 F0 的一致性

原 P1 F0 的单次 Recall 作为一个历史观测值，而非 bit-level 锚点。

要求原 F0 值落在当前重复实验得到的：

```text
95% prediction interval
```

内。

若落在区间内，说明原 F0 与当前修正 artifact 的测量属于同一合理波动范围。

若落在区间外，则停止并检查：

* query binary 语义变化；
  -线程调度或共享状态；
* index 内容变化；
* GT/input identity；
* driver 参数映射。

不能通过扩大固定绝对容差强行通过。

---

# 5. Canary 结果处理

## 5.1 DiskANN

已有的：

```text
Recall@10 = 0.9688
```

保留为第一次有效重复，再新增两次。

## 5.2 DGAI

已有的：

```text
Recall@10 = 0.9210
```

保留为十次重复中的第一次，不覆盖、不丢弃。

原先错误使用 Tq=1 的 0.9195 继续标记为：

```text
INVALID_CANARY_CONFIGURATION
```

不得纳入统计。

## 5.3 OdinANN

DGAI 不再因单次差异阻塞 OdinANN。

Codex 可以继续执行 OdinANN 修复后的十次 F0 重复。

若仍出现：

```text
Bad file descriptor
negative CQE
0 Recall
约 1 I/O/query
异常短的运行时间
```

立即停止，不能形成有效 baseline。

---

# 6. 重复性通过后的 P2-A-R1

三个系统均通过重复性门禁后，进入完整 10K、Tq=1 calibration。

网格保持：

```text
DiskANN:
L = 10, 12, 16, 20, 24, 32, 40, 60, 80

DGAI:
L = 20, 40, 80, 120, 160, 240, 320

OdinANN:
L = 20, 40, 80, 120, 160, 240, 320
```

---

# 7. Calibration 重复策略

每个 coarse-grid L 点运行三次。

汇总使用：

```text
median Recall
median QPS
median latency
median mean-I/O
```

同时保留三个 raw runs。

原因是当前已经确认单次 DGAI Recall 存在可测的运行波动，继续让单次值决定 Recall bracket 不够稳健。

coverage 计算只使用：

* 三次均为 valid；
  -相同 artifact/input identity；
  -median Recall。

若同一系统的 median Recall 随 L 出现明显下降：

1. 检查 raw runs；
   2.再补充两次形成五次；
   3.仍然异常则停止归因。

不得通过排序或 isotonic regression 修改正式测量值。

---

# 8. 共同 Recall coverage

继续检查：

```text
0.93
0.95
0.97
0.98
0.99
```

每个目标必须由三个系统各自的有效 median curve 覆盖。

coarse grid 可以判断 coverage，但最终 matched point 仍需在目标附近运行实际参数点，不能只使用插值结果。

---

# 9. 停止边界

P2-A-R1 完成后必须停止。

即使获得两个以上共同 Recall 目标，也不自动运行：

* P2-B；
* Tq=16；
* W1；
* 1% churn；
* 20% churn；
* DEEP/GIST；
* W2。

先提交：

```text
codex/share/dynamic_vamana_p2a_r1_repeatability_and_calibration_0715.md
```

报告必须包含：

1. 三系统 F0 重复分布；
2. 旧 F0 是否落入 prediction interval；
3. OdinANN 修复后的有效性证据；
4. calibration 三次重复的 raw 与 median；
5. common Recall coverage；
6. invalid attempts；
7. 尚未进入 P2-B/W1 的声明。

---

# 10. 最终授权

Codex 当前获授权：

```text
完成三系统 F0 重复性实验
→ 检查统计门禁
→ 若通过，执行三次重复的 P2-A-R1 calibration
→ 汇总并停止
```

DGAI 的 `0.9210` 不再因与单次历史值相差 `0.0006` 而单独阻塞流程。
