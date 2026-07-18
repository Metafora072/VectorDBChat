# ContractANN C0：Dynamic ANN Update Contract 只读可行性门禁

## 1. 裁决

批准一次 **ContractANN C0 只读审计**。

本轮仅验证“动态 ANN / 向量数据库的 update completion 指标是否存在系统性语义不可比”，不运行更新实验、不执行 crash injection、不新增 instrumentation、不构建 matched-R，也不提出新持久化协议。

以下候选继续保持停止：

- Dynamic Vamana 写优化；
- Write Reducibility 的第二实现扩展；
- Semantic Repair Efficiency；
- queue coalescing；
- matched-R；
- RAG document-version atomic refresh；
- multi-NVMe/query-path 实验。

## 2. 必须修正的抽象

不得把：

```text
ack → online-searchable → fresh-process-searchable → crash-recoverable
```

当作所有系统共有的单调状态链。

更新合同至少包含五个相互独立的维度：

### A. Acknowledgement boundary

- 请求仅被接收；
- 请求进入内存队列；
- 更新 driver/future 返回；
- WAL/commit log 接收；
- 索引更新函数返回；
- publish/save 返回。

### B. Visibility boundary

- 当前更新进程内可查询；
- 同一服务进程的其他查询线程可查询；
- 同一节点的新查询进程可查询；
- 服务重启后可查询；
- 其他副本可查询。

### C. Index-readiness boundary

- 只存在于 delta / mutable segment；
- 可由 brute-force 或 fallback 路径查询；
- 已进入 ANN graph/index；
- 已完成 optimizer / compaction；
- 查询性能恢复到稳定 indexed path。

### D. Persistence boundary

- 仅在内存；
- 已发出 application write；
- application write completion；
- 已进入 WAL；
- 进程崩溃可恢复；
- OS 崩溃可恢复；
- 断电后可恢复。

除非源码和明确同步原语能够证明，不得把 WAL、write completion、fresh-process visibility或“未观察到fsync”直接解释为断电持久性。

### E. Replication / ordering boundary

- 单副本确认；
- 配置数量副本确认；
- operation ordering；
- read consistency；
- leader/consensus metadata；
- point data 是否进入共识。

这些维度必须用 contract vector 表示，不能强行压成单一“完成等级”。

## 3. 审计对象

### 研究系统

1. DGAI paper；
2. DGAI 当前 frozen artifact；
3. OdinANN paper；
4. OdinANN 当前 frozen artifact；
5. FreshDiskANN；
6. IP-DiskANN。

Paper 与 artifact 必须分开列行。论文主张不得自动套用到本地代码版本，本地行为也不得反向代表论文完整系统。

### 生产控制组

7. Qdrant；
8. Weaviate。

生产系统只用于证明真实产品已经显式区分 WAL、search visibility、index readiness、replica acknowledgement 等合同，不作为与研究原型进行性能排名的 baseline。

## 4. Primary-source 审计要求

每个系统只使用：

- 论文原文；
- 官方代码；
- 官方 API / storage / consistency 文档；
- 当前本地 frozen artifact 的真实调用链与已有 machine evidence。

禁止使用博客二手摘要替代核心结论。

对每个合同结论标记：

```text
PROMISED      论文或官方API明确承诺
IMPLEMENTED   源码存在对应路径/同步原语
OBSERVED      本地已有实验直接观测
UNKNOWN       证据不足
NOT_APPLICABLE
```

`UNKNOWN` 不得改写为“不支持”或“不持久”。

## 5. 每个系统必须回答

1. 用户或 driver 在哪个精确调用点获得成功返回？
2. 返回前是否写 WAL / commit log？
3. 返回前是否等待图更新、后台任务或 ANN index readiness？
4. 返回后新向量是否能由：
   - 当前对象查询；
   - 新进程查询；
   - 重启后的服务查询；
   - 其他副本查询？
5. 查询命中新向量时走：
   - ANN graph；
   - mutable delta；
   - unindexed segment；
   - brute-force fallback；
   - version fallback？
6. 哪个同步原语建立：
   - application completion；
   - process-crash recovery；
   - OS-crash recovery；
   - power-loss durability？
