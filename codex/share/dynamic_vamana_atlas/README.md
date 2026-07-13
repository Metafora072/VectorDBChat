# Dynamic Vamana Atlas preparation utilities

This directory contains the deterministic data/trace and exact-GT utilities used by the approved preparation stage. Large outputs are written only under:

`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas`

`prepare_dataset.py` creates a 1M logical corpus, an 80% initial active set, a 20% never-active insert pool, replace-new checkpoints at 0/5/10/20%, tag files, a 100-operation update smoke trace, and a same-vector API control. `prepare_update_smoke.py` materializes the binary update traces and the 100-op active set. `compute_exact_gt.sh` recomputes tag-level L2 top-100 ground truth for every checkpoint, while `validate_groundtruth.py` adds structural checks and an independent NumPy brute-force audit. `hash_manifest.py` records byte length and SHA256 for every retained dataset artifact.

`run_build_smoke.sh`, `run_query_smoke.sh`, and `run_dynamic_smoke.sh` are the replay entry points. The dynamic runner always copies a static index into an independent attempt directory before mutation and accepts `ATLAS_TRACE_KIND=replace_new` (default) or `same_vector`. `resource_probe.py` samples the process tree, `smaps_rollup`, cgroup v2 counters, page-cache movement, and apparent/allocated index space. The `manifests/` directory contains compact, reviewable evidence; full logs and large indexes remain on the project NVMe path above.

The 1M numbers are readiness evidence only. They must not be used as a formal cross-system ranking.
