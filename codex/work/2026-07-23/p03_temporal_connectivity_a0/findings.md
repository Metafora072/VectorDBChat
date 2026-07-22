# P03 result-to-claim findings

## Tested claim

Chronological cohort streaming causes a directional cross-cohort connectivity deficit, that deficit harms cohort-specific ANN queries, and degree-matched replacement has Oracle recovery headroom.

## Local evidence boundary

- Supported: chronological insertion causes a stable early-to-late directed-edge deficit on SIFT1M under R=64/L=96. STATIC and cohort-shuffled streaming are nearly identical, while TIME has C0→C3 mass only 0.612–0.614× SHUFFLE over three seeds.
- Not supported: the structural deficit causes Recall@10 or search-work harm. All four GT-1NN cohorts miss the preregistered 1pp Recall / 5% work gates; TIME uses slightly fewer comparisons.
- Not tested by design: degree-matched Oracle repair, because query harm is its prerequisite.

## Constraints for future attempts

- Do not treat edge-density matrices, path transitions, or target-entry shifts as utility evidence.
- Do not lower search-L or choose an adversarial query subset after seeing this result merely to manufacture harm.
- Do not implement cross-cohort repair, temporal pruning, maintenance, or scheduling without an independently justified workload where the query-harm gate first passes.
- The current result is SIFT1M/file-cohort specific and does not establish a general theorem about all temporal vector streams.

## Pipeline route

`HOLD-P03-STRUCTURE-ONLY`; no Oracle and no mechanism design. Await independent result-to-claim review, then either archive P03 and move to the already approved P10 A0 or request a genuinely temporal dataset before revisiting P03.

## Independent result-to-claim review

- `claim_supported`: `partial`
- `confidence`: `high`
- Supported claim: cohort-ordered streaming causes stable directed edge-mass redistribution on the tested SIFT1M configuration.
- Unsupported claim: the redistribution causes query harm or offers repair headroom.
- Route: keep `HOLD-P03-STRUCTURE-ONLY`, forbid Oracle, and move to the already approved P10 A0. Reopen P03 only with genuinely temporal data or prospectively registered reasonable search budgets, never by tuning this SIFT1M run after seeing the outcome.
