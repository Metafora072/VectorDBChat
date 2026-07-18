#include "z0a_trace.h"

#include <fcntl.h>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

namespace {
void submit_and_write(int fd, uint64_t offset, uint64_t requested, uint64_t returned,
                      uint16_t source, AtlasZ0ATraceToken &token) {
  atlas_z0a_prepare(&token);
  const bool accepted = atlas_z0a_submit(&token, source, fd, offset, requested);
  if (atlas_z0a_enabled() && !accepted) throw std::runtime_error("submit rejected");
  std::string bytes(returned, 'x');
  const ssize_t result = syscall(SYS_pwrite64, fd, bytes.data(), bytes.size(), offset);
  if (result != static_cast<ssize_t>(returned)) throw std::runtime_error("selftest pwrite failed");
}
}  // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: z0a_trace_selftest INDEX_ROOT\n";
    return 2;
  }
  const std::string root = argv[1];
  const std::string first = root + "/index_disk.index";
  const std::string second = root + "/index_shadow_disk.index";
  const int fd1 = ::open(first.c_str(), O_CREAT | O_RDWR, 0600);
  const int fd2 = ::open(second.c_str(), O_CREAT | O_RDWR, 0600);
  if (fd1 < 0 || fd2 < 0) return 1;

  atlas_z0a_set_context(7, 0, ATLAS_Z0A_PHASE_INSERT);
  AtlasZ0ATraceToken a, b, c;
  submit_and_write(fd1, 2048, 5000, 5000, ATLAS_Z0A_SOURCE_LIBAIO_EXECUTE_IO, a);
  submit_and_write(fd2, 2048, 4096, 2048, ATLAS_Z0A_SOURCE_IOURING_EXECUTE_IO, b);
  submit_and_write(fd1, 16384, 4096, 4096, ATLAS_Z0A_SOURCE_PWRITE, c);
  // Deliberately complete out of submission order. This checks that completion
  // order comes from event.data/CQE user_data tokens rather than request-vector order.
  atlas_z0a_complete(&b, 2048, 0);
  atlas_z0a_complete(&a, 5000, 0);
  atlas_z0a_complete(&c, 4096, 0);
  atlas_z0a_set_phase_name("publish_begin");
  atlas_z0a_flush();
  ::close(fd1);
  ::close(fd2);
  return 0;
}
