# Round 2 Refinement

## Problem Anchor

- **Bottom-line problem**: 在强 token merging 与量化之后，visual late-interaction candidate object 仍跨多个 4 KiB pages；需要只读取部分 token pages，就求出外层 Col-Bandit 所需的 MaxSim cells，并产生表示压缩 baseline 达不到的 page/storage/CPU/fidelity Pareto。
- **Must-solve bottleneck**: P1 证明 page oracle 存在，但 P2 的 single centroid-radius 把每页 token set 包成一个大球，upper bound 在真实 128D ColQwen2 embedding 上过松，导致读取 99.92%–100% pages。
- **Non-goals**: 不发明新的 outer bandit；不直接实现 async SSD engine；不把 heuristic page order 冒充 exact；不以只在 raw unmerged representation 上成立的收益复活系统；不把 PageMaxSim 改名为通用 DiskColBERT。
- **Constraints**: 4 KiB direct-I/O alignment；真实 ViDoRe/ColQwen2 candidate sets；必须计入 codebook、per-page metadata、padding、bound CPU；优先复用当前 CPU pilot；P3 仍未获批准。
- **Success condition**: 在 held-out queries 上，新的 feasible bound 对 raw int8 和 Light-style f9 int8 都能严格恢复请求 cells，并形成 full scan、single-ball、strong representation 与 single-vector baseline 均无法达到的新 Pareto；否则继续 Kill。

## Anchor Check

- 仍只替换 P2 失败的 exact page synopsis，不修改 outer algorithm 或 representation。
- FP64 interval-style arithmetic 与 DRAM access model 是执行规范，不是新增贡献。
- 不接受用 approximate page budget、learned router 或 disk metadata engine扩大问题。

## Simplicity Check

- Dominant contribution 仍只有 shared-codebook residual certificate。
- Scheduler、k-means、codebook 与 numerical interval 均是复用/正确性工具。
- 首轮只做 K=64/256；f9 无安全跳页就立即停止。

## Changes Made

1. 将 certificate construction/evaluation 改为 FP64，并显式上界 serving FP32 dot error；FP32 radius 只以 outward cast 序列化。
2. 冻结全部 synopsis 为 DRAM-resident optimistic control plane，pair lists 不再被隐式当作免费 metadata。
3. raw-int8 与 f9-int8 分别训练 codebook，固定 k-means 参数。
4. `group oracle` 重命名为 `exact-group/page envelope`。
5. 固定五维 cost tuple 与 page-touch crossover 展示范围。

## Revised Proposal

# Research Proposal: Residual-Certified PageMaxSim

## Method Thesis

一个 corpus-shared decoded-FP16 codebook 加 per-page `(codeword ID, outward residual radius)` 列表，能否以小型 DRAM control plane 为强压缩 visual late-interaction 提供 exact physical-page admission control。

## Certified Serving Semantics

```text
x_hat = normalize_fp32(dequantize_int8(code, fp16_scale))
q_hat = normalize_fp32(serving query token)
mu_hat = FP16 codeword decoded exactly into FP32
```

exact page scan 使用 serving FP32 dot accumulation；certificate 必须上界该 serving score，而不仅是实数内积。

### Offline outward residual

将 `x_hat`、`mu_hat` 精确提升为 FP64。二者是 FP32 值，因此差值和乘积可在 FP64 中高精度表示。对每个 residual `e=x_hat-mu_hat`：

```text
s = sum_i e_i^2 in FP64
gamma64_n = n*u64/(1-n*u64), n=128, u64=2^-53
R64_upper = nextafter64(sqrt(s * (1 + gamma64_127)), +inf)
R_group = max residual R64_upper
R32_disk = outward_cast_fp32(R_group)
```

`outward_cast_fp32(v)` 先 round-to-nearest cast；若解码值小于 `v`，再 `nextafter_fp32(+inf)`。gate 同时保留 FP64 `R_group` 做 reference audit；实际 bound 只使用从序列化文件解码的 `R32_disk`。

### Online serving-score upper bound

在 FP64 中计算：

```text
d = sum_i q_hat_i * mu_hat_i
A = sum_i abs(q_hat_i * mu_hat_i)
d_upper = d + gamma64_127 * A

gamma32_128 = 128*u32/(1-128*u32), u32=2^-24
serving_dot_error <= gamma32_128 * (A + R32_disk)

U(q,g,k) = outward_add64(
    d_upper,
    R32_disk,
    gamma32_128 * (A + R32_disk)
)
U(q,g) = max_k_present U(q,g,k)
```

`A+R` 来自 `sum |q_i x_i| <= sum |q_i mu_i| + ||q||_2 ||e||_2` 且 `||q||=1`。所有 FP64 additions 后朝 `+inf` nextafter；stopping comparison 使用 FP64 `lower_serving_score <= U`。输出 zero violation、最小 `U-serving_page_max` 与最小停止 margin。任何 violation 先判实现错误，不能作为机制结果。

