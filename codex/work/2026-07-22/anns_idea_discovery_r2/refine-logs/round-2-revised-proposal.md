# Refined Proposal R2: TraceGuard — Result-Sensitive Stopping for Feedback ANN

## Decision after Round 1

TraceGuard no longer claims a generic HNSW certificate or uses the current query's ranking gap to predict future top-k stability. Its single contribution is **result-sensitive stopping**: spend search work according to how much the unresolved result alternatives can change the next retrieval state, rather than according to current-query hardness alone.

The direction remains **HOLD pending A0**. A low frontier-coverage result kills it; no auxiliary learned model or new index will be added to rescue it.

## Formal problem

Let a length-\(H\) retrieval process have state \(s_t\), query \(q_t=G(s_t)\), exact top-k set \(R_t^*=\operatorname{kNN}(q_t)\), and returned approximate set \(\widehat R_t(b_t)\) after effort \(b_t\). Restrict the feedback class to affine/additive set updates

\[
s_{t+1}=F(s_t,R_t)=A s_t+\frac{\beta}{k}\sum_{x\in R_t}\phi(x)+c.
\]

This includes centroid and Rocchio-style feedback without training. Under a total online search budget \(\sum_t b_t\le B\), choose stopping efforts to minimize terminal exact-reference state divergence

\[
\|s_H-s_H^*\|,
\]

and its cumulative analogue, where the counterfactual trajectory \(s_t^*\) always uses exact top-k at its own exact-reference query. The paper does not claim a generic agent/LLM update, a new ANN graph, or cross-query reuse.

## Coverage event and observable branch bound

At effort \(b\), an anytime graph search exposes its current result set \(C_t(b)\) and a capped set \(U_t(b)\) of discovered but unresolved candidates. For a small integer \(m\), define the exact event

\[
\Omega_t^m(b):
|R_t^*\setminus C_t(b)|\le m
\quad\land\quad
R_t^*\setminus C_t(b)\subseteq U_t(b).
\]

This is **complete result-set coverage**, not per-object hit rate: every omitted exact top-k object must be simultaneously represented, and there may be at most \(m\) misses.

Let \(\mu_C=k^{-1}\sum_{v\in C}\phi(v)\),

\[
a(u)=\|\phi(u)-\mu_C\|,
\qquad
r_C=\max_{v\in C}\|\phi(v)-\mu_C\|.
\]

If \(a_{(1)}\ge\cdots\) are the sorted values for \(u\in U\), define the computable conservative radius

\[
\bar\rho_t^m(b)=\frac{|\beta|}{k}
\left(\sum_{j=1}^{m}a_{(j)}+m r_C\right).
\]

It costs \(O((|U|+k)d+|U|\log m)\), avoids enumerating swap combinations, and handles up to \(m\) simultaneous misses.

### Conditional one-step theorem

If \(\Omega_t^m(b)\) holds, then for the same incoming state and query,

\[
\|F(s_t,R_t^*)-F(s_t,C_t(b))\|
\le \bar\rho_t^m(b).
\]

**Proof sketch.** Pair each omitted exact object with a false positive in \(C_t\). For each pair \((u,v)\), triangle inequality through \(\mu_C\) gives \(\|\phi(u)-\phi(v)\|\le a(u)+r_C\). Sum at most \(m\) pairs and multiply by \(|\beta|/k\). The top-\(m\) discovered-candidate scores upper-bound the omitted-object terms under \(\Omega_t^m\).

This theorem is deliberately conditional. Ordinary HNSW/Vamana provides no guarantee that \(\Omega_t^m\) holds; A0 directly measures its frequency. Across a horizon, if \(F\) and \(G\) have known state amplification bounds \(L_t\), repeated application gives the diagnostic bound

\[
E_H\le \sum_{t=0}^{H-1}
\left(\prod_{j=t+1}^{H-1}L_j\right)\bar\rho_t^m(b_t)
\]

on trajectories whose per-step coverage events hold. This recursion is supporting analysis, not the novelty claim.

## Result-sensitive stopping

At fixed effort checkpoints, TraceGuard recomputes \(\bar\rho_t^m(b)\). It resumes the same search while the amplification-weighted marginal decrease

\[
\frac{w_t[\bar\rho_t^m(b)-\bar\rho_t^m(b+\delta)]}{\operatorname{cost}(\delta)}
\]

exceeds an online shadow price, subject to reserving the minimum effort for all remaining steps. A standard dual update adjusts the price to satisfy \(B\). This accounting rule is intentionally simple; the contribution is the push-forward result sensitivity in \(\bar\rho\), not primal-dual budgeting.

The decisive comparison uses matched queries with similar local recall, exact margin, visited-node count, and DARTH-style hardness but different \(\bar\rho\). If \(\bar\rho\) does not predict future state/terminal loss after this matching, the mechanism is not distinct from dynamic `ef` and is killed.

## Overhead contract

Use \(k=10\), \(m\in\{1,2\}\), and cap \(|U|\le32\) in A0. One radius computation requires at most \((|U|+k)d\) vector arithmetic plus top-\(m\) selection—roughly 42 vector passes in the default case. Implement it incrementally at geometric effort checkpoints, not after every node expansion.

Every main result reports:

1. total exact vector-distance computations;
2. total controller vector operations converted to distance-equivalent work;
3. end-to-end CPU wall-clock time;
4. page reads when an SSD index is used.

If gains exist only when controller overhead is ignored, the direction is killed.

## A0 hard gates

1. **Phenomenon:** at local recall \(\ge0.95\), exact-reference terminal overlap loses at least 15 points for two dataset/law cells after causal decomposition.
2. **Coverage:** \(\Pr[\Omega_t^m]\ge0.90\) for \(m\le2\) at the effort range where intervention matters.
3. **Incremental information:** branch radius predicts one-step state error and terminal loss beyond local recall, exact margin, and single-query hardness; matched-pair effect is significant.
4. **Equal-work win:** at least 25% lower terminal divergence than uniform, margin, and DARTH-style controllers at equal wall-clock, with the same conclusion under distance-equivalent work.
5. **Mechanism:** removing feedback push-forward loses most of the gain; the online rule retains at least 50% of an oracle allocation's improvement.

Failure of Gate 2, Gate 3, or equal-wall-clock Gate 4 is an immediate KILL. We will not add a new index, learned coverage predictor, cache, or future-query preview afterward.

## Defensible contribution if A0 passes

> A result-sensitive ANN stopping rule for feedback retrieval, supported by a conditional multi-miss state-error bound and evidence that result alternatives carry downstream-risk information unavailable to single-query hardness measures.

This is narrower than “trajectory-stable ANN” and does not claim that feedback loops, approximation propagation, dynamic effort, or the Lipschitz recursion are themselves new.
