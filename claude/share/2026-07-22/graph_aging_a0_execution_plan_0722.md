# GraphAging A0 实验执行计划

**Date:** 2026-07-22
**Author:** Claude
**Status:** 待 Codex 执行

---

## 前置条件（已就绪）

- **Binary:** `/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/graph_aging_a0/PipeANN/build-a0/tests/graph_aging_a0`
  - 已编译，支持 4 种模式：`build | a01 | path2 | path3`
  - 源码：`tests/graph_aging_a0.cpp`（414 行）
- **数据集:**
  - `full_1m.bin`: 1M × 128d float32（512 MB）
  - `query.bin`: 10K × 128d float32
  - `gt_cp00`: 10K × 100 NN（含距离）
  - 路径前缀：`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas`

---

## 执行步骤

### 环境变量

```bash
export BIN=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/graph_aging_a0/PipeANN/build-a0/tests/graph_aging_a0
export DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin
export QUERY=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin
export GT=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/groundtruth/sift1m/gt_cp00
export WORKDIR=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/graph_aging_a0
export RESULTDIR=$WORKDIR/results
export INDEXDIR=$WORKDIR/index
export THREADS=32

mkdir -p $RESULTDIR $INDEXDIR
```

### Step 0: 生成 sequential tag 文件（path2 需要）

```bash
python3 -c "
import struct, numpy as np
tags = np.arange(1000000, dtype=np.uint32)
with open('$INDEXDIR/sequential_tags_1m.bin', 'wb') as f:
    f.write(struct.pack('<II', 1000000, 1))
    tags.tofile(f)
print('Written sequential_tags_1m.bin')
"
```

### Step 1: 构建 5 个基准索引 G0（不同 build seed）

每个约 1-3 分钟。**可并行**（内存允许的话串行更安全，每个约 4-6 GB RSS）。

```bash
for SEED in 42 137 271 503 719; do
  echo "=== Building G0 with seed $SEED ==="
  $BIN build \
    --data $DATA --query $QUERY --gt $GT \
    --npoints 1000000 --R 64 --L 96 --search-L 96 \
    --nqueries 1000 --build-seed $SEED \
    --save-edges $INDEXDIR/g0_seed${SEED}.edges \
    --save-index $INDEXDIR/g0_seed${SEED}.index \
    --out $RESULTDIR/results.jsonl \
    --label "g0_seed${SEED}" \
    --threads $THREADS
done
```

**预期输出：** 5 行 JSON 写入 `results.jsonl`，每行包含 `recall_at_10`、`edge_count`、`distance_calcs_*` 等。

**预期 recall_at_10:** ≥ 0.95（SIFT1M, R=64, L=96 的标准水平）。

**如果 recall < 0.90**，检查 GT 格式是否匹配 `load_truthset`。

### Step 2: A0-1 插入—删除可逆循环（核心实验）

对每个 build seed × 3 个 update seed，执行 100 轮插入—删除循环。
- batch = 100K（10% of 1M）
- 每轮：插入 100K 向量副本（tag = 1M + original_tag）→ 删除副本 → consolidate
- checkpoints: 1, 10, 100

**预计时间：每组 (build_seed, update_seed) 约 20-40 分钟，共 15 组，总计 5-10 小时。**

**建议：先跑 1 组 pilot（seed=42, update_seed=1001），确认可行后再跑全部。**

```bash
# === PILOT: 先跑一组验证 ===
echo "=== A0-1 PILOT: seed=42, update_seed=1001 ==="
$BIN a01 \
  --index $INDEXDIR/g0_seed42.index \
  --data $DATA --query $QUERY --gt $GT \
  --batch 100000 --update-seed 1001 --build-seed 42 \
  --checkpoints 1,10,100 \
  --baseline-edges $INDEXDIR/g0_seed42.edges \
  --out $RESULTDIR/results.jsonl \
  --R 64 --L 96 --search-L 96 --nqueries 1000 \
  --threads $THREADS \
  --label "a01_b42_u1001"

# 检查 pilot 结果
echo "=== Pilot results ==="
grep "a01_b42" $RESULTDIR/results.jsonl | python3 -m json.tool
```

**Pilot PASS 条件：**
- 程序正常退出（exit code 0）
- 输出 3 行 JSON（checkpoint 1, 10, 100）
- recall_at_10 和 edge_jaccard 字段有合理值

**Pilot PASS 后，跑全部 15 组：**

```bash
for BSEED in 42 137 271 503 719; do
  for USEED in 1001 2002 3003; do
    # 跳过已跑的 pilot
    if [ "$BSEED" = "42" ] && [ "$USEED" = "1001" ]; then continue; fi
    echo "=== A0-1: build_seed=$BSEED, update_seed=$USEED ==="
    $BIN a01 \
      --index $INDEXDIR/g0_seed${BSEED}.index \
      --data $DATA --query $QUERY --gt $GT \
      --batch 100000 --update-seed $USEED --build-seed $BSEED \
      --checkpoints 1,10,100 \
      --baseline-edges $INDEXDIR/g0_seed${BSEED}.edges \
      --out $RESULTDIR/results.jsonl \
      --R 64 --L 96 --search-L 96 --nqueries 1000 \
      --threads $THREADS \
      --label "a01_b${BSEED}_u${USEED}"
  done
done
```

### Step 3: A0-2 同终态不同历史

两条路径到达同样的 1M 向量集合：

**Path 1 = Step 1 的静态构建**（已有结果）

**Path 2 = 增量构建：先 build 500K，再 insert 500K**

