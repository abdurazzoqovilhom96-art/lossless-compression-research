# Tashqi raqiblar: build muhiti va tekshiruv (Q1, 1-qadam)

Holat: 2026-10-29. Beshala raqib Docker konteynerida build qilindi va sintetik xaritalarda **81/81 lossless** tekshiruvdan o‘tdi. Haqiqiy ma’lumotda hali hech narsa ishga tushirilmagan; bu protokol B yozilgandan keyin bo‘ladi.

## 1. Muhit

| Narsa | Qiymat |
|---|---|
| Asos image | `ubuntu@sha256:78d4744e…2044d` (Ubuntu 24.04, amd64; Docker Hub, 29 767 612 bayt) |
| Muhit image | `bdlc-baselines-env:2026-10-29` (`sha256:b97ba0a1…`) |
| Build qilingan image | `bdlc-baselines:2026-10-29` (`sha256:6445969c…`); binary’lar `/opt/baselines/bin` da |
| Kompilyator | GCC/G++ 13.3.0, CMake 3.28.3, GNU Make 4.3, libpng 1.6.43 |
| Paketlar | 177 ta, aniq versiyalari `packages.tsv` da; `Dockerfile` — shu muhitning hujjati |
| Docker | Docker Desktop 29.8.0 (WSL2 backend) |

`apt` paketlari 2026-10-29 da archive.ubuntu.com’dan olingan: indekslar 33.6 MB, 85 ta paket 109 MB. Ubuntu snapshot arxivi ishlamadi (HTTPS, asos image’da sertifikatlar yo‘q). Shuning uchun takrorlanuvchanlik `packages.tsv` dagi versiyalar bilan ta’minlanadi.

## 2. Build (`build_baselines.sh`)

Har loyiha **o‘zining standart flaglari** bilan build qilinadi:

| Vosita | Manba | Build | Binary |
|---|---|---|---|
| ECC-2026 | commit `fe3f2f1` | `make` (`-std=c++17 -O2`), patch bilan (§3) | `ecc_encoder`, `ecc_decoder` |
| JBIG1 | JBIG-KIT 2.1 | `make` (`-O2`), `make test` — barcha o‘z testlari PASSED | `pbmtojbg`, `jbgtopbm` |
| FLIF | v0.4 | `make flif` (`-O2 -ftree-vectorize -flto`) | `flif` |
| HEVC SCC | HM-16.21+SCM-8.8 | CMake Release, `-Wno-error=array-bounds` (§3) | `TAppEncoder`, `TAppDecoder`, `hm_cfg/` |
| Compresso | commit `b1f7fd6` | `g++ -std=c++11 -O3` (paket `setup.py` dagi flaglar) + `cpso_cli.cpp` | `cpso_cli` |

Binary’larning SHA-256 lari `build_out/binaries.sha256` da, loglar `build_out/logs/` da. Patch’siz binary’lar ikki marta build qilinganda bit-bit bir xil chiqdi.

## 3. Manba yoki build’dagi o‘zgarishlar (hammasi hujjatlashtirilgan)

1. **ECC: `patches/ecc_ub_fixes.patch` (3 qator).**
   - **Muammo.** `get_3OT` (`utility.cpp`) va `get_overlap_3OT` (`decoder.cpp`) `int` qaytarishi kerak, lekin ba’zi yo‘llarda `return` siz tugaydi. C++ da bu aniqlanmagan xatti-harakat. GCC 13 `-O2` bilan build qilingan original encoder doimiy bo‘lmagan **har bir** xaritada qulaydi (segfault yoki FPE).
   - **Tuzatish.** Ikkala funksiya oxiriga `return 0;` qo‘shildi. Bu funksiyalarning qiymatini hech bir chaqiruvchi ishlatmaydi, shuning uchun mantiq o‘zgarmaydi.
   - **Qo‘shimcha.** Decoder kirish buferi 16 ta nol bayt bilan kengaytirildi, chunki arifmetik dekoder oqim oxiridan keyin oldinga o‘qiydi.
   - **Tekshiruv.** Patch’dan keyin ASan+UBSan build’i 9 ta xaritada xatosiz ishladi, oqimlar `-O2` build bilan bayt-bayt bir xil.
2. **HM: `-Wno-error=array-bounds`.** HM `-Werror` bilan build qilinadi. GCC 13 `TComLoopFilter.cpp:214` da soxta `-Warray-bounds` ogohlantirishini beradi, shu bitta ogohlantirish xato emas deb belgilandi. Ogohlantirish flaglari mashina kodini o‘zgartirmaydi, manba tegilmagan.
3. **Compresso: `cpso_cli.cpp`.** Repo’da C++ CLI yo‘q. Wrapper Python paketining `compress()` standart sozlamalarini aynan takrorlaydi:
   - Fortran tartibi, `sx = H`;
   - 4×4×1 bloklar, `connectivity` 4, `random_access_z_index` yoqiq;
   - RLE xatosida 8×8×1 bloklar bilan qayta urinish.

