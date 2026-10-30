"""Size-only analyses (not timed).

byte_breakdown: exact stream/header/payload bytes per image plus the ideal information content
  (sum of -log2 p, in bits) of each BDLC decision category, from bdlc.analyze().  Arithmetic coding
  admits no exact per-category byte attribution; the category sums differ from the payload only by
  the coder's termination and rounding overhead (column payload_minus_model_bytes).
loso_sizes: development only.  For every held-out sequence the initial table is built (same rule
  and strength 32 as T1) from the other sequences only; the image is coded with that table
  (model id 3) and decoded back.  This is the honest development size of BDLC, because T1 itself
  was built from all 52 development maps.
"""
import csv
import os
import sys

import numpy as np

BENCH = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BENCH)
for p in (BENCH, ROOT, os.path.join(ROOT, 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)
import bdlc  # noqa: E402
from bdlc.api import CATEGORIES  # noqa: E402
from worker import load  # noqa: E402


def _write(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _img(r):
    return load(r['path'], r['native_uint16'].lower() == 'false')


def byte_breakdown(rows, path):
    out = []
    for r in sorted(rows, key=lambda r: r['input_id']):
        res = bdlc.analyze(_img(r))
        d = {'input_id': r['input_id'], 'dataset': r['dataset'], 'group': r['group'], 'pixels': r['pixels'],
             'K': res['K'], 'stream_bytes': res['stream_bytes'], 'header_bytes': res['header_bytes'],
             'payload_bytes': res['payload_bytes']}
        for name, _, _ in CATEGORIES:
            d[name + '_bits'] = round(res[name + '_bits'], 3)
        d['model_bits_total'] = round(res['model_bits_total'], 3)
        d['payload_minus_model_bytes'] = round(res['payload_bytes'] - res['model_bits_total'] / 8, 3)
        d['unattributed_bits'] = round(res['unattributed_bits'], 6)
        out.append(d)
    _write(path, out)
    return out


def loso_sizes(rows, path, strength=32):
    from init_eval import table
    imgs = {r['input_id']: _img(r) for r in rows}
    counts = {i: bdlc.analyze(a, counts=True)['counts'] for i, a in imgs.items()}
    out = []
    for g in sorted({r['group'] for r in rows}):
        init = table(np.sum([counts[r['input_id']] for r in rows if r['group'] != g], axis=0), strength)
        for r in sorted((r for r in rows if r['group'] == g), key=lambda r: r['input_id']):
            a = imgs[r['input_id']]
            b = bdlc.encode(a, init=init)
            if not np.array_equal(bdlc.decode(b, init=init), a):
                raise RuntimeError('LOSO roundtrip failed: ' + r['input_id'])
            out.append({'input_id': r['input_id'], 'dataset': r['dataset'], 'group': r['group'],
                        'pixels': r['pixels'], 'bytes_loso': len(b), 'bytes_t1_in_sample': len(bdlc.encode(a)),
                        'loso_train_groups': '|'.join(sorted({q['group'] for q in rows} - {g}))})
    _write(path, out)
    return out
