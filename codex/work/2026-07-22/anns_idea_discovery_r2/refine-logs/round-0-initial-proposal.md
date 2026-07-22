# Research Proposal: TraceGuard — Trajectory-Stable ANN under Feedback

## Problem Anchor

- **Bottom-line problem:** Determine whether ANN errors in a feedback-dependent retrieval sequence cause additional cumulative or terminal failure relative to an exact-retrieval counterfactual, and allocate a fixed total search budget to control that trajectory divergence.
- **Must-solve bottleneck:** Per-query recall, hard-query scores, and adaptive stopping treat each query independently. They cannot distinguish an error that is locally harmless from one that changes the next query and sends the retrieval process onto another branch.
- **Non-goals:** A new graph index, edge score, cache, entry-point reuse rule, relevance-feedback model, agent framework, or generic dynamic-ef wrapper; security, permissions, recovery, and enterprise lifecycle are out of scope.
- **Constraints:** No GPU training; use pre-generated embeddings, CPU, and commodity NVMe; one dominant algorithmic contribution; one-week A0 before a full implementation; target AAAI/IJCAI/NeurIPS/ICML.
- **Success condition:** On at least two real embedding datasets and two standard feedback laws, a causal open-loop control shows that high local ANN recall can still yield meaningful terminal failure, and an online trajectory-risk controller reduces terminal divergence by at least 25% at matched total distance computations versus uniform, margin-only, and strongest single-query adaptive baselines.

## Technical Gap

Approximate kNN has been used inside relevance-feedback loops since at least 2008, so the setting and the observation that approximation may require extra rounds are not new. Modern DABS/DARTH-style methods can spend more work on a hard individual query. What remains absent is a retrieval-side definition of exact-reference trajectory fidelity and an observable signal that predicts whether a boundary error will change future queries.

A generic Lipschitz recursion is insufficient because hard top-k is discontinuous at rank boundaries. The missing mechanism must expose *branch risk*: whether plausible alternatives still hidden in the current ANN frontier would, after the known feedback update, move the next query outside the current exact-top-k stability region.

## Method Thesis

- **One-sentence thesis:** Continue an anytime ANN search until the feedback-induced next-query branches implied by its unresolved frontier are sufficiently narrow, and distribute a finite horizon budget according to the predicted downstream amplification of those branches.
- **Why this is the smallest adequate intervention:** The base ANN index and feedback law stay unchanged; only the stopping/allocation layer consumes information already present in an anytime search frontier.
- **Why timely:** Agentic and interactive retrieval make answer-dependent query sequences common, while ANN evaluation still centers on independent recall-latency points.

## Contribution Focus

- **Dominant contribution:** A margin-conditioned trajectory-risk certificate derived from unresolved top-k alternatives in an ANN frontier.
- **Supporting contribution:** A receding-horizon allocator that spends expansion units according to certificate reduction per unit cost.
- **Explicit non-contributions:** No learned controller, new graph construction, cache, query-reuse mechanism, or new relevance-feedback rule.

## Proposed Method

### Complexity Budget

- **Frozen/reused:** HNSW/Vamana/DiskANN or DABS-style anytime search; exact vector distance; user-specified feedback update `F`; pre-generated embeddings.
- **New trainable components:** None.
- **Intentionally excluded:** RL/bandit allocation, learned GNN hardness predictor, LLM query planner, cross-query cache, and graph rewiring.

### System Overview

```text
state s_t -> query q_t -> resumable ANN frontier
                         | current top-k C_t
                         | unresolved boundary alternatives U_t
                         v
                 feedback branch set
          {F(s_t, phi(C_t swap u)) : u in U_t}
                         |
             branch diameter + rank margin
                         |
            trajectory-risk / marginal value
                         |
          expand now or preserve budget for later
                         v
               answer R_t -> next state s_{t+1}
```

### Core Mechanism: Frontier Branch-Risk Certificate

At step `t`, the base search exposes the current top-k `C_t`, unexpanded candidates/frontier `U_t`, exact distances for visited points, and the current k/(k+1) boundary gap. Construct a small alternative family by swapping each boundary member with the best unresolved candidates allowed by the search's distance envelope. Apply the known feedback map to each alternative result and obtain a set of possible next queries.

Define the one-step branch diameter

`D_t(b) = max_{R,R' in A_t(b)} ||G(F(s_t, phi(R))) - G(F(s_t, phi(R')))||`,

