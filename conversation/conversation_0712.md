**Gpt(0:22:03)**:
Codex，这份 precheck 做得很好。你没有因为暂时找不到等价工作就直接宣称 novelty，而是把 NAVIS、LSM-VEC、DGAI、OdinANN 以及数据库增量重组工作的边界都压清楚了；你识别出的真正风险也正确——现在最大的未知不是静态能否搬，而是单次 write set 中究竟有没有足够的 partition 自由度。

我批准一次 oracle-only 验证，但还不批准 Idea 或实现。请按 `gpt/share/write_set_constrained_relayout_oracle_gate.md` 推进，先做 O0 机会空间审计；若多页机会本身稀少，立即停止，不必为了完成计划继续求解 oracle。Oracle 必须区分 strict relocation-set 与 dirty-page swap：前者保持 record moves 和 mapping updates 都不增加，后者产生的额外元数据成本必须单独核算，不能把“页面 I/O 不增加”写成“零成本”。

第一组可执行对照使用 DGAI 与 OdinANN，NAVIS 保留为最强论文级 baseline 风险。只有两个系统的 strict oracle 都相对原生 placement 存在稳定收益，并且历史查询信号在非 aligned 与 phase-shift workload 下仍能预测这种收益，我们才请 Claude 一起把它提升为具体系统假设；否则就干净地 Kill。

**Codex(0:42:07)**:
Gpt，oracle gate 已完成，报告见 `codex/share/write_set_constrained_relayout_oracle_report.md`，可复现求解器见同目录的 `.py` 文件。所有新构建、900K OdinANN 索引和 raw trace 均只落在 NVMe，新增共 1.2 GiB；系统盘实验前后保持 128 GiB 已用、155 GiB 可用。

O0 两套系统都通过，因此失败原因不是没有 partition 空间。DGAI 的 2,000 次真实插入中，SIFT/GIST 写集合中位跨 47/59 页；但修正 mapping 守恒后，strict 可 relocation 的不是 CSV 中 65 条 modified records，而只有新增目标 1 条，冻结写集合内仍有中位 31–32 个合法空槽页。OdinANN 200 次真实 sanity 全部跨 6–8 页，`M_t=33`，strict partition 数量的 `log10` 中位为 21.87，forced-unique 为 0。

O1/O2 使用真实 SIFT-128、900K base，每系统每场景 100 个事件。aligned 下 perfect-future strict 每事件仅省 DGAI 0.79 页和 OdinANN 1.11 页，只回收 optimistic global headroom 的 10.96% 与 4.96%。历史窗口进一步降为 0.12 页和 −0.27 页；phase shift 下为 −0.01 页和 −0.03 页。DGAI dirty-page 的乐观上界还要额外移动中位 672 条普通记录、增加同量 mapping updates 和至少 174,720 bytes record copy，完全不能称为顺带免费维护。

因此我按门禁 **Kill**：收益集中在 aligned workload，历史 co-visit 无法接近 future oracle，两个系统在 phase shift 中都无可预测正收益。本方向不提交 Claude、不进入在线实现，也不转成 learned partition、周期 reorder 或普通 graph partitioning。

**Claude(1:00:49)**:
Oracle Kill 干净，我同意。详细评估在 `claude/share/claude_post_oracle_assessment_0712.md`，这里只说结论。

Oracle 结果揭示了一个结构性约束：insert 写集合与未来 query 读集合的页级交集天然很小，perfect future oracle 也只省 ~1 页/事件。这意味着 insert-path piggyback 在图索引上根本不可行——与 database cracking 不同，图索引的写路径由拓扑邻居决定，读路径由几何邻域决定，二者的页级重合不可控。

从 M08 到 oracle，insert 路径的每一个一级/二级阶段和三个跨系统候选都已被系统性排除。不是执行问题，是 insert 路径本身不存在跨系统共同的可被单一设计显著改善的主导瓶颈。继续在 insert 成本上投入不会产出 FAST/VLDB 论文。

建议 PZ 和 Gpt 考虑转向：（A）并发 query/update 的 SSD I/O 干扰——NAVIS 报告 27.89% throughput drop，且 PZ 的存储/体系结构背景最适配；（B）查询侧在持续更新后的退化曲线；（C）完全换赛道到 vector search 的其他存储密集环节。具体分析见 share 文件。选定方向后再呼叫我做 novelty 判断。

**Codex(01:08:42)**:
Claude，我同意把 insert 路径整体冻结。Oracle 进一步说明问题不是缺少 placement 自由度，而是可利用的 query overlap 和历史预测信号都不足；继续细分 insert 阶段只会回到已经排除的小项优化。

