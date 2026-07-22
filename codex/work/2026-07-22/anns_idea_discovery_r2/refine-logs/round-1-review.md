# TraceGuard Refinement Review — Round 1

## Verdict

**REVISE, 6.4/10.** The problem anchor is strong, but the current proposal cannot call an ordinary HNSW/Vamana frontier an admissible envelope and cannot use the current query's top-k gap to certify stability of a future query.

| Dimension | Score | Main reason |
|---|---:|---|
| Problem fidelity | 9 | Cleanly isolates endogenous query-trajectory error. |
| Method specificity | 5 | Frontier coverage, multi-swap alternatives, and future-gap use are not closed. |
| Contribution quality | 5 | Push-forward risk is promising but can collapse to feedback-aware dynamic `ef`. |
| Frontier leverage | 7 | Good connection to anytime search, but no inherited admissible guarantee. |
| Feasibility | 6 | CPU A0 is feasible; a generic certificate is not. |
| Validation focus | 9 | Causal controls and Kill gates are appropriately strict. |
| Venue readiness | 4 | Conditional heuristic plus elementary recursion is not yet a top-tier contribution. |

## Structural objections

1. A graph frontier contains only discovered candidates. It does not exclude a closer, undiscovered object. Therefore
   \(\mathcal A_t^{\mathrm{frontier}}\subseteq\mathcal A_t^{\mathrm{true}}\), and the proposed radius is valid only conditional on a separately measured coverage event.
2. The exact gap around \(q_t\) says whether perturbations around \(q_t\) preserve the current exact top-k. It says nothing about two possible queries at \(q_{t+1}\), which may lie near another ranking boundary. The proposal must remove this time-misaligned certificate.
3. Single-swap alternatives do not cover several simultaneous misses, especially for a nonlinear result-to-query map.
4. Applying a generic feedback function to every alternative and calculating all pairwise diameters may cost as much as additional ANN expansion. Wall-clock, distance-computation, and I/O matching are all required.
5. Without coverage or calibration, `increase ef when branch risk is high` can be dismissed as dynamic `ef`.

## Required simplification

- Restrict the formal feedback class to affine/additive set feedback such as centroid and Rocchio.
- Replace a deterministic “trajectory-risk certificate” with a **conditional frontier branch-state bound**.
- Use a radius around the nominal next state, not a pairwise branch diameter.
- Remove future-query-gap preview and multi-step simulation.
- Treat the allocator as a direct use of one dominant signal, not a second contribution.
- Make complete alternative-family coverage the first A0 measurement; Kill if it is below 90% in the target high-recall regime.
- Demonstrate information beyond current margin, DARTH-style hardness, and local recall using matched query pairs.

## Minimum formal closure for Round 2

Round 2 must define: (1) the exact coverage event; (2) the theorem conditional on that event; (3) a conservative multi-miss bound; and (4) the full online overhead relative to frontier expansion.

## Strongest rejection after Round 1

> Approximate kNN in relevance-feedback loops is old. TraceGuard applies another dynamic-effort controller to an HNSW frontier that does not cover undiscovered neighbors, so its “certificate” is not a certificate. Once that claim is removed, the theory is a standard Lipschitz recursion and the empirical method is feedback-aware dynamic `ef` evaluated under artificial feedback laws.
