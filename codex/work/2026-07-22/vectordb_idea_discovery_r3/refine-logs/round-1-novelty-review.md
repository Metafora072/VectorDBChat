# Round 1：机制级 novelty review

- Capacity collective：SIGMOD 2008 已定义相同 CCA，并用 incremental NN 做 NIA/IDA；STOC 2014 已将 ANN 用于 metric/geometric matching。降为 KILL。
- Similarity sampling：Gumbel-MIPS、Fast Sampling for MIPS、RF-softmax、LSH/MIDX sampler 直接覆盖。降为 KILL。
- Fresh-world distributional：保留为唯一 HOLD/GO A0。要求只保留 compact posterior + lazy inverse-CDF + simultaneous UCB-MIPS，不加 learned predictor 或系统部件。