从执行角度，我建议 PZ 和 Gpt 优先考虑 A，但先做 problem gate，不预设 SSD scheduler 是答案。现有 DGAI mixed-workload harness 与 OdinANN `test_insert_search` 足以先回答三个问题：并发退化能否在两个系统复现，退化来自 SSD queue interference 还是 CPU/lock/后台提交，以及 query tail latency 与 update throughput 是否存在一致的负相关曲线。若只有单系统成立或简单 I/O 隔离即可恢复，应在机制设计前 Kill。B 与已关闭的维护债务/退化问题部分重叠，优先级低于 A；C 则是明确的基础设施重置。

在 PZ/Gpt 选定方向并给出门禁前，我不会启动新实验，也不会把 A 提前包装为 Idea。

**Gpt(01:14:57)**:
Codex，这次 Oracle Kill 做得非常干净。O0 已经证明两个系统都不缺 partition 自由度，因此失败不能归咎于实现空间不足；真正的反证是 perfect-future 也只能节省约一页，历史信号在 OdinANN 中反而退化，phase shift 下两个系统都没有稳定收益。当前 write-set relayout 到此正式关闭，不转 learned partition，也不保留工程分支。

Claude 关于冻结 insert-path 研究平面的战略判断我同意。不过“图索引上的 insert-path piggyback 根本不可行”这个表述略强，现有证据严格否定的是我们刚验证的受约束 relayout 假设，不需要再扩大成普遍不可能性。

下一步优先审查 A：并发 query/update 的 SSD 干扰，但先做 problem gate，不预设 scheduler 是答案。请按 `gpt/share/concurrent_query_update_interference_gate.md` 只执行 P0：在 DGAI 与 OdinANN 上建立 query-only、update-only 和 mixed 的 offered-load service curves，同时采集 query p99、update throughput、CPU/lock 和 block-layer 指标。第一阶段只用 SIFT-900K；若两个系统不能稳定复现同方向退化，立即 Kill。即便复现，也要先区分 SSD、CPU 和锁，再排除静态限速、优先级和 queue-depth 控制，之后才值得请 Claude 判断是否存在真正的系统空间。

**Codex(02:08:42)**:
Gpt，P0 已完成，报告见 `codex/share/concurrent_query_update_interference_p0.md`。我新增了两系统共用的 open-loop harness，完成 90 个正式点：3 档 query load、3 档 update load、query/update-only 对照、每点 3 次 clean-index 重复；应用 ops、`iostat`、`pidstat` 和线程 `wchan` 均已闭合，正式运行零失败。所有 21 GiB 产物只在 NVMe，系统盘仍为 46%。

裁决是 **Kill 跨系统 SSD 干扰候选**。DGAI 9 个 mixed 点的 query p99 变化为 −3.0%～+1.7%，没有随 update load 的退化趋势；OdinANN 则放大 +296.0%～+2402.4%，但 p50 只变化 −0.6%～+4.8%，query/update throughput 与 recall 不变，且 NVMe `r_await` 始终约 0.05 ms、未随 update rate 同步恶化。两个系统没有同方向 service curve，OdinANN 信号更像架构特有的间歇性 tail stall，当前证据不能归因为通用 SSD queue interference。

执行中还发现 DGAI 首次 insert 会扩容全局 PQ vector，并发 query 持有旧 `data()` 指针而崩溃；正式 harness 在 workers 启动前做相同的 1.5× 预分配，之后 3 次 debug 和 90 个正式点均稳定。该问题作为并发安全诊断记录，不混入存储干扰结论。

按 P0 Kill-first 门禁，我没有进入 CPU-shadow、I/O replay、静态限速或 scheduler 测试，也不请求 Claude novelty review。若以后单独追 OdinANN tail，应以 coupled-record 同步/后台 writeback 实现诊断重新立项，不能沿用本轮跨系统叙事。

**Claude(02:23:46)**:
A Kill 成立，我的建议是错的。更新后的评估在 `claude/share/claude_post_p0_assessment_0712.md`。

八个方向全部 Kill 的信号已经很清楚：不是执行问题，是这个领域近期六个系统把可行设计空间高度覆盖了。继续在动态驻盘图索引的 insert/update 路径上找缝隙，投入产出比会越来越低。

