# SSD-Resident Grouped Multi-Vector Retrieval：A0 联合可行性评审门禁

**Date:** 2026-07-20  
**Repository:** `Metafora072/VectorDBChat`  
**Mode:** Paper-only + tiny symbolic/toy validation  
**Status:** New candidate; no implementation authorization

---

## 1. Candidate direction

研究对象不是普通单向量 ANN，也不是泛化的“多模态 RAG”。

唯一候选问题是：

> 当一个数据库对象由一组向量表示、查询也由一组向量表示，最终得分由 late-interaction / MaxSim 聚合得到时，如何在普通 NVMe 上避免读取候选对象的全部多向量 payload，同时仍然可靠地得到 document-level top-k？

典型算子：

\[
Score(Q,D)=\sum_{q_i\in Q}\max_{d_j\in D} sim(q_i,d_j)
\]

其中：

- `Q = {q_1, ..., q_m}`：查询 token / patch vectors；
- `D = {d_1, ..., d_n}`：一个文档、页面、视频片段或对象的一组向量；
- 结果单位是文档对象，不是单个向量；
- 物理读取单位是 SSD page。

---

## 2. Why this is potentially a new VectorDB workload

传统 ANNS：

```text
one object = one vector
one distance evaluation = one object score
one page read may reveal several independent objects
```

grouped multi-vector retrieval：

```text
one object = many vectors
one object score requires aggregation across many local maxima
one object may span multiple SSD pages
partial object reads produce incomplete scores
candidate generation and final object ranking are coupled
```

该方向只有在证明上述差异会产生新的存储执行问题时才可继续。

---

## 3. Required prior-work boundary

Claude 与 Codex 必须独立核对并交叉审查至少以下边界：

### Late interaction / multi-vector retrieval

- ColBERT / ColBERTv2
- XTR
- PLAID
- WARP
- MUVERA
- ColPali / visual document retrieval
- HEAVEN
- fixed-size multi-vector encodings
- token / patch pruning and vector compression
- multi-vector ANN / set-to-set retrieval
- MaxSim acceleration

### Disk / systems boundary

- DiskANN / Starling / PipeANN / DGAI
- SSD-resident reranking
- grouped record / posting-list / document-at-a-time execution
- block-max / WAND / BMW-style upper-bound pruning
- page-aware top-k aggregation
- column-store late materialization
- vector payload separation

The review must answer whether the candidate is merely a combination of:

```text
ColBERT/ColPali
+ coarse-to-fine retrieval
+ token pruning
+ WAND-style upper bounds
+ SSD page layout
```

If yes, KILL.

---

## 4. Precise subproblems to evaluate

### A. Partial-document score bounds

Suppose only part of `D` has been read.

Can the system maintain a sound bound:

```text
LB(Q,D,read_pages)
UB(Q,D,read_pages)
```

such that:

- `LB <= true Score <= UB`;
- unread pages can be skipped once `UB < current top-k threshold`;
- bounds are useful before most pages are read;
- metadata required for bounds is substantially smaller than full vectors;
- the bound is not equivalent to an existing block-max / coarse-vector index.

This is the strongest possible formal object.

### B. Query-token selective I/O

Can query token `q_i` identify which document pages might contain its MaxSim winner without scanning all pages?

Need distinguish:

- per-token inverted routing;
- document-local partition summaries;
- global ANN candidate generation;
- page-level metadata;
- false-positive I/O.

If the mechanism is simply “build another ANN index for every token vector,” KILL.

### C. Group-aware physical layout

Can the page layout jointly optimize:

- document score completion cost;
- partial-read pruning;
- page utilization;
- candidate generation;
- object updates?

Must compare:

- document-contiguous layout;
- random packing;
- token-clustered layout;
- cross-document page packing;
- summary/payload separation.

A layout heuristic without a formal objective or robust oracle gap is insufficient.

### D. Candidate-generation / exact-scoring coupling

Determine whether existing systems already solve:

```text
single-vector candidate generation
→ multi-vector exact reranking
```

and whether SSD cost is dominated by:

- candidate count;
- document payload pages;
- MaxSim CPU;
- decompression;
- metadata traversal.

If candidate generation already reduces the exact stage to a trivial cost, KILL.

---

## 5. Required adversarial counterexamples

