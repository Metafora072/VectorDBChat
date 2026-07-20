# P0 Experiment Tracker

当前所有运行项均未获执行授权；`TODO-REVIEW` 表示仅供 Gpt 选择。

| Run ID | Milestone | Purpose | System / variant | Inputs | Metrics | Priority | Status | Budget |
|---|---|---|---|---|---|---|---|---|
| D001 | M0 | G0 control-flow audit | PipeANN PRE/IN/POST | source only | exact lines/path | MUST | DONE-DOC | 20 min, 0 write |
| D002 | M0 | artifact identity | PipeANN + GateANN | source/official docs | commit/deps/I/O mode | MUST | DONE-DOC | 30 min, 0 write |
| D003 | M0 | strong baseline audit | RocksDB page-prefix | docs/design | capability/fairness | MUST | DONE-DOC | 30 min, 0 write |
| R001 | M1 | fresh/stale IN_FILTER witness | standalone toy | <=12-node graph | candidate/page-read/exact trace | MUST | TODO-REVIEW | 5 min, <0.1 GiB |
| R002 | M1 | PRE_FILTER omission witness | standalone toy | same graph | candidate omission | MUST | TODO-REVIEW | 5 min, <0.1 GiB |
| R003 | M1 | POST_FILTER negative control | standalone toy | same graph | no policy pruning | MUST | TODO-REVIEW | 5 min, <0.1 GiB |
| R010 | M2 | clean compile smoke | PipeANN official | existing source/data | build identity | MUST | TODO-REVIEW | 15–30 min, <8 GiB, <1 GiB |
| R011 | M2 | SIFT1M filtered smoke | PipeANN official | existing SIFT1M + generated ACL | recall/I/O path | MUST | TODO-REVIEW | 20–40 min, <8 GiB, <2 GiB |
| R012 | M2 | GateANN feasibility smoke | GateANN official | existing SIFT1M if compatible | build/search identity | CONDITIONAL | TODO-REVIEW | 20–45 min, <8 GiB, <2 GiB |
| R020 | M3 | A1 random ACL | strongest reproducible path | fixed selectivity | recall/read/visited/yield | MUST | TODO-REVIEW | 10 min |
| R021 | M3 | A2 clustered ACL | same | fixed selectivity | same | MUST | TODO-REVIEW | 10 min |
| R022 | M3 | A3 shared/private | same | fixed selectivity | same | MUST | TODO-REVIEW | 10 min |
| R023 | M3 | A5 anti-correlated | same | fixed selectivity | same | MUST | TODO-REVIEW | 10 min |
| R024-R027 | M3 | repeat/control | same | selected A1-A5 | variability/cold-I/O | CONDITIONAL | TODO-REVIEW | <=40 min total |
| R030 | M4 | metadata cost sweep | analytical/replay | Claude workload params | bytes/read share/cache | MUST | TODO-REVIEW | 15 min |
| R031 | M4 | update cost sweep | RocksDB conceptual baseline | update trace | WA/pages/interference | MUST | TODO-REVIEW | 15 min |
| R032-R035 | M4 | targeted confirmation | selected only | dominance candidate | Q/M/U matrix | CONDITIONAL | TODO-REVIEW | <=30 min total |
