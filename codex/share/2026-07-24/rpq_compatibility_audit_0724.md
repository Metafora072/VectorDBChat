# RPQ-COMPATIBILITY-AUDIT

**日期：** 2026-07-24  
**范围：** 只审计，不训练、不运行 RPQ  
**最终裁决：** `RPQ-REPRODUCIBILITY-RISK`

## 结论

RPQ 的机制与当前 frozen-graph 问题高度相关：它学习 routing-aware
product quantizer，理论上可以只替换导航 codebook/codes，而复用原图、
SSD 读取和 full-vector rerank。因此“受控接入”在接口层面可行。

但论文指向的官方代码目前不能直接支持这项对照。仓库只实现了 NSG
graph feature extractor，没有论文所称的 DiskANN integration；训练入口、
CUDA 设备、图路径和编译路径均有硬编码，也没有环境锁定、release/tag
或可导入 DiskANN 的 artifact exporter。结论不是 RPQ 机制不兼容，而是
当前官方 artifact 不足以低风险复现 controlled frozen-graph baseline。

建议：若后续专门批准 RPQ baseline，先做受控 adapter 并通过 artifact
审计；不要先跑 native NSG fork，也不要把 native 系统差异归因于量化器。

## 论文、代码与版本

- 论文：[Routing-Guided Learned Product Quantization for Graph-Based
  Approximate Nearest Neighbor Search](https://arxiv.org/abs/2311.18724)。
- 论文和 README 指向的官方仓库：
  [Lsyhprum/BREWESS](https://github.com/Lsyhprum/BREWESS)。
- 审计 commit：`85f6f5196fa78e671740a492d72eb008c1617069`。
- 最新 commit 时间：2023-08-05；浅克隆可见 3 个 commits。
- tag/release：无。
- license：MIT。

## 17 项兼容性核对

| 项目 | 审计结果 | 边界/风险 |
|---|---|---|
| 1. 论文与官方仓库 | 已对应 | arXiv 与 README 相互对应 |
| 2. commit/release/version | 固定 commit；无 release/tag | 只能以 commit 复现 |
| 3. license | MIT | 允许修改与实验 |
| 4. DiskANN integration | **官方仓库未包含** | 仅见 `lib/pg` 的 NSG C++ 接入；论文虽报告 DiskANN 实验，但实现未发布 |
| 5. 数据格式/metric/维度 | Python loader 支持 fvecs/ivecs；训练以 L2 为主 | 没有声明最大维度 |
| 6. GIST1M-960D | 数据 loader/论文表格支持 | 唯一入口名为 `sift1m.py`，需改参数与资源控制 |
| 7. 复用现有 full graph | 机制上可以，现有代码不可以直接读 | 当前 graph extractor 读 NSG 格式，不读 DiskANN frozen graph |
| 8. 是否必须重构图 | RPQ 机制本身不要求 | 官方代码路径若直接运行会换到 NSG，破坏 controlled comparison |
| 9. codebook/code 格式 | PyTorch checkpoint 内的学习参数 | 没有导出 DiskANN pivots/codes 的工具或 schema |
| 10. 接当前 ADC | 通过 adapter 可行 | 需导出 rotation/codebooks/codes，并验证与 DiskANN chunk offsets、centering 一致 |
| 11. 32B/vector 含义 | 32 个 8-bit subcodes | 另有 codebook、模型和可能的旋转/训练 metadata；必须单列实际 resident bytes |
| 12. 训练资源 | 官方实现强依赖 CUDA | 论文 GIST 报告 8×V100、4.56h、模型约 1.8MB；CPU-only 不现实 |
| 13. 训练输入 | 500K learn vectors、graph 邻域和 routing samples | 需要从 frozen graph 重新抽 routing features；不应使用测试 query |
| 14. train/test 隔离 | 论文称 query 仅测试 | 脚本每 10 epochs 在正式 query 上评估；若据此选 checkpoint 会产生 model-selection leakage |
| 15. 量化外的优化 | 训练侧包含 graph feature sampling/joint losses | 搜索端理论上可只换 codes；native fork 的系统差异无法由当前仓库拆出 |
| 16. controlled frozen graph | **接口上可行，当前未就绪** | 需新增 DiskANN graph reader、route sampler 和 artifact exporter |
| 17. native-only 拆分 | 当前无法干净拆分 | NSG native 路径既改变图格式又改变执行器，不是可接受的量化器对照 |

## 代码级复现风险

- `lib/pg/__init__.py` 将 NSG graph 路径硬编码为开发机上的
  `/home/zjlab/.../sift10k_nsg.graph`。
- `lib/pg/setup.py` 包含开发机绝对 include/object 路径。
- `sift1m.py` 和模型代码广泛直接调用 `.cuda()`，并硬编码
  `CUDA_VISIBLE_DEVICES=7`。
- 默认训练为 500 epochs；脚本包含 GPU Faiss exact-NN 依赖。
- 仓库无 `requirements.txt`、conda environment、容器或版本锁定。
- 只有一个训练入口，没有 released checkpoint、GIST 配置或预生成 routing
  records。
- checkpoint 不是 DiskANN 可消费的 pivots/codes；没有导出或 round-trip
  验证。

## Controlled adapter 最小设计

目标保持：

```text
same GIST1M-960D base/train/query/GT
+ byte-identical R64/L100 full-precision graph
+ same W=4, K=10, L={50,100,200,400,800}
+ same ADC / SSD read / full-vector rerank
```

预计修改/新增：

1. 替换 `lib/pg/__init__.py` 与 `lib/pg/pg.cpp/.h` 的 NSG-only reader，
   或新增独立 DiskANN graph/routing extractor；
2. 修改 `sift1m.py`，参数化 dataset、seed、device、train/validation split；
3. 新增 exporter，将 learned transform、256-way chunk codebooks 和 1M
   codes 写成当前 DiskANN pivot/compressed schema；
4. 当前 DiskANN 搜索器原则上不改；只有 artifact loader 无法表达 RPQ
   transform 时才允许加最小、可审计的 loader；
5. 新增 graph SHA、row-ID SHA、test-query exclusion、codes round-trip 与
   reconstruction/routing-loss 审计。

这是 3–6 个工程日的 adapter 工作，不是一周内“下载即跑”的 baseline。

## 最小训练与搜索矩阵

若另行批准，先执行：

```text
Train:
  PQ32 (已存在 control)
  RPQ32 (frozen graph routing samples; fixed seed)

Canary:
  200 queries × L={100,200,400,800}

Full:
  PQ32 / RPQ32 / PQ64
  × L={50,100,200,400,800}
  × 1K held-out queries
  × two full repeats; conditional third repeat
```

RPQ64 不是回答“32B 强统一量化器能否消除 PQ64 差距”的必要项，只有
RPQ32 通过 canary 且训练稳定后再考虑。

## 资源预算

以下为基于论文配置与当前代码结构的保守规划，不是实测：

- GPU：官方路径需要 GPU；论文 GIST 使用 8×Tesla V100。单张现代
  24GB GPU 可能需要数小时到一天，必须先做小样本 profiling。
- GPU 显存：建议至少 16–24GB；routing batch/Faiss 配置可能提高需求。
- CPU RAM：32–64GB。
- NVMe：16–32GB（代码、learn/base 数据视图、routing records、
  checkpoints、codes 与日志；复用现有 base/graph 时增量可更低）。
- adapter：3–6 工程日。
- 正式训练：论文报告 GIST 4.56h/8×V100；不能线性外推单卡时间。
- 搜索：沿用当前 A0，约 20–35 分钟。

CPU-only 改写虽不是数学上不可能，但相对论文 GPU/Faiss/PyTorch 路径会
形成新的实现变量和过高耗时，不建议作为强 baseline。

## Hard stop

任一条件触发即停止：

- controlled path 改变 graph topology、entry point、node IDs 或 graph SHA；
- 使用正式 test queries 生成 routing samples、训练、early stopping 或选择
  checkpoint；
- exporter 不能复现 learned quantizer 的 ADC distance；
- 需要改搜索 beam、pruning、I/O batch、cache 或 rerank 才能获得收益；
- 32B 不再表示每个 base vector 的 32 个 8-bit subcodes；
- native NSG 结果无法与 representation-only 收益分离；
- GPU/显存/时间超过批准预算，或官方依赖无法锁定。

## 裁决

```text
reproducibility: RPQ-REPRODUCIBILITY-RISK
frozen-graph compatibility: CONCEPTUALLY-FEASIBLE-BUT-ADAPTER-REQUIRED
recommended path: CONTROLLED-FIRST, ONLY AFTER SEPARATE APPROVAL
native path: REJECT-AS-REPRESENTATION-ONLY-BASELINE
```

RPQ 仍是 mixed-precision idea 的最强邻近威胁，不能因代码复现风险而从
Kill Map 中删除；但它当前不满足“立刻运行且公平隔离量化器收益”的门禁。
