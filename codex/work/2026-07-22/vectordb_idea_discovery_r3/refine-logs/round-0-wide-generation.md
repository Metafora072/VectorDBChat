# Round 0：宽域生成

从驻盘图/HNSW 放宽到整个 VectorDB/ANNS 后，按 query primitive、data semantics、global constraint、uncertainty、result objective 和 index guarantee 六条轴生成 14 个候选。禁止安全、恢复、权限、WAL/LSM 拼装，也禁止只换边评分、阈值或 beam。

初筛后最强三者为 capacity-constrained collective ANN、compact fresh-world distributional ANN、similarity-proportional sampling。MOVE 与 region certificate 作为边界机制进入 A0。
