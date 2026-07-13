# Result-to-Claim Postmortem

## Verdict

- `claim_supported`: no
- `confidence`: high
- `recommended_action`: kill
- Reviewer: independent secondary Codex reviewer, 2026-07-13

## What failed

1. Selective recoupling did not beat strong locality baselines. At 10% budget, the capsule oracle saved only about 6--9% pages across SIFT/GIST workloads, while LRU saved 14--87% and vector-hot often saved 10--18%.
2. Capsule lifetime collapsed under real update page writes. At 1% updates, target plus actual insert topology-page invalidation reached 99.54%; optimistic rebuild break-even was about 1,343 queries.
3. No update-induced layout debt appeared. Same-graph fresh/restored layout never beat current layout through 20% uniform mixed updates; it was also worse for clustered aligned and separate regions.
4. Adjacency relayout is a static opportunity, not debt: its benefit decreased from 14.97% at 0% updates to 8.26% at 20%.
5. Recall degradation is not a layout result. Layout replay preserves the same logical query path and recall, so the declining recall must be investigated at graph/search maintenance level.

## Why the hypotheses failed

- The reusable locality is dominated by ordinary frequency locality, which LRU/vector-hot captures more directly than cross-store coaccess packing.
- DGAI insertion touches a broad set of topology pages, while deletion scans/re-writes the topology store; page-versioned derived capsules therefore have poor survival.
- Refresh updates do not move active vector locations or progressively fragment occupancy enough to harm query locality. The current online placement is at least as good as restoring the initial mapping.
- Future-query coaccess has a very large offline upper bound, but the gate did not reveal a causal online signal that can approach it.

## Do-not-repeat constraints

- Do not relabel ordinary hot-page caching as selective recoupling.
- Do not cite M3 adjacency gains as update-induced layout debt without subtracting the larger 0% static gain.
- Do not present page-exact replay or future-query oracle as measured end-to-end latency.
- Do not attribute recall loss to physical layout when same-path replay preserves recall.
- Do not reopen insert-only/delete-only or second-dataset update sweeps merely to rescue these claims; require a new mechanism-level hypothesis first.
- If graph-quality degradation is pursued, create a new gate with graph connectivity/neighbor-quality measurements and separate delete versus reinsert effects.
