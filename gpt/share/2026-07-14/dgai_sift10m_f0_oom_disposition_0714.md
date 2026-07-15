# DGAI SIFT10M F0 OOM：处置裁决

**日期**：2026-07-14
**输入报告**：`codex/share/dgai_sift10m_f0_oom_review_request_0714.md`
**裁决**：**允许一次 build-only 跨 NUMA 重试；算法参数保持不变**

---

## 1. 对失败性质的判断

本次失败应记录为：

```text
DGAI build failed under single-NUMA memory binding
```

不能写成：

```text
DGAI cannot build SIFT10M
```

已测配置为：

```text
dataset = SIFT10M checkpoint 0
active vectors = 8,000,000
dtype = float32
R = 32
L = 75
B = 1
M = 64
T = 24
CPU = 0-23
memory policy = membind node 0
```

失败发生在 PQ refinement，进程达到约：

```text
anonymous RSS = 120.3 GiB
file RSS ≈ 4.4 GiB
```

而 NUMA node 0 总容量约 128.6 GB。

整机约有 251 GiB DRAM，因此当前证据说明单 NUMA 容量不足，尚未说明整机资源不足。

---

## 2. 为什么不先调整 M

DGAI 的参数说明把 `M` 称为 indexing RAM budget，但该参数不是进程 RSS 的硬上限。

当前 artifact 中：

```text
num_pq_chunks = 64
```

被直接固定。

执行顺序为：

```text
生成第一套 PQ
→ PQ refinement
→ 重新编码
→ build_merged_vamana_index(..., indexing_ram_budget, ...)
```

因此当前 OOM 发生在 `M` 真正参与 Vamana partition/build 之前。

降低 `M`：

* 不会直接缩小固定 64-chunk refinement；
* 不能保证降低 refinement 峰值；
* 会改变后续 partition/shard 行为；
* 可能增加分片、合并和构建时间；
* 会引入新的公平性变量。

所以本轮不修改 `M=64`。

---

## 3. 为什么不先调整 T

线程数可能影响 BLAS workspace 和部分临时内存，但当前 refinement 还包含与线程数无关的大块内存：

* 全量或分块数据；
* PQ map；
  -误差数组；
  -候选中心数组；
* closest-center distance matrix；
  -排序与 k-means 状态。

仅降低 `T` 是否足以从约 125 GiB 降到单节点安全范围没有证据。

同时，降低 `T` 会改变构建时间，仍然可能在长时间运行后 OOM。

因此本轮优先采用不改变算法配置的内存策略修正。

---

# 4. 授权的重试配置

只对 **DGAI build phase** 使用：

```text
numactl --physcpubind=0-23 --interleave=0,1
```

保持：

```text
R = 32
L = 75
B = 1
M = 64
T = 24
```

以下阶段仍使用原 serving 约束：

```text
DGAI postprocess:
CPU 0-23
membind node 0

DGAI query:
CPU 0-23
membind node 0
```

如果 postprocess 也出现单节点内存不足，再单独提交证据，不自动扩大其内存策略。

---

## 5. 公平性边界

build-only 跨 NUMA 是一个明确的 artifact 特例。

本轮允许这样做，因为 Pilot 的核心比较对象是：

* query Recall–QPS；
* query latency；
* serving DRAM；
  -更新与可见性；
* churn 后性能。

初始索引构建只是进入实验的 prerequisite。

因此：

* DGAI query 仍与其他系统使用同一 CPU/NUMA serving 约束；
* DGAI build wall time 与 DiskANN/OdinANN build wall time暂不做严格横向排名；
* DGAI build peak DRAM 仍如实报告；
  -报告中标注 `build-only cross-NUMA memory exception`。

后续若论文需要比较 build cost，则必须补做统一构建资源模式，不能直接使用这组三系统 build 时间。

---

# 6. 重试执行方式

## 6.1 保留失败证据

保留：

