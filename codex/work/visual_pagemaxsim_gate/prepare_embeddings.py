#!/usr/bin/env python3
"""Prepare a deterministic ViDoRe/ColQwen2 pilot corpus on the data disk.

The script deliberately separates offline encoding from the storage gate.  It
never writes model or dataset artifacts into the chat repository.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from datasets import load_dataset
from transformers import ColQwen2ForRetrieval, ColQwen2Processor


SEED = 20260712


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--parquet", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--documents", type=int, default=96)
    p.add_argument("--queries", type=int, default=24)
    p.add_argument("--skip-documents", type=int, default=0)
    p.add_argument("--image-batch", type=int, default=1)
    p.add_argument("--query-batch", type=int, default=8)
    p.add_argument("--threads", type=int, default=32)
    p.add_argument("--dtype", choices=("float32", "bfloat16"), default="bfloat16")
    p.add_argument("--sanity", action="store_true")
    return p.parse_args()


def masked_rows(embeddings: torch.Tensor, attention_mask: torch.Tensor) -> list[np.ndarray]:
    rows: list[np.ndarray] = []
    for emb, mask in zip(embeddings, attention_mask, strict=True):
        selected = emb[mask.bool()].detach().float().cpu().numpy()
        norm = np.linalg.norm(selected, axis=1, keepdims=True)
        selected = selected / np.maximum(norm, 1e-12)
        rows.append(selected.astype(np.float32, copy=False))
    return rows


def save_ragged(path: Path, arrays: list[np.ndarray], ids: list[str], texts: list[str] | None = None) -> None:
    lengths = np.asarray([len(x) for x in arrays], dtype=np.int32)
    offsets = np.concatenate(([0], np.cumsum(lengths, dtype=np.int64)))
    values = np.concatenate(arrays, axis=0).astype(np.float16) if arrays else np.empty((0, 128), dtype=np.float16)
    payload: dict[str, np.ndarray] = {
        "values": values,
        "offsets": offsets,
        "ids": np.asarray(ids),
    }
    if texts is not None:
        payload["texts"] = np.asarray(texts)
    np.savez(path, **payload)


def main() -> None:
    args = parse_args()
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    args.out.mkdir(parents=True, exist_ok=True)

    requested_documents = 2 if args.sanity else args.documents
    requested_queries = 2 if args.sanity else args.queries

    ds = load_dataset("parquet", data_files={"test": str(args.parquet)}, split="test")
    # Keep the first occurrence of each real document; this is deterministic and
    # avoids duplicated pages masquerading as independent candidates.
    doc_rows: list[int] = []
    seen_docs: set[str] = set()
    unique_seen = 0
    for i, row in enumerate(ds):
        doc_id = str(row["docId"])
        if doc_id not in seen_docs:
            seen_docs.add(doc_id)
            if unique_seen >= args.skip_documents:
                doc_rows.append(i)
            unique_seen += 1
        if len(doc_rows) == requested_documents:
            break
    if len(doc_rows) < requested_documents:
        raise RuntimeError(f"only {len(doc_rows)} unique documents available")

    corpus_ids = {str(ds[i]["docId"]) for i in doc_rows}
    query_rows: list[int] = []
    if requested_queries:
        for i, row in enumerate(ds):
            if str(row["docId"]) in corpus_ids:
                query_rows.append(i)
            if len(query_rows) == requested_queries:
                break
    if len(query_rows) < requested_queries:
        raise RuntimeError(f"only {len(query_rows)} in-corpus queries available")

    dtype = torch.float32 if args.dtype == "float32" else torch.bfloat16
    started = time.perf_counter()
    model = ColQwen2ForRetrieval.from_pretrained(
        str(args.model),
        torch_dtype=dtype,
        device_map="cpu",
        attn_implementation="sdpa",
        local_files_only=True,
    ).eval()
    processor = ColQwen2Processor.from_pretrained(str(args.model), local_files_only=True)
    load_seconds = time.perf_counter() - started

    document_embeddings: list[np.ndarray] = []
    image_seconds: list[float] = []
    doc_ids: list[str] = []
    for start in range(0, len(doc_rows), args.image_batch):
        indices = doc_rows[start : start + args.image_batch]
        images = [ds[i]["image"].convert("RGB") for i in indices]
        inputs = processor(images=images, return_tensors="pt", padding=True)
        tick = time.perf_counter()
        with torch.inference_mode():
            output = model(**inputs).embeddings
        image_seconds.append(time.perf_counter() - tick)
        document_embeddings.extend(masked_rows(output, inputs["attention_mask"]))
        doc_ids.extend(str(ds[i]["docId"]) for i in indices)
        print(
            json.dumps(
                {
                    "stage": "images",
                    "done": len(document_embeddings),
                    "total": len(doc_rows),
                    "last_seconds": image_seconds[-1],
                    "last_tokens": [len(x) for x in document_embeddings[-len(indices) :]],
                }
            ),
            flush=True,
        )

    query_embeddings: list[np.ndarray] = []
    query_seconds: list[float] = []
    query_ids: list[str] = []
    query_texts: list[str] = []
    positive_doc_ids: list[str] = []
    for start in range(0, len(query_rows), args.query_batch):
        indices = query_rows[start : start + args.query_batch]
        texts = [str(ds[i]["query"]) for i in indices]
        inputs = processor(text=texts, return_tensors="pt", padding=True)
        tick = time.perf_counter()
        with torch.inference_mode():
            output = model(**inputs).embeddings
        query_seconds.append(time.perf_counter() - tick)
        query_embeddings.extend(masked_rows(output, inputs["attention_mask"]))
        query_ids.extend(str(ds[i]["questionId"]) for i in indices)
        query_texts.extend(texts)
        positive_doc_ids.extend(str(ds[i]["docId"]) for i in indices)
        print(
            json.dumps(
                {
                    "stage": "queries",
                    "done": len(query_embeddings),
                    "total": len(query_rows),
                    "last_seconds": query_seconds[-1],
                    "last_tokens": [len(x) for x in query_embeddings[-len(indices) :]],
                }
            ),
            flush=True,
        )

    save_ragged(args.out / "documents.npz", document_embeddings, doc_ids)
    save_ragged(args.out / "queries.npz", query_embeddings, query_ids, query_texts)
    manifest = {
        "seed": SEED,
        "dataset": "vidore/docvqa_test_subsampled",
        "dataset_revision": "49bf8f13e13c41dd8cdb0cae5314e31c1da1e0d6",
        "model": "vidore/colqwen2-v1.0-hf",
        "model_revision": "0d3e414967fde994dd99a0ccc29bcb34b5355712",
        "dtype": args.dtype,
        "threads": args.threads,
        "documents": len(document_embeddings),
        "queries": len(query_embeddings),
        "document_ids": doc_ids,
        "query_ids": query_ids,
        "positive_document_ids": positive_doc_ids,
        "document_token_counts": [len(x) for x in document_embeddings],
        "query_token_counts": [len(x) for x in query_embeddings],
        "model_load_seconds": load_seconds,
        "image_batch_seconds": image_seconds,
        "query_batch_seconds": query_seconds,
        "environment": {
            "torch": torch.__version__,
            "transformers": __import__("transformers").__version__,
            "numpy": np.__version__,
            "cpu_count": os.cpu_count(),
        },
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"stage": "complete", "out": str(args.out), "manifest": manifest}), flush=True)


if __name__ == "__main__":
    main()
