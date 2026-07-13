# Dynamic Vamana Controlled Atlas：artifact / dataset 准备与 smoke 验收

**日期**：2026-07-13

**执行者**：Codex

**上游门禁**：`gpt/share/dynamic_vamana_atlas_preparation_approval_0713.md`（PASS WITH AMENDMENTS）

**阶段结论**：**准备门禁已完成；12/12 build-load-query smoke 与 9/9 replace-new dynamic smoke 均打通。按门禁停止，尚未启动正式 10M 排名或 mixed matrix。**

本报告中的 QPS、时延和 Recall 只用于确认 artifact、数据、GT、tag mapping、搜索参数扫描和更新 API 可工作，不能解读为四系统正式性能排名。大文件、源码、build、索引和完整日志均位于项目 NVMe：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas`；系统盘占用在执行前后均约 45%。

## 1. Artifact 来源、commit 与等级

| 系统 | 选定来源 | commit | 等级 | 许可证 / 审计结论 |
|---|---|---|---|---|
| DiskANN | `microsoft/DiskANN`，`cpp_main` | `78256bbab4685e1774e78d331e081a153be26823` | official | MIT；仅作为 static query 与 future fresh-rebuild baseline，不伪装在线更新能力 |
| FreshDiskANN | `g4197/FreshDiskANN-baseline` | `8ea2f4dfcb0dac6fa65f9398ec5b6bb21c01a200` | reference reproduction | 不是 Microsoft 后续 dynamic-memory API，也不是可确认的独立论文官方 artifact；上游 LICENSE 含未清理 conflict marker，正文为 MIT |
| DGAI | `iDC-NEU/DGAI` | `a0179b876a4bd453336dc2893b46ae890f680555` | official repository, clean commit | 上游根目录无 LICENSE，正式使用前需作者确认许可；未复用此前 instrumentation/search dirty tree |
| OdinANN | `thustorage/PipeANN` 集成仓库 | `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b` | author-provided integrated implementation | Apache-2.0；不是独立 OdinANN 仓库，但覆盖 `DynamicIndex`、PQ neighbor、direct insert/delete、shadow/merge、pipeline search 与 io_uring 路径 |

额外保留 `Yuming-Xu/DiskANN_Baseline` 的 `diskv2` commit `55789099ff60be04cac43d1dc4e4643f15a920ab` 作为 SPFresh artifact provenance，但没有把它与上述 Fresh reference reproduction、Microsoft DiskANN 后续动态 API 合并命名。其 LICENSE 同样含上游 conflict marker。

## 2. FreshDiskANN / OdinANN 身份边界

Fresh 的当前可执行对象只能标为 **reference reproduction**。它实现 disk index + memory delta + delete set + merge 的 Fresh 风格路径，但来源不是 Microsoft 官方 DiskANN，也不能据此声称复现了论文所有工程细节。Microsoft 官方 DiskANN commit 只承担 static/rebuild 角色。

OdinANN 采用论文作者组织维护的 PipeANN 集成实现，而非第三方 DGAI 附带 baseline。代码和实际运行均确认 `USE_URING`、`O_DIRECT`、PQ neighbor、直接更新和双前缀 shadow/merge 路径；因此可称 author-provided integrated implementation，但报告不会把它扩大描述为独立、完整的官方 release。

## 3. Clean base 与全部 patch

四套代码均从固定 commit 的独立 NVMe clone 开始；未修改 core search/update 语义。实际 dirty 状态只包含构建兼容层和 Atlas driver：

| Patch | SHA256 | 内容 |
|---|---|---|
| `patches/DiskANN_system_blas.patch` | `1f3ef6b49df4293708be6988f73ea22c5a3e99d6fe0e7e03b2390ec42fd99354` | system BLAS/LAPACK、local tcmalloc 与 MKL ABI compatibility |
| `patches/FreshDiskANN_reference_system_blas.patch` | `5d6cca75aa9c074a2112c66dd27b24aa2430bbba841717b946943ce23bb737f8` | system BLAS、local tcmalloc、MKL compatibility、统一 trace driver |
| `patches/DGAI_mkl_cblas_compat.patch` | `cc5a1d06a5902c0d8fcdbe24e1e2c2a770e3070b3c9ad5b426c6d54d00604319` | 缺失的 `mkl_cblas.h` ABI 声明与统一 trace driver |
| `patches/OdinANN_system_uring_cblas.patch` | `97af1345dd5ecb3e66e20597caf1aabfd8b4be52f2fcd56f6c11468f7eb41ee7` | system liburing / local gperftools / CBLAS compatibility 与统一 trace driver |

Fresh 还需要 `setarch x86_64 -R` 才能稳定运行该旧 release binary；默认 ASLR 下可复现启动崩溃。该措施记录为 artifact compatibility caveat，不算算法修复。

## 4. 数据来源、manifest、SHA256 与 L2 口径

| 数据集 | 来源与转换 | N / query / dim / dtype | 主文件 SHA256 | 距离口径 |
|---|---|---|---|---|
| SIFT1M | ANN-Benchmarks `sift-128-euclidean.hdf5`，原 HDF5 SHA `dd6f0a6ed6b7ebb8934680f861a33ed01ff33991eaee4fd60914d854a0ca5984`，经 `scripts/prepare_ann_benchmark_dataset.py` 转 float bin | 1,000,000 / 10,000 / 128 / float32 | base `8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e`; query `9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65` | squared L2 |
| GIST1M | ANN-Benchmarks `gist-960-euclidean.hdf5`，原 HDF5 SHA `8e95831936bfdbfa0a56086942e2cf98cd703517c67f985914183eb4cdbf026a`，同一转换器 | 1,000,000 / 1,000 / 960 / float32 | base `fd57967ae1461c453336b9be9621c74a2b5927e74cafa9f5e899a5dc5df6a5b8`; query `220465f0ab851de6890d87ab1dd5081f526da8d214aa7a3849e738e63cad6775` | squared L2 |
| DEEP1M | Yandex DEEP `base.10M.fbin` 的首 1M + 官方 `query.public.10K.fbin` | 1,000,000 / 10,000 / 96 / float32 | base1M `5b1f111897df7df0b8ef20c4248a7a87c8e1eee765485f24f6164d5364d381f4`; query `8438fc763f14e0f9741fda15b3e11215aef089ce17d1ad47d53b52a7c9fda5bb` | squared L2；原向量范数抽样约为 1，未二次归一化 |

DEEP 原始 10M base SHA 为 `290b341abc7ba570541e013fd20fd6d38c5873490ef395b512de5ed8dee18ce7`；下载的官方 full-corpus GT SHA 为 `9429e662db0f1a24a78a279f41ab1a20405e372178875e79f342d3a57ced9970`，但它不适用于 1M/80%-active 逻辑集，因此没有被错误复用。每个 dataset 目录共 23 个保留文件的完整 byte length + SHA256 见 `manifests/{sift1m,gist1m,deep1m}_sha256.json`。

## 5. 80/20 active / insert 划分

固定 seed 为 `20260713`。每个 1M corpus 的 tag 即原始 row ID：初始 active set 为 800,000 个 tag，insert pool 为此前从未 active 的 200,000 个 tag。checkpoint 分母严格为“累计被替换对象数 / 初始 active corpus 800,000”：

| checkpoint | 累计 replace 数 | active 数 |
|---:|---:|---:|
| 0% | 0 | 800,000 |
| 5% | 40,000 | 800,000 |
| 10% | 80,000 | 800,000 |
| 20% | 160,000 | 800,000 |

三个数据集复用完全相同的 tag-level trace，`replace_new_trace.csv` SHA256 均为 `fef6f1d0395c48cac7ee265b11e7fc974764c54ae3901a86952df8b6f3c6de51`。

## 6. Replace-new trace 与 same-vector control

正式 W1 候选 trace 每一步删除一个当前 active tag，再插入 insert pool 中未激活的新 tag，160,000 步内 cardinality 与唯一性恒为 800,000。smoke 取前 100 步并物化为 `<count, delete_tags[], insert_tags[]>` little-endian binary。same-vector control 仅做 API/tag 语义检查，不作为正式 workload。

所有 dynamic smoke 都从只读 static index 复制到独立 `attempt1` 后再修改，避免串扰或污染基线。DiskANN 不执行 insert/delete；以后只走 fresh rebuild workflow。

## 7. 每 checkpoint exact GT

`compute_exact_gt.sh` 对 0/5/10/20% 的实际 active vectors + tags 调用 exact L2 top-100，并为每个 checkpoint 输出新的 GT。`validate_groundtruth.py` 逐一检查 shape、active-tag membership、finite、distance monotonicity，再用独立 NumPy chunked brute-force 审计 query 0 与 17。

三数据集全部通过；每个审计 top-100 overlap 为 100，少量 ID 顺序差异只发生在等距 tie；最大绝对距离误差为 `4.53e-6`。完整证据见 `manifests/*_gt_validation.json`。100-op smoke 另用其实际 active set 重算 `gt_100.bin`，而非沿用 checkpoint 0 GT。

## 8. 12 个 build / load / query smoke

**12/12 组合均 build、load、query PASS。** 搜索统一扫描 `L={20,40,80,120}`，没有只挑作者默认单点。完整 readiness Recall 见 `manifests/query_smoke_summary.tsv`，原始日志位于 NVMe `results/atlas1m/<system>/<dataset>/query.log`。

关键构建参数：DiskANN `R64/L100/PQ-memory=64/T24`；Fresh `R64/L75`，但 GIST 使用 `R32`；DGAI `R32/L75` + refined PQ + split/reorder；OdinANN `R96/L128/PQ32`。GIST/Fresh 原生 R64 会产生 4100-byte record，而该 legacy layout 要求一条 record 落在单个 4 KiB sector，稳定触发除零；失败日志保留，smoke 改用该 artifact 可承载的 R32。DiskANN 与 OdinANN 的高维路径能使用 8 KiB I/O 承载大于 4 KiB 的 node。

1M 查询值只证明参数扫描和 GT 能闭环；没有据此生成 Pareto、排名或论文 Idea。

## 9. 9 个 replace-new dynamic update smoke

**Fresh / DGAI / OdinANN × SIFT1M / GIST1M / DEEP1M = 9/9 进程、更新、post-update exact-GT query PASS。** 每组为同一 canonical 100-op trace；before/after Recall 见 `manifests/dynamic_smoke_summary.tsv`。观察到的变化在 smoke 精度范围内，且 post-update query 使用重算后的 active-set GT。

same-vector SIFT1M control 的重要结果：Fresh 与 OdinANN 的 post-update query 可完成；DGAI 虽正常退出，但 merge 后元数据明确报告 `num_points=799900`。因此 DGAI 的“同 tag 并发 delete + reinsert”不是透明 refresh，control 标为 **control-fail**，也再次说明它不能替代 replace-new 主负载。

## 10. Update visibility 实测

| 系统 | 实测分类 | 代码 + 行为依据 |
|---|---|---|
| Fresh | immediate | insert/delete futures ready 后立即查询新 GT，driver 在 smoke 末尾退出，尚未触发 merge |
| DGAI | merge-visible | artifact driver 在 insert/delete 后同步 `merge_kernel`、reload，再执行 post-update query；没有证据支持 API-return immediate |
| OdinANN | immediate | insert/delete futures ready 后立即查询新 GT，末 batch 在 consolidation/merge 前退出 |
| DiskANN | unsupported（online update） | 本实验只把它登记为 static/fresh rebuild baseline |

这里的 immediate 指“API 完成后、merge 前对该 driver 的 query path 可见”，不等价于 crash-persistent。正式实验若要测 visibility lag，需要为 inserted-vector probe 和 deletion probe 增加 per-op timestamp，而不是从论文名称推断。

## 11. I/O backend 与资源采集原型

| 系统 | 本次实际 backend | 关键证据 / 参数 |
|---|---|---|
| DiskANN | Linux native AIO (`libaio`) + `O_DIRECT` | `io_submit`；query beam width 4 |
| Fresh | 默认 io_uring 分支 + `O_DIRECT|O_RDWR` | 未定义 `USE_AIO`；query beam width 4；兼容运行需 ASLR off |
| DGAI | `USE_AIO=ON`，libaio + `O_DIRECT` | topology / coord 分离，beam width 16，strategy 23 |
| OdinANN | `USE_URING` + `O_DIRECT` | build flags 与 runtime `io_uring_queue_init` 均验证；沙箱内被 seccomp 拒绝，沙箱外真实路径 PASS |

`resource_probe.py` 已同时采集 process-tree RSS、`smaps_rollup`、`/usr/bin/time -v`、cgroup v2 `memory.current/peak`、全机 page-cache 前后值以及 attempt 目录 apparent/allocated bytes。自测通过，完整 9 组资源摘要见 `manifests/resource_smoke_summary.tsv`。

cgroup 当前属于共享 session scope，所以其数字只做探针可用性验证，不能作为正式 `MEMdram`；正式运行必须进入 dedicated cgroup。所有系统使用 direct I/O，相关 index I/O 的 page-cache 应接近不适用，但 mapped metadata/PQ 和全机噪声仍需分开。正式报告将以 smaps private/anonymous、file-backed resident、dedicated-cgroup peak 和 relevant cache 四列呈现。

## 12. SSD logical / allocated / steady / peak

静态 1M 索引 apparent 与 allocated bytes 均已逐目录记录，见 `manifests/static_index_space.tsv`；两者接近，未发现依赖 sparse-hole 的虚假节省。dynamic attempt 的 final apparent / allocated size也已记录。

从 smoke 可见，Fresh 和 OdinANN 的 shadow/copy 路径峰值约为 static index 的 2 倍；OdinANN/GIST 因 8 KiB node I/O，static 约 6.58 GB、dynamic attempt 约 13.17 GB。DGAI 当前 merge 主要原地覆盖，但正式预算仍按旧/新文件并存 2 倍预留。DiskANN fresh rebuild 必须明确计入 old + new 两套索引同时存在的峰值，不能只报告最终 `du`。

本阶段总占用：datasets 约 26 GB、GT 129 MB、static + independent dynamic attempts 约 61 GB、src/build 约 4.2 GB；全部在 `/dev/nvme8n1`。执行结束时该盘约 20% used、系统盘约 45% used。

## 13. 正式 SIFT10M / DEEP10M / GIST1M 成本估算与停止点

以下只用于容量排期，按 1M 实测线性外推并加 1.5–2× 安全系数；不是正式结果：

| workload | raw full vectors | 单套 static index 粗估范围 | 单 dynamic attempt 峰值预留 | 单系统 build 粗估 |
|---|---:|---:|---:|---:|
| SIFT10M, 128D | 5.12 GB | 约 7.8–14.2 GB | 约 16–30 GB | 约 12–150 min（含安全系数） |
| DEEP10M, 96D | 3.84 GB | 约 6.5–12.6 GB | 约 14–27 GB | 约 10–185 min（含安全系数） |
| GIST1M, 960D | 3.84 GB | 实测 3.67–7.27 GB | 实测/预留约 7–15 GB | 实测 10–51 min |

三套数据、四系统 static、至少一套 old/new 或 shadow、副本化 dynamic attempt、GT 和日志合计建议预留 **300–450 GB NVMe**；当前约 1.4 TB 可用，容量充分。正式三系统 dynamic checkpoint + W0 query sweep 的第一轮建议按 **1–2 天墙钟** 排期；W2 mixed matrix 未经下一次审查不估算也不启动。

准备阶段剩余风险已经显式化：Fresh 不是官方 artifact 且依赖 ASLR-off；DGAI 缺少上游 LICENSE、same-tag refresh 失败且只能证实 merge-visible；GIST 会触发三个实现不同的跨 4 KiB record handling；dedicated cgroup 尚未用于 formal measurement。这些不是被隐藏的 smoke 失败，而是下一门禁必须决定的可接受性条件。

**停止声明**：已完成 GPT 批准的代码、数据、trace、GT、12 query smoke、9 dynamic smoke、visibility 与资源探针；未运行 SIFT10M/DEEP10M 正式索引、正式 Pareto 排名、W2 mixed matrix，也未从 1M 数值推导论文结论。请 GPT / Claude 复核后再发下一阶段授权。
