# Visual PageMaxSim Residual Multi-Ball Stage A Report

**日期**：2026-07-12

**上游 gate**：`gpt/share/pagemaxsim_stage_a_decision_0712.md`

**最终裁决**：**CLOSE residual-certified exact synopsis branch**

**未执行**：K=1024、正式 A2 crossover、P3、architecture/system implementation

## 1. 结论

Stage A 按 Gpt 指定的 A0 → A1 顺序执行，并在 A1 触发关闭条件。

- **A0 通过**：codeword-sorted layout 的 exact page envelope 在 f9-int8、K=64 上将 95.1 页降到 76.0 页；因此 page grouping 后仍有约20%的理想空间，值得测试 certificate。
- **A1 失败**：raw-int8/f9-int8、K=64/256、sequential/best-upper 全部读取 **100% 页面**；128个 query-configuration rows 中没有一项跳过任何页面。
- **安全实现正确**：certificate violation 总数为 0；全局最小 certificate margin 为正，f9 K64/K256 分别为 0.04179/0.04119。
- **失败原因明确**：multi-ball 将 f9 平均 page slack 仅从约0.793降到0.750（K64）或0.741（K256），但每个 cell 在读到 true-max page 后仍平均有2.94–2.95个页面形成 false threat。f9 对象平均只有3页，等价于几乎所有未读页仍无法排除。
- **K 增大不收敛**：K=256 的 residual p50 比K64更小，但 exact-envelope pages反而由76.0增至80.8，multi-ball pages仍为95.1；metadata、DRAM和CPU同时增长。因此不满足K=1024放行条件。

这说明：

```text
page oracle / exact-envelope space 存在
        但
低成本 L2 residual certificate 无法兑现该空间
```

按 gate，本轮关闭 **residual-certified exact PageMaxSim admission**。不扩大成“所有近似page-aware MaxSim永远无空间”，但冻结当前 exact branch，不现场追加 angular cap、hierarchy、per-token sketch、learned router或scheduler。

## 2. 数据与执行边界

| 项目 | 配置 |
|---|---|
| Test workload | 原P0–P2的64个ViDoRe DocVQA documents、16 queries |
| Candidate set | normalized mean-vector top-32，保留qrel正例 |
| Outer policy | Col-Bandit `alpha=0.2, B=4, M=5, delta=0.01` |
| Codebook train | 额外256个document-disjoint ViDoRe pages |
| Representations | raw-int8、Light-style f9-int8，分别训练codebook |
| K | 64、256 |
| Page | 4096 B；int8 token row 130 B；实际serializer |
| Seed | 20260712 |
| Compute | CPU-only；无GPU |

256个训练页面从同一公开MIT Parquet离线编码，跳过原test的前64个unique documents。训练/测试document IDs集合在harness中强制`isdisjoint`。编码约33分钟；KMeans固定：

```text
random_state=20260712
n_init=10
max_iter=300
tol=1e-4
algorithm=lloyd
```

raw/f9均在真实serving representation上训练：int8逐token反量化后FP32归一化。persistent codeword为FP16，启动时解码FP32；radius与bound使用outward-safe arithmetic。

## 3. A0：Exact Group/Page Envelope

A0只训练codebook、按codeword ID重排装页，并使用每个物理页对query token的真实serving maximum作为exact upper envelope；没有构造residual radius。

| Representation | K | Full pages | Exact-envelope pages | Page oracle | Envelope/full |
|---|---:|---:|---:|---:|---:|
| f9-int8 | 64 | 95.06 | **76.00** | 71.25 | 79.94% |
| f9-int8 | 256 | 95.06 | 80.81 | 80.00 | 85.01% |
| raw-int8 | 64 | 792.63 | 429.94 | 186.69 | 54.23% |
| raw-int8 | 256 | 792.63 | 457.38 | 185.13 | 57.69% |

解释：

- f9 K64存在19.06页/query的理想可调度空间，并非“只省一两页”，所以A0允许进入A1。
- exact-envelope仍高于page oracle，因为固定best-upper order要同时服务一个document的多个active query-token cells，并非预知最终maxima union的omniscient scheduler。
- K256没有单调改善。更细codeword改变token packing，使f9 maxima分散到更多页；page oracle由71.25升到80.00。这已经否定“增加K自然逼近oracle”的假设。

## 4. A1：Outward-Safe Residual Multi-Ball

### 4.1 安全语义

certificate上界与serving FP32 MaxSim使用同一反量化、归一化token和固定逐页scan。residual norm、query norm、dot error、正值乘法和加法均采用FP64 outward上界；FP32 radius写盘时朝`+inf`舍入。

停止条件：

```text
max_observed_serving_score >= max_unread_page_upper
```

额外随机安全测试覆盖2400个page/query cases，violation为0。正式Stage A的128个query-configuration rows同样：

```text
certificate violations = 0
minimum certificate margin > 0
```

### 4.2 页面结果（best-upper schedule）

| Representation | K | Full | Exact envelope | Multi-ball | Saved | Multi/full | Min margin |
|---|---:|---:|---:|---:|---:|---:|---:|
| f9-int8 | 64 | 95.06 | 76.00 | **95.06** | 0 | 100% | 0.04179 |
| f9-int8 | 256 | 95.06 | 80.81 | **95.06** | 0 | 100% | 0.04119 |
| raw-int8 | 64 | 792.63 | 429.94 | **792.63** | 0 | 100% | 0.13067 |
| raw-int8 | 256 | 792.63 | 457.38 | **792.63** | 0 | 100% | 0.09595 |

