# Ambiguity-Monotone Graph A0 Final Gate

**Date:** 2026-07-19

**Executor:** Codex

**Scope:** paper-only definition, counterexample, source-path, nearest-work, and theorem gate

**Execution constraint:** no experiment, implementation, PageTxn work, Z0B restart, or broad idea-discovery was performed.

## 1. Final status

```text
Z0B = failed_stopped; formal results 0/6; not a completed Z0B result
Ambiguity A0 = KILL
```

The A0 outcome is `KILL`, not `PASS-SALVAGED-FORMAL-OBJECT`. The original interval-width monotonicity is query-dependent and does not imply a safe exact-read decision. In the inspected coupled path, skipping exact computation after page arrival saves no distinct SSD page. In the decoupled path, the sound page rule is ordinary query-time branch-and-bound. Under a restricted same-information model, a mandatory static width order can be arbitrarily worse than lower-bound scheduling. Broader page-layout, coverage, or metadata-access salvages are not proved impossible, but no completed non-toy theorem or nearest-work separation was produced for them in this gate.

## 2. Z0B read-only status

At `2026-07-19 20:42:54 UTC+8`, the frozen status tool reported:

```text
state=failed_stopped
traces=0/6 (0.0%)
stage=21.43% [not time percentage]
ETA=stopped after failure
dgai-50k-r1=failed
dgai-50k-r2/r3=prepared
odinann-400k-r1/r2/r3=prepared
```

No Z0B process is running. `CAMPAIGN_FAILED.json` records the fail-stop at `2026-07-19 18:24:02 UTC+8`, with `retry_permitted=false`. The failed run also records `attempt_reuse_permitted=false`. The requested completed report `codex/share/2026-07-19/zns_ann_z0b_sequence_endpoint_reclaim_0719.md` does not exist.

The first DGAI capture closed its raw, normalized, and final-live ledgers, but the first registered replay failed; no full trace result completed and OdinANN never ran. The prior read-only semantic diagnostic therefore remains implementation/failure evidence, not a Z0B endpoint result. It is not legal to assign the old completed-result vocabulary `PASS-RECLAIM-SIGNAL / HOLD-PLACEMENT-DOMINATED / KILL-NO-RECLAIM-SIGNAL` to an experiment with 0/6 completed results. Under the newer direction gate, the appropriate description is `INCONCLUSIVE-IMPLEMENTATION-ERROR`.

## 3. Exact original claim

Claude's proposal was:

> Construct graph edges such that quantized distance intervals shrink monotonically along search paths, and issue an SSD full-precision read only when a candidate's interval overlaps the current top-k boundary.

The intended causal chain is:

$$
\text{static quantization-aware topology}
\Longrightarrow
\text{monotone uncertainty along traversal}
\Longrightarrow
\text{fewer exact vector probes}
\Longrightarrow
\text{fewer distinct SSD pages}.
$$

A0 tests every implication rather than treating the chain as a heuristic.

## 4. Definitions and quantifiers

### 4.1 Metric and interval metadata

Let $V$ be a finite dataset in metric space $(\mathcal X,d)$. Each point $v\in V$ has lossy metadata $m(v)$. For query $q\in Q$, metadata yields a sound distance interval

$$
I_q(v)=[L_q(v),U_q(v)],
\qquad
L_q(v)\le d(q,v)\le U_q(v),
$$

and width

$$
W_q(v)=U_q(v)-L_q(v).
$$

Let the verified search state at step $t$ contain at least $k$ exact distances, and let $\tau_t$ be its current exact $k$-th distance. With a fixed no-tie rule, define boundary ambiguity

$$
A(q,\tau_t,v)=
\mathbf 1\{L_q(v)\le\tau_t\le U_q(v)\}.
$$

Unlike a node label, $A$ depends on the query and evolving search state.

### 4.2 Faithful versions of uncertainty monotonicity

The statement “intervals shrink monotonically along search paths” has three possible meanings.

**Strong edge uncertainty-monotonicity (edge-UM):**

$$
\forall q\in Q,\ \forall (u,v)\in E,
\quad W_q(v)\le W_q(u).
$$

