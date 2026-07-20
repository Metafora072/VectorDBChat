# Research Proposal: Equivalence-First Gate for SSD Permission Maintenance

## Problem Anchor

- **Bottom-line problem:** 在十亿级 SSD 驻盘图 ANN 中，以固定的 policy-plane DRAM 预算支持动态 RBAC/ACL；权限更新后仍须保持 authorized top-k 可达，并保证任何返回结果都满足查询快照上的精确授权。
- **Must-solve bottleneck:** 现有 SSD filtered ANN 的 routing/filter summary 主要按只读数据设计。若权限 grant 必须随机原地重写 node/page summary，会产生 SSD 小写与更新尾延迟；若异步更新 summary，新授权对象会因 stale-negative routing 被永久剪掉，返回前 exact recheck 也无法恢复 recall。revoke 则允许 summary 暂时 stale-positive，但必须由精确验证阻止泄露。
- **Non-goals:** 不设计通用复合查询优化器；不发明新 ANN 图或新 ACL 语言；不把 MVCC、WAL、consistency token、Bloom、LSM 或 lazy revoke 本身写成贡献；不把 `time/type` 当主贡献；不承诺 24/32 GiB 下容纳 1B 的通用 DiskANN PQ state。
- **Constraints:** 复用 DiskANN/PipeANN/OdinANN 异步 SSD Vamana 数据路径；不依赖 GPU；真实服务器有 251 GiB DRAM，但正式比较使用 cgroup 冻结的 64 GiB deployment cap；所有大工件放 `/dev/nvme8n1`；首轮 preflight 上限为 1M、4 小时、10 GiB 新增数据、24 GiB RSS，且不在本 proposal 阶段运行。
- **Success condition:** 在 normalized MVCC policy store、Curator-equivalent lazy revoke 和 generic LSM summary-delta 强基线均存在时，仍能证明 SSD graph-page-aware grant maintenance 在至少两类权限模型上减少物理 permission-write bytes 与 update p99，同时满足 `unauthorized_output_count=0`、revoke snapshot contract 和相对 fresh synchronous-summary baseline 的 authorized Recall@k 门禁。

## Current Thesis

ACL-on-SSD 场景成立，但 page-addressed grant delta 尚不是已成立的贡献。下一步只验证是否存在普通 page-prefix RocksDB 无法获得的 ANN-specific physical-I/O residual。

## Gate 0: Source Witness

在目标 ANN 代码中定位 approximate policy predicate 的真实剪枝点、tunneling 和 refill 规则。用最小确定性图证明 stale object-side grant 会在相同搜索参数下造成不可恢复的 authorized recall loss。失败则 `KILL-NO-ANN-WITNESS`。

## Gate 1: Strongest Natural Combination

对照必须允许 RocksDB 使用 `(graph_generation, graph_page, policy_atom, begin_csn, node_id)` page-prefix key、相同 WAL、cache、batching、durability、snapshot 与 compaction 预算。不得再使用 node-keyed 弱基线。

## Gate 2: Unique Property

候选只能保留一个普通强基线不具备的性质，例如把 correctness-preserving overlay lookup 与已有 graph-page I/O 物理合并，并给出额外 I/O 上界。若差异只是 schema/cache，或三项决定性指标均低于 15%，执行 `KILL-RENAME-MVCC-LSM`。

## Shared Correctness Requirements

- 同一 durable commit record 绑定 policy tuple 与 routing visibility；routing-visible watermark 后才 ACK grant。
- 查询固定 `(q_csn, base_generation, delta_generation)`；ACK 后开始的查询看到对应 grant/revoke。
- correctness locator 不可因 cache eviction 产生 false negative。
- merge/GC 服从 `base_csn` 与 `oldest_active_snapshot`。
- exact verifier 失败后继续 refill；返回结果必须满足查询快照上的 exact authorization。

## Scope and Budget

仅覆盖改变对象侧 approximate predicate 的 object-side policy atom updates；query-side role closure 复用 PolicyStore。当前不运行实验。后续若 Gpt 批准，先提交 G0/G1 的逐项时间与空间预算，仍限制为 <=4 小时、<=10 GiB 数据盘新增、<=24 GiB RSS，禁止系统盘大写入。
