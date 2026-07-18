# Dynamic Vamana M0–M3 Final Closure and Novelty Gate

## 1. 最终实验裁决

正式接受 M3 write supersession closure，并关闭 M0–M3 实验链。

必须写入以下结论：

1. M0/M1 已完整定位应用层写入来源，并证明 recurring update-window 的跨系统差距主要来自 insert-neighbor-repair。
2. M2 已将 neighbor-repair page touches 精确分解为 scheduled repair fanout、page mapping 和 temporal rewriting。
3. 当前跨系统差距严重混杂：
   - DGAI：`R=32`、记录 644 B、每 4 KiB 页 6 条；
   - OdinANN：`R=96`、记录 900 B、每页 4 条；
   - search、prune、position allocation、page cache、I/O engine 与 publish 路径也不同。
4. `3×` 只表示 scheduled repair attempts 的计数因子，不等于：
   - 3×有效图修改；
   - 端到端写入差距中至少3×可归因于R；
   - online visibility 的代价。
5. M3 的 22.52M page-version events 中，submit 前同页覆盖机会精确为0。
6. Stage-wide temporal rewriting全部发生在 prior completion 之后，不能由当前 background queue 的page-key coalescing消除。
7. 正式 Kill：
   `利用现有background queue进行same-page pre-submit supersession/queue coalescing`。
8. 不得把进程内online visibility、application completion、fresh-process visibility和crash durability混为同一语义边界。

## 2. Matched-R 裁决

本轮不构建 matched-R base。

Matched-R factorial 是未来进行跨系统因果表述的必要前提，但不是当前的自动下一步，因为即使匹配R、L、C、beam和alpha，仍无法消除：

- search与candidate generation语义；
- prune与reverse-edge repair算法；
- position allocation；
- page cache与锁生命周期；
- libaio与io_uring执行路径；
- publish/save与shadow-copy语义。

因此，matched-R只能回答“统一数值配置后组合差距是否仍存在”，不能证明差距来自online visibility或任何单一机制。

只有在novelty审议后出现一个必须依赖跨系统残余差距的明确机制假设，才重新授权matched-R。届时应使用预注册的factorial设计，而不是事后选择参数。

## 3. 旧叙述修正

检查并标记所有历史报告中的以下表述：

- “online visibility导致约4–5×写放大”；
- “OdinANN的写放大主要来自其在线可见性机制”；
- “3× fanout说明至少3×总写入来自R”；
- “stage-wide rewrite可以通过queue coalescing消除”；
- “更深queue意味着更多同页合并机会”。

这些表述均不得作为最终结论引用。

保留历史文件，但在文件开头标注：

```text
该文件属于中间分析，其中相关机制解释已被M2/M3运行时证据推翻。
```

## 4. Novelty Boundary Review

生成严格的prior-work matrix，至少覆盖：

- FreshDiskANN；
- DGAI；
- OdinANN；
- IP-DiskANN；
- A Topology-Aware Localized Update Strategy for Graph-Based ANN Index；
- SVFusion；
- 其他直接处理dynamic graph ANN更新、reverse-edge repair、localized repair、batch consolidation或写放大的工作。

对每项工作分别整理：

| Work | Update semantics | Storage layout | Repair scope | Write-reduction mechanism | Visibility/durability | Remaining boundary |
|---|---|---|---|---|---|---|

必须依据论文原文、代码或官方材料，不得只引用二手摘要。

重点判断以下候选空间是否已被占据：

1. 解耦vector与topology以减少冗余RMW；
2. 只定位并修改affected vertices；
3. 减少reverse-edge或replacement-edge数量；
4. 避免全局consolidation；
5. direct in-place insertion；
6. batch/lazy update；
7. page/block-aware布局；
8. background write buffering与普通page coalescing；
9. 通过放宽durability换取写入合并。

## 5. 新候选机制门禁

只有候选同时满足以下条件，才可进入下一轮实验：

1. 问题由M0–M3或新profiling直接观测，不依赖跨系统混杂差距；
2. 机制不是参数调优、简单减小R或选择另一组L/C/beam；
3. 机制不是已有decoupling、localized repair、direct insert、lazy batch或普通write coalescing的改名；
4. 有明确状态机、数据结构或系统不变量；
5. 不通过模糊阈值决定何时生效；
6. 不偷换online visibility、fresh visibility或durability语义；
7. 可在单机多NVMe环境实现；
8. 能用至少一个强baseline和真实动态工作负载量化；
9. 预期贡献足以形成系统机制，而非若干工程补丁。

若没有候选通过，必须明确写：

```text
M0–M3没有产生可继续实现的Dynamic Vamana写优化idea。
```

不要为了维持方向而强行提出系统。

## 6. 是否转向其他研究线

若无候选通过，评估是否回到已经存在独立动机的方向：

- 多NVMe并行图遍历；
- query-path I/O并行与投机读取；
- 解耦存储下的query locality修复；
- 其他不依赖本轮错误因果前提的VectorDB SSD问题。

这一步只做证据与novelty比较，不启动实验。

## 7. 输出

输出：

```text
codex/share/2026-07-18/
dynamic_vamana_m0_m3_final_novelty_review_0718.md
```

报告完成后停止：

- 不构建matched-R base；
- 不实现queue coalescing；
- 不修改锁或durability contract；
- 不自动启动新方向实验。
