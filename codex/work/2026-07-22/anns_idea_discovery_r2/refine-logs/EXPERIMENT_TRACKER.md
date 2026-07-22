# TraceGuard A0 Experiment Tracker

Current phase: **RETHINK pre-gate not started; certificate A0 canceled**

| ID | Experiment | Status | Gate/result | Artifact |
|---|---|---|---|---|
| P0 | SIFT100K phenomenon micro-pilot | complete | Positive signal only; not causal/equal-budget evidence | `../TRAJECTORY_MICRO_PILOT.md` |
| R2.K | Discovered-frontier coverage theorem audit | complete | **KILL:** coverage event is vacuous for nonzero misses | `round-2-review.md` |
| P1 | Four-path causal decomposition + regression | pending | Reproduce P0 and isolate direct/state-drift terms | — |
| P2 | Result-change residual prediction | pending | Add information beyond patience/margin/hardness | — |
| P3 | Second dataset + label-grounded feedback | pending | >=15-point causal terminal separation | — |
| P4 | Equal-work result-change stopping | pending | >=25% over strongest baseline at equal wall-clock | — |
| P5 | Final Route-A ruling | pending | Continue only if every pre-gate passes | — |

## Routing rule

- Frontier alternative certificate -> **KILLED-FRONTIER-COVERAGE**.
- Phenomenon without allocation benefit -> **KILL-CHARACTERIZATION-ONLY**.
- Beats uniform but not margin/hardness -> **KILL-DYNAMIC-EF**.
- Only SIFT/artificial updates -> **KILL-TOY-DYNAMICS**.
- Gain disappears under wall-clock accounting -> **KILL-CONTROLLER-OVERHEAD**.
- All pre-gates pass -> **HOLD-TO-FRESH-NOVELTY-CHECK**, not paper-ready PASS.
