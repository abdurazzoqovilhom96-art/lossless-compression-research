import glob
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bdlc  # noqa: E402

FLAGS = [0, 1, 2, 4, 7]
MODELS = [1, 2]


def synthetic_labels(rng, h, w, n_obj, max_id=65535):
    """Random disks/rectangles with arbitrary IDs over background 0 (overlaps allowed)."""
    x = np.zeros((h, w), np.uint16)
    yy, xx = np.mgrid[:h, :w]
    ids = rng.choice(np.arange(1, max_id + 1), size=n_obj, replace=False)
    for k in ids:
        cy, cx = rng.integers(0, h), rng.integers(0, w)
        if rng.random() < 0.5:
            r = rng.integers(1, max(2, min(h, w) // 4))
            x[(yy - cy) ** 2 + (xx - cx) ** 2 <= r * r] = k
        else:
            hh, ww = rng.integers(1, max(2, h // 3)), rng.integers(1, max(2, w // 3))
            x[cy:cy + hh, cx:cx + ww] = k
    return x


class RoundTrip(unittest.TestCase):
    def check(self, x, flags=0, crc=False):
        for model in MODELS:
            b = bdlc.encode(x, crc=crc, flags=flags, model=model)
            y = bdlc.decode(b)
            self.assertEqual(y.dtype, np.uint16)
            self.assertEqual(y.shape, x.shape)
            self.assertTrue(np.array_equal(x, y))
            self.assertEqual(b, bdlc.encode(x, crc=crc, flags=flags, model=model), 'encoder not deterministic')
        return bdlc.encode(x, crc=crc, flags=flags)

    def test_random_alphabets(self):
        r = np.random.default_rng(7)
        for shape in [(1, 1), (1, 257), (257, 1), (65, 71), (256, 256)]:
            for k in [1, 2, 3, 256, 257, 65536]:
                x = r.integers(0, k, shape, dtype=np.uint16)
                for f in FLAGS:
                    self.check(x, f)

    def test_all_ids(self):
        x = np.arange(65536, dtype=np.uint16).reshape(256, 256)
        self.check(x)
        self.check(x.T.copy())
        self.check(x[::-1].copy())

    def test_edge_images(self):
        cases = [np.full((1, 1), 65535, np.uint16), np.zeros((1, 1), np.uint16),
                 np.full((37, 53), 12345, np.uint16),
                 np.tile(np.array([[0, 65535]], np.uint16), (9, 40)),        # vertical stripes
                 np.tile(np.array([[3], [9]], np.uint16), (40, 9)),          # horizontal stripes
                 (np.indices((50, 50)).sum(0) % 2).astype(np.uint16) * 7,    # checkerboard
                 np.eye(64, dtype=np.uint16) * 65535,                        # diagonal line
                 np.triu(np.ones((80, 80), np.uint16)) * 2]                 # staircase boundary
        for x in cases:
            for f in FLAGS:
                for crc in (False, True):
                    self.check(np.ascontiguousarray(x), f, crc)

    def test_synthetic_objects(self):
        r = np.random.default_rng(11)
        for t in range(60):
            h, w = int(r.integers(1, 200)), int(r.integers(1, 200))
            x = synthetic_labels(r, h, w, int(r.integers(1, 40)))
            self.check(x, FLAGS[t % len(FLAGS)])

    def test_noncontiguous_and_big_endian_input(self):
        x = synthetic_labels(np.random.default_rng(3), 120, 90, 15)
        self.assertTrue(np.array_equal(bdlc.decode(bdlc.encode(x[:, ::2])), x[:, ::2]))
        with self.assertRaises(ValueError):
            bdlc.encode(x.astype('>u2'))
        with self.assertRaises(ValueError):
            bdlc.encode(x.astype(np.int32))
        with self.assertRaises(ValueError):
            bdlc.encode(np.zeros((0, 5), np.uint16))

    def test_raw_fallback_bounds_size(self):
        x = np.random.default_rng(5).integers(0, 65536, (64, 64), dtype=np.uint16)
        b = self.check(x)
        self.assertTrue(b[1] & 0x80, 'noise should be stored raw')
        self.assertLessEqual(len(b), 2 * x.size + 8)

    def test_real_label_maps(self):
        import tifffile
        files = sorted(glob.glob(os.path.join(ROOT, '..', 'data', '*', '*', 'SEG', '*.tif')))
        if not files:
            self.skipTest('development label maps not present')
        for f in files:
            x = tifffile.imread(f)
            for fl in (0, 7):
                b = self.check(x, fl)
                self.assertFalse(b[1] & 0x80)


class Corruption(unittest.TestCase):
    def setUp(self):
        self.x = synthetic_labels(np.random.default_rng(1), 96, 120, 25)

    def test_header_errors(self):
        b = bdlc.encode(self.x)
        for bad in [b'', b[:3], b'\x00' + b[1:], b[:1] + bytes([b[1] ^ 0x08]) + b[2:], b[:2] + b'\xff\xff\xff\xff\xff\xff']:
            with self.assertRaises(ValueError):
                bdlc.decode(bad)

    def test_crc_never_returns_wrong_pixels(self):
        # A changed byte may leave the decoded image unchanged (the final coder interval
        # admits several code values); what must never happen is a *wrong* image accepted.
        b = bdlc.encode(self.x, crc=True)
        hdr = 2 + len(bdlc.api._uvarint(96)) + len(bdlc.api._uvarint(120))
        for i in range(hdr, len(b)):
            for delta in (1, 0x80):
                q = bytearray(b)
                q[i] ^= delta
                try:
                    y = bdlc.decode(bytes(q))
                except ValueError:
                    continue
                self.assertTrue(np.array_equal(y, self.x), 'wrong image accepted, byte %d' % i)

    def test_fuzz_never_crashes(self):
        r = np.random.default_rng(99)
        b = bdlc.encode(self.x)
        for t in range(3000):
            q = bytearray(b)
            kind = t % 4
            if kind == 0:
                for _ in range(int(r.integers(1, 4))):
                    q[int(r.integers(6, len(q)))] ^= 1 << int(r.integers(0, 8))
            elif kind == 1:
                q = q[:int(r.integers(6, len(q)))]
            elif kind == 2:
                q += bytes(r.integers(0, 256, int(r.integers(1, 64)), dtype=np.uint8))
            else:
                q = q[:6] + bytes(r.integers(0, 256, int(r.integers(1, 400)), dtype=np.uint8))
            try:
                y = bdlc.decode(bytes(q))
                self.assertEqual(y.shape, self.x.shape)
                self.assertEqual(y.dtype, np.uint16)
            except ValueError:
                pass


if __name__ == '__main__':
    unittest.main()
