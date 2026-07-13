#include <algorithm>
#include <cstdint>
#include <iostream>
#include <numeric>
#include <random>
#include <vector>

int main() {
  constexpr uint32_t kPoints = 900000;
  constexpr uint32_t kExpected[] = {858547, 590351, 544834, 243196, 580277,
                                    86554, 820409, 876942, 341223, 305245};
  std::vector<uint32_t> ids(kPoints);
  for (uint64_t seed = 0; seed <= 10000; ++seed) {
    std::iota(ids.begin(), ids.end(), 0);
    std::mt19937_64 rng(seed);
    std::shuffle(ids.begin(), ids.end(), rng);
    if (std::equal(std::begin(kExpected), std::end(kExpected), ids.begin())) {
      std::cout << seed << '\n';
      return 0;
    }
  }
  return 1;
}
