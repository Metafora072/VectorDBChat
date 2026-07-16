# W1 CP05 cumulative replay-base mode stop analysis

## Verdict

The `pilot3_sift10m_w1_cp05_trajectory` attempt stopped fail-closed during `replay_DGAI` before any replay query, replay update, formal SIFT10M clone, formal update, or DiskANN query. The failure is a replay-base immutability precondition failure, not an algorithm, memory, NVMe, trace, GT, or formal-input failure. This attempt is terminal and must not be retried or continued under the same identity.

## Exact failure

- Start: `2026-07-16 23:05:30 UTC+8`
- Terminal manifest: `status=stopped_failed`, `stopped_phase=replay_DGAI`, `exit_code=1`
- Controller diagnostic: `immutable base file has write bit: .../index/atlas1m/DGAI/sift1m/BUILD_OK`
- The shared clone helper correctly rejected the 1M replay base before publishing a private clone.
- The failure notification was accepted by MailSender with HTTP 202.

The issue is broader than one marker. The current 1M DGAI replay base has 15 regular files at mode `0664` and its root directory at `0775`; the OdinANN replay base has four regular files at `0664` (plus one at `0644`) and its root directory at `0775`. Their allocated sizes are `1,415,053,312 B` and `848,158,720 B`. The formal 10M DGAI/OdinANN/DiskANN CP00 bases are unaffected and remain byte/mode exact against accepted R05/R06/R07 evidence.

## Evidence retained

- Real preflight passed.
- Formal 80K and 320K deltas were derived from the columnar master, validated, inode-disjoint, and frozen read-only.
- Replay 16 and 64 deltas/GT/probes were derived, validated, inode-disjoint, and frozen read-only.
- Stop-time preservation passed for all 61 protected artifacts with zero mismatch, including all accepted formal bases and the 14-entry DiskANN runtime lineage.
- The stopped result tree occupies only about `6.9 MB` allocated; project-NVMe free space remains about `1.327 TB`.

No replay checkpoint evidence, `CUMULATIVE_TRAJECTORY_OK`, formal result, formal clone, CP05 freeze, or DiskANN CP05 result exists.

## Requested GPT decision

Please decide whether to authorize a fresh cumulative attempt with new run/attempt/result identities after creating dedicated immutable 1M replay-base copies. The safest proposal is:

1. Preserve the existing writable 1M indexes unchanged.
2. Create new DGAI/OdinANN replay-base copies on the project NVMe, prove content equality to the current source manifests, prove inode independence, then freeze directories/files to `0555/0444` with owner-denial tests. Expected extra allocated space is about `2.3 GB`.
3. Add those immutable replay-base identities to preflight and final preservation.
4. Use entirely fresh result/formal/delta paths and new replay/formal attempt names; rederive the small execution deltas from the frozen sources rather than reusing the terminal attempt.
5. Keep the same unique runner and the authorized `16→80` replay followed by formal `CP00→CP01→CP05`; CP10/CP20 remain HOLD.

An alternative in-place `chmod` of the existing 1M bases would save space but would mutate shared historical artifacts and is therefore not recommended without explicit authorization. Codex has stopped and has not applied either repair.
