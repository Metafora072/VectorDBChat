# Z0A-R2 canonical packing / independent readback audit

## Verdict

The packing and 4 KiB materialization path is implementable, but the existing
DGAI FULL-R1 artifact is not a valid final-closure trace.  It records file
extension writes and omits the later truncate that restores the original EOF.
The existing OdinANN FULL-R1 artifact does close.

This is a closure audit only.  It does not authorize Z0B and it does not turn
the short-trace HostWA into a research result.

## Independent prototypes

- `canonical_pack.py`: reads the initial-live JSONL and an immutable pre-run
  snapshot; verifies the complete file set, size and SHA-256; sorts pages by
  `(file_role, stable_object_id, aligned_page_offset)`; writes a sparse logical
  zone image plus a JSONL physical map.
- `independent_readback.py`: imports neither the packer nor either simulator.
  It independently parses the initial JSONL, packing map/image, raw ABI,
  normalized-page ABI and trace metadata; rederives the raw-request split;
  classifies every page event as replacement or new; and checks final live-set
  equality against the recorded final snapshot.
- `short_closure_config.json`: closure-only geometry: 4 KiB blocks, 4 MiB zone
  size/capacity, 32 zones, max-open 1, max-active 30 and two host spares.  This
  is a fixed harness configuration, not a parameter sweep or device claim.

Both programs create outputs exclusively and fail closed.  A completed run's
`clone_root` is a final, mutated snapshot and must not be supplied as the
pre-run snapshot.  Packing must run before the workload, or from a separately
preserved snapshot whose complete file set and hashes equal the initial
manifest.

## Physical-map interface

The JSONL begins with one `packing_header`, contains one `packed_page` for
every initial-live page, and ends with one complete `packing_trailer`.

Each packed page contains at least:

```text
packing_index
page_key
stable_object_id
file_role
aligned_page_offset
page_bytes
allocated_append_bytes = 4096
padding_bytes = 4096 - page_bytes
zone_id
zone_offset
physical_image_offset
initial_version = 0
payload_sha256
```

The physical image is the logical ZNS address space.  Each mapped 4 KiB block
contains the exact snapshot bytes followed by zero padding for a partial tail.
Ordinary zones precede the fixed spare-zone suffix.  No initial page may enter
a spare zone or exceed zone capacity.  The trailer closes logical bytes,
allocated bytes, padding bytes, used/active zones and the exact spare-zone set.

## Fixed 4 KiB materialization and byte accounts

One normalized touched page produces one full 4096-byte appended logical-page
version.  This is the only write materialization used by the prototype.

```text
application_bytes
  = sum(successful raw returned bytes)

normalized_fragment_bytes
  = sum(page intersection bytes)
  = application_bytes

allocated_append_bytes
  = 4096 * normalized page-event count

replacement_rmw_read_bytes
  = sum(4096 - fragment_bytes) for partial replacement events

new_page_zero_fill_bytes
  = sum(4096 - fragment_bytes) for partial first-version events

relocation_allocated_bytes
  = 4096 * relocated current-page count
  (reported by the simulator, not added by the validator)
```

`replacement_rmw_read_bytes` is a reconstruction read cost, not another ZNS
write.  `new_page_zero_fill_bytes` is synthesized content inside the allocated
4 KiB append.  HostWA must use allocated appends plus allocated relocation
bytes; it must not call application returned bytes "new logical page bytes".
Application-byte expansion and page-log HostWA should be reported separately.

## Replay closure results on the existing FULL-R1 artifacts

### OdinANN FULL-R1: positive end-to-end witness

The pre-run snapshot was reconstructed from the immutable sanity index and
matched all five initial-manifest hashes.  Canonical packing and independent
readback both passed.

```text
initial live pages                    1,752
initial logical bytes             7,168,436
initial allocated append bytes    7,176,192
initial zero padding                  7,756

raw requests                         19,837
normalized page events               24,231
application/fragment bytes       99,197,976
allocated append bytes           99,250,176
new-page events                        3,005
replacement events                    21,226
new-page zero-fill bytes               12,920
replacement RMW read bytes             39,280

replayed/final live pages              4,757 / 4,757
missing / extra pages                      0 / 0
final logical bytes               19,469,160
```

This proves the interface can close a real short FULL trace.  It does not yet
prove simulator/reference per-event equality; the emitted replay spec is the
input for that separate gate.

