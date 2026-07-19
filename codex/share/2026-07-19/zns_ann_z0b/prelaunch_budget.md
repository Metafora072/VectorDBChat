# ZNS-ANN Z0B prelaunch space and time budget

## 1. Scope and verdict

This is a read-only-derived prelaunch budget for the GPT-authorized
`Z0B Sequence-Only Endpoint Reclaim` gate.  It covers exactly:

```text
DGAI 50K, 3 independent FULL traces
OdinANN 400K, 3 independent FULL traces
```

No Z0B run has been started.  At audit time there was no Z0B experiment
directory and no Z0B process.  The measurements below come from the frozen M3
endpoints and the completed Z0A-R2 implementation.

The existing R2 storage representation is **not launchable at Z0B scale**:

- retaining its sparse-but-payload-populated images gives an estimated new
  footprint of `233.47 GiB` before failure/compression/safety allowance;
- map-only with the current expanded JSON replay specification still gives
  `146.60 GiB` before those allowances;
- both violate the gate's requirement to stop before launch when expected
  peak exceeds `150 GiB`.

The only approved prelaunch representation in this budget is:

```text
compact binary/extent manifests
compact map-only initial placement
no retained or temporary payload image
streaming raw/normalized replay; no expanded replay_spec JSON
streaming main/reference comparison; no per-event state log
compact final-live manifest
placement seed/boundary/digest records instead of duplicated full maps
```

Its corrected central expected peak is `128.36 GiB`; the preregistered
accounting range is `128–129 GiB`.  This is below `150 GiB`, and its `1.5x`
requirement is at most `193.5 GiB`, well below the measured `849.46 GiB` available on
`/dev/nvme8n1`.  This space verdict does not by itself authorize execution:
the compact formats and streaming replay must first pass their own short
closure and throughput/RAM preflight.

## 2. Device and existing read-only inputs

At the audit point:

```text
mount/source       /home/ubuntu/pz/VectorDB/data -> /dev/nvme8n1
major:minor        259:10
filesystem         ext4
available bytes    912,102,715,392 B
available GiB      849.46 GiB
```

The two immutable CP10 initial snapshots already exist on that filesystem and
are part of the prelaunch dependency set, but create no new allocation when
Z0B starts:

| System | Apparent bytes | Allocated bytes | 4 KiB pages | Allocated page bytes |
|---|---:|---:|---:|---:|
| DGAI | 14,131,068,900 | 14,130,737,152 | 3,449,976 | 14,131,101,696 |
| OdinANN | 16,960,280,936 | 16,960,311,296 | 4,140,698 | 16,960,299,008 |
| Total | 31,091,349,836 | 31,091,048,448 | 7,590,674 | 31,091,400,704 |

Their allocated total is `28.956 GiB`.  It is reported explicitly because the
GPT gate lists initial snapshots, but it is not duplicated into the Z0B root
and therefore is not part of the incremental `126–128 GiB` launch peak.  The
free-space measurement above was taken after these snapshots already existed.
If a future implementation copies either snapshot into the Z0B root, this
budget becomes invalid and launch must stop for a new review.

The frozen roots are:

```text
formal/pilot3_sift10m_w1_cp10_trajectory_r12/
  DGAI/trajectory-cp10-12/index
  OdinANN/trajectory-cp10-12/index
```

M3 confirmed that a fresh mutable clone has the same final apparent size as
its corresponding initial snapshot.  The frozen snapshot, M0–M3 evidence,
Z0A/Z0A-R2 artifacts, datasets, input prefixes and accepted builds remain
read-only dependencies and are never cleanup candidates.

## 3. Measured endpoint bases

The following are measured from the accepted M3 runs, not synthetic scaling
assumptions:

| Endpoint | Raw requests per trace | Normalized 4 KiB events per trace | Allocated update-page bytes | M3 workload wall |
|---|---:|---:|---:|---:|
| DGAI-50K | 118,207 | 1,789,678 | 7,330,521,088 | 70.956 s |
| OdinANN-400K | 16,219,270 | 21,794,291 | 89,269,415,936 | 537.600 s |

The update-page-byte formula is always `normalized_events * 4096`; it is an
application-to-ZNS byte account and is not retained as a payload file.

