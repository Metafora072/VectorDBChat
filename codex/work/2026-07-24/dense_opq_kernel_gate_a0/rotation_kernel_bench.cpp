#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

#include "mkl.h"

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

double pct(std::vector<double> values, double fraction)
{
    std::sort(values.begin(), values.end());
    return values[static_cast<size_t>(fraction * (values.size() - 1))];
}

std::vector<float> make_signed_permutation(uint32_t dim)
{
    std::vector<float> matrix(static_cast<size_t>(dim) * dim, 0.0f);
    for (uint32_t i = 0; i < dim; ++i)
    {
        const uint32_t j = (i * 131u + 17u) % dim;
        matrix[static_cast<size_t>(i) * dim + j] = (i % 2 == 0) ? 1.0f : -1.0f;
    }
    return matrix;
}

std::vector<float> make_queries(uint32_t queries, uint32_t dim)
{
    std::mt19937 rng(20260724u + dim);
    std::normal_distribution<float> dist(0.0f, 1.0f);
    std::vector<float> out(static_cast<size_t>(queries) * dim);
    for (auto &value : out)
        value = dist(rng);
    return out;
}

void rotate_v0(const float *query, const float *rot, uint32_t dim, float *out)
{
    std::vector<float> tmp(dim, 0.0f);
    for (uint32_t d = 0; d < dim; ++d)
        for (uint32_t d1 = 0; d1 < dim; ++d1)
            tmp[d] += query[d1] * rot[static_cast<size_t>(d1) * dim + d];
    std::memcpy(out, tmp.data(), dim * sizeof(float));
}

void rotate_v1(const float *query, const float *rot, uint32_t dim, float *out)
{
    std::fill(out, out + dim, 0.0f);
    for (uint32_t d1 = 0; d1 < dim; ++d1)
    {
        const float q = query[d1];
        const float *row = rot + static_cast<size_t>(d1) * dim;
        for (uint32_t d = 0; d < dim; ++d)
            out[d] += q * row[d];
    }
}

void rotate_v2(const float *query, const float *rot, uint32_t dim, float *out)
{
    cblas_sgemv(CblasRowMajor, CblasTrans, static_cast<int>(dim), static_cast<int>(dim), 1.0f, rot,
                static_cast<int>(dim), query, 1, 0.0f, out, 1);
}

double rel_l2(const std::vector<float> &a, const std::vector<float> &b)
{
    double num = 0.0, den = 0.0;
    for (size_t i = 0; i < a.size(); ++i)
    {
        const double diff = static_cast<double>(a[i]) - b[i];
        num += diff * diff;
        den += static_cast<double>(a[i]) * a[i];
    }
    return std::sqrt(num / std::max(den, 1e-30));
}

