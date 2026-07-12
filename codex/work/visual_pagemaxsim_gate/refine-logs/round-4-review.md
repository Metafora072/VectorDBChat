# Round 4 Review

# Round 4 Final Re-evaluation

## 最终评分

| 维度 | 分数 |
|---|---:|
| Problem Fidelity | 10/10 |
| Method Specificity | 9/10 |
| Contribution Quality | 8/10 |
| Frontier Leverage | 9/10 |
| Feasibility | 10/10 |
| Validation Focus | 10/10 |
| Venue Readiness | 8/10 |

加权 Overall：

```text
0.15×10 + 0.25×9 + 0.25×8 + 0.15×9
+ 0.10×10 + 0.05×10 + 0.05×8
= 9.00
```

**Overall：9.0/10**

**Verdict：READY to execute Stage A CPU-only gate**

**Drift Warning：NONE**

这里的 READY 只批准 Stage A，不代表 P3、architecture、系统实现或论文 claim 已获批准。

## 实现时审计注意点

1. 所有正值乘法也要 outward round。尤其是 `Q_upper*R32_disk`、`gamma64*A_upper` 和 `gamma32*(A_upper+real_cauchy)`，建议统一实现 `outward_mul64`；不能只对最终加法做 `nextafter`。
2. 固定并记录 serving FP32 dot kernel、累加顺序和编译设置；禁用会改变语义的 fast-math/TF32。certificate audit 必须对同一 serving score。
3. 验证 persistent FP16 codeword 解码后的 FP32 bit pattern，以及 `R32_disk >= R_group`；任何 certificate violation 都先归类为实现错误。
4. persistent bytes 使用实际文件大小，DRAM codebook、pair tables 和 query-state 使用实际分配或可审计的精确字节数，不以理论字段和代替。
5. 严格执行早停：f9 仍为 100% pages、residual-direction gap 主导或成本被 f9 full scan 支配时，立即 Kill；不得用 K=1024、scheduler 或新 synopsis 补救。

**Simplification Opportunities：NONE**

**Modernization Opportunities：NONE**
