"""External command-line baselines (Q1 step 1), run as subprocesses in the Linux container.

Container stream (what the harness stores and decodes):
    uvarint H, uvarint W, [label-set block], tool stream
  * The tools' own streams already contain H and W (their decoders need no sizes), so the uvarint
    H/W prefix is only a wrapper convenience and is not counted: eta = 0 (Q1_REJA_UZ.md §1.3).
  * 'pi' configurations give the tool the order-preserving rank map pi(x) = index of x in the
    sorted label set S (8-bit, K <= 256) and store S in exactly
        sigma*(K) = ceil((17 + ceil(log2 C(2^16, K))) / 8) bytes,
    the theoretical minimum of §1.3, as an enumerative code: K-1 in 17 bits, then the combinadic
    rank sum_j C(S[j], j+1) of S among all K-subsets of {0..65535}.
  * 'direct' configurations give the tool the label values themselves (8-bit, max label <= 255);
    the tool stores them (sigma = 0).  'u16' configurations take uint16 directly (sigma = 0).
Counted size (accounted_bytes) = len(container) - len(uvarint H) - len(uvarint W)
                                = |tool stream| + sigma.
A configuration that does not apply to an image raises NotApplicable (coverage rule, §1.4).

Tools and versions: docker/README_UZ.md (image bdlc-baselines / bdlc-bench:2026-10-29).
"""
import atexit
import hashlib
import math
import os
import shutil
import subprocess
import tempfile

import numpy as np

BIN = os.environ.get('BDLC_EXTERNAL_BIN', '/opt/baselines/bin')
HM_CFG = os.path.join(BIN, 'hm_cfg', 'encoder_intra_main_scc.cfg')
L = 1 << 16


class NotApplicable(Exception):
    """This configuration does not apply to this image (coverage rule); not an error."""


# name -> (tool, input, options, description for the protocol/paper)
CONFIGS = {
    'ecc_pi':          ('ecc', 'pi', {}, 'ECC-2026 (InterDigital fe3f2f1 + docker/patches/ecc_ub_fixes.patch), '
                                         'pi(x) as 8-bit YUV 4:0:0, 1 frame; label set sigma*(K)'),
    'ecc_direct':      ('ecc', 'direct', {}, 'ECC-2026, label values <= 255 as 8-bit YUV 4:0:0 (ECC stores its palette)'),
    'hevc_scc_pi':     ('hm', 'pi', {}, 'HM-16.21+SCM-8.8, encoder_intra_main_scc.cfg, lossless (transquant bypass, '
                                        'CostMode lossless), palette on, 4:0:0 8-bit pi(x); label set sigma*(K)'),
    'hevc_scc_direct': ('hm', 'direct', {}, 'HM-16.21+SCM-8.8 as hevc_scc_pi, label values <= 255'),
    'jbig_gray_pi':    ('jbig', 'pi', {'gray': True}, 'JBIG-KIT 2.1 pbmtojbg -q (sequential), bit planes of pi(x), '
                                                      'Gray code; label set sigma*(K)'),
    'jbig_binary_pi':  ('jbig', 'pi', {'gray': False}, 'JBIG-KIT 2.1 pbmtojbg -q -b, bit planes of pi(x), binary code; '
                                                       'label set sigma*(K)'),
    'flif_u16_e60':    ('flif', 'u16', {'effort': 60}, 'FLIF 0.4, 16-bit PGM (maxval 65535), effort 60 (default)'),
    'flif_u16_e100':   ('flif', 'u16', {'effort': 100}, 'FLIF 0.4, 16-bit PGM (maxval 65535), effort 100'),
    'flif_pi_e60':     ('flif', 'pi', {'effort': 60}, 'FLIF 0.4, 8-bit PGM of pi(x), effort 60; label set sigma*(K)'),
    'flif_pi_e100':    ('flif', 'pi', {'effort': 100}, 'FLIF 0.4, 8-bit PGM of pi(x), effort 100; label set sigma*(K)'),
    'compresso':       ('cpso', 'u16', {}, 'Compresso b1f7fd6 via docker/cpso_cli.cpp: Python-package defaults '
                                           '(Fortran order, steps 4x4x1, connectivity 4, z index)'),
}
TOOL_BINARIES = {'ecc': ['ecc_encoder', 'ecc_decoder'], 'hm': ['TAppEncoder', 'TAppDecoder'],
                 'jbig': ['pbmtojbg', 'jbgtopbm'], 'flif': ['flif'], 'cpso': ['cpso_cli']}


