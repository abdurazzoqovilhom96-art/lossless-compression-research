"""Run-to-run reproducibility of two benchmark runs on the same inputs.

For every codec present in both runs: are the streams byte-identical (stream SHA-256), and how much
do the per-image median times differ (ratio run_b / run_a; median and range over images, and the
ratio of summed medians, which is what throughput uses).
Usage: python tools/compare_runs.py RUN_A RUN_B OUT.csv
"""
import csv
import json
import os
import sys

import numpy as np


def load(run, c):
    p = os.path.join(run, 'raw', c + '.json')
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return {m['input_id']: m for m in json.load(f)['images']}


def main():
    a, b, out = sys.argv[1:4]
    with open(os.path.join(a, 'status.json'), encoding='utf-8') as f:
        codecs = json.load(f)['codecs']
    rows = []
    for c in codecs:
        ra, rb = load(a, c), load(b, c)
        if not ra or not rb:
            continue
        ids = sorted(ra.keys() & rb.keys())
        same = sum(ra[i]['stream_sha256'] == rb[i]['stream_sha256'] for i in ids)
        row = {'codec': c, 'images': len(ids), 'identical_streams': same}
        for k in ('enc', 'dec'):
            r = np.array([rb[i][k + '_median_ns'] / ra[i][k + '_median_ns'] for i in ids])
            row[k + '_ratio_median'] = float(np.median(r))
            row[k + '_ratio_min'] = float(r.min())
            row[k + '_ratio_max'] = float(r.max())
            row[k + '_ratio_of_sums'] = (sum(rb[i][k + '_median_ns'] for i in ids) /
                                         sum(ra[i][k + '_median_ns'] for i in ids))
        rows.append(row)
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print('%-24s same %2d/%2d  enc sum-ratio %.3f (img %.2f..%.2f)  dec sum-ratio %.3f (img %.2f..%.2f)' % (
            r['codec'], r['identical_streams'], r['images'], r['enc_ratio_of_sums'], r['enc_ratio_min'],
            r['enc_ratio_max'], r['dec_ratio_of_sums'], r['dec_ratio_min'], r['dec_ratio_max']))


if __name__ == '__main__':
    main()
