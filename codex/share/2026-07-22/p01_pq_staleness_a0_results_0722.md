# P01-A0：动态更新后的 PQ 码本陈旧性

执行日期：2026-07-22（UTC）

## 结论

**VERDICT: PASS-PROBLEM（INSERT/BUILD mean PQ error ratio = 2.037635，> 1.10）**

按任务约定的均值比阈值，本实验通过“问题存在”判定。需要强调的是，该比值由约 0.1%--0.2% 向量的稀疏尾部误差驱动，并非全体 INSERT 向量普遍变差：BUILD 和 INSERT 的 median、p95、p99 均为 0。

## 数据与切分

源文件：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin`

| 集合 | 向量数 | 维度 | float32 数据文件大小 |
|---|---:|---:|---:|
| BUILD（前 700K） | 700,000 | 128 | 358,400,008 bytes |
| INSERT（后 300K） | 300,000 | 128 | 153,600,008 bytes |
| 合计 | 1,000,000 | 128 | 512,000,016 bytes（两个独立 8-byte header） |

源文件 header 为 `(1,000,000, 128)`，源文件总大小为 512,000,008 bytes；两个切分的 header、负载长度和文件尾均经过检查。`700,000 + 300,000 = 1,000,000`，维度为预期的 128。

切分命令：

```bash
python3 split_sift1m.py \
  /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin \
  build_700k.bin insert_300k.bin --build-count 700000
```

## DiskANN 构建

使用了任务指定的预构建 upstream DiskANN 二进制，命令如下，构建参数无偏离：

```bash
/home/ubuntu/pz/VectorDB/repos/DiskANN/build/apps/build_disk_index \
  --data_type float --dist_fn l2 \
  --data_path /home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p01_pq_staleness_a0/build_700k.bin \
  --index_path_prefix /home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p01_pq_staleness_a0/index/sift700k \
  -R 64 -L 100 --PQ_disk_bytes 0 \
  --num_threads 8 --search_DRAM_budget 4 --build_DRAM_budget 16
