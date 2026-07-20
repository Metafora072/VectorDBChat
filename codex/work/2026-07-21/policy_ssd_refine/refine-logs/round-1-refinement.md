# Round 1 Refinement

## Problem Anchor

- **Bottom-line problem:** 在十亿级 SSD 驻盘图 ANN 中，以固定的 policy-plane DRAM 预算支持动态 RBAC/ACL；权限更新后仍须保持 authorized top-k 可达，并保证任何返回结果都满足查询快照上的精确授权。
- **Must-solve bottleneck:** 现有 SSD filtered ANN 的 routing/filter summary 主要按只读数据设计。若权限 grant 必须随机原地重写 node/page summary，会产生 SSD 小写与更新尾延迟；若异步更新 summary，新授权对象会因 stale-negative routing 被永久剪掉，返回前 exact recheck 也无法恢复 recall。revoke 则允许 summary 暂时 stale-positive，但必须由精确验证阻止泄露。
- **Non-goals:** 不设计通用复合查询优化器；不发明新 ANN 图或新 ACL 语言；不把 MVCC、WAL、consistency token、Bloom、LSM 或 lazy revoke 本身写成贡献；不把 `time/type` 当主贡献；不承诺 24/32 GiB 下容纳 1B 的通用 DiskANN PQ state。
- **Constraints:** 复用 DiskANN/PipeANN/OdinANN 异步 SSD Vamana 数据路径；不依赖 GPU；真实服务器有 251 GiB DRAM，但正式比较使用 cgroup 冻结的 64 GiB deployment cap；所有大工件放 `/dev/nvme8n1`；首轮 preflight 上限为 1M、4 小时、10 GiB 新增数据、24 GiB RSS，且不在本 proposal 阶段运行。
- **Success condition:** 在 normalized MVCC policy store、Curator-equivalent lazy revoke 和 generic LSM summary-delta 强基线均存在时，仍能证明 SSD graph-page-aware grant maintenance 在至少两类权限模型上减少物理 permission-write bytes 与 update p99，同时满足 `unauthorized_output_count=0`、revoke snapshot contract 和相对 fresh synchronous-summary baseline 的 authorized Recall@k 门禁。

## Anchor Check

- 原始瓶颈仍是 object-side grant 造成的 policy-induced stale negative，以及同步维护的 SSD 写成本。
- 不再假定该问题必然需要一个新系统；先验证实际 ANN 路径是否存在不可恢复的剪枝点。
- 将 user-role membership 与 role hierarchy 更新移到 query-side closure，不再声称 page delta 统一覆盖所有 RBAC 更新。
- 不接受通过加入 planner、学习模型或更多谓词来回避 novelty 反证；这会偏离锚点。

## Simplicity Check

- 当前没有获准的论文级 dominant contribution，只有一个待证候选性质：是否能把 grant routing visibility 与已有 graph-page I/O 合并，并获得普通独立 page-prefix LSM 无法提供的额外 I/O 上界。
- lazy revoke、MVCC、WAL、exact verifier、snapshot token 全部降为复用基础设施。
- 删除弱的 node-keyed delta 主基线、materialized user×object 主对照和“大系统整合即贡献”的表述。
- 若最强自然组合具备相同 invariant 与 I/O 行为，立即 `KILL-RENAME-MVCC-LSM`。

## Changes Made

### 1. 将方法方案改为等价性优先门禁

- Reviewer said：按 graph page 排序的 RocksDB column family 已自然覆盖大部分 page-addressed delta 行为。
- Action：把 strongest baseline 升级为同样使用 graph-page prefix、相同 cache/WAL/batching/compaction 的 RocksDB 实现。
- Impact：不再把 key layout 当 novelty，先寻找强基线无法提供的单一物理性质。

### 2. 收紧更新适用域

- Reviewer said：user-role grant 通常只改变查询侧 atom closure。
- Action：核心只讨论改变 SSD graph record approximate predicate 的 object-side grants/revokes。
- Impact：避免把所有 ACL churn 人为转换成 page write fanout。

### 3. 把正确性协议变成基线要求

- Reviewer said：locator/cache、commit、old snapshot、merge、refill 均未闭合。
- Action：这些全部列为任何候选与基线共同满足的工程契约，不再列为贡献。
- Impact：性能对照只在等语义、等资源、等正确性条件下成立。

## Revised Proposal

# Research Proposal: Equivalence-First Feasibility Gate for SSD Permission Maintenance

## Problem Anchor

