#!/usr/bin/env python3
"""Execute the narrow VAQ semantic physical-design G0 finding gate."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import duckdb
import faiss
import h5py
import hnswlib
import numpy as np
import pandas as pd


SEED = 7112026
K = 30


@dataclass
class Dataset:
    name: str
    vectors: np.ndarray
    groups: np.ndarray
    group_names: list[str]
    fact_count: np.ndarray
    fact_sum: np.ndarray
    fact_aux_sum: np.ndarray
    query_vectors: np.ndarray
    query_groups: np.ndarray
    query_source_ids: np.ndarray


@dataclass
class SearchResult:
    ids: np.ndarray
    distances: np.ndarray
    candidates: int
    latency_ms: float


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["sanity", "full"], default="sanity")
    p.add_argument("--data-root", type=Path,
                   default=Path(os.environ.get("DATA_ROOT", "/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0")))
    p.add_argument("--dataset", choices=["all", "tpch_sift", "movielens"], default="all")
    p.add_argument("--force-prepare", action="store_true")
    p.add_argument("--analysis-only", action="store_true",
                   help="recompute statistics from completed query CSVs")
    return p.parse_args()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def prepare_tpch(data_root: Path, n: int, nq: int, force: bool) -> Dataset:
    cache = data_root / "prepared" / f"tpch_sift_n{n}_q{nq}.npz"
    if cache.exists() and not force:
        return load_dataset(cache, "tpch_sift")

    dbgen = (data_root / "work/Exqutor/Vector-augmented_SQL_analytics/dataset/"
             "third_party/tpch-kit/dbgen")
    part_path, lineitem_path = dbgen / "part.tbl", dbgen / "lineitem.tbl"
    sift_path = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/downloads/real/sift-128-euclidean.hdf5")
    if not (part_path.exists() and lineitem_path.exists() and sift_path.exists()):
        raise FileNotFoundError("TPC-H SF1 or SIFT1M input is missing")

    # DuckDB performs the 6M-row fact aggregation without materializing lineitem
    # in Python.  The result is cached on the data disk.
    agg_path = data_root / "prepared" / "tpch_part_fact_sf1.parquet"
    agg_path.parent.mkdir(parents=True, exist_ok=True)
    if force or not agg_path.exists():
        (data_root / "tmp").mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        con.execute("PRAGMA threads=8")
        con.execute("PRAGMA temp_directory=?", [str(data_root / "tmp")])
        query = f"""
        COPY (
          SELECT column01::BIGINT AS partkey,
                 COUNT(*)::DOUBLE AS fact_count,
                 SUM(column05::DOUBLE * (1.0-column06::DOUBLE)) AS fact_sum,
                 SUM(column04::DOUBLE) AS fact_aux_sum
          FROM read_csv('{lineitem_path}', delim='|', header=false,
                        auto_detect=true, all_varchar=true, null_padding=true)
          GROUP BY column01
        ) TO '{agg_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        con.execute(query)
        con.close()

    part_cols = ["partkey", "name", "mfgr", "brand", "type", "size",
                 "container", "retailprice", "comment"]
    parts = pd.read_csv(part_path, sep="|", header=None, names=part_cols,
                        usecols=[0, 2], nrows=n)
    facts = duckdb.sql(f"SELECT * FROM read_parquet('{agg_path}')").df()
    parts = parts.merge(facts, how="left", on="partkey").fillna(0.0)
    names = sorted(parts.mfgr.unique().tolist())
    gmap = {g: i for i, g in enumerate(names)}
    groups = parts.mfgr.map(gmap).to_numpy(np.int32)
    with h5py.File(sift_path) as h:
        vectors = np.asarray(h["train"][:n], dtype=np.float32)
        qvec = np.asarray(h["test"][:nq], dtype=np.float32)
    qgroups = np.arange(nq, dtype=np.int32) % len(names)
    source = np.full(nq, -1, dtype=np.int64)
    ds = Dataset("tpch_sift", vectors, groups, names,
                 parts.fact_count.to_numpy(np.float64),
                 parts.fact_sum.to_numpy(np.float64),
                 parts.fact_aux_sum.to_numpy(np.float64), qvec, qgroups, source)
    save_dataset(cache, ds)
    return ds