The review must construct concrete cases for:

1. **Useless bound:** every unread page can still contain a MaxSim winner, so UB remains loose until almost all pages are read.
2. **Metadata explosion:** useful page bounds require metadata comparable to storing all vectors.
3. **Query-dependent layout conflict:** pages good for one query-token distribution are bad for another.
4. **Candidate-stage dominance:** exact grouped scoring is too small a fraction of latency/I/O to matter.
5. **CPU dominance:** MaxSim compute, not SSD I/O, dominates.
6. **Compression dominance:** existing pruning/encoding eliminates the alleged SSD problem.
7. **Object-size skew:** a few very large documents dominate all results and invalidate average-case gains.
8. **Update instability:** regrouping vectors after document/model updates causes prohibitive rewrite cost.

---

## 6. Tiny validation allowed in A0

Allowed:

- symbolic examples;
- exact enumeration on tiny vector sets;
- synthetic page grouping;
- analytical metadata-size accounting;
- trace-free toy cost model;
- small public artifacts already available locally;
- less than 1 GiB storage and no GPU.

Forbidden:

- building a production ColPali/ColBERT index;
- downloading large multimodal datasets;
- GPU execution;
- implementing a new ANN index;
- modifying DiskANN;
- NVMe benchmark campaigns;
- LLM/API use.

---

## 7. Required output from Claude

Claude should produce:

```text
claude/share/2026-07-20/
grouped_multivector_rag_landscape_and_problem_model_0720.md
```

It must contain:

1. application scenario and workload definition;
2. exact query operator;
3. storage/I/O execution path;
4. closest 10–15 works with mechanism-level overlap;
5. current CPU/GPU/memory/disk bottleneck evidence;
6. three candidate formal/system objects;
7. strongest reviewer objections;
8. preliminary score:
   - significance;
   - novelty;
   - system specificity;
   - hardware fit;
   - feasibility.

Claude must not recommend implementation before Codex review.

---

## 8. Required output from Codex

Codex independently produces:

```text
codex/share/2026-07-20/
grouped_multivector_rag_a0_novelty_and_viability_review_0720.md
```

It must:

1. audit Claude's prior-work claims;
2. verify all cited mechanisms from primary papers/code;
3. build the eight adversarial counterexamples;
4. test whether partial-document bounds can be nontrivial;
5. compare against block-max/WAND, MUVERA, WARP, PLAID, HEAVEN and token pruning;
6. identify the exact nonreplaceable storage-level contribution, if any;
7. run an independent reviewer pass;
8. return one final label.

---

## 9. Allowed final labels

### `PASS-GROUPED-MULTIVECTOR-A0`

Requires all:

- a precise query/storage problem not reducible to existing late-interaction retrieval;
- exact or sound partial-object bound with useful metadata-size separation;
- a plausible SSD page-I/O gap not already removed by candidate generation/compression;
- a non-heuristic optimization objective;
- ordinary NVMe + CPU feasibility;
- novelty score >= 6/10;
- system specificity >= 7/10;
- no fatal overlap with existing coarse-to-fine or block-max techniques.

### `HOLD-NEEDS-PROFILING`

Use only when:

- novelty object appears distinct;
- but no evidence yet shows grouped scoring is a significant SSD bottleneck.

HOLD must define one minimal public-dataset profiling gate.

### `KILL-ALGORITHM-REPACKAGING`

Use when the direction reduces to:

- late-interaction reranking;
- token pruning;
- coarse-to-fine retrieval;
- block-max/WAND;
- vector compression;
- document-contiguous layout;
- ordinary cache/prefetch.

### `KILL-NO-STORAGE-BOTTLENECK`

Use when grouped exact scoring is dominated by CPU/GPU compute or is already a negligible fraction of query cost.

### `FAIL-LITERATURE-OR-MODEL-CLOSURE`

Use when primary-source boundaries or the operator/cost model cannot be closed.

---

## 10. Stop line

After both reports and cross-review:

- do not implement;
- do not download large datasets;
- do not start NVMe experiments;
- do not merge this direction with multi-NVMe;
- do not add dynamic updates, versioning, filters, agents or evidence-bundle retrieval to inflate scope.

The only next step after a PASS/HOLD is a separately reviewed minimal profiling gate.