```

构建成功并以退出码 0 完成。DiskANN 根据 4 GiB search DRAM budget 自动选择了 128 bytes/vector，即 128 个一维 PQ chunks、每个 chunk 256 个中心。它从 BUILD 中随机抽取了 255,301 条训练向量（代码中的训练上限为 256K）。日志计时：PQ 训练和编码 185.039 s，Vamana 构建 57.174 s，总 indexing time 242.902 s；最终 disk index 为 573,444,096 bytes。

## PQ 重建误差

误差定义严格为实际解码后的 `||x - (pivot[code] + centroid)||²`。BUILD 使用 DiskANN 自身生成的 `sift700k_pq_compressed.bin` codes；INSERT 使用相同 pivots、centroid 和 chunk offsets，逐 chunk 选取精确最近中心后解码。

| 集合 | mean | median | p95 | INSERT/BUILD mean ratio |
|---|---:|---:|---:|---:|
| BUILD | 0.0091985714 | 0 | 0 | — |
| INSERT | 0.0187433333 | 0 | 0 | **2.0376352436** |

补充尾部统计：

| 集合 | p99 | p99.9 | max | error > 0 数量 | error > 0 比例 | 全集误差和 |
|---|---:|---:|---:|---:|---:|---:|
| BUILD | 0 | 1 | 477 | 734 / 700,000 | 0.104857% | 6,439 |
| INSERT | 0 | 1 | 901 | 582 / 300,000 | 0.194000% | 5,623 |

因此，INSERT 的非零误差发生率约为 BUILD 的 1.85 倍，同时 INSERT 存在更重的最大尾部误差；二者共同使 mean ratio 达到 2.0376。

## Per-chunk 误差

共计算了全部 128 个 chunk。下表列出按 INSERT mean error 排序的前 10 个；由于每个 chunk 恰好对应一个原始维度，chunk ID 与维度 ID 相同。全部 128 项保存在工作目录的 `pq_error_results.json`。

| chunk / dim | BUILD mean | INSERT mean | ratio |
|---:|---:|---:|---:|
| 117 | 0.0000342857 | 0.0030566667 | 89.1528 |
| 90 | 0.0000285714 | 0.0018333333 | 64.1667 |
| 3 | 0.0000500000 | 0.0015266667 | 30.5333 |
| 87 | 0.0005285714 | 0.0011933333 | 2.2577 |
| 34 | 0.0004014286 | 0.0011166667 | 2.7817 |
| 29 | 0.0000085714 | 0.0006033333 | 70.3889 |
| 31 | 0.0000400000 | 0.0005066667 | 12.6667 |
| 94 | 0.0000100000 | 0.0004233333 | 42.3333 |
| 21 | 0.0001300000 | 0.0002933333 | 2.2564 |
| 2 | 0.0001128571 | 0.0002866667 | 2.5401 |

128 个 chunk mean 的和分别精确回到 BUILD mean `0.0091985714` 和 INSERT mean `0.0187433333`。

## 一致性检查

- PQ pivots 文件为 256 centers × 128 dims，centroid 为 128 × 1，chunk offsets 为 129 × 1；compressed headers 分别为 `(700000, 128)` 和 `(300000, 128)`。
- BUILD codes 直接来自索引输出并用于解码。对 BUILD IDs `0, 1, 12345, 699999, 197930` 逐 chunk 暴力枚举 256 个中心，存储 code 与最近中心 code 的 mismatch 均为 0。
- 对 INSERT IDs `0, 1, 12345, 299999, 244826` 做同样的独立暴力复核，自编码 code mismatch 均为 0。普通样本误差为 0，最大误差样本 ID 244826 的误差为 901，既非 0 伪结果也非数量级异常。
- 最大 INSERT 样本在 dim 117 的原值为 187，而该维码本可解码最大值为 157，产生 `(187-157)^2 = 900`；dim 104 再贡献 1，总计 901。最大 BUILD 抽样复核值为 477。这确认尾部误差来自训练样本没有覆盖的极端标量值，而不是文件偏移或解码错误。
- pivots、BUILD codes、INSERT codes 的 SHA-256 分别为 `a4d6b0a6b5c55c117e773e1b0856babed5c800bb0c704e648a403ed17ebfcf36`、`39975bcb727d1235c15646f7a9c5989f9c803472efea330efe07b373f5a20a5d`、`534a7390328f6baee9075fef390ef409a546995e6f59123e8de2840a0b1590fa`。

## 偏离、限制与解释注意事项

- 构建命令无偏离。INSERT 编码没有调用预构建 `generate_pq`：该版本工具即使选择普通 PQ，源码仍以 `use_opq=true` 调用已有 pivots 的编码路径，会要求不存在的 rotation matrix。任务允许在此情况下自行实现标准 DiskANN PQ 编码，因此使用 NumPy 实现，并按 DiskANN 源码的 centroid、chunk 和最近中心规则逐点复核。
- `--search_DRAM_budget 4` 对 700K × 128d 数据足以让 DiskANN 选择最大 128 chunks。SIFT 值是整数的 float32 表示，而每个一维 chunk 有 256 个中心，所以 99% 以上向量可被完全无损重建。当前 PASS 信号是“稀疏、但 INSERT 更频繁且更重的未覆盖尾部”，不是分布主体的系统性误差抬升。
- mean error 相比典型向量 squared norm（抽样约 258K）非常小；在没有召回实验的情况下，不能据此断言有实际可测的 recall 损失。
- PQ 训练只随机抽样了 255,301 / 700,000 BUILD 向量，因此 BUILD 本身也包含未参与码本训练的尾部点。DiskANN 命令未提供固定 sampler seed，重建码本后尾部数值和 ratio 可能有随机波动。
- 未执行按 old/new 真近邻分段的 recall。上游 disk index 是静态索引，动态插入需要额外驱动；本轮按任务优先级集中完成 PQ-error 核心信号。故上述 PASS 是结构化输出契约规定的 PQ mean-ratio 判定，不包含 recall 佐证。

## 复现实物

所有工作文件均位于：

`/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p01_pq_staleness_a0/`

关键文件：`split_sift1m.py`、`analyze_pq.py`、`build_disk_index.log`、`analyze_pq.log`、`pq_error_results.json`、`index/sift700k_pq_pivots.bin`、`index/sift700k_pq_compressed.bin`、`insert_pq_compressed.bin`。