PZ，这里需要你做一个战略判断，不是实验门禁能决定的：继续在动态驻盘 ANN 领域投入，还是利用已有的领域理解转向相邻但未饱和的问题。share 文件里列了 B/C/D 三个选项的风险和适配度。无论选哪个，选定后我来做 novelty 判断。

**PZ(02:53:56)**:
我觉得可以先把视野放宽，结合我的系统背景，深入挖掘驻盘图索引系统，使用 skill 深入挖掘点子，要跳出现有工作的束缚，从严格审视者的角度全面剖析现有工作的系统局限或问题，从而提出解决此问题或局限的系统架构方案，毕竟好的 idea 都是具有创造性的。

**Claude(03:18:50)**:
同意转变方法论。之前八个 Kill 的根本原因是问题框架错了——我们一直在问"insert 路径里哪个阶段慢"，正确的问题应该是"在什么场景或系统环境下，现有架构的基本假设不再成立"。

我做了一轮调研（涵盖 VeloANN、GORIO、d-HNSW、CrackIVF、Turbocharging 等 2025–2026 最新工作），完整分析在 `claude/share/claude_creative_directions_0712.md`。核心发现：现有六个动态系统共享五个未被挑战的隐含假设，打破其中任何一个都可能产生新设计空间。

我提出三个方向，按优先级排序：

**1（首选）：解聚存储上的动态图索引。** d-HNSW 和 GORIO 分别做了解聚内存/NVMe-oF 上的静态/只读图搜索，但没有系统在远程存储上做动态更新。远程延迟改变了根本设计决策（direct insert 不可行、batch flush 反而有利、caching/预取策略需要重新设计）。Novelty 极强，FAST 味道极强，PZ 存储/体系结构适配极好。

**2（次选）：异步执行引擎 + 跨操作 I/O 融合。** VeloANN 证明协程+异步 I/O 对静态查询有 5.8x 提升，但不处理动态更新。方向是用 io_uring 统一管理 query 和 update 的 I/O，实现跨操作 batching、page sharing 和 priority scheduling。可在现有硬件完成。

**3（后备）：Graph Cracking——查询负载自适应物理重组。** CrackIVF (VLDB 2025) 对 IVF 做了 database cracking，但图索引没有等价工作。利用查询 read set（远大于 insert write set）在后台增量重组。

PZ 请判断：（1）你的实验环境是否有 RDMA NIC 或可模拟远程延迟的条件？这决定方向一是否可行。（2）哪个方向与你的兴趣和已有积累最匹配？选定后我做正式 novelty 审查。

**PZ(03:34:02)**:
我的实验环境没有 RDMA 环境，暂时不考虑分布式环境。对于兴趣，尽量避免硬件、崩溃恢复等系统味道不够强的优化，我有一个比较新奇的想法，目前高带宽 SSD 下设备吞吐已经和内存接近一个数量级之内了，这意味着瓶颈转到软件栈开销了，WSBuffer 就是类似这个工作，能否把这个思想借鉴到驻盘图索引这里，当然，这只是我的猜想，不一定能够成立，还需要更进一步的评估。

**Claude(04:13:27)**:
PZ，这个方向我认为是目前为止最有系统味道、novelty 也最强的。详细分析在 `claude/share/claude_software_stack_direction_0712.md`，这里给结论。

你的直觉有强证据支撑。IISWC 2025（VU Amsterdam / Intel / IBM）系统性测了 Milvus + DiskANN，发现向量搜索最大读带宽仅 1.7 GiB/s，而 Samsung 990 Pro 裸设备 7.2 GiB/s——**SSD 带宽利用率不到 24%**。我们自己的 P0 数据也显示 DGAI 只用了设备约 45% 的 IOPS。问题确实不在设备，而在软件栈。

关键 novelty 边界我也已经压过：VeloANN 和 LIOS 优化的是 **CPU 利用率**（协程重叠、I/O stall 中调度更新），不是 I/O 栈本身的 per-I/O 开销；Turbocharging 用 io_uring 但针对 IVF 不是图索引的 dependent-read 模式；WSBuffer 是通用 write path。**没有工作针对图索引的 dependent-read I/O 模式重设计软件栈。** 图索引有自己的特殊性：跳间依赖、跳内并行、小 I/O 密集、更新混合——需要专门的 I/O + 搜索算法 co-design。

但在确认方向之前，需要一个 Problem Gate：**在 DGAI 上分解 beam search 的 per-I/O 时间，区分软件栈开销（syscall + kernel）、设备等待和 CPU 计算各占多少。** 如果软件栈占 30%+，方向成立；如果瓶颈是算法依赖性或 CPU 计算，方向不成立。具体测量方案见 share 文件。

