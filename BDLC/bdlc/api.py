"""BDLC v1 container: header, optional CRC32, raw fallback, validation.

Stream layout
  byte 0      0xBD (magic)
  byte 1      bit7 raw | bit6 crc | bits5..3 model id | bits2..0 ablation flags
                model id 1 = BDLC v1 with frozen initial table T1 (default)
                model id 2 = BDLC v1 with uniform initial probabilities (ablation)
                model id 3 = caller-supplied initial table (research only; decoder needs it)
  varint H, varint W            (unsigned LEB128)
  [4 bytes CRC32 of little-endian uint16 pixels]   if crc
  payload: range-coded stream (trailing zero bytes omitted) or 2*H*W raw bytes
"""
import hashlib
import os
import struct
import zlib

import numpy as np

from . import core

MAGIC = 0xBD
VERSION = 1
MAX_PIXELS = 1 << 28
_NOCOST = np.zeros(0, np.float64)
# SHA-256 of the frozen table T1 (q0 then n0, little-endian int64), built from the 52 development maps
T1_SHA256 = '8295261d117d3941b1d63107a023f60e889f3b9b9fafaf88e9a84deaf27ea559'


def _load_t1():
    z = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'init_v1.npz'))
    q0 = np.ascontiguousarray(z['q0'], np.int64)
    n0 = np.ascontiguousarray(z['n0'], np.int64)
    digest = hashlib.sha256(q0.astype('<i8').tobytes() + n0.astype('<i8').tobytes()).hexdigest()
    if digest != T1_SHA256 or q0.shape != (core.NCTX,) or n0.shape != (core.NCTX,):
        raise RuntimeError('initial table T1 does not match the frozen specification')
    return q0, n0


TABLES = {1: _load_t1(), 2: (core.UNIFORM_Q0, core.UNIFORM_N0)}


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


def _check(img):
    a = np.asarray(img)
    if a.ndim != 2 or a.dtype != np.uint16 or a.size == 0:
        raise ValueError('nonempty 2D uint16 array required')
    if a.size > MAX_PIXELS:
        raise ValueError('image too large')
    return np.ascontiguousarray(a)


def _model(model, init):
    if init is not None:
        return 3, init
    if model not in TABLES:
        raise ValueError('model id')
    return model, TABLES[model]


def encode(img, crc=False, flags=0, model=1, init=None):
    """Lossless BDLC encoding of a 2D uint16 label map; returns bytes."""
    a = _check(img)
    h, w = a.shape
    if not 0 <= flags <= 7:
        raise ValueError('flags')
    mid, (q0, n0) = _model(model, init)
    body, k = core.encode_kernel(a, core.RECIP, q0, n0, _NOCOST, flags)
    if k == -1:
        raise RuntimeError('range coder invariant violated')
    raw = k == -2 or len(body) >= 2 * a.size
    hdr = bytearray([MAGIC, (0x80 if raw else 0) | (0x40 if crc else 0) | (mid << 3) | flags])
    hdr += _uvarint(h) + _uvarint(w)
    if crc:
        hdr += struct.pack('<I', zlib.crc32(a.astype('<u2', copy=False)))
    return bytes(hdr) + (a.astype('<u2', copy=False).tobytes() if raw else body.tobytes())


def decode(buf, init=None):
    """Inverse of encode; raises ValueError on any invalid stream."""
    buf = memoryview(buf).cast('B') if not isinstance(buf, (bytes, bytearray)) else buf
    if len(buf) < 4 or buf[0] != MAGIC:
        raise ValueError('not a BDLC stream')
    mode = buf[1]
    mid = (mode >> 3) & 7
    if mid == 3:
        if init is None:
            raise ValueError('stream needs the caller-supplied initial table')
        q0, n0 = init
    elif mid in TABLES:
        q0, n0 = TABLES[mid]
    else:
        raise ValueError('unsupported model id')
    raw, crc, flags = mode & 0x80, mode & 0x40, mode & 7
    h, pos = _read_uvarint(buf, 2)
    w, pos = _read_uvarint(buf, pos)
    if not h or not w or h * w > MAX_PIXELS:
        raise ValueError('invalid dimensions')
    want = None
    if crc:
        if pos + 4 > len(buf):
            raise ValueError('truncated CRC')
        want = struct.unpack_from('<I', buf, pos)[0]
        pos += 4
    if raw:
        if len(buf) - pos != 2 * h * w:
            raise ValueError('raw length')
        out = np.frombuffer(buf, '<u2', count=h * w, offset=pos).reshape(h, w).astype(np.uint16)
    else:
        data = np.frombuffer(buf, np.uint8, offset=pos)
        out = np.empty((h, w), np.uint16)
        st = core.decode_kernel(data, out, core.RECIP, q0, n0, flags)
        if st:
            raise ValueError('corrupt BDLC stream (code %d)' % st)
    if crc and zlib.crc32(out.astype('<u2', copy=False)) != want:
        raise ValueError('CRC mismatch')
    return out


# cost categories: (name, context ranges [lo, hi), bypass slots)
CATEGORIES = [
    ('label_set', [(core.CX_EG_K, core.CX_EG_GAP + core.EG_W)], [core.NCTX + 0, core.NCTX + 1, core.NCTX + 2]),
    ('label_above_k1', [(core.CX_L1, core.CX_L1 + 6)], []),
    ('label_nextrun_k2', [(core.CX_L2, core.CX_L2 + 3)], []),
    ('label_escape', [(core.CX_ESCNEW, core.CX_IDX0 + 1)], [core.NCTX + 6]),
    ('newobject_length', [(core.CX_EG_ESC, core.CX_EG_ESC + core.EG_W)], [core.NCTX + 3]),
    ('noref_end_length', [(core.CX_END, core.CX_END + 2), (core.CX_EG_NOREF, core.CX_EG_NOREF + core.EG_W)], [core.NCTX + 4]),
    ('mode_vertical_pass', [(core.CX_MV, core.CX_MP + 4)], []),
    ('displacement', [(core.CX_DZ, core.CX_HS)], []),
    ('horizontal_jump', [(core.CX_HS, core.NCTX), (core.CX_EG_H, core.CX_EG_H + core.EG_W)], [core.NCTX + 5]),
]


def analyze(img, flags=0, model=1, init=None, counts=False):
    """Ideal model information content (bits) per decision category, plus exact sizes.

    Arithmetic coding admits no exact per-category byte attribution; the category values are
    sums of -log2(p) over the decisions of that category, and their total differs from the
    payload length only by the coder's termination/rounding overhead."""
    a = _check(img)
    mid, (q0, n0) = _model(model, init)
    cost = np.zeros(core.NCOST + (2 * core.NCTX if counts else 0), np.float64)
    body, k = core.encode_kernel(a, core.RECIP, q0, n0, cost, flags)
    stream = encode(a, flags=flags, model=model, init=init)
    res = {'K': int(k), 'stream_bytes': len(stream), 'payload_bytes': len(body),
           'header_bytes': len(stream) - len(body)}
    total = 0.0
    for name, ranges, slots in CATEGORIES:
        bits = sum(cost[lo:hi].sum() for lo, hi in ranges) + sum(cost[s] for s in slots)
        res[name + '_bits'] = float(bits)
        total += bits
    res['model_bits_total'] = float(total)
    res['unattributed_bits'] = float(cost[:core.NCOST].sum() - total)
    if counts:
        res['counts'] = cost[core.NCOST:].reshape(core.NCTX, 2).copy()
    return res
