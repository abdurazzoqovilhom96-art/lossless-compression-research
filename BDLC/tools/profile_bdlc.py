"""Where does BDLC spend its time?  Per-image component timings under the benchmark conditions
(one pinned logical CPU, high priority, GC off, median of N repeats).

  encode_api      bdlc.encode (header + kernel + bytes conversion)
  encode_kernel   core.encode_kernel only
  scan_labels     core._scan_labels only (the O(HW) label pass)
  decode_api      bdlc.decode
  decode_fresh    core.decode_kernel into a newly allocated output (includes page faults)
  decode_reuse    core.decode_kernel into a reused, already touched output buffer
  copy_floor      np.copyto of the image into a reused buffer (memory-traffic floor for HW pixels)
plus counts of adaptive decisions and bypass bits (from bdlc.analyze) and ns per decision.
Usage: python tools/profile_bdlc.py --manifest ../real_manifest.csv --out PROFILE.csv [--repeats 9]
"""
import argparse
import csv
import gc
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, 'bench')):
    sys.path.insert(0, p)
from worker import load, pin  # noqa: E402


def med(f, reps):
    ts = []
    for _ in range(reps):
        s = time.perf_counter_ns()
        f()
        ts.append(time.perf_counter_ns() - s)
    return int(np.median(ts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--repeats', type=int, default=9)
    ap.add_argument('--cpu', type=int, default=2)
    a = ap.parse_args()
    info = pin(a.cpu, True)
    import bdlc
    from bdlc import api, core
    with open(a.manifest, encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['split'] in ('development', 'test')]
    base = os.path.dirname(os.path.abspath(a.manifest))
    q0, n0 = api.TABLES[1]
    out = []
    for r in sorted(rows, key=lambda r: r['input_id']):
        x = load(os.path.join(base, r['path']), r['native_uint16'].lower() == 'false')
        h, w = x.shape
        b = bdlc.encode(x)
        payload = np.frombuffer(b, np.uint8, offset=2 + len(api._uvarint(h)) + len(api._uvarint(w)))
        res = bdlc.analyze(x, counts=True)
        cnt = res['counts']
        cost = np.zeros(core.NCOST, np.float64)
        core.encode_kernel(x, core.RECIP, q0, n0, cost, 0)
        bypass = int(round(cost[core.NCTX:core.NCOST].sum()))
        ruse = np.empty((h, w), np.uint16)
        core.decode_kernel(payload, ruse, core.RECIP, q0, n0, 0)
        cbuf = np.empty_like(x)
        flg = np.zeros(65536, np.uint8)
        labs = np.empty(65536, np.int64)

        def scan():
            flg[:] = 0
            core._scan_labels(x, flg, labs)

        def dec_fresh():
            o = np.empty((h, w), np.uint16)
            core.decode_kernel(payload, o, core.RECIP, q0, n0, 0)

        for f in (scan, dec_fresh):
            f()
        gc.collect()
        gc.disable()
        try:
            t = {'encode_api_ns': med(lambda: bdlc.encode(x), a.repeats),
                 'encode_kernel_ns': med(lambda: core.encode_kernel(x, core.RECIP, q0, n0, api._NOCOST, 0), a.repeats),
                 'scan_labels_ns': med(scan, a.repeats),
                 'decode_api_ns': med(lambda: bdlc.decode(b), a.repeats),
                 'decode_fresh_ns': med(dec_fresh, a.repeats),
                 'decode_reuse_ns': med(lambda: core.decode_kernel(payload, ruse, core.RECIP, q0, n0, 0), a.repeats),
                 'copy_floor_ns': med(lambda: np.copyto(cbuf, x), a.repeats)}
        finally:
            gc.enable()
        changes = int(np.count_nonzero(x[:, 1:] != x[:, :-1]))
        adaptive = int(cnt.sum())
        out.append({'input_id': r['input_id'], 'dataset': r['dataset'], 'pixels': h * w, 'K': res['K'],
                    'runs': changes + h, 'adaptive_decisions': adaptive, 'bypass_bits': bypass,
                    'stream_bytes': len(b), **t,
                    'ns_per_decision_encode_kernel': (t['encode_kernel_ns'] - t['scan_labels_ns']) / max(adaptive, 1),
                    'ns_per_decision_decode_reuse': t['decode_reuse_ns'] / max(adaptive, 1)})
    with open(a.out, 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=list(out[0]))
        wr.writeheader()
        wr.writerows(out)
    print('pin', info)
    for ds in sorted({o['dataset'] for o in out}):
        rs = [o for o in out if o['dataset'] == ds]
        s = {k: sum(o[k] for o in rs) for k in rs[0]
             if k.endswith('_ns') or k in ('pixels', 'adaptive_decisions', 'bypass_bits', 'runs')}
        print(ds, {k: (round(v / 1e6, 3) if k.endswith('_ns') else v) for k, v in s.items()})


if __name__ == '__main__':
    main()