def prepare_movielens(data_root: Path, nq: int, force: bool) -> Dataset:
    cache = data_root / "prepared" / f"movielens_q{nq}.npz"
    if cache.exists() and not force:
        return load_dataset(cache, "movielens")
    raw = data_root / "raw/ml-20m"
    scores_path, movies_path, ratings_path = (raw / "genome-scores.csv",
                                               raw / "movies.csv", raw / "ratings.csv")
    if not all(p.exists() for p in [scores_path, movies_path, ratings_path]):
        raise FileNotFoundError("MovieLens-20M input is missing")

    scores = pd.read_csv(scores_path, dtype={"movieId": np.int32, "tagId": np.int16,
                                              "relevance": np.float32})
    mids = np.sort(scores.movieId.unique())
    mid_to_row = pd.Series(np.arange(len(mids), dtype=np.int32), index=mids)
    rows = mid_to_row.loc[scores.movieId].to_numpy(np.int32)
    cols = scores.tagId.to_numpy(np.int32) - 1
    dim = int(scores.tagId.max())
    vectors = np.zeros((len(mids), dim), dtype=np.float32)
    vectors[rows, cols] = scores.relevance.to_numpy(np.float32)
    # Cosine-like semantic geometry represented as unit-normalized L2.
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    del scores, rows, cols

    movies = pd.read_csv(movies_path).set_index("movieId").reindex(mids)
    primary = movies.genres.fillna("(no genres listed)").str.split("|").str[0]
    # Merge rare groups into OTHER so every local index has enough training data.
    counts = primary.value_counts()
    primary = primary.where(primary.map(counts) >= 80, "OTHER")
    names = sorted(primary.unique().tolist())
    gmap = {g: i for i, g in enumerate(names)}
    groups = primary.map(gmap).to_numpy(np.int32)

    agg_path = data_root / "prepared" / "movielens_rating_fact.parquet"
    agg_path.parent.mkdir(parents=True, exist_ok=True)
    if force or not agg_path.exists():
        (data_root / "tmp").mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        con.execute("PRAGMA threads=8")
        con.execute("PRAGMA temp_directory=?", [str(data_root / "tmp")])
        con.execute(f"""
          COPY (
            SELECT movieId::BIGINT AS movie_id, COUNT(*)::DOUBLE AS fact_count,
                   SUM(rating)::DOUBLE AS fact_sum,
                   SUM(CASE WHEN rating >= 4.0 THEN 1 ELSE 0 END)::DOUBLE AS fact_aux_sum
            FROM read_csv_auto('{ratings_path}', header=true)
            GROUP BY movieId
          ) TO '{agg_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        con.close()
    facts = duckdb.sql(f"SELECT * FROM read_parquet('{agg_path}')").df().set_index("movie_id")
    facts = facts.reindex(mids).fillna(0.0)

    rng = np.random.default_rng(SEED)
    eligible = np.flatnonzero(np.bincount(groups)[groups] >= 80)
    qids = rng.choice(eligible, size=min(nq, len(eligible)), replace=False)
    # A user intent need not equal an indexed movie.  Averaging two real movies
    # from the same genre gives non-synthetic labels while avoiding self-match.
    partners = []
    for qid in qids:
        pool = np.flatnonzero(groups == groups[qid])
        partner = int(rng.choice(pool[pool != qid]))
        partners.append(partner)
    qvec = vectors[qids] + vectors[np.asarray(partners)]
    qvec /= np.maximum(np.linalg.norm(qvec, axis=1, keepdims=True), 1e-12)
    qgroups = groups[qids].copy()
    ds = Dataset("movielens", vectors, groups, names,
                 facts.fact_count.to_numpy(np.float64), facts.fact_sum.to_numpy(np.float64),
                 facts.fact_aux_sum.to_numpy(np.float64), qvec, qgroups,
                 np.full(len(qids), -1, dtype=np.int64))
    save_dataset(cache, ds)
    return ds


def save_dataset(path: Path, ds: Dataset) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, vectors=ds.vectors, groups=ds.groups,
                        group_names=np.asarray(ds.group_names), fact_count=ds.fact_count,
                        fact_sum=ds.fact_sum, fact_aux_sum=ds.fact_aux_sum,
                        query_vectors=ds.query_vectors, query_groups=ds.query_groups,
                        query_source_ids=ds.query_source_ids)


def load_dataset(path: Path, name: str) -> Dataset:
    z = np.load(path, allow_pickle=False)
    return Dataset(name, z["vectors"], z["groups"], z["group_names"].tolist(),
                   z["fact_count"], z["fact_sum"], z["fact_aux_sum"],
                   z["query_vectors"], z["query_groups"], z["query_source_ids"])


class HNSWBundle:
    def __init__(self, ds: Dataset, out: Path, m: int = 12):
        self.ds, self.out, self.m = ds, out, m
        self.global_index = None
        self.locals: dict[int, tuple[hnswlib.Index, np.ndarray]] = {}
        self.meta: dict[str, dict] = {}

    def _build(self, x: np.ndarray, labels: np.ndarray, path: Path) -> tuple[hnswlib.Index, dict]:
        idx = hnswlib.Index(space="l2", dim=x.shape[1])
        idx.init_index(max_elements=len(x), ef_construction=100, M=self.m,
                       random_seed=SEED, allow_replace_deleted=False)
        split = max(1, int(len(x) * .99))
        t0 = time.perf_counter(); idx.add_items(x[:split], labels[:split], num_threads=8)
        build_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter(); idx.add_items(x[split:], labels[split:], num_threads=1)
        update_ms = (time.perf_counter() - t0) * 1000 / max(1, len(x)-split)
        path.parent.mkdir(parents=True, exist_ok=True); idx.save_index(str(path))
        return idx, {"bytes": path.stat().st_size, "build_ms": build_ms,
                     "update_ms_per_vector": update_ms}

    def build(self) -> None:
        self.global_index, self.meta["global"] = self._build(
            self.ds.vectors, np.arange(len(self.ds.vectors)), self.out / "global.bin")
        local_meta = []
        for g in range(len(self.ds.group_names)):
            ids = np.flatnonzero(self.ds.groups == g).astype(np.int64)
            idx, meta = self._build(self.ds.vectors[ids], ids, self.out / f"local_{g}.bin")
            self.locals[g] = (idx, ids); local_meta.append(meta)
        self.meta["local"] = {
            "bytes": sum(x["bytes"] for x in local_meta),
            "build_ms": sum(x["build_ms"] for x in local_meta),
            "update_ms_per_vector": statistics.fmean(x["update_ms_per_vector"] for x in local_meta),
        }

    def search(self, design: str, q: np.ndarray, group: int | None, k: int, effort: int) -> SearchResult:
        assert self.global_index is not None
        eligible = self.ds.groups == group if group is not None else np.ones(len(self.ds.groups), bool)
        source = -1
        t0 = time.perf_counter(); candidates = 0
        if design == "D0_postfilter":
            selectivity = float(eligible.mean())
            want = min(len(eligible), int(math.ceil(2*k/max(selectivity, 1e-12))))
            self.global_index.set_ef(max(effort, want))
            lab, dist = self.global_index.knn_query(q, k=want, num_threads=1)
            candidates = want; lab, dist = lab[0], dist[0]
            keep = eligible[lab] & (lab != source); lab, dist = lab[keep][:k], dist[keep][:k]
        elif design == "D1_prefilter":
            self.global_index.set_ef(max(effort, k))
            filt: Callable[[int], bool] = lambda x: bool(eligible[x])
            lab, dist = self.global_index.knn_query(q, k=k, num_threads=1, filter=filt)
            lab, dist = lab[0], dist[0]; candidates = k
        elif design == "D2_local":
            if group is not None:
                idx, _ = self.locals[group]; idx.set_ef(max(effort, k))
                lab, dist = idx.knn_query(q, k=min(k, idx.get_current_count()), num_threads=1)
                lab, dist = lab[0], dist[0]; candidates = len(lab)
            else:
                pieces = []
                for idx, _ in self.locals.values():
                    kk = min(k, idx.get_current_count()); idx.set_ef(max(effort, kk))
                    la, di = idx.knn_query(q, k=kk, num_threads=1)
                    pieces.extend(zip(di[0].tolist(), la[0].tolist())); candidates += kk
                pieces.sort(); dist = np.asarray([x[0] for x in pieces[:k]], np.float32)
                lab = np.asarray([x[1] for x in pieces[:k]], np.int64)
        elif design == "D3_joint_adaptive":
            want = k
            lab = dist = np.empty(0)
            while want <= min(len(eligible), k * 32):
                self.global_index.set_ef(max(effort, want))
                la, di = self.global_index.knn_query(q, k=want, num_threads=1)
                candidates += want; keep = eligible[la[0]]
                lab, dist = la[0][keep][:k], di[0][keep][:k]
                if len(lab) >= k or want == min(len(eligible), k * 32): break
                want = min(len(eligible), k * 32, want * 2)
        else: raise ValueError(design)
        return SearchResult(np.asarray(lab, np.int64), np.asarray(dist, np.float32),
                            candidates, (time.perf_counter()-t0)*1000)


class IVFBundle:
    def __init__(self, ds: Dataset, out: Path):
        self.ds, self.out = ds, out
        self.global_index = None
        self.locals: dict[int, faiss.IndexIVFFlat] = {}
        self.meta: dict[str, dict] = {}

    def _build(self, x: np.ndarray, labels: np.ndarray, path: Path) -> tuple[faiss.IndexIVFFlat, dict]:
        nlist = max(1, min(256, int(math.sqrt(len(x))), len(x)//40))
        idx = faiss.IndexIVFFlat(faiss.IndexFlatL2(x.shape[1]), x.shape[1], nlist)
        sample = x if len(x) <= 20000 else x[np.linspace(0, len(x)-1, 20000, dtype=int)]
        t0 = time.perf_counter(); idx.train(sample)
        split = max(1, int(len(x) * .99)); idx.add_with_ids(x[:split], labels[:split])
        build_ms = (time.perf_counter()-t0)*1000
        t0 = time.perf_counter(); idx.add_with_ids(x[split:], labels[split:])
        update_ms = (time.perf_counter()-t0)*1000/max(1, len(x)-split)
        path.parent.mkdir(parents=True, exist_ok=True); faiss.write_index(idx, str(path))
        return idx, {"bytes": path.stat().st_size, "build_ms": build_ms,
                     "update_ms_per_vector": update_ms, "nlist": nlist}

    def build(self) -> None:
        ids = np.arange(len(self.ds.vectors), dtype=np.int64)
        self.global_index, self.meta["global"] = self._build(
            self.ds.vectors, ids, self.out / "global.faiss")
        metas = []
        for g in range(len(self.ds.group_names)):
            ids = np.flatnonzero(self.ds.groups == g).astype(np.int64)
            idx, meta = self._build(self.ds.vectors[ids], ids, self.out / f"local_{g}.faiss")
            self.locals[g] = idx; metas.append(meta)
        self.meta["local"] = {"bytes": sum(x["bytes"] for x in metas),
                              "build_ms": sum(x["build_ms"] for x in metas),
                              "update_ms_per_vector": statistics.fmean(x["update_ms_per_vector"] for x in metas)}

    @staticmethod
    def _run(idx: faiss.IndexIVFFlat, q: np.ndarray, k: int, nprobe: int,
             selector=None) -> tuple[np.ndarray, np.ndarray]:
        params = faiss.SearchParametersIVF(nprobe=min(nprobe, idx.nlist), sel=selector)
        dist, lab = idx.search(q.reshape(1, -1), k, params=params)
        keep = lab[0] >= 0
        return lab[0][keep], dist[0][keep]

    def search(self, design: str, q: np.ndarray, group: int | None, k: int, effort: int) -> SearchResult:
        assert self.global_index is not None
        eligible = self.ds.groups == group if group is not None else np.ones(len(self.ds.groups), bool)
        t0 = time.perf_counter(); candidates = 0
        if design == "D0_postfilter":
            selectivity = float(eligible.mean())
            want = min(len(eligible), int(math.ceil(2*k/max(selectivity, 1e-12))))
            lab, dist = self._run(self.global_index, q, want, effort)
            candidates = want; keep = eligible[lab]; lab, dist = lab[keep][:k], dist[keep][:k]
        elif design == "D1_prefilter":
            ids = np.flatnonzero(eligible).astype(np.int64)
            selector = faiss.IDSelectorArray(ids)
            lab, dist = self._run(self.global_index, q, k, effort, selector); candidates = k
        elif design == "D2_local":
            if group is not None:
                lab, dist = self._run(self.locals[group], q, k, effort); candidates = len(lab)
            else:
                pieces = []
                for idx in self.locals.values():
                    la, di = self._run(idx, q, k, effort); candidates += len(la)
                    pieces.extend(zip(di.tolist(), la.tolist()))
                pieces.sort(); dist = np.asarray([x[0] for x in pieces[:k]], np.float32)
                lab = np.asarray([x[1] for x in pieces[:k]], np.int64)
        elif design == "D3_joint_adaptive":
            want = k; lab = dist = np.empty(0)
            while want <= min(len(eligible), k*32):
                la, di = self._run(self.global_index, q, want, effort); candidates += want
                keep = eligible[la]; lab, dist = la[keep][:k], di[keep][:k]
                if len(lab) >= k or want == min(len(eligible), k*32): break
                want = min(len(eligible), k*32, want*2)
        else: raise ValueError(design)
        return SearchResult(np.asarray(lab, np.int64), np.asarray(dist, np.float32),
                            candidates, (time.perf_counter()-t0)*1000)


def exact_search(ds: Dataset, q: np.ndarray, group: int | None, k: int,
                 source_id: int) -> SearchResult:
    ids = np.arange(len(ds.vectors), dtype=np.int64)
    if group is not None: ids = ids[ds.groups == group]
    if source_id >= 0: ids = ids[ids != source_id]
    t0 = time.perf_counter()
    d = np.sum((ds.vectors[ids] - q) ** 2, axis=1)
    take = min(k, len(ids)); pos = np.argpartition(d, take-1)[:take]
    order = pos[np.argsort(d[pos])]
    return SearchResult(ids[order], d[order].astype(np.float32), len(ids),
                        (time.perf_counter()-t0)*1000)


def rank_overlap(ds: Dataset, ids_a: np.ndarray, ids_b: np.ndarray, top: int = 3) -> float:
    def ranks(ids: np.ndarray) -> list[int]:
        scores = np.bincount(ds.groups[ids], weights=ds.fact_count[ids],
                             minlength=len(ds.group_names))
        return np.argsort(-scores)[:top].tolist()
    a, b = ranks(ids_a), ranks(ids_b)
    return len(set(a) & set(b)) / max(1, len(set(a) | set(b)))


def metrics(ds: Dataset, exact: SearchResult, approx: SearchResult) -> dict[str, float]:
    exact_set, approx_set = set(exact.ids.tolist()), set(approx.ids.tolist())
    hit = np.asarray([i for i in approx.ids if int(i) in exact_set], dtype=np.int64)
    missed = np.asarray([i for i in exact.ids if int(i) not in approx_set], dtype=np.int64)
    recall = len(hit) / max(1, len(exact.ids))
    ec, es, ea = (ds.fact_count[exact.ids].sum(), ds.fact_sum[exact.ids].sum(),
                  ds.fact_aux_sum[exact.ids].sum())
    ac, ass, aa = (ds.fact_count[approx.ids].sum(), ds.fact_sum[approx.ids].sum(),
                   ds.fact_aux_sum[approx.ids].sum())
    rel = lambda x, y: abs(x-y) / max(abs(x), 1e-12)
    exact_avg, approx_avg = es/max(ec, 1e-12), ass/max(ac, 1e-12)
    exact_aux_avg, approx_aux_avg = ea/max(ec, 1e-12), aa/max(ac, 1e-12)
    exact_groups = set(ds.groups[exact.ids].tolist())
    hit_groups = set(ds.groups[hit].tolist()) if len(hit) else set()
    miss_weight = ds.fact_count[missed] if len(missed) else np.empty(0)
    high_cut = np.quantile(ds.fact_count[exact.ids], .75) if len(exact.ids) else 0
    high_fn = float(miss_weight[miss_weight >= high_cut].sum()/max(miss_weight.sum(), 1e-12))
    if len(missed):
        gm = np.bincount(ds.groups[missed], weights=miss_weight, minlength=len(ds.group_names))
        p = gm / max(gm.sum(), 1e-12); fn_hhi = float(np.square(p).sum())
    else: fn_hhi = 0.0
    return {
        "local_recall": recall,
        "join_tuple_recall": float(ds.fact_count[hit].sum()/max(ec, 1e-12)),
        "group_coverage": len(hit_groups)/max(1, len(exact_groups)),
        "count_rel_error": rel(ec, ac), "sum_rel_error": rel(es, ass),
        "avg_rel_error": rel(exact_avg, approx_avg),
        "aux_avg_rel_error": rel(exact_aux_avg, approx_aux_avg),
        "top_group_rank_overlap": rank_overlap(ds, exact.ids, approx.ids),
        "fn_high_weight_share": high_fn, "fn_group_hhi": fn_hhi,
        "false_negative_count": float(len(missed)),
    }


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator, rounds: int = 2000) -> tuple[float, float]:
    if len(values) < 2: return float("nan"), float("nan")
    sample_ids = rng.integers(0, len(values), size=(rounds, len(values)))
    means = values[sample_ids].mean(axis=1)
    return tuple(np.quantile(means, [.025, .975]).tolist())


def analyze(records: list[dict], k: int) -> dict:
    df = pd.DataFrame(records)
    summary = (df.groupby(["dataset", "query_family", "ann", "design", "effort"], as_index=False)
               .agg(local_recall=("local_recall", "mean"),
                    downstream_error=("downstream_error", "mean"),
                    join_tuple_recall=("join_tuple_recall", "mean"),
                    latency_ms=("latency_ms", "mean"), candidates=("candidates", "mean"),
                    bytes=("index_bytes", "first")))
    rng = np.random.default_rng(SEED + 99); pairs = []
    keys = ["dataset", "query_family", "ann"]
    for key, sub in df.groupby(keys):
        configs = list(sub.groupby(["design", "effort"]))
        for i, (ca, a) in enumerate(configs):
            for cb, b in configs[i+1:]:
                if ca[0] == cb[0]: continue
                m = a.merge(b, on="query_id", suffixes=("_a", "_b"))
                if len(m) < 5: continue
                rd = (m.local_recall_a-m.local_recall_b).to_numpy()
                ed = (m.downstream_error_a-m.downstream_error_b).to_numpy()
                if abs(rd.mean()) > 1/k: continue
                rci = bootstrap_ci(rd, rng)
                # One retrieved item is the natural measurement resolution at
                # Recall@k.  Equivalence requires the complete paired 95% CI to
                # remain inside that +/-1/k band (TOST-style criterion).
                equivalent = rci[0] >= -1/k and rci[1] <= 1/k
                if not equivalent: continue
                eci = bootstrap_ci(ed, rng)
                significant = not (eci[0] <= 0 <= eci[1])
                pairs.append({"dataset": key[0], "query_family": key[1], "ann": key[2],
                              "a": f"{ca[0]}@{ca[1]}", "b": f"{cb[0]}@{cb[1]}",
                              "recall_diff": rd.mean(), "recall_diff_ci95": rci,
                              "error_diff": ed.mean(), "error_diff_ci95": eci,
                              "downstream_significant": significant})
    qualifying = [p for p in pairs if p["downstream_significant"]]
    datasets = sorted({p["dataset"] for p in qualifying})
    families = sorted({(p["dataset"], p["query_family"]) for p in qualifying})
    affected_query_families = sorted({p["query_family"] for p in qualifying})
    structural_pass = len(datasets) == 2 and len(affected_query_families) >= 2
    return {"summary": summary.to_dict(orient="records"), "matched_recall_pairs": pairs,
            "qualifying_pairs": qualifying, "datasets_with_effect": datasets,
            "dataset_family_effects": [list(x) for x in families],
            "affected_query_families": affected_query_families,
            "structural_pass": structural_pass,
            "decision": "CONTINUE_TO_ORACLE" if structural_pass else "KILL_AT_ERROR_PROPAGATION"}


def run_dataset(ds: Dataset, data_root: Path, mode: str) -> tuple[list[dict], dict]:
    out = data_root / "runs" / mode / ds.name
    out.mkdir(parents=True, exist_ok=True)
    bundles = {"hnsw": HNSWBundle(ds, out / "indices/hnsw"),
               "ivf": IVFBundle(ds, out / "indices/ivf")}
    for bundle in bundles.values(): bundle.build()
    designs = ["D0_postfilter", "D1_prefilter", "D2_local", "D3_joint_adaptive"]
    efforts = {"hnsw": [32, 64] if mode == "sanity" else [16, 32, 64, 128],
               "ivf": [2, 8] if mode == "sanity" else [1, 2, 4, 8, 16]}
    records: list[dict] = []
    for qi, (q, qg, source) in enumerate(zip(ds.query_vectors, ds.query_groups, ds.query_source_ids)):
        for family, group in [("scalar_filter_topk_join", int(qg)),
                              ("threshold_join_group_aggregate", None)]:
            exact = exact_search(ds, q, group, K, int(source))
            threshold = float(exact.distances[-1]) if len(exact.distances) else float("inf")
            for ann, bundle in bundles.items():
                for effort in efforts[ann]:
                    for design in designs:
                        result = bundle.search(design, q, group, K, effort)
                        if source >= 0:
                            keep = result.ids != source
                            result.ids, result.distances = result.ids[keep], result.distances[keep]
                        if family.startswith("threshold"):
                            keep = result.distances <= threshold
                            result.ids, result.distances = result.ids[keep], result.distances[keep]
                        row = metrics(ds, exact, result)
                        scope = "local" if design == "D2_local" else "global"
                        meta = bundle.meta[scope]
                        row.update({"dataset": ds.name, "query_id": qi, "query_family": family,
                                    "group": int(qg), "ann": ann, "design": design,
                                    "effort": effort, "k": K, "threshold": threshold,
                                    "returned": len(result.ids), "candidates": result.candidates,
                                    "latency_ms": result.latency_ms,
                                    "index_bytes": meta["bytes"], "build_ms": meta["build_ms"],
                                    "update_ms_per_vector": meta["update_ms_per_vector"]})
                        row["downstream_error"] = statistics.fmean([
                            row["count_rel_error"], row["sum_rel_error"], row["avg_rel_error"],
                            1-row["top_group_rank_overlap"]])
                        records.append(row)
        if (qi + 1) % 5 == 0: print(f"{ds.name}: {qi+1}/{len(ds.query_vectors)} queries", flush=True)
    pd.DataFrame(records).to_csv(out / "query_records.csv", index=False)
    atomic_json(out / "index_metadata.json", {a: b.meta for a, b in bundles.items()})
    return records, {a: b.meta for a, b in bundles.items()}


def main() -> None:
    args = parse_args(); root = args.data_root
    if not root.is_dir(): raise FileNotFoundError(root)
    if args.analysis_only:
        result_dir = root / "runs" / args.mode
        names = ["tpch_sift", "movielens"] if args.dataset == "all" else [args.dataset]
        frames = [pd.read_csv(result_dir / name / "query_records.csv") for name in names]
        analysis = analyze(pd.concat(frames, ignore_index=True).to_dict(orient="records"), K)
        atomic_json(result_dir / "analysis.json", analysis)
        print(json.dumps({"decision": analysis["decision"],
                          "qualifying_pairs": len(analysis["qualifying_pairs"])}, indent=2))
        return
    n, nq = (20_000, 12) if args.mode == "sanity" else (200_000, 60)
    datasets = []
    if args.dataset in ("all", "tpch_sift"):
        datasets.append(prepare_tpch(root, n, nq, args.force_prepare))
    if args.dataset in ("all", "movielens"):
        datasets.append(prepare_movielens(root, nq, args.force_prepare))
    all_records, metadata = [], {}
    for ds in datasets:
        print(f"running {ds.name}: n={len(ds.vectors)}, d={ds.vectors.shape[1]}, q={len(ds.query_vectors)}")
        rec, meta = run_dataset(ds, root, args.mode); all_records.extend(rec); metadata[ds.name] = meta
    analysis = analyze(all_records, K)
    result_dir = root / "runs" / args.mode
    atomic_json(result_dir / "analysis.json", analysis)
    atomic_json(result_dir / "manifest.json", {
        "seed": SEED, "mode": args.mode, "k": K,
        "datasets": [{"name": d.name, "n": len(d.vectors), "dim": d.vectors.shape[1],
                      "queries": len(d.query_vectors), "groups": d.group_names} for d in datasets],
        "metadata": metadata, "decision": analysis["decision"]})
    print(json.dumps({"decision": analysis["decision"],
                      "qualifying_pairs": len(analysis["qualifying_pairs"])}, indent=2))


if __name__ == "__main__":
    main()
