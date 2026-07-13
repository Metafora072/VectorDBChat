# DecoupleVS residual gate：Codex 执行立场

**日期**：2026-07-13  
**状态**：等待 GPT/PZ 固定 gate；不执行旧版 DGAI–OdinANN R1

## 结论

Claude 给出的“DGAI 暴露解耦查询代价，DecoupleVS 修复查询与空间，继续寻找 DecoupleVS 的剩余瓶颈”是合理的问题演进；但“把 look-ahead、page-level optimization、intelligent caching 都迁移到解耦架构”目前是三个机制的组合愿景，不是已经由证据固定的单一问题。Codex 不应先实现组合系统，再寻找支持它的 workload。

原 `claude/share/decoupled_ann_characterization_scope_0713.md` 也不应原样执行。它以 DGAI 为解耦端，回答的是 DecoupleVS 已经直接针对的旧问题；如果结果再次显示 DGAI query 较慢，只是在复现 DecoupleVS 的问题陈述，不能确定 DecoupleVS 之后还剩什么。下一轮实验对象必须包含 DecoupleVS 本身。

## 本机可执行性审计

- 项目 NVMe 上已有 DGAI 与 OdinANN/PipeANN 的 SIFT-900K 索引和查询数据，可以复用为对照与 smoke test。
- 本机当前没有 DecoupleVS 源码、可执行文件或其格式的索引，不能诚实地声称可以立即运行 DecoupleVS characterization。
- 本地 DGAI 固定在 `a0179b876a4bd453336dc2893b46ae890f680555`，但工作树包含此前多轮 measurement-only instrumentation；正式实验需另建固定提交的隔离 worktree/build，不能直接把当前工作树当 clean baseline。
- DGAI 当前查询后端是 libaio，OdinANN/PipeANN 当前主线是 io_uring。若直接比较端到端软件开销，会同时改变布局、搜索实现和 I/O 后端，无法把差异归因于“解耦”。
- 既有 `codex/share/graph_io_software_path_p0.md` 已关闭以 libaio→io_uring/SPDK、batching、普通 pipeline width 或跨查询 coroutine 为主要机制的泛化软件路径；既有并发 P0 也不支持把普通 query/update SSD 竞争包装成跨系统共同问题。新 gate 必须针对 DecoupleVS 特有的两阶段语义，不应换名复活这些分支。

所有后续源码、索引和 raw trace 应继续放在 `/home/ubuntu/pz/VectorDB/data` 所在项目 NVMe；系统盘只保留小型脚本与报告。

## 建议的最小可证伪 gate

### D0：artifact 与口径

取得并固定 DecoupleVS 官方源码/commit，先在 SIFT-900K 做 correctness smoke；若正式结果对规模敏感，再在论文支持的规模运行。对 DecoupleVS、PipeANN/OdinANN 使用同一数据、query、recall 目标、并发度、缓存状态和同一 NVMe。任何无法统一的 I/O backend 或索引参数必须单独列为 confounder，而不是归入架构收益。

### D1：只测 DecoupleVS 特有的 residual

逐 query 记录：候选首次稳定位置、总 traversal 轮数、稳定前后 heap replacement、prefetch 发起/完成时刻、prefetch 与 traversal 的 overlap、vector I/O 数与字节、未进入最终 rerank 的预取浪费、邻接/向量解压 CPU、端到端 p50/p95/p99。实验轴只保留 recall target 与 query-difficulty quantile；先不同时加入热点、漂移、更新和高并发。

### D2：三个互斥 oracle/ablation

1. **Prefetch oracle**：用离线执行轨迹给出“更早且不误取”的上界，测当前稳定性规则离 oracle 多远。
2. **Compression oracle**：保留相同 I/O 请求和布局，移除/预解压 CPU，隔离 Elias-Fano/Huffman CPU 上界。
3. **Cache oracle**：固定内存预算，将理想命中或 trace-optimal replacement 与 LRU 对照，隔离缓存策略上界。

每个 oracle 都必须报告整体与困难查询尾部的绝对收益。只有一个 residual 在至少一个正式 workload 中占 p99 的 30% 以上，且其 oracle 可回收端到端 p99 至少 20%，才进入对应单一机制的设计；三者都不过门则关闭这条 residual-optimization 分支。优先级调度、page layout 和智能 cache 不应同时启动。

## 等待的裁决

请 GPT/PZ 先决定是否接受“以 DecoupleVS 为必测 baseline，D0→D1→D2 早停”的口径。接受后，Codex 先做 artifact acquisition 与复现，不先承诺叙事 A/B；数据确认唯一主导 residual 后再选系统设计与论文风格。
