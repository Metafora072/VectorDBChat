#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <omp.h>

#include "distance.h"
#include "parameters.h"
#include "percentile_stats.h"
#include "utils.h"
#include "v2/dynamic_index.h"

namespace {

std::vector<size_t> parse_sizes(const std::string &text) {
  std::vector<size_t> values;
  std::stringstream stream(text);
  std::string item;
  while (std::getline(stream, item, ',')) values.push_back(std::stoull(item));
  return values;
}

double percentile(std::vector<double> values, double fraction) {
  if (values.empty()) return 0;
  std::sort(values.begin(), values.end());
  const size_t pos = std::min(values.size() - 1, static_cast<size_t>(fraction * values.size()));
  return values[pos];
}

std::set<uint32_t> expected_from_gt(const uint32_t *row, size_t gt_dim,
                                    const std::unordered_set<uint32_t> &active, size_t k) {
  std::set<uint32_t> expected;
  for (size_t i = 0; i < gt_dim && expected.size() < k; ++i) {
    if (active.count(row[i])) expected.insert(row[i]);
  }
  return expected;
}

double recall(const std::set<uint32_t> &expected, const std::vector<uint32_t> &results, size_t k) {
  if (expected.empty()) return -1;
  size_t hits = 0;
  for (size_t i = 0; i < std::min(k, results.size()); ++i) hits += expected.count(results[i]);
  return static_cast<double>(hits) / expected.size();
}

template <typename T>
std::vector<uint32_t> exact_topk(const T *base, size_t n, size_t dim, const T *query,
                                 const std::unordered_set<uint32_t> &active, size_t k) {
  const int threads = std::max(1, omp_get_max_threads());
  std::vector<std::vector<std::pair<float, uint32_t>>> local(threads);
#pragma omp parallel
  {
    const int tid = omp_get_thread_num();
    auto &best = local[tid];
    best.reserve(k + 1);
#pragma omp for schedule(static)
    for (size_t id = 0; id < n; ++id) {
      if (!active.count(static_cast<uint32_t>(id))) continue;
      float distance = 0;
#pragma omp simd reduction(+ : distance)
      for (size_t d = 0; d < dim; ++d) {
        const float delta = static_cast<float>(base[id * dim + d]) - static_cast<float>(query[d]);
        distance += delta * delta;
      }
      if (best.size() < k) {
        best.emplace_back(distance, static_cast<uint32_t>(id));
        if (best.size() == k) std::make_heap(best.begin(), best.end());
      } else if (std::make_pair(distance, static_cast<uint32_t>(id)) < best.front()) {
        std::pop_heap(best.begin(), best.end());
        best.back() = {distance, static_cast<uint32_t>(id)};
        std::push_heap(best.begin(), best.end());
      }
    }
  }
  std::vector<std::pair<float, uint32_t>> merged;
  for (const auto &part : local) merged.insert(merged.end(), part.begin(), part.end());
  std::sort(merged.begin(), merged.end());
  if (merged.size() > k) merged.resize(k);
  std::vector<uint32_t> ids;
  for (const auto &entry : merged) ids.push_back(entry.second);
  return ids;
}

struct TagAudit {
  uint64_t active_internal = 0;
  uint64_t unique_tags = 0;
  uint64_t duplicate_tags = 0;
  uint64_t expected_missing = 0;
  std::unordered_map<uint32_t, uint32_t> tag_to_internal;
  std::unordered_set<uint32_t> active_tags;
};

template <typename T>
TagAudit audit_tags(pipeann::DynamicSSDIndex<T, uint32_t> &index, uint64_t expected_tag_count) {
  TagAudit audit;
  const uint64_t max_id = index._disk_index->cur_id.load();
  audit.tag_to_internal.reserve(expected_tag_count);
  audit.active_tags.reserve(expected_tag_count);
  for (uint64_t id = 0; id < max_id; ++id) {
    uint32_t topo_loc = 0, coord_loc = 0;
    if (!index._disk_index->measurement_locations(static_cast<uint32_t>(id), topo_loc, coord_loc)) continue;
    const uint32_t tag = index._disk_index->id2tag(static_cast<uint32_t>(id));
    audit.active_internal++;
    if (!audit.active_tags.insert(tag).second) audit.duplicate_tags++;
    audit.tag_to_internal[tag] = static_cast<uint32_t>(id);
  }
  audit.unique_tags = audit.active_tags.size();
  for (uint32_t tag = 0; tag < expected_tag_count; ++tag) {
    if (!audit.active_tags.count(tag)) audit.expected_missing++;
  }
  return audit;
}

template <typename T>
void write_search_sweep(pipeann::DynamicSSDIndex<T, uint32_t> &index, const T *queries, size_t query_dim,
                        size_t query_limit, const uint32_t *gt, size_t gt_dim, const TagAudit &audit,
                        size_t checkpoint, size_t k, const std::vector<size_t> &search_ls,
                        const std::vector<size_t> &beams, const std::vector<size_t> &reranks,
                        std::ofstream &summary, std::ofstream &per_query) {
  for (size_t search_l : search_ls) {
    for (size_t beam : beams) {
      for (size_t rerank : reranks) {
        std::vector<double> recalls, latencies, ios;
        recalls.reserve(query_limit);
        latencies.reserve(query_limit);
        ios.reserve(query_limit);
        for (size_t qid = 0; qid < query_limit; ++qid) {
          const size_t result_count = std::max(k, rerank);
          std::vector<uint32_t> tags(result_count, std::numeric_limits<uint32_t>::max());
          std::vector<float> distances(result_count, std::numeric_limits<float>::max());
          pipeann::QueryStats stats;
          const size_t returned = index._disk_index->rerank_search(
              queries + qid * query_dim, result_count, 0, search_l, tags.data(), distances.data(), beam, &stats,
              &index.deletion_sets[index.active_delete_set]);
          tags.resize(returned);
          const auto expected = expected_from_gt(gt + qid * gt_dim, gt_dim, audit.active_tags, k);
          const double value = recall(expected, tags, k);
          recalls.push_back(value);
          latencies.push_back(stats.total_us);
          ios.push_back(stats.n_ios);
          per_query << checkpoint << ',' << qid << ',' << search_l << ',' << beam << ',' << rerank << ','
                    << value << ',' << stats.total_us << ',' << stats.n_ios << ',' << returned << '\n';
        }
        const double mean_recall = std::accumulate(recalls.begin(), recalls.end(), 0.0) / recalls.size();
        const double mean_latency = std::accumulate(latencies.begin(), latencies.end(), 0.0) / latencies.size();
        const double mean_ios = std::accumulate(ios.begin(), ios.end(), 0.0) / ios.size();
        summary << checkpoint << ',' << search_l << ',' << beam << ',' << rerank << ',' << query_limit << ','
                << mean_recall << ',' << mean_latency << ',' << percentile(latencies, 0.50) << ','
                << percentile(latencies, 0.95) << ',' << percentile(latencies, 0.99) << ',' << mean_ios << '\n';
        summary.flush();
        per_query.flush();
        std::cerr << "$G0_SEARCH,checkpoint=" << checkpoint << ",L=" << search_l << ",beam=" << beam
                  << ",rerank=" << rerank << ",recall=" << mean_recall << '\n';
      }
    }
  }
}

template <typename T>
int run(const std::string &index_prefix, const std::string &base_path, const std::string &query_path,
        const std::string &truth_path, const std::string &output_prefix, size_t query_limit,
        size_t max_operation_percent, size_t k, uint64_t seed, int strategy, const std::string &mode,
        size_t delete_threads, size_t sampled_neighbors, const std::string &id_mode, size_t exact_queries,
        const std::vector<size_t> &search_ls, const std::vector<size_t> &beams,
        const std::vector<size_t> &reranks) {
  T *base = nullptr, *queries = nullptr;
  size_t base_count = 0, base_dim = 0, query_count = 0, query_dim = 0;
  pipeann::load_bin<T>(base_path, base, base_count, base_dim);
  pipeann::load_bin<T>(query_path, queries, query_count, query_dim);
  uint32_t *gt = nullptr;
  float *gt_distances = nullptr;
  size_t gt_count = 0, gt_dim = 0;
  pipeann::load_truthset(truth_path, gt, gt_distances, gt_count, gt_dim);
  if (base_dim != query_dim || query_count != gt_count) return 2;
  query_limit = std::min(query_limit, query_count);

  pipeann::Parameters parameters;
  parameters.Set<unsigned>("L_disk", static_cast<unsigned>(*std::max_element(search_ls.begin(), search_ls.end())));
  parameters.Set<unsigned>("R_disk", 64);
  parameters.Set<float>("alpha_disk", 1.2f);
  parameters.Set<unsigned>("C", 384);
  parameters.Set<unsigned>("beamwidth", static_cast<unsigned>(*std::max_element(beams.begin(), beams.end())));
  parameters.Set<unsigned>("nodes_to_cache", 0);
  parameters.Set<unsigned>("num_threads", static_cast<unsigned>(std::max<size_t>(delete_threads, 1)));
  pipeann::DistanceL2 distance;
  pipeann::DynamicSSDIndex<T, uint32_t> index(parameters, index_prefix, index_prefix, &distance,
                                               pipeann::Metric::L2, RERANK_SEARCH, false, strategy);
  const uint64_t initial_points = index._disk_index->num_points;
  if (initial_points != base_count) return 3;

  std::ofstream audit_out(output_prefix + "_audit.csv");
  std::ofstream search_out(output_prefix + "_search_summary.csv");
  std::ofstream query_out(output_prefix + "_query.csv");
  std::ofstream exact_out(output_prefix + "_exact_gt.csv");
  std::ofstream refresh_out(output_prefix + "_refresh.csv");
  if (!audit_out || !search_out || !query_out || !exact_out || !refresh_out) return 4;
  audit_out << "checkpoint,active_internal,unique_tags,duplicate_tags,expected_missing,cur_id\n";
  search_out << "checkpoint,search_l,beam,rerank,queries,mean_recall,mean_latency_us,p50_latency_us,p95_latency_us,p99_latency_us,mean_ios\n";
  query_out << "checkpoint,qid,search_l,beam,rerank,recall,latency_us,ios,returned\n";
  exact_out << "qid,provided_gt_matches_exact,exact_tags,provided_tags\n";
  refresh_out << "checkpoint,tag,old_internal,new_internal,old_visible,vector_read_ok,vector_max_abs_error\n";
  audit_out << std::setprecision(12);
  search_out << std::setprecision(12);
  query_out << std::setprecision(12);

  TagAudit initial_audit = audit_tags(index, initial_points);
  for (size_t qid = 0; qid < std::min(exact_queries, query_limit); ++qid) {
    const auto exact = exact_topk(base, base_count, base_dim, queries + qid * query_dim,
                                  initial_audit.active_tags, k);
    const auto provided_set = expected_from_gt(gt + qid * gt_dim, gt_dim, initial_audit.active_tags, k);
    std::set<uint32_t> exact_set(exact.begin(), exact.end());
    exact_out << qid << ',' << (exact_set == provided_set ? 1 : 0) << ",\"";
    for (size_t i = 0; i < exact.size(); ++i) exact_out << (i ? ";" : "") << exact[i];
    exact_out << "\",\"";
    size_t pos = 0;
    for (uint32_t tag : provided_set) exact_out << (pos++ ? ";" : "") << tag;
    exact_out << "\"\n";
  }

  const size_t max_refresh = initial_points * max_operation_percent / 200;
  std::vector<uint32_t> refresh_ids;
  refresh_ids.reserve(max_refresh);
  std::mt19937_64 rng(seed);
  if (id_mode == "clustered_gt") {
    std::vector<uint8_t> seen(initial_points, 0);
    for (size_t qid = 0; qid < std::min<size_t>(gt_count, 1500) && refresh_ids.size() < max_refresh; ++qid) {
      for (size_t j = 0; j < gt_dim && refresh_ids.size() < max_refresh; ++j) {
        const uint32_t tag = gt[qid * gt_dim + j];
        if (tag < initial_points && !seen[tag]) {
          seen[tag] = 1;
          refresh_ids.push_back(tag);
        }
      }
    }
    std::vector<uint32_t> rest;
    for (uint32_t tag = 0; tag < initial_points; ++tag) if (!seen[tag]) rest.push_back(tag);
    std::shuffle(rest.begin(), rest.end(), rng);
    refresh_ids.insert(refresh_ids.end(), rest.begin(), rest.begin() + (max_refresh - refresh_ids.size()));
  } else {
    refresh_ids.resize(initial_points);
    std::iota(refresh_ids.begin(), refresh_ids.end(), 0);
    std::shuffle(refresh_ids.begin(), refresh_ids.end(), rng);
    refresh_ids.resize(max_refresh);
  }

  std::unordered_map<uint32_t, uint32_t> original_internal;
  original_internal.reserve(refresh_ids.size());
  for (uint32_t tag : refresh_ids) original_internal[tag] = initial_audit.tag_to_internal.at(tag);

  auto snapshot = [&](size_t checkpoint) {
    TagAudit audit = audit_tags(index, initial_points);
    audit_out << checkpoint << ',' << audit.active_internal << ',' << audit.unique_tags << ','
              << audit.duplicate_tags << ',' << audit.expected_missing << ',' << index._disk_index->cur_id.load()
              << '\n';
    audit_out.flush();
    write_search_sweep(index, queries, query_dim, query_limit, gt, gt_dim, audit, checkpoint, k,
                       search_ls, beams, reranks, search_out, query_out);
    std::cerr << "$G0_AUDIT,checkpoint=" << checkpoint << ",active=" << audit.active_internal
              << ",unique=" << audit.unique_tags << ",duplicates=" << audit.duplicate_tags
              << ",missing=" << audit.expected_missing << '\n';
  };

  snapshot(0);
  size_t refreshed = 0;
  for (size_t checkpoint : {size_t{1}, size_t{5}, size_t{10}, size_t{20}}) {
    if (checkpoint > max_operation_percent) break;
    const size_t target = initial_points * checkpoint / 200;
    if (mode == "refresh_same") {
      for (size_t i = refreshed; i < target; ++i) index.lazy_delete(refresh_ids[i]);
      index.trigger_deletion(static_cast<uint32_t>(delete_threads), static_cast<uint32_t>(sampled_neighbors));
      for (size_t i = refreshed; i < target; ++i) {
        const uint32_t tag = refresh_ids[i];
        if (index.insert(base + static_cast<size_t>(tag) * base_dim, tag) < 0) return 5;
      }
      TagAudit after = audit_tags(index, initial_points);
      const size_t sample_end = std::min(target, refreshed + size_t{1000});
      for (size_t i = refreshed; i < sample_end; ++i) {
        const uint32_t tag = refresh_ids[i];
        const uint32_t old_internal = original_internal.at(tag);
        const uint32_t new_internal = after.tag_to_internal.at(tag);
        uint32_t old_topo_loc = 0, old_coord_loc = 0;
        const bool old_visible = index._disk_index->measurement_locations(old_internal, old_topo_loc, old_coord_loc);
        std::vector<T> stored;
        const bool read_ok = index._disk_index->measurement_read_vector(new_internal, stored);
        double max_error = 0;
        if (read_ok) {
          for (size_t d = 0; d < base_dim; ++d) {
            max_error = std::max(max_error, std::abs(static_cast<double>(stored[d]) -
                                                     static_cast<double>(base[static_cast<size_t>(tag) * base_dim + d])));
          }
        }
        refresh_out << checkpoint << ',' << tag << ',' << old_internal << ',' << new_internal << ','
                    << (old_visible ? 1 : 0) << ',' << (read_ok ? 1 : 0) << ',' << max_error << '\n';
      }
      refreshed = target;
    } else if (mode != "noop") {
      return 6;
    }
    snapshot(checkpoint);
  }

  delete[] base;
  delete[] queries;
  delete[] gt;
  delete[] gt_distances;
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  if (argc != 20 || std::string(argv[1]) != "float") {
    std::cerr << "Usage: " << argv[0]
              << " float <index_prefix> <base.bin> <query.bin> <groundtruth.bin> <output_prefix>"
                 " <query_limit> <max_operation_percent> <k> <seed> <strategy> <noop|refresh_same>"
                 " <delete_threads> <sampled_neighbors> <uniform|clustered_gt> <exact_queries>"
                 " <L_csv> <beam_csv> <rerank_csv>\n";
    return 1;
  }
  return run<float>(argv[2], argv[3], argv[4], argv[5], argv[6], std::stoull(argv[7]),
                    std::stoull(argv[8]), std::stoull(argv[9]), std::stoull(argv[10]), std::stoi(argv[11]),
                    argv[12], std::stoull(argv[13]), std::stoull(argv[14]), argv[15], std::stoull(argv[16]),
                    parse_sizes(argv[17]), parse_sizes(argv[18]), parse_sizes(argv[19]));
}
