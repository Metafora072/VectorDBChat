# Dynamic Vamana Atlas：三系统 Pilot Scope Amendment

**日期**：2026-07-14
**原门禁**：`gpt/share/dynamic_vamana_formal_atlas_w0_w1_gate_0714.md`
**预算审计**：`codex/share/dynamic_vamana_three_system_pilot_budget_audit_0714.md`
**裁决**：**批准三系统方向发现 Pilot，分阶段执行**

---

## 1. Scope Amendment

SIFT10M Pilot 暂时只运行：

* DiskANN；
* DGAI；
* OdinANN。

Fresh-Ref 延后，不进入本轮代码执行。

原因是：

* Fresh-Ref 只是 reference reproduction，不是可以确认的官方 FreshDiskANN artifact；
* 依赖关闭 ASLR；
* 存在 legacy 4 KiB record 限制；
* 当前主要问题可以先通过 DiskANN、DGAI 和 OdinANN形成静态、解耦动态、耦合动态三角对照；
* 减少一个脆弱 artifact，可以降低 Pilot 中途失败的概率。

---

## 2. 本轮能够回答的问题

三系统 Pilot 可以初步回答：

1. DiskANN 的静态查询与 rebuild 上界在哪里；
2. DGAI 的解耦、merge-visible 路线位于怎样的查询—更新—资源位置；
3. OdinANN 的耦合、immediate-visible 路线位于怎样的位置；
4. DGAI 与 OdinANN 是否在 matched Recall 下形成明显不同的系统级 Pareto 点；
5. churn 后查询性能、SSD 空间和 DRAM 是否出现不同趋势；
6. 是否存在值得扩展到更多系统和数据集的方向性 gap。

---

## 3. 本轮不能回答的问题

三系统 Pilot 不能声称：

* 已完整覆盖动态 Vamana 设计空间；
* FreshDiskANN 或批量耦合路线被其他系统支配；
* DGAI 与 OdinANN 的全部差异都由“解耦/耦合”造成；
* 某系统在所有数据集和负载下更优；
* 已形成完整的 `Vq–Vm` frontier；
* 已经找到论文 Idea。

DGAI 与 OdinANN 同时还存在以下差异：

* update visibility；
* update algorithm；
* graph parameters；
* physical layout；
* search pipeline；
* PQ 组织；
* I/O backend；
* merge/consolidation 行为。

因此 Pilot 先比较完整系统位置，不做单机制因果归因。

---

## 4. Fresh-Ref 的后续触发条件

出现以下任一结果时，重新评估 Fresh-Ref 或其他更可信的批量更新 artifact：

1. DGAI 和 OdinANN 之间存在较大空白，但无法判断 batch maintenance 是否能占据该区域；
2. OdinANN 的 immediate update 在查询稳定性或空间上付出明显代价；
3. DGAI 的 merge-visible 模式表现出较高可见延迟，但更新 I/O 较低；
4. 需要区分“耦合/解耦”和“incremental/batch”两组因素；
5. 找到作者提供的 FreshDiskANN artifact 或更可靠的同路线系统。

---

# 5. Pilot 分阶段执行

不批准一次性启动完整 18–57 小时流程。按以下阶段推进。

## P0：脚本审查

Codex 先准备：

```text
f0_diskann.sh
f0_dgai.sh
f0_odinann.sh
```

每个脚本必须包含：

* 数据和路径检查；
* 禁止写系统盘；
* exact commit 检查；
* clean/allowed-patch 检查；
* dedicated cgroup；
* CPU/NUMA 绑定；
* build；
* load/query smoke；
* Recall/GT 校验；
* RSS、cgroup memory、设备 I/O 和 SSD 空间采集；
* timeout；
  -失败状态；
  -幂等完成标记。

同时准备统一的数据脚本：

```text
prepare_sift10m.sh
validate_sift10m.sh
```

P0 完成后只提交脚本与命令，不启动 tmux。

---

## P1：SIFT10M 数据与 F0 Readiness

脚本审查通过后，串行执行：

1. SIFT10M 下载、hash、canonical 转换；
2. 80/20 active/insert 划分；
3. checkpoint 0 GT；
4. DiskANN build/load/query；
5. DGAI build/load/query；
6. OdinANN build/load/query。

P1 完成后必须停止并报告：

* 实际下载体积与时间；
  -每个系统 build wall time；
* load 时间；
  -实际 index allocated/apparent size；
* build 和 serving peak DRAM；
* query 是否产生真实设备 I/O；
* Recall 是否闭环；
  -后续 W0/W1 的修订 ETA。

