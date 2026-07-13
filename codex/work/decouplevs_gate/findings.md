# DecoupleVS Late-Stability Findings

## Result-to-Claim Verdict

- `claim_supported`: `partial`
- `confidence`: `high`
- 支持：高召回下 fixed-B trigger 几乎消失，并暴露约 0.5–1.2 ms vector tail。
- 不支持：residual 与 query difficulty 存在强可利用关系；fixed tuning 无法覆盖 residual；continuous dual-frontier scheduler 能形成新 Pareto。

## Postmortem

R1 证明 late stability 是真实现象，但 difficulty 与 stability/tail 的 Spearman 相关系数只有 0.12–0.22，per-query 最优 `B` 也没有随 difficulty quartile 稳定迁移。R2 中 earliest-safe oracle 相对 fixed baseline 的收益在有效 `W=8/16` 配置上只有约 9.5%/5.3%，而 workload-level fixed vector quota 已达到约 8.3%/3.8%。因此剩余方法空间不足以支持 query-adaptive continuous dual-frontier design。

## Future Constraints

不得把 exposed tail 的存在直接解释为 adaptive scheduler 的必要性。不得把 Oracle A、B、C 混合成一个组合上界。不得使用 final-set match 低于 100% 的异步 frontier replay 数据。不得把本部分复现称为官方 DecoupleVS 结果，也不得将结论外推到 compression、cache 或 update path。

如果未来只做描述性 tail characterization，必须补充第二数据集、官方 artifact 与跨设备验证。如果目标是独立系统机制，应转向新的 residual，而不是继续堆叠 look-ahead、page layout 或 intelligent cache。
