"""BDLC benchmark harness.

  audit inputs -> codec freeze check -> unit tests -> preflight -> for every codec (random order):
  pinned bench worker (all images, random order) -> independent verification process -> cold start
  -> byte breakdown (+ LOSO sizes on development data) -> report.

Usage
  python bench/run_bench.py --manifest ../real_manifest.csv --split development --repeats 9
  python bench/run_bench.py --manifest ../test_manifest.csv --split test --write-protocol protocol_test.json
  python bench/run_bench.py --manifest ../test_manifest.csv --split test --protocol protocol_test.json
The test split refuses to run without a protocol written beforehand (--write-protocol runs no codec
on the inputs); the protocol pins code hashes, codec list/parameters, packages, platform and inputs.
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

import numpy as np

BENCH = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BENCH)
for p in (BENCH, ROOT, os.path.join(ROOT, 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)
import backends  # noqa: E402
from worker import dump, load, pixel_sha  # noqa: E402

PY = sys.executable
FIELDS = ['input_id', 'dataset', 'group', 'split', 'native_uint16', 'path']


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def code_hashes():
    out = {}
    for sub in ('bdlc', 'bench', 'tools', 'tests'):
        d = os.path.join(ROOT, sub)
        for n in sorted(os.listdir(d)):
            if n.endswith(('.py', '.npz')):
                out[sub + '/' + n] = sha_file(os.path.join(d, n))
    for n in ('legacy_rvc.py', 'freeze.json', 'requirements.txt', 'START_BDLC.cmd'):
        if os.path.exists(os.path.join(ROOT, n)):
            out[n] = sha_file(os.path.join(ROOT, n))
    return out


def cpu_name():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0')
        return winreg.QueryValueEx(k, 'ProcessorNameString')[0].strip()
    except (ImportError, OSError):
        pass
    try:
        with open('/proc/cpuinfo', encoding='utf-8') as f:
            for line in f:
                if line.startswith('model name'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def read_manifest(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    base = os.path.dirname(os.path.abspath(path))
    for r in rows:
        for k in FIELDS:
            if not r.get(k):
                raise ValueError('manifest %s: field %s missing' % (path, k))
        r['path'] = os.path.normpath(os.path.join(base, r['path']))
    return rows


def audit(rows):
    ids, groups, shas = set(), {}, {}
    for r in rows:
        if r['input_id'] in ids:
            raise ValueError('duplicate input_id ' + r['input_id'])
        ids.add(r['input_id'])
        a = load(r['path'], allow_upcast=r['native_uint16'].lower() == 'false')
        s = pixel_sha(a)
        key = (r['dataset'], r['group'])
        if groups.setdefault(key, r['split']) != r['split']:
            raise ValueError('group split leakage: %s' % (key,))
        if shas.setdefault(s, r['split']) != r['split']:
            raise ValueError('identical pixels across splits: ' + r['input_id'])
        r.update(pixel_sha=s, file_sha=sha_file(r['path']), shape=list(a.shape), pixels=int(a.size),
                 K=int(np.count_nonzero(np.bincount(a.ravel(), minlength=65536))),
                 key=hashlib.sha256(r['input_id'].encode()).hexdigest()[:16])
    return rows


def protocol(args, rows, codecs, unavailable):
    with open(os.path.join(ROOT, 'freeze.json'), encoding='utf-8') as f:
        codec_freeze = json.load(f)
    pipf = subprocess.run([PY, '-m', 'pip', 'freeze'], capture_output=True, text=True).stdout.split()
    ext = [c for c in codecs if c in backends.EXTERNAL]
    extra = {}
    if ext:
        import external
        extra['external_tools'] = {'bin': external.BIN, 'sha256': external.tool_info(ext)}
    return {
        'split': args.split,
        'manifest_sha256': sha_file(args.manifest),
        'inputs': sorted([r['input_id'], r['file_sha'], r['pixel_sha']] for r in rows),
        'codec_freeze': {k: codec_freeze[k] for k in ('files_sha256', 'T1_table_sha256_q0_n0_int64le', 'constants')},
        'code_sha256': code_hashes(),
        'codecs': {c: list(backends.SPEC[c]) for c in codecs},
        'unavailable': unavailable,
        'parameters': {'repeats': args.repeats, 'cpu_affinity_mask': hex(1 << args.cpu),
                       'priority': 'HIGH (0x80)' if os.name == 'nt' else 'nice -10 (setpriority)',
                       'null_run': '1x1 map, repeats pairs, per codec (CLI fixed cost, Q1 1.6)',
                       'seed': args.seed, 'timer': 'time.perf_counter_ns', 'statistic': 'median of repeats',
                       'warmup': '1 encode + 1 decode + array_equal per image', 'gc': 'disabled in timed loop',
                       'coldstart_runs': args.coldstart_runs,
                       'size_jobs': args.size_jobs, 'shard_size': args.shard_size,
                       'timing_column': args.timing_column,
                       'timing_images': (sum(r.get(args.timing_column) == '1' for r in rows)
                                         if args.timing_column else len(rows)),
                       'phases': ('size phase: all images, %d parallel unpinned-priority workers (sizes are '
                                  'deterministic); then timing phase: pinned single CPU, sequential, nothing '
                                  'else running' % args.size_jobs) if args.size_jobs else
                                 'single phase: pinned timing worker on all images'},
        'python': sys.version, 'platform': platform.platform(), 'cpu': cpu_name(),
        'logical_cpus': os.cpu_count(), 'packages': pipf, **extra,
    }


def run(cmd, log, timeout, env=None):
    with open(log, 'w', encoding='utf-8') as f:
        p = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=timeout, env=env)
    return p.returncode


# relative cost of one image (development measurements), used only to start long shards first
_COST = {'jpegxl10': 100, 'hevc_scc_pi': 80, 'hevc_scc_direct': 80, 'jpegxl9': 25, 'flif_u16_e100': 25,
         'flif_pi_e100': 25, 'brotli11': 15, 'flif_u16_e60': 15, 'flif_pi_e60': 15, 'lzma9e': 8,
         'palette_lzma9e': 8, 'jpegxl7': 6, 'rvc': 6, 'zstd19': 3, 'blosc2_zstd_bitshuffle': 3}


def size_phase(out, ok, items, jobs, shard_size, timeout, failures):
    """All images, every codec, in `jobs` parallel workers (one CPU each, normal priority).

    Writes raw_size/<codec>.json and verification/<codec>.json (merged from shards). Timing is not
    measured here; sizes and streams do not depend on parallel execution."""
    import concurrent.futures as cf
    import queue
    import threading
    cpus = queue.Queue()
    for c in range(jobs):
        cpus.put(c)
    lock = threading.Lock()
    tasks = []
    for c in ok:
        for k in range(0, len(items), shard_size):
            tasks.append((c, k // shard_size, items[k:k + shard_size]))
    tasks.sort(key=lambda t: (-_COST.get(t[0], 1), t[0], t[1]))

    def one(task):
        c, s, imgs = task
        cpu = cpus.get()
        try:
            name = '%s__%03d' % (c, s)
            base = {'codec': c, 'shard': s, 'images': imgs, 'stream_dir': os.path.join(out, 'compressed', c), 'cpu': cpu}
            ts = dict(base, mode='size', output=os.path.join(out, 'raw_size', 'shards', name + '.json'))
            tv = dict(base, mode='verify', output=os.path.join(out, 'verification', 'shards', name + '.json'))
            errs = []
            for t, stage in ((ts, 'size'), (tv, 'verify')):
                tf = os.path.join(out, 'tasks', name + '_' + stage + '.json')
                dump(tf, t)
                try:
                    rc = run([PY, os.path.join(BENCH, 'worker.py'), tf], os.path.join(out, 'logs', name + '_' + stage + '.txt'), timeout)
                    if rc:
                        errs.append({'codec': c, 'stage': stage, 'shard': s, 'error': 'worker exit code %d' % rc})
                except subprocess.TimeoutExpired:
                    errs.append({'codec': c, 'stage': stage, 'shard': s, 'error': 'timeout %d s' % timeout})
            with lock:
                failures.extend(errs)
        finally:
            cpus.put(cpu)

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for n, _ in enumerate(ex.map(one, tasks), 1):
            if n % 50 == 0 or n == len(tasks):
                print('[size] %d/%d shards  %.0f s  failures so far: %d' % (n, len(tasks), time.time() - t0, len(failures)), flush=True)
    for c in ok:   # merge shards
        raw = {'codec': c, 'mode': 'size', 'images': [], 'errors': [], 'not_applicable': [], 'shards': 0}
        ver = {'codec': c, 'mode': 'verify', 'images': []}
        for k in range(0, len(items), shard_size):
            name = '%s__%03d' % (c, k // shard_size)
            for path, dst, fields in ((os.path.join(out, 'raw_size', 'shards', name + '.json'), raw, ('images', 'errors', 'not_applicable')),
                                      (os.path.join(out, 'verification', 'shards', name + '.json'), ver, ('images',))):
                if os.path.exists(path):
                    with open(path, encoding='utf-8') as f:
                        j = json.load(f)
                    for fl in fields:
                        dst[fl] += j.get(fl, [])
            raw['shards'] += 1
        dump(os.path.join(out, 'raw_size', c + '.json'), raw)
        dump(os.path.join(out, 'verification', c + '.json'), ver)
        failures.extend({'codec': c, 'stage': 'size', **e} for e in raw['errors'])
        done = {i['input_id'] for i in raw['images']}
        failures.extend({'codec': c, 'stage': 'verify', 'input_id': v['input_id'],
                         'error': v.get('error', 'pixel SHA-256 mismatch')}
                        for v in ver['images'] if not v['ok'] and v['input_id'] in done)
    return time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--split', choices=['development', 'test'], default='development')
    ap.add_argument('--repeats', type=int, default=9)
    ap.add_argument('--codecs', default=','.join(backends.DEFAULT))
    ap.add_argument('--out')
    ap.add_argument('--cpu', type=int, default=2)
    ap.add_argument('--seed', type=int, default=20261028)
    ap.add_argument('--timeout', type=int, default=4 * 3600, help='seconds per worker process')
    ap.add_argument('--coldstart-runs', type=int, default=3)
    ap.add_argument('--exclude-manifest', action='append', default=[],
                    help='manifest whose pixels must not occur in this split (leakage check)')
    ap.add_argument('--write-protocol')
    ap.add_argument('--protocol')
    ap.add_argument('--skip-tests', action='store_true')
    ap.add_argument('--size-jobs', type=int, default=0,
                    help='> 0: size phase on all images in this many parallel workers, then a separate '
                         'pinned sequential timing phase (default 0: single phase as in test A)')
    ap.add_argument('--shard-size', type=int, default=200, help='images per size-phase task')
    ap.add_argument('--timing-column', help='manifest column (1/0) selecting the images of the timing phase')
    args = ap.parse_args()
    if args.repeats < 1:
        ap.error('repeats >= 1')
    if args.timing_column and not args.size_jobs:
        ap.error('--timing-column needs --size-jobs (sizes of all images come from the size phase)')
    if args.size_jobs < 0 or args.shard_size < 1:
        ap.error('--size-jobs >= 0 and --shard-size >= 1')
    codecs = [c for c in args.codecs.split(',') if c]
    for c in codecs:
        if c not in backends.SPEC:
            ap.error('unknown codec ' + c)

    if subprocess.run([PY, os.path.join(ROOT, 'tools', 'write_freeze.py'), '--check'], cwd=ROOT).returncode:
        raise SystemExit('codec freeze mismatch: frozen BDLC files changed')

    rows = [r for r in read_manifest(args.manifest) if r['split'] == args.split]
    if not rows:
        raise SystemExit('no %s rows in manifest' % args.split)
    audit(rows)
    for m in args.exclude_manifest:
        other = {pixel_sha(load(r['path'], r['native_uint16'].lower() == 'false')) for r in read_manifest(m)}
        hit = [r['input_id'] for r in rows if r['pixel_sha'] in other]
        if hit:
            raise SystemExit('pixel-identical images shared with %s: %s' % (m, hit[:5]))
    if args.split == 'test' and any(r['group'] in ('', 'UNSPECIFIED') for r in rows):
        raise SystemExit('test split needs group (sequence) labels')
    if args.timing_column:
        if any(r.get(args.timing_column) not in ('0', '1') for r in rows):
            raise SystemExit('manifest column %s must be 0 or 1 in every row' % args.timing_column)
        if not any(r[args.timing_column] == '1' for r in rows):
            raise SystemExit('no image selected by --timing-column')

    # preflight on synthetic probes only (no codec touches the inputs before the protocol is fixed)
    unavailable = dict(backends.UNAVAILABLE)
    ok = []
    for c in codecs:
        try:
            e, d = backends.get(c)
            ran = 0
            for k, a in backends.probes().items():
                try:
                    b = e(a)
                except backends.NotApplicable:
                    continue
                y = d(b)
                if y.dtype != np.uint16 or y.shape != a.shape or not np.array_equal(y, a):
                    raise ValueError('preflight roundtrip failed on ' + k)
                ran += 1
            if not ran:
                raise ValueError('not applicable to any preflight probe')
            ok.append(c)
        except Exception as ex:
            unavailable[c] = '%s: %s' % (type(ex).__name__, ex)
    proto = protocol(args, rows, ok, unavailable)

    if args.write_protocol:
        proto['written_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        dump(args.write_protocol, proto)
        print('protocol written (no codec was run on the inputs):', args.write_protocol)
        return
    if args.split == 'test':
        if not args.protocol:
            raise SystemExit('test split requires --protocol written beforehand')
        with open(args.protocol, encoding='utf-8') as f:
            pre = json.load(f)
        pre.pop('written_at', None)
        diff = sorted(k for k in set(pre) | set(proto) if pre.get(k) != proto.get(k))
        if diff:
            raise SystemExit('protocol mismatch in: %s' % diff)

    out = os.path.abspath(args.out or os.path.join(ROOT, 'runs', time.strftime('%Y%m%d_%H%M%S') + '_' + args.split))
    os.makedirs(out, exist_ok=False)
    two = args.size_jobs > 0
    dirs = ['provenance', 'raw', 'verification', 'coldstart', 'tasks', 'logs', 'fixtures'] + ['compressed/' + c for c in ok]
    if two:
        dirs += ['raw_size/shards', 'verification/shards'] + ['compressed_timing/' + c for c in ok]
    for d in dirs:
        os.makedirs(os.path.join(out, d))
    timed_rows = [r for r in rows if r.get(args.timing_column) == '1'] if args.timing_column else rows
    status = {'status': 'RUNNING', 'split': args.split, 'scope': 'REAL ' + args.split.upper(),
              'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'codecs': ok, 'images': len(rows),
              'mode': 'two-phase' if two else 'single-phase', 'timing_images': len(timed_rows)}
    dump(os.path.join(out, 'status.json'), status)
    dump(os.path.join(out, 'unavailable.json'), unavailable)
    proto['run'] = {'out': out, 'started': status['started'], 'protocol_file': args.protocol}
    dump(os.path.join(out, 'provenance', 'freeze.json'), proto)
    dump(os.path.join(out, 'provenance', 'input_audit.json'), rows)
    failures = []
    try:
        if not args.skip_tests:
            if run([PY, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], os.path.join(out, 'logs', 'tests.txt'), 1800):
                raise RuntimeError('unit tests failed (logs/tests.txt)')

        first = min(rows, key=lambda r: r['input_id'])
        npy = os.path.join(out, 'fixtures', 'coldstart.npy')
        np.save(npy, load(first['path'], first['native_uint16'].lower() == 'false'))
        items = [{k: r[k] for k in ('input_id', 'key', 'path', 'pixel_sha', 'shape')} |
                 {'allow_upcast': r['native_uint16'].lower() == 'false'} for r in rows]
        if two:
            # ---- size phase: every image, all CPUs (results do not depend on parallel execution)
            el = size_phase(out, ok, items, args.size_jobs, args.shard_size, args.timeout, failures)
            status['size_phase'] = {'jobs': args.size_jobs, 'shard_size': args.shard_size, 'elapsed_s': round(el, 1),
                                    'finished': time.strftime('%Y-%m-%d %H:%M:%S')}
            dump(os.path.join(out, 'status.json'), status)
            dump(os.path.join(out, 'failures.json'), failures)
            sizesha = {}
            for c in ok:
                with open(os.path.join(out, 'raw_size', c + '.json'), encoding='utf-8') as f:
                    sizesha[c] = {i['input_id']: i['stream_sha256'] for i in json.load(f)['images']}
        # ---- timing phase: one pinned CPU, one codec at a time, nothing else running
        timed_ids = {r['input_id'] for r in timed_rows}
        titems = [it for it in items if it['input_id'] in timed_ids]
        order = ok[:]
        random.Random(args.seed).shuffle(order)
        t_phase = time.time()
        for n, c in enumerate(order, 1):
            seed = args.seed ^ int(hashlib.sha256(c.encode()).hexdigest()[:8], 16)
            imgs = titems[:]
            random.Random(seed).shuffle(imgs)
            base = {'codec': c, 'images': imgs,
                    'stream_dir': os.path.join(out, 'compressed_timing' if two else 'compressed', c)}
            t0 = time.time()
            tb = dict(base, mode='bench', repeats=args.repeats, cpu=args.cpu, high_priority=True,
                      output=os.path.join(out, 'raw', c + '.json'))
            tf = os.path.join(out, 'tasks', c + '_bench.json')
            dump(tf, tb)
            try:
                rc = run([PY, os.path.join(BENCH, 'worker.py'), tf], os.path.join(out, 'logs', c + '_bench.txt'), args.timeout)
                if rc:
                    failures.append({'codec': c, 'stage': 'bench', 'error': 'worker exit code %d' % rc})
            except subprocess.TimeoutExpired:
                failures.append({'codec': c, 'stage': 'bench', 'error': 'timeout %d s' % args.timeout})
            if os.path.exists(tb['output']):
                with open(tb['output'], encoding='utf-8') as f:
                    braw = json.load(f)
                failures += [{'codec': c, 'stage': 'bench', **e} for e in braw['errors']]
                if not (braw['pin']['affinity_ok'] and braw['pin']['priority_ok']):
                    failures.append({'codec': c, 'stage': 'bench', 'error': 'CPU pin/priority not applied: %s' % braw['pin']})
                if two:   # timed streams must be the very streams verified in the size phase
                    failures += [{'codec': c, 'stage': 'timing', 'input_id': i['input_id'],
                                  'error': 'timing-phase stream differs from the verified size-phase stream'}
                                 for i in braw['images'] if sizesha[c].get(i['input_id']) != i['stream_sha256']]
            tv = dict(base, mode='verify', output=os.path.join(out, 'verification', c + '.json'))
            tf = os.path.join(out, 'tasks', c + '_verify.json')
            if not two:
                dump(tf, tv)
                try:
                    if run([PY, os.path.join(BENCH, 'worker.py'), tf], os.path.join(out, 'logs', c + '_verify.txt'), args.timeout):
                        failures.append({'codec': c, 'stage': 'verify', 'error': 'verify worker failed'})
                except subprocess.TimeoutExpired:
                    failures.append({'codec': c, 'stage': 'verify', 'error': 'timeout'})
            if not two and os.path.exists(tv['output']):
                with open(tv['output'], encoding='utf-8') as f:
                    vres = json.load(f)
                done = {i['input_id'] for i in braw['images']} if os.path.exists(tb['output']) else set()
                failures += [{'codec': c, 'stage': 'verify', 'input_id': v['input_id'],
                              'error': v.get('error', 'pixel SHA-256 mismatch')}
                             for v in vres['images'] if not v['ok'] and v['input_id'] in done]
            variants = [('cache', None)] + ([('nocache', 1)] if c == 'bdlc' else [])
            cs = []
            for mode, fresh in variants:
                for k in range(args.coldstart_runs):
                    env = dict(os.environ)
                    tmp = None
                    if fresh:
                        tmp = tempfile.mkdtemp(prefix='nbc', dir=os.environ.get('TEMP'))
                        env['NUMBA_CACHE_DIR'] = tmp
                    o = os.path.join(out, 'coldstart', '%s_%s_%d.json' % (c, mode, k))
                    tf = os.path.join(out, 'tasks', '%s_cold_%s_%d.json' % (c, mode, k))
                    dump(tf, {'mode': 'coldstart', 'codec': c, 'npy': npy, 'cpu': args.cpu, 'output': o})
                    try:
                        rc = run([PY, os.path.join(BENCH, 'worker.py'), tf], os.path.join(out, 'logs', c + '_cold.txt'), 1800, env)
                        if not rc:
                            with open(o, encoding='utf-8') as f:
                                cj = json.load(f)
                            if 'not_applicable' not in cj:   # coldstart image outside this codec's coverage
                                cs.append(dict(cj, cache_mode=mode, run=k))
                        else:
                            failures.append({'codec': c, 'stage': 'coldstart', 'error': 'exit %d' % rc})
                    finally:
                        if tmp:
                            shutil.rmtree(tmp, ignore_errors=True)
            dump(os.path.join(out, 'coldstart', c + '.json'), cs)
            dump(os.path.join(out, 'failures.json'), failures)
            print('[%2d/%d] %-24s %6.1f s  failures so far: %d' % (n, len(order), c, time.time() - t0, len(failures)), flush=True)

        status['timing_phase'] = {'images': len(titems), 'elapsed_s': round(time.time() - t_phase, 1)}
        import analysis
        analysis.byte_breakdown(rows, os.path.join(out, 'byte_breakdown.csv'))
        if args.split == 'development':
            os.makedirs(os.path.join(out, 'tables'), exist_ok=True)
            analysis.loso_sizes(rows, os.path.join(out, 'tables', 'loso_sizes.csv'))
    except BaseException as ex:
        status.update(status='BLOCKED', reason='%s: %s' % (type(ex).__name__, ex))
        dump(os.path.join(out, 'status.json'), status)
        dump(os.path.join(out, 'failures.json'), failures)
        traceback.print_exc()
        raise SystemExit(1)

    def count(sub, n_rows):
        measured, na = 0, []
        for c in ok:
            p = os.path.join(out, sub, c + '.json')
            if os.path.exists(p):
                with open(p, encoding='utf-8') as f:
                    j = json.load(f)
                measured += len(j['images'])
                na += [dict(x, codec=c) for x in j.get('not_applicable', [])]
        return measured, len(ok) * n_rows - len(na), na   # coverage rule (Q1 1.4): N/A pairs are not expected

    measured, expected, not_applicable = count('raw_size' if two else 'raw', len(rows))
    t_measured, t_expected, _ = count('raw', len(timed_rows))
    complete = not failures and measured == expected and t_measured == t_expected
    dump(os.path.join(out, 'not_applicable.json'), not_applicable)
    status.update(status='COMPLETE' if complete else 'PARTIAL', finished=time.strftime('%Y-%m-%d %H:%M:%S'),
                  measured_pairs=measured, expected_pairs=expected, not_applicable_pairs=len(not_applicable),
                  timed_pairs=t_measured, expected_timed_pairs=t_expected,
                  failures=len(failures), unavailable=sorted(unavailable))
    dump(os.path.join(out, 'status.json'), status)
    dump(os.path.join(out, 'failures.json'), failures)
    try:   # results/: tables, figures, statistics, paper, reports (own status file; the run's status is final)
        import make_reports
        make_reports.build(out)
    except Exception:
        traceback.print_exc()
        print('reporting failed; re-run: python bench/make_reports.py', out)
    dump(os.path.join(out, 'provenance', 'artifact_hashes.json'),
         {os.path.relpath(os.path.join(dp, n), out).replace(os.sep, '/'): sha_file(os.path.join(dp, n))
          for dp, _, fs in os.walk(out) for n in fs if n != 'artifact_hashes.json'})
    print('RESULTS:', out, status['status'])


if __name__ == '__main__':
    main()
