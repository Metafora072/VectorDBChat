# Round 1 Refinement

## Problem Anchor

- **Bottom-line problem**: 在强 token merging 与量化之后，visual late-interaction candidate object 仍跨多个 4 KiB pages；需要只读取部分 token pages，就求出外层 Col-Bandit 所需的 MaxSim cells，并产生表示压缩 baseline 达不到的 page/storage/CPU/fidelity Pareto。
- **Must-solve bottleneck**: P1 证明 page oracle 存在，但 P2 的 single centroid-radius 把每页 token set 包成一个大球，upper bound 在真实 128D ColQwen2 embedding 上过松，导致读取 99.92%–100% pages。
- **Non-goals**: 不发明新的 outer bandit；不直接实现 async SSD engine；不把 heuristic page order 冒充 exact；不以只在 raw unmerged representation 上成立的收益复活系统；不把 PageMaxSim 改名为通用 DiskColBERT。
- **Constraints**: 4 KiB direct-I/O alignment；真实 ViDoRe/ColQwen2 candidate sets；必须计入 codebook、per-page metadata、padding、bound CPU；优先复用当前 CPU pilot；P3 仍未获批准。
- **Success condition**: 在 held-out queries 上，新的 feasible bound 对 raw int8 和 Light-style f9 int8 都能严格恢复请求 cells，并形成 full scan、single-ball、strong representation 与 single-vector baseline 均无法达到的新 Pareto；否则继续 Kill。

## Anchor Check

- 原始瓶颈仍是 inner exact page maximum 的安全上界过松。
- 方案只替换 synopsis geometry，outer candidate/Col-Bandit/representation/page format 均冻结。
- learned router、approximate fixed budget、async engine 会把问题改成近似 pruning 或 I/O engineering，继续排除。

## Simplicity Check

- 唯一候选贡献收缩为 **shared-codebook residual certificate**。
- 删除 scheduler supporting contribution；只把现有 sequential/best-upper-bound order 当执行 baseline。
- 只保留一种 L2 residual synopsis。angular cap、learned routing、hierarchy都不并列加入；若 L2 因 residual direction 失败，本轮直接 Kill。

## Changes Made

1. 定义 serving vector、decoded codeword、outward-rounded radius 和 dot-product error，闭合实现安全。
2. 增加 single-ball → multi-ball → group oracle → page oracle 的 slack source decomposition。
3. 固定 actual metadata record、global codebook amortization、完整 CPU path 与 page-cost crossover。
4. 使用额外 disjoint ViDoRe documents 训练 codebook，原 64/16 replay 完全 held out。
5. 两级早停：K=64/256 先证伪，只有 f9-int8 有真实跳页信号才运行 K=1024。
6. 增加 PLAID/WARP/Col-Bandit 四列表，收紧贡献边界。

## Revised Proposal

# Research Proposal: Residual-Certified PageMaxSim

## Technical Gap

P2 的 single-ball page synopsis 丢失两类结构：页内多模态 token 被一个球混合，以及 Cauchy `q·e <= ||e||` 丢失 residual direction。shared-codebook multi-ball 只针对第一类。因而下一 gate 的第一目标不是“省多少页”，而是分解这两类 slack；若 multi-ball 与 group oracle 的差距仍主导，就停止，不用更大 K 或 scheduler 掩盖失败。

## Method Thesis

用一个 corpus-shared FP16 token codebook 与实际 page 内的 outward-safe `(codeword ID, max residual radius)` 列表，将 page token set 表示成多个小 residual balls 的并集，以小 control plane 对 exact MaxSim page 做安全 admission。

## Contribution Focus

- **Dominant contribution**: shared-codebook residual certificate 是否能成为强压缩 visual late interaction 的 exact physical-page control plane。
- **Explicit non-contributions**: codebook/k-means、Col-Bandit、token merging、int8、scheduler、async I/O。

## Exact Certified Object

对 int8 路径，认证对象固定为 serving 真正评分的向量：

```text
x_hat = normalize_fp32(dequantize_int8(code, fp16_scale))
q_hat = serving query token converted to FP32 and normalized
mu_hat = FP16 codeword decoded to FP32
```

assignment 与 residual 都相对 `mu_hat` 计算。对 page `g` 中属于 codeword `k` 的 token：

```text
R32(g,k) = nextafter_fp32(max ||x_hat - mu_hat_k||_2, +infinity)
```

gate 首先使用 FP32 outward radius，不用 round-to-nearest FP16 radius。FP32 dot 的累计误差补偿为：

```text
gamma_128 = 128*u/(1-128*u), u=2^-24
epsilon_dot(q,k) = gamma_128 * sum_i |q_i * mu_k_i|

U(q,g) = nextafter_fp32(
             max_k_in_g(nextafter_fp32(q dot mu_hat_k,+inf)
                        + R32(g,k) + epsilon_dot(q,k)),
             +infinity)
```

exact scan 与 certificate 使用同一个 `x_hat/q_hat`。除逐 cell exact equality audit 外，输出最坏 `U - true_page_max`、最小停止 margin 和 violation count；任何 negative safety margin 立即判实现失败。若 gate 有信号，再单独测试 outward-rounded FP16 radius 的 bytes/tightness，不提前混入。

## Physical Layout and Actual Metadata

离线对 disjoint training documents 的 token 做 k-means，K 分两级：

