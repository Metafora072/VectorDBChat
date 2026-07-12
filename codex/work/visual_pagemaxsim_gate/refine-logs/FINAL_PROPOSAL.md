# Research Proposal: Residual-Certified PageMaxSim

## Problem Anchor

- **Bottom-line problem**: 在强 token merging 与量化之后，visual late-interaction candidate object 仍跨多个 4 KiB pages；需要只读取部分 token pages，就求出外层 Col-Bandit 所需的 MaxSim cells，并产生表示压缩 baseline 达不到的 page/storage/CPU/fidelity Pareto。
- **Must-solve bottleneck**: P1 证明 page oracle 存在，但 P2 single centroid-radius 在真实 ColQwen2 embedding 上过松，导致读取 99.92%–100% pages。
- **Non-goals**: 不发明 outer bandit；不实现 async SSD engine；不把 heuristic 冒充 exact；不接受 raw-only 收益；不复活 generic DiskColBERT。
- **Constraints**: 4 KiB alignment；真实 ViDoRe/ColQwen2 candidates；计入 persistent/DRAM/query-state/CPU；P3 未获批准。
- **Success condition**: raw-int8 与 f9-int8 均取得 zero-violation exact page skip，并在完整成本下形成非支配点；否则 Kill。

## Method Thesis

使用 representation-specific corpus-shared codebook 与 per-page `(codeword ID, outward residual radius)` 列表，将一个 page 表示为多个小 residual balls 的并集，作为 exact physical-page admission certificate。

## Frozen Pipeline

冻结 official ColQwen2、Light-style f9、per-token int8、mean-vector top-32 candidates、Col-Bandit `alpha=0.2`、4 KiB serializer 与 serving FP32 MaxSim。新机制只有 synopsis；k-means、layout order 与page order均非贡献。

## Exact Serving Certificate

```text
x_hat  = normalize_fp32(dequantize_int8(code, fp16_scale))
q_hat  = normalize_fp32(serving query token)
mu_hat = persistent FP16 codeword decoded to FP32 at startup
```

exact scan 使用固定 FP32 accumulation。certificate 使用 FP64 outward arithmetic 上界相同 serving score。

定义：

```text
gamma64_n = n*u64/(1-n*u64), u64=2^-53
gamma32_n = n*u32/(1-n*u32), u32=2^-24
upper_positive_sum(s,n) = nextafter64(s/(1-gamma64_n),+inf)
```

对 `e=x_hat-mu_hat`：

```text
s_upper = upper_positive_sum(sum_fp64(e_i^2),127)
R64 = nextafter64(sqrt(s_upper),+inf)
R32_disk = outward_cast_fp32(max_group R64)
```

对 query/codeword：

```text
A_upper = upper_positive_sum(sum_fp64(abs(q_i*mu_i)),127)
d_upper = outward_add64(sum_fp64(q_i*mu_i),
                        outward_mul64(gamma64_127,A_upper))
Q_upper = nextafter64(
    sqrt(upper_positive_sum(sum_fp64(q_i^2),127)),+inf)
real_cauchy = outward_mul64(Q_upper,R32_disk)
serving_error = outward_mul64(
    gamma32_128,
    outward_add64(A_upper,real_cauchy))
U(q,g,k) = outward_add64(d_upper,real_cauchy,serving_error)
U(q,g) = max_k_present U(q,g,k)
```

每个正值乘法和加法都向 `+inf` round。停止条件：

```text
max_observed_serving_FP32_score >= max_unread_page_U_FP64
```

输出 violation count、最小 page margin、最小 stopping margin；任何 violation 先归为实现错误。

## Codebook Protocol

- 额外256个与test 64 documents不重叠的ViDoRe pages只用于训练。
- raw/f9分别训练自己的codebook。
- `KMeans(random_state=20260712,n_init=10,max_iter=300,tol=1e-4,algorithm="lloyd")`。
- Stage A仅K={64,256}；f9已有安全跳页才允许K=1024。
- 报告occupancy、empty/singleton、train/test residual gap。

## Actual Control Plane

Persistent image实际写出并4 KiB对齐：64B header、FP16 codebook、document/page offsets、8B `(ID,count,FP32 radius)` pairs。Stage A采用乐观的DRAM-resident模型：startup将codebook解码为FP32，全部pair tables常驻。

分别报告：

- persistent file `st_size`；
- decoded FP32 codebook和pair-table DRAM；
- `Q*K*8` query-codeword table；
- active cells与page-priority query state。

## Attribution and Execution

四层分解：old single-ball、multi-ball L2、exact-group/page envelope、maxima-page oracle；另报true-max page已读后的false-threatening pages。

只比较sequential与fixed best-upper-bound-first。CPU计入query-codebook GEMM、pair lookup、bound materialization、priority和exact scan。

配置点：

```text
(pages/query,
 persistent data+synopsis bytes,
 DRAM control-plane bytes,
 query-state bytes,
 total online CPU/query,
 ranking fidelity)
```

报告0.5–100us/page crossover，并标出旧f9约4.47us/page参考点。

## Stage A Decision

立即停止条件：

- certificate violation非零：修实现，不能裁决机制；
- f9-int8仍读100%页面：机制Kill；
- multi-ball到exact-page的residual-direction gap主导：机制Kill；
- 完整成本曲线被f9 full scan支配：机制Kill。

只有这些条件均未触发才允许K=1024。Stage B通过也只允许请求P3，不批准architecture、system或paper claim。

## Closest-Work Boundary

Col-Bandit解决outer cell elimination；PLAID/WARP已有centroid/residual primitives。唯一候选增量是outward-safe 4 KiB physical-page admission。任何正结果在请求P3前必须核实PLAID/WARP是否已有等价 exact residual/page skipping。

## Compute

CPU-only：额外编码约35分钟；K=64/256训练与replay约10–30分钟。GPU、P3、系统实现均为0。
