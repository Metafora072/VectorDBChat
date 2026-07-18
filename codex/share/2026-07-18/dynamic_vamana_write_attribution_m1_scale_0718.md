# Dynamic Vamana Write Attribution M1 Matched-Size Scale

## 裁决与实验边界

GPT 已正式接受由 DGAI R03/V4 与 OdinANN R04/V5 组成的 M0 双系统 100K closure，并授权进入 M1 matched-size 分解。M1 复用两个 accepted 100K anchor，只新增 DGAI 与 OdinANN 各自的 50K、200K 和 400K 点。每个新点都从同一 R12 frozen CP10 source 创建独立 private clone，使用 master replacement trace 的嵌套 prefix `[800000:850000]`、`[800000:1000000]` 和 `[800000:1200000]`，不从前一个规模的 mutable result 继续。

M1 只分析固定写入成本与每 replacement 边际写入成本。OdinANN 的 application physical total 包含一次性 load/shadow-copy，因此不得用 M0 total ratio `3.596×` 表示持续更新写放大。报告会分别保留 load、recurring update-window、insert-neighbor-repair、publish-save 以及 logical target/neighbor role，并以 application-requested bytes 为主要归因指标；wall time 与 device bytes 仅作为描述性和 sanity evidence。完成双系统四点分解后停止，不启动新系统、write buffering、邻居修复优化、额外 churn checkpoint 或 novelty 结论。

## 构建与完整性门禁

M1 build 位于项目 NVMe 的 `build/write-attribution-m1-v5-r01`。profiler SHA-256 为 `b06d9800...16d3e`，与 accepted OdinANN R04 完全相同；OdinANN instrumented binary 继续使用 `fcb8ed09...ac12`。新构建的 DGAI V5 binary SHA-256 为 `e5a9fdfe...df383`，不同于 canonical `d3048e11...28106`。DGAI 继续使用已接受的 libaio authoritative async ledger，新增 `sendfile()` hook 在该工作负载上不触发。

empty、POSIX、4 KiB boundary、FD reuse、DGAI libaio no-sendfile 和 filesystem-copy overwrite 六项自测全部 PASS。copy synthetic 仍只产生一个 `sendfile()` request，returned bytes、目标实时 FD identity 和最终内容一致，不与既有 POSIX wrapper 重复。每个正式点继续执行 input range、active-set、online/fresh visibility 语义、fresh-process query smoke、changed-file coverage、physical ledger/bucket/entry closure、phase/component coverage、R12 source content/mode preservation、positive NVMe write、无 OOM 和 logical role 门禁；任一项失败即停止后续点。

## 运行顺序与资源预算

正式 run identity 为 `pilot3_sift10m_write_attribution_m1_scale_r01`，attempt 使用 `m1-n<size>-01`。运行器严格串行执行 DGAI 50K、OdinANN 50K、DGAI 200K、OdinANN 200K、DGAI 400K 和 OdinANN 400K。50K 是最小 formal sanity stage；只有该点及其配对系统通过，才进入后续规模。100K 不重跑，最终 machine summary 直接绑定 M0 closure 中的两个 accepted summary、input manifest 与 profiler identity。

R12 frozen base 的 apparent size 为 DGAI 14,131,068,900 bytes、OdinANN 16,960,280,936 bytes。六个 fresh clone 的基础空间合计约 93.27 GB，计入更新后文件增长、输入、结果与 441 MB 的 M1 build，预计新增约 95–105 GB。启动前项目 NVMe `/dev/nvme8n1` 可用 1,137,753,100,288 bytes，MemAvailable 为 251,537,564 KiB；controller 要求至少 150 GB headroom，并给每个 stage 设置 40 GiB memory limit 和 2 小时 runtime hard limit。按既有 M0 时长外推，六点串行 controller wall 预计为 35–55 分钟。所有 build、input、clone、profile、log 与 result 均位于项目 NVMe，不使用系统盘执行实验。

## Machine Summary 与拟合方法

