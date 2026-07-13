# DecoupleVS Residual Experiment Tracker

| 阶段 | 状态 | 产物 | 裁决 |
|---|---|---|---|
| Artifact/local audit | Complete | 本地无官方 DecoupleVS artifact；PipeANN isolated worktree | 使用明确标注的部分复现 |
| Layout export | Complete | `sift900k_graph.bin`、`sift900k_vectors.bin` | identity 与坐标抽样验证通过 |
| R0 reproduction | Complete | `r0_batched/`、`r0_batched_widths/` | W=8/16 定性恢复通过，W=4 打平 |
| R1 characterization | Complete | `r1_batched/`、`analysis_batched/r1_*` | residual 存在，difficulty 关系弱 |
| R2 mutually exclusive oracles | Complete | `r2_batched/`、`analysis_batched/r2_*` | final-set match 100%；fixed quota 基本覆盖 oracle 空间 |
| Result-to-Claim | Complete | `findings.md` | `partial`，confidence high；方法 claim 不支持 |
| Second dataset | Stopped | 无 | SIFT 已不满足进入设计条件 |
| Dual-frontier implementation | Stopped | 无 | 不批准继续设计 |
