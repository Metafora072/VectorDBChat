# M1 G0 deterministic fixture

## Purpose and boundary

This directory contains a four-node, dependency-free control-flow model for
the G0 correctness witness.  It models only the semantic ordering needed by
the P0 ruling:

- approximate admission before a main-pool page read;
- bounded connectivity-pool bridge promotion;
- exact authorization only after a read;
- termination after one exact-allowed result (`l_search = 1`);
- PRE/IN/POST filtering under fresh and stale approximate policy state.

It does **not** link to or modify PipeANN, DGAI, or OdinANN.  It is not an
artifact reproduction, an I/O implementation, or a performance benchmark.
In particular, `device_submit` is a modeled event, not evidence of physical
SSD traffic.

## Four-node graph

```text
E (entry, exact deny, backend cached)
├── B (approx false, distance 0.2, bridge promoted, exact deny)
├── T (newly granted exact top-1, distance 0.7)
└── A (approx true authorized decoy, distance 1.0)
```

The bridge distance band ends at `0.5`.  Therefore B demonstrates promotion,
while stale T enters the connectivity pool and is rejected.  Fresh T enters
the main pool, is read, passes exact authorization, and wins.  Stale T is
never read; A passes exact authorization and terminates the search, so no
final verifier can recover T.

PRE_FILTER models a stale materialized ID set that omits T.  POST_FILTER uses
an unconditional approximate callback and is the negative control: its fresh
and stale outputs must be identical apart from the state label.

## Output contract

Every one of the six cases emits a JSON record containing:

```text
approx_true
approx_false
false_to_connectivity_pool
bridge_promoted
bridge_rejected
main_pool_read
backend_cache_hit
device_submit
exact_allow
exact_deny
termination_reason
target_node_event_sequence
```

`main_pool_read == backend_cache_hit + device_submit` is asserted explicitly.
This prevents a logical read counter from being presented as physical I/O.
The full ordered `event_log` is included for auditability.

For PRE_FILTER, approximate and bridge counters are intentionally zero because
that path materializes candidate IDs instead of invoking IN_FILTER's
approximate callback.  The target trace records `pre_filter_include` or
`pre_filter_omit` instead.

## Run commands

No build step or third-party package is required.  From this directory:

```bash
python3 g0_fixture.py --pretty
python3 -m unittest -v test_g0_fixture.py
```

To inspect one case:

```bash
python3 g0_fixture.py --strategy IN_FILTER --state stale --pretty
```

The executable performs the complete six-case contract assertion before
printing output.  The unittest suite repeats the contract and separately
checks the IN_FILTER witness, PRE_FILTER omission, POST_FILTER negative
control, required fields, and cache/device accounting.
