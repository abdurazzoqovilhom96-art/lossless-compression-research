# Protokol B — oldindan yozilgan (2026-10-29, natija ko‘rilishidan oldin)

Bu hujjat va `protocol_B.json` (harness protokoli: kod hashlari, kodeklar, paketlar, platforma, kirish fayllari) run boshlanishidan **oldin** yoziladi. Run bir marta yuritiladi. Natijaga qarab hech narsa o‘zgartirilmaydi: na BDLC, na raqib sozlamalari, na tahlil.

## 1. Nima o‘lchanadi

- **Kodek.** BDLC v1, muzlatilgan (`freeze.json`, model 1, flaglar 0). v2 bu run’da yo‘q.
- **Raqiblar.** Jami 41 konfiguratsiya:
  - test A ning 30 tasi (BDLC va uning 5 varianti shu ichida);
  - 11 ta tashqi konfiguratsiya: ECC-2026 ×2, HEVC SCC ×2, JBIG1 ×2, FLIF ×4, Compresso.

  Tafsilot: `docker\README_UZ.md`, `bench\external.py`.
- **Ma’lumot** (`manifest_B.csv`, `tools\build_manifest_B.py`):
  - **DAVIS 2017 trainval 480p** — barcha 6 208 annotatsiya, 90 video. Bu asosiy domen va ECC maqolasining o‘z dataseti. Biz to‘liq o‘lchamdan foydalanamiz (asosan 854×480); ECC maqolasi esa 848×480 ga kesgan.
  - **CTC test kohortasi A** — GOWT1 50, PSC 4, SIM+ 215 xarita. Ular ilgari faqat 30 kodek bilan o‘lchangan, bu safar tashqi raqiblar bilan ham solishtiriladi. SIM+ simulyatsiya, alohida.
  - Dev xaritalari (`real_manifest.csv`) bilan piksel-bir xillik tekshiriladi (`--exclude-manifest`).
- **Muhit.** `bdlc-bench:2026-10-29` konteyneri: Ubuntu 24.04, WSL2, Python 3.14.4, i7-13700F; GPU ishlatilmaydi, kodeklar faqat CPU’da ishlaydi.
- **Ikki bosqich** — kompyuter to‘liq quvvatda ishlaydi, lekin natijaga ta’sir qilmaydi:
  1. **Hajm bosqichi** — barcha 6 477 xarita, 41 konfiguratsiya, 20 parallel ishchi (100 tasvirli bo‘laklar).
     - Har oqim alohida process’da decode qilinib, piksel SHA-256 bilan tekshiriladi.
     - Hajm va oqim deterministik, shuning uchun parallel ishlash ularni o‘zgartirmaydi. Dev’da tekshirilgan: ikki bosqichli va bir bosqichli run’da 364/364 juftlik bayt soni bir xil.
     - Bu bosqichda vaqt o‘lchanmaydi.
  2. **Tezlik bosqichi** — konteynerda boshqa hech narsa ishlamaydi.
     - `timing = 1` bo‘lgan 1 169 xarita: har DAVIS videosidan 10 kadr, indekslar $i_k=\lfloor kN/M\rfloor$, $M=\min(N,10)$ (Q1_REJA §2.2); CTC ning 269 xaritasining hammasi.
     - Bir vCPU (2) ga pin, nice −10, 3 takror, mediana; kodeklar bittadan.
     - CLI kodeklarda null (1×1) vaqt ayiriladi.
     - Bu bosqichda yozilgan har oqim hajm bosqichida tekshirilgan oqim bilan SHA-256 bo‘yicha bir xil bo‘lishi shart.
- **Bayt hisobi** (Q1_REJA §1.3):
  - π orqali ishlaydigan konfiguratsiyalar label to‘plamini aynan σ*(K) baytda saqlaydi;
  - `direct`, uint16 va o‘z label’ini saqlaydigan kodeklarda σ = 0;
  - η = 0.

## 2. Gipotezalar (asosiy oila: DAVIS, n = 90 klaster, α = 0.05, Holm)

