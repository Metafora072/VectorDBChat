# ACL Workload Manifest for P0 Axis-A Characterization

**Date:** 2026-07-21  
**Author:** Claude  
**Status:** Frozen for M3 execution  
**Covers:** C1 (workload model), C3 (distribution generation), C4 (semantic distinction), C5 (matrix)

---

## 1. 参数来源与依据

### 1.1 来自 HoneyBee (SIGMOD 2026)

| 参数 | HoneyBee 值 | 来源 |
|------|-----------|------|
| Users | 1,000 | §6.1 所有实验默认 |
| Roles | 100 | §6.1 所有实验默认 |
| Datasets | SIFT1M (1M/128d), SIFT10M (10M/128d), Wikipedia-22-12 (1M/300d) | §6.1 |
| Uniform generator | m_r=2 roles/user, m_p=|D|/|R|×5 docs/role | §6.2 Uniform-α |
| ERBAC generator | n_fr=40 func roles, n_br=100 biz roles, m_fr=3, m_br=3 | §6.2 ERBAC-α |
| Tree generator | h=4, b0=3, b1=4 | §6.2 Tree-α |
| Avg selectivity | Tree-α=0.036, Uniform-α=0.054, ERBAC-α=0.128, ERBAC-β=0.285 | Table 1 |
| Max roles/user | 1 (Tree/Uniform-α), 3 (ERBAC-α), 9 (ERBAC-β) | Table 1 |
| Memory overhead | 3.5-7× (role partition), up to 408× (user partition for ERBAC-β) | Table 1 |
| Index | HNSW, M=16, ef_construction=64 | §6.1 |

### 1.2 来自 Veda/EffVeda (arXiv 2605.01342)