### DGAI FULL-R1: negative lifecycle witness

Canonical packing itself passed using a hash-identical pre-run sanity snapshot:

```text
initial live pages                    4,428
initial logical bytes            18,111,652
initial allocated append bytes   18,137,088
initial zero padding                 25,436
```

Independent replay then failed final closure:

```text
normalized page events               22,250
application/fragment bytes       91,127,960
allocated append bytes           91,136,000
new-page events                        1,499
replacement events                    20,751
replacement RMW read bytes              8,040

write-only replay live pages           5,927
final snapshot live pages              4,428
missing / extra pages                      0 / 1,499
```

All 1,499 extra pages belong to the initial `index_disk.index` incarnation.
Their offsets are `6,832,128..12,967,936`; the final file size is exactly
`6,832,128`.  Therefore the trace captured a temporary extension and did not
capture the later EOF truncate.  Applying the final snapshot as an unordered
post-hoc tombstone would hide the missing lifecycle event and is not accepted.

## Required lifecycle interface for a formal DGAI R2 trace

The next DGAI FULL trace must use one ordered event domain for data and
namespace/size lifecycle.  A sidecar that lacks a common order with write
submissions is insufficient.  The minimum unified record is:

```text
global_seq                 # one monotonically increasing order domain
event_kind                 # WRITE | TRUNCATE | CREATE | RENAME | UNLINK
run_hash
object_incarnation         # stable across rename
thread_id / thread_seq
phase / source / file_role
monotonic_timestamp_ns
status                     # only successful lifecycle effects alter replay

# WRITE
request_id / offset / requested_bytes / returned_bytes / status

# TRUNCATE
old_size_bytes / new_size_bytes

# CREATE, RENAME, UNLINK
path_hash_before / path_hash_after / link_count_after
```

`global_seq` is the replay linearization order, not an independently numbered
sidecar sequence.  Under the current submit-ordered append model, a WRITE gets
this sequence at accepted submission.  A lifecycle event must be ordered in
the same domain after the applicable async-write drain/barrier.  If a truncate
or unlink overlaps in-flight writes and the tracer cannot establish a unique
linearization, the trace is ambiguous and must fail validation rather than be
ordered from timestamps.

Required replay rules:

1. A successful `WRITE` is split and materialized in `global_seq` order.
2. A shrinking `TRUNCATE` invalidates every current page whose aligned offset
   is at or beyond the new EOF.  Its surviving partial tail has
   `page_bytes = new_size % 4096`; a shrink alone writes no ZNS append.
3. An extending `TRUNCATE` changes EOF but creates holes, not physical appends.
   Hole policy must be explicit in both initial and final manifests.
4. `RENAME` preserves the object incarnation and only changes the path binding.
5. `UNLINK` removes the object's current live set only when the last link is
   gone.  `CREATE` registers a new run-local incarnation before its first write.
6. The independent validator must rederive the ordered live set without using
   the final snapshot as input; the snapshot is used only as the final oracle.

For the observed DGAI artifact, a recorded successful shrink from at least
`12,972,032` bytes to `6,832,128` after the extension writes should remove the
1,499 tail pages.  The exact old size and order must come from instrumentation,
not inference from this audit.

## Final-snapshot closure boundary

The v1 write trace carries no write payload.  Consequently the independent
validator can prove exact object identity, file/page membership, EOF-derived
page count and byte-account closure, but cannot reconstruct and compare final
payload hashes from the trace alone.  Payload lineage must not be claimed.

For R2 the accepted final closure is:

```text
replayed logical live-page key set == final snapshot page-key set
replayed EOF/page_bytes metadata     == final snapshot sizes
final snapshot file hashes           recorded as oracle evidence
```

If byte-for-byte replay content is required later, the trace ABI must add
payload bytes or content hashes and the RMW source semantics; it cannot be
retroactively inferred from the current offset/length records.

## Gate consequence

- OdinANN FULL-R1 is usable as the positive packing/readback closure witness.
- DGAI FULL-R1 is not usable as the formal R2 replay witness.
- Recollect one DGAI FULL short trace with ordered truncate lifecycle capture,
  then rerun the independent validator before simulator/reference replay.
- If ordered DGAI lifecycle capture still cannot close exactly, the gate's
  `final-live set cannot close` KILL condition applies.  Do not repair it with
  a final-snapshot-derived delete list.
