#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <libaio.h>
#include <liburing.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

extern "C" void m0_set_phase(const char *);
extern "C" void m0_record_async_request(const char *, int, uint64_t, uint64_t);

int main(int argc, char **argv) {
  if (argc != 3) return 2;
  const std::string mode = argv[1], root = argv[2];
  m0_set_phase("ingest_begin");
  if (mode == "empty") return 0;
  std::string path = root + "/index_disk.index";
  int fd = ::open(path.c_str(), O_CREAT | O_TRUNC | O_RDWR, 0600);
  if (fd < 0) return 3;
  void *raw = nullptr;
  if (posix_memalign(&raw, 4096, 8192) != 0) return 4;
  std::memset(raw, 0x5a, 8192);
  int rc = 0;
  if (mode == "posix") {
    rc = ::pwrite(fd, raw, 4096, 8192) == 4096 ? 0 : 5;
  } else if (mode == "boundary") {
    rc = ::pwrite(fd, raw, 4096, 2048) == 4096 ? 0 : 6;
  } else if (mode == "aio") {
    io_context_t ctx = 0; iocb cb{}; iocb *list[1] = {&cb}; io_event event{};
    if (io_setup(1, &ctx) != 0) rc = 7;
    if (!rc) { io_prep_pwrite(&cb, fd, raw, 4096, 4096); int n = io_submit(ctx, 1, list); if (n == 1) m0_record_async_request("linux_aligned.execute_io.libaio", fd, 4096, 4096); else rc = 8; }
    if (!rc && io_getevents(ctx, 1, 1, &event, nullptr) != 1) rc = 9;
    if (ctx) io_destroy(ctx);
  } else if (mode == "uring") {
    io_uring ring{}; if (io_uring_queue_init(2, &ring, 0) != 0) rc = 10;
    if (!rc) { io_uring_sqe *sqe = io_uring_get_sqe(&ring); io_uring_prep_write(sqe, fd, raw, 4096, 4096); int n = io_uring_submit(&ring); if (n == 1) m0_record_async_request("linux_aligned.execute_io.io_uring", fd, 4096, 4096); else rc = 11; }
    io_uring_cqe *cqe = nullptr; if (!rc && (io_uring_wait_cqe(&ring, &cqe) != 0 || cqe->res != 4096)) rc = 12; if (cqe) io_uring_cqe_seen(&ring, cqe); io_uring_queue_exit(&ring);
  } else if (mode == "fdreuse") {
    if (::pwrite(fd, raw, 4096, 4096) != 4096) rc = 13;
    ::close(fd); fd = ::open((root + "/index_pq_compressed.bin").c_str(), O_CREAT | O_TRUNC | O_RDWR, 0600);
    if (fd < 0 || ::pwrite(fd, raw, 4096, 0) != 4096) rc = 14;
  } else rc = 15;
  if (fd >= 0) ::close(fd);
  free(raw);
  return rc;
}
