"""Acquire the independent test cohort (CTC training-set GT/SEG maps) and write test_manifest.csv.

  python -I tools/fetch_test.py --plan        # sizes only (HEAD / Zenodo metadata), downloads nothing
  python -I tools/fetch_test.py --download    # download (each archive into its own new empty folder)
  python -I tools/fetch_test.py --extract     # extract *_GT/SEG/man_seg*.tif, audit, write manifest

Sources: the official CTC host first, then the official CTC Zenodo copy when one exists.
Nothing is ever replaced by synthetic data; a dataset that cannot be fetched is recorded as unavailable.
Fluo-N2DH-SIM+ is simulated and is flagged synthetic=true (reported separately, never pooled with real data).
CTC terms of use must be checked by the user; the paper cites the CTC and the dataset sources.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DL = os.path.join(ROOT, 'downloads')
DATA = os.path.join(ROOT, 'data_test')
CTC = 'https://data.celltrackingchallenge.net/training-datasets/%s.zip'
ZENODO = {'PhC-C2DL-PSC': 15608232, 'Fluo-N2DH-GOWT1': 15608211, 'Fluo-N2DH-SIM+': 15608207}
DATASETS = ['Fluo-N2DL-HeLa', 'PhC-C2DL-PSC', 'Fluo-C2DL-Huh7', 'Fluo-C2DL-MSC', 'Fluo-N2DH-GOWT1']
OPTIONAL_BF = ['BF-C2DL-HSC', 'BF-C2DL-MuSC']   # only if the cohort stays <= 5 GB in total
SYNTHETIC = ['Fluo-N2DH-SIM+']
LIMIT = 5 * 10 ** 9
UA = {'User-Agent': 'Mozilla/5.0 BDLC-Research'}
STATUS = os.path.join(DL, 'ACQUISITION.json')


def _open(url, method='GET', timeout=30):
    return urllib.request.urlopen(urllib.request.Request(url, method=method, headers=UA), timeout=timeout)


def candidates(name):
    """[(source label, url, size or None, md5 or None)] in order of preference."""
    out = []
    try:
        with _open(CTC % urllib.parse.quote(name), 'HEAD', 25) as r:
            out.append(('CTC official host', CTC % urllib.parse.quote(name), int(r.headers['Content-Length']), None))
    except Exception as ex:
        out.append(('CTC official host', CTC % urllib.parse.quote(name), None, 'unreachable: %s' % type(ex).__name__))
    if name in ZENODO:
        for attempt in range(4):
            try:
                with _open('https://zenodo.org/api/records/%d' % ZENODO[name]) as r:
                    rec = json.load(r)
                f = next(f for f in rec['files'] if f['key'] == name + '.zip')
                out.append(('Zenodo %s (creator: %s, license %s)' % (rec['doi'], rec['metadata']['creators'][0]['name'],
                                                                     rec['metadata']['license']['id']),
                            'https://zenodo.org/records/%d/files/%s?download=1' % (ZENODO[name], urllib.parse.quote(f['key'])),
                            int(f['size']), f['checksum'].split(':', 1)[1]))
                break
            except urllib.error.HTTPError as ex:
                if ex.code != 429:
                    raise
                time.sleep(15 * (attempt + 1))
    return out


def plan():
    rows = {}
    for n in DATASETS + OPTIONAL_BF + SYNTHETIC:
        c = [x for x in candidates(n) if x[2] is not None]
        rows[n] = {'available': bool(c), 'source': c[0][0] if c else None, 'url': c[0][1] if c else None,
                   'bytes': c[0][2] if c else None, 'md5_expected': c[0][3] if c else None,
                   'synthetic': n in SYNTHETIC}
    core = sum(r['bytes'] or 0 for n, r in rows.items() if n not in OPTIONAL_BF)
    bf = sum(rows[n]['bytes'] or 0 for n in OPTIONAL_BF)
    for n in OPTIONAL_BF:
        rows[n]['selected'] = rows[n]['available'] and core + bf <= LIMIT
    for n in DATASETS + SYNTHETIC:
        rows[n]['selected'] = rows[n]['available']
    return rows


def download(rows):
    os.makedirs(DL, exist_ok=True)
    for n, r in rows.items():
        if not r['selected']:
            continue
        d = os.path.join(DL, n)
        dest = os.path.join(d, n + '.zip')
        if os.path.exists(dest) and r.get('sha256'):
            continue
        if os.path.exists(d) and os.listdir(d):
            raise SystemExit('target folder not empty: ' + d)
        os.makedirs(d, exist_ok=True)
        print('YUKLASH: %s.zip | manba: %s | hajm: %.1f MB' % (n, r['source'], r['bytes'] / 1e6), flush=True)
        md5, sha = hashlib.md5(), hashlib.sha256()
        part = dest + '.part'
        with _open(r['url'], timeout=120) as resp, open(part, 'wb') as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                md5.update(chunk)
                sha.update(chunk)
        size = os.path.getsize(part)
        if size != r['bytes'] or (r['md5_expected'] and md5.hexdigest() != r['md5_expected']):
            os.remove(part)
            raise SystemExit('size/MD5 mismatch for %s' % n)
        with zipfile.ZipFile(part) as z:
            if z.testzip() is not None:
                os.remove(part)
                raise SystemExit('corrupt ZIP ' + n)
        os.replace(part, dest)
        r.update(path=dest, md5=md5.hexdigest(), sha256=sha.hexdigest(), downloaded_at=time.strftime('%Y-%m-%d %H:%M:%S'))
        _save(rows)


def extract(rows):
    import numpy as np
    import tifffile
    man = []
    for n, r in rows.items():
        if not r.get('sha256'):
            continue
        cnt = 0
        with zipfile.ZipFile(r['path']) as z:
            for m in z.infolist():
                parts = m.filename.replace('\\', '/').split('/')
                if m.is_dir() or len(parts) < 3 or parts[-2] != 'SEG' or not parts[-3].endswith('_GT'):
                    continue
                fn = parts[-1]
                if not (fn.startswith('man_seg') and fn.lower().endswith(('.tif', '.tiff'))):
                    continue
                seq = parts[-3]
                out = os.path.join(DATA, n, seq, 'SEG', fn)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, 'wb') as f:
                    f.write(z.read(m))
                with tifffile.TiffFile(out) as t:
                    pages = len(t.pages)
                    a = t.asarray()
                ok2d = pages == 1 and a.ndim == 2
                rec = {'input_id': '%s/%s/%s' % (n, seq, fn), 'dataset': n + '_GT_SEG', 'group': '%s/%s' % (n, seq),
                       'split': 'test', 'native_uint16': 'true' if a.dtype == np.uint16 else 'false',
                       'path': os.path.relpath(out, ROOT).replace(os.sep, '/'), 'synthetic': str(r['synthetic']).lower(),
                       'dtype': str(a.dtype), 'shape': 'x'.join(map(str, a.shape)), 'pages': pages}
                if not ok2d or a.dtype not in (np.uint8, np.uint16):
                    rec['excluded'] = 'not 2D single-page uint8/uint16'
                man.append(rec)
                cnt += 1
        r['gt_seg_maps'] = cnt
    good = [m for m in man if 'excluded' not in m]
    with open(os.path.join(ROOT, 'test_manifest.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['input_id', 'dataset', 'group', 'split', 'native_uint16', 'path', 'synthetic'],
                           extrasaction='ignore')
        w.writeheader()
        w.writerows(sorted(good, key=lambda m: m['input_id']))
    with open(os.path.join(DL, 'test_inventory.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['input_id', 'dataset', 'group', 'dtype', 'shape', 'pages', 'native_uint16',
                                          'synthetic', 'excluded'], extrasaction='ignore')
        w.writeheader()
        w.writerows(sorted(man, key=lambda m: m['input_id']))
    _save(rows)
    print('manifest: %d maps (%d excluded)' % (len(good), len(man) - len(good)))


def _save(rows):
    os.makedirs(DL, exist_ok=True)
    with open(STATUS, 'w', encoding='utf-8') as f:
        json.dump({'updated': time.strftime('%Y-%m-%d %H:%M:%S'), 'datasets': rows,
                   'note': 'CTC terms of use to be checked by the user; cite CTC and the dataset sources.'}, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--plan', action='store_true')
    g.add_argument('--download', action='store_true')
    g.add_argument('--extract', action='store_true')
    a = ap.parse_args()
    if a.plan:
        rows = plan()
        _save(rows)
        for n, r in rows.items():
            print('%-16s %-9s %-10s %s %s' % (n, 'OK' if r['available'] else 'UNAVAIL', 'select' if r['selected'] else '-',
                                             ('%.1f MB' % (r['bytes'] / 1e6)) if r['bytes'] else '', r['source'] or ''))
        return
    with open(STATUS, encoding='utf-8') as f:
        rows = json.load(f)['datasets']
    if a.download:
        download(rows)
    else:
        extract(rows)


if __name__ == '__main__':
    sys.exit(main())
