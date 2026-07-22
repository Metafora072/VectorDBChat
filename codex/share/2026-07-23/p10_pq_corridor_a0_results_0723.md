# P10 PQ Navigation Corridor A0 — Results

## Bottom line

P10 establishes a real compressed-navigation phenomenon but fails algorithmic uniqueness. The formal A0 gate returns **`HOLD-P10-NONUNIQUE`**; under Gpt’s stricter portfolio rule, the fixed-window mechanism should be treated as **`KILL-P10-AS-STANDALONE`**.

With a valid 16-byte PQ and the graph/SSD file held byte-identical, exact navigation improves Recall@10 from 96.46% to 99.76%. Paths split at median expansion 2. Exact steering limited to the first eight expansion blocks reaches 98.58% while using 14.1% as many full-vector reads as exact navigation; the same amount of exact work near the end gives only 96.47%.

The mechanism nevertheless loses its independent identity against an ordinary control: PQ search at `L=150,W=4` gives 98.44% Recall at 12.11 ms, versus Early-8’s 98.58% at 12.17 ms. The paired +0.14pp difference has a 95% bootstrap CI of [-0.13, 0.41]. At `L=200,W=4`, plain PQ reaches 99.14%, significantly above Early-8.

## Experimental correction retained as evidence

The inherited index used a 128-byte code on 128-dimensional SIFT. Because the source coordinates are integer-valued, this scalar quantizer was lossless: expanded-node PQ residual median and P90 were both exactly zero, and PQ/exact navigation were identical. This run is retained as a zero-error negative control rather than mislabeled as a P10 failure.

The actual hypothesis test trained a 16-byte PQ on 10% of SIFT1M and reused the same `sift1m_disk.index`. This isolates navigation-code loss from graph-construction differences. The 16-byte residual is 7.07% at the median and 9.34% at P90.

## Decision table

| Gate | Evidence | Decision |
|---|---|---|
| Path divergence has outcome consequence | Exact +3.30pp; 95% CI [2.89, 3.73] | PASS |
| Benefit is early, not generic exact work | Early-8 +2.12pp; Late-4 +0.01pp | PASS |
| Early work is sparse relative to exact nav | 961 vs 6808 reads (14.1%) | PASS |
| Beats ordinary matched search | L150 matches recall/latency; L200 beats recall | FAIL |
| Online query selector exists | PQ residual quartiles are anti-predictive | FAIL |

## Reproducibility

- Plan, frozen gates, source hooks, scripts, per-query metrics and summaries: `codex/work/2026-07-23/p10_pq_corridor_a0/`
- Main machine-readable result: `results/analysis_summary_pq16.json`
- Zero-error control: `results/analysis_summary.json`
- Large reproducible PQ artifacts: `/home/ubuntu/pz/VectorDB/data/VectorDB/p10_pq_corridor_a0_0723/`
- Reused graph/SSD index: `codex/work/2026-07-22/p07_page_bonus_a0/index/sift1m_disk.index`

CPU-only resource use stayed below 1 GB resident memory per run; each 1,000-query variant took roughly 8–16 seconds of measured search time plus loading. No GPU or training was used.

## Next action

Do not tune more early windows. Archive P10 as a useful phenomenon/negative mechanism result and request independent review. A resurrection would require a new selector or bound that beats adaptive larger-search baselines under a frozen cost model; otherwise it returns to generic adaptive computation, exactly the failure mode already identified for Trajectory-Stable ANN.

Independent result-to-claim review returns `claim_supported=partial`, confidence high. It independently confirms the formal HOLD and recommends `KILL` for fixed-window Early-Exact as a standalone mainline. A selective ambiguity-certificate method would be a new candidate requiring fresh novelty checking, not a post-hoc P10 patch.
