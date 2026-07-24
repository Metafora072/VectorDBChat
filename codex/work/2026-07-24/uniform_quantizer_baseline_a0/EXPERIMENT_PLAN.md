# UNIFORM-QUANTIZER-BASELINE-A0 Plan

**Status:** completed  
**Dataset:** GIST1M-960D  
**Data root:** `/home/ubuntu/pz/VectorDB/data/VectorDB/uniform_quantizer_baseline_a0_0724`

## Frozen comparison

```text
PQ32 / OPQ32 / PQ64 / OPQ64
× L={50,100,200,400,800}
× W=4, K=10, one thread, zero node cache
× full 1K queries
```

PQ32/PQ64 reuse the completed discovery results. OPQ32/64 use the same
100,000-row training matrix and the same byte-identical full-precision
R64/L100 graph. Only the in-memory navigation representation changes.

## OPQ implementation

The existing DiskANN source provides native `generate_opq_pivots` and
query-side rotation support:

- center the training/base vectors;
- learn a 960×960 orthogonal rotation for 20 OPQ iterations;
- learn 256 centroids per chunk;
- encode the original base vectors after centering and rotation;
- rotate each query immediately before ADC lookup-table construction.

The base vectors and graph are not rewritten. SSD node reads, final
full-vector reranking, node IDs, entry point, and graph topology remain
unchanged. Each OPQ prefix points to the existing shared graph.

Native k-means++ used `std::random_device`. The experiment adds an
opt-in `PQR_KMEANS_SEED=20260724` hook; behavior is unchanged when the
variable is absent.

## Milestones

1. M0: compile and verify native OPQ/frozen-graph path.
2. M1: train/code OPQ32 and OPQ64 from the shared sample.
3. M2: run a 200-query OPQ canary and audit artifacts.
4. M3: run two full multi-L repetitions per OPQ representation.
5. M3b: if any p50 or QPS drift exceeds 25%, run that complete
   representation a third time.
6. M4: compare complete Pareto frontiers and issue the frozen verdict.

## Budget

- OPQ training and code generation: estimated 35–70 minutes total.
- Canary and full search: estimated 20–35 minutes.
- Audit and report: estimated 15–25 minutes.
- Hard wall: 120 minutes for the automated OPQ pipeline.
- Peak RAM estimate: below 8 GiB.
- NVMe increment estimate: below 250 MB.
- GPU: 0.

## Hard stops

- graph SHA or realpath differs from the archived shared graph;
- OPQ requires rotating base data for graph construction;
- search bypasses the existing ADC or final-rerank path;
- rotation is not approximately orthogonal;
- query/result/GT row counts are inconsistent;
- automated run exceeds 120 minutes.

## Execution note

The native base-code generation path materialized several full 1M×960
buffers, so the measured peak was 12.4 GiB/process rather than the estimated
8 GiB. The initial automated pipeline reached its 120-minute wall during the
partial OPQ32 repeat 2. That partial output was isolated and excluded.

A search-only recovery then reran complete OPQ32/64 repeat 2 and, because the
25% stability gate triggered, complete repeat 3. No training, graph, query,
L/W/K, cache, thread, ADC, or rerank setting changed. Total experiment wall
time including the preregistered repeats was 129m43s.
