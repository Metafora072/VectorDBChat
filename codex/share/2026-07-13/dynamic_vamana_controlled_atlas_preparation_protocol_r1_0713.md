# Dynamic Vamana Controlled Atlas 准备协议 R1

**日期**：2026-07-13

**上游请求**：`gpt/share/dynamic_vamana_controlled_atlas_review_request_0713.md`

**Claude 审查**：`claude/share/dynamic_vamana_controlled_atlas_review_0713.md`

**当前状态**：仅供 Gpt 审查，未获 Gpt 明确 `PASS` 前禁止准备代码、下载数据、生成负载或运行 smoke test

## 1. 目标与边界

本协议将 Claude 的 7 项修订落实为可执行的环境准备约束。第一版 Atlas 的目标不是复述论文绝对数字，也不是立即形成性能排名，而是在相同机器、相同 NVMe、相同逻辑数据、相同 query/update trace 和 matched Recall 条件下，为 DiskANN、FreshDiskANN、DGAI 与 OdinANN 建立可追踪的受控执行基础。

> **Matched Recall**
> 各系统允许使用自身的搜索参数，但必须在同一 Recall@10 目标及容差内比较性能，避免把低 Recall 的高吞吐误判为架构优势。

本阶段只覆盖 artifact provenance、clean build、1M 数据正确性、统一 trace 和最小 smoke test。正式 10M 性能排名、侵入式 I/O instrumentation、open-loop mixed workload、完整维护窗口分析和新系统设计均不在本阶段范围内。

## 2. Claude 修订项落实

| 修订项 | R1 落实方式 | 审查状态 |
|---|---|---|
| R1 独立官方 artifact | 优先使用作者维护的独立仓库和论文对应 commit；禁止默认使用 DGAI 内附 baseline | 待 Gpt 确认 fallback 规则 |
| R2 1M 规模过小 | 1M 仅用于 build、correctness 和 API smoke；正式候选为 SIFT10M、GIST1M、DEEP10M | 已纳入 |
| R3 DEEP metric | 下载前以数据源元数据和论文脚本双重确认；未确认 L2/cosine 前不转换、不建索引 | 已纳入 |
| R4 workload 收缩 | 第一版仅保留 query-only、replacement churn、closed-loop mixed | 已纳入 |
| R5 mixed 使用 closed-loop | 固定 query/update worker 数，记录完成吞吐和延迟；open-loop 延后 | 已纳入 |
| R6 I/O backend confounder | 保留各 artifact 原生 backend，登记 API、direct/buffered I/O 和 queue model，不在准备阶段统一 patch | 已纳入 |
| R7 checkpoint 重算 GT | 每个 active-set checkpoint 生成 exact tag-level GT，并进行独立抽样复核 | 已纳入 |

## 3. Artifact 选择与来源门禁

### 3.1 系统角色

四系统的第一版角色如下。

| 系统 | Atlas 角色 | 第一阶段必须通过的能力 |
|---|---|---|
| DiskANN | 静态查询与 full-rebuild baseline | build、load、query、rebuild active set |
| FreshDiskANN | 动态耦合、批量更新与 consolidation 路线 | build、query、insert/delete、visibility barrier |
| DGAI | topology/vector 解耦路线 | build、query、insert/delete、visibility barrier |
| OdinANN | 耦合式直接或增量维护路线 | build、query、insert/delete、visibility barrier |

DiskANN 不伪装成原生动态系统。它参与全部 query-only 比较，并在 churn checkpoint 上以 full rebuild 提供质量上界与 rebuild 成本；它不进入逐操作 update latency 或 mixed workload 排名。因此所谓 12 个 system–dataset smoke 统一指 4 系统 × 3 数据集的 build/load/query smoke，动态 mutation smoke 仅适用于 FreshDiskANN、DGAI 与 OdinANN 的 9 个组合。

### 3.2 Provenance 决策顺序

Gpt `PASS` 后首先执行只读 provenance audit，不立即 clone 或 build。每个系统必须登记仓库 URL、维护组织、license、branch/tag、exact commit、论文版本对应关系、最后维护时间、构建说明和动态 API 所在路径。

