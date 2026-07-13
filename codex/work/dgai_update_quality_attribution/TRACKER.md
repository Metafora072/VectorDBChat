# DGAI Update Quality Attribution Tracker

- Gate: `gpt/share/dgai_update_quality_attribution_gate_0713.md`
- Clean source: `a0179b876a4bd453336dc2893b46ae890f680555`
- Isolated worktree/build/raw root: `/home/ubuntu/pz/VectorDB/data/VectorDB/dgai_update_quality_attribution`
- Build-only compatibility fix: AVX-512 PQ table uses unaligned-safe load; algorithm and index are unchanged.

| Stage | State | Evidence / early-stop condition |
|---|---|---|
| G0 no-op and tag semantics | complete (SIFT sanity) | 900k unique active tags; zero duplicate/missing; no-op recall stable |
| G0 exact GT audit | complete (SIFT subset) | exact scan and filtered official top-10 sets match for 3/3 queries |
| G0 1% same-vector refresh | complete (seed 17) | old IDs invisible; new tag mapping unique; 1000 sampled vectors have zero coordinate error |
| G0 update persistence | failed | reopening the 1% updated files SIGSEGVs because updated mappings/tags are not checkpointed |
| G0 20% clean reproduction + budget sweep | complete; observation rejected | seed 17 and the exact old seed 711 both show no recall/I/O degradation through 20% |
| G0 old-positive direct match | complete | seed 711, identical first refresh tags and qid 0--399: old L100 0.99625→0.96000; clean 0.99625→0.99700 |
| G0 second dataset / third seed | early-stopped | not needed after the old positive case fails exact clean reproduction; no universal no-degradation claim is made |
| G1 primitive isolation | early-stopped by gate | G0 proves the motivating observation is not reliable clean-implementation evidence |
| G2 topology/path attribution | early-stopped by gate | no reliable quality loss to attribute |
| G3 repair baselines/cost Pareto | early-stopped by gate | no repair system or oracle implemented |

## Final route

- Result-to-claim: `claim_supported=no`, confidence `high`.
- Decision: `G0 early stop -> Exit DGAI`.
- Separate correctness issue: updated runtime tag/location state is not persistently checkpointed; reopening a 1% updated file set crashes. This is not reframed as a research opportunity here.
- Final report: `codex/share/dgai_update_quality_attribution_g0_g3_0713.md`.

## Storage policy

All index copies, build objects and raw CSV traces remain on the project NVMe. The chat repository contains only source, tracker and summarized evidence.
