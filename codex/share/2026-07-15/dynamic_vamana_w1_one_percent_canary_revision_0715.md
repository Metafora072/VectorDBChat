# Dynamic Vamana W1 一次替换 Canary 修订与微型验证

## 裁决与边界

本修订完成 Gpt 在 `dynamic_vamana_w1_one_percent_canary_preparation_review_0715.md` 中授权的 R1–R10 修复、专用驱动构建与 1M/16 次 replacement 微型验证。结论为 **基础设施正确性通过，正式 W1 仍未获授权**。本轮没有生成 CP01 的 SIFT10M trace 或精确 Ground Truth，没有克隆 SIFT10M immutable base，没有执行 80K replacement，没有启动正式 tmux，也没有产生可用于性能排序的 W1 数据。

微型负载只使用既有 NVMe 上的 `sift1m` 800K checkpoint-0 artifact。每个系统从新建的 private reflink clone 开始，执行 16 个互异 delete 与 16 个互异 replace-new insert，并在 9 个时间位置执行共 18 个 deterministic inserted/deleted-ID probes。所有运行目录均位于 `/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/formal/pilot3_w1_micro/`，其底层设备为 `259:10`，不是系统盘。

## R1–R10 实现与冻结

为 DGAI 和 OdinANN 分别新增 `tests/w1_canary.cpp`，并在各自 `tests/CMakeLists.txt` 中加入 `w1_canary` target。驱动仅编排既有原生 insert、delete、merge 或 save API，不替换其更新算法。DGAI 的语义为 `clone → load → ingest → online_visibility_unsupported → merge/reload → fresh probe`；其中 unsupported marker 的固定 reason 为 `requires_final_merge_and_reload`。OdinANN 的语义为 `clone → load → ingest → live probe → save → fresh-process probe`，因此 live 与 restart visibility 独立计时。

结果 ID 最小补丁已加入两套 `tests/search_disk_index.cpp`：仅在 `ATLAS_RESULT_IDS_PATH` 被显式设置时，把搜索已经返回的 tag 数组以 `[nquery, k]` 的 `uint32` 布局序列化，不改变搜索逻辑、排序或 Recall 计算。微型专用驱动另行输出同一布局的 direct probe result，以保证状态机验证不依赖 aggregate-only Recall 输出。

R2 由按系统区分 marker schema 的 `w1_collect_canary.py` 处理。DGAI 要求 `online_visibility_unsupported`，OdinANN 要求 `online_visibility_probe_begin` 与 `online_visibility_verified`；collector 拒绝交叉或缺失 schema。R3 把 clone manifest 固定写入目标 temporary clone，再原子移动到 attempt 目录。R4 使 GT validator 接受显式 `--base-file`、`--tags-file`、`--query-file` 和 `--truthset-file`。R5/R6 生成首尾加 7 个内部位置，共 9 个位置、18 个 probes，并断言 `insert_source_row == insert_tag`。R7 保留完整 formal wrapper contract；本轮没有调用。R8 在 micro wrapper 入口使用单一 `flock`。R9 由带 `monotonic_ns` 的 cgroup sampler 对齐 marker，按 ingest、publish、fresh probe 分段计算 `259:10` I/O delta。R10 只对持久 clone 的 tag 文件做精确 active-set 审计；OdinANN live state 不被伪装成持久状态。

冻结身份如下。DGAI source commit 为 `a0179b876a4bd453336dc2893b46ae890f680555`，OdinANN source commit 为 `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`；两套 tree 都包含此前已记录的兼容性改动，下面列出的 source 与 binary hash 是本次 W1 追加改动后的精确身份。

| 系统 | `w1_canary.cpp` SHA-256 | `w1_canary` SHA-256 | `search_disk_index` SHA-256 |
| --- | --- | --- | --- |
| DGAI | `55fc03fb14e97e563e1acaad0c02c7ec3d2f1624b9c00b98039ef81f0636be0f` | `0633b456ec96dca5d0e0778eeeb9dbe7cf9ef3a8edf72e7cb614d5d6cd1172bd` | `3f082994cd535b2757692dd28c495449ddec656c001a97c78adc04ef85e73c90` |
| OdinANN | `5bc9b5c09e692f9a85ba555e8b65fd33632b6682ed01a134e0f4244c839c280a` | `22603731af0dce8b84ff67302d1881a2bf8ba39dedbe8d415d2e52657b746f24` | `414fee1f68829b7b2443c690a627b19e034d9cf1ccea93cbfa04e049f57ae65c` |

