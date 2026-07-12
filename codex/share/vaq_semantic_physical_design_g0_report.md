# VAQ 语义约束物理设计 G0 报告

## 裁决

**KILL：不进入 semantic what-if abstraction 或 advisor 架构审查。**

实验确认了一个较弱的事实：在自然 join multiplicity 下，Recall@30 统计等价的 HNSW 物理设计可以产生显著不同的 COUNT/SUM/AVG 误差，且 MovieLens 的差异确实与漏失对象的高权重分布有关。但这个现象没有改变物理设计选择：在两套数据、两类查询的四个 case 中，使用 local recall 的 vector-local Pareto frontier 与使用 downstream answer error 的 joint-semantic Pareto frontier **配置集合完全相同**；V→R sequential baseline 在四个 case 中均到达 joint frontier，遗漏点为 0。Recall 对负 answer error 的配置级 Spearman 排名相关为 0.9833–0.9975。因此触发 Gpt gate 的 Kill 条件：semantic objective 改变误差数值，却没有产生 sequential optimization 无法达到的新设计点。

本轮没有实现 advisor，没有进入 held-out simple-rule 或 architecture review，也没有扩大到 materialized view、buffer、tiering、布局等旋钮。

## Workload 与数据

### A：Exqutor-compatible TPC-H + SIFT1M

- 使用 Exqutor 官方仓库（commit `d9df41c`）中的 TPC-H kit 生成 SF1；关系和查询形状来自其 vector-augmented SQL workload。
- 对 `part` 的前 200,000 行挂接 SIFT1M 的 128 维真实图像描述向量；`p_mfgr` 是标量分区/过滤属性。
- 事实表使用原始 6,001,215 行 `lineitem`，按 `l_partkey` 精确聚合 `COUNT(*)`、discounted extended price `SUM` 和 quantity `SUM`。
- 60 个 SIFT held-out query vectors；SIFT 与 TPC-H 标量独立，因此该数据作为标准 VAQ/control workload，而不作为真实相关性证据。

### B：MovieLens-20M

- 10,381 个具有 genome scores 的 movie，每个 movie 的 1,128 维 tag-relevance 向量经 L2 normalization。
- 标量属性为真实 primary genre；少于 80 个对象的稀有类别仅合并为 `OTHER`，未打乱或复制标签。
- 事实表为 20,000,263 条真实 ratings，按 movie 精确记录 rating count、rating sum 和高分（≥4）count。
- 60 个 query vectors 由同 genre 的两个真实 movie genome vectors 归一化求和，避免 indexed-item self match；关联标签和事实权重均来自原始数据。

所有下载、环境、TPC-H 生成数据、索引与结果均位于独立数据盘：

```text
/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0
```

实验结束时该目录为 3.4 GiB；系统盘使用率在实验前后均为 46%，数据盘使用率为 13%。

## 查询与 exact reference

每个数据集执行两类查询，各 60 条：

1. `scalar_filter_topk_join`：scalar filter → ANN top-30 → fact join → COUNT/SUM/AVG；对应 Exqutor 的 filter/vector/join/aggregate 形状。
2. `threshold_join_group_aggregate`：以 exhaustive top-30 的第 30 个距离作为 query-specific threshold，执行 ANN range → fact join → category group/rank → COUNT/SUM/AVG。

全量 float32 L2 scan 提供 exact reference。ANN 候选物化后执行确定性的精确事实聚合，等价于由强 optimizer 固定普通 relational plan；因此结果不包含 join-order/cardinality 误判。记录了 local Recall@30、join tuple recall、group coverage、COUNT/SUM/AVG relative error、top-group rank overlap、false-negative 高权重占比与 group HHI。

## 实际物理设计与预算

只运行 gate 规定的小空间：

- D0：global ANN + selectivity-sized one-shot post-filter；
- D1：global ANN + native scalar pre-filter；
- D2：attribute-partitioned local ANN indexes；
- D3：scalar bitmap + adaptive global ANN expansion。

ANN 为真实 HNSW（M=12，`efSearch` 16/32/64/128）与 IVF-Flat（`nprobe` 1/2/4/8/16）。每个 index 使用 99% build + 1% timed insert，实际序列化到数据盘计量 bytes。

| 数据 | ANN | Global bytes | Local total bytes | Global build | Local build | Global update | Local update |
|---|---:|---:|---:|---:|---:|---:|---:|
| TPC-H/SIFT | HNSW | 125.737 MB | 125.737 MB | 3.53 s | 2.37 s | 0.158 ms/vector | 0.100 ms/vector |
| TPC-H/SIFT | IVF | 104.133 MB | 104.520 MB | 0.59 s | 1.04 s | 0.010 ms/vector | 0.018 ms/vector |
| MovieLens | HNSW | 48.051 MB | 48.051 MB | 0.61 s | 0.45 s | 0.419 ms/vector | 0.480 ms/vector |
| MovieLens | IVF | 47.379 MB | 47.909 MB | 0.17 s | 2.20 s | 0.104 ms/vector | 3.739 ms/vector |

Global/local HNSW 容量几乎完全相同；IVF local overhead 分别为 0.37% 和 1.12%。因此 error-propagation 配对不是大索引对小索引。Query latency 是 scalar/vector candidate access 的 wall time；candidate count 是物化/请求候选数，不冒充 HNSW 内部未暴露的 visited-node count。

