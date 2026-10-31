"""Builds the input set of test cohort C (PROTOKOL_C_UZ.md): COCO-Stuff semantic maps.

  python -I tools/build_manifest_C.py COCOSTUFF_ZIP

* COCO-Stuff 2017, validation split: every map val2017/<id>.png of stuffthingmaps_trainval2017.zip
  (one 8-bit grey PNG per image; values 0..181 = stuff and thing classes, 255 = unlabeled) is stored
  unchanged as a single-page uint8 TIFF (zlib) in data_C/COCO-Stuff/val2017/. The training split is not used.
* COCO images are independent photographs, so every map is its own cluster (group = map).
* Timing column: every 5th map in id order (1,000 of 5,000 maps).
Writes manifest_C.csv and data_C/COCO-Stuff/INVENTORY.csv (source sha256 per map).
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
TIMING_EVERY = 5


def main(zpath):
    z = zipfile.ZipFile(zpath)
    names = sorted(n for n in z.namelist() if n.startswith('val2017/') and n.endswith('.png'))
    if not names:
        raise SystemExit('no val2017/*.png members in ' + zpath)
    out_dir = os.path.join(ROOT, 'data_C', 'COCO-Stuff')
    rows, inv = [], []
    for k, n in enumerate(names):
        stem = os.path.splitext(os.path.basename(n))[0]
        raw = z.read(n)
        im = Image.open(io.BytesIO(raw))
        if im.mode not in ('L', 'P'):
            raise SystemExit('unexpected PNG mode %s: %s' % (im.mode, n))
        a = np.ascontiguousarray(np.array(im), np.uint8)
        if a.ndim != 2:
            raise SystemExit('not 2D: ' + n)
        rel = os.path.join('data_C', 'COCO-Stuff', 'val2017', stem + '.tif')
        dst = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tifffile.imwrite(dst, a, compression='zlib')
        if not np.array_equal(tifffile.imread(dst), a):
            raise SystemExit('TIFF roundtrip failed: ' + dst)
        iid = 'COCO-Stuff/val2017/' + stem
        rows.append({'input_id': iid, 'dataset': 'COCO-Stuff_val2017', 'group': iid, 'split': 'test',
                     'native_uint16': 'false', 'path': rel.replace(os.sep, '/'), 'synthetic': 'false',
                     'subset': 'val2017', 'timing': '1' if k % TIMING_EVERY == 0 else '0'})
        inv.append({'zip_member': n, 'png_mode': im.mode, 'png_sha256': hashlib.sha256(raw).hexdigest(),
                    'pixel_sha256_uint8': hashlib.sha256(a.tobytes()).hexdigest(),
                    'H': a.shape[0], 'W': a.shape[1], 'K': int(np.unique(a).size), 'max': int(a.max())})
    with open(os.path.join(ROOT, 'manifest_C.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out_dir, 'INVENTORY.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(inv[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(inv)
    ks = sorted(r['K'] for r in inv)
    print('COCO-Stuff val2017 maps', len(rows), '| timed', sum(r['timing'] == '1' for r in rows),
          '| K min/median/max', ks[0], ks[len(ks) // 2], ks[-1],
          '| sizes', len({(r['H'], r['W']) for r in inv}), 'distinct')


if __name__ == '__main__':
    main(sys.argv[1])
