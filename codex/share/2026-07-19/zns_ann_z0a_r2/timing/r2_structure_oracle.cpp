#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <unordered_map>
#include <unordered_set>

namespace {
constexpr uint64_t kPage = 4096;

enum class Phase : uint8_t { Other, Load, Insert, Delete, Visibility, Publish, Metadata };

struct ObjectPage {
  uint64_t dev;
  uint64_t ino;
  uint64_t page;
  bool operator==(const ObjectPage &other) const {
    return dev == other.dev && ino == other.ino && page == other.page;
  }
};
struct ObjectPageHash {
  size_t operator()(const ObjectPage &key) const {
    return static_cast<size_t>((key.dev * 0x9e3779b97f4a7c15ULL) ^ key.ino ^ (key.page << 1));
  }
};
struct Aggregate {
  uint64_t bytes = 0;
  uint64_t requests = 0;
  uint64_t page_events = 0;
};
struct State {
  std::mutex mutex;
  std::atomic<uint8_t> phase{static_cast<uint8_t>(Phase::Other)};
  std::atomic<bool> flushed{false};
  std::string root;
  std::string output;
  Aggregate total;
  std::unordered_map<std::string, Aggregate> entries;
  std::unordered_map<uint8_t, Aggregate> phases;
  std::unordered_set<ObjectPage, ObjectPageHash> unique_pages;
  std::unordered_map<std::string, Aggregate> roles;
};

State &state() {
  static State *value = [] {
    auto *result = new State;
    if (const char *root = std::getenv("ATLAS_R2_ORACLE_INDEX_ROOT")) result->root = root;
    if (const char *output = std::getenv("ATLAS_R2_ORACLE_OUTPUT")) result->output = output;
    return result;
  }();
  return *value;
}

thread_local bool in_oracle = false;

bool path_under_root(int fd, const std::string &root, std::string &path, struct stat &st) {
  if (root.empty() || syscall(SYS_fstat, fd, &st) != 0) return false;
  char link[64], value[4096];
  std::snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
  const ssize_t length = syscall(SYS_readlink, link, value, sizeof(value) - 1);
  if (length <= 0) return false;
  value[length] = 0;
  path.assign(value);
  const std::string deleted = " (deleted)";
  if (path.size() >= deleted.size() && path.compare(path.size() - deleted.size(), deleted.size(), deleted) == 0)
    path.resize(path.size() - deleted.size());
  return path.size() >= root.size() && path.compare(0, root.size(), root) == 0 &&
         (path.size() == root.size() || path[root.size()] == '/');
}

void set_phase(const char *name) {
  if (!name) return;
  std::string value(name);
  Phase phase = Phase::Other;
  if (value == "clone_ready" || value == "load" || value == "index_loaded") phase = Phase::Load;
  else if (value == "insert" || value == "ingest_begin" || value == "insert_neighbor_repair") phase = Phase::Insert;
  else if (value == "delete") phase = Phase::Delete;
  else if (value.find("visibility") != std::string::npos) phase = Phase::Visibility;
  else if (value.find("publish") != std::string::npos || value.find("save") != std::string::npos) phase = Phase::Publish;
  else if (value == "metadata") phase = Phase::Metadata;
  state().phase.store(static_cast<uint8_t>(phase), std::memory_order_relaxed);
}

void record_async(const char *entry, int fd, uint64_t offset, uint64_t length) {
  if (!entry || !length || in_oracle) return;
  in_oracle = true;
  State &s = state();
  std::string path;
  struct stat st {};
  if (!path_under_root(fd, s.root, path, st)) {
    in_oracle = false;
    return;
  }
  const uint8_t phase = s.phase.load(std::memory_order_relaxed);
  Aggregate delta{length, 1, 0};
  const uint64_t end = offset + length;
  for (uint64_t position = offset; position < end;) {
    const uint64_t aligned = position / kPage * kPage;
    const uint64_t amount = std::min(end - position, kPage - (position - aligned));
    (void)amount;
    ++delta.page_events;
    position += amount;
  }
  {
    std::lock_guard<std::mutex> guard(s.mutex);
    s.total.bytes += delta.bytes;
    s.total.requests += delta.requests;
    s.total.page_events += delta.page_events;
    Aggregate &entry_total = s.entries[entry];
    entry_total.bytes += delta.bytes;
    entry_total.requests += delta.requests;
    entry_total.page_events += delta.page_events;
    Aggregate &phase_total = s.phases[phase];
    phase_total.bytes += delta.bytes;
    phase_total.requests += delta.requests;
    phase_total.page_events += delta.page_events;
    for (uint64_t page = offset / kPage; page <= (end - 1) / kPage; ++page)
      s.unique_pages.insert({static_cast<uint64_t>(st.st_dev), static_cast<uint64_t>(st.st_ino), page});
  }
  in_oracle = false;
}

void record_role(const char *role, uint64_t offset, uint64_t length) {
  if (!role || !length || in_oracle) return;
  in_oracle = true;
  Aggregate delta{length, 1, (offset + length - 1) / kPage - offset / kPage + 1};
  State &s = state();
  std::lock_guard<std::mutex> guard(s.mutex);
  Aggregate &total = s.roles[role];
  total.bytes += delta.bytes;
  total.requests += delta.requests;
  total.page_events += delta.page_events;
  in_oracle = false;
}

void emit_map(std::ostringstream &out, const std::unordered_map<std::string, Aggregate> &values) {
  bool first = true;
  out << '{';
  for (const auto &item : values) {
    if (!first) out << ',';
    first = false;
    out << '"' << item.first << "\":{" << "\"bytes\":" << item.second.bytes
        << ",\"requests\":" << item.second.requests
        << ",\"page_events\":" << item.second.page_events << '}';
  }
  out << '}';
}

void flush() {
  State &s = state();
  if (s.output.empty() || s.flushed.exchange(true)) return;
  std::lock_guard<std::mutex> guard(s.mutex);
  std::ostringstream out;
  out << "{\n  \"schema\":\"zns-ann-z0a-r2-common-structure-oracle-v1\","
      << "\n  \"scope\":\"source-instrumented async engine writes; no POSIX interposition\","
      << "\n  \"async_application_bytes\":" << s.total.bytes
      << ",\n  \"async_request_count\":" << s.total.requests
      << ",\n  \"async_page_event_count\":" << s.total.page_events
      << ",\n  \"unique_logical_pages\":" << s.unique_pages.size() << ",\n  \"entries\":";
  emit_map(out, s.entries);
  out << ",\n  \"phase_counts\":{";
  bool first = true;
  for (const auto &item : s.phases) {
    if (!first) out << ',';
    first = false;
    out << '"' << static_cast<unsigned>(item.first) << "\":{" << "\"bytes\":" << item.second.bytes
        << ",\"requests\":" << item.second.requests
        << ",\"page_events\":" << item.second.page_events << '}';
  }
  out << "},\n  \"roles\":";
  emit_map(out, s.roles);
  out << "\n}\n";
  const std::string data = out.str();
  const int fd = syscall(SYS_openat, AT_FDCWD, s.output.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
  if (fd < 0) return;
  size_t written = 0;
  while (written < data.size()) {
    const ssize_t amount = syscall(SYS_write, fd, data.data() + written, data.size() - written);
    if (amount <= 0) break;
    written += static_cast<size_t>(amount);
  }
  syscall(SYS_fsync, fd);
  syscall(SYS_close, fd);
}
}  // namespace

extern "C" void m0_set_phase(const char *name) { set_phase(name); }
extern "C" void m0_record_async_request(const char *entry, int fd, uint64_t offset, uint64_t length) {
  record_async(entry, fd, offset, length);
}
extern "C" void m0_record_role_page(const char *role, uint64_t offset, uint64_t length) {
  record_role(role, offset, length);
}
extern "C" void r2_oracle_force_link() {}
__attribute__((destructor)) static void r2_oracle_destructor() { flush(); }
