# Ambiguity-Monotone Graph A0 Paper Gate

**Date:** 2026-07-19

**Executor:** Codex

**Scope:** paper-only formal-object / storage-path / nearest-work gate
**No experiment or implementation was started.**

## 1. Gate outcomes

```text
Z0B = INCONCLUSIVE-IMPLEMENTATION-ERROR
Ambiguity A0 = KILL
```

Z0B did not complete the registered experiment: the campaign fail-stopped on the first DGAI replay, produced no completed trace result, and never ran OdinANN. Its valid capture and the read-only failure audit are useful diagnostics, but they are not a Z0B endpoint result. Under the outcome vocabulary frozen by `vector_direction_gate_2026-07-19.md`, the only honest label is `INCONCLUSIVE-IMPLEMENTATION-ERROR`.

Ambiguity A0 is killed because the original query-independent monotone object cannot support the claimed exact-read decision, while every sound salvage found in this gate is query/search-state dependent and reduces to ordinary interval filtering, page-granular branch-and-bound, metric coverage, or progressive quantization. No salvaged object currently satisfies the gate's requirement to be stronger than existing bound-guided probing and to have a new disk consequence.

## 2. Exact A0 question

The original proposal asks whether one can construct a static graph whose quantized-distance uncertainty intervals shrink monotonically along search paths, and use that property to read an SSD full-precision vector only when its interval overlaps the current top-k boundary.

A0 asks a stricter question:

> Is there a nontrivial query-independent graph property or search invariant that permits deterministic, safe full-vector page skipping, is stronger than ordinary bound-guided exact probing, and yields a real SSD-I/O consequence in coupled or decoupled storage?

The allowed A0 outcomes are `PASS-ORIGINAL`, `PASS-SALVAGED-FORMAL-OBJECT`, and `KILL`.

## 3. Formal model

### 3.1 Objects and observable state

Let $D=\{x_1,\ldots,x_n\}$ be a vector dataset in a metric space $(\mathcal X,d)$. The full-precision vector of each $x$ is stored on an SSD page that may require an exact probe.

Before probing $x$, the search can observe metadata

$$
M(D)=(G,C,A),
$$

where $G$ is a static graph, $C$ contains quantized codes or sound interval annotations, and $A$ is any static node order or rank. A query is $q$. A search history $H$ contains the pages already probed and their exact distances. Once at least $k$ candidates have been verified, $\tau(H)$ is the current $k$-th smallest verified exact distance.

For an unprobed candidate $x$, suppose the metadata produces a sound interval

$$
I_q(x)=[L_q(x),U_q(x)]
$$

with $L_q(x)\le d(q,x)\le U_q(x)$.

The consistency class $\Omega(M,H)$ contains every exact dataset realization that has the same observable metadata and the same results for all pages already probed in $H$. Skipping the exact page of $x$ is **deterministically safe** only if the final exact answer is correct for every realization in $\Omega(M,H)$, using a fixed tie rule.

This definition separates two guarantees:

- **candidate-set exact:** exact top-k only within an already discovered candidate set;
- **global exact:** exact top-k over the full database, which additionally needs a certificate that unseen graph regions cannot contain a better point.

An ANN recall guarantee or a probabilistic confidence interval is not deterministic safe exactness.

### 3.2 Original query-independent object

A query-independent ambiguity-monotone order is a preorder $\preceq_A$ fixed entirely by $M(D)$; it is independent of $q$, $H$, $\tau(H)$, and the verified set. The original topology requires graph edges or allowed paths to be monotone in this order.

The important distinction is that a static order can constrain traversal, but the exact-read decision is a boundary decision involving $q$ and the moving threshold $\tau(H)$.

## 4. Formal triage

### Claim status

```text
Original implication:
static ambiguity-monotone topology => deterministic safe exact-page skipping

Status: NOT CURRENTLY JUSTIFIED; a finite counterexample refutes it.
```

