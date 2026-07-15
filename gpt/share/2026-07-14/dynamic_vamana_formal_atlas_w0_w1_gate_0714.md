# Dynamic Vamana Controlled Atlas：W0/W1 正式实验门禁

**日期**：2026-07-14
**上游结果**：

* `codex/share/dynamic_vamana_artifact_dataset_preparation_0713.md`
* `claude/share/dynamic_vamana_atlas_preparation_review_0713.md`

**裁决**：**PASS WITH EXECUTION GATES**

允许进入 SIFT10M、DEEP10M、GIST1M 的正式 W0/W1 实验，但必须分阶段执行。W2 mixed workload、系统 Idea 提取和论文结论暂不授权。

---

# 1. 对准备阶段的确认

以下条件已经满足：

* 12/12 system–dataset query smoke 通过；
* 9/9 动态 system–dataset update smoke 通过；
* query ground truth 经独立 brute-force 验证；
* replace-new trace 保持 active corpus 大小不变；
* DiskANN、Fresh-Ref、DGAI、OdinANN 的 artifact 身份已区分；
* 代码来自固定 clean commit；
* compatibility patch 与算法修改已分离；
* update visibility 已通过 artifact 行为初步验证；
* 1M 结果没有被用于生成性能排名或 Idea。

因此，不需要继续停留在 artifact 准备阶段。

---

# 2. 三项保留条件

## C1：DGAI 许可

DGAI 可以继续用于内部实验。

在任何外部发布之前，需要确认：

* 是否允许公开 benchmark 结果；
* 是否允许公开兼容性 patch；
* 是否允许公开基于其代码的修改。

在许可明确前，不向公共仓库分发 DGAI 源码或 patch，也不承诺其一定进入最终论文表格。

---

## C2：Fresh-Ref 的身份与 GIST 限制

该 artifact 统一命名为：

```text
Fresh-Ref
```

不能无脚注地称为官方 FreshDiskANN。

GIST 上 Fresh-Ref 因 legacy 4 KiB record 限制只能使用 R32，而其他系统可能使用 R64/R96。因此该数据点：

* 可以出现在原始结果表中；
* 必须明确标注 `R32 / 4KiB-layout constrained`；
* 可以用于展示该 artifact 的实际能力；
* 不能单独用于证明 FreshDiskANN 架构在高维数据上被其他系统支配。

---

## C3：Dedicated cgroup

正式运行必须为每次实验建立独立 cgroup scope。

采集至少包括：

* `memory.current`；
* `memory.peak`；
* process tree RSS；
* `smaps_rollup`；
* page-cache 变化；
* build/update/query 阶段的独立峰值。

shared login/session cgroup 的数据不能进入正式结果。

---

# 3. 正式数据集

## 3.1 SIFT10M

使用标准 BIGANN/SIFT corpus 的前 10M vectors，而不是对 SIFT1M 复制或重采样。

需要保留：

* 原始下载文件；
* 截取脚本；
* canonical float/bvec 格式；
* query；
* manifest；
* SHA256；
  -数据来源说明。

## 3.2 DEEP10M

使用已下载的 Yandex DEEP 10M corpus：

* squared L2；
* 96D float32；
* 官方 query；
* 不二次归一化。

## 3.3 GIST1M

继续使用准备阶段已验证的 GIST1M：

* 960D；
* squared L2；
* 作为高维 record-size 压力点。

GIST1M 不用于声称规模扩展性，但可用于观察维度和节点记录大小造成的架构差异。

---

# 4. 统一逻辑数据状态

所有系统使用相同的：

```text
80% initial active set
20% insert pool
seed = 20260713
```

正式索引初始只包含 80% active vectors。

不能出现：

* DiskANN 构建 100% corpus；
* 动态系统构建 80% corpus；
* 不同系统使用不同 active ID；
* 系统自己的默认插入顺序替代 canonical trace。

每个数据集必须生成并保存：

```text
checkpoint 0%
checkpoint 5%
checkpoint 10%
checkpoint 20%
```

对应的 active-tag manifest 和 exact top-100 GT。

---

# 5. 执行环境冻结

正式实验开始前输出一次环境 manifest：

* CPU 型号；
* socket/NUMA topology；
* DRAM；
* kernel；
* filesystem；
* NVMe 型号、firmware 和挂载参数；
* compiler；
* CMake；
* libaio；
* liburing；
* BLAS；
* transparent huge page 状态；
* CPU governor；
* SMT 状态；
  -系统后台服务和其他 I/O 任务。

所有系统：

* 使用同一块实验 NVMe；
* 不并行构建或运行；
* 固定 NUMA node 和 CPU set；
* 使用相同的 query/update CPU 配额；
* 每个正式点至少重复三次；
* 保存单次结果，不只保存平均值。