int main(int argc, char **argv)
{
    if (argc != 4)
        throw std::runtime_error("usage: rotation_kernel_bench ROTATION.bin QUERY.bin OUT.jsonl");

    uint32_t rr = 0, rc = 0, qr = 0, qc = 0;
    auto actual_rotation = load_bin<float>(argv[1], rr, rc);
    auto actual_queries = load_bin<float>(argv[2], qr, qc);
    if (rr != rc || qc != rr)
        throw std::runtime_error("actual rotation/query shape mismatch");

    std::ofstream out_json(argv[3]);
    const uint32_t dims[] = {128, 768, 960, 1536};
    const uint32_t bench_queries = std::min<uint32_t>(qr, 1000);
    volatile double checksum = 0.0;

    for (uint32_t dim : dims)
    {
        std::vector<float> rotation = dim == rr ? actual_rotation : make_signed_permutation(dim);
        std::vector<float> queries = dim == rr ? actual_queries : make_queries(bench_queries, dim);
        const uint32_t nq = dim == rr ? bench_queries : bench_queries;
        std::vector<float> ref(dim), tmp(dim);

        rotate_v0(queries.data(), rotation.data(), dim, ref.data());
        rotate_v1(queries.data(), rotation.data(), dim, tmp.data());
        const double v1_rel = rel_l2(ref, tmp);
        double v1_max = 0.0;
        for (uint32_t i = 0; i < dim; ++i)
            v1_max = std::max(v1_max, std::abs(static_cast<double>(ref[i]) - tmp[i]));
        rotate_v2(queries.data(), rotation.data(), dim, tmp.data());
        const double v2_rel = rel_l2(ref, tmp);
        double v2_max = 0.0;
        for (uint32_t i = 0; i < dim; ++i)
            v2_max = std::max(v2_max, std::abs(static_cast<double>(ref[i]) - tmp[i]));

        for (const std::string impl : {"v0", "v1", "v2"})
        {
            std::vector<double> timings;
            timings.reserve(nq);
            for (uint32_t warmup = 0; warmup < std::min<uint32_t>(25, nq); ++warmup)
            {
                const float *q = queries.data() + static_cast<size_t>(warmup) * dim;
                if (impl == "v0")
                    rotate_v0(q, rotation.data(), dim, tmp.data());
                else if (impl == "v1")
                    rotate_v1(q, rotation.data(), dim, tmp.data());
                else
                    rotate_v2(q, rotation.data(), dim, tmp.data());
            }
            for (uint32_t qid = 0; qid < nq; ++qid)
            {
                const float *q = queries.data() + static_cast<size_t>(qid) * dim;
                const auto start = std::chrono::steady_clock::now();
                if (impl == "v0")
                    rotate_v0(q, rotation.data(), dim, tmp.data());
                else if (impl == "v1")
                    rotate_v1(q, rotation.data(), dim, tmp.data());
                else
                    rotate_v2(q, rotation.data(), dim, tmp.data());
                const auto end = std::chrono::steady_clock::now();
                timings.push_back(std::chrono::duration<double, std::micro>(end - start).count());
                checksum += tmp[qid % dim];
            }
            const double mean = std::accumulate(timings.begin(), timings.end(), 0.0) / timings.size();
            const double flops = 2.0 * dim * dim;
            out_json << "{\"kind\":\"single\",\"impl\":\"" << impl << "\",\"dim\":" << dim
                     << ",\"queries\":" << nq << ",\"mean_us\":" << mean
                     << ",\"p50_us\":" << pct(timings, 0.50)
                     << ",\"p95_us\":" << pct(timings, 0.95)
                     << ",\"gflops\":" << (flops / (mean * 1000.0))
                     << ",\"matrix_bandwidth_gbs\":"
                     << ((static_cast<double>(dim) * dim * sizeof(float)) / (mean * 1000.0))
                     << ",\"v1_max_abs_error\":" << v1_max << ",\"v1_rel_l2_error\":" << v1_rel
                     << ",\"v2_max_abs_error\":" << v2_max << ",\"v2_rel_l2_error\":" << v2_rel
                     << ",\"steady_heap_allocs_per_query\":" << (impl == "v0" ? 1 : 0) << "}\n";
        }

        if (dim == rr)
        {
            for (uint32_t batch : {8u, 32u, 128u})
            {
                std::vector<float> batch_out(static_cast<size_t>(batch) * dim, 0.0f);
                std::vector<double> timings;
                for (uint32_t start_q = 0; start_q + batch <= nq; start_q += batch)
                {
                    const auto start = std::chrono::steady_clock::now();
                    cblas_sgemm(CblasRowMajor, CblasNoTrans, CblasNoTrans, static_cast<int>(batch),
                                static_cast<int>(dim), static_cast<int>(dim), 1.0f,
                                queries.data() + static_cast<size_t>(start_q) * dim, static_cast<int>(dim),
                                rotation.data(), static_cast<int>(dim), 0.0f, batch_out.data(), static_cast<int>(dim));
                    const auto end = std::chrono::steady_clock::now();
                    timings.push_back(std::chrono::duration<double, std::micro>(end - start).count());
                    checksum += batch_out[start_q % batch];
                }
                const double mean_batch = std::accumulate(timings.begin(), timings.end(), 0.0) / timings.size();
                out_json << "{\"kind\":\"batch\",\"impl\":\"v3_sgemm\",\"dim\":" << dim
                         << ",\"batch\":" << batch << ",\"mean_batch_us\":" << mean_batch
                         << ",\"queries_per_s\":" << (1e6 * batch / mean_batch) << "}\n";
            }
        }
    }
    std::cerr << "checksum=" << checksum << "\n";
    return 0;
}
