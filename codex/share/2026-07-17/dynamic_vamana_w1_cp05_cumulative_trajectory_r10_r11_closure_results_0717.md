# Dynamic Vamana W1 CP05 R10 + R11 Composed Closure

## 裁决

本closure由两个不可混同的run组成：R10提供已接受的DGAI/OdinANN replay与formal `CP00→CP01→CP05`；R11仅提供DiskANN冻结CP00 index对CP05 GT的stale-static negative control。R10仍保持`stopped_failed`，没有被伪装为单次完整成功。

## Dynamic update成本（R10）

| System | Stage | Replacements | Ingest s | Repl/s | E2E read GiB | E2E write GiB | Peak RSS GiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| DGAI | CP01 | 80,000 | 80.735 | 990.894 | 50.554 | 7.228 | 3.528 |
| DGAI | CP05 | 320,000 | 319.055 | 1002.963 | 166.033 | 16.449 | 3.944 |
| OdinANN | CP01 | 80,000 | 51.099 | 1565.601 | 72.997 | 26.582 | 1.992 |
| OdinANN | CP05 | 320,000 | 185.907 | 1721.295 | 203.339 | 68.525 | 2.130 |

## Dynamic query（R10）

| System | Checkpoint | L | Median Recall@10 | Median QPS | Median P99 us | Median mean I/O |
|---|---:|---:|---:|---:|---:|---:|
| DGAI | CP00 | 64 | 0.951460 | 1260.750 | 1014.000 | 96.359 |
| DGAI | CP00 | 128 | 0.980150 | 874.520 | 1331.000 | 155.400 |
| DGAI | CP01 | 64 | 0.951280 | 1253.250 | 1010.000 | 97.417 |
| DGAI | CP01 | 128 | 0.980090 | 835.750 | 1371.000 | 154.234 |
| DGAI | CP05 | 64 | 0.949940 | 1245.810 | 1022.000 | 98.319 |
| DGAI | CP05 | 128 | 0.978510 | 849.834 | 1381.000 | 156.992 |
| OdinANN | CP00 | 29 | 0.950850 | 1609.040 | 817.000 | 51.325 |
| OdinANN | CP00 | 46 | 0.979910 | 1345.380 | 956.000 | 65.897 |
| OdinANN | CP01 | 29 | 0.950240 | 1628.830 | 802.000 | 51.440 |
| OdinANN | CP01 | 46 | 0.979240 | 1420.910 | 936.000 | 65.365 |
| OdinANN | CP05 | 29 | 0.946620 | 1666.780 | 780.000 | 51.575 |
| OdinANN | CP05 | 46 | 0.978190 | 1315.530 | 968.000 | 66.231 |

## DiskANN stale-static trajectory（R11 closure）

| Checkpoint | L | Median Recall@10 |
|---|---:|---:|
| CP00 | 29 | 0.951600 |
| CP00 | 53 | 0.980000 |
| CP01 | 29 | 0.936000 |
| CP01 | 53 | 0.962800 |
| CP05 | 29 | 0.880100 |
| CP05 | 53 | 0.902600 |

R11使用accepted P1R07 DiskANN base，`L={29,53}`、`Tq=1`、每点3次；结果形状、sentinel、top-10唯一性、NVMe read、OOM/fatal和base content/mode preservation均通过。stale结果允许包含CP05已删除ID，不与动态更新吞吐量排名。

## 证据边界

机器可读closure：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_cp05_diskann_closure_r11/closure_manifest.json`。R10 stop与post-R11 preservation均PASS；R10 dynamic evidence与frozen clones已重新验证且未被R11修改。CP10/CP20继续HOLD。
