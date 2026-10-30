"""Development: leave-one-sequence-out (LOSO) evaluation of trained initial probability tables.

Context selection depends only on the image, never on probabilities, so per-image decision counts
are computed once; for every held-out sequence the table is built from the other sequences only.
Also writes tables built from ALL development sequences with --write (for freezing).
"""
import argparse
import csv
import glob
import os
import sys
import time

import numpy as np
import tifffile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bdlc  # noqa: E402
from bdlc import core  # noqa: E402


def table(counts, strength):
    n0, n1 = counts[:, 0], counts[:, 1]
    n = n0 + n1
    p1 = (n1 + 0.5) / (n + 1.0)
    q0 = np.clip(np.rint(p1 * (1 << 24)), 1 << 8, (1 << 24) - (1 << 8)).astype(np.int64)
    q0[n == 0] = 1 << 23
    cnt = np.minimum(n, strength).astype(np.int64)
    return q0, np.minimum(cnt, core.NMAX)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--flags', type=int, default=0)
    ap.add_argument('--strengths', default='0,8,16,32,64,128')
    ap.add_argument('--write', type=int, default=0, help='strength for the all-data table to write')
    ap.add_argument('--note', default='')
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(ROOT, '..', 'data', '*', '*', 'SEG', '*.tif')))
    imgs, groups, dsets, counts = [], [], [], []
    for f in files:
        x = tifffile.imread(f)
        parts = os.path.normpath(f).split(os.sep)
        groups.append(parts[-4] + '/' + parts[-3])
        dsets.append('HeLa' if 'HeLa' in f else 'U373')
        imgs.append(x)
        counts.append(bdlc.analyze(x, flags=a.flags, counts=True)['counts'])
    counts = np.array(counts)
    gset = sorted(set(groups))
    res = {}
    for s in [int(v) for v in a.strengths.split(',')]:
        tot = {}
        for g in gset:
            train = np.array([gg != g for gg in groups])
            init = table(counts[train].sum(0), s) if s > 0 else None
            for i in np.where(~train)[0]:
                b = bdlc.encode(imgs[i], flags=a.flags, init=init)
                assert np.array_equal(bdlc.decode(b, init=init), imgs[i])
                tot[dsets[i]] = tot.get(dsets[i], 0) + len(b)
        res[s] = tot
        print('strength %4d  HeLa %6d  U373 %6d' % (s, tot['HeLa'], tot['U373']))
    log = os.path.join(ROOT, 'dev_log.csv')
    with open(log, 'a', newline='') as fh:
        w = csv.writer(fh)
        for s, tot in res.items():
            npx = {'HeLa': 18 * 512 * 512, 'U373': 34 * 520 * 696}
            w.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), 'init_loso', a.flags,
                        '%.6f' % (8 * tot['HeLa'] / npx['HeLa']), '%.6f' % (8 * tot['U373'] / npx['U373']),
                        'LOSO init strength=%d %s' % (s, a.note)])
    if a.write:
        q0, n0 = table(counts.sum(0), a.write)
        out = os.path.join(ROOT, 'bdlc', 'init_dev_all.npz')
        np.savez(out, q0=q0, n0=n0, strength=a.write)
        print('wrote', out)


if __name__ == '__main__':
    main()
