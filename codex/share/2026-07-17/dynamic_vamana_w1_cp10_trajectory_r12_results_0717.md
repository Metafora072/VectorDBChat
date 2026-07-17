# Dynamic Vamana W1 CP10 trajectory R12 results

R10+R11 composed CP05 closure已绑定；R12仅从两个R10冻结CP05 clone新建private clone，并应用master `[400000:800000]` 的400K replacements。CP00、CP01、CP05和1M replay均未重跑。

执行边界保持可审计：首次`execution_manifest.json`在DGAI stage PASS后、首个query启动前因query-unit命名被控制面门禁拒绝，保留为`stopped_failed`；`continuation_manifest.json`严格绑定该terminal identity、PASS stage、空query目录和未改变的checkpoint state，只读完成DGAI query/freeze，并执行fresh OdinANN与DiskANN，最终状态为`complete`。两份manifest组成R12 closure，未将首次execution伪装为单次成功。

## CP05→CP10增量

| 系统 | replacements | ingest s | ingest replacements/s | publish s | end-to-end s | end-to-end replacements/s | peak RSS GiB | apparent growth GiB | allocated growth GiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DGAI | 400000 | 385.675 | 1037.142 | 69.909 | 457.381 | 874.544 | 4.02 | 0.000 | 0.000 |
| OdinANN | 400000 | 251.278 | 1591.861 | 213.702 | 470.091 | 850.899 | 2.29 | 0.000 | 0.000 |

以上两种吞吐均由machine stage evidence重新计算：`ingest replacements/s = replacements / ingest wall time`，`end-to-end replacements/s = replacements / end-to-end wall time`。

| 系统 | phase | read GiB | write GiB |
|---|---|---:|---:|
| DGAI | ingest | 189.715 | 14.590 |
| DGAI | publish | 15.500 | 5.086 |
| DGAI | end-to-end | 205.217 | 19.677 |
| OdinANN | ingest | 211.608 | 67.343 |
| OdinANN | publish | 27.337 | 7.630 |
| OdinANN | end-to-end | 246.574 | 82.602 |

DGAI按设计不支持publish前online visibility；OdinANN online probe在约0.006秒内PASS，publish/reload后的fresh probe同样PASS。两系统resource returncode均为0，OOM/oom_kill/oom_group_kill均为0。

## 动态查询完整轨迹（3次中位数）

| 系统 | checkpoint | L | Recall@10 | QPS | P99 us |
|---|---|---:|---:|---:|---:|
| DGAI | cp00 | 64 | 0.9515 | 1260.75 | 1014.00 |
| DGAI | cp00 | 128 | 0.9801 | 874.52 | 1331.00 |
| DGAI | cp01 | 64 | 0.9513 | 1253.25 | 1010.00 |
| DGAI | cp01 | 128 | 0.9801 | 835.75 | 1371.00 |
| DGAI | cp05 | 64 | 0.9499 | 1245.81 | 1022.00 |
| DGAI | cp05 | 128 | 0.9785 | 849.83 | 1381.00 |
| DGAI | cp10 | 64 | 0.9478 | 1270.51 | 1001.00 |
| DGAI | cp10 | 128 | 0.9777 | 832.20 | 1385.00 |
| OdinANN | cp00 | 29 | 0.9508 | 1609.04 | 817.00 |
| OdinANN | cp00 | 46 | 0.9799 | 1345.38 | 956.00 |
| OdinANN | cp01 | 29 | 0.9502 | 1628.83 | 802.00 |
| OdinANN | cp01 | 46 | 0.9792 | 1420.91 | 936.00 |
| OdinANN | cp05 | 29 | 0.9466 | 1666.78 | 780.00 |
| OdinANN | cp05 | 46 | 0.9782 | 1315.53 | 968.00 |
| OdinANN | cp10 | 29 | 0.9461 | 1267.56 | 1013.00 |
| OdinANN | cp10 | 46 | 0.9768 | 1168.69 | 1069.00 |

## DiskANN stale-static negative control

| checkpoint | L | median Recall@10 | median QPS |
|---|---:|---:|---:|
| cp00 | 29 | 0.9516 | — |
| cp00 | 53 | 0.9800 | — |
| cp01 | 29 | 0.9360 | — |
| cp01 | 53 | 0.9628 | — |
| cp05 | 29 | 0.8801 | — |
| cp05 | 53 | 0.9026 | — |
| cp10 | 29 | 0.8190 | 339.23 |
| cp10 | 53 | 0.8382 | 217.02 |

两个CP10 clone均已冻结为后续CP20只读source；DiskANN仍是不更新的negative control，不参与动态更新吞吐排名。CP20保持HOLD。

机器汇总：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_w1_cp10_trajectory_r12/summary.json`。
