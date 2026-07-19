# Pipeline Restart Assessment

**Date**: 2026-07-19
**Question**: Should we restart /idea-discovery?
**Verdict**: No — not yet.

---

## What Gpt Actually Rejected

Gpt's review killed most ideas, but the critique is about **mechanism depth**, not **search direction**:

1. **Inflated novelty**: "No paper with this exact title" ≠ mechanism gap. I scored ZoneEpoch-ANN 10/10 novelty when the navigability certificate isn't even computable.
2. **"Apply X to Y" pattern**: GraphKV = "put graph ANN in KV cache," PageTxn = "add WAL to graph ANN," FreshCert = "add freshness certificate to graph search." All lacked the mechanism that makes them more than engineering.
3. **Underestimated field coverage**: KV retrieval (6+ recent papers), filtered ANN (GLS, Curator, GateANN), quantization-graph (SymphonyQG, QuIVer, δ-EMQG) are all more crowded than I assessed.

A second pipeline run hitting the same field would produce the same patterns. The problem isn't search breadth — it's that I can't manufacture mechanism novelty through brainstorming.

## What's Still Alive

| Direction | Status | Next Gate | Blocker |
|-----------|--------|-----------|---------|
| ZNS Z0 | Z0A PASS, Z0B failed (bug) | Fix Z0B → run OdinANN-400K | DGAI-50K "no reclaimable victim" should be expected, not fatal |
| Ambiguity-Monotone | HOLD | Paper gate: query-independent uncertainty invariant | Need formal object beyond heuristic scoring |
| PageTxn-ANN | HOLD | Paper gate: graph-specific crash invariant beyond WAL | Need to prove WAL is insufficient |

## Z0B Failure Analysis

Z0B campaign failed 10 minutes after launch at dgai-50k-r1: `no reclaimable victim`. Root cause: DGAI-50K has ρ ≈ 1.04 (96.4% new-page writes, 3.6% repeats). With almost no page invalidation, every victim zone is still nearly full of live data — GC can't reclaim anything.

**This is expected behavior.** Gpt's gate explicitly says DGAI-50K is a "low-repeat control" allowed to not trigger GC. The campaign error-handling should have reported "no GC triggered" and continued to OdinANN-400K. Instead it hard-stopped.

OdinANN-400K (ρ ≈ 5.0, 80% repeat writes) never ran. That's where the actual reclaim signal would come from.

## When to Restart the Pipeline

Restart /idea-discovery only if ALL three remaining paths are exhausted:

1. Z0B OdinANN-400K → KILL-NO-RECLAIM-SIGNAL
2. Ambiguity-Monotone → no query-independent invariant found
3. PageTxn-ANN → no graph-specific crash invariant found

If we do restart, the search should leave disk-resident ANN internals entirely. Gpt's closing message: "两者都失败后，应离开当前DiskANN内部构图/更新语义，而不是继续枚举新名字。" A new pipeline should explore a fundamentally different problem space, not re-brainstorm the same territory.

## Recommended Next Action

1. **Immediate**: Fix Z0B to handle DGAI-50K gracefully (report no-GC-trigger, continue to OdinANN-400K)
2. **This week**: Get OdinANN-400K Z0B result
3. **If Z0B PASS**: Propose Z0C (ANN-specificity test)
4. **If Z0B KILL**: Run Ambiguity-Monotone paper gate (formal uniqueness proof)
5. **Only if everything fails**: Restart pipeline with fundamentally different direction