Klaster — video sequence. $d_g=\ln\big(\sum_{i\in g}B^{\text{BDLC}}_i/\sum_{i\in g}B^{\text{ref}}_i\big)$, $\bar d$ — o‘rtacha, $\Delta=100(1-e^{\bar d})\%$ (musbat — BDLC kichik).

| # | Savol | Taqqoslash | Test |
|---|---|---|---|
| **B1** | ECC bilan hajm farqi qancha? | ref = har tasvirda ECC ning eng kichigi, $\min$(`ecc_direct`, `ecc_pi`) | **Ikki tomonlama**, yo‘nalish oldindan da’vo qilinmaydi. $\Delta$ va 95% CI (klaster bootstrap, 10 000). Sign test va aniq/normal Wilcoxon ikki tomonlama |
| **B2** | ECC dan tashqari barcha raqiblarning eng yaxshisidan kichikmi? | ref = har tasvirda ECC dan tashqari 33 raqib konfiguratsiyasining eng kichigi (41 dan 6 ta BDLC konfiguratsiyasi va 2 ta ECC chiqarilgan) | Bir tomonlama, $H_1$: median $d_g<0$. Sign test |
| **B3** | ECC dan tezmi? | ref = `ecc_direct` (ECC ning tabiiy rejimi), klaster bo‘yicha jami vaqt | Bir tomonlama sign test encode **va** decode uchun (ikkalasi ham rad etilishi kerak — intersection-union) |
| **B4** | BDLC Pareto-optimalmi? | har raqib konfiguratsiyasi | Tavsifiy: raqib klasterlarning > 50% ida ham kichik, ham encode, ham decode’da tez bo‘lsa, BDLC u raqibga nisbatan Pareto-optimal emas |

**Holm.** B1, B2, B3 uchun $\alpha/3,\ \alpha/2,\ \alpha$.

**Dev’dagi oldindan ma’lum dalil.** ECC dev’da 7.3% kichik, BDLC 9–19× tez. Shuning uchun B1 natijasi qanday chiqsa, shunday yoziladi. "BDLC eng kichik" degan da’vo faqat B1 yo‘nalishi va CI shuni ko‘rsatsa qilinadi.

**Maqoladagi da’volar natijaga qarab:**

| Natija | Da’vo |
|---|---|
| B1: Δ > 0 va CI 0 dan yuqori | BDLC ECC dan ham kichik (DAVIS’da) |
| B1: CI 0 ni o‘z ichiga oladi | Hajmda ECC bilan teng (farq aniqlanmadi) |
| B1: Δ < 0 va CI 0 dan past | ECC hajmda yaxshiroq; BDLC — Pareto/tezlik da’vosi (B3, B4) |
| B2 rad etilmasa | ECC dan tashqari raqiblarga nisbatan ham ustunlik da’vo qilinmaydi |

## 3. Ikkilamchi (tavsifiy) tahlillar

- Har 35 ta raqib konfiguratsiyasiga nisbatan hajm yutug‘i, yutgan tasvirlar va klasterlar, tezlanish (`comparison.csv`).
- CTC (GOWT1, PSC — 4 klaster; SIM+ alohida) uchun xuddi shu jadvallar. 4 klaster bilan faqat tavsifiy.
- Sezgirlik S0: π konfiguratsiyalarida σ = 0.
- Qamrov: hamma konfiguratsiya DAVIS’ning hamma tasviriga qo‘llanadi (K ≤ 256, label ≤ 255), N/A soni hisobotda.
- BDLC bayt taqsimoti (`byte_breakdown.csv`) va cold start.

## 4. Halollik qoidalari

- **Tahlil skripti.** Virtual eng yaxshi raqib, B1–B4, Holm uchun yoziladigan `posthoc\protocol_B_analysis.py` run tugashidan oldin yoziladi. Shu vaqtda oraliq hajm natijalariga qaralmaydi; faqat `status.json` va xato soni kuzatiladi.
- **Raqiblar.** ECC uchun 3 qatorli UB patch (`docker\patches\ecc_ub_fixes.patch`) hujjatlashtirilgan; boshqa raqiblar standart sozlamalarda.
- **Platforma.** Tezlik faqat shu konteyner ichida solishtiriladi; Windows raqamlari bilan aralashtirilmaydi.
- **Xatolar.** Har qanday xato yoki verifikatsiya mos kelmasligi hisobotda yoziladi. Xato bergan konfiguratsiya oracle’dan chiqariladi va bu ham yoziladi.

