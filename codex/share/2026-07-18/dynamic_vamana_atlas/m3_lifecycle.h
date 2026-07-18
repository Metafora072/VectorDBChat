#pragma once

#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <map>
#include <mutex>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <unordered_map>
#include <utility>
#include <vector>

namespace atlas_m3 {

enum class Lifecycle : uint8_t { generated, queued, inflight, completed, barrier };

inline const char *classification(Lifecycle prior) {
  switch (prior) {
    case Lifecycle::generated: return "superseded_before_enqueue";
    case Lifecycle::queued: return "superseded_while_queued";
    case Lifecycle::inflight: return "superseded_while_inflight";
    case Lifecycle::completed: return "repeat_after_completion_before_barrier";
    case Lifecycle::barrier: return "repeat_after_barrier";
  }
  return "invalid";
}

struct VersionRef {
  uint64_t page = 0;
  uint64_t version = 0;
  uint64_t operation = 0;
  uint64_t batch = 0;
};

struct PageState {
  uint64_t version = 0;
  uint64_t operation = 0;
  uint64_t batch = 0;
  uint64_t later_while_inflight = 0;
  Lifecycle lifecycle = Lifecycle::generated;
};

class Collector {
 public:
  Collector() {
    const char *path = std::getenv("ATLAS_M3_LIFECYCLE_OUTPUT");
    if (path && *path) {
      output_ = path;
      enabled_ = true;
    }
  }
  ~Collector() { write_once(); }
  Collector(const Collector &) = delete;
  Collector &operator=(const Collector &) = delete;

  bool enabled() const { return enabled_; }

  void configure(const std::string &system, const std::string &engine, const std::string &path) {
    if (!enabled_) return;
    if (identity_ready_.load(std::memory_order_acquire)) return;
    struct stat st {};
    if (::stat(path.c_str(), &st) != 0) {
      std::lock_guard<std::mutex> lock(mu_);
      ++identity_errors_;
      return;
    }
    std::lock_guard<std::mutex> lock(mu_);
    if (!configured_) {
      system_ = system;
      engine_ = engine;
      path_ = path;
      device_ = static_cast<uint64_t>(st.st_dev);
      inode_ = static_cast<uint64_t>(st.st_ino);
      configured_ = true;
      identity_ready_.store(true, std::memory_order_release);
    } else if (system_ != system || engine_ != engine || device_ != static_cast<uint64_t>(st.st_dev) ||
               inode_ != static_cast<uint64_t>(st.st_ino)) {
      ++identity_errors_;
    }
  }

  std::vector<VersionRef> generated(const std::vector<uint64_t> &pages, uint64_t operation_key) {
    if (!enabled_) return {};
    std::lock_guard<std::mutex> lock(mu_);
    const uint64_t operation = operation_sequence_++;
    const uint64_t submit_batch = operation / 128;
    const uint64_t record_batch = operation_key / 128;
    std::vector<VersionRef> refs;
    refs.reserve(pages.size());
    for (uint64_t page : pages) {
      auto it = pages_.find(page);
      uint64_t version = 1;
      if (it == pages_.end()) {
        ++classes_["no_prior_version"];
      } else {
        ++classes_[classification(it->second.lifecycle)];
        version = it->second.version + 1;
        if (it->second.lifecycle == Lifecycle::inflight) {
          ++it->second.later_while_inflight;
          ++later_versions_while_inflight_;
        }
        if (it->second.lifecycle == Lifecycle::generated || it->second.lifecycle == Lifecycle::queued) {
          ++unproven_presubmit_containment_;
        }
      }
      PageState next;
      next.version = version;
      next.operation = operation;
      next.batch = submit_batch;
      next.lifecycle = Lifecycle::generated;
      pages_[page] = next;
      refs.push_back({page, version, operation, submit_batch});
      ++generated_;
      ++versions_since_barrier_;
      batch_page_keys_.push_back((record_batch << 32) | (page & 0xffffffffULL));
    }
    return refs;
  }

  void enqueued(const std::vector<VersionRef> &refs) {
    if (!enabled_) return;
    std::lock_guard<std::mutex> lock(mu_);
    ++queued_tasks_;
    queued_pages_ += refs.size();
    add_hist(queue_depth_tasks_hist_, queued_tasks_);
    add_hist(queue_depth_pages_hist_, queued_pages_);
    for (const auto &ref : refs) {
      PageState *state = current(ref, Lifecycle::generated);
      if (!state) continue;
      state->lifecycle = Lifecycle::queued;
      ++enqueued_;
      add_hist(per_page_queued_hist_, 1);
    }
  }

