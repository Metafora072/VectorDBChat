#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <libaio.h>
#include <liburing.h>
#include <linux/io_uring.h>
#include <mutex>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

namespace {
constexpr uint64_t kPage = 4096;

enum class Phase : uint8_t {
  Other = 0, Load, InsertNeighborRepair, Delete, Visibility, PublishSave, Metadata
};

const char *phase_name(Phase p) {
  switch (p) {
    case Phase::Load: return "load";
    case Phase::InsertNeighborRepair: return "insert_neighbor_repair";
    case Phase::Delete: return "delete";
    case Phase::Visibility: return "visibility";
    case Phase::PublishSave: return "publish_save";
    case Phase::Metadata: return "metadata";
    default: return "other";
  }
}

struct Bucket {
  uint64_t requested_bytes = 0;
  uint64_t write_calls = 0;
  uint64_t page_touches = 0;
  uint64_t fsync_calls = 0;
  uint64_t fdatasync_calls = 0;
};

struct PageKey {
  uint32_t bucket;
  uint64_t page;
  bool operator==(const PageKey &o) const { return bucket == o.bucket && page == o.page; }
};

struct PageHash {
  size_t operator()(const PageKey &v) const {
    uint64_t x = v.page ^ (uint64_t(v.bucket) * 0x9e3779b97f4a7c15ULL);
    x ^= x >> 30; x *= 0xbf58476d1ce4e5b9ULL;
    x ^= x >> 27; x *= 0x94d049bb133111ebULL;
    return size_t(x ^ (x >> 31));
  }
};

struct BucketMeta {
  Phase phase;
  std::string component;
  std::string path;
};

struct RoleStats {
  uint64_t requested_bytes = 0;
  uint64_t page_touches = 0;
  std::unordered_map<uint64_t, uint32_t> pages;
};

struct State {
  std::mutex mu;
  std::atomic<uint8_t> phase{uint8_t(Phase::Other)};
  std::string index_root;
  std::string output;
  std::unordered_map<int, std::string> fd_paths;
  std::unordered_map<std::string, uint32_t> bucket_ids;
  std::vector<BucketMeta> metas;
  std::vector<Bucket> buckets;
  std::unordered_map<PageKey, uint32_t, PageHash> pages;
  std::unordered_map<std::string, RoleStats> roles;
  std::atomic<bool> flushed{false};
};

State &state() {
  static State *s = [] {
    auto *value = new State;
    if (const char *p = getenv("ATLAS_M0_INDEX_ROOT")) value->index_root = p;
    if (const char *p = getenv("ATLAS_M0_PROFILE_OUTPUT")) value->output = p;
    return value;
  }();
  return *s;
}

thread_local bool in_hook = false;

template <typename T> T next_symbol(const char *name) {
  return reinterpret_cast<T>(dlsym(RTLD_NEXT, name));
}

std::string json_escape(const std::string &s) {
  std::ostringstream o;
  for (unsigned char c : s) {
    switch (c) {
      case '\\': o << "\\\\"; break;
      case '"': o << "\\\""; break;
      case '\n': o << "\\n"; break;
      case '\r': o << "\\r"; break;
      case '\t': o << "\\t"; break;
      default:
        if (c < 0x20) {
          const char *hex = "0123456789abcdef";
          o << "\\u00" << hex[c >> 4] << hex[c & 15];
        } else o << c;
    }
  }
  return o.str();
}

std::string fd_path_locked(State &s, int fd) {
  auto it = s.fd_paths.find(fd);
  if (it != s.fd_paths.end()) return it->second;
  char link[64], target[4096];
  snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
  ssize_t n = syscall(SYS_readlink, link, target, sizeof(target) - 1);
  if (n <= 0) return {};
  target[n] = 0;
  std::string path(target);
  constexpr const char deleted[] = " (deleted)";
  if (path.size() >= sizeof(deleted) - 1 &&
      path.compare(path.size() - sizeof(deleted) + 1, sizeof(deleted) - 1, deleted) == 0)
    path.resize(path.size() - sizeof(deleted) + 1);
  s.fd_paths.emplace(fd, path);
  return path;
}

bool under_root(const State &s, const std::string &path) {
  if (s.index_root.empty() || path.size() < s.index_root.size()) return false;
  if (path.compare(0, s.index_root.size(), s.index_root) != 0) return false;
  return path.size() == s.index_root.size() || path[s.index_root.size()] == '/';
}

std::string component_for(const std::string &path, uint64_t offset) {
  const auto slash = path.find_last_of('/');
  const std::string name = slash == std::string::npos ? path : path.substr(slash + 1);
  if (name.find(".tags") != std::string::npos || name.find("reorder_map") != std::string::npos ||
      name.find("index_map") != std::string::npos) return "metadata";
  if (name.find("delete") != std::string::npos || name.find("tombstone") != std::string::npos ||
      name.find("journal") != std::string::npos) return "delete_tombstone";
  if (name.find("disk_index_graph") != std::string::npos ||
      name.find("reordered_disk_index_graph") != std::string::npos) return "graph";
  if (name.find("disk_index_data") != std::string::npos || name.find("pq_") != std::string::npos ||
      name.find("vector") != std::string::npos) return "vector";
  if (name.find("_disk.index") != std::string::npos) {
    return offset < kPage ? "metadata" : "graph_vector_combined";
  }
  return "other";
}

uint32_t bucket_locked(State &s, Phase phase, const std::string &component, const std::string &path) {
  std::string key = std::to_string(unsigned(phase)) + "\n" + component + "\n" + path;
  auto it = s.bucket_ids.find(key);
  if (it != s.bucket_ids.end()) return it->second;
  uint32_t id = s.buckets.size();
  s.bucket_ids.emplace(std::move(key), id);
  s.metas.push_back({phase, component, path});
  s.buckets.emplace_back();
  return id;
}

void record_write(int fd, uint64_t offset, uint64_t len) {
  if (!len || in_hook) return;
  in_hook = true;
  State &s = state();
  std::lock_guard<std::mutex> lock(s.mu);
  const std::string path = fd_path_locked(s, fd);
  if (!under_root(s, path)) { in_hook = false; return; }
  std::string component = component_for(path, offset);
  Phase phase = Phase(s.phase.load(std::memory_order_relaxed));
  if (phase != Phase::Load && phase != Phase::PublishSave && component == "metadata") phase = Phase::Metadata;
  if (component == "delete_tombstone") phase = Phase::Delete;
  uint32_t id = bucket_locked(s, phase, component, path);
  Bucket &b = s.buckets[id];
  b.requested_bytes += len;
  b.write_calls++;
  const uint64_t first = offset / kPage;
  const uint64_t last = (offset + len - 1) / kPage;
  for (uint64_t page = first; page <= last; ++page) {
    ++s.pages[{id, page}];
    ++b.page_touches;
  }
  in_hook = false;
}

void record_sync(int fd, bool data_only) {
  if (in_hook) return;
  in_hook = true;
  State &s = state();
  std::lock_guard<std::mutex> lock(s.mu);
  const std::string path = fd_path_locked(s, fd);
  if (under_root(s, path)) {
    Phase phase = Phase(s.phase.load(std::memory_order_relaxed));
    std::string component = component_for(path, 0);
    uint32_t id = bucket_locked(s, phase, component, path);
    if (data_only) ++s.buckets[id].fdatasync_calls; else ++s.buckets[id].fsync_calls;
  }
  in_hook = false;
}

void set_phase(const char *name) {
  if (!name) return;
  Phase p = Phase::Other;
  std::string n(name);
  if (n == "clone_ready" || n == "load") p = Phase::Load;
  else if (n == "insert" || n == "ingest_begin" || n == "insert_neighbor_repair") p = Phase::InsertNeighborRepair;
  else if (n == "delete") p = Phase::Delete;
  else if (n == "online_visibility_probe_begin" || n == "visibility") p = Phase::Visibility;
  else if (n == "publish_begin" || n == "publish_save") p = Phase::PublishSave;
  else if (n == "metadata") p = Phase::Metadata;
  state().phase.store(uint8_t(p), std::memory_order_relaxed);
}

void flush() {
  State &s = state();
  if (s.output.empty() || s.flushed.exchange(true)) return;
  std::lock_guard<std::mutex> lock(s.mu);
  std::vector<uint64_t> unique(s.buckets.size()), rewritten(s.buckets.size()), max_touches(s.buckets.size());
  std::vector<uint64_t> once(s.buckets.size());
  for (const auto &entry : s.pages) {
    ++unique[entry.first.bucket];
    if (entry.second == 1) ++once[entry.first.bucket];
    else ++rewritten[entry.first.bucket];
    if (entry.second > max_touches[entry.first.bucket]) max_touches[entry.first.bucket] = entry.second;
  }
  std::ostringstream o;
  o << "{\n  \"schema\": \"dynamic-vamana-write-attribution-m0-v1\",\n"
    << "  \"index_root\": \"" << json_escape(s.index_root) << "\",\n"
    << "  \"buckets\": [\n";
  for (size_t i = 0; i < s.buckets.size(); ++i) {
    const Bucket &b = s.buckets[i]; const BucketMeta &m = s.metas[i];
    if (i) o << ",\n";
    o << "    {\"phase\":\"" << phase_name(m.phase) << "\",\"component\":\""
      << json_escape(m.component) << "\",\"path\":\"" << json_escape(m.path)
      << "\",\"requested_bytes\":" << b.requested_bytes << ",\"write_calls\":" << b.write_calls
      << ",\"unique_4k_pages\":" << unique[i] << ",\"page_write_touches\":" << b.page_touches
      << ",\"pages_written_once\":" << once[i] << ",\"pages_rewritten\":" << rewritten[i]
      << ",\"max_page_writes\":" << max_touches[i] << ",\"page_rewrite_factor\":"
      << (unique[i] ? double(b.page_touches) / double(unique[i]) : 0.0)
      << ",\"fsync_count\":" << b.fsync_calls << ",\"fdatasync_count\":" << b.fdatasync_calls << "}";
  }
  o << "\n  ],\n  \"logical_rmw_roles\": [\n";
  bool first = true;
  for (const auto &entry : s.roles) {
    if (!first) o << ",\n";
    first = false;
    uint64_t rewritten_pages = 0, max_writes = 0;
    for (const auto &page : entry.second.pages) {
      if (page.second > 1) ++rewritten_pages;
      if (page.second > max_writes) max_writes = page.second;
    }
    o << "    {\"role\":\"" << json_escape(entry.first) << "\",\"requested_bytes\":"
      << entry.second.requested_bytes << ",\"unique_4k_pages\":" << entry.second.pages.size()
      << ",\"page_write_touches\":" << entry.second.page_touches << ",\"pages_rewritten\":"
      << rewritten_pages << ",\"max_page_writes\":" << max_writes << ",\"page_rewrite_factor\":"
      << (entry.second.pages.empty() ? 0.0 : double(entry.second.page_touches) / entry.second.pages.size()) << "}";
  }
  o << "\n  ]\n}\n";
  const std::string data = o.str();
  int fd = syscall(SYS_openat, AT_FDCWD, s.output.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
  if (fd < 0) return;
  size_t done = 0;
  while (done < data.size()) {
    ssize_t n = syscall(SYS_write, fd, data.data() + done, data.size() - done);
    if (n <= 0) break;
    done += size_t(n);
  }
  syscall(SYS_fsync, fd);
  syscall(SYS_close, fd);
}
}

extern "C" void m0_set_phase(const char *name) { set_phase(name); }

extern "C" void m0_record_role_page(const char *role, uint64_t offset, uint64_t len) {
  if (!role || !len || in_hook) return;
  in_hook = true;
  State &s = state();
  std::lock_guard<std::mutex> lock(s.mu);
  auto &r = s.roles[role];
  r.requested_bytes += len;
  uint64_t first = offset / kPage, last = (offset + len - 1) / kPage;
  for (uint64_t page = first; page <= last; ++page) { ++r.pages[page]; ++r.page_touches; }
  in_hook = false;
}

extern "C" ssize_t write(int fd, const void *buf, size_t count) {
  using Fn = ssize_t (*)(int, const void *, size_t); static Fn real = next_symbol<Fn>("write");
  ssize_t rc = real(fd, buf, count); if (rc > 0) { off_t end = lseek(fd, 0, SEEK_CUR); record_write(fd, end >= rc ? uint64_t(end - rc) : 0, rc); } return rc;
}
extern "C" ssize_t pwrite(int fd, const void *buf, size_t count, off_t off) {
  using Fn = ssize_t (*)(int, const void *, size_t, off_t); static Fn real = next_symbol<Fn>("pwrite");
  ssize_t rc = real(fd, buf, count, off); if (rc > 0) record_write(fd, off, rc); return rc;
}
extern "C" ssize_t pwrite64(int fd, const void *buf, size_t count, off64_t off) {
  using Fn = ssize_t (*)(int, const void *, size_t, off64_t); static Fn real = next_symbol<Fn>("pwrite64");
  ssize_t rc = real(fd, buf, count, off); if (rc > 0) record_write(fd, off, rc); return rc;
}
extern "C" ssize_t writev(int fd, const struct iovec *iov, int n) {
  using Fn = ssize_t (*)(int, const struct iovec *, int); static Fn real = next_symbol<Fn>("writev");
  ssize_t rc = real(fd, iov, n); if (rc > 0) { off_t end = lseek(fd, 0, SEEK_CUR); record_write(fd, end >= rc ? uint64_t(end - rc) : 0, rc); } return rc;
}
extern "C" ssize_t pwritev(int fd, const struct iovec *iov, int n, off_t off) {
  using Fn = ssize_t (*)(int, const struct iovec *, int, off_t); static Fn real = next_symbol<Fn>("pwritev");
  ssize_t rc = real(fd, iov, n, off); if (rc > 0) record_write(fd, off, rc); return rc;
}
extern "C" int fsync(int fd) { using Fn = int (*)(int); static Fn real = next_symbol<Fn>("fsync"); int rc = real(fd); if (!rc) record_sync(fd, false); return rc; }
extern "C" int fdatasync(int fd) { using Fn = int (*)(int); static Fn real = next_symbol<Fn>("fdatasync"); int rc = real(fd); if (!rc) record_sync(fd, true); return rc; }
extern "C" int close(int fd) {
  using Fn = int (*)(int); static Fn real = next_symbol<Fn>("close");
  if (!in_hook) { in_hook = true; State &s = state(); std::lock_guard<std::mutex> lock(s.mu); s.fd_paths.erase(fd); in_hook = false; }
  return real(fd);
}

extern "C" int io_submit(io_context_t ctx, long nr, struct iocb **ios) {
  using Fn = int (*)(io_context_t, long, struct iocb **); static Fn real = next_symbol<Fn>("io_submit");
  struct Req { int fd; uint64_t off; uint64_t len; }; std::vector<Req> reqs;
  if (!in_hook) {
    reqs.reserve(nr > 0 ? size_t(nr) : 0);
    for (long i = 0; i < nr; ++i) {
      iocb *cb = ios[i]; if (!cb) { reqs.push_back({-1,0,0}); continue; }
      uint64_t len = 0, off = 0;
      if (cb->aio_lio_opcode == IO_CMD_PWRITE) { len = cb->u.c.nbytes; off = cb->u.c.offset; }
      else if (cb->aio_lio_opcode == IO_CMD_PWRITEV) {
        const iovec *v = cb->u.v.vec; for (unsigned long j = 0; j < cb->u.v.nr; ++j) len += v[j].iov_len; off = cb->u.v.offset;
      }
      reqs.push_back({cb->aio_fildes, off, len});
    }
  }
  int rc = real(ctx, nr, ios);
  if (rc > 0) for (int i = 0; i < rc && i < int(reqs.size()); ++i) if (reqs[i].fd >= 0 && reqs[i].len) record_write(reqs[i].fd, reqs[i].off, reqs[i].len);
  return rc;
}

extern "C" int io_uring_submit(struct io_uring *ring) {
  using Fn = int (*)(struct io_uring *); static Fn real = next_symbol<Fn>("io_uring_submit");
  struct Req { int fd; uint64_t off; uint64_t len; }; std::vector<Req> reqs;
  if (!in_hook && ring) {
    unsigned head = ring->sq.sqe_head, tail = ring->sq.sqe_tail;
    reqs.reserve(tail - head);
    for (unsigned i = head; i != tail; ++i) {
      io_uring_sqe &sqe = ring->sq.sqes[i & ring->sq.ring_mask]; uint64_t len = 0;
      if (sqe.opcode == IORING_OP_WRITE || sqe.opcode == IORING_OP_WRITE_FIXED) len = sqe.len;
      else if (sqe.opcode == IORING_OP_WRITEV) { const iovec *v = reinterpret_cast<const iovec *>(sqe.addr); for (unsigned j = 0; j < sqe.len; ++j) len += v[j].iov_len; }
      reqs.push_back({sqe.fd, sqe.off, len});
    }
  }
  int rc = real(ring);
  if (rc > 0) for (int i = 0; i < rc && i < int(reqs.size()); ++i) if (reqs[i].fd >= 0 && reqs[i].len) record_write(reqs[i].fd, reqs[i].off, reqs[i].len);
  return rc;
}

__attribute__((destructor)) static void m0_profiler_fini() { flush(); }
