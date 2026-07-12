# PageMaxSim P2 Reconsideration

**日期**：2026-07-12

**裁决修正**：`single centroid-radius = KILL`；`PageMaxSim = REVISE / 允许一次新的 CPU-only synopsis gate`。

## 1. 为什么 P2 失败不等于问题永久关闭

P1 的 page oracle 是真实信号：raw-int8 可从 792.6 页降到181.8页，f9-int8可从95.1页降到80.9页。P2只测试了每页一个 centroid/radius 的球形外包络。它读取100%页面，说明这个外包络过松，不证明所有page synopsis都无法逼近oracle。

旧bound同时混合了两类损失：

1. 一个page中的多个语义/视觉cluster被包成一个大球；
2. `q·e <= ||q||||e||` 丢失residual direction。

增加scheduler不能解决这两类几何松弛；应先换更准确且仍安全的集合表示。

## 2. 推荐的最小机制

**Residual-Certified Multi-Ball Page Synopsis**：训练一个corpus-shared token codebook，按codeword ID对document tokens重排并装页；每页只保存其包含的 `(codeword ID, outward max residual radius)`。page不再是一个大球，而是多个小residual balls的并集：

```text
U(q,page) = max_k_in_page [q·codeword_k + safe residual term]
```

codeword向量全corpus共享，不在每页重复。per-page metadata只保存ID、count和radius。certificate严格上界真实serving FP32 MaxSim，所有residual/dot/norm/add/multiply使用FP64 outward arithmetic并计入FP32 accumulation error。

这不是新的outer bandit、codebook、PQ或scheduler；唯一候选贡献是exact 4 KiB page admission control。

## 3. 为什么暂不选择其他路线

- **更复杂scheduler**：P2已证明page order不是主因；bound不紧时scheduler只增加CPU。
- **learned/heuristic page router**：可能形成近似quality/I/O trade-off，但会进入PLAID/WARP/token-pruning边界，且不再exact；本轮不混入。
- **angular cap / hierarchy / per-token sketches**：可能更紧，但会扩大方法或metadata。先用最小multi-ball做几何证伪；失败后不现场堆模块。

## 4. 两级早停 gate

### Stage A：K=64/256

- 额外256个disjoint ViDoRE pages只训练codebook；原64 documents/16 queries完全held out。
- raw-int8与f9-int8分别训练codebook。
- 比较single-ball、multi-ball、exact-page envelope、page oracle。
- 实际写出persistent synopsis；计入decoded FP32 DRAM codebook、pair tables、query state与完整CPU。
- 只用sequential和fixed best-upper-bound-first，不优化scheduler。

立即停止：

- certificate violation非零：先修实现；
- f9-int8仍读100%页面：机制Kill；
- residual-direction gap仍主导：机制Kill；
- 完整成本被f9 full scan支配：机制Kill。

### Stage B：K=1024

只有Stage A已在f9上安全跳页且形成非支配信号才运行。通过也只允许请求P3，不批准系统或论文claim。

## 5. 成本与结论

- GPU：0。
- 新数据：ViDoRe同一公开Parquet，无下载需求。
- CPU：额外编码约35分钟；K=64/256训练与replay约10–30分钟。
- 数据、cache、环境继续只放项目NVMe。

四轮独立refinement从6.8提升至9.0/10，最终结论是 **READY to execute Stage A CPU-only gate**。完整数值安全规范、成本格式与评审历史见：

```text
codex/work/visual_pagemaxsim_gate/refine-logs/FINAL_PROPOSAL.md
codex/work/visual_pagemaxsim_gate/refine-logs/REVIEW_SUMMARY.md
```

因此，对PZ问题的直接回答是：**有设计空间，但只值得一次小而严格的multi-ball synopsis gate；当前不能说一定能解决，也不应直接进入P3。**
