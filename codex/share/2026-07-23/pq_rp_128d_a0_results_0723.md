# PQ-RP-128D-A0：普通 PQ 导航的 Recall–Performance 边界

## 裁决

**`PASS-CHARACTERIZATION / KILL-PQ8 / HOLD-PQ16 / SATURATED-PQ32`。**

本轮只刻画边界，不提出新算法。8B PQ 的误差不能靠本轮范围内增大 `L` 经济地补回；16B 在 97%–99.6% Recall 区间存在显著但迅速变贵的恢复曲线；32B 从 `L=100` 起已基本贴住 Exact oracle。因而 P10 的 corridor drift 是实体现象，但在 SIFT128 上，新的 selective-exact 类机制若不能优于 **16B→32B 的普通表示升级**，没有独立算法身份。

## 控制与协议

- SIFT1M，官方 10K queries、官方 top-10 IDs，`K=10`；
- 同一份 819,204,096-byte Vamana/DiskANN 图，入口、最终 rerank、同步 I/O、单线程、`W=4` 均相同；
- 仅切换 PQ-8B、PQ-16B、PQ-32B 与 Exact navigation；
- `L={50,100,150,200,300}`，每个进程一次加载、200-query warm-up、连续执行五个 L；
- Recall 使用 repeat-1 返回 ID 重新对官方 truthset 计算；性能三次重复取中位数；
- Canary 的 PQ16 `L=100/150/200` 精确复现 P10 的 96.51%/98.44%/99.14%（1K），Exact `L=100` 为 99.76%。

完整协议见 [`EXPERIMENT_PLAN.md`](../../work/2026-07-23/pq_rp_128d_a0/EXPERIMENT_PLAN.md)，聚合表见 [`curve_summary.csv`](../../work/2026-07-23/pq_rp_128d_a0/results/curve_summary.csv)。

## 核心曲线

| 表示 | L=50 Recall / QPS | L=100 | L=150 | L=200 | L=300 |
|---|---:|---:|---:|---:|---:|
| PQ-8B | 67.228% / 207.93 | 79.614% / 122.55 | 85.607% / 86.36 | 89.080% / 66.12 | 92.966% / 45.77 |
| PQ-16B | 91.131% / 210.57 | 97.004% / 122.89 | 98.605% / 83.48 | 99.201% / 65.44 | 99.636% / 44.87 |
| PQ-32B | 98.311% / 201.11 | 99.633% / 116.20 | 99.823% / 81.45 | 99.889% / 63.09 | 99.924% / 42.75 |
| Exact | 98.971% / 187.27 | 99.742% / 109.25 | 99.848% / 76.88 | 99.901% / 59.47 | 99.924% / 40.40 |

| 表示 | 最大同 L gap | L=300 剩余 gap |
|---|---:|---:|
| PQ-8B | 31.743 pp | 6.958 pp |
| PQ-16B | 7.840 pp | 0.288 pp |
| PQ-32B | 0.660 pp | 0.000 pp |

## 恢复 1pp Recall 的边际代价

- PQ16 `L=50→100`：772 comparisons、8.3 reads、0.51 ms p50；
- PQ16 `100→150`：2,757 comparisons、30.8 reads、2.24 ms；
- PQ16 `150→200`：7,278 comparisons、83.3 reads、4.93 ms；
- PQ16 `200→300`：19,482 comparisons、228.7 reads、15.16 ms。

PQ32 在 `L=100` 已达 99.633%；再到 `L=150` 每 1pp 需要约 23,190 comparisons、260 reads 和 18.15 ms p50，之后更差。完整 CPU/I/O、p50/p95/p99、hops 与 bytes 见 [`marginal_cost.csv`](../../work/2026-07-23/pq_rp_128d_a0/results/marginal_cost.csv)。

## 内存与成本来源

| 表示 | 导航码常驻 | 额外全向量常驻 | 实测 peak RSS |
|---|---:|---:|---:|
| PQ-8B | 8 MB | 0 | 35.6 MiB |
| PQ-16B | 16 MB | 0 | 43.5 MiB |
| PQ-32B | 32 MB | 0 | 59.3 MiB |
| Exact | 16 MB | 512 MB | 532.6 MiB |

查询 scratch 未单列，因为 allocator 与 scratch-pool 的共享开销无法可靠剥离。SSD touched bytes 按 `4096*n_ios`，Exact 另计 `512*n_exact_nav_reads` 的 DRAM navigation bytes。

## 图与可复现材料

七张 PDF/PNG 曲线为 [`Recall–QPS`](../../work/2026-07-23/pq_rp_128d_a0/figures/fig1_recall_qps.pdf)、[`p50`](../../work/2026-07-23/pq_rp_128d_a0/figures/fig2_recall_p50.pdf)、[`p95`](../../work/2026-07-23/pq_rp_128d_a0/figures/fig3_recall_p95.pdf)、[`p99`](../../work/2026-07-23/pq_rp_128d_a0/figures/fig4_recall_p99.pdf)、[`comparisons`](../../work/2026-07-23/pq_rp_128d_a0/figures/fig5_recall_comparisons.pdf)、[`I/Os`](../../work/2026-07-23/pq_rp_128d_a0/figures/fig6_recall_ios.pdf) 与 [`bytes`](../../work/2026-07-23/pq_rp_128d_a0/figures/fig7_recall_bytes.pdf)。原始 gzip CSV、summaries、日志、manifests、命令与脚本均在 [`pq_rp_128d_a0/`](../../work/2026-07-23/pq_rp_128d_a0/)。

## 边界与下一步

- PQ8/PQ32 分别独立用 10% 随机样本训练；PQ16 复用 P10 artifact，微小差异不能只归因于 code bytes。
- SIFT1M 是低维整数视觉描述子，结论不能直接外推到现代高维语义 embedding。
- 没有“两个粗点之间遗漏明确拐点”的证据，因此未追加 midpoint。
- 下一步不应给 P10 打 selective-exact 后验补丁。若继续，应把 **16B→32B 普通 PQ 升级**作为强 baseline，并先在典型 768D/1024D 预生成 embedding 数据集做同类 A0；若仍饱和，则 KILL 该机制线并回到开放 idea-discovery。

## 实际耗时

Canary 搜索 276.11 s，完整 12 个进程 7,808.22 s；搜索总时长 **8,084.33 s（2 h 14 min 44 s）**。从 truthset manifest 落盘到最终聚合约 **2 h 24 min 30 s**。
