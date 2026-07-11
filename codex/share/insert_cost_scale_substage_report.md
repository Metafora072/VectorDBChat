# Insert Cost 规模与子阶段门禁报告

## 裁决

本轮裁决为 **Kill 当前机制假设，并 Reframe 为 DGAI 的 Linux AIO 提交路径诊断问题**。不进入 R32/64/96/128 完整矩阵，也不进入跨系统 exact-vector access 验证。

否决依据是 GPT 设定的核心门禁未通过。SIFT-128 与 GIST-960 在 900K base 的稳定尾窗中，最高子阶段均为 request construction + `io_submit`，但占总插入时间仅为 5.15% [5.06%, 5.25%] 与 6.01% [5.97%, 6.05%]，远低于 30%–40%。高占比只在部分 fresh-process cluster 中出现，而且同一配置会在约 4%–8% 与 45%–69% 两种状态之间切换，cluster bootstrap 置信区间不能收敛。该信号不满足 cold/stable 同时存在、随规模可解释和非单系统实现偶然性三个条件。

## 实验协议与计时闭合

实验固定 R=64、L=160、beam=4、单线程，比较 SIFT-128 与 GIST-960 的 100K/900K base。stable 每组在同一进程执行 2,000 次 insert，前 500 次作为 warmup；从 100-row checkpoint 中选择此后 dominant stage 不变且 share 总漂移不超过 1 个百分点的最早稳定尾窗。application-cold 每组使用 10 个独立 source copy 和新进程，每个 cluster 取 100 次 insert，并在启动 clusters 前对无关的 7.4 GiB 文件执行 direct scan。

所有正式行的 coordinate 子阶段满足逐行守恒，最大误差为 0 μs。各条件最低全插入阶段闭合率为 99.41%–99.75%，高于 95% 门禁。一次 GIST-100K fresh-process cluster 在首条 insert 发生非确定性 SIGSEGV，未产生 CSV，因此排除并补足 10 个有效 cluster；pending-insert visibility 修复继续关闭，以保持与上一轮原始 DGAI 基线一致。

## Cold-cache 定义审计

`linux_aligned_file_reader.cpp` 中 coordinate 文件通过 `O_RDWR | O_LARGEFILE | O_DIRECT` 打开，topology 文件也使用相同标志。coordinate exact rerank 没有跨请求持久化应用缓存，所谓 cache hit 仅表示同一批 160 个候选映射到重复 coordinate page；topology 路径则存在新进程创建的 `BlockCache`。

因此，文件复制带入 Linux page cache 不会被 coordinate `O_DIRECT` 读取命中，`drop_caches` 与 `posix_fadvise(DONTNEED)` 也不能控制该数据路径，更不能重置 SSD 固件内部状态。本轮未使用全局 `drop_caches`。为降低刚复制文件可能造成的设备侧缓存偏差，所有副本先批量准备，再执行 7.4 GiB 无关文件 direct scan；然而 `io_submit` 仍呈双峰，说明当前环境无法构造可验证、可重复的绝对物理 cold 状态。

本报告据此把 cold 严格命名为 application-cold，即新进程、空 topology `BlockCache`、coordinate 始终 direct I/O，并明确保留设备缓存不可重置的限制。cold cluster CI 不收敛本身就是门禁失败证据，不能只选择高占比 cluster 形成结论。

## 100K 与 900K 子阶段分解

表中所有数值均为子阶段占 total insert wall time 的百分比。`request+submit` 保留 GPT 要求的合并口径，同时额外拆出后确认其中几乎全部时间位于 `io_submit()` 系统调用，而不是 C++ request construction。

| Dataset/base/cache | Candidate | Dedup/map | Lookup | Request+submit | Completion wait | Copy | Exact distance | Bookkeeping | Residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SIFT 100K stable | 0.62 | 0.83 | 0.07 | 11.79 | 5.17 | 0.28 | 0.17 | 1.78 | 0.23 |
| SIFT 900K stable | 0.43 | 0.60 | 0.04 | 5.15 | 3.72 | 0.21 | 0.09 | 1.35 | 0.16 |
| GIST 100K stable | 0.56 | 0.66 | 0.04 | 7.66 | 4.17 | 1.39 | 0.37 | 1.70 | 0.18 |
| GIST 900K stable | 0.26 | 0.47 | 0.04 | 6.01 | 3.87 | 0.90 | 0.30 | 0.94 | 0.13 |
| SIFT 100K application-cold | 0.12 | 0.16 | 0.01 | 58.71 | 0.62 | 0.09 | 0.03 | 0.43 | 0.06 |
| SIFT 900K application-cold | 0.11 | 0.30 | 0.01 | 52.68 | 0.60 | 0.07 | 0.02 | 0.36 | 0.05 |
| GIST 100K application-cold | 0.14 | 0.19 | 0.02 | 53.60 | 1.21 | 0.47 | 0.14 | 0.48 | 0.07 |
| GIST 900K application-cold | 0.16 | 0.34 | 0.02 | 22.97 | 1.28 | 0.56 | 0.16 | 0.54 | 0.08 |

