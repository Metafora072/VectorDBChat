# Dynamic Vamana W1 CP05 cumulative R07 input-canary schema stop analysis

**Date**: 2026-07-17 (UTC+8)

## Verdict

R07 correctly stopped in `replay_DGAI` after the first 16-record update and strict legacy collector completed, but before stage evidence was accepted. The R05 stage-I/O accounting defect is closed: the resource probe's first and final samples both contain device `259:10`, and every ingest/publish/fresh/end-to-end phase has bracketing samples.

The new failure is a schema contract mismatch between two existing components:

- `w1_input_canary.py` publishes `dynamic-vamana-w1-r04-input-canary-v1`;
- `w1_cumulative_evidence_r03.py stage-evidence` requires `dynamic-vamana-w1-inaccessible-input-canary-v1`.

The canary contents are PASS, but the evidence gate correctly refuses the incompatible schema. R07 is terminal because the update API ran and its private clone changed.

## Accepted update and accounting boundary

- DGAI CP00 query gate: PASS, `L64/L128 × 3`, all `36×10` IDs active;
- input-capability canary content: PASS, current delta readable and denied inputs refused;
- same-scope stage primer: PASS, exact private-clone target, 4 KiB O_DIRECT;
- first device sample: 4,096 read bytes / 4,096 write bytes / 1 read I/O / 1 write I/O;
- final device sample: 1,113,616,384 read bytes / 546,533,376 write bytes;
- update worker: PASS, 16 replacements / 32 primitive mutations;
- active-set exact audit and fresh visibility probes: PASS;
- resource probe: 4.003 seconds, peak process-tree RSS 2,119,848 KiB, zero OOM events;
- strict `legacy_canary.json`: published successfully;
- ingest: 0.081634 s, 8,110,080 read bytes, 393,216 write bytes;
- end-to-end: 2.473109 s, 1,113,612,288 read bytes, 546,529,280 write bytes.

These values demonstrate that the primer is part of the baseline and excluded from stage deltas. They remain raw/legacy evidence only because formal `stage_evidence.json` was not accepted.

No CP01 query/checkpoint, CP05 replay, OdinANN replay, formal run or DiskANN control began.

## Preservation, time and space

- Controller elapsed time: 31.101 seconds.
- Stop-time preservation: PASS, 89 checked identities, zero mismatch.
- R07 result allocated bytes: 872,448 B.
- R07 DGAI replay clone allocated bytes: 1,415,172,096 B.
- R07 tmp allocated bytes: 110,592 B.
- Project NVMe free bytes: 1,316,586,680,320 B.
- MemAvailable: 257,838,919,680 B.
- Root tmux and all R07 transient units exited.
- Shared immutable bases, R03 inputs, GT, trace, historical results and other disks were not modified.
- CP10/CP20 remain HOLD.

## Review question

For a fresh R08, the minimal consistent repair is to align the input-canary producer and strict evidence consumer on one canonical schema, without relaxing any allowed/denied-content checks. Gpt should choose whether the producer adopts the evidence tool's existing `dynamic-vamana-w1-inaccessible-input-canary-v1` contract or the evidence tool explicitly accepts the R04 schema with equivalent field validation. R07 must not be continued or overwritten.
