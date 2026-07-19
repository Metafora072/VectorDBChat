# Z0A-R2 Build, Mode, and Resource Proof

## Mode linkage

`readelf -d` confirms that both NATIVE binaries depend on `libr2oracle.so` but do not contain a `DT_NEEDED` entry for `libz0atrace.so`. NATIVE was launched without `LD_PRELOAD`. SHIM-CONTROL and FULL-TRACE for each system used the same patched `z0a_canary` binary and the same `libz0atrace.so`; only `ATLAS_Z0A_MODE` differed. SHIM emitted no raw trace, meta, ledger, or ordered lifecycle file in all 26 SHIM runs.

| Artifact | SHA-256 |
|---|---|
| `full/libz0atrace.so` | `8c6b93afb68fd7a1cb97406fa8ddab9fad9847320ba4086823f4c4e74496309e` |
| `common/libr2oracle.so` | `350b3ae3a48fe537eca0cb4e0bb3ab305e1b3c5cd4454da3e258920cb653d429` |
| DGAI NATIVE `w1_canary` | `a1374e5b2753a15a97f1ecf29972f17201e4c46f217c8df416ac435d61d11976` |
| OdinANN NATIVE `w1_canary` | `c3290082f440b2a2d65b71f4ad9dd4458e14d192853f4b9c80ce02885bf426c4` |
| DGAI SHIM/FULL `z0a_canary` | `71378d82ace1f1f7d739dd959d78fcc35e94481fa59c5bb599c696442050a823` |
| OdinANN SHIM/FULL `z0a_canary` | `d1c7676d3e49e130ce451dcd56578bb88ff7b2abab827c55ea22bbbe26e9c6ae` |

## Resource closure

The experiment root resolved to `/dev/nvme8n1`, major/minor `259:10`, rather than the system disk. All runs used `numactl --physcpubind=0-27,56-59 --membind=0`. The root occupied 2,654,912,512 bytes before formal execution and 3,274,997,760 bytes afterward, with approximately 850 GiB free at completion. The workload interval was 2026-07-19 15:35:32–15:56:30 UTC+8; 78 workload wall times summed to 473.76 seconds.