最终 `scale_summary.json` 将绑定 M0 closure SHA、M1 build manifest SHA、8 个 run identity、4 个 input prefix 与各点 profiler SHA，并再次逐字节验证 50K、100K、200K trace 均为 400K master trace 的 delete/insert 双数组前缀。每个点保存 application physical bytes、async/POSIX bytes、device writes、request count、phase、raw component、exclusive physical file class、logical role、bucket-level unique 4 KiB page sum、page touches、rewrite factor、bytes/pages per replacement、wall time与正确性状态。

对每个系统的 total、recurring window、各 phase、各 physical file class 和 logical role，使用 50K、100K、200K、400K 四个真实点拟合 `value(N) = intercept + slope × N`。machine summary 会同时输出每点 actual、predicted、signed/absolute residual、relative residual、per-replacement value 和 residual sign pattern，不使用任意阈值或仅凭 R² 宣称线性成立。最终结论必须依据残差与 per-replacement 趋势回答 insert/publish 来源、unique pages 与 rewrite factor、neighbor-only 边际稳定性、load 固定成本和 5.14× insert 单点观察是否跨规模持续。

## 四点原始结果

M1 于 `2026-07-18 12:17:12 UTC+8` 完成。6 个新点与 2 个 accepted 100K anchors 共 8 点全部通过 formal machine gate，50K、100K、200K trace 的 delete/insert 双数组均再次验证为 400K trace 的严格前缀。所有点的 active set、online/fresh visibility 语义、fresh query、changed-file coverage、physical ledger closure、source preservation 和 OOM 门禁均通过。

| system | N | total GB | load GB | recurring GB | insert GB | publish GB | insert unique pages | insert page touches | insert rewrite factor | E2E s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DGAI | 50K | 7.330 | 0 | 7.330 | 1.325 | 6.005 | 287,335 | 323,476 | 1.126 | 78.387 |
| DGAI | 100K | 9.015 | 0 | 9.015 | 3.010 | 6.005 | 608,343 | 734,854 | 1.208 | 130.264 |
| DGAI | 200K | 13.066 | 0 | 13.066 | 7.061 | 6.005 | 1,183,850 | 1,723,882 | 1.456 | 246.670 |
| DGAI | 400K | 21.670 | 0 | 21.670 | 15.665 | 6.005 | 1,778,335 | 3,824,432 | 2.151 | 469.770 |
| OdinANN | 50K | 23.597 | 8.480 | 15.117 | 6.637 | 8.480 | 1,296,350 | 1,620,264 | 1.250 | 111.993 |
| OdinANN | 100K | 32.417 | 8.480 | 23.937 | 15.457 | 8.480 | 2,195,076 | 3,773,732 | 1.719 | 181.934 |
| OdinANN | 200K | 51.322 | 8.480 | 42.842 | 34.361 | 8.480 | 2,974,834 | 8,389,012 | 2.820 | 282.723 |
| OdinANN | 400K | 89.272 | 8.480 | 80.792 | 72.312 | 8.480 | 3,473,207 | 17,654,192 | 5.083 | 521.270 |

表中的 GB 使用十进制字节换算。insert phase 在每个点均只有一个 authoritative async bucket，因此该列的 unique page 数不是跨 bucket 相加产生的近似值，而是该 phase 内的实际唯一 4 KiB page 数。device write 继续只作 sanity evidence；6 个新点的 device write 均为正，且 process-tree peak RSS 为 2.32–4.52 GiB，未触发 40 GiB cgroup limit。

## 固定成本与描述性拟合

DGAI publish-save 在四点均精确为 6,005,336,152 bytes，OdinANN publish-save 均精确为 8,480,136,500 bytes；两条 slope 均为 0、残差为 0。OdinANN load/shadow-copy 在四点均精确为 8,480,136,420 bytes，同样为零 slope 和零残差。DGAI 当前路径没有 load 物理写入。这三项可以直接视为本 workload 下的固定成本。

