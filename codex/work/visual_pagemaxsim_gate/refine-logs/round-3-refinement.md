# Round 3 Refinement

## Problem Anchor

- **Bottom-line problem**: 在强 token merging 与量化之后，visual late-interaction candidate object 仍跨多个 4 KiB pages；需要只读取部分 token pages，就求出外层 Col-Bandit 所需的 MaxSim cells，并产生表示压缩 baseline 达不到的 page/storage/CPU/fidelity Pareto。
- **Must-solve bottleneck**: P1 证明 page oracle 存在，但 P2 的 single centroid-radius 把每页 token set 包成一个大球，upper bound 在真实 128D ColQwen2 embedding 上过松，导致读取 99.92%–100% pages。
- **Non-goals**: 不发明新的 outer bandit；不直接实现 async SSD engine；不把 heuristic page order 冒充 exact；不以只在 raw unmerged representation 上成立的收益复活系统；不把 PageMaxSim 改名为通用 DiskColBERT。
- **Constraints**: 4 KiB direct-I/O alignment；真实 ViDoRe/ColQwen2 candidate sets；必须计入 codebook、per-page metadata、padding、bound CPU；优先复用当前 CPU pilot；P3 仍未获批准。
- **Success condition**: 在 held-out queries 上，新的 feasible bound 对 raw int8 和 Light-style f9 int8 都能严格恢复请求 cells，并形成 full scan、single-ball、strong representation 与 single-vector baseline 均无法达到的新 Pareto；否则继续 Kill。

## Anchor and Simplicity Check

- 仍只替换 P2 exact synopsis；没有 approximate routing、scheduler claim 或 SSD engine。
- 本轮只修正 interval arithmetic 和 DRAM accounting，不新增方法组件。
- Dominant contribution 仍为 shared-codebook residual certificate。

## Changes Made

1. residual positive sum 使用 `s/(1-gamma)` 的严格反向误差上界。
2. 实际上界 FP32 query norm `Q_upper`；主 Cauchy bound和serving dot error均使用 `Q_upper*R`。
3. `A=sum|q_i mu_i|` 同样 outward upper；所有加法通过统一 `outward_add64`。
4. 明确停止条件 `L >= max_unread U`。
5. Stage A 固定 persistent FP16、startup-decoded FP32 DRAM codebook，并单列 query-state bytes。

## Final Execution-Ready Proposal

# Residual-Certified PageMaxSim: Stage A Synopsis Gate

## Method

对 raw-int8 与 Light-style f9-int8 分别训练 corpus-shared token codebook。测试 token 按 codeword ID 排序后装入真实 4 KiB pages；每页保存 `(codeword ID, token count, outward residual radius)`。page 是多个 residual balls 的并集：

```text
U(q,g) = max_k_present upper_serving_score(q, mu_k, R(g,k))
```

outer Col-Bandit、candidate set、representation、page cache 与 exact scan全部冻结。

## Serving Values

```text
x_hat  = normalize_fp32(dequantize_int8(code, fp16_scale))
q_hat  = normalize_fp32(serving query token)
mu_hat = persistent FP16 codeword decoded to FP32 at startup
```

exact scan 使用 serving FP32 accumulation。certificate construction与comparison使用FP64，但必须上界 serving FP32 score。

## Unified Outward Arithmetic

令：

```text
gamma64_n = n*u64/(1-n*u64), u64=2^-53
gamma32_n = n*u32/(1-n*u32), u32=2^-24
upper_positive_sum(fl_sum,n) = nextafter64(fl_sum/(1-gamma64_n), +inf)
outward_add64(a,b,...) = every addition followed by nextafter64(+inf)
```

FP32 decoded values提升到FP64。对 residual `e=x_hat-mu_hat`：

```text
s_fl = sum_128 e_i^2 in FP64
s_upper = upper_positive_sum(s_fl,127)
R64_upper = nextafter64(sqrt(s_upper),+inf)
R_group = max R64_upper
R32_disk = outward_cast_fp32(R_group)
```

