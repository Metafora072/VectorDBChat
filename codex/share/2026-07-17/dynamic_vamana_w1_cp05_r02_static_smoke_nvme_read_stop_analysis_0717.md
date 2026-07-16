# Dynamic Vamana W1 CP05 R02 Static Smoke NVMe Read 停止分析

## 停止结论

修正 DGAI `aio` identity 后，R02 preparation 再次在 DGAI static load smoke evidence gate 停止。直接错误为 `expected exactly one cgroup io row for device 259:10`。DGAI `L64/L128` 查询均返回完整且 active 的 `36×10` 结果，但资源探针的全部 `cgroup_io_stat` samples 为空，不满足 GPT 门禁要求的真实 NVMe device read。

R02 execution manifest 仍未激活。新的 replay/formal inputs、private clone、动态 update 和 DiskANN stale control 均未开始，CP10 与 CP20 继续 HOLD。两份 immutable replay bases 的 accepted R07 lineage、content、mode、write denial 与 shared-source preservation 在停止前再次通过。

## 根因

前序 immutable-base 创建、全量 content 验证和两轮 DGAI static query 已将所需 index pages 预热到系统页缓存。修正后的查询虽然产生了进程级 read accounting，但没有触发项目设备 `/dev/nvme8n1` 的块层读取，因此对应 transient scope 的 `io.stat` 没有 `259:10` 行。这是 static-smoke 冷读前置条件缺失，不是 NVMe 设备、查询二进制或索引故障。

全局执行 `drop_caches` 可以产生冷读，但会影响机器上无关工作负载。修复改为仅对目标 immutable index tree 的每个 regular file 调用 `POSIX_FADV_DONTNEED`，不清理全局页缓存。cache-eviction helper 在调用前验证 index root 位于 `259:10`、目录为 `0555`、文件为 `0444`、无 symlink/special file/hardlink，并在调用后证明 inode、size、UID/GID、mode、link count 与 mtime 均未变化。它只请求丢弃该 index 的 clean cached pages，不修改文件内容或权限。

## 修复验证

集成回归使用正式 DGAI immutable copy、canonical-v6 binary、相同 36-query CP00 输入、ubuntu scope、CPU `0–23`、NUMA node 0 和 `8 GiB` memory limit。执行 per-file cache eviction 后，DGAI `L64` 查询返回码为 0，结果形状与 active-ID validation 通过；scope 对设备 `259:10` 的 read delta 为 `190,304,256 B`。该回归证明 cache-eviction 请求能够恢复 static smoke 所需的真实 NVMe read evidence。

正式 orchestrator 将在四个 static smoke 点的每一次查询前独立执行同一 per-file eviction，并保存 `cache_evict.json`。最终通过条件仍由查询 scope 自身的 cgroup device-read delta 给出，eviction report 不能替代 I/O 证据。失败的 partial smoke、controller log 与 preparation tmp 将整体归档，不作为后续 PASS evidence 复用。

## 有效性边界

该修复只控制 static load smoke 的缓存状态，不改变 DGAI/OdinANN binary、L、query、GT、active tags、index bytes 或后续 replay/formal 状态机。它不保证性能测量的冷缓存可比性，且本轮 smoke 的 Recall、QPS 与 latency 仍仅作为诊断指标。正式动态阶段的性能解释继续以原门禁定义为准。
