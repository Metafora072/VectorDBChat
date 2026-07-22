#!/usr/bin/env python3
"""
Measure PQ reconstruction error for BUILD vs INSERT vectors.

PQ pivots file format (DiskANN):
  - First: 5 uint64 offsets at position 0
  - offset[0]: PQ tables (256 centroids × ndims float32)
  - offset[1]: centroid (ndims × 1 float32) — global mean
  - offset[2]: rearrangement (ndims × 1 uint32) — identity, ignored
  - offset[3]: chunk_offsets ((n_chunks+1) × 1 uint32)
  - offset[4]: (optional rotation matrix)

PQ compressed file format:
  - 4-byte uint32 npts, 4-byte uint32 n_chunks
  - npts × n_chunks uint8 codes
"""
import struct
import numpy as np

WORK = "/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p01_pq_staleness_a0"

def load_bin(path):
    with open(path, "rb") as f:
        npts, ndim = struct.unpack("II", f.read(8))
        data = np.frombuffer(f.read(npts * ndim * 4), dtype=np.float32).reshape(npts, ndim)
    return data

def load_pq_pivots(path):
    with open(path, "rb") as f:
        # Read offset table (DiskANN bin format: 4-byte npts, 4-byte ndim)
        offsets_npts, offsets_ndim = struct.unpack("II", f.read(8))
        offsets = np.frombuffer(f.read(offsets_npts * offsets_ndim * 8), dtype=np.uint64)
        print(f"  PQ pivots: {offsets_npts} offsets = {offsets}")

        # offset[0]: PQ tables (256 centroids × ndims)
        f.seek(offsets[0])
        t_npts, t_ndim = struct.unpack("II", f.read(8))
        tables = np.frombuffer(f.read(t_npts * t_ndim * 4), dtype=np.float32).reshape(t_npts, t_ndim)
        print(f"  PQ tables: {t_npts} centroids × {t_ndim} dims")

        # offset[1]: centroid (ndims × 1)
        f.seek(offsets[1])
        c_npts, c_ndim = struct.unpack("II", f.read(8))
        centroid = np.frombuffer(f.read(c_npts * c_ndim * 4), dtype=np.float32)
        print(f"  Centroid: {c_npts} dims")

        # offset[2]: could be chunk_offsets or rearrangement
        # Try reading it; for DiskANN with 4 offsets, offset[2] is chunk_offsets
        f.seek(offsets[2])
        co_npts, co_ndim = struct.unpack("II", f.read(8))
        chunk_data = np.frombuffer(f.read(co_npts * co_ndim * 4), dtype=np.uint32)
        print(f"  Offset[2] data: {co_npts} × {co_ndim}, values[:10]={chunk_data[:10]}")

        # Determine if this is chunk_offsets (monotonically increasing, ending at ndim)
        # or rearrangement (permutation of 0..ndim-1)
        if co_npts > 2 and chunk_data[-1] == t_ndim and np.all(np.diff(chunk_data.astype(np.int64)) >= 0):
            chunk_offsets = chunk_data
            n_chunks = co_npts - 1
            print(f"  → Identified as chunk_offsets: {n_chunks} chunks")
        else:
            # It's a rearrangement; chunk_offsets should be at offset[3]
            print(f"  → Identified as rearrangement, reading chunk_offsets from offset[3]")
            if offsets_npts > 3:
                f.seek(offsets[3])
                co_npts, co_ndim = struct.unpack("II", f.read(8))
                chunk_offsets = np.frombuffer(f.read(co_npts * co_ndim * 4), dtype=np.uint32)
                n_chunks = co_npts - 1
                print(f"  Chunk offsets: {co_npts} values → {n_chunks} chunks")
            else:
                # Default: one dimension per chunk
                n_chunks = t_ndim
                chunk_offsets = np.arange(n_chunks + 1, dtype=np.uint32)
                print(f"  → Defaulting to {n_chunks} chunks (1 dim/chunk)")

    return tables, centroid, chunk_offsets, n_chunks

def load_pq_compressed(path):
    with open(path, "rb") as f:
        npts, n_chunks = struct.unpack("II", f.read(8))
        codes = np.frombuffer(f.read(npts * n_chunks), dtype=np.uint8).reshape(npts, n_chunks)
    print(f"  PQ compressed: {npts} points × {n_chunks} chunks")
    return codes

def pq_reconstruct(codes, tables, centroid, chunk_offsets, n_chunks):
    """Reconstruct vectors from PQ codes."""
    npts = codes.shape[0]
    ndims = len(centroid)
    recon = np.zeros((npts, ndims), dtype=np.float32)

    for c in range(n_chunks):
        start = chunk_offsets[c]
        end = chunk_offsets[c + 1]
        chunk_size = end - start
        # For each point, look up the centroid for chunk c
        chunk_codes = codes[:, c]  # (npts,)
        # tables shape: (256, ndims), chunk c spans dims [start:end]
        chunk_centroids = tables[:, start:end]  # (256, chunk_size)
        recon[:, start:end] = chunk_centroids[chunk_codes]

    # Add back the global centroid
    recon += centroid[np.newaxis, :]
    return recon

def encode_with_codebook(vectors, tables, centroid, chunk_offsets, n_chunks):
    """Encode new vectors using existing PQ codebook."""
    npts = vectors.shape[0]
    centered = vectors - centroid[np.newaxis, :]
    codes = np.zeros((npts, n_chunks), dtype=np.uint8)

    for c in range(n_chunks):
        start = chunk_offsets[c]
        end = chunk_offsets[c + 1]
        chunk_data = centered[:, start:end]  # (npts, chunk_size)
        chunk_centroids = tables[:, start:end]  # (256, chunk_size)

        # Compute distances from each point to each centroid
        # Use batch processing to avoid memory issues
        batch_size = 10000
        for b in range(0, npts, batch_size):
            batch = chunk_data[b:b+batch_size]
            # (batch, 1, chunk_size) - (1, 256, chunk_size) → (batch, 256, chunk_size)
            diffs = batch[:, np.newaxis, :] - chunk_centroids[np.newaxis, :, :]
            dists = np.sum(diffs ** 2, axis=2)  # (batch, 256)
            codes[b:b+batch_size, c] = np.argmin(dists, axis=1).astype(np.uint8)

    return codes