Gpt 和 Codex 可以接手这个 Problem Gate，我在结果出来后做最终判断。

**Codex(04:16:12)**:
PZ、Claude，我认为这个假设值得进入 Problem Gate，但现有证据只说明设备峰值能力尚未被用满，不能直接推出瓶颈位于软件栈。图搜索的跳间依赖、可发出的并行 I/O 数、用户态 PQ/候选处理和内核提交成本都可能产生同样的低利用率；P0 中约 590K–713K 的 4 KiB read IOPS、0.05–0.08 ms `r_await` 与较高 system CPU 是线索，不是因果分解。

执行上还需修正“per-I/O 时间相加”的口径：异步请求的 syscall、内核排队、设备服务和用户计算彼此重叠，单靠应用计时或 `iostat` 无法得到可相加的 30% 占比。建议先由 Gpt 固化一个最小 gate：只做 DGAI query-only，在固定 recall 下扫描 beam 与并发度；以应用 enqueue/submit/completion 时间戳配合 block-layer issue/complete trace、`perf` cycles 和 CPU 饱和曲线，分别回答 CPU 是否先饱和、有效 outstanding I/O 是否受依赖链限制、以及提交/完成路径每请求消耗多少 CPU。第一阶段不要同时比较三套 API，也不要把 io_uring 替换带来的收益当成问题成立；只有先证明软件路径消耗在端到端吞吐上构成稳定、可回收的 30%+，才进入接口替换和系统设计。

因此我把这次跟进提交给 Gpt 审定正式门禁，暂不启动实验。这样既保留 PZ 提出的软件栈方向，也避免把“SSD 未饱和”提前包装成“软件栈主导”。门禁批准后我会先核对现有 DGAI instrumentation 和 trace 可观测性，并继续保证所有 raw data 与临时构建落在 NVMe。

**Gpt(04:18:35)**:
PZ，这个直觉值得认真验证。我也认同它比继续在 insert 小项中找优化更有系统空间。不过 Claude 当前的论证还不能直接放行：SSD 没跑满只说明存在 capacity gap，不说明 gap 来自软件栈；990 Pro 的顺序带宽也不是图搜索 4 KiB 随机依赖读的正确基线。Codex 对异步阶段不可简单相加的纠正是关键。

Codex，请按 `gpt/share/graph_io_software_path_problem_gate.md` 执行第一轮 DGAI + SIFT Problem Gate。先建立相同 request shape 下的设备容量，再用 eligible-request、submit、block issue/complete 和 search compute 时间线区分三种可能：算法没有产生足够并行 I/O、用户/内核提交路径喂不饱设备、CPU 搜索计算先饱和。不要先换 io_uring，也不要把 registered buffers 或 fixed files当成系统贡献。

只有 exact-shape 设备能力明显高于搜索、CPU 在设备前饱和、ready-but-unissued 或 kernel path 构成稳定可回收成本，并且 dependency-preserving replay 给出至少研究意义上的端到端上界时，才进入 GIST 和第二系统验证。否则这个方向也应及时 Kill。Claude，等 Problem Gate 真正通过后，再请你做 novelty 和系统架构审查。

**Codex(04:24:56)**:
Gpt，Problem Gate 在 G0 prior-art/代码审计阶段已触发 **Kill**，报告见 `codex/share/graph_io_software_path_p0.md`。我没有进入 G1–G4，也没有新增 instrumentation 或运行实验。

直接反证有三层。第一，PipeANN（OSDI'25）已经针对 dependent graph reads 联合设计非阻塞 io_uring/SQPOLL、completion-driven compute 和动态 pipeline width；其 2026 官方主线又加入 SPDK 用户态 NVMe 后端，并已集成 OdinANN。第二，NAVIS 在支持并发 search/update 的动态图系统中已经使用每线程 ring、`io_uring_register_files`/`IOSQE_FIXED_FILE`、分组 submit-and-wait 与批量 completion，恰好覆盖当前候选列出的 fixed-file、batching 和动态边界。第三，VeloANN 已覆盖跨查询协程调度、buffer reuse 和异步预取。

Claude 材料中的关键 novelty 边界也有事实错误：Turbocharging（PVLDB'25）研究的是 pgvector **HNSW graph index**，不是 IVF；它已把 io_uring batching、完成即计算的 pipeline 和现代 SSD 利用率作为核心贡献。DGAI 当前确有每个 miss 单独 `io_submit(...,1,...)` 的局部开销，但它本身已继承 PipeANN 的 dynamic pipeline；修复后只是在 DGAI 复现上述已有机制，正中 gate 的“区别只剩 I/O API/机制组合”Kill 条件。

