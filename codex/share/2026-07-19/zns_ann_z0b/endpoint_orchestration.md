# Z0B endpoint orchestration (implementation status)

Status at implementation time: **dry-run/audit only; no formal FULL trace has
been started**.  All operational timestamps are emitted in both UTC and UTC+8.
Sequence replay never consumes those timestamps.

## Frozen campaign

- build: `zns-ann-z0b-endpoint-v1-r05` only; the prelaunch gate hashes the
  tracer and both system binaries;
- capture interposition: r05 `libz0btrace.so` followed by the frozen M3
  `libm0write.so`; both are SHA-256 pinned.  Normalization closes against the
  tracer ledger, while the M0 profile is independently required to match its
  accepted request count and requested bytes exactly;
- inputs: DGAI 50K and OdinANN 400K only;
- realizations: three independently cloned, independently captured FULL traces
  per system/endpoint, six traces total;
- storage: Atlas NVMe8 (`MAJ:MIN=259:10`) only;
- reuse/retry: forbidden; the controller stops the entire campaign after the
  first failed stage;
- corrected guarded peak: 128.360 GiB; registered as 129 GiB; launch requires
  `free >= 193.5 GiB` and `registered peak <= 150 GiB`.

## Safe read-only commands

```bash
cd /home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-19/zns_ann_z0b
python3 prelaunch_gate.py --mode audit
python3 prepare_endpoints.py
python3 run_endpoints.py
python3 status_endpoints.py
python3 status_endpoints.py --json
```

The first three commands above are non-mutating audits/plans unless the caller
adds `--execute`.  Formal preparation and execution additionally require exact
acknowledgement environment variables embedded in the scripts.  The native
compact toolchain lock is a hard dependency: until every artifact exists and
matches its locked SHA-256, `launch_ready` remains false.

## Formal stage markers

Each attempt advances monotonically through `PREPARED_OK`, `RUN_STARTED`,
`CAPTURE_OK`, `NORMALIZED_OK`, `CLOSURE_OK`, `REPLAY_OK`, `REFERENCE_OK`, and
`Z0B_RUN_OK`.  `FAILED.json` is terminal.  `status_endpoints.py` reports both
whole-trace completion and operational-stage completion; neither is presented
as a time percentage.  Before the native benchmark is closed, ETA is reported
as a conservative range and explicitly labelled provisional.

No expanded initial-page JSONL, payload image, or expanded replay specification
is permitted.  Initial/final manifests, lifecycle and simulator inputs remain
compact binary artifacts; all temporary/output paths live below the NVMe
campaign root.
