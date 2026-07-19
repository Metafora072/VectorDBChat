#include "z0a_trace.h"

#include <atomic>
#include <cerrno>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <limits>
#include <mutex>
#include <sstream>
#include <string>
#include <sys/mman.h>
#include <sys/sendfile.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <time.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

namespace {

constexpr uint64_t kInvalidSlot = std::numeric_limits<uint64_t>::max();
constexpr uint64_t kTokenGuard = 0x5a30415452414345ULL;  // Z0ATRACE
constexpr uint32_t kAccepted = 1U << 0;
constexpr uint32_t kCompleted = 1U << 1;
constexpr uint32_t kIdentityError = 1U << 2;

enum class CaptureMode { Disabled, ShimControl, FullTrace };

#pragma pack(push, 1)
struct TraceHeader {
  char magic[8];
  uint32_t version;
  uint32_t header_bytes;
  uint32_t record_bytes;
  uint32_t reserved;
  uint64_t record_count;
  uint64_t capacity;
  uint64_t dropped;
  uint64_t buffer_bytes;
  uint64_t run_hash;
  char run_id[96];
  char system[16];
};

struct TraceRecord {
  uint64_t request_id;
  uint64_t submit_seq;
  uint64_t completion_seq;
  uint64_t thread_seq;
  uint64_t thread_id;
  uint64_t submit_timestamp_ns;
  uint64_t completion_timestamp_ns;
  uint64_t run_hash;
  uint64_t object_incarnation;
  uint64_t device_id;
  uint64_t inode;
  uint64_t offset;
  uint64_t length;
  int64_t returned_bytes;
  int64_t completion_status;
  uint64_t update_or_replacement_id;
  uint64_t batch_id;
  uint64_t path_hash;
  uint32_t flags;
  uint16_t system;
  uint16_t phase;
  uint16_t source_entrypoint;
  uint16_t file_role;
};

struct LifecycleRecord {
  uint64_t global_seq;
  uint64_t timestamp_ns;
  uint64_t thread_seq;
  uint64_t thread_id;
  uint64_t run_hash;
  uint64_t object_incarnation;
  uint64_t device_id;
  uint64_t inode;
  uint64_t path_hash;
  uint64_t old_size_bytes;
  uint64_t new_size_bytes;
  int64_t status;
  uint32_t flags;
  uint16_t system;
  uint16_t phase;
  uint16_t source_entrypoint;
  uint16_t file_role;
};
#pragma pack(pop)

static_assert(sizeof(TraceRecord) == 156, "trace ABI changed");
static_assert(sizeof(LifecycleRecord) == 108, "lifecycle ABI changed");

struct LifecycleToken {
  uint64_t slot = kInvalidSlot;
  bool active = false;
};

struct IdentityKey {
  uint64_t dev;
  uint64_t ino;
  bool operator==(const IdentityKey &other) const {
    return dev == other.dev && ino == other.ino;
  }
};
struct IdentityHash {
  size_t operator()(const IdentityKey &x) const {
    return static_cast<size_t>((x.dev * 0x9e3779b97f4a7c15ULL) ^ x.ino);
  }
};
struct ObjectMeta {
  uint64_t incarnation;
  uint64_t dev;
  uint64_t ino;
  uint64_t ctime_ns;
  uint16_t initial_role;
  bool initial;
  std::string path;
};
struct Identity {
  uint64_t incarnation = 0;
  uint64_t dev = 0;
  uint64_t ino = 0;
  uint64_t path_hash = 0;
  uint16_t role = ATLAS_Z0A_ROLE_UNKNOWN;
  bool valid = false;
};

struct CachedIdentity {
  Identity identity;
};

thread_local AtlasZ0AContext tls_context;
thread_local uint64_t tls_thread_seq = 0;
thread_local bool tls_in_hook = false;
thread_local std::unordered_map<int, CachedIdentity> tls_fd_identities;

uint64_t fnv1a(const char *data, size_t size) {
  uint64_t value = 1469598103934665603ULL;
  for (size_t i = 0; i < size; ++i) {
    value ^= static_cast<unsigned char>(data[i]);
    value *= 1099511628211ULL;
  }
  return value;
}
uint64_t hash_string(const std::string &value) { return fnv1a(value.data(), value.size()); }
uint64_t monotonic_ns() {
  timespec ts{};
  syscall(SYS_clock_gettime, CLOCK_MONOTONIC, &ts);
  return static_cast<uint64_t>(ts.tv_sec) * 1000000000ULL + static_cast<uint64_t>(ts.tv_nsec);
}
std::string escape_json(const std::string &value) {
  std::ostringstream out;
  for (unsigned char c : value) {
    if (c == '\\') out << "\\\\";
    else if (c == '"') out << "\\\"";
    else if (c == '\n') out << "\\n";
    else if (c == '\r') out << "\\r";
    else if (c == '\t') out << "\\t";
    else if (c < 0x20) out << '?';
    else out << c;
  }
  return out.str();
}
std::string fd_path(int fd) {
  char link[64];
  char path[4096];
  std::snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
  const ssize_t size = syscall(SYS_readlink, link, path, sizeof(path) - 1);
  if (size <= 0) return {};
  path[size] = 0;
  std::string result(path);
  const std::string deleted = " (deleted)";
  if (result.size() >= deleted.size() && result.compare(result.size() - deleted.size(), deleted.size(), deleted) == 0)
    result.resize(result.size() - deleted.size());
  return result;
}
std::string base_name(const std::string &path) {
  const size_t slash = path.find_last_of('/');
  return slash == std::string::npos ? path : path.substr(slash + 1);
}
uint16_t role_for_path(const std::string &path) {
  const std::string name = base_name(path);
  if (name.find("shadow_disk.index") != std::string::npos) return ATLAS_Z0A_ROLE_SHADOW_COMBINED;
  if (name.find("disk_index_graph") != std::string::npos) return ATLAS_Z0A_ROLE_GRAPH;
  if (name.find("disk_index_data") != std::string::npos) return ATLAS_Z0A_ROLE_VECTOR;
  if (name.find("reordered_disk") != std::string::npos) return ATLAS_Z0A_ROLE_REORDERED_DERIVED;
  if (name.find(".tags") != std::string::npos) return ATLAS_Z0A_ROLE_TAGS;
  if (name.find("pq_") != std::string::npos || name.find("_pq") != std::string::npos) return ATLAS_Z0A_ROLE_PQ;
  if (name.find("map") != std::string::npos) return ATLAS_Z0A_ROLE_MAP;
  if (name.find("delete") != std::string::npos || name.find("tombstone") != std::string::npos)
    return ATLAS_Z0A_ROLE_DELETE_TOMBSTONE;
  if (name.find("_disk.index") != std::string::npos) return ATLAS_Z0A_ROLE_PRIMARY_COMBINED;
  if (name.find("tmp") != std::string::npos || name.find("temp") != std::string::npos)
    return ATLAS_Z0A_ROLE_TEMPORARY;
  return ATLAS_Z0A_ROLE_METADATA;
}
uint16_t system_code(const std::string &system) {
  if (system == "DGAI") return 1;
  if (system == "OdinANN") return 2;
  return 0;
}
bool write_all(int fd, const void *data, size_t size) {
  const char *cursor = static_cast<const char *>(data);
  while (size) {
    const ssize_t written = syscall(SYS_write, fd, cursor, size);
    if (written <= 0) return false;
    cursor += written;
    size -= static_cast<size_t>(written);
  }
  return true;
}
bool write_atomic(const std::string &path, const std::string &data) {
  if (path.empty()) return true;
  const std::string temporary = path + ".tmp";
  const int fd = syscall(SYS_openat, AT_FDCWD, temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
  if (fd < 0) return false;
  const bool ok = write_all(fd, data.data(), data.size()) && syscall(SYS_fsync, fd) == 0;
  syscall(SYS_close, fd);
  if (!ok || syscall(SYS_rename, temporary.c_str(), path.c_str()) != 0) {
    syscall(SYS_unlink, temporary.c_str());
    return false;
  }
  return true;
}

class Collector {
 public:
  Collector() {
    const char *mode = std::getenv("ATLAS_Z0A_MODE");
    if (mode && std::strcmp(mode, "shim-control") == 0)
      mode_ = CaptureMode::ShimControl;
    else if (mode && std::strcmp(mode, "full-trace") == 0)
      mode_ = CaptureMode::FullTrace;
    else
      return;
    read_env("ATLAS_Z0A_TRACE_OUTPUT", trace_output_);
    read_env("ATLAS_Z0A_META_OUTPUT", meta_output_);
    read_env("ATLAS_Z0A_LEDGER_OUTPUT", ledger_output_);
    read_env("ATLAS_Z0A_LIFECYCLE_OUTPUT", lifecycle_output_);
    read_env("ATLAS_Z0A_INDEX_ROOT", index_root_);
    read_env("ATLAS_Z0A_SYSTEM", system_);
    read_env("ATLAS_Z0A_RUN_ID", run_id_);
    read_env("ATLAS_Z0A_OBJECT_MAP", object_map_);
    if (trace_output_.empty() || meta_output_.empty() || ledger_output_.empty() || lifecycle_output_.empty() || index_root_.empty() ||
        system_.empty() || run_id_.empty()) {
      configuration_error_ = true;
      return;
    }
    run_hash_ = hash_string(run_id_);
    capacity_ = 65536;
    if (const char *raw = std::getenv("ATLAS_Z0A_TRACE_CAPACITY")) {
      char *end = nullptr;
      const unsigned long long parsed = std::strtoull(raw, &end, 10);
      if (end && *end == 0 && parsed > 0) capacity_ = static_cast<uint64_t>(parsed);
    }
    if (capacity_ > std::numeric_limits<size_t>::max() / sizeof(TraceRecord)) {
      configuration_error_ = true;
      return;
    }
    buffer_bytes_ = capacity_ * sizeof(TraceRecord);
    records_ = static_cast<TraceRecord *>(mmap(nullptr, static_cast<size_t>(buffer_bytes_), PROT_READ | PROT_WRITE,
                                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (records_ == MAP_FAILED) {
      records_ = nullptr;
      configuration_error_ = true;
      return;
    }
    lifecycle_capacity_ = 4096;
    lifecycle_buffer_bytes_ = lifecycle_capacity_ * sizeof(LifecycleRecord);
    lifecycle_records_ = static_cast<LifecycleRecord *>(
        mmap(nullptr, static_cast<size_t>(lifecycle_buffer_bytes_), PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (lifecycle_records_ == MAP_FAILED) {
      lifecycle_records_ = nullptr;
      configuration_error_ = true;
      return;
    }
    load_object_map();
  }
  ~Collector() {
    flush();
    if (records_) munmap(records_, static_cast<size_t>(buffer_bytes_));
    if (lifecycle_records_) munmap(lifecycle_records_, static_cast<size_t>(lifecycle_buffer_bytes_));
  }
  bool enabled() const { return mode_ != CaptureMode::Disabled && !configuration_error_ && records_; }
  bool full_trace() const { return mode_ == CaptureMode::FullTrace; }

  bool submit(AtlasZ0ATraceToken *token, uint16_t source, int fd, uint64_t offset, uint64_t length) {
    if (!enabled() || !token || !length) return false;
    Identity identity = identify(fd, source);
    if (!identity.valid) return false;
    // SHIM-CONTROL follows the same interposition, phase/source and object
    // identity path and initializes the same fixed buffer, but never reserves
    // or appends a record and never emits a trace.
    if (!full_trace()) return true;
    const uint64_t slot = reserved_.fetch_add(1, std::memory_order_relaxed);
    if (slot >= capacity_) {
      dropped_.fetch_add(1, std::memory_order_relaxed);
      return false;
    }
    TraceRecord &record = records_[slot];
    record.request_id = request_id_.fetch_add(1, std::memory_order_relaxed) + 1;
    record.submit_seq = global_seq_.fetch_add(1, std::memory_order_relaxed) + 1;
    record.thread_seq = ++tls_thread_seq;
    record.thread_id = static_cast<uint64_t>(syscall(SYS_gettid));
    record.submit_timestamp_ns = monotonic_ns();
    record.run_hash = run_hash_;
    record.object_incarnation = identity.incarnation;
    record.device_id = identity.dev;
    record.inode = identity.ino;
    record.offset = offset;
    record.length = length;
    record.returned_bytes = std::numeric_limits<int64_t>::min();
    record.completion_status = std::numeric_limits<int64_t>::min();
    record.update_or_replacement_id = tls_context.update_or_replacement_id;
    record.batch_id = tls_context.batch_id;
    record.path_hash = identity.path_hash;
    record.system = system_code(system_);
    record.phase = tls_context.phase;
    record.source_entrypoint = source;
    record.file_role = identity.role;
    record.flags = kAccepted;
    std::atomic_thread_fence(std::memory_order_release);
    token->slot = slot;
    token->request_id = record.request_id;
    token->guard = kTokenGuard;
    return true;
  }

  void prepare_truncate_fd(LifecycleToken *token, int fd, uint64_t new_size) {
    if (!token) return;
    token->slot = kInvalidSlot;
    token->active = false;
    if (!enabled()) return;
    Identity identity = identify(fd, 0xffff);
    struct stat st{};
    if (!identity.valid || syscall(SYS_fstat, fd, &st) != 0 || st.st_size < 0) return;
    prepare_truncate(token, identity, static_cast<uint64_t>(st.st_size), new_size);
  }

  void prepare_truncate_path(LifecycleToken *token, const char *path, uint64_t new_size) {
    if (!token) return;
    token->slot = kInvalidSlot;
    token->active = false;
    if (!enabled() || !path) return;
    const int fd = static_cast<int>(syscall(SYS_openat, AT_FDCWD, path, O_RDONLY | O_CLOEXEC));
    if (fd < 0) return;
    Identity identity = identify(fd, 0xffff);
    struct stat st{};
    const bool stat_ok = syscall(SYS_fstat, fd, &st) == 0 && st.st_size >= 0;
    tls_fd_identities.erase(fd);
    syscall(SYS_close, fd);
    if (!identity.valid || !stat_ok) return;
    prepare_truncate(token, identity, static_cast<uint64_t>(st.st_size), new_size);
  }

  void complete_truncate(LifecycleToken *token, int result, int status) {
    if (!enabled() || !full_trace() || !token || !token->active || token->slot >= lifecycle_capacity_) return;
    LifecycleRecord &record = lifecycle_records_[token->slot];
    record.status = result == 0 ? 0 : status;
    record.flags |= kCompleted;
  }

  void complete(AtlasZ0ATraceToken *token, int64_t result, int64_t status) {
    if (!enabled() || !full_trace() || !token || token->guard != kTokenGuard || token->slot >= capacity_) return;
    TraceRecord &record = records_[token->slot];
    if (record.request_id != token->request_id) {
      identity_errors_.fetch_add(1, std::memory_order_relaxed);
      record.flags |= kIdentityError;
      return;
    }
    record.returned_bytes = result;
    record.completion_status = status;
    record.completion_timestamp_ns = monotonic_ns();
    record.completion_seq = completion_seq_.fetch_add(1, std::memory_order_relaxed) + 1;
    std::atomic_thread_fence(std::memory_order_release);
    record.flags |= kCompleted;
  }

  void flush() {
    if (!enabled() || flushed_.exchange(true)) return;
    if (!full_trace()) return;
    const uint64_t count = std::min(reserved_.load(std::memory_order_acquire), capacity_);
    TraceHeader header{};
    std::memcpy(header.magic, "Z0ATRCE1", 8);
    header.version = 1;
    header.header_bytes = sizeof(header);
    header.record_bytes = sizeof(TraceRecord);
    header.record_count = count;
    header.capacity = capacity_;
    header.dropped = dropped_.load();
    header.buffer_bytes = buffer_bytes_;
    header.run_hash = run_hash_;
    std::snprintf(header.run_id, sizeof(header.run_id), "%s", run_id_.c_str());
    std::snprintf(header.system, sizeof(header.system), "%s", system_.c_str());
    const std::string temporary = trace_output_ + ".tmp";
    const int fd = syscall(SYS_openat, AT_FDCWD, temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
    bool trace_ok = fd >= 0 && write_all(fd, &header, sizeof(header)) &&
                    write_all(fd, records_, static_cast<size_t>(count * sizeof(TraceRecord))) && syscall(SYS_fsync, fd) == 0;
    if (fd >= 0) syscall(SYS_close, fd);
    if (trace_ok) trace_ok = syscall(SYS_rename, temporary.c_str(), trace_output_.c_str()) == 0;
    if (!trace_ok) syscall(SYS_unlink, temporary.c_str());
    const uint64_t lifecycle_count = std::min(lifecycle_reserved_.load(std::memory_order_acquire), lifecycle_capacity_);
    const bool lifecycle_ok = write_lifecycle(lifecycle_count);
    write_meta(count, lifecycle_count, trace_ok && lifecycle_ok);
    write_ledger(count, lifecycle_count, trace_ok && lifecycle_ok);
  }

 private:
  static void read_env(const char *name, std::string &output) {
    if (const char *value = std::getenv(name)) output = value;
  }
  bool under_root(const std::string &path) const {
    return path.size() >= index_root_.size() && path.compare(0, index_root_.size(), index_root_) == 0 &&
           (path.size() == index_root_.size() || path[index_root_.size()] == '/');
  }
  static uint64_t ctime_ns(const struct stat &st) {
#if defined(__linux__)
    return static_cast<uint64_t>(st.st_ctim.tv_sec) * 1000000000ULL + static_cast<uint64_t>(st.st_ctim.tv_nsec);
#else
    return static_cast<uint64_t>(st.st_ctime) * 1000000000ULL;
#endif
  }
  Identity identify(int fd, uint16_t source) {
    Identity result;
    auto cached = tls_fd_identities.find(fd);
    const bool engine_owned_long_lived_fd =
        source == ATLAS_Z0A_SOURCE_LIBAIO_EXECUTE_IO ||
        source == ATLAS_Z0A_SOURCE_IOURING_EXECUTE_IO;
    if (cached != tls_fd_identities.end() && engine_owned_long_lived_fd)
      return cached->second.identity;

    struct stat st{};
    if (syscall(SYS_fstat, fd, &st) != 0) return result;
    if (cached != tls_fd_identities.end()) {
      // POSIX entry points may observe short-lived descriptors and therefore
      // verify dev/inode on every submission.  Engine-owned libaio/io_uring
      // descriptors are constructed once and remain live for the run.
      if (cached->second.identity.dev == static_cast<uint64_t>(st.st_dev) &&
          cached->second.identity.ino == static_cast<uint64_t>(st.st_ino))
        return cached->second.identity;
      tls_fd_identities.erase(cached);
    }
    const std::string path = fd_path(fd);
    if (path.empty() || !under_root(path)) return result;
    const IdentityKey key{static_cast<uint64_t>(st.st_dev), static_cast<uint64_t>(st.st_ino)};
    std::lock_guard<std::mutex> lock(objects_mu_);
    auto found = objects_by_key_.find(key);
    if (found == objects_by_key_.end()) {
      const uint64_t incarnation = next_incarnation_++;
      ObjectMeta meta{incarnation, key.dev, key.ino, ctime_ns(st), role_for_path(path), false, path};
      objects_.push_back(meta);
      found = objects_by_key_.emplace(key, incarnation).first;
    }
    result.incarnation = found->second;
    result.dev = key.dev;
    result.ino = key.ino;
    result.path_hash = hash_string(path);
    result.role = role_for_path(path);
    result.valid = true;
    tls_fd_identities.emplace(fd, CachedIdentity{result});
    return result;
  }
  void prepare_truncate(LifecycleToken *token, const Identity &identity, uint64_t old_size, uint64_t new_size) {
    // SHIM-CONTROL deliberately performs path/identity/stat work but neither
    // allocates a sequence number nor timestamps/appends an event.
    if (!full_trace()) return;
    const uint64_t slot = lifecycle_reserved_.fetch_add(1, std::memory_order_relaxed);
    if (slot >= lifecycle_capacity_) {
      lifecycle_dropped_.fetch_add(1, std::memory_order_relaxed);
      return;
    }
    LifecycleRecord &record = lifecycle_records_[slot];
    record.global_seq = global_seq_.fetch_add(1, std::memory_order_relaxed) + 1;
    record.timestamp_ns = monotonic_ns();
    record.thread_seq = ++tls_thread_seq;
    record.thread_id = static_cast<uint64_t>(syscall(SYS_gettid));
    record.run_hash = run_hash_;
    record.object_incarnation = identity.incarnation;
    record.device_id = identity.dev;
    record.inode = identity.ino;
    record.path_hash = identity.path_hash;
    record.old_size_bytes = old_size;
    record.new_size_bytes = new_size;
    record.status = std::numeric_limits<int64_t>::min();
    record.flags = kAccepted;
    record.system = system_code(system_);
    record.phase = tls_context.phase;
    record.source_entrypoint = 1;  // TRUNCATE/FTRUNCATE v1
    record.file_role = identity.role;
    token->slot = slot;
    token->active = true;
  }

  bool write_lifecycle(uint64_t count) {
    std::ostringstream out;
    out << "{\"record_type\":\"lifecycle_header\",\"schema\":\"zns-ann-z0a-r2-lifecycle-v1\","
        << "\"run_id\":\"" << escape_json(run_id_) << "\",\"run_hash\":" << run_hash_
        << ",\"system\":\"" << escape_json(system_) << "\",\"record_count\":" << count
        << ",\"capacity\":" << lifecycle_capacity_ << ",\"dropped\":" << lifecycle_dropped_.load() << "}\n";
    for (uint64_t i = 0; i < count; ++i) {
      const LifecycleRecord &r = lifecycle_records_[i];
      out << "{\"record_type\":\"lifecycle_event\",\"event_kind\":\"TRUNCATE\",\"global_seq\":" << r.global_seq
          << ",\"timestamp_ns\":" << r.timestamp_ns << ",\"thread_seq\":" << r.thread_seq
          << ",\"thread_id\":" << r.thread_id << ",\"run_hash\":" << r.run_hash
          << ",\"object_incarnation\":" << r.object_incarnation << ",\"device_id\":" << r.device_id
          << ",\"inode\":" << r.inode << ",\"path_hash\":" << r.path_hash
          << ",\"old_size_bytes\":" << r.old_size_bytes << ",\"new_size_bytes\":" << r.new_size_bytes
          << ",\"status\":" << r.status << ",\"flags\":" << r.flags << ",\"system\":" << r.system
          << ",\"phase\":" << r.phase << ",\"source_entrypoint\":" << r.source_entrypoint
          << ",\"file_role\":" << r.file_role << "}\n";
    }
    out << "{\"record_type\":\"lifecycle_trailer\",\"status\":\""
        << (lifecycle_dropped_.load() == 0 ? "complete" : "fail") << "\",\"record_count\":" << count << "}\n";
    return write_atomic(lifecycle_output_, out.str());
  }
  void load_object_map() {
    if (object_map_.empty()) return;
    std::ifstream input(object_map_);
    if (!input) {
      configuration_error_ = true;
      return;
    }
    std::string line;
    while (std::getline(input, line)) {
      if (line.empty() || line[0] == '#') continue;
      std::istringstream row(line);
      uint64_t incarnation = 0, dev = 0, ino = 0, ctime = 0;
      unsigned role = 0;
      std::string path;
      if (!(row >> incarnation >> dev >> ino >> ctime >> role)) {
        configuration_error_ = true;
        return;
      }
      row >> std::ws;
      std::getline(row, path);
      if (path.empty() || incarnation == 0 || !under_root(path)) {
        configuration_error_ = true;
        return;
      }
      IdentityKey key{dev, ino};
      if (!objects_by_key_.emplace(key, incarnation).second) {
        configuration_error_ = true;
        return;
      }
      objects_.push_back({incarnation, dev, ino, ctime, static_cast<uint16_t>(role), true, path});
      next_incarnation_ = std::max(next_incarnation_, incarnation + 1);
    }
  }
  void write_meta(uint64_t count, uint64_t lifecycle_count, bool trace_ok) {
    std::ostringstream out;
    out << "{\n  \"schema\": \"zns-ann-z0a-trace-meta-v1\",\n  \"status\": \""
        << (trace_ok && dropped_.load() == 0 && identity_errors_.load() == 0 ? "complete" : "fail")
        << "\",\n  \"run_id\": \"" << escape_json(run_id_) << "\",\n  \"run_hash\": " << run_hash_
        << ",\n  \"system\": \"" << escape_json(system_) << "\",\n  \"index_root\": \""
        << escape_json(index_root_) << "\",\n  \"record_count\": " << count << ",\n  \"capacity\": " << capacity_
        << ",\n  \"buffer_peak_bytes\": " << (buffer_bytes_ + lifecycle_buffer_bytes_)
        << ",\n  \"lifecycle_record_count\": " << lifecycle_count
        << ",\n  \"lifecycle_dropped_events\": " << lifecycle_dropped_.load()
        << ",\n  \"dropped_events\": " << dropped_.load()
        << ",\n  \"identity_errors\": " << identity_errors_.load() << ",\n  \"objects\": [";
    {
      std::lock_guard<std::mutex> lock(objects_mu_);
      for (size_t i = 0; i < objects_.size(); ++i) {
        const auto &object = objects_[i];
        if (i) out << ',';
        out << "\n    {\"stable_object_id\": \"" << escape_json(run_id_) << ':' << object.incarnation
            << "\", \"incarnation\": " << object.incarnation << ", \"device_id\": " << object.dev
            << ", \"inode\": " << object.ino << ", \"ctime_ns\": " << object.ctime_ns
            << ", \"initial\": " << (object.initial ? "true" : "false") << ", \"initial_role\": "
            << object.initial_role << ", \"path\": \"" << escape_json(object.path) << "\"}";
      }
    }
    out << "\n  ]\n}\n";
    write_atomic(meta_output_, out.str());
  }
  void write_ledger(uint64_t count, uint64_t lifecycle_count, bool trace_ok) {
    uint64_t accepted = 0, completed = 0, requested = 0, returned = 0, failures = 0;
    std::unordered_map<uint16_t, uint64_t> phases, roles, sources;
    for (uint64_t i = 0; i < count; ++i) {
      const TraceRecord &record = records_[i];
      if (record.flags & kAccepted) {
        ++accepted;
        requested += record.length;
        ++phases[record.phase];
        ++roles[record.file_role];
        ++sources[record.source_entrypoint];
      }
      if (record.flags & kCompleted) {
        ++completed;
        if (record.returned_bytes > 0) returned += static_cast<uint64_t>(record.returned_bytes);
        if (record.returned_bytes < 0 || record.completion_status != 0) ++failures;
      }
    }
    auto emit_map = [](std::ostringstream &out, const std::unordered_map<uint16_t, uint64_t> &map) {
      out << '{'; bool first = true;
      for (const auto &entry : map) { if (!first) out << ','; first = false; out << '"' << entry.first << "\":" << entry.second; }
      out << '}';
    };
    std::ostringstream out;
    out << "{\n  \"schema\": \"zns-ann-z0a-trace-ledger-v1\",\n  \"status\": \""
        << (trace_ok && accepted == completed && dropped_.load() == 0 ? "complete" : "fail")
        << "\",\n  \"accepted_requests\": " << accepted << ",\n  \"completed_requests\": " << completed
        << ",\n  \"requested_bytes\": " << requested << ",\n  \"returned_bytes\": " << returned
        << ",\n  \"failed_requests\": " << failures << ",\n  \"lifecycle_events\": " << lifecycle_count
        << ",\n  \"lifecycle_dropped_events\": " << lifecycle_dropped_.load()
        << ",\n  \"dropped_events\": " << dropped_.load()
        << ",\n  \"phase_counts\": "; emit_map(out, phases); out << ",\n  \"role_counts\": "; emit_map(out, roles);
    out << ",\n  \"source_counts\": "; emit_map(out, sources); out << "\n}\n";
    write_atomic(ledger_output_, out.str());
  }

  CaptureMode mode_ = CaptureMode::Disabled;
  bool configuration_error_ = false;
  std::atomic<bool> flushed_{false};
  std::string trace_output_, meta_output_, ledger_output_, lifecycle_output_, index_root_, system_, run_id_, object_map_;
  uint64_t run_hash_ = 0, capacity_ = 0, buffer_bytes_ = 0, lifecycle_capacity_ = 0, lifecycle_buffer_bytes_ = 0;
  TraceRecord *records_ = nullptr;
  LifecycleRecord *lifecycle_records_ = nullptr;
  std::atomic<uint64_t> reserved_{0}, dropped_{0}, request_id_{0}, global_seq_{0}, completion_seq_{0}, identity_errors_{0};
  std::atomic<uint64_t> lifecycle_reserved_{0}, lifecycle_dropped_{0};
  std::mutex objects_mu_;
  std::unordered_map<IdentityKey, uint64_t, IdentityHash> objects_by_key_;
  std::vector<ObjectMeta> objects_;
  uint64_t next_incarnation_ = 1;
};

Collector &collector() {
  static Collector *instance = new Collector;
  return *instance;
}

template <typename Function>
Function next_symbol(const char *name) {
  return reinterpret_cast<Function>(dlsym(RTLD_NEXT, name));
}

template <typename Function, typename... Args>
ssize_t traced_posix(uint16_t source, int fd, uint64_t offset, uint64_t requested, Function function, Args... args) {
  if (tls_in_hook) return function(args...);
  tls_in_hook = true;
  AtlasZ0ATraceToken token;
  atlas_z0a_prepare(&token);
  atlas_z0a_submit(&token, source, fd, offset, requested);
  tls_in_hook = false;
  const ssize_t result = function(args...);
  tls_in_hook = true;
  atlas_z0a_complete(&token, result, result < 0 ? errno : 0);
  tls_in_hook = false;
  return result;
}

}  // namespace

extern "C" bool atlas_z0a_enabled() { return collector().enabled(); }
extern "C" void atlas_z0a_set_phase_name(const char *name) {
  if (!name) return;
  std::string value(name);
  if (value == "clone_ready" || value == "load" || value == "index_loaded") tls_context.phase = ATLAS_Z0A_PHASE_LOAD;
  else if (value == "ingest_begin" || value == "insert" || value == "insert_neighbor_repair") tls_context.phase = ATLAS_Z0A_PHASE_INSERT;
  else if (value == "delete") tls_context.phase = ATLAS_Z0A_PHASE_DELETE;
  else if (value.find("visibility") != std::string::npos) tls_context.phase = ATLAS_Z0A_PHASE_VISIBILITY;
  else if (value.find("publish") != std::string::npos || value.find("save") != std::string::npos) tls_context.phase = ATLAS_Z0A_PHASE_PUBLISH;
  else if (value.find("shadow") != std::string::npos) tls_context.phase = ATLAS_Z0A_PHASE_SHADOW_COPY;
  else if (value.find("repair") != std::string::npos) tls_context.phase = ATLAS_Z0A_PHASE_REPAIR;
  else tls_context.phase = ATLAS_Z0A_PHASE_OTHER;
}
extern "C" void atlas_z0a_set_context(uint64_t update, uint64_t batch, uint16_t phase) {
  tls_context.update_or_replacement_id = update;
  tls_context.batch_id = batch;
  tls_context.phase = phase;
}
extern "C" AtlasZ0AContext atlas_z0a_get_context() { return tls_context; }
extern "C" void atlas_z0a_restore_context(AtlasZ0AContext context) { tls_context = context; }
extern "C" void atlas_z0a_prepare(AtlasZ0ATraceToken *token) {
  if (!token) return;
  token->slot = kInvalidSlot;
  token->request_id = 0;
  token->guard = kTokenGuard;
}
extern "C" bool atlas_z0a_submit(AtlasZ0ATraceToken *token, uint16_t source, int fd, uint64_t offset, uint64_t length) {
  return collector().submit(token, source, fd, offset, length);
}
extern "C" void atlas_z0a_complete(AtlasZ0ATraceToken *token, int64_t returned, int64_t status) {
  collector().complete(token, returned, status);
}
extern "C" void atlas_z0a_flush() { collector().flush(); }

extern "C" ssize_t write(int fd, const void *buffer, size_t count) {
  using Function = ssize_t (*)(int, const void *, size_t);
  static Function real = next_symbol<Function>("write");
  const off_t end = syscall(SYS_lseek, fd, 0, SEEK_CUR);
  const uint64_t offset = end >= 0 ? static_cast<uint64_t>(end) : 0;
  return traced_posix(ATLAS_Z0A_SOURCE_WRITE, fd, offset, count, real, fd, buffer, count);
}
extern "C" ssize_t pwrite(int fd, const void *buffer, size_t count, off_t offset) {
  using Function = ssize_t (*)(int, const void *, size_t, off_t);
  static Function real = next_symbol<Function>("pwrite");
  return traced_posix(ATLAS_Z0A_SOURCE_PWRITE, fd, offset, count, real, fd, buffer, count, offset);
}
extern "C" ssize_t pwrite64(int fd, const void *buffer, size_t count, off64_t offset) {
  using Function = ssize_t (*)(int, const void *, size_t, off64_t);
  static Function real = next_symbol<Function>("pwrite64");
  return traced_posix(ATLAS_Z0A_SOURCE_PWRITE64, fd, offset, count, real, fd, buffer, count, offset);
}
extern "C" ssize_t writev(int fd, const iovec *iov, int count) {
  using Function = ssize_t (*)(int, const iovec *, int);
  static Function real = next_symbol<Function>("writev");
  uint64_t bytes = 0; for (int i = 0; i < count; ++i) bytes += iov[i].iov_len;
  const off_t end = syscall(SYS_lseek, fd, 0, SEEK_CUR);
  return traced_posix(ATLAS_Z0A_SOURCE_WRITEV, fd, end >= 0 ? static_cast<uint64_t>(end) : 0, bytes, real, fd, iov, count);
}
extern "C" ssize_t pwritev(int fd, const iovec *iov, int count, off_t offset) {
  using Function = ssize_t (*)(int, const iovec *, int, off_t);
  static Function real = next_symbol<Function>("pwritev");
  uint64_t bytes = 0; for (int i = 0; i < count; ++i) bytes += iov[i].iov_len;
  return traced_posix(ATLAS_Z0A_SOURCE_PWRITEV, fd, offset, bytes, real, fd, iov, count, offset);
}
extern "C" ssize_t sendfile(int out_fd, int in_fd, off_t *offset, size_t count) {
  using Function = ssize_t (*)(int, int, off_t *, size_t);
  static Function real = next_symbol<Function>("sendfile");
  const off_t out_offset = syscall(SYS_lseek, out_fd, 0, SEEK_CUR);
  return traced_posix(ATLAS_Z0A_SOURCE_SENDFILE, out_fd, out_offset >= 0 ? static_cast<uint64_t>(out_offset) : 0,
                      count, real, out_fd, in_fd, offset, count);
}
extern "C" ssize_t copy_file_range(int in_fd, off64_t *in_offset, int out_fd, off64_t *out_offset,
                                     size_t length, unsigned flags) {
  using Function = ssize_t (*)(int, off64_t *, int, off64_t *, size_t, unsigned);
  static Function real = next_symbol<Function>("copy_file_range");
  uint64_t offset = out_offset ? static_cast<uint64_t>(*out_offset) : 0;
  if (!out_offset) { const off_t current = syscall(SYS_lseek, out_fd, 0, SEEK_CUR); if (current >= 0) offset = current; }
  return traced_posix(ATLAS_Z0A_SOURCE_COPY_FILE_RANGE, out_fd, offset, length, real,
                      in_fd, in_offset, out_fd, out_offset, length, flags);
}

extern "C" int ftruncate(int fd, off_t length) {
  using Function = int (*)(int, off_t);
  static Function real = next_symbol<Function>("ftruncate");
  if (tls_in_hook || length < 0) return real(fd, length);
  tls_in_hook = true;
  LifecycleToken token;
  collector().prepare_truncate_fd(&token, fd, static_cast<uint64_t>(length));
  tls_in_hook = false;
  const int result = real(fd, length);
  const int saved_errno = errno;
  tls_in_hook = true;
  collector().complete_truncate(&token, result, result == 0 ? 0 : saved_errno);
  tls_in_hook = false;
  errno = saved_errno;
  return result;
}

extern "C" int ftruncate64(int fd, off64_t length) {
  using Function = int (*)(int, off64_t);
  static Function real = next_symbol<Function>("ftruncate64");
  if (tls_in_hook || length < 0) return real(fd, length);
  tls_in_hook = true;
  LifecycleToken token;
  collector().prepare_truncate_fd(&token, fd, static_cast<uint64_t>(length));
  tls_in_hook = false;
  const int result = real(fd, length);
  const int saved_errno = errno;
  tls_in_hook = true;
  collector().complete_truncate(&token, result, result == 0 ? 0 : saved_errno);
  tls_in_hook = false;
  errno = saved_errno;
  return result;
}

extern "C" int truncate(const char *path, off_t length) {
  using Function = int (*)(const char *, off_t);
  static Function real = next_symbol<Function>("truncate");
  if (tls_in_hook || length < 0) return real(path, length);
  tls_in_hook = true;
  LifecycleToken token;
  collector().prepare_truncate_path(&token, path, static_cast<uint64_t>(length));
  tls_in_hook = false;
  const int result = real(path, length);
  const int saved_errno = errno;
  tls_in_hook = true;
  collector().complete_truncate(&token, result, result == 0 ? 0 : saved_errno);
  tls_in_hook = false;
  errno = saved_errno;
  return result;
}

extern "C" int truncate64(const char *path, off64_t length) {
  using Function = int (*)(const char *, off64_t);
  static Function real = next_symbol<Function>("truncate64");
  if (tls_in_hook || length < 0) return real(path, length);
  tls_in_hook = true;
  LifecycleToken token;
  collector().prepare_truncate_path(&token, path, static_cast<uint64_t>(length));
  tls_in_hook = false;
  const int result = real(path, length);
  const int saved_errno = errno;
  tls_in_hook = true;
  collector().complete_truncate(&token, result, result == 0 ? 0 : saved_errno);
  tls_in_hook = false;
  errno = saved_errno;
  return result;
}

extern "C" int close(int fd) {
  using Function = int (*)(int);
  static Function real = next_symbol<Function>("close");
  if (!tls_in_hook) tls_fd_identities.erase(fd);
  return real(fd);
}

__attribute__((destructor)) static void atlas_z0a_destructor() { atlas_z0a_flush(); }
