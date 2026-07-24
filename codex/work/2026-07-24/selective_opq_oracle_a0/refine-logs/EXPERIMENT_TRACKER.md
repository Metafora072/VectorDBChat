# Experiment Tracker

**Status:** `APPROVED-STAGE-A / STAGE-B-BLOCKED`

Stage A is approved. Stage B requires Stage-A result review and a second
explicit approval.

| Run ID | Stage | Purpose | System / Variant | Metrics | Status | Notes |
|---|---|---|---|---|---|---|
| A001 | A | frozen artifact audit | OPQ32/64 + graph/query/GT/train IDs | hashes, shapes | DONE | all frozen hashes/shapes pass |
| A002 | A | trace instrumentation canary | per-L node + boundary events | parity, event schema | DONE | endpoint parity passed; 1K records at every L |
| A003 | A | uniform payload controls | OPQ40/48/56 | artifact audit | DONE | chunks, rotations, codes, graph links and RAM cap pass |
| A004 | A | build per-L controls | RANDOM/VISIT-FREQUENCY | cardinality, ties | DONE | exact H at all 15 budget/L pairs; seed 20260724 |
| A005 | A | build distance selector | DISTANCE-REGRET × 5 L | score, exact top-H | DONE | independent frozen trace per L |
| A006 | A | build routing selector | ROUTING-AWARE × 5 L | inversion score, top-H | DONE | independent frozen boundary pairs per L |
| A007 | A | uniform algorithmic frontier | OPQ40/48/56 × 5 L | Recall, reads, comparisons | IN-PROGRESS | one deterministic pass |
| A008 | A | mixed algorithmic gate | 3 budgets × 4 selectors × 5 L | Recall, reads, comparisons | TODO | dual-dense adapter; no system claim |
| A009 | A | Stage-A verdict | selector-specific + combined gate | PASS/HOLD/KILL | TODO | Stage B never auto-starts |
| B001 | B | actual-memory guards | OPQ45/53/61 | artifact audit | BLOCKED-STAGE-A | needs second approval |
| B002 | B | compact layout | low/high/tag/rank | bytes, rank parity | BLOCKED-STAGE-A | exhaustive 1M audit |
| B003 | B | endpoint correctness | all-low/all-high compact | ADC/search parity | BLOCKED-STAGE-A | abs error ≤1e-5 |
| B004 | B | 1M algorithmic gate | positive mixed vs OPQ45/53/61 | Recall, reads, comparisons | BLOCKED-STAGE-A | actual allocated bytes |
| B005 | B | system repeat 1 | positive compact configurations | QPS, p50, p99, preprocessing | BLOCKED-STAGE-A | interleaved |
| B006 | B | system repeat 2 | positive compact configurations | QPS, p50, p99, preprocessing | BLOCKED-STAGE-A | no third repeat |
| B007 | B | final verdict | actual-memory + scale view | PASS/HOLD/KILL | BLOCKED-STAGE-A | system-only failure cannot direction-KILL |
