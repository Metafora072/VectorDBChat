#include "z0a_trace.h"

#include <fcntl.h>
#include <stdexcept>
#include <string>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  const std::string path = std::string(argv[1]) + "/created.tmp";
  atlas_z0a_set_context(7, 3, ATLAS_Z0A_PHASE_INSERT);
  int fd = open(path.c_str(), O_CREAT | O_TRUNC | O_RDWR, 0600);
  if (fd < 0) throw std::runtime_error("create failed");
  std::string payload(5000, 'z');
  if (pwrite(fd, payload.data(), payload.size(), 137) != static_cast<ssize_t>(payload.size()))
    throw std::runtime_error("pwrite failed");
  if (ftruncate(fd, 4096) != 0) throw std::runtime_error("truncate failed");
  close(fd);
  if (unlink(path.c_str()) != 0) throw std::runtime_error("unlink failed");
  atlas_z0a_flush();
  return 0;
}
