# Dynamic Vamana P2-A：受限重校准门禁

**日期**：2026-07-15
**上游报告**：`codex/share/dynamic_vamana_p2a_configuration_review_0714.md`
**裁决**：**REVISE AND RE-RUN P2-A ONLY**

当前 P2-A 的 21 个结果点全部保留为诊断证据，但不能进入正式 calibration curve，也不能启动 P2-B。

---

# 1. 当前结果的有效性裁决

## 1.1 DGAI

DGAI 的结果呈现合理的单调趋势：

```text
L 增大
→ Recall 上升
→ QPS 下降
→ I/O 增大
```

但本轮使用的 `gt_cp00_2000` 距离区不正确，因此这些点只能作为查询路径已经跑通的诊断证据。

不能将其作为正式 matched-Recall 数据。

## 1.2 DiskANN

DiskANN 在 L=20–320 上全部 Recall=1.0，当前不能简单归因于“L 网格过高”。

还存在两个混杂因素：

* 使用了前 2,000 条 query，可能存在 query-prefix 偏差；
* `gt_cp00_2000` 的距离区被错误截取。

因此既不能接受全部 1.0，也不能直接只增加更低 L 后继续。

## 1.3 OdinANN

OdinANN 的七个点全部无效。

其日志包含大量：

```text
Failed Bad file descriptor
```

当前 reader 在只读查询模式下仍使用 `O_RDWR`；打开失败后，I/O completion 路径只打印错误，仍把请求视为完成，导致进程可能以 0 返回并输出伪结果。

以下数据全部禁止使用：

* Recall=0；
  -约 0.05 秒完成 2,000 queries；
  -约 1 I/O/query；
  -由这些点计算出的 QPS 或 latency。

---

# 2. 修复 Ground Truth 口径

## 2.1 废弃当前子集 GT

将：

```text
gt_cp00_2000
```

标记为：

```text
INVALID_GT_LAYOUT
```

不得删除文件和旧结果，但任何后续汇总必须排除它们。

## 2.2 本轮直接使用完整 10K

重校准统一使用：

```text
query = 原始完整 10,000 queries
GT    = 原始 checkpoint-0 exact top-100 GT
```

不再截取 query prefix 或 GT prefix。

理由：

* 完整 10K 查询运行时间仍然可控；
  -消除前 2,000 query 的分布偏差；
  -消除 truthset 切片格式问题；
  -可直接与 F0 的 Recall 进行复现核对。

## 2.3 后续如需 truthset 子集

新增专用工具，例如：

```text
slice_truthset.py
```

它必须分别读取和写入：

```text
header
IDs block
distances block
```

不能复用面向普通 `.bin/.fbin` 数据文件的 `make_binary_prefix.py`。

至少需要验证：

* 输出 header；
  -输出文件大小；
  -随机 query 的 ID 行与原 GT 完全一致；
  -随机 query 的 distance 行与原 GT 完全一致；
  -tie-aware Recall 与原文件对应 query 子集完全一致。

---

# 3. OdinANN 查询修复

## 3.1 Reader open flags

在 io_uring reader 中改为：

```text
enable_writes = false
→ O_RDONLY | O_DIRECT | O_LARGEFILE

enable_writes = true
→ O_RDWR   | O_DIRECT | O_LARGEFILE
```

`enable_create=true` 只能与可写模式共同使用。

更新路径仍必须使用可写描述符，不能为了查询修复破坏 OdinANN update path。

## 3.2 打开失败必须 fail closed

不能只依赖：

```cpp
assert(fd != -1);
```

因为 release build 可能关闭 assertion。

文件打开失败时必须输出：

* filename；
* flags；
* errno；
* strerror(errno)；

随后以非零状态退出。

## 3.3 io_uring 错误必须成为实验失败

当：

```text
cqe->res < 0
```

时不能继续把该请求标记为成功完成。

至少应：

-记录真实的 `cqe->res`；
-终止当前查询；
-令 driver 返回非零；
-不输出有效 metric row。

该修改属于错误处理与只读兼容性修复，不改变成功 I/O 下的搜索算法。

## 3.4 Patch 记录

更新：

```text
OdinANN_system_uring_cblas.patch
```

并同步：

* patch SHA256；
  -允许修改文件列表；
* rebuild binary hash；
* artifact manifest；
  -修改前后语义说明。

---

# 4. Validator 与汇总器修复

## 4.1 Fatal markers

aggregate validator 至少拒绝：

