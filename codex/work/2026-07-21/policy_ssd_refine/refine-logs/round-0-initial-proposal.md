# Research Proposal: Page-Addressed Permission Maintenance for SSD Graph ANN

## Problem Anchor

- **Bottom-line problem:** 在十亿级 SSD 驻盘图 ANN 中，以固定的 policy-plane DRAM 预算支持动态 RBAC/ACL；权限更新后仍须保持 authorized top-k 可达，并保证任何返回结果都满足查询快照上的精确授权。
- **Must-solve bottleneck:** 现有 SSD filtered ANN 的 routing/filter summary 主要按只读数据设计。若权限 grant 必须随机原地重写 node/page summary，会产生 SSD 小写与更新尾延迟；若异步更新 summary，新授权对象会因 stale-negative routing 被永久剪掉，返回前 exact recheck 也无法恢复 recall。revoke 则允许 summary 暂时 stale-positive，但必须由精确验证阻止泄露。
- **Non-goals:** 不设计通用复合查询优化器；不发明新 ANN 图或新 ACL 语言；不把 MVCC、WAL、consistency token、Bloom、LSM 或 lazy revoke 本身写成贡献；不把 `time/type` 当主贡献；不承诺 24/32 GiB 下容纳 1B 的通用 DiskANN PQ state。
- **Constraints:** 复用 DiskANN/PipeANN/OdinANN 异步 SSD Vamana 数据路径；不依赖 GPU；真实服务器有 251 GiB DRAM，但正式比较使用 cgroup 冻结的 64 GiB deployment cap；所有大工件放 `/dev/nvme8n1`；首轮 preflight 上限为 1M、4 小时、10 GiB 新增数据、24 GiB RSS，且不在本 proposal 阶段运行。
- **Success condition:** 在 normalized MVCC policy store、Curator-equivalent lazy revoke 和 generic LSM summary-delta 强基线均存在时，仍能证明 SSD graph-page-aware grant maintenance 在至少两类权限模型上减少物理 permission-write bytes 与 update p99，同时满足 `unauthorized_output_count=0`、revoke snapshot contract 和相对 fresh synchronous-summary baseline 的 authorized Recall@k 门禁。

## Technical Gap

### Grounded baseline facts

- GateANN 的 63 GiB 数字对应 1B、`Rmax=16` 的 neighbor store 单项，不是 100M。其 100M artifact 总内存约 17 GiB；1B 默认 `Rmax=32` 的 raw core state 约 154–161 GiB。当前 251 GiB 机器可直接容纳，因此不能声称本机内存不足。
- PipeANN-Filter 已把 exact attributes 与索引放 SSD，只在 DRAM 保留 PQ 和约 4 B/vector Bloom summary，并在最终 rerank 时 exact verify。1B、PQ32 + Bloom4 的 raw state 约 33.5 GiB，可在 64 GiB cap 内运行。
- Curator 已使用 stale-positive Bloom + exact shortlist 支持 lazy revoke；Zanzibar/SpiceDB、MVCC、WAL 和 LSM 已覆盖版本、snapshot、watch、恢复与 compaction。

因此，`out-of-core metadata`、`lazy revoke` 或 `snapshot token` 均不是技术缺口。唯一可能的 ANN-specific gap 是：

> Grant 会改变“哪些 node/page 必须对 ANN routing 可见”。普通 KV delta 只保证新 tuple 可读，却不自动保证搜索前沿能够发现新授权对象。如何让新 grant 在 SSD 图数据路径中立即可达，又不为每次 grant 随机重写 node/page summary？

### 为什么 naive fixes 不够

1. **只做最终 exact verify：** 能阻止 revoke 泄露，但无法恢复被 stale-negative summary 剪掉的新授权结果。
2. **同步原地更新每个 node Bloom/summary：** 正确，但把 role/document fanout 转成随机小写，可能是自造写放大。
3. **仅使用 normalized MVCC/LSM：** 能持久化政策变更，却没有 graph-page routing 接口；若查询仍需逐 candidate 随机查 policy store，查询 I/O 可能主导。
4. **物化 user×document ACL：** 会人为制造 fanout，不能作为弱 baseline。
5. **缓存完整 per-user authorized bitmap：** 对冷用户、role combination 和 churn 可能产生内存与重建开销，且不是最小干预。

## Route Comparison

### Route A: Page-addressed grant delta（选择）

在固定 PipeANN-Filter-style base summary 上增加按 graph page 定址的 durable grant delta。Grant 只有在 delta 已可被 routing 路径发现后才发布；revoke 立即写入权威 MVCC policy store，但允许 base/delta 保留 stale positive，由最终 exact verifier 拒绝。后台按 page 合并 delta。

优点：直接解决 grant recall 与随机 summary rewrite 的矛盾；复用现有查询、存储与一致性原语；只有一个 ANN-specific 新接口。

风险：若 generic RocksDB delta + cache 已取得相同性能，则只是 LSM 重命名，应 KILL。