若某系统需要额外后台线程，必须记录其线程数和 CPU 占用，不能只限制前台 driver。

---

# 6. F0：10M Readiness

不要一开始直接运行完整矩阵。

## 6.1 顺序

建议首先在 SIFT10M 上依次完成：

```text
DiskANN
Fresh-Ref
DGAI
OdinANN
```

每个系统完成后验证：

* build 成功；
  -索引可重载；
* query 可完成；
* tag 与 GT 正确；
  -实际产生设备 I/O；
  -资源采集完整；
  -没有修改 core search/update 语义。

SIFT10M 四系统通过后，再执行 DEEP10M 和 GIST1M。

## 6.2 Build 指标

每个索引记录：

* build wall time；
* build CPU time；
* peak DRAM；
* read/write bytes；
* steady index size；
* allocated/apparent size；
* temporary peak SSD space；
  -主要参数；
  -产生的文件分解。

DiskANN 后续 rebuild baseline 必须使用相同构建流程。

## 6.3 Immutable base

初始静态索引完成后制作只读 base snapshot。

每次 churn 实验从 base snapshot 创建独立副本，禁止：

* 复用前一次失败后的索引；
* 不同系统共享可修改文件；
* 不同随机种子串行污染同一索引；
* 在 W0 索引上直接执行 W1 后继续称其为 W0。

---

# 7. W0：Query-only Atlas

## 7.1 系统范围

四个系统全部参与：

* DiskANN；
* Fresh-Ref；
* DGAI；
* OdinANN。

测试对象均为 checkpoint 0 的相同 80% active corpus。

## 7.2 搜索参数

每个系统扫描自己的 search parameters，例如：

* L；
* beam width；
* pipeline width；
* rerank candidates。

不强制相同参数值。

最终保存完整：

```text
Recall@10
vs
QPS / P50 / P95 / P99
```

曲线，而不是只保留一个作者默认点。

Matched-Recall 参考点：

```text
0.95
0.98
0.99
```

允许误差：

```text
±0.5 percentage points
```

若系统达不到某个 Recall 点，报告其最高可达结果。

## 7.3 Query concurrency

至少测试：

```text
Tq = 1, 8, 16, 32
```

若硬件或 artifact 明确不适合某档线程数，可以调整，但四个系统必须使用相同 concurrency set。

需要同时展示：

* 单线程 path efficiency；
* 中等并发；
  -高并发饱和吞吐；
  -并发提高后的尾延迟。

不能将不同查询线程数下的最大 QPS 放在同一表中却不标注 concurrency。

## 7.4 Cache 与进程生命周期

每个正式重复：

1. 结束上一实验进程；
2. 确认无遗留 worker；
3. 清理 page cache；
4. 启动新的 dedicated cgroup scope；
5. 加载系统需要的 DRAM-resident components；
6. 完成固定 warm-up；
7. 开始计时；
8. 保存原始 per-query latency。

由于四系统均使用 O_DIRECT，`drop_caches` 主要控制 metadata、mmap 和辅助文件读取，不能把它描述为清空设备本身的缓存。

## 7.5 W0 指标

必须记录：

* Recall@10；
* QPS；
* P50/P95/P99；
* query count；
* failed query count；
* runtime；
* query threads；
* search parameters；
* steady/peak DRAM；
* SSD index size；
* device read bytes；
* IOPS；
* bandwidth；
  -平均 queue depth；
* CPU utilization。

第一轮可以不加入侵入式 pages/query instrumentation，但设备级 I/O 指标不能全部缺失。

---

# 8. W1：Replace-new Churn

## 8.1 动态系统

参与：

* Fresh-Ref；
* DGAI；
* OdinANN。

从相同 checkpoint 0 base snapshot 开始，顺序执行 canonical replace-new trace：

```text
delete one active old vector
insert one never-active new vector
```

检查点：

```text
5%
10%
20%
```

百分比分母为初始 active corpus 大小。

## 8.2 更新性能必须拆成两种口径

### Ingestion throughput

从 update driver 开始提交，到系统 update API 完成。

记录：

```text
updates/s_ingest
```

### Visible-update throughput

从 update 开始，到对应 checkpoint 的完整 active set能够被查询正确观察。

记录：

```text
updates/s_visible
```

其中：

* Fresh-Ref/OdinANN：通常接近 API-complete visibility，但必须用 probe 验证；
* DGAI：必须包含 merge、reload 和 publish；
* DiskANN：对应 full rebuild + publish。

因此，DGAI 的 `Vm` 不能只使用 merge 前 ingestion throughput。

每个系统还需记录：

