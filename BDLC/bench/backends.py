"""Benchmark backends.  get(name) -> (encode(a) -> bytes, decode(b) -> uint16 array (H, W)).

Stream conventions (every stream is self-contained; its full length is what is counted):
  * BDLC, legacy RVC, image codecs and Crackle: native bitstream, no wrapper.
  * Generic byte compressors and compressed_segmentation: uvarint H, uvarint W, then the payload
    (row-major little-endian uint16 pixels for the generic compressors).
  * Palette variants: uvarint H, uvarint W, uvarint K, the K sorted labels as uint16 LE, then the
    compressed index plane (uint8 when K <= 256, else uint16 LE).
Codec-specific imports happen inside get(), so a fresh process can time its own import cost.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.dirname(os.path.abspath(__file__))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# name -> (family, wrapper, parameters as documented in the paper)
SPEC = {
    'bdlc':                   ('BDLC', 'native', 'model 1 (frozen table T1), no CRC'),
    'bdlc_crc':               ('BDLC', 'native', 'model 1, CRC32 of pixels in header'),
    'bdlc_uniform':           ('BDLC', 'native', 'model 2 (uniform initial probabilities)'),
    'bdlc_noslope':           ('BDLC', 'native', 'model 1, flag F_NOSLOPE (ablation)'),
    'bdlc_nok2':              ('BDLC', 'native', 'model 1, flag F_NOK2 (ablation)'),
    'bdlc_nopass':            ('BDLC', 'native', 'model 1, flag F_NOPASS (ablation)'),
    'rvc':                    ('legacy', 'native', 'legacy RVC codec.py, tile 64, spatial mode on'),
    'zlib9':                  ('generic', 'varint_hw', 'zlib level 9'),
    'lzma9e':                 ('generic', 'varint_hw', 'xz, preset 9 | PRESET_EXTREME'),
    'zstd3':                  ('generic', 'varint_hw', 'zstd level 3, single thread'),
    'zstd19':                 ('generic', 'varint_hw', 'zstd level 19, single thread'),
    'brotli11':               ('generic', 'varint_hw', 'brotli quality 11 (imagecodecs)'),
    'bz2_9':                  ('generic', 'varint_hw', 'bzip2 level 9'),
    'blosc2_zstd_bitshuffle': ('generic', 'varint_hw', 'blosc2 zstd level 9, bitshuffle, typesize 2, 1 thread'),
    'png16':                  ('image', 'native', 'PNG 16-bit gray, zlib level 9'),
    'jpegls':                 ('image', 'native', 'JPEG-LS (CharLS) near=0'),
    'jpegxl7':                ('image', 'native', 'JPEG XL lossless effort 7, 1 thread, bare codestream'),
    'jpegxl9':                ('image', 'native', 'JPEG XL lossless effort 9, 1 thread, bare codestream'),
    'jpegxl10':               ('image', 'native', 'JPEG XL lossless effort 10, 1 thread, bare codestream'),
    'jpeg2k':                 ('image', 'native', 'JPEG 2000 reversible 5/3 (OpenJPEG), J2K codestream, 1 thread'),
    'htj2k':                  ('image', 'native', 'HTJ2K reversible (OpenJPH), codestream'),
    'lerc':                   ('image', 'native', 'LERC maxZError 0'),
    'lerc_zstd':              ('image', 'native', 'LERC maxZError 0 + zstd level 19'),
    'palette_zstd19':         ('palette', 'varint_hw_palette', 'palette indices + zstd level 19'),
    'palette_lzma9e':         ('palette', 'varint_hw_palette', 'palette indices + xz preset 9 | EXTREME'),
    'crackle_mo0':            ('crackle', 'native', 'Crackle markov_model_order=0, parallel=1'),
    'crackle_mo3':            ('crackle', 'native', 'Crackle markov_model_order=3, parallel=1'),
    'crackle_mo0_zstd19':     ('crackle', 'native', 'Crackle mo0 stream + zstd level 19'),
    'crackle_mo3_zstd19':     ('crackle', 'native', 'Crackle mo3 stream + zstd level 19'),
    'cseg_gzip9':             ('neuroglancer', 'varint_hw', 'compressed_segmentation uint32 (H,W,1), block (8,8,1), gzip level 9'),
}
DEFAULT = list(SPEC)   # the 30 configurations of test A; jpegxl10 included (~0.7 s per 0.3 MPix image)

# Q1 step 1: command-line baselines built in the bdlc-bench container (bench/external.py). They are
# not in DEFAULT; on a machine without the binaries get() raises and the preflight marks them
# unavailable. Wrapper 'cli': counted bytes = |tool stream| + sigma (label set), eta = 0.
from external import CONFIGS as _EXT, NotApplicable  # noqa: E402  (pure Python, no tool is started)
for _n, (_tool, _mode, _opt, _desc) in _EXT.items():
    SPEC[_n] = ('external', 'cli', _desc)
EXTERNAL = list(_EXT)
UNAVAILABLE = {}


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


def _pixels(a):
    a = np.ascontiguousarray(a)
    if a.ndim != 2 or a.dtype != np.uint16 or not a.size:
        raise ValueError('nonempty 2D uint16 array required')
    return a


def _image(y, shape=None):
    y = np.asarray(y)
    if y.ndim == 3 and y.shape[2] == 1:
        y = y[:, :, 0]
    if y.ndim != 2 or y.dtype != np.uint16 or (shape is not None and y.shape != shape):
        raise ValueError('decoded image has wrong shape/dtype: %s %s' % (y.shape, y.dtype))
    return y


def _le_bytes(a):
    """Zero-copy byte view of a C-contiguous array (little-endian host); compressors take buffers."""
    if sys.byteorder != 'little' and a.dtype.itemsize > 1:
        a = a.astype(a.dtype.newbyteorder('<'))
    return memoryview(a).cast('B')


def _bytecodec(comp, decomp):
    """Generic byte compressor on raw little-endian uint16 pixels, H/W in a varint header."""
    def enc(a):
        a = _pixels(a)
        return _uvarint(a.shape[0]) + _uvarint(a.shape[1]) + comp(_le_bytes(a))

    def dec(b):
        h, w, pos = _hw(b)
        r = decomp(memoryview(b)[pos:], 2 * h * w)
        if len(r) != 2 * h * w:
            raise ValueError('payload length')
        return np.frombuffer(r, '<u2').reshape(h, w)
    return enc, dec


def _palette(comp, decomp):
    def enc(a):
        a = _pixels(a)
        present = np.zeros(65536, np.bool_)
        present[a.ravel()] = True
        s = np.flatnonzero(present).astype('<u2')
        k = len(s)
        lut = np.zeros(65536, np.uint8 if k <= 256 else '<u2')
        lut[s] = np.arange(k)
        idx = lut[a]
        return (_uvarint(a.shape[0]) + _uvarint(a.shape[1]) + _uvarint(k) + s.tobytes()
                + comp(_le_bytes(idx)))

    def dec(b):
        h, w, pos = _hw(b)
        k, pos = _read_uvarint(b, pos)
        if not 1 <= k <= min(65536, h * w):
            raise ValueError('palette size')
        s = np.frombuffer(b, '<u2', count=k, offset=pos)
        if k > 1 and np.any(s[1:] <= s[:-1]):
            raise ValueError('palette order')
        dt = np.uint8 if k <= 256 else '<u2'
        isz = 1 if k <= 256 else 2
        r = decomp(memoryview(b)[pos + 2 * k:], isz * h * w)
        if len(r) != isz * h * w:
            raise ValueError('index length')
        idx = np.frombuffer(r, dt)
        if idx.max() >= k:
            raise ValueError('index range')
        return s[idx].reshape(h, w)
    return enc, dec


# ------------------------------------------------------------------ factories
def get(name):
    if name in UNAVAILABLE:
        raise RuntimeError(UNAVAILABLE[name])
    if name not in SPEC:
        raise KeyError(name)

    if name in _EXT:
        import external
        return external.get(name)

    if name.startswith('bdlc'):
        import bdlc
        kw = {'bdlc': {}, 'bdlc_crc': {'crc': True}, 'bdlc_uniform': {'model': 2},
              'bdlc_noslope': {'flags': 1}, 'bdlc_nok2': {'flags': 2}, 'bdlc_nopass': {'flags': 4}}[name]
        return (lambda a: bdlc.encode(a, **kw)), bdlc.decode

    if name == 'rvc':
        import legacy_rvc
        return (lambda a: legacy_rvc.encode(a, 64, spatial=True)), legacy_rvc.decode

    if name == 'zlib9':
        import zlib
        return _bytecodec(lambda r: zlib.compress(r, 9), lambda p, n: zlib.decompress(p, bufsize=n))
    if name == 'lzma9e':
        import lzma
        pr = 9 | lzma.PRESET_EXTREME
        return _bytecodec(lambda r: lzma.compress(r, preset=pr), lambda p, n: lzma.decompress(p))
    if name in ('zstd3', 'zstd19'):
        import zstandard as zs
        c = zs.ZstdCompressor(level=int(name[4:]))
        d = zs.ZstdDecompressor()
        return _bytecodec(c.compress, lambda p, n: d.decompress(p, max_output_size=n))
    if name == 'brotli11':
        import imagecodecs as ic
        return _bytecodec(lambda r: ic.brotli_encode(r, level=11), lambda p, n: ic.brotli_decode(bytes(p)))
    if name == 'bz2_9':
        import bz2
        return _bytecodec(lambda r: bz2.compress(r, 9), lambda p, n: bz2.decompress(p))
    if name == 'blosc2_zstd_bitshuffle':
        import imagecodecs as ic
        return _bytecodec(lambda r: ic.blosc2_encode(r, level=9, compressor='zstd', shuffle='bitshuffle',
                                                     typesize=2, numthreads=1),
                          lambda p, n: ic.blosc2_decode(bytes(p), numthreads=1))

    if name == 'palette_zstd19':
        import zstandard as zs
        c = zs.ZstdCompressor(level=19)
        d = zs.ZstdDecompressor()
        return _palette(c.compress, lambda p, n: d.decompress(p, max_output_size=n))
    if name == 'palette_lzma9e':
        import lzma
        pr = 9 | lzma.PRESET_EXTREME
        return _palette(lambda r: lzma.compress(r, preset=pr), lambda p, n: lzma.decompress(p))

    if name in ('png16', 'jpegls', 'jpegxl7', 'jpegxl9', 'jpegxl10', 'jpeg2k', 'htj2k', 'lerc', 'lerc_zstd'):
        import imagecodecs as ic
        if name == 'png16':
            e, d = (lambda a: ic.png_encode(_pixels(a), level=9)), ic.png_decode
        elif name == 'jpegls':
            e, d = (lambda a: ic.jpegls_encode(_pixels(a), level=0)), ic.jpegls_decode
        elif name.startswith('jpegxl'):
            eff = int(name[6:])
            e = lambda a: ic.jpegxl_encode(_pixels(a), lossless=True, effort=eff, numthreads=1)
            d = lambda b: ic.jpegxl_decode(b, numthreads=1)
        elif name == 'jpeg2k':
            e = lambda a: ic.jpeg2k_encode(_pixels(a), codecformat='j2k', reversible=True, numthreads=1)
            d = lambda b: ic.jpeg2k_decode(b, numthreads=1)
        elif name == 'htj2k':
            e, d = (lambda a: ic.htj2k_encode(_pixels(a), reversible=True)), ic.htj2k_decode
        elif name == 'lerc':
            e, d = (lambda a: ic.lerc_encode(_pixels(a), level=0)), ic.lerc_decode
        else:
            e = lambda a: ic.lerc_encode(_pixels(a), level=0, compression='zstd', compressionargs={'level': 19})
            d = ic.lerc_decode
        return (lambda a: bytes(e(a))), (lambda b: _image(d(b)))

    if name.startswith('crackle'):
        import crackle
        mo = int(name[len('crackle_mo')])
        if name.endswith('zstd19'):
            import zstandard as zs
            c = zs.ZstdCompressor(level=19)
            dz = zs.ZstdDecompressor()
            return ((lambda a: c.compress(crackle.compress(_pixels(a), markov_model_order=mo, parallel=1))),
                    (lambda b: _image(crackle.decompress(dz.decompress(b), parallel=1))))
        return ((lambda a: crackle.compress(_pixels(a), markov_model_order=mo, parallel=1)),
                (lambda b: _image(crackle.decompress(b, parallel=1))))

    if name == 'cseg_gzip9':
        import gzip
        import compressed_segmentation as cs

        def enc(a):
            a = _pixels(a)
            h, w = a.shape
            v = a.astype(np.uint32)[:, :, None]
            return _uvarint(h) + _uvarint(w) + gzip.compress(bytes(cs.compress(v, block_size=(8, 8, 1))),
                                                             compresslevel=9, mtime=0)

        def dec(b):
            h, w, pos = _hw(b)
            v = cs.decompress(gzip.decompress(memoryview(b)[pos:]), (h, w, 1), np.uint32, block_size=(8, 8, 1))
            v = np.asarray(v).reshape(h, w)
            if v.max() > 65535:
                raise ValueError('label out of uint16 range')
            return v.astype(np.uint16)
        return enc, dec

    raise KeyError(name)


def accounted_bytes(name, b):
    """Counted size of a stream: its full length, except the command-line baselines (external.py)."""
    if name in _EXT:
        import external
        return external.accounted_bytes(name, b)
    return len(b)


def probes():
    """Small fixed arrays for the preflight roundtrip (edge cases every codec must survive).

    A configuration may declare a probe not applicable (NotApplicable); it must pass all others."""
    r = np.random.default_rng(20261028)
    return {
        'one_pixel_max': np.full((1, 1), 65535, np.uint16),
        'tiny_mixed': np.array([[0, 1, 65535], [257, 257, 0]], np.uint16),
        'odd_k300': r.integers(0, 300, (37, 53)).astype(np.uint16) * 211,
        'blocks': np.kron(r.integers(0, 40, (9, 11)), np.ones((13, 7), np.int64)).astype(np.uint16) * 1601,
        'small_labels': np.kron(r.integers(0, 12, (6, 5)), np.ones((9, 10), np.int64)).astype(np.uint16),
    }
