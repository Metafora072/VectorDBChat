#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <list>
#include <limits>
#include <memory>
#include <set>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "linux_aligned_file_reader.h"
#include "nbr/pq_table.h"
#include "utils.h"

namespace {

using Clock = std::chrono::steady_clock;

double us_since(const Clock::time_point &start) {
  return std::chrono::duration<double, std::micro>(Clock::now() - start).count();
}

struct LayoutHeader {
  char magic[8];
  uint64_t npoints;
  uint64_t dim;
  uint64_t degree;
  uint64_t entry;
  uint64_t record_bytes;
  uint64_t nodes_per_page;
  uint64_t page_bytes;
};
static_assert(sizeof(LayoutHeader) == 64);

struct Candidate {
  uint32_t id;
  float pq;
};

struct AlignedFloatDeleter {
  void operator()(float *p) const { pipeann::aligned_free(p); }
};

struct Page {
  void *buf = nullptr;
  int state = 0;  // 0 absent, 1 inflight, 2 ready
  double issue_us = 0;
  double complete_us = 0;
  std::vector<uint32_t> requested_ids;

  Page() { pipeann::alloc_aligned(&buf, SECTOR_LEN, SECTOR_LEN); }
  ~Page() { pipeann::aligned_free(buf); }
  Page(const Page &) = delete;
  Page &operator=(const Page &) = delete;
};

enum class IOType { Graph, Vector };

struct Pending {
  IORequest req;
  IOType type;
  uint64_t page;
  Page *data;

  Pending(IOType type, uint64_t page, Page *data)
      : req((1 + page) * SECTOR_LEN, SECTOR_LEN, data->buf, 0, SECTOR_LEN), type(type), page(page), data(data) {}
};

struct Config {
  std::string graph_path;
  std::string vector_path;
  std::string pq_codes_path;
  std::string pq_pivots_path;
  std::string query_path;
  std::string truth_path;
  std::string output_path;
  std::string mode = "fixed";
  uint32_t k = 10;
  uint32_t l = 100;
  uint32_t width = 4;
  uint32_t batch = 10;
  uint32_t query_limit = 0;
  uint32_t query_start = 0;
  uint32_t vector_quota = 1;
};

struct Stats {
  uint32_t qid = 0;
  double total_us = 0;
  double traversal_us = 0;
  double exposed_vector_tail_us = 0;
  double pq_cpu_us = 0;
  double exact_cpu_us = 0;
  double graph_io_wait_us = 0;
  double vector_io_wait_us = 0;
  uint64_t graph_ios = 0;
  uint64_t vector_ios = 0;
  uint64_t expanded = 0;
  uint64_t discovered = 0;
  uint64_t heap_replacements = 0;
  uint64_t heap_full_expanded = 0;
  uint64_t stability_expanded = 0;
  double stability_us = 0;
  double stability_position = 1.0;
  double trigger_remaining_fraction = 0;
  uint64_t io_poll_rounds = 0;
  uint64_t prefetched_candidates = 0;
  uint64_t useful_prefetched_candidates = 0;
  uint64_t wasted_prefetch_candidates = 0;
  uint64_t unfinished_vector_pages_at_traversal_end = 0;
  uint64_t ready_vector_pages_at_traversal_end = 0;
  double prefetch_overlap_us = 0;
  uint64_t final_no_replace_streak = 0;
  uint64_t rerank_batches = 0;
  double prefetch_benefit_ratio = 0;
  uint64_t oracle_earliest_safe_expanded = 0;
  uint64_t oracle_final_set_match = 0;
  double recall = 0;
};

Config parse_args(int argc, char **argv) {
  Config c;
  auto value = [&](int &i) -> std::string {
    if (i + 1 >= argc) throw std::runtime_error(std::string("missing value for ") + argv[i]);
    return argv[++i];
  };
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--graph") c.graph_path = value(i);
    else if (a == "--vectors") c.vector_path = value(i);
    else if (a == "--pq-codes") c.pq_codes_path = value(i);
    else if (a == "--pq-pivots") c.pq_pivots_path = value(i);
    else if (a == "--queries") c.query_path = value(i);
    else if (a == "--truth") c.truth_path = value(i);
    else if (a == "--output") c.output_path = value(i);
    else if (a == "--mode") c.mode = value(i);
    else if (a == "--k") c.k = std::stoul(value(i));
    else if (a == "--L") c.l = std::stoul(value(i));
    else if (a == "--width") c.width = std::stoul(value(i));
    else if (a == "--B") c.batch = std::stoul(value(i));
    else if (a == "--query-limit") c.query_limit = std::stoul(value(i));
    else if (a == "--query-start") c.query_start = std::stoul(value(i));
    else if (a == "--vector-quota") c.vector_quota = std::stoul(value(i));
    else throw std::runtime_error("unknown argument: " + a);
  }
  if (c.graph_path.empty() || c.vector_path.empty() || c.pq_codes_path.empty() || c.pq_pivots_path.empty() ||
      c.query_path.empty() || c.truth_path.empty() || c.output_path.empty())
    throw std::runtime_error("required path argument missing");
  if (c.k == 0 || c.l < c.k || c.width == 0 || c.width > MAX_N_SECTOR_READS || c.batch == 0)
    throw std::runtime_error("invalid K/L/width/B");
  if (c.mode != "naive" && c.mode != "fixed" && c.mode != "oracle_final" && c.mode != "oracle_safe" &&
      c.mode != "oracle_bw")
    throw std::runtime_error("mode must be naive, fixed, oracle_final, oracle_safe, or oracle_bw");
  if (c.vector_quota == 0 || c.vector_quota > c.width) throw std::runtime_error("invalid vector quota");
  return c;
}

