# Dynamic Vamana Atlas preparation utilities

This directory contains the deterministic data/trace and exact-GT utilities used by the approved preparation stage. Large outputs are written only under:

`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas`

`prepare_dataset.py` creates a logical corpus, an 80% initial active set, a 20% never-active insert pool, replace-new checkpoints at 0/5/10/20%, tag files, a 100-operation update smoke trace, and a same-vector API control. `--full-name` keeps the retained full-corpus filename explicit for both 1M and 10M datasets. `prepare_update_smoke.py` reads that manifest field. `compute_exact_gt.sh` recomputes tag-level L2 top-100 ground truth for every checkpoint, or for the explicit `ATLAS_CHECKPOINTS` subset; `validate_groundtruth.py` provides the corresponding `--checkpoints` subset and an independent NumPy brute-force audit. `hash_manifest.py` records byte length and SHA256 for every retained dataset artifact.

`run_build_smoke.sh`, `run_query_smoke.sh`, and `run_dynamic_smoke.sh` are the replay entry points. The dynamic runner always copies a static index into an independent attempt directory before mutation and accepts `ATLAS_TRACE_KIND=replace_new` (default) or `same_vector`. `resource_probe.py` samples the process tree, `smaps_rollup`, cgroup v2 counters, page-cache movement, and apparent/allocated index space. The `manifests/` directory contains compact, reviewable evidence; full logs and large indexes remain on the project NVMe path above.

The approved three-system SIFT10M Pilot preparation is in `prepare_sift10m.sh`, `validate_sift10m.sh`, and `formal/`. The scripts deliberately have no default download URL: the operator must provide a licensed standard BIGANN source through `SIFT10M_BASE_INPUT`/`SIFT10M_QUERY_INPUT` or the matching explicit URLs. All writes, including `TMPDIR`, are rejected unless they are under the experiment NVMe root. `formal/f0_{diskann,dgai,odinann}.sh` require an already prepared and checkpoint-0-validated dataset, check the exact commits and allowed patch hashes, create a dedicated root-managed systemd cgroup scope, bind NUMA/CPU, collect cgroup/RSS/device-I/O/SSD evidence, and preserve failed attempts rather than overwriting them. They are P0 review artifacts only until GPT/Claude approve a launch.

The 1M numbers are readiness evidence only. They must not be used as a formal cross-system ranking.