16/16 queries、两种表示、两个K、两种schedule均为100% pages。sequential与best-upper的结论完全相同，证明失败不来自page order。

### 4.3 Slack来源

| Representation | K | Single-ball mean slack | Multi-ball mean slack | Multi P95 | False threats/cell |
|---|---:|---:|---:|---:|---:|
| f9-int8 | 64 | 0.7932 | 0.7496 | 0.9085 | 2.943 |
| f9-int8 | 256 | 0.7898 | 0.7414 | 0.9064 | 2.950 |
| raw-int8 | 64 | 0.8287 | 0.7959 | 0.9324 | 23.796 |
| raw-int8 | 256 | 0.8228 | 0.7825 | 0.9297 | 23.732 |

multi-ball确实比single-ball稍紧，但改善远小于“multi-ball → exact-page envelope”的剩余差距。主要损失不是page内多模态混合，而是：

```text
q·residual <= ||q|| ||residual||
```

抹去residual direction。K256只把f9 test residual p50从0.879降到0.848、p95从0.970降到0.957，仍远大于top-page之间的MaxSim gap，因此每页上界继续互相重叠。

## 5. Representation、Metadata与CPU诊断

### 5.1 Train/test residual与occupancy

| Representation | K | Occupancy min/P50/max | Train residual P50/P95 | Test residual P50/P95 |
|---|---:|---:|---:|---:|
| f9-int8 | 64 | 99/345/559 | 0.875/0.969 | 0.879/0.970 |
| f9-int8 | 256 | 12/81/264 | 0.830/0.942 | 0.848/0.957 |
| raw-int8 | 64 | 511/3048/7055 | 0.895/0.976 | 0.901/0.979 |
| raw-int8 | 256 | 132/670/2606 | 0.851/0.955 | 0.878/0.969 |

所有codewords均非空、无singleton。train/test residual接近，失败不是明显的codebook过拟合或held-out drift。

### 5.2 实际control plane

| Representation | K | Persistent synopsis | Data bytes | Synopsis/data | DRAM control | Mean query state |
|---|---:|---:|---:|---:|---:|---:|
| f9-int8 | 64 | 40,960 B | 782,336 B | 5.24% | 53,432 B | 21,999 B |
| f9-int8 | 256 | 98,304 B | 782,336 B | 12.57% | 161,632 B | 57,615 B |
| raw-int8 | 64 | 69,632 B | 6,520,832 B | 1.07% | 82,296 B | 33,868 B |
| raw-int8 | 256 | 147,456 B | 6,520,832 B | 2.26% | 209,192 B | 69,484 B |

文件大小来自实际`.bin`的`st_size`，含header、offsets、pair records和4 KiB尾部对齐。K256在f9上使persistent metadata超过data的12%，但没有减少一页。

### 5.3 CPU

向量化reference实现下，f9 K64/K256的完整online CPU约3.84/4.47 ms/query；旧f9 full-MaxSim reference约0.425 ms/query。由于data pages完全相同，任何正page service time下multi-ball都等于：

```text
same page cost + extra CPU + extra DRAM + extra persistent bytes
```

因此它被f9 full scan严格支配，不需要正式进入A2 crossover。上述CPU/metadata只是A1诊断计数，不构成“已执行A2”。

## 6. K=1024裁决

K=1024的五项放行条件均未满足：

1. f9没有安全跳过任何页；
2. K64→256的page结果不单调，反而变差；
3. metadata/CPU快速增长；
4. 当前page cost附近不可能进入Pareto，因为page数不变；
5. exact-envelope有空间，但certificate没有向它收敛。

所以K=1024 **未运行且不获批准**。

## 7. Gate映射与最终边界

命中Gpt的关闭条件：

- factor-9 multi-ball仍读取全部页面；
- residual-direction slack主导；
- control-plane CPU与空间使f9 full scan占据Pareto；
- K增大只增加成本，没有稳定收敛；
- raw也没有可兑现收益。

最终准确表述：

```text
Residual-certified exact PageMaxSim admission = CLOSED
PageMaxSim approximate branch = not evaluated / frozen
P3 = not run
architecture/system = not started
```

以后若研究approximate page admission，必须建立独立的ranking-fidelity/page-I/O/metadata故事，不能作为本轮exact claim的现场补丁。

## 8. 可复现材料

代码：

```text
codex/work/visual_pagemaxsim_gate/prepare_embeddings.py
codex/work/visual_pagemaxsim_gate/analyze_stage_a.py
codex/work/visual_pagemaxsim_gate/README.md
```

数据盘结果：

```text
/home/ubuntu/pz/VectorDB/data/pagemaxsim_gate/results/stage_a_a0/
/home/ubuntu/pz/VectorDB/data/pagemaxsim_gate/results/stage_a_full/
/home/ubuntu/pz/VectorDB/data/pagemaxsim_gate/artifacts/stage_a/
```

全部模型、环境、cache、embeddings、codebooks和结果仍只位于项目NVMe，总计约6.8 GiB。系统盘实验前后均为46%。

## 9. 下一步

按Gpt决策，无论Stage A结果如何，下一项主线转入：

```text
decoupled ANN architecture characterization
```

本报告不自动启动该任务；等待下一条对话固定characterization范围。
