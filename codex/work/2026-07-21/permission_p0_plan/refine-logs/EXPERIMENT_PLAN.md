# P0 Experiment Plan: Permission-aware SSD ANN Characterization

**Problem**: 在 SSD-resident graph ANN 与明确 policy-plane DRAM 配额下，判断 ACL 对图导航、policy metadata I/O、object-side update maintenance 的哪一条路径构成主导瓶颈。
**Method thesis**: 当前不冻结方法；先用源码 witness、强 baseline 审计和三轴成本分解选择 Q/M/U 中唯一主轴。
**Date**: 2026-07-21 (UTC+8)
**Authorization state**: 仅批准设计、源码/API 审计和预算；所有运行项均为 `PENDING_GPT_APPROVAL`。

## Claim Map

| Claim / hypothesis | Why it matters | Minimum convincing evidence | Linked blocks |
|---|---|---|---|
| H0：近似权限层的 stale object-side grant 在至少一种真实执行路径中会造成 exact verifier 无法恢复的 authorized recall loss | 这是方向级正确性前提 | 源码控制流 + 与该路径一致的最小确定性图；同时列出不受影响的路径 | B0 |
| H1：相同 global authorized selectivity 下，ACL 局部结构会改变 SSD graph navigation cost | 决定是否选择 Q 路线 | A1/A2/A3/A5 固定 selectivity，对比 reads、bytes、visited、bridge、yield、recall 与不足 k；趋势跨查询重复 | B2 |
| H2：在公平 DRAM cap 下，policy lookup 或 object-side update 可能而非必然主导 | 防止预设 M/U 路线 | 分别报告 policy-only read share、DRAM/SSD bytes、update physical bytes、WA、query interference | B3/B4 |
| Anti-claim：收益不是由弱 baseline、OS page cache 或 user-role fanout 人为制造 | 保证后续机制比较可信 | page-prefix RocksDB 强基线；direct-I/O/cold-cache证据；query-side closure 独立处理 | B1-B4 |

本 P0 没有论文级 contribution claim，也不使用固定 15% KILL 阈值。判定依据是稳定的瓶颈占比、随 scale/selectivity/churn 的趋势、I/O/空间拐点及不能同时满足的性质。

## Paper / Decision Storyline

- 必须证明：H0 是否成立；ACL structure 是否在相同选择率下改变真实 SSD 成本；Q/M/U 哪一轴主导。
- 可作为附录：A4 hierarchical RBAC 的 query-side closure 成本、100M/1B 结构化外推。
- 明确删除：`time/type` 主贡献、通用复合 planner、page-addressed delta 预设方案、100M/1B 实跑、LLM/VLM/RL 组件。

## Experiment Blocks

### B0：G0 source witness

- **Claim tested**: H0。
- **Dataset/task**: 无数据集；目标源码 + 12 节点以内确定性图。
- **Compared paths**: PipeANN `PRE_FILTER`、`IN_FILTER`、`POST_FILTER`；必要时 GateANN tunneling。
- **Decisive evidence**: 真实 predicate 调用点、page-read 触发点、exact verify 触发点、bridge promotion 与 termination；fresh/stale 两条控制流。
- **Success criterion**: 至少一条会被真实 router 选择的路径中，fresh grant 可进入候选并 exact-pass，而 stale grant 从未发起页面读取或候选准入；exact verifier 无机会恢复。
- **Failure interpretation**: 若所有路径都 tunnel/post-filter 且不造成 false-negative pruning，则 `NO-G0-WITNESS`，撤回该方向级论据。
- **Priority**: MUST-RUN；当前只做静态审计，完成情况见独立 G0 文档。

### B1：Artifact identity and clean reproduction gate

- **Claim tested**: 后续指标来自可复现官方路径，而非本机 dirty fork。
- **Dataset**: 已有 SIFT1M；不下载新向量数据。
- **Compared systems**: official GateANN、official PipeANN-Filter；DGAI/OdinANN 不作为本轮修改目标。
- **Metrics**: commit、tracked-diff hash、untracked manifest、binary hash、toolchain、I/O engine、index format、build/search exit code。
- **Success criterion**: clean source identity、命令与依赖闭合；所有 build/temp/result 位于 `/dev/nvme8n1`；可证明真实 I/O 模式。
- **Failure interpretation**: 依赖安装需要系统盘、artifact 不含 1M filtered path、或只能走 buffered I/O，则 `HOLD-ARTIFACT`，不进入 B2。
- **Priority**: MUST-RUN，等待 Gpt 再授权。

### B2：Axis A first — fragmentation versus navigation

- **Claim tested**: H1。
- **Dataset/task**: SIFT1M；固定 query 与 authorized selectivity，优先 A1 random、A2 role-clustered、A3 shared-core/private-tail、A5 anti-correlated；A4 先做逻辑模型。
- **Systems**: global graph + exact postfilter；PipeANN-Filter speculative router；可复现时加 GateANN；HoneyBee-like 只做逻辑 partition simulator，不伪装成 artifact 结果。
- **Primary metrics**: authorized Recall@10、physical SSD reads/bytes per query、visited/expanded、unauthorized bridge nodes、valid-candidate yield、不足 k 比例、p50/p99。
- **Controls**: 同一 graph/query/search budget/global selectivity；报告 local selectivity；相同 cold/direct-I/O policy。
- **Success criterion**: 不预设百分比；要求 ACL structure effect 可重复、方向一致，并能通过 I/O/visited 分解解释，而非仅 latency noise。
- **Failure interpretation**: 若选择率解释全部差异且结构不影响导航，Q 路线降级，转评 B3/B4。
- **Priority**: FIRST CHARACTERIZATION；等待授权。

