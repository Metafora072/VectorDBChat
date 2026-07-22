# P07 A0 实验结果：Page Bonus — Free Co-Resident Node Utility

实验日期：2026-07-22（UTC）  
数据集：SIFT1M，float32，128 维，L2  
DiskANN 源码基线：`78256bbab4685e1774e78d331e081a153be26823`（见第 7 节关于本地兼容性改动的说明）

## 1. 磁盘布局统计

按任务指定参数在完整 1,000,000 个向量上成功构建 R64/L100 磁盘索引。DiskANN 磁盘索引头和节点槽抽查结果如下。

| 项目 | 结果 |
|---|---:|
| 逻辑扇区大小 | 4,096 B |
| 数据节点数 | 1,000,000 |
| 向量维度 | 128 |
| 图最大度数 | 64 |
| `max_node_len` | 772 B |
| 每个完整扇区节点数 | 5 |
| 完整扇区已用空间 | 3,860 B |
| 每个完整扇区尾部空闲 | 236 B（5.76%） |
| 数据扇区数 | 200,000 |
| 元数据扇区数 | 1 |
| 总扇区数 | 200,001 |
| 磁盘索引文件大小 | 819,204,096 B |
| medoid 节点 ID | 123,742 |

节点数/数据扇区分布为：**5 节点：200,000 个扇区（100%）**。1,000,000 恰好被 5 整除，没有不满的尾扇区。随机等距抽查 1,000 个隐式节点槽，存储度数均为 64，且节点槽偏移和文件边界全部有效。

实际 DiskANN 格式与任务描述中的简化格式略有差异：节点 ID 不写入扇区，而由槽位隐式确定；物理扇区 0 是元数据，节点 `id` 位于物理扇区 `1 + id / 5`、槽位 `id % 5`。每个槽位是 `[128×float32 vector][uint32 nnbrs][neighbor IDs][padding]`。因此 sector→node 映射无需猜测或扫描 ID：零基数据扇区 `s` 对应节点 `{5s, ..., 5s+4}`。

完整性检查：索引头的 1,000,000 节点与 `full_1m.bin` 头完全一致；声明文件大小、实际文件大小及 `200001 × 4096` 三者均为 819,204,096 B。

## 2. 方法摘要

### 索引与搜索配置

- 索引：完整 SIFT1M，`R=64`、`Lbuild=100`、`PQ_disk_bytes=0`、8 线程、搜索/构建内存预算 4/16 GB。
- 查询样本：原始 10,000 条查询中**保持原顺序的前 1,000 条**（10%）。
- 搜索：`K=10`、`L=100`、`beamwidth=2`、单线程、`num_nodes_to_cache=0`。
- 搜索质量：Recall@10 为 **99.75%**；返回 top-10 的 100% 均在精确 GT-100 中。

### visited/expanded 轨迹

没有修改原 DiskANN 仓库。将源码复制到工作目录后，只在副本中加入一个由 `P07_TRACE_PATH` 环境变量控制的最小日志钩子：每次 `cached_beam_search()` 从候选队列取出并标记为 expanded 的节点，按顺序写入该查询的 CSV 行；搜索驱动在调用前写入稳定的 query ID。不开启环境变量时钩子不产生文件或额外 I/O。

轨迹验证通过：恰好 1,000 行、qid 恰好为 0–999、每行非空、所有节点 ID 均在 `[0, 1,000,000)`，且单条查询内没有重复 expanded ID。轨迹中的平均 106.355 个 expanded 节点与搜索器报告的平均 106.36 I/O 一致。

### GT 与 bonus 定义

使用 DiskANN `compute_groundtruth` 对这 1,000 条查询和全部 1M 基向量计算精确 GT-100。GT 文件为 1,000×100，并保持查询文件顺序。另用 NumPy 对 qid 0、499、999 全库暴力复算：三条查询的 GT-100 集合均 100/100 一致，top-1 也一致；qid 499 有两个等距项的次序差异，但本实验只使用集合成员关系，不受影响。

对每条查询，按 expanded 顺序处理每次读取的扇区。扇区中的其他节点若此前尚未显式展开，则记录为该查询的 bonus；同一 bonus 节点在同一查询内只计一次，并保留首次免费出现的步骤。随后检查它是否属于 GT-100、是否在更晚步骤被 expanded，以及是否属于最终 top-10。另保留未去重的 bonus exposure 数，便于检查去重影响。

## 3. 每查询 bonus 节点分析汇总

1,000 条查询共发生 106,355 次显式节点读取，产生 425,074 次 bonus exposure；按“查询内节点 ID”去重后为 424,056 个 bonus 节点，去重仅减少 1,018 次（0.24%）。

