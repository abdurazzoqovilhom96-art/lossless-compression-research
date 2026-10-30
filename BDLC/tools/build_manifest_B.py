"""Builds the input set of test cohort B (Q1_REJA_UZ.md section 2; PROTOKOL_B_UZ.md).

  python -I tools/build_manifest_B.py DAVIS_ZIP

* DAVIS 2017 trainval 480p: every annotation map (Annotations/480p/<sequence>/<frame>.png, palette
  PNG) is stored unchanged as a single-page uint8 TIFF (zlib) in data_B/DAVIS2017/<sequence>/; values
  are the object ids (0 = background; 255 occurs in a few maps and is kept as a label). One cluster
  (group) per video sequence.
* The CTC maps of test cohort A (test_manifest.csv) are appended unchanged, so that the external
  baselines are also compared on them; Fluo-N2DH-SIM+ stays marked synthetic.
Writes manifest_B.csv and data_B/DAVIS2017/INVENTORY.csv (source sha256 per map).
"""
import csv
import hashlib
import io
import os
import sys
import zipfile

import numpy as np
import tifffile
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = ['input_id', 'dataset', 'group', 'split', 'native_uint16', 'path', 'synthetic', 'subset', 'timing']
M_TIMING = 10   # timed frames per DAVIS sequence: i_k = floor(k N / M), k = 0..M-1, M = min(N, 10)


def timing_frames(n):
    m = min(n, M_TIMING)
    return {(k * n) // m for k in range(m)}


def main(zpath):
    z = zipfile.ZipFile(zpath)
    sets = {}
    for sub in ('train', 'val'):
        for s in z.read('DAVIS/ImageSets/2017/%s.txt' % sub).decode().split():
            sets[s] = sub
    names = sorted(n for n in z.namelist() if n.startswith('DAVIS/Annotations/480p/') and n.endswith('.png'))
    out_dir = os.path.join(ROOT, 'data_B', 'DAVIS2017')
    rows, inv = [], []
    for n in names:
        seq, frame = n.split('/')[-2], os.path.splitext(n.split('/')[-1])[0]
        raw = z.read(n)
        im = Image.open(io.BytesIO(raw))
        if im.mode != 'P':
            raise SystemExit('unexpected PNG mode %s: %s' % (im.mode, n))
        a = np.ascontiguousarray(np.array(im), np.uint8)
        if a.ndim != 2:
            raise SystemExit('not 2D: ' + n)
        rel = os.path.join('data_B', 'DAVIS2017', seq, frame + '.tif')
        dst = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tifffile.imwrite(dst, a, compression='zlib')
        if not np.array_equal(tifffile.imread(dst), a):
            raise SystemExit('TIFF roundtrip failed: ' + dst)
        rows.append({'input_id': 'DAVIS2017/%s/%s' % (seq, frame), 'dataset': 'DAVIS2017_480p',
                     'group': 'DAVIS2017/' + seq, 'split': 'test', 'native_uint16': 'false',
                     'path': rel.replace(os.sep, '/'), 'synthetic': 'false', 'subset': sets.get(seq, '?')})
        inv.append({'zip_member': n, 'png_sha256': hashlib.sha256(raw).hexdigest(),
                    'pixel_sha256_uint8': hashlib.sha256(a.tobytes()).hexdigest(),
                    'H': a.shape[0], 'W': a.shape[1], 'K': int(np.unique(a).size), 'max': int(a.max())})
    # timing column: M_TIMING frames per DAVIS sequence (frames in name order); every CTC map
    by_seq = {}
    for r in rows:
        by_seq.setdefault(r['group'], []).append(r)
    for g, rs in by_seq.items():
        rs.sort(key=lambda r: r['input_id'])
        pick = timing_frames(len(rs))
        for i, r in enumerate(rs):
            r['timing'] = '1' if i in pick else '0'
    with open(os.path.join(ROOT, 'test_manifest.csv'), encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            rows.append({k: r.get(k, '') for k in FIELDS[:-2]} | {'subset': 'CTC test cohort A', 'timing': '1'})
    with open(os.path.join(ROOT, 'manifest_B.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out_dir, 'INVENTORY.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(inv[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(inv)
    seqs = {r['group'] for r in rows if r['dataset'] == 'DAVIS2017_480p'}
    print('DAVIS maps', len(inv), 'sequences', len(seqs), '| CTC rows', len(rows) - len(inv),
          '| manifest_B.csv rows', len(rows), '| timed', sum(r['timing'] == '1' for r in rows))


if __name__ == '__main__':
    main(sys.argv[1])