## Error propagation 事实

Recall 等价采用预注册的自然分辨率：一次 top-k query 的一个结果对应 `1/k = 0.0333`，只有 paired bootstrap 95% CI **完整落入** ±1/k 才判为等价。Downstream difference 的 paired bootstrap 95% CI 必须排除 0。以下均为真实物理设计配对；过滤 top-k 的两侧都返回 30 条，排除了结果不足造成的伪差异。

| 数据 / 查询 | 配对 | Recall diff（95% CI） | Downstream error diff（95% CI） | 观察 |
|---|---|---:|---:|---|
| TPC-H / filter-topk | D0 HNSW@16 − D1 HNSW@64 | −0.00278 [−0.00500, −0.00056] | +0.00047 [+0.00010, +0.00095] | 小但显著 |
| TPC-H / threshold-group | D0 HNSW@128 − D2 HNSW@128 | −0.00722 [−0.01222, −0.00278] | +0.00823 [+0.00236, +0.01638] | local index 更接近 exact |
| MovieLens / filter-topk | D2 HNSW@64 − D3 HNSW@64 | +0.00389 [0, +0.00778] | −0.01252 [−0.03495, −0.00010] | D3 漏失高权重 movie |
| MovieLens / threshold-group | D0 HNSW@64 − D2 HNSW@16 | −0.00167 [−0.00944, +0.00611] | +0.00540 [+0.00044, +0.01181] | 相同 recall 下加权误差不同 |

最清楚的分布证据来自 MovieLens filter-topk：D2 与 D3 的平均返回数同为 30；D2/D3 join tuple recall 为 0.99868/0.99444，false-negative high-weight share 为 0/0.0613，其差异 CI 为 [−0.1226, −0.0113]。这说明 local recall 确实不能精确恢复 answer-error 数值。

然而该结果没有形成 design ranking reversal。配置级 `Recall` 与 `−downstream_error` 的 Spearman 相关如下：

| 数据 | Filter-topk | Threshold-group |
|---|---:|---:|
| TPC-H/SIFT | 0.9912 | 0.9891 |
| MovieLens | 0.9833 | 0.9975 |

即使少数相近 recall 配对的误差幅度不同，更高 recall 几乎总能给出正确的设计排序。

## 五类 Oracle 与最终 Kill

小空间直接枚举，不设无自然依据的 scalarized 权重或质量阈值：

- Vector-local：`latency, bytes, build, update, 1−local_recall` 的弱 Pareto frontier；
- Relational-local：`latency, bytes, build, update, candidate_count` 的弱 Pareto frontier；
- Sequential V→R：先保留 vector-local frontier，再按 joint semantic objectives 取 frontier；
- Sequential R→V：先保留 relational-local frontier，再取 vector frontier 和 semantic frontier；
- Joint semantic：`latency, bytes, build, update, downstream_error` 的弱 Pareto frontier。

| 数据 / 查询 | Vector-local 点 | Relational-local 点 | V→R 点 | R→V 点 | Joint 点 | Joint − V→R |
|---|---:|---:|---:|---:|---:|---:|
| TPC-H / filter-topk | 15 | 4 | 15 | 3 | 15 | **0** |
| TPC-H / threshold-group | 12 | 2 | 12 | 2 | 12 | **0** |
| MovieLens / filter-topk | 16 | 2 | 16 | 2 | 16 | **0** |
| MovieLens / threshold-group | 12 | 1 | 12 | 1 | 12 | **0** |

四个 case 的 V→R 配置集合均与 joint semantic frontier 完全相同。换言之，semantic error 能解释同 recall 附近的误差幅度，却没有产生 MINT-like vector tuning 后无法选择的 Pareto 点。继续做 advisor 最终只能写成“把 end-to-end quality 放入 cost function”，正中 gate 的 Kill 条件。

因此停止执行：不做 simple-rule held-out 扩展，不邀请 Claude 进入 architecture review，不再构建索引。

## 可复现产物

- 执行器：`codex/work/vaq_semantic_g0/run_g0.py`
- Oracle 分析：`codex/work/vaq_semantic_g0/analyze_oracle.py`
- Full query records：`data/vaq_semantic_g0/runs/full/{tpch_sift,movielens}/query_records.csv`
- Error propagation：`data/vaq_semantic_g0/runs/full/analysis.json`
- 五类 oracle：`data/vaq_semantic_g0/runs/full/oracle_analysis.json`
- Index metadata：`data/vaq_semantic_g0/runs/full/{tpch_sift,movielens}/index_metadata.json`

## 边界与不主张事项

- 没有运行 Exqutor 原型本身；复用了其 TPC-H workload/query semantics，并通过 candidate materialization + exact aggregation 消除普通 plan confound。
- TPC-H 使用 SIFT 向量挂接，不主张 vector–scalar correlation；真实相关性结论只来自 MovieLens。
- 未将 Python callback/FAISS selector 的 latency 外推为生产 PostgreSQL 性能；本轮只比较受控实现中的 Pareto 集合。
- 没有证明所有 VAQ workload 都可由 recall 优化；只证明当前批准的 G0 未满足“sequential baseline 遗漏 joint Pareto 点”这一继续条件。