```text
pilot3_sift10m_p1r07/f0/DGAI/p1r07-01
```

不得删除、覆盖或从其部分文件恢复。

## 6.2 新 attempt

使用独立目录，例如：

```text
run = pilot3_sift10m_p1r08
attempt = p1r08-dgai-01
```

从空的 DGAI index directory 重新构建。

以下资产可以复用：

* SIFT10M canonical dataset；
* checkpoint-0 GT；
* GT audit；
* DiskANN 已完成的 immutable F0 index。

不需要重新下载数据、重新计算 GT 或重建 DiskANN。

## 6.3 Phase-specific NUMA policy

不要把所有系统的公共 `NUMA_NODE` 改成跨 NUMA。

建议增加明确的 DGAI build-only 配置：

```text
DGAI_BUILD_MEMORY_POLICY=interleave
DGAI_BUILD_MEMORY_NODES=0,1
```

公共 launcher 根据：

```text
system == DGAI
phase == build
```

选择跨 NUMA；其他 phase 保持 `membind=0`。

每个 phase 保存实际：

```text
taskset -pc
numactl --show
cgroup path
memory.current
memory.peak
memory.events
```

---

# 7. 运行保护

为避免影响整机稳定性，DGAI build scope 建议设置操作性安全上限：

```text
MemoryMax = 200 GiB
```

该值不是算法参数，也不用于性能结论。

选择依据：

* 已测峰值约 125 GiB；
  -整机约 251 GiB；
  -需要给内核、文件缓存和其他必要进程保留空间。

同时设置：

```text
watchdog = 6 hours
```

若达到 MemoryMax、发生 OOM、超时或设备空间异常，立即停止并保留证据。

邮件通知应包含：

* current phase；
* elapsed time；
* peak memory；
* current chunk/progress；
* estimated remaining；
  -失败原因。

---

# 8. 重试成功后的验证

DGAI build 成功后，必须验证：

1. 所有预期索引文件存在且非空；
2. build process 返回码为 0；
   3.日志不存在 OOM、bad_alloc、fatal 或 assertion；
3. postprocess 完成；
4. query 在 `membind=0` 下运行；
5. Recall@10 可解析且有限；
6. query 使用 checkpoint-0 exact GT；
7. query 对实验 NVMe 产生真实读取；
8. serving peak DRAM 单独记录，不与 build peak 混合；
9. query validation level 标记为 `aggregate-only validation`。

---

# 9. OdinANN 的执行

如果 DGAI 跨 NUMA重试成功：

```text
DGAI query
→ OdinANN F0
→ P1 汇总
```

如果 DGAI 再次失败：

1. 将其标记为：

```text
resource-infeasible on current 251-GiB host
under the preserved artifact configuration
```

2. 不进行第二轮参数搜索；
   3.继续执行 OdinANN F0；
   4.提交两系统结果和 DGAI resource-failure 证据；
   5.再决定是否缩小 DGAI 数据规模或联系作者。

不能让 DGAI 的构建失败永久阻塞 OdinANN readiness。

---

# 10. 本轮不授权的操作

当前不允许：

-降低 `M` 后反复试值；
-降低 `T` 后反复试值；
-关闭 PQ refinement；
-减少 PQ chunks；
-修改 error percentage；
-改变 R 或 L；
-复用失败构建的中间文件；
-修改 DGAI 核心算法以降低内存；
-启动 W0/W1；
-将跨 NUMA build 时间与单 NUMA build 时间直接排名。

---

# 11. 最终裁决

执行一次：

```text
same DGAI algorithm/configuration
+ same CPU set
+ build-only interleaved memory across nodes 0 and 1
```

这是当前最小且最可解释的恢复方案。

它保持了 DGAI 索引本身的参数与算法语义，只放宽了我们人为施加的单 NUMA 构建约束。

重试后，无论成功或失败，都继续 OdinANN F0，并在 P1 汇总后停止。