**Navigable path uncertainty-monotonicity (path-UM):** for each query and its true nearest neighbor $x^*(q)$, there exists an entry-to-$x^*$ path $(v_0,\ldots,v_s)$ such that

$$
W_q(v_{i+1})\le W_q(v_i)
\quad\text{for every }i.
$$

**Interval-containment monotonicity:**

$$
I_q(v_{i+1})\subseteq I_q(v_i).
$$

The third is much stronger and generally incompatible with moving distance centers. The first two are the most faithful formalizations of the original words, but both speak only about width. Neither is a safe read-skipping condition.

### 4.3 Safe exact exclusion

Given a candidate set $C$, exact top-k IDs and distances, fixed tie handling, and interval values that may be independently realized, excluding an unprobed candidate $v$ is deterministically safe when every exact realization consistent with all visible metadata and prior probes has the same final top-k answer.

The local sufficient rule is

$$
L_q(v)>\tau_t.
$$

If $U_q(v)<\tau_t$, the candidate is certified to improve the current threshold; this is not a reason to discard it. If the final answer must include its exact distance, it still needs an exact probe unless its metadata is lossless.

For global exactness, the candidate-set rule is insufficient: unseen graph regions also require a sound coverage certificate.

## 5. Complete numerical counterexamples

All examples use a one-dimensional Euclidean metric and the standard reconstruction-center plus residual-radius interval

$$
I_q(v)=
[\max(0,|q-c_v|-r_v),\ |q-c_v|+r_v].
$$

### 5.1 Query-dependent interval-width order reversal

Let

$$
a:(c_a=0,r_a=3),
\qquad
b:(c_b=10,r_b=2).
$$

For $q_1=0$:

$$
I_{q_1}(a)=[0,3],\quad W_{q_1}(a)=3,
$$

$$
I_{q_1}(b)=[8,12],\quad W_{q_1}(b)=4.
$$

Thus $a$ is less uncertain than $b$.

For $q_2=10$:

$$
I_{q_2}(a)=[7,13],\quad W_{q_2}(a)=6,
$$

$$
I_{q_2}(b)=[0,2],\quad W_{q_2}(b)=2.
$$

Now $b$ is less uncertain than $a$. The order strictly reverses. A fixed orientation $a\rightarrow b$ or $b\rightarrow a$ violates width descent for at least one query.

This reversal uses the nonnegative clipping that a distance interval requires. If an implementation stores only a query-independent radius and reports an unclipped width $2r_v$, width becomes static, but the actual boundary ambiguity still reverses.

### 5.2 Boundary-ambiguity reversal with equal static widths

Let

$$
a:(c_a=0,r_a=0.25),
\qquad
b:(c_b=10,r_b=0.25),
\qquad
\tau=1.
$$

For $q_1=0.8$:

$$
I_{q_1}(a)=[0.55,1.05]
$$

overlaps $\tau$, while

$$
I_{q_1}(b)=[8.95,9.45]
$$

has lower bound above $\tau$ and is safely filterable.

For $q_2=9.2$, the intervals swap roles:

$$
I_{q_2}(b)=[0.55,1.05]
$$

is ambiguous, while

$$
I_{q_2}(a)=[8.95,9.45]
$$

is filterable. Both static radii and both widths are equal, yet the required probe priority reverses with the query.

### 5.3 A wider far interval is filterable; a narrower near interval is ambiguous

Let $q=0$ and suppose verified exact results give $\tau=1$.

Near candidate $n$ has

$$
c_n=1,\quad r_n=0.1,
\quad I_q(n)=[0.9,1.1],
\quad W_q(n)=0.2.
$$

The interval crosses the threshold. The two compatible distances $0.95$ and $1.05$ require opposite membership decisions, so $n$ cannot be safely excluded.

Far candidate $f$ has

$$
c_f=7,\quad r_f=2,
\quad I_q(f)=[5,9],
\quad W_q(f)=4.
$$

Although its interval is $20\times$ wider, $L_q(f)=5>\tau$, so it is safely filtered without an exact probe.

Therefore interval width is not the relevant order:

$$
W_q(n)<W_q(f)
\quad\text{but}\quad
n\text{ requires a probe and }f\text{ does not}.
$$

