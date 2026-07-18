# Research Idea Report

**方向**：基于现有全部 VectorDB 实验数据，判断 Dynamic Vamana / 动态驻盘 ANN 是否仍有研究空间  
**生成时间**：2026-07-18 17:05（UTC+8）  
**流程**：`idea-creator` + 三个独立子智能体（证据审计、发散生成、反方审稿）  
**候选收敛**：10 个候选 → 3 个只读 problem gate → 0 个获准实现 → 0 个 pilot  
**总裁决**：`CLOSE CURRENT IMPLEMENTATION LINE / ALLOW ONE BOUNDED PROBLEM-DISCOVERY ROUND`

## 1. 结论先行

若问题限定为“从 M0–M3 继续推出 Dynamic Vamana 写优化机制”，剩余空间接近零，不值得继续自由 brainstorm，更不应启动 matched-R、queue coalescing、普通 page buffering、降低 R、lazy repair、multi-NVMe placement 或新的写优化原型。

若允许把已有数据转化为新的问题定义，仍有低到中等空间，但只集中在三类相邻方向：

1. dynamic ANN 的 update completion / visibility / durability contract；
2. 区分“页面重复写”与“可安全删除写”的 lifecycle-aware reducibility 方法；
3. scheduled repair 与真正 semantic mutation 之间是否存在可转化为整页 I/O 的差距。

三者目前都只是 `Problem-to-validate`，不是可实现 idea。合理目标是用一轮低成本、只读或离线门禁确认是否存在新问题；最可能的最终结果仍是 `no viable idea`。

## 2. 已有实验对 brainstorm 的硬约束

### 2.1 已被直接否决的方向

- M08 stable-ID lazy incoming-edge repair：delete 仅占 same-ID refresh 平均 5.12%；5K 后续插入后仍约 75% stale edges 存活，单节点最大 stale incoming edges 为 1,534–1,831，明显超过 `2R=128`。
- Deferred topology-write coalescing：R64 真实单线程 100 ms 窗口仅 1.0304×，32 线程模拟仅 2.10×；正确的 1B page-domain 下，batch=1000 仅预测 1.000485×。
- DGAI 单瓶颈优化：900K stable 下 search loop 合计占 37%–43%，但最大直接子阶段仅 9.78%–12.34%，且 SIFT/GIST 主项不同。
- Write-set constrained relayout：perfect-future oracle 每次 update 仅省 DGAI 0.79 页、OdinANN 1.11 页；历史信号和 phase shift 均无稳定正收益。
- 通用 query/update SSD interference：DGAI p99 变化为 −3.0%～+1.7%，OdinANN 为 +296%～+2402%；两系统没有共同 service curve，OdinANN 的 NVMe await 仍约 0.05 ms。
- Dynamic Vamana queue coalescing：M3 审计 22,522,471 个 page-version events，pre-enqueue、queued、inflight supersession 全部精确为 0。
- Visibility-write “无人探索中间态”：FreshDiskANN 与 SVFusion 已分别覆盖 searchable delta / background merge 和 versioned asynchronous propagation / fallback。
- 普通 affected-only、localized repair、少边修复、page-aware layout：Greator、IP-DiskANN、Wolverine、SVFusion、DGAI、OdinANN 已直接占据主要机制空间。

### 2.2 仍成立但未形成机制的事实

- SIFT10M 在累计 20% replacement 后，DGAI/OdinANN Recall 相对下降均小于 0.9%；stale-static DiskANN 则发生严重绝对下降，但单位 churn 损失逐段略降。
- M1/M2 将 recurring gap 定位到 neighbor-only writes；target + shared-page 两系统均为 4,096 B/replacement。
- M2 中 DGAI/OdinANN 实际配置分别是 `R=32/96`、`644/900 B record`、`6/4 records per page`，算法、布局、search/prune、allocator 和 I/O engine 均混杂。
- 400K 时 DGAI/OdinANN scheduled attempts 为 32/96，而真正 mutated records 约为 21.1/54.3；这说明 effect/write mismatch 存在，但尚未证明能省掉整页提交。
- OdinANN-400K temporal rewrite factor 约 4.999，92.71% 的 unique pages 被重复触及，但 top 1% pages 只贡献 2.73% touches；这是广泛重复，不是热点。
- Online visibility、application completion、fresh-process visibility 与 crash durability 是四个不同边界；当前 M3 路径未观察到 `fsync/fdatasync`，但没有执行 crash test。

