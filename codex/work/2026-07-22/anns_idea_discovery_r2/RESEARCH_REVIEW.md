# ARIS Research Review

Date: 2026-07-22

## Independent verdict

| Candidate | Importance | Mechanism novelty | Theory | A0 falsifiability | CPU feasibility | Venue fit | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Trajectory-Stable ANN | 4/5 | 3/5 | 2.5/5 | 5/5 | 5/5 | 3.5/5 | **HOLD; only candidate worth continuing** |
| Query-Coverage Budgeted Backfill | 4/5 | 1.5/5 | 2/5 | 4/5 | 4/5 | 2/5 | **KILL** |
| Active Spectral Certification | 2/5 for ANNS | 2.5/5 | 3.5/5 | 4/5 | 4/5 | 2/5 | **KILL as ANNS** |

## Why Trajectory-Stable remains only HOLD

The setting is old: approximate kNN has appeared in relevance-feedback loops, and current methods already adapt single-query effort. The only defensible paper core is an online feedback-aware instability certificate whose prediction and budget choices are not reducible to current-query margin or dynamic ef.

The micro-pilot is enough to justify A0 but mixes three terms that the full A0 must separate:

1. direct ANN error at the approximate-path query;
2. pure state drift, measured by exact search at approximate versus exact states;
3. end-to-end approximate result error relative to the exact trajectory.

The A0 must match local-recall distributions, total distance computations, and ordinary hard-query scores. It must also include at least one label- or trace-grounded feedback law and a second CPU ANN family.

Hard result routing:

- phenomenon without allocation benefit → `KILL-CHARACTERIZATION-ONLY`;
- beats uniform but not margin/DARTH-style → `KILL-DYNAMIC-EF`;
- only SIFT or artificial feedback → `KILL-TOY-DYNAMICS`;
- online certificate predicts amplification and wins at equal work → promote to `PASS`.

## Why Seed A is killed

FastFill directly studies policy-based partial backfilling and its quality curve; WACV 2025 covers mixed-version rank merge; lambda-Orthogonality adds another sample ordering. Query coverage is likely a new priority heuristic with a standard submodular surrogate, while actual mixed-version top-k recovery need not be monotone or submodular. The scheduler also faces an information cycle: without computing a new embedding, it may not know the object's new top-k risk.

## Why spectral certification is killed for ANNS

The narrower certification problem is mathematically clean but drifts from ANN query recall/latency. Once a candidate supergraph exists, exact distances on `O(nk)` pairs may not be the real bottleneck; candidate discovery is. The result would fit active graph learning or spectral algorithms better than VectorDB/ANNS, and the certificate may be more expensive than directly refining candidates.

## Strongest rejection to design against

> Approximate kNN in relevance-feedback loops is old; the reported divergence comes from an artificial discontinuous feedback law, the theorem is a standard Lipschitz recursion, and the algorithm is merely dynamic ef.

No further mechanism should be added. Every theory and A0 choice must directly falsify that rejection.
