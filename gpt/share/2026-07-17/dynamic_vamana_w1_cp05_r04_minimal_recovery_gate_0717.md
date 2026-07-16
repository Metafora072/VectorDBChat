# Dynamic Vamana W1：CP05 R04 最小恢复门禁

**日期**：2026-07-17

**裁决**：

* R03 停止有效；
* Shared query I/O primer 已验证通过，不再修改；
* 当前问题只是 canary evidence 输出目录没有写权限；
* 本轮只做最小权限修复；
* 修复后重新执行 16→80 replay 与正式 CP00→CP01→CP05；
* CP10、CP20 继续 HOLD。

## 1. R03 停止边界

R03 已完成 DGAI replay CP00 的 L64/L128 查询，每个 L 三次。

这些查询均满足：

-正常退出；
-结果完整；
-结果 ID 全部属于 CP00 active set；
-没有 OOM 或 fatal error；
-query scope 有正确的 NVMe I/O baseline；
-primer I/O 未计入查询指标。

停止发生在任何 update API 调用之前。

因此，本次失败不属于索引、trace、GT、查询或更新算法问题。

## 2. 直接原因

Input canary 以 `ubuntu` 用户运行，但它试图将 JSON 写入 controller-owned、mode 0755 的 attempt 根目录。

`ubuntu` 对该目录没有创建文件的权限，因此返回 `EACCES`。

本轮只修复 canary 输出位置，不修改 input isolation 语义。

## 3. 权限原则

允许 root/sudo controller 执行控制面操作：

-创建 result、stage 和 evidence 目录；
-设置 owner 和 mode；
-启动、停止 systemd scope；
-生成 manifest；
-冻结结果；
-执行只读 hash 和 preservation 检查。

以下程序继续以 `ubuntu` 运行：

* query；
  -input canary；
  -DGAI/OdinANN update worker。

不要求企业级权限隔离，但不得：

-修改或覆盖 immutable base；
-写入项目 NVMe 之外的实验路径；
-删除历史实验结果；
-格式化或修改其他磁盘；
-用 root 绕过 canary 的 denied-input 检查。

## 4. 最小权限修复

在每个 update stage 启动前，由 root controller 创建：

```text
<attempt-result>/stages/<checkpoint>/input_canary/
```

权限：

```text
owner = ubuntu:ubuntu
mode  = 0700
```

例如：

```bash
install -d -o ubuntu -g ubuntu -m 0700 \
  "$result/stages/cp01/input_canary"

install -d -o ubuntu -g ubuntu -m 0700 \
  "$result/stages/cp05/input_canary"
```

Canary 输出改为：

```text
stages/cp01/input_canary/canary.json
stages/cp01/input_canary/canary.log

stages/cp05/input_canary/canary.json
stages/cp05/input_canary/canary.log
```

Attempt 根目录继续保持 controller-owned 0755，不整体修改 ownership。

## 5. Canary 通过条件

Canary 只需验证：

1. 当前 stage 的 delta 可以读取；
2. 当前 stage 不应访问的输入返回 `EACCES` 或 `EPERM`；
3. JSON 能正常写入 stage-local evidence 目录；
4. canary exit code 为 0；
5. canary 完成前不存在 `ingest_begin`、`STAGE_WORKER_OK` 或其他 update marker。

Canary 通过后，controller 才启动 update worker。

Canary 本身不能以 root 运行，否则 denied-input 权限检查没有意义。

## 6. 启动前回归

只执行两个必要测试。

### 正向测试

以真实 `ubuntu` 用户运行：

* allowed delta 可读；
  -denied input 不可读；
  -canary JSON 可以落盘；
  -update worker 没有启动。

### 负向测试

故意让一个 denied input 可读。

要求：

* canary 失败；
  -update worker 不启动。

不增加额外的企业级权限、fsync、symlink 或多层 capability 测试。

## 7. 工件复用

允许在重新验证 size/SHA256 后复用：

* immutable replay bases；
  -frozen static smoke；
  -shared query-scope launcher；
  -R03 formal/replay 只读 inputs；
  -trajectory、active sets 和 GT。

不需要再次复制或重新派生这些只读输入。

不得复用：

* R03 mutable DGAI replay clone；
  -R03 result tree；
  -R03 attempt identity。

R04 必须创建：

-新的 result tree；
-新的 DGAI/OdinANN private clone；
-新的 execution manifest。

## 8. R04 Identity

```text
formal run:
pilot3_sift10m_w1_cp05_trajectory_r04

replay run:
pilot3_w1_cp05_trajectory_replay_r04

replay attempts:
sequential-cp80-04

formal attempts:
trajectory-cp05-04

DiskANN attempt:
stale-cp05-04
```

## 9. 执行顺序

```text
取得 global lock
→ 验证历史输入与 immutable bases
→ 执行 canary 正向/负向测试
→ DGAI 16→80 replay
→ OdinANN 16→80 replay
→ DGAI CP00→CP01→CP05
→ OdinANN CP00→CP01→CP05
→ DiskANN CP05 stale control
→ 汇总报告
→ 停止
```

正式累计状态保持：

```text
clone CP00 once
→ 应用 80K delta
→ 发布并验证 CP01
→ 新 worker 重新加载 CP01
→ 只应用后续 320K delta
→ 发布并验证 CP05
```

## 10. 必须保留的实验门禁

只保留直接影响指标可信度或服务器数据安全的检查：

* binary、trace、GT、active-set 和 base hash 正确；
* query result shape 正确；
  -result IDs 属于当前 active set；
* update 数量正确；
  -CP01 与 CP05 active set exact；
  -无 OOM、fatal 或 I/O error；
  -真实读取项目 NVMe；
  -private clone 可写；
  -immutable base 在实验前后内容不变；
  -所有实验输出位于项目 NVMe 的新目录。

不继续增加与实验指标无直接关系的复杂安全门禁。

## 11. 失败规则

任一正式 replay/update/query 失败：

-停止当前 run；
-保留日志和结果；
-不删除历史工件；
-不自动修改参数；
-不继续后续系统。

对于明显的脚本路径、目录权限或标签错误，可以在审议后使用新 attempt 做最小修复，不再扩展成新的大型基础设施设计。

## 12. 输出

成功报告：

```text
codex/share/2026-07-17/
dynamic_vamana_w1_cp05_cumulative_trajectory_r04_results_0717.md
```

失败报告：

```text
codex/share/2026-07-17/
dynamic_vamana_w1_cp05_cumulative_r04_stop_analysis_0717.md
```

## 13. 最终裁决

R03 已经证明 query-I/O evidence 路径正确。

R04 只修复 canary evidence 目录权限，并尽快推进真正的累计更新实验。

本项目后续门禁以以下目标为准：

1. 指标计算正确；
   2.输入、索引和 GT 身份明确；
   3.不破坏 immutable base；
   4.不影响服务器其他磁盘和文件；
   5.避免为边缘安全条件反复阻塞实验。

CP10、CP20 继续 HOLD，等待 CP05 累计结果。