  void submitted(const std::vector<VersionRef> &refs) {
    if (!enabled_) return;
    std::lock_guard<std::mutex> lock(mu_);
    if (queued_tasks_ == 0) ++queue_underflow_;
    else --queued_tasks_;
    if (queued_pages_ < refs.size()) {
      ++queue_underflow_;
      queued_pages_ = 0;
    } else {
      queued_pages_ -= refs.size();
    }
    ++inflight_tasks_;
    inflight_pages_ += refs.size();
    add_hist(queue_depth_tasks_hist_, queued_tasks_);
    add_hist(queue_depth_pages_hist_, queued_pages_);
    for (const auto &ref : refs) {
      PageState *state = current(ref, Lifecycle::queued);
      if (!state) continue;
      state->lifecycle = Lifecycle::inflight;
      ++submitted_;
      add_hist(per_page_inflight_hist_, 1);
      add_hist(generation_to_submit_operation_hist_, operation_sequence_ - ref.operation - 1);
      const uint64_t current_batch = operation_sequence_ ? (operation_sequence_ - 1) / 128 : 0;
      add_hist(generation_to_submit_batch_hist_, current_batch >= ref.batch ? current_batch - ref.batch : 0);
    }
  }

  void completed(const std::vector<VersionRef> &refs) {
    if (!enabled_) return;
    std::lock_guard<std::mutex> lock(mu_);
    if (inflight_tasks_ == 0) ++inflight_underflow_;
    else --inflight_tasks_;
    if (inflight_pages_ < refs.size()) {
      ++inflight_underflow_;
      inflight_pages_ = 0;
    } else {
      inflight_pages_ -= refs.size();
    }
    for (const auto &ref : refs) {
      PageState *state = current(ref, Lifecycle::inflight);
      if (!state) continue;
      add_hist(later_while_inflight_hist_, state->later_while_inflight);
      state->lifecycle = Lifecycle::completed;
      ++completed_;
    }
    cv_.notify_all();
  }

  void barrier() {
    if (!enabled_) return;
    std::unique_lock<std::mutex> lock(mu_);
    cv_.wait(lock, [&] { return queued_tasks_ == 0 && inflight_tasks_ == 0; });
    for (auto &entry : pages_) {
      if (entry.second.lifecycle == Lifecycle::completed) entry.second.lifecycle = Lifecycle::barrier;
    }
    add_hist(versions_per_barrier_hist_, versions_since_barrier_);
    versions_since_barrier_ = 0;
    ++barriers_;
  }

  void write_once() noexcept {
    if (!enabled_ || written_.exchange(true)) return;
    try {
      std::lock_guard<std::mutex> lock(mu_);
      std::sort(batch_page_keys_.begin(), batch_page_keys_.end());
      std::map<uint64_t, uint64_t> same_page_per_batch_hist;
      for (size_t i = 0; i < batch_page_keys_.size();) {
        size_t j = i + 1;
        while (j < batch_page_keys_.size() && batch_page_keys_[j] == batch_page_keys_[i]) ++j;
        add_hist(same_page_per_batch_hist, j - i);
        i = j;
      }
      std::map<uint64_t, uint64_t> versions_per_page_barrier_hist;
      for (const auto &entry : pages_) add_hist(versions_per_page_barrier_hist, entry.second.version);
      const uint64_t class_sum = sum(classes_);
      const bool complete = configured_ && identity_errors_ == 0 && stale_events_ == 0 && queue_underflow_ == 0 &&
                            inflight_underflow_ == 0 && generated_ == class_sum && enqueued_ == submitted_ &&
                            submitted_ == completed_ && barriers_ > 0 && queued_tasks_ == 0 && inflight_tasks_ == 0 &&
                            unproven_presubmit_containment_ == 0;
      std::ofstream out(output_ + ".tmp", std::ios::trunc);
      if (!out) throw std::runtime_error("cannot open M3 lifecycle output");
      out << "{\n  \"schema\": \"dynamic-vamana-write-supersession-m3-lifecycle-v1\",\n";
      out << "  \"status\": \"" << (complete ? "complete" : "fail") << "\",\n";
      out << "  \"identity\": {\"system\": \"" << system_ << "\", \"engine\": \"" << engine_
          << "\", \"device\": " << device_ << ", \"inode\": " << inode_ << ", \"path\": \"" << path_ << "\"},\n";
      out << "  \"page_key\": \"(st_dev,st_ino,aligned_4k_offset)\",\n";
      out << "  \"totals\": {\"generated\": " << generated_ << ", \"enqueued\": " << enqueued_
          << ", \"submitted\": " << submitted_ << ", \"completed\": " << completed_
          << ", \"barriers\": " << barriers_ << ", \"unique_pages\": " << pages_.size() << "},\n";
      out << "  \"generation_classes\": "; write_string_map(out, classes_); out << ",\n";
      out << "  \"closure\": {\"class_sum\": " << class_sum
          << ", \"identity_errors\": " << identity_errors_ << ", \"stale_or_fork_events\": " << stale_events_
          << ", \"queue_underflow\": " << queue_underflow_ << ", \"inflight_underflow\": " << inflight_underflow_
          << ", \"unproven_presubmit_containment\": " << unproven_presubmit_containment_
          << ", \"later_versions_while_inflight\": " << later_versions_while_inflight_ << "},\n";
      out << "  \"histograms\": {\n";
      write_named_hist(out, "queue_depth_tasks", queue_depth_tasks_hist_, true);
      write_named_hist(out, "queue_depth_pages", queue_depth_pages_hist_, true);
      write_named_hist(out, "per_page_queued_versions", per_page_queued_hist_, true);
      write_named_hist(out, "per_page_inflight_versions", per_page_inflight_hist_, true);
      write_named_hist(out, "generation_to_submit_operation_distance", generation_to_submit_operation_hist_, true);
      write_named_hist(out, "generation_to_submit_batch_distance", generation_to_submit_batch_hist_, true);
      write_named_hist(out, "later_versions_during_inflight", later_while_inflight_hist_, true);
      write_named_hist(out, "same_page_versions_per_128_record_batch", same_page_per_batch_hist, true);
      write_named_hist(out, "versions_per_page_between_barriers", versions_per_page_barrier_hist, true);
      write_named_hist(out, "versions_per_barrier", versions_per_barrier_hist_, false);
      out << "  }\n}\n";
      out.close();
      if (::rename((output_ + ".tmp").c_str(), output_.c_str()) != 0) throw std::runtime_error("rename failed");
    } catch (...) {
    }
  }