For storage estimation, the accepted ABIs are:

```text
raw request record       156 B, plus 176 B header
normalized page record    64 B, plus 32 B header
```

OdinANN has natural concurrent variation, so the final 15% safety allowance
must absorb a realization above this measured M3 anchor.  It is forbidden to
discard or replace a larger valid realization merely to recover budget.

## 4. GPT gate line-item budget

### 4.1 Six mutable clones

| Endpoint | Per clone | Three clones |
|---|---:|---:|
| DGAI-50K | 13.161 GiB | 39.482 GiB |
| OdinANN-400K | 15.795 GiB | 47.386 GiB |
| Total | — | **86.868 GiB** |

All six clones are retained through final-snapshot closure and GPT review.
The trace has no payload lineage, so a final clone cannot be deleted early and
replaced only by hashes.

### 4.2 Six raw traces

Using `176 + requests * 156` bytes per trace:

| Endpoint | Per trace | Three traces |
|---|---:|---:|
| DGAI-50K | 18,440,468 B | 0.052 GiB |
| OdinANN-400K | 2,530,206,296 B | 7.069 GiB |
| Total | — | **7.121 GiB** |

Lifecycle records and trace metadata are covered by the miscellaneous/state
allowance below.  Trace capacity must be preregistered above the measured
request count; buffer overflow or a dropped event stops the sequence and is
not repaired by replacing the run.

### 4.3 Six normalized traces

Using `32 + events * 64` bytes per trace (the exact `Z0BNORM1` ABI):

| Endpoint | Per trace | Three traces |
|---|---:|---:|
| DGAI-50K | 114,539,424 B | 0.320 GiB |
| OdinANN-400K | 1,394,834,656 B | 3.897 GiB |
| Total | — | **4.217 GiB** |

The simulator reads this representation as a stream.  It must not expand it
into the R2 JSON `replay_spec` format.

### 4.4 Six initial manifests

The compact manifest budget is `64 B` per initial-live page, with a separate
small object/header table:

| Endpoint | Three manifests |
|---|---:|
| DGAI-50K | 0.617 GiB |
| OdinANN-400K | 0.740 GiB |
| Total | **1.357 GiB** |

The fixed record must retain run identity, object incarnation, role, aligned
offset, page bytes and initial version/live status.  Extent encoding may be
smaller, but the budget does not claim that reduction.

### 4.5 Six canonical physical maps/images

The gate explicitly permits an independently validated map-only
representation.  Z0B therefore budgets:

```text
compact physical map       64 B per initial-live page
retained payload image      0 B
temporary payload image     0 B
```

| Endpoint | Three compact maps |
|---|---:|
| DGAI-50K | 0.617 GiB |
| OdinANN-400K | 0.740 GiB |
| Total | **1.357 GiB** |

Independent validation must stream the immutable snapshot and verify the map,
page bytes, canonical order, capacity and spare-zone account directly.  It
must not materialize an image as a convenience.

Canonical is the base map for a trace.  `RoleSeparated`, the three registered
`RandomPacking` seeds and `OfflineHotColdOracle` are represented by compact
placement parameters plus a complete placement digest.  They are regenerated
and independently checked while streaming; six additional full maps per trace
must not be persisted.  If an implementation requires duplicated placement
maps, this budget is invalid.

### 4.6 Simulator/reference state

Main and independent reference replay run together and compare every event,
but their logical/zone state is memory-resident.  No full state checkpoint and
no per-event state dump is retained.  Disk allowance for configuration,
placement digests, lifecycle sidecars, run metadata and atomic small outputs is
`0.250 GiB` total.

RAM is a separate gate.  Two Python object graphs are conservatively estimated
at `6–16 GiB` for the long endpoint, but the formal implementation must use a
compact streaming/native state and demonstrate peak RAM on an M3-derived
prefix before launch.  Storage headroom must not be used as a substitute for
that RAM proof.

### 4.7 Per-cycle output

Only cycle and tail summaries are retained:

```text
allocated/relocated bytes and HostWA
victim and valid fraction
relocated pages
free zones and live/invalid bytes per cycle
cycle start/end sequence
victim role composition
crossing update/batch IDs
trend and cross-realization summaries
```

