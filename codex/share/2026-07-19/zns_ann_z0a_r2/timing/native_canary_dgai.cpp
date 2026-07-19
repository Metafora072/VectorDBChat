// Z0A preflight driver: the artifact's real update/save APIs and libaio engine
// are retained, while the tiny workload is made serial and fully identified.
#define main dgai_legacy_overall_performance_main
#include "overall_performance.cpp"
#undef main

#include <cstdlib>
#include <fstream>

extern "C" void m0_set_phase(const char *) __attribute__((weak));
extern "C" void r2_oracle_force_link();

namespace {
uint64_t mono_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch()).count();
}
void mark(const char *name) {
  if (m0_set_phase) m0_set_phase(name);
  const char *path = std::getenv("ATLAS_W1_MARKERS");
  if (!path || !*path) throw std::runtime_error("ATLAS_W1_MARKERS is required");
  std::ofstream out(path, std::ios::app);
  if (!out) throw std::runtime_error("cannot open marker file");
  out << "{\"marker\":\"" << name << "\",\"monotonic_ns\":" << mono_ns() << "}\n";
}
template <typename T>
void run(const std::string &data, const std::string &prefix, const std::string &trace) {
  pipeann::Parameters parameters;
  parameters.Set<unsigned>("L_disk", 75); parameters.Set<unsigned>("R_disk", 32);
  parameters.Set<float>("alpha_disk", 1.2); parameters.Set<unsigned>("C", 160);
  parameters.Set<unsigned>("beamwidth", 16); parameters.Set<unsigned>("nodes_to_cache", 0);
  parameters.Set<unsigned>("num_threads", 32);
  pipeann::DistanceL2 distance;
  mark("clone_ready");
  pipeann::DynamicSSDIndex<T, unsigned> index(parameters, prefix, prefix, &distance, pipeann::Metric::L2, 2, 0);
  index._disk_index->reader->close();
  index._disk_index->reader->open(prefix + "_disk.index", true, false);
  mark("index_loaded");
  std::vector<T> vectors; std::vector<unsigned> deletes, inserts;
  get_atlas_trace<T, unsigned>(data, trace.c_str(), deletes, inserts, vectors);
  if (deletes.size() != inserts.size()) throw std::runtime_error("replacement trace shape mismatch");
  mark("ingest_begin");
  for (size_t i = 0; i < inserts.size(); ++i) {
    index.insert(vectors.data() + 128 * i, inserts[i]);
    atlas_m3::barrier();
  }
  for (size_t i = 0; i < deletes.size(); ++i) {
    index.lazy_delete(deletes[i]);
  }
  mark("ingest_end");
  mark("publish_begin");
  merge_kernel<T, unsigned>(index, const_cast<std::string &>(prefix));
  mark("publish_end");
}
}
int main(int argc, char **argv) {
  try {
    r2_oracle_force_link();
    if (argc == 5 && std::string(argv[1]) == "run") {
      run<float>(argv[2], argv[3], argv[4]); return 0;
    }
    std::cerr << "usage: z0a_canary run DATA PREFIX TRACE\n"; return 2;
  } catch (const std::exception &error) {
    std::cerr << "z0a_canary fatal: " << error.what() << '\n'; return 1;
  }
}