 private:
  PageState *current(const VersionRef &ref, Lifecycle expected) {
    auto it = pages_.find(ref.page);
    if (it == pages_.end() || it->second.version != ref.version || it->second.lifecycle != expected) {
      ++stale_events_;
      return nullptr;
    }
    return &it->second;
  }
  static void add_hist(std::map<uint64_t, uint64_t> &hist, uint64_t value) { ++hist[value]; }
  static uint64_t sum(const std::map<std::string, uint64_t> &values) {
    uint64_t total = 0; for (const auto &entry : values) total += entry.second; return total;
  }
  static void write_hist(std::ostream &out, const std::map<uint64_t, uint64_t> &hist) {
    out << "{"; bool first = true;
    for (const auto &entry : hist) { if (!first) out << ", "; first = false; out << "\"" << entry.first << "\": " << entry.second; }
    out << "}";
  }
  static void write_string_map(std::ostream &out, const std::map<std::string, uint64_t> &values) {
    out << "{"; bool first = true;
    for (const auto &entry : values) { if (!first) out << ", "; first = false; out << "\"" << entry.first << "\": " << entry.second; }
    out << "}";
  }
  static void write_named_hist(std::ostream &out, const char *name, const std::map<uint64_t, uint64_t> &hist, bool comma) {
    out << "    \"" << name << "\": "; write_hist(out, hist); out << (comma ? ",\n" : "\n");
  }

  bool enabled_ = false;
  bool configured_ = false;
  std::atomic<bool> identity_ready_{false};
  std::string output_, system_, engine_, path_;
  uint64_t device_ = 0, inode_ = 0;
  std::mutex mu_;
  std::condition_variable cv_;
  std::atomic<bool> written_{false};
  std::unordered_map<uint64_t, PageState> pages_;
  std::vector<uint64_t> batch_page_keys_;
  std::map<std::string, uint64_t> classes_{{"superseded_before_enqueue", 0}, {"superseded_while_queued", 0},
      {"superseded_while_inflight", 0}, {"repeat_after_completion_before_barrier", 0},
      {"repeat_after_barrier", 0}, {"no_prior_version", 0}};
  std::map<uint64_t, uint64_t> queue_depth_tasks_hist_, queue_depth_pages_hist_, per_page_queued_hist_,
      per_page_inflight_hist_, generation_to_submit_operation_hist_, generation_to_submit_batch_hist_,
      later_while_inflight_hist_, versions_per_barrier_hist_;
  uint64_t operation_sequence_ = 0, generated_ = 0, enqueued_ = 0, submitted_ = 0, completed_ = 0;
  uint64_t queued_tasks_ = 0, queued_pages_ = 0, inflight_tasks_ = 0, inflight_pages_ = 0;
  uint64_t barriers_ = 0, versions_since_barrier_ = 0, identity_errors_ = 0, stale_events_ = 0;
  uint64_t queue_underflow_ = 0, inflight_underflow_ = 0, later_versions_while_inflight_ = 0;
  uint64_t unproven_presubmit_containment_ = 0;
};

inline Collector &collector() { static Collector instance; return instance; }
inline void configure(const std::string &system, const std::string &engine, const std::string &path) {
  collector().configure(system, engine, path);
}
inline std::vector<VersionRef> generated(const std::vector<uint64_t> &pages, uint64_t operation) {
  return collector().generated(pages, operation);
}
inline void enqueued(const std::vector<VersionRef> &refs) { collector().enqueued(refs); }
inline void submitted(const std::vector<VersionRef> &refs) { collector().submitted(refs); }
inline void completed(const std::vector<VersionRef> &refs) { collector().completed(refs); }
inline void barrier() { collector().barrier(); }

}  // namespace atlas_m3