where `A_t(b)` is the plausible result family after spending budget `b`. The certificate is meaningful only under an explicit frontier-coverage assumption supplied by the base anytime search; experiments separately measure violations of that assumption.

For Euclidean distance, if the exact k/(k+1) gap at a reference query is `Delta_t`, every query perturbation of radius less than `Delta_t/2` preserves its exact top-k set because point distances are 1-Lipschitz. TraceGuard combines this local stable radius with the feedback branch diameter. It expands the current search when plausible branches cross the remaining stability slack; otherwise it stops even if ordinary margin-based hardness is high.

This signal is different from current-query hardness: two queries with the same boundary gap can receive different effort when their result alternatives induce very different next-query branches.

### Supporting Mechanism: Receding-Horizon Budget Allocation

Maintain an upper estimate `E_t` of trajectory divergence. Locally, under a feedback-state Lipschitz factor `a_t`, branch error obeys

`E_{t+1} <= a_t E_t + D_t(b_t)`.

For a short lookahead horizon `h`, weight current certificate reduction by the estimated product of future amplification factors. Spend the next expansion unit on the current step only while its amplification-weighted marginal reduction exceeds a shadow price for the remaining budget. In the offline case with known decreasing convex error curves, the resulting allocation reduces to weighted water-filling; the online method uses only a short receding horizon and reports oracle allocation separately as an upper bound.

### Inference Path

1. Start/resume the base ANN search for `q_t` at a small effort floor.
2. Extract `C_t`, a capped frontier alternative set `U_t`, and distance envelope.
3. Push alternatives through the fixed feedback function; compute branch diameter and stable-radius slack.
4. Either expand the same search or return `C_t` according to marginal certificate reduction and remaining horizon budget.
5. Update the real state with the returned result. Do not reuse nodes, results, or cache entries across queries in the main comparison.

### Failure Modes and Diagnostics

- **Frontier misses the true alternative:** compare alternative coverage with exact top-k on A0 subsets; if coverage is below 90%, the certificate claim is killed.
- **Feedback law is contractive:** open/closed-loop separation disappears; report this as a regime boundary rather than tuning an expansive law.
- **Near ties dominate:** stratify by exact margin and use deterministic tie handling.
- **Controller equals margin-only:** match current-query margins and show different allocations/outcomes; otherwise kill the mechanism claim.
- **Oracle-only gain:** require the online estimator to retain at least 50–60% of oracle allocation improvement.

## Novelty and Elegance Argument

Earlier relevance-feedback systems establish the loop; DABS/DARTH establish adaptive single-query work; generic control theory establishes perturbation recursions. TraceGuard's only novelty claim is the interface joining them: an ANN-frontier result-alternative set is pushed through the feedback map and compared with a top-k stability radius. If that branch-risk certificate does not outperform current-query hardness at equal work, the idea is not publishable and should be killed.

## Claim-Driven Validation Sketch

### Claim 1: Independent recall hides causal trajectory loss

- **Minimal experiment:** Exact closed loop, ANN closed loop, exact-query open-loop ANN replay, and approximate-query replay with feedback disabled.
- **Data/laws:** SIFT/Deep or GloVe plus one text embedding set; centroid and Rocchio/query-by-example updates.
- **Metric:** Local recall, terminal exact-trajectory overlap, trajectory divergence, final task success.
- **Gate:** At local recall at least 0.95, terminal overlap loses 15–20 points on two datasets/laws, and the loss is absent or materially smaller in open-loop controls.

### Claim 2: Branch risk beats single-query hardness

- **Baselines:** Uniform budget, margin-only, DABS/DARTH-style per-query controller, oracle horizon allocation, and optional entry-reuse/cache as explicitly orthogonal controls.
- **Metric:** Terminal divergence and cumulative regret at matched distance computations/I/O.
- **Gate:** At least 25% terminal-divergence reduction over the strongest implementable baseline; online estimator retains at least half the oracle improvement.

## Experiment Handoff Inputs

- **Must-prove:** Closed-loop causal separation; frontier alternative coverage; branch risk gives information beyond current gap; equal-budget terminal improvement.
- **Must-run ablations:** No future amplification, no feedback push-forward, margin only, random alternatives, oracle alternatives.
- **Highest-risk assumptions:** Frontier coverage and task-grounded feedback sensitivity.

## Compute & Timeline Estimate

- GPU-hours: 0.
- A0: 12–36 CPU-hours, less than 100 GB additional NVMe.
- Full study: 1–2 weeks on a 16–32 core machine, 64–128 GB RAM, 100–300 GB NVMe.
