# Dynamic Vamana W1 Checkpoint-1 GT 恢复结果

## 结论

R02 的 checkpoint-1 exact ground truth 恢复门禁全部通过。恢复流程未修改 DiskANN 的 KNN(K-Nearest Neighbors，K 近邻) 计算实现，而是先生成 location ID truthset，再通过冻结的 `active_cp01.tags.bin` 执行外部 tag 映射。最终 truthset 已原子发布，后续 DGAI 与 OdinANN 的 80K 更新实验可以在同一全局锁内继续。

## 恢复方法与证据

CP01 复用审计保持原目录只读，并完成 trace 重验证、全部 8,000,000 行 active vector 与 frozen corpus/tag 映射的流式语义重建，以及固定 seed 的抽样核验。由于父 execution manifest 在 CP01 生成前写入，不含第一次执行的逐文件 CP01 hash，本报告保留该历史证据缺口，并使用完整语义重建作为补偿证据。

GT 流程依次通过 synthetic tag-0 回归、checkpoint-0 逐字节一致性回归、query 7150 完整 top-100 审计、完整 checkpoint-1 truthset 验证，以及失败 GT 对比。除 query 7150 外，其余 9,999 行与旧失败文件逐字节一致；query 7150 原有 99 个有效 pair 均被保留，并恢复合法 tag 0。全部计算日志均未出现 `WARNING: found less than k GT entries`。

## 时间与空间

| 阶段 | Wall time(s) | Peak process-tree RSS(B) | cgroup memory peak(B) | Peak allocated(B) |
|---|---:|---:|---:|---:|
| R02 GT regressions 与完整恢复 | 127.504 | 20570230784 | 20660887552 | 49672192 |

该资源统计包含 synthetic、checkpoint-0、query 7150 与完整 checkpoint-1 GT，不与动态系统 update cost 比较。

## 发布边界

最终 GT 位于 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/groundtruth/sift10m/w1_r02/gt_cp01`，其 SHA256 为 `4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28`。恢复仅授权继续当前 W1 R02 的 DGAI、OdinANN 与 DiskANN stale-static control，不授权更高 churn、W2 或其他 workload。