```text
Stage A: K={64,256}
Stage B: K=1024 only if Stage A skips f9 pages safely
```

测试 document tokens 按 nearest decoded codeword ID 排序，再装入原有 4 KiB pages。实际 synopsis：

```text
64 B global header
K * 128 * 2 B decoded-FP16 codeword payload
8 B * document_count document offset table
8 B per-page header/offset
8 B * n_pairs records:
    uint16 codeword_id
    uint16 token_count
    fp32 outward radius
4 KiB final alignment
```

同时报告 actual file size、bytes/document、bytes/token、distinct pairs/page、codeword occupancy/empty/singleton rate，以及 codebook 相对 corpus 的摊销 break-even document count。codebook 是 query-time DRAM control plane；per-page pair lists 可以按候选 metadata 访问模型计费，不默认免费驻 DRAM。

## Bound and Execution

每个 query token 先一次性计算 `q_hat @ mu_hat[K]`。每页 upper 通过 pair-list lookup 得到。为隔离 synopsis，执行器只比较：

1. sequential page order；
2. fixed best-upper-bound-first order。

不优化 active-batch scheduler、不声称新的 scheduling contribution。每个 page read 仍同时更新 document 的全部 active cells。

## Slack Source Decomposition

对相同 page/cell 输出四层：

1. **single-ball slack**：旧 P2 `U_single - true_page_max`；
2. **multi-ball L2 slack**：新 `U_multi - true_page_max`；
3. **group oracle slack**：每个 `(g,k)` 预知真实 group maximum，再对 group 取 max；这移除 residual-direction loss但保留 grouping；
4. **page oracle**：真实 maximizing page union。

并报告在 true-max page 已读后仍错误威胁该 cell 的 page 数。若 `multi-ball -> group oracle` 的 gap 仍占主要部分，失败来自 residual direction；直接 Kill，不升级 K/调度器。

## Honest Held-out Protocol

从同一 MIT ViDoRe Parquet 额外编码最多 256 个与现有 64 test documents 不重叠的真实 pages，仅用于 codebook training。原 64 documents、16 queries、mean-vector top-32 candidates 和 Col-Bandit reveal sets完全冻结为 held-out replay。训练集不用于 quality/page 指标。

K=1024 只有在约 190K raw training tokens 与约 21K f9 training tokens上运行；必须报告 occupancy、singleton rate 与 train/test residual-radius gap。若不新增 disjoint pool，则只能声明 query-held-out，不能声明 document generalization。

## Complete Cost Accounting

在线 CPU 分开报告：

- query-codebook GEMM；
- pair-list decode；
- bound materialization；
- page priority；
- read-page exact MaxSim；
- total CPU。

对每个点报告：

```text
extra_CPU_per_page_saved = (new_total_CPU - f9_full_CPU) / pages_saved
break-even_page_touch_cost
```

不预设 SSD latency、不偷跑 P3；给出 page-touch cost 的 crossover curve。旧 f9 full MaxSim 约 0.425 ms，而旧 greedy 已达 2.51 ms，因此任何 CPU 明显更高且只省少量页的点会自然被支配。

## Closest-Mechanism Boundary

| Work | Existing mechanism | What it does not establish | Only candidate delta |
|---|---|---|---|
| Col-Bandit | outer document/query-token cell elimination | one cell needs which physical pages | exact inner page maximum |
| PLAID | centroid IDs, residual compression, centroid interaction/pruning | audited outward-safe 4 KiB per-document page certificate | per-page residual envelope |
| WARP | late-interaction indexing and selected-token execution | must verify physical page organization, exactness and residual bound | only survives if exact page admission is absent |
| This proposal | codeword-sorted pages + residual certificate | does not invent codebook/residual indexing | strong-representation exact page skipping with full cost |

在解释任何正结果前，必须核实 PLAID/WARP 是否已有等价 residual upper bound 或 exact centroid-partition skip；若等价，结果只作为 characterization，不升级 novelty。

## Two-Level Gate

### Stage A: Geometry/safety micro-gate

- K=64/256；raw-int8 + f9-int8；disjoint codebook train/test。
- 输出四层 slack、false-threatening pages、actual pairs/bytes、total CPU、zero safety violations。
- **Immediate Kill**：f9-int8 仍读 100%；或 multi-ball 到 group-oracle 的 residual-direction gap仍主导；或 metadata/CPU 明显使点被 f9 full scan 支配。

### Stage B: High-resolution point

只在 Stage A 的 f9-int8 已安全少读页面时运行 K=1024，比较 actual serialized metadata 与完整 crossover。通过只意味着可以请求 P3，不等于批准系统或 architecture review。

## Success Condition

无需人为百分比。必须同时满足：

- certificate violation = 0，最小 safety margin非负；
- f9-int8 在 held-out replay 上严格少于 95.1 pages/query；
- raw-int8 与 f9-int8 都形成计入 codebook、pair metadata、padding、total CPU 后的非支配点；
- page saving 对 page-touch cost 有可解释的 crossover，而不是在所有合理成本下被 f9 full scan 支配；
- 收益不是只由 raw representation 或 training-document leakage 提供。

## Compute & Timeline

- 额外 256 pages CPU encoding：按现有约 8 s/page，约 35 分钟。
- K=64/256 k-means、serialization、16-query replay：预计 10–30 分钟，记录实耗。
- K=1024：仅 Stage A 通过后运行。
- GPU、P3 SSD replay、architecture work：0。