LayoutHeader read_header(const std::string &path, const char expected[8]) {
  std::ifstream in(path, std::ios::binary);
  LayoutHeader h{};
  in.read(reinterpret_cast<char *>(&h), sizeof(h));
  if (!in || std::memcmp(h.magic, expected, 8) != 0 || h.page_bytes != SECTOR_LEN)
    throw std::runtime_error("bad layout header: " + path);
  return h;
}

class Searcher {
 private:
  struct OraclePlan {
    std::vector<uint32_t> final_ids;
    uint64_t earliest_safe_expanded = 0;
  };

 public:
  explicit Searcher(const Config &cfg) : cfg_(cfg), pq_table_(pipeann::Metric::L2) {
    gh_ = read_header(cfg.graph_path, "DCSRGR01");
    vh_ = read_header(cfg.vector_path, "DCSRVE01");
    if (gh_.npoints != vh_.npoints || gh_.dim != vh_.dim || gh_.entry != vh_.entry)
      throw std::runtime_error("graph/vector metadata mismatch");
    size_t npts = 0, chunks = 0;
    pipeann::load_bin<uint8_t>(cfg.pq_codes_path, pq_codes_, npts, chunks);
    if (npts != gh_.npoints) throw std::runtime_error("PQ point count mismatch");
    chunks_ = chunks;
    pq_table_.load_pq_centroid_bin(cfg.pq_pivots_path.c_str(), chunks_);
    if (pq_table_.ndims != gh_.dim) throw std::runtime_error("PQ dimension mismatch");
    graph_reader_.open(cfg.graph_path, false, false);
    vector_reader_.open(cfg.vector_path, false, false);
    if (cfg.mode == "oracle_final" || cfg.mode == "oracle_safe") {
      std::ifstream in(cfg.graph_path, std::ios::binary | std::ios::ate);
      size_t bytes = static_cast<size_t>(in.tellg());
      graph_memory_.resize(bytes);
      in.seekg(0);
      in.read(graph_memory_.data(), bytes);
      if (!in) throw std::runtime_error("failed to load graph for oracle prepass");
    }
  }

