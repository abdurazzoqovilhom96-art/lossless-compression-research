# BDLC v1: metod va matematik asos

**BDLC** (Boundary-Displacement Label Codec) — 2D `uint16` label xaritalari (segmentatsiya maskalari) uchun yo‘qotishsiz kodek. Bu hujjat muzlatilgan v1 ni to‘liq tavsiflaydi: `bdlc/core.py` SHA-256 `af4cf5e7…dff687`, `bdlc/api.py` `9d2985eb…33ec14`, jadval T1 `8295261d…27ea559` (to‘liq hashlar `freeze.json` da).

Hujjatdagi har bir qoida koddagi aniq qatorga mos keladi. Raqamli natijalar bu yerda keltirilmaydi — ular `NATIJALAR_TAHLILI_UZ.md` da, o‘lchangan CSV’lardan olinadi.

---

## 1. Belgilashlar

- Tasvir $X \in \{0,\dots,65535\}^{H\times W}$, qatorlar $r=0..H-1$, ustunlar $c=0..W-1$.
- $\mathcal S = \{S[0] < S[1] < \dots < S[K-1]\}$ — tasvirda uchraydigan label’lar to‘plami; $\lambda_0 = S[0]$.
- **O‘zgarish nuqtalari** (qator $r$): $C_r = \{c \in [1, W-1] : X[r,c] \ne X[r,c-1]\}$.
- **Run** — $[a_0, a_1)$ oralig‘i, unda qator bir xil label $\ell$ ga ega va $a_0 \in \{0\}\cup C_r$, $a_1 \in C_r \cup \{W\}$ — keyingi o‘zgarish nuqtasi.
- **Mos yozuvlar qatori** $R$: $r>0$ da $R = X[r-1,\cdot]$; $r=0$ da virtual qator $R \equiv \lambda_0$ (hech qanday o‘zgarish nuqtasi yo‘q).
- $P = C_{r-1}$ (yuqori qatorning o‘zgarish nuqtalari), oxiriga ikki marta $W$ qo‘shilgan: `ppos`.
- Har bir $p \in P$ uchun **siljish (slope)** $\sigma(p)$ saqlanadi: shu chegara yuqoridagi qatorga nisbatan necha ustunga siljigani ($\S$4.4), noma’lum bo‘lsa $\mathrm{UNK}$; va $\sigma_2(p)$ — shu chegaraning o‘z mos chegarasining siljishi.

Har bir qaror **binar**: yo kontekstga ega adaptiv bit, yo ehtimolligi 1/2 bo‘lgan "bypass" bit.

## 2. Oqim formati (`api.py`)

| Bayt(lar) | Mazmun |
|---|---|
| 0 | `0xBD` (magic) |
| 1 | bit7 = raw, bit6 = crc, bit5..3 = model id, bit2..0 = flaglar |
| varint | $H$ (unsigned LEB128) |
| varint | $W$ |
| 4 bayt (ixtiyoriy) | CRC32 (piksellar, little-endian `uint16`) — faqat `crc=1` da |
| qolgani | payload: range-coder oqimi yoki raw holatda $2HW$ bayt piksel |

- **Model id:** 1 = muzlatilgan boshlang‘ich jadval T1; 2 = bir tekis ($p=1/2$, $n=0$) — ablation; 3 = tashqi jadval (faqat tadqiqot, dekoderga jadval beriladi).
- **Flaglar:** `F_NOSLOPE=1` (slope konteksti va bashorati o‘chiriladi), `F_NOK2=2` (ikkinchi label kandidati o‘chiriladi), `F_NOPASS=4` (PASS rejimi o‘chiriladi). Flaglar oqimga yoziladi, dekoder ularni o‘qiydi.

### 2.1. Raw fallback chegarasi

Kodlash davomida har qator boshida chiqarilgan baytlar soni $2HW$ dan oshsa yoki yakuniy payload $\ge 2HW$ bo‘lsa, piksellar xom holda yoziladi. Demak **har qanday kirish uchun**

