# Reproduction Runbook

## Environment

- Python 3.12
- `numpy`, `scipy`, `pandas`, `scikit-learn`, `hnswlib`
- MovieLens-20M ratings at `/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0/raw/ml-20m/ratings.csv`
- CPU only; no model training or GPU

Run from repository root `/home/ubuntu/pz/VectorDB/chat`.

## Commands

```bash
python3 codex/work/2026-07-22/vectordb_idea_discovery_r3/move_a0.py \
  --output codex/work/2026-07-22/vectordb_idea_discovery_r3/move_a0_results.json

python3 codex/work/2026-07-22/vectordb_idea_discovery_r3/region_certificate_a0.py \
  --output codex/work/2026-07-22/vectordb_idea_discovery_r3/region_certificate_a0_results.json

python3 codex/work/2026-07-22/vectordb_idea_discovery_r3/capacity_ann_a0.py \
  --output codex/work/2026-07-22/vectordb_idea_discovery_r3/capacity_ann_a0_results.json

python3 codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_a0.py \
  --users 20000 --items 20000 --samples 5 --ks 10 100 --deltas 0.01 \
  --output codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_a0_scale20k_results.json

python3 codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_hnsw_a0.py \
  --alpha 0.1 \
  --output codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_hnsw_a0_results.json

python3 codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_hnsw_a0.py \
  --queries 64 --alpha 0.2 \
  --output codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_hnsw_a0_alpha02_results.json

python3 codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_hnsw_a0.py \
  --queries 64 --alpha 0.4 \
  --output codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_hnsw_a0_alpha04_results.json
```

## Integrity checks

```bash
python3 -m py_compile codex/work/2026-07-22/vectordb_idea_discovery_r3/*.py
python3 -m json.tool codex/work/2026-07-22/vectordb_idea_discovery_r3/distributional_hnsw_a0_results.json >/dev/null
git diff --check
```

`*_smoke.json` 是开发阶段的小样本 sanity check，不参与报告裁决。
