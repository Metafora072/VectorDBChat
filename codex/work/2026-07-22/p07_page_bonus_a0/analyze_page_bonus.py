#!/usr/bin/env python3
"""
P07 A0: Analyze co-resident node utility on SSD pages.

Approach:
1. Parse disk index to get sector→node mapping + adjacency lists
2. For each sector, check if co-resident nodes are graph-neighbors
3. Load ground truth; for a sample of queries, simulate beam search visiting,
   check if co-resident nodes appear in GT
"""
import struct
import numpy as np
from collections import defaultdict
import time

WORK = "/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p07_page_bonus_a0"
DATA = "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m"
SECTOR_LEN = 4096

def parse_disk_index(path):
    """Parse DiskANN disk index: extract sector→nodes mapping and adjacency."""
    with open(path, 'rb') as f:
        # Read metadata (first sector)
        nr, nc = struct.unpack('II', f.read(8))
        meta = [struct.unpack('Q', f.read(8))[0] for _ in range(nr)]
        npts = meta[0]
        ndims = meta[1]
        medoid = meta[2]
        max_node_len = meta[3]
        nnodes_per_sector = meta[4]

        print(f"Index: npts={npts}, ndims={ndims}, medoid={medoid}")
        print(f"  max_node_len={max_node_len}, nnodes_per_sector={nnodes_per_sector}")

        # Each node in a sector: [vector (ndims*sizeof(T) bytes), nnbrs (uint32), nbr_ids (nnbrs*uint32)]
        # node layout: vector first, then nnbrs, then neighbor IDs
        vec_size = ndims * 4  # float32
        n_sectors = (npts + nnodes_per_sector - 1) // nnodes_per_sector

        sector_nodes = {}  # sector_id → [node_ids]
        node_to_sector = {}  # node_id → sector_id
        adjacency = {}  # node_id → set(neighbor_ids)

        f.seek(SECTOR_LEN)  # skip metadata sector

        for sector_id in range(n_sectors):
            sector_data = f.read(SECTOR_LEN)
            nodes_in_sector = []

            for slot in range(nnodes_per_sector):
                node_id = sector_id * nnodes_per_sector + slot
                if node_id >= npts:
                    break

                offset = slot * max_node_len
                # Read vector (skip it for now)
                # Read nnbrs
                nnbrs_offset = offset + vec_size
                nnbrs = struct.unpack_from('I', sector_data, nnbrs_offset)[0]

                # Read neighbor IDs
                nbrs_offset = nnbrs_offset + 4
                nbrs = set()
                for i in range(min(nnbrs, 64)):  # cap at R=64
                    nbr = struct.unpack_from('I', sector_data, nbrs_offset + i * 4)[0]
                    if nbr < npts:
                        nbrs.add(nbr)

                nodes_in_sector.append(node_id)
                adjacency[node_id] = nbrs

            sector_nodes[sector_id] = nodes_in_sector
            for nid in nodes_in_sector:
                node_to_sector[nid] = sector_id

            if sector_id % 50000 == 0:
                print(f"  Parsed sector {sector_id}/{n_sectors}...")

    return sector_nodes, node_to_sector, adjacency, npts, medoid, nnodes_per_sector

def analyze_coresidency_graph(sector_nodes, adjacency, nnodes_per_sector):
    """For each sector, check if co-resident nodes are graph neighbors."""
    print("\n[1] Co-residency graph analysis...")

    n_sectors = len(sector_nodes)
    total_pairs = 0
    neighbor_pairs = 0
    two_hop_pairs = 0

    sector_neighbor_fracs = []

    for sid, nodes in sector_nodes.items():
        if len(nodes) < 2:
            continue

        n_pairs = len(nodes) * (len(nodes) - 1) // 2
        total_pairs += n_pairs

        pair_neighbor = 0
        pair_two_hop = 0
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                if b in adjacency.get(a, set()) or a in adjacency.get(b, set()):
                    pair_neighbor += 1
                else:
                    # Check 2-hop: do a and b share any neighbor?
                    shared = adjacency.get(a, set()) & adjacency.get(b, set())
                    if shared:
                        pair_two_hop += 1

        neighbor_pairs += pair_neighbor
        two_hop_pairs += pair_two_hop
        if n_pairs > 0:
            sector_neighbor_fracs.append(pair_neighbor / n_pairs)

    frac_1hop = neighbor_pairs / total_pairs if total_pairs > 0 else 0
    frac_2hop = two_hop_pairs / total_pairs if total_pairs > 0 else 0

    print(f"  Total co-resident pairs: {total_pairs}")
    print(f"  1-hop neighbor pairs: {neighbor_pairs} ({frac_1hop*100:.2f}%)")
    print(f"  2-hop neighbor pairs: {two_hop_pairs} ({frac_2hop*100:.2f}%)")
    print(f"  Neither: {total_pairs - neighbor_pairs - two_hop_pairs} ({(1-frac_1hop-frac_2hop)*100:.2f}%)")

    if sector_neighbor_fracs:
        arr = np.array(sector_neighbor_fracs)
        print(f"\n  Per-sector 1-hop fraction: mean={np.mean(arr):.4f}, median={np.median(arr):.4f}, p25={np.percentile(arr,25):.4f}, p75={np.percentile(arr,75):.4f}")

    return frac_1hop, frac_2hop

