#!/usr/bin/env python3
"""Prepare the deterministic 1% replace-new checkpoint-1 inputs.

This tool is intentionally data-only: it never opens or mutates an index.  It
must be invoked only after the W1 execution gate is granted.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, os, struct
from pathlib import Path
import numpy as np

SEED = 20260713
COUNT = 80_000

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()

def header(path: Path) -> tuple[int, int]:
    with path.open('rb') as f: raw = f.read(8)
    if len(raw) != 8: raise ValueError(f'short header: {path}')
    return struct.unpack('<II', raw)

def read_tags(path: Path) -> np.ndarray:
    n, d = header(path)
    if d != 1 or path.stat().st_size != 8 + n * 4: raise ValueError(f'invalid tag file: {path}')
    return np.asarray(np.memmap(path, dtype='<u4', mode='r', offset=8, shape=(n,)))

def write_bin(path: Path, values: np.ndarray) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('wb') as f:
        f.write(struct.pack('<II', values.size, 1)); values.astype('<u4', copy=False).tofile(f)
    os.replace(tmp, path)

def materialize_vectors(full: Path, tags: np.ndarray, out: Path) -> None:
    n, dim = header(full)
    if tags.size == 0 or int(tags.max()) >= n: raise ValueError('tag out of full-corpus range')
    if full.stat().st_size != 8 + n * dim * 4: raise ValueError(f'invalid full corpus: {full}')
    src = np.memmap(full, dtype='<f4', mode='r', offset=8, shape=(n, dim))
    tmp = out.with_suffix(out.suffix + '.tmp')
    with tmp.open('wb') as f:
        f.write(struct.pack('<II', tags.size, dim))
        for lo in range(0, tags.size, 16384):
            np.asarray(src[tags[lo:lo + 16384]], dtype='<f4').tofile(f)
    os.replace(tmp, out)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--count', type=int, default=COUNT)
    p.add_argument('--materialize-active', action='store_true')
    p.add_argument('--authorized', action='store_true', help='required to write a real checkpoint')
    a = p.parse_args()
    if not a.authorized: raise SystemExit('refusing preparation without --authorized (W1 gate required)')
    if a.count != COUNT: raise SystemExit(f'W1-C requires exactly {COUNT} replacements')
    ds, out = a.dataset.resolve(), a.output_dir.resolve()
    active = read_tags(ds / 'active_cp00.tags.bin')
    if active.size != 8_000_000 or np.unique(active).size != active.size: raise ValueError('invalid checkpoint-0 active set')
    rows: list[dict[str, str]] = []
    with (ds / 'replace_new_trace.csv').open(newline='') as f:
        reader = csv.DictReader(f)
        for _ in range(a.count):
            try: rows.append(next(reader))
            except StopIteration as exc: raise ValueError('source trace shorter than 80K') from exc
    deletes = np.asarray([int(r['delete_tag']) for r in rows], dtype='<u4')
    inserts = np.asarray([int(r['insert_tag']) for r in rows], dtype='<u4')
    if np.unique(deletes).size != a.count or np.unique(inserts).size != a.count: raise ValueError('trace tags are not unique')
    if np.intersect1d(deletes, inserts).size or not np.all(np.isin(deletes, active)) or np.any(np.isin(inserts, active)):
        raise ValueError('trace does not form a replace-new transition')
    expected = np.sort(np.concatenate((active[~np.isin(active, deletes)], inserts))).astype('<u4', copy=False)
    if expected.size != active.size or np.unique(expected).size != expected.size: raise ValueError('invalid checkpoint-1 cardinality')
    out.mkdir(parents=True, exist_ok=False)
    trace = out / 'replace_cp01_80k.bin'
    with trace.open('wb') as f:
        f.write(struct.pack('<i', a.count)); deletes.tofile(f); inserts.tofile(f)
    with (out / 'replace_cp01_80k.tsv').open('w', newline='') as f:
        w = csv.writer(f, delimiter='\t'); w.writerow(['op_seq','delete_tag','insert_tag','insert_source_row'])
        for i, r in enumerate(rows): w.writerow([i, deletes[i], inserts[i], r.get('insert_source_row', inserts[i])])
    write_bin(out / 'active_cp01.tags.bin', expected)
    positions = sorted(set([0, a.count - 1] + [round(i * (a.count - 1) / 7) for i in range(1, 7)]))
    probes = []
    for pos in positions:
        probes += [{'ordinal': len(probes), 'op_seq': pos, 'kind': 'insert', 'query_tag': int(inserts[pos]), 'expected_tag': int(inserts[pos])},
                   {'ordinal': len(probes) + 1, 'op_seq': pos, 'kind': 'delete', 'query_tag': int(deletes[pos]), 'forbidden_tag': int(deletes[pos])}]
    (out / 'visibility_probes.json').write_text(json.dumps({'schema':'dynamic-vamana-w1-probes-v1','selection':'first,last,seven equally spaced trace positions','probes':probes}, indent=2) + '\n')
    if a.materialize_active:
        materialize_vectors(ds / 'full_10m.bin', expected, out / 'active_cp01.bin')
        full_n, dim = header(ds / 'full_10m.bin'); full = np.memmap(ds / 'full_10m.bin', dtype='<f4', mode='r', offset=8, shape=(full_n, dim))
        query_tags = np.asarray([x['query_tag'] for x in probes], dtype=np.uint32)
        tmp = out / 'visibility_probes.bin.tmp'
        with tmp.open('wb') as f:
            f.write(struct.pack('<II', query_tags.size, dim)); np.asarray(full[query_tags], dtype='<f4').tofile(f)
        os.replace(tmp, out / 'visibility_probes.bin')
    manifest = {'schema':'dynamic-vamana-w1-trace-v1','seed':SEED,'operation_count':a.count,'delete_count':a.count,'insert_count':a.count,
                'initial_active_set_sha256':sha(ds/'active_cp00.tags.bin'),'delete_tag_sha256':hashlib.sha256(deletes.tobytes()).hexdigest(),
                'insert_tag_sha256':hashlib.sha256(inserts.tobytes()).hexdigest(),'binary_trace_sha256':sha(trace),
                'expected_cp01_active_set_sha256':sha(out/'active_cp01.tags.bin'),'expected_active_cardinality':int(expected.size),
                'source_trace_sha256':sha(ds/'replace_new_trace.csv')}
    (out / 'replace_cp01_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__': main()