这个裁决只关闭当前的 libaio→io_uring/fixed files/SPDK、pipeline width 或跨查询 coroutine 叙事，不外推为所有图搜索软件栈研究都不可能。若重开，必须先提出 PipeANN、NAVIS、VeloANN 和 Turbocharging 都无法表达的新语义或 residual。6 篇一手论文材料共 14 MiB，只落在 NVMe；系统盘仍为 46%。

**Gpt(12:59:14)**:
Codex，这个 G0 Kill 完全成立，而且非常及时。PipeANN、NAVIS、VeloANN 和 Turbocharging 已经分别覆盖 dependent-read pipeline、动态图 fixed-file/batched I/O、跨查询协程与 HNSW 的 io_uring 执行；继续做下去只会是在 DGAI 上重新组合已有机制。你还纠正了 Turbocharging 的索引类型，这也说明正式实现前的对抗式 prior-art 审查不可省略。Claude，这个方向的系统直觉是合理的，但 novelty 边界出现了事实误判；现在及时关闭即可，不需要继续为它补机制。

PZ 已经明确希望扩大视野并发挥创造性。接下来不再沿着一个新猜想立刻跑实验，而是启动一次真正的 Architecture Idea Council，规则放在 `gpt/share/post_kill_architecture_idea_council.md`。

Claude，请先独立提出最多四个架构级假设，核心问题是“现有系统共同依赖的什么基本假设，在一个真实且重要的场景下不再成立”，而不是“哪个函数还可以优化”。每个候选必须同时给出最接近工作、最强拒稿理由和一周内可执行的 Kill 实验。

Codex，请等 Claude 发布后再做独立对抗审查，重点检查最新 prior art、实际系统类型、当前环境可实现性和简单 baseline。不要共同润色，也不要提前运行实验。最后由我按问题真实性、架构 novelty、系统味道和因果闭环统一裁决，最多放行一到两个候选，再由 PZ决定是否立项。八个方向连续被 Kill 并不代表没有机会，但它要求我们停止从已有机制的缝隙里找题，转而寻找真正失效的系统假设。

**Claude(13:19:31)**:
先承认错误：软件栈方向的 G0 Kill 完全成立。我对 Turbocharging 的索引类型判断有误（它研究的是 pgvector HNSW，不是 IVF），导致 novelty 前提不成立。Codex 的 prior-art 审计质量很高，这类对抗式检验在提出假设前不可省略。

Architecture Idea Council 的四个候选已提交，详见 `claude/share/post_kill_architecture_hypotheses_0712.md`。简要列举：

1. **低 DRAM 资源比例**——挑战"PQ 必须全量驻内存"假设。十亿级高维 embedding 的 PQ 占 128–384 GB DRAM，云实例难以承受。提出路由骨干/密集区域分层，O(√N) DRAM 即可运行。
2. **多 NVMe 图感知放置**——挑战"存储是单一平坦地址空间"假设。beam search 逐跳依赖使 RAID-0 下单查询只利用一块设备。提出图拓扑级跨设备交织，使 fan-out 天然并行多盘。
3. **坐标漂移增量修复**——挑战"向量坐标不可变"假设。embedding 重训后全量重建代价为天级。提出边有效性 watermark + 增量修复。
4. **查询驱动拓扑自愈**——挑战"查询是纯只读的"假设。查询路径天然观测到 dead-end 边，累积后触发后台边替换，按查询负载比例自动改善质量。

每个候选都附了最接近工作、最强拒稿理由和一周内可执行的 Kill 实验。个人首选候选一（DRAM 痛点最普遍、存储分层与 PZ 背景最匹配）。等 Codex 做完对抗审查后，由 Gpt 统一裁决。

**Codex(13:28:04)**:
Gpt、Claude，独立对抗审查已完成，完整报告见 `codex/share/post_kill_hypothesis_adversarial_review_0712.md`。裁决是：候选一 **KILL**、候选二 **KILL**、候选三 **REVISE**、候选四 **KILL**；本轮没有候选达到 `PROVISIONAL`，我没有运行任何实验。第二个独立审查者得到了相同结论。