def analyze_search_bonus(sector_nodes, node_to_sector, adjacency, npts, medoid,
                         data_path, query_path, gt_path):
    """Simulate greedy search and analyze bonus node utility."""
    print("\n[2] Search-time bonus analysis...")

    # Load data
    data = load_bin(data_path)
    queries = load_bin(query_path)

    # Load or compute ground truth
    try:
        gt = load_gt_ivecs(gt_path)
        print(f"  Loaded GT: {gt.shape}")
    except:
        print("  No GT file found, computing brute-force GT for 1000 queries on 100K sample...")
        sample_data = data[:100000]
        gt = np.zeros((min(1000, len(queries)), 100), dtype=np.int32)
        for qi in range(gt.shape[0]):
            dists = np.sum((sample_data - queries[qi]) ** 2, axis=1)
            gt[qi] = np.argsort(dists)[:100]
        print(f"  Computed GT: {gt.shape}")

    # Simulate greedy search for a sample of queries
    n_queries = min(1000, len(queries))
    print(f"  Running greedy search simulation for {n_queries} queries...")

    bonus_in_gt100 = []
    bonus_in_later_visited = []
    bonus_total = []
    sectors_read_per_query = []

    for qi in range(n_queries):
        q = queries[qi]
        gt_set = set(gt[qi].tolist()) if qi < len(gt) else set()

        # Greedy search: start from medoid, follow neighbors
        visited = set()
        beam = [(np.sum((data[medoid] - q) ** 2), medoid)]
        visited.add(medoid)

        visited_order = [medoid]
        max_iters = 200  # limit beam search iterations

        for _ in range(max_iters):
            if not beam:
                break
            beam.sort()
            # Expand best unvisited
            expanded = False
            for dist, nid in beam:
                if nid in visited and expanded:
                    continue
                # Expand this node
                for nbr in adjacency.get(nid, set()):
                    if nbr not in visited and nbr < npts:
                        visited.add(nbr)
                        visited_order.append(nbr)
                        d = np.sum((data[nbr] - q) ** 2)
                        beam.append((d, nbr))
                expanded = True
                break
            if not expanded:
                break
            # Keep beam at reasonable size
            beam.sort()
            beam = beam[:100]

        # Analyze sectors read
        sectors_read = set()
        for nid in visited_order:
            if nid in node_to_sector:
                sectors_read.add(node_to_sector[nid])
        sectors_read_per_query.append(len(sectors_read))

        # For each visited node, find its co-residents (bonus nodes)
        all_bonus = set()
        for nid in visited_order:
            sid = node_to_sector.get(nid)
            if sid is None:
                continue
            for co_nid in sector_nodes[sid]:
                if co_nid != nid and co_nid not in visited:
                    all_bonus.add(co_nid)

        bonus_total.append(len(all_bonus))

        # How many bonus nodes are in GT-100?
        n_in_gt = len(all_bonus & gt_set)
        bonus_in_gt100.append(n_in_gt)

        # How many bonus nodes were later visited? (i.e., appear in visited_order after first encounter)
        n_later = 0
        first_encounter = {}
        for idx, nid in enumerate(visited_order):
            sid = node_to_sector.get(nid)
            if sid is None:
                continue
            for co_nid in sector_nodes[sid]:
                if co_nid != nid and co_nid not in first_encounter:
                    first_encounter[co_nid] = idx
            if nid in first_encounter and first_encounter[nid] < idx:
                n_later += 1
        bonus_in_later_visited.append(n_later)

        if qi % 200 == 0:
            print(f"    Query {qi}/{n_queries}: visited={len(visited)}, sectors={len(sectors_read)}, bonus={len(all_bonus)}, in_gt={n_in_gt}")

    print(f"\n  Results across {n_queries} queries:")
    print(f"  Visited nodes/query: mean={np.mean([len(v) for v in [visited_order]]):.1f}")
    print(f"  Sectors read/query: mean={np.mean(sectors_read_per_query):.1f}, median={np.median(sectors_read_per_query):.1f}")
    print(f"  Bonus nodes/query: mean={np.mean(bonus_total):.1f}, median={np.median(bonus_total):.1f}")
    print(f"  Bonus in GT-100/query: mean={np.mean(bonus_in_gt100):.4f}, median={np.median(bonus_in_gt100):.1f}")
    print(f"  Bonus later visited/query: mean={np.mean(bonus_in_later_visited):.1f}")

    if np.mean(bonus_total) > 0:
        frac_gt = np.mean(bonus_in_gt100) / np.mean(bonus_total) * 100
        frac_later = np.mean(bonus_in_later_visited) / np.mean(bonus_total) * 100
        print(f"\n  Fraction of bonus nodes in GT-100: {frac_gt:.2f}%")
        print(f"  Fraction of bonus nodes later visited: {frac_later:.2f}%")

        # Potential I/O savings: bonus nodes that would eliminate a future sector read
        potential_savings = []
        for qi in range(n_queries):
            if sectors_read_per_query[qi] > 0 and bonus_total[qi] > 0:
                # Rough estimate: each bonus node that's later visited saves ~1 sector read
                potential_savings.append(bonus_in_later_visited[qi] / sectors_read_per_query[qi])
        if potential_savings:
            print(f"  Potential I/O savings: mean={np.mean(potential_savings)*100:.2f}%")

    return bonus_in_gt100, bonus_total

