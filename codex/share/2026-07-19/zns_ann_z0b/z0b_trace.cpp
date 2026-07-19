// Z0B endpoint tracer: R2 write tracing plus fail-closed namespace lifecycle.
//
// The accepted R2 implementation remains untouched and is included as a
// frozen base.  This translation unit adds only namespace interposition needed
// by the long M3 endpoints.  Lifecycle source_entrypoint values are:
//   1 truncate/ftruncate (R2), 2 CREATE, 3 UNLINK, 4 OPEN_TRUNCATE.

#include <atomic>
#include <cerrno>
#include <cstdarg>
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

// Collector's storage is exposed only inside this derived translation unit so
// namespace records can reuse the exact R2 global sequence and object table.
#define private public
#include "../zns_ann_z0a_r2/timing/z0a_trace_r2.cpp"
#undef private

namespace {

thread_local bool z0b_namespace_guard = false;

enum : uint16_t {
  Z0B_LIFECYCLE_CREATE = 2,
  Z0B_LIFECYCLE_UNLINK = 3,
  Z0B_LIFECYCLE_OPEN_TRUNCATE = 4,
};

bool path_under_index(const char *path) {
  if (!path || !*path) return false;
  const char *root = std::getenv("ATLAS_Z0A_INDEX_ROOT");
  if (!root || !*root) return false;
  const size_t n = std::strlen(root);
  return std::strncmp(path, root, n) == 0 && (path[n] == 0 || path[n] == '/');
}

std::string at_path(int dirfd, const char *path) {
  if (!path || !*path || path[0] == '/' || dirfd == AT_FDCWD) return path ? std::string(path) : std::string();
  char link[64], base[4096];
  std::snprintf(link, sizeof(link), "/proc/self/fd/%d", dirfd);
  const ssize_t n = syscall(SYS_readlink, link, base, sizeof(base) - 1);
  if (n <= 0) return {};
  base[n] = 0;
  return std::string(base) + "/" + path;
}

void retag(LifecycleToken &token, uint16_t source) {
  if (!token.active || token.slot >= collector().lifecycle_capacity_) return;
  collector().lifecycle_records_[token.slot].source_entrypoint = source;
}

void erase_unlinked_identity(const struct stat &st) {
  const IdentityKey key{static_cast<uint64_t>(st.st_dev), static_cast<uint64_t>(st.st_ino)};
  std::lock_guard<std::mutex> lock(collector().objects_mu_);
  collector().objects_by_key_.erase(key);
}

template <typename Call>
int traced_open_common(const std::string &path, int flags, Call call) {
  if (z0b_namespace_guard || !path_under_index(path.c_str())) return call();
  z0b_namespace_guard = true;
  struct stat before{};
  const bool existed = syscall(SYS_stat, path.c_str(), &before) == 0;
  LifecycleToken trunc_token;
  if (existed && (flags & O_TRUNC)) {
    collector().prepare_truncate_path(&trunc_token, path.c_str(), 0);
    retag(trunc_token, Z0B_LIFECYCLE_OPEN_TRUNCATE);
  }
  z0b_namespace_guard = false;
  const int fd = call();
  const int saved = errno;
  z0b_namespace_guard = true;
  if (existed && (flags & O_TRUNC)) collector().complete_truncate(&trunc_token, fd >= 0 ? 0 : -1, fd >= 0 ? 0 : saved);
  if (fd >= 0 && !existed && (flags & O_CREAT)) {
    LifecycleToken create_token;
    collector().prepare_truncate_fd(&create_token, fd, 0);
    retag(create_token, Z0B_LIFECYCLE_CREATE);
    collector().complete_truncate(&create_token, 0, 0);
  }
  z0b_namespace_guard = false;
  errno = saved;
  return fd;
}

template <typename Call>
int traced_unlink_common(const std::string &path, Call call) {
  if (z0b_namespace_guard || !path_under_index(path.c_str())) return call();
  z0b_namespace_guard = true;
  struct stat before{};
  const bool existed = syscall(SYS_stat, path.c_str(), &before) == 0;
  LifecycleToken token;
  if (existed) {
    collector().prepare_truncate_path(&token, path.c_str(), 0);
    retag(token, Z0B_LIFECYCLE_UNLINK);
  }
  z0b_namespace_guard = false;
  const int result = call();
  const int saved = errno;
  z0b_namespace_guard = true;
  if (existed) collector().complete_truncate(&token, result, result == 0 ? 0 : saved);
  if (existed && result == 0) erase_unlinked_identity(before);
  z0b_namespace_guard = false;
  errno = saved;
  return result;
}

bool namespace_relevant_mode(const char *mode) {
  // Both "w" and "a" create a missing file; only "w" truncates an
  // existing one.  Keep the wrapper active for either case.
  return mode && (std::strchr(mode, 'w') || std::strchr(mode, 'a'));
}

[[noreturn]] void unsupported_namespace_mutation(const char *op, const char *a, const char *b = nullptr) {
  std::fprintf(stderr, "Z0B fail-closed: unsupported namespace mutation %s(%s%s%s) under index root\n",
               op, a ? a : "", b ? "," : "", b ? b : "");
  std::fflush(stderr);
  _exit(87);
}

}  // namespace

