#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <stdexcept>
#include <span>
#include <string>
#include <string_view>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unordered_map>
#include <tuple>
#include <type_traits>
#include <unistd.h>

namespace z0b {

struct Error : std::runtime_error {
  using std::runtime_error::runtime_error;
};

#pragma pack(push, 1)
struct InitialHeader {
  char magic[8];
  uint32_t version;
  uint32_t record_bytes;
  uint64_t record_count;
  uint64_t run_hash;
};

struct InitialRecord {
  uint64_t object_incarnation;
  uint64_t aligned_offset;
  uint32_t page_bytes;
  uint16_t role;
  uint16_t reserved;
};

struct NormalHeader {
  char magic[8];
  uint32_t version;
  uint32_t record_bytes;
  uint64_t event_count;
  uint64_t request_count;
};

struct NormalRecord {
  uint64_t global_seq;
  uint64_t request_id;
  uint64_t object_incarnation;
  uint64_t aligned_offset;
  uint64_t update_id;
  uint64_t batch_id;
  uint32_t fragment_bytes;
  uint32_t page_index_within_request;
  uint16_t phase;
  uint16_t role;
  uint16_t source;
  uint16_t reserved;
};

struct LifecycleHeader {
  char magic[8];
  uint32_t version;
  uint32_t record_bytes;
  uint64_t event_count;
  uint64_t run_hash;
};

struct LifecycleRecord {
  uint64_t global_seq;
  uint64_t object_incarnation;
  uint64_t new_size_bytes;
  uint64_t update_id;
  uint64_t batch_id;
  uint16_t kind;  // 1 = shrinking/expanding TRUNCATE
  uint16_t role;
  uint32_t reserved;
};
#pragma pack(pop)

static_assert(sizeof(InitialHeader) == 32);
static_assert(sizeof(InitialRecord) == 24);
static_assert(sizeof(NormalHeader) == 32);
static_assert(sizeof(NormalRecord) == 64);
static_assert(sizeof(LifecycleHeader) == 32);
static_assert(sizeof(LifecycleRecord) == 48);

struct Key {
  uint64_t object;
  uint64_t offset;
  friend bool operator==(const Key&, const Key&) = default;
};

struct KeyHash {
  static uint64_t mix(uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
  }
  size_t operator()(const Key& key) const {
    return static_cast<size_t>(mix(key.object) ^ (mix(key.offset) << 1));
  }
};

struct MappedFile {
  int fd = -1;
  size_t bytes = 0;
  const std::byte* data = nullptr;

  explicit MappedFile(const std::filesystem::path& path) {
    fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
    if (fd < 0) throw Error("open failed: " + path.string() + ": " + std::strerror(errno));
    struct stat st {};
    if (::fstat(fd, &st) != 0 || st.st_size < 0) throw Error("fstat failed: " + path.string());
    bytes = static_cast<size_t>(st.st_size);
    if (bytes == 0) throw Error("empty input: " + path.string());
    void* value = ::mmap(nullptr, bytes, PROT_READ, MAP_PRIVATE, fd, 0);
    if (value == MAP_FAILED) throw Error("mmap failed: " + path.string());
    data = static_cast<const std::byte*>(value);
  }
  MappedFile(const MappedFile&) = delete;
  MappedFile& operator=(const MappedFile&) = delete;
  ~MappedFile() {
    if (data) ::munmap(const_cast<std::byte*>(data), bytes);
    if (fd >= 0) ::close(fd);
  }

  template <class Header, class Record>
  std::pair<const Header*, std::span<const Record>> records(std::string_view magic) const {
    if (bytes < sizeof(Header)) throw Error("short binary header");
    const auto* header = reinterpret_cast<const Header*>(data);
    if (std::memcmp(header->magic, magic.data(), 8) != 0 || header->version != 1 ||
        header->record_bytes != sizeof(Record)) {
      throw Error("binary ABI mismatch");
    }
    const uint64_t count = [&] {
      if constexpr (std::is_same_v<Header, InitialHeader>) return header->record_count;
      else return header->event_count;
    }();
    const __uint128_t expected = sizeof(Header) + static_cast<__uint128_t>(count) * sizeof(Record);
    if (expected != bytes) throw Error("binary size/count closure failure");
    const auto* first = reinterpret_cast<const Record*>(data + sizeof(Header));
    return {header, std::span<const Record>(first, static_cast<size_t>(count))};
  }
};

struct Args {
  std::unordered_map<std::string, std::string> values;

