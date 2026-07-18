#include "m2_metrics.h"

int main() {
  atlas_m2::configure({"synthetic", "memory-only", 32, 75, 160, 16, 1.2, 128, 644, 6, 0});
  atlas_m2::record({3, 2, 1, 2, 2, {10, 11}, {10, 11}, false, {10, 11}});
  atlas_m2::record({2, 2, 0, 2, 2, {10, 12}, {12}, true, {12}});
  atlas_m2::write_once();
  return 0;
}
