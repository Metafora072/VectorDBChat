#include "ssd_index.h"

#include <algorithm>
#include <cstring>
#include <vector>

#include "linux_aligned_file_reader.h"
#include "utils.h"

namespace pipeann {

namespace {

template <typename T, typename TagT>
bool read_page_for_location(SSDIndex<T, TagT> *index, uint32_t location, bool topology, char *page) {
  auto *reader = static_cast<LinuxAlignedFileReader *>(index->reader.get());
  const uint32_t per_page = topology ? index->ntopo_per_sector : index->ncoord_per_sector;
  if (per_page == 0) return false;
  const uint64_t logical_page = location / per_page;
  uint64_t physical_page = logical_page;
  const auto &mapping = topology ? reader->loc2phy_topo : reader->loc2phy_coord;
  if (!mapping.empty()) {
    if (logical_page >= mapping.size()) return false;
    physical_page = mapping[logical_page];
  }
  const int fd = topology ? reader->topo_file_desc : reader->coord_file_desc;
  if (fd < 0) return false;
  const ssize_t bytes = ::pread(fd, page, SECTOR_LEN, static_cast<off_t>(physical_page * SECTOR_LEN));
  return bytes == static_cast<ssize_t>(SECTOR_LEN);
}

}  // namespace

template <typename T, typename TagT>
bool SSDIndex<T, TagT>::measurement_locations(uint32_t id, uint32_t &topo_loc, uint32_t &coord_loc) {
  topo_loc = id2loc_topo(id);
  coord_loc = id2loc_coord(id);
  if (topo_loc == kInvalidID || coord_loc == kInvalidID) return false;
  return loc2id_topo(topo_loc) == id && loc2id_coord(coord_loc) == id;
}

template <typename T, typename TagT>
bool SSDIndex<T, TagT>::measurement_read_vector(uint32_t id, std::vector<T> &vector) {
  uint32_t topo_loc = 0, coord_loc = 0;
  if (!measurement_locations(id, topo_loc, coord_loc)) return false;
  char *page = nullptr;
  alloc_aligned(reinterpret_cast<void **>(&page), SECTOR_LEN, SECTOR_LEN);
  const bool ok = read_page_for_location(this, coord_loc, false, page);
  if (ok) {
    vector.resize(data_dim);
    const char *record = offset_to_loc_coord(page, coord_loc);
    std::memcpy(vector.data(), record, data_dim * sizeof(T));
  }
  aligned_free(page);
  return ok;
}

template <typename T, typename TagT>
bool SSDIndex<T, TagT>::measurement_read_neighbors(uint32_t id, std::vector<uint32_t> &neighbors) {
  uint32_t topo_loc = 0, coord_loc = 0;
  if (!measurement_locations(id, topo_loc, coord_loc)) return false;
  char *page = nullptr;
  alloc_aligned(reinterpret_cast<void **>(&page), SECTOR_LEN, SECTOR_LEN);
  const bool ok = read_page_for_location(this, topo_loc, true, page);
  if (ok) {
    const auto *record = reinterpret_cast<const uint32_t *>(offset_to_loc_topo(page, topo_loc));
    const uint32_t degree = std::min<uint32_t>(record[0], max_degree);
    neighbors.assign(record + 1, record + 1 + degree);
  }
  aligned_free(page);
  return ok;
}

template bool SSDIndex<float, uint32_t>::measurement_locations(uint32_t, uint32_t &, uint32_t &);
template bool SSDIndex<float, uint32_t>::measurement_read_vector(uint32_t, std::vector<float> &);
template bool SSDIndex<float, uint32_t>::measurement_read_neighbors(uint32_t, std::vector<uint32_t> &);
template bool SSDIndex<int8_t, uint32_t>::measurement_locations(uint32_t, uint32_t &, uint32_t &);
template bool SSDIndex<int8_t, uint32_t>::measurement_read_vector(uint32_t, std::vector<int8_t> &);
template bool SSDIndex<int8_t, uint32_t>::measurement_read_neighbors(uint32_t, std::vector<uint32_t> &);
template bool SSDIndex<uint8_t, uint32_t>::measurement_locations(uint32_t, uint32_t &, uint32_t &);
template bool SSDIndex<uint8_t, uint32_t>::measurement_read_vector(uint32_t, std::vector<uint8_t> &);
template bool SSDIndex<uint8_t, uint32_t>::measurement_read_neighbors(uint32_t, std::vector<uint32_t> &);

}  // namespace pipeann
