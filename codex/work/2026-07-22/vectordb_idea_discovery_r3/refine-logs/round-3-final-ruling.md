# Round 3：A0 后最终裁决

Fresh-world proposal 未通过 claim gate：

- `α=0.1` 时 world Recall 0.992，但相对 mean-overfetch 仅 +0.0043；没有算法收益。
- `α=0.2` 时 exact UCB p50 已枚举 2,239.5/20K，HNSW-UCB Recall 0.8156，反而远低于 mean-overfetch 0.9859。
- `α=0.4` 时 exact UCB p50 枚举 7,365/20K，选择性消失。

根因是 ANN top-results oracle 不等于 ordered upper-bound certificate。继续换图、学 stopping predictor 或做 calibration 会改变论文核心，不能作为 refinement。

最终：三个 finalist 全部 KILL，保留 0 个。
