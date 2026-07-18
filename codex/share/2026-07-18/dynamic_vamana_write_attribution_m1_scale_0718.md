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
