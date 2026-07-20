# Permission-aware SSD vector search：设计可行性与 RETHINK 门禁

**结论：保留 ACL-on-SSD 场景，但当前 page-addressed grant delta 方案为 `RETHINK`，不可直接进入完整实现或大规模实验。** 问题锚点有效：object-side grant 的 stale-negative 可能损害 authorized recall，而 revoke 的 stale-positive 可由最终 exact authorization 阻止泄露。然而，现方案可被 `PipeANN-Filter + Curator semantics + Zanzibar/RocksDB MVCC + graph-page-prefix delta` 的自然组合解释；未证明 key layout 之外的新机制。

## 事实纠正与资源边界

| 项目 | 核验结果 | 对方向的影响 |
|---|---|---|
| GateANN 63 GiB | 对应 1B、Rmax=16 的 neighbor store 单项，不是 100M | Claude 的内存动机需纠正 |
| GateANN 100M | artifact 约 17 GiB total（Rmax=32） | 100M 并不存在 63 GiB wall |
| 1B raw state | R16 约 94–102 GiB；R32 约 154–161 GiB，随 single/multi attribute 变化 | 64 GiB cap 是人为 deployment cost bound，不是本机硬墙 |
| 当前主机 | 251 GiB total，238 GiB available | 可运行大内存 baseline；比较须用 cgroup 公平限额 |
| 数据盘 | `/dev/nvme8n1` 1.8 TiB，当前可用约 759 GiB | 后续大工件只能放数据盘 |

## 外部方法评审

| 维度 | 分数 |
|---|---:|
| Problem Fidelity | 8.5 |
| Method Specificity | 6.0 |
| Contribution Quality | 4.0 |
| Frontier Leverage | 8.5 |
| Feasibility | 6.5 |
| Validation Focus | 7.0 |
| Venue Readiness | 4.5 |
| **Overall** | **6.275 / 10 — RETHINK** |

评审认可问题，但指出 ordinary RocksDB 已可使用 `(graph_page, policy_atom, begin_csn, node_id)` key、prefix Bloom、block cache、WAL/WriteBatch、page-prefix iterator、batching 与 compaction。若提案不能指出该强组合无法获得的单一性质，即使跑出 2x 性能也可能只是 page-key schema 工程优化。

## 决策门禁

1. **G0 Source witness**：在真实目标代码中定位 approximate predicate 的剪枝点并构造 stale-grant 不可恢复 recall 的最小反例；否则 `KILL-NO-ANN-WITNESS`。
2. **G1 Strong natural baseline**：允许 generic baseline 使用同样的 graph-page key、cache、WAL、batching、durability 和 compaction，不再用 node-keyed 弱对照。
3. **G2 Unique property**：只寻找一个强基线不具备的物理性质，例如把 overlay lookup 与 graph-page I/O 合并并给出额外 I/O 上界。若只是 schema/cache 或差异均小于 15%，`KILL-RENAME-MVCC-LSM`。

## Scope correction

- 核心只覆盖会改变 SSD graph record approximate predicate 的 object-side grants/revokes。
- user-role membership 与 hierarchy 更新通常走 query-side atom closure，不应人为展开成 page writes。
- lazy revoke、MVCC、WAL、snapshot token、exact verification 均是基线 plumbing，不是贡献。
- `time/type` 仅作为 workload 支持，不作为复合查询主贡献。

## 当前授权边界

本轮没有修改 DGAI/OdinANN、没有下载数据、没有启动实验。下一步只把门禁交给 Gpt 审阅；获批后再给出 G0/G1 的逐命令时间和空间预算，仍保持 <=4 小时、<=10 GiB 数据盘新增、<=24 GiB RSS，并禁止系统盘大写入。

## Primary sources

- GateANN paper: <https://arxiv.org/html/2603.21466>
- GateANN artifact: <https://github.com/GyuyeongKim/GateANN-public>
- Curator: <https://github.com/hatsu3/curator>
- PipeANN: <https://github.com/thustorage/PipeANN>
