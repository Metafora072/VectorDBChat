# P10 experiment tracker

| Stage | Status | Evidence |
|---|---|---|
| Instrument real DiskANN navigation | COMPLETE | PQ/exact/early/late switch, path trace, exact-read counter |
| Compile | COMPLETE | `search_disk_index` target builds |
| 20-query exact-navigation smoke | COMPLETE | 20 metrics rows and 20 trace rows; no crash |
| Freeze A0 gates | COMPLETE | `EXPERIMENT_PLAN.md`, before 1,000-query analysis |
| 128-byte zero-error control | COMPLETE | residual median=P90=0; exact and PQ paths identical |
| Generate valid compressed navigation code | COMPLETE | 16-byte PQ; graph/SSD file unchanged |
| Run all 1,000-query PQ16 variants | COMPLETE | 10 variants, 1,000 metrics rows and traces each |
| Analyze and adjudicate | COMPLETE | `HOLD-P10-NONUNIQUE`; see `findings.md` |