$$B \;\le\; 2 + |\mathrm{varint}(H)| + |\mathrm{varint}(W)| + 4\cdot\mathrm{crc} + 2HW .$$

Ya’ni xom 16-bit saqlashga nisbatan eng yomon kengayish faqat sarlavha: $H,W < 2^{21}$ uchun ko‘pi bilan $2+3+3+4 = 12$ bayt.

## 3. Entropiya kodlovchi (`core.py`, `_enc`, `_dec`)

### 3.1. Binar range coder (LZMA uslubi)

Holat: `low` (33 bit, carry bilan), `range` $R$ (32 bit). Boshlang‘ich: `low = 0`, $R = 2^{32}-1$, `cache = 0`, `cache_size = 1`.

Kontekst $x$ ning ehtimollik holati $Q_x \in [0, 2^{24}]$. Kodlashda ishlatiladigan ehtimollik:

$$p_1 = \mathrm{clip}(\lfloor Q_x / 2^8 \rfloor,\; 1,\; 65535),\qquad \hat p(1) = p_1/2^{16},\quad \hat p(0) = 1-\hat p(1).$$

Bir qaror:

$$\mathrm{bound} = \lfloor R/2^{16}\rfloor \cdot (2^{16} - p_1);\qquad
b=0:\ R \leftarrow \mathrm{bound};\qquad b=1:\ \mathrm{low} \mathrel{+}= \mathrm{bound},\ R \leftarrow R-\mathrm{bound}.$$

So‘ng $R < 2^{24}$ bo‘lguncha: $R \leftarrow 2^8 R$ va `shift_low` (eng yuqori bayt `cache` orqali chiqariladi, carry `cache` ga va kutilayotgan `0xFF` baytlarga qo‘shiladi).

**Bypass bit:** $R \leftarrow \lfloor R/2\rfloor$; $b=1$ bo‘lsa `low += R`; so‘ng renormalizatsiya.

**Dekoder** 4 baytdan `code` ni yig‘adi va $b = [\mathrm{code} \ge \mathrm{bound}]$ ni tiklaydi; oqim tugagach nol baytlar bilan to‘ldiradi.

### 3.2. Intervallar hech qachon bo‘sh emas

Renormalizatsiyadan keyin doim $2^{24} \le R < 2^{32}$. $q = \lfloor R/2^{16}\rfloor \ge 2^8$, $s = R \bmod 2^{16}$ bo‘lsin. $p_1 \in [1, 65535]$ bo‘lgani uchun:

- $b=0$ intervali: $\mathrm{bound} = q(2^{16}-p_1) \ge q \ge 2^8 > 0$;
- $b=1$ intervali: $R - \mathrm{bound} = s + q\,p_1 \ge q \ge 2^8 > 0$.

Demak ikkala qaror ham qaytariladigan (dekodlanadigan), $R$ esa musbat qoladi.

### 3.3. Bitta qarorning narxi

