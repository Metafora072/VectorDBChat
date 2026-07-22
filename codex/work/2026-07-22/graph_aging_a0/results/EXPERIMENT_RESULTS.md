# Experiment results

Final decision: **KILL-NO-PROBLEM / KILL-SHADOW-NO-UTILITY**.

The authoritative narrative report is:

`/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-22/graph_aging_a0_results_0722.md`

Machine-readable aggregation: `final_summary.json`.

Core evidence:

- Official IP-DiskANN explicit deletion after 100 cycles: Recall −0.006 pp, comparisons +0.414%.
- PipeANN/FreshDiskANN-style 10% batch, five update seeds after 100 cycles: Recall +0.004 pp, comparisons +3.85% vs identity G0.
- A0-2 pre-prune comparisons +9.68%; equal-degree post-prune −0.024%.
- Oracle Shadow Replay on A0-2: high structural acceptance, tiny Recall gain, and about 3% more work.