## 5. Natijalarni avtomatik yaratish

Run tugagach `bench\make_reports.py` faqat shu run’ning tekshirilgan o‘lchovlaridan `results\` ni yaratadi:
- `tables`, `statistics` (B1–B4 testlari ham), `plot_data`;
- `figures` — PNG, 300 dpi;
- `paper\tables` — MD va TeX; `paper\figures` — PDF, SVG va PNG 300 dpi;
- `reports` — `NATIJALAR_UZ.md`, `status.json`, `errors.md`, `artifact_manifest.json`.

Yaratilgach o‘zi tekshiradi:
- fayllar bor va o‘qiladi;
- CSV faqat sarlavhadan iborat emas;
- formulalar, tasvir va takror soni to‘g‘ri;
- jadval va grafik qiymatlari asosiy to‘plamga mos;
- yo‘q o‘lchov 0 deb yozilmagan.

Hisobot holati (`reporting_status`) run holatidan alohida saqlanadi. Mavjud run uchun benchmark’ni qayta yuritmasdan: `python bench\make_reports.py runs\<run>`.

Tekshirilgan: test A (`runs\20261028_213039_test`), dev va ikki sinov run’i. Hammasida COMPLETE, 0 xato. Test A da yangi jadvallar eski jadvallar bilan 236 qatorda aynan bir xil, run’ning 8 606 ta eski fayli o‘zgarmagan.

## 6. Bajarish

- **Bekor qilingan urinish.** Birinchi urinish (protokol `9255064…`, 07:26–07:33 UTC) foydalanuvchi ruxsatisiz boshlab yuborilgani uchun to‘xtatildi. Natijasi ochilmagan. Papka: `runs\20261029_072604_test_B_ABORTED\`, ichida `ABORTED.txt` va eski protokol.
- **Ikkinchi to‘xtatilgan nusxa.** Ruxsatdan keyin boshlangan nusxa (08:06–08:08 UTC) foydalanuvchi run’ni o‘zi qo‘lda boshlashga qaror qilgani uchun to‘xtatildi. Natijasi ochilmagan. Papka: `runs\20261029_080633_test_B_ABORTED\`. Protokol o‘zgarmagan.
- **Joriy protokol.** `protocol_B.json` yozildi: 2026-10-29 07:54:37 UTC, konteyner ichida. Tarkibi:
  - 6 477 kirish fayli;
  - 41 konfiguratsiya (unavailable yo‘q);
  - hajm bosqichi 20 ishchi, tezlik bosqichi 1 169 xarita;
  - 24 ta kod fayli hashi, `make_reports.py` ham shu ichida;
  - 9 ta tashqi binary hashi.

  SHA-256: `96e16ed17a3a4089117bcd98f4245841cccb4cdf63467aae05404fcf3ae9bb3e`. Harness protokol bilan biror farq bo‘lsa ishga tushmaydi.
- **Ishga tushirish** (faqat foydalanuvchi ruxsatidan keyin):

  ```
  docker run -d --name bdlc-B --cap-add SYS_NICE -v <loyiha>:/proj bdlc-bench:2026-10-29 bash /proj/BDLC/docker/run_B.sh run
  ```

- **Taxminiy vaqt** (dev o‘tkazuvchanligidan): hajm bosqichi taxminan 0.5 soat, tezlik bosqichi taxminan 3–4 soat, hisobot taxminan 10 daqiqa. Jami taxminan 4–5 soat.
- **Tezlik bosqichida.** Kompyuterda og‘ir ish qilinmasligi kerak, aks holda vaqt o‘lchoviga ta’sir qilishi mumkin.
