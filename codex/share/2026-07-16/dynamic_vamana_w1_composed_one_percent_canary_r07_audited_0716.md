# Audited Composed W1 1% Canary Result

本报告是 R07 composed result 的术语与计量口径审计版。原始报告及机器证据保持不变。结果组合自 R05 DGAI、R06 OdinANN、R07 DiskANN stale-static control 和 R02 exact GT，来自多个隔离的 continuation attempt，不是一次无中断 controller run。

## Replacement throughput 与 visibility

每条 replacement record 包含一次 delete 和一次 insert；下表分母均为 80,000 条 replacement，不使用含义不明确的 `ops/s`。Primitive mutation throughput 仅作为 `2 × replacements/s` 的派生值。

| System | Ingestion (s) | Replacements/s | Primitive mutations/s | Online-visible | Fresh/restart-visible |
|---|---:|---:|---:|---|---|
| DGAI | 79.852742 | 1001.844 | 2003.688 | unsupported | 103.025837 s / 776.504 replacements/s |
| OdinANN | 49.446224 | 1617.919 | 3235.838 | 49.449186 s / 1617.822 replacements/s | 147.467815 s / 542.491 replacements/s |

DGAI restart-visible 与 OdinANN online-visible/fresh-visible 的语义不同，不能作为同一 visibility throughput 直接排名。OdinANN/DGAI ingestion ratio `1.615×` 只描述本次两个完整冻结系统配置，不归因为某个单独机制。

## Device I/O 与 persistent layout

| System | Ingest R/W (B) | Publish R/W (B) | End-to-end R/W (B) | Apparent persistent growth (B) | Allocated persistent growth (B) |
|---|---|---|---|---:|---:|
| DGAI | 40,366,260,224 / 2,300,735,488 | 13,885,784,064 / 5,461,368,832 | 54,258,987,008 / 7,762,075,648 | 0 | 0 |
| OdinANN | 45,313,896,448 / 12,129,304,576 | 24,870,457,344 / 8,192,376,832 | 78,375,845,888 / 28,545,339,392 | 8,480,140,468 | 8,480,153,600 |

DGAI 的 apparent/allocated delta 为 0 只表示正式 attempt 的最终目录 size 没有增长，不能解释为没有设备写入；其 end-to-end device writes 为 7,762,075,648 B。OdinANN end-to-end writes 约为 DGAI 的 `3.678×`，同样只描述完整配置。

## Dynamic P99

| System | Phase | L | Recall@10 median | QPS median | P99 median (us) | Mean I/O median |
|---|---|---:|---:|---:|---:|---:|
| DGAI | pre CP00 | 64 | 0.95150 | 1288.84 | 993 | 96.37 |
| DGAI | pre CP00 | 128 | 0.98010 | 844.41 | 1390 | 155.61 |
| DGAI | post CP01 | 64 | 0.95090 | 1253.20 | 1008 | 97.57 |
| DGAI | post CP01 | 128 | 0.98030 | 859.28 | 1367 | 156.53 |
| OdinANN | pre CP00 | 29 | 0.95072 | 1595.14 | 855 | 51.17 |
| OdinANN | pre CP00 | 46 | 0.97981 | 1244.34 | 981 | 65.63 |
| OdinANN | post CP01 | 29 | 0.94991 | 1617.36 | 804 | 51.10 |
| OdinANN | post CP01 | 46 | 0.97933 | 1328.84 | 936 | 65.95 |

## DiskANN P99.9 stale-static control

DiskANN 使用 CP00 immutable index 对 CP01 exact GT 查询，不执行 update，不参与 replacement throughput 或 visibility 排名。其 binary 输出的是 P99.9，不与上表动态系统 P99 合列。

| L | Recall@10 | QPS median | P99.9 median (us) | Mean I/O |
|---:|---:|---:|---:|---:|
| 29 | 0.93600 | 319.89 | 6226 | 45.45 |
| 53 | 0.96280 | 217.06 | 8638 | 68.16 |

相对冻结 CP00 点，stale DiskANN 在 L29/L53 的 Recall@10 分别下降 0.0156/0.0172，证明 CP01 GT 能捕捉 stale-index 退化。

## 后续解释边界

后续 CP05/CP10/CP20 trajectory 的主要分析单位是同一系统自身随累计 churn 的归一化 slope：replacement throughput、device bytes/replacement、apparent/allocated space、Recall/QPS/P99 和 visibility cost。跨系统绝对值只作次要完整配置描述。当前数据不支持 matched-Recall churn frontier、更高 churn 外推、mixed workload、DiskANN rebuild 或单一架构机制归因。
