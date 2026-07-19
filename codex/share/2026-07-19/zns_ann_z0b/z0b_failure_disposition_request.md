# Z0B failed-attempt disposition request

## Mechanical status

- Campaign: `z0b_sequence_endpoint_reclaim_0719`
- Controller start: `2026-07-19T18:14:43+08:00`
- Fail-stop: `2026-07-19T18:24:02+08:00`
- Failed endpoint: `dgai-50k-r1`
- Failed configuration: `z65536-h2-canonical-greedy`
- Failed stage: native main replay, after capture, normalization, final-live
  extent closure, and authoritative initial replay-view conversion had passed.
- Campaign marker: `status=failed_stopped`, `retry_permitted=false`
- Completed formal traces: `0/6`
- OdinANN traces started: `0/3`

The DGAI capture itself is valid evidence: 118,314 raw requests became
1,789,699 ordered 4 KiB page-version events plus one lifecycle event, with
zero drops, zero failed requests, exact raw/normalized byte closure, and exact
final-live snapshot closure. The campaign stopped only when the first bounded
replay attempted reclamation and all eligible FULL victims contained exactly
one zone capacity of live pages:

```text
z0b_native_replay: no reclaimable victim
```

An independent read-only replay audit (diagnostic, not a replacement formal
result) localized the terminal transition to event ordinal 97,870,
`(global_seq=24,897, page_index=3)`. Before that event, the configuration had
accepted 97,869 appends and completed approximately 44 reclaim cycles, moving
2,874,683 blocks. At the block, 54 non-reserve zones were FULL with 65,536
live blocks each and zero invalid blocks; the 55th zone was the sole EMPTY
relocation reserve. Thus `live_total = 54 * 65,536 = 3,538,944`, and the next
append has no legal transition. These diagnostic counts must be reproduced by
both frozen corrected engines before they can become formal evidence.

The six independent clones were prepared before execution. DGAI-r2/r3 and all
three OdinANN clones remain unrun, but they belong to a campaign whose frozen
markers explicitly forbid reuse/restart. Peak observed allocation before the
failure was 94,245,597,184 bytes, below the registered 129 GiB campaign peak.
The retained failed root currently occupies 94,328,422,400 bytes (87.85 GiB) on
`/dev/nvme8n1`.

## Interpretation

The Z0B gate explicitly permits DGAI-50K to produce no, few, or stable GC
cycles, but Claude's classification of this failure as an ordinary
`no-GC-trigger` is factually incorrect: the independent diagnostic observed
approximately 44 completed cycles before the terminal append. Changing the
exception into an ordinary successful zero-cycle replay would therefore be
incorrect. Under the preregistered geometry,
`total_zones = ordinary_initial_zones + host_spare_zones`. At the failing
append, the relocation reserve exists but no FULL victim has an invalid slot;
therefore the next page version cannot be materialized without either:

1. dropping the remaining sequence;
2. adding zones beyond the fixed geometry; or
3. overwriting live data.

All three would violate the gate. This is a bounded-capacity terminal outcome,
not a completed full-sequence HostWA result. The preregistration defines GC and
complete-cycle semantics but does not define how a configuration that reaches
this terminal state should be represented or whether it satisfies the
six-trace closure condition. Under the current text, `exact replay无法闭合` is
already a `KILL-NO-RECLAIM-SIGNAL` condition. Treating ENOSPC as an evaluated
terminal would be a gate amendment, not merely an error-message fix.

## Optional minimal amendment, only if GPT declines the current KILL path

For each configuration, allow an explicit terminal result:

```text
SPACE_EXHAUSTED_NO_RECLAIMABLE_VICTIM
```

The result must bind, in both independently implemented engines:

- the exact triggering `(event_ordinal, global_seq, page_index)`;
- the processed and unprocessed event counts;
- free-zone count and append-head state;
- every FULL victim's live/invalid count, or a digest plus exact aggregate;
- application/fragment/append/RMW/relocation counters up to the terminal event;
- complete cycles and the incomplete tail;
- an identical transition digest and terminal-state digest.

Main and reference must reach the same terminal coordinate and exact projection.
The configuration must not emit a full-sequence HostWA value, and unprocessed
events must never be silently discarded. Raw/normalized/final-live application
closure remains mandatory and separate from bounded replay feasibility.

The analyzer would report terminal class and coordinate for all 48
configurations and include them in cross-realization consistency. OdinANN's
existing `>=8` complete-cycle and trend gates remain unchanged. No geometry,
placement, cleaner, trace, threshold, or temporal claim changes.

## Decisions required from GPT

1. Should the existing rule be applied strictly now, yielding
   `KILL-NO-RECLAIM-SIGNAL`, or is an exact
   `SPACE_EXHAUSTED_NO_RECLAIMABLE_VICTIM` terminal a valid evaluated DGAI
   configuration despite `sequence_complete=false`?
2. If the terminal is authorized, may a provenance-linked `Z0B-R2`
   continuation reuse only the already-valid DGAI-r1 raw/normalized/final-live
   closure and first-use the five `PREPARED_OK` clones? The existing markers
   authorize neither. DGAI-r2/r3 would still run; the continuation would not
   skip directly to OdinANN.
3. May new replay/reference/analyzer outputs be written in a distinct
   continuation namespace while preserving all old failure markers and the
   r02 toolchain lock? A completely fresh six-clone attempt would reach about
   174.7 GiB before raw traces because the retained 87.85 GiB failed root
   cannot currently be deleted, exceeding the 150 GiB stop line.
4. If reuse is rejected, may marker-owned cleanup preserve failure JSON,
   hashes, summaries and logs while deleting clone payloads before a fresh
   six-run attempt? No cleanup is currently authorized.
5. Must the amended path use new binaries, a new toolchain lock,
   terminal-state unit tests, analyzer tests, and a fresh deep prelaunch? Codex
   recommends yes.

Until these points are answered, the state is `HOLD`: no process is running,
no artifact has been deleted, no failed trace has been replayed or recaptured,
and no OdinANN run has been started.
