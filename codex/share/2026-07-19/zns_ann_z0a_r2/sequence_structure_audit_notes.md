# Z0A R2 sequence-only 审计说明

## 判定边界

本审计只使用主机提交序列，不使用墙钟、时间戳、simulator 状态、GC、relocation 或 age。页版本事件的唯一顺序定义为 `(submit_seq, page_index_within_request)`：请求之间按主机提交序列排列，同一请求内部按递增页偏移排列。FULL 可以记录并比较这个顺序；NATIVE 与 SHIM-CONTROL 不产生 append record，因此两种 control 只能与 FULL 比较 application bytes、request/page-event counts、phase/role counts 和 active set，不能声称其未观测序列与 FULL 相同。

独立分析器为 `sequence_structure_audit.py`。它直接解析 `raw_trace.bin`、`normalized_pages.bin` 与 `trace_meta.json`，将 run-scoped hash、inode 和 clone 路径替换为 `(file role, basename, aligned offset)` 语义页键，计算：

- versions per page；
- 相邻同页版本之间的 page-event sequence reuse distance；
- 以 `update_or_replacement_id` 分组的 unique-page、page-event 和 request fanout；
- 各 phase 的 repeat fraction、HHI、top-1/top-10/top-1% page concentration；
- 重写页 first/last version sequence span；
- 跨 FULL 轮次的 exact semantic fingerprint、TV、KS 与一阶 Wasserstein 距离。

所有距离仅作描述，不新造 PASS 阈值。DGAI 可以使用 exact equality；OdinANN 应按其自然并发导致的轮间分布变化呈现。

## 对既有正式 Z0A 数据的回算

回算产物为 `formal_sequence_audit_original_z0a.json`。它覆盖既有 8 个 DGAI FULL、8 个 DGAI control、5 个 OdinANN FULL 和 5 个 OdinANN control；这些旧 control 不是 R2 明确区分的 NATIVE/SHIM-CONTROL，因此结果只能验证分析器和提供自然变动基线，不能替代 R2 六组随机 triplet。

DGAI 的 8 个 FULL 轮次在 semantic sequence fingerprint 及五组要求的分布上全部逐项相同，pairwise TV、KS、normalized W1 均为 0；phase-local concentration 也逐项相同。每轮为 19,333 requests、22,250 page events、3,334 unique semantic pages；versions/page 中位数为 7，reuse event-gap 中位数为 1,839，2,000 个显式 update 的 unique-page fanout 中位数为 11。既有 FULL/control accepted aggregate signature 也完全相同。

OdinANN 的 5 个 FULL fingerprint 不相同，符合自然并发下不应要求 exact sequence 的预期。pairwise 最大 KS 为：versions/page 0.01369、reuse distance 0.00674、per-update fanout 0.03000、first/last span 0.03068；对应最大 normalized W1 分别为 1.299%、0.896%、0.508% 和 1.672%。phase concentration 的最大绝对差为 repeat fraction 0.002059、HHI `2.99e-6`、top-1 share `5.16e-5`、top-10 share `6.06e-4`、top-1% share `8.86e-4`。精确整数直方图的 TV 对轻微平移很敏感（reuse 最大 0.337、span 最大 0.807），不能单独把高 TV 解读为结构失稳；R2 报告应同时保留 KS/W1 与 control 的自然变动尺度。

## 唯一 4 KiB materialization 语义

每个 normalized page event 唯一物化为一个完整的 4,096-byte logical page image，并按上述 submit sequence append。`returned_bytes`/`normalized_page_bytes` 只表示应用实际修改的 payload，不能作为 append logical bytes；append logical bytes 必须是 `4096 * page_event_count`。若事件只修改一部分页面，host 必须将 payload 与当前 logical page image 的未修改部分合并，再 append 完整页；未修改部分计入 `unchanged_bytes_reconstructed`，不得隐去这个 read/merge 前提。

既有 DGAI 每轮有 3 个 partial events：application mutation 为 91,127,960 B，完整页 append 为 91,136,000 B，需重建 8,040 B，materialization/application 比为 1.000088。既有 OdinANN 每轮有 15 个 partial events，需重建 52,200 B，完整页 materialization/application 比为 1.000526–1.000528。该口径只闭合 host page-version 输入，不授权任何 GC、relocation 或设备寿命结论。

## R2 使用方式

R2 完成至少六个随机 NATIVE/SHIM-CONTROL/FULL triplet 后，将每个 run directory 作为一个 `--run` 传入。若目录名不足以推断身份，可用 `LABEL:SYSTEM:MODE=DIR` 显式标注。例如：

```bash
python3 sequence_structure_audit.py \
  --run d1-full:DGAI:FULL-TRACE=/path/to/d1-full \
  --run d1-shim:DGAI:SHIM-CONTROL=/path/to/d1-shim \
  --run d1-native:DGAI:NATIVE=/path/to/d1-native \
  --output r2_sequence_audit.json
```

只有真实 R2 triplet 的 aggregate closeness、DGAI exact structure、OdinANN 相对 native-concurrency 的 shift 以及重复 FULL 稳定性均满足 gate 后，sequence-only fallback 才可能成立；本回算本身不把 Z0A 从 HOLD 改为 PASS，也不授权 Z0B。
