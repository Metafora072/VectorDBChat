# Dynamic Vamana M2：Neighbor-Repair Amplification Decomposition

## 范围与停止边界

M2 只运行 DGAI/OdinANN 的 50K 与 400K 四个 fresh-clone 点，复用 accepted V5 physical profiler，并新增结束时一次性输出的内存聚合逻辑计数。目标是把 neighbor-repair-only 写入拆成 repair fanout、page mapping 与 temporal rewriting；不实现缓存、延迟写回、批处理或其他优化，不运行额外规模。

## 源码与配置审计

正式 driver 对两个系统均设置 `R=32`、`L=75`、`alpha=1.2`、候选上限 `C=160`、`beam_width=16`、32 个 update threads，输入 replacement 顺序和 128 条一批的 insertion kernel 保持不变。运行时 logical profile 会再次记录实际生效的参数、节点记录字节数与每 4 KiB 页记录容量；若同一 run 内配置变化则 gate 失败。

DGAI 经 `do_beam_search → prune_neighbors` 形成 `new_nhood`，再逐邻居 append target、必要时执行本实现的 PQ/delta prune，最终由 `writes_4k` 在单次 replacement 内按页去重，走 libaio/wbc-write。OdinANN 经 `do_pipe_search → prune_neighbors` 形成 `new_nhood`，还包含 entry-point removal 与 `R+1 → R` 调整，逐邻居使用其 `delta_prune_neighbors`，随后由 `writes_4k` 单操作去重并进入 io_uring background writer。两者参数与页大小可归一，但搜索、prune、位置分配和执行引擎并不相同，所以跨系统结论严格视为组合差异。

Instrumentation 在每个 `insert_in_place` 内只构造局部计数，随后以一次互斥内存聚合更新完整整数直方图与 page-touch frequency；不记录邻居 ID、page ID 明细或逐操作日志。它分别统计 scheduled repair attempt、target 最终保留的 accepted reverse edge、真正 adjacency-mutated record，避免把被 prune 后仍因 relocation 写回的记录混作有效反向边。每次操作的 neighbor-only logical page set 必须与 `writes_4k` 提交页集合完全一致，最终还必须满足 physical neighbor-repair-only bytes = submitted touches × 4096。

## 启动前资源预算

独立 build 位于项目 NVMe 的 `neighbor-repair-m2-v1-r01`。启动前项目 NVMe 可用约 973 GiB、MemAvailable 约 240 GiB；四个 clone、结果与 build 预计新增 64–72 GB，build 预计 5–10 分钟，四点严格串行 controller wall 预计 25–40 分钟。每点使用 40 GiB cgroup memory limit 与 2 小时 hard limit，任一 formal/logical closure gate 失败即停止。

## 结果

待四点完成后填写。