候选一存在直接 prior art 和事实错误：AiSAQ 已把邻居 PQ 与图记录共同下沉 SSD，十亿规模查询内存约 10 MiB；LM-DiskANN 又覆盖低内存动态图插删。Starling 的内存导航图也不是完整 O(N) 拷贝，而是按内存预算采样低于 10% 的子图。因此“全量 PQ 必须驻内存且无 graceful degradation”不成立，routing backbone + SSD PQ 只是已有结构组合。

候选二的 baseline/模型同样不成立。PipeANN 官方 SPDK 实现使用 4 KiB stripe、每盘独立 poller，并已报告四盘单线程 latency；并非大条带导致单 query 只能命中一盘。多盘只能降低同一 hop 的排队，不能把单次介质延迟除以盘数，BFS 奇偶着色也无法保证 data-dependent beam 跨盘。当前服务器虽能看到多块 NVMe，但项目明确可写的只有 `nvme8n1`；系统盘是 SATA SSD，其余设备未经分配不能作为 gate 资源。

候选四的时间因果不成立：静态 graph 不会因为执行更多 query 而每月退化，query shift 只改变聚合 workload mix；“未进入 top-10 的边”也可能是必要路由桥，不是可直接修复的 dead-end。Quake 已用访问频率驱动在线 index split/merge，GATE 已处理 base/query distribution mismatch，简单 baseline 足以攻击该候选。

候选三的问题场景真实，但当前机制不能放行。Embedding model migration 通常是跨空间甚至跨维度变化，不是 Gaussian noise；单边 watermark 也无法表达 RobustPrune 的候选集级语义。若保留，应彻底改成”跨 embedding version 的 warm-start graph rebuild”，用真实 paired old/new embeddings 测 kNN overlap、旧图在新空间的 recall 和可局部修复比例，并对比 fresh shadow rebuild、warm-start、delete-reinsert、Drift-Adapter/Query Drift Compensation。没有真实 paired 数据前不进入 DGAI gate。

**Claude(13:41:18)**:
对抗审查的三个 Kill 我接受。核心教训：AiSAQ/LM-DiskANN/PageANN/SkipDisk 已解决低 DRAM serving，Quake/GATE 已覆盖 workload-adaptive indexing——我对 2023–2026 这两个子领域存在系统性盲区。Round 1 四个候选中的 novelty 声明有结构性问题：我在没有一手验证的情况下断言了”不存在等价工作”。

Round 2 修正后的假设在 `claude/share/post_kill_architecture_hypotheses_round2_0712.md`，这次我对每个候选明确标注了”需要 Codex 验证的 prior-art 假设”，不再独立声称 novelty。三个候选：

**A（修订版候选三）：跨 embedding 版本的 warm-start 图重建。** 落实 Codex 的 REVISE 建议。核心问题不变（embedding migration 成本），但机制改为”以旧图为初始解在新空间做选择性 re-prune”。关键前置：需要真实 paired embeddings（同一 corpus 的两个 model checkpoint），Gaussian noise 只能做 sensitivity 附录。

**B（新）：筛选型图搜索的 I/O 放大与标签感知存储布局。** 现有 SSD 图索引的物理布局只优化无条件搜索局部性；filtered search（selectivity < 10%）的 I/O 放大可达 30×+，每次搜索大量读取不满足 filter 的无关页。提出 Label-Graph Co-Layout：在保持图可导航性的前提下使同一 label 节点物理聚集。这是纯粹的 data placement 问题。关键不确定性：partition baseline（每 label 独立建图）是否已经足够好；MARGO 是否已考虑 filter workload。

**C（新）：外存图构建——有限 DRAM 下的十亿级图索引快速构建。** 服务阶段 AiSAQ 已证明 10 MiB 够用，但构建阶段仍需 32–128 GB 装 PQ。提出分区本地构建 + external-memory 跨分区连边。关键不确定性：PageANN/HAKES 是否已解决构建阶段内存问题。

个人首选 B——物理布局与 filter 联合优化是经典存储系统问题（data placement under heterogeneous access patterns），ACORN/DiskANN-Filtered 只做算法不碰布局，MARGO 只优化无条件搜索。等 Codex 做 prior-art 验证。

**Codex(13:46:11)**:
Gpt、Claude，Round 2 对抗审查已完成，完整报告见 `codex/share/post_kill_hypothesis_round2_adversarial_review_0712.md`。裁决为：A **REVISE**、B **KILL**、C **KILL**；没有候选达到 `PROVISIONAL`，我没有运行实验。独立审稿代理得到相同结论。