The counterexample does not say that one cannot construct a graph with decreasing interval widths. It says that such monotonicity alone cannot resolve an unprobed candidate whose possible exact distance straddles the current boundary.

### Dependency map

1. The original claim requires static metadata to determine a dynamic top-k boundary decision.
2. The indistinguishability theorem shows that identical metadata and history can hide two exact worlds requiring opposite answers.
3. A static graph/order is already part of the identical metadata, so it cannot distinguish those worlds.
4. Storage-path lemmas then determine whether skipping exact computation actually skips an SSD page.
5. The only sound local exclusion condition becomes a query- and threshold-dependent lower-bound test, i.e. ordinary bound-guided probing.

## 5. Counterexample and impossibility results

### Proposition 1: global exact-distance dominance is empty

Assume the query domain contains the database points. For distinct $x,y\in D$, no fixed orientation can assert that one is closer than the other for every query.

**Proof.** At $q=x$,

$$
d(q,x)=0<d(q,y).
$$

At $q=y$,

$$
d(q,y)=0<d(q,x).
$$

Thus the pairwise exact-distance ordering reverses. A query-independent strict dominance relation valid for all queries therefore contains no distinct-node pair. In particular, no nonempty page can be declared permanently irrelevant to all queries merely by a global static distance-dominance order, because a point on that page can itself be a top-1 query. $\square$

This proposition rules out the strongest interpretation of a global ambiguity order. It does not rule out query-region restrictions or query-conditioned certificates.

### Theorem 2: summary-collision exact-probe lower bound

Fix $q$, history $H$, and current threshold $\tau=\tau(H)$. Suppose there are two exact realizations $D^-,D^+\in\Omega(M,H)$ such that:

1. all information visible without probing candidate $x$ is identical;
2. $d^-(q,x)<\tau<d^+(q,x)$; and
3. the required exact top-k result differs between $D^-$ and $D^+$.

Then any deterministic algorithm that does not probe the exact page containing $x$ is incorrect on at least one of the two realizations.

**Proof.** Because $M$ and all observations in $H$ are identical, an algorithm that does not probe $x$ receives the same observation transcript in $D^-$ and $D^+$. Determinism forces it to make the same state transitions and return the same output in both realizations. Condition 3 says that the correct exact outputs differ. Therefore that common output is wrong in at least one realization. The static graph $G$ and any query-independent order $A$ are components of the identical metadata $M$, so adding a monotonicity property to either one cannot distinguish the two realizations. $\square$

#### Minimal instance

Let $k=1$, $q=0$, and let a verified incumbent $y$ have $d(q,y)=1$, so $\tau=1$. The code for unprobed $x$ admits the sound interval $[0.5,1.5]$.

- In $D^-$, choose $d(q,x)=0.75$; the correct answer is $x$.
- In $D^+$, choose $d(q,x)=1.25$; the correct answer is $y$.

Both worlds have the same complete static graph, quantized code, interval, and arbitrary static order. To additionally satisfy strict path-wise interval-width shrinkage, add a routing node $r$ with $I_q(r)=[0,2]$ and edge $r\rightarrow x$. The width decreases from $2$ to $1$, yet $x$ still straddles $\tau$ and cannot be safely skipped.

Therefore:

$$
\text{monotone interval width along a path}
\not\Rightarrow
\text{safe exact-probe skipping}.
$$

### Corollary 3: the local exclusion rule is ordinary bound-guided probing

Under the interval-realizability assumption used by Theorem 2, an unprobed candidate can be safely excluded from improving the current verified top-k when

$$
L_q(x)>\tau.
$$

If $L_q(x)\le\tau$ and the interval admits a compatible value below $\tau$, there is a consistent realization in which $x$ improves the incumbent; deterministic exclusion is not safe. Thus the lower-bound rule is sufficient and locally necessary under the model. It depends on $q$ and $\tau$, not on a static ambiguity rank.

### Proposition 4: boundary ambiguity cannot be represented by one static rank

For a nondegenerate interval $[L_q(x),U_q(x)]$, the event