`outward_cast_fp32(v)` 的 decoded FP32 若小于 `v`，再向 `+inf` nextafter。

对 query/codeword：

```text
d_fl = sum_128 q_i*mu_i in FP64
A_fl = sum_128 abs(q_i*mu_i) in FP64
A_upper = upper_positive_sum(A_fl,127)
d_upper = outward_add64(d_fl, gamma64_127*A_upper)

qnorm_sq_fl = sum_128 q_i^2 in FP64
Q_upper = nextafter64(sqrt(upper_positive_sum(qnorm_sq_fl,127)),+inf)

real_cauchy = Q_upper * R32_disk
serving_error = gamma32_128 * (A_upper + real_cauchy)

U(q,g,k) = outward_add64(d_upper, real_cauchy, serving_error)
U(q,g) = max_k_present U(q,g,k)
```

这同时覆盖实数域 residual contribution 与 serving FP32 dot accumulation 的误差。停止规则固定为：

```text
stop cell iff
max_observed_serving_FP32_score >= max_unread_page_U_FP64
```

相等时可停止。gate 输出 certificate violation count、最小 `U-serving_page_max`、最小 stopping margin；violation非零视为实现错误。

## Codebook and Held-out Protocol

- 额外编码256个与现有64 replay documents不重叠的ViDoRe pages。
- raw/f9分别训练各自 codebook，每点只计对应表。
- `sklearn KMeans(random_state=20260712,n_init=10,max_iter=300,tol=1e-4,algorithm="lloyd")`，normalized vector上的Euclidean distance。
- Stage A K={64,256}；记录occupancy、empty/singleton、train/test residual gap。
- 只有f9安全跳页才允许Stage B K=1024。

## Actual Metadata and Access Model

Stage A 固定 optimistic **DRAM-resident** control plane：

```text
persistent:
  64 B header
  K*128*2 B FP16 codebook
  8 B/document offset table
  8 B/page headers
  8 B/(page,codeword) pair
  4 KiB final alignment

DRAM:
  K*128*4 B startup-decoded FP32 codebook
  full offset/page/pair tables

query state:
  Q*K*8 B FP64 q-codeword bounds
  active-cell lower bounds/status
  page priority state
```

persistent、DRAM与query state分别报告。pair lists无额外I/O但绝不免费；若此最有利模型仍失败就Kill，不设计disk synopsis。

## Attribution and Cost

四层分解：single-ball、multi-ball L2、exact-group/page envelope（零slack endpoint）、maxima-page oracle。另报true-max page已读后仍false-threatening pages。

执行只比较 sequential 与 fixed best-upper-bound-first，不优化scheduler。完整点为：

```text
(pages/query,
 persistent data+synopsis bytes,
 DRAM control-plane bytes,
 query-state bytes,
 total online CPU/query,
 ranking fidelity)
```

CPU包括query-codebook GEMM、decode/lookup、bound materialization、priority、exact scan。报告0.5–100us/page latency crossover，并标出旧f9约4.47us/page参考点。

## Two-Level Decision

### Stage A: K=64/256

必须同时在held-out raw-int8与f9-int8运行。立即Kill条件：

- safety violation非零（先修实现再裁决机制）；
- f9-int8仍读100%页面；
- multi-ball到exact-page envelope的residual-direction gap仍解释主要failure；
- 计入persistent/DRAM/query-state/total CPU后，在相关page-cost curve上被f9 full scan支配。

### Stage B: K=1024

仅当Stage A f9已安全跳页且形成非支配信号时运行。通过只表示可请求P3，不批准系统、论文或architecture review。

## Closest-Work Boundary

Col-Bandit只解决outer cells；PLAID/WARP已有centroid/residual机制。唯一候选delta是outward-safe physical 4 KiB page admission。正结果后、请求P3前必须核实PLAID/WARP是否已有等价exact residual/page skipping；等价则不声称novelty。

## Compute

CPU-only：额外编码约35分钟，K=64/256训练与replay约10–30分钟。GPU/P3/system implementation均为0。
