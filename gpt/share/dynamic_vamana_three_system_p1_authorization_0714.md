# 三系统 SIFT10M Pilot：P1 执行授权

**日期**：2026-07-14
**上游报告**：`codex/share/dynamic_vamana_three_system_f0_p0_revision_0714.md`
**裁决**：**PASS — 允许进入 P1 数据准备与三系统 F0**

---

## 1. P0 验收结论

以下问题已经解决：

* CPU 通过 `numactl --physcpubind=0-23` 实际绑定；
* 内存通过 `numactl --membind=0` 实际绑定；
* 每个 phase 保存 effective CPU/NUMA policy；
* root-managed transient systemd scope 已在当前主机实测；
* scope 内命令以 UID 1000 运行；
* `memory.current`、`memory.peak` 与实验 NVMe `io.stat` 可采集；
* 所有输出路径通过 `realpath`、`findmnt` 和 major:minor 验证；
* 数据准备的重型阶段具有 300 GB 空间门禁；
* 原始与 canonical 数据均记录 SHA256；
* source hash 漂移和跨 URL partial resume 会被拒绝；
* DiskANN query result 已具备 shape、Recall 和 active-ID 校验；
* 邮件通知失败不会覆盖或改变主实验结果。

runtime canary 的失败 attempt 被保留，最终 attempt 已通过，没有隐藏失败记录。

因此 P0 不再阻塞 P1。

---

## 2. DGAI/OdinANN 逐查询 ID 边界裁决

本轮不要求为 DGAI 和 OdinANN 增加新的 result-ID instrumentation patch。

原因：

1. 这两个 artifact 当前使用原生 search driver；
2. driver 已根据 exact GT 计算聚合 Recall；
3. F0 与 W0 的 checkpoint 0 是静态、无删除状态；
   4.新增输出 patch 会扩大被冻结的 patch 集，并引入重新编译与代码语义审查；
   5.当前目标只是方向发现 Pilot，而不是发布最终 benchmark artifact。

但必须将验收强度分开记录：

| 系统      | F0 query 验收                                         |
| ------- | --------------------------------------------------- |
| DiskANN | result shape + finite Recall + active-ID membership |
| DGAI    | finite aggregate Recall against exact GT            |
| OdinANN | finite aggregate Recall against exact GT            |

DGAI/OdinANN 标记为：

```text
aggregate-only validation
```

不得写成已经通过逐 query ID 独立审计。

在启动 P1 前，只需对现有日志检查增加一个轻量守卫：

* 至少成功解析一个 Recall@10；
* Recall 必须为有限数；
* Recall 必须位于 `[0,1]`；
* search process 返回码必须为 0；
  -日志不得包含 fatal、abort、segmentation fault 或 assertion failure。

该守卫不需要修改 artifact 源码。

---

# 3. P1 授权范围

P1 只包含：

1. SIFT10M source 获取与 provenance；
2. canonical corpus 转换；
3. 80/20 active/insert 划分；
4. checkpoint 0 exact GT 与独立审计；
5. DiskANN F0；
6. DGAI F0；
7. OdinANN F0；
8. 实际时间、空间、DRAM 和 I/O 汇总。

本轮仍不授权：

* slim W0；
* 1% churn canary；
* 20% churn；
* DiskANN checkpoint-20 rebuild；
* DEEP10M；
* GIST1M；
* Fresh-Ref；
* W2 mixed workload；
* Idea 或系统优劣结论。

---

# 4. SIFT10M source 要求

Codex 使用明确的标准 BIGANN/SIFT `.bvecs` 来源。

开始前记录：

* base source URL 或本地来源；
* query source URL 或本地来源；
  -来源所属项目或数据集说明；
  -原始文件字节数；
  -原始 base/query SHA256；
  -canonical base/query SHA256。

若没有上游公开 expected checksum：

```text
expected_hash_available = false
source_review_status = operator-reviewed-standard-BIGANN
```

这表示我们确认来源链条，但不虚构官方 checksum。

禁止：

* 复制 SIFT1M 十次；
  -对 SIFT1M 重采样；
  -从其他格式生成无法追溯的 corpus；
  -使用未记录 URL 的临时镜像；
  -忽略 hash 漂移继续运行。

---

# 5. P1 运行顺序

在一个受控 tmux 流程中严格串行：

```text
runtime canary
    ↓
prepare_sift10m.sh
    ↓
validate_sift10m.sh
    ↓
f0_diskann.sh
    ↓
f0_dgai.sh
    ↓
f0_odinann.sh
    ↓
生成 P1 汇总并停止
```

runtime canary 已经通过，但正式长流程启动时再执行一次成本很低，可同时验证 sudo credential、scope 和邮件环境没有变化。

三个索引构建不得并发。

---

# 6. tmux 与通知

建议 session：

```text
tmux:p1-sift10m
```

主日志必须位于实验 NVMe。

邮件通知至少覆盖：

* P1 正式启动；
  -数据准备成功；
  -数据准备失败；
  -GT validation 成功；
  -GT validation 失败；
  -每个系统 F0 成功；
  -每个系统 F0 失败；
  -P1 全部完成。

通知失败只写入本地日志，不得令已经成功的实验被标记为失败。

邮件内容包含：

* phase；
  -system；
  -attempt；
  -exit code；
  -result directory；
  -systemd unit；
  -下一步是否停止。

---

# 7. 失败策略

任何阶段失败后：

1. 停止后续阶段；
   2.保留当前 attempt；
   3.发送异常通知；
   4.记录失败 phase、exit code、日志和资源；
   5.不得在同一 attempt 目录静默重跑；
   6.不得自动修改参数或 artifact；
   7.等待下一轮审查。

下载中断可以使用受 provenance 保护的续传；索引构建失败不能覆盖原目录。

---

# 8. P1 必须汇总的数据

## 数据准备

* source URL；
* source/canonical SHA256；
  -下载字节与时间；
  -转换时间；
  -checkpoint 物化时间；
  -GT 计算与验证时间；
  -实际 allocated/apparent bytes；
  -剩余 NVMe 空间。

## 每个系统 F0

* artifact commit；
* build 参数；
  -build wall time；
  -postprocess wall time；
  -load/query wall time；
  -build peak DRAM；
  -query peak DRAM；
  -cgroup memory peak；
  -process-tree RSS；
  -device read/write bytes；
  -index apparent/allocated bytes；
  -Recall@10；
  -query validation level；
  -effective CPU affinity；
  -effective NUMA policy；
  -exit status；
  -caveats。

还需确认 query 阶段确实对实验 NVMe 产生设备读取；若全部数据意外驻留 DRAM，需要明确记录。

---

# 9. P1 输出

输出：

```text
codex/share/dynamic_vamana_three_system_p1_results_0714.md
```

报告必须区分：

* measured；
  -derived；
  -estimated；
  -not available。

根据实测重新计算：

* P2 slim W0 时间预算；
* P3 1% canary 时间预算；
* P4 20% trajectory 的初步上界；
  -后续 NVMe 峰值。

不得继续沿用 1M 线性外推而不更新。

---

# 10. 停止条件

三系统 F0 完成后必须停止。

P1 的目标只是确认：

```text
标准 SIFT10M 数据
+ 三系统 8M active 索引
+ 正确 query/GT
+ 真实 SSD I/O
+ 可用资源测量
```

P1 结果经 Gpt/Claude 审查后，才决定是否进入 P2 slim W0。