# ------------------------------------------------------------------ helpers
def _uvarint(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_uvarint(buf, pos):
    v = 0
    for shift in range(0, 35, 7):
        if pos >= len(buf):
            raise ValueError('truncated header')
        b = buf[pos]
        pos += 1
        v |= (b & 0x7F) << shift
        if not b & 0x80:
            return v, pos
    raise ValueError('varint too long')


def _hw(b):
    h, pos = _read_uvarint(b, 0)
    w, pos = _read_uvarint(b, pos)
    if not h or not w or h * w > 1 << 28:
        raise ValueError('invalid dimensions')
    return h, w, pos


def sigma_star(k):
    """Bytes of the minimal label-set code for K labels out of 2^16 (Q1_REJA_UZ.md §1.3)."""
    return (17 + (math.comb(L, k) - 1).bit_length() + 7) // 8


def encode_labelset(s):
    """Sorted distinct labels -> exactly sigma_star(len(s)) bytes."""
    k = len(s)
    if not 1 <= k <= L:
        raise ValueError('label count')
    rank = 0
    for j, v in enumerate(s):
        rank += math.comb(int(v), j + 1)
    nbits = (math.comb(L, k) - 1).bit_length()
    total = 17 + nbits
    nbytes = (total + 7) // 8
    return ((((k - 1) << nbits) | rank) << (8 * nbytes - total)).to_bytes(nbytes, 'big')


def decode_labelset(b, pos=0):
    """Inverse of encode_labelset; returns (sorted labels as uint16, position after the block)."""
    if len(b) < pos + 3:
        raise ValueError('truncated label set')
    k = (int.from_bytes(b[pos:pos + 3], 'big') >> 7) + 1
    nbits = (math.comb(L, k) - 1).bit_length()
    total = 17 + nbits
    nbytes = (total + 7) // 8
    if len(b) < pos + nbytes:
        raise ValueError('truncated label set')
    rank = (int.from_bytes(b[pos:pos + nbytes], 'big') >> (8 * nbytes - total)) & ((1 << nbits) - 1)
    if rank >= math.comb(L, k):
        raise ValueError('label-set rank out of range')
    s = [0] * k
    hi = L - 1
    for j in range(k - 1, -1, -1):          # largest v with C(v, j+1) <= rank, v < previous label
        lo = j
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if math.comb(mid, j + 1) <= rank:
                lo = mid
            else:
                hi = mid - 1
        s[j] = lo
        rank -= math.comb(lo, j + 1)
        hi = lo - 1
    return np.array(s, np.uint16), pos + nbytes


_TMP = None


def _tmp():
    """One scratch directory per process, on tmpfs when available (Q1 §1.6)."""
    global _TMP
    if _TMP is None:
        _TMP = tempfile.mkdtemp(prefix='bdlc_ext_', dir='/dev/shm' if os.path.isdir('/dev/shm') else None)
        atexit.register(shutil.rmtree, _TMP, True)
    return _TMP


def _run(args):
    p = subprocess.run([str(a) for a in args], cwd=_tmp(), stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError('%s exit %d: %s' % (os.path.basename(str(args[0])), p.returncode,
                                                p.stderr[-400:].decode('utf-8', 'replace').strip()))


def _f(name):
    return os.path.join(_tmp(), name)


def _read(path):
    if not os.path.exists(path) or not os.path.getsize(path):
        raise RuntimeError('tool produced no output: ' + os.path.basename(path))
    with open(path, 'rb') as fh:
        return fh.read()


def _write(path, data):
    with open(path, 'wb') as fh:
        fh.write(data)


def _write_pgm(path, a, maxval):
    h, w = a.shape
    body = a.astype('>u2').tobytes() if maxval > 255 else a.astype(np.uint8).tobytes()
    _write(path, b'P5\n%d %d\n%d\n' % (w, h, maxval) + body)


def _read_pnm(path):
    """P5 (8/16-bit) or P4 (1 bit, 1 = black) -> int array (H, W)."""
    data = _read(path)
    magic = data[:2]
    if magic not in (b'P4', b'P5'):
        raise ValueError('unexpected PNM type %r' % magic)
    need = 2 if magic == b'P4' else 3          # width, height[, maxval] after the magic
    tok, pos, n = [], 2, len(data)
    while len(tok) < need:
        if pos >= n:
            raise ValueError('truncated PNM header')
        c = data[pos:pos + 1]
        if c.isspace():
            pos += 1
        elif c == b'#':
            while pos < n and data[pos:pos + 1] != b'\n':
                pos += 1
        else:
            st = pos
            while pos < n and not data[pos:pos + 1].isspace():
                pos += 1
            tok.append(data[st:pos])
    pos += 1
    w, h = int(tok[0]), int(tok[1])
    if magic == b'P4':
        rb = (w + 7) // 8
        bits = np.unpackbits(np.frombuffer(data, np.uint8, count=rb * h, offset=pos).reshape(h, rb), axis=1)
        return bits[:, :w].astype(np.int64)
    dt = '>u2' if int(tok[2]) > 255 else np.uint8
    return np.frombuffer(data, dt, count=w * h, offset=pos).reshape(h, w).astype(np.int64)


# ------------------------------------------------------------------ tools (8-bit / uint16 planes)
def _ecc_enc(x8):
    h, w = x8.shape
    _write(_f('e.yuv'), np.ascontiguousarray(x8, np.uint8).tobytes())
    if os.path.exists(_f('e.bin')):
        os.remove(_f('e.bin'))
    _run([os.path.join(BIN, 'ecc_encoder'), '-i', _f('e.yuv'), '-o', _f('e.bin'), '-r', h, '-c', w,
          '-f', 1, '-s', 0, '-t', 400])
    return _read(_f('e.bin'))


def _ecc_dec(stream, h, w):
    _write(_f('d.bin'), stream)
    if os.path.exists(_f('d.yuv')):
        os.remove(_f('d.yuv'))
    _run([os.path.join(BIN, 'ecc_decoder'), '-i', _f('d.bin'), '-o', _f('d.yuv')])
    y = np.frombuffer(_read(_f('d.yuv')), np.uint8)
    if y.size != h * w:
        raise ValueError('ECC output size %d != %d' % (y.size, h * w))
    return y.reshape(h, w)


def _hm_enc(x8):
    h, w = x8.shape
    _write(_f('e.yuv'), np.ascontiguousarray(x8, np.uint8).tobytes())
    if os.path.exists(_f('e.hevc')):
        os.remove(_f('e.hevc'))
    _run([os.path.join(BIN, 'TAppEncoder'), '-c', HM_CFG, '-i', _f('e.yuv'), '-b', _f('e.hevc'), '-o', '/dev/null',
          '-wdt', w, '-hgt', h, '-fr', 1, '-f', 1, '--InputBitDepth=8', '--InternalBitDepth=8',
          '--InputChromaFormat=400', '--ChromaFormatIDC=400', '--ConformanceWindowMode=1',
          '--TransquantBypassEnable=1', '--CUTransquantBypassFlagForce=1', '--CostMode=lossless'])
    return _read(_f('e.hevc'))


def _hm_dec(stream, h, w):
    _write(_f('d.hevc'), stream)
    if os.path.exists(_f('d.yuv')):
        os.remove(_f('d.yuv'))
    _run([os.path.join(BIN, 'TAppDecoder'), '-b', _f('d.hevc'), '-o', _f('d.yuv'), '-d', 8])
    y = np.frombuffer(_read(_f('d.yuv')), np.uint8)
    if y.size != h * w:
        raise ValueError('HM output size %d != %d' % (y.size, h * w))
    return y.reshape(h, w)


def _jbig_enc(x8, k, gray):
    _write_pgm(_f('e.pgm'), x8, max(k - 1, 1))
    _run([os.path.join(BIN, 'pbmtojbg'), '-q'] + ([] if gray else ['-b']) + [_f('e.pgm'), _f('e.jbg')])
    return _read(_f('e.jbg'))


def _jbig_dec(stream, gray):
    _write(_f('d.jbg'), stream)
    _run([os.path.join(BIN, 'jbgtopbm')] + ([] if gray else ['-b']) + [_f('d.jbg'), _f('d.pnm')])
    return _read_pnm(_f('d.pnm'))


def _flif_enc(a, maxval, effort):
    _write_pgm(_f('e.pgm'), a, maxval)
    if os.path.exists(_f('e.flif')):
        os.remove(_f('e.flif'))
    _run([os.path.join(BIN, 'flif'), '-e', '-E%d' % effort, _f('e.pgm'), _f('e.flif')])
    return _read(_f('e.flif'))


def _flif_dec(stream):
    _write(_f('d.flif'), stream)
    if os.path.exists(_f('d.pgm')):
        os.remove(_f('d.pgm'))
    _run([os.path.join(BIN, 'flif'), '-d', _f('d.flif'), _f('d.pgm')])
    return _read_pnm(_f('d.pgm'))


def _cpso_enc(a):
    h, w = a.shape
    _write(_f('e.u16'), np.ascontiguousarray(a, '<u2').tobytes())
    _run([os.path.join(BIN, 'cpso_cli'), 'c', _f('e.u16'), h, w, _f('e.cpso')])
    return _read(_f('e.cpso'))


def _cpso_dec(stream, h, w):
    _write(_f('d.cpso'), stream)
    _run([os.path.join(BIN, 'cpso_cli'), 'd', _f('d.cpso'), _f('d.u16')])
    y = np.frombuffer(_read(_f('d.u16')), '<u2')
    if y.size != h * w:
        raise ValueError('Compresso output size %d != %d' % (y.size, h * w))
    return y.reshape(h, w)


# ------------------------------------------------------------------ public
def available(name):
    """Raise RuntimeError if the binaries of this configuration are missing (e.g. on Windows)."""
    tool = CONFIGS[name][0]
    for b in TOOL_BINARIES[tool] + (['hm_cfg/encoder_intra_main_scc.cfg'] if tool == 'hm' else []):
        p = os.path.join(BIN, b)
        if not os.path.isfile(p) or (not b.endswith('.cfg') and not os.access(p, os.X_OK)):
            raise RuntimeError('external tool not found: %s (runs in the bdlc-bench container)' % p)


def get(name):
    """(encode(a uint16 HxW) -> container bytes, decode(bytes) -> uint16 HxW) for one configuration."""
    available(name)
    tool, mode, opt, _ = CONFIGS[name]

    def enc(a):
        a = np.ascontiguousarray(a)
        if a.ndim != 2 or a.dtype != np.uint16 or not a.size:
            raise ValueError('nonempty 2D uint16 array required')
        h, w = a.shape
        head = _uvarint(h) + _uvarint(w)
        if mode == 'u16':
            if tool == 'flif':
                return head + _flif_enc(a, 65535, opt['effort'])
            return head + _cpso_enc(a)
        present = np.zeros(L, np.bool_)
        present[a.ravel()] = True
        s = np.flatnonzero(present)
        k = int(s.size)
        if mode == 'direct':
            if s[-1] > 255:
                raise NotApplicable('direct 8-bit input needs labels <= 255 (max %d)' % s[-1])
            x8, block = a.astype(np.uint8), b''
        else:
            if k > 256:
                raise NotApplicable('pi(x) as 8-bit needs K <= 256 (K = %d)' % k)
            lut = np.zeros(L, np.uint8)
            lut[s] = np.arange(k, dtype=np.uint8)
            x8, block = lut[a], encode_labelset(s)
        if tool == 'ecc':
            t = _ecc_enc(x8)
        elif tool == 'hm':
            t = _hm_enc(x8)
        elif tool == 'jbig':
            t = _jbig_enc(x8, k if mode == 'pi' else 256, opt['gray'])
        else:
            t = _flif_enc(x8, 255, opt['effort'])
        return head + block + t

    def dec(b):
        h, w, pos = _hw(b)
        if mode == 'u16':
            y = _flif_dec(b[pos:]) if tool == 'flif' else _cpso_dec(b[pos:], h, w)
            y = np.asarray(y)
            if y.shape != (h, w):
                raise ValueError('decoded shape %s != %s' % (y.shape, (h, w)))
            return y.astype(np.uint16)
        s = None
        if mode == 'pi':
            s, pos = decode_labelset(b, pos)
        t = b[pos:]
        if tool == 'ecc':
            x = _ecc_dec(t, h, w)
        elif tool == 'hm':
            x = _hm_dec(t, h, w)
        elif tool == 'jbig':
            x = _jbig_dec(t, opt['gray'])
        else:
            x = _flif_dec(t)
        x = np.asarray(x)
        if x.shape != (h, w):
            raise ValueError('decoded shape %s != %s' % (x.shape, (h, w)))
        if s is None:
            return x.astype(np.uint16)
        if x.max() >= len(s):
            raise ValueError('rank out of range')
        return s[x]
    return enc, dec


def accounted_bytes(name, b):
    """Counted size of a container stream: everything except the uvarint H/W prefix (eta = 0)."""
    _, _, pos = _hw(b)
    return len(b) - pos


def tool_info(names):
    """SHA-256 of the binaries/config used by these configurations (recorded in the protocol)."""
    out = {}
    for n in names:
        tool = CONFIGS[n][0]
        for b in TOOL_BINARIES[tool] + (['hm_cfg/encoder_intra_main_scc.cfg'] if tool == 'hm' else []):
            p = os.path.join(BIN, b)
            if os.path.isfile(p) and b not in out:
                h = hashlib.sha256()
                with open(p, 'rb') as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b''):
                        h.update(chunk)
                out[b] = h.hexdigest()
    return out