  ~Searcher() {
    graph_reader_.close();
    vector_reader_.close();
    delete[] pq_codes_;
  }

  Stats run(uint32_t qid, const float *query, const uint32_t *truth, uint32_t truth_dim) {
    Stats s;
    s.qid = qid;
    OraclePlan oracle;
    if (cfg_.mode == "oracle_final" || cfg_.mode == "oracle_safe") oracle = build_oracle_plan(query);
    s.oracle_earliest_safe_expanded = oracle.earliest_safe_expanded;
    const auto query_start = Clock::now();
    void *ctx = graph_reader_.get_ctx();
    float *chunk_dists_raw = nullptr;
    pipeann::alloc_aligned(reinterpret_cast<void **>(&chunk_dists_raw), 256 * chunks_ * sizeof(float), 64);
    std::unique_ptr<float, AlignedFloatDeleter> chunk_dists(chunk_dists_raw);
    auto cpu_start = Clock::now();
    pq_table_.populate_chunk_distances(query, chunk_dists.get());
    s.pq_cpu_us += us_since(cpu_start);

    auto pq_dist = [&](uint32_t id) {
      auto st = Clock::now();
      float d = 0;
      const uint8_t *code = pq_codes_ + static_cast<uint64_t>(id) * chunks_;
      for (uint64_t c = 0; c < chunks_; ++c) d += chunk_dists.get()[c * 256 + code[c]];
      s.pq_cpu_us += us_since(st);
      return d;
    };

    std::vector<Candidate> pool;
    pool.reserve(cfg_.l + 1);
    std::unordered_set<uint32_t> discovered;
    discovered.reserve(cfg_.l * 16);
    std::unordered_map<uint32_t, uint8_t> graph_state;  // 0 not issued, 1 issued, 2 expanded
    std::unordered_map<uint64_t, std::unique_ptr<Page>> graph_pages;
    std::unordered_map<uint64_t, std::unique_ptr<Page>> vector_pages;
    std::list<Pending> pending;
    std::vector<uint32_t> expanded_ids;
    expanded_ids.reserve(cfg_.l);
    std::vector<uint32_t> graph_round;
    graph_round.reserve(cfg_.width);
    std::unordered_set<uint32_t> prefetched_ids;
    uint64_t no_replace_streak = 0;
    bool heap_full_seen = false;
    bool triggered = false;
    uint64_t target = cfg_.k + cfg_.batch;
    double traversal_end_us = 0;

    auto in_pool = [&](uint32_t id) {
      return std::any_of(pool.begin(), pool.end(), [&](const Candidate &x) { return x.id == id; });
    };

    auto insert_candidate = [&](uint32_t id, float d) {
      if (id >= gh_.npoints || !discovered.insert(id).second) return false;
      s.discovered++;
      auto it = std::lower_bound(pool.begin(), pool.end(), d, [](const Candidate &a, float v) { return a.pq < v; });
      size_t pos = static_cast<size_t>(it - pool.begin());
      bool top_changed = pos < target;
      if (pool.size() < cfg_.l) {
        pool.insert(it, Candidate{id, d});
        graph_state[id] = 0;
      } else if (pos < cfg_.l) {
        uint32_t evicted = pool.back().id;
        pool.pop_back();
        pool.insert(pool.begin() + pos, Candidate{id, d});
        graph_state[id] = 0;
        graph_state.erase(evicted);
      } else {
        top_changed = false;
      }
      if (top_changed && pool.size() >= target) s.heap_replacements++;
      if (!heap_full_seen && pool.size() >= target) {
        heap_full_seen = true;
        s.heap_full_expanded = s.expanded;
      }
      return top_changed;
    };

    insert_candidate(static_cast<uint32_t>(gh_.entry), pq_dist(static_cast<uint32_t>(gh_.entry)));

    auto graph_page_id = [&](uint32_t id) { return static_cast<uint64_t>(id) / gh_.nodes_per_page; };
    auto vector_page_id = [&](uint32_t id) { return static_cast<uint64_t>(id) / vh_.nodes_per_page; };

    auto count_inflight = [&]() {
      size_t n = 0;
      for (const auto &p : pending)
        if (!p.req.finished) ++n;
      return n;
    };

    auto count_vector_inflight = [&]() {
      size_t n = 0;
      for (const auto &p : pending)
        if (!p.req.finished && p.type == IOType::Vector) ++n;
      return n;
    };

    auto issue_page = [&](IOType type, uint64_t page_id, uint32_t id) {
      auto &pages = type == IOType::Graph ? graph_pages : vector_pages;
      auto found = pages.find(page_id);
      if (found != pages.end()) {
        found->second->requested_ids.push_back(id);
        return false;
      }
      auto page = std::make_unique<Page>();
      page->state = 1;
      page->issue_us = us_since(query_start);
      page->requested_ids.push_back(id);
      Page *raw = page.get();
      pages.emplace(page_id, std::move(page));
      pending.emplace_back(type, page_id, raw);
      Pending &p = pending.back();
      if (type == IOType::Graph) {
        graph_reader_.send_io(p.req, ctx, false);
        s.graph_ios++;
      } else {
        vector_reader_.send_io(p.req, ctx, false);
        s.vector_ios++;
      }
      return true;
    };

    auto issue_vector_for = [&](uint32_t id) {
      if (prefetched_ids.insert(id).second) s.prefetched_candidates++;
      return issue_page(IOType::Vector, vector_page_id(id), id);
    };

    auto graph_ready = [&](uint32_t id) {
      auto it = graph_pages.find(graph_page_id(id));
      return it != graph_pages.end() && it->second->state == 2;
    };
    auto vector_ready = [&](uint32_t id) {
      auto it = vector_pages.find(vector_page_id(id));
      return it != vector_pages.end() && it->second->state == 2;
    };

    auto expand_one = [&](uint32_t id) {
      auto pit = graph_pages.find(graph_page_id(id));
      Page *page = pit->second.get();
      uint64_t slot = id % gh_.nodes_per_page;
      const char *rec = static_cast<const char *>(page->buf) + slot * gh_.record_bytes;
      uint32_t degree = 0;
      std::memcpy(&degree, rec, sizeof(degree));
      if (degree > gh_.degree) throw std::runtime_error("corrupt graph degree");
      const uint32_t *nbrs = reinterpret_cast<const uint32_t *>(rec + 4);
      bool top_changed = false;
      for (uint32_t i = 0; i < degree; ++i) top_changed |= insert_candidate(nbrs[i], pq_dist(nbrs[i]));
      graph_state[id] = 2;
      expanded_ids.push_back(id);
      s.expanded++;
      if (top_changed) no_replace_streak = 0;
      else ++no_replace_streak;
      if (!triggered && pool.size() >= target && no_replace_streak >= cfg_.batch &&
          (cfg_.mode == "fixed" || cfg_.mode == "oracle_bw")) {
        triggered = true;
        s.stability_expanded = s.expanded;
        s.stability_us = us_since(query_start);
      }
      if (!triggered && cfg_.mode == "oracle_safe" && s.expanded >= oracle.earliest_safe_expanded) {
        triggered = true;
        s.stability_expanded = s.expanded;
        s.stability_us = us_since(query_start);
      }
    };

    auto ensure_graph_round = [&]() {
      if (!graph_round.empty()) return false;
      for (const Candidate &c : pool) {
        auto st = graph_state.find(c.id);
        if (st != graph_state.end() && st->second == 0) graph_round.push_back(c.id);
        if (graph_round.size() == cfg_.width) break;
      }
      return !graph_round.empty();
    };

    auto expand_ready = [&]() {
      if (graph_round.empty()) return false;
      for (uint32_t id : graph_round) {
        auto st = graph_state.find(id);
        if (st == graph_state.end() || st->second != 1 || !graph_ready(id)) return false;
        if (cfg_.mode == "naive" && !vector_ready(id)) return false;
      }
      for (uint32_t id : graph_round) expand_one(id);
      graph_round.clear();
      return true;
    };

    auto has_graph_work = [&]() {
      for (const Candidate &c : pool) {
        auto it = graph_state.find(c.id);
        if (it != graph_state.end() && it->second != 2) return true;
      }
      return false;
    };

    auto issue_naive_vectors = [&]() {
      bool progress = false;
      for (const Candidate &c : pool) {
        if (count_inflight() >= cfg_.width) break;
        auto st = graph_state.find(c.id);
        if (st != graph_state.end() && st->second == 1 && graph_ready(c.id) && !vector_ready(c.id)) {
          progress |= issue_vector_for(c.id);
        }
      }
      return progress;
    };

    auto issue_graphs = [&]() {
      bool progress = ensure_graph_round();
      for (uint32_t id : graph_round) {
        if (count_inflight() >= cfg_.width) break;
        auto st = graph_state.find(id);
        if (st == graph_state.end() || st->second != 0) continue;
        uint64_t page_id = graph_page_id(id);
        auto pg = graph_pages.find(page_id);
        graph_state[id] = 1;
        if (pg == graph_pages.end()) progress |= issue_page(IOType::Graph, page_id, id);
        else if (pg->second->state == 2) progress = true;
      }
      return progress;
    };

    auto issue_fixed_prefetch = [&]() {
      if (!triggered) return false;
      bool progress = false;
      size_t n = std::min<size_t>(target, pool.size());
      for (size_t i = 0; i < n && count_inflight() < cfg_.width; ++i) {
        if (!vector_ready(pool[i].id)) progress |= issue_vector_for(pool[i].id);
      }
      return progress;
    };

    auto issue_oracle_prefetch = [&]() {
      if (cfg_.mode == "oracle_safe" && !triggered) return false;
      bool progress = false;
      for (uint32_t id : oracle.final_ids) {
        if (count_inflight() >= cfg_.width || count_vector_inflight() >= cfg_.vector_quota) break;
        if (!discovered.count(id) || vector_ready(id)) continue;
        progress |= issue_vector_for(id);
      }
      return progress;
    };

    auto issue_bw_prefetch = [&]() {
      if (!triggered) return false;
      bool progress = false;
      size_t n = std::min<size_t>(target, pool.size());
      for (size_t i = 0; i < n; ++i) {
        if (count_inflight() >= cfg_.width || count_vector_inflight() >= cfg_.vector_quota) break;
        if (!vector_ready(pool[i].id)) progress |= issue_vector_for(pool[i].id);
      }
      return progress;
    };

    auto harvest = [&]() {
      graph_reader_.poll(ctx);
      s.io_poll_rounds++;
      bool any = false;
      for (auto it = pending.begin(); it != pending.end();) {
        if (!it->req.finished) {
          ++it;
          continue;
        }
        any = true;
        it->data->state = 2;
        it->data->complete_us = us_since(query_start);
        double wait = it->data->complete_us - it->data->issue_us;
        if (it->type == IOType::Graph) s.graph_io_wait_us += wait;
        else s.vector_io_wait_us += wait;
        it = pending.erase(it);
      }
      return any;
    };

    while (true) {
      bool progress;
      do {
        progress = false;
        while (expand_ready()) progress = true;
        if (cfg_.mode == "naive") progress |= issue_naive_vectors();
        if (cfg_.mode == "oracle_final") progress |= issue_oracle_prefetch();
        if (cfg_.mode == "oracle_bw") progress |= issue_bw_prefetch();
        progress |= issue_graphs();
        if (cfg_.mode == "fixed") progress |= issue_fixed_prefetch();
        if (cfg_.mode == "oracle_safe") progress |= issue_oracle_prefetch();
      } while (progress && count_inflight() < cfg_.width);

      // Traversal ends when every live graph candidate is expanded.  Vector
      // requests may still be in flight; their remaining time is the exposed
      // rerank tail and is intentionally harvested in the next phase.
      if (!has_graph_work()) break;
      if (!harvest()) std::this_thread::yield();
    }

    traversal_end_us = us_since(query_start);
    s.traversal_us = traversal_end_us;
    if (triggered) {
      s.stability_position = s.expanded ? static_cast<double>(s.stability_expanded) / s.expanded : 1.0;
      s.trigger_remaining_fraction = 1.0 - s.stability_position;
    }
    s.final_no_replace_streak = no_replace_streak;

    std::vector<uint32_t> rerank_ids;
    if (cfg_.mode == "naive") rerank_ids = expanded_ids;
    else {
      size_t n = std::min<size_t>(target, pool.size());
      for (size_t i = 0; i < n; ++i) rerank_ids.push_back(pool[i].id);
    }
    if (cfg_.mode == "oracle_final" || cfg_.mode == "oracle_safe") {
      std::unordered_set<uint32_t> actual(rerank_ids.begin(), rerank_ids.end());
      std::unordered_set<uint32_t> planned(oracle.final_ids.begin(), oracle.final_ids.end());
      s.oracle_final_set_match = actual == planned ? 1 : 0;
    }

    std::unordered_set<uint64_t> final_vector_pages;
    for (uint32_t id : rerank_ids) final_vector_pages.insert(vector_page_id(id));
    for (uint64_t page_id : final_vector_pages) {
      auto it = vector_pages.find(page_id);
      if (it != vector_pages.end() && it->second->state == 1) s.unfinished_vector_pages_at_traversal_end++;
      if (it != vector_pages.end() && it->second->state == 2) s.ready_vector_pages_at_traversal_end++;
    }
    for (const auto &kv : vector_pages) {
      const Page &page = *kv.second;
      if (page.issue_us >= traversal_end_us) continue;
      double covered_until = page.state == 2 ? std::min(page.complete_us, traversal_end_us) : traversal_end_us;
      s.prefetch_overlap_us += std::max(0.0, covered_until - page.issue_us);
    }

    size_t next = 0;
    while (next < rerank_ids.size() || count_inflight()) {
      while (next < rerank_ids.size() && count_inflight() < cfg_.width) {
        issue_vector_for(rerank_ids[next++]);
      }
      if (count_inflight() && !harvest()) std::this_thread::yield();
    }
    s.exposed_vector_tail_us = us_since(query_start) - traversal_end_us;

    std::vector<Candidate> exact;
    exact.reserve(rerank_ids.size());
    cpu_start = Clock::now();
    for (uint32_t id : rerank_ids) {
      Page *page = vector_pages.at(vector_page_id(id)).get();
      uint64_t slot = id % vh_.nodes_per_page;
      const float *vec = reinterpret_cast<const float *>(static_cast<const char *>(page->buf) + slot * vh_.record_bytes);
      float d = 0;
      for (uint64_t j = 0; j < vh_.dim; ++j) {
        float diff = query[j] - vec[j];
        d += diff * diff;
      }
      exact.push_back({id, d});
    }
    s.exact_cpu_us = us_since(cpu_start);
    std::sort(exact.begin(), exact.end(), [](const Candidate &a, const Candidate &b) { return a.pq < b.pq; });
    if (exact.size() > cfg_.k) exact.resize(cfg_.k);

    std::unordered_set<uint32_t> final_rerank(rerank_ids.begin(), rerank_ids.end());
    for (uint32_t id : prefetched_ids) {
      if (final_rerank.count(id)) s.useful_prefetched_candidates++;
      else s.wasted_prefetch_candidates++;
    }
    s.prefetch_benefit_ratio = prefetched_ids.empty()
                                   ? 0.0
                                   : static_cast<double>(s.useful_prefetched_candidates) / prefetched_ids.size();
    s.rerank_batches = (rerank_ids.size() + cfg_.batch - 1) / cfg_.batch;
    std::unordered_set<uint32_t> gt(truth, truth + std::min<uint32_t>(cfg_.k, truth_dim));
    uint32_t hits = 0;
    for (const auto &x : exact) hits += gt.count(x.id) ? 1 : 0;
    s.recall = static_cast<double>(hits) / cfg_.k;
    s.total_us = us_since(query_start);
    return s;
  }

