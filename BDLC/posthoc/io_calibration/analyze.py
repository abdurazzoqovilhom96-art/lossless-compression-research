"""Analysis of the I/O calibration (design in prepare.py). Reads only the run folder given as argument and
writes per_map.csv and summary.json there.

    python posthoc/io_calibration/analyze.py runs/<ts>_io_calibration
"""
import csv
import json
import math
import os
import statistics
import sys


def load(run, tag):
    r = json.load(open(os.path.join(run, 'raw', tag + '.json'), encoding='utf-8'))
    if r['errors']:
        raise SystemExit('%s: %d errors, analysis refused' % (tag, len(r['errors'])))
    if 'error' in r.get('null', {}):
        raise SystemExit('%s: null run failed' % tag)
    null_e, null_d = r['null']['enc_median_ns'], r['null']['dec_median_ns']
    out = {}
    for im in r['images']:
        out[im['input_id']] = ((im['enc_median_ns'] - null_e) / 1e9, (im['dec_median_ns'] - null_d) / 1e9)
    return out, null_e / 1e6, null_d / 1e6


def main(run):
    real, nre, nrd = load(run, 'ecc_real')
    shim, nse, nsd = load(run, 'ecc_shim')
    ours, nbe, nbd = load(run, 'bdlc')
    ids = sorted(i for i in real if i.startswith('DAVIS2017/'))
    assert set(ids) <= set(shim) and set(ids) <= set(ours) and len(ids) == 900, len(ids)
    rows, groups = [], {}
    for i in ids:
        g = i.rsplit('/', 1)[0]
        e_real, d_real = real[i]; e_shim, d_shim = shim[i]; e_b, d_b = ours[i]
        rows.append({'input_id': i, 'group': g, 'ecc_enc_s': e_real, 'ecc_dec_s': d_real, 'shim_enc_s': e_shim,
                     'shim_dec_s': d_shim, 'bdlc_enc_s': e_b, 'bdlc_dec_s': d_b})
        acc = groups.setdefault(g, [0.0] * 6)
        for k, v in enumerate((e_real, d_real, e_shim, d_shim, e_b, d_b)):
            acc[k] += v
    with open(os.path.join(run, 'per_map.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def geo(num_idx, den_idx, sub_idx=None):
        """B3 statistic: exp(-mean_g ln(sum BDLC / sum ref)); ref optionally minus the pass-through time."""
        d = []
        for acc in groups.values():
            ref = acc[den_idx] - (acc[sub_idx] if sub_idx is not None else 0.0)
            if ref <= 0:
                return None
            d.append(math.log(acc[num_idx] / ref))
        return math.exp(-sum(d) / len(d))

    def ratio(col_ref, col_b, col_sub=None):
        ref = sum(r[col_ref] - (r[col_sub] if col_sub else 0.0) for r in rows)
        return ref / sum(r[col_b] for r in rows)

    S = {
        'maps': len(rows), 'sequences': len(groups),
        'median_ms': {k: 1000 * statistics.median(r[k] for r in rows) for k in rows[0] if k.endswith('_s')},
        'null_ms': {'ecc_enc': nre, 'ecc_dec': nrd, 'shim_enc': nse, 'shim_dec': nsd, 'bdlc_enc': nbe, 'bdlc_dec': nbd},
        'speedup_geo_measured': {'enc': geo(4, 0), 'dec': geo(5, 1)},
        'speedup_geo_io_removed': {'enc': geo(4, 0, 2), 'dec': geo(5, 1, 3)},
        'speedup_sum_measured': {'enc': ratio('ecc_enc_s', 'bdlc_enc_s'), 'dec': ratio('ecc_dec_s', 'bdlc_dec_s')},
        'speedup_sum_io_removed': {'enc': ratio('ecc_enc_s', 'bdlc_enc_s', 'shim_enc_s'),
                                   'dec': ratio('ecc_dec_s', 'bdlc_dec_s', 'shim_dec_s')},
        'shim_share_of_ecc_net_pct': {'enc': 100 * sum(r['shim_enc_s'] for r in rows) / sum(r['ecc_enc_s'] for r in rows),
                                      'dec': 100 * sum(r['shim_dec_s'] for r in rows) / sum(r['ecc_dec_s'] for r in rows)},
        'sequences_bdlc_faster_io_removed': {
            'enc': sum(a[4] < a[0] - a[2] for a in groups.values()),
            'dec': sum(a[5] < a[1] - a[3] for a in groups.values())},
    }
    with open(os.path.join(run, 'summary.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(S, f, indent=1)
    print(json.dumps(S, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