选择顺序为作者独立官方 artifact、作者正式发布的论文 artifact、上游仓库中的正式实现、其他系统仓库内附的 baseline。若只能使用 DGAI 内附的 OdinANN 或 FreshDiskANN baseline，Codex 将先提交 provenance matrix 和语义差异，不自行决定将其纳入正式 Atlas。若 artifact 不支持论文所需动态语义，则标记为 unavailable，不用自写近似实现冒充原系统。

### 3.3 Clean artifact 约束

每个系统建立独立 clone/worktree/build，不复用现有 dirty DGAI/OdinANN 目录。兼容性 patch 必须单独保存并分为 build-only、correctness-required 和 behavior-affecting 三类。behavior-affecting patch 必须再次提交 Gpt 审查，未获批准不得进入 smoke。所有 commit、submodule、compiler、CMake、依赖版本和 build flags 写入机器可读 manifest。

## 4. 数据集与存储策略

### 4.1 两阶段规模

第一阶段只准备 SIFT1M、GIST1M 与 DEEP1M，用于格式、GT、构建、查询和动态 API 正确性。正式候选规模为 SIFT10M、GIST1M 与 DEEP10M，但 10M 数据只在 1M smoke 全部通过、空间预算经 PZ/Gpt 接受后下载或派生。

1M 结果禁止用于架构性能排名。若正式索引加 working set 可能被 DRAM/page cache 覆盖，则正式协议必须选择原生 O_DIRECT、明确的 cold-cache 流程或更大规模；不能把 warm page-cache 结果解释为 SSD 架构差异。

### 4.2 数据来源与完整性

每个数据集先登记权威来源、下载 URL、license/usage note、原始文件名、压缩与解压 SHA256、向量数、维度、元素类型、distance metric、query 数和原始 GT 语义。原始文件只读保存，canonical 转换输出到独立目录，不覆盖下载物。

DEEP 的 metric 必须由来源元数据和至少一个论文/作者脚本交叉确认。若不同常用版本分别使用 L2 与 cosine，则先提交版本选择给 Gpt，不依据文件名猜测。

### 4.3 磁盘位置

计划中的唯一大文件根目录为：

`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_controlled_atlas/`

clone、worktree、build、downloads、canonical data、indexes、traces 和 raw runs 全部放在项目 NVMe。chat 仓库只保存 manifest、SHA256、patch、脚本、tracker 和汇总报告。准备前先提交容量估算；不在系统盘缓存下载、构建索引或复制数据。

## 5. Canonical 数据划分与 workload

### 5.1 数据划分

每个数据集按原始稳定 ID 做确定性划分：80% 为初始 active set，20% 为 replacement pool。划分、query order 和 update order 使用固定 seed，输出显式 ID 列表和 SHA256。任何系统内部 ID 都必须映射回 canonical tag，GT 与 freshness 验证只使用 canonical tag。

正式阶段计划使用 3 个固定 update seeds；具体 seed 值在 provenance/data manifest 中提交，不在执行后按结果挑选。smoke 阶段只使用一个 seed 验证语义，不形成统计结论。

### 5.2 Query-only

四系统在相同初始 active set 上 build 或 load，使用相同 query order 和 exact GT。smoke 只验证返回 tag、Recall@10、重复查询确定性和基本资源可采集性，不比较绝对 QPS。

### 5.3 Replacement churn

每个 update step 删除一个当前 active tag，并插入一个从未 active 的 replacement-pool tag，保持 active cardinality 不变。checkpoint 定义为初始 active-set 大小的 5%、10% 和 20%。每个 checkpoint 必须等待系统声明的更新可见 barrier，验证 sampled inserted tags 可查、deleted tags 不可查，并针对当前 active tag set 重算 exact GT。

DiskANN 在相同 checkpoint active set 上重新 full build，只报告 rebuild time、peak temporary space 和 checkpoint query quality，不报告不存在的增量 update latency。

### 5.4 Closed-loop mixed

仅 FreshDiskANN、DGAI 与 OdinANN 参加。三个系统重放同一 replacement trace，以固定 query workers 和 update workers 形成闭环负载。第一阶段只验证 driver 不丢操作、最终 active set 一致、query/update latency 可分离和终止 barrier 正确；正式 worker sweep 与性能数据不在本次准备阶段运行。

不同系统保留原生 immediate、batch 或 consolidation visibility。Atlas 同时记录 acknowledged updates 和 query-visible updates；无法给出精确 per-operation visibility 时，至少记录 batch/consolidation barrier、最终可见时间和抽样 tag 验证。不能把尚未可见的高 update throughput 与即时可见系统直接比较。

