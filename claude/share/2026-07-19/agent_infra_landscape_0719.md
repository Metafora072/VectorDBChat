# Phase 1: Agent Infrastructure Landscape Survey

**Date**: 2026-07-19
**Scope**: Agent-related systems and infrastructure, no GPU dependency
**Sources**: 12 WebSearch queries, ~80 papers/systems surveyed

---

## Sub-Directions Mapped

### 1. Agent Memory Systems
**State**: Active, fast-moving, prototype-grade
- Taxonomy: episodic / semantic / procedural (converged 2025)
- Benchmarks: LoCoMo, LongMemEval, BEAM (1M/10M token)
- Leading: MAGMA (0.7 LoCoMo), Mem0 (6,956 tokens/query, ECAI 2025), Zep (graph-native), MemoryOS, Letta
- Key paper: "Is Agent Memory a Database?" (arXiv 2605.26252, May 2026) — proposes Governed Evolving Memory (GEM), formalizes ingestion/revision/forgetting/retrieval operators; argues correctness is trajectory-level, not record-level
- Open problems: cross-session identity, temporal abstraction at scale, contradiction resolution, memory staleness, confidence tracking

### 2. Tool Use & MCP
**State**: Infrastructure mature, research opportunities narrow
- MCP: 97M monthly downloads, 5800+ servers, de facto standard
- ICML 2026: EvoC2F (compiled tool orchestration), MAS-Orchestra, MCP-Persona
- 57.3% of organizations have agents in production
- Open: tool orchestration optimization, cost-optimal planning (CostBench)

### 3. RAG / Context Engine
**State**: Very crowded, incremental
- Evolution from RAG → "Context Engine" / "Agentic RAG"
- GraphRAG for multi-hop, agentic retrieval pipelines
- Multiple comprehensive surveys (arXiv 2506.00054, 2501.09136)
- Production: batch refresh strategies, freshness-latency tradeoff
- Open: adaptive retrieval, privacy-preserving retrieval, real-time streaming

### 4. Multi-Agent Coordination
**State**: Framework-heavy, systems research gap
- Frameworks: LangGraph, CrewAI, AutoGen/AG2, Google ADK, OpenAI Agents SDK
- AAAI 2026 WMAC bridge program
- Core unsolved: "shared mutable state across parallel workers" (direct quote from industry analysis)
- Trust model enforced by convention, not infrastructure
- Open: formal concurrency control, conflict resolution, governance

### 5. Code Agents
**State**: Model-capability-dominated, infrastructure thin
- SWE-bench Verified: 93.9% (Claude Mythos), up from 50% being "moonshot" at launch
- Key finding: "bottleneck is model capability, not scaffolding" (mini-swe-agent)
- Approaches: real-time search (Claude Code) vs pre-built index vs hybrid
- "Filesystem is the Database" thesis for agent workloads
- Open: persistent incremental code understanding, cross-session state

### 6. Agent Sandbox & Security
**State**: Engineering-driven, security-critical
- Isolation: MicroVMs, gVisor, WASM, hardened containers
- OWASP Agentic AI Top 10 (Dec 2025)
- 90% incident reduction with sandboxing
- 39 papers catalogued (2023-2026), 4 CVEs in production harnesses
- Open: formal isolation guarantees, side-channel attacks on agent state

### 7. Durable Execution & Checkpointing
**State**: Industry frameworks exist, formal gaps
- Temporal, LangGraph MemorySaver, AWS Lambda Durable Functions (Dec 2025), MS Durable Task (Apr 2026)
- Overhead: 10-50ms per activity dispatch (negligible for LLM calls)
- Deterministic replay works IF code is deterministic
- Key gap: "non-persistable regions" — cannot checkpoint mid-stream response or post-side-effect-pre-record
- Semantic checkpointing (context summaries) for recovery without full replay
- Open: formal recovery theory for agent workflows, exactly-once for external tools

### 8. Agent Trace / Observability
**State**: Rapid growth (39 papers H1 2026 vs ~1 in 2024)
- OpenTelemetry GenAI semantic conventions as emerging standard
- AgentTelemetry benchmark: 14 fault types, 9 agent span kinds
- View-oriented Conversation Compiler for trace analysis (arXiv 2603.29678)
- Session replay = agent transaction log replay
- Open: efficient trace storage, trace-level queries, cross-session analysis

### 9. Agent Data Management (Nascent)
**State**: Emerging area, very few systems papers
- "Is Agent Memory a Database?" (arXiv 2605.26252) — position paper
- VLDB 2026 Agents+Graph workshop (Sep 4, Boston)
- Experience Graphs (arXiv 2606.29823) — structured procedural memory
- "The Filesystem Is the Database" thesis
- ElephantBroker: knowledge-grounded cognitive runtime
- Open: almost everything — this is a wide-open systems research gap

---

## Structural Gaps Identified

| Gap | Area | Prior Work | Novelty Risk | PZ Fit |
|-----|------|-----------|-------------|--------|
| **G1**: Agent Memory Store — disk-resident, versioned, durable memory engine | Memory + Data Mgmt | GEM paper (formalization only), no system | LOW (wide open) | **HIGH** |
| **G2**: Working Set Management for Agent Memory — hot/cold tiering, buffer pool theory | Memory | None identified | LOW | **HIGH** |
| **G3**: Multi-Agent Shared State Consistency — formal concurrency control | Coordination | "Convention not infrastructure" | MEDIUM (could be generic DB) | MEDIUM |
| **G4**: Agent Trace Storage Engine — efficient storage/query/replay for trajectories | Observability | OpenTelemetry, ad-hoc logging | MEDIUM | MEDIUM |
| **G5**: Durable Agent Recovery with Non-Persistable Regions | Checkpointing | Temporal/LangGraph (practical) | MEDIUM (could be generic WAL) | MEDIUM |
| **G6**: Persistent Incremental Code Understanding Store | Code Agents | Real-time search, pre-built index | LOW-MEDIUM | **HIGH** |
| **G7**: Memory Contradiction & Temporal Consistency | Memory | Identified as open, no formal solution | LOW | MEDIUM |
| **G8**: Experience Graph Storage for Self-Improving Agents | Memory + Graph | Experience Graphs paper (recent) | MEDIUM (prior art forming) | HIGH |

## Key Observations

1. **The GEM paper creates an opening**: "Is Agent Memory a Database?" explicitly argues that agent memory needs new data management primitives. But it's a formalization — no system exists. A systems paper building this would be the first.

2. **"Filesystem is the Database" for agents is a thesis, not a system**: Multiple blog posts and one patent reference this idea, but no systems paper has formalized or implemented it with proper storage engine techniques.

3. **Agent workloads have novel access patterns**: Write-heavy (continuous learning), read patterns are query-dependent (semantic + temporal + multi-hop), memory has confidence/staleness, working set changes with task. These are NOT the same as traditional DB workloads.

4. **The VLDB 2026 Agents+Graph workshop** (Sep 4) signals that the data management community is just starting to engage with agent infrastructure — a paper targeting this area would be timely.

5. **No GPU dependency**: All identified gaps are CPU/storage/NVMe problems, fitting PZ's hardware constraints.

6. **Disk residency matters**: As agents accumulate memory over weeks/months, in-memory-only approaches break. Disk-resident agent memory with proper buffer management is an open infrastructure problem.