stable 下没有子阶段超过 12%。SIFT 从 100K 扩至 900K 时，request+submit share 从 11.79% 降至 5.15%；GIST 从 7.66% 降至 6.01%，不支持随索引规模放大的机制。稳定尾窗的 mean total insert 分别为 SIFT 3.21/7.95 ms 与 GIST 7.67/6.38 ms，但该总时延变化没有对应到一个跨数据集一致增长的 coordinate 子阶段。

`io_submit()` 与 `io_getevents()` 在同一原始 AIO 调用路径内分别计时。request construction 在所有条件下远低于 1%，高 share 几乎完全来自 `io_submit()` 内部停留，而 completion wait 仅为 0.60%–5.17%。这不等于设备 I/O 消失，而是说明 Linux AIO 可在 submit 调用中同步消耗时间；把全部设备等待只归入 `io_getevents()` 会产生错误机制判断。更重要的是，该 submit 时间会在长进程中突然从数毫秒降到约 0.3–0.6 ms，而候选数和唯一页数不变，因此当前信号更像 DGAI 批量 AIO/内核状态偶然性，而不是可推广的索引算法成本。

## 逻辑读取与 Host-submitted I/O

每次 insert 的 requested vectors 和 unique vectors 均为 160，重复 vector 比例为 0，最终进入邻接表的候选固定为 64，funnel ratio 为 40%。SIFT 的 unique coordinate pages 为 156.3–159.0，request-local page reuse 为 0.6%–2.3%；每个 request 为 4 KiB，因此 host-submitted pages 与 unique pages 相同，平均提交约 640–651 KiB。

GIST 的 160 个候选始终对应 160 个不同 logical coordinate pages，没有 request-local hit。由于运行时 `size_per_io=8192`，每个 logical request 提交 2 个 4 KiB host pages，即每次 insert 为 320 host pages、1,310,720 bytes。早期 CSV 曾把 request 数误标为 host pages；正式汇总已按实际 request length 确定性校正，修复后的 2-insert GIST smoke 逐行记录为 160 logical pages、320 submitted pages、1,310,720 bytes，子阶段守恒仍为 0 μs 误差。

稳定尾窗中，SIFT 的 completion wait 摊销为每 host page 1.06 μs（100K）和 1.86 μs（900K）；GIST 为 1.00 μs（100K）和 0.77 μs（900K）。唯一页数基本固定，等待时间没有随 base 规模单调增长。

## 置信区间与有效性限制

stable 使用选定稳定尾窗的 per-insert bootstrap。dominant request+submit share 分别为 SIFT-100K 11.79% [11.62%, 11.94%]、SIFT-900K 5.15% [5.06%, 5.25%]、GIST-100K 7.66% [7.50%, 7.81%]、GIST-900K 6.01% [5.97%, 6.05%]。

application-cold 使用 cluster bootstrap。对应结果为 SIFT-100K 58.71% [53.32%, 61.58%]、SIFT-900K 52.68% [40.88%, 57.86%]、GIST-100K 53.60% [29.82%, 62.35%]、GIST-900K 22.97% [3.33%, 37.97%]。四组均未全部达到 CI 半宽不超过 2 个百分点的停止条件，后两组尤其明显。继续增加副本只会堆叠不可控状态，且 stable 门禁已经明确失败，因此按 Kill-first 原则停止。

新增 instrumentation 的 1,000-insert × 9 配对开销复核仍被同一双峰污染，paired median 为 5.95%，95% bootstrap CI 为 [-19.79%, 55.07%]，不能给出精确 overhead 校正。page-event logging 保持关闭。该不确定性不支持 Continue；相反，它进一步说明 wall time 受未控制 AIO 状态影响。上一轮较短 instrumentation 已证明计时守恒和 ops-only 日志不存在稳定可辨开销，但本轮不把该结论外推为精确的新开销界限。

## 最终边界

本轮只支持以下结论。100K pilot 中的宽阶段主导无法在 900K stable 条件下收敛为一个占比超过 30% 的明确子阶段；高 share 来自 `io_submit()` 的非平稳停留，而不是 request construction、copy、exact distance 或 bookkeeping。减少这一项是否会转移到 completion wait 尚未通过替代 AIO 实现验证，因此不能据此提出新系统。

完整 R 矩阵与跨系统验证均停止。若未来单独恢复该方向，唯一合理的前置工作是 DGAI 内部 AIO 语义对照，例如限制 queue depth、逐请求提交、`io_uring` 与同步 `pread` 对照，并以设备 trace 验证 submit 内停留是否只是等待迁移；这属于实现诊断，不是当前获批实验，也不构成系统 Idea。

机器可读汇总位于主项目 `reports/insert_cost_scale_substage.json`。原始 formal runs 位于 NVMe 的 `VectorDB/data/VectorDB/runs/insert_cost_scale_substage/formal/`，占用约 65 GiB；`repos/DGAI/data` 保持 4 KiB，系统盘未承载新增大型实验产物。
