# Dynamic Vamana W1 CP20 trajectory R13 results

R12 composed closure已绑定；R13只从两个R12冻结CP10 clone创建fresh private clone，并仅应用master `[800000:1600000]` 的800K replacements。CP00、CP01、CP05、CP10及1M replay均未重跑。两个CP20 clone与DiskANN CP20 stale-static control全部PASS；完成后停止并等待最终轨迹评审。

执行边界保持可审计：首次`execution_manifest.json`在DGAI stage完整PASS后、首个query scope创建前因shared launcher capability变量名不匹配而保留为`stopped_failed/cp20_DGAI/exit=64`；`continuation_manifest.json`绑定该terminal identity，仅对DGAI执行query/freeze，再运行fresh OdinANN与DiskANN。两份manifest组成R13 closure，没有重做DGAI 800K update，也没有将首次execution伪装为单次成功。

## CP10→CP20增量

| 系统 | replacements | ingest s | ingest replacements/s | publish s | end-to-end s | end-to-end replacements/s | peak RSS GiB | apparent growth GiB | allocated growth GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DGAI | 800000 | 768.167 | 1041.441 | 93.840 | 863.787 | 926.155 | 4.60 | 0.000 | 0.000 |
| OdinANN | 800000 | 462.863 | 1728.372 | 254.204 | 721.354 | 1109.026 | 2.53 | 0.000 | 0.000 |

两种吞吐均从machine stage evidence重算：`ingest replacements/s = replacements / ingest wall time`；`end-to-end replacements/s = replacements / end-to-end wall time`。

| 系统 | phase | wall s | read GiB | write GiB | read bytes/replacement | write bytes/replacement |
|---|---|---:|---:|---:|---:|---:|
| DGAI | ingest | 768.167 | 380.881 | 30.708 | 511210.1 | 41215.9 |
| DGAI | publish | 93.840 | 16.879 | 5.086 | 22654.0 | 6826.7 |
| DGAI | end-to-end | 863.787 | 397.762 | 35.795 | 533866.6 | 48042.6 |
| OdinANN | ingest | 462.863 | 422.955 | 137.194 | 567681.0 | 184138.3 |
| OdinANN | publish | 254.204 | 29.835 | 7.629 | 40044.1 | 10240.1 |
| OdinANN | end-to-end | 721.354 | 460.420 | 152.453 | 617965.5 | 204618.4 |

DGAI按设计不支持publish前online visibility；OdinANN online与fresh visibility均PASS（wall分别为`0.005031s`与`4.152767s`）。两系统resource returncode均为0，OOM事件均为0。

## 动态查询完整轨迹（3次中位数）

| 系统 | checkpoint | L | Recall@10 | QPS | P99 us | mean I/O |
|---|---|---:|---:|---:|---:|---:|
| DGAI | cp00 | 64 | 0.95146 | 1260.75 | 1014.00 | 96.359 |
| DGAI | cp00 | 128 | 0.98015 | 874.52 | 1331.00 | 155.400 |
| DGAI | cp01 | 64 | 0.95128 | 1253.25 | 1010.00 | 97.417 |
| DGAI | cp01 | 128 | 0.98009 | 835.75 | 1371.00 | 154.234 |
| DGAI | cp05 | 64 | 0.94994 | 1245.81 | 1022.00 | 98.319 |
| DGAI | cp05 | 128 | 0.97851 | 849.83 | 1381.00 | 156.992 |
| DGAI | cp10 | 64 | 0.94781 | 1270.51 | 1001.00 | 97.731 |
| DGAI | cp10 | 128 | 0.97768 | 832.20 | 1385.00 | 155.003 |
| DGAI | cp20 | 64 | 0.94613 | 1235.72 | 1013.00 | 98.432 |
| DGAI | cp20 | 128 | 0.97634 | 827.91 | 1397.00 | 155.516 |
| OdinANN | cp00 | 29 | 0.95085 | 1609.04 | 817.00 | 51.325 |
| OdinANN | cp00 | 46 | 0.97991 | 1345.38 | 956.00 | 65.897 |
| OdinANN | cp01 | 29 | 0.95024 | 1628.83 | 802.00 | 51.440 |
| OdinANN | cp01 | 46 | 0.97924 | 1420.91 | 936.00 | 65.365 |
| OdinANN | cp05 | 29 | 0.94662 | 1666.78 | 780.00 | 51.575 |
| OdinANN | cp05 | 46 | 0.97819 | 1315.53 | 968.00 | 66.231 |
| OdinANN | cp10 | 29 | 0.94605 | 1267.56 | 1013.00 | 51.580 |
| OdinANN | cp10 | 46 | 0.97682 | 1168.69 | 1069.00 | 65.737 |
| OdinANN | cp20 | 29 | 0.94255 | 1712.27 | 742.00 | 51.400 |
| OdinANN | cp20 | 46 | 0.97431 | 1226.82 | 1044.00 | 65.837 |

## 动态更新成本完整轨迹

| 系统 | checkpoint | replacements | ingest replacements/s | end-to-end replacements/s | E2E read bytes/replacement | E2E write bytes/replacement |
|---|---|---:|---:|---:|---:|---:|
| DGAI | cp01 | 80000 | 990.894 | 766.066 | 678519.4 | 97007.0 |
| DGAI | cp05 | 320000 | 1002.963 | 841.515 | 557115.7 | 55193.3 |
| DGAI | cp10 | 400000 | 1037.142 | 874.544 | 550875.8 | 52818.8 |
| DGAI | cp20 | 800000 | 1041.441 | 926.155 | 533866.6 | 48042.6 |
| OdinANN | cp01 | 80000 | 1565.601 | 529.012 | 979744.4 | 356773.8 |
| OdinANN | cp05 | 320000 | 1721.295 | 865.601 | 682291.4 | 229931.3 |
| OdinANN | cp10 | 400000 | 1591.862 | 850.899 | 661892.4 | 221734.0 |
| OdinANN | cp20 | 800000 | 1728.372 | 1109.026 | 617965.5 | 204618.4 |

## DiskANN stale-static negative control

| checkpoint | L | median Recall@10 | median QPS | median reported tail us | median mean I/O |
|---|---:|---:|---:|---:|---:|
| cp00 | 29 | 0.9516 | — | — | — |
| cp00 | 53 | 0.9800 | — | — | — |
| cp01 | 29 | 0.9360 | — | — | — |
| cp01 | 53 | 0.9628 | — | — | — |
| cp05 | 29 | 0.8801 | — | — | — |
| cp05 | 53 | 0.9026 | — | — | — |
| cp10 | 29 | 0.8190 | 339.23 | — | — |
| cp10 | 53 | 0.8382 | 217.02 | — | — |
| cp20 | 29 | 0.7110 | 360.06 | 5884.00 | 45.450 |
| cp20 | 53 | 0.7258 | 232.77 | 8267.00 | 68.160 |

两个CP20 clone均已冻结；DiskANN仍是不更新的negative control，不参与动态更新吞吐排名。R13到此停止，不自动启动新实验。

机器汇总：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_cp20_trajectory_r13/summary.json`。
