# Visual PageMaxSim P0–P2 problem gate

This directory contains the reproducible offline harness requested by
`gpt/share/visual_pagemaxsim_problem_gate_0712.md`. Large models, datasets,
embeddings, serialized objects, and raw result tables live on the project NVMe
under `/home/ubuntu/pz/VectorDB/data/pagemaxsim_gate`; they are intentionally
excluded from the chat repository and never use the system disk.

## Fixed inputs

- Dataset: `vidore/docvqa_test_subsampled`, revision
  `49bf8f13e13c41dd8cdb0cae5314e31c1da1e0d6` (MIT), local Parquet.
- Encoder: `vidore/colqwen2-v1.0-hf`, revision
  `0d3e414967fde994dd99a0ccc29bcb34b5355712` (Apache-2.0).
- Seed: `20260712`.
- Corpus/query pilot: 64 unique real document pages, 16 real questions.
- First-stage candidates: top 32 by normalized mean-vector score, with the
  labeled positive retained if the coarse stage misses it.
- Storage page: 4096 bytes; each object starts page-aligned, has a 64-byte
  object header and 16-byte continuation-page headers, and no token row is
  allowed to straddle a page.

## Commands

The environment variables keep every cache on the data disk. The exact local
paths are deliberate so a run cannot silently spill into `$HOME`.

```bash
DATA=/home/ubuntu/pz/VectorDB/data/pagemaxsim_gate
PY=$DATA/env/venv/bin/python
export HF_HOME=$DATA/cache/huggingface
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1

$PY prepare_embeddings.py \
  --model $DATA/models/colqwen2-v1.0-hf \
  --parquet $DATA/datasets/docvqa_test_subsampled/data/test-00000-of-00001.parquet \
  --out $DATA/artifacts/main_embeddings \
  --documents 64 --queries 16 --image-batch 4 --query-batch 8 \
  --threads 64 --dtype bfloat16

$PY analyze_p0_p1.py \
  --embeddings $DATA/artifacts/main_embeddings \
  --artifacts $DATA/artifacts/p0_p1 \
  --results $DATA/results/p0_p1 \
  --candidates 32 --top-k 5 --repeats 5

# Run only because this experiment's P1 produced a non-dominated page-oracle point.
$PY analyze_p2.py \
  --embeddings $DATA/artifacts/main_embeddings \
  --p0-p1-artifacts $DATA/artifacts/p0_p1 \
  --artifacts $DATA/artifacts/p2 \
  --results $DATA/results/p2 \
  --candidates 32 --top-k 5

# Residual multi-ball Stage A (only after gpt/share/pagemaxsim_stage_a_decision_0712.md)
$PY prepare_embeddings.py \
  --model $DATA/models/colqwen2-v1.0-hf \
  --parquet $DATA/datasets/docvqa_test_subsampled/data/test-00000-of-00001.parquet \
  --out $DATA/artifacts/stage_a_train_embeddings \
  --documents 256 --queries 0 --skip-documents 64 \
  --image-batch 4 --threads 64 --dtype bfloat16

# A0 first: trains/caches K=64/256 codebooks but does not build the certificate.
$PY analyze_stage_a.py \
  --test-embeddings $DATA/artifacts/main_embeddings \
  --train-embeddings $DATA/artifacts/stage_a_train_embeddings \
  --p0-p1-artifacts $DATA/artifacts/p0_p1 \
  --artifacts $DATA/artifacts/stage_a \
  --results $DATA/results/stage_a_a0 \
  --candidates 32 --top-k 5 --ks 64 256 --phase a0

# Run only if A0 retains non-trivial f9 exact-envelope space.
$PY analyze_stage_a.py \
  --test-embeddings $DATA/artifacts/main_embeddings \
  --train-embeddings $DATA/artifacts/stage_a_train_embeddings \
  --p0-p1-artifacts $DATA/artifacts/p0_p1 \
  --artifacts $DATA/artifacts/stage_a \
  --results $DATA/results/stage_a_full \
  --candidates 32 --top-k 5 --ks 64 256 --phase full
```

`analyze_p0_p1.py` stops before P1 if the P0 kill condition fires. In the
recorded run P1 retained a page-oracle Pareto point, so P2 was implemented and
run. P2 then hit the safe-bound kill and no P3 command exists in this harness.

## Representation and oracle definitions

- `raw_fp16`: complete 128D ColQwen2 late-interaction sequence.
- `raw_int8`: symmetric per-token int8 with an inline fp16 scale.
- `light_f9_*`: post-hoc cosine average-linkage semantic merging to
  `ceil(tokens/9)`, matching the 11.8%-footprint Light-ColPali operating point.
- `light_f49_fp16`: aggressive `ceil(tokens/49)` semantic merging, matching the
  approximately 2.8%-footprint stress point.
- `single_fp16`: normalized mean vector.

The report calls these **Light-style post-hoc semantic merging**, not the
fine-tuned Light-ColPali model. This distinction prevents the pilot from
overclaiming representation quality.

P1 reports three interaction policies on identical real candidates:

1. a minimum deterministic exact top-k certificate under valid cosine-cell
   support `[-1, 1]` (threshold enumeration, with omniscient reveal selection);
2. Col-Bandit Algorithm 1 at the deployed `alpha=0.2`, `B=4`, `M=5`,
   `delta=0.01`;
3. its `alpha=1.0` certificate corner.

For every revealed-cell set, the page-contribution oracle reads the union of
pages containing each cell's true maximizing document token. The ordinary
layout baseline must read every page of each touched document, because one
MaxSim cell scans all document tokens.
