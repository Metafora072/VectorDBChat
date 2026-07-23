# PQ-RP-HIGHDIM-A0 Experiment Tracker

**State**: `STOP-CANARY`; full matrix and third repeat are forbidden by the frozen gate.

| Run ID | Milestone | Purpose | System / variant | Split | Metrics | Priority | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| R000 | M0 | provenance and shape audit | Cohere-1M-768D | all files | hashes, shapes, license | MUST | FAIL-FALLBACK | base max `abs(norm-1)=16.4741764`; no normalization or repair |
| R001 | M0 | independent GT/metric audit | Cohere exact CPU | six queries | top-100 overlap, norms | MUST | NOT-RUN-GATE | norm gate failed first |
| R002 | M0 | fallback validation | GIST1M-960D | local | hashes, GT audit | MUST-IF-FALLBACK | PASS | four hashes match; six exact top-100 sets 100/100; monotonic violations 0 |
| R010 | M1 | full graph | Vamana R64/L100 | selected 1M base | build time/RSS/hash | MUST | PASS | 8192004096B; SHA `52827694...`; 24:40; peak 12.2GiB |
| R011 | M1 | shared sample | deterministic 10% IDs | selected base | ID-list SHA256 | MUST | PASS | seed 20260724; ID SHA `44b57941...`; exactly 100000 rows |
| R012 | M1 | PQ artifacts | PQ16/32/64 | shared sample | residuals/bytes/hashes | MUST | PASS | same graph realpath; 16/32/64MB; residuals monotone |
| R020 | M2 | Canary | PQ32/PQ64/Exact | 200 queries | full metric set | MUST | FAIL-STOP | p50 drift: PQ32 L200 65.1%, Exact L200 28.1%; limit 25% |
| R030 | M3 | full frontier | PQ16/PQ32/PQ64/Exact | official 1K | full metric set | MUST | NOT-RUN-CANARY | no full runs and no third repeat |
| R040 | M4 | decision analysis | frozen B4 gates | all results | RP-memory frontier | MUST | NOT-ELIGIBLE | diagnostic matched-recall only; no GO/HOLD/KILL decision |
