# P0 X1 — G0 Source Witness

**Decision:** `PASS-G0-CONTROL-FLOW-WITNESS / HOLD-END-TO-END-DYNAMIC-ACL-REPRODUCTION`
**Scope:** 只读源码审计；未下载、编译、运行或修改任何 ANN 源码。

## 1. Source identity

- Repo: `https://github.com/thustorage/PipeANN.git`
- Local commit: `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`
- Local path: `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/src/PipeANN`
- 目标搜索/过滤文件相对该 commit 无 diff；worktree 的 CMake/test 辅助文件有既有修改，因此未来仍需 clean worktree。
- 本机 OdinANN-PipeANN 的两个核心搜索文件与该 PipeANN 副本相同；普通 DGAI 不含此过滤路径。
- 本机未发现 GateANN 源码树。

## 2. Actual control flow

| Stage | File and lines | Effect |
|---|---|---|
| PRE/IN/POST cost routing | `src/search/spec_filter_search.cpp:51-111` | 每个查询自动选择策略 |
| IN_FILTER entry | `src/search/spec_filter_search.cpp:284-322` | 构造 approximate 与 exact callbacks |
| Approximate one-hop admission | `src/search/pipe_search_common.h:146-155` | true 进入主 pool |
| Approximate-false connectivity path | `src/search/pipe_search_common.h:179-184,200-203` | false 一跳节点进入有限 `cand_pool` |
| Bridge promotion | `src/search/pipe_search_common.h:206-223` | 仅低局部密度且落入近距离 band 才提升 |
| Page read submission | `src/search/pipe_search_common.h:319-328` | 只有主 pool 节点发读请求 |
| Exact authorization | `src/search/pipe_search_common.h:86-97,335-344` | page 抵达后才能验证 |
| Termination | `src/search/pipe_search_common.h:349-378` | exact member 达到 `l_search` 后可终止 |
| PRE_FILTER candidate materialization | `src/search/spec_filter_search.cpp:153-173` | 只对 `pre_filter()` 返回的 ID 算 PQ 距离 |

PipeANN 的 approximate contract 明确要求 no false negatives。ACL 系统若让 exact grant 先对查询可见、approximate summary 后可见，就会违反这一复用前提。这是未来系统必须维护的发布 invariant，不是现有 artifact 自带的动态 ACL bug。

## 3. Minimal deterministic witness

强制 `spec_infilter_search`，设置 `k_search=l_search=1`、`beam_width=1`、dense list 为空。

```text
E (entry, unauthorized)
├── T (newly authorized true top-1)
└── A (authorized decoy)

T exact distance = 0.1, approximate distance = 0.7
A exact/approximate distance = 1.0
exact_allow(T)=true, stale_approx(T)=false
exact_allow(A)=true, approx(A)=true
```

控制流：

1. E 被读取并 exact-reject，但仍展开邻居。
2. A approximate true，进入主 pool；T stale false，进入 `cand_pool`。
3. bridge 检查的当前 band 由已访问 entry 的 distance 0.0 限定；T 的 0.7 超出 band，不提升。
4. 只有 A 从主 pool 发起 page read；A exact-pass 后满足 `l_search=1`，查询终止。
5. 返回 A，但 authorized exact top-1 是 T；T 从未读页，exact verifier 没有恢复入口。
6. 若 summary fresh，T approximate true 并进入主 pool；因 0.7 < 1.0，T 先读页且 exact-pass，返回 T。

因此 recall 差异来自 stale-negative approximate policy state。该 witness 已覆盖有限 tunneling，不依赖“false 必然硬剪枝”的错误简化。

## 4. Scope boundary

- **IN_FILTER:** witness 成立，但必须强制或记录真实 route；自动 planner 可能选择其他策略。
- **PRE_FILTER:** stale grant 若不在 `pre_filter()` ID 集，后续同样无恢复入口。
- **POST_FILTER:** approximate callback 恒 true；本 witness 不适用，应作为 negative control。
- **Dynamic ACL reproduction:** 当前公开接口主要在新向量插入时写 attribute；尚未确认既有对象 grant/revoke 的 snapshot-aware API。因此 end-to-end dynamic ACL 仍为 HOLD。

## 5. I/O instrumentation caveat

- 图文件通过 `O_DIRECT` 打开，但发设备 I/O 前存在用户态 page cache。
- 当前 `stats.n_ios` 在逻辑 read 提交处累计，即使用户态 cache 命中也可能计数；它不能单独代表物理 SSD I/O。
- 最小 counters 应包括 `approx_true/false`、`false_to_cand_pool`、`bridge_promoted/rejected`、`main_pool_read`、`backend_cache_hit/device_submit`、`exact_allow/deny` 和目标 ID event sequence。

## 6. Budget if later approved

| Work | Wall time | Peak RSS | New data-disk space |
|---|---:|---:|---:|
| 三节点 fixture + assertions | 1–2 h | <2 GiB | <0.25 GiB |
| counters + force-IN_FILTER hook + build/test | 2–3 h | <4 GiB | <2 GiB |
| optional 1M read-only trace | 0.5–1.5 h | <8 GiB | <1 GiB |

以上是互斥的逐级授权项，不应在一个 4 小时窗口内全部执行。所有 build/result/temp 必须位于 `/dev/nvme8n1`，不修改 DGAI/OdinANN 主路径。
