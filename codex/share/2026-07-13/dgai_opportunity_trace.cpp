#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <set>
#include <string>
#include <vector>

#include "distance.h"
#include "linux_aligned_file_reader.h"
#include "parameters.h"
#include "percentile_stats.h"
#include "ssd_index.h"
#include "utils.h"

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

void json_heap_events(std::ostream &out, const std::vector<pipeann::QueryTraceEvent> &events) {
  out << '[';
  for (size_t i = 0; i < events.size(); ++i) {
    if (i) out << ',';
    const auto &event = events[i];
    out << "{\"s\":" << event.sequence << ",\"t\":\""
        << (event.type == pipeann::QueryTraceEventType::kHeapPush ? "push" : "expand")
        << "\",\"n\":" << event.node_id << ",\"d\":" << event.distance << '}';
  }
  out << ']';
}

double percentile(std::vector<double> values, double fraction) {
  if (values.empty()) return 0;
  std::sort(values.begin(), values.end());
  size_t pos = static_cast<size_t>(fraction * static_cast<double>(values.size() - 1));
  return values[pos];
}

double recall_at_k(const uint32_t *ground_truth, size_t gt_dim, uint64_t active_points,
                   const std::vector<uint32_t> &results, size_t k) {
  std::set<uint32_t> expected;
  for (size_t i = 0; i < gt_dim && expected.size() < k; ++i) {
    if (ground_truth[i] < active_points) expected.insert(ground_truth[i]);
  }
  if (expected.empty()) return -1;
  size_t hits = 0;
  for (uint32_t result : results) hits += expected.count(result);
  return static_cast<double>(hits) / static_cast<double>(expected.size());
}

