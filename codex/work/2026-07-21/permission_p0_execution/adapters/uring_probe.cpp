#include <cerrno>
#include <cstring>
#include <iostream>
#include <linux/io_uring.h>
#include <sys/syscall.h>
#include <unistd.h>

int main() {
  io_uring_params params;
  std::memset(&params, 0, sizeof(params));
  int fd = static_cast<int>(syscall(SYS_io_uring_setup, 2, &params));
  if (fd < 0) {
    std::cerr << "io_uring_setup failed errno=" << errno << "\n";
    return errno == 0 ? 1 : errno;
  }
  close(fd);
  std::cout << "regular io_uring setup: PASS\n";
  return 0;
}
