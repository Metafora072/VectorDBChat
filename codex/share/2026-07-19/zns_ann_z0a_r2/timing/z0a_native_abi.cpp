#include "z0a_trace.h"

// ABI-only library for the NATIVE arm.  The instrumented canary binary has
// direct references to the context API, so this library satisfies those
// symbols without defining any POSIX interposer or performing identity,
// buffering, timestamping, record capture, or output.

namespace {
thread_local AtlasZ0AContext context;
}

extern "C" bool atlas_z0a_enabled() { return false; }
extern "C" void atlas_z0a_set_phase_name(const char *) {}
extern "C" void atlas_z0a_set_context(uint64_t update, uint64_t batch, uint16_t phase) {
  context.update_or_replacement_id = update;
  context.batch_id = batch;
  context.phase = phase;
}
extern "C" AtlasZ0AContext atlas_z0a_get_context() { return context; }
extern "C" void atlas_z0a_restore_context(AtlasZ0AContext next) { context = next; }
extern "C" void atlas_z0a_prepare(AtlasZ0ATraceToken *token) {
  if (!token) return;
  token->slot = std::numeric_limits<uint64_t>::max();
  token->request_id = 0;
  token->guard = 0;
}
extern "C" bool atlas_z0a_submit(AtlasZ0ATraceToken *, uint16_t, int, uint64_t, uint64_t) {
  return false;
}
extern "C" void atlas_z0a_complete(AtlasZ0ATraceToken *, int64_t, int64_t) {}
extern "C" void atlas_z0a_flush() {}
