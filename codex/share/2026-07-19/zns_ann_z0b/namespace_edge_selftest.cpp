#include <cerrno>
#include <cstdio>
#include <cstring>
#include <dlfcn.h>
#include <fcntl.h>
#include <string>
#include <unistd.h>

int main(int argc, char **argv) {
  if (argc != 3) return 2;
  const std::string root = argv[1];
  const std::string mode = argv[2];
  if (mode == "append-create") {
    const std::string path = root + "/append-created.tmp";
    FILE *file = std::fopen(path.c_str(), "a");
    if (!file) return 3;
    if (std::fwrite("x", 1, 1, file) != 1 || std::fclose(file) != 0) return 4;
    using Enabled = bool (*)();
    using Flush = void (*)();
    auto enabled = reinterpret_cast<Enabled>(::dlsym(RTLD_DEFAULT, "atlas_z0a_enabled"));
    auto flush = reinterpret_cast<Flush>(::dlsym(RTLD_DEFAULT, "atlas_z0a_flush"));
    if (!enabled || !flush || !enabled()) return 8;
    flush();
    return 0;
  }
  if (mode == "renameat-reject") {
    const int fd = ::open(root.c_str(), O_RDONLY | O_DIRECTORY);
    if (fd < 0) return 5;
    const int result = ::renameat(fd, "source.tmp", fd, "target.tmp");
    const int saved = errno;
    ::close(fd);
    std::fprintf(stderr, "renameat unexpectedly returned %d: %s\n", result, std::strerror(saved));
    return 6;
  }
  return 7;
}
