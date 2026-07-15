# 写集合约束微量重排 Oracle 门禁报告

## 裁决

本轮裁决为 **Kill**。两套系统均通过 O0 机会空间门槛，但 O1 与 O2 不满足继续条件。Perfect-future strict 在 aligned workload 中每次更新仅减少 DGAI 0.79 个、OdinANN 1.11 个 4 KiB 页面读取，分别只回收 optimistic global headroom 的 10.96% 与 4.96%。使用历史查询窗口后，收益降为 DGAI 0.12 页和 OdinANN −0.27 页；在 phase shift 中分别为 −0.01 页和 −0.03 页。由此同时触发历史 co-visit 无法接近 future oracle、收益无法在 non-aligned workload 中稳定成立两项 Kill 条件，不进入 Claude 系统假设讨论，也不实现在线 relocation。

## 实验对象与方法

实验使用真实 SIFT-128 数据集、900K base、R=64、L=160 和 10K×100 ground-truth 邻居。DGAI 固定于提交 `a0179b876a4bd453336dc2893b46ae890f680555`，复用已经完成的 2,000 次真实插入 trace 与 900K topology layout。OdinANN 使用官方 `thustorage/PipeANN` 提交 `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`，在 NVMe 上重新构建 900K 索引。官方副本仅增加环境缺失的 CBLAS ABI 声明和由 `ODINANN_ORACLE_O0_CSV` 控制的 54 行 measurement-only trace，不改变 allocation、mapping 或 writeback。

O1/O2 每个系统、每种场景抽取 100 次更新。查询访问集合取每条 ground-truth 的前 10 个有效 base ID。aligned 使用同分布的奇偶查询窗口；query-hot/update-cold 选择查询 trace 中未出现的更新目标；query-cold/update-hot 选择历史热、未来冷的目标；phase shift 使用前后两个 5K 查询窗口。DGAI strict 只允许把 baseline 新增目标放入原写集合内的空槽，保持一次 mapping update；OdinANN strict 只重分 baseline 本来就要 relocation 的 33 条 coupled records，保持 33 次 mapping updates。DGAI 的单记录选择是穷举最优；OdinANN 使用 perfect-future co-visit 权重的容量约束 greedy partition，因此是 best-found oracle，而非经 ILP 证明的全局最优。global 对照使用逐查询容量下界，属于偏向保留该方向的 optimistic lower bound。

所有新源码副本、构建、索引、trace 和原始结果均位于 `VectorDB/data/VectorDB/oracle_gate/`，总占用 1.2 GiB。实验前后系统盘均为 128 GiB 已用、155 GiB 可用，未在系统盘生成大型实验数据。

## O0 机会空间

DGAI 的 2,000 次 900K stable 插入中，每次读取或修改 65 条 topology records。SIFT 的原生写集合中位为 47 页，P95 为 57 页；GIST 分别为 59 页和 63 页。这里必须修正 `M_t` 口径：64 条 reverse-neighbor records 只是原位重写，若搬动会增加 mapping updates；strict 版本实际只有新增目标这一条 relocation record。基于冻结 layout 重建的 400 个场景事件中，目标在原写集合内具有中位 31–32 个合法空槽页，forced-unique 比例为 0。因此 DGAI 存在多页选择，但自由度是一条记录的 placement choice，并非 65 条记录的任意重排。SIFT 原生 topology 写字节中位为 192,512 bytes，strict 保持页面集合、一次 mapping update 和写字节不变。

OdinANN 的 100K sanity 真实执行 200 次单线程插入。每次 `|R_t|=32`、`|M_t|=33`；写集合为 6–8 页，中位 6 页，页容量为 6 条记录，写前空槽中位 36、写后空槽中位 3。所有 200 次更新均存在两种以上 strict partition，forced-unique 比例为 0；strict partition 数量的 `log10` 中位为 21.87。baseline mapping updates 固定为 33，写字节中位为 24,576 bytes。900K R64 layout 的 coupled record 增至 772 bytes，容量为 5，正式事件均使用 7 个 4 KiB 页面和 28,672 bytes；strict 同样保持 page IDs、page count、record moves、mapping updates 和 write bytes 不变。

O0 据此通过。机会空间不是本方向失败的原因。

## O1 Strict、Swap 与 Global 对照

下表报告每种场景 100 次更新累计的绝对 4 KiB page reads，以及相对 native 的累计节省。正数表示减少读取，负数表示退化。

| 系统与场景 | Native pages | Graph/co-update 节省 | Historical 节省 | Perfect strict 节省 | Dirty swap 上界节省 | Global headroom | Strict 恢复比例 |
|---|---:|---:|---:|---:|---:|---:|---:|
| DGAI aligned | 826 | 18 | 12 | 79 | 286 | 721 | 10.96% |
| DGAI query-hot/update-cold | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| DGAI query-cold/update-hot | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| DGAI phase shift | 62 | 3 | −1 | 7 | 23 | 54 | 12.96% |
| OdinANN aligned | 2,876 | −14 | −27 | 111 | 111 | 2,240 | 4.96% |
| OdinANN query-hot/update-cold | 1,500 | 3 | 2 | 9 | 9 | 1,172 | 0.77% |
| OdinANN query-cold/update-hot | 1,725 | 5 | 0 | 20 | 20 | 1,353 | 1.48% |
| OdinANN phase shift | 1,840 | 0 | −3 | 36 | 36 | 1,436 | 2.51% |

