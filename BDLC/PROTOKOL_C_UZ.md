# Protokol C — oldindan yozilgan (2026-10-30, natija ko'rilishidan oldin)

Bu hujjat va `protocol_C.json` run boshlanishidan **oldin** yoziladi. Run bir marta yuritiladi. Natijaga qarab hech narsa o'zgartirilmaydi: na BDLC, na raqib sozlamalari, na tahlil.

## 1. Maqsad

Maqola taqrizida aniqlangan **B3** cheklovi: ko'p sinfli semantik xaritalar sinalmagan. Protokol B'dagi xulosalar (hajm va tezlik, Pareto) ko'p sinfli semantik xaritalarda ham saqlanadimi?

## 2. Nima o'lchanadi

- **Kodek.** BDLC v1, muzlatilgan (`freeze.json`, model 1, flaglar 0). Protokol B bilan bir xil fayllar.
- **Raqiblar.** Protokol B'dagi 41 konfiguratsiya, xuddi o'sha sozlamalar va o'sha binary'lar (`bdlc-bench:2026-10-29`).
- **Ma'lumot** (`manifest_C.csv`, `tools/build_manifest_C.py`):
  - COCO-Stuff 2017, **val2017** qismi: `stuffthingmaps_trainval2017.zip` dagi har bir `val2017/<id>.png` xaritasi.
  - Manba: `calvin.inf.ed.ac.uk` (COCO-Stuff mualliflari); litsenziya: annotatsiyalar CC BY 4.0.
  - Qiymatlar: 0–181 — sinflar, 255 — belgilanmagan; hammasi label sifatida o'zgarishsiz saqlanadi (uint8 TIFF).
  - Train qismi ishlatilmaydi.
  - Har bir xarita mustaqil fotosuratdan olingan, shuning uchun **har bir xarita alohida klaster** (group = xarita).
  - Tezlik: id tartibida har 5-xarita (`timing = 1`).
- **Muhit va ikki bosqich** protokol B bilan bir xil: hajm bosqichi 20 parallel ishchi; tezlik bosqichi bitta pinlangan yadro (vCPU 2), nice −10, 3 takror, mediana, CLI'larda null (1×1) vaqt ayiriladi; har bir oqim alohida jarayonda decode qilinib SHA-256 bilan tekshiriladi.
- **Bayt hisobi** protokol B bilan bir xil ($\sigma^{*}(K)$, $\eta$).

## 3. Gipotezalar (asosiy oila: COCO-Stuff val2017, α = 0.05, Holm)

Birlik — xarita. $d_i=\ln(B^{\text{BDLC}}_i/B^{\text{ref}}_i)$, $\Delta=100(1-e^{\bar d})\%$ (musbat — BDLC kichik).

| # | Savol | Taqqoslash | Test |
|---|---|---|---|
| **C1** | ECC bilan hajm farqi | ref = har xaritada min(`ecc_direct`, `ecc_pi`) | Ikki tomonlama sign test; $\Delta$ va 95% bootstrap CI (10 000) |
| **C2** | ECC dan tashqari 33 raqibning har xaritadagi eng yaxshisidan kichikmi | ref = 33 konfiguratsiyaning har xaritadagi minimumi | Bir tomonlama sign test |
| **C3** | `ecc_direct` dan encode **va** decode'da tezmi | xarita bo'yicha vaqtlar | Bir tomonlama sign testlar, intersection–union (kattaroq p) |
| **C4** | Pareto | har bir raqib | Tavsifiy: raqib xaritalarning > 50% ida ham kichik, ham encode, ham decode'da tez bo'lsa, BDLC unga nisbatan Pareto-optimal emas |

**Holm.** C1–C3 uchun.

**Sezgirlik S0.** C1 va C2 label to'plami hisobisiz takrorlanadi ($\sigma=0$, BDLC'dan o'z label to'plami bitlari ayiriladi), protokol B'dagi kabi.

**Natijaga qarab da'volar.**
- C1 qanday chiqsa, shunday yoziladi. Protokol B'da ECC kichikroq bo'lgan.
- C2 rad etilmasa, "ECC dan tashqari raqiblardan kichik" da'vosi COCO-Stuff uchun qilinmaydi.
- C3 yoki C4 bajarilmasa, bu maqolada ochiq yoziladi va Pareto da'vosi COCO-Stuff uchun qilinmaydi.

## 4. Halollik qoidalari

- Tahlil `bench/make_reports.py` bilan avtomatik qilinadi (protokol B'dagi bilan bir xil kod). Klaster = xarita.
- Har qanday xato, qo'llanmaydigan juftlik yoki verifikatsiya mos kelmasligi hisobotda yoziladi.
- Bu run protokol B natijalari ko'rilgandan **keyin**, taqrizdagi B3 cheklovini yopish uchun rejalashtirilgan. Bu maqolada ochiq aytiladi.
