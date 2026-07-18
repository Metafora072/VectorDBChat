#pragma once

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <map>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace atlas_m2 {

struct LayoutConfig {
  std::string system;
  std::string execution_engine;
  uint64_t R = 0;
  uint64_t L = 0;
  uint64_t candidate_limit = 0;
  uint64_t beam_width = 0;
  double alpha = 0;
  uint64_t data_dim = 0;
  uint64_t record_bytes = 0;
  uint64_t records_per_4k_page = 0;
  uint64_t attr_bytes = 0;
};

struct Replacement {
  uint64_t reverse_attempts = 0;
  uint64_t accepted_reverse_updates = 0;
  uint64_t pruned_or_rejected_updates = 0;
  uint64_t mutated_neighbor_records = 0;
  uint64_t distinct_mutated_neighbor_ids = 0;
  std::vector<uint64_t> logical_neighbor_pages;
  std::vector<uint64_t> logical_neighbor_only_pages;
  bool target_page_shared = false;
  std::vector<uint64_t> submitted_neighbor_only_pages;
};

class Collector {
 public:
  Collector() {
    const char *path = std::getenv("ATLAS_M2_LOGICAL_OUTPUT");
    if (path && *path) {
      output_ = path;
      enabled_ = true;
    }
  }

  ~Collector() { write_once(); }
  Collector(const Collector &) = delete;
  Collector &operator=(const Collector &) = delete;

  void configure(const LayoutConfig &config) {
    if (!enabled_) return;
    std::lock_guard<std::mutex> lock(mu_);
    if (!configured_) {
      config_ = config;
      configured_ = true;
      return;
    }
    if (config_.system != config.system || config_.execution_engine != config.execution_engine ||
        config_.R != config.R || config_.L != config.L || config_.candidate_limit != config.candidate_limit ||
        config_.beam_width != config.beam_width || config_.alpha != config.alpha ||
        config_.data_dim != config.data_dim || config_.record_bytes != config.record_bytes ||
        config_.records_per_4k_page != config.records_per_4k_page || config_.attr_bytes != config.attr_bytes) {
      ++configuration_mismatch_count_;
    }
  }

  void record(const Replacement &r) {
    if (!enabled_) return;
    std::lock_guard<std::mutex> lock(mu_);
    ++replacement_count_;
    add_hist("reverse_edge_repair_attempts", r.reverse_attempts);
    add_hist("accepted_reverse_edge_updates", r.accepted_reverse_updates);
    add_hist("pruned_or_rejected_updates", r.pruned_or_rejected_updates);
    add_hist("mutated_neighbor_node_records", r.mutated_neighbor_records);
    add_hist("distinct_mutated_neighbor_node_ids", r.distinct_mutated_neighbor_ids);
    add_hist("distinct_neighbor_page_ids_before_submission", r.logical_neighbor_pages.size());
    add_hist("distinct_neighbor_only_page_ids_before_submission", r.logical_neighbor_only_pages.size());
    add_hist("target_page_shared_with_neighbor", r.target_page_shared ? 1 : 0);
    add_hist("submitted_neighbor_only_4k_page_writes", r.submitted_neighbor_only_pages.size());

    reverse_attempts_total_ += r.reverse_attempts;
    accepted_total_ += r.accepted_reverse_updates;
    rejected_total_ += r.pruned_or_rejected_updates;
    mutated_total_ += r.mutated_neighbor_records;
    distinct_mutated_total_ += r.distinct_mutated_neighbor_ids;
    logical_page_events_ += r.logical_neighbor_pages.size();
    logical_neighbor_only_page_events_ += r.logical_neighbor_only_pages.size();
    submitted_neighbor_only_page_touches_ += r.submitted_neighbor_only_pages.size();
    target_shared_count_ += r.target_page_shared ? 1 : 0;

    for (uint64_t page : r.logical_neighbor_pages) ++logical_page_touches_[page];
    for (uint64_t page : r.logical_neighbor_only_pages) ++logical_neighbor_only_page_touches_[page];
    for (uint64_t page : r.submitted_neighbor_only_pages) ++submitted_neighbor_only_page_touches_by_page_[page];

    std::vector<uint64_t> logical = r.logical_neighbor_only_pages;
    std::vector<uint64_t> submitted = r.submitted_neighbor_only_pages;
    std::sort(logical.begin(), logical.end());
    std::sort(submitted.begin(), submitted.end());
    if (logical != submitted) ++operation_closure_mismatch_count_;
    if (r.reverse_attempts != r.accepted_reverse_updates + r.pruned_or_rejected_updates)
      ++fanout_identity_mismatch_count_;
  }

  void write_once() noexcept {
    if (!enabled_ || written_.exchange(true)) return;
    try {
      std::lock_guard<std::mutex> lock(mu_);
      std::ofstream out(output_ + ".tmp", std::ios::trunc);
      if (!out) throw std::runtime_error("cannot open M2 logical output");
      out << "{\n  \"schema\": \"dynamic-vamana-neighbor-repair-m2-logical-v1\",\n";
      out << "  \"status\": \"" << (configured_ ? "complete" : "not-configured") << "\",\n";
      out << "  \"config\": {\n";
      out << "    \"system\": \"" << config_.system << "\",\n";
      out << "    \"execution_engine\": \"" << config_.execution_engine << "\",\n";
      out << "    \"R\": " << config_.R << ", \"L\": " << config_.L
          << ", \"candidate_limit\": " << config_.candidate_limit << ", \"beam_width\": " << config_.beam_width
          << ", \"alpha\": " << std::setprecision(9) << config_.alpha << ",\n";
      out << "    \"data_dim\": " << config_.data_dim << ", \"record_bytes\": " << config_.record_bytes
          << ", \"records_per_4k_page\": " << config_.records_per_4k_page
          << ", \"attr_bytes\": " << config_.attr_bytes << "\n  },\n";
      out << "  \"totals\": {\n";
      out << "    \"replacements\": " << replacement_count_ << ",\n";
      out << "    \"reverse_edge_repair_attempts\": " << reverse_attempts_total_ << ",\n";
      out << "    \"accepted_reverse_edge_updates\": " << accepted_total_ << ",\n";
      out << "    \"pruned_or_rejected_updates\": " << rejected_total_ << ",\n";
      out << "    \"mutated_neighbor_node_records\": " << mutated_total_ << ",\n";
      out << "    \"distinct_mutated_neighbor_node_ids_operation_sum\": " << distinct_mutated_total_ << ",\n";
      out << "    \"neighbor_logical_page_events\": " << logical_page_events_ << ",\n";
      out << "    \"neighbor_only_logical_page_events\": " << logical_neighbor_only_page_events_ << ",\n";
      out << "    \"neighbor_only_submitted_page_touches\": " << submitted_neighbor_only_page_touches_ << ",\n";
      out << "    \"stage_unique_neighbor_pages\": " << logical_page_touches_.size() << ",\n";
      out << "    \"stage_unique_neighbor_only_pages\": " << submitted_neighbor_only_page_touches_by_page_.size() << ",\n";
      out << "    \"target_page_shared_operations\": " << target_shared_count_ << "\n  },\n";
      out << "  \"closure\": {\n";
      out << "    \"operation_page_set_mismatch_count\": " << operation_closure_mismatch_count_ << ",\n";
      out << "    \"fanout_identity_mismatch_count\": " << fanout_identity_mismatch_count_ << ",\n";
      out << "    \"configuration_mismatch_count\": " << configuration_mismatch_count_ << ",\n";
      out << "    \"logical_neighbor_only_events_equal_submitted_touches\": "
          << (logical_neighbor_only_page_events_ == submitted_neighbor_only_page_touches_ ? "true" : "false") << "\n  },\n";
      out << "  \"operation_histograms\": "; write_nested_hist(out, operation_histograms_); out << ",\n";
      out << "  \"page_touch_frequency\": {\n";
      out << "    \"logical_neighbor_pages\": "; write_hist(out, frequency_hist(logical_page_touches_)); out << ",\n";
      out << "    \"logical_neighbor_only_pages\": "; write_hist(out, frequency_hist(logical_neighbor_only_page_touches_)); out << ",\n";
      out << "    \"submitted_neighbor_only_pages\": "; write_hist(out, frequency_hist(submitted_neighbor_only_page_touches_by_page_)); out << "\n  },\n";
      auto hot = hottest(submitted_neighbor_only_page_touches_by_page_);
      out << "  \"hottest_submitted_neighbor_only_page\": {\"touch_count\": " << hot.first
          << ", \"touch_fraction\": " << std::setprecision(17)
          << (submitted_neighbor_only_page_touches_ ? static_cast<double>(hot.first) / submitted_neighbor_only_page_touches_ : 0.0)
          << "}\n}\n";
      out.close();
      if (!out) throw std::runtime_error("failed writing M2 logical output");
      if (std::rename((output_ + ".tmp").c_str(), output_.c_str()) != 0)
        throw std::runtime_error("failed renaming M2 logical output");
    } catch (...) {
      // The formal runner requires the output and will fail closed.
    }
  }

  static Collector &instance() {
    static Collector collector;
    return collector;
  }

 private:
  void add_hist(const std::string &name, uint64_t value) { ++operation_histograms_[name][value]; }

  static std::map<uint64_t, uint64_t> frequency_hist(const std::unordered_map<uint64_t, uint64_t> &pages) {
    std::map<uint64_t, uint64_t> out;
    for (const auto &item : pages) ++out[item.second];
    return out;
  }

  static std::pair<uint64_t, uint64_t> hottest(const std::unordered_map<uint64_t, uint64_t> &pages) {
    std::pair<uint64_t, uint64_t> out{0, 0};
    for (const auto &item : pages) if (item.second > out.first) out = {item.second, item.first};
    return out;
  }

  static void write_hist(std::ostream &out, const std::map<uint64_t, uint64_t> &hist) {
    out << "{"; bool first = true;
    for (const auto &item : hist) { if (!first) out << ","; first = false; out << "\"" << item.first << "\":" << item.second; }
    out << "}";
  }

  static void write_nested_hist(std::ostream &out, const std::map<std::string, std::map<uint64_t, uint64_t>> &hists) {
    out << "{"; bool first = true;
    for (const auto &item : hists) { if (!first) out << ","; first = false; out << "\n    \"" << item.first << "\": "; write_hist(out, item.second); }
    if (!hists.empty()) out << "\n  ";
    out << "}";
  }

  bool enabled_ = false;
  bool configured_ = false;
  std::atomic<bool> written_{false};
  std::string output_;
  std::mutex mu_;
  LayoutConfig config_;
  uint64_t replacement_count_ = 0;
  uint64_t reverse_attempts_total_ = 0;
  uint64_t accepted_total_ = 0;
  uint64_t rejected_total_ = 0;
  uint64_t mutated_total_ = 0;
  uint64_t distinct_mutated_total_ = 0;
  uint64_t logical_page_events_ = 0;
  uint64_t logical_neighbor_only_page_events_ = 0;
  uint64_t submitted_neighbor_only_page_touches_ = 0;
  uint64_t target_shared_count_ = 0;
  uint64_t operation_closure_mismatch_count_ = 0;
  uint64_t fanout_identity_mismatch_count_ = 0;
  uint64_t configuration_mismatch_count_ = 0;
  std::map<std::string, std::map<uint64_t, uint64_t>> operation_histograms_;
  std::unordered_map<uint64_t, uint64_t> logical_page_touches_;
  std::unordered_map<uint64_t, uint64_t> logical_neighbor_only_page_touches_;
  std::unordered_map<uint64_t, uint64_t> submitted_neighbor_only_page_touches_by_page_;
};

inline void configure(const LayoutConfig &config) { Collector::instance().configure(config); }
inline void record(const Replacement &replacement) { Collector::instance().record(replacement); }
inline void write_once() { Collector::instance().write_once(); }

}  // namespace atlas_m2