| 每查询指标 | 均值 | 中位数 | P95 | 最小–最大 |
|---|---:|---:|---:|---:|
| 显式 expanded/读取数 | 106.355 | 106 | 109 | 101–113 |
| 唯一数据扇区数 | 106.014 | 106 | 109 | 99–112 |
| 同扇区重复读取数 | 0.341 | 0 | 2 | 0–10 |
| bonus exposure 数 | 425.074 | 424 | 436 | 403–451 |
| 唯一 bonus 节点数 | 424.056 | 424 | 436 | 396–448 |
| bonus∩GT-100 数 | 0.313 | 0 | 2 | 0–10 |
| 后续被 expanded 的 bonus 数 | 0.341 | 0 | 2 | 0–10 |
| bonus∩最终 top-10 数 | 0.011 | 0 | 0 | 0–1 |

效用高度集中且多数查询为零：797/1,000（79.7%）查询没有任何 GT-100 bonus，770/1,000（77.0%）没有任何后续 expanded bonus；只有 11 个查询出现一个最终 top-10 bonus。GT-100 bonus 命中的 67.09% 集中在命中数最高的 10% 查询中，后续 expanded 命中的相同比例为 61.88%。

## 4. Bonus utility 分解

分母均为每查询去重后再汇总的 424,056 个 bonus 节点。

| Utility 事件 | 命中数 | 汇总比例 | 每查询比例均值 / 中位数 / P95 |
|---|---:|---:|---:|
| 属于精确 GT-100 | 313 | **0.0738%** | 0.0751% / 0% / 0.4632% |
| 在同一搜索中稍后被 expanded | 341 | **0.0804%** | 0.0817% / 0% / 0.4675% |
| 属于最终 top-10 | 11 | **0.00259%** | 0.00263% / 0% / 0% |

三个指标都远低于任务中的问题存在阈值；即便只看“搜索后来确实需要了该节点”这一最直接的轨迹证据，也只有约 1/1,244 的 bonus 节点命中。

## 5. I/O 节省估计

若首次读到一个扇区时保留其全部五个节点槽，则之后对同一扇区中其他节点的显式读取可以省掉。基于原搜索轨迹的重放估计为：

- 原始显式节点/扇区读取：106,355。
- 不重复的扇区：106,014。
- 可由此前/同批次已读扇区覆盖的后续节点读取：341。
- 潜在读取减少：`341 / 106355 =` **0.3206%**。

每查询 I/O 节省率均值为 0.3190%，中位数 0%，P95 为 1.8357%，最大值 9.1743%。因此绝大多数查询没有可复用的同页节点；即使按理想化的“bonus 数据零成本保留”计算，汇总节省也远低于 10% PASS 阈值和 5% KILL 判据。

这是固定轨迹上的潜在节省估计：它准确计数原轨迹中能直接消除的重复扇区读取，但不模拟“把所有 bonus 立即加入候选集”后搜索路径可能发生的二阶变化。

## 6. Verdict

**KILL-NO-PROBLEM**。

合同判据是：GT-100 bonus 比例或 I/O 节省超过阈值则 PASS；若两者都低于 5% 则 KILL。本实验中：

- GT-100 bonus 比例：**0.0738% < 5%**；
- 估计 I/O 节省：**0.3206% < 5%**。

两个主要指标不仅低于 5%，而且分别比 5% 小约 68 倍和 16 倍。对该 R64/L100 SIFT1M 布局与搜索配置，没有证据表明为“免费同页节点扩展”增加搜索复杂度能带来有意义的导航或 I/O 收益。

## 7. 限制、偏差与复现信息

### 限制与计划偏差

1. 因任务允许在时间预算内缩减查询数，本实验使用原查询顺序的前 1,000 条，而非全部 10,000 条；这不是随机样本，可能存在顺序偏差。尽管如此，两个主指标距阈值很远，结论余量较大。
2. 只构建并评估一个 R64/L100 索引，未覆盖不同随机种子、R/L/beamwidth 或其他数据集。
3. A0 是离线轨迹重放，没有真正改变候选队列。I/O 估计假设已读同页节点可以保留且不计额外 CPU/内存，也不能捕获搜索路径改变带来的新增或减少读取。
4. `num_nodes_to_cache=0` 禁用了 DiskANN 节点缓存，但 SIFT1M 较小，OS page cache 仍可能影响延迟；本结论基于节点 ID/扇区关系和 I/O 次数，不依赖延迟。
5. 任务描述中的扇区内显式 node ID/`nnodes` 头并不存在于此版本的实际格式；分析器按索引头和 DiskANN `get_node_sector()` 的隐式映射实现，并抽查节点槽验证。
6. 原 DiskANN 工作树在实验开始前已有本地 system-BLAS 兼容性文件/改动（`CMakeLists.txt`、`src/CMakeLists.txt`、`include/mkl.h`、`src/lapack_compat.cpp`）。实验没有修改原仓库；追踪版从该工作树复制，因此复现应使用同一工作树状态，而不仅是提交哈希。

