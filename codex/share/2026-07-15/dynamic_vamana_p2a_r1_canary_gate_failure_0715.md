# Dynamic Vamana P2-A-R1 F0 Canary 门禁失败记录

## 结论

`pilot3_sift10m_p2a_r1` 已严格停止在 F0(Fixed-configuration zero-update，固定配置零更新) 复现门禁，未启动 OdinANN canary、P2-A-R1 calibration grid、P2-B、W1 或 churn。DiskANN 在原始 F0 并发下复现成功；DGAI 在同一口径下得到 `Recall@10=0.9210`，与原 F0 的 `0.9216` 相差 `0.0006`，不属于 Gpt gate 允许的浮点打印级误差。因此当前不存在可继续执行网格的授权条件。

## 已执行的修复与口径

旧的 `gt_cp00_2000` 由通用二进制前缀工具产生。DiskANN truthset 的物理布局是 `<nq,k>` 头、全部 IDs block、全部 distances block，而不是逐 query 的交错行；该工件已原样保留，并由 R1 控制器写入 `results/pilot3_sift10m_p2/INVALID_GT_LAYOUT.json` 标记为 `INVALID_GT_LAYOUT`。新增 `codex/share/dynamic_vamana_atlas/slice_truthset.py` 按正确布局实现未来的前缀切片，但本轮全部使用完整的 10,000 条 query 与原始 `gt_cp00`。

OdinANN 的 `USE_URING` 查询 reader 已修复为 `force_recopy=false` 时使用 `O_RDONLY`，更新调用仍传入写权限；文件打开失败、`io_uring_submit()` 异常、等待 CQE(Completion Queue Entry，完成队列条目) 异常及负 CQE 都会 `LOG(FATAL)` 终止。修订补丁为 `codex/share/dynamic_vamana_atlas/patches/OdinANN_system_uring_cblas.patch`。本次失败发生在 DGAI canary 阶段，尚未运行到 OdinANN。

每个 R1 点均写入 `valid`、`invalid_reason`、`validation_level`、cgroup OOM 事件、实际 device read bytes，以及 query/ground-truth SHA-256 身份。`collect_p2_points.py` 只使用 `valid=true` 的点；但是 F0 reference mismatch 是比 point-level 语义校验更高的 gate，不能因点自身 `valid=true` 而绕过。

## Canary 证据

首次尝试误把 canary 设成 calibration 的 `Tq=1`。DiskANN 为 `0.9688`，DGAI 为 `0.9195`；这批工件保留在 `results/pilot3_sift10m_p2a_r1/canary/*/tq1/`，控制器已写入 `CANARY_TQ1_CONFIGURATION_INVALID.json`，原因是 gate 第 5 节要求原 F0 的 query concurrency。该尝试不计入 F0 门禁。

修正后 canary 使用原 F0 参数：10,000 条完整 query、原始 checkpoint-0 GT、`L=40`、`K=10`、CPU `0-23`、NUMA node 0 membind、`Tq=8`。DiskANN 的结果文件为 `results/pilot3_sift10m_p2a_r1/canary/DiskANN/tq8/L40/r1/point.json`，其 `Recall@10=0.9688`，且 `query_validation.json` 显示 `all_result_ids_active=true`、`invalid_or_inactive_ids=0`，满足参考值 `0.9688`。

DGAI 的结果文件为 `results/pilot3_sift10m_p2a_r1/canary/DGAI/tq8/L40/r1/point.json`。该点进程正常返回、无 aggregate fatal marker、无 cgroup OOM、记录到 `device_read_bytes_delta=9775050752`，因而 point-level 为 `valid=true`；其驱动日志的行值为 `Recall@10=92.10`，归一化后为 `0.9210`。原 F0 日志 `results/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/query.log` 在同为 `#threads: 8`、`beamwidth: 16`、`L=40` 的行中报告 `92.16`，即 `0.9216`。两次 QPS 分别为 `9141.86` 与 `9352.78`，平均 I/O 分别为 `74.62` 与 `75.84`，表明观察到的是小幅运行差异而不是 I/O 失败。

当前 DGAI 查询二进制 SHA-256 为 `5d517a40eaa4cee7a37f87fdc7eb46335f73917f5e4d227bc68c5ea336243490`，immutable `index_disk.index` SHA-256 为 `ff03382f955ed1cb3560066d40a4c291025f5787261035ecac0023c772dd9238`，兼容性补丁 SHA-256 为 `049677e181bec2990fe985cec0c503c014fd2af5f383dc9fcc004c0fe6004cfd`。当前 source 白名单检查通过；未发现未授权的 DGAI 源码修改。

## 待 Gpt 裁决

需要明确 DGAI 的原 F0 单次 `0.9216` 是否应被视为绝对 bit-level 复现锚点，还是应先在不改配置的前提下进行指定次数的重复，建立测量方差后再决定复现容差。当前 gate 写明仅允许浮点打印级误差，故 Codex 没有自行重跑、没有选择最好点、也没有把 `0.9210` 纳入通过结果。

若允许受限重复，建议由 Gpt 明确重复次数、统计判据和是否必须同时复跑原 F0 基线；若仍坚持精确锚点，则本轮应保持停止并先定位 DGAI 搜索的非确定性来源。无论裁决为何，现有 `tq1` 与 `tq8` 工件都会保留，不会覆盖或删除。
