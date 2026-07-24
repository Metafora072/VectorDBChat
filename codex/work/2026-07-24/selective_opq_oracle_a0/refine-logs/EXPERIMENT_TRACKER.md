# Experiment Tracker

**Status:** `PLAN-ONLY / WAITING-FOR-GPT-APPROVAL`

No row may move from `BLOCKED` before explicit GPT approval.

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| R001 | M0 | chunk/layout unit audit | OPQ40/48/56 + rank layout | synthetic + frozen metadata | offsets, ranks, bytes | MUST | BLOCKED | no training/search |
| R002 | M0 | endpoint parity | all-low/all-high mixed | canary queries | ADC/search parity | MUST | BLOCKED | requires implementation approval |
| R003 | M1 | uniform payload controls | OPQ40/48/56 | frozen GIST train/base | artifact audit | MUST | BLOCKED | own rotation/codebook |
| R004 | M1 | equal-memory guards | OPQ45/53/61 | frozen GIST train/base | artifact audit | MUST | BLOCKED | nearest stronger actual bytes |
| R005 | M2 | trace generation | OPQ32 ∪ OPQ64 events | 1K queries × 5 L | event/error trace | MUST | BLOCKED | test-conditioned feasibility only |
| R006 | M2 | selector build | random/visit/trace-conditioned | full trace | cardinality, objective | MUST | BLOCKED | top-H exact only for modular objective |
| R007 | M3 | uniform frontier repeat 1 | OPQ32/40/45/48/53/56/61/64 | 1K × 5 L | all gate metrics | MUST | BLOCKED | interleaved |
| R008 | M3 | mixed frontier repeat 1 | 3 budgets × 3 selectors | 1K × 5 L | all gate metrics | MUST | BLOCKED | dual preprocessing charged |
| R009 | M3 | uniform frontier repeat 2 | OPQ32/40/45/48/53/56/61/64 | 1K × 5 L | all gate metrics | MUST | BLOCKED | no third repeat |
| R010 | M3 | mixed frontier repeat 2 | 3 budgets × 3 selectors | 1K × 5 L | all gate metrics | MUST | BLOCKED | no third repeat |
| R011 | M4 | verdict | equal-memory Pareto audit | raw repeats | PASS/KILL | MUST | BLOCKED | means cannot rescue failed repeat |