### 5.4 Strict path shrinkage still cannot skip an overlapping candidate

Let $k=1$, $q=0$, and let verified incumbent $y$ have exact distance $1$, so $\tau=1$. Let routing node $r$ have interval $[0,2]$ and candidate $x$ have interval $[0.5,1.5]$, with edge $r\rightarrow x$. Width strictly shrinks from $2$ to $1$.

Use one code cell with reconstruction center $c_x=1$ and radius $r_x=0.5$. Two exact worlds can place $x$ at different locations inside that same cell:

- $D^-$ sets $d(q,x)=0.75$, so $x$ must replace $y$;
- $D^+$ sets $d(q,x)=1.25$, so $y$ remains top-1.

Take $G$ to be the same fixed chain in both worlds (or a graph constructed from the shared code rather than the hidden residual). Both worlds then share graph, code, intervals, static order, and prior observations. An algorithm that skips $x$ has the same transcript and output in both worlds and is wrong in one. Thus strict path-UM **alone** does not imply safe exact skipping. This does not refute an exact-vector-dependent graph whose differing topology encodes additional information about the hidden residual; such topology must instead be charged as a stronger summary.

## 6. Formal results

### Proposition 1: fixed pairwise exact-distance dominance fails over the full query domain

Assume the query domain contains the database points. For distinct $x,y\in V$, at $q=x$,

$$
d(q,x)=0<d(q,y),
$$

while at $q=y$,

$$
d(q,y)=0<d(q,x).
$$

Every fixed pairwise exact-distance orientation reverses. Therefore no nonempty strict node dominance order is valid for all queries. A nontrivial salvage must restrict the query region or depend on the query.

### Theorem 2: indistinguishability lower bound

Let $M$ include the graph, quantized metadata, static ranks, and all already probed results. If two exact realizations $D^-,D^+$ have the same $M$, but an unprobed $x$ lies below $\tau$ in one and above $\tau$ in the other and the exact top-k answers differ, then any deterministic algorithm that does not probe $x$ fails on one realization.

**Proof.** Without probing $x$, every observation and state transition is identical in the two realizations. Determinism produces one common output, while the correct outputs differ. Therefore the common output is wrong in at least one realization. Adding a static monotone graph does not help because it is already part of identical $M$. $\square$

**Status under proof-writer triage:** the original implication is false as stated. The corrected negative claim is `PROVABLE AS STATED` under the explicit consistency-class and deterministic-exact assumptions above.

## 7. Coupled DGAI: step-by-step I/O accounting

### 7.1 Three page counters

For one query, distinguish:

- $N_{logical}$: logical node/candidate requests constructed by search code;
- $N_{submitted}$: 4 KiB requests submitted after software cache/reuse;
- $N_{distinct}$: distinct submitted SSD page addresses.

Device-controller or NAND reads may be lower; source code cannot establish them. The A0 system claim is therefore audited at $N_{distinct}$.

### 7.2 Coupled record and beam path

The coupled DGAI record contains exact coordinates plus degree/neighbor IDs. `SECTOR_LEN` is 4096 bytes. The beam path is:

1. Select frontier candidates (`beam_search.cpp:121-140`).
2. Map each frontier ID to its record location/page and construct an `IORequest` (`:142-162`).
3. Submit `read/read_alloc` (`:163-168`).
4. After page arrival, use one `node_disk_buf` to parse neighbors and exact coordinates (`:176-194`).
5. Copy coordinates and compute exact distance (`:184-192`).
6. Expand adjacency and compute neighbor PQ distances from DRAM codes (`:194-227`).
7. Sort expanded nodes by exact distance (`:282-284`).

The proposed ambiguity check, if inserted immediately before exact computation in step 5, occurs after step 3. Therefore:

$$
\Delta N_{submitted}=0,
\qquad
\Delta N_{distinct}=0.
$$

It can save only copy/compute work.

To save the page, the decision must occur before step 3 and must also skip adjacency expansion. A chain `entry -> x -> z`, where the nearest neighbor $z$ is reachable only through adjacency stored on $x$'s page, shows why a candidate distance bound is insufficient: skipping $x$ makes $z$ undiscoverable.