### Route B: Query-scoped authorization view cache（拒绝为主线）

为每个 tenant/role-signature 物化 compressed authorized bitmap，并缓存热点 view。

优点：membership check 简单，容易接入 GateANN。

拒绝原因：与 HoneyBee/Veda 的 role partition/view、bitmap cache 和普通 materialized view 太接近；冷用户 view 构建与 invalidation 引入第二个主问题，贡献易扩散。

## Method Thesis

- **One-sentence thesis:** 用 graph-page-addressed、只追加的 grant delta 维护“routing summary 是精确授权集合的保守超集”这一 invariant，使新授权立即可达、撤权无需同步重写 ANN summary，并由 snapshot-aware batched exact verifier 保证零未授权输出。
- **Why this is the smallest adequate intervention:** 不改 Vamana 图、不改 PQ frontier、不新建 per-role 图；只在 PipeANN-Filter 的 approximate-member 与 exact-member 两阶段接口之间增加一个 page-addressed grant overlay。
- **Why this route is timely:** enterprise RAG 的权限更新要求把只读 filtered ANN 变成持续维护的安全查询系统；无需引入 LLM/VLM/RL 组件，因为瓶颈是存储可达性与一致性，而不是学习或语义建模。

## Contribution Focus

- **Dominant contribution:** 面向 SSD graph routing 的 page-addressed grant delta 及其保守超集 invariant。
- **Supporting contribution:** 在固定 snapshot contract 下，将 stale revoke 从同步 ANN-summary 更新路径移除，并通过 batched exact verifier 保证输出安全；一致性协议本身明确复用 MVCC/WAL。
- **Explicit non-contributions:** Bloom filter、lazy revoke、MVCC、WAL、LSM compaction、policy token、图 tunneling、多谓词 planner、ACL 语言。

## Proposed Method

### Complexity Budget

- **Frozen/reused backbone:** SSD Vamana records、PQ frontier、io_uring pipeline、PipeANN-Filter approximate/exact predicate interface、normalized MVCC policy store、WAL/CSN、final vector rerank。
- **New components:** 一个 page-addressed grant log/index；一个固定预算 grant-page cache；一个 base-summary/delta merge policy。
- **Intentionally excluded:** 新图构建、role partition、per-user bitmap、learned planner、专用 time/range index、跨机器授权服务。

### System Overview

```text
policy update
  -> normalized MVCC policy WAL / commit CSN
  -> grant: append (graph_page, node, policy_atom, begin_csn) to durable grant delta
  -> publish grant CSN only after delta becomes routable
  -> revoke: publish exact deny/end_csn; summary cleanup deferred

query(user, vector, q_csn)
  -> compile user to tenant/role/direct-principal atoms
  -> PipeANN/OdinANN graph traversal
       base approximate policy summary
       OR page-addressed grant delta at q_csn
  -> SSD candidate/rerank pipeline
  -> batched exact MVCC authorization at q_csn
  -> return only exact-allowed top-k

background
  -> merge hot/large page deltas into new summary pages
  -> fsync + atomic manifest switch
  -> reclaim old delta after early snapshots exit
```

### Core Mechanism

#### State

1. `BaseSummary[v]`: PipeANN-Filter-compatible conservative membership summary at `base_csn`.
2. `GrantLog`: append-only records keyed by physical graph page and node ID; records contain normalized policy atom and `begin_csn`.
3. `GrantPageDirectory`: fixed-budget DRAM directory/cache from graph page ID to relevant delta extent and compact atom summary.
4. `PolicyStore`: authoritative normalized RBAC/ACL tuples with MVCC `begin_csn/end_csn` on SSD.

#### Publish rules

- **Grant:** write authoritative tuple and GrantLog record under one commit intent; fsync; install its page-directory visibility; only then publish/ACK CSN. A query with `q_csn` at or after the ACK must see the grant in `BaseSummary OR GrantLog`.
- **Revoke:** set `end_csn` in PolicyStore and ACK after WAL durability. BaseSummary/GrantLog need not synchronously delete the atom. This creates only a routing false positive; final exact verification rejects it.
- **Crash recovery:** replay policy WAL and reconstruct every committed grant after `base_csn` into GrantPageDirectory before opening queries. Unpublished grant intents are discarded.

#### Search invariant

For every query snapshot `q` and node `v`:

```text
ExactAllow(q, v) => BaseSummary(q, v) OR VisibleGrantDelta(q, v)
```

The routing predicate may have false positives but must have no policy-induced false negatives. Output is separately constrained by:

```text
Return(q, v) => ExactAllow(q, v)
```

This separates authorized recall from authorization soundness.

#### ANN-specific page addressing

Generic LSM delta is keyed only by logical policy tuple. The proposed delta additionally stores the graph page of each affected node and maintains a page-local atom summary. When traversal touches a candidate/page, it can determine whether relevant grants exist without a global policy lookup; if so, it fetches or caches only that page's delta extent. This is the only intended mechanism-level novelty.

#### Merge

