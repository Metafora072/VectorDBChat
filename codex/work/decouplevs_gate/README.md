# DecoupleSearch-R Reproduction Files

本目录保存 `DecoupleSearch-R` 的可审计源文件和脚本。大规模 layout、build 与 query-level CSV 不进入 chat Git 仓库，统一位于项目 NVMe 的 `/home/ubuntu/pz/VectorDB/data/VectorDB/decouplevs_gate/`。

核心源文件为 `decouple_search_r.cpp`。`export_decoupled_layout.py` 从同一个 Vamana index 导出 graph/vector layout。`run_r0_matched_repeats.sh` 和 `run_r0_width_repeats.sh` 运行同 recall 的 R0；`run_r1_matrix.sh` 扫描 `L/W/B`；`run_r2_oracles.sh` 运行三个互斥 oracle；`analyze_r0_r1.py` 与 `analyze_r2.py` 生成聚合结果。

正式结果只使用 `r0_batched`、`r0_batched_widths`、`r1_batched`、`r2_batched` 与 `analysis_batched`。其他同名前缀目录为实现审计过程中产生的无效或被替代批次，不能用于结论。

构建基于 PipeANN commit `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b`，需要在 CMake 中加入 `tests/decouple_search_r.cpp` target，并配置 `PIPEANN_FORCE_URING=ON`、`USE_TCMALLOC=OFF`。由于 sandbox 内核策略可能使 `io_uring` probe 失败，应只在确认宿主机 `io_uring_queue_init()` 成功后强制启用。