No per-event snapshot log is allowed.  The combined output allowance for all
systems, traces, four geometries, six placements and two cleaners is
`0.750 GiB`.

### 4.8 Compact final-live manifests

Final snapshot closure uses a compact `80 B` page record plus object hashes:

| Endpoint | Three final manifests |
|---|---:|
| DGAI-50K | 0.771 GiB |
| OdinANN-400K | 0.926 GiB |
| Total | **1.697 GiB** |

This is reported separately from per-cycle output because it is the retained
snapshot oracle.  The physical clone remains authoritative until review.

### 4.9 Failure residue

Failure residue allowance is `1.000 GiB` for markers, logs, incomplete compact
metadata and atomic-output fragments.  It does not reserve a seventh clone:

- an unsuccessful attempt is one of the preregistered six and remains in its
  scheduled slot;
- the gate forbids replacing it with a new run to reach three successes;
- its clone/raw/normalized partial data are already bounded by the six-clone,
  six-raw and six-normalized line items;
- core dumps remain disabled.

If a failure creates data outside those six registered attempts, launch has
violated this budget and must stop.

### 4.10 Compression temporary

Compression is not required for replay.  A conservative `7.000 GiB` permits
one largest artifact to coexist with one atomic compressed candidate.  Only
one compression job may run at a time.  The source is not removed until the
compressed stream, count, digest and downstream readability have passed.

If compression needs decompression to another full temporary file for replay,
the compact plan is invalid; replay must stream the accepted representation.

### 4.11 Safety margin

The subtotal before safety margin is:

| Item | GiB |
|---|---:|
| Six clones | 86.868 |
| Six raw traces | 7.121 |
| Six normalized traces | 4.217 |
| Six compact manifests | 1.357 |
| Six compact maps; no images | 1.357 |
| Six compact final-live manifests | 1.697 |
| Simulator/reference metadata/state on disk | 0.250 |
| Per-cycle/tail output | 0.750 |
| Failure residue | 1.000 |
| Compression temporary | 7.000 |
| **Subtotal** | **111.617** |

A `15%` non-reclaimable safety margin is `16.743 GiB`, giving:

```text
central expected peak = 111.617 + 16.743 = 128.360 GiB
registered range      = 128–129 GiB
hard GPT stop line    = 150 GiB
headroom to stop line = 21.640 GiB at the 128.360 GiB estimate
```

The safety margin is not reusable for an optional artifact.  Any planned
format, duplicate map/image, decompression file, retry or event log that is not
listed above requires a new budget before it is created.

## 5. Rejected storage plans

The estimates below use R2's measured bytes per page/event at the M3 endpoint
counts:

| Plan | New peak before failure/compression/safety | Verdict |
|---|---:|---|
| Current R2 JSON + retained payload images | 233.47 GiB | Stop, exceeds 150 GiB |
| Map-only, current JSON including replay spec | 146.60 GiB | Stop, allowances force it above 150 GiB |
| Map-only and streaming, but current full JSON manifests/maps/final-live | 125.47 GiB | Not accepted; allowances make it marginal/over 150 GiB |
| Compact map-only + streaming plan in this document | 102.61 GiB core; 128.36 GiB guarded | Space-pass |

The first plan's image line alone is `86.868 GiB` across six traces because the
R2 packer writes every initial page.  A logically sparse image is therefore
not physically cheap enough.  The second plan's expanded replay JSON alone is
about `21.136 GiB`.  Both are eliminated, not treated as optional cleanup.

## 6. Dual space gate

Both conditions must pass immediately before launch:

```text
expected guarded peak < 150 GiB
available bytes >= 1.5 * expected guarded peak
```

Using the upper registered peak:

```text
expected guarded peak        129.00 GiB
1.5x required                193.50 GiB
measured available           849.46 GiB
available / required           4.39x
absolute surplus             655.96 GiB
```

Thus the audited compact plan passes both disk conditions.  The check must be
repeated from the actual Z0B root immediately before any clone is made and
must resolve to major:minor `259:10`.  Existing free space elsewhere, including
the system disk, cannot satisfy the gate.

