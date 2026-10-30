"""Environment check for timing inside the Linux container (not a benchmark run).

Times one codec on the development maps with the same loop as bench/worker.py
(verified warm-up, GC disabled, perf_counter_ns, median of R encode/decode pairs),
but pins with os.sched_setaffinity and raises priority with os.setpriority, which
bench/worker.py does only on Windows.  Used only to see whether the container is
a usable timing environment; numbers from it are not reported as results.

usage: python env_calibration.py CODEC MANIFEST OUT_CSV [CPU] [REPEATS]
"""
import csv
import gc
import os
import platform
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'bench'), ROOT]
import numpy as np  # noqa: E402

from worker import load  # noqa: E402  (Windows-only parts of worker are not called)


def main(codec, manifest, out_csv, cpu=2, reps=9):
    pin_ok, prio = False, None
    try:
        os.sched_setaffinity(0, {cpu})
        pin_ok = os.sched_getaffinity(0) == {cpu}
    except OSError as e:
        print('affinity failed:', e)
    try:
        os.setpriority(os.PRIO_PROCESS, 0, -10)
    except OSError as e:
        print('priority not raised:', e)
    prio = os.getpriority(os.PRIO_PROCESS, 0)
    import backends
    enc, dec = backends.get(codec)
    base = os.path.dirname(os.path.abspath(manifest))
    rows = [r for r in csv.DictReader(open(manifest, encoding='utf-8')) if r['split'] == 'development']
    px = te_sum = td_sum = 0
    nbytes = 0
    for r in rows:
        a = load(os.path.join(base, r['path']))
        gc.collect()
        b = enc(a)
        if not np.array_equal(dec(b), a):
            raise SystemExit('LOSSLESS FAILURE %s %s' % (codec, r['input_id']))
        te, td = [], []
        gc.disable()
        try:
            for _ in range(reps):
                s = time.perf_counter_ns()
                b2 = enc(a)
                e = time.perf_counter_ns()
                d = dec(b2)
                f = time.perf_counter_ns()
                te.append(e - s)
                td.append(f - e)
        finally:
            gc.enable()
        if not np.array_equal(d, a):
            raise SystemExit('LOSSLESS FAILURE (timed) %s %s' % (codec, r['input_id']))
        px += a.size
        nbytes += len(b)
        te_sum += statistics.median(te)
        td_sum += statistics.median(td)
    row = dict(codec=codec, images=len(rows), pixels=px, bytes=nbytes,
               encode_MPix_s=round(px / te_sum * 1e3, 2), decode_MPix_s=round(px / td_sum * 1e3, 2),
               cpu=cpu, pinned=pin_ok, nice=prio, repeats=reps,
               python=platform.python_version(), system=platform.platform())
    new = not os.path.exists(out_csv)
    with open(out_csv, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(row), lineterminator='\n')
        if new:
            w.writeheader()
        w.writerow(row)
    print(row)


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else 2, int(a[4]) if len(a) > 4 else 9)