### 产物与校验

工作目录：`/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0/`

- 分析器：`scripts/analyze_page_bonus.py`
- 查询抽样：`scripts/prepare_query_sample.py`
- 独立 GT 抽查：`scripts/verify_gt_sample.py`
- 追踪源码副本：`DiskANN_trace/`
- 可复现的最小追踪补丁：`p07_trace.patch`
- expanded 轨迹：`traces/expanded_q1000.csv`
- 每查询明细：`results/per_query_bonus.csv`
- 机器可读汇总：`results/analysis_summary.json`
- 完整命令日志：`logs/`

关键 SHA-256：

```text
3a54e065feb6b924a6fe51f4b919e713648d4fede7c37b56758e0193be08f326  index/sift1m_disk.index
efb671a995d8f39c7de70c033318d744343fb78cfd39e665b43f8e37774c1c50  results/gt_1000_top100
958b32708f01661df3d82ecc2b404b0f308a546c66b840f3def4623e64d3ff92  traces/expanded_q1000.csv
9e3d9c4ee69e4bc2b86454c372f6bcc109e4707f92f5cfc1115f162d25179647  results/search_q1000_k10_100_idx_uint32.bin
840da18378a601e263291e62665b524fe4a34f524a84a2e208ea2aa22922f2d7  results/analysis_summary.json
```

### 精确复现命令

以下命令从工作目录执行。

```bash
# 0) 准备目录
mkdir -p index logs scripts traces results

# 1) 构建完整 SIFT1M R64 磁盘索引
/home/ubuntu/pz/VectorDB/repos/DiskANN/build/apps/build_disk_index \
  --data_type float --dist_fn l2 \
  --data_path /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin \
  --index_path_prefix "$PWD/index/sift1m" \
  -R 64 -L 100 --PQ_disk_bytes 0 --num_threads 8 \
  --search_DRAM_budget 4 --build_DRAM_budget 16

# 2) 生成保持原顺序的 1,000 查询样本
python3 scripts/prepare_query_sample.py \
  /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin \
  queries_1000.bin --count 1000

# 3) 精确 GT-100（该版本实际输出路径不自动追加 .bin）
OMP_NUM_THREADS=8 \
/home/ubuntu/pz/VectorDB/repos/DiskANN/build/apps/utils/compute_groundtruth \
  --data_type float --dist_fn l2 \
  --base_file /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin \
  --query_file "$PWD/queries_1000.bin" \
  --gt_file "$PWD/results/gt_1000_top100" --K 100

# 4) 复制源码、应用最小追踪补丁并构建追踪版
rsync -a --exclude build --exclude .git \
  /home/ubuntu/pz/VectorDB/repos/DiskANN/ "$PWD/DiskANN_trace/"
git -C DiskANN_trace apply "$PWD/p07_trace.patch"
cmake -S DiskANN_trace -B trace_build -DCMAKE_BUILD_TYPE=Release \
  -DDISKANN_USE_SYSTEM_BLAS=ON \
  -DDISKANN_BLAS_LIBRARY=/usr/lib/x86_64-linux-gnu/libblas.so.3 \
  -DDISKANN_LAPACK_LIBRARY=/usr/lib/x86_64-linux-gnu/liblapack.so.3 \
  -DDISKANN_USE_TCMALLOC=OFF
cmake --build trace_build --target search_disk_index -j8

# 5) 单线程、零节点缓存搜索并记录 expanded node IDs
rm -f "$PWD/traces/expanded_q1000.csv"
P07_TRACE_PATH="$PWD/traces/expanded_q1000.csv" \
"$PWD/trace_build/apps/search_disk_index" \
  --data_type float --dist_fn l2 \
  --index_path_prefix "$PWD/index/sift1m" \
  --result_path "$PWD/results/search_q1000_k10" \
  --query_file "$PWD/queries_1000.bin" \
  -K 10 -L 100 -W 2 --num_nodes_to_cache 0 --num_threads 1

# 6) 离线分析与验证
python3 scripts/analyze_page_bonus.py \
  --disk-index index/sift1m_disk.index \
  --base /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin \
  --queries queries_1000.bin --gt results/gt_1000_top100 \
  --results results/search_q1000_k10_100_idx_uint32.bin \
  --trace traces/expanded_q1000.csv \
  --json-out results/analysis_summary.json \
  --csv-out results/per_query_bonus.csv

python3 scripts/verify_gt_sample.py \
  --base /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin \
  --queries queries_1000.bin --gt results/gt_1000_top100 \
  --qids 0 499 999 --k 100
```
