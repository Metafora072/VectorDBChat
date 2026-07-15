# M08 与 Dir 1 实验结论

M08（stable-ID lazy incoming edge）被两项关键证据否定：删除路径平均仅占 same-ID refresh 总耗时的 5.12%，远低于 40% Continue 门槛；同时 stale edges 在 5,000 次后续插入后仍约有 75% 存活，单节点最大 stale incoming edges 达 1,534--1,831，远超 `2R=128`，因此 M08 KILL。

Dir 1（Deferred Topology Writes with Batch Coalescing）在 100K trace 上，R64 的 batch=100 合并倍率为 1.52x，真实单线程 100ms 窗口仅 1.03x；模拟 32 线程、100ms 也只有 2.10x，需放宽到 8 线程、1 秒才超过 3x。均匀模型能以 7.61%/2.30% 的误差预测 R64 batch=100/1000；按正确的 R64 布局，1B 节点约有 66.67M topology pages，batch=1000 预测仅 1.0005x，触发规模外推 KILL。R128 的全页 Gini=0.4364 单独满足热点 Continue 条件，因此最终结论是门禁冲突下的保守 KILL，同时保留“仅针对 R128 热点页”的窄化方向。

本摘要供 Claude 与 Gpt 审查两个问题：是否同意 KILL-first 的冲突处理；R128 热点页信号是否值得另立一个严格限定的新实验计划。
