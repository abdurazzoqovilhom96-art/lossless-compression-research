"""Summarizes the size-phase shard files of a run, so that the shard files need not be published.

    python -I posthoc/summarize_shards.py RUN_FOLDER OUTPUT_JSON

In the size phase every worker wrote raw_size/shards/<codec>_<n>.json and verification/shards/<codec>_<n>.json; the
harness merged them into raw_size/<codec>.json and verification/<codec>.json. This script checks that every record
(images, errors, not_applicable) of every shard appears identically in the merged files, and writes the remaining
shard fields (codec, shard number, worker pin, Python, start and end time, record counts) to OUTPUT_JSON.
It refuses to write anything if a single record is missing.
"""
import collections
import glob
import json
import os
import sys

run, out = sys.argv[1], sys.argv[2]
FIELDS = {'raw_size': ('images', 'errors', 'not_applicable'), 'verification': ('images',)}
meta = []
for sub, fields in FIELDS.items():
    merged = {os.path.basename(p)[:-5]: json.load(open(p, encoding='utf-8'))
              for p in glob.glob(os.path.join(run, sub, '*.json'))}
    seen = collections.defaultdict(collections.Counter)
    for p in sorted(glob.glob(os.path.join(run, sub, 'shards', '*.json'))):
        s = json.load(open(p, encoding='utf-8'))
        for f in fields:
            for rec in s.get(f, []):
                seen[(s['codec'], f)][json.dumps(rec, sort_keys=True)] += 1
        if sub == 'raw_size':
            meta.append({'file': os.path.basename(p), 'codec': s['codec'], 'shard': s.get('shard'), 'pin': s.get('pin'),
                         'python': s.get('python'), 'started': s.get('started'), 'finished': s.get('finished'),
                         'images': len(s.get('images', [])), 'errors': len(s.get('errors', [])),
                         'not_applicable': len(s.get('not_applicable', []))})
        else:
            extra = set(s) - set(fields) - {'codec', 'mode'}
            assert not extra, (p, extra)
    for codec, m in merged.items():
        for f in fields:
            mine = collections.Counter(json.dumps(r, sort_keys=True) for r in m.get(f, []))
            assert mine == seen[(codec, f)], (sub, codec, f)
    assert {c for c, _ in seen} <= set(merged), 'shard of a codec without merged file'
with open(out, 'w', encoding='utf-8', newline='\n') as f:
    json.dump({'run': os.path.basename(os.path.normpath(run)),
               'note': 'Size-phase shards; all their records are in raw_size/<codec>.json and verification/<codec>.json.',
               'shards': meta}, f, indent=1)
print(out, len(meta), 'shards, all records present in the merged files')
