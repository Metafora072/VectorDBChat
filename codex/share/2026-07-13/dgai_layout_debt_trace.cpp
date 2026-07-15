#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <set>
#include <string>
#include <vector>

#include "distance.h"
#include "parameters.h"
#include "percentile_stats.h"
#include "utils.h"
#include "v2/dynamic_index.h"

namespace {

template <typename T>
void json_array(std::ostream &out, const std::vector<T> &values) {
  out << '[';
  for (size_t i = 0; i < values.size(); ++i) {
    if (i) out << ',';
    out << values[i];
  }
  out << ']';
}

double recall_at_k(const uint32_t *ground_truth, size_t gt_dim, uint64_t active_tag_limit,
                   const std::vector<uint32_t> &results, size_t k) {
  std::set<uint32_t> expected;
  for (size_t i = 0; i < gt_dim && expected.size() < k; ++i) {
    if (ground_truth[i] < active_tag_limit) expected.insert(ground_truth[i]);
  }
  size_t hits = 0;
  for (uint32_t result : results) hits += expected.count(result);
  return expected.empty() ? -1 : static_cast<double>(hits) / expected.size();
}

template <typename T>
int run(const std::string &index_prefix, const std::string &base_path, const std::string &query_path,
        const std::string &truth_path, const std::string &output_prefix, size_t query_limit,
        size_t max_operation_percent, size_t k, size_t search_l, size_t beam_width,
        size_t delete_threads, uint64_t seed, int strategy, size_t refresh_override,
        const std::string &id_mode) {
  T *base = nullptr, *queries = nullptr;
  size_t base_count = 0, base_dim = 0, query_count = 0, query_dim = 0;
  pipeann::load_bin<T>(base_path, base, base_count, base_dim);
  pipeann::load_bin<T>(query_path, queries, query_count, query_dim);
  uint32_t *gt_ids = nullptr;
  float *gt_dists = nullptr;
  size_t gt_count = 0, gt_dim = 0;
  pipeann::load_truthset(truth_path, gt_ids, gt_dists, gt_count, gt_dim);
  if (query_dim != base_dim || gt_count != query_count) return 2;
  query_limit = std::min(query_limit, query_count);

  pipeann::Parameters parameters;
  parameters.Set<unsigned>("L_disk", static_cast<unsigned>(search_l));
  parameters.Set<unsigned>("R_disk", 64);
  parameters.Set<float>("alpha_disk", 1.2f);
  parameters.Set<unsigned>("C", 384);
  parameters.Set<unsigned>("beamwidth", static_cast<unsigned>(beam_width));
  parameters.Set<unsigned>("nodes_to_cache", 0);
  parameters.Set<unsigned>("num_threads", static_cast<unsigned>(std::max<size_t>(delete_threads, 1)));
  pipeann::DistanceL2 distance;
  pipeann::DynamicSSDIndex<T, uint32_t> index(parameters, index_prefix, index_prefix, &distance,
                                               pipeann::Metric::L2, RERANK_SEARCH, false, strategy);
  const uint64_t initial_points = index._disk_index->num_points;
  if (base_count < initial_points) return 3;

  std::vector<uint32_t> refresh_ids(initial_points);
  std::mt19937_64 rng(seed);
  size_t max_refresh = refresh_override ? refresh_override : initial_points * max_operation_percent / 200;
  if (id_mode == "clustered_gt") {
    refresh_ids.clear();
    std::vector<uint8_t> seen(initial_points, 0);
    const size_t clustered_queries = std::min<size_t>(gt_count, 1500);
    for (size_t qid = 0; qid < clustered_queries && refresh_ids.size() < max_refresh; ++qid) {
      for (size_t j = 0; j < gt_dim && refresh_ids.size() < max_refresh; ++j) {
        uint32_t id = gt_ids[qid * gt_dim + j];
        if (id < initial_points && !seen[id]) {
          seen[id] = 1;
          refresh_ids.push_back(id);
        }
      }
    }
    if (refresh_ids.size() < max_refresh) {
      std::vector<uint32_t> remainder;
      remainder.reserve(initial_points - refresh_ids.size());
      for (uint32_t id = 0; id < initial_points; ++id) if (!seen[id]) remainder.push_back(id);
      std::shuffle(remainder.begin(), remainder.end(), rng);
      refresh_ids.insert(refresh_ids.end(), remainder.begin(),
                         remainder.begin() + static_cast<std::ptrdiff_t>(max_refresh - refresh_ids.size()));
    }
  } else {
    std::iota(refresh_ids.begin(), refresh_ids.end(), 0);
    std::shuffle(refresh_ids.begin(), refresh_ids.end(), rng);
  }
  if (max_refresh > refresh_ids.size()) return 4;

  std::ofstream trace_out(output_prefix + ".jsonl");
  std::ofstream layout_out(output_prefix + "_layout.csv");
  if (!trace_out || !layout_out) return 5;
  trace_out << std::setprecision(9);
  layout_out << "checkpoint_percent,internal_id,tag,topology_location,vector_location\n";

  auto snapshot = [&](size_t checkpoint) {
    uint64_t active = 0;
    const uint64_t max_id = index._disk_index->cur_id.load();
    for (uint64_t internal = 0; internal < max_id; ++internal) {
      uint32_t topo_loc = 0, coord_loc = 0;
      if (!index._disk_index->measurement_locations(static_cast<uint32_t>(internal), topo_loc, coord_loc)) continue;
      layout_out << checkpoint << ',' << internal << ',' << index._disk_index->id2tag(internal) << ','
                 << topo_loc << ',' << coord_loc << '\n';
      active++;
    }

    double recall_sum = 0;
    for (size_t qid = 0; qid < query_limit; ++qid) {
      std::vector<uint32_t> tags(k, std::numeric_limits<uint32_t>::max());
      std::vector<float> distances(k, std::numeric_limits<float>::max());
      pipeann::QueryTrace trace;
      pipeann::QueryStats stats;
      stats.trace = &trace;
      index.search(queries + qid * query_dim, k, 0, search_l, beam_width, tags.data(), distances.data(), &stats, true);
      double recall = recall_at_k(gt_ids + qid * gt_dim, gt_dim, initial_points, tags, k);
      recall_sum += recall;
      trace_out << "{\"schema\":\"dgai-layout-debt-query-v1\",\"checkpoint_percent\":" << checkpoint
                << ",\"qid\":" << qid << ",\"latency_us\":" << stats.total_us
                << ",\"recall_at_" << k << "\":" << recall
                << ",\"topology_logical_reads\":" << stats.search_topology_logical_pages
                << ",\"topology_unique_pages\":" << stats.search_topology_unique_pages
                << ",\"vector_logical_reads\":" << stats.coord_unique_vectors
                << ",\"vector_unique_pages\":" << stats.coord_unique_pages
                << ",\"result_tags\":";
      json_array(trace_out, tags);
      trace_out << ",\"topology_nodes\":";
      json_array(trace_out, trace.topology_requested_nodes);
      trace_out << ",\"topology_pages\":";
      json_array(trace_out, trace.topology_requested_pages);
      trace_out << ",\"expanded_nodes\":";
      json_array(trace_out, trace.expanded_nodes);
      trace_out << ",\"rerank_nodes\":";
      json_array(trace_out, trace.rerank_candidate_nodes);
      trace_out << ",\"rerank_pages\":";
      json_array(trace_out, trace.rerank_candidate_pages);
      trace_out << "}\n";
    }
    trace_out.flush();
    layout_out.flush();
    std::cerr << "$LAYOUT_DEBT_CHECKPOINT,percent=" << checkpoint << ",active_records=" << active
              << ",max_internal_id=" << max_id << ",mean_recall=" << recall_sum / query_limit << "\n";
  };

  snapshot(0);
  size_t refreshed = 0;
  for (size_t checkpoint : {size_t{1}, size_t{5}, size_t{10}, size_t{20}}) {
    if (checkpoint > max_operation_percent) break;
    const size_t target_refresh = refresh_override ? refresh_override : initial_points * checkpoint / 200;
    const auto start = std::chrono::steady_clock::now();
    for (size_t i = refreshed; i < target_refresh; ++i) index.lazy_delete(refresh_ids[i]);
    index.trigger_deletion(static_cast<uint32_t>(delete_threads), 20);
    size_t failures = 0;
    for (size_t i = refreshed; i < target_refresh; ++i) {
      uint32_t tag = refresh_ids[i];
      if (index.insert(base + static_cast<size_t>(tag) * base_dim, tag) < 0) failures++;
    }
    const auto end = std::chrono::steady_clock::now();
    std::cerr << "$LAYOUT_DEBT_UPDATE,percent=" << checkpoint << ",new_refreshes="
              << target_refresh - refreshed << ",cumulative_refreshes=" << target_refresh
              << ",failures=" << failures << ",wall_s="
              << std::chrono::duration<double>(end - start).count() << "\n";
    if (failures) return 6;
    refreshed = target_refresh;
    snapshot(checkpoint);
    if (refresh_override) break;
  }

  delete[] base;
  delete[] queries;
  delete[] gt_ids;
  delete[] gt_dists;
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  if (argc != 17 || std::string(argv[1]) != "float") {
    std::cerr << "Usage: " << argv[0]
              << " float <index_prefix> <base.bin> <query.bin> <groundtruth.bin> <output_prefix>"
                 " <query_count> <max_operation_percent> <k> <L> <beam_width> <delete_threads> <seed> <strategy>"
                 " <refresh_override_or_0> <uniform|clustered_gt>\n";
    return 1;
  }
  return run<float>(argv[2], argv[3], argv[4], argv[5], argv[6], std::stoull(argv[7]),
                    std::stoull(argv[8]), std::stoull(argv[9]), std::stoull(argv[10]),
                    std::stoull(argv[11]), std::stoull(argv[12]), std::stoull(argv[13]), std::stoi(argv[14]),
                    std::stoull(argv[15]), argv[16]);
}
