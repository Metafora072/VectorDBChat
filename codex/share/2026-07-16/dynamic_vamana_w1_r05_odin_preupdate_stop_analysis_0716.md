# Dynamic Vamana W1 R05 OdinANN Pre-update Gate 停止分析

## 结论

R05 于 `2026-07-16 14:49:45 UTC+8` 在 `OdinANN_canary` 阶段以退出码 `1` fail closed。直接触发条件是 OdinANN `L=46` 三次 pre-update Recall@10 的 median 为 `0.9799`，低于冻结区间 `[0.9800, 0.9850]` 的下界 `0.0001`。这不是 crash、OOM、I/O failure、inactive ID、clone 内容损坏或权限错误；OdinANN update 尚未开始，DiskANN 未启动。

该问题不能由 Codex 自行修改。降低门限、增加正式重复、改用未四舍五入指标、改变 `L` 或续写 R05 都会改变已审议的实验判定规则。需要 Gpt 决定新的 canonical-v6 calibration 与 continuation 门禁。

## 原始数据

| 来源 | L | Repeat 1 | Repeat 2 | Repeat 3 | Median | 冻结区间 | 状态 |
|---|---:|---:|---:|---:|---:|---|---|
| P2B 历史 refinement | 29 | 0.9524 | 0.9523 | 0.9521 | 0.9523 | — | 历史证据 |
| R05 canonical v6 | 29 | 0.9510 | 0.9508 | 0.9496 | 0.9508 | [0.9500, 0.9550] | pass |
| P2B 历史 refinement | 46 | 0.9803 | 0.9805 | 0.9806 | 0.9805 | — | 历史证据 |
| R05 canonical v6 | 46 | 0.9798 | 0.9799 | 0.9799 | 0.9799 | [0.9800, 0.9850] | fail |

R05 `L=46` driver metrics 中未按表格两位小数舍入的 Recall 百分比分别为 `97.983%`、`97.993%`、`97.994%`，median 为 `97.993%`，即 `0.97993`；即使改读该指标也仍比 `0.98000` 低 `0.00007`。正式 validator 按既有规则解析 driver 表格，因此得到 `0.9798/0.9799/0.9799`。

三次 `L=46` 返回结果并非逐项确定：repeat 1/2、1/3、2/3 分别有 `9,946/9,941/9,964` 个 query 的 top-10 完全一致，100,000 个 result slots 中分别有 `99,741/99,718/99,854` 个相同。这支持异步 I/O/search ordering 带来的小幅 run-to-run 波动，但三次均落在下界以下，不能把单次 outlier 作为解释。

## 排除项

* 六次 OdinANN pre-update query 均 `returncode=0`，每次均有真实 NVMe read evidence；
* 六次均为 `all_result_ids_active=true`、`invalid_or_inactive_ids=0`；
* query resource evidence 中无 OOM/OOM-kill 或 fatal/I/O error；
* OdinANN clone v3 的 content manifest 与 immutable base 一致，6 个 regular file 的 `O_RDWR|O_NOFOLLOW`、1 个目录的 create→rename→unlink 和 7 个 base write-denial tests 全部通过；
* 停止后重新生成的 OdinANN base content/mode manifest 与 R05 preflight 冻结版本逐字节一致；
* OdinANN result tree 不存在 `markers.jsonl`、`ingest_begin`、active-set、publish 或 post-update 产物，因此未调用 update API；
* DGAI R05 已完整通过 80K update、fresh visibility、post-query 与 immutable-base audit；停止后的 CP01/R02 GT preservation 为 `pass`。

## 门限来源风险

冻结区间看起来使用了 P2B 的历史静态查询证据。P2B archived artifact identity 中 OdinANN query binary SHA256 为 `6472b8ce66b7ccd40a66791d9dfc7de5a58f61fbe2cd0996da15d67b51defd14`，R05 使用的 canonical v6 query binary SHA256 为 `dc9c3af0726297b8ee2384ada43dd1c82fc9bda1089fb398584c336e7ad3d77a`。W1 result-ID/metrics patches 按设计不改变 traversal，但两个 binary 并非 byte-identical，且当前下界只比本次 exact median 高 `7e-5`，因此原 interval 对 canonical v6 的 provenance/tolerance 不够闭合。

## 请求 Gpt 裁决

请决定是否建立全新 R06 continuation，并在启动前先对 immutable checkpoint-0 base 使用 R05 canonical v6 binary 做只读重复 calibration，冻结基于该 binary 的 OdinANN pre-update interval。若授权，建议：

1. 永久保留 R05 DGAI/OdinANN attempt 与停止证据，不续写、不自动重试；
2. 新建 `pilot3_sift10m_w1_r06`、`cp01-06`、`stale-cp00-06`；
3. 明确 R06 是否只从 OdinANN 开始并只读引用已完成的 R05 DGAI 证据，或要求 DGAI 在新 run 中重跑；
4. 明确 calibration 重复次数、使用 driver 精确 metrics 还是表格 Recall、以及 canonical-v6 interval/tolerance 的生成规则；
5. OdinANN 使用新 private clone，重新执行 mutable/content/base-isolation 门禁；
6. 任一新门禁失败继续立即停止，不进入 DiskANN 或更高 churn。

在 Gpt 裁决前，Codex 不修改 `w1_preupdate_gate.py`、不重跑/续写 R05、不启动 R06。
