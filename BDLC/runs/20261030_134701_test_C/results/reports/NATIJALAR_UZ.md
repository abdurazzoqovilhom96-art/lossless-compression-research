# Natijalar (avtomatik yaratilgan)

Bu fayl `bench/make_reports.py` tomonidan faqat shu run’ning saqlangan o‘lchovlaridan yaratildi. Qo‘lda kiritilgan yoki taxminiy qiymat yo‘q.

## Tajriba holati

- Run holati (`status.json`): **COMPLETE**
- Rejim: two-phase; kodeklar: 41; tasvirlar: 5000; tezlik o‘lchangan tasvirlar: 1000
- Takrorlar (protokol): 3; o‘lchangan juftliklar: 205000 / 205000; N/A: 0; xatolar: 0
- Asosiy o‘lchovlar to‘plami: 205000 ta tekshirilgan (kodek, tasvir) juftligi; tezligi bilan: 41000
- Platforma: Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39; CPU: 13th Gen Intel(R) Core(TM) i7-13700F

## COCO-Stuff_val2017

### Hajm

- BDLC 33 ta raqib konfiguratsiyasidan kichik, **2 tasidan katta** (umumiy bayt, bir xil tasvirlar kesishmasida).
  - **Yutqazish:** ECC-2026 — BDLC 4.24% katta; tasvirlar: 1839 kichik / 20 teng / 3141 katta (kesishma 5000/5000).
  - **Yutqazish:** ECC-2026 (rank map) — BDLC 2.88% katta; tasvirlar: 2117 kichik / 21 teng / 2862 katta (kesishma 5000/5000).
  - Eng yaqin yutilgan raqib: Crackle mo0 + zstd — BDLC 8.73% kichik (4296/5000 tasvirda kichik).
  - Eng yaqin yutilgan raqib: Crackle mo3 + zstd — BDLC 8.92% kichik (4420/5000 tasvirda kichik).
  - Eng yaqin yutilgan raqib: FLIF rank map -E100 — BDLC 24.11% kichik (4930/5000 tasvirda kichik).
  - Virtual eng yaxshi (all_competitors, 35 a’zo): Δ = -5.14% (95% CI -5.50 … -4.79), 1768/5000 klasterda BDLC kichik.
  - Virtual eng yaxshi (all_except_ECC, 33 a’zo): Δ = 10.10% (95% CI 9.79 … 10.41), 4209/5000 klasterda BDLC kichik.
  - Virtual eng yaxshi (ECC_only, 2 a’zo): Δ = -4.47% (95% CI -4.85 … -4.10), 1839/5000 klasterda BDLC kichik.

### Siqish (encode) tezligi

- BDLC 33 ta raqibdan tezroq, **2 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.396 (kesishma 1000 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.678 (kesishma 1000 tasvir).

### Tiklash (decode) tezligi

- BDLC 32 ta raqibdan tezroq, **3 tasidan sekinroq** (bir xil tezlik o‘lchangan tasvirlarda).
  - **Sekinroq:** Zstandard -3 — koeffitsiyent 0.309 (kesishma 1000 tasvir).
  - **Sekinroq:** Zstandard -19 — koeffitsiyent 0.344 (kesishma 1000 tasvir).
  - **Sekinroq:** JPEG-LS — koeffitsiyent 0.655 (kesishma 1000 tasvir).

## Oldindan e’lon qilingan gipotezalar (PROTOKOL_B_UZ.md)

| Scope | Gipoteza | Klasterlar | Baho | 95% CI | p (sign) | p (Holm) |
|---|---|---:|---|---|---:|---:|
| COCO-Stuff_val2017 | B1 size vs ECC (oracle of ecc_direct+ecc_pi), two-sided | 5000 | -4.47 | -4.85 … -4.10 | 0.0000 | 0.0000 |
| COCO-Stuff_val2017 | B2 size vs best non-ECC competitor (33 configurations), one-sided | 5000 | 10.10 | 9.79 … 10.41 | 0.0000 | 0.0000 |
| COCO-Stuff_val2017 | B3 faster than ecc_direct in encode and decode, one-sided (intersection-union) | 1000 | 22.809 / 10.780 |  | 0.0000 | 0.0000 |

- B4 (Pareto): BDLC ni klasterlarning yarmidan ko‘pida hajmda ham, encode va decode’da ham ustun qilgan raqiblar: yo‘q

## Xatolar va qamrov

- Batafsil: `reports/errors.md`. Asosiy to‘plamdan chiqarilgan yoki muammoli yozuvlar: 0.
