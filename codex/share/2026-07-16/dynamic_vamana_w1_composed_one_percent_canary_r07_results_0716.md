# Composed W1 1% Canary Result

## 结论

本报告组合 R05 DGAI、R06 OdinANN、R07 DiskANN stale-static control 与 R02 checkpoint-1 exact GT。三个系统结果来自多个严格隔离、fail-closed continuation attempt，不是一次无中断 controller run。结果只支持固定 W0 policy 下的 W1 1% replace-new canary，不构成 matched-Recall frontier，也不支持更高 churn 外推。

## Dynamic update 与可见性

| System/source | Ingestion(s) | Ingestion ops/s | Online-visible(s/ops/s) | Fresh or restart-visible(s/ops/s) |
|---|---:|---:|---|---|
| DGAI / R05 cp01-05 | 79.853 | 1001.844 | unsupported | 103.026 / 776.504 |
| OdinANN / R06 cp01-06 | 49.446 | 1617.919 | 49.449 / 1617.822 | 147.468 / 542.491 |

DGAI restart-visible 与 OdinANN online-visible 的语义不同，不作同列吞吐排名。DGAI 仅在 merge/publish 后由 fresh process 验证可见；OdinANN 同时提供 live online 与 save 后 fresh-process 证据。

## Device I/O、空间与内存

| System | Ingest R/W(B) | Publish R/W(B) | End-to-end R/W(B) | Persistent growth(B) | Peak RSS(B) | cgroup peak(B) |
|---|---|---|---|---:|---:|---:|
| DGAI | 40366260224/2300735488 | 13885784064/5461368832 | 54258987008/7762075648 | 0 | 3785252864 | 17766035456 |
| OdinANN | 45313896448/12129304576 | 24870457344/8192376832 | 78375845888/28545339392 | 8480140468 | 2148999168 | 10857242624 |

Clone 与 permission normalization 属于 preparation，不计入 ingestion 或 visibility 区间。OdinANN 的 persistent growth 包含 save 后 shadow/fresh-process layout；DGAI persistent growth 为其正式 attempt 观测值。

## Dynamic query stability

| System | Phase | L | Recall median[min,max] | QPS median | P99 median(us) | Mean I/O median |
|---|---|---:|---|---:|---:|---:|
| DGAI | pre_cp00 | 64 | 0.95150[0.95140,0.95160] | 1288.84 | 993.0 | 96.37 |
| DGAI | pre_cp00 | 128 | 0.98010[0.98000,0.98020] | 844.41 | 1390.0 | 155.61 |
| DGAI | post_cp01 | 64 | 0.95090[0.94980,0.95110] | 1253.20 | 1008.0 | 97.57 |
| DGAI | post_cp01 | 128 | 0.98030[0.98020,0.98030] | 859.28 | 1367.0 | 156.53 |
| OdinANN | pre_cp00 | 29 | 0.95072[0.95056,0.95085] | 1595.14 | 855.0 | 51.17 |
| OdinANN | pre_cp00 | 46 | 0.97981[0.97963,0.98000] | 1244.34 | 981.0 | 65.63 |
| OdinANN | post_cp01 | 29 | 0.94991[0.94964,0.95022] | 1617.36 | 804.0 | 51.10 |
| OdinANN | post_cp01 | 46 | 0.97933[0.97927,0.97934] | 1328.84 | 936.0 | 65.95 |

## DiskANN stale-static negative control

DiskANN 使用 immutable checkpoint-0 index 对 checkpoint-1 exact GT 查询。它允许返回 checkpoint-1 已删除 tag，不执行 update，也不参与动态 update throughput 排名。

| L | Repeat | Recall@10 | QPS | Reported tail(us/percentile) | Mean I/O | NVMe read(B) |
|---:|---:|---:|---:|---|---:|---:|
| 29 | 1 | 0.93600 | 319.89 | 6147.0 / P99.9 | 45.45 | 1861648384 |
| 29 | 2 | 0.93600 | 317.47 | 6542.0 / P99.9 | 45.45 | 1861648384 |
| 29 | 3 | 0.93600 | 344.13 | 6226.0 / P99.9 | 45.45 | 1861648384 |
| 53 | 1 | 0.96280 | 217.06 | 8551.0 / P99.9 | 68.16 | 2791673856 |
| 53 | 2 | 0.96280 | 221.18 | 8640.0 / P99.9 | 68.16 | 2791673856 |
| 53 | 3 | 0.96280 | 210.07 | 8638.0 / P99.9 | 68.16 | 2791673856 |

## Loader/runtime identity

DiskANN binary SHA256 为 `631fc53b4514fdac8325a7d789792ff6d19fb007e5442410898ec4a9505d4c3e`，ELF interpreter 为 `/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2`。全部 `10` 个直接 DT_NEEDED 均已解析；实验私有 `libtcmalloc.so.9.9.5` 固定到 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/build/gperftools-install/lib/libtcmalloc.so.9.9.5`，SHA256 为 `9035515aa26ebfaa2cf390291378e0ccba66175ba8291b92aa32e92f97a8b904`。正式 scope 以 ubuntu、CPU 0–23、NUMA node 0 和显式 `LD_LIBRARY_PATH` 运行。

## 证据索引与边界

机器可读 composed summary 为 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_r07/composed_summary.json`，逐点汇总为 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_r07/summary.tsv`，R05/R06 freezes、runtime manifest 与 loader tests 位于 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_r07/preflight`，DiskANN raw evidence 位于 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07`。本轮完成后停止，不自动执行更高 churn、DiskANN rebuild、Recall refinement、mixed workload、W2、DEEP 或 GIST。
