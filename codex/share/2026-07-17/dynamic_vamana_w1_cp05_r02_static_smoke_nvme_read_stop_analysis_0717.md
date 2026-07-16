# Dynamic Vamana W1 CP05 R02 Static Smoke NVMe Read 停止分析

## 停止结论

修正 DGAI `aio` identity 后，R02 preparation 两次在 DGAI static load smoke evidence gate 停止，直接错误均为 `expected exactly one cgroup io row for device 259:10`。第一次停止时，DGAI `L64/L128` 资源探针的全部 `cgroup_io_stat` samples 均无 `259:10` 行。增加 per-file cache eviction 后，查询产生了真实 NVMe read，但 `L64/L128` 的前 `5/4` 个 samples 仍无该行，后续分别有 `39/37` 个 samples 包含该行；严格 validator 会从首个 baseline sample 取零点，因此继续 fail closed。两轮查询均返回完整且 active 的 `36×10` 结果。

R02 execution manifest 仍未激活。新的 replay/formal inputs、private clone、动态 update 和 DiskANN stale control 均未开始，CP10 与 CP20 继续 HOLD。两份 immutable replay bases 的 accepted R07 lineage、content、mode、write denial 与 shared-source preservation 在停止前再次通过。

## 根因

问题包含两个连续条件。前序 immutable-base 创建、全量 content 验证和 DGAI static query 已将所需 index pages 预热到系统页缓存，最初没有触发 `/dev/nvme8n1` 的块层读取。per-file eviction 解决冷读后，新建 cgroup 的 `io.stat` 仍要等到第一次块 I/O 才创建 `259:10` 行；资源探针在该事件之前采集 baseline，因此首样本缺行。后续读取数据有效，但不能为缺失的 baseline 提供严格零点。这是 static-smoke 冷读与 cgroup accounting 初始化的编排缺口，不是 NVMe 设备、查询二进制或索引故障。

全局执行 `drop_caches` 可以产生冷读，但会影响机器上无关工作负载。修复只对目标 immutable index tree 的每个 regular file 调用 `POSIX_FADV_DONTNEED`，不清理全局页缓存。cache-eviction helper 在调用前验证 index root 位于 `259:10`、目录为 `0555`、文件为 `0444`、无 symlink/special file/hardlink，并在调用后证明 inode、size、UID/GID、mode、link count 与 mtime 均未变化。随后在同一个 query scope 内、资源探针启动前，对 immutable `index_disk.index` 执行一次 `4 KiB O_DIRECT` read，使 `io.stat` 建立 `259:10` 行。资源探针在 primer 之后采集 baseline，因此查询增量不会包含该 `4 KiB`。

## 修复验证

最终集成回归使用正式 DGAI immutable copy、canonical-v6 binary、相同 36-query CP00 输入、ubuntu scope、CPU `0–23`、NUMA node 0 和 `8 GiB` memory limit。执行 per-file cache eviction 与同 scope primer 后，资源探针首样本恰有一个 `259:10` 行，值为 `4,096 B/1 I/O`；末样本为 `190,275,584 B`，查询净增量为 `190,271,488 B`。DGAI `L64` 返回码为 0，结果形状与 active-ID validation 通过。该回归精确覆盖 validator 的首样本、末样本和正 read-delta 条件。

正式 orchestrator 将在四个 static smoke 点的每一次查询前独立执行同一 per-file eviction，并保存 `cache_evict.json`；同一 scope 内先执行 `4 KiB O_DIRECT` primer，再启动资源探针与查询。最终通过条件仍由探针 baseline 之后的 query cgroup device-read delta 给出，eviction report 与 primer 均不能替代查询 I/O 证据。失败的 partial smoke、controller log 与 preparation tmp 将整体归档，不作为后续 PASS evidence 复用。

## 有效性边界

该修复只控制 static load smoke 的缓存状态，不改变 DGAI/OdinANN binary、L、query、GT、active tags、index bytes 或后续 replay/formal 状态机。它不保证性能测量的冷缓存可比性，且本轮 smoke 的 Recall、QPS 与 latency 仍仅作为诊断指标。正式动态阶段的性能解释继续以原门禁定义为准。
