# 三系统 SIFT10M Pilot：P0 修订与运行时 Canary 证据

**状态：** 已完成 GPT 要求的 R1--R3 和 R4 的路径、空间、DiskANN 查询结果校验；尚未下载 BIGANN、物化 SIFT10M、计算 8M GT、构建正式索引、启动 tmux 或运行 W0/W1。

**上游审查：** `gpt/share/dynamic_vamana_three_system_f0_p0_review_0714.md`。
**本次结果：** runtime canary `attempt-04` 通过；DGAI/OdinANN 的逐 query ID 校验仍是显式未决边界，见“R4”与“待裁决事项”。

## R1：真实 NUMA 与 CPU 约束

`formal/f0_common.sh` 现在在每个 F0 入口的 preflight 中读取 `/sys/devices/system/node/node<N>/cpulist`，确认目标 NUMA node 存在且请求 CPUSET 是其子集。当前默认 `CPUSET=0-23`，完整属于 node 0 的 `0-27,56-83`。

每个 build/query/canary 都在 `resource_probe.py` 外层执行：

```text
numactl --physcpubind=0-23 --membind=0
```

每个 phase 另外保存 `*_effective_policy.txt`，其中包含实际 `taskset -pc` 和 `numactl --show`，而不再只在 environment manifest 中写请求值。

## R2：SIFT10M provenance 与 hash

新增 `sift10m_provenance.py`，由 `prepare_sift10m.sh` 使用。它记录并在复用时重新验证：

* 原始 base `.bvecs` SHA256；
* 原始 query `.bvecs` SHA256；
* canonical `base.10m.fbin` SHA256；
* canonical query FBin SHA256；
* 四个文件的真实路径与字节数；
* 显式下载 URL；
* `SIFT10M_BASE_EXPECTED_SHA256`、`SIFT10M_QUERY_EXPECTED_SHA256` 的匹配结果。

expected hash 若被提供则为硬失败门槛。若上游未公开 checksum，manifest 明确标为 `operator-source-review-required`，不会因文件名或维度而自动声称标准 BIGANN。脚本还记录 partial 下载 URL，拒绝把旧 URL 的 `.partial` 续传到新 URL；canonical 文件已存在但其 conversion provenance 缺失或与当前 source hash 不同也会失败。

## R3：dedicated cgroup 运行时 Canary

新增 `formal/f0_runtime_canary.sh` 和小型 payload。它以 root-managed transient scope 启动但通过 `--uid=1000` 运行 payload，写入约 1 MB NVMe 数据、`fsync` 后读取、触碰 16 MB 内存并保持三秒，供资源采样。

最终通过的原始证据位于：

```text
/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/results/
  pilot3_sift10m/canary/attempt-04/
```

| 项目 | 实测值 |
| --- | --- |
| systemd unit | `dv-pilot3_sift10m-RuntimeCanary-canary-attempt-04-745719` |
| cgroup path | `/sys/fs/cgroup/system.slice/...attempt-04-745719.scope` |
| command/output UID | 1000 / 1000 |
| effective CPU affinity | 0--23 |
| effective NUMA policy | `policy: bind`，`membind: 0` |
| cgroup memory counters | `memory.current`、`memory.peak` 非空 |
| cgroup I/O | `259:10 wbytes=1048576, wios=8` |
| payload return code | 0 |

`attempt-01` 在 payload 启动前发现 `systemd-run` 不支持 `--scope --wait`；`attempt-02` 证明 scope/NUMA/UID 成立但 buffered write 未进入 cgroup `io.stat`；两个失败 attempt 均被保留。移除互斥参数并加入 `fsync` 后，`attempt-03` 与 `attempt-04` 通过。没有覆盖失败证据。

## R4：路径、空间与查询验收

所有准备和 F0 输出路径现在先 `realpath -m`，若目标尚未创建则回退到最近存在父目录，再用 `findmnt` 检查 source `/dev/nvme8n1` 与 major:minor `259:10`。仅有字符串前缀不再足够。`prepare_sift10m.sh` 在下载前、转换前和 checkpoint 物化前均检查 NVMe 空闲至少 300 GB；当前约余 1.4 TB。

新增 `validate_query_result.py`。DiskANN F0 的 `result_40_idx_uint32.bin` 必须满足：结果 shape 与 query count/K 一致、文件长度正确、Recall@10 可解析为有限 `[0,1]`、每个返回 ID 都在 checkpoint-0 active tags 中。DiskANN 已有结果文件，因此该校验可直接执行。

### DGAI/OdinANN 的边界

现有 DGAI/OdinANN `search_disk_index` driver 只打印聚合 Recall，不写逐 query result IDs。仅解析日志能检查有限 Recall，却不能独立证明所有返回 ID 属于 active set。要满足 GPT R4 的同一强度 ID 验收，需要新增仅输出结果的 instrumentation patch，并重新编译两个 artifact；这会扩大已冻结 patch 集和本轮工作量。

根据 PZ 的“能快速实现的做、额外时间成本的可不做”指示，本次**没有**擅自加入该 patch，也不把 DGAI/OdinANN 称为已经通过 per-ID 校验。F0 脚本中保留现有 GT/Recall smoke，P1 是否允许继续应由 GPT 明确决定：接受此方向发现 Pilot 的受限验收，或要求该 instrumentation patch 后再运行。

## 通知

已按 mailsender skill 使用其固定收件人服务做健康检查，返回 `ok`。新增 `formal/notify_owner.sh`，被数据准备、GT validation、F0 与 canary 的成功/失败路径调用；默认 `ATLAS_NOTIFY_EMAIL=1`，可显式置零。Canary 使用 `ATLAS_NOTIFY_EMAIL=0`，故没有发送测试邮件或声称邮件送达。

## 静态检查与停止条件

已通过 shell `bash -n`、相关 Python `py_compile`、provenance record/verify 小样本、DiskANN bin result validator 小样本、source allowed-patch guard 与 `git diff --check`。本文件提交后仍停在 P0：等待 Claude/GPT 对 DGAI/OdinANN 的 R4 边界及 P1 授权作出裁决。
