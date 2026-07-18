#!/usr/bin/env python3
"""Derive the tracer TSV registry from the authoritative JSONL manifest."""
import argparse, json
from pathlib import Path


ROLE = {
    "active_graph_vector": 1, "shadow_graph_vector": 2,
    "long_lived_aux_graph_source": 3, "long_lived_aux_vector_source": 4,
    "active_tags": 5, "shadow_tags": 5,
    "active_pq_vectors": 6, "active_pq_pivots": 6,
    "shadow_pq_vectors": 6, "shadow_pq_pivots": 6,
    "long_lived_aux_pq_vectors": 6, "long_lived_aux_pq_vectors_refined": 6,
    "long_lived_aux_pq_pivots": 6, "long_lived_aux_pq_pivots_refined": 6,
    "long_lived_aux_mapping": 7, "long_lived_aux_reorder_mapping": 7,
    "long_lived_aux_reordered_graph": 8, "control_marker": 10,
}


def main():
    p=argparse.ArgumentParser(); p.add_argument('--manifest',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    header=None; rows=[]
    for line in a.manifest.read_text().splitlines():
        row=json.loads(line)
        if row['record_type']=='manifest_header': header=row
        elif row['record_type']=='object': rows.append(row)
    if not header or not rows: raise SystemExit('manifest lacks header/objects')
    expected={f"{header['run_id']}:{row['object_incarnation']}" for row in rows}
    actual={row['stable_object_id'] for row in rows}
    if actual != expected: raise SystemExit('stable identity/incarnation mismatch')
    with a.output.open('x') as out:
        out.write('# incarnation device inode ctime_ns role absolute_path\n')
        root=Path(header['clone_root'])
        for row in sorted(rows,key=lambda r:r['object_incarnation']):
            role=ROLE.get(row['file_role'])
            if role is None: raise SystemExit(f"unmapped role {row['file_role']}")
            path=(root/row['relative_path']).resolve(strict=True)
            out.write(f"{row['object_incarnation']} {row['device_number']} {row['inode']} {row['ctime_ns']} {role} {path}\n")


if __name__=='__main__': main()
