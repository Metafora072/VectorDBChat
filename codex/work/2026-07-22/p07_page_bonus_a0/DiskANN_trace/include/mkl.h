// Minimal MKL source-compatibility declarations for DISKANN_USE_SYSTEM_BLAS.
// This is intentionally limited to the CBLAS/LAPACKE surface used by DiskANN.
#pragma once

#ifndef DISKANN_USE_SYSTEM_BLAS
#error "This compatibility header is only for DISKANN_USE_SYSTEM_BLAS builds"
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef int MKL_INT;

typedef enum CBLAS_LAYOUT
{
    CblasRowMajor = 101,
    CblasColMajor = 102
} CBLAS_LAYOUT;
typedef CBLAS_LAYOUT CBLAS_ORDER;

typedef enum CBLAS_TRANSPOSE
{
    CblasNoTrans = 111,
    CblasTrans = 112,
    CblasConjTrans = 113
} CBLAS_TRANSPOSE;

#define LAPACK_ROW_MAJOR 101
#define LAPACK_COL_MAJOR 102

float cblas_sdot(const int n, const float *x, const int incx, const float *y, const int incy);
float cblas_snrm2(const int n, const float *x, const int incx);
void cblas_sgemm(const CBLAS_LAYOUT layout, const CBLAS_TRANSPOSE transa, const CBLAS_TRANSPOSE transb, const int m,
                 const int n, const int k, const float alpha, const float *a, const int lda, const float *b,
                 const int ldb, const float beta, float *c, const int ldc);
void cblas_sgemv(const CBLAS_LAYOUT layout, const CBLAS_TRANSPOSE trans, const int m, const int n, const float alpha,
                 const float *a, const int lda, const float *x, const int incx, const float beta, float *y,
                 const int incy);

int LAPACKE_sgesdd(int matrix_layout, char jobz, int m, int n, float *a, int lda, float *s, float *u, int ldu,
                   float *vt, int ldvt);
void mkl_set_num_threads(int num_threads);

#ifdef __cplusplus
}
#endif
