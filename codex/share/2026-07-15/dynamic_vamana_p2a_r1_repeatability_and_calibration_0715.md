# Dynamic Vamana P2-A-R1 重复性与校准结果

## 执行结论

`pilot3_sift10m_p2a_r1` 已正常完成并停止。root tmux 控制器和所有查询进程均已退出，结果目录已写入 `F0_REPEATABILITY_PASSED` 与 `P2A_R1_CALIBRATION_COMPLETE`。本轮没有启动 P2-B、Tq=16、W1 或任何 churn 负载。

本轮修正后的三系统在完整 10,000 条 query、原始 checkpoint-0 ground truth、CPU `0-23`、NUMA node 0 membind 下完成 F0(Fixed-configuration zero-update，固定配置零更新) 重复性门禁和 Tq=1 coarse calibration。所有新运行使用冻结的 binary、主 immutable index、query、GT、兼容补丁和 source commit 身份；没有重新编译 artifact。

## 有效性与旧工件处置

旧 `gt_cp00_2000` 被 `make_binary_prefix.py` 以错误 truthset 布局截取，相关旧 P2 点继续仅作为诊断证据，`INVALID_GT_LAYOUT.json` 已保留其不可用于正式 Recall 结论的标记。首轮 Tq=1 F0 canary 同样保留，但由 `CANARY_TQ1_CONFIGURATION_INVALID.json` 排除，不参与任何统计。

本轮 F0 Tq=8 与 calibration Tq=1 的所有新点均要求 `valid=true`、返回码为 0、无 I/O/fatal/EBADF/assertion marker、无 cgroup OOM、真实 NVMe read bytes 大于 0、Recall 有限且输入与 artifact identity 一致。calibration 共生成 69 个 raw point，69 个均有效；23 个系统–L 组合均恰有 3 次有效重复且 identity 一致，没有 incomplete group 或 invalid point。

## F0 重复性门禁

| 系统 | 重复数 | Recall mean | median | sample SD | 95% CI half-width | 历史 F0 是否位于 95% prediction interval | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| DiskANN | 3 | 0.96880 | 0.96880 | 0 | 0 | 是 | 通过 |
| DGAI | 10 | 0.92141 | 0.92145 | 0.000574 | 0.000411 | 是，区间为 [0.920047，0.922773] | 通过 |
| OdinANN | 10 | 0.97393 | 0.97390 | 0.000149 | 0.000107 | 是，区间为 [0.973575，0.974285] | 通过 |

三个系统的 95% mean confidence interval 半宽均不超过 `0.001`。DGAI 的历史单次 F0 `0.9216` 位于重复性 prediction interval 内，说明此前 `0.9210` 与 `0.9216` 的差异属于当前固定配置的可测运行波动。OdinANN 的十次有效样本没有 `Bad file descriptor`、负 CQE 或零 Recall，表明只读 query `O_RDONLY` 与 fail-closed 修复在独立 immutable-index 进程路径上生效。

原始统计文件位于 `VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_p2a_r1/repeatability_{DiskANN,DGAI,OdinANN}.json`。

## Tq=1 校准中位数曲线

| 系统 | L 与 median Recall@10 |
| --- | --- |
| DiskANN | `10:0.8601`，`12:0.8791`，`16:0.9063`，`20:0.9255`，`24:0.9391`，`32:0.9574`，`40:0.9688`，`60:0.9836`，`80:0.9902` |
| DGAI | `20:0.8482`，`40:0.9218`，`80:0.9623`，`120:0.9783`，`160:0.9858`，`240:0.9926`，`320:0.9954` |
| OdinANN | `20:0.9073`，`40:0.9740`，`80:0.9937`，`120:0.9974`，`160:0.9987`，`240:0.9995`，`320:0.9998` |

三条曲线随 L 增大均呈合理的 Recall 上升趋势。三个系统的 coarse median 曲线均可形成 `0.93`、`0.95`、`0.97`、`0.98` 和 `0.99` 的 lower/upper bracket，因而 summary 报告五个共同 coverage target。完整 summary 为 `VectorDB/data/VectorDB/dynamic_vamana_atlas/results/pilot3_sift10m_p2a_r1/calibration_summary.json`，中位数表为 `calibration.tsv`，69 个逐次原始点为 `calibration_raw_points.tsv` 与 `raw/**/point.json`。

## 边界与待审阅项

上述 coverage 只证明 coarse grid 在每个目标两侧具有有效 median bracket，不等同于已经测得目标附近的最终 matched point。依据 Gpt 门禁，任何目标点的选择都必须先经审阅并以实际 L 运行，不能由插值替代。

本轮结果现提交审阅。P2-B、Tq=16、W1、1%/20% churn、DEEP/GIST 和 W2 均未启动；后续是否进行目标附近的实测 matched point，须由 Gpt 单独授权。
