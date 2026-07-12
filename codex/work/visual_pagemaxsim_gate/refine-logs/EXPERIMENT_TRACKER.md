# Residual Multi-Ball Stage A Tracker

| Run | Milestone | Configuration | Status | Notes |
|---|---|---|---|---|
| SA-S0 | Encoder sanity | 2 disjoint pages, skip=64, queries=0 | DONE | IDs disjoint; 16.5 s/batch |
| SA-S1 | Harness sanity | K=2, 4 test docs, 2 train docs | DONE | A0/A1/A2 outputs valid; zero violations |
| SA-D0 | Training embeddings | 256 disjoint ViDoRe pages, ColQwen2 BF16 CPU | DONE | 33 min; data/cache only on project NVMe |
| SA-A0 | Exact envelope | raw/f9 int8, K=64/256 | DONE / PASS | f9 K64: 95.1 → 76.0 pages |
| SA-A1 | Residual certificate | raw/f9 int8, K=64/256 | DONE / CLOSE | All configurations read 100%; zero violations |
| SA-A2 | Full cost | persistent/DRAM/query state/CPU/crossover | SKIPPED-BY-GATE | A1 did not skip a page; diagnostic counters retained only |
| SA-B | K=1024 | conditional | NOT AUTHORIZED | K64→256 not monotonic and f9 skipping absent |
| P3 | SSD replay | — | NOT AUTHORIZED | Never run in Stage A |