Qaror narxi $c = -\log_2(R'/R)$, bunda $R'$ — tanlangan sub-interval.

**1-bit.** $\dfrac{R-\mathrm{bound}}{R} = \dfrac{s + q p_1}{2^{16}q + s} \ge \dfrac{p_1}{2^{16}}$, chunki bu $2^{16}s \ge p_1 s$ ga teng kuchli va $p_1 < 2^{16}$. Demak $c \le -\log_2 \hat p(1)$ — 1-bit hech qachon idealdan qimmat emas.

**0-bit.** $q \ge (R - 2^{16}+1)/2^{16}$ va $R \ge 2^{24}$ dan $\dfrac{\mathrm{bound}}{R} \ge \hat p(0)\left(1 - \dfrac{2^{16}}{R}\right) \ge \hat p(0)(1-2^{-8})$. Demak

$$c \le -\log_2 \hat p(0) - \log_2(1-2^{-8}) \le -\log_2 \hat p(0) + 0.00565 .$$

**Bypass bit.** $\lfloor R/2\rfloor / R \ge \tfrac12(1 - 1/R)$, ya’ni $c \le 1 + \log_2\frac{R}{R-1} < 1 + 10^{-7}$.

**Har qanday adaptiv qaror** uchun $\hat p \ge 2^{-16}$, shuning uchun $c \le 16 + 0.00565$ bit.

### 3.4. Oqim boshi va oxiri; payload uzunligi chegarasi

*Birinchi bayt har doim 0.* Barcha sub-intervallar boshlang‘ich $[0, 2^{32}-1)$ ichida joylashgan, shuning uchun kodlanayotgan son $< 2^{32}$ (boshlang‘ich masshtabda) va `cache` orqali chiqadigan birinchi baytga carry hech qachon tushmaydi. Kod bu baytni tashlab yuboradi (`out[1:n]`) va u 0 bo‘lmasa xato beradi; dekoder `code` ni payloadning dastlabki 4 baytidan boshlaydi.

*Flush.* Oxirgi intervalda $[\mathrm{low}, \mathrm{low}+R-1]$ eng ko‘p oxirgi nol bitga ega butun son $v$ tanlanadi, 5 marta `shift_low` qilinadi, so‘ng oxirgi nol baytlar kesiladi (dekoder ularni 0 deb o‘qiydi — natija aynan bir xil son).

*Uzunlik chegarasi.* Barcha qarorlardan keyin real interval kengligi $w = \frac{2^{32}-1}{2^{32}}\prod_i 2^{-c_i}$. Kengligi $w$ bo‘lgan har qanday yarim-ochiq intervalda maxraji $2^{k}$, $k=\lceil -\log_2 w\rceil$ bo‘lgan diadik son bor. Joriy masshtabda interval kengligi $R \ge 2^{24}$ bo‘lgani uchun bu son tanlanadigan butunlar orasida bor, `flush` esa eng qisqasini oladi. Birinchi (nol) bayt tashlab yuborilgach:

$$\boxed{\;B_{\text{payload}} \le \left\lceil \tfrac18\Big(\textstyle\sum_i c_i + 4\cdot10^{-10}\Big)\right\rceil\;}$$

Bu yerda $c_i$ $\S$3.3 dagi chegaralarga bo‘ysunadi. Natijada

$$8B_{\text{payload}} \le I + 0.00565\,D_0 + 10^{-7} D_{\text{byp}} + 8,\qquad I = \sum_{\text{adaptiv}} -\log_2\hat p_i(b_i) + D_{\text{byp}},$$

$D_0$ — adaptiv 0-qarorlar soni, $D_{\text{byp}}$ — bypass bitlar soni. $I$ — `bdlc.analyze()` qaytaradigan "ideal" bitlar yig‘indisi (aynan shu $\hat p$ bilan). Pastki chegara yo‘q: 1-bitlar va flush tufayli $8B_{\text{payload}}$ $I$ dan biroz kichik bo‘lishi ham mumkin. Development run’da `byte_breakdown.csv` dagi `payload_minus_model_bytes` ustuni shu farqni har tasvir uchun beradi.

### 3.5. Ehtimollik bahosi va Krichevsky–Trofimov (KT) tengligi

Har kontekstda sanoq $n_x$ va holat $Q_x$. Qaror $b$ kodlangandan keyin:

$$n \leftarrow \min(n+1,\ N_{\max}),\quad N_{\max}=1023;\qquad
Q \leftarrow Q + \left\lfloor \frac{(b\cdot 2^{24} - Q)\, R_n}{2^{16}} \right\rfloor,\quad R_n = \left\lfloor\frac{2^{16}}{n+1}\right\rfloor .$$

(Kodda $b=1$ uchun $Q + \lfloor (2^{24}-Q)R_n/2^{16}\rfloor$, $b=0$ uchun $Q - \lfloor Q R_n/2^{16}\rfloor$.) Yangilanish paytida doim $n \ge 1$, shuning uchun $R_n \le 2^{15}$ va qadam ko‘pi bilan farqning yarmi: $Q$ hech qachon $[0, 2^{24}]$ dan chiqmaydi.

**Teorema (KT).** Aniq bo‘lishda ($R_n = 2^{16}/(n+1)$, yaxlitlashsiz) va $N_{\max}$ ga yetilmaguncha, boshlang‘ich $p_0 = Q_0/2^{24}$ va $n_0 = m$ bo‘lsa, $k$ ta kuzatuvdan ($n_1$ tasi 1) keyin

$$p_k = \frac{(m+1)\,p_0 + n_1}{m+1+k}.$$

*Isbot (induksiya).* $k=0$ da to‘g‘ri. $k$-kuzatuvda $n = m+k$, vazn $1/(m+k+1)$: $p_k = p_{k-1} + \frac{b-p_{k-1}}{m+k+1}$, ya’ni $(m+k+1)p_k = (m+k)p_{k-1} + b$. Induksiya farazi $(m+k)p_{k-1} = (m+1)p_0 + n_1^{(k-1)}$ dan $(m+k+1)p_k = (m+1)p_0 + n_1^{(k)}$. $\square$

- **Bir tekis boshlanish** (model 2): $p_0 = 1/2$, $m=0$ ⇒ $p_k = (n_1 + \tfrac12)/(k+1)$ — aynan KT bahosi.
- **T1 jadvali** (model 1): o‘quv sanoqlari $c, c_1$ dan $Q_0 = \mathrm{round}\big(2^{24}\frac{c_1+1/2}{c+1}\big)$ ($[2^8, 2^{24}-2^8]$ ga clip), $N_0 = \min(c, 32)$; $c=0$ da $Q_0 = 2^{23}$, $N_0=0$. Agar $c \le 32$ bo‘lsa, $p_k = (c_1 + n_1 + \frac12)/(c+k+1)$ — o‘quv sanoqlaridan davom etgan KT. $c > 32$ da prior kuchi $33$ psevdo-kuzatuvga kamaytiriladi (Beta prior, o‘rtachasi $p_0$).
- $n$ $N_{\max} = 1023$ ga yetgach vazn $1/1024$ da qoladi — eksponensial unutish (EMA).
- Butun sonli $R_n$ va $\lfloor\cdot\rfloor$ KT ni taqriban beradi; koder va dekoder **aynan bir xil** butun arifmetikani bajaradi, shuning uchun bu taqriblik dekodlanuvchanlikka ta’sir qilmaydi, faqat siqishga.

### 3.6. Butun sonli kodlar

- **Exp-Golomb(0)**, $v \ge 0$: $v_1 = v+1$, $m = \lfloor\log_2 v_1\rfloor$. Prefiks: $m$ ta 1 va bitta 0 — adaptiv, $i$-bit konteksti `base + min(i, 32)` (har to‘plamga 33 kontekst). Suffiks: $v_1$ ning pastki $m$ biti — bypass. Dekoder $m > 40$ da xato beradi.
- **Truncated binary**, $0 \le v < n$, $n\ge2$: $k = \lceil\log_2 n\rceil$, $u = 2^k - n$; $v<u$ bo‘lsa $k-1$ bit, aks holda $v+u$ ning $k$ biti; barcha bitlar bypass.

## 4. Model (`_encode_core` / `_decode_core`)

### 4.1. Sarlavha (AC oqimi boshida)

$\mathrm{EG}(K-1)$, $\mathrm{EG}(S[0])$, so‘ng $i=1..K-1$ uchun $\mathrm{EG}(S[i]-S[i-1]-1)$ — uchta alohida EG kontekst to‘plami. Dekoder $K \le \min(65536, HW)$ va $S[i] \le 65535$ ni tekshiradi.

### 4.2. Qator bo‘yicha kodlash tartibi

Har qator chapdan o‘ngga run’larga bo‘linadi. Har run uchun avval **label**, keyin **run oxiri** $a_1$ kodlanadi. Run tugagach $\ell$ "ko‘rilgan" deb belgilanadi. Qator tugagach uning o‘zgarish nuqtalari va slope’lari keyingi qator uchun $P$, $\sigma$, $\sigma_2$ bo‘ladi.

### 4.3. Label

`prev` — chapdagi run label’i ($a_0=0$ da yo‘q). Run ta’rifiga ko‘ra $\ell \ne \mathrm{prev}$.

1. **Birinchi kandidat** $k_1 = R[a_0]$ (tepadagi piksel). $k_1 \ne \mathrm{prev}$ bo‘lsa, $[\ell = k_1]$ biti kodlanadi. Kontekst: $a_0=0$ → 0; $R$ da $a_0$ nuqtasida o‘zgarish bor ($R[a_0-1]\ne R[a_0]$) → 1; aks holda 2; $r=0$ bo‘lsa $+3$ (jami 6).
2. **Ikkinchi kandidat** (flag `F_NOK2` bo‘lmasa, 1-kandidat qabul qilinmagan bo‘lsa). $p_0$ — $R$ da $a_0$ dan keyingi birinchi o‘zgarish ($p_0 < W$ bo‘lsa). $k_2 = R[p_0]$. $R[a_0..p_0-1]$ o‘zgarmas va $R[p_0]\ne R[p_0-1]$ bo‘lgani uchun **doim $k_2 \ne k_1$**. $k_2 \ne \mathrm{prev}$ va $k_2 \ne e_1$ (rad etilgan 1-kandidat) bo‘lsa, $[\ell=k_2]$ kodlanadi; kontekst $d = p_0 - a_0 \in \{1, 2, \ge3\}$.
3. **Escape.** Rad etilganlar $E = \{\mathrm{prev}, e_1, e_2\}$ (mavjudlari) vaqtincha ikkala Fenwick daraxtidan olinadi: $F_u$ — hali ko‘rilmagan, $F_s$ — ko‘rilgan label’lar (rank bo‘yicha). $n_u, n_s$ — qolganlar soni.
   - $n_u>0$ va $n_s>0$ bo‘lsa, `isnew` biti kodlanadi; aks holda u ma’lum.
   - Yangi label: $\mathrm{idx}$ = ko‘rilmaganlar ichidagi rank. $n_u>1$ bo‘lsa $[\mathrm{idx}=0]$ biti (adaptiv), $\mathrm{idx}>0$ va $n_u>2$ bo‘lsa $\mathrm{idx}-1$ — truncated binary ($n_u-1$ ta).
   - Ko‘rilgan label: $n_s>1$ bo‘lsa $\mathrm{idx}$ — truncated binary ($n_s$ ta).
   - So‘ng $E$ daraxtlarga qaytariladi.

   $\ell \notin E$ (run ta’rifi va kandidatlar rad etilgani uchun), demak $\ell$ doim qolgan to‘plamda — escape har doim aniqlangan. Dekoder $n_u=n_s=0$ ni xato deb biladi.

Label manbai: `src` = 1 ($k_1$), 2 ($k_2$) yoki 0 (escape).

### 4.4. Run oxiri $a_1 \in (a_0, W]$

**Escape run** (`src = 0`, yangi obyekt boshlanishi kabi): $\mathrm{EG}(a_1-a_0-1)$; slope = UNK.

**Aks holda** $lo = a_0$ dan sikl:

1. $b_1$ — $P$ da $lo$ dan **qat’iy katta** birinchi o‘zgarish; agar $R[b_1] = \ell$ bo‘lsa, bitta keyingisi olinadi. Bir martadan ortiq o‘tkazish shart emas: ketma-ket run’lar har xil, shuning uchun keyingi o‘zgarishda $R \ne \ell$. $b_2$ — $b_1$ dan keyingi o‘zgarish yoki $W$.
2. **NOREF** ($b_1 = W$): $[a_1 = W]$ biti (kontekst $[\ell = \lambda_0]$); $a_1<W$ bo‘lsa $\mathrm{EG}(a_1 - lo - 1)$. Slope = UNK.
3. **PASS** ($a_1 > b_2$, `F_NOPASS` yo‘q): `mode_V` = 0, `PASS` = 1; $lo \leftarrow b_2$; 1-qadamga qaytish.
4. **V rejimi** ($|a_1 - b_1| \le D_{\max} = 8$): `mode_V` = 1. Bashorat $\mathrm{pred} = \mathrm{clip}(\sigma(b_1), -2, 2)$ ($\sigma=\mathrm{UNK}$ yoki `F_NOSLOPE` da 0). $\delta = a_1-b_1$, $\delta' = \delta - \mathrm{pred}$:
   - $[\delta'=0]$ biti; nol bo‘lmasa ishora $[\delta'<0]$;
   - $|\delta'| \in [1, M]$, $M = 8+\mathrm{pred}$ (manfiy) yoki $8-\mathrm{pred}$ (musbat) — chunki $|\delta|\le 8$. Truncated unary: $t=1..M-1$ uchun $[|\delta'|>t]$, birinchi 0 da to‘xtaydi; $t=M$ ga yetsa $|\delta'|=M$. $\mathrm{pred}\in[-2,2]$ ⇒ $M \ge 6$.
   - Yangi o‘zgarish nuqtasi $a_1$ ga $\sigma = \delta$, $\sigma_2 = \sigma(b_1)$ yoziladi.