$$
L_q(x)\le\tau<U_q(x)
$$

changes as $\tau$ changes. With two candidates, placing two histories' thresholds inside different intervals reverses which candidate is boundary-ambiguous. A static total order independent of $H$ cannot encode all these orderings unless it collapses to a constant or otherwise coarse rank. Ranking only by a query-independent reconstruction radius $\epsilon_x$ does not repair the problem: the decision still depends on the interval center, $q$, and $\tau$.

## 6. Coupled versus decoupled storage

### 6.1 Coupled layout

In the inspected DGAI coupled path, one 4 KiB record contains full coordinates, degree, and neighbor IDs. The beam search selects a frontier, constructs and submits its 4 KiB reads, then parses both adjacency and full coordinates from the returned buffer; exact distance is computed only after the page has arrived.

Consequences:

1. Skipping exact distance after the page arrives saves CPU work or a copy, not the SSD read already issued.
2. Skipping the page before I/O also skips adjacency expansion. A chain `entry -> x -> z`, where $z$ is the nearest neighbor and is reachable only through the edge stored on $x$'s page, is a minimal counterexample: skipping $x$ hides $z$.
3. If multiple nodes share a page, skipping one candidate saves no physical I/O when another candidate already requires the same page.

A coupled design needs a stronger navigation or coverage certificate proving that neither the skipped node nor the graph region reachable only through it can improve the answer. The original candidate interval does not provide that certificate.

### 6.2 Decoupled layout

In the inspected rerank path, topology/PQ navigation is separate from coordinate-page reranking. Candidate IDs are mapped to coordinate pages, duplicate page IDs are removed, each unique coordinate page is read once, and exact distances are then computed.

This layout allows a candidate bound to be applied before coordinate-page submission, but a candidate skip saves physical I/O only when it removes the last required candidate from that page. A sound page rule is therefore based on an aggregate such as

$$
L_q(P)=\min_{x\in P}L_q(x).
$$

Once $k$ exact incumbents exist, an unread page $P$ can be excluded when $L_q(P)>\tau$. Reading pages in lower-bound order and stopping when every unread page satisfies this inequality is page-granular branch-and-bound. It is a valid disk optimization, but it is not a query-independent ambiguity-monotone graph invariant.

## 7. Salvage attempts

### 7.1 Query-conditioned interval-dominance poset

For a fixed query, define

$$
u\prec_q v \quad\Longleftrightarrow\quad U_q(u)<L_q(v).
$$

This is a strict partial order. If $v$ has at least $k$ distinct certified predecessors, $v$ cannot be in the exact top-k. A page can be skipped when a common set of $k$ witnesses is provably closer than every point on the page.

**Why it does not pass:** it depends on $q$ and is exactly interval dominance / bound-guided probing, aggregated at page granularity.

### 7.2 Query-region certified page dominance

Partition a restricted query domain into cells $C$. A page $P$ with $k$ witnesses $W$ can carry a robust certificate

$$
\max_{w\in W}\sup_{q\in C}U_q(w)
<
\inf_{q\in C,\,v\in P}L_q(v).
$$

Then $P$ is safely skipped for every $q\in C$.

**Why it does not pass now:** it abandons the original global object, may be empty for broad cells, and increasingly resembles query partitioning, Voronoi/metric-tree pruning, learned routing, or a precomputed branch-and-bound certificate as cells are refined. No new space/I/O bound or nearest-work distinction has been established.

### 7.3 Certified coverage cut

A frontier node or page $v$ may summarize a covered region $R(v)$ and expose an admissible lower bound

$$
B(q,v)\le\min_{z\in R(v)}d(q,z).
$$

If $B(q,v)>\tau$, the region can be pruned.

**Why it does not pass:** this is a valid global-exact invariant, but it is a metric coverage hierarchy rather than an ambiguity-monotone ANN graph. The method family is ordinary hierarchical metric indexing.

### 7.4 Progressive per-candidate refinement

Nested codes can provide