```text
Bad file descriptor
Failed
I/O error
io_uring_* failed
segmentation fault
assertion failure
core dumped
```

不能因为进程 exit code 为 0 就认为结果有效。

## 4.2 Point validity

每个 `point.json` 增加：

```text
valid
invalid_reason
validation_level
```

只有满足全部条件的点才可标记为 valid：

* process return code 为 0；
  -无 fatal marker；
* metric row 可解析；
* Recall 有限且位于 `[0,1]`；
  -cgroup 无 OOM；
  -实验 NVMe read bytes 有实际增长；
  -查询输入与 GT identity 正确。

## 4.3 Collector

`collect_p2_points.py`：

* 保留所有 raw point；
  -只使用 `valid=true` 的点计算 coverage；
  -invalid 点不得参与 lower/upper bracket；
  -summary 中报告每个系统的 invalid point 数及原因。

---

# 5. F0 复现 canary

正式扫描前，先用完整 10K query、原始 GT 和原 F0 参数复现三个系统。

使用与 F0 相同的 query concurrency 和搜索配置：

```text
DiskANN: L=40
DGAI:    L=40
OdinANN: L=40
```

预期 Recall 参考：

```text
DiskANN = 0.9688
DGAI    = 0.9216
OdinANN = 0.9738
```

允许仅有浮点打印级误差。

Canary 必须同时验证：

* 三个进程正常退出；
  -没有 I/O error；
  -OdinANN 不再出现 EBADF；
  -device read bytes 非零；
  -Recall 与 F0 基本复现；
  -DiskANN result shape 与 active-ID membership 仍通过。

任一系统无法复现 F0 时，停止，不启动 calibration grid。

---

# 6. P2-A-R1 重校准

新 run name，例如：

```text
pilot3_sift10m_p2a_r1
```

旧的：

```text
pilot3_sift10m_p2
```

完整保留，不覆盖。

统一条件：

```text
queries = 10,000
GT = 原始 checkpoint-0 GT
Tq = 1
K = 10
CPU = 0-23
memory policy = membind node 0
```

## 6.1 DiskANN coarse grid

```text
L = 10, 12, 16, 20, 24, 32, 40, 60, 80
```

L 不得小于 K。

## 6.2 DGAI coarse grid

```text
L = 20, 40, 80, 120, 160, 240, 320
```

## 6.3 OdinANN coarse grid

```text
L = 20, 40, 80, 120, 160, 240, 320
```

除 L 外，保留各 artifact 的其他原生 query 参数。

各系统的 L 只代表其自身搜索广度，不要求相同 L 具有相同内部工作量。

---

# 7. 共同 Recall 目标

继续检查：

```text
0.93
0.95
0.97
0.98
0.99
```

coarse grid 完成后，可以为目标附近补充少量中间 L。

要求：

* 三个系统均有 valid 实测点；
  -目标上下界由实际点覆盖；
  -目标测量点落在 ±0.005；
  -不得使用无效点；
  -不得只通过插值得到最终性能数据。

---

# 8. 本轮停止位置

P2-A-R1 完成后必须停止。

即使得到两个以上共同 Recall 目标，也不自动启动 P2-B。

原因是本轮同时修改了：

* GT 口径；
  -OdinANN reader；
  -I/O error handling；
  -validator；
  -query 数量；
  -DiskANN 网格。

需要先审阅：

* 三系统曲线是否单调合理；
  -F0 canary 是否复现；
  -共同 Recall 区间；
  -每个系统的有效点数量；
  -计时口径；
  -I/O 与 latency 是否正常。

通过后再单独授权 P2-B 的三次重复与 Tq=16。

---

# 9. 输出

输出：

```text
codex/share/dynamic_vamana_p2a_recalibration_results_0715.md
```

报告必须包括：

1. GT slicing bug 的确认与旧结果失效声明；
2. OdinANN EBADF 根因和修复 diff；
3. F0 三系统复现 canary；
4. 完整 10K coarse calibration；
5. invalid-point 汇总；
6. common Recall coverage；
7. 所有原始点路径；
8. 尚未启动 P2-B/W1/churn 的声明。

---

# 10. 最终裁决

不关闭 Pilot。

但当前 P2-A 的 21 个点不能修补后直接拼接使用，必须以正确的完整 10K query/GT 重新运行三系统 calibration。

当前只授权：

```text
修复 GT/validator/OdinANN
→ F0 reproduction canary
→ P2-A-R1 full-10K recalibration
→ 停止并提交审查
```
