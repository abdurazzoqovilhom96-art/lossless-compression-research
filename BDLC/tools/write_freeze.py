"""Write or verify freeze.json: SHA-256 of the frozen BDLC codec files and its constants.

Usage:
  python tools/write_freeze.py           # writes freeze.json (refuses to overwrite a different freeze)
  python tools/write_freeze.py --check   # exit 1 if any frozen file changed
"""
import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FILES = ['bdlc/core.py', 'bdlc/api.py', 'bdlc/__init__.py', 'bdlc/init_v1.npz', 'legacy_rvc.py']
CONSTS = ['NMAX', 'DMAX', 'PMAX', 'REL_CTX', 'WIN_PRED', 'H_SLOPE', 'LEFT_CTX', 'NCTX', 'EG_W']


def sha_file(rel):
    with open(os.path.join(ROOT, rel), 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def current():
    from bdlc import api, core
    return {
        'codec': 'BDLC v1 (stream version %d)' % api.VERSION,
        'files_sha256': {f: sha_file(f) for f in FILES},
        'T1_table_sha256_q0_n0_int64le': api.T1_SHA256,
        'constants': {c: int(getattr(core, c)) for c in CONSTS},
        'model_ids': {'1': 'T1 frozen initial table (strength 32)', '2': 'uniform initial table', '3': 'external table (research)'},
        'flags': {'1': 'F_NOSLOPE', '2': 'F_NOK2', '4': 'F_NOPASS'},
        'legacy_rvc_note': 'legacy_rvc.py is a byte-identical copy of ../codec.py (old RVC codec)',
        'development_tuning': 'T1 and REL_CTX were selected on the 52 development maps; every tried variant is in dev_log.csv',
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    path = os.path.join(ROOT, 'freeze.json')
    cur = current()
    if a.check or os.path.exists(path):
        if not os.path.exists(path):
            print('freeze.json missing')
            return 1
        with open(path, encoding='utf-8') as f:
            old = json.load(f)
        bad = [k for k in ('files_sha256', 'T1_table_sha256_q0_n0_int64le', 'constants') if old.get(k) != cur[k]]
        if bad:
            print('FREEZE MISMATCH:', bad)
            for f, h in cur['files_sha256'].items():
                if old.get('files_sha256', {}).get(f) != h:
                    print('  changed:', f)
            return 1
        print('freeze OK (%s)' % old.get('frozen_at'))
        return 0
    cur['frozen_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cur, f, indent=2)
    print('wrote', path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
