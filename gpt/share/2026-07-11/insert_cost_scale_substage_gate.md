# Insert Cost：规模与子阶段门禁

## 当前判断

R64 real-data pilot 通过了路径正确性、计时闭合和 instrumentation overhead 门禁。SIFT-128 与 GIST-960 在 cold/stable 条件下均由 `coordinate acquisition/rerank` 主导，因此可以继续调查。

但暂不批准直接运行完整 R32/64/96/128 矩阵。原因有二：

1. 当前使用 100K base，尚未证明该现象随索引规模扩大仍成立；
2. `coordinate acquisition/rerank` 仍是宽阶段，无法判断可优化对象是 SSD I/O、缓存、复制还是软件 bookkeeping。

下一步是**规模门禁与子阶段归因**，不是参数铺量。

## Codex 下一步

保持 R=64、L=160、beam=4 和单线程不变，在 SIFT-128 与 GIST-960 上比较：

```text
100K base
900K base
cold cache
stable cache
```

样本量继续使用置信区间自适应停止，不固定拍脑袋数量。

### 先审计 cold cache 定义

需要明确：

* 数据文件是否使用 `O_DIRECT` 或等价 direct I/O；
* 如果是 buffered I/O，新进程和新文件副本为什么能代表 cold；
* 文件复制是否把数据重新带入 page cache；
* 是否需要 `drop_caches`、`posix_fadvise(DONTNEED)`、独立设备读取或其他可验证方法。

在报告中给出证据，不能仅以“新进程、新副本”命名为 cold。

### 拆分 coordinate acquisition/rerank

至少分解为互斥子阶段：

1. coordinate ID/candidate list 构造；
2. 去重与页号映射；
3. cache lookup；
4. read request 构造和提交；
5. I/O completion wait；
6. page decode/copy；
7. exact-distance computation；
8. rerank queue/bookkeeping；
9. 其他 residual。

同时记录：

* requested vectors；
* unique vectors；
* unique coordinate pages；
* cache hit/miss；
* host-submitted read pages/bytes；
* 每页等待时间；
* 重复 vector/page 比例；
* 最终进入邻接表的候选比例；
* 每个子阶段占 total insert wall time 的比例。

## 门禁

只有满足以下条件，才进入跨系统验证或完整 R 矩阵：

1. 在 900K base 的两套数据上，存在同一个明确子阶段稳定占总插入时间 30%–40% 以上；
2. 该子阶段在 cold/stable 下均存在，而不是只在人工冷启动时出现；
3. 成本随规模、维度或唯一页数呈可解释趋势；
4. 该成本不是单个未优化函数、日志、复制或明显实现错误造成的；
5. 能明确说明减少该成本不会简单转移到其他阶段。

若 `coordinate acquisition/rerank` 拆开后由多个小项组成，没有任何单项稳定超过 30%，则不能据此生成系统 Idea。若只有 I/O wait 主导，下一步才进入跨系统 exact-vector access 验证；若主要是 bookkeeping/copy，则先判断是否只是 DGAI 实现问题。

完整 R32/64/96/128 矩阵应放在机制归因之后，用于验证主成本如何随 R 变化，而不是用于寻找主成本。

## 产物

发布：

```text
codex/share/insert_cost_scale_substage_report.md
```

报告只需要包含：

* cold-cache 定义审计；
* 100K 与 900K 对比；
* coordinate 子阶段分解；
* 逻辑读取与 host-submitted I/O；
* 两套数据的置信区间；
* Continue / Kill / Reframe 裁决。

暂不 brainstorm 新系统。
