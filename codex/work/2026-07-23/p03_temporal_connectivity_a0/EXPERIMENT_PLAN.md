# P03 Temporal Connectivity Gap A0

## Claim under test

Chronological cohort insertion creates a directional cross-cohort connectivity deficit that is absent from a cohort-shuffled streaming control. Only if that structural effect is stable do we test cohort-specific query harm; only if query harm exists do we test degree-matched Oracle repair.

## Controls

- `STATIC`: one-shot build over a globally shuffled order.
- `STREAM-TIME`: four chronological cohorts; points are shuffled only within each cohort.
- `STREAM-SHUFFLE`: the same globally shuffled order as `STATIC`, inserted in four equal batches.
- All variants use the same active vectors, tag IDs, `R=64`, `Lbuild=96`, `alpha=1.2`, 12 threads, equal final pruning, and permutation seeds.

## Stages and early stops

1. Structure sanity on 10K points.
2. SIFT1M structure runs for seeds 11/22/33. Report the full directed 4x4 matrix, source-degree-normalized mass, incoming/outgoing cross mass, SCCs, and sampled-target shortest-path reachability.
3. If TIME and SHUFFLE have no stable directional difference beyond seed variation: `KILL-P03-NO-TEMPORAL-EFFECT`.
4. Only after a structural signal: grouped-query Recall@10, comparisons, expanded nodes, first target-cohort entry, and path cohort transitions.
5. Only after query harm: degree-matched Oracle replacement using STATIC cross-cohort edges.

Query harm is preregistered before reading query results as either: (a) median TIME-vs-SHUFFLE Recall@10 loss of at least 1 percentage point for one GT-1NN cohort, with every seed losing at least 0.5 point; or (b) median comparisons or visited-node growth of at least 5%, with every seed growing at least 2%. Path-transition differences alone cannot pass this gate.

The 0.5x C0→C3 and 20% matrix thresholds are descriptive checks, not sufficient final evidence. No repair mechanism is implemented before Stages 2 and 4 pass.
