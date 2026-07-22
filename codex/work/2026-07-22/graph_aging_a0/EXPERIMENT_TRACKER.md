# Experiment tracker

| ID | Status | Evidence | Decision |
|---|---|---|---|
| G0 / sanity | PASS | 10K smoke and five SIFT1M static builds | Metrics and variance baseline valid |
| A0-1 PipeANN, 10% batch | PASS (negative phenomenon) | Five update seeds through cycle 100 | Recall +0.004 pp; work +3.85% vs identity |
| A0-1 PipeANN, 1% batch | PASS (negative phenomenon) | One SIFT1M seed through cycle 100 | Recall −0.01 pp; mean comparisons +0.93% |
| A0-1 official DiskANN3 replacement control | PASS (negative phenomenon) | SIFT1M through cycle 100 | No aging; control only, not IP-delete evidence |
| A0-1 official IP-DiskANN explicit delete | PASS (KILL gate) | SIFT1M through cycle 100 | Recall −0.006 pp; mean comparisons +0.414% |
| A0-2 fair static vs incremental | PASS (negative phenomenon) | Paths 1–3, five seeds, pre/post final prune | Path2 +9.6% pre-prune becomes −0.05% after equal-degree comparison |
| A0-3 logical counterfactual ledger | DONE | Changed-owner and edge-difference instrumentation | Full filesystem/block tracing stopped by KILL gate |
| A0-4 Oracle Shadow Replay | DONE | 10K smoke, cycle-100, Paths 2–3 | Tiny Recall gain with ~2.7–3.0% more work; large candidate storage |
| Seven-history × multi-seed expansion | EARLY STOP | Strong-baseline KILL gate fired | Not run |
| Semi-coupled prototype | EARLY STOP | Core phenomenon rejected | Not run |

Overall decision: **KILL-NO-PROBLEM / KILL-SHADOW-NO-UTILITY**.