## Representation-Specific Codebooks

raw-int8 与 f9-int8 分别在额外 256 个、与 64-document replay 完全不重叠的 ViDoRe pages 上训练各自 codebook；每个结果点只计其 representation 对应的一张表。

固定实现：

```text
sklearn.cluster.KMeans
random_state=20260712
n_init=10
max_iter=300
tol=1e-4
algorithm="lloyd"
distance=Euclidean on normalized serving vectors
empty cluster=由 sklearn deterministic relocation 处理并记录
```

Stage A 仅 K={64,256}。记录 occupancy、empty/singleton rate、inertia、train/test residual quantiles。只有 f9-int8 已安全少读页面才训练 K=1024。

## Physical Layout and DRAM Control Plane

test tokens 按 codeword ID 排序后装入原 4 KiB object format。control plane 固定为 **完全 DRAM-resident 的乐观模型**：

```text
64 B global header
K * 128 * 2 B codebook
8 B * document_count offsets
8 B * page_count page headers/offsets
8 B * pair_count records:
  uint16 codeword_id
  uint16 token_count
  fp32 outward radius
4 KiB final alignment for persistent synopsis image
```

运行时不收 synopsis I/O，但在 cost tuple 中计入全部 DRAM control-plane bytes、persistent synopsis bytes 与 decode/materialization CPU。如果在这个最有利模型下仍失败，直接 Kill；本轮不设计 disk-resident metadata path。

## Slack Source Decomposition

对每个 page/query-token 报告：

1. old single-ball slack；
2. multi-ball L2 slack；
3. **exact-group/page envelope**：每 `(page,codeword)` 直接取真实 serving token maximum，再对 groups 取 max；数值等于 true page maximum，作为 residual-direction loss 的零-slack endpoint；
4. maxima-page oracle。

另报 true-max page 已读后仍 false-threatening 的 pages/cell。若 multi-ball 到 exact-page envelope 的 gap主导，Stage A Kill，不用 K=1024 或 scheduler补救。

## Execution and Complete Cost

只比较 sequential 与 fixed best-upper-bound-first；二者均非 contribution。一次 page read 同时更新 document 的全部 Col-Bandit active cells。

每个配置点固定为：

```text
(
  data_pages_read_per_query,
  persistent_data_bytes + persistent_synopsis_bytes,
  DRAM_control_plane_bytes,
  total_online_CPU_per_query,
  ranking_fidelity
)
```

CPU 包含 query-codebook GEMM、pair decode、bound materialization、page priority 和 exact MaxSim。另报：

```text
extra_CPU_per_page_saved
break_even_page_touch_cost
latency(page_cost) = CPU + pages * page_cost
```

crossover 至少覆盖 0.5–100 us/page，并标出旧 P0 f9-int8 约 4.47 us/page 的参考位置；通过依赖完整 Pareto curve，不依赖选择一个无限大的有利 page cost。

## Closest Work Boundary

| Work | Existing mechanism | Missing evidence | Candidate delta |
|---|---|---|---|
| Col-Bandit | outer cell elimination | physical pages required by one cell | exact inner page maximum |
| PLAID | centroid/residual index and pruning | outward-safe per-4 KiB document-page certificate | physical-page residual envelope |
| WARP | selected-token late-interaction execution | exact page organization/bound must be verified | only if equivalent page admission absent |
| Proposed gate | codeword-sorted page + residual certificate | not a new codebook/index | strong-representation exact page skipping |

Closest-work核实不是 Stage A blocker，但在正结果解释或请求 P3 前必须完成。

## Two-Level Decision

### Stage A: K=64/256 geometry/safety gate

- disjoint codebook train；held-out 64/16 replay；raw-int8 + f9-int8。
- actual DRAM/persistent bytes、完整 CPU、四层 slack、zero violations。
- **Kill**：f9 仍读100%；residual-direction gap主导；或五维成本点在整个相关 page-cost curve 上被 f9 full scan 支配。

### Stage B: K=1024

仅当 Stage A 的 f9-int8 已安全跳页且未被成本支配时运行。通过只允许请求 P3；不等于系统/论文/architecture批准。

## Success Condition

- safety violation=0，所有 certificate margins非负；
- f9-int8 held-out safe pages严格少于95.1/query；
- raw/f9各自计入其 codebook、pair metadata、padding、DRAM与total CPU后至少一个点非支配；
- crossover在所报告 page-cost range 内可解释，不靠无限 page cost；
- 不依赖 raw-only、训练文档泄漏或逐 token control-plane 退化。

## Compute

- 额外 256 pages 编码约35分钟；K=64/256 training+replay预计10–30分钟。
- K=1024按早停决定。
- GPU/P3/system implementation：0。
