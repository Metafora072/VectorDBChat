# CPU/NVMe A0 Kill 实验报告

所有实验均在本机 CPU 上运行，未训练模型、未使用 GPU。代码和 JSON 结果位于本目录。

## A0-1：MOVE / migration order envelope

脚本：`move_a0.py`
结果：`move_a0_results.json`

数据为 MovieLens-20M 子集，10K users、5K items，rank-32 SVD；依次迁移到 85%/90%/95%/100% 观测矩阵表示。

| 阶段 | kNN overlap | IVF-cell stay | PQ-cell stay | top-k unchanged | sound envelope p50 | sound envelope p95 |
|---|---:|---:|---:|---:|---:|---:|
| 85%→90% | 0.856 | 0.931 | 0.715 | 0.314 | 36.75× | 59.97× |
| 90%→95% | 0.847 | 0.942 | 0.639 | 0.217 | 47.00× | 86.05× |
| 95%→100% | 0.894 | 0.966 | 0.773 | 0.350 | 17.25× | 40.90× |

简单 margin certificate 的认证率为 0。尽管 stale top-2k recall 为 0.971–0.992，sound candidate envelope 已大到失去 ANN 价值。**KILL**。

## A0-2：Region certificate tightness

脚本：`region_certificate_a0.py`
结果：`region_certificate_a0_results.json`

100K 个 128D 合成向量，128 coarse cells，进一步划为 512 subcells。比较 exact top-k threshold 与 cell lower bound。

| 粒度 | p50 扫描比例 | lower bound 为 0 的 cell 比例 |
|---|---:|---:|
| coarse cell | 100.0% | 89.2% |
| subcell | 99.998% | 69.7% |

高维 ball/box bound 几乎不能排除区域。继续加层只是在建另一棵高成本 exact index。**KILL**。

## A0-3：Capacity collective candidate expansion

脚本：`capacity_ann_a0.py`
结果：`capacity_ann_a0_results.json`

MovieLens SVD，batch=512，capacity=1/2/4。top-1 collision 率为 49%。相对 uniform top-L，Hall-guided expansion 的 candidate-edge 节省为 12.2%/44.0%/35.6%，assignment regret 均低于 0.18%；random workload 亦有 28.7%/46.7% 节省。

现象门通过，但实现只在预先计算的完整相似矩阵上数候选边，没有证明实际 ANN oracle calls 或 wall-clock 优势。更重要的是，它被 SIGMOD 2008 NIA/IDA 与 STOC 2014 ANN-assisted matching 直接覆盖。**KILL-NOVELTY**。

## A0-4：Compact fresh-world distributional ANN

脚本：`distributional_a0.py`、`distributional_hnsw_a0.py`
结果：`distributional_a0_scale20k_results.json`、`distributional_hnsw_a0_results.json`、`distributional_hnsw_a0_alpha02_results.json`、`distributional_hnsw_a0_alpha04_results.json`

设置：20K objects，Gaussian compact posterior，fresh-world max-of-5，256 queries（alpha sweep 为 64 queries）；exact full-world 为 ground truth。HNSW-UCB 使用 `(d+1)` augmented vector，mean baseline 在均值索引上按与 UCB 相同 candidate count over-fetch。

### Exact UCB 的选择性

| uncertainty α | exact UCB p50 candidates | p95 candidates | 占 20K 的 p50 |
|---:|---:|---:|---:|
| 0.1 | 54.5（HNSW run）/约 63（offline） | 468 / 371 | 0.27–0.32% |
| 0.2 | 2,239.5 | 3,751.7 | 11.20% |
| 0.4 | 7,365 | 8,553 | 36.83% |

### 实际 HNSW 结果

| α | HNSW-UCB world Recall@10 | matched mean-overfetch | UCB gain | 结论 |
|---:|---:|---:|---:|---|
| 0.1 | 0.99219 | 0.98789 | +0.00430 | 可靠但收益太小；p95 候选略超 50k gate |
| 0.2 | 0.81563 | 0.98594 | −0.17031 | approximate UCB frontier 严重漏项 |
| 0.4 | 0.69531 | 0.45000 | +0.24531 | 两者均不可用，exact envelope 已近扫描 |

`α=0.1` 时单查询 UCB 索引约 1.409 ms，mean 索引约 1.134 ms；没有速度优势。更关键的是，在 uncertainty 真正改变 top-k 时，精确 UCB tail 极宽；HNSW 若提前停止则 theorem 不再适用。

预注册 A0 gates：world Recall≥0.99、p95 candidates≤`50·k`（本实验为 500）、相对 matched mean-overfetch 至少 +0.10 Recall。没有一个 uncertainty regime 同时通过三门。**KILL-MECHANISM**。

## 总资源预算

- CPU：单机 16–32 核足够；主要脚本可在数分钟至数小时完成。
- 内存：20K/100K pilot 约 4–32 GB；无需 GPU。
- NVMe：代码、MovieLens 缓存、向量与 JSON 远低于 20 GB；扩展到 1M 也可控制在 100 GB 内。
- 没有训练深度模型；embedding/SVD 均预生成或 CPU 构造。

## A0 总裁决

四条路线分别在必要现象、bound tightness、novelty、效率—保证兼容性上被击杀。当前没有值得进入完整论文实验矩阵的候选。
