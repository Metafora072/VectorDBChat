# PQ-RP-HIGHDIM-A0 Experiment Tracker

**State**: `WAITING-FOR-GPT-APPROVAL`; no data download, build, PQ training, or search has started.

| Run ID | Milestone | Purpose | System / variant | Split | Metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| R000 | M0 | provenance and shape audit | Cohere-1M-768D | all files | hashes, shapes, license | MUST | BLOCKED-APPROVAL | no download yet |
| R001 | M0 | independent GT/metric audit | Cohere exact CPU | six queries | top-100 overlap, norms | MUST | BLOCKED-APPROVAL | fallback on any failure |
| R002 | M0 | fallback validation | GIST1M-960D | local | hashes, GT audit | MUST-IF-FALLBACK | READY-LOCAL | no execution authorized |
| R010 | M1 | full graph | Vamana R64/L100 | selected 1M base | build time/RSS/hash | MUST | BLOCKED-APPROVAL | one graph only |
| R011 | M1 | shared sample | deterministic 10% IDs | selected base | ID-list SHA256 | MUST | BLOCKED-APPROVAL | reused by all PQ codes |
| R012 | M1 | PQ artifacts | PQ16/32/64 | shared sample | residuals/bytes/hashes | MUST | BLOCKED-APPROVAL | ordinary PQ only |
| R020 | M2 | Canary | PQ32/PQ64/Exact | 200 queries | full metric set | MUST | BLOCKED-APPROVAL | L=100/200/400/800, 2 repeats |
| R030 | M3 | full frontier | PQ16/PQ32/PQ64/Exact | official 1K | full metric set | MUST | BLOCKED-CANARY | L=50/100/200/400/800, 2 repeats |
| R040 | M4 | decision analysis | frozen B4 gates | all results | RP-memory frontier | MUST | BLOCKED-FULL | no method implementation |