## 3. Landscape Summary

本地未发现独立的 `papers/` 或 `literature/` 论文库；本轮使用已有审查矩阵，并重新核对 2024–2026 的论文与官方页面。动态更新主线已被 [FreshDiskANN](https://arxiv.org/pdf/2105.09613)、[DGAI](https://arxiv.org/abs/2510.25401)、[OdinANN](https://www.usenix.org/conference/fast26/presentation/guo)、[IP-DiskANN](https://arxiv.org/abs/2502.13826)、[Greator](https://www.vldb.org/pvldb/vol19/p495-yu.pdf)、[Wolverine](https://www.vldb.org/pvldb/vol18/p2268-zheng.pdf) 和 [SVFusion](https://www.vldb.org/pvldb/vol19/p1074-yang.pdf) 从 searchable delta、direct insert、in-place delete、localized repair、少边修复与版本传播等维度密集覆盖。

查询和 I/O 主线同样拥挤：[PipeANN](https://www.usenix.org/conference/osdi25/presentation/guo) 已处理依赖读取与 SSD pipeline，[NAVIS](https://arxiv.org/abs/2605.11523) 处理 position seeking、selective vector read 和动态维护，[VeloANN](https://arxiv.org/abs/2602.22805) 处理 locality、record cache 与 coroutine runtime，[OctopusANN/I/O DSE](https://arxiv.org/abs/2602.21514) 系统比较 layout/search 组合。普通 multi-SSD striping、prefetch、page shuffle、dynamic beam 或 cache tuning 都不能因本轮写方向失败而自动复活。

最新研究还进一步占据 update scheduling 与 characterization：[LIOS](https://arxiv.org/abs/2605.19335) 利用 search I/O stall 调度 update；[Disk-Resident Graph ANN Experimental Evaluation](https://arxiv.org/abs/2603.01779) 已系统比较 storage、layout、cache、query execution 与 update strategy，并指出 dimension、page size 和 in-place/out-of-place trade-off；[How to Write to SSDs](https://arxiv.org/abs/2603.09927) 又从 DBMS 与介质两层强调 out-of-place write 的 write-amplification 优势。因此，单纯“减少写字节”或“换 I/O 粒度”不足以形成 novelty。

仍较少被统一处理的是 correctness/measurement boundary：系统论文通常分别报告 update throughput、freshness 或 consistency，但本地数据已经证明 application completion、searchability、fresh-process reload 与 crash durability不可互换。这个缺口可能支撑 benchmark/methodology，而不是新的 Vamana 写机制。

## 4. Recommended Problem Gates

### 4.1 Rank 1：ContractANN——动态 ANN 更新完成语义与故障合同

- **假设**：不同动态 ANN 系统使用不可比的“update 完成”口径；按 online visibility、fresh-process visibility、durability 和 recovery 分层后，现有性能/写成本排名会发生实质变化。
- **最小验证**：只读审计 DGAI、OdinANN、FreshDiskANN、IP-DiskANN 和一个生产 VectorDB 的 API、源码与论文 contract；建立 `ack → online-searchable → fresh-process-searchable → crash-recoverable` 状态矩阵。只有审计发现至少三个系统存在可复现差异，才申请小规模 fault-injection gate。
- **成功条件**：至少两个常用指标在 contract normalization 后发生 ranking reversal，或同一 acknowledgement 在可见性/恢复上呈现系统性分歧；差异不能由“论文从未承诺 durability”一句话消解。
- **Novelty**：5.5/10；最接近威胁是已有 VectorDBBench/freshness benchmark、FreshDiskANN/SVFusion consistency protocol 和通用数据库 crash testing。
- **贡献类型**：correctness benchmark / measurement methodology。
- **可行性**：只读审计 2–4 天、磁盘增量 <5 GB、无实验运行；若获新 gate，fault injection 预计 3–7 天、20–50 GB。
- **风险**：中高。
- **审稿人最强反对意见**：这些系统根本没有承诺单更新 crash durability，结果只是发现没有 `fsync`，属于文档审计而非研究。
- **裁决**：`PROBLEM-GATE ONLY`。这是当前最值得继续检查的方向，但不得从“未 fsync”直接跳到新协议。

### 4.2 Rank 2：Write Reducibility——从 rewrite factor 到可删除写的生命周期方法

- **假设**：`unique pages`、`rewrite factor`、短窗碰撞率等常用指标会系统性高估优化空间；只有同时满足版本覆盖、锁生命周期、可见性和恢复不变量的 page version 才是 reducible write。
- **最小验证**：复用 M2/M3 结果建立 `repeated / mechanically supersedable / semantically supersedable / durability-required` 四级分类，并对至少一个独立 dynamic index trace 做相同审计。不得提出 coalescing prototype。
- **成功条件**：在至少两个实现或 workload 中，传统 rewrite upper bound 与真实 reducible bytes 相差至少 2×，且分类能提前正确 Kill 一个看似有收益的优化。
- **Novelty**：5/10；最近的 experimental evaluation 与一般 storage write-coalescing 是主要威胁。
- **贡献类型**：measurement methodology / negative result。
- **可行性**：本地重分析 1–3 天、增量 <2 GB；独立系统扩展约一周，需另行授权。
- **风险**：中。
- **审稿人最强反对意见**：M3 的零机会只是 OdinANN 当前锁和队列实现的 bookkeeping，不具有普适性。
- **裁决**：`PROBLEM-GATE ONLY`。若无法找到第二个实现或独立 workload，降为技术报告，不立项。

### 4.3 Rank 3：Semantic Repair Efficiency——scheduled repair 是否产生可省整页写

- **假设**：scheduled attempts 与最终 mutated records 的差距中，存在 byte-identical 或 query-irrelevant 的页面版本；若能在不改变图不变量的情况下识别，可形成 effect-aware write suppression。
- **最小验证**：新增最小 measurement-only instrumentation，记录 before/after page hash、record mutation mask 与提交页集合；先计算“byte-identical submitted page”的精确 oracle，再考虑 query-value oracle。M2 未保存 page/neighbor 明细，不能从现有聚合数据事后得出答案。
- **成功条件**：跨至少两种数据集/规模，byte-identical 或已被同操作内其他 mutation 覆盖的整页占提交页比例显著且稳定；简单 dirty-bit、降低 R、matched-R 或 affected-only baseline 不能达到同一点。
- **Novelty**：3/10；Greator、IP-DiskANN、Wolverine、SVFusion 是强反证。
- **贡献类型**：diagnostic，只有出现新的可达性或 repair-value 不变量后才可能升级为 method。
- **可行性**：设计/静态审计 0.5–1 天；任何新 trace 预计 1–2 天、20–40 GB，必须另行 gate。
- **风险**：高。
- **审稿人最强反对意见**：这只是普通 no-op write suppression 或 dirty-page tracking；即使存在也没有论文 novelty。
- **裁决**：`HOLD`。只有 Rank 1/2 审计没有占满资源且 GPT 单独批准时，才值得做零实现 oracle。

## 5. Conditional Adjacent Pivot

### RAG document-version atomic refresh

此前 prior-art 审计保留过一个相邻问题：一次 source edit 改变 chunk boundary 时，逐条 upsert 可能让查询混合看到旧/新 document chunks。它与本轮 visibility contract 有概念联系，但当前实验没有 RAG revision trace，也没有 answer-level harm 数据。

- **最小验证**：真实 revision trace 的 changed-chunk fanout、mixed-version retrieval exposure、downstream answer harm，以及 document shadow build + atomic pointer flip 的成本。
- **Kill**：普通 diff-upsert 足够；mixed version 不伤 answer；shadow baseline 成本可接受；或问题只在特制 corpus 成立。
- **裁决**：`SEPARATE PROJECT / NO CURRENT EVIDENCE`。不应把它伪装为 Dynamic Vamana continuation。

## 6. Eliminated Ideas

| Candidate | 淘汰原因 |
|---|---|
| Current queue coalescing | M3 的 22.52M lifecycle events 给出精确 0 supersession |
| Cross-completion repair epoch | 必须新建版本、可达性、fallback、recovery 和 durability 状态机；FreshDiskANN/SVFusion/Greator 已占主要空间 |
| Matched-R factorial | 不能隔离算法、布局、cache、I/O engine 或 visibility；没有候选机制依赖该 residual |
| Lower-R / fewer reverse edges | 参数调优；localized/selective repair 已被 IP-DiskANN、Greator、Wolverine、SVFusion 覆盖 |
| Hot-page cache / R128 hotspot | EXP-5 的小规模 Gini 被 M2 的广泛非热点重复推翻，且 1B collision 几乎为零 |
| Multi-NVMe graph-aware placement | PipeANN 已有 SPDK multi-SSD，普通 striping/hash 是强 baseline；本地没有新的多盘残差 |
| Generic SSD-aware update scheduler | DGAI/OdinANN 无共同干扰曲线；LIOS 已直接研究 update-in-search-stall scheduling |
| OdinANN tail-stall 直接立项 | 现象强但只支持单系统实现诊断，可能只是 lock/writeback bug |
| Churn coverage phase model | 可能只是 page-domain coupon-collector 规律；即使预测准确也缺乏系统机制 |
| Endurance-normalized ranking | application-requested bytes 不等于 NAND writes；仅按 TBW 换算不构成贡献 |
| Paper–artifact conformance suite | 可能只是版本漂移或文档错误，单独影响不足 |
| Semantic-normalized cost table | 可作为 Rank 1 的输出，单独做 benchmark 容易被 2026 experimental evaluation 覆盖 |

## 7. Independent Checks

三个子智能体分别执行证据、发散与反方检查，结论一致：

- 当前 Dynamic Vamana 写优化机制空间应维持关闭；
- brainstorm 只能以新的 problem discovery 为目标；
- 优先级为 correctness/contract > lifecycle measurement > semantic repair oracle；
- 每个候选必须同时具备现有数据锚点、与最近工作的明确 delta、低成本 Kill gate，以及超出参数调优/dirty-bit/page buffering 的新不变量；
- 最合理的最终产出可能仍是 characterization 或 `no viable idea`。

反方检查特别指出：M2 的 `scheduled 96 → mutated 54.3` 不能直接解释为 41.7 条 repair 可删除，因为 rejected target edge、relocation、prune 与合法 adjacency mutation 并不等价；M3 也只证明当前 queue 中机械 supersession 为零，没有证明跨 completion 的中间版本语义可删除。

## 8. Pilot Experiment Results

本轮没有 pilot。原因不是资源不可用，而是没有候选通过“问题真实性 + novelty + 状态机/不变量”前置门禁。按 `idea-creator` 规则，pilot 前必须先估算成本；当前任何 fault injection、新 instrumentation 或新系统 trace 都属于新的实验授权范围，不能自动启动。

| Idea | Pilot | Time | Space | Status |
|---|---|---:|---:|---|
| ContractANN | 只读 contract 审计 | 2–4 天 | <5 GB | 可在新 gate 下执行 |
| Write Reducibility | 现有 M2/M3 重分析 | 1–3 天 | <2 GB | 可在新 gate 下执行 |
| Semantic Repair Efficiency | before/after page oracle | 1–2 天运行期 | 20–40 GB | 暂缓，需明确授权 |

## 9. Suggested Execution Order

1. 先由 GPT/Claude 审阅本报告，只决定是否批准 Rank 1/2 的只读 problem gate。
2. 若 Rank 1 在文献/API 审计中没有形成清晰 contract gap，立即 Kill，不做 crash injection。
3. 若 Rank 2 找不到第二个实现或独立 workload，降为 M2/M3 方法学附录，不立项。
4. Rank 3 仅在前两项存活且单独获批后执行；先做 byte-identical page oracle，禁止直接实现 repair policy。
5. 所有候选均失败时，正式停止 Dynamic ANN 内部优化，转向由真实应用约束驱动的相邻项目，而不是继续枚举 kernel/layout/cache 变体。

## 10. 最终建议

可以使用 skill 和子智能体继续一次 brainstorm/check，但空间不是“还能自由找很多 idea”，而是“还有三个可以快速证伪的新问题入口”。对当前 Dynamic Vamana 写优化线，判断是**几乎没有空间**；对 correctness、measurement methodology 和 application-level atomic refresh，判断是**存在有限空间，但尚无可实现 idea**。