extern "C" int open(const char *path, int flags, ...) {
  using Fn = int (*)(const char *, int, ...);
  static Fn real = next_symbol<Fn>("open");
  mode_t mode = 0;
  if (flags & O_CREAT) { va_list ap; va_start(ap, flags); mode = static_cast<mode_t>(va_arg(ap, int)); va_end(ap); }
  return traced_open_common(path ? std::string(path) : std::string(), flags,
                            [&] { return (flags & O_CREAT) ? real(path, flags, mode) : real(path, flags); });
}

extern "C" int open64(const char *path, int flags, ...) {
  using Fn = int (*)(const char *, int, ...);
  static Fn real = next_symbol<Fn>("open64");
  mode_t mode = 0;
  if (flags & O_CREAT) { va_list ap; va_start(ap, flags); mode = static_cast<mode_t>(va_arg(ap, int)); va_end(ap); }
  return traced_open_common(path ? std::string(path) : std::string(), flags,
                            [&] { return (flags & O_CREAT) ? real(path, flags, mode) : real(path, flags); });
}

extern "C" int openat(int dirfd, const char *path, int flags, ...) {
  using Fn = int (*)(int, const char *, int, ...);
  static Fn real = next_symbol<Fn>("openat");
  mode_t mode = 0;
  if (flags & O_CREAT) { va_list ap; va_start(ap, flags); mode = static_cast<mode_t>(va_arg(ap, int)); va_end(ap); }
  const std::string absolute = at_path(dirfd, path);
  return traced_open_common(absolute, flags,
                            [&] { return (flags & O_CREAT) ? real(dirfd, path, flags, mode) : real(dirfd, path, flags); });
}

extern "C" int openat64(int dirfd, const char *path, int flags, ...) {
  using Fn = int (*)(int, const char *, int, ...);
  static Fn real = next_symbol<Fn>("openat64");
  mode_t mode = 0;
  if (flags & O_CREAT) { va_list ap; va_start(ap, flags); mode = static_cast<mode_t>(va_arg(ap, int)); va_end(ap); }
  const std::string absolute = at_path(dirfd, path);
  return traced_open_common(absolute, flags,
                            [&] { return (flags & O_CREAT) ? real(dirfd, path, flags, mode) : real(dirfd, path, flags); });
}

extern "C" int creat(const char *path, mode_t mode) { return open(path, O_WRONLY | O_CREAT | O_TRUNC, mode); }
extern "C" int creat64(const char *path, mode_t mode) { return open64(path, O_WRONLY | O_CREAT | O_TRUNC, mode); }

extern "C" FILE *fopen(const char *path, const char *mode) {
  using Fn = FILE *(*)(const char *, const char *);
  static Fn real = next_symbol<Fn>("fopen");
  if (!namespace_relevant_mode(mode) || z0b_namespace_guard || !path_under_index(path)) return real(path, mode);
  z0b_namespace_guard = true;
  struct stat before{};
  const bool existed = syscall(SYS_stat, path, &before) == 0;
  LifecycleToken trunc_token;
  if (existed && std::strchr(mode, 'w')) {
    collector().prepare_truncate_path(&trunc_token, path, 0);
    retag(trunc_token, Z0B_LIFECYCLE_OPEN_TRUNCATE);
  }
  FILE *file = real(path, mode);
  const int saved = errno;
  if (existed && std::strchr(mode, 'w')) collector().complete_truncate(&trunc_token, file ? 0 : -1, file ? 0 : saved);
  if (file && !existed) {
    LifecycleToken create_token;
    collector().prepare_truncate_fd(&create_token, fileno(file), 0);
    retag(create_token, Z0B_LIFECYCLE_CREATE);
    collector().complete_truncate(&create_token, 0, 0);
  }
  z0b_namespace_guard = false;
  errno = saved;
  return file;
}

