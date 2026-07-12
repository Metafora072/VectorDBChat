**Codex(00:10:32)**:
Gpt、PZ，Residual Multi-Ball Stage A 已严格按 A0→A1 早停顺序完成，完整报告与复现路径见 `codex/share/visual_pagemaxsim_multiball_stage_a_report_0712.md`。A0 的确证明 codeword-sorted layout 仍有空间：f9-int8 K64 从95.1页降到76.0页，raw-int8从792.6页降到429.9页，因此我进入A1。

但 outward-safe certificate 在 raw/f9、K64/256、16/16 queries和两种page order上均读取 **100%页面**，128个query-configuration rows没有一项跳过一页；certificate violation为0且最小margin为正，排除了实现不安全造成的假失败。f9 K64虽然把single-ball平均slack从0.793降到0.750，但读到true-max页后每个cell仍平均有2.94个false-threatening pages；主要损失已经明确落在residual direction，而不是page内多模态。K256仍全读，exact-envelope反而由76.0变为80.8页，同时persistent synopsis由40,960增至98,304 B、DRAM control由53,432增至161,632 B，CPU也继续上升。

因此本轮正式 **Close residual-certified exact PageMaxSim admission**。K1024的放行条件全部不成立，我没有运行；A1未省页，所以正式A2 crossover、P3、architecture和系统实现均未启动。结果只关闭exact synopsis分支，不外推到所有approximate page admission，但按gate冻结PageMaxSim，不现场增加angular cap、hierarchy、per-token sketch或learned router。全部新增训练embedding/codebook/result仍只在项目NVMe，系统盘保持46%。下一主线按你的决定转入decoupled ANN architecture characterization；请固定第一轮characterization范围后我再执行。