## 4. Kirish formatlari (sintetik testda ishlatilgan)

| Vosita | Kirish | Variantlar |
|---|---|---|
| Compresso | uint16 to‘g‘ridan-to‘g‘ri | standart |
| FLIF | uint16 PGM (maxval 65535) va 8-bit rank xaritasi $\pi(x)$ | `-E60` (standart), `-E100` |
| JBIG1 | $\pi(x)$ bit-plane’lari (PGM, maxval $=\max(K-1,1)$), `-q` | Gray (standart) va ikkilik (`-b`; decoder’ga ham `-b` kerak) |
| ECC | $\pi(x)$, 8-bit YUV 4:0:0, 1 kadr (`-t 400`) | standart |
| HEVC SCC | $\pi(x)$, 8-bit YUV 4:0:0; `encoder_intra_main_scc.cfg` + `TransquantBypassEnable=1`, `CUTransquantBypassFlagForce=1`, `CostMode=lossless`, `ConformanceWindowMode=1` | palette yoqiq, faqat intra |

## 5. Lossless tekshiruv (`selftest/`, natija `build_out/selftest_result.csv`)

- **Xaritalar.** 9 ta sintetik xarita; haqiqiy ma’lumot ishlatilmagan:
  - doimiy (0 va 7);
  - K = 2, 10, 30, 120, 256;
  - labellari 65535 gacha bo‘lgan K = 12;
  - shovqinli K = 5;
  - o‘lchami 8 ga karrali bo‘lmagan 100×75.
- **Natija.** 9 xarita × 9 vosita-variant = **81/81 LOSSLESS**. Har biri pikselma-piksel solishtirilgan; rank xaritalari $\pi(x)$ bilan.
- **Yo‘lda topilgan va tuzatilgan xatolar.** Ikkalasi ham mening chaqiruvim yoki test kodimda edi, vositalarda emas:
  - JBIG ikkilik variantida decoder’ga `-b` berilmagan edi;
  - test skriptida PBM (`P4`) o‘qilmas edi.

## 6. BDLC va Python codec’lar uchun muhit (`bdlc-bench:2026-10-29`)