def load_bin(path):
    with open(path, "rb") as f:
        npts, ndim = struct.unpack("II", f.read(8))
        data = np.frombuffer(f.read(npts * ndim * 4), dtype=np.float32).reshape(npts, ndim)
    return data

def load_gt_ivecs(path):
    """Load ground truth in ivecs format."""
    with open(path, 'rb') as f:
        data = []
        while True:
            buf = f.read(4)
            if len(buf) < 4:
                break
            dim = struct.unpack('I', buf)[0]
            vec = np.frombuffer(f.read(dim * 4), dtype=np.int32)
            data.append(vec)
    return np.array(data)

def main():
    print("=" * 70)
    print("P07 A0: Page Bonus — Co-Resident Node Utility Analysis")
    print("=" * 70)

    t0 = time.time()

    # Parse disk index
    print("\n[0] Parsing disk index...")
    idx_path = f"{WORK}/index/sift1m_disk.index"
    sector_nodes, node_to_sector, adjacency, npts, medoid, nnps = parse_disk_index(idx_path)
    print(f"  Parsed in {time.time()-t0:.1f}s")

    # Phase 1: Graph-based analysis (no search needed)
    frac_1hop, frac_2hop = analyze_coresidency_graph(sector_nodes, adjacency, nnps)

    # Phase 2: Search-time analysis
    gt_path = f"/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/groundtruth/sift1m"
    gt_files = []
    import os
    if os.path.isdir(gt_path):
        gt_files = [f for f in os.listdir(gt_path) if f.endswith('.ivecs') or f.endswith('.bin')]
        print(f"\n  GT files found: {gt_files}")

    # Use brute-force GT computation on 100K sample for speed
    analyze_search_bonus(
        sector_nodes, node_to_sector, adjacency, npts, medoid,
        f"{DATA}/full_1m.bin", f"{DATA}/query.bin",
        os.path.join(gt_path, gt_files[0]) if gt_files else ""
    )

    # Overall verdict
    print(f"\n{'=' * 70}")
    print("VERDICT")
    print(f"{'=' * 70}")
    if frac_1hop > 0.15:
        print(f"  PASS-PROBLEM: {frac_1hop*100:.1f}% of co-resident pairs are 1-hop neighbors")
        print(f"  Graph-order layout creates strong co-residency of useful nodes")
    elif frac_1hop > 0.05:
        print(f"  HOLD: {frac_1hop*100:.1f}% of co-resident pairs are 1-hop neighbors (moderate)")
    else:
        print(f"  KILL-NO-PROBLEM: only {frac_1hop*100:.1f}% co-resident pairs are 1-hop neighbors")

    print(f"\n  Total time: {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