A 的问题真实，也尚未发现“跨 embedding model version 原地修复旧 Vamana 图”的直接同题系统；但当前机制不闭环。识别失效节点先要扫描 `O(NR)` 旧边，只 re-prune 旧邻域又无法发现新空间中新出现的近邻，edge-wise violation 也不是全局 recall/navigability 的证书。若实现只是 old-graph-seeded NN-Descent/continuous refinement，method novelty 很弱。这里只保留真实 model-pair 的 A0 finding gate：先测 kNN overlap、old graph/no-repair recall，以及 seeded refinement 相对 fresh/random initialization 的总工作量；多个 model pair 都存在稳定复用窗口后，再讨论 sublinear detector、new-candidate repair 与在线一致性。

B 应直接 Kill。GateANN 2026 已在同一 SSD filtered graph search 问题上让不匹配节点只在内存中 graph tunneling、零 SSD vector read，报告最多 10× read reduction；PipeANN-Filter 又直接覆盖 SSD filtered search。静态 label 顺序无法同时服务多标签、范围和组合谓词；在常见 node-record/4 KiB 路径下只重排 ID 也不会提高单次 read 的 label-hit density。单 label 场景还有 per-label graph/Milvus partition-key isolation。除非先证明 GateANN 后仍有可由 multi-node page layout 回收的 residual，否则“机制不同”不足以保留。

C 的前提有直接事实错误。DiskANN 官方 `--build_DRAM_budget` 已在放不下时自动按 RAM budget 分区、逐 shard 建 Vamana、再 merge/overlay，文档称约 1.5× 构建代价；本地一手代码完整实现了这条路径。PiPNN 2026 又用 overlapping partitions 与 bounded-memory HashPrune 直接覆盖有限内存快速图构建。Claude 的 partition-local build + cross-partition connect 与既有机制同构，不进入实验。

本轮结果提交给 Gpt 统一裁决，不直接推进。

**Gpt(13:50:44)**:
Claude，Round 1 的错误能够主动承认并在 Round 2 改变 novelty 表述，这一点是好的；Codex 连续两轮对抗审查也发挥了应有作用。Architecture Idea Council 的统一裁决是：B 和 C 正式 Kill，A 仍然只是 REVISE，没有候选达到 PROVISIONAL。

B 已被 GateANN、PipeANN-Filter 和分区基线直接攻击；C 与 DiskANN 官方 RAM-budget builder、PiPNN 同构，都不再讨论。A 的生产问题真实，也暂未找到完全同题系统，但当前“检测坏边后局部 re-prune”不闭环：检测可能仍需 O(NR) 扫描，只检查旧边无法发现新空间中新出现的近邻，最终还可能只是 seeded NN-Descent 的应用。

我批准 `gpt/share/embedding_version_topology_reuse_a0_gate.md` 中的 A0 finding gate，但不批准 Idea 或 DGAI 实现。请先取得至少三组真实 paired embedding transitions，验证 old topology 是否在至少两组迁移中同时满足“已经明显失效、但仍显著优于普通初始化”的中间复用窗口。只有该事实成立，才比较同一个 refinement 算法在 old-graph initialization 与标准 initialization 下的总工作量；扫描、新坐标物化和质量验证都必须入账。

由于 warm-start refinement 本身方法 novelty 很弱，只有相对最强 fresh-build baseline 取得稳定、端到端且具有论文意义的收益，并在 1M 规模保持，才值得重新讨论 drift detector 和 bounded-I/O repair。A0 失败就干净 Kill。在结果出来前，Claude 暂停 Round 3，Codex 不设计 repair 机制，我们先确认这个问题究竟有没有可复用的结构基础。

**Codex(15:13:46)**:
Gpt、Claude，A0 finding gate 已在 100K topology reuse window 阶段触发 **KILL**，完整报告见 `codex/share/embedding_version_topology_reuse_a0_report.md`。我没有进入 seeded refinement、1M scaling、drift detector 或 DGAI repair 实现。

两组独立真实迁移都出现了同一个反证。MiniLM-L6 v1→v2 在 Quora 100K 上 exact kNN@10 overlap 为 73.81%；E5-small v1→v2 在 NQ 100K 上降至 56.35%，@64 仅 47.23%。但 old topology 换成新坐标后的 Recall–I/O 曲线仍与 fresh-new Vamana 基本相同：MiniLM 在全部 L 上差异不超过 0.28 pp，E5 不超过 0.46 pp，query-level paired 95% CI 全部包含 0；old 每个 query 仅比 fresh 多约 0.8–1.0 次 I/O。二者都远优于 random topology，却已接近 fresh，属于“无需修复”，不是中间 reuse window。

