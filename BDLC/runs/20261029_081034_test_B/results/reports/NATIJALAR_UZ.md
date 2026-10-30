# Natijalar (avtomatik yaratilgan)

Bu fayl `bench/make_reports.py` tomonidan faqat shu run’ning saqlangan o‘lchovlaridan yaratildi. Qo‘lda kiritilgan yoki taxminiy qiymat yo‘q.

## Tajriba holati

- Run holati (`status.json`): **COMPLETE**
- Rejim: two-phase; kodeklar: 41; tasvirlar: 6477; tezlik o‘lchangan tasvirlar: 1169
- Takrorlar (protokol): 3; o‘lchangan juftliklar: 265557 / 265557; N/A: 0; xatolar: 0
- Asosiy o‘lchovlar to‘plami: 265557 ta tekshirilgan (kodek, tasvir) juftligi; tezligi bilan: 47929
- Platforma: Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39; CPU: 13th Gen Intel(R) Core(TM) i7-13700F

## ALL_REAL

### Hajm

- BDLC 33 ta raqib konfiguratsiyasidan kichik, **2 tasidan katta** (umumiy bayt, bir xil tasvirlar kesishmasida).
  - **Yutqazish:** ECC-2026 — BDLC 9.79% katta; tasvirlar: 263 kichik / 45 teng / 5954 katta (kesishma 6262/6262).
  - **Yutqazish:** ECC-2026 (rank map) — BDLC 7.41% katta; tasvirlar: 783 kichik / 89 teng / 5390 katta (kesishma 6262/6262).
  - Eng yaqin yutilgan raqib: Crackle mo0 + zstd — BDLC 28.18% kichik (6207/6262 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo3 + zstd — BDLC 29.31% kichik (6222/6262 tasvirda kichik).
  - Eng yaqin yutilgan raqib: FLIF 16-bit -E100 — BDLC 36.38% kichik (6160/6262 tasvirda kichik).
  - Virtual eng yaxshi (all_competitors, 35 a’zo): Δ = -10.30% (95% CI -11.44 … -9.19), 4/94 klasterda BDLC kichik.
  - Virtual eng yaxshi (all_except_ECC, 33 a’zo): Δ = 33.26% (95% CI 30.71 … 35.67), 91/94 klasterda BDLC kichik.
  - Virtual eng yaxshi (ECC_only, 2 a’zo): Δ = -9.86% (95% CI -10.84 … -8.86), 4/94 klasterda BDLC kichik.

### Siqish (encode) tezligi

- BDLC 33 ta raqibdan tezroq, **2 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.506 (kesishma 954 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.671 (kesishma 954 tasvir).

### Tiklash (decode) tezligi

- BDLC 32 ta raqibdan tezroq, **3 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -19 — koeffitsiyent 0.409 (kesishma 954 tasvir).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.446 (kesishma 954 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.554 (kesishma 954 tasvir).

## DAVIS2017_480p

### Hajm

- BDLC 33 ta raqib konfiguratsiyasidan kichik, **2 tasidan katta** (umumiy bayt, bir xil tasvirlar kesishmasida).
  - **Yutqazish:** ECC-2026 — BDLC 9.83% katta; tasvirlar: 258 kichik / 42 teng / 5908 katta (kesishma 6208/6208).
  - **Yutqazish:** ECC-2026 (rank map) — BDLC 7.49% katta; tasvirlar: 746 kichik / 85 teng / 5377 katta (kesishma 6208/6208).
  - Eng yaqin yutilgan raqib: Crackle mo0 + zstd — BDLC 28.09% kichik (6153/6208 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo3 + zstd — BDLC 29.23% kichik (6168/6208 tasvirda kichik).
  - Eng yaqin yutilgan raqib: FLIF 16-bit -E100 — BDLC 36.13% kichik (6106/6208 tasvirda kichik).
  - Virtual eng yaxshi (all_competitors, 35 a’zo): Δ = -10.66% (95% CI -11.77 … -9.53), 2/90 klasterda BDLC kichik.
  - Virtual eng yaxshi (all_except_ECC, 33 a’zo): Δ = 33.12% (95% CI 30.44 … 35.61), 87/90 klasterda BDLC kichik.
  - Virtual eng yaxshi (ECC_only, 2 a’zo): Δ = -10.20% (95% CI -11.12 … -9.22), 2/90 klasterda BDLC kichik.

### Siqish (encode) tezligi

- BDLC 33 ta raqibdan tezroq, **2 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.495 (kesishma 900 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.665 (kesishma 900 tasvir).

### Tiklash (decode) tezligi

- BDLC 32 ta raqibdan tezroq, **3 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -19 — koeffitsiyent 0.417 (kesishma 900 tasvir).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.453 (kesishma 900 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.475 (kesishma 900 tasvir).

## Fluo-N2DH-GOWT1_GT_SEG

### Hajm

- BDLC 34 ta raqib konfiguratsiyasidan kichik, **1 tasidan katta** (umumiy bayt, bir xil tasvirlar kesishmasida).
  - **Yutqazish:** ECC-2026 — BDLC 6.09% katta; tasvirlar: 1 kichik / 3 teng / 46 katta (kesishma 50/50).
  - Eng yaqin yutilgan raqib: ECC-2026 (rank map) — BDLC 1.92% kichik (33/50 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo0 + zstd — BDLC 45.19% kichik (50/50 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo3 + zstd — BDLC 47.78% kichik (50/50 tasvirda kichik).
  - Virtual eng yaxshi (all_competitors, 35 a’zo): Δ = -6.27% (95% CI -9.38 … -3.24), 0/2 klasterda BDLC kichik.
  - Virtual eng yaxshi (all_except_ECC, 33 a’zo): Δ = 43.99% (95% CI 40.97 … 46.85), 2/2 klasterda BDLC kichik.
  - Virtual eng yaxshi (ECC_only, 2 a’zo): Δ = -6.27% (95% CI -9.38 … -3.24), 0/2 klasterda BDLC kichik.

### Siqish (encode) tezligi

- BDLC 33 ta raqibdan tezroq, **2 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.630 (kesishma 50 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.740 (kesishma 50 tasvir).

### Tiklash (decode) tezligi

- BDLC 33 ta raqibdan tezroq, **2 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -19 — koeffitsiyent 0.325 (kesishma 50 tasvir).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.380 (kesishma 50 tasvir).

## Fluo-N2DH-SIM+_GT_SEG

### Hajm

- BDLC 33 ta raqib konfiguratsiyasidan kichik, **2 tasidan katta** (umumiy bayt, bir xil tasvirlar kesishmasida).
  - **Yutqazish:** ECC-2026 — BDLC 17.95% katta; tasvirlar: 0 kichik / 0 teng / 215 katta (kesishma 215/215).
  - **Yutqazish:** ECC-2026 (rank map) — BDLC 12.18% katta; tasvirlar: 14 kichik / 0 teng / 201 katta (kesishma 215/215).
  - Eng yaqin yutilgan raqib: Crackle mo3 + zstd — BDLC 15.58% kichik (215/215 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo0 + zstd — BDLC 19.91% kichik (215/215 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo3 — BDLC 24.28% kichik (215/215 tasvirda kichik).
  - Virtual eng yaxshi (all_competitors, 35 a’zo): Δ = -18.06% (95% CI -18.90 … -17.23), 0/2 klasterda BDLC kichik.
  - Virtual eng yaxshi (all_except_ECC, 33 a’zo): Δ = 15.09% (95% CI 11.98 … 18.10), 2/2 klasterda BDLC kichik.
  - Virtual eng yaxshi (ECC_only, 2 a’zo): Δ = -18.06% (95% CI -18.90 … -17.23), 0/2 klasterda BDLC kichik.

### Siqish (encode) tezligi

- BDLC 33 ta raqibdan tezroq, **2 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.533 (kesishma 215 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.642 (kesishma 215 tasvir).

### Tiklash (decode) tezligi

- BDLC 32 ta raqibdan tezroq, **3 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -19 — koeffitsiyent 0.410 (kesishma 215 tasvir).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.424 (kesishma 215 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.531 (kesishma 215 tasvir).

## PhC-C2DL-PSC_GT_SEG

### Hajm

- BDLC 35 ta raqib konfiguratsiyasidan kichik, **0 tasidan katta** (umumiy bayt, bir xil tasvirlar kesishmasida).
  - Eng yaqin yutilgan raqib: ECC-2026 — BDLC 1.02% kichik (4/4 tasvirda kichik).
  - Eng yaqin yutilgan raqib: ECC-2026 (rank map) — BDLC 10.16% kichik (4/4 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo3 + zstd — BDLC 27.28% kichik (4/4 tasvirda kichik).
  - Virtual eng yaxshi (all_competitors, 35 a’zo): Δ = 1.02% (95% CI 0.63 … 1.40), 2/2 klasterda BDLC kichik.
  - Virtual eng yaxshi (all_except_ECC, 33 a’zo): Δ = 27.28% (95% CI 27.12 … 27.44), 2/2 klasterda BDLC kichik.
  - Virtual eng yaxshi (ECC_only, 2 a’zo): Δ = 1.02% (95% CI 0.63 … 1.40), 2/2 klasterda BDLC kichik.

### Siqish (encode) tezligi

- BDLC 33 ta raqibdan tezroq, **2 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.458 (kesishma 4 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.598 (kesishma 4 tasvir).

### Tiklash (decode) tezligi

- BDLC 32 ta raqibdan tezroq, **3 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.315 (kesishma 4 tasvir).
  - **Sekinroq:** Zstandard -19 — koeffitsiyent 0.335 (kesishma 4 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.570 (kesishma 4 tasvir).

## Oldindan e’lon qilingan gipotezalar (PROTOKOL_B_UZ.md)

| Scope | Gipoteza | Klasterlar | Baho | 95% CI | p (sign) | p (Holm) |
|---|---|---:|---|---|---:|---:|
| ALL_REAL | B1 size vs ECC (oracle of ecc_direct+ecc_pi), two-sided | 94 | -9.86 | -10.84 … -8.86 | 0.0000 | 0.0000 |
| ALL_REAL | B2 size vs best non-ECC competitor (33 configurations), one-sided | 94 | 33.26 | 30.71 … 35.67 | 0.0000 | 0.0000 |
| ALL_REAL | B3 faster than ecc_direct in encode and decode, one-sided (intersection-union) | 94 | 17.241 / 8.507 |  | 0.0000 | 0.0000 |
| DAVIS2017_480p | B1 size vs ECC (oracle of ecc_direct+ecc_pi), two-sided | 90 | -10.20 | -11.12 … -9.22 | 0.0000 | 0.0000 |
| DAVIS2017_480p | B2 size vs best non-ECC competitor (33 configurations), one-sided | 90 | 33.12 | 30.44 … 35.61 | 0.0000 | 0.0000 |
| DAVIS2017_480p | B3 faster than ecc_direct in encode and decode, one-sided (intersection-union) | 90 | 17.148 / 8.631 |  | 0.0000 | 0.0000 |
| Fluo-N2DH-GOWT1_GT_SEG | B1 size vs ECC (oracle of ecc_direct+ecc_pi), two-sided | 2 | -6.27 | -9.38 … -3.24 | 0.5000 | 0.7500 |
| Fluo-N2DH-GOWT1_GT_SEG | B2 size vs best non-ECC competitor (33 configurations), one-sided | 2 | 43.99 | 40.97 … 46.85 | 0.2500 | 0.7500 |
| Fluo-N2DH-GOWT1_GT_SEG | B3 faster than ecc_direct in encode and decode, one-sided (intersection-union) | 2 | 26.588 / 8.882 |  | 0.2500 | 0.7500 |
| Fluo-N2DH-SIM+_GT_SEG | B1 size vs ECC (oracle of ecc_direct+ecc_pi), two-sided | 2 | -18.06 | -18.90 … -17.23 | 0.5000 | 0.7500 |
| Fluo-N2DH-SIM+_GT_SEG | B2 size vs best non-ECC competitor (33 configurations), one-sided | 2 | 15.09 | 11.98 … 18.10 | 0.2500 | 0.7500 |
| Fluo-N2DH-SIM+_GT_SEG | B3 faster than ecc_direct in encode and decode, one-sided (intersection-union) | 2 | 14.934 / 5.533 |  | 0.2500 | 0.7500 |
| PhC-C2DL-PSC_GT_SEG | B1 size vs ECC (oracle of ecc_direct+ecc_pi), two-sided | 2 | 1.02 | 0.63 … 1.40 | 0.5000 | 0.7500 |
| PhC-C2DL-PSC_GT_SEG | B2 size vs best non-ECC competitor (33 configurations), one-sided | 2 | 27.28 | 27.12 … 27.44 | 0.2500 | 0.7500 |
| PhC-C2DL-PSC_GT_SEG | B3 faster than ecc_direct in encode and decode, one-sided (intersection-union) | 2 | 14.276 / 4.261 |  | 0.2500 | 0.7500 |

- B4 (Pareto): BDLC ni klasterlarning yarmidan ko‘pida hajmda ham, encode va decode’da ham ustun qilgan raqiblar: yo‘q

## Xatolar va qamrov

- Batafsil: `reports/errors.md`. Asosiy to‘plamdan chiqarilgan yoki muammoli yozuvlar: 0.
