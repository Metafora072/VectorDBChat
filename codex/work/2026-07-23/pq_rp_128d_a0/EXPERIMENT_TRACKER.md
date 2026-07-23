# PQ-RP-128D-A0 tracker

| Stage | Status | Evidence |
|---|---|---|
| Freeze controls and canary gate | COMPLETE | `EXPERIMENT_PLAN.md` |
| Add multi-L metrics and runtime warm-up | COMPLETE | patched and rebuilt `search_disk_index` |
| Prepare official 10K truthset | COMPLETE | IDs unchanged; truthset manifest recorded |
| Prepare byte-identical PQ8/PQ16/PQ32 prefixes | COMPLETE | 8/16/32 MB codes; same 819,204,096-byte graph |
| Canary PQ16 + Exact, 1K | COMPLETE-PASS | exact P10 reproduction; no p50 drift >25% |
| Full 10K × 4 representations × 5 L × 3 repeats | COMPLETE | 12 processes; 600,000 per-query rows |
| Analyze and draw seven curves | COMPLETE | `curve_summary.csv`, `marginal_cost.csv`, seven PDF/PNG pairs |
| Report and conversation update | COMPLETE | `codex/share/2026-07-23/pq_rp_128d_a0_results_0723.md` |
