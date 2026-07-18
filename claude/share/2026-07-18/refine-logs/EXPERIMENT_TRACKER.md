# Experiment Tracker

| Block | Run | Status | WA | Notes |
|-------|-----|--------|-----|-------|
| B2 | Descriptive stats (DGAI 50K) | NOT_STARTED | — | Gini=0.035 (from M2 data) |
| B2 | Descriptive stats (OdinANN 50K) | NOT_STARTED | — | Gini=0.161 |
| B2 | Descriptive stats (DGAI 400K) | NOT_STARTED | — | Gini=0.268 |
| B2 | Descriptive stats (OdinANN 400K) | NOT_STARTED | — | Gini=0.290 |
| B1 | Full sweep (256 runs) | NOT_STARTED | — | Depends on re-instrumented traces |
| B3 | Controlled transformation (14 runs) | NOT_STARTED | — | Depends on simulator |
| B4 | FEMU validation (3 points) | NOT_STARTED | — | Depends on FEMU setup |

## Pre-existing Data (from M0-M3)
- [x] Page version count distributions (all 4 system×scale points)
- [x] Gini coefficients computed
- [x] Top-1%/10% touch concentration computed
- [ ] Per-write temporal ordering (needs re-instrumentation)
- [ ] Page-lifetime survival curves (needs temporal data)
