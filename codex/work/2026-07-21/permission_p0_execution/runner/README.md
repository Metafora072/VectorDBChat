# P0 guarded runner

All commands write below:

`/home/ubuntu/pz/VectorDB/data/VectorDB/permission_aware_ssd_p0/r01`

The guard enforces the shared 4-hour, 24-GiB RSS and 10-GiB data limits, refuses writable file descriptors outside `/home/ubuntu/pz/VectorDB/data/`, and writes per-stage JSON status.

The exact commands are published in
`codex/share/2026-07-21/permission_aware_ssd_p0_execution_manifest_0721.md`.
All harness paths passed to a guarded child must be absolute because the guard
sets the working directory to the data-disk run root.

Example M0 invocation:

```bash
export RUN_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/permission_aware_ssd_p0/r01
export SOURCE_REPO=/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/src/PipeANN
export COMMIT=9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b
export DATASET_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/datasets/real/sift-128-euclidean
export HARNESS_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-21/permission_p0_execution

python3 "$HARNESS_ROOT/runner/run_guard.py" --run-root "$RUN_ROOT" --stage m0_identity_build -- \
  env RUN_ROOT="$RUN_ROOT" SOURCE_REPO="$SOURCE_REPO" COMMIT="$COMMIT" \
      DATASET_ROOT="$DATASET_ROOT" HARNESS_ROOT="$HARNESS_ROOT" \
      CCACHE_DISABLE=1 bash "$HARNESS_ROOT/runner/m0_identity_build.sh"
```

Do not enter M3 until Claude's machine-readable workload manifest has been committed and hashed into the run manifest.
