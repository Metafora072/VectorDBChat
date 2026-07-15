# 三系统 SIFT10M Pilot：P1 F0 实测结果

**状态：** P1 F0 完成并停止；未启动 W0/W1、1% churn、20% churn、DEEP/GIST 或 Fresh-Ref。  
**范围：** 8M checkpoint-0 SIFT（从官方 BIGANN 前 10M 的 80/20 划分），10,000 queries，exact GT top-100。  
**目的：** 仅确认三套 artifact 能在统一 serving 约束下完成 F0 与产生可解析结果；这不是 matched-recall 的性能排名。

## 1. 先决条件与验收

* source/header/payload/canonical provenance 已通过；checkpoint-0 GT 的 10,000×100 IDs 均 active、distance finite/monotonic。
* 独立 brute-force audit 的 query 0 与 17 均与 GT top-100 完全一致，最大距离误差为 0。
* DiskANN 做到 result shape + active-ID membership；DGAI/OdinANN 是本轮获批的 `aggregate-only validation`，不能升级表述为逐 ID 独立审计。

## 2. F0 结果（实测）

| System | Build 参数 | Build wall | Build peak RSS | Index allocated | F0 query（10K） | Recall@10 | 验收 |
|---|---|---:|---:|---:|---:|---:|---|
| DiskANN | R64/L100/B1/M64/T24 | 30m50s | 14.9 GiB | 7.10 GiB | 4.80s, 2626.98 QPS | 0.9688 | shape + active-ID |
| DGAI | R32/L75/B1/M64/T24 | 40m02s | 132.3 GiB | 13.16 GiB | 5.34s, 9352.78 QPS | 0.9216 | aggregate-only |
| OdinANN | R96/L128/B32/M64/T24 | 24m47s | 10.7 GiB | 7.90 GiB | 1.56s, 10350.24 QPS | 0.9738 | aggregate-only |

查询阶段均回到 CPU 0--23、`membind=0`。DiskANN 的 mean latency 为 2904.57 µs、mean I/O 55.73；DGAI 为 824.44 µs、mean I/O 75.84；OdinANN 为 705.83 µs、mean I/O 61.52。它们的 R/L/PQ/beam 与 Recall 不匹配，**不得据此声称 QPS、I/O 或空间支配关系**。

## 3. DGAI OOM 与恢复

`p1r07` 的 DGAI 在 single-NUMA `membind=0` 下于 PQ refinement 被 OOM killer 终止；该失败 attempt 已保留。GPT 批准的一次 `p1r08` retry 保持算法参数不变，仅 build 使用 CPU 0--23 + `--interleave=0,1`、`MemoryMax=200 GiB` 和 6h watchdog；postprocess/query 仍为 node-0 serving policy。

该 retry 成功，build RSS 峰值为 132.3 GiB。故准确结论是：**DGAI 在单 NUMA 构建约束下 OOM；在本机 251 GiB 总 DRAM、build-only cross-NUMA exception 下可构建。** 该 exception 使 DGAI build wall time/DRAM 不能与 DiskANN/OdinANN 作严格横向 build-cost 比较。

## 4. 资源与记录边界

* 所有 source、index、TMP 与结果均在实验 NVMe；没有向系统盘写入实验产物。
* DGAI/OdinANN 的 resource JSON 成功记录了 elapsed、RSS、I/O 与 cgroup path；但新加的 `memory.events` 使用了只识别 `key:value` 的解析器，而该文件使用空格分隔，故 JSON 中为空对象。成功退出与 cgroup MemoryMax 启动时的直接核验说明本次未被 cgroup OOM；不过该字段记录实现有缺陷，**在任何后续 W0/W1 之前必须修复并做小 canary 验证**。
* 本轮只得到一个 search setting、单次重复和 aggregate-only 的两套结果；它不能支持系统优劣、解耦/耦合机制归因或论文 claim。

## 5. 请 GPT 审阅的决策

P1 的 readiness 目标已经达成。请决定是否：

1. 先修复 `memory.events` 记录并运行数秒级 canary，再按既有授权进入 slim W0；或
2. 先围绕 F0 的 recall mismatch 与 build-only exception 重新定义可比口径；或
3. 基于本轮结果停止该 Pilot。

在得到明确裁决前，Codex 不启动任何后续实验。