 private:
  Config cfg_;
  LayoutHeader gh_{};
  LayoutHeader vh_{};
  uint8_t *pq_codes_ = nullptr;
  uint64_t chunks_ = 0;
  pipeann::FixedChunkPQTable<float> pq_table_;
  LinuxAlignedFileReader graph_reader_;
  LinuxAlignedFileReader vector_reader_;
  std::vector<char> graph_memory_;

  OraclePlan build_oracle_plan(const float *query) {
    float *chunk_raw = nullptr;
    pipeann::alloc_aligned(reinterpret_cast<void **>(&chunk_raw), 256 * chunks_ * sizeof(float), 64);
    std::unique_ptr<float, AlignedFloatDeleter> chunk(chunk_raw);
    pq_table_.populate_chunk_distances(query, chunk.get());
    auto dist = [&](uint32_t id) {
      float d = 0;
      const uint8_t *code = pq_codes_ + static_cast<uint64_t>(id) * chunks_;
      for (uint64_t c = 0; c < chunks_; ++c) d += chunk.get()[c * 256 + code[c]];
      return d;
    };
    std::vector<Candidate> pool;
    std::unordered_set<uint32_t> seen;
    std::unordered_set<uint32_t> expanded;
    std::unordered_map<uint32_t, uint64_t> first_discovery;
    auto insert = [&](uint32_t id, float d, uint64_t at) {
      if (id >= gh_.npoints || !seen.insert(id).second) return;
      first_discovery[id] = at;
      auto it = std::lower_bound(pool.begin(), pool.end(), d, [](const Candidate &a, float v) { return a.pq < v; });
      size_t pos = static_cast<size_t>(it - pool.begin());
      if (pool.size() < cfg_.l) pool.insert(it, {id, d});
      else if (pos < cfg_.l) {
        pool.pop_back();
        pool.insert(pool.begin() + pos, {id, d});
      }
    };
    insert(static_cast<uint32_t>(gh_.entry), dist(static_cast<uint32_t>(gh_.entry)), 0);
    uint64_t nexpanded = 0;
    while (true) {
      std::vector<uint32_t> batch;
      for (const auto &c : pool) {
        if (!expanded.count(c.id)) batch.push_back(c.id);
        if (batch.size() == cfg_.width) break;
      }
      if (batch.empty()) break;
      for (uint32_t id : batch) {
        expanded.insert(id);
        ++nexpanded;
        uint64_t page_id = static_cast<uint64_t>(id) / gh_.nodes_per_page;
        uint64_t slot = id % gh_.nodes_per_page;
        const char *rec = graph_memory_.data() + (1 + page_id) * SECTOR_LEN + slot * gh_.record_bytes;
        uint32_t degree = 0;
        std::memcpy(&degree, rec, sizeof(degree));
        const uint32_t *nbrs = reinterpret_cast<const uint32_t *>(rec + 4);
        for (uint32_t i = 0; i < degree; ++i) insert(nbrs[i], dist(nbrs[i]), nexpanded);
      }
    }
    OraclePlan plan;
    size_t target = std::min<size_t>(cfg_.k + cfg_.batch, pool.size());
    for (size_t i = 0; i < target; ++i) {
      plan.final_ids.push_back(pool[i].id);
      plan.earliest_safe_expanded = std::max(plan.earliest_safe_expanded, first_discovery.at(pool[i].id));
    }
    return plan;
  }
};

