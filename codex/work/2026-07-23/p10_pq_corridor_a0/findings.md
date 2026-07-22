# P10 A0 findings

## Verdict

Machine gate: **`HOLD-P10-NONUNIQUE`**.

Portfolio recommendation under the latest Gpt rule (“matched-cost larger beam solves it → immediate KILL”): **`KILL-P10-AS-STANDALONE`**. Preserve the phenomenon as evidence about compressed navigation, but do not promote fixed-window early exact steering as a paper mechanism.

## Validity control

The inherited P07 index used 128 PQ bytes for 128-dimensional integer-valued SIFT. Its measured PQ residual was exactly zero at the median and P90; PQ and exact navigation had identical expanded/visited sets and the same 99.76% Recall@10. This is a useful zero-error control but cannot test corridor drift.

We therefore trained a 16-byte PQ on a 10% sample while reusing the byte-identical graph/SSD file. No graph was rebuilt. Baseline expansion-score residual then became 7.07% median and 9.34% P90.

## Main result

| Variant | Recall@10 | Mean page reads | Exact-nav reads | Touched KiB | Latency ms |
|---|---:|---:|---:|---:|---:|
| PQ, L100/W2 | 96.46% | 106.80 | 0 | 427.2 | 12.45 |
| Exact nav, L100/W2 | 99.76% | 106.36 | 6808 | 3829.6 | 12.85 |
| Early exact h=1 | 96.46% | 106.64 | 65 | 459.1 | 12.63 |
| Early exact h=2 | 96.44% | 106.58 | 193 | 522.8 | 12.06 |
| Early exact h=4 | 97.00% | 106.51 | 449 | 650.5 | 12.51 |
| Early exact h=8 | 98.58% | 106.49 | 961 | 906.5 | 12.17 |
| Late exact, start block 50 | 96.47% | 106.81 | 500 | 677.3 | 14.02 |
| PQ, L100/W4 | 96.51% | 112.08 | 0 | 448.3 | 8.37 |
| PQ, L150/W4 | 98.44% | 161.39 | 0 | 645.6 | 12.11 |
| PQ, L200/W4 | 99.14% | 211.05 | 0 | 844.2 | 15.90 |

Paired query bootstrap (10,000 resamples): exact versus PQ gain is +3.30pp, 95% CI [2.89, 3.73]; Early-8 versus PQ is +2.12pp [1.80, 2.45]. Early-8 versus ordinary L150/W4 is only +0.14pp, CI [-0.13, 0.41]. L200/W4 exceeds Early-8 by +0.56pp [0.31, 0.81].

## Path evidence

Exact navigation diverges from PQ at median expansion 2. Its median expanded-set Jaccard is 0.455, expansion-bigram Jaccard 0.0145, and visited-set Jaccard 0.563. Early-8 also diverges at expansion 2 and retains only 0.680 expanded-set / 0.066 order-bigram / 0.739 visited-set Jaccard. Late-4 has median Jaccards of 1.0 because the baseline search is effectively decided before block 50.

Thus the causal phenomenon is real: lossy PQ changes the early corridor, and exact steering in the early window recovers substantial recall. It is not merely final reranking noise.

## Why this is not a paper mechanism yet

Early-8 recovers 64% of the exact-navigation recall gain using 14% of its exact reads, so it passes the preregistered early-locality gate. However, L150/W4 reaches statistically indistinguishable Recall at the same measured latency and lower touched bytes; L200/W4 is more accurate at lower touched bytes than Early-8, though slower and with more SSD pages. The core method is therefore not uniquely better than ordinary search-budget expansion.

The proposed online signal is also unsupported. Exact-navigation gain is largest in the lowest PQ-residual quartile (+3.92pp) and smallest in the highest (+2.32pp), so baseline trace residual does not identify the harmed queries. Tight top-k margin correlates in the expected direction, but exact margin is unavailable online.

## Claims allowed and forbidden

Supported: aggressive PQ compression can alter DiskANN paths almost immediately; early exact steering has real Oracle headroom; late exact steering does not.

Not supported: early exact steering is a better algorithm than increasing ordinary search budget; PQ residual provides an online selector; the result generalizes beyond SIFT1M/16-byte PQ; extra full-vector reads are free.

Do not continue by searching h values beyond the frozen set, choosing only queries where Early-8 wins, or redefining cost to exclude RAM reads/SSD pages after seeing results. A continuation needs a new mechanism that dominates adaptive larger-search controls under a preregistered cost model, not another window size.

## Independent result-to-claim review

The independent reviewer assigns `claim_supported=partial`, confidence high. It agrees that `HOLD-P10-NONUNIQUE` is the direct preregistered outcome and recommends killing fixed-window Early-Exact as the mainline. The phenomenon may only be reused in a newly checked candidate based on selective ambiguity certificates (for example, PQ distance-error intervals overlapping the frontier threshold), evaluated against a fully tuned L/W Pareto frontier and without changing the current gates.
