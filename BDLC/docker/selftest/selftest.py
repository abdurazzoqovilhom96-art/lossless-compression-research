"""Lossless round-trip self-test of the external baselines on synthetic maps.

  python selftest.py make  WORK   writes synthetic inputs in every format
  python selftest.py check WORK   compares decoded outputs with the originals

Between the two steps, roundtrip.sh runs inside bdlc-baselines:2026-10-29 with
WORK mounted at /work.  No real data is used.
"""
import csv
import json
import os
import sys

import numpy as np


def maps():
    rng = np.random.default_rng(20261029)
    out = {}

    def blobs(h, w, k, n, big=False):
        a = np.zeros((h, w), np.uint16)
        yy, xx = np.mgrid[0:h, 0:w]
        labels = rng.choice(np.arange(1, 65536 if big else 4096), size=k - 1, replace=False).astype(np.uint16)
        for i in range(n):
            cy, cx = rng.integers(0, h), rng.integers(0, w)
            ry, rx = rng.integers(2, max(3, h // 4)), rng.integers(2, max(3, w // 4))
            a[((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1] = labels[i % (k - 1)]
        return a

    out['const_0_64x48'] = np.zeros((48, 64), np.uint16)
    out['const_7_40x24'] = np.full((24, 40), 7, np.uint16)
    out['k2_256x256'] = blobs(256, 256, 2, 12)
    out['k10_100x75'] = blobs(75, 100, 10, 30)          # not a multiple of 8
    out['k30_512x384'] = blobs(384, 512, 30, 80)
    out['k120_256x256'] = blobs(256, 256, 120, 200)      # more than HM palette size 63
    out['k256_320x240'] = blobs(240, 320, 256, 600)      # largest rank map that fits uint8
    out['k12_big_200x136'] = blobs(136, 200, 12, 40, big=True)   # labels up to 65535
    out['noise_k5_64x64'] = rng.integers(0, 5, (64, 64)).astype(np.uint16)
    for name, a in out.items():
        assert a.dtype == np.uint16
    return out


def rank_map(a):
    s = np.unique(a)
    return np.searchsorted(s, a).astype(np.uint8 if s.size <= 256 else np.uint16), s


def write_pgm(path, a, maxval):
    h, w = a.shape
    with open(path, 'wb') as f:
        f.write(b'P5\n%d %d\n%d\n' % (w, h, maxval))
        f.write((a.astype('>u2') if maxval > 255 else a.astype(np.uint8)).tobytes())


def read_pnm(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic = data[:2]
    if magic not in (b'P4', b'P5'):
        raise ValueError('unsupported PNM type %r' % magic)
    need = 3 if magic == b'P4' else 4          # PBM has no maxval
    tokens, pos, n = [], 0, len(data)
    while len(tokens) < need:
        if pos >= n:
            raise ValueError('truncated PNM header')
        if data[pos:pos + 1].isspace():
            pos += 1
            continue
        if data[pos:pos + 1] == b'#':
            while pos < n and data[pos:pos + 1] != b'\n':
                pos += 1
            continue
        start = pos
        while pos < n and not data[pos:pos + 1].isspace():
            pos += 1
        tokens.append(data[start:pos])
    pos += 1
    w, h = int(tokens[1]), int(tokens[2])
    if magic == b'P4':                         # 1 bit per pixel, rows padded to bytes, 1 = black
        rowbytes = (w + 7) // 8
        bits = np.unpackbits(np.frombuffer(data[pos:], np.uint8, count=rowbytes * h).reshape(h, rowbytes), axis=1)
        return bits[:, :w].astype(np.int64), 1
    maxval = int(tokens[3])
    dt = '>u2' if maxval > 255 else np.uint8
    return np.frombuffer(data[pos:], dtype=dt, count=w * h).reshape(h, w).astype(np.int64), maxval


def make(work):
    os.makedirs(os.path.join(work, 'in'), exist_ok=True)
    index = []
    for name, a in maps().items():
        h, w = a.shape
        r, s = rank_map(a)
        k = int(s.size)
        base = os.path.join(work, 'in', name)
        np.save(base + '.npy', a)
        a.astype('<u2').tofile(base + '.u16')
        write_pgm(base + '.u16.pgm', a, 65535)
        if k <= 256:
            r.tofile(base + '.r8.yuv')
            write_pgm(base + '.r8.pgm', r, 255)
            write_pgm(base + '.jbig.pgm', r, max(k - 1, 1))
        index.append(dict(name=name, H=h, W=w, K=k, rank8=int(k <= 256)))
    with open(os.path.join(work, 'index.csv'), 'w', newline='') as f:  # LF: read by bash
        wr = csv.DictWriter(f, fieldnames=list(index[0]), lineterminator='\n')
        wr.writeheader()
        wr.writerows(index)
    print('wrote', len(index), 'maps to', work)


def check(work):
    idx = list(csv.DictReader(open(os.path.join(work, 'index.csv'))))
    res = list(csv.DictReader(open(os.path.join(work, 'roundtrip.csv'))))
    ok_all = True
    rows = []
    for r in res:
        m = next(i for i in idx if i['name'] == r['name'])
        a = np.load(os.path.join(work, 'in', m['name'] + '.npy')).astype(np.int64)
        rank, s = rank_map(a.astype(np.uint16))
        rank = rank.astype(np.int64)
        H, W = int(m['H']), int(m['W'])
        out = os.path.join(work, r['decoded']) if r['decoded'] else ''
        verdict = 'ENC/DEC FAILED (exit %s)' % r['exit'] if r['exit'] != '0' else ''
        if not verdict:
            try:
                kind = r['kind']
                if kind == 'u16raw':
                    d = np.fromfile(out, '<u2').astype(np.int64)
                    good = d.size == H * W and np.array_equal(d.reshape(H, W), a)
                elif kind == 'r8yuv':
                    d = np.fromfile(out, np.uint8).astype(np.int64)
                    good = d.size == H * W and np.array_equal(d.reshape(H, W), rank)
                elif kind in ('u16pnm', 'r8pnm', 'jbigpnm'):
                    d, maxval = read_pnm(out)
                    ref = a if kind == 'u16pnm' else rank
                    good = d.shape == (H, W) and np.array_equal(d, ref)
                else:
                    raise ValueError(kind)
                verdict = 'LOSSLESS' if good else 'MISMATCH'
            except Exception as e:  # noqa: BLE001 - report any read problem
                verdict = 'READ ERROR: %s' % e
        ok_all &= verdict == 'LOSSLESS'
        rows.append(dict(r, verdict=verdict))
    with open(os.path.join(work, 'selftest_result.csv'), 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    for r in rows:
        print('%-10s %-18s %8s B  %s' % (r['tool'], r['name'], r['bytes'], r['verdict']))
    print('ALL LOSSLESS' if ok_all else 'SOME FAILED')
    return 0 if ok_all else 1


if __name__ == '__main__':
    cmd, work = sys.argv[1], sys.argv[2]
    sys.exit(make(work) or 0 if cmd == 'make' else check(work))