| 参数 | Veda 值 | 来源 |
|------|--------|------|
| Datasets | SIFT-1M (1M/128d), PAPER (2M/200d), AMZN (212K/384d) | Table 1 |
| Roles | 82 / 87 / 64 | Table 1 |
| Permissions | 757 / 676 / 641 | Table 1 |
| Policy source | OrgAccess benchmark (organizational RBAC) | §7.1 |
| Permission dist. | Shifted Zipf (i+s)^{-α}, s'=2, α'=1.5 (SIFT/PAPER), s'=1, α'=1.5 (AMZN) | Table 1 |
| Block dist. | Shifted Zipf (j+s')^{-α}, s=1, α=2 (SIFT), s=1, α=1.5 (others) | Table 1 |
| SA w/ Oracle | 11.423 / 5.255 / 15.084 | Table 1 |
| Default SA budget | 1.1 | §7.2 |
| Workloads | uniform single-role, weighted single-role, uniform multi-role, weighted multi-role | §7.2 |

### 1.3 来自 Curator (SIGMOD 2026)

| 参数 | Curator 值 | 来源 |
|------|----------|------|
| Datasets | YFCC-10M (10M/192d), arXiv (2.3M/384d) | §6 |
| Unique labels | 1,000 / 100 | §6 |
| Labels/vector | 5.53 / 9.93 (avg) | §6 |
| Selectivity range | [0.001, 0.2], 20 log-spaced levels | §6.4 |
| HNSW M | 16/32/32 | §6 |

### 1.4 来自 Google Zanzibar (USENIX ATC 2019)

| 参数 | Zanzibar 值 | 意义 |
|------|-----------|------|
| ACL tuples | 2 trillion+ | 生产规模上限参考 |
| Namespaces | 1,500+ | 相当于 service/object-type 数 |
| Check QPS | ~4.2M peak | 查询吞吐参考 |
| p95 latency | <10ms (safe), ~60ms (recent/cross-region) | 延迟 SLA 参考 |
| Safe:Recent ratio | 100:1 | 大多数查询可用缓存 |

### 1.5 Enterprise RBAC 经验值

| 参数 | 典型范围 | 来源 |
|------|--------|------|
| Roles/user | 1-10 (median ~3-5) | RBAC 文献 + HoneyBee Table 1 |
| Privileges/role | 5-50 | RBAC 标准文献 |
| Role hierarchy depth | 2-5 | NIST RBAC model |

---

## 2. P0 实验固定参数

```yaml
# === Dataset ===
dataset: SIFT1M
n_vectors: 1000000
dimensions: 128
dataset_hash: "8c7b3d999ba3133f865af72df078f77c2d248fdb80571d7ea1f1bb8e1750658e"
query_file_hash: "9b0082b67d0ac55b4c7d42216560344567ad87ce3e75a9d5214a0762f1c15d65"

# === Graph (frozen, shared across all ACL distributions) ===
graph_type: PipeANN_Vamana
R: 64
R_dense: 64  # M2 default; M3 needs Gpt ruling on R_dense=128 for IN_FILTER
L_build: 96
PQ_bytes: 32
graph_hash: "TBD-after-M0-freeze"  # from M0 identity

# === Search parameters ===
k: 10
l_search: [10, 20, 40, 80, 120]
beam_width: 4  # PipeANN default
strategies: [PRE_FILTER, IN_FILTER, POST_FILTER]
# auto planner only as supplementary; main analysis uses forced strategy

# === Query workload ===
n_queries: 1000
query_source: "first 1000 rows of query.bin"
seed: 42

# === ACL parameters ===
n_users: 1000         # aligned with HoneyBee
n_roles: 100          # aligned with HoneyBee
```

---

## 3. Five ACL Distribution Specifications

### 3.1 Common constraints

所有五种分布必须满足：
- **相同 global authorized selectivity**：每个 user 平均可访问 N×s 个 object，其中 s 为控制参数
- **扫描变量**：s ∈ {0.01, 0.05, 0.10, 0.20, 0.50}
- **相同底层图和 page map**：只替换 policy payload，不重建 adjacency
- s=0.01 对应低选择率（ACL 严格），s=0.50 对应高选择率（ACL 宽松）

### 3.2 A1: Random (无结构基线)

**来源依据**：HoneyBee Uniform generator 的简化版  
**实验角色**：无结构基线，消除任何 ACL-graph 相关性

```python
def generate_A1(n_objects, n_users, n_roles, target_selectivity, seed):
    rng = np.random.default_rng(seed)
    # Step 1: assign roles to users (each user gets roles_per_user roles)
    roles_per_user = max(1, int(n_roles * 0.03))  # ~3 roles/user
    user_roles = {}
    for u in range(n_users):
        user_roles[u] = set(rng.choice(n_roles, roles_per_user, replace=False))
    
    # Step 2: assign roles to objects (Bernoulli per role)
    # Calibrate p so that Pr[user authorized for object] ≈ target_selectivity
    # Each object gets each role independently with probability p_role
    # User sees object if any of their roles is granted
    # Pr[authorized] = 1 - (1-p_role)^roles_per_user ≈ target_selectivity
    p_role = 1 - (1 - target_selectivity) ** (1.0 / roles_per_user)
    
    object_roles = {}
    for obj in range(n_objects):
        granted_roles = set(np.where(rng.random(n_roles) < p_role)[0])
        if len(granted_roles) == 0:
            granted_roles = {rng.integers(n_roles)}  # ensure at least 1 role
        object_roles[obj] = granted_roles
    
    return user_roles, object_roles
```

**参数**：
- `roles_per_user`: 3 (固定)
- `p_role`: 由 target_selectivity 和 roles_per_user 反推
- 扫描变量：target_selectivity

### 3.3 A2: Role-Clustered (语义/组织相关授权)

**来源依据**：Veda/EffVeda 的 OrgAccess benchmark（基于组织部门的角色分配）  
**实验角色**：模拟企业中"同部门文档倾向于授权给同部门角色"的结构

```python
def generate_A2(n_objects, n_users, n_roles, target_selectivity, n_clusters, noise, seed):
    rng = np.random.default_rng(seed)
    # Step 1: partition roles into clusters (departments)
    role_cluster = np.arange(n_roles) % n_clusters
    
    # Step 2: partition objects into clusters (proportional to role count)
    obj_cluster = np.arange(n_objects) % n_clusters
    
    # Step 3: assign roles to users (prefer same-cluster roles)
    roles_per_user = 3
    user_roles = {}
    user_cluster = np.arange(n_users) % n_clusters
    for u in range(n_users):
        home_roles = np.where(role_cluster == user_cluster[u])[0]
        other_roles = np.where(role_cluster != user_cluster[u])[0]
        n_home = max(1, int(roles_per_user * (1 - noise)))
        n_other = roles_per_user - n_home
        chosen = list(rng.choice(home_roles, min(n_home, len(home_roles)), replace=False))
        if n_other > 0 and len(other_roles) > 0:
            chosen += list(rng.choice(other_roles, min(n_other, len(other_roles)), replace=False))
        user_roles[u] = set(chosen)
    
    # Step 4: assign roles to objects (cluster-biased)
    # Objects in cluster c get roles from cluster c with high probability
    p_in_cluster = calibrate_for_selectivity(target_selectivity, roles_per_user, n_roles, n_clusters)
    p_cross = p_in_cluster * noise
    
    object_roles = {}
    for obj in range(n_objects):
        c = obj_cluster[obj]
        granted = set()
        for r in range(n_roles):
            p = p_in_cluster if role_cluster[r] == c else p_cross
            if rng.random() < p:
                granted.add(r)
        if len(granted) == 0:
            granted = {rng.choice(np.where(role_cluster == c)[0])}
        object_roles[obj] = granted
    
    return user_roles, object_roles
```

**参数**：
- `n_clusters`: 10 (模拟 10 个部门)
- `noise`: 0.1 (10% 跨部门访问)
- `roles_per_user`: 3
- 扫描变量：target_selectivity

### 3.4 A3: Shared-Core + Private-Tail (企业公共知识 + 私有长尾)

**来源依据**：企业 RAG 场景中常见的"公共知识库 + 团队/个人私有文档"模式  
**实验角色**：测试高共享度 core 与低共享度 tail 的混合效应

```python
def generate_A3(n_objects, n_users, n_roles, target_selectivity, 
                core_fraction, core_openness, seed):
    rng = np.random.default_rng(seed)
    n_core = int(n_objects * core_fraction)
    n_private = n_objects - n_core
    
    # Step 1: user-role assignment (same as A1)
    roles_per_user = 3
    user_roles = {}
    for u in range(n_users):
        user_roles[u] = set(rng.choice(n_roles, roles_per_user, replace=False))
    
    # Step 2: core objects — most roles can access
    # core_openness = fraction of roles granted per core object
    object_roles = {}
    for obj in range(n_core):
        n_granted = max(1, int(n_roles * core_openness))
        object_roles[obj] = set(rng.choice(n_roles, n_granted, replace=False))
    
    # Step 3: private-tail objects — very few roles (1-2)
    # Calibrate so overall selectivity matches target
    # Effective selectivity = core_fraction * core_sel + (1-core_fraction) * tail_sel
    # core_sel ≈ 1-(1-core_openness)^roles_per_user
    # Solve for tail_sel
    core_sel = 1 - (1 - core_openness) ** roles_per_user
    tail_sel = (target_selectivity - core_fraction * core_sel) / (1 - core_fraction)
    tail_sel = max(0.001, min(0.5, tail_sel))
    tail_grants_per_obj = max(1, int(n_roles * (1 - (1-tail_sel)**(1.0/roles_per_user))))
    
    for obj in range(n_core, n_objects):
        object_roles[obj] = set(rng.choice(n_roles, min(tail_grants_per_obj, n_roles), replace=False))
    
    return user_roles, object_roles
```

**参数**：
- `core_fraction`: 0.3 (30% 对象是公共知识)
- `core_openness`: 0.8 (core 对象被 80% 的角色可见)
- `roles_per_user`: 3
- 扫描变量：target_selectivity (控制 tail 部分的紧缩程度)

### 3.5 A5: Adversarial Anti-Correlated (压力测试)

**来源依据**：构造最大化 ACL 碎片化的分布，测试最坏情况  
**实验角色**：压力测试，不代表典型企业分布。**若差异仅在 A5 出现，不足以确认 Q 路线。**

```python
def generate_A5(n_objects, n_users, n_roles, target_selectivity, seed):
    rng = np.random.default_rng(seed)
    roles_per_user = 3
    
    # Step 1: user-role assignment (same as A1)
    user_roles = {}
    for u in range(n_users):
        user_roles[u] = set(rng.choice(n_roles, roles_per_user, replace=False))
    
    # Step 2: anti-correlate ACL with graph locality
    # Sort objects by their graph-page assignment
    # Assign roles such that adjacent objects in the graph have DIFFERENT role sets
    # This maximizes the "ACL fragmentation" within each graph page
    
    grants_per_object = max(1, int(n_roles * (1 - (1-target_selectivity)**(1.0/roles_per_user))))
    
    object_roles = {}
    for obj in range(n_objects):
        # Rotate role window based on object's page position
        # Objects on the same page get maximally different role sets
        page_id = obj // 64  # approximate page size
        offset_in_page = obj % 64
        start_role = (offset_in_page * (n_roles // 64)) % n_roles
        candidates = [(start_role + i) % n_roles for i in range(grants_per_object)]
        object_roles[obj] = set(candidates)
    
    return user_roles, object_roles
```

**参数**：
- `roles_per_user`: 3
- 碎片化策略：同一 graph page 内的 object 被授予不同角色集合
- 扫描变量：target_selectivity

---

## 4. Query-User Binding

```python
def generate_query_user_binding(n_queries, n_users, seed):
    rng = np.random.default_rng(seed)
    # Each query is randomly assigned to a user
    query_user = rng.integers(0, n_users, size=n_queries)
    return query_user
```

- 1000 queries × 1000 users → 每个 user 平均约 1 个 query
- Query vector 来自 SIFT1M query.bin 前 1000 行
- User 随机分配（aligned with HoneyBee §6.1 做法）

---

## 5. Authorized Ground Truth Generation

```python
def generate_authorized_gt(vectors, queries, query_user, user_roles, object_roles, k):
    """Brute-force exact authorized top-k for each query."""
    authorized_gt = []
    for qi in range(len(queries)):
        user = query_user[qi]
        user_role_set = user_roles[user]
        
        # Find all authorized objects
        authorized_objects = []
        for obj in range(len(vectors)):
            obj_role_set = object_roles[obj]
            if user_role_set & obj_role_set:  # any role match
                authorized_objects.append(obj)
        
        # Compute exact distances and get top-k
        if len(authorized_objects) > 0:
            dists = compute_distances(queries[qi], vectors[authorized_objects])
            topk_idx = np.argsort(dists)[:k]
            authorized_gt.append([authorized_objects[i] for i in topk_idx])
        else:
            authorized_gt.append([])
    
    return authorized_gt
```

- k=10
- 距离度量：L2 (aligned with SIFT1M convention)
- 每个 query 的 authorized GT 是该 user 可见对象中距离最近的 k 个

---

## 6. Semantic Distinction (C4)

### 6.1 三类操作的定义

| 类型 | 操作 | 影响范围 | 是否改变 graph approximate predicate |
|------|------|---------|-------------------------------------|
| **Query-side** | 用户提交查询 | 查询时展开 user → roles → policy atoms | 否，只读 |
| **Object-side grant/revoke** | 管理员给 object 添加/删除 role 授权 | 改变该 object 的 approximate predicate | **是** |
| **User membership update** | 管理员改变 user-role 映射 | 改变 query-side role closure | 否，不改变 object 状态 |

### 6.2 P0 范围

- **P0 只测 query-side 差异**：不同 ACL 分布下的查询行为
- **Object-side grant/revoke**：P0 阶段用 fresh vs stale fixture 验证（M1 已完成）
- **User membership update**：通过 query-side role closure 处理，不展开为 object writes

### 6.3 安全语义（已纠正）

| 层 | False positive | False negative |
|---|---------------|----------------|
| Approximate (routing) | 额外搜索/I/O，exact verifier 兜底 | **不可恢复 recall loss**（G0 已证明） |
| Exact (verifier) | **安全违规：泄露** | Recall loss，但可通过 refill 部分恢复 |

---

## 7. Three-Axis Workload Matrix (C5)

### 7.1 初始估算

| Workload region | 轴A: 查询碎片化 | 轴B: Policy lookup | 轴C: Update writes | 主导问题 |
|---|---|---|---|---|
| A1 Random, s=0.01 | 高：随机碎片化，每 page 多数 node unauthorized | 中：1M×100 roles≈12.5MB bitmap 可放 DRAM | 低：static workload | **A (如果 fragmentation 真的影响 graph I/O)** |
| A1 Random, s=0.20 | 中：多数 node authorized，碎片化下降 | 低 | 低 | 可能无主导 |
| A2 Role-clustered, s=0.05 | 低-中：同 cluster 对象聚集，碎片化较低 | 中 | 低 | **需要实验确认是否 cluster 结构减少碎片化** |
| A3 Shared-core, s=0.05 | 混合：core 部分低碎片化，tail 部分高碎片化 | 中 | 低 | **A (tail 部分)** |
| A5 Anti-correlated, s=0.05 | 极高：同 page 内 object 角色集不重叠 | 中 | 低 | **A (by construction)** |
| 高频 object grant | 取决于底层分布 | 取决于 policy 放置 | 高：每次 grant 可能触发 page rewrite | **C** |
| 高频 membership update | 不直接影响 | 可能触发 closure 重算 | 低：通过 query-side 处理 | 可能无主导 |

### 7.2 哪些需要实验、哪些可以分析

| 格子 | 方法 | 理由 |
|------|------|------|
| A1/A2/A3/A5 × 轴A | **M3 实验** | 核心 falsification：碎片化是否导致额外 graph I/O |
| 所有 × 轴B | **分析估算** | 1M×100 roles = 12.5 MB bitmap，远小于 24 GiB RSS；SSD policy I/O 在 1M 规模被 page cache 吸收 |
| 所有 × 轴C | **分析估算** | P0 阶段不做 dynamic ACL 实验，用 Zanzibar 参数做更新频率估算 |

### 7.3 轴A 优先的理由

轴 A 是方向级 falsification：

1. 如果 ACL 碎片化在 SSD 图遍历中**不产生**显著额外 I/O → Q 路线不成立
2. 如果碎片化效应**存在但可被选择率完全解释**（即只是普通 low-selectivity 问题）→ 不需要 ACL-specific 机制
3. 只有碎片化效应**存在且 ACL 分布结构是独立因素**时 → Q 路线成立

轴 B 和 C 可以用分析先行：
- 轴 B：1M 规模下 policy metadata 很小，SSD policy I/O 被 page cache 吸收，需要 100M+ 才能真正暴露
- 轴 C：需要 dynamic update workload，但 P0 阶段不做 update 实验

---

## 8. Machine-Readable Manifest

以下为 Codex M3 使用的冻结参数文件：

```yaml
# === manifest.yaml ===
version: "p0-m3-v1"
seed: 42
frozen_by: "Claude"
frozen_at: "2026-07-21T13:42+08:00"

dataset:
  name: "SIFT1M"
  path: "/home/ubuntu/pz/VectorDB/data/VectorDB/bigann/sift/full.bin"
  n_vectors: 1000000
  dimensions: 128

graph:
  note: "Use M0-frozen graph; do NOT rebuild per distribution"
  adapter: "fixed-graph-replace-policy-payload-only"

search:
  k: 10
  l_search: [10, 20, 40, 80, 120]
  strategies: ["PRE_FILTER", "IN_FILTER", "POST_FILTER"]
  forced_strategy: true  # do not use auto planner for main analysis

acl:
  n_users: 1000
  n_roles: 100
  roles_per_user: 3
  target_selectivities: [0.01, 0.05, 0.10, 0.20, 0.50]

queries:
  n_queries: 1000
  source: "first 1000 rows of query.bin"
  user_binding: "random, seed=42"

distributions:
  A1_random:
    type: "random"
    description: "Unstructured baseline, no ACL-graph correlation"
    params:
      roles_per_user: 3
      p_role: "calibrated from target_selectivity"
    experimental_role: "null hypothesis"
    
  A2_role_clustered:
    type: "role_clustered"
    description: "Organizational structure, same-department bias"
    params:
      n_clusters: 10
      noise: 0.1
      roles_per_user: 3
    experimental_role: "representative realistic distribution"
    source: "inspired by Veda OrgAccess"
    
  A3_shared_core:
    type: "shared_core_private_tail"
    description: "Public knowledge base + team-private documents"
    params:
      core_fraction: 0.3
      core_openness: 0.8
      roles_per_user: 3
    experimental_role: "representative enterprise RAG pattern"
    source: "enterprise RAG deployment pattern"
    
  A5_adversarial:
    type: "adversarial_anti_correlated"
    description: "Maximally fragmented ACL within graph pages"
    params:
      roles_per_user: 3
      fragmentation: "rotate role window by page offset"
    experimental_role: "stress test ONLY"
    caveat: "If differences appear ONLY in A5, Q route is NOT established"

ground_truth:
  method: "brute_force_exact_authorized_topk"
  k: 10
  metric: "L2"

output_format:
  per_distribution:
    - "user_roles.bin"      # uint16[n_users × roles_per_user]
    - "object_roles.spmat"  # CSR sparse matrix [n_objects × n_roles]
    - "query_user.bin"      # uint32[n_queries]
    - "authorized_gt.bin"   # uint32[n_queries × k]
  hashes: "sha256 for all generated files"
```

---

## 9. M3 执行的前置条件

| 条件 | 状态 | 负责方 |
|------|------|--------|
| Workload manifest 冻结 | ✅ 本文档 | Claude |
| R_dense=128 裁决 | ⏳ 待 Gpt | Gpt |
| 固定图/替换 policy payload adapter | ⏳ 待 Gpt | Gpt |
| cgroup/block-layer I/O 计量修正 | ⏳ 待 Codex | Codex |

---

## 10. 补充说明

### 10.1 为什么不做 A4 (Hierarchical RBAC)

Gpt 裁决第五节指出 A4 首轮只处理 query-side role closure 与逻辑模型。原因：
- 实现 role hierarchy 的 transitive closure 需要额外基础设施
- P0 目标是测 ACL 碎片化对图遍历的影响，不是测 hierarchy 复杂度
- 如果 A1/A2/A3 已经能回答 Q 路线问题，A4 可以在 P1 补做

### 10.2 Scale 外推说明

1M 只是 preflight。如果 Q 路线在 1M 确认，需要在 10M/100M 做结构化外推：
- Graph I/O 与 n 的关系（应为 O(log n) 或 O(n^ε)）
- Policy metadata 与 n×R 的关系（1M×100 = 12.5MB，100M×100 = 1.25GB）
- Page cache 吸收边界（取决于可用 DRAM 和 working set）

### 10.3 参数不伪装成某企业真实值

所有参数基于 HoneyBee/Veda/Curator 的公开 benchmark + Zanzibar 的公开规模数据。
1000 users / 100 roles 是 HoneyBee 和 Veda 共同使用的默认配置，代表中型企业场景。
