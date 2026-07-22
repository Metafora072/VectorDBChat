# P07 A0: Page Bonus — Free Co-Resident Node Utility

## Goal

Measure whether co-resident nodes on SSD pages (read for free during beam search) would be useful as additional navigation candidates. DiskANN reads a 4KB page to get 1 requested node but delivers ~5 nodes. Are the other ~4 "bonus" nodes useful?

## Experiment Design

### Setup
- Dataset: SIFT1M (128d float32, L2)
- Data path: `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin`
- Query: `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/query.bin`
- System: DiskANN at `/home/ubuntu/pz/VectorDB/repos/DiskANN`
- Build dir: `/home/ubuntu/pz/VectorDB/repos/DiskANN/build`

### Protocol

**Step 1: Build disk index**
```
./build_disk_index --data_type float --dist_fn l2 \
  --data_path <full_1m.bin> \
  --index_path_prefix <output_dir>/sift1m \
  -R 64 -L 100 --PQ_disk_bytes 0 \
  --num_threads 8 --search_DRAM_budget 4 --build_DRAM_budget 16
```

**Step 2: Analyze disk layout**

Parse the disk index (`sift1m_disk.index`) to extract the page→node mapping:
- DiskANN disk layout: SECTOR_LEN = 4096 bytes
- Each sector: 4-byte nnodes, then for each node: [4-byte id, 4-byte nnbrs, nnbrs*4-byte neighbor_ids, dim*sizeof(T)-byte vector]
- Actually the format is: each node occupies `max_node_len` bytes within a sector. `max_node_len = (4 + 4*R + dim*sizeof(T))` rounded to alignment.
- For SIFT1M (128d float32, R=64): node_size = 4(nnbrs) + 64*4(neighbors) + 128*4(vector) = 4 + 256 + 512 = 772 bytes. With alignment ≈ 800 bytes. Nodes per sector ≈ 4096/800 ≈ 5.

Write a tool to:
1. Read the disk index header to get `nnodes_per_sector` and `max_node_len`
2. For each sector, record which node IDs live on it
3. Build a map: sector_id → {node_id_1, node_id_2, ...}
4. Build reverse map: node_id → sector_id

**Step 3: Instrument search to trace visited nodes and their sectors**

Modify `search_disk_index.cpp` or write a new driver that:
1. For each query, runs beam search and records:
   - The ordered list of nodes actually visited (expanded) during search
   - For each visited node, its sector_id
   - All co-resident nodes on each visited sector
2. After search completes, for each query compute:
   - `bonus_nodes`: all co-resident nodes NOT in the beam (not explicitly requested)
   - `bonus_in_later_beam`: bonus nodes that appear in later beam expansion steps
   - `bonus_in_topk`: bonus nodes that appear in the final top-k result
   - `bonus_in_gt100`: bonus nodes that appear in ground truth top-100

**Simplified Alternative (recommended for A0):**

Instead of modifying search code, do a post-hoc analysis:
1. Run `search_disk_index` with high verbosity or add lightweight logging to capture the list of visited node IDs per query
2. Using the sector map from Step 2, compute which bonus nodes WOULD have been available
3. Check ground truth: for each bonus node, is it in the query's GT top-100?
4. Check search path: for each bonus node, was it visited later in the search?

Even simpler offline analysis:
1. Build the sector→nodes map
2. Run search, capture the set of visited nodes per query  
3. For each visited node, look up its sector → get bonus nodes
4. Count: what fraction of bonus nodes are in {later visited set} or {GT top-100}?

### Key Code Locations
- Disk layout construction: `src/disk_utils.cpp` — `create_disk_layout()`
- Sector metadata: in `pq_flash_index.h` — `nnodes_per_sector`, `max_node_len`
- Search: `src/pq_flash_index.cpp` — `cached_beam_search()` — this is where nodes are fetched from sectors
- DiskANN disk index format: first sector is metadata, then nodes packed into sectors sequentially

### Metrics

| Metric | PASS threshold | KILL threshold |
|--------|---------------|---------------|
| Fraction of bonus nodes in GT-100 | >15% | <5% |
| Fraction of bonus nodes visited later in same search | >10% | <3% |
| Potential I/O savings (bonus nodes that would eliminate a future read) | >10% of total reads | <3% |

### PASS / KILL

- **PASS-PROBLEM**: >15% of bonus nodes are in GT-100 OR >10% would eliminate future reads → free expansion has real value
- **HOLD**: 5-15% of bonus nodes are useful but I/O savings unclear
- **KILL-NO-PROBLEM**: <5% of bonus nodes are useful → layout doesn't co-locate useful navigation information

### Output

Write results to: `/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-22/p07_page_bonus_a0_results_0722.md`

Include:
1. Disk layout statistics (nodes per sector distribution, total sectors)
2. Per-query bonus node analysis (mean/median/p95 across queries)
3. Bonus utility breakdown: in GT-100, in later beam, in final top-k
4. I/O savings estimate
5. Final verdict: PASS-PROBLEM / HOLD / KILL-NO-PROBLEM
6. Distribution of bonus utility (is it uniform or concentrated in certain queries?)

### Time Budget
3-4 hours max. The offline analysis approach (parse layout + post-hoc check) is preferred for A0 — avoid modifying core search code if possible.

### Important Notes
- DiskANN uses graph-order layout: nodes visited early during a BFS/DFS from the entry point are placed on earlier sectors. This creates spatial locality — nearby nodes (in graph distance) tend to be on the same or adjacent sectors.
- The experiment measures whether this locality translates to SEARCH-TIME utility: are co-resident nodes useful for the QUERY's navigation, not just graph-close?
- SIFT1M is small enough that cache effects may interfere. Consider using `--num_nodes_to_cache 0` to disable caching and force all reads to go through disk path.