When a page delta exceeds a frozen byte/count threshold, construct a replacement summary page from `BaseSummary + visible grants - expired exact permissions`, fsync it, atomically switch the manifest, then reclaim old delta after all earlier query snapshots complete. Threshold adaptation is not a contribution in the initial design.

### Modern Primitive Usage

- **LLM/VLM/Diffusion/RL:** none.
- **Reason:** no trainable component is required to maintain a storage correctness invariant. Adding a learned planner would weaken problem fidelity and create an unrelated contribution.

### Failure Modes and Diagnostics

- **Generic LSM absorbs the benefit:** compare against the same normalized PolicyStore with generic node-keyed delta and identical cache budget; if page addressing improves all decisive metrics by <15%, label `KILL-RENAME-MVCC-LSM`.
- **Role fanout is self-inflicted:** include normalized user-role and role-object updates; if gains occur only after expanding user×document ACL, label `KILL-SELF-INFLICTED-FANOUT`.
- **Grant delta hurts recall:** compare against fresh synchronous summary at the same ANN search parameters; any policy-induced missing authorized node beyond the frozen tolerance fails correctness.
- **Exact verifier dominates:** report policy MultiGet I/O separately; if batching/cache cannot bound it, the proposed routing optimization is irrelevant.
- **Delta saturation:** report stale-positive rate, delta bytes/page and compaction duty cycle; do not hide cleanup cost.
- **No real churn trace:** synthetic positives remain `HOLD-SYNTHETIC-CHURN`.

### Novelty and Elegance Argument

The proposal does not claim that versioned policies, append logs or lazy revoke are new. Curator already delays Bloom cleanup; Zanzibar and RocksDB provide the consistency/storage primitives; PipeANN-Filter already separates approximate and exact checks. The narrower claim is that grant has an ANN-specific reachability obligation absent from ordinary secondary indexes: a committed authorized object must remain discoverable through graph-page routing. A page-addressed grant delta is justified only if it preserves that reachability with materially fewer random summary writes than synchronous maintenance and materially fewer query I/Os than a generic logical-key delta.

## Claim-Driven Validation Sketch

### Claim 1: Page-addressed grant delta preserves snapshot-correct authorized search

- **Minimal experiment:** deterministic 1M crash/concurrency model plus exact top-k oracle; inject grant/revoke at WAL append、fsync、CSN publish、summary write、manifest swap、delta GC boundaries.
- **Baselines:** fresh synchronous summary、generic MVCC/LSM delta、Curator-equivalent lazy revoke。
- **Metrics:** unauthorized outputs、post-revoke stale allow、authorized Recall@k delta、lost acknowledged grants after recovery。
- **Decisive evidence:** all safety counts zero；ACK grant never becomes permanently unreachable；authorized Recall@k stays within frozen tolerance of fresh summary。

### Claim 2: Page addressing lowers policy-maintenance cost beyond generic storage machinery

- **Minimal experiment:** flat per-object ACL and hierarchical RBAC; separately sweep user-role、role-object、direct ACL、document updates under the same 64 GiB final-target memory model, using a 1M sanity before any larger scale.
- **Baselines:** normalized RocksDB PolicyStore + post-filter；generic versioned summary delta；PipeANN-Filter eager summary rewrite；proposed page-addressed delta。
- **Metrics:** physical/logical permission bytes、random writes/update、update p99、query graph/vector/policy I/O、query p99、compaction duty cycle。
- **Decisive evidence:** relative to strongest generic baseline, at least 2x lower physical permission-write bytes and 1.5x lower update p99, while query p99 regression <=10%, safety zero violations and recall gate passes in two permission models。

### Simplification/deletion check

- Remove page addressing and retain the same MVCC/WAL/delta/cache. If performance remains within 15% on update bytes、p99 and query I/O, the ANN-specific mechanism is unnecessary and the idea is killed.

## Experiment Handoff Inputs

- **Must-prove claims:** conservative-superset invariant under crash/concurrency；page addressing adds value beyond generic delta。
- **Must-run ablations:** no page address；eager revoke cleanup；no batched exact verify；materialized ACL versus normalized policy。
- **Critical data/metrics:** separate permission update types；authorized exact top-k；graph/vector/policy I/O；logical/physical write bytes；snapshot timeline。
- **Highest-risk assumptions:** realistic churn trace availability；page-local grant skew；exact verifier cost；role hierarchy fanout；PipeANN-Filter artifact adaptability。

## Compute & Timeline Estimate

- **GPU-hours:** 0。
- **Data cost:** existing SIFT-1M for correctness/sanity；permission relations initially generated and explicitly labeled synthetic。No 100M/1B data download is authorized in this phase。
- **Preflight target if later approved:** <=4 hours wall，<=10 GiB new data on `/dev/nvme8n1`，<=24 GiB RSS，system-disk large writes forbidden。
- **Design/refinement timeline:** 1 day for source/API feasibility and invariant tests design；implementation/experiment budget deferred to a later `experiment-plan` only if external review rates the method viable。
