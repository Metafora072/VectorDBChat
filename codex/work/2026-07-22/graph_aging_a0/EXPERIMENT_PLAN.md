# GraphAging / ReversibleANN A0 experiment plan

## Claim under test

For the same terminal active vector set, update history causes graph-ANN query quality or search cost to degrade beyond ordinary build-seed variance. If a strong IP-DiskANN path has no such aging, the direction is killed before implementing semi-coupled storage.

## Gates

1. Sanity: output parseable metrics and preserve the active set.
2. A0-1: reversible cycles at checkpoints 1/10/100.
3. Strong-baseline gate: official DiskANN3 `VisitedAndTopK` in-place deletion must show material aging; otherwise KILL.
4. A0-2: compare static and incremental histories only after forcing the same final degree cap.
5. A0-3/A0-4: run only as diagnostics if the phenomenon survives; do not build a full storage system.

Material aging is preregistered as Recall@10 loss at least 1 percentage point or search-work growth at least 5%, with the effect exceeding ordinary build-seed variation.

## Workloads

- SIFT1M, 128-dimensional float32, 10K queries, exact top-100 ground truth.
- PipeANN/OdinANN-style Vamana: R=64, Lbuild=Lsearch=96.
- Official Microsoft DiskANN3 commit `028d8d56abce91800bc7205a8115bee1940dbe7f`.
- CPU and ordinary NVMe only; no GPU.

## Early-stop rule

The full seven-history × multi-seed matrix, block-layer tracing, and semi-coupled implementation are skipped if the official strong-baseline gate fires. This is a scientific early stop, not missing follow-up work.
