#pragma once

#include <cstdint>
#include <limits>

// Stable ABI used by the LD_PRELOAD library and the two instrumented I/O
// engines.  The trace is intentionally request-oriented; 4 KiB page events
// are derived offline so request/page byte closure can be checked independently.

enum AtlasZ0APhase : uint16_t {
  ATLAS_Z0A_PHASE_OTHER = 0,
  ATLAS_Z0A_PHASE_LOAD = 1,
  ATLAS_Z0A_PHASE_INSERT = 2,
  ATLAS_Z0A_PHASE_DELETE = 3,
  ATLAS_Z0A_PHASE_VISIBILITY = 4,
  ATLAS_Z0A_PHASE_PUBLISH = 5,
  ATLAS_Z0A_PHASE_SHADOW_COPY = 6,
  ATLAS_Z0A_PHASE_REPAIR = 7,
  ATLAS_Z0A_PHASE_METADATA = 8,
};

enum AtlasZ0ASource : uint16_t {
  ATLAS_Z0A_SOURCE_UNKNOWN = 0,
  ATLAS_Z0A_SOURCE_LIBAIO_EXECUTE_IO = 1,
  ATLAS_Z0A_SOURCE_IOURING_EXECUTE_IO = 2,
  ATLAS_Z0A_SOURCE_WRITE = 3,
  ATLAS_Z0A_SOURCE_PWRITE = 4,
  ATLAS_Z0A_SOURCE_PWRITE64 = 5,
  ATLAS_Z0A_SOURCE_WRITEV = 6,
  ATLAS_Z0A_SOURCE_PWRITEV = 7,
  ATLAS_Z0A_SOURCE_SENDFILE = 8,
  ATLAS_Z0A_SOURCE_COPY_FILE_RANGE = 9,
};

enum AtlasZ0ARole : uint16_t {
  ATLAS_Z0A_ROLE_UNKNOWN = 0,
  ATLAS_Z0A_ROLE_PRIMARY_COMBINED = 1,
  ATLAS_Z0A_ROLE_SHADOW_COMBINED = 2,
  ATLAS_Z0A_ROLE_GRAPH = 3,
  ATLAS_Z0A_ROLE_VECTOR = 4,
  ATLAS_Z0A_ROLE_TAGS = 5,
  ATLAS_Z0A_ROLE_PQ = 6,
  ATLAS_Z0A_ROLE_MAP = 7,
  ATLAS_Z0A_ROLE_REORDERED_DERIVED = 8,
  ATLAS_Z0A_ROLE_DELETE_TOMBSTONE = 9,
  ATLAS_Z0A_ROLE_METADATA = 10,
  ATLAS_Z0A_ROLE_TEMPORARY = 11,
};

struct AtlasZ0AContext {
  uint64_t update_or_replacement_id = std::numeric_limits<uint64_t>::max();
  uint64_t batch_id = std::numeric_limits<uint64_t>::max();
  uint16_t phase = ATLAS_Z0A_PHASE_OTHER;
  uint16_t reserved = 0;
};

// This object must remain alive from kernel submission through completion. For
// libaio it is stored in iocb.data; for io_uring its address is SQE user_data.
struct AtlasZ0ATraceToken {
  uint64_t slot = std::numeric_limits<uint64_t>::max();
  uint64_t request_id = 0;
  uint64_t guard = 0;
};

extern "C" {
bool atlas_z0a_enabled();
void atlas_z0a_set_phase_name(const char *name);
void atlas_z0a_set_context(uint64_t update_or_replacement_id, uint64_t batch_id, uint16_t phase);
AtlasZ0AContext atlas_z0a_get_context();
void atlas_z0a_restore_context(AtlasZ0AContext context);

void atlas_z0a_prepare(AtlasZ0ATraceToken *token);
bool atlas_z0a_submit(AtlasZ0ATraceToken *token, uint16_t source_entrypoint, int fd,
                      uint64_t offset, uint64_t length);
void atlas_z0a_complete(AtlasZ0ATraceToken *token, int64_t returned_bytes,
                        int64_t completion_status);
void atlas_z0a_flush();
}

class AtlasZ0AScopedContext {
 public:
  explicit AtlasZ0AScopedContext(AtlasZ0AContext next) : prior_(atlas_z0a_get_context()) {
    atlas_z0a_restore_context(next);
  }
  ~AtlasZ0AScopedContext() { atlas_z0a_restore_context(prior_); }
  AtlasZ0AScopedContext(const AtlasZ0AScopedContext &) = delete;
  AtlasZ0AScopedContext &operator=(const AtlasZ0AScopedContext &) = delete;

 private:
  AtlasZ0AContext prior_;
};
