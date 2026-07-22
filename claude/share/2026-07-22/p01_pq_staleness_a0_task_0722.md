# P01 A0: PQ Codebook Staleness After Dynamic Updates

## Goal

Measure whether PQ codebooks trained at build time become stale after dynamic insertions, causing systematically higher quantization error for new vectors and biased search recall.

## Experiment Design

### Setup
- Dataset: SIFT1M (128d float32, L2)
- Data path: `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin`
- Query: `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin`
- System: DiskANN (upstream, not PipeANN) at `/home/ubuntu/pz/VectorDB/repos/DiskANN`
- Build dir: `/home/ubuntu/pz/VectorDB/repos/DiskANN/build`

### Protocol

**Step 1: Split data**
- Take full_1m.bin (1M vectors, 128d float32, DiskANN .bin format: 4-byte npts + 4-byte ndim header)
- Split into BUILD set (first 700K) and INSERT set (remaining 300K)
- Write them as separate .bin files

**Step 2: Build disk index on BUILD set**
```
./build_disk_index --data_type float --dist_fn l2 \
  --data_path <build_700k.bin> \
  --index_path_prefix <output_dir>/sift700k \
  -R 64 -L 100 --PQ_disk_bytes 0 \
  --num_threads 8 --search_DRAM_budget 4 --build_DRAM_budget 16
```
This trains PQ codebooks on the 700K build set.

**Step 3: Measure PQ reconstruction error**

Write a C++ tool (or Python using the PQ pivots file) that:
1. Loads the PQ pivots file (`sift700k_pq_pivots.bin`) and PQ compressed data (`sift700k_pq_compressed.bin`)
2. For each vector in BUILD set: compute PQ reconstruction, measure L2 error = ||x - PQ(x)||²
3. For each vector in INSERT set: encode with same codebook, compute PQ reconstruction, measure L2 error
4. Report: mean/median/p95 PQ error for BUILD vs INSERT vectors
5. Also report per-chunk error breakdown if possible

**Step 4: Search quality by NN age**

1. Load the disk index built on 700K
2. Use `test_streaming_scenario` or write a driver that:
   - Inserts the 300K vectors dynamically
   - Runs queries
   - For each query, tags each true NN as "old" (in build set) or "new" (in insert set)
   - Reports recall separately for old-NN queries and new-NN queries
3. If `test_streaming_scenario` doesn't support this, use `search_disk_index` before and after insert, and compute GT for each query noting which GTs are old vs new

**Simplified Alternative (if dynamic insert is too complex):**

Instead of dynamic insert on disk index, do the following:
1. Build memory index (`build_memory_index`) on 700K
2. Insert 300K vectors into the memory index
3. Search with the index
4. Compute PQ error separately for old (tag < 700K) and new (tag >= 700K) vectors
5. This tests the PQ staleness hypothesis without disk index complexity

Even simpler: just measure PQ reconstruction error (Step 3) without search. If PQ error for INSERT set is NOT significantly higher than BUILD set, the phenomenon doesn't exist and we KILL.

### Key Files
- PQ pivots: generated during `build_disk_index`, saved as `*_pq_pivots.bin`
- PQ compressed: saved as `*_pq_compressed.bin`
- PQ table code: `include/pq.h` — `FixedChunkPQTable::inflate_vector()` reconstructs from PQ codes
- PQ generation: `src/pq.cpp` — `generate_pq_pivots()` trains codebook, `generate_pq_data_from_pivots()` encodes vectors
- Existing PQ tools: `apps/utils/generate_pq.cpp`

### Metrics

| Metric | PASS threshold | KILL threshold |
|--------|---------------|---------------|
| Mean PQ error ratio (new/old) | >1.10 (10% higher) | <1.05 |
| Recall@10 for new-NN queries vs old-NN | >1pp lower | <0.5pp difference |

### PASS / KILL

- **PASS-PROBLEM**: PQ error for INSERT vectors is >10% higher than BUILD vectors AND recall for new-NN queries is measurably lower
- **HOLD**: PQ error difference is 5-10% but recall difference is ambiguous
- **KILL-NO-PROBLEM**: PQ error difference <5%, no recall difference

### Output

Write results to: `/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-22/p01_pq_staleness_a0_results_0722.md`

Include:
1. Data split sizes and confirmation
2. PQ error statistics table (mean/median/p95 for old vs new)
3. Per-chunk error if computed
4. Search recall by NN age (if computed)
5. Final verdict: PASS-PROBLEM / HOLD / KILL-NO-PROBLEM
6. Any anomalies or unexpected observations

### Time Budget
2-3 hours max. If dynamic insert proves too complex, fall back to PQ-error-only measurement.

### Important Notes
- SIFT1M vectors are naturally ordered by some image feature extraction order. The split at 700K may or may not create distribution shift. If no natural shift exists, the experiment will show the KILL case (PQ error is similar for both sets) — this is a valid result.
- The key insight to test: PQ codebook optimized for 700K vectors may not be optimal for the remaining 300K.
- If using `generate_pq` tool, you can generate PQ codes for the INSERT set using the BUILD set's pivots.
