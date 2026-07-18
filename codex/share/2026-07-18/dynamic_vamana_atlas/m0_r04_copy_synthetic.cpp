#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>

static void emit_stat(const char *name, const std::filesystem::path &path) {
  struct stat st {};
  if (::stat(path.c_str(), &st) != 0) throw std::runtime_error("stat failed: " + path.string());
  std::cout << "\"" << name << "\":{\"path\":\"" << path.string() << "\",\"device\":"
            << static_cast<unsigned long long>(st.st_dev) << ",\"inode\":"
            << static_cast<unsigned long long>(st.st_ino) << ",\"size\":"
            << static_cast<unsigned long long>(st.st_size) << "}";
}

static bool content_equal(const std::filesystem::path &left, const std::filesystem::path &right) {
  if (std::filesystem::file_size(left) != std::filesystem::file_size(right)) return false;
  std::ifstream a(left, std::ios::binary), b(right, std::ios::binary);
  return std::equal(std::istreambuf_iterator<char>(a), std::istreambuf_iterator<char>(),
                    std::istreambuf_iterator<char>(b));
}

int main(int argc, char **argv) {
  if (argc != 3) return 2;
  const std::filesystem::path source = std::filesystem::canonical(argv[1]);
  const std::filesystem::path destination = std::filesystem::absolute(argv[2]);
  std::cout << "{";
  emit_stat("source_before", source);
  std::cout << ",";
  emit_stat("destination_before", destination);
  std::filesystem::copy(source, destination, std::filesystem::copy_options::overwrite_existing);
  std::cout << ",";
  emit_stat("destination_after", destination);
  const bool equal = content_equal(source, destination);
  std::cout << ",\"content_equal\":" << (equal ? "true" : "false") << "}\n";
  return equal ? 0 : 3;
}