* update P50/P95/P99；
* batch latency；
* merge/consolidation latency；
* update CPU；
* update read/write bytes；
* DRAM peak；
* SSD peak；
* visibility probe 结果。

对于 batch-visible 系统，若无法定义有意义的 per-update P99，应报告：

* batch latency；
* batch size；
* amortized update latency；
* visibility completion latency。

不能伪造逐更新 P99。

## 8.3 Checkpoint Query

每个 5/10/20% checkpoint：

* 使用该 checkpoint 的 exact GT；
  -重新执行 W0 search sweep；
  -记录 Recall–QPS/P99；
  -记录 steady DRAM/SSD；
  -记录索引空间增长；
  -记录查询是否需要额外层、delta 或 mapping。

需要比较：

```text
checkpoint 0
→ 5%
→ 10%
→ 20%
```

下的查询性能和资源变化。

---

# 9. DiskANN Rebuild Baseline

DiskANN 不参与 online churn。

它的更新策略定义为：

```text
在新 active set 上重新构建完整索引
并原子发布新版本
```

## 第一阶段

强制执行：

* checkpoint 0；
* checkpoint 20%。

记录：

* rebuild time；
  -可见延迟；
* build peak DRAM；
* peak SSD；
* steady index size；
* rebuilt query frontier。

## 后续补齐

如果动态系统在 5%/10% 已出现明显趋势，或者 active-set 分布显著改变查询性能，则补做 DiskANN 5%/10% rebuild。

若未构建 5%/10% DiskANN，图中不得绘制或插值相应的 DiskANN 点。

---

# 10. Fresh/GIST 结果处理

Fresh-Ref/GIST R32 结果保留，但标记为：

```text
Fresh-Ref, GIST1M, R32,
legacy 4KiB-record constrained
```

建议同时报告：

* 它能够达到的最高 Recall；
* R32 下的 QPS/资源；
* R64 构建失败原因；
  -其他系统的 R 和 record/I/O size。

该结果可以揭示“固定单页记录布局在高维数据上的可扩展性边界”，但当前阶段不能直接把它包装为新的 Idea。

---

# 11. 结果文件

输出：

```text
codex/share/dynamic_vamana_formal_atlas_w0_w1_0714.md
```

原始机器可读结果建议：

```text
results/formal/
├── environment.json
├── artifact_manifest.json
├── dataset_manifest.json
├── build_results.tsv
├── w0_query_results.tsv
├── w1_update_results.tsv
├── w1_checkpoint_query_results.tsv
├── resource_results.tsv
└── raw/
```

每一行至少带：

* system；
* artifact level；
* commit；
* dataset；
* checkpoint；
* workload；
* repeat；
* query/update threads；
* parameters；
* Recall；
* QPS；
* latency；
* update ingestion/visible throughput；
* DRAM；
* SSD；
* I/O；
* status；
* caveats。

---

# 12. 本轮可以生成的图

允许生成描述性图，但暂不提 Idea：

1. Recall–QPS；
2. Recall–P99；
3. Query QPS vs churn volume；
4. Query P99 vs churn volume；
5. Ingestion update throughput；
6. Visible update throughput；
7. DRAM vs query performance；
8. SSD size vs query/update performance；
9. Update bytes vs churn volume；
10. Query performance before/after updates。

所有图必须显示原始系统名称、artifact 身份和关键限制。

---

# 13. 尚未形成最终 Vq–Vm Frontier

W0+W1可以回答：

* 纯查询能力；
  -更新处理能力；
  -更新可见成本；
  -更新后的查询性能；
  -DRAM/SSD 资源；
  -长期 churn 稳定性。

但它还不能完整回答：

> 查询和更新同时运行时，系统能够维持怎样的联合前沿？

真正的：

```text
Vq = f(Vm, Recall, DRAM, SSD, freshness)
```

需要 W2 concurrent mixed workload。

因此 W0+W1 完成后应停止，由 Gpt/PZ/Claude 根据结果选择：

* 是否执行完整 W2；
* W2 使用哪些线程/到达率区间；
* 哪些系统和数据集最值得继续；
  -是否已经出现值得深入的 architecture gap。

---

# 14. 停止条件

W0+W1 完成后停止，不执行：

* W2 mixed matrix；
* 100M 扩展；
  -新系统机制；
  -论文贡献总结；
  -自动选择“赢家”；
  -根据单个数据集生成 Idea。

若某个 10M artifact 无法运行：

1. 保存失败证据；
   2.检查是否为兼容性或资源问题；
   3.禁止修改核心 search/update 语义；
   4.将该组合登记为 unsupported/failed；
   5.继续其他可执行组合。

不得为了得到完整表格而实现一个未经验证的替代版本。
