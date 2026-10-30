"""BDLC v1 numerical core (Numba).

Boundary-Displacement Label Coding: every image row is a sequence of runs;
each run's label is predicted from the row above and each run end is coded
as a displacement from the matching boundary of the row above.  All decisions
are binary and coded with an LZMA-style range coder driven by count-adaptive
(Krichevsky-Trofimov) probability estimates.  Encoder and decoder execute the
same integer arithmetic, so the model state is identical on both sides.
See METOD_VA_MATEMATIKA_UZ.md for the formal specification.

Implementation note: the coding loops are compiled with ``_nrt=False``.  With
Numba's reference counting enabled, every inlined helper that receives an
array argument pays atomic incref/decref operations (~40 ns per binary
decision measured); without NRT a decision costs ~3 ns.  NRT-free functions
cannot allocate, so all buffers are allocated by thin wrappers.
"""
import numpy as np
from numba import njit

# ---------------------------------------------------------------- constants
TOP = 1 << 24            # range renormalisation threshold
MASK32 = 0xFFFFFFFF
QONE = 1 << 24           # probability state scale (p1 = Q / 2^24)
NMAX = 1023              # KT counting up to NMAX, then exponential forgetting
DMAX = 8                 # largest |delta| coded in vertical mode
UNK = 1 << 20            # "slope unknown" sentinel

# ablation flags (also stored in the stream header)
F_NOSLOPE = 1
F_NOK2 = 2
F_NOPASS = 4

# context layout
EG_W = 33
CX_EG_K = 0
CX_EG_S0 = 33
CX_EG_GAP = 66
CX_EG_ESC = 99
CX_EG_NOREF = 132
CX_EG_H = 165
CX_L1 = 198      # 6  label == pixel above
CX_L2 = 204      # 3  label == next run above
CX_ESCNEW = 207  # 1  escape: unseen label?
CX_IDX0 = 208    # 1  escape: smallest unseen?
CX_END = 209     # 2  no reference boundary: run reaches row end?
CX_MV = 211      # 32 vertical mode?  (slope base class 8 x near 2 x source 2)
CX_MP = 243      # 4  pass mode?
CX_DZ = 247      # 128 delta' == 0?   (slope class 32 x left-edge class 4)
CX_DS = 375      # 128 delta' < 0?
CX_DM = 503      # 128 |delta'| unary bins (slope class 32 x bin 4)
CX_HS = 631      # 8  horizontal-mode sign (slope base class)
NCTX = 639
PMAX = 2        # largest |predicted displacement|
REL_CTX = 1      # 1: condition displacement on second-order slope relation (development option)
WIN_PRED = 0     # 1: vertical window centred on b1+pred, else on b1 (development option)
H_SLOPE = 0      # 1: horizontal-mode displacements are tracked as slopes (development option)
LEFT_CTX = 0     # 1: condition delta' on the displacement of the run's left edge (development option)
# cost-accounting slots for bypass bits: NCTX + EG set index (0..5), NCTX + 6 for escape indices
NCOST = NCTX + 8

