#include "m3_lifecycle.h"
#include <cassert>
#include <string>

int main() {
  using atlas_m3::Lifecycle;
  assert(std::string(atlas_m3::classification(Lifecycle::generated)) == "superseded_before_enqueue");
  assert(std::string(atlas_m3::classification(Lifecycle::queued)) == "superseded_while_queued");
  assert(std::string(atlas_m3::classification(Lifecycle::inflight)) == "superseded_while_inflight");
  assert(std::string(atlas_m3::classification(Lifecycle::completed)) == "repeat_after_completion_before_barrier");
  assert(std::string(atlas_m3::classification(Lifecycle::barrier)) == "repeat_after_barrier");
  return 0;
}
