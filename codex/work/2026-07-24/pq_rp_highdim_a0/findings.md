# Findings: PQ-RP-HIGHDIM-A0

## Verdict

`STOP-CANARY / claim_supported=no / pending external Gpt review`.

## What was tested

The approved pipeline attempted Cohere-1M-768D first, then followed the frozen
fallback to GIST1M-960D. It built one R64/L100 graph and ordinary
PQ16/PQ32/PQ64 representations from one deterministic 10% training sample.
Canary compared PQ32, PQ64, and Exact navigation at L={100,200,400,800}, with
exactly two performance repeats.

## What failed

The Cohere mirror was not unit-normalized as declared. GIST M0 and M1 passed,
but Canary p50 stability failed at PQ32 L200 (65.1% drift) and Exact L200
(28.1% drift), above the frozen 25% limit. Full execution was therefore
forbidden.

## What the completed evidence supports

- The shared-graph/shared-sample artifact controls are implementable.
- Increasing uniform GIST navigation code size reduces PQ reconstruction error.
- On the 200-query diagnostic, PQ64 reaches a substantially better
  recall-performance point than PQ32 at the 95.5% common-recall grid.

## What it does not support

- No stable 1K-query RP-memory curve.
- No paper-level GO/HOLD/KILL decision.
- No conclusion attributable to dimension alone.
- No evidence that higher precision benefits are selective over nodes,
  queries, or frontier decisions.
- No mixed-precision method claim.

## Constraints for future attempts

- Do not normalize or silently repair the downloaded Cohere mirror under this
  preregistration.
- Do not rescue this run with a third repeat, extra L points, or selective
  reporting.
- Do not treat the diagnostic GIST matched-recall result as a GO token.
- Any continuation needs a newly reviewed performance-control protocol and a
  validated modern semantic dataset; it is not an automatic continuation of
  this A0.