### B3：Axis B analytical precheck — metadata placement

- **Claim tested**: H2/M。
- **Inputs**: Claude workload 参数；per-object atom count、role count、sharing、cache budget。
- **Representations**: exact bitmap、sparse postings、probabilistic coarse filter、independent policy page、graph-record colocated attrs。
- **Metrics**: bytes/object、total DRAM/SSD、policy lookup count、policy-only reads、graph/policy I/O overlap、cache hit、coarse-filter false-positive exploration、100M/1B extrapolation。
- **Success criterion**: 识别随内存 cap 出现的可解释拐点及 policy I/O 占比；不以“机器装不下”作证据。
- **Failure interpretation**: 合理表示在 cap 下轻松驻留且 lookup 非主导，则 M 路线降级。
- **Priority**: MUST ANALYZE；首轮可不运行完整 artifact。

### B4：Axis C analytical precheck — object-side update cost

- **Claim tested**: H2/U。
- **Updates**: object-role grant/revoke、directory batch share、document move/inheritance；user-role membership 只走 query-side closure。
- **Baselines**: in-place object policy update；ordinary RocksDB/MVCC overlay；graph-page-prefix overlay；batch page-summary rebuild。
- **Metrics**: logical/physical bytes、pages/update、WA、compaction/merge I/O、query p99 interference、grant/revoke visibility latency。
- **Success criterion**: 找到随 affected objects、page entropy 或 churn 增长的主导成本；不使用 materialized user×object 弱设计制造 fanout。
- **Failure interpretation**: normalized overlay 吸收成本且不干扰查询，则 U 路线降级。
- **Priority**: MUST ANALYZE；首轮只做接口与计费规格。

## Run Order and Milestones

| Milestone | Goal | Run IDs | Decision gate | Future approved cost | Risk |
|---|---|---|---|---|---|
| M0 | 静态源码、artifact、baseline 审计 | D001-D003 | G0 条件结论 + clean-path manifest | 0.5–1.0 h，<1 GiB RSS，0 data write | dirty source 混淆官方行为 |
| M1 | 独立 toy witness / metrics sanity | R001-R003 | fresh/stale 控制流及计数闭合 | 0.25 h，<2 GiB RSS，<0.1 GiB | witness 与真实 path 不一致 |
| M2 | 官方 artifact 1M smoke | R010-R012 | build/search/I/O identity 通过 | 0.75–1.25 h，<8 GiB RSS，<3 GiB | dependency/system-disk write |
| M3 | Axis A 最小矩阵 | R020-R027 | 结构效应可解释或 Q 降级 | 1.0–1.5 h，<16 GiB RSS，<2 GiB | page cache 吞掉 SSD 信号 |
| M4 | B/C 分析与小 replay | R030-R035 | 形成 Q/M/U dominance matrix | 0.5–0.75 h，<12 GiB RSS，<1 GiB | workload 参数缺实证 |

所有未来运行按 gate 串行停止，不能机械执行完整矩阵。建议首个审批包只包含 PipeANN G0/轴 A：200 分钟计划 + 40 分钟 guard、20 GiB RSS soft / 24 GiB hard、数据盘 8.5 GiB soft / 10 GiB hard；GateANN、M/U 实测另行审议。

## Compute and Data Budget

- GPU：0。
- 已有数据：SIFT1M `full_1m.bin` 约 0.477 GiB；已有 OdinANN SIFT1M index 约 0.763 GiB，可只读复用但不能冒充 filtered artifact。
- 新增数据盘预算：首包操作 soft cap 8.5 GiB，hard cap 10 GiB；不得用多个 artifact index 同时占用预算。
- 峰值 RSS：目标 <=20 GiB，hard cap 24 GiB。
- 系统盘：0 大工件；设置 data-disk `TMPDIR`、build、cache、result roots。若必须 apt/pip 全局安装，停止并报 `HOLD-DEPENDENCY`。
- 最大瓶颈：1M working set 容易被 251 GiB 主机 page cache 吸收；优先 artifact 原生 direct I/O。若没有，需单独批准受控 cold-cache 方法并记录块层 I/O，不能仅依赖应用逻辑计数。

## Risks and Mitigations

- **PipeANN 本机源树 dirty**：冻结 HEAD、tracked diff hash、untracked manifest、build config、binary hash；另建 data-disk clean worktree 后才复现。
- **G0 只对某种 strategy 成立**：分别报告 PRE/IN/POST，不把 conditional witness 泛化到全部查询。
- **bridge tunneling 可恢复部分 false negative**：witness 必须显式覆盖 density gate、distance band 与唯一入边，不能假设硬剪枝。
- **1M cache residency**：要求 direct I/O 或可审计 cold-cache/块层证据；否则 latency 只作 CPU/cache 结果。
- **三轴工作量膨胀**：优先 B0/B1/B2；B3/B4 首轮只做分析与最小 replay；P0 后只选 Q/M/U 一轴。

## Final Checklist

- [x] 方向与具体机制分离
- [x] 强自然 baseline 纳入
- [x] Q/M/U 只选一轴的分叉定义
- [x] 时间、RSS、数据盘与系统盘边界显式化
- [x] frontier model 不适用并明确删除
- [ ] Gpt 批准实际运行范围
- [ ] Claude workload 参数接入
- [ ] clean artifact identity 闭合
- [ ] 真实 SSD I/O 证据闭合
