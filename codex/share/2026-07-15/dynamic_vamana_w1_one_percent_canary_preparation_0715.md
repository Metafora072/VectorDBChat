# Dynamic Vamana W1-C：1% replace-new canary 准备报告

**日期**：2026-07-15
**状态**：**PREPARED FOR REVIEW — 未执行 trace、GT、clone、80K update 或 tmux**
**上游门禁**：`gpt/share/2026-07-15/dynamic_vamana_w1_one_percent_canary_preparation_gate_0715.md`

## 范围与硬保护

准备内容只位于 `codex/share/2026-07-15/dynamic_vamana_atlas/`。所有会写 NVMe 的入口
`w1_prepare_cp01_trace.py`、`w1_compute_cp01_gt.sh`、`w1_clone_base.sh`、两个系统 canary
脚本和 `start_w1_canary_tmux.sh` 都要求显式 `W1_EXECUTE_AUTHORIZED=1`；未授权时 clone 与 tmux
启动返回 64。当前目录树中没有 `pilot3_sift10m_w1` attempt，checkpoint-0 base 未被触碰。

## 更新 driver 审计

### DGAI

`src/DGAI-clean/tests/overall_performance.cpp` 的 `update`（401 起）在加载 index 后读取
`ATLAS_TRACE_BIN`（468–475），然后以原生固定顺序同步调用 `insertion_kernel`（481）、
`deletion_kernel`（483）和 `merge_kernel`（484）。`merge_kernel` 进入
`trigger_deletion`/`final_merge`（209–215）；持久化 tag 文件由
`src/update/delete_merge.cpp:325–339` 写出 `<prefix>_disk.index.tags`。因此 DGAI 的
`ingest_end` 应位于两类 API 返回后，不能包含 merge；原 driver 没有 merge 前可安全 probe 的
独立对外语义，故在线可见性必须标记 `unsupported`，其首个有效状态是 merge/reload 后的
published/restart-visible 状态。

### OdinANN

`src/OdinANN-PipeANN/tests/overall_performance.cpp` 的 `update`（222 起）读取 trace（279–286）后，
以两个 future 并行执行原生 insert/delete（288–291），在等待中做 live query（296–309），最后在
314 直接 `exit(0)`。所以现有 driver 没有 publish 或 fresh-process 阶段，不能拿 live query 当
restart-visible。OdinANN 的原生 `DynamicIndex::save`（`include/dynamic_index.h:549–605`）才会合并、
reload 并更新前缀；W1 driver 必须在 live probe 后显式调用它，再由全新 query 进程验证。

两个系统的 `search_disk_index.cpp` 都已经将返回 tag 放进 `query_result_tags`，但只打印 aggregate
指标，未序列化。准备了仅写出该既有数组的最小补丁：

* `patches/DGAI_w1_result_ids.patch` — SHA256 `f3ea75505285e82f5fad234da0c27bc20fdef5281ade18adbab4c7236dc5fbf8`；
* `patches/OdinANN_w1_result_ids.patch` — SHA256 `cf3da673226fdf1981ade9b5e6f9aba13f6fc1edf8c5cfa3b711b4802ba90fbe`。

两者均已对当前源码 `git apply --check` 通过，尚未应用或编译。它们不改变 traversal、candidate
selection、distance 或 rerank，只在 `ATLAS_RESULT_IDS_PATH` 被设置时写出 `[nquery,k] + uint32 tags`
二进制。`patches/W1_canary_driver_contract.md`（SHA256
`ed62736c944e1be7f485694543f4ed69611f76114eea57a3e3f329db1160d6e8`）明确了尚待审查的专用
`w1_canary` driver：JSONL monotonic markers、DGAI online unsupported、OdinANN live→save→fresh
process，以及任何失败非零退出。这个专用 source/binary 目前是执行前阻塞项，不会以现有
`overall_performance` 偷换语义。

当前上游 source identity 保持：DGAI `a0179b876a4bd453336dc2893b46ae890f680555`，OdinANN
`9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`；各自仅保留已审查 compatibility patch 所覆盖的
工作树改动。

## Trace、GT 与正确性链路