  Args(int argc, char** argv) {
    for (int i = 1; i < argc; i += 2) {
      if (i + 1 >= argc || std::string_view(argv[i]).substr(0, 2) != "--") {
        throw Error("arguments must be --key value pairs");
      }
      values.emplace(std::string(argv[i] + 2), argv[i + 1]);
    }
  }
  const std::string& need(const std::string& name) const {
    auto it = values.find(name);
    if (it == values.end()) throw Error("missing --" + name);
    return it->second;
  }
  std::string get(const std::string& name, std::string fallback) const {
    auto it = values.find(name);
    return it == values.end() ? std::move(fallback) : it->second;
  }
  uint64_t u64(const std::string& name, uint64_t fallback = 0, bool required = true) const {
    auto it = values.find(name);
    if (it == values.end()) {
      if (required) throw Error("missing --" + name);
      return fallback;
    }
    size_t used = 0;
    const auto result = std::stoull(it->second, &used);
    if (used != it->second.size()) throw Error("bad integer --" + name);
    return result;
  }
};

inline bool key_less(const InitialRecord& a, const InitialRecord& b) {
  return std::tie(a.role, a.object_incarnation, a.aligned_offset) <
         std::tie(b.role, b.object_incarnation, b.aligned_offset);
}

// Fixed-size, order-sensitive fingerprint of every logical page transition
// caused by one event. The enclosing SHA-256 stream also binds the transition
// count, event identity, and complete post-event counters.
struct TransitionDelta {
  uint64_t object = 0, offset = 0;
  uint32_t old_version = 0, old_zone = UINT32_MAX, old_slot = UINT32_MAX;
  uint32_t new_version = 0, new_zone = UINT32_MAX, new_slot = UINT32_MAX;
  uint16_t role = 0;
  uint8_t old_live = 0, new_live = 0, reason = 0;
};

inline uint64_t audit_mix64(uint64_t x) {
  x += 0x9e3779b97f4a7c15ULL;
  x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
  x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}

struct DeltaAccumulator {
  uint64_t count = 0;
  uint64_t lo = 0x243f6a8885a308d3ULL;
  uint64_t hi = 0x13198a2e03707344ULL;

  void add(const TransitionDelta& d) {
    const uint64_t words[] = {
      d.object, d.offset, d.old_version, d.old_zone, d.old_slot,
      d.new_version, d.new_zone, d.new_slot, d.role,
      d.old_live, d.new_live, d.reason,
    };
    ++count;
    for (uint64_t value : words) {
      lo = (lo ^ value) * 0x100000001b3ULL;
      hi += value + 0x9e3779b97f4a7c15ULL;
      hi = ((hi << 27) | (hi >> 37)) * 0x94d049bb133111ebULL;
    }
  }
};

#pragma pack(push, 1)
struct TransitionAuditRecord {
  uint64_t ordinal, seq;
  int64_t page;
  uint8_t op;
  uint64_t argument, update, batch;
  uint32_t destination;
  uint8_t gc;
  uint32_t victim, moved;
  uint64_t delta_count, delta_lo, delta_hi;
  uint64_t user, copied, resets, app, fragment, rmw, zero;
  uint64_t live, invalid, free;
  int64_t head;
  uint8_t head_state;
  uint64_t head_write_pointer, head_live;
};
#pragma pack(pop)
static_assert(sizeof(TransitionAuditRecord) == 191);

inline std::string json_escape(std::string_view input) {
  std::string out;
  out.reserve(input.size() + 8);
  for (char ch : input) {
    if (ch == '\\' || ch == '"') { out.push_back('\\'); out.push_back(ch); }
    else if (ch == '\n') out += "\\n";
    else out.push_back(ch);
  }
  return out;
}

}  // namespace z0b