7. 删除、插入和 replacement 的合同是否不同？
8. 单机与分布式配置的合同是否不同？
9. 论文报告的 update throughput / latency 截止在哪个边界？
10. artifact 中能够复现的边界与论文主张是否一致？

## 6. Qdrant / Weaviate 控制证据

审计应特别核验：

### Qdrant

- `wait=false` 与 `wait=true` 的不同返回边界；
- WAL、update queue、mutable/unoptimized segment 与 fully indexed HNSW 的阶段；
- write consistency factor 与 write ordering；
- Raft 只覆盖哪些 metadata，point operations 是否进入共识；
- WAL 恢复声明与断电持久性证据的边界。

### Weaviate

- 成功响应前 WAL/commit-log 的官方承诺；
- acknowledged write 的 crash-recovery声明；
- HNSW commit log / snapshot；
- ONE / QUORUM / ALL replication acknowledgement；
- object visibility、vector-index visibility与replica visibility是否相同。

## 7. 禁止的比较

本轮不得：

- 将 DGAI、OdinANN、FreshDiskANN、IP-DiskANN 的原始吞吐直接排名；
- 把 paper 与 artifact 混为同一实现；
- 用不同 R、数据集、batch、线程、layout 的结果制造 ranking reversal；
- 仅凭“没有fsync”断言数据必然丢失；
- 仅凭“有WAL”断言断电持久；
- 将生产数据库与研究原型做绝对性能比较；
- 提出新的 WAL、MVCC、delta 或 recovery 机制。

## 8. C0 通过条件

ContractANN 只有同时满足以下条件才保留：

1. 至少三个系统对看似相同的“update完成/成功返回”提供不同的 contract vector；
2. 差异来自明确承诺或源码边界，而不是术语翻译差异；
3. 至少两个研究系统的已报告 update cost 截止在不同合同边界；
4. 存在一个后续可执行的共同操作序列，能够在不改变索引参数与数据集的情况下分别测量两个合同边界；
5. 该问题没有被现有向量数据库 benchmark 明确覆盖；
6. 结果不仅是“研究原型没有承诺数据库级 durability”。

本轮不要求、也不得预设 ranking reversal。是否发生 reversal 只能由后续同实现、同配置、多边界测量得出。

## 9. Kill 条件

出现任一情况即关闭 ContractANN：

- 研究系统根本没有外部 acknowledgement contract，只有离线 driver wall time；
- 所有差异都能由“库与数据库定位不同”完全解释；
- 生产数据库已明确公开这些合同，而研究原型不声称与其可比；
- 现有 benchmark 已同时覆盖 acknowledgement、visibility、index readiness 和 recovery；
- 无法设计同实现、同参数下的多边界测量；
- 贡献最终只是 API / 文档汇总表；
- 需要先运行 crash test才能判断只读审计是否有问题。

## 10. Write Reducibility 裁决

Rank 2 暂不批准。

原因：

- M2/M3 已经完成两个实现的核心 lifecycle 审计；
- 当前缺少真正独立的第三实现或不同状态机；
- 直接扩展容易形成 instrumentation bookkeeping，而不是独立研究问题；
- 它可以作为 ContractANN 的一个 measurement dimension，但不能并行立项。

只有 ContractANN C0 失败、且找到一个具有不同锁/队列/持久化状态机的独立实现时，才重新提交 Rank 2 gate。

## 11. 输出

输出：

```text
codex/share/2026-07-18/
contractann_c0_readonly_audit_0718.md
```

报告必须包含：

- contract-vector定义；
- paper/artifact分离矩阵；
- 每个结论的PROMISED/IMPLEMENTED/OBSERVED/UNKNOWN标签；
- update metric截止边界；
- 现有benchmark覆盖矩阵；
- 通过或Kill裁决；
- 若通过，仅给出下一阶段最小可执行序列与资源估算。

完成后停止。

不得自动：

- fault injection；
- crash testing；
-运行任何系统；
-新增instrumentation；
-实现新协议；
-启动Rank 2/3；
-转向RAG或query path。
