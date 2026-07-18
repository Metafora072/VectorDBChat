# Dynamic ANN Repair Bounds B0：Final Closure

## 1. 最终裁决

正式接受 B0 的双层结论：

```text
theorem gate: PASS-B
research / implementation gate: STOP
```

B0 已经在一般 bounded-degree directed metric graph、固定 deterministic greedy search 和单点删除模型下，构造了完整的 finite-radius local-certificate impossibility：

- 对任意固定有限半径 `r`；
- 两个实例具有相同 dataset、query/entry distribution、删除点局部视图和删除前成功轨迹；
- 删除后恢复 `P_success=1` 所需的 minimum extra edge additions 分别为 `0` 与 `1`；
- 因而任何只依赖固定半径局部视图、对所有实例 sound 的 exact/complete lower-bound 或 skip oracle，都会在某些正 optimum 实例上退化为 `0`。

该证明可作为内部理论负结果保留。

## 2. 不允许外推的结论

不得声称：

- 一般 local repair 不可能；
- Wolverine、SPatch、Greator 或 IP-DiskANN 的修复无效；
- query-conditioned/global-summary certificate 不可能；
- Vamana/DiskANN builder output 上也存在同样下界；
- `0/1` edge gap 可以转化为 adjacency-record、4 KiB page 或 SSD write gap；
- 该结果已经形成可投稿的 Dynamic ANN 算法或系统贡献。

B0 只关闭：

```text
universally sound
fixed finite-radius
deletion-centered
pure-local
exact / complete / instance-optimal
pre-I/O repair oracle
```

保守过修、充分条件、query trace/global state、learning heuristic和受限 graph-family witness均不在定理覆盖范围内。

## 3. 为什么不进入 B1

B1 不获授权，原因包括：

1. 构造适用于一般 directed metric graph，未证明属于 Vamana、HNSW、alpha-RNG 或 MSNET builder family；
2. optimum separation 只有 `0/1` extra edge；
3. edge gap 可能被相同 adjacency record 或 page granularity完全吞没；
4. 无 constructive repair witness 或 approximation algorithm；
5. 独立评分为：
   - significance `5/10`
   - novelty `4/10`
   - depth `5/10`
6. 该结论不足以支撑用户需要的完整系统型毕业工作。

继续将 theorem 收紧到 Vamana family 需要新的独立理论动机，不能作为 B0 自动 continuation。

## 4. 研究线总状态

以下研究线继续保持关闭：

- Dynamic Vamana write optimization；
- queue coalescing；
- neighbor-repair write suppression；
- architecture frontier A0候选；
- repair-bound B1；
- ContractANN；
- Write Reducibility；
- Semantic Repair Efficiency；
- matched-R；
- 原 multi-NVMe placement；
- RAG pivot。

M0–M3、A0 与 B0 应作为完整的探索与否定性证据归档，不继续投入实现资源。

## 5. 下一步边界

下一阶段必须选择一个独立问题，满足：

- 由新的 runtime observation、真实应用需求或独立 workload驱动；
- 不以 M0–M3 已推翻的 visibility/write 因果为前提；
- 不从 A0 已关闭的四类架构组合中重新排列模块；
- 不依赖把 B0 的一般图负结果包装成系统设计；
- 先完成 problem significance 与 primary-work gate，再决定 profiling。

本文件完成后保持停止，不自动生成新实验或新方向设计。
