# Reproduction Runbook

The large artifacts live under:

`/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_ssd_maintenance_p0_0722/`

The PipeANN source baseline is `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`. Apply `patches/pipeann_dynamic_ssd_canary.patch`, then configure two builds:

```bash
CCACHE_DIR=/tmp/dynamic_ssd_ccache cmake -S . -B build-canary -DUSE_TCMALLOC=OFF -DIO_ENGINE=aio -DCMAKE_BUILD_TYPE=Release
CCACHE_DIR=/tmp/dynamic_ssd_ccache cmake --build build-canary --target dynamic_ssd_canary build_disk_index compute_groundtruth -j8
ADDITIONAL_DEFINITIONS=-DIN_PLACE_RECORD_UPDATE CCACHE_DIR=/tmp/dynamic_ssd_ccache cmake -S . -B build-canary-inplace -DUSE_TCMALLOC=OFF -DIO_ENGINE=aio -DCMAKE_BUILD_TYPE=Release
CCACHE_DIR=/tmp/dynamic_ssd_ccache cmake --build build-canary-inplace --target dynamic_ssd_canary -j8
```

Driver modes encode the exact argument contract:

```text
search LABEL PREFIX QUERY GT NQ OUT
insert_search LABEL PREFIX QUERY GT DATA START COUNT FIRST_TAG NQ OUT
churn_search LABEL PREFIX QUERY GT DATA START COUNT FIRST_TAG DELETE_TAGS NQ OUT
tombstone_search LABEL PREFIX QUERY GT DELETE_TAGS COUNT NQ OUT
merge_search LABEL PREFIX QUERY GT DELETE_TAGS COUNT NQ OUT MERGE_PREFIX
```

Data preparation is deterministic:

```bash
python3 prepare_canary_data.py --source /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin --output-dir /home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_ssd_maintenance_p0_0722/data --seed 20260722 --delete-count 100000 --noise-sigma 0.01
```

All states use R=64, Lbuild=96, Lsearch=96, PQ=32 and the first 1000 queries. Start each B variant from an independent copy/reflink of the same 900K static prefix. Start each C search from the same immutable S0 prefix. Finally run:

```bash
python3 analyze_canary.py
```

Raw command contracts and immutable hashes in the main report are sufficient to reconstruct every JSONL row; build/update logs retained in `logs/` document the long A runs.