## 7. Time estimate and replay implementation gate

Pure workload time extrapolated from M3 is:

```text
3 * DGAI-50K       212.9 s   =  3.55 min
3 * OdinANN-400K 1,612.8 s   = 26.88 min
total pure workload            30.43 min
```

Clone creation, hash/identity checks, raw dump, normalization, compact
manifest/map validation and final snapshot closure raise the six-trace capture
and closure estimate to `1.5–3 hours` when run strictly serially.

The complete matrix contains:

```text
4 geometries * 6 placements * 2 cleaners = 48 simulations per trace
DGAI event-policy steps  =   257,713,632
Odin event-policy steps  = 3,138,377,904
total                    = 3,396,091,536
```

The current R2 Python replay took roughly `13–15 s` for about `24K` events
while evaluating two cleaners.  Linear scaling already gives a lower bound of
about `12 days` for Z0B, and its periodic full-map scans make the long case
worse than linear.  That implementation is rejected for launch.

Before launch, a streaming/native main/reference implementation must pass a
read-only M3-derived prefix benchmark with at least `0.5 million
event-policy steps/s`, exact per-event equality and bounded RAM.  At that
floor the pure matrix loop is about `1.9 hours`; allowing GC relocation,
placement construction, I/O and validation gives a conservative replay range
of `4–12 hours`.  Total end-to-end controller wall is therefore budgeted at
approximately `6–15 hours`, with explicit progress in sequence/config counts,
never wall-clock workload claims.

Failure to meet the throughput/RAM preflight is a prelaunch blocker, not a
reason to weaken the exact-order or independent-reference gate.

## 8. Marker-owned cleanup boundary

Cleanup authority is limited to a future single Z0B root and must be
fail-closed.  A cleanup candidate must satisfy all of the following:

1. its canonical real path is strictly beneath the preregistered Z0B root;
2. that root and the exact attempt/scratch directory contain the expected
   Z0B-owned marker and schedule identity;
3. `findmnt` resolves the path to major:minor `259:10`;
4. neither the candidate nor any parent below the Z0B root is a symlink;
5. there is no active Z0B systemd unit, tmux/controller process or open file
   descriptor referring to it;
6. it is explicitly listed as an atomic `.partial` file or compression scratch
   in the owning attempt manifest;
7. its accepted replacement already passed byte count, record count, digest
   and downstream readback checks.

During execution and review, the following are not cleanup candidates:

- any of the six mutable final clones;
- raw or normalized traces;
- compact initial/final manifests or maps;
- per-cycle evidence and failure evidence;
- a failed registered attempt, because it cannot be silently replaced;
- the two immutable CP10 snapshots;
- M0–M3 formal/results/build roots;
- Z0A or Z0A-R2 artifacts;
- SIFT datasets, M1 input prefixes, source/build provenance;
- any pre-existing `dynamic_vamana_atlas/tmp` content.

At audit time the pre-existing atlas `tmp` tree occupied about
`6,201,884,672 B`, and three unrelated historical `failed_*` result directories
occupied only about `0.4 MiB`.  None is Z0B-owned; none is counted as reclaimable
headroom; none may be removed by the Z0B cleanup path.

After successful compression, only the explicitly owned source intermediate
may be deleted.  Attempt directories and final clones remain until all six
closures, final report and GPT review are complete.  No cleanup command may
accept an unconstrained user-provided path or operate on the experiment parent
directory.

## 9. Prelaunch stop checklist

Launch remains blocked unless every item is true:

- compact fixed/extent manifest, map and final-live formats are implemented
  and independently read back on a short real trace;
- no payload image and no expanded replay JSON is generated;
- all six attempts, placements and seeds are preregistered;
- streaming main/reference replay proves exact per-event equality;
- the prefix benchmark demonstrates throughput and RAM bounds;
- the actual Z0B root is marker-owned on `259:10`;
- recalculated guarded peak is at most `129 GiB` and strictly below `150 GiB`;
- current free space is at least `1.5x` that recalculated peak;
- unrelated frozen, historical and temporary artifacts remain outside cleanup
  authority;
- execution is serial and any failed trace stops the controller without retry.
