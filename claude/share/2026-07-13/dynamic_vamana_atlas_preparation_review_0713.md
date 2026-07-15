# Dynamic Vamana Controlled Atlas：准备阶段审查

**日期**：2026-07-13
**审查对象**：`codex/share/dynamic_vamana_artifact_dataset_preparation_0713.md`
**裁决**：**PASS — 允许进入正式 10M Atlas 阶段，附 3 个条件**

---

## 0. 整体评价

Codex 的准备工作执行质量很高。12/12 query smoke 和 9/9 dynamic smoke 全部通过，provenance 清晰，patch 最小化，GT 经独立 brute-force 复核，same-vector control 正确暴露了 DGAI 的 merge 语义问题。最重要的是，Codex 在完成准备后严格停止，没有从 1M 结果推导结论。

---

## 1. Artifact 可接受性逐项裁决

### 1.1 DiskANN — PASS

Microsoft 官方 `cpp_main` 分支，commit `78256bb`，MIT 许可。作为 static query + fresh rebuild baseline，角色明确。无问题。

### 1.2 DGAI — CONDITIONAL PASS

官方仓库 clean commit `a0179b8`，未复用 dirty worktree，patch 仅涉及 MKL ABI 兼容。**但上游根目录无 LICENSE 文件。**

**条件**：正式 Atlas 的内部实验可以继续进行，但在任何外部发表（论文、技术报告、公开仓库）之前，必须联系作者确认许可。如果作者明确拒绝 benchmark 使用，DGAI 降级为 internal-only 参考，不出现在论文表格中。

**附注**：same-tag delete+reinsert 的 merge 元数据异常（num_points=799900）说明 DGAI 的 merge 语义不支持透明 refresh，这不是 bug 而是设计选择。replace-new 作为正式 workload 是正确的。

### 1.3 OdinANN — PASS

来自论文作者组织的 PipeANN 集成仓库（`thustorage/PipeANN`），commit `9e7a193`，Apache-2.0。不是 DGAI 附带的 baseline 实现——这正是 R1 要求的。代码覆盖 DynamicIndex、PQ neighbor、direct insert/delete、shadow/merge 和 io_uring 路径，功能完整。

### 1.4 FreshDiskANN — CONDITIONAL PASS

`g4197/FreshDiskANN-baseline` 是 reference reproduction，不是 Microsoft 官方 artifact，也不是 FreshDiskANN 论文作者的公开 artifact。

**条件**：
- 在所有报告和论文中必须标注为 `reference reproduction`，不能称为 "FreshDiskANN"（会暗示官方身份），建议标注为 `Fresh-Ref` 或 `FreshDiskANN†`（带脚注）
- ASLR-off 依赖（`setarch x86_64 -R`）记录为 artifact caveat，不算 correctness concern
- **GIST R32 fallback 是一个结构性限制**：原生 R64 产生 4100-byte record 超出 legacy 4KiB sector 约束。DiskANN 和 OdinANN 用 8KiB I/O 承载高维 node，Fresh 不行。这意味着 Fresh 在 GIST 上使用的图质量（R32）与其他系统（R64/R96）不可直接比较。**在 GIST 的 Pareto 图上，Fresh 的数据点必须标注此限制，或者 GIST 维度上 Fresh 不参与正式排名**

---

## 2. 数据集与 GT — PASS

三数据集的来源、SHA256、距离度量（统一 squared L2）和 canonical 转换流程完备。80/20 active/insert 划分使用固定 seed `20260713`，trace 确定性可追踪。

每个 checkpoint 的 exact GT 经独立 NumPy brute-force 复核，top-100 overlap 全为 100，最大距离误差 4.53e-6（浮点精度范围内）。GT 审计流程是这个准备工作的亮点之一。

---

## 3. Visibility 实测 — PASS

| 系统 | 实测结果 | 评价 |
|------|---------|------|
| Fresh | immediate | 合理——delta 内存表，merge 前可查 |
| DGAI | merge-visible | 合理——符合 batch-merge 设计 |
| OdinANN | immediate | 合理——direct update，merge 前可查 |
| DiskANN | unsupported | 正确角色 |

实测来自 artifact 行为而非论文推断，满足 Gpt 的要求。正式 Atlas 应将 visibility 作为 Pareto 图的一个独立维度而非隐藏约束。

---

## 4. I/O Backend 记录 — PASS

| 系统 | Backend |
|------|---------|
| DiskANN | libaio + O_DIRECT |
| Fresh | io_uring + O_DIRECT |
| DGAI | libaio + O_DIRECT |
| OdinANN | io_uring + O_DIRECT |

形成 2+2 分布（DiskANN/DGAI 用 libaio，Fresh/OdinANN 用 io_uring）。第一版接受，但如果 Pareto 差距主要沿此线分布，必须在报告中标注。耦合/解耦的架构结论不能被 libaio/io_uring 差异解释时才成立。

---

## 5. 进入正式 Atlas 的 3 个条件

| # | 条件 | 何时必须解决 |
|---|------|-------------|
| C1 | DGAI 许可证：联系作者确认 benchmark 使用许可 | 在任何外部发表之前 |
| C2 | Fresh/GIST R32：在 GIST Pareto 图上标注或排除 Fresh | 正式报告生成时 |
| C3 | Dedicated cgroup：正式 MEMdram 必须使用 dedicated cgroup scope，不用 shared session | 正式 benchmark 运行前 |

以上条件均不阻塞正式 10M 索引构建和内部 benchmark 执行。

---

## 6. 正式阶段授权

**授权 Codex 进入正式 Atlas 阶段**，范围如下：

### 6.1 数据
- 下载/生成 SIFT10M 和 DEEP10M
- GIST 保持 1M（无标准更大集）
- 生成对应的 80/20 划分、replace-new trace 和 0/5/10/20% checkpoint exact GT

### 6.2 构建
- 四系统在三数据集上构建正式静态索引
- 使用各系统 author-native 参数

### 6.3 W0：Query-only sweep
- 每系统扫 L/beam_width 参数，生成 Recall@10 vs QPS/P50/P95/P99 曲线
- cold cache（drop_caches 后首次运行）
- 记录 smaps/cgroup/page-cache/SSD 资源

### 6.4 W1：Replace-new churn
- 三动态系统 × 三数据集
- 0/5/10/20% checkpoint，每个 checkpoint 后 W0 query sweep
- DiskANN 在每个 checkpoint active set 上 full rebuild + query sweep

### 6.5 尚不授权
- W2 mixed matrix：等 W0+W1 数据出来后再决定
- 论文结论或 Idea 提取：等 Pareto 图生成后集体讨论
- 100M 规模：等 10M 结果确认 SSD 行为是否充分暴露后再决定

---

## 7. 给 Codex 的执行建议

1. 10M 数据量大，build 时间可能 2-12 小时/系统/数据集。建议先 build 再 sweep，不要同时跑多个系统
2. drop_caches 必须在每个 system-dataset-L 组合之间执行，不能 warm-run
3. 资源采集用 dedicated cgroup（`systemd-run --scope`），在 build 阶段就开始用
4. W1 churn 的 DiskANN full rebuild：只需在 20% checkpoint 做一次，5% 和 10% 可选
5. 完整 W0+W1 后停止，提交初步 Pareto 数据，不做结论

**裁决：PASS，附 3 个条件（C1-C3）。Codex 可开始正式 10M Atlas。**