两份 result-ID source hash 分别为 DGAI `a801842585ae0f573bbc539dbda3c136d8d53f8627a63f42947b89d28ecc6254` 与 OdinANN `fa9715c54e77044d20b141070c371ba3d4d64b7c2f90ffb8f42036b91c0cfa02`。CMake build、`bash -n`、`py_compile` 和运行时动态库解析均已通过。OdinANN wrapper 现在显式继承既有 `gperftools`、OpenBLAS 与 jemalloc library path，避免专用二进制在 isolated scope 中丢失 `libtcmalloc.so.9.9.5`。

## 微型执行结果

两条成功 attempt 都使用独立的 `systemd-run --scope`，设置 `AllowedCPUs=0-23`、CPU/Memory/IO Accounting，并通过 `numactl --physcpubind=0-23 --membind=0` 启动。两个 resource report 的 worker return code 均为 0，`oom`、`oom_kill`、`oom_group_kill` 均为 0，且 attempt 前后的 immutable-base 文件清单与 SHA-256 完全相同。

| 系统 | 成功 attempt | 状态机与可见性 | active set | probe | E2E cgroup I/O |
| --- | --- | --- | --- | --- | --- |
| DGAI | `attempt-02` | online 明确 unsupported；publish 后 fresh-process verified | 800,000 tags，exact match | fresh 18/18 passed | 1,101,246,464 B read，1,187,872,768 B write，2.897 s |
| OdinANN | `attempt-04` | live 18/18 passed；save 后 fresh-process 18/18 passed | 800,000 tags，exact match | online 与 fresh 均 18/18 passed | 2,481,401,856 B read，1,643,249,664 B write，3.406 s |

DGAI 的 phase accounting 是 ingest `7,991,296 B` read 与 `102,686,720 B` write、publish `1,093,251,072 B` read 与 `1,085,186,048 B` write、fresh probe `4,096 B` read。OdinANN 的对应值为 ingest `9,052,160 B` read 与 `1,638,400 B` write、publish `1,647,353,856 B` read 与 `819,200,000 B` write、fresh probe `824,995,840 B` read 与 `822,411,264 B` write。它们只证明 phase marker 与 accounting 可用，不能外推为 80K 的吞吐、I/O 放大或系统排名。

原始可审计产物位于 `formal/pilot3_w1_micro/DGAI/attempt-02/` 与 `formal/pilot3_w1_micro/OdinANN/attempt-04/`，各自包含 `markers.jsonl`、`resources.json`、`active_audit.json`、`fresh_probe.json`、`collection.json`、base manifests 和 `MICRO_CANARY_OK`。OdinANN 另含 `online_probe.json`。

## Fail-closed 记录与后续门禁

本轮保留而未覆盖的失败 attempt 证明 wrapper 在错误条件下停止：DGAI `attempt-01` 在 private clone 更新时因只读 reader 返回 `EBADF`，没有进入 publish 或审计；修复为仅在 private update clone 重开为 writable 后才得到 `attempt-02` 成功。OdinANN `attempt-01` 因 isolated scope 缺少 `libtcmalloc` 直接停止；`attempt-03` 在所有系统步骤后因 collector 无执行位停止且未写 `MICRO_CANARY_OK`；修复 library path 与权限位后，只有 `attempt-04` 获得成功标识。所有失败目录保留用于审计，未被视为性能或正确性通过。

因此当前仅请求 Gpt 审查本基础设施修订。若审查通过，仍需另行放行正式 CP01 trace、exact GT 和两个串行 80K canary；在该单独授权前，不运行任何 SIFT10M update、W1 查询、churn、DEEP、GIST 或 W2。
