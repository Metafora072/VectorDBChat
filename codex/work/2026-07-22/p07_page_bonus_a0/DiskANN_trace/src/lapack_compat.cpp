// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT license.

#ifdef DISKANN_USE_SYSTEM_BLAS

#include "mkl.h"

#include <algorithm>
#include <cstring>
#include <omp.h>
#include <vector>

extern "C" void sgesdd_(char *jobz, int *m, int *n, float *a, int *lda, float *s, float *u, int *ldu, float *vt,
                         int *ldvt, float *work, int *lwork, int *iwork, int *info);

namespace
{
int call_sgesdd(char jobz, int m, int n, float *a, int lda, float *s, float *u, int ldu, float *vt, int ldvt)
{
    const int min_dim = std::min(m, n);
    std::vector<int> iwork(static_cast<size_t>(8) * min_dim);
    float workspace_size = 0;
    int lwork = -1;
    int info = 0;
    sgesdd_(&jobz, &m, &n, a, &lda, s, u, &ldu, vt, &ldvt, &workspace_size, &lwork, iwork.data(), &info);
    if (info != 0)
        return info;
    lwork = std::max(1, static_cast<int>(workspace_size));
    std::vector<float> work(static_cast<size_t>(lwork));
    sgesdd_(&jobz, &m, &n, a, &lda, s, u, &ldu, vt, &ldvt, work.data(), &lwork, iwork.data(), &info);
    return info;
}
} // namespace

extern "C" int LAPACKE_sgesdd(int matrix_layout, char jobz, int m, int n, float *a, int lda, float *s, float *u,
                               int ldu, float *vt, int ldvt)
{
    if (matrix_layout == LAPACK_COL_MAJOR)
        return call_sgesdd(jobz, m, n, a, lda, s, u, ldu, vt, ldvt);
    if (matrix_layout != LAPACK_ROW_MAJOR || jobz != 'A')
        return -1;

    // Row-major A(m,n) has the same byte layout as column-major A^T(n,m).
    // SVD(A^T) swaps U and V; copying the column-major outputs directly gives
    // row-major U and V^T for the original matrix.
    std::vector<float> transposed_u(static_cast<size_t>(n) * n);
    std::vector<float> transposed_vt(static_cast<size_t>(m) * m);
    int transposed_m = n;
    int transposed_n = m;
    int info = call_sgesdd(jobz, transposed_m, transposed_n, a, transposed_m, s, transposed_u.data(), transposed_m,
                           transposed_vt.data(), transposed_n);
    if (info == 0)
    {
        std::memcpy(u, transposed_vt.data(), static_cast<size_t>(m) * m * sizeof(float));
        std::memcpy(vt, transposed_u.data(), static_cast<size_t>(n) * n * sizeof(float));
    }
    return info;
}

extern "C" void mkl_set_num_threads(int num_threads)
{
    omp_set_num_threads(num_threads);
}

#endif