- **Image.** `bdlc-bench:2026-10-29` (`sha256:d98f9339…`) = `bdlc-baselines` + Python muhiti; skript: `setup_python.sh`.
- **Python.** 3.14.4, Windows bilan bir xil versiya. Manba: python-build-standalone `20260414`, 127 044 682 bayt; SHA-256 rasmiy `SHA256SUMS` bilan mos. Fayl: `downloads\python\`.
- **Paketlar.** `requirements.txt` dagi barcha pinlar aynan shu versiyalarda (`build_out/pip_freeze_linux.txt`; farq faqat `pip` ning o‘zi).
  - Linux wheel’lari `downloads\wheels-cp314-linux\` da saqlangan: 28 ta fayl, 145.1 MB, hashlari `build_out/wheels.sha256` da.
  - Keyingi o‘rnatishlar internetsiz, faqat shu papkadan qilinadi.
- **Tekshiruv** (`check_bdlc.sh`):
  - `freeze.json` hashlari mos;
  - BDLC unit testlari 10/10, shu jumladan dev xaritalaridagi test.

## 7. Konteynerda vaqt o‘lchash sharoiti (`env_calibration.py`; natija `build_out/env_calibration_*.csv`)

Bu natija sifatida ishlatilmaydi, faqat muhit tekshiruvi. O‘lchov sharoiti:
- dev xaritalari (52 ta), bench/worker.py bilan bir xil sikl;
- vCPU 2 ga pin (`sched_setaffinity` ishladi), `nice` −10 (`--cap-add SYS_NICE` bilan);
- har kodek alohida process’da, ikki raund.

| Kodek | Bayt (Win = Linux) | Encode: Win → Linux, MPix/s | Decode: Win → Linux, MPix/s |
|---|---:|---|---|
| bdlc | 25 876 | 1552 → 1567 (1.01×) | 1974 → 2091 (1.06×) |
| jpegls | 145 426 | 1544 → 2395 (1.55×) | 3423 → 4112 (1.20×) |
| zstd3 | 165 076 | 3090 → 3372 (1.09×) | 3095 → 4893 (1.58×) |
| zstd19 | 131 852 | 25.9 → 30.9 (1.19×) | 3920 → 4613 (1.18×) |
| crackle_mo0_zstd19 | 35 424 | 179 → 342 (1.91×) | 288 → 585 (2.03×) |
| jpegxl7 | 75 054 | 9.0 → 12.6 (1.39×) | 34.0 → 47.1 (1.39×) |

- **Hajm.** Hamma kodekda bayt soni Windows bilan bir xil: oqimlar platformaga bog‘liq emas.
- **Takrorlanuvchanlik.** Ikki raund orasidagi nisbat 0.98–1.02; faqat zstd19 decode’da 0.935.
- **Asosiy topilma: tezlik nisbatlari platformaga bog‘liq.** BDLC (Numba/LLVM) ikkala tizimda bir xil tezlikda, raqib kutubxonalar esa Linux’da 1.1–2.0× tezroq. BDLC tezlanishi, Windows → Linux:

  | Raqib | Encode | Decode |
  |---|---|---|
  | Crackle mo0+zstd19 | 8.67× → 4.58× | 6.86× → 3.58× |
  | JPEG-LS | 1.01× → 0.65× | 0.58× → 0.51× |
  | JPEG XL e7 | 172× → 124× | 58× → 44× |
  | zstd3 | 0.50× → 0.46× | 0.64× → 0.43× |

  Sababi tekshirilmagan; ehtimol Windows wheel’lari boshqa kompilyator yoki flaglar bilan build qilingan.
- **Xulosa.**
  - Test A dagi tezlik nisbatlari faqat Windows uchun to‘g‘ri va maqolada shunday belgilanadi.
  - Protokol B da hamma kodek, shu jumladan BDLC, shu konteynerda o‘lchanadi.
  - Konteyner — Docker Desktop’ning WSL2 virtual mashinasi. vCPU fizik yadroga qat’iy bog‘lanmaydi, bu cheklov sifatida yoziladi.

## 8. Harness adapterlari (`bench/external.py`) va harness o‘zgarishlari (2026-10-29)

**11 ta tashqi konfiguratsiya** (`backends.EXTERNAL`; `DEFAULT` — test A ning 30 tasi, o‘zgarmagan):

| Nomi | Vosita | Kirish | σ (label to‘plami) |
|---|---|---|---|
| `ecc_pi`, `ecc_direct` | ECC-2026 | π(x) yoki label ≤ 255 o‘zi, 8-bit YUV 4:0:0 | σ*(K) / 0 (ECC palitrasini o‘zi saqlaydi) |
| `hevc_scc_pi`, `hevc_scc_direct` | HM-16.21+SCM-8.8 | xuddi shunday | σ*(K) / 0 |
| `jbig_gray_pi`, `jbig_binary_pi` | JBIG-KIT 2.1 (`-q`) | π(x) bit-plane’lari | σ*(K) |
| `flif_u16_e60`, `flif_u16_e100` | FLIF 0.4 | 16-bit PGM | 0 |
| `flif_pi_e60`, `flif_pi_e100` | FLIF 0.4 | π(x), 8-bit PGM | σ*(K) |
| `compresso` | Compresso (`cpso_cli`) | uint16 | 0 |

**Oqim va bayt hisobi** (Q1_REJA §1.3):
- Konteyner tuzilishi: `uvarint H, uvarint W, [label bloki], vosita oqimi`.
- Vositalarning o‘z oqimida H va W bor, decoder’lari o‘lchamsiz ishlaydi. Shuning uchun η = 0: `uvarint` prefiksi hisobga kirmaydi.
- **Label bloki aynan σ*(K) bayt.** U enumerativ kod: K−1 uchun 17 bit, keyin S ning kombinatorik rangi $\sum_j \binom{S[j]}{j+1}$. Rejadagi nazariy minimum shu tarzda haqiqiy, decode qilinadigan oqimga aylandi.
- **Tekshiruv.** 456 ta tasodifiy to‘plamda kod xatosiz tiklandi; K = 10, 27, 256 da log₂C = 138.2, 338.9, 2411.3 bit — rejadagi bilan bir xil. Decode eng sekin holatda (K = 256) 26 ms.
- **Worker yozuvlari.** `bytes` — hisobdagi hajm, `stream_bytes` — to‘liq konteyner.

**Qamrov qoidasi** (Q1_REJA §1.4):
- π konfiguratsiyalari K > 256 da, `direct` lar label > 255 da `NotApplicable` beradi.
- Worker bunday holatni xato emas, `not_applicable` deb yozadi.
- `run_bench` kutilgan juftliklardan ularni ayiradi va `not_applicable.json` ga yozadi.
- Preflight’da qo‘llanmaydigan probe o‘tkazib yuboriladi, lekin kamida bittasi bajarilishi shart. Shu maqsadda kichik labelli yangi probe qo‘shildi.

**CLI vaqti** (Q1_REJA §1.6):
- Worker har kodek uchun 1×1 xaritada `repeats` ta null juftlikni o‘lchaydi.
- Report CLI kodeklarida `encode_s = median − null median` ni ishlatadi. Xom vaqt (`*_raw`) va null (`null_*`) ham `per_image.csv` da qoladi.
- Vaqtinchalik fayllar `/dev/shm` (tmpfs) da turadi.

**Linux’da pin:**
- `worker.pin()`: `sched_setaffinity` va `setpriority(−10)`. Konteyner `--cap-add SYS_NICE` bilan ishga tushiriladi.
- CLI vositalar pin va prioritetni ota process’dan meros oladi.
- Protokolga quyidagilar yoziladi: platformaga mos prioritet, Linux’da CPU nomi, tashqi binary’lar va HM cfg ning SHA-256 lari.

**Tekshiruv:**
- **Konteyner preflight** (`preflight.sh`): 41/41 konfiguratsiya o‘tdi.
- **Windows preflight:** test A ning 30 tasi o‘tdi, 11 tashqi konfiguratsiya "external tool not found" bilan unavailable (kutilganidek).
- **Uchdan-uchgacha sinov run’i:** `runs\20261029_064301_development_container_smoke\` (`smoke_dev.sh`). Konteynerda, dev’ning 52 xaritasida, 3 takror; BDLC, JPEG-LS, Crackle mo0+zstd19 va 11 tashqi konfiguratsiya.
  - **Holat:** COMPLETE, 728/728 o‘lchov, 0 xato, verifikatsiya 728/728. Pin va nice −10 hamma kodekda qo‘llangan.
  - **Null-vaqt:** ECC encode 3.1–3.4 ms, HM 2.8 ms, FLIF 1.2 ms, Compresso 0.7 ms, JBIG 0.4 ms.
  - **Hajm natijasi (dev, sinov uchun; hajm deterministik):**

    | Kodek | Bayt | BDLC ga nisbatan |
    |---|---:|---:|
    | **ecc_direct** | **23 985** | **−7.3%** (52/52 xaritada kichik) |
    | **ecc_pi** | **24 916** | **−3.7%** (48/52) |
    | bdlc | 25 876 | — |
    | crackle_mo0_zstd19 | 35 424 | +36.9% |
    | flif_u16_e100 | 50 241 | +94.2% |
    | jbig_binary_pi | 69 590 | +168.9% |
    | hevc_scc_direct | 73 690 | +184.8% |
    | compresso | 150 964 | +483.4% |

  - **Tezlik:** BDLC ECC’dan encode’da 18.7×, decode’da 8.6× tez (sof vaqt, konteyner).
  - **Xulosa:** ECC-2026 dev’da BDLC dan hajmda yaxshiroq. Batafsil: `NATIJALAR_TAHLILI_UZ.md`.

**Test A kodi saqlangan.** `bench\` o‘zgargani uchun test A ishlatgan aynan fayllar `archive\harness_testA\` ga tiklandi va saqlandi (hashlar `protocol_test.json` bilan mos).

## 9. Ochiq masalalar va cheklovlar

- **ECC’ning boshqa xavfli joylari.** Yana 5 ta funksiyada xuddi shu "return yo‘q" ogohlantirishi bor: `get_direction1`, `get_direction2`, `get_dec_MSC`, `get_rmse_index`, `to_3OT`. Ularning qiymati ishlatiladi, sintetik testda esa bu yo‘llarga kirilmadi. Bundan tashqari:
  - `objectExpand` 10 000 elementli qat’iy stekka ega;
  - chiqish buferi 10 000 000 bayt bilan cheklangan.

  Shuning uchun haqiqiy ma’lumotda har bir ECC oqimi alohida process’da decode qilib tekshiriladi. Xato bo‘lsa yashirilmaydi, "failure" sifatida yoziladi.
- **ECC tezligiga ta’sir.** ECC encoder har chaqiruvda 10 MB buferni nol bilan to‘ldiradi. Bu uning CLI vaqtiga kiradi; protokol B dagi CLI vaqt tuzatmasi ($t - t_{\text{null}}$) buni qanday hisoblashi oldindan yoziladi.
- **Mualliflarga xabar.** ECC xatolarini mualliflarga GitHub issue sifatida yuborish mumkin. Bu ochiq post bo‘ladi, shuning uchun faqat sizning ruxsatingiz bilan.
- **Vaqt o‘lchovi muhiti — qaror qabul qilindi (2026-10-29).** Protokol B da barcha kodeklar (BDLC, 24 ta hozirgi raqib va 5 ta yangi CLI vosita) shu `bdlc-bench` konteynerida o‘lchanadi (§7). Buning uchun `bench/worker.py` dagi `pin()` Linux’da ham ishlashi kerak (`sched_setaffinity` + `setpriority`). Hozir u faqat Windows’da pin qiladi; bu protokol B dan oldin qilinadi.
