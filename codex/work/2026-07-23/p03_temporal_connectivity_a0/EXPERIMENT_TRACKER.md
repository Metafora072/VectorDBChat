# P03 A0 tracker

| Stage | Status | Evidence | Gate |
|---|---|---|---|
| Environment and plan | DONE | CPU/NVMe data and prior GraphAging harness located | Proceed |
| 10K structure sanity | PASS | 3 graphs, 640K edges each, one SCC; TIME C0→C3 mass is 0.654× SHUFFLE | Proceed to SIFT1M; not a phenomenon verdict |
| SIFT1M STATIC/TIME/SHUFFLE, 3 seeds | PASS | C0→C3 TIME/SHUFFLE 0.612–0.614; C0→C2 0.720; all graphs one SCC | GO-P03-QUERY-EFFECT |
| Grouped-query effect | DONE (negative utility) | All cohort Recall deltas <0.1pp; TIME comparisons 0.7–1.6% lower; visited within 0.2% | HOLD-P03-STRUCTURE-ONLY |
| Degree-matched Oracle | EARLY STOP | Prerequisite query harm absent | Not run; adding repair would violate gate |

Overall decision: **HOLD-P03-STRUCTURE-ONLY**. The temporal edge asymmetry is real and highly stable, but it does not produce query harm at the preregistered SIFT1M R64/L96 operating point.
