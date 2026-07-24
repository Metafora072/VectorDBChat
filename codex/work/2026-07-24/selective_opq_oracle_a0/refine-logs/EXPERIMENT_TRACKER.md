# Experiment Tracker

**Status:** `PLAN-ONLY / WAITING-FOR-GPT-APPROVAL`

No row may leave `BLOCKED` before explicit approval. Stage B additionally
requires a positive Stage-A verdict and a second approval.

| Run ID | Stage | Purpose | System / Variant | Metrics | Status | Notes |
|---|---|---|---|---|---|---|
| A001 | A | frozen artifact audit | OPQ32/64 + graph/query/GT/train IDs | hashes, shapes | BLOCKED | no training/search |
| A002 | A | trace instrumentation canary | per-L node + boundary events | parity, event schema | BLOCKED | no cross-L scores |
| A003 | A | uniform payload controls | OPQ40/48/56 | artifact audit | BLOCKED | only Stage-A training |
| A004 | A | build per-L controls | RANDOM/VISIT-FREQUENCY | cardinality, ties | BLOCKED | seed 20260724 |
| A005 | A | build distance selector | DISTANCE-REGRET × 5 L | score, exact top-H | BLOCKED | surrogate-specific |
| A006 | A | build routing selector | ROUTING-AWARE × 5 L | inversion score, top-H | BLOCKED | frozen boundary pairs |
| A007 | A | uniform algorithmic frontier | OPQ40/48/56 × 5 L | Recall, reads, comparisons | BLOCKED | one deterministic pass |
| A008 | A | mixed algorithmic gate | 3 budgets × 4 selectors × 5 L | Recall, reads, comparisons | BLOCKED | dual-dense adapter; no system claim |
| A009 | A | Stage-A verdict | selector-specific + combined gate | GO/HOLD/KILL | BLOCKED | Stage B never auto-starts |
| B001 | B | actual-memory guards | OPQ45/53/61 | artifact audit | BLOCKED-STAGE-A | needs second approval |
| B002 | B | compact layout | low/high/tag/rank | bytes, rank parity | BLOCKED-STAGE-A | exhaustive 1M audit |
| B003 | B | endpoint correctness | all-low/all-high compact | ADC/search parity | BLOCKED-STAGE-A | abs error ≤1e-5 |
| B004 | B | 1M algorithmic gate | positive mixed vs OPQ45/53/61 | Recall, reads, comparisons | BLOCKED-STAGE-A | actual allocated bytes |
| B005 | B | system repeat 1 | positive compact configurations | QPS, p50, p99, preprocessing | BLOCKED-STAGE-A | interleaved |
| B006 | B | system repeat 2 | positive compact configurations | QPS, p50, p99, preprocessing | BLOCKED-STAGE-A | no third repeat |
| B007 | B | final verdict | actual-memory + scale view | PASS/HOLD/KILL | BLOCKED-STAGE-A | system-only failure cannot direction-KILL |