### 7.3 Exact distinct-page condition

Let $E$ be expanded nodes, $p(x)$ their page mapping, and $H$ pages already resident before the reads. Ignoring an observed same-batch duplicate-request artifact, the theoretical distinct misses are

$$
N_{distinct}=|\{p(x):x\in E\}\setminus H|.
$$

Removing a candidate subset $S$ strictly reduces distinct pages if and only if there exists a page $P\notin H$ such that every expanded node on $P$ is removed:

$$
E\cap p^{-1}(P)\subseteq S.
$$

Removing one node does not save a page if another expanded node on that page remains or if the page was already resident.

The existing `stats->n_ios/n_4k` increments per frontier node and cannot be interpreted as distinct SSD pages. The software page cache is consulted in `linux_aligned_file_reader.cpp:738-768`; repeated pages across iterations may hit it, while two same-page requests in one batch may both miss before either is inserted.

## 8. Decoupled DGAI: page-level condition

The decoupled rerank path separates topology/PQ navigation from coordinate pages:

1. Build the PQ candidate heap (`rerank_search.cpp:349-389`).
2. Submit/reuse topology-page reads (`:394-543`).
3. Parse topology and expand with PQ, without exact coordinates (`:601-771`).
4. Truncate the PQ result set and map IDs to coordinate page IDs (`:959-1161`).
5. Deduplicate coordinate pages (`:1164-1177`).
6. Create one request per unique coordinate page and submit (`:1186-1224`).
7. Copy exact coordinates, compute exact distances, and sort (`:1232-1272`).

Let candidate subset on coordinate page $P$ be

$$
C_P=\{x\in C:p(x)=P\}.
$$

Filtering candidates reduces distinct coordinate pages if and only if it empties at least one $C_P$. Candidate-count reduction alone is insufficient.

Given at least $k$ verified exact results, a sound page lower bound is

$$
L_q(P)=\min_{x\in C_P}L_q(x).
$$

The page can be safely excluded when

$$
L_q(P)>\tau_t
$$

(or the tie-aware equivalent). Reading pages in ascending $L_q(P)$, updating $\tau_t$, and stopping when all unread page bounds exceed $\tau_t$ is exactly page-granular branch-and-bound/filter-and-refine. It is a valid I/O optimization but not a static uncertainty-monotone graph invariant.

## 9. Strict nearest-work verification

Primary paper PDFs were downloaded to `/tmp` and checked in full text; they were not added to the repository.

