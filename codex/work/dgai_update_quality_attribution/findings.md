# DGAI Update Quality Attribution Findings

## Result-to-claim verdict

- `claim_supported`: `no`
- `confidence`: `high`
- Route: `G0 early stop -> Exit DGAI`

## What was tested

The intended claim was that same-vector delete--reinsert reliably degrades clean DGAI search quality, cannot be covered by ordinary search budget, and therefore merits topology attribution and budgeted local repair. The clean test used commit `a0179b876a4bd453336dc2893b46ae890f680555`, a fresh strategy-23 SIFT-900K index for each run, checkpoints 0/1/5/10/20, and search budgets L=100/200/400/800. It included seed 17 and seed 711, the latter reconstructed from the exact first ten tags of the old positive run.

## What failed

The old positive result does not reproduce. On qid 0--399 the dirty/instrumented run with seed 711 changed L100 Recall@10 from 0.99625 to 0.96000, while the clean direct match changed it from 0.99625 to 0.99700. L200/400/800 also stayed flat or improved, and mean logical I/O did not rise. Seed 17 independently remained flat through 20%.

Tag uniqueness, old/new internal-ID visibility, sampled stored-vector equality and a small exact-GT audit passed. The old worktree contains behavior-affecting search/rerank control-flow changes in addition to instrumentation, so its recall trace is not acceptable clean-implementation evidence. The current evidence does not identify one offending line and must not claim that it does.

## What the evidence supports

In clean DGAI plus the minimum crash-prevention correctness guards, uniform same-vector refresh on SIFT for seeds 17 and 711 does not cause recall or logical-I/O degradation through 20% checkpoints. It supports rejecting the prior dirty observation and stopping the attribution gate.

## What it does not support

It does not prove that refresh is harmless for every dataset, update distribution, seed or scale. GIST, a third seed and the full query-set matrix were intentionally not run after the exact old positive case failed clean reproduction. It also does not support topology repair, a repair-cost Pareto, or any claim about decoupling enabling stronger repair.

## Separate correctness issue

The in-process update path maintains correct active mappings, but the runtime tag/location changes are not checkpointed in a form that reload reconstructs. Reopening the 1% updated file set crashes before query. This deserves ordinary correctness engineering if DGAI is reused, but it is not evidence for the rejected research claim.

## Constraints for future attempts

Do not reuse the dirty profiling worktree as quality evidence. Any future historical forensics must start from the clean commit and enable old patches one at a time. Do not reopen G1--G3 unless a clean, persisted, multi-seed positive observation is first established. Do not describe the present SIFT result as a universal theorem.
