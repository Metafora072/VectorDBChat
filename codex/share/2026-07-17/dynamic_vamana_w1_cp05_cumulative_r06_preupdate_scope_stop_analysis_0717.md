# Dynamic Vamana W1 CP05 cumulative R06 pre-update scope stop analysis

**Date**: 2026-07-17 (UTC+8)

## Verdict

R06 stopped in `replay_DGAI` with `exit=1` before the CP01 input canary, stage scope or update API. The failure was a local shell-variable wiring defect: `primer` was declared inside `collect_stage()` but referenced inside `run_stage()` under `set -u`. It is not an index, query, resource, correctness or stage-I/O-primer failure.

Under Gpt's 15:34 authorization, this is a safe pre-update control-plane issue. R06 remains terminal and unmodified; the minimum recovery is a fresh R07 identity with the declaration moved into `run_stage()`.

## Accepted evidence and exact boundary

- immutable replay bases and static smoke revalidation: PASS;
- same-scope stage-I/O fixture: PASS;
- R06 execution preflight and evidence self-test: PASS;
- fresh DGAI replay clone: published under `sequential-cp80-06`;
- DGAI CP00 query gate: PASS, six points (`L64/L128 × 3`);
- last published state: CP00 read-only query manifests;
- CP01 input-canary directory: absent;
- update markers, `STAGE_WORKER_OK`, worker identity and stage evidence: absent;
- OdinANN replay, formal runs and DiskANN: not started;
- update API calls: zero.

Stop-time preservation is PASS with 91 checked identities and zero mismatch. Shared immutable bases, R03 inputs, GT, trace, historical results and other disks were not modified.

## Time and space

- Controller elapsed time: 27.118 seconds.
- R06 result allocated bytes: 647,168 B.
- R06 DGAI replay clone allocated bytes: 1,415,176,192 B.
- R06 tmp allocated bytes: 110,592 B.
- Project NVMe free bytes after stop: 1,318,002,843,648 B.
- MemAvailable after stop: 257,968,984,064 B.
- Root tmux and all R06 transient units exited.
- CP10/CP20 remain HOLD.