不能仅根据 1M 外推继续自动启动 W0。

---

## P2：Slim W0

P1 复核通过后，运行：

```text
3 systems
× Tq {1, 16}
× 4 search settings
× 1 discovery repeat
```

得到完整的：

* Recall–QPS；
* Recall–P99；
* DRAM；
* SSD；
* device I/O。

一个新进程生命周期内可以扫描同一系统、同一并发下的四个 search settings，但不同系统和不同并发必须独立启动和记录。

Discovery repeat 只能用于识别方向。

若系统间差距接近运行噪声，不能排名；需要在关键点增加重复后再判断。

P2 完成后停止并报告初步 query frontier。

---

## P3：W1 Canary

不直接运行完整 20% churn。

DGAI 与 OdinANN先分别执行一个小规模 canary：

```text
1% replace-new
```

即：

```text
80,000 replace operations
```

需要记录：

* ingestion throughput；
* visible-update throughput；
* merge/reload/publish 时间；
  -更新 P50/P95/P99 或 batch latency；
* DRAM peak；
* SSD growth；
* read/write bytes；
* insert/delete visibility probes；
  -查询 correctness；
  -按实际 throughput 外推 20% ETA。

Canary 使用 probe GT 或新生成的 exact GT；不得继续使用 checkpoint 0 GT 评价 Recall。

若 1% canary：

* active-set/tag 校验失败；
  -可见性校验失败；
  -设备空间超预算；
  -实际 ETA 明显超过 watchdog；
  -出现不可解释的 Recall 退化；

则停止该系统的 20% trajectory，先归因。

---

## P4：W1 20% Pilot

P3 通过后再执行：

* DGAI direct-to-20%，包括 merge/reload/publish；
* OdinANN direct-to-20%；
* DiskANN checkpoint-20 full rebuild；
  -三系统 checkpoint-20 query sweep。

DGAI 的 `visible-update throughput` 必须包含：

```text
updates
+ merge
+ reload
+ publish
```

OdinANN 也必须通过查询 probe 验证 API 完成后的实际可见性。

DiskANN 的动态成本定义为：

```text
full rebuild
+ publish
```

P4 完成后停止，不启动 DEEP10M、GIST1M 或 W2。

---

# 6. Pilot 预算

Codex 的预算可以作为保护上界：

| 阶段                  |       时间预算 |
| ------------------- | ---------: |
| 数据准备                |     2–6 小时 |
| 三系统 F0 build        | 2.5–4.3 小时 |
| F0 query/validation |     1–2 小时 |
| Slim W0             | 1.5–4.5 小时 |
| DGAI 20% W1         |    6–24 小时 |
| OdinANN 20% W1      |     2–8 小时 |
| DiskANN rebuild     |     1–3 小时 |
| W1 query            | 1.5–4.5 小时 |
| 总保护预算               |   18–57 小时 |

NVMe 新增峰值保护值：

```text
243 GB
```

该数字是串行执行下的峰值，不是各行空间简单求和。

但 P1 完成后必须用实测数据替换外推预算。

---

# 7. 停止与扩展条件

## 扩展到 DEEP/GIST 的条件

至少出现以下一种稳定现象：

* DGAI 与 OdinANN 在 matched Recall 下形成明显不同的 query/update frontier；
* 查询性能与 visible-update throughput 存在明显交换；
* DRAM 或 SSD 成本改变系统排序；
* churn 后某系统明显偏离初始 query frontier；
* immediate 与 merge-visible 语义产生重要成本差异；
  -现有三系统之间出现无法通过简单调参覆盖的区域。

“明显”必须超过运行波动，并在关键点重复后保持，不用预设固定百分比代替统计证据。

## 暂停扩展的条件

* 三系统位置几乎重合；
  -差异主要由 I/O backend 或线程配置解释；
  -只在单个异常参数点出现差异；
  -10M 仍未产生真实 SSD 压力；
* artifact correctness 或 visibility 无法对齐；
  -结果不足以支持任何可验证的新问题。

---

# 8. 当前授权

Codex 现在只获授权执行 **P0：准备三份 F0 脚本及数据准备脚本**。

脚本提交并经审查前：

* 不启动 tmux；
  -不下载 SIFT10M；
  -不构建正式索引；
  -不运行 W0/W1；
  -不修改 core search/update 语义。

P0 报告路径：

```text
codex/share/dynamic_vamana_three_system_f0_scripts_0714.md
```