5. **H rejimi** (aks holda): `mode_V` = 0, `PASS` = 0 (agar PASS yoqilgan bo‘lsa), ishora $[\delta>0]$, $\mathrm{EG}(|\delta| - 9)$. Slope = UNK.

**Kontekstlar.** $\sigma = \sigma(b_1)$, $\sigma_2 = \sigma_2(b_1)$:

- base: $\sigma \in [-2,2]$ → $\sigma+3$; $\sigma<-2$ → 6; $\sigma>2$ → 7; UNK (yoki `F_NOSLOPE`) → 0.
- rel (`REL_CTX = 1`): $\sigma_2 = \mathrm{UNK}$ → 0; $\sigma = \sigma_2$ → 1; $\sigma > \sigma_2$ → 2; aks holda 3. $sc = 4\cdot\mathrm{base} + \mathrm{rel} \in [0,31]$.
- $\mathrm{near} = [b_2 - b_1 \le 2]$.
- `mode_V`: $(2\,\mathrm{base}+\mathrm{near})\cdot2 + (\mathrm{src}-1)$ (32); `PASS`: $2\,\mathrm{near} + \mathrm{src}-1$ (4); $[\delta'=0]$ va ishora: $4\,sc + lc$, $lc = 0$ (`LEFT_CTX = 0`); unary: $4\,sc + \min(t-1,3)$; H ishorasi: base.

**Kontekst joylashuvi** (jami `NCTX = 639`): EG to‘plamlari 6×33 = 198 (K, S0, gap, escape-uzunlik, NOREF, H); L1 198 (6); L2 204 (3); ESCNEW 207; IDX0 208; END 209 (2); MV 211 (32); MP 243 (4); DZ 247 (128); DS 375 (128); DM 503 (128); HS 631 (8).

Muzlatilgan konstantalar: `NMAX = 1023`, `DMAX = 8`, `PMAX = 2`, `REL_CTX = 1`, `WIN_PRED = 0`, `H_SLOPE = 0`, `LEFT_CTX = 0`.

## 5. Dekodlanuvchanlik isboti

**Teorema.** `decode(encode(X)) = X` har qanday 2D `uint16` $X$ uchun (har bir model id va flag kombinatsiyasida).

*Isbot.* Koder chiqaradigan qarorlar ketma-ketligi $e_1, e_2, \dots$ bo‘lsin; har $e_j$ — (kontekst yoki bypass, bit). Dekoder holati: dekodlangan piksellar, $P$, $\sigma$, $\sigma_2$, Fenwick daraxtlari, ko‘rilgan bayroqlar, barcha $(Q_x, n_x)$ va range-dekoder registrlari. $j$ bo‘yicha induksiya bilan quyidagini ko‘rsatamiz: $e_j$ dan oldin dekoder model holati koder holati bilan aynan bir xil va dekoder $e_j$ ning kontekstini va bitini to‘g‘ri tiklaydi.

1. **Kontekst va kandidatlar faqat dekodlangan ma’lumotga bog‘liq.** $e_j$ ning konteksti quyidagilardan hisoblanadi: (a) $R$ — oldingi to‘liq dekodlangan qator yoki sarlavhadan ma’lum $\lambda_0$; (b) $P$, $\sigma$, $\sigma_2$ — oldingi qatorni dekodlashda yozilgan (V rejimida $\sigma = \delta = \mathrm{pred} + \delta'$ dekoderda xuddi shunday hisoblanadi; boshqa rejimlarda UNK); (c) $a_0$ (oldingi run’ning dekodlangan $a_1$), `prev`, $k_1, k_2, e_1, e_2$; (d) Fenwick/ko‘rilgan holati — oldingi label’larning funksiyasi; (e) shu run ichidagi oldingi qarorlar ($lo$, `src`, $\ell$). Hammasi $e_1..e_{j-1}$ dan aniqlanadi.
2. **Model holati bir xil.** $(Q_x, n_x)$ faqat $x$ kontekstda kodlangan bitlar bilan, bir xil butun formulada yangilanadi (§3.5). Model id va flaglar sarlavhadan o‘qiladi, boshlang‘ich jadval esa model id bo‘yicha bir xil.
3. **Bit tiklanadi.** Bir xil $p_1$ va bir xil $R$ da dekoder `code` ni `bound` bilan solishtiradi; §3.2 ga ko‘ra ikkala sub-interval bo‘sh emas, standart range-coding invarianti (code ∈ joriy interval) saqlanadi. Bypass bitlar ham shunday. Flush tanlagan $v$ oxirgi interval ichida (§3.4) va kesilgan nol baytlar dekoderda nol bilan to‘ldiriladi — shuning uchun oxirgi qarorlar ham to‘g‘ri tiklanadi.
4. **Tuzilma tiklanadi.** Dekoder koder bilan bir xil shartlarda bir xil qarorlarni kutadi: $k_1 \ne \mathrm{prev}$ sharti, $p_0<W$, $k_2\notin\{\mathrm{prev},e_1\}$, $n_u,n_s$ shartlari, PASS/V/H tartibi (`mode_V`, keyin `PASS`, keyin H) — bular 1-banddagi kattaliklarning funksiyasi. Label $\ell$ dekoderda $k_1$, $k_2$ yoki Fenwick `select` orqali tiklanadi (rank → $S[q]$); $a_1$ esa $a_0 + 1 + L$, $b_1 + \delta$ yoki $W$ orqali.

Induksiya bo‘yicha barcha qarorlar va barcha run’lar tiklanadi; har run $[a_0,a_1)$ ni $\ell$ bilan to‘ldirgani uchun $X$ to‘liq tiklanadi. Raw holat trivial. $\square$

**Yaroqsiz oqimlar.** Dekoder quyidagilarni tekshiradi va buzilsa `ValueError` beradi: magic, model id, $H,W>0$, $HW \le 2^{28}$, CRC (bo‘lsa), raw uzunlik, EG prefiksi $\le 40$, $K \le \min(65536, HW)$, $S[i]\le65535$, escape’da $n_u+n_s>0$, rank $< K$, har bir $a_1 \in (lo, W]$, PASS’da $b_2<W$, H magnitudasi chegarasi, va oxirida **barcha $K$ label ko‘rilgan** (`cnt[0] == 0`). Fuzz testi (3000 ta buzilgan oqim) va `NUMBA_BOUNDSCHECK=1` bilan to‘liq test to‘plami o‘tgan (2026-10-28).

## 6. Murakkablik

$E_r = |C_r|$, $E = \sum_r E_r$, $N_{\text{esc}}$ — escape qilingan run’lar soni.

- **Encode:** label skani $O(HW)$; $S$ ni saralash $O(K\log K)$, $K\le 2^{16}$; har qator o‘zgarishlarni topish $O(W)$; har run uchun qarorlar soni $O(1)$ + PASS qadamlari, va $P$ ko‘rsatkichlari ($j$, $jj$) qator ichida faqat oldinga yuradi ⇒ qator uchun $O(W + E_r + E_{r-1})$; escape Fenwick amallari $O(\log K)$. Jami $O(HW + E + N_{\text{esc}}\log K)$; $2^{16}$ o‘lchamli yordamchi massivlar — o‘zgarmas xarajat.
- **Decode:** xuddi shu qarorlar + har pikselni yozish: $O(HW + E + N_{\text{esc}}\log K)$.
- Xotira: $O(HW)$ chiqish + $O(W + K + 2^{16})$ ish xotirasi.

## 7. Implementatsiya eslatmalari (natijaga ta’sir qiladi)

- Kod Numba (LLVM JIT) da. Kodlash sikllari `@njit(_nrt=False)`: NRT refcount bilan inline helperlar bir qarorga ~40 ns sarflagan, NRT siz ~3 ns. NRT siz funksiyalar xotira ajrata olmaydi, shuning uchun barcha buferlar `encode_kernel`/`decode_kernel` da ajratiladi.
- JIT kompilyatsiyasi birinchi chaqiruvda (yoki disk cache’dan yuklash) bo‘ladi; benchmark’da u warm-up’ga tushadi, cold-start alohida o‘lchanadi.
- Yangi ajratilgan chiqish massiviga birinchi yozish (masalan 512 KB) sahifa xatolari tufayli ~110 µs qo‘shadi; bu xarajat chiqishni yangi massivga yozadigan barcha kodeklarda bor.

## 8. Metrika formulalari (benchmark)

$B_i$ — $i$-tasvirning to‘liq oqim hajmi (bayt; barcha sarlavha/palitra/wrapper ichida), $N_i$ — piksellar soni, $t_i$ — takrorlar medianasi (sekund).

- $\mathrm{bpp}_i = 8B_i/N_i$; **micro bpp** $= 8\sum B_i / \sum N_i$; **macro bpp** = $\mathrm{bpp}_i$ o‘rtachasi; $\mathrm{CR} = 16/\text{micro bpp}$.
- **Hajm yutug‘i** (faqat ikkala kodek tugatgan tasvirlar kesishmasida): $100\,(1 - \sum B^{\text{BDLC}} / \sum B^{\text{ref}})$.
- **Tezlanish:** $\sum t^{\text{ref}} / \sum t^{\text{BDLC}}$ (encode va decode alohida); vaqt qisqarishi $100\,(1 - T^{\text{BDLC}}/T^{\text{ref}})$; o‘tkazuvchanlik $\sum N / \sum t / 10^6$ MPix/s.
- **Qo‘shma yutuq (tasvir):** $B^{\text{BDLC}} < B^{\text{ref}}$ va $t_{\text{enc}}^{\text{BDLC}} < t_{\text{enc}}^{\text{ref}}$; decode yutug‘i alohida.
- Qamrovi to‘liq bo‘lmagan summary qatori belgilanadi va g‘olib e’lon qilishda ishlatilmaydi.
- **Sequence (klaster) darajasidagi testlar:** har sequence uchun $\log(\sum B^{\text{BDLC}}/\sum B^{\text{ref}})$; sign test $P[X \ge w]$, $X\sim\mathrm{Bin}(n, 1/2)$; aniq bir tomonlama Wilcoxon signed-rank (nollar tashlanadi, teng $|d|$ ga o‘rtacha rank). $n$ ta sequence’da eng kichik erishiladigan bir tomonlama p-qiymat $2^{-n}$; $n=4$ da $0.0625$ — shuning uchun 4 sequence bilan ahamiyatlilik da’vo qilinmaydi.
