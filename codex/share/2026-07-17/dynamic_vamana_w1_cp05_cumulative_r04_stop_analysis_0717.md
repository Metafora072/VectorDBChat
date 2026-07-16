# Dynamic Vamana W1 CP05 cumulative R04 stop analysis

**Date**: 2026-07-17 (UTC+8)

## Verdict

R04 correctly stopped in `replay_DGAI` with `exit=1`. The R03 canary-output defect is closed: the real `ubuntu` canary wrote its evidence under `stages/cp01/input_canary/`, read the current 16-record delta, received `EACCES` for both denied inputs, exited successfully, and no update marker existed.

The new stop is another narrow result-directory ownership error. The controller created the canary directory as `ubuntu:ubuntu/0700`, but its parent `stages/cp01/` and the attempt-result root remained `root:root/0755`. The ubuntu update service therefore could not create either:

- `stages/cp01/worker_identity.json`;
- `cp01_stage_resources.json`.

Both writes failed with `PermissionError: [Errno 13]`. The service stopped after 417 ms with a 5.9 MiB memory peak and zero device read/write bytes. It failed during worker precheck, before the DGAI driver or any update API was invoked.

## Accepted boundary

- R04 preflight and execution-manifest activation passed.
- Reused R03 formal/replay inputs, immutable bases, frozen static smoke, protected artifacts, binaries and shared query launcher all revalidated.
- DGAI replay CP00 `L64/L128 × 3` completed; all six outputs were `36×10`, all IDs were active, with diagnostic Recall@10 `0.9833/0.9917`.
- The R04 CP01 input canary passed as uid/gid 1000 and bound the exact allowed/denied paths.
- No `markers.jsonl`, `STAGE_WORKER_OK`, `stage_evidence.json`, checkpoint evidence or completion marker exists.
- Stop-time preservation is `pass`, 85 identities checked, zero mismatch.
- OdinANN replay, both SIFT10M formal systems and DiskANN did not start.

R04 is terminal and must not be continued or overwritten.

## Minimal proposed correction for a fresh identity

Before launching an update service, the controller should explicitly create the fresh attempt-result root and `stages/<checkpoint>/` as `ubuntu:ubuntu` (private or owner-writable), while retaining the already accepted `input_canary/` rule. This only grants the ubuntu query/update worker access to its new R05 result tree; it does not change the immutable base, R03 read-only inputs, formal clone ownership, denied-input list, query validator or experiment parameters.

The next launch should retain the two existing canary regressions and add no broader safety framework. Gpt should assign the fresh run/attempt identity and confirm reuse of the already PASS R04 preflight inputs versus recomputation.

## Time and space at stop

- Controller elapsed time: approximately 25.7 seconds.
- R04 result allocated bytes: 659,456 B.
- R04 DGAI replay clone allocated bytes: 1,415,172,096 B.
- R04 tmp allocated bytes: 81,920 B.
- Project NVMe `/dev/nvme8n1` (`259:10`) free bytes: 1,320,834,887,680 B.
- MemAvailable: 258,129,203,200 B.
- Root tmux and transient scopes exited; CP10/CP20 remain HOLD.

