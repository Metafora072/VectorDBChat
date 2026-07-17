# Dynamic Vamana W1 CP05 cumulative R05 stage-I/O baseline stop analysis

**Date**: 2026-07-17 (UTC+8)

## Verdict

R05 correctly stopped in `replay_DGAI` with `exit=1` after the first 16-record update completed but before stage evidence was accepted. The R04 ownership defect is closed: the ubuntu worker successfully wrote `worker_identity.json`, `cp01_stage_resources.json`, all update markers, active-set audit, fresh probe and `STAGE_WORKER_OK`.

The failing gate was `w1_collect_canary.py`: `ValueError: phase has no bracketing cgroup I/O samples`. This is an update-scope I/O-baseline issue, not an update execution failure.

## Exact evidence gap

The stage resource probe sampled every 25 ms and retained 164 samples. Its cgroup did not expose device `259:10` until the first real update I/O occurred:

- `ingest_begin`: monotonic ns `2326393103910399`;
- first `259:10` sample: `2326393185640131`, already containing 7,241,728 read bytes and 270,336 write bytes;
- `ingest_end`: `2326393193403984`.

There is therefore no device sample at or before `ingest_begin`. The strict collector cannot compute an ingest phase delta without silently omitting the initial I/O, and correctly refuses the evidence. The validator was not relaxed.

This is the update analogue of the previously fixed query-scope baseline issue. A fresh attempt would need a same-scope, pre-resource-baseline device primer, so `259:10` exists before `resource_probe` starts and the primer itself is excluded from stage deltas.

## Update execution boundary

The DGAI 16-record replay update itself exited successfully:

- service return code: 0;
- service runtime: 4.176 s;
- resource-probe elapsed time: 4.077797 s;
- worker identity: PASS, 16 incremental replacements / 32 primitive mutations;
- active-set exact audit: valid;
- fresh visibility probes: 36/36 valid;
- `STAGE_WORKER_OK`: present;
- resource peak process-tree RSS: 2,117,176 KiB;
- process-tree I/O totals observed: 1,113,554,944 read bytes / 600,989,696 write bytes;
- cgroup OOM, oom_kill and oom_group_kill: all zero.

These raw values prove the update ran and correctness probes passed, but they are not accepted stage-performance evidence because ingest I/O lacks a bracketing baseline. No CP01 query/checkpoint evidence was published, and no CP05 replay, OdinANN replay, SIFT10M formal or DiskANN stage began.

R05 is terminal and must not be continued or overwritten. Because an update API ran and the private R05 clone changed, the next identity requires Gpt review under the explicit R05 authorization boundary.

## Preservation, time and space

- Controller elapsed time: approximately 31.4 seconds.
- Stop-time preservation: PASS, 89 checked identities, zero mismatch.
- R05 result allocated bytes: 839,680 B.
- R05 DGAI replay clone allocated bytes: 1,415,172,096 B.
- R05 tmp allocated bytes: 81,920 B.
- Project NVMe free bytes: 1,319,418,785,792 B.
- MemAvailable: 258,316,046,336 B.
- Root tmux and all R05 transient units exited.
- Shared immutable bases, R03 inputs, GT, trace, historical results and other disks were not modified.
- CP10/CP20 remain HOLD.

