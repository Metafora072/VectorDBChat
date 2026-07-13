# Dynamic Vamana Formal Atlas：W0/W1 耗时估算

**估算时间**：2026-07-14 02:26 CST

**状态**：只读估算；尚未下载 SIFT10M、构建正式索引或启动正式点。

## 结论

在门禁要求的“单 NVMe、无并行、dedicated cgroup、每点 3 次重复”下，完整 W0+W1 应按 **4–8 天墙钟** 预留；保守上界为 **10 天**。其中最不确定的是 10M 的动态 update trajectory（尤其 DGAI merge/reload）和 SIFT10M 的原始 BIGANN 文件下载/截取。不是 GPU 计算，允许无人值守连续运行，但不应承诺一两天完成。

在进入全矩阵前，建议先跑门禁规定的 SIFT10M F0 四系统 readiness。含下载、环境冻结、四次 build/load/query、resource collection 和 immutable snapshots，估计 **12–24 小时**；它会把后续排期误差从倍数级收敛到约 ±30%。

## 依据

准备阶段在同机、同 NVMe、0.8M active vectors 上的 build wall time 为：

| 系统 | SIFT1M | DEEP1M | GIST1M |
|---|---:|---:|---:|
| DiskANN | 3.4 min | 8.5 min | 51.0 min |
| Fresh-Ref | 6.0 min | 9.2 min | 19.3 min |
| DGAI | 7.4 min | 7.5 min | 18.6 min |
| OdinANN | 1.1 min | 0.9 min | 10.3 min |

对 SIFT10M/DEEP10M，正式 active set 是 8M，是上述 active 规模的 10 倍。按线性外推再加 I/O、PQ 和 layout 的 1.3–2.0 倍安全系数，静态 build 的合理预算如下：

| 阶段 | 串行墙钟估算 |
|---|---:|
| 下载/校验/截取 SIFT10M 与 environment manifest | 1–6 h（网络为主要不确定性） |
| SIFT10M 四系统 F0 build + load/query + snapshot | 8–16 h |
| DEEP10M 四系统 build + load/query + snapshot | 8–16 h |
| GIST1M 四系统在 formal cgroup 下重建/重验 | 2–4 h |
| 静态资产与 readiness 小计 | 19–42 h |

DEEP10M base 已在 NVMe（3.84 GB）；SIFT10M 尚未下载。当前 NVMe 约有 1.4 TB 可用，按准备阶段静态索引外推、独立 snapshot 与临时 rebuild 双份预留，容量足够，但实验必须继续串行。

## W0 点数与时长

W0 的原始 measurement point 数是：

```text
4 systems × 3 datasets × 4 query concurrencies × 4 search settings × 3 repeats
= 576 Recall–performance points
```

每个 `Tq × repeat` 可在同一新进程中扫描四个 search settings，因此为 144 次独立 cold-lifecycle sweep。以 10M 上每个 sweep 约 2–6 分钟、加上 page-cache reset、cgroup 创建、load、warm-up、I/O telemetry 和结果落盘，W0 预算为 **10–22 小时**。

## W1 点数与时长

每个动态系统在每个数据集、每次 repeat 都需要从 immutable checkpoint-0 snapshot 顺序走到 20% churn；SIFT10M/DEEP10M 的 checkpoint 分别为 400k、800k、1.6M replace-new operations，GIST1M 为 40k、80k、160k。

checkpoint query 的量为：

```text
3 dynamic systems × 3 datasets × 3 checkpoints × 4 concurrencies × 4 settings × 3 repeats
= 1,296 points
```

它们可合并为 324 个独立 checkpoint-query sweep，预算 **22–48 小时**。动态 trajectory 本身尚不能从 100-op smoke 可靠线性外推：正式 batch size、DGAI merge/reload、Fresh/Odin publish 行为都会主导时长。因此先按 **24–72 小时** 预留；F0 后应先各跑一个 5% pilot，再用实际 visible-update throughput 重新估算剩余 10%/20%。

DiskANN 还需 checkpoint-20 rebuild + publish；若按每个 dataset、每次 repeat 执行，则额外约 **10–24 小时**。W1 合计预算为 **56–144 小时**。

## 推荐执行切分

1. F0：SIFT10M 四系统 readiness（12–24 h），立即报告实际 build/query/GT/cgroup 数据。
2. 仅在 F0 全部可运行后，完成 DEEP10M 与 GIST1M formal assets（8–20 h）。
3. W0 全部 576 点（10–22 h），保存每次结果。
4. W1 先做每系统/数据集一次 5% pilot；确认 visible-update 语义、batch behavior 与 trajectory ETA 后，再执行三重复的 5/10/20% 全矩阵（56–144 h）。

因此从批准到 W0+W1 全部结束的现实排期是 **约 4–8 天**；若 SIFT 下载慢、DGAI 10M merge 远慢于预期或出现 artifact resource failure，可能接近 10 天。W2 不在此估算内，也不会自行启动。
