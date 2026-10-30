"""Benchmark worker: exactly one codec per process.

Task JSON field 'mode':
  bench      pin to one logical CPU (high priority; Windows or Linux), then per image: warm-up encode +
             decode + equality check, `repeats` timed (encode, decode) pairs, medians; saves the stream.
             Images a configuration does not apply to (backends.NotApplicable) are listed, not failed.
             Finally `repeats` null pairs on a 1x1 map (fixed per-call cost of command-line codecs).
  size       size phase (no timing): per image encode, decode, equality check, saved stream; may run
             in parallel with other size workers because sizes and streams are deterministic.
  verify     fresh process: decode every saved stream, compare pixel SHA-256 with the source.
  coldstart  fresh process: time the codec's import + factory, then its first and second
             encode/decode calls on one image (loaded from .npy so no image library is preloaded).
Timing uses time.perf_counter_ns(); garbage collection is disabled inside the timed loop.
"""
import ctypes
import gc
import hashlib
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


# ------------------------------------------------------------------ OS helpers (Windows)
class _PMC(ctypes.Structure):
    _fields_ = [('cb', ctypes.c_uint32), ('PageFaultCount', ctypes.c_uint32),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


def _k32():
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    k.SetProcessAffinityMask.restype = ctypes.c_int
    k.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                         ctypes.POINTER(ctypes.c_size_t)]
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.GetPriorityClass.argtypes = [ctypes.c_void_p]
    k.GetPriorityClass.restype = ctypes.c_uint32
    return k


def pin(cpu, high_priority=True):
    info = {'requested_cpu': cpu, 'affinity_ok': False, 'priority_ok': False}
    if cpu is None or cpu < 0:
        return info
    if os.name != 'nt':
        # Linux (bdlc-bench container): pin the calling thread, raise priority to nice -10
        # (needs CAP_SYS_NICE, i.e. docker run --cap-add SYS_NICE). Child processes started by the
        # external CLI codecs inherit both.
        try:
            os.sched_setaffinity(0, {cpu})
            info['affinity_ok'] = os.sched_getaffinity(0) == {cpu}
            info['affinity_mask'] = hex(1 << cpu)
        except (AttributeError, OSError) as ex:
            info['affinity_error'] = str(ex)
        if high_priority:
            try:
                os.setpriority(os.PRIO_PROCESS, 0, -10)
            except (AttributeError, OSError) as ex:
                info['priority_error'] = str(ex)
            info['nice'] = os.getpriority(os.PRIO_PROCESS, 0)
            info['priority_ok'] = info['nice'] <= -10
        return info
    k = _k32()
    h = k.GetCurrentProcess()
    info['affinity_ok'] = bool(k.SetProcessAffinityMask(h, 1 << cpu))
    if high_priority:
        info['priority_ok'] = bool(k.SetPriorityClass(h, 0x80))   # HIGH_PRIORITY_CLASS
    pm, sm = ctypes.c_size_t(), ctypes.c_size_t()
    if k.GetProcessAffinityMask(h, ctypes.byref(pm), ctypes.byref(sm)):
        info['affinity_mask'] = hex(pm.value)
    info['priority_class'] = hex(k.GetPriorityClass(h))
    return info


def peak_working_set():
    if os.name != 'nt':
        return None
    try:
        psapi = ctypes.WinDLL('psapi')
        c = _PMC()
        c.cb = ctypes.sizeof(c)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_uint32]
        if psapi.GetProcessMemoryInfo(_k32().GetCurrentProcess(), ctypes.byref(c), c.cb):
            return int(c.PeakWorkingSetSize)
    except OSError:
        pass
    return None