template <typename T>
int run(const std::string &index_prefix, const std::string &query_path, const std::string &truth_path,
        const std::string &output_path, size_t query_limit, size_t k, size_t search_l,
        size_t beam_width, int strategy) {
  T *queries = nullptr;
  size_t query_count = 0, query_dim = 0;
  pipeann::load_bin<T>(query_path, queries, query_count, query_dim);
  query_limit = std::min(query_limit, query_count);

  uint32_t *gt_ids = nullptr;
  float *gt_dists = nullptr;
  size_t gt_count = 0, gt_dim = 0;
  pipeann::load_truthset(truth_path, gt_ids, gt_dists, gt_count, gt_dim);
  if (gt_count != query_count) {
    std::cerr << "query/ground-truth count mismatch\n";
    return 2;
  }

  std::shared_ptr<AlignedFileReader> reader(new LinuxAlignedFileReader());
  static_cast<LinuxAlignedFileReader *>(reader.get())->strategy = strategy;
  pipeann::Parameters parameters;
  parameters.Set<unsigned>("L", static_cast<unsigned>(search_l));
  parameters.Set<unsigned>("R", 64);
  parameters.Set<unsigned>("C", 160);
  parameters.Set<float>("alpha", 1.2f);
  parameters.Set<unsigned>("beamwidth", static_cast<unsigned>(beam_width));
  parameters.Set<bool>("saturate_graph", false);
  pipeann::SSDIndex<T, uint32_t> index(pipeann::Metric::L2, reader, false, true, &parameters);
  int load_status = index.load(index_prefix.c_str(), 1, true, false);
  if (load_status != 0) return load_status;

  // Warm the code path but leave the formal trace cold with respect to any
  // persistent application cache (strategy must keep DGAI's block cache off).
  std::vector<uint32_t> warm_tags(k);
  std::vector<float> warm_dists(k);
  pipeann::QueryStats warm_stats;
  index.rerank_search(queries, k, 0, search_l, warm_tags.data(), warm_dists.data(), beam_width, &warm_stats);

  std::ofstream out(output_path);
  if (!out) {
    std::cerr << "cannot open output: " << output_path << '\n';
    return 3;
  }
  out << std::setprecision(9);
  std::vector<double> latencies;
  std::vector<double> recalls;
  uint64_t trace_topology_requests = 0, stat_topology_requests = 0;
  uint64_t trace_coord_candidates = 0, stat_coord_candidates = 0;

  for (size_t qid = 0; qid < query_limit; ++qid) {
    std::vector<uint32_t> tags(k, std::numeric_limits<uint32_t>::max());
    std::vector<float> distances(k, std::numeric_limits<float>::max());
    pipeann::QueryTrace trace;
    pipeann::QueryStats stats;
    stats.trace = &trace;
    index.rerank_search(queries + qid * query_dim, k, 0, search_l, tags.data(), distances.data(),
                        beam_width, &stats);
    double recall = recall_at_k(gt_ids + qid * gt_dim, gt_dim, index.num_points, tags, k);
    latencies.push_back(stats.total_us);
    recalls.push_back(recall);
    trace_topology_requests += trace.topology_requested_nodes.size();
    stat_topology_requests += stats.search_topology_logical_pages;
    trace_coord_candidates += trace.rerank_candidate_nodes.size();
    stat_coord_candidates += stats.coord_unique_vectors;

    out << "{\"schema\":\"dgai-opportunity-query-v1\",\"qid\":" << qid
        << ",\"latency_us\":" << stats.total_us << ",\"recall_at_" << k << "\":" << recall
        << ",\"topology_logical_reads\":" << stats.search_topology_logical_pages
        << ",\"topology_unique_pages\":" << stats.search_topology_unique_pages
        << ",\"topology_submitted_bytes\":" << stats.search_topology_submitted_bytes
        << ",\"vector_logical_reads\":" << stats.coord_unique_vectors
        << ",\"vector_unique_pages\":" << stats.coord_unique_pages
        << ",\"vector_submitted_bytes\":" << stats.coord_submitted_bytes
        << ",\"expanded_count\":" << stats.search_expanded_nodes
        << ",\"result_tags\":";
    json_array(out, tags);
    out << ",\"topology_nodes\":";
    json_array(out, trace.topology_requested_nodes);
    out << ",\"topology_pages\":";
    json_array(out, trace.topology_requested_pages);
    out << ",\"expanded_nodes\":";
    json_array(out, trace.expanded_nodes);
    out << ",\"rerank_nodes\":";
    json_array(out, trace.rerank_candidate_nodes);
    out << ",\"rerank_pages\":";
    json_array(out, trace.rerank_candidate_pages);
    out << ",\"heap_events\":";
    json_heap_events(out, trace.heap_events);
    out << "}\n";
  }

  double recall_sum = 0;
  for (double value : recalls) recall_sum += value;
  bool consistent = trace_topology_requests == stat_topology_requests &&
                    trace_coord_candidates == stat_coord_candidates;
  std::cout << std::setprecision(9)
            << "{\"schema\":\"dgai-opportunity-summary-v1\",\"queries\":" << query_limit
            << ",\"active_points\":" << index.num_points
            << ",\"mean_recall\":" << (recalls.empty() ? 0 : recall_sum / recalls.size())
            << ",\"latency_p50_us\":" << percentile(latencies, 0.50)
            << ",\"latency_p95_us\":" << percentile(latencies, 0.95)
            << ",\"latency_p99_us\":" << percentile(latencies, 0.99)
            << ",\"trace_topology_requests\":" << trace_topology_requests
            << ",\"stat_topology_requests\":" << stat_topology_requests
            << ",\"trace_coord_candidates\":" << trace_coord_candidates
            << ",\"stat_coord_candidates\":" << stat_coord_candidates
            << ",\"trace_consistent\":" << (consistent ? "true" : "false") << "}\n";

  delete[] queries;
  delete[] gt_ids;
  delete[] gt_dists;
  return consistent ? 0 : 4;
}

}  // namespace

int main(int argc, char **argv) {
  if (argc != 11 || std::string(argv[1]) != "float") {
    std::cerr << "Usage: " << argv[0]
              << " float <index_prefix> <query.bin> <groundtruth.bin> <trace.jsonl>"
                 " <query_count> <k> <L> <beam_width> <strategy>\n";
    return 1;
  }
  return run<float>(argv[2], argv[3], argv[4], argv[5], std::stoull(argv[6]), std::stoull(argv[7]),
                    std::stoull(argv[8]), std::stoull(argv[9]), std::stoi(argv[10]));
}