| Work | Publication state checked | What the primary source establishes | Boundary against A0 |
|---|---|---|---|
| [RaBitQ](https://arxiv.org/abs/2405.12497), Gao & Long | SIGMOD 2024 | $D$-bit randomized quantization, unbiased distance estimator, and a sharp **probabilistic** error bound; efficient bit/SIMD estimation | Supplies the error-bound ingredient. Applying its bound to exact probing is bound-guided filtering, and probabilistic bounds do not become deterministic exact certificates automatically. |
| [SymphonyQG](https://arxiv.org/abs/2411.12229), Gou et al. | SIGMOD 2025 | Replicates neighbor quantization codes, uses FastScan batch estimates, avoids explicit reranking, and refines graph structure for in-batch computation | Shares the graph/quantization co-design ingredient. It does not cover deterministic exact page admission, but A0 cannot claim first quantization-aware topology. |
| [QuIVer](https://arxiv.org/abs/2605.02171), Xiao et al. | arXiv preprint v3, 2026 | Performs Vamana edge selection, diversity pruning, and beam navigation in a 2-bit Sign-Magnitude BQ space; float32 is used only for final reranking; reports a workload applicability boundary | Shares the quantized-topology ingredient. It is empirical/approximate rather than an exact safe page certificate. |
| [δ-EMG / δ-EMQG](https://arxiv.org/abs/2511.16921), Xiang et al. | arXiv preprint v1, 2025 | $\delta$-monotonic graph with approximation guarantees for arbitrary queries; localized degree-balanced quantized variant preserves theoretical guarantees | Shares monotonic graph and quantized search, but its geometric monotonicity and approximation target are not query-evolving interval ambiguity or SSD page admission. |
| [DGAI](https://arxiv.org/abs/2510.25401), Lou et al. | arXiv preprint v5, 2026 | Physically decouples topology and raw vectors, uses hierarchical PQ to identify promising candidates, then exactly refines a small number of raw vectors; also co-designs placement | Directly instantiates the decoupled candidate-to-coordinate-page pipeline in which A0's remaining rule becomes page-level reranking. |
| [SkipDisk](https://arxiv.org/abs/2605.05787), Song et al. | technical report, 2026 | Uses per-point pivots for tighter lower bounds, filters candidates before full-vector disk access, stores neighbors in memory to decouple traversal from disk access, and overlaps I/O | Directly occupies lower-bound-driven disk-read skipping plus decoupled navigation. A0 would need a theorem beyond this filter-and-refine family. |

These works do not collectively prove that no new disk ANN, graph-conditioned page certificate, or ambiguity-aligned layout is possible. They establish that the ingredients—quantized topology, monotonic approximate navigation, decoupled exact refinement, and lower-bound page filtering—are already separate known mechanisms. The proposed combination needs a new theorem or separation; a new name is insufficient.

## 10. Local DGAI and RaBitQ code verification

The checked `/VectorDB/repos/DGAI` baseline uses PQ in the audited paths; it does not contain `rabitq_nbr.h`. The RaBitQ integration is a distinct local tree under `dynamic_vamana_atlas/src/OdinANN-PipeANN` and must not be described as the same checkout.

In that OdinANN integration:

- the library computes `f_error` and documents it as a distance-estimation error bound (`rabitq_impl.hpp:60-116`);
- the integration explicitly states `drop f_error as we do not use it` (`rabitq_nbr.h:255-268`);
- serialization states `Do not save f_error` (`:369-386`);
- estimators accept `g_error` but do not use it in their bodies (`:400-417`).

Thus the current local path returns a point estimate, not a sound lower/upper interval for safe page admission. Restoring an error term would still require validating whether its guarantee is deterministic or probabilistic and how it composes over candidates. Even if valid, applying it to $L_q(P)>\tau_t$ remains bound-guided reranking rather than a new static topology invariant.

## 11. Certified Rerank-Minimizing Graph and query-time scheduling

### 11.1 Policy class and same-information domination observation

Fix a consistency class $\Omega(M)$ defined by visible metadata $M$:

- a decoupled candidate set $C$ is already discovered;
- candidate intervals and coordinate-page packing are fixed and visible;
- one page probe reveals exact distances for every candidate stored on that page;
- metadata inspection and lower-bound evaluation are free in this restricted model;
- exact top-k IDs and distances are required;
- ties use a fixed rule.

An admissible policy maps only its visible metadata and prior probe transcript to its next page; it cannot inspect hidden exact values. It must be correct for **every** realization in $\Omega(M)$. Let $\mathcal A(M)$ be this class of non-clairvoyant correct policies. For realized instance $D\in\Omega(M)$, define the standard per-instance benchmark

$$
\operatorname{OPT}_{\Omega}(D)
=
\inf_{A\in\mathcal A(M)}\operatorname{cost}_A(D).
$$

Every policy in the infimum remains correct across the whole consistency class; the algorithm itself is not given $D$. The infimum is evaluated per instance, as in an instance-optimal comparison.

If CRMG has exactly the same $M$, its scheduler is one member of $\mathcal A(M)$, so

$$
\operatorname{OPT}_{\Omega}(D)
\le
\operatorname{cost}_{CRMG}(D).
$$

This is a **same-information domination observation**, not a substantive CRMG impossibility theorem: it is true by definition for every admissible algorithm. It only prevents the incoherent claim that a new schedule uses fewer probes than the unconstrained optimum with the same information.

It does not rule out a graph as a compact data structure that implements the same probe optimum with fewer metadata accesses, nor a graph that changes the metadata, candidate set, packing, or coverage information. Those require a different cost model and comparison.

### 11.2 Conditional page-level instance-optimal theorem

To obtain a non-tautological statement, impose the following stronger product-interval model:

1. $C$ is partitioned into coordinate pages $\mathcal P$.
2. Every interval value can be realized independently of every other interval while preserving $M$.
3. A page probe reveals exact distances for all candidates on that page.
4. All intervals needed in the answer are non-lossless; no exact result distance is already encoded in metadata.
5. There are no exact-distance ties, and for the realized final threshold $\tau^*$ no page lower bound equals $\tau^*$.
6. Metric, shared-codebook, graph-construction, and same-page correlations impose no extra joint constraint beyond the intervals.

Define

$$
L_q(P)=\min_{x\in P}L_q(x).
$$

**Theorem.** In this product model, the policy that probes pages in nondecreasing $L_q(P)$, maintains the exact $k$-th threshold, and stops when the next page lower bound exceeds the threshold is instance-optimal in page probes. On realized instance $D$, it reads exactly

$$
\mathcal P^*(D)=\{P\in\mathcal P:L_q(P)<\tau^*(D)\}.
$$

**Proof, sufficiency.** Every true top-k candidate has exact distance at most $\tau^*$. Soundness gives its page lower bound at most its distance; assumptions 4–5 make the relevant comparison strict. Thus all pages needed to reveal the exact top-k IDs and distances occur in $\mathcal P^*$. After the ordered policy reads all pages in $\mathcal P^*$, it has the exact top-k threshold $\tau^*$. Every unread page has lower bound greater than $\tau^*$ and cannot change the result, so the policy stops correctly.

**Proof, necessity.** Suppose a correct policy does not read some $P\in\mathcal P^*$. Choose $x\in P$ with $L_q(x)<\tau^*$. By independent realizability and the no-boundary condition, there is a realization consistent with the identical transcript in which $d(q,x)<\tau^*$, while probed-page results stay fixed. The exact top-k IDs or distances then differ, but the policy returns the same output because it never reads $P$. This contradicts correctness over $\Omega(M)$. Hence every correct policy reads every page in $\mathcal P^*$, and the ordered policy is instance-optimal. $\square$

**Limits.** Independent realizability is decisive and is not established for a real metric, shared quantizer, graph, or page. Joint constraints can certify a page even when its pointwise minimum lower bound is small. Lossless intervals and ties require separate handling. Metadata scans and bound evaluations are treated as free. Therefore this is a conditional baseline theorem, not an unconditional KILL of every graph-conditioned certificate.

### 11.3 No finite approximation for a mandatory width-probe order

Consider $k=1$ with $n$ distractors $d_1,\ldots,d_n$ followed by good candidate $g$. Let a mandatory width-monotone order be

$$
d_1\rightarrow d_2\rightarrow\cdots\rightarrow d_n\rightarrow g.
$$

Assign each distractor an interval

$$
I(d_i)=[2,2+w_i],
\qquad
w_1>w_2>\cdots>w_n>1,
$$

and exact distance $3$. Let

$$
I(g)=[0,1],
\qquad
d(q,g)=0.
$$

Widths strictly decrease along the entire chain. A policy forced to exact-probe in that order uses $n+1$ probes. An optimal lower-bound scheduler probes $g$ first, obtains $\tau=0$, and filters every distractor because its lower bound is $2$, using one probe. The ratio is $n+1$ and is unbounded.

This result is conditional on interpreting the graph order as a mandatory exact-probe order. It refutes that specific policy class, not general CRMG. If topology can be traversed without exact probes and CRMG may reschedule all discovered candidates optimally, the counterexample does not apply; the graph may then match ordinary lower-bound scheduling, but width monotonicity still supplies no demonstrated probe advantage.

### 11.4 Distinct-page objective

For pages rather than candidates, the mandatory exact objects are aggregated by page. Better packing can reduce the number of pages containing unresolved candidates. That can be a legitimate page-layout theorem, but it is not a consequence of node-wise uncertainty-width monotonicity.

### 11.5 Structural-theorem verdict

The complete structural result obtained here is conditional and negative:

> In the independent product-interval model, page lower-bound scheduling is instance-optimal; if width order is forced to be exact-probe order, width monotonicity has no finite approximation guarantee.

This leaves three plausible broader targets—ambiguity-aligned packing, query-region coverage certificates, and sublinear metadata-access scheduling—but this gate produced no proved non-toy positive separation, approximation, or space–I/O theorem for any of them.

## 12. Salvage audit

### Query-conditioned interval dominance

Define $u\prec_q v$ when $U_q(u)<L_q(v)$. This is a strict partial order and can certify that $v$ is not top-k when $k$ certified predecessors exist. It depends on $q$ and is ordinary interval dominance.

### Query-region page certificate

For query cell $R$, page $P$, and $k$ witnesses $W$, a robust certificate such as

$$
\max_{w\in W}\sup_{q\in R}U_q(w)
<
\inf_{q\in R,v\in P}L_q(v)
$$

can safely skip $P$ in that cell. It abandons the global object and approaches query partitioning, Voronoi/metric trees, or precomputed branch-and-bound. No new space–I/O theorem was found.

### Coverage cut

A frontier summary $B(q,v)\le\min_{z\in R(v)}d(q,z)$ can prune a covered region when $B(q,v)>\tau$. This is a valid global-exact invariant but is a metric coverage hierarchy, not the proposed ambiguity topology.

### Progressive codes

Nested intervals $I_q^0(x)\supseteq I_q^1(x)\supseteq\cdots$ can safely refine one candidate before reading a full vector. This is progressive quantization plus bound probing, not monotonicity across graph nodes.

### Ambiguity-aligned page layout

One could place candidates that are jointly ambiguous or jointly filterable under a query distribution onto the same pages and seek an expected distinct-page separation over query-oblivious packing. This is a coherent, non-toy target, but it is a layout/distribution theorem rather than the original graph-width invariant. No construction, lower bound, or prior-work separation was completed in A0.

### Sublinear metadata-access scheduler

A graph or hierarchy could seek the same exact-page probe count as a full lower-bound scan while evaluating only a sublinear number of bounds. This changes the cost objective from SSD probes alone to metadata/DRAM work plus I/O. It is not ruled out by the same-information observation, but A0 has no proved algorithm or complexity separation for it.

These possibilities prevent an unconditional claim that every future CRMG-like object is impossible. They do not meet the current gate's `PASS-SALVAGED-FORMAL-OBJECT` requirements: no precise completed construction, non-toy positive theorem, and strict nearest-work distinction are present now.

## 13. Independent adversarial review

An independent read-only reviewer returned `REJECT current draft; KILL-original supported`. Its strongest objection was that the first draft presented the definitional inequality `OPT <= CRMG` as a substantive impossibility result and left `OPT` vulnerable to a clairvoyant interpretation. It also found that independent interval realizability was doing essential work but was not sufficiently exposed.

The reviewer independently verified:

- all arithmetic in Sections 5.1–5.3, including the $20\times$ width ratio;
- the logic of the two-world example after requiring a shared code cell and fixed observable graph;
- the coupled post-read `zero distinct-page saving` conclusion for the inspected source path;
- the decoupled page-minimum lower-bound rule for candidate-set exact reranking.

Mandatory corrections made after review:

1. `OPT` is now defined over non-clairvoyant policies correct for every realization in one consistency class.
2. `OPT <= CRMG` is labeled a same-information observation, not a new lower bound.
3. The page-level instance-optimal theorem now states product realizability, page reveal semantics, tie/lossless boundaries, and free metadata-access assumptions and includes a proof.
4. The unbounded example is restricted to mandatory width-probe order and no longer claims to refute general CRMG.
5. Coupled I/O language is restricted to the inspected insertion point and layout.
6. Prior-work descriptions now say “shares an ingredient” rather than claiming the works occupy the exact same formal object.
7. Ambiguity-aligned layout, query-cell coverage, and sublinear metadata access are recorded as coherent but unproved salvage classes.

The reviewer could not produce a positive separation under the **same candidate/bounds/layout and SSD-probe-only model**, which would contradict the benchmark definition. It did identify positive targets only after changing packing, coverage metadata, or the online-cost model. Because none was developed into the precise theorem and nearest-work distinction required by this A0 gate, they do not change the final `KILL` outcome for the submitted idea.

After the corrections, the same independent reviewer returned `ACCEPT`: the conditional page theorem is valid under its stated product-interval assumptions, the limitations are no longer overgeneralized to real correlated metrics/quantizers, and `A0 = KILL` conforms to the gate because the submitted width-monotone object failed and no positive salvage theorem was completed. This acceptance does not mean every layout/coverage/metadata-access direction is closed.

## 14. Final outcome

```text
KILL
```

Three decisive reasons are sufficient:

1. Complete numerical examples show both uncertainty order and boundary ambiguity reverse with the query; interval width can be $20\times$ larger for a safely filtered far point than for an ambiguous near point.
2. Coupled post-read filtering saves zero distinct SSD pages; decoupled safe page admission is ordinary page-granular branch-and-bound.
3. In the explicit product-interval model, page lower-bound scheduling is instance-optimal; mandatory width-probe ordering can be unboundedly worse, while broader salvage classes remain unproved.

`PASS-ORIGINAL` is false. `PASS-SALVAGED-FORMAL-OBJECT` is unsupported because the sound candidates either reduce to query-conditioned filtering or change the object into metric coverage, layout, progressive quantization, or metadata-access indexing without completing the required theorem and nearest-work separation.

## 15. What this proves and does not prove

### Proves under the stated models

- no nontrivial exact-distance dominance order is query-independent over a query domain containing the data points;
- path-wise interval-width shrinkage does not imply safe exact-probe skipping;
- width is not a correct proxy for boundary ambiguity;
- coupled post-read exact-compute skipping does not reduce distinct submitted pages;
- decoupled candidate filtering saves a page only when every required candidate on that page is eliminated;
- in the stated product-interval/free-metadata model, page lower-bound scheduling is instance-optimal;
- a mandatory width-probe order has no finite approximation guarantee in that model.

### Does not prove

- quantization/topology co-design is impossible;
- approximate, probabilistic, or distribution-specific scheduling cannot improve latency;
- restricted query-region certificates can never be useful;
- ambiguity-aligned page packing cannot yield an expected-I/O theorem;
- graph/hierarchy metadata cannot reduce online bound-evaluation work;
- progressive quantization or lower-bound filtering is ineffective;
- all possible coverage indexes are known;
- ZNS is killed—the Z0B campaign remains incomplete.

## 16. Reproduction

### Local gate and proposal

- `gpt/share/2026-07-19/vector_direction_gate_2026-07-19.md`
- `gpt/share/2026-07-19/claude_ann_candidate_directions_strict_review_0719.md`
- `claude/share/2026-07-18/idea_report_phase2_merged_0718.md`
- `codex/share/2026-07-19/ambiguity_a0_paper_gate_0719.md`

### Z0B read-only status

```bash
python3 codex/share/2026-07-19/zns_ann_z0b/status_endpoints.py \
  --root ../data/VectorDB/dynamic_vamana_atlas/z0b_sequence_endpoint_reclaim_0719
sed -n '1,220p' \
  ../data/VectorDB/dynamic_vamana_atlas/z0b_sequence_endpoint_reclaim_0719/CAMPAIGN_FAILED.json
```

### Source paths

- `/home/ubuntu/pz/VectorDB/repos/DGAI/src/search/beam_search.cpp`
- `/home/ubuntu/pz/VectorDB/repos/DGAI/src/search/rerank_search.cpp`
- `/home/ubuntu/pz/VectorDB/repos/DGAI/src/utils/linux_aligned_file_reader.cpp`
- `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/src/OdinANN-PipeANN/include/nbr/rabitq_nbr.h`
- `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/src/OdinANN-PipeANN/include/nbr/rabitq/utils/rabitq_impl.hpp`

### Primary-paper verification

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  curl -L 'https://export.arxiv.org/api/query?id_list=2405.12497,2411.12229,2605.02171,2511.16921,2605.05787,2510.25401'
```

The full PDFs checked in `/tmp/a0_papers` were RaBitQ, SymphonyQG, QuIVer, δ-EMG/δ-EMQG, DGAI, and SkipDisk. `/tmp` contents are disposable and not part of the evidence repository.