# ------------------------------------------------------------------ data
def load(path, allow_upcast=False):
    """2D label map as C-contiguous uint16.  uint8 is widened (ID-preserving) only if allowed."""
    if str(path).lower().endswith('.npy'):
        a = np.load(path, allow_pickle=False)
    else:
        import tifffile
        with tifffile.TiffFile(path) as t:
            if len(t.pages) != 1:
                raise ValueError('single-page TIFF required: %s' % path)
            a = t.asarray()
    if a.ndim != 2 or not a.size:
        raise ValueError('2D nonempty label map required: %s' % path)
    if a.dtype == np.uint16:
        return np.ascontiguousarray(a)
    if a.dtype == np.uint8 and allow_upcast:
        return np.ascontiguousarray(a.astype(np.uint16))
    raise ValueError('native uint16 required (got %s): %s' % (a.dtype, path))


def pixel_sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).astype('<u2', copy=False).tobytes()).hexdigest()


def dump(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


# ------------------------------------------------------------------ modes
def run_bench(t):
    info = pin(t.get('cpu', 2), t.get('high_priority', True))
    import backends
    enc, dec = backends.get(t['codec'])
    reps = int(t['repeats'])
    res = {'codec': t['codec'], 'mode': 'bench', 'repeats': reps, 'pin': info,
           'python': sys.version, 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'images': [], 'errors': [],
           'not_applicable': []}
    for item in t['images']:
        try:
            a = load(item['path'], item.get('allow_upcast', False))
            if pixel_sha(a) != item['pixel_sha']:
                raise ValueError('source pixels differ from audit')
            gc.collect()
            try:
                b = enc(a)
            except backends.NotApplicable as ex:   # coverage rule: recorded, not an error
                res['not_applicable'].append({'input_id': item['input_id'], 'reason': str(ex)})
                dump(t['output'], res)
                continue
            d = dec(b)
            if d.dtype != np.uint16 or d.shape != a.shape or not np.array_equal(d, a):
                raise ValueError('LOSSLESS FAILURE in warm-up')
            te, td, same = [], [], True
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
                    if b2 != b:
                        same = False
                    if not np.array_equal(d, a):
                        raise ValueError('LOSSLESS FAILURE in timed repeat')
            finally:
                gc.enable()
            sp = os.path.join(t['stream_dir'], item['key'] + '.bin')
            with open(sp, 'wb') as f:
                f.write(b)
            res['images'].append({'input_id': item['input_id'], 'key': item['key'],
                                  'bytes': backends.accounted_bytes(t['codec'], b), 'stream_bytes': len(b),
                                  'stream_sha256': hashlib.sha256(b).hexdigest(), 'deterministic': same,
                                  'enc_ns': te, 'dec_ns': td,
                                  'enc_median_ns': int(np.median(te)), 'dec_median_ns': int(np.median(td))})
        except Exception as ex:   # recorded, never hidden
            res['errors'].append({'input_id': item['input_id'], 'error': '%s: %s' % (type(ex).__name__, ex)})
        dump(t['output'], res)
    # null run (Q1_REJA_UZ.md §1.6): the same call on a 1x1 map, so that the fixed per-call cost of
    # command-line codecs (process start, file I/O) can be subtracted; recorded for every codec.
    try:
        z = np.zeros((1, 1), np.uint16)
        if not np.array_equal(dec(enc(z)), z):
            raise ValueError('null roundtrip failed')
        ne, nd = [], []
        gc.disable()
        try:
            for _ in range(reps):
                s = time.perf_counter_ns()
                bz = enc(z)
                e = time.perf_counter_ns()
                dec(bz)
                f = time.perf_counter_ns()
                ne.append(e - s)
                nd.append(f - e)
        finally:
            gc.enable()
        res['null'] = {'enc_ns': ne, 'dec_ns': nd, 'enc_median_ns': int(np.median(ne)),
                       'dec_median_ns': int(np.median(nd))}
    except Exception as ex:
        res['null'] = {'error': '%s: %s' % (type(ex).__name__, ex)}
    res['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
    res['peak_working_set_bytes'] = peak_working_set()
    dump(t['output'], res)


def run_size(t):
    """Size phase: encode, decode, equality check and saved stream per image; no timing.

    Sizes and streams are deterministic, so several size workers may run in parallel on different
    CPUs without affecting any result; speed is measured only by run_bench (timing phase)."""
    info = pin(t.get('cpu', -1), False)
    import backends
    enc, dec = backends.get(t['codec'])
    res = {'codec': t['codec'], 'mode': 'size', 'shard': t.get('shard'), 'pin': info, 'python': sys.version,
           'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'images': [], 'errors': [], 'not_applicable': []}
    for n, item in enumerate(t['images']):
        try:
            a = load(item['path'], item.get('allow_upcast', False))
            if pixel_sha(a) != item['pixel_sha']:
                raise ValueError('source pixels differ from audit')
            try:
                b = enc(a)
            except backends.NotApplicable as ex:   # coverage rule: recorded, not an error
                res['not_applicable'].append({'input_id': item['input_id'], 'reason': str(ex)})
                continue
            d = dec(b)
            if d.dtype != np.uint16 or d.shape != a.shape or not np.array_equal(d, a):
                raise ValueError('LOSSLESS FAILURE')
            with open(os.path.join(t['stream_dir'], item['key'] + '.bin'), 'wb') as f:
                f.write(b)
            res['images'].append({'input_id': item['input_id'], 'key': item['key'],
                                  'bytes': backends.accounted_bytes(t['codec'], b), 'stream_bytes': len(b),
                                  'stream_sha256': hashlib.sha256(b).hexdigest()})
        except Exception as ex:   # recorded, never hidden
            res['errors'].append({'input_id': item['input_id'], 'error': '%s: %s' % (type(ex).__name__, ex)})
        if n % 50 == 49:
            dump(t['output'], res)
    res['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
    dump(t['output'], res)


def run_verify(t):
    import backends
    _, dec = backends.get(t['codec'])
    res = {'codec': t['codec'], 'mode': 'verify', 'images': []}
    for item in t['images']:
        sp = os.path.join(t['stream_dir'], item['key'] + '.bin')
        r = {'input_id': item['input_id']}
        try:
            with open(sp, 'rb') as f:
                b = f.read()
            d = dec(b)
            r.update(stream_sha256=hashlib.sha256(b).hexdigest(), shape=list(d.shape), dtype=str(d.dtype),
                     pixel_sha=pixel_sha(d))
            r['ok'] = (r['pixel_sha'] == item['pixel_sha'] and r['shape'] == item['shape'] and r['dtype'] == 'uint16')
        except Exception as ex:
            r.update(ok=False, error='%s: %s' % (type(ex).__name__, ex))
        res['images'].append(r)
    dump(t['output'], res)


def run_coldstart(t):
    info = pin(t.get('cpu', 2), t.get('high_priority', True))
    a = np.load(t['npy'], allow_pickle=False)
    import backends
    s = time.perf_counter_ns()
    enc, dec = backends.get(t['codec'])
    t1 = time.perf_counter_ns()
    try:
        b = enc(a)
    except backends.NotApplicable as ex:
        dump(t['output'], {'codec': t['codec'], 'mode': 'coldstart', 'pin': info, 'not_applicable': str(ex)})
        return
    t2 = time.perf_counter_ns()
    d = dec(b)
    t3 = time.perf_counter_ns()
    ok = bool(np.array_equal(d, a))
    b = enc(a)
    t4 = time.perf_counter_ns()
    d = dec(b)
    t5 = time.perf_counter_ns()
    dump(t['output'], {'codec': t['codec'], 'mode': 'coldstart', 'pin': info, 'ok': ok and np.array_equal(d, a),
                       'numba_cache_dir': os.environ.get('NUMBA_CACHE_DIR', '(default)'),
                       'import_ns': t1 - s, 'first_encode_ns': t2 - t1, 'first_decode_ns': t3 - t2,
                       'second_encode_ns': t4 - t3, 'second_decode_ns': t5 - t4})


def main():
    with open(sys.argv[1], encoding='utf-8') as f:
        t = json.load(f)
    {'bench': run_bench, 'size': run_size, 'verify': run_verify, 'coldstart': run_coldstart}[t['mode']](t)


if __name__ == '__main__':
    main()