void write_header(std::ostream &out) {
  out << "qid,mode,K,L,width,B,vector_quota,total_us,traversal_us,exposed_vector_tail_us,pq_cpu_us,exact_cpu_us,"
         "graph_io_wait_us,vector_io_wait_us,graph_ios,vector_ios,expanded,discovered,heap_replacements,"
         "heap_full_expanded,stability_expanded,stability_us,stability_position,trigger_remaining_fraction,"
         "io_poll_rounds,prefetched_candidates,"
         "useful_prefetched_candidates,wasted_prefetch_candidates,unfinished_vector_pages_at_traversal_end,"
         "ready_vector_pages_at_traversal_end,prefetch_overlap_us,final_no_replace_streak,rerank_batches,"
         "prefetch_benefit_ratio,oracle_earliest_safe_expanded,oracle_final_set_match,recall\n";
}

void write_stats(std::ostream &out, const Config &c, const Stats &s) {
  out << s.qid << ',' << c.mode << ',' << c.k << ',' << c.l << ',' << c.width << ',' << c.batch << ','
      << c.vector_quota << ','
      << std::fixed << std::setprecision(3) << s.total_us << ',' << s.traversal_us << ','
      << s.exposed_vector_tail_us << ',' << s.pq_cpu_us << ',' << s.exact_cpu_us << ',' << s.graph_io_wait_us
      << ',' << s.vector_io_wait_us << ',' << s.graph_ios << ',' << s.vector_ios << ',' << s.expanded << ','
      << s.discovered << ',' << s.heap_replacements << ',' << s.heap_full_expanded << ',' << s.stability_expanded << ','
      << s.stability_us << ',' << s.stability_position << ',' << s.trigger_remaining_fraction << ','
      << s.io_poll_rounds << ',' << s.prefetched_candidates << ','
      << s.useful_prefetched_candidates << ',' << s.wasted_prefetch_candidates << ','
      << s.unfinished_vector_pages_at_traversal_end << ',' << s.ready_vector_pages_at_traversal_end << ','
      << s.prefetch_overlap_us << ',' << s.final_no_replace_streak << ',' << s.rerank_batches << ','
      << s.prefetch_benefit_ratio << ',' << s.oracle_earliest_safe_expanded << ',' << s.oracle_final_set_match << ','
      << s.recall << '\n';
}

}  // namespace

