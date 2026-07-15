# W1 canary driver contract

These are review artifacts, not applied source changes.  The existing dynamic
`overall_performance` executables are deliberately not reused for the W1
canary: DGAI merges synchronously after every update batch, while OdinANN exits
immediately after live probing and never calls `DynamicIndex::save`.

The reviewed follow-up binary names are `DGAI/tests/w1_canary` and
`OdinANN-uring/tests/w1_canary`.  Their source must preserve the current
insert/delete implementation and add only:

1. JSONL monotonic markers `clone_ready`, `index_loaded`, `ingest_begin`,
   `ingest_end`, `online_visibility_probe_begin`, `online_visibility_verified`,
   `publish_begin`, `publish_end`, `fresh_process_probe_begin`, and
   `fresh_process_visibility_verified` to `ATLAS_W1_MARKERS`.
2. A DGAI `online_visibility_supported=false` marker after API completion; its
   first valid visibility is post-`final_merge`/reload.  It must not infer a
   live-online rate.
3. An OdinANN live probe before `DynamicIndex::save`, then `save` followed by a
   wholly fresh `search_disk_index` process for restart visibility.
4. Calls to the reviewed result-ID serialization patches and the existing
   persisted `*_disk.index.tags` API; no raw internal-memory decoding.
5. Nonzero exit on failed insert/delete/save/reload/probe or result-ID write.

The driver source and binaries are intentionally not built or run in this
preparation-only change.  Their final patch and binary hashes are an explicit
execution-gate prerequisite.