`w1_prepare_cp01_trace.py` 从既有 seed `20260713` 的 deterministic source trace 取前 80,000
pair，严格检查 delete/insert 的唯一性、相交性和 checkpoint-0 membership，生成：

```text
replace_cp01_80k.bin            # int32 count + deletes block + inserts block
replace_cp01_80k.tsv
replace_cp01_manifest.json
active_cp01.tags.bin
visibility_probes.json
visibility_probes.bin           # 执行时由 --materialize-active 生成
active_cp01.bin                # 执行时由 --materialize-active 生成
```

probe 的位置固定为首、尾及七个等距 trace index；每个位置生成 insert-vector 与 deleted-vector
两个 query。`w1_validate_cp01_trace.py` 独立复算 active set 与 manifest hash。`w1_compute_cp01_gt.sh`
在通过 trace validation 后才调用 exact top-100 GT，并借扩展后的 `validate_groundtruth.py` 校验
checkpoint 1：所有 tag active、距离 finite/单调、query 0/17/9999 独立 brute-force audit。

`w1_dump_active_tags.py` 只解析 artifact 已公开、持久化的 `*_disk.index.tags` 格式，不读取内部
内存布局；输出 count、排序 hash、min/max、duplicate count，并和 expected set 做精确相等检查。
`w1_visibility_probe.py` 要求每个 insert target 出现在实际 result IDs 中、每个 deleted tag 不在其
top-k 中，且每个返回 tag 都属于 checkpoint-1 active set；没有百分比容忍。

## Clone、资源采集与时间口径

`w1_clone_base.sh` 仅允许在 NVMe
`formal/pilot3_sift10m_w1/` 下创建从 W0 immutable base 出发的独立 clone；先后 SHA256 全部 base
文件并比较，优先 reflink、否则显式记录 fallback，拒绝覆盖 attempt。DGAI 与 OdinANN 分别串行运行，
不会共享可写 index 或并发占用设备。

专用 driver 必须写出如下 JSONL monotonic markers：`clone_ready`、`index_loaded`、`ingest_begin`、
`ingest_end`、`online_visibility_probe_begin`、`online_visibility_verified`、`publish_begin`、
`publish_end`、`fresh_process_probe_begin`、`fresh_process_visibility_verified`。`w1_collect_canary.py`
只接受完整且有序的 marker，并计算：

```text
ingestion = 80K / (ingest_end - ingest_begin)
online-visible = 80K / (online_visibility_verified - ingest_begin)
restart-visible = 80K / (fresh_process_visibility_verified - ingest_begin)
```

它同时收集 process/cgroup RSS、memory.events、NVMe `259:10` 的 rbytes/wbytes/rios/wios delta、
I/O PS、payload-normalized device write 和 persistent index growth。DGAI 的 online field 由 driver
显式 unsupported，不会与 OdinANN live-online 的数值并列排名。

## 容量与时间预算（未运行估计）

当前 immutable index apparent size 为 DGAI 14.13 GB、OdinANN 8.48 GB；NVMe 可用约 1.43 TB。
checkpoint-1 materialization 额外约 3.90 GB，GT 约 8 MB 加日志。保守预留 DGAI 50 GB、OdinANN
35 GB、trace/GT 临时空间 20 GB，总计不超过约 105 GB，因此低于现有可用空间但仍要求每个 attempt
启动前检查 150 GB free-space guard。预计 serial W1-C 总 wall time 为 3–8 小时，其中 exact 10K×8M
GT 与两套 full-index publish/merge 是主导项；该范围是保守预估，不作为结果。

## 静态验证与下一步

`bash -n` 已通过所有 W1 shell entrypoint；五个 Python helper 已 `py_compile`；两份 result-ID patch
均 `git apply --check`；合成 result-ID/marker/cgroup-I/O 测试通过，且未授权 clone/tmux 均 fail-closed
返回 64。未启动 tmux、未生成真实 80K trace/GT、未 clone、未执行 update。

请审查后再决定是否先批准完成专用 driver source/binary 的受限构建与 hash freeze，随后才可单独放行
trace/GT preparation 和两个串行 canary。