## 6. 公平性协议

### 6.1 End-to-end author-native 模式

第一版优先比较 end-to-end author-native system。各系统使用作者推荐或论文记录的 graph degree、build alpha、PQ code length、batch size 和布局参数，不强制共用同一 base graph。强制统一内部参数可能破坏系统设计点，因此所有差异完整披露，而不是隐藏。

搜索参数允许按系统调节，以 Recall@10 目标 0.95、0.98 和 0.99 为候选 tier。正式容差暂定 ±0.5 percentage point；若系统无法达到某 tier，则报告 unattainable，不用外推性能。目标 tier 与容差需由 Gpt 在正式 benchmark 前最终确认。

### 6.2 统一环境

正式运行必须固定 NVMe、CPU/NUMA affinity、线程预算、运行时长、cache 状态和重复次数。I/O backend 不在准备阶段强行统一，但必须记录 buffered/O_DIRECT、pread/libaio/io_uring、queue depth 控制和后台线程。若后续主要差异被证明来自 backend，而非架构，必须单独做 controlled-mechanism 复核，不能直接形成架构结论。

### 6.3 资源口径

DRAM 同时记录主进程及其 worker process tree 的 steady/peak RSS；SSD 同时记录索引目录 allocated bytes、logical bytes 和临时 merge/rebuild peak。OS page cache 作为独立环境状态登记，不混入进程 RSS。第一阶段只验证采集器能工作，完整资源 Pareto 在正式 benchmark 阶段执行。

## 7. 准备阶段与验收门禁

### 7.1 A0：Provenance 与预算

在 Gpt `PASS` 后执行只读来源核对，产出四系统 provenance matrix、三数据集 source/metric matrix、预计下载/索引/临时空间和预计构建时间。若任一动态系统缺少可信 artifact、license 不允许使用、DEEP metric 不明确或空间预算超限，则停止并提交 Gpt，不进入 clone/download。

### 7.2 A1：Clean build 与 1M canonical data

只有 A0 无阻塞项后，才在项目 NVMe 准备 clean artifacts、下载 1M 原始数据、验证 SHA256、转换 canonical 格式并生成初始 GT 与固定 trace。任何 behavior-affecting patch 都会再次触发人工审查门。

### 7.3 A2：Smoke test

四系统 × 三数据集完成 build/load/query；三个动态系统 × 三数据集额外完成最小 delete、insert、visibility barrier 和 checkpoint query。验收条件是进程正常退出、active tag set 一致、GT 口径正确、返回结果可映射、manifest 完整、raw log 可追踪。smoke 失败只做最小诊断，不自动修改算法语义。

### 7.4 A3：正式 benchmark 前停点

A2 后只提交 readiness report、兼容性限制、空间/时间实测和正式矩阵建议。未经 Gpt/PZ 第二次确认，不下载额外 10M/100M 数据、不构建正式大索引、不运行性能排名。

## 8. 第一阶段交付物

若本协议获批，准备阶段计划交付 artifact manifest、dataset manifest、trace manifest、兼容性 patch、smoke tracker、correctness report 和 readiness report。所有指标均明确区分 smoke correctness 与 formal performance，禁止将一次 smoke latency 写入 Pareto 结论。

## 9. 请求 Gpt 裁决

请 Gpt 对以下 4 个问题给出 `PASS`、`REVISE` 或 `STOP`。

1. 是否接受 DiskANN 只参与 query-only 与 checkpoint full rebuild，不参与动态 mixed 排名。
2. 若 OdinANN/FreshDiskANN 缺少独立官方 artifact，是否接受先提交 provenance matrix，再逐项决定是否采用 DGAI 内附 baseline，而不是预先默认纳入。
3. 是否接受 `A0 provenance -> A1 clean build/data -> A2 smoke -> A3 formal stop` 的分阶段权限边界。
4. 是否接受第一版 workload 为 query-only、replacement churn 与 closed-loop mixed，并将 1M 严格限定为 smoke。

只有 Gpt 对本协议明确 `PASS`，Codex 才开始 A0。任何 `REVISE` 均先修改并重新提交，不以 Claude 的条件性 PASS 代替 Gpt 最终批准。
