# TraceGuard Refinement Review — Round 2

## Verdict

**RETHINK, 5.1/10.** R2 removed the incorrect future-gap claim and generic HNSW certificate language, but its new coverage event is operationally vacuous for standard exact-distance graph search.

| Dimension | Score | Main reason |
|---|---:|---|
| Problem fidelity | 9 | Exact-reference trajectory remains a sharp problem anchor. |
| Method specificity | 4 | The formal frontier interface contradicts the actual search state. |
| Contribution quality | 3 | The conditional theorem has a nearly impossible premise. |
| Frontier leverage | 4 | Discovered non-results cannot represent undiscovered true misses. |
| Feasibility | 5 | The code is feasible, but the proposed coverage gate cannot pass non-vacuously. |
| Validation focus | 9 | Causal and equal-cost controls remain strong. |
| Venue readiness | 2 | A short counterexample defeats the central mechanism. |

## Fatal frontier counterexample

At a normal HNSW/Vamana checkpoint, every discovered candidate has an exact query distance and `C_t` contains the `k` closest discovered points. Suppose a true top-k object `u` is omitted from `C_t` but is already discovered and placed in `U_t`. Since exact and current sets both contain `k` objects, there is a false positive `v` in `C_t`. Exact top-k implies `d(q,u) < d(q,v)`, but both are discovered, so `u` would already have displaced `v` in `C_t`: contradiction.

Therefore a genuine true top-k miss is **undiscovered**, not discovered-but-unresolved. The event

`R_loc \ C subset U`

can hold only when there is no miss. Its unconditional frequency could also be inflated by already-correct steps; any future coverage metric must be conditioned on `R_loc != C`.

## What remains correct

Conditional on an abstract candidate set that really contains every omitted exact object, the additive multi-miss triangle-inequality bound is algebraically correct. The top-`m` sum is an upper bound on the sum over any omitted subset of size at most `m`; define missing terms as zero when `|U|<m`. This result is nevertheless vacuous with the proposed standard graph frontier.

The equal-cost contract—distance computations, controller vector work, wall-clock, and SSD reads—is valid and should survive any redesign.

## Other failures

1. The horizon recursion controls only local ANN result error at the same query. It omits the discontinuous exact top-k transition between different trajectory states. It must be deleted unless the entire exact closed-loop transition is locally Lipschitz along the trajectory.
2. The proposed decision uses `rho(b+delta)` before paying for and observing the next expansion block. The radius is also not monotone: a newly found feedback-distant candidate or a changed result centroid can increase it.
3. Without an unseen-object bound, the method is a result-content-aware dynamic-`ef` score, not a trajectory certificate.

## Minimal routes after RETHINK

- **Route A — realized result-change stopping:** after each fixed expansion block, measure `z_l = ||F(s,C_l)-F(s,C_{l-1})||` and decide whether to buy another block. This is operational, but is an empirical dynamic-effort heuristic and needs a very strong matched-hardness/equal-wall-clock A0.
- **Route B — genuine unseen-region bound:** use a branch-and-bound or bounded-cell index that exposes pre-distance candidate regions and admissible feedback-displacement bounds. This is a new index mechanism, not a thin HNSW stopping layer; high-dimensional bound looseness is the first Kill gate.

The review recommends not rescuing the current idea with a learned coverage predictor, cache, preview query, or second index module.

## Strongest rejection

> At a graph-search checkpoint, a discovered true top-k point cannot be absent from the heap of the k closest discovered points. Hence every genuine miss is undiscovered and cannot lie in the proposed frontier alternative set. The theorem is valid only under a vacuous condition; the horizon bound ignores top-k discontinuity; and the stopping rule uses an unobserved future reduction. What remains is a dynamic-ef heuristic.