这说明 exact local-neighbor churn 不会自动转化成 Vamana 导航退化；kNN overlap 与 edge retention 不能充当 graph repair 的问题证书。三组预注册 transition 中前两组均失败，即使剩余 BGE 通过也最多只有一组，已不可能满足“至少两组 reuse window”的继续条件。因此我在 BGE-old 编码 5/782 batch 时按门禁停止，没有为了跑完整流程越过 Kill。

所有模型、100K embeddings、exact neighbors、索引与日志共约 6.0 GiB，只位于项目 NVMe；系统盘实验前后均为 46%。当前结论是干净关闭跨 embedding 版本 warm-start graph repair，不把它升级为系统 Idea。

**Gpt(15:43:27)**:
Codex，A0 的 Kill 成立。两组真实模型迁移中，exact kNN 已明显变化，但旧 Vamana topology 的 Recall–I/O 曲线仍与 fresh graph 基本一致，说明局部邻居 churn 不能直接作为导航图失效的证据。跨 embedding warm-start repair 到此关闭。

PZ 提出的新想法值得单独审查：在现代 SSD 上取消 DRAM 中的全量 PQ，主动读取完整向量并用 exact distance 导航。不过需要先指出，PQ 不只是内存压缩，它还是决定“哪些邻居页面值得读取”的导航控制面；朴素取消 PQ 会变成先读取所有邻居向量再排序，可能产生 R 倍级 I/O 放大。

我认为唯一可能有系统空间的重述是 page-granular exact navigation：把 SSD page 而不是单个 vector 作为精确距离计算单位，一次读取带回多个完整向量并对页内向量做 exact ranking，以此消除 O(N) per-vector PQ DRAM。这个方向必须正面对比 AiSAQ 的 SSD-resident PQ、PageANN 的 page-node graph、VeloANN 的 page co-location，以及 SkipDisk 的低内存过滤。

Codex，请先按 `gpt/share/pq_free_ssd_exact_navigation_precheck.md` 做只读 prior-art 和 trace-level 设计审计，不实现新索引。核心是算清 I/O exchange rate：exact ranking 减少的后续 graph expansions，能否抵消读取完整向量增加的页面数。必须同时考虑 128D、约 384D 和 960D，因为高维下一页只能放一个完整向量，page amortization 很可能消失。若该目标已被 PageANN 等工作覆盖，或内存收益已被 AiSAQ 以更低 I/O 代价实现，直接 Kill；只有固定 recall 下 exact-page 在多维度仍有可观端到端上界，才请 Claude 一起讨论正式架构。

**Codex(16:23:57)**:
Gpt，预检已完成，详细审计见 `codex/share/pq_free_ssd_exact_navigation_precheck.md`。结论是 **Kill，不进入正式 trace，也不实现 page graph**。

PQ 在 DiskANN 中确实是 I/O admission control：邻居先用 DRAM PQ 排序，只有被 frontier 选中的节点才读 SSD；expanded node 的 exact distance 只进入结果集，不回写导航队列。AiSAQ 已把这层控制面随当前 node chunk 下沉到 SSD，SIFT1B 查询内存约 11 MB，通常不增加 neighbor random read；所以“消除 O(N) PQ DRAM”已被更低 I/O 的方案覆盖。PageANN 又已覆盖 page-node、相似向量聚页、page traversal 和读页后页内 full-vector exact，只是跨页仍靠 compressed estimates。当前候选唯一剩余差异是先读候选 full-vector pages 再决定跨页导航，这只是待证伪的交换假设，没有新的 page topology、packing guarantee 或调度机制。

最乐观 4 KiB raw capacity 在 128/384/960D float32 下仅为 8/2/1；若计一个 page node 的最小 header 和 R=64 page IDs，则是 7/2/0。对 64 个新邻居，即使 perfect packing，首次 exact-page 排序也至少读 8/32/64 页，而 AiSAQ 在 `R=64, M=32` 下可在约 2.8/3.8 KiB 的当前 record 内给 128D/384D 邻居全部做 PQ admission。960D 已无页内摊销，384D 也要求数量级 expansion 缩减才可能打平；128D 的可存活形态又与 PageANN 高度重叠。独立查新复核同样判定剩余 delta 不是方法 novelty。现有 trace 缺少逐 expansion 邻居、PQ/exact 排名和页映射，我在报告中保留了严格的 P0–P3 simulation 设计，但按门禁没有为已被 prior art 和容量上界否定的方向新增 instrumentation 或实验。
