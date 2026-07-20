#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef enum CBLAS_ORDER {
  CblasRowMajor = 101,
  CblasColMajor = 102
} CBLAS_ORDER;

typedef enum CBLAS_TRANSPOSE {
  CblasNoTrans = 111,
  CblasTrans = 112,
  CblasConjTrans = 113
} CBLAS_TRANSPOSE;

typedef enum CBLAS_UPLO {
  CblasUpper = 121,
  CblasLower = 122
} CBLAS_UPLO;

float cblas_sdot(const int n, const float *x, const int incx,
                 const float *y, const int incy);
void cblas_sgemm(const CBLAS_ORDER order, const CBLAS_TRANSPOSE transa,
                 const CBLAS_TRANSPOSE transb, const int m, const int n,
                 const int k, const float alpha, const float *a, const int lda,
                 const float *b, const int ldb, const float beta, float *c,
                 const int ldc);
void cblas_ssyrk(const CBLAS_ORDER order, const CBLAS_UPLO uplo,
                 const CBLAS_TRANSPOSE trans, const int n, const int k,
                 const float alpha, const float *a, const int lda,
                 const float beta, float *c, const int ldc);

#ifdef __cplusplus
}
#endif