```bash
for SEED in 42 137 271 503 719; do
  echo "=== A0-2 Path2: seed=$SEED ==="
  $BIN path2 \
    --data $DATA --query $QUERY --gt $GT \
    --final-n 1000000 --initial-n 500000 \
    --full-tags $INDEXDIR/sequential_tags_1m.bin \
    --build-seed $SEED --update-seed $SEED \
    --baseline-edges $INDEXDIR/g0_seed${SEED}.edges \
    --out $RESULTDIR/results.jsonl \
    --R 64 --L 96 --search-L 96 --nqueries 1000 \
    --threads $THREADS \
    --label "path2_seed${SEED}" \
    --batch 100000
done
```

### Step 4: 结果汇总

```bash
python3 << 'PYEOF'
import json, sys
from collections import defaultdict

results = []
with open("$RESULTDIR/results.jsonl") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        results.append(json.loads(line))

# --- G0 baselines ---
g0 = [r for r in results if r["experiment"] == "static"]
print("=== G0 Baselines ===")
for r in g0:
    print(f"  {r['label']}: recall@10={r['recall_at_10']:.4f}, edges={r['edge_count']}, cmps_mean={r['distance_calcs_mean']:.1f}")

recalls = [r["recall_at_10"] for r in g0]
print(f"  Build-seed variance: min={min(recalls):.4f}, max={max(recalls):.4f}, range={max(recalls)-min(recalls):.4f}")

# --- A0-1: recall vs cycles ---
a01 = [r for r in results if r["experiment"] == "a0_1"]
print("\n=== A0-1: Insert-Delete Reversibility ===")
by_checkpoint = defaultdict(list)
for r in a01:
    by_checkpoint[r["checkpoint"]].append(r)

for cp in sorted(by_checkpoint.keys()):
    group = by_checkpoint[cp]
    recalls = [r["recall_at_10"] for r in group]
    jaccards = [r["edge_jaccard_vs_g0"] for r in group]
    print(f"  After {cp} cycles:")
    print(f"    recall@10: mean={sum(recalls)/len(recalls):.4f}, min={min(recalls):.4f}, max={max(recalls):.4f}")
    print(f"    jaccard:   mean={sum(jaccards)/len(jaccards):.4f}, min={min(jaccards):.4f}, max={max(jaccards):.4f}")

# --- A0-2: static vs path2 ---
path2 = [r for r in results if r["experiment"] == "a0_2"]
print("\n=== A0-2: Same Final State, Different History ===")
for r in path2:
    print(f"  {r['label']}: recall@10={r['recall_at_10']:.4f}, jaccard={r['edge_jaccard_vs_g0']:.4f}")

# --- KILL gate check ---
print("\n=== KILL Gate Evaluation ===")
if g0 and a01:
    g0_recall_range = max(r["recall_at_10"] for r in g0) - min(r["recall_at_10"] for r in g0)
    cp100 = [r for r in a01 if r["checkpoint"] == 100]
    if cp100:
        aging_drop = sum(r["recall_at_10"] for r in g0)/len(g0) - sum(r["recall_at_10"] for r in cp100)/len(cp100)
        print(f"  Build-seed recall range: {g0_recall_range:.4f}")
        print(f"  Aging-induced recall drop (100 cycles): {aging_drop:.4f}")
        if aging_drop < 0.01 and aging_drop < g0_recall_range:
            print(f"  >>> KILL-NO-PROBLEM: aging drop ({aging_drop:.4f}) < 1pp AND < build-seed variance ({g0_recall_range:.4f})")
        elif aging_drop >= 0.01:
            print(f"  >>> PASS: aging drop ({aging_drop:.4f}) >= 1pp, phenomenon is real")
        else:
            print(f"  >>> HOLD: aging drop ({aging_drop:.4f}) marginal, need more data")
PYEOF
```

---

## 结果输出

所有结果写入 **`$RESULTDIR/results.jsonl`**（每行一个 JSON record）。

最终报告写入 **`/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-22/graph_aging_a0_results_0722.md`**，包含：
1. 实验环境（commit, build config, 数据路径）
2. G0 baseline recall 和 build-seed variance
3. A0-1：recall@10 vs 循环次数（表格 + 趋势描述）
4. A0-2：static vs incremental 的性能差异
5. Edge Jaccard 变化趋势
6. **裁决：PASS / HOLD / KILL**（附 KILL gate 判定依据）

---

## 时间预算

| 步骤 | 预计时间 |
|------|----------|
| Step 0 (tags) | < 1 秒 |
| Step 1 (5× build) | 5-15 分钟 |
| Step 2 pilot | 20-40 分钟 |
| Step 2 full (14 组) | 4-9 小时 |
| Step 3 (5× path2) | 15-30 分钟 |
| Step 4 (汇总) | < 1 分钟 |
| **总计** | **5-10 小时** |

**建议分两轮执行：**
- **Round 1（1-2 小时）：** Step 0 + Step 1 + Step 2 pilot + Step 3 → 出初步判断
- **Round 2（4-9 小时）：** Step 2 full → 统计显著性

---

## 注意事项

1. **内存：** 每个 build/a01 进程约 4-6 GB RSS。不要并行跑多个。
2. **磁盘：** 每个索引 ~2-3 GB，5 个约 15 GB。确保 WORKDIR 有足够空间。
3. **GT 格式：** `gt_cp00` 是 PipeANN 标准格式（`[uint32 n][uint32 K]` + IDs + distances）。已验证兼容。
4. **如果 build 过程中 recall < 0.90：** 停止，检查 `load_truthset` 是否正确解析 GT。可能需要用 `--search-L 128` 或 `--search-L 200` 重试。
5. **如果 a01 中 consolidate 崩溃：** 报告错误信息。可能需要检查 `insert_point` 和 `lazy_delete` 的 tag 空间是否冲突。
6. **A0-1 的 batch=100000 如果太慢：** 可以先用 batch=10000（1%）做 quick pilot。