RECIP = (65536 // (np.arange(NMAX + 1, dtype=np.int64) + 1)).astype(np.int64)
UNIFORM_Q0 = np.full(NCTX, 1 << 23, np.int64)   # p1 = 1/2 for every context
UNIFORM_N0 = np.zeros(NCTX, np.int64)


# ---------------------------------------------------------------- range encoder
@njit(cache=True, inline='always')
def _shift_low(es, out):
    low = es[0]
    if low < 0xFF000000 or low > MASK32:
        carry = low >> 32
        temp = es[2]
        pos = es[4]
        n = es[3]
        while n > 0:
            out[pos] = (temp + carry) & 0xFF
            pos += 1
            temp = 0xFF
            n -= 1
        es[4] = pos
        es[3] = 0
        es[2] = (low >> 24) & 0xFF
    es[3] += 1
    es[0] = (low & 0x00FFFFFF) << 8


@njit(cache=True, inline='always')
def _enc(es, out, Q, N, recip, cost, ctx, bit):
    q = Q[ctx]
    p1 = q >> 8
    if p1 < 1:
        p1 = 1
    elif p1 > 65535:
        p1 = 65535
    if cost.shape[0] > 0:
        cost[ctx] -= np.log2((p1 if bit else 65536 - p1) / 65536.0)
        if cost.shape[0] > NCOST:
            cost[NCOST + 2 * ctx + bit] += 1.0
    rng = es[1]
    bound = (rng >> 16) * (65536 - p1)
    if bit == 0:
        rng = bound
    else:
        es[0] += bound
        rng -= bound
    while rng < TOP:
        rng <<= 8
        _shift_low(es, out)
    es[1] = rng
    n = N[ctx]
    if n < NMAX:
        n += 1
        N[ctx] = n
    if bit:
        Q[ctx] = q + (((QONE - q) * recip[n]) >> 16)
    else:
        Q[ctx] = q - ((q * recip[n]) >> 16)


@njit(cache=True, inline='always')
def _enc_direct(es, out, cost, slot, bit):
    if cost.shape[0] > 0:
        cost[slot] += 1.0
    rng = es[1] >> 1
    if bit:
        es[0] += rng
    while rng < TOP:
        rng <<= 8
        _shift_low(es, out)
    es[1] = rng


@njit(cache=True, _nrt=False)
def _enc_eg(es, out, Q, N, recip, cost, base, v):
    """Exp-Golomb(0) of v >= 0: adaptive unary prefix, bypass suffix."""
    v1 = v + 1
    m = 0
    while (v1 >> (m + 1)) != 0:
        m += 1
    for i in range(m):
        _enc(es, out, Q, N, recip, cost, base + min(i, EG_W - 1), 1)
    _enc(es, out, Q, N, recip, cost, base + min(m, EG_W - 1), 0)
    slot = NCTX + base // EG_W
    for i in range(m - 1, -1, -1):
        _enc_direct(es, out, cost, slot, (v1 >> i) & 1)


@njit(cache=True, _nrt=False)
def _enc_tb(es, out, cost, v, n):
    """Truncated binary code of 0 <= v < n (n >= 2), bypass bits."""
    k = 0
    while (1 << k) < n:
        k += 1
    u = (1 << k) - n
    if v < u:
        for i in range(k - 2, -1, -1):
            _enc_direct(es, out, cost, NCTX + 6, (v >> i) & 1)
    else:
        x = v + u
        for i in range(k - 1, -1, -1):
            _enc_direct(es, out, cost, NCTX + 6, (x >> i) & 1)


@njit(cache=True, _nrt=False)
def _flush(es, out):
    """Terminate: pick the value with most trailing zero bits in [low, low+range)."""
    low = es[0]
    hi = low + es[1] - 1
    v = low
    for k in range(32, -1, -1):
        m = (1 << k) - 1
        c = (low + m) & ~m
        if c <= hi:
            v = c
            break
    es[0] = v
    for _ in range(5):
        _shift_low(es, out)


# ---------------------------------------------------------------- range decoder
@njit(cache=True, inline='always')
def _dec(ds, data, Q, N, recip, ctx):
    q = Q[ctx]
    p1 = q >> 8
    if p1 < 1:
        p1 = 1
    elif p1 > 65535:
        p1 = 65535
    rng = ds[1]
    code = ds[0]
    bound = (rng >> 16) * (65536 - p1)
    if code < bound:
        rng = bound
        bit = 0
    else:
        code -= bound
        rng -= bound
        bit = 1
    while rng < TOP:
        rng <<= 8
        pos = ds[2]
        b = data[pos] if pos < data.shape[0] else 0
        ds[2] = pos + 1
        code = ((code << 8) | b) & MASK32
    ds[0] = code
    ds[1] = rng
    n = N[ctx]
    if n < NMAX:
        n += 1
        N[ctx] = n
    if bit:
        Q[ctx] = q + (((QONE - q) * recip[n]) >> 16)
    else:
        Q[ctx] = q - ((q * recip[n]) >> 16)
    return bit


@njit(cache=True, inline='always')
def _dec_direct(ds, data):
    rng = ds[1] >> 1
    code = ds[0]
    if code >= rng:
        code -= rng
        bit = 1
    else:
        bit = 0
    while rng < TOP:
        rng <<= 8
        pos = ds[2]
        b = data[pos] if pos < data.shape[0] else 0
        ds[2] = pos + 1
        code = ((code << 8) | b) & MASK32
    ds[0] = code
    ds[1] = rng
    return bit


@njit(cache=True, _nrt=False)
def _dec_eg(ds, data, Q, N, recip, base):
    m = 0
    while _dec(ds, data, Q, N, recip, base + min(m, EG_W - 1)):
        m += 1
        if m > 40:
            return -1
    v1 = 1
    for _ in range(m):
        v1 = (v1 << 1) | _dec_direct(ds, data)
    return v1 - 1


@njit(cache=True, _nrt=False)
def _dec_tb(ds, data, n):
    k = 0
    while (1 << k) < n:
        k += 1
    u = (1 << k) - n
    x = 0
    for _ in range(k - 1):
        x = (x << 1) | _dec_direct(ds, data)
    if x < u:
        return x
    x = (x << 1) | _dec_direct(ds, data)
    return x - u


# ---------------------------------------------------------------- Fenwick tree over label ranks
@njit(cache=True, inline='always')
def _fw_add(t, K, i, d):
    i += 1
    while i <= K:
        t[i] += d
        i += i & (-i)


@njit(cache=True, inline='always')
def _fw_prefix(t, i):
    s = 0
    while i > 0:
        s += t[i]
        i -= i & (-i)
    return s


@njit(cache=True, _nrt=False)
def _fw_select(t, K, k):
    """0-based rank of the k-th (0-based) element with count 1."""
    pos = 0
    step = 1
    while step * 2 <= K:
        step *= 2
    rem = k
    while step > 0:
        nxt = pos + step
        if nxt <= K and t[nxt] <= rem:
            pos = nxt
            rem -= t[nxt]
        step >>= 1
    return pos


@njit(cache=True, _nrt=False)
def _excl(e, rank_of, seen, Fu, Fs, K, cnt, d):
    """Add d (-1 remove / +1 restore) for label e in the tree that holds it."""
    if e >= 0:
        q = rank_of[e]
        if seen[q]:
            _fw_add(Fs, K, q, d)
            cnt[1] += d
        else:
            _fw_add(Fu, K, q, d)
            cnt[0] += d


@njit(cache=True, inline='always')
def _mark_seen(q, seen, Fu, Fs, K, cnt):
    if seen[q] == 0:
        seen[q] = 1
        _fw_add(Fu, K, q, -1)
        _fw_add(Fs, K, q, 1)
        cnt[0] -= 1
        cnt[1] += 1


@njit(cache=True, inline='always')
def _slope_class(sl, sl2, flags):
    """Returns (base class 0..7, full class 0..31, predicted displacement).

    sl  = displacement of the reference boundary (row r-1 relative to row r-2),
    sl2 = displacement of that boundary one row earlier; UNK when not tracked."""
    if sl == UNK or (flags & F_NOSLOPE):
        return 0, 0, 0
    if sl < -2:
        base = 6
    elif sl > 2:
        base = 7
    else:
        base = sl + 3
    if REL_CTX == 0 or sl2 == UNK:
        rel = 0
    elif sl == sl2:
        rel = 1
    elif sl > sl2:
        rel = 2
    else:
        rel = 3
    p = sl
    if p < -PMAX:
        p = -PMAX
    elif p > PMAX:
        p = PMAX
    return base, base * 4 + rel, p


@njit(cache=True, inline='always')
def _left_class(sl):
    if LEFT_CTX == 0 or sl == UNK:
        return 0
    return 1 if sl < 0 else (2 if sl == 0 else 3)


@njit(cache=True, _nrt=False)
def _init_sets(K, Fu, Fs, seen, cnt):
    for i in range(K + 1):
        Fu[i] = i & (-i)
        Fs[i] = 0
    for i in range(K):
        seen[i] = 0
    cnt[0] = K
    cnt[1] = 0


# ---------------------------------------------------------------- encoder
@njit(cache=True, _nrt=False)
def _scan_labels(img, flg, labs):
    H, W = img.shape
    K = 0
    for r in range(H):
        row = img[r]
        v = row[0]
        if flg[v] == 0:
            flg[v] = 1
            labs[K] = v
            K += 1
        for c in range(1, W):
            x = row[c]
            if x != v:
                v = x
                if flg[v] == 0:
                    flg[v] = 1
                    labs[K] = v
                    K += 1
    return K


@njit(cache=True, _nrt=False)
def _encode_core(img, S, K, rank_of, Q, N, es, out, limit, seen, Fu, Fs, cnt, vrow,
                 ppos, pslp, cpos, cslp, recip, cost, flags):
    """Codes the label set and all rows.  Returns 0, or 1 if the stream exceeds `limit` bytes."""
    H, W = img.shape
    _enc_eg(es, out, Q, N, recip, cost, CX_EG_K, K - 1)
    _enc_eg(es, out, Q, N, recip, cost, CX_EG_S0, S[0])
    for i in range(1, K):
        _enc_eg(es, out, Q, N, recip, cost, CX_EG_GAP, S[i] - S[i - 1] - 1)
    _init_sets(K, Fu, Fs, seen, cnt)
    lam0 = S[0]
    ppos[0] = W
    ppos[1] = W
    pm = 0
    for r in range(H):
        if es[4] + es[3] > limit:
            return 1
        ref = vrow if r == 0 else img[r - 1]
        row = img[r]
        cm = 0
        v = row[0]
        for c in range(1, W):
            x = row[c]
            if x != v:
                cpos[cm] = c
                cm += 1
                v = x
        a0 = 0
        prev = -1
        j = 0
        i = 0
        while True:
            lab = np.int64(row[a0])
            a1 = cpos[i] if i < cm else W
            while ppos[j] <= a0:
                j += 1
            # ---- label ----
            k1 = np.int64(ref[a0])
            src = 0
            e1 = -1
            e2 = -1
            if k1 != prev:
                if a0 == 0:
                    cx = 0
                elif ref[a0 - 1] != ref[a0]:
                    cx = 1
                else:
                    cx = 2
                if r == 0:
                    cx += 3
                bit = 1 if lab == k1 else 0
                _enc(es, out, Q, N, recip, cost, CX_L1 + cx, bit)
                if bit:
                    src = 1
                else:
                    e1 = k1
            if src == 0 and (flags & F_NOK2) == 0:
                p0 = ppos[j]
                if p0 < W:
                    k2 = np.int64(ref[p0])
                    if k2 != prev and k2 != e1:
                        d = p0 - a0
                        cx = 0 if d == 1 else (1 if d == 2 else 2)
                        bit = 1 if lab == k2 else 0
                        _enc(es, out, Q, N, recip, cost, CX_L2 + cx, bit)
                        if bit:
                            src = 2
                        else:
                            e2 = k2
            if src == 0:
                _excl(prev, rank_of, seen, Fu, Fs, K, cnt, -1)
                _excl(e1, rank_of, seen, Fu, Fs, K, cnt, -1)
                _excl(e2, rank_of, seen, Fu, Fs, K, cnt, -1)
                nu = cnt[0]
                ns = cnt[1]
                q = rank_of[lab]
                isnew = 1 if seen[q] == 0 else 0
                if nu > 0 and ns > 0:
                    _enc(es, out, Q, N, recip, cost, CX_ESCNEW, isnew)
                if isnew:
                    idx = _fw_prefix(Fu, q)
                    if nu > 1:
                        _enc(es, out, Q, N, recip, cost, CX_IDX0, 1 if idx == 0 else 0)
                        if idx > 0 and nu > 2:
                            _enc_tb(es, out, cost, idx - 1, nu - 1)
                else:
                    idx = _fw_prefix(Fs, q)
                    if ns > 1:
                        _enc_tb(es, out, cost, idx, ns)
                _excl(e2, rank_of, seen, Fu, Fs, K, cnt, 1)
                _excl(e1, rank_of, seen, Fu, Fs, K, cnt, 1)
                _excl(prev, rank_of, seen, Fu, Fs, K, cnt, 1)
            _mark_seen(rank_of[lab], seen, Fu, Fs, K, cnt)
            # ---- run end ----
            slope = UNK
            slope2 = UNK
            if src == 0:
                _enc_eg(es, out, Q, N, recip, cost, CX_EG_ESC, a1 - a0 - 1)
            else:
                lc = _left_class(cslp[0, i - 1] if i > 0 else UNK)
                lo = a0
                jj = j
                while True:
                    while ppos[jj] <= lo:
                        jj += 1
                    jb = jj
                    if jb < pm and ref[ppos[jb]] == lab:
                        jb += 1
                    b1 = ppos[jb]
                    if b1 >= W:
                        isend = 1 if a1 == W else 0
                        _enc(es, out, Q, N, recip, cost, CX_END + (1 if lab == lam0 else 0), isend)
                        if isend == 0:
                            _enc_eg(es, out, Q, N, recip, cost, CX_EG_NOREF, a1 - lo - 1)
                        break
                    b2 = ppos[jb + 1]
                    sb, sc, pred = _slope_class(pslp[0, jb], pslp[1, jb], flags)
                    near = 1 if b2 - b1 <= 2 else 0
                    cxv = CX_MV + (sb * 2 + near) * 2 + (src - 1)
                    cxp = CX_MP + near * 2 + (src - 1)
                    if a1 > b2 and (flags & F_NOPASS) == 0:
                        _enc(es, out, Q, N, recip, cost, cxv, 0)
                        _enc(es, out, Q, N, recip, cost, cxp, 1)
                        lo = b2
                        continue
                    dl = a1 - b1
                    dp = dl - pred
                    slope = dl
                    slope2 = pslp[0, jb]
                    hv = dp if WIN_PRED else dl
                    if -DMAX <= hv <= DMAX:
                        _enc(es, out, Q, N, recip, cost, cxv, 1)
                        _enc(es, out, Q, N, recip, cost, CX_DZ + sc * 4 + lc, 1 if dp == 0 else 0)
                        if dp != 0:
                            neg = 1 if dp < 0 else 0
                            _enc(es, out, Q, N, recip, cost, CX_DS + sc * 4 + lc, neg)
                            mag = -dp if neg else dp
                            M = DMAX if WIN_PRED else (DMAX + pred if neg else DMAX - pred)
                            t = 1
                            while t < M:
                                b = 1 if mag > t else 0
                                _enc(es, out, Q, N, recip, cost, CX_DM + sc * 4 + min(t - 1, 3), b)
                                if b == 0:
                                    break
                                t += 1
                        break
                    _enc(es, out, Q, N, recip, cost, cxv, 0)
                    if (flags & F_NOPASS) == 0:
                        _enc(es, out, Q, N, recip, cost, cxp, 0)
                    _enc(es, out, Q, N, recip, cost, CX_HS + sb, 1 if hv > 0 else 0)
                    _enc_eg(es, out, Q, N, recip, cost, CX_EG_H, (hv if hv > 0 else -hv) - DMAX - 1)
                    if H_SLOPE == 0:
                        slope = UNK
                    break
            if a1 >= W:
                break
            cslp[0, i] = slope
            cslp[1, i] = slope2
            prev = lab
            a0 = a1
            i += 1
        # current row becomes the reference row
        for t in range(cm):
            ppos[t] = cpos[t]
            pslp[0, t] = cslp[0, t]
            pslp[1, t] = cslp[1, t]
        ppos[cm] = W
        ppos[cm + 1] = W
        pm = cm
    _flush(es, out)
    return 0


@njit(cache=True)
def encode_kernel(img, recip, q0, n0, cost, flags):
    """Returns (payload uint8 array, K).  K == -2: coded stream would not beat raw storage.
    The payload omits the always-zero first byte of the LZMA-style coder and trailing zero bytes."""
    H, W = img.shape
    flg = np.zeros(65536, np.uint8)
    labs = np.empty(65536, np.int64)
    K = _scan_labels(img, flg, labs)
    S = np.sort(labs[:K])
    rank_of = np.empty(65536, np.int64)
    for i in range(K):
        rank_of[S[i]] = i
    Q = q0.copy()
    N = n0.copy()
    es = np.zeros(5, np.int64)
    es[1] = MASK32
    es[3] = 1
    limit = 2 * H * W
    # one row emits < 256*W bytes: <= 35 adaptive decisions (<= 16.01 bits each, p >= 2^-16)
    # and <= 44 bypass bits per run, <= 2 adaptive decisions per pass step
    rowb = 256 * W + 1024
    out = np.empty(limit + rowb + 4096 + 40 * K + 16, np.uint8)
    seen = np.empty(K, np.uint8)
    Fu = np.empty(K + 1, np.int64)
    Fs = np.empty(K + 1, np.int64)
    cnt = np.zeros(2, np.int64)
    vrow = np.full(W, S[0], np.uint16)
    ppos = np.empty(W + 2, np.int64)
    pslp = np.empty((2, W + 2), np.int64)
    cpos = np.empty(W + 2, np.int64)
    cslp = np.empty((2, W + 2), np.int64)
    st = _encode_core(img, S, K, rank_of, Q, N, es, out, limit, seen, Fu, Fs, cnt, vrow,
                      ppos, pslp, cpos, cslp, recip, cost, flags)
    if st != 0:
        return out[:0].copy(), -2
    n = es[4]
    if n < 1 or out[0] != 0:
        return out[:0].copy(), -1
    while n > 1 and out[n - 1] == 0:
        n -= 1
    return out[1:n].copy(), K


# ---------------------------------------------------------------- decoder
@njit(cache=True, _nrt=False)
def _decode_header(data, ds, Q, N, recip, S, H, W):
    code = 0
    for t in range(4):
        b = data[t] if t < data.shape[0] else 0
        code = (code << 8) | b
    ds[0] = code
    ds[1] = MASK32
    ds[2] = 4
    K = _dec_eg(ds, data, Q, N, recip, CX_EG_K) + 1
    if K < 1 or K > 65536 or K > H * W:
        return -1
    v = _dec_eg(ds, data, Q, N, recip, CX_EG_S0)
    if v < 0 or v > 65535:
        return -2
    S[0] = v
    for i in range(1, K):
        g = _dec_eg(ds, data, Q, N, recip, CX_EG_GAP)
        if g < 0:
            return -2
        v = S[i - 1] + 1 + g
        if v > 65535:
            return -2
        S[i] = v
    return K


@njit(cache=True, _nrt=False)
def _decode_core(data, img, ds, S, K, rank_of, Q, N, seen, Fu, Fs, cnt, vrow,
                 ppos, pslp, cpos, cslp, recip, flags):
    """Fills img.  Returns 0 on success, negative code on invalid stream."""
    H, W = img.shape
    _init_sets(K, Fu, Fs, seen, cnt)
    lam0 = S[0]
    ppos[0] = W
    ppos[1] = W
    pm = 0
    for r in range(H):
        ref = vrow if r == 0 else img[r - 1]
        row = img[r]
        a0 = 0
        prev = -1
        j = 0
        cm = 0
        while True:
            while ppos[j] <= a0:
                j += 1
            k1 = np.int64(ref[a0])
            src = 0
            e1 = -1
            e2 = -1
            lab = -1
            if k1 != prev:
                if a0 == 0:
                    cx = 0
                elif ref[a0 - 1] != ref[a0]:
                    cx = 1
                else:
                    cx = 2
                if r == 0:
                    cx += 3
                if _dec(ds, data, Q, N, recip, CX_L1 + cx):
                    lab = k1
                    src = 1
                else:
                    e1 = k1
            if src == 0 and (flags & F_NOK2) == 0:
                p0 = ppos[j]
                if p0 < W:
                    k2 = np.int64(ref[p0])
                    if k2 != prev and k2 != e1:
                        d = p0 - a0
                        cx = 0 if d == 1 else (1 if d == 2 else 2)
                        if _dec(ds, data, Q, N, recip, CX_L2 + cx):
                            lab = k2
                            src = 2
                        else:
                            e2 = k2
            if src == 0:
                _excl(prev, rank_of, seen, Fu, Fs, K, cnt, -1)
                _excl(e1, rank_of, seen, Fu, Fs, K, cnt, -1)
                _excl(e2, rank_of, seen, Fu, Fs, K, cnt, -1)
                nu = cnt[0]
                ns = cnt[1]
                if nu > 0 and ns > 0:
                    isnew = _dec(ds, data, Q, N, recip, CX_ESCNEW)
                elif nu > 0:
                    isnew = 1
                elif ns > 0:
                    isnew = 0
                else:
                    return -3
                if isnew:
                    idx = 0
                    if nu > 1:
                        if _dec(ds, data, Q, N, recip, CX_IDX0) == 0:
                            idx = 1 + (_dec_tb(ds, data, nu - 1) if nu > 2 else 0)
                    q = _fw_select(Fu, K, idx)
                else:
                    idx = _dec_tb(ds, data, ns) if ns > 1 else 0
                    q = _fw_select(Fs, K, idx)
                _excl(e2, rank_of, seen, Fu, Fs, K, cnt, 1)
                _excl(e1, rank_of, seen, Fu, Fs, K, cnt, 1)
                _excl(prev, rank_of, seen, Fu, Fs, K, cnt, 1)
                if q < 0 or q >= K:
                    return -4
                lab = S[q]
            _mark_seen(rank_of[lab], seen, Fu, Fs, K, cnt)
            slope = UNK
            slope2 = UNK
            if src == 0:
                L = _dec_eg(ds, data, Q, N, recip, CX_EG_ESC)
                if L < 0 or L > W - a0 - 1:
                    return -5
                a1 = a0 + 1 + L
            else:
                lc = _left_class(cslp[0, cm - 1] if cm > 0 else UNK)
                lo = a0
                jj = j
                while True:
                    while ppos[jj] <= lo:
                        jj += 1
                    jb = jj
                    if jb < pm and ref[ppos[jb]] == lab:
                        jb += 1
                    b1 = ppos[jb]
                    if b1 >= W:
                        if _dec(ds, data, Q, N, recip, CX_END + (1 if lab == lam0 else 0)):
                            a1 = W
                        else:
                            L = _dec_eg(ds, data, Q, N, recip, CX_EG_NOREF)
                            if L < 0 or L > W - lo - 2:
                                return -6
                            a1 = lo + 1 + L
                        break
                    b2 = ppos[jb + 1]
                    sb, sc, pred = _slope_class(pslp[0, jb], pslp[1, jb], flags)
                    near = 1 if b2 - b1 <= 2 else 0
                    cxv = CX_MV + (sb * 2 + near) * 2 + (src - 1)
                    cxp = CX_MP + near * 2 + (src - 1)
                    if _dec(ds, data, Q, N, recip, cxv):
                        if _dec(ds, data, Q, N, recip, CX_DZ + sc * 4 + lc):
                            dp = 0
                        else:
                            neg = _dec(ds, data, Q, N, recip, CX_DS + sc * 4 + lc)
                            M = DMAX if WIN_PRED else (DMAX + pred if neg else DMAX - pred)
                            mag = 1
                            while mag < M and _dec(ds, data, Q, N, recip, CX_DM + sc * 4 + min(mag - 1, 3)):
                                mag += 1
                            dp = -mag if neg else mag
                        dl = pred + dp
                        slope = dl
                    elif (flags & F_NOPASS) == 0 and _dec(ds, data, Q, N, recip, cxp):
                        if b2 >= W:
                            return -8
                        lo = b2
                        continue
                    else:
                        pos = _dec(ds, data, Q, N, recip, CX_HS + sb)
                        mg = _dec_eg(ds, data, Q, N, recip, CX_EG_H)
                        if mg < 0 or mg > 2 * W + PMAX:
                            return -9
                        hv = mg + DMAX + 1
                        if pos == 0:
                            hv = -hv
                        dl = pred + hv if WIN_PRED else hv
                        slope = dl if H_SLOPE else UNK
                    a1 = b1 + dl
                    if a1 <= lo or a1 > W:
                        return -7
                    slope2 = pslp[0, jb]
                    break
            lv = np.uint16(lab)
            for c in range(a0, a1):
                row[c] = lv
            if a1 >= W:
                break
            cpos[cm] = a1
            cslp[0, cm] = slope
            cslp[1, cm] = slope2
            cm += 1
            prev = lab
            a0 = a1
        for t in range(cm):
            ppos[t] = cpos[t]
            pslp[0, t] = cslp[0, t]
            pslp[1, t] = cslp[1, t]
        ppos[cm] = W
        ppos[cm + 1] = W
        pm = cm
    if cnt[0] != 0:
        return -10
    return 0


@njit(cache=True)
def decode_kernel(data, img, recip, q0, n0, flags):
    """Fills img (H, W uint16).  Returns 0 on success, negative code on invalid stream."""
    H, W = img.shape
    ds = np.zeros(3, np.int64)
    Q = q0.copy()
    N = n0.copy()
    S = np.empty(65536, np.int64)
    K = _decode_header(data, ds, Q, N, recip, S, H, W)
    if K < 0:
        return K
    rank_of = np.empty(65536, np.int64)
    for i in range(K):
        rank_of[S[i]] = i
    seen = np.empty(K, np.uint8)
    Fu = np.empty(K + 1, np.int64)
    Fs = np.empty(K + 1, np.int64)
    cnt = np.zeros(2, np.int64)
    vrow = np.full(W, S[0], np.uint16)
    ppos = np.empty(W + 2, np.int64)
    pslp = np.empty((2, W + 2), np.int64)
    cpos = np.empty(W + 2, np.int64)
    cslp = np.empty((2, W + 2), np.int64)
    return _decode_core(data, img, ds, S, K, rank_of, Q, N, seen, Fu, Fs, cnt, vrow,
                        ppos, pslp, cpos, cslp, recip, flags)