- **Bottom-line problem:** 在十亿级 SSD 驻盘图 ANN 中，以固定的 policy-plane DRAM 预算支持动态 RBAC/ACL；权限更新后仍须保持 authorized top-k 可达，并保证任何返回结果都满足查询快照上的精确授权。
- **Must-solve bottleneck:** 现有 SSD filtered ANN 的 routing/filter summary 主要按只读数据设计。若权限 grant 必须随机原地重写 node/page summary，会产生 SSD 小写与更新尾延迟；若异步更新 summary，新授权对象会因 stale-negative routing 被永久剪掉，返回前 exact recheck 也无法恢复 recall。revoke 则允许 summary 暂时 stale-positive，但必须由精确验证阻止泄露。
- **Non-goals:** 不设计通用复合查询优化器；不发明新 ANN 图或新 ACL 语言；不把 MVCC、WAL、consistency token、Bloom、LSM 或 lazy revoke 本身写成贡献；不把 `time/type` 当主贡献；不承诺 24/32 GiB 下容纳 1B 的通用 DiskANN PQ state。
- **Constraints:** 复用 DiskANN/PipeANN/OdinANN 异步 SSD Vamana 数据路径；不依赖 GPU；真实服务器有 251 GiB DRAM，但正式比较使用 cgroup 冻结的 64 GiB deployment cap；所有大工件放 `/dev/nvme8n1`；首轮 preflight 上限为 1M、4 小时、10 GiB 新增数据、24 GiB RSS，且不在本 proposal 阶段运行。
- **Success condition:** 在 normalized MVCC policy store、Curator-equivalent lazy revoke 和 generic LSM summary-delta 强基线均存在时，仍能证明 SSD graph-page-aware grant maintenance 在至少两类权限模型上减少物理 permission-write bytes 与 update p99，同时满足 `unauthorized_output_count=0`、revoke snapshot contract 和相对 fresh synchronous-summary baseline 的 authorized Recall@k 门禁。

## Technical Gap

技术缺口尚未被证明。先验证两个必要条件：目标代码中的 approximate predicate 是否在候选准入或图扩展处造成 grant stale-negative；以及 page-prefix RocksDB 强基线是否仍需要与每次 graph-page touch 分离的额外 SSD I/O。任一条件不成立，都不足以立项。

## Method Thesis

- **当前 thesis：** 先用源码 witness 和自然组合等价性原型判断是否存在 ANN-specific residual，而不是预设 page-addressed delta 是新机制。
- **唯一候选性质：** 在 grant visibility 不产生 false negative 的前提下，将 policy overlay 的定位或读取与已有 graph-page I/O 物理合并，并给出独立 page-prefix LSM 不具备的额外 I/O 上界。
- **状态：** hypothesis，未成为 contribution。

## Contribution Focus

- Dominant contribution：未冻结；等待等价性反证。
- Reused plumbing：normalized PolicyStore、MVCC/CSN、WAL、lazy revoke、batched exact verifier、snapshot retention。
- Explicit non-contributions：page-key schema、Bloom、cache、prefix iterator、WriteBatch、compaction、权限一致性 token。

## Proposed Gate

### G0：源码级 stale-negative witness

在拟复用 ANN 查询路径标出：predicate 输入、剪枝行、是否允许 unauthorized node tunneling、candidate refill。构造一个固定小图，证明 fresh summary 能发现 authorized top-k，而 stale grant summary 在同参数下不可恢复地丢失它。若 exact/post-filter 或 tunneling 已消除该失败，`KILL-NO-ANN-WITNESS`。

### G1：最强自然组合 baseline

实现或复用：

```text
key = (graph_generation, graph_page, policy_atom, begin_csn, node_id)
value = normalized permission payload
```

允许 prefix extractor、prefix Bloom、block cache、WAL/WriteBatch、page-prefix iterator/MultiGet、touched-page batching 与标准 compaction；其 DRAM、durability、query snapshot 和后台资源必须与候选完全一致。

### G2：单一 residual 判定

只比较一次 graph-page touch 导致的 policy lookup 数、物理读 I/O、读字节、grant 写字节和 p99。若候选只是改变 schema/cache，或相对 G1 三项决定性指标均小于 15%，`KILL-RENAME-MVCC-LSM`。只有发现不可由 G1 配置获得的单一性质，才返回方法设计阶段。

## Shared Correctness Contract

- grant tuple 与 routing delta 由同一 durable commit record 绑定到 CSN；只有 routing-visible watermark 越过该 CSN 才 ACK。
- 查询原子取得 `(q_csn, base_generation, delta_generation)`；ACK 后开始的查询满足 `q_csn >= grant_csn/revoke_csn`。
- correctness locator 不可驱逐；DRAM cache 只影响性能。若使用完整 locator，必须先给出 1B 字节公式。
- merge 以明确 `base_csn` 生成新 generation；旧版本在 `oldest_active_snapshot` 越过后回收。
- exact verifier 失败后继续 frontier/refill，直到满足 k、预算耗尽或搜索空间结束。
- `Return(q,v) => ExactAllow(q,v)`；policy-induced recall 与 ANN intrinsic recall 分开报告。

## Minimal Validation

1. G0 只需 deterministic unit graph，不下载数据、不跑大实验。
2. G1/G2 只做 schema/API 原型与受控冷缓存 I/O microbenchmark；先冻结预计时间、空间与数据盘路径，经 Gpt 审阅后才能执行。
3. 不进入 100M/1B；不在当前轮启动 DGAI/OdinANN 构建或实验。

## Decision

- `GO-METHOD-DESIGN`：G0 成立，且 G2 找到强自然组合不具备的单一、可形式化物理性质。
- `KILL-NO-ANN-WITNESS`：真实代码没有不可恢复的 grant stale-negative。
- `KILL-RENAME-MVCC-LSM`：page-prefix RocksDB 已提供相同 invariant 和 I/O 行为。
- `HOLD-ENGINE-API`：问题成立，但目标 artifact 无法以小改动接入。

## Compute & Timeline Estimate

- 当前文档阶段：0 GPU、0 新数据、0 实验写入。
- 后续若获批：先提交 G0/G1 的逐命令时间与空间预算；上限仍为 4 小时、10 GiB 数据盘新增、24 GiB RSS。