| system / metric | fitted intercept | fitted slope | max relative residual | residual signs by N |
|---|---:|---:|---:|---|
| DGAI recurring bytes | 5.019 GB | 41.343 KB/replacement | 3.33% | `+ - - +` |
| OdinANN recurring bytes | 5.374 GB | 188.253 KB/replacement | 2.18% | `+ - - +` |
| DGAI insert bytes | -0.987 GB | 41.343 KB/replacement | 18.44% | `+ - - +` |
| OdinANN insert bytes | -3.106 GB | 188.253 KB/replacement | 4.97% | `+ - - +` |
| DGAI insert unique pages | 181,973 pages | 4.173 pages/replacement | 35.95% | `- + + -` |
| OdinANN insert unique pages | 1,428,542 pages | 5.634 pages/replacement | 31.93% | `- + + -` |

bytes 拟合在较大 N 上残差变小，但 insert 的负 intercept、`+ - - +` 弯曲模式以及实际 bytes/replacement 随 N 上升，说明简单固定项加恒定边际项不能作为全区间机制模型。unique-page 拟合的 31.93%–35.95% 最大相对残差更明确地否决了恒定页面边际。machine summary 因此保留拟合用于描述，不将 intercept 解释为真实固定写入来源，也不宣称全区间线性成立。

## 核心归因结论

OdinANN 与 DGAI 的 recurring update-window 比值随 N 从 2.062、2.655、3.279 上升到 3.728。两系统 publish 差值固定为 2,474,800,348 bytes，而 insert 差值从 5.312 GB 增至 56.647 GB；insert 对 recurring gap 的贡献从 68.2% 上升到 95.8%。因此跨规模差距主要由 insert-neighbor-repair 产生，publish 只贡献固定差值。

两系统每个 replacement 的 target-only 与 target+neighbor shared-page bytes 之和都精确为 4,096 bytes，所以 insert 差值全部来自 neighbor-repair-only。neighbor-repair-only 的实际 bytes/replacement 在 DGAI 中为 22.4、26.0、31.2、35.1 KB，在 OdinANN 中为 128.6、150.5、167.7、176.7 KB；它们在 50K–400K 全区间均非恒定。相邻规模的边际值在 DGAI 中为 29.6、36.4、38.9 KB/replacement，在 OdinANN 中为 172.3、184.9、185.7 KB/replacement，显示高 N 区间趋于稳定，但不能把 50K–400K 整体概括为单一稳定边际。

insert 的 OdinANN/DGAI unique-page 比值从 4.512 降至 1.953，rewrite-factor 比值则从 1.110 升至 2.364。50K 差距主要表现为 OdinANN 触及更多唯一页面；随着 N 增大，唯一页面逐渐饱和，而重复改写迅速增加。到 400K，约 1.95× unique pages 与 2.36× rewrite factor 共同形成 4.62× page touches/insert bytes，且 rewrite-factor ratio 已大于 unique-page ratio。因此不能只归因于页面覆盖面或只归因于重复改写，主导结构随规模发生转移。

M0 100K 观察到的 insert ratio 5.135× 在 matched-size 四点上分别为 5.009×、5.135×、4.866×、4.616×。约 4.6–5.1× 的大差距持续存在，但比值随 N 系统性下降，不能称为固定 5.14×。publish ratio 在四点精确保持 1.412×，OdinANN load 则保持精确固定。上述结果只描述当前两套布局、I/O engine 和更新算法的组合差异，不能单独归因于 online visibility。

## 完成状态与证据

`scale_summary.json` 的 SHA-256 为 `ff035288...f79a71`，绑定 M0 closure、M1 build manifest、8 个 summary、4 个 input manifest 和 profiler identity。M1 formal/result apparent size 分别为 93,274,175,246 和 177,344,263 bytes；controller free-space delta 为 93,451,333,632 bytes，实际 wall 约 44 分钟，符合启动前预算。结束后无 active tmux、systemd unit 或 experiment process，项目 NVMe 仍可用约 973 GiB。M1 已按 gate 停止，没有启动新系统、优化原型、novelty 结论或额外 checkpoint。
