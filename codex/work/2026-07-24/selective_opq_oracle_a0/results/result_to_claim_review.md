# Result-to-Claim Review

## Verdict

```text
claim_supported: partial
confidence: high

PASS-ALGORITHMIC-SELECTIVITY-SIGNAL
HOLD-STAGE-B-FOR-REVIEW
```

## What the results support

Within the strictly limited GIST1M-960D, frozen-graph, fixed 1K-query,
OPQ32/64 and per-L test-trace hindsight setting, static mixed precision has
strict positive algorithmic points. The most credible routing-relevant point
is `DISTANCE-REGRET, L=50, budget=56`: Recall rises by 0.0127 (127 top-k
hits), reads fall by 0.631%, and comparisons fall by 0.539%; all three paired
query bootstrap intervals remain favorable. Random selection has no positive
point.

## What the results do not support

The evidence does not yet establish that OPQ64 routing value is concentrated
on a small, generalizable static node subset:

- the only fully stable point assigns OPQ64 to 75% of nodes;
- visit-frequency nearly matches distance-regret at that point;
- routing-aware's only strict point has reads and comparisons intervals that
  cross zero;
- the 60-point hindsight scan is exposed to selection bias;
- no deployable held-out selector, cross-workload result, actual-resident
  memory result, or system result has been established.

## Revised claim

On the fixed GIST1M test trace, hindsight per-L distance-regret at `L=50` and
75% OPQ64 allocation gives a small but paired-bootstrap-stable joint
Recall–reads–comparisons improvement over uniform OPQ56. This is an
algorithmic-selectivity signal, not evidence for a deployable selector,
general routing-value concentration, actual-memory advantage, or system
Pareto improvement.

## Recommended route

Do not enter full Stage B automatically. Ask for approval of a smaller Stage
A.5 kill gate:

1. pre-register `L=50, budget=56`;
2. construct selectors only from a calibration query split;
3. evaluate on held-out queries;
4. compare distance-regret directly with visit-frequency using paired
   differences;
5. only if held-out joint improvement survives, request a reduced Stage B
   beginning with mixed56 versus uniform OPQ61.

