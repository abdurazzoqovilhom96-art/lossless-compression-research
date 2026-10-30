"""Development-only size evaluation of BDLC variants against the strongest specialist (Crackle).

Usage: python tools/dev_eval.py [--flags N] [--crackle]
Prints micro bpp per dataset and per-image wins.  Appends one line to dev_log.csv so every
tried variant stays on record (development tuning must be disclosed).
"""
import argparse
import csv
import glob
import hashlib
import lzma
import os
import sys
import time

import numpy as np
import tifffile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bdlc  # noqa: E402
from bdlc import core  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--flags', type=int, default=0)
    p.add_argument('--crackle', action='store_true')
    p.add_argument('--note', default='')
    a = p.parse_args()
    files = sorted(glob.glob(os.path.join(ROOT, '..', 'data', '*', '*', 'SEG', '*.tif')))
    agg = {}
    for f in files:
        x = tifffile.imread(f)
        ds = 'HeLa' if 'HeLa' in f else 'U373'
        b = bdlc.encode(x, flags=a.flags)
        assert np.array_equal(bdlc.decode(b), x)
        t = agg.setdefault(ds, dict(B=0, N=0, C=0, wins=0, n=0))
        t['B'] += len(b)
        t['N'] += x.size
        t['n'] += 1
        if a.crackle:
            import crackle
            import zstandard as zs
            c = min(len(zs.ZstdCompressor(level=19).compress(crackle.compress(x, markov_model_order=mo))) for mo in (0, 3))
            c = min(c, min(len(crackle.compress(x, markov_model_order=mo)) for mo in (0, 3)))
            t['C'] += c
            t['wins'] += len(b) < c
    src = hashlib.sha256(open(os.path.join(ROOT, 'bdlc', 'core.py'), 'rb').read()).hexdigest()[:12]
    row = dict(time=time.strftime('%Y-%m-%d %H:%M:%S'), core_sha=src, flags=a.flags, note=a.note)
    for ds, t in agg.items():
        row[ds + '_bpp'] = '%.6f' % (8 * t['B'] / t['N'])
        msg = '%s n=%d bdlc bpp %.6f bytes %d' % (ds, t['n'], 8 * t['B'] / t['N'], t['B'])
        if a.crackle:
            msg += ' | best-crackle(per image oracle) bytes %d gain %.2f%% wins %d/%d' % (t['C'], 100 * (1 - t['B'] / t['C']), t['wins'], t['n'])
        print(msg)
    log = os.path.join(ROOT, 'dev_log.csv')
    new = not os.path.exists(log)
    with open(log, 'a', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['time', 'core_sha', 'flags', 'HeLa_bpp', 'U373_bpp', 'note'])
        if new:
            w.writeheader()
        w.writerow(row)


if __name__ == '__main__':
    main()
