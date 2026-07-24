#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

template <typename T>
std::vector<T> load_bin(const std::string &path, uint32_t &rows, uint32_t &cols)
{
    std::ifstream input(path, std::ios::binary);
    if (!input.read(reinterpret_cast<char *>(&rows), sizeof(rows)) ||
        !input.read(reinterpret_cast<char *>(&cols), sizeof(cols)))
        throw std::runtime_error("cannot read header: " + path);
    std::vector<T> values(static_cast<size_t>(rows) * cols);
    if (!input.read(reinterpret_cast<char *>(values.data()), values.size() * sizeof(T)))
        throw std::runtime_error("cannot read payload: " + path);
    return values;
}

double percentile(std::vector<double> values, double fraction)
{
    std::sort(values.begin(), values.end());
    return values[static_cast<size_t>(fraction * (values.size() - 1))];
}

int main(int argc, char **argv)
{
    if (argc != 3)
        throw std::runtime_error("usage: rotation_bench ROTATION.bin QUERY.bin");
    uint32_t rr, rc, qr, qc;
    auto rotation = load_bin<float>(argv[1], rr, rc);
    auto queries = load_bin<float>(argv[2], qr, qc);
    if (rr != rc || qc != rr)
        throw std::runtime_error("shape mismatch");
    std::vector<float> output(rc);
    std::vector<double> timings;
    timings.reserve(qr);
    volatile double checksum = 0.0;
    for (uint32_t warmup = 0; warmup < std::min<uint32_t>(10, qr); ++warmup)
        for (uint32_t d = 0; d < rc; ++d)
            for (uint32_t d1 = 0; d1 < rc; ++d1)
                output[d] += queries[static_cast<size_t>(warmup) * rc + d1] *
                             rotation[static_cast<size_t>(d1) * rc + d];
    for (uint32_t q = 0; q < qr; ++q)
    {
        std::fill(output.begin(), output.end(), 0.0f);
        const auto start = std::chrono::steady_clock::now();
        for (uint32_t d = 0; d < rc; ++d)
            for (uint32_t d1 = 0; d1 < rc; ++d1)
                output[d] += queries[static_cast<size_t>(q) * rc + d1] *
                             rotation[static_cast<size_t>(d1) * rc + d];
        const auto end = std::chrono::steady_clock::now();
        timings.push_back(
            std::chrono::duration<double, std::micro>(end - start).count());
        checksum += output[q % rc];
    }
    const double mean = std::accumulate(timings.begin(), timings.end(), 0.0) / timings.size();
    std::cout << "{\"queries\":" << qr << ",\"dimension\":" << rc
              << ",\"mean_us\":" << mean
              << ",\"p50_us\":" << percentile(timings, 0.50)
              << ",\"p95_us\":" << percentile(timings, 0.95)
              << ",\"p99_us\":" << percentile(timings, 0.99)
              << ",\"checksum\":" << checksum << "}\n";
}
