# VAQ semantic physical-design G0

This directory contains the reproducible executor for the narrow G0 gate in
`gpt/share/vaq_semantic_physical_design_g0_gate.md`.  It is not an advisor and
does not modify an ANN algorithm.

All large inputs, indices, and results live under the separately mounted data
disk:

```text
/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0
```

Run the correctness/sanity stage with:

```bash
DATA_ROOT=/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0 \
  /home/ubuntu/pz/VectorDB/data/vaq_semantic_g0/env/bin/python run_g0.py \
  --mode sanity
```

The executor uses two public datasets:

- Exqutor-compatible TPC-H SF1 relations with SIFT1M vectors attached to
  `part`, preserving the standard VAQ filter/ANN/join/aggregate shape.
- MovieLens-20M genome-tag relevance vectors, movie metadata, and the natural
  20M-row ratings fact table.

It compares global post-filter, global native pre-filter, attribute-local ANN,
and adaptive scalar-bitmap/global-ANN execution using both HNSW and IVF.  Exact
flat search supplies the reference answers.  Query-level records include ANN
recall, weighted join recall, aggregate errors, group/rank errors, false-negative
distribution, latency, storage, build time, and update cost.

Final G0 outcome: `KILL_SEQUENTIAL_REACHES_JOINT_FRONTIER`.  Error propagation
was measurable, but the vector-local and joint-semantic Pareto configuration
sets were identical in all four dataset/query-family cases.  See
`../../share/vaq_semantic_physical_design_g0_report.md`.
