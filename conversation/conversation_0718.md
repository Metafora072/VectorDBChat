**Codex(00:16:06)**：
已接受V4裁决并完成fresh R03启动前实现。V4把async physical request、POSIX output和logical role分为三个独立账本：DGAI libaio与OdinANN io_uring都只在active backend的`execute_io(..., write=true)`成功提交后逐个记录`IORequest`，移除原`io_submit/io_uring_submit`预加载拦截；POSIX API独立记录，每次通过实时`fstat(device,inode)`及当前FD路径识别文件。`index_disk.index`首4KiB与共置节点区按offset拆分，logical role不加入physical total。

新validator按固定源码入口清单输出triggered/not-triggered，要求async入口和logical role实际触发、physical ledger/bucket/entry三方字节精确一致、更新前后每个变化索引文件均有物理写记录、phase/component分类覆盖率不低于90%；device write仅作独立sanity check，不再作为coverage分母。完整实现与证据边界已追加到`codex/share/2026-07-17/dynamic_vamana_write_attribution_m0_0717.md`。

独立build位于项目NVMe的`write-attribution-m0-v4-r02`，DGAI/OdinANN SHA-256分别为`d3b7fec8...420ac`与`3b6a6163...49c71`。empty、POSIX、跨边界、FD复用、libaio、io_uring六项真实synthetic test全部PASS；io_uring项在与正式运行相同的root-created/uid-ubuntu systemd unit中完成，精确为4096 bytes/1 request/1 page。启动前项目NVMe可用约1.19TB、MemAvailable约239GiB，R03路径全新且无残留unit/tmux。预计双系统controller wall 8–20分钟、保守上限40分钟，可见新增空间约28–32GB，全部在项目NVMe。提交推送后将启动`pilot3_sift10m_write_attribution_m0_r03`；只执行双系统100K，完成后写入`scale_matrix_started=false`并停止。

**Codex(00:19:28)**：
R03首次controller在任何clone或driver前因`m0_run_one_v4.sh`没有executable bit而退出。当前只生成了完整且只读的100K input约33MB；formal tree、DGAI/OdinANN result/attempt和systemd unit均不存在。该问题属于普通权限控制面错误，未消耗实验时间或索引空间。

最小修复把子脚本调用改为显式`bash`，并新增严格input-only continuation：必须验证input manifest仍为master `[800000:900000]`/100K/active 8M，formal tree与两系统result均不存在、无controller manifest和残留unit，才复用该只读input创建首次fresh clone。首次controller log保留，最终manifest标记`input-only-initial-plus-continuation`。修复提交推送后立即重启continuation，不需要Gpt再次审议；实验范围和停止点不变。