def compute_error_stats(original, reconstructed, label):
    """Compute per-vector L2 reconstruction error."""
    errors = np.sum((original - reconstructed) ** 2, axis=1)
    print(f"\n  {label} ({len(errors)} vectors):")
    print(f"    Mean L2² error:   {np.mean(errors):.4f}")
    print(f"    Median L2² error: {np.median(errors):.4f}")
    print(f"    P95 L2² error:    {np.percentile(errors, 95):.4f}")
    print(f"    P99 L2² error:    {np.percentile(errors, 99):.4f}")
    print(f"    Std L2² error:    {np.std(errors):.4f}")

    rmse = np.sqrt(errors)
    print(f"    Mean RMSE:        {np.mean(rmse):.4f}")
    print(f"    Median RMSE:      {np.median(rmse):.4f}")

    # Per-dim error
    per_dim_mse = np.mean((original - reconstructed) ** 2, axis=0)
    print(f"    Per-dim MSE: mean={np.mean(per_dim_mse):.6f}, max={np.max(per_dim_mse):.6f}")

    return errors

def main():
    print("=" * 60)
    print("P01 A0: PQ Codebook Staleness Measurement")
    print("=" * 60)

    # Load data
    print("\n[1] Loading data...")
    build_data = load_bin(f"{WORK}/build_700k.bin")
    insert_data = load_bin(f"{WORK}/insert_300k.bin")
    print(f"  BUILD: {build_data.shape}, INSERT: {insert_data.shape}")

    # Load PQ model
    print("\n[2] Loading PQ model...")
    tables, centroid, chunk_offsets, n_chunks = load_pq_pivots(f"{WORK}/index/sift700k_pq_pivots.bin")
    build_codes = load_pq_compressed(f"{WORK}/index/sift700k_pq_compressed.bin")

    # Reconstruct BUILD vectors and measure error
    print("\n[3] Reconstructing BUILD vectors...")
    build_recon = pq_reconstruct(build_codes, tables, centroid, chunk_offsets, n_chunks)
    build_errors = compute_error_stats(build_data, build_recon, "BUILD (in-distribution)")

    # Encode INSERT vectors with BUILD codebook
    print("\n[4] Encoding INSERT vectors with BUILD codebook...")
    insert_codes = encode_with_codebook(insert_data, tables, centroid, chunk_offsets, n_chunks)

    # Reconstruct INSERT vectors and measure error
    print("\n[5] Reconstructing INSERT vectors...")
    insert_recon = pq_reconstruct(insert_codes, tables, centroid, chunk_offsets, n_chunks)
    insert_errors = compute_error_stats(insert_data, insert_recon, "INSERT (out-of-distribution)")

    # Compare
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    ratio_mean = np.mean(insert_errors) / np.mean(build_errors)
    ratio_median = np.median(insert_errors) / np.median(build_errors)
    ratio_p95 = np.percentile(insert_errors, 95) / np.percentile(build_errors, 95)

    print(f"  Error ratio (INSERT/BUILD):")
    print(f"    Mean:   {ratio_mean:.4f}")
    print(f"    Median: {ratio_median:.4f}")
    print(f"    P95:    {ratio_p95:.4f}")

    # Per-chunk error comparison
    print(f"\n  Per-chunk error comparison:")
    for c in range(n_chunks):
        start = chunk_offsets[c]
        end = chunk_offsets[c + 1]
        build_chunk_err = np.mean(np.sum((build_data[:, start:end] - build_recon[:, start:end]) ** 2, axis=1))
        insert_chunk_err = np.mean(np.sum((insert_data[:, start:end] - insert_recon[:, start:end]) ** 2, axis=1))
        ratio = insert_chunk_err / build_chunk_err if build_chunk_err > 0 else float('inf')
        print(f"    Chunk {c} (dims {start}-{end-1}): BUILD={build_chunk_err:.4f}, INSERT={insert_chunk_err:.4f}, ratio={ratio:.4f}")

    # Verdict
    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    if ratio_mean > 1.10:
        print(f"  PASS-PROBLEM: INSERT PQ error is {(ratio_mean-1)*100:.1f}% higher than BUILD")
        print(f"  PQ codebook staleness is a real phenomenon on SIFT1M")
    elif ratio_mean > 1.05:
        print(f"  HOLD: INSERT PQ error is {(ratio_mean-1)*100:.1f}% higher (marginal)")
    else:
        print(f"  KILL-NO-PROBLEM: INSERT PQ error is only {(ratio_mean-1)*100:.1f}% higher")
        print(f"  PQ codebook does NOT become meaningfully stale with this data split")

    # Also check: is the centroid shift significant?
    print(f"\n  Data distribution comparison:")
    build_mean = np.mean(build_data, axis=0)
    insert_mean = np.mean(insert_data, axis=0)
    centroid_shift = np.sqrt(np.sum((build_mean - insert_mean) ** 2))
    build_spread = np.mean(np.sqrt(np.sum((build_data - build_mean) ** 2, axis=1)))
    print(f"    Centroid shift (L2): {centroid_shift:.4f}")
    print(f"    BUILD mean spread:   {build_spread:.4f}")
    print(f"    Shift / Spread:      {centroid_shift / build_spread:.4f}")

if __name__ == "__main__":
    main()
