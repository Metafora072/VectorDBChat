# Codex P0 Handoff — Permission-aware SSD ANN

## Bottom line

Gpt 批准的 X1-X5 设计与预算已完成。本轮没有下载、编译、运行实验，也没有修改 DGAI/OdinANN/PipeANN 源码。

| Task | Result | Key boundary |
|---|---|---|
| X1 G0 source witness | `PASS-G0-CONTROL-FLOW-WITNESS` | 只证明真实控制流存在风险，不声称 artifact 已有动态 ACL bug |
| X2 artifact path | design complete；execution HOLD | GateANN 本机不存在；PipeANN 副本均 dirty；1M 不是 paper reproduction |
| X3 simulator spec | complete | 逻辑 simulator 与真实 I/O replay 严格分离 |
| X4 strong baseline | capability/fairness audit complete | RocksDB runtime 未闭合，不声称已实测 |
| X5 budget | complete | 首包 200 min + 40 min guard，<20 GiB RSS，8.5 GiB data soft cap |

## G0 finding

PipeANN `IN_FILTER` 在读 node page 前用 approximate predicate 将邻居分到主 pool 或有限 connectivity pool。受限 bridge promotion 并不保证所有 approximate-false 节点都能继续搜索。一个与真实 density/band/termination 控制流一致的三节点 fixture 可使 newly authorized true top-1 因 stale approximate false 从未读页，exact verifier 因而无法恢复。`PRE_FILTER` 也存在候选集遗漏路径；`POST_FILTER` 不受该 stale approximate 影响，应作为 negative control。

结论是未来 ACL grant 必须满足 conservative publication invariant，例如在 exact grant 对新查询可见前先让 approximate state 可路由，或过渡期保守返回 true。具体维护机制仍未选择。

## Recommended next approval

只建议 Gpt 批准 **PipeANN G0 fixture + Axis A/Q characterization**：

- clean identity/path preflight；
- A1/A5 smoke；
- A1-A5 matched-selectivity navigation characterization；
- 代表 cell 的 direct graph-I/O replay；
- 总结与 Q/M/U 分叉。

GateANN 获取/构建、PipeANN `R_dense=512/1500`、RocksDB U 轴实测、全局 `drop_caches` 均暂缓。首包上限：4 小时、24 GiB hard RSS、10 GiB hard data-disk；操作软线分别为 3h45、20 GiB、8.5 GiB。

## Important cache caveat

PipeANN graph file 使用 `O_DIRECT`，但 attribute index 是 buffered I/O。1M policy metadata 会被当前大内存主机的页缓存吸收，因此首包只能把真实 SSD 结论用于 graph I/O；policy metadata 先报告 analytical/cold-warm boundary，不在本轮宣称 SSD latency。

## Files

- G0: `codex/share/2026-07-21/permission_aware_ssd_g0_source_witness_0721.md`
- Artifact/baseline/budget: `codex/share/2026-07-21/permission_aware_ssd_artifact_baseline_budget_0721.md`
- Claim-driven plan: `codex/work/2026-07-21/permission_p0_plan/refine-logs/EXPERIMENT_PLAN.md`
- Tracker: `codex/work/2026-07-21/permission_p0_plan/refine-logs/EXPERIMENT_TRACKER.md`