int main(int argc, char **argv) {
  try {
    Config cfg = parse_args(argc, argv);
    float *queries = nullptr;
    uint32_t *truth = nullptr;
    float *truth_dists = nullptr;
    size_t nq = 0, dim = 0, ngt = 0, gt_dim = 0;
    pipeann::load_bin<float>(cfg.query_path, queries, nq, dim);
    pipeann::load_truthset(cfg.truth_path, truth, truth_dists, ngt, gt_dim);
    if (nq != ngt) throw std::runtime_error("query/truth count mismatch");
    uint32_t begin = std::min<uint32_t>(cfg.query_start, nq);
    uint32_t end = cfg.query_limit ? std::min<uint32_t>(nq, begin + cfg.query_limit) : nq;
    std::ofstream out(cfg.output_path);
    if (!out) throw std::runtime_error("cannot open output");
    out.setf(std::ios::unitbuf);
    write_header(out);
    Searcher searcher(cfg);
    for (uint32_t qid = begin; qid < end; ++qid) {
      if ((qid - begin) % 100 == 0) std::cerr << "begin_qid=" << qid << '\n';
      Stats s = searcher.run(qid, queries + static_cast<uint64_t>(qid) * dim,
                             truth + static_cast<uint64_t>(qid) * gt_dim, gt_dim);
      write_stats(out, cfg, s);
      if ((qid - begin + 1) % 100 == 0) {
        out.flush();
        std::cerr << "queries=" << (qid - begin + 1) << '/' << (end - begin) << '\n';
      }
    }
    delete[] queries;
    delete[] truth;
    delete[] truth_dists;
  } catch (const std::exception &e) {
    std::cerr << "ERROR: " << e.what() << '\n';
    return 2;
  }
  return 0;
}