extern "C" FILE *fopen64(const char *path, const char *mode) {
  using Fn = FILE *(*)(const char *, const char *);
  static Fn real = next_symbol<Fn>("fopen64");
  if (!namespace_relevant_mode(mode) || z0b_namespace_guard || !path_under_index(path)) return real(path, mode);
  z0b_namespace_guard = true;
  struct stat before{};
  const bool existed = syscall(SYS_stat, path, &before) == 0;
  LifecycleToken trunc_token;
  if (existed && std::strchr(mode, 'w')) {
    collector().prepare_truncate_path(&trunc_token, path, 0);
    retag(trunc_token, Z0B_LIFECYCLE_OPEN_TRUNCATE);
  }
  FILE *file = real(path, mode);
  const int saved = errno;
  if (existed && std::strchr(mode, 'w')) collector().complete_truncate(&trunc_token, file ? 0 : -1, file ? 0 : saved);
  if (file && !existed) {
    LifecycleToken create_token;
    collector().prepare_truncate_fd(&create_token, fileno(file), 0);
    retag(create_token, Z0B_LIFECYCLE_CREATE);
    collector().complete_truncate(&create_token, 0, 0);
  }
  z0b_namespace_guard = false;
  errno = saved;
  return file;
}

extern "C" int unlink(const char *path) {
  using Fn = int (*)(const char *);
  static Fn real = next_symbol<Fn>("unlink");
  return traced_unlink_common(path ? std::string(path) : std::string(), [&] { return real(path); });
}

extern "C" int unlinkat(int dirfd, const char *path, int flags) {
  using Fn = int (*)(int, const char *, int);
  static Fn real = next_symbol<Fn>("unlinkat");
  const std::string absolute = at_path(dirfd, path);
  return traced_unlink_common(absolute, [&] { return real(dirfd, path, flags); });
}

extern "C" int remove(const char *path) {
  using Fn = int (*)(const char *);
  static Fn real = next_symbol<Fn>("remove");
  return traced_unlink_common(path ? std::string(path) : std::string(), [&] { return real(path); });
}

extern "C" int rename(const char *old_path, const char *new_path) {
  using Fn = int (*)(const char *, const char *);
  static Fn real = next_symbol<Fn>("rename");
  if (path_under_index(old_path) || path_under_index(new_path)) unsupported_namespace_mutation("rename", old_path, new_path);
  return real(old_path, new_path);
}

extern "C" int renameat(int old_dirfd, const char *old_path, int new_dirfd, const char *new_path) {
  using Fn = int (*)(int, const char *, int, const char *);
  static Fn real = next_symbol<Fn>("renameat");
  const std::string old_absolute = at_path(old_dirfd, old_path);
  const std::string new_absolute = at_path(new_dirfd, new_path);
  if (path_under_index(old_absolute.c_str()) || path_under_index(new_absolute.c_str()))
    unsupported_namespace_mutation("renameat", old_absolute.c_str(), new_absolute.c_str());
  return real(old_dirfd, old_path, new_dirfd, new_path);
}

extern "C" int renameat2(int old_dirfd, const char *old_path, int new_dirfd, const char *new_path,
                          unsigned int flags) {
  using Fn = int (*)(int, const char *, int, const char *, unsigned int);
  static Fn real = next_symbol<Fn>("renameat2");
  const std::string old_absolute = at_path(old_dirfd, old_path);
  const std::string new_absolute = at_path(new_dirfd, new_path);
  if (path_under_index(old_absolute.c_str()) || path_under_index(new_absolute.c_str()))
    unsupported_namespace_mutation("renameat2", old_absolute.c_str(), new_absolute.c_str());
  return real(old_dirfd, old_path, new_dirfd, new_path, flags);
}

extern "C" int link(const char *old_path, const char *new_path) {
  using Fn = int (*)(const char *, const char *);
  static Fn real = next_symbol<Fn>("link");
  if (path_under_index(old_path) || path_under_index(new_path)) unsupported_namespace_mutation("link", old_path, new_path);
  return real(old_path, new_path);
}

extern "C" int linkat(int old_dirfd, const char *old_path, int new_dirfd, const char *new_path, int flags) {
  using Fn = int (*)(int, const char *, int, const char *, int);
  static Fn real = next_symbol<Fn>("linkat");
  const std::string old_absolute = at_path(old_dirfd, old_path);
  const std::string new_absolute = at_path(new_dirfd, new_path);
  if (path_under_index(old_absolute.c_str()) || path_under_index(new_absolute.c_str()))
    unsupported_namespace_mutation("linkat", old_absolute.c_str(), new_absolute.c_str());
  return real(old_dirfd, old_path, new_dirfd, new_path, flags);
}

extern "C" int symlink(const char *target, const char *link_path) {
  using Fn = int (*)(const char *, const char *);
  static Fn real = next_symbol<Fn>("symlink");
  if (path_under_index(link_path)) unsupported_namespace_mutation("symlink", target, link_path);
  return real(target, link_path);
}

extern "C" int symlinkat(const char *target, int new_dirfd, const char *link_path) {
  using Fn = int (*)(const char *, int, const char *);
  static Fn real = next_symbol<Fn>("symlinkat");
  const std::string absolute = at_path(new_dirfd, link_path);
  if (path_under_index(absolute.c_str())) unsupported_namespace_mutation("symlinkat", target, absolute.c_str());
  return real(target, new_dirfd, link_path);
}