DGAI aligned 的 perfect strict 平均收益为 0.79 页/更新，bootstrap 95% CI 为 [0.70, 0.88]；其最强可执行 baseline 是 graph placement，已获得 0.18 页/更新，strict 对该 baseline 的额外绝对收益仅 0.61 页/更新。OdinANN aligned 的 perfect strict 为 1.11 页/更新，95% CI 为 [0.92, 1.30]，但只占 native 28.76 页/更新的 3.86%。non-aligned 条件下，DGAI strict 为 0，OdinANN strict 仅为 0.09–0.20 页/更新。phase shift 中 perfect strict 也只有 DGAI 0.07 页和 OdinANN 0.36 页。

DGAI dirty-page 数值只是偏乐观上界，不是联合可行 partition。取得 aligned 上界需要把中位 672 条普通驻留 topology records 纳入候选，相应增加约 672 次 record moves、672 次 mapping updates 和至少 174,720 bytes 的 record copying；journal/recovery 至少还需覆盖这些新增 mapping transitions，锁范围从 1 条 relocation record 扩到数百条。具体 journal entry 字节数依赖尚未实现的恢复格式，因此没有伪造精确值。该成本相对每事件最多 2.86 个页面读取上界明显不可称为免费。OdinANN 正式 write pages 由 baseline relocation set 填充，本轮 swap 没有比 strict 增加收益；100K sanity 中少数 partial pages 虽扩大 swap 候选空间，但没有形成可复现的额外 query-page 收益。

## O2 历史信号与可预测性

历史 co-visit 未能逼近 perfect future。DGAI aligned 的 historical 收益为 0.12 页/更新，95% CI 为 [0.04, 0.20]，只达到 perfect strict 的 15.2%；phase shift 中变为 −0.01 页，95% CI 为 [−0.03, 0.00]。OdinANN aligned historical 为 −0.27 页，95% CI 为 [−0.41, −0.13]，即稳定劣于 native；phase shift 为 −0.03 页，95% CI 为 [−0.09, 0.03]。Graph adjacency 与 co-updated packing 同样没有提供跨场景稳定信号，aligned 下分别仅节省 DGAI 18 页并使 OdinANN多读 14 页。

该结果说明 future oracle 看到的有限 headroom 无法由自然可用的历史窗口恢复。继续加入学习预测器只会把方向转成普通 learned partition policy，且违反当前门禁中不得用机器学习掩盖 phase-shift 失败的要求。

## I/O 与 Metadata 守恒

Strict 结果在求解前冻结 `W_t` 和目标页容量。DGAI 始终保留原写集合，写字节为 `|W_t|×4096`，record moves 与 mapping updates 均为 1；OdinANN 始终保留 7 个目标页、28,672 bytes、33 条 record moves 和 33 次 mapping updates。求解器只改变合法 records 到这些既有 slots 的对应关系，没有扩大 `R_t`、`W_t`、page count 或 write bytes。

Dirty swap 与 strict 分账。DGAI 的新增 moves、mapping updates、copy bytes 和锁范围已按普通驻留 records 单独计数；recovery metadata 只报告条目数下界，不声称零开销。OdinANN 本轮没有观察到 swap 相对 strict 的有效增益。global lower bound 不满足写集合约束，只用于归一化 headroom，不能解释为可实现结果。

## 有效性边界

本轮 O1/O2 是基于真实 900K layout、真实 ground-truth co-visit 集合和真实系统图的离线 replay，不是在线端到端 query latency 实验。DGAI 的新目标使用现有节点作为语义等价代理；OdinANN perfect partition 是 deterministic greedy best-found，而非精确 ILP。两项限制都可能低估或高估小幅收益，但不会改变 O2 的关键反证：历史策略在 OdinANN aligned 中显著退化，并在两个系统的 phase shift 中均无正收益。global 采用不可联合实现的逐查询下界，反而最大化了可见 headroom，没有对 Kill 结论施加不利偏置。

## 最终边界

本轮只支持以下结论：DGAI 与 OdinANN 的 frozen write set 中确实存在多页合法自由度，但有自由度不等于有可利用的在线信号。Strict perfect-future 的绝对收益小、只恢复很少一部分 global headroom，并集中在 aligned workload；历史查询、graph adjacency 和 co-updated grouping 均无法跨系统、跨 phase 稳定预测。DGAI 较大的 dirty-page 上界依赖数百次额外 relocation 与 metadata 更新，违背微量、顺带维护的核心叙事。

因此该方向按现有定义关闭，不提交 Claude，不进入实现，也不改写为 learned partition、周期 reorder、cache replacement 或普通 graph partitioning。若未来出现不同的自然 write set，使 baseline 本来就 relocation 的记录数显著增加且历史 co-visit 在 phase shift 下仍稳定，再以新证据重新立项；当前结果不保留工程优化分支。

机器可读结果位于 NVMe 的 `VectorDB/data/VectorDB/oracle_gate/raw/oracle_formal.json`，SHA-256 为 `eba16150837ec71c3d8a7c8f57a2d81f55d01a35bfc5677f0ef8bc530ddbfcdd`。OdinANN O0 原始 trace 为 `VectorDB/data/VectorDB/oracle_gate/raw/odin_o0.csv`，SHA-256 为 `d35d6611cdd58b09bb12b0ab718b3b466c1cb3102a259990fd62d890a091e809`。可复现实验脚本为 `codex/share/write_set_constrained_relayout_oracle.py`。