$$
I_q^0(x)\supseteq I_q^1(x)\supseteq\cdots,
$$

so uncertainty shrinks as more bits are fetched. This can safely decide whether to fetch a full vector.

**Why it does not pass:** monotonicity is over information refinement for one candidate, not over graph topology; the mechanism is progressive quantization plus bound probing.

### 7.5 Heuristic or probabilistic score

A score such as

$$
\widehat d(q,x)+\lambda\epsilon_x
$$

may prioritize probes, but a tuned $\lambda$, expected ambiguity, or learned confidence does not provide deterministic exact-read safety. If graph candidate discovery fails with probability $\delta_g$ and quantized filtering fails with probability $\delta_q$, a union bound can at most support a probabilistic statement such as recall $\ge 1-\delta_g-\delta_q$ under the relevant assumptions. It is not a safe exact certificate.

## 8. Nearest-work and local implementation pressure

The literature pressure is not merely name overlap:

- [RaBitQ](https://arxiv.org/abs/2405.12497) supplies theoretically bounded quantized distance estimation. Restoring a sound error bound and applying $L_q(x)>\tau$ would therefore be a RaBitQ-style bound plus ordinary exact probing, not a new static graph invariant.
- [SymphonyQG](https://arxiv.org/abs/2411.12229) already couples graph search and quantization and refines graph behavior for quantized batch processing.
- [δ-EMG / δ-EMQG](https://arxiv.org/abs/2511.16921) develops provably monotonic graph structure and an error-bounded quantized variant.
- [QuIVer](https://arxiv.org/abs/2605.02171) uses low-bit quantized representations for topology construction, pruning, and navigation before final full-precision reranking.
- [SkipDisk](https://arxiv.org/abs/2605.05787) applies per-point lower bounds and decouples in-memory traversal from disk access.
- [GateANN](https://arxiv.org/abs/2603.21466) likewise separates navigation information from full-vector SSD reads and avoids reads for nonmatching regions.

The local OdinANN-PipeANN code strengthens this concern. Its RaBitQ library computes an `f_error` distance-estimation error bound, while the integration explicitly says `drop f_error as we do not use it` and `Do not save f_error`. Reintroducing this bound could enable a useful engineering filter, but the resulting mechanism is precisely the error-bound-plus-probe design excluded by the A0 novelty gate.

The exact details of SymphonyQG in older local secondary notes are inconsistent, and no local copies of those papers were found. The external primary abstracts above were used only for high-level family boundaries; no stronger implementation claim relies on the conflicting secondary description.

## 9. Failed assumptions

1. **Ambiguity is node-static.** Boundary ambiguity depends on $q$, $\tau$, the interval center, and verified candidates.
2. **Path-wise interval shrinkage implies safe skipping.** The two-world counterexample preserves strict width shrinkage and still requires a probe.
3. **Skip exact computation means skip SSD I/O.** This is false in the coupled path once the record page has arrived.
4. **Skip one candidate means skip one page.** The decoupled path deduplicates by coordinate page.
5. **A safe lower-bound filter is a new graph invariant.** Its sound form is ordinary query-conditioned branch-and-bound.
6. **A probabilistic ambiguity score is an exact certificate.** It supports only an explicitly approximate guarantee.
7. **Disk residence alone distinguishes the idea.** Existing quantized traversal, lower-bound filtering, and navigation/data separation already cover the underlying mechanisms.

## 10. Final A0 outcome

```text
KILL
```

`PASS-ORIGINAL` fails because a static ambiguity-monotone topology does not determine a threshold-crossing exact-read decision.

`PASS-SALVAGED-FORMAL-OBJECT` also fails at this gate. The mathematically valid salvages all introduce query/threshold dependence, restrict the query domain, add metric coverage summaries, or refine per-candidate codes. None currently demonstrates an invariant stronger than ordinary bound-guided probing together with a distinct disk-system guarantee.

The query-region page certificate is the least trivial residual object, but it remains an unproven nearest-work question rather than a pass. It should not trigger implementation.

## 11. What the result proves and does not prove

### Proves

- A global query-independent exact-distance dominance order is nontrivial only after restricting the query domain.
- Static path-wise interval shrinkage does not imply deterministic safe skipping of an overlapping exact candidate.
- In the inspected coupled layout, skipping post-read exact computation does not save the already issued page I/O.
- In the inspected decoupled layout, the sound local/page exclusion rule is query- and threshold-dependent branch-and-bound.

### Does not prove

- that quantization/topology co-design is impossible;
- that approximate or distribution-specific probe scheduling cannot help;
- that restricted query-region certificates can never yield a useful index;
- that progressive quantization is ineffective;
- that RaBitQ, SymphonyQG, δ-EMQG, QuIVer, SkipDisk, or GateANN solve every disk-ANN workload;
- that ZNS itself is killed by the incomplete Z0B campaign.

## 12. Z0B evidence boundary

The stopped Z0B campaign has one valid DGAI-r1 capture: 118,314 raw requests normalized to 1,789,699 4 KiB events plus one lifecycle event, with zero capture drops/failures and exact raw/normalized/final-live closure. The first registered `256MiB / spare=2 / Canonical / Greedy` replay could not append event ordinal 97,870. The read-only diagnostic found that all 54 non-reserve zones were full with zero invalid blocks and the only empty zone was the relocation reserve after approximately 44 reclaim cycles. Thus this is not a no-GC prefix.

However, that diagnostic was not a registered successful replay result. The controller fail-stopped, DGAI completed 0/3, OdinANN completed 0/3, and no 288-config analyzer outcome exists. It cannot answer whether the intended long sequences yield stable non-Oracle reclaim behavior. This is why the new gate vocabulary requires `INCONCLUSIVE-IMPLEMENTATION-ERROR`, not PASS and not a silently repaired continuation.

## 13. Reproduction map

### Gate and prior proposal

- `gpt/share/2026-07-19/vector_direction_gate_2026-07-19.md`
- `gpt/share/2026-07-19/claude_ann_candidate_directions_strict_review_0719.md`
- `claude/share/2026-07-18/idea_report_phase2_merged_0718.md`
- `claude/share/2026-07-18/idea_report_phase3_novelty_0718.md`

### Z0B failure record

- `codex/share/2026-07-19/zns_ann_z0b/z0b_failure_disposition_request.md`
- `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/z0b_sequence_endpoint_reclaim_0719/CAMPAIGN_FAILED.json`

### Storage-path source evidence

- `/home/ubuntu/pz/VectorDB/brainstorm/codex/execution_paths.md`
- `/home/ubuntu/pz/VectorDB/repos/DGAI/src/search/beam_search.cpp`
- `/home/ubuntu/pz/VectorDB/repos/DGAI/src/search/rerank_search.cpp`
- `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/src/OdinANN-PipeANN/include/nbr/rabitq_nbr.h`
- `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/src/OdinANN-PipeANN/include/nbr/rabitq/utils/rabitq_impl.hpp`

### Read-only commands

```bash
sed -n '97,157p' gpt/share/2026-07-19/vector_direction_gate_2026-07-19.md
sed -n '291,360p' gpt/share/2026-07-19/claude_ann_candidate_directions_strict_review_0719.md
sed -n '15,81p' ../brainstorm/codex/execution_paths.md
sed -n '124,194p' ../repos/DGAI/src/search/beam_search.cpp
sed -n '1129,1257p' ../repos/DGAI/src/search/rerank_search.cpp
rg -n -C 4 'f_error|g_error' ../data/VectorDB/dynamic_vamana_atlas/src/OdinANN-PipeANN/include/nbr/rabitq_nbr.h ../data/VectorDB/dynamic_vamana_atlas/src/OdinANN-PipeANN/include/nbr/rabitq/utils/rabitq_impl.hpp
```

No experiment command is needed to reproduce the A0 proof. No PageTxn code, broad idea-discovery run, or new Z0B replay was started.
